from __future__ import annotations

import base64
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.config import ConfigStore
from services.feishu_alert_service import FeishuAlertService, _feishu_sign


class FeishuAlertConfigTests(unittest.TestCase):
    def test_settings_are_sanitized_and_secret_is_preserved_on_empty_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "config.json"
            path.write_text(json.dumps({"auth-key": "test-auth"}), encoding="utf-8")
            store = ConfigStore(path)

            store.update(
                {
                    "feishu_alert": {
                        "enabled": True,
                        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/abcdef",
                        "secret": "secret-value",
                    }
                }
            )
            public = store.get()["feishu_alert"]

            self.assertEqual(public["webhook_url"], "https://open.feishu.cn/open-apis/bot/v2/hook/****cdef")
            self.assertTrue(public["secret_configured"])
            self.assertEqual(public["secret"], "")

            store.update(
                {
                    "feishu_alert": {
                        "enabled": True,
                        "webhook_configured": True,
                        "webhook_url": "",
                        "secret_configured": True,
                        "secret": "",
                    }
                }
            )

            raw = store.get_feishu_alert_settings(raw=True)
            self.assertEqual(raw["webhook_url"], "https://open.feishu.cn/open-apis/bot/v2/hook/abcdef")
            self.assertEqual(raw["secret"], "secret-value")


class FeishuAlertServiceTests(unittest.TestCase):
    def test_feishu_signature_matches_expected_algorithm(self) -> None:
        timestamp = "1710000000"
        secret = "abc"
        expected = base64.b64encode(
            hmac.new(f"{timestamp}\n{secret}".encode("utf-8"), b"", hashlib.sha256).digest()
        ).decode("utf-8")

        self.assertEqual(_feishu_sign(timestamp, secret), expected)

    def test_build_payload_includes_interactive_card_and_signature(self) -> None:
        service = FeishuAlertService()
        settings = {
            "keyword": "账号池告警",
            "secret": "abc",
            "include_register_status": True,
            "include_manage_link": False,
        }
        event = {
            "event_type": "triggered",
            "severity": "warning",
            "title": "存活率低，已自动启动注册机",
            "message": "账号池存活率 10.0% 低于阈值 20%",
            "total_accounts": 10,
            "alive_accounts": 1,
            "alive_rate": 10.0,
            "threshold": 20,
            "occurred_at": "2026-06-29T10:00:00+00:00",
            "cooldown_remaining_seconds": 1800,
            "register_running": True,
            "register_mode": "available",
            "register_target_available": 10,
            "register_target_quota": 100,
            "suggestion": "观察注册机运行结果",
        }

        payload = service._build_payload(settings, event)

        self.assertEqual(payload["msg_type"], "interactive")
        self.assertIn("timestamp", payload)
        self.assertIn("sign", payload)
        self.assertEqual(payload["card"]["header"]["template"], "orange")
        self.assertIn("[账号池告警]", payload["card"]["header"]["title"]["content"])

    def test_cooldown_skips_same_fingerprint(self) -> None:
        service = FeishuAlertService()
        with patch("services.feishu_alert_service.config") as fake_config, \
             patch.object(service, "_post", return_value={"ok": True, "status": 200, "code": 0, "message": "success"}), \
             patch("services.feishu_alert_service.save_feishu_alert_state", side_effect=lambda state: state):
            fake_config.get_feishu_alert_settings.return_value = {
                "enabled": True,
                "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/abcdef",
                "secret": "",
                "keyword": "账号池告警",
                "notify_events": ["triggered"],
                "alert_cooldown_minutes": 30,
                "recovery_notify": True,
                "include_register_status": True,
                "include_manage_link": False,
            }
            fake_config.base_url = ""
            event = {
                "event_type": "triggered",
                "severity": "warning",
                "title": "存活率低，已自动启动注册机",
                "message": "账号池存活率 10.0% 低于阈值 20%",
                "total_accounts": 10,
                "alive_accounts": 1,
                "alive_rate": 10.0,
                "threshold": 20,
                "occurred_at": "2026-06-29T10:00:00+00:00",
                "cooldown_remaining_seconds": 1800,
                "register_running": True,
                "register_mode": "available",
                "register_target_available": 10,
                "register_target_quota": 100,
                "suggestion": "观察注册机运行结果",
            }

            first = service.notify_account_pool_event(event)
            second = service.notify_account_pool_event(event)

        self.assertTrue(first["ok"])
        self.assertTrue(second["skipped"])
        self.assertEqual(second["reason"], "cooldown")


if __name__ == "__main__":
    unittest.main()
