from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.account_service import AccountService
from services.account_pool_guard_service import AccountPoolGuardService
from services.storage.json_storage import JSONStorageBackend


class FakeConfig:
    def __init__(self, settings: dict):
        self.settings = settings

    def get_account_pool_guard_settings(self) -> dict:
        return dict(self.settings)


class FakeRegisterService:
    def __init__(self, *, running: bool = False, ready: bool = True):
        self.running = running
        self.ready = ready
        self.started = 0
        self.last_guard_config: dict | None = None

    def is_running(self) -> bool:
        return self.running

    def validate_ready(self) -> tuple[bool, str]:
        return self.ready, "" if self.ready else "注册机邮箱 provider 未配置或未启用"

    def start_from_guard(self, guard_config: dict) -> dict:
        self.started += 1
        self.running = True
        self.last_guard_config = dict(guard_config)
        return {"enabled": True}


class AccountPoolGuardTests(unittest.TestCase):
    def test_pool_health_counts_image_available_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = AccountService(JSONStorageBackend(Path(tmp_dir) / "accounts.json"))
            service.add_account_items(
                [
                    {"access_token": "ok-1", "status": "正常", "quota": 3},
                    {"access_token": "ok-2", "status": "正常", "quota": 0, "image_quota_unknown": True},
                    {"access_token": "limited", "status": "限流", "quota": 10},
                    {"access_token": "invalid", "status": "异常", "quota": 10},
                    {"access_token": "empty", "status": "正常", "quota": 0},
                ]
            )

            self.assertEqual(
                service.get_pool_health(),
                {"total_accounts": 5, "alive_accounts": 2, "alive_rate": 40.0},
            )

    def test_guard_triggers_when_alive_rate_is_below_threshold(self) -> None:
        settings = {
            "enabled": True,
            "check_interval_minutes": 5,
            "alive_rate_threshold": 20,
            "min_total_accounts": 5,
            "trigger_cooldown_minutes": 30,
            "allow_empty_pool_trigger": False,
            "register_mode": "available",
            "register_target_available": 10,
            "register_target_quota": 100,
        }
        fake_register = FakeRegisterService()
        with patch("services.account_pool_guard_service.config", FakeConfig(settings)), \
             patch("services.account_pool_guard_service.account_service") as fake_accounts, \
             patch("services.account_pool_guard_service.register_service", fake_register), \
             patch("services.account_pool_guard_service.save_account_pool_guard_state", side_effect=lambda state: state), \
             patch("services.account_pool_guard_service.load_account_pool_guard_state", return_value={}):
            fake_accounts.get_pool_health.return_value = {
                "total_accounts": 10,
                "alive_accounts": 1,
                "alive_rate": 10.0,
            }
            service = AccountPoolGuardService()

            result = service.run_once()

        self.assertEqual(fake_register.started, 1)
        self.assertEqual(result["state"]["last_action"], "triggered")
        self.assertEqual(fake_register.last_guard_config["register_mode"], "available")

    def test_guard_skips_empty_pool_unless_allowed(self) -> None:
        settings = {
            "enabled": True,
            "check_interval_minutes": 5,
            "alive_rate_threshold": 20,
            "min_total_accounts": 5,
            "trigger_cooldown_minutes": 30,
            "allow_empty_pool_trigger": False,
            "register_mode": "available",
            "register_target_available": 10,
            "register_target_quota": 100,
        }
        fake_register = FakeRegisterService()
        with patch("services.account_pool_guard_service.config", FakeConfig(settings)), \
             patch("services.account_pool_guard_service.account_service") as fake_accounts, \
             patch("services.account_pool_guard_service.register_service", fake_register), \
             patch("services.account_pool_guard_service.save_account_pool_guard_state", side_effect=lambda state: state), \
             patch("services.account_pool_guard_service.load_account_pool_guard_state", return_value={}):
            fake_accounts.get_pool_health.return_value = {
                "total_accounts": 0,
                "alive_accounts": 0,
                "alive_rate": 0.0,
            }
            service = AccountPoolGuardService()

            result = service.run_once()

        self.assertEqual(fake_register.started, 0)
        self.assertEqual(result["state"]["last_action"], "skipped_min_sample")

    def test_guard_cooldown_prevents_repeated_trigger(self) -> None:
        settings = {
            "enabled": True,
            "check_interval_minutes": 5,
            "alive_rate_threshold": 20,
            "min_total_accounts": 5,
            "trigger_cooldown_minutes": 30,
            "allow_empty_pool_trigger": False,
            "register_mode": "available",
            "register_target_available": 10,
            "register_target_quota": 100,
        }
        fake_register = FakeRegisterService()
        with patch("services.account_pool_guard_service.config", FakeConfig(settings)), \
             patch("services.account_pool_guard_service.account_service") as fake_accounts, \
             patch("services.account_pool_guard_service.register_service", fake_register), \
             patch("services.account_pool_guard_service.save_account_pool_guard_state", side_effect=lambda state: state), \
             patch("services.account_pool_guard_service.load_account_pool_guard_state", return_value={}):
            fake_accounts.get_pool_health.return_value = {
                "total_accounts": 10,
                "alive_accounts": 1,
                "alive_rate": 10.0,
            }
            service = AccountPoolGuardService()
            service.run_once()
            fake_register.running = False

            result = service.run_once()

        self.assertEqual(fake_register.started, 1)
        self.assertEqual(result["state"]["last_action"], "skipped_cooldown")


if __name__ == "__main__":
    unittest.main()
