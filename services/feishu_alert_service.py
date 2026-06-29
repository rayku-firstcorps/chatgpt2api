from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any

import requests

from services.config import config, load_feishu_alert_state, save_feishu_alert_state
from services.log_service import LOG_TYPE_ALERT, log_service
from services.register_service import register_service


ALERT_EVENT_META = {
    "triggered": {
        "severity": "warning",
        "template": "orange",
        "title": "存活率低，已自动启动注册机",
        "suggestion": "观察注册机运行结果；如果失败数持续上升，请检查邮箱 provider、代理和上游风控。",
    },
    "skipped_register_config": {
        "severity": "critical",
        "template": "red",
        "title": "存活率低，但注册机配置不完整",
        "suggestion": "请尽快检查注册机邮箱 provider、代理、线程数等基础配置，修复后再观察账号池恢复情况。",
    },
    "error": {
        "severity": "critical",
        "template": "red",
        "title": "账号池健康检查异常",
        "suggestion": "请检查服务日志、账号存储状态和健康守护线程是否持续报错。",
    },
    "skipped_register_running": {
        "severity": "info",
        "template": "blue",
        "title": "注册机运行中，已跳过重复触发",
        "suggestion": "继续观察注册机运行结果；如账号池长时间不恢复，请检查注册任务失败原因。",
    },
    "skipped_cooldown": {
        "severity": "warning",
        "template": "yellow",
        "title": "存活率低，处于自动触发冷却期",
        "suggestion": "当前仍受冷却保护，不会重复启动注册机；如影响业务，请人工检查注册机状态。",
    },
    "healthy_recovered": {
        "severity": "success",
        "template": "green",
        "title": "账号池已恢复健康",
        "suggestion": "账号池存活率已回到阈值以上，可继续观察后续趋势。",
    },
    "healthy": {
        "severity": "success",
        "template": "green",
        "title": "账号池健康",
        "suggestion": "无需处理。",
    },
    "skipped_min_sample": {
        "severity": "info",
        "template": "blue",
        "title": "账号池样本数不足，已跳过",
        "suggestion": "如这是新部署环境，可先导入账号或开启空池触发策略。",
    },
    "disabled": {
        "severity": "info",
        "template": "blue",
        "title": "账号池健康守护未启用",
        "suggestion": "如需自动补号和告警，请在系统设置中启用账号池健康守护。",
    },
}

