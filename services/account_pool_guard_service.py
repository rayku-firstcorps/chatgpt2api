from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from services.account_service import account_service
from services.config import config, load_account_pool_guard_state, save_account_pool_guard_state
from services.log_service import LOG_TYPE_ACCOUNT, log_service
from services.register_service import register_service


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


class AccountPoolGuardService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = load_account_pool_guard_state()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="account-pool-guard")
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread:
            thread.join(timeout=1)

    def get_status(self) -> dict[str, Any]:
        settings = config.get_account_pool_guard_settings()
        state = self._get_state()
        return {
            "config": settings,
            "state": state,
            "cooldown_remaining_seconds": self._cooldown_remaining_seconds(settings, state),
            "register_running": register_service.is_running(),
        }

    def run_once(self) -> dict[str, Any]:
        settings = config.get_account_pool_guard_settings()
        if not settings.get("enabled"):
            health = account_service.get_pool_health()
            return self._record(settings, health, "disabled", "账号池健康守护未启用")

        health = account_service.get_pool_health()
        total_accounts = int(health["total_accounts"])
        alive_rate = float(health["alive_rate"])
        threshold = int(settings["alive_rate_threshold"])

        if register_service.is_running():
            return self._record(settings, health, "skipped_register_running", "已跳过，注册机运行中")

        cooldown_remaining = self._cooldown_remaining_seconds(settings, self._get_state())
        if cooldown_remaining > 0:
            minutes = max(1, int((cooldown_remaining + 59) // 60))
            return self._record(settings, health, "skipped_cooldown", f"已跳过，自动触发冷却剩余约 {minutes} 分钟")

        if not self._pool_size_can_trigger(settings, total_accounts):
            min_total = int(settings["min_total_accounts"])
            return self._record(
                settings,
                health,
                "skipped_min_sample",
                f"账号池总数 {total_accounts} 低于最小样本数 {min_total}，未触发注册机",
            )

        if alive_rate >= threshold:
            return self._record(
                settings,
                health,
                "healthy",
                f"账号池存活率 {alive_rate:.1f}% 高于或等于阈值 {threshold}%，无需补号",
            )

        ready, reason = register_service.validate_ready()
        if not ready:
            return self._record(settings, health, "skipped_register_config", reason)

        result = register_service.start_from_guard(settings)
        detail = {
            "total_accounts": total_accounts,
            "alive_accounts": int(health["alive_accounts"]),
            "alive_rate": alive_rate,
            "threshold": threshold,
            "register_mode": settings["register_mode"],
            "target_available": settings["register_target_available"],
            "target_quota": settings["register_target_quota"],
        }
        log_service.add(LOG_TYPE_ACCOUNT, "账号池健康守护触发注册机", detail)
        return self._record(
            settings,
            health,
            "triggered",
            f"账号池存活率 {alive_rate:.1f}% 低于阈值 {threshold}%，已自动启动注册机",
            triggered=True,
            extra={"register": result},
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            settings = config.get_account_pool_guard_settings()
            interval_seconds = max(1, int(settings["check_interval_minutes"])) * 60
            try:
                self.run_once()
            except Exception as exc:
                log_service.add(LOG_TYPE_ACCOUNT, "账号池健康守护检查异常", {"error": str(exc)})
                health = account_service.get_pool_health()
                self._record(settings, health, "error", f"健康检查异常：{exc}")
            self._stop_event.wait(interval_seconds)

    def _record(
        self,
        settings: dict[str, Any],
        health: dict[str, Any],
        action: str,
        message: str,
        *,
        triggered: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        next_state = {
            **self._get_state(),
            "last_checked_at": _now(),
            "last_alive_rate": float(health["alive_rate"]),
            "last_total_accounts": int(health["total_accounts"]),
            "last_alive_accounts": int(health["alive_accounts"]),
            "last_action": action,
            "last_message": message,
        }
        if triggered:
            next_state["last_triggered_at"] = next_state["last_checked_at"]
        with self._lock:
            self._state = save_account_pool_guard_state(next_state)

        self._notify_alert(settings, health, action, message)

        if action.startswith("skipped_"):
            log_service.add(
                LOG_TYPE_ACCOUNT,
                "账号池健康守护跳过注册机",
                {
                    "action": action,
                    "message": message,
                    "total_accounts": int(health["total_accounts"]),
                    "alive_accounts": int(health["alive_accounts"]),
                    "alive_rate": float(health["alive_rate"]),
                    "threshold": int(settings["alive_rate_threshold"]),
                },
            )
        return {**self.get_status(), **(extra or {})}

    def _notify_alert(
        self,
        settings: dict[str, Any],
        health: dict[str, Any],
        action: str,
        message: str,
    ) -> None:
        try:
            from services.feishu_alert_service import feishu_alert_service

            state = self._get_state()
            event = feishu_alert_service.build_account_pool_event(
                action=action,
                message=message,
                settings=settings,
                health=health,
                state=state,
                cooldown_remaining_seconds=self._cooldown_remaining_seconds(settings, state),
            )
            feishu_alert_service.notify_account_pool_event(event)
        except Exception as exc:
            log_service.add(LOG_TYPE_ACCOUNT, "飞书账号池告警处理异常", {"error": str(exc), "action": action})

    def _get_state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    @staticmethod
    def _pool_size_can_trigger(settings: dict[str, Any], total_accounts: int) -> bool:
        if total_accounts == 0:
            return bool(settings.get("allow_empty_pool_trigger"))
        return total_accounts >= int(settings["min_total_accounts"])

    @staticmethod
    def _cooldown_remaining_seconds(settings: dict[str, Any], state: dict[str, Any]) -> int:
        last_triggered_at = _parse_time(state.get("last_triggered_at"))
        if last_triggered_at is None:
            return 0
        cooldown_seconds = int(settings.get("trigger_cooldown_minutes") or 0) * 60
        if cooldown_seconds <= 0:
            return 0
        elapsed = (datetime.now(timezone.utc) - last_triggered_at).total_seconds()
        return max(0, int(cooldown_seconds - elapsed))


account_pool_guard_service = AccountPoolGuardService()