RECOVERY_SOURCE_EVENTS = {"triggered", "skipped_register_config", "skipped_cooldown", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _format_time(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "无"
    parsed = _parse_time(text)
    if parsed is None:
        return text
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _duration_text(seconds: int) -> str:
    if seconds <= 0:
        return "无"
    minutes = max(1, int((seconds + 59) // 60))
    return f"{minutes} 分钟"


def _rate_bucket(rate: float) -> str:
    floor = int(max(0, rate) // 5) * 5
    return f"{floor}-{floor + 5}"


def _feishu_sign(timestamp: str, secret: str) -> str:
    key = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(key, b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class FeishuAlertService:
    def __init__(self) -> None:
        self._state = load_feishu_alert_state()

    def get_status(self) -> dict[str, Any]:
        return {
            "config": config.get_feishu_alert_settings(),
            "state": dict(self._state),
        }

    def notify_account_pool_event(self, event: dict[str, Any]) -> dict[str, Any]:
        settings = config.get_feishu_alert_settings(raw=True)
        if not bool(settings.get("enabled")):
            return {"ok": False, "skipped": True, "reason": "disabled"}
        if not str(settings.get("webhook_url") or "").strip():
            self._log_skip(event, "飞书告警 Webhook 未配置")
            return {"ok": False, "skipped": True, "reason": "webhook_missing"}

        event = self._maybe_recovery_event(event, settings)
        event_type = str(event.get("event_type") or "")
        if event_type not in settings.get("notify_events", []):
            if event_type not in {"healthy", "disabled"}:
                self._log_skip(event, "事件未订阅")
            return {"ok": False, "skipped": True, "reason": "event_not_subscribed"}

        fingerprint = self._fingerprint(event)
        if self._is_in_cooldown(fingerprint, int(settings.get("alert_cooldown_minutes") or 0)):
            self._log_skip(event, "同类事件处于飞书告警冷却期")
            return {"ok": False, "skipped": True, "reason": "cooldown", "fingerprint": fingerprint}

        return self._send_event(settings, event, fingerprint)

    def send_test(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = config.get_feishu_alert_settings(raw=True)
        for key, value in (overrides or {}).items():
            if key in {"webhook_url", "secret"} and not str(value or "").strip():
                continue
            settings[key] = value
        settings["keyword"] = str(settings.get("keyword") or "账号池告警").strip() or "账号池告警"
        if not str(settings.get("webhook_url") or "").strip():
            raise ValueError("请先填写飞书 Webhook 地址")
        event = {
            "event_id": f"account_pool_guard:test:{_now()}",
            "event_type": "triggered",
            "severity": "warning",
            "occurred_at": _now(),
            "title": "飞书告警测试",
            "message": "这是一条账号池飞书告警测试消息",
            "total_accounts": 27,
            "alive_accounts": 5,
            "alive_rate": 18.5,
            "threshold": 20,
            "register_running": False,
            "register_mode": "available",
            "register_target_available": 10,
            "register_target_quota": 100,
            "cooldown_remaining_seconds": 0,
            "suggestion": "如果你能看到这张卡片，说明飞书 Webhook 配置可用。",
        }
        payload = self._build_payload(settings, event)
        result = self._post(settings, payload)
        if result["ok"]:
            log_service.add(LOG_TYPE_ALERT, "飞书测试告警发送成功", {"response_code": result.get("code")})
        else:
            log_service.add(LOG_TYPE_ALERT, "飞书测试告警发送失败", {"error": result.get("error")})
        return result

    def build_account_pool_event(
        self,
        *,
        action: str,
        message: str,
        settings: dict[str, Any],
        health: dict[str, Any],
        state: dict[str, Any],
        cooldown_remaining_seconds: int,
    ) -> dict[str, Any]:
        meta = ALERT_EVENT_META.get(action, ALERT_EVENT_META["error"])
        register = register_service.get()
        return {
            "event_id": f"account_pool_guard:{action}:{state.get('last_checked_at') or _now()}",
            "event_type": action,
            "severity": meta["severity"],
            "occurred_at": state.get("last_checked_at") or _now(),
            "title": meta["title"],
            "message": message,
            "total_accounts": int(health.get("total_accounts") or 0),
            "alive_accounts": int(health.get("alive_accounts") or 0),
            "alive_rate": float(health.get("alive_rate") or 0),
            "threshold": int(settings.get("alive_rate_threshold") or 20),
            "register_running": register_service.is_running(),
            "register_mode": str(settings.get("register_mode") or register.get("mode") or "available"),
            "register_target_available": int(settings.get("register_target_available") or register.get("target_available") or 10),
            "register_target_quota": int(settings.get("register_target_quota") or register.get("target_quota") or 100),
            "cooldown_remaining_seconds": cooldown_remaining_seconds,
            "suggestion": meta["suggestion"],
        }

    def _maybe_recovery_event(self, event: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        event_type = str(event.get("event_type") or "")
        previous_event = str(self._state.get("last_event_type") or "")
        if (
            event_type == "healthy"
            and bool(settings.get("recovery_notify"))
            and previous_event in RECOVERY_SOURCE_EVENTS
        ):
            meta = ALERT_EVENT_META["healthy_recovered"]
            return {
                **event,
                "event_id": f"account_pool_guard:healthy_recovered:{event.get('occurred_at') or _now()}",
                "event_type": "healthy_recovered",
                "severity": meta["severity"],
                "title": meta["title"],
                "message": "账号池存活率已恢复到阈值以上",
                "suggestion": meta["suggestion"],
            }
        return event

    def _send_event(self, settings: dict[str, Any], event: dict[str, Any], fingerprint: str) -> dict[str, Any]:
        payload = self._build_payload(settings, event)
        result = self._post(settings, payload)
        sent_at = _now()
        status = "success" if result["ok"] else "failed"
        self._state = save_feishu_alert_state(
            {
                **self._state,
                "last_sent_at": sent_at,
                "last_event_type": event.get("event_type"),
                "last_fingerprint": fingerprint,
                "last_status": status,
                "last_error": "" if result["ok"] else str(result.get("error") or ""),
                "last_response_code": int(result.get("code") or 0),
                "last_response_message": str(result.get("message") or ""),
                "last_recovered_at": sent_at if event.get("event_type") == "healthy_recovered" else self._state.get("last_recovered_at"),
                "recent_events": [
                    *list(self._state.get("recent_events") or [])[-49:],
                    {
                        "sent_at": sent_at,
                        "event_type": event.get("event_type"),
                        "status": status,
                        "fingerprint": fingerprint,
                    },
                ],
            }
        )
        summary = "飞书账号池告警发送成功" if result["ok"] else "飞书账号池告警发送失败"
        log_service.add(
            LOG_TYPE_ALERT,
            summary,
            {
                "event_type": event.get("event_type"),
                "severity": event.get("severity"),
                "fingerprint": fingerprint,
                "response_code": result.get("code"),
                "error": result.get("error"),
            },
        )
        return {"ok": result["ok"], "event": event, "fingerprint": fingerprint, **result}

    def _build_payload(self, settings: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        meta = ALERT_EVENT_META.get(str(event.get("event_type") or ""), ALERT_EVENT_META["error"])
        keyword = str(settings.get("keyword") or "账号池告警").strip() or "账号池告警"
        title = f"[{keyword}] {event.get('title') or meta['title']}"
        fields = [
            ("总账号数", str(event.get("total_accounts", 0))),
            ("存活账号数", str(event.get("alive_accounts", 0))),
            ("存活率", f"{float(event.get('alive_rate') or 0):.1f}%"),
            ("阈值", f"{int(event.get('threshold') or 0)}%"),
            ("冷却剩余", _duration_text(int(event.get("cooldown_remaining_seconds") or 0))),
            ("发生时间", _format_time(event.get("occurred_at"))),
        ]
        elements: list[dict[str, Any]] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**事件**：{event.get('message') or title}\n**级别**：{event.get('severity')}",
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            },
        ]
        if bool(settings.get("include_register_status")):
            target = (
                f"目标正常账号数 {event.get('register_target_available')}"
                if event.get("register_mode") == "available"
                else f"目标剩余额度 {event.get('register_target_quota')}"
                if event.get("register_mode") == "quota"
                else "沿用注册机总数"
            )
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**注册机**：{'运行中' if event.get('register_running') else '空闲'} / 模式 {event.get('register_mode')} / {target}",
                    },
                }
            )
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**建议**：{event.get('suggestion') or meta['suggestion']}",
                },
            }
        )
        manage_url = self._manage_url(settings)
        if manage_url:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "打开系统设置"},
                            "type": "default",
                            "url": manage_url,
                        }
                    ],
                }
            )
        payload: dict[str, Any] = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": meta["template"],
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": elements,
            },
        }
        secret = str(settings.get("secret") or "").strip()
        if secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = _feishu_sign(timestamp, secret)
        return payload

    def _post(self, settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        webhook_url = str(settings.get("webhook_url") or "").strip()
        try:
            response = requests.post(webhook_url, json=payload, timeout=5)
        except Exception as exc:
            return {"ok": False, "status": 0, "code": 0, "message": "", "error": str(exc)}
        try:
            data = response.json()
        except Exception:
            data = {}
        code = int(data.get("code") or data.get("StatusCode") or 0)
        message = str(data.get("msg") or data.get("message") or data.get("StatusMessage") or "")
        ok = 200 <= response.status_code < 300 and code == 0
        return {
            "ok": ok,
            "status": response.status_code,
            "code": code,
            "message": message,
            "error": "" if ok else message or response.text[:300],
        }

    def _fingerprint(self, event: dict[str, Any]) -> str:
        return ":".join(
            [
                str(event.get("event_type") or ""),
                str(event.get("severity") or ""),
                str(event.get("threshold") or ""),
                str(event.get("register_mode") or ""),
                _rate_bucket(float(event.get("alive_rate") or 0)),
            ]
        )

    def _is_in_cooldown(self, fingerprint: str, cooldown_minutes: int) -> bool:
        if cooldown_minutes <= 0:
            return False
        if fingerprint != str(self._state.get("last_fingerprint") or ""):
            return False
        last_sent_at = _parse_time(self._state.get("last_sent_at"))
        if last_sent_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last_sent_at).total_seconds()
        return elapsed < cooldown_minutes * 60

    def _log_skip(self, event: dict[str, Any], reason: str) -> None:
        log_service.add(
            LOG_TYPE_ALERT,
            "飞书账号池告警跳过",
            {
                "event_type": event.get("event_type"),
                "reason": reason,
            },
        )

    def _manage_url(self, settings: dict[str, Any]) -> str:
        if not bool(settings.get("include_manage_link")):
            return ""
        base_url = config.base_url
        return f"{base_url}/settings" if base_url else ""


feishu_alert_service = FeishuAlertService()
