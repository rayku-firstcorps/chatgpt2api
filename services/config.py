from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
from pathlib import Path
import time

from services.storage.base import StorageBackend

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"
VERSION_FILE = BASE_DIR / "VERSION"
BACKUP_STATE_FILE = DATA_DIR / "backup_state.json"
ACCOUNT_POOL_GUARD_STATE_FILE = DATA_DIR / "account_pool_guard_state.json"
FEISHU_ALERT_STATE_FILE = DATA_DIR / "feishu_alert_state.json"

DEFAULT_BACKUP_INCLUDE = {
    "config": True,
    "register": True,
    "cpa": True,
    "sub2api": True,
    "logs": True,
    "image_tasks": True,
    "accounts_snapshot": True,
    "auth_keys_snapshot": True,
    "images": False,
}

DEFAULT_IMAGE_STORAGE = {
    "enabled": False,
    "mode": "local",
    "webdav_url": "",
    "webdav_username": "",
    "webdav_password": "",
    "webdav_root_path": "chatgpt2api/images",
    "public_base_url": "",
}

DEFAULT_ACCOUNT_POOL_GUARD = {
    "enabled": False,
    "check_interval_minutes": 5,
    "alive_rate_threshold": 20,
    "min_total_accounts": 5,
    "trigger_cooldown_minutes": 30,
    "allow_empty_pool_trigger": False,
    "register_mode": "available",
    "register_target_available": 10,
    "register_target_quota": 100,
}

SUPPORTED_FEISHU_ALERT_EVENTS = {
    "triggered",
    "skipped_register_config",
    "error",
    "skipped_register_running",
    "skipped_cooldown",
    "healthy_recovered",
    "healthy",
    "skipped_min_sample",
    "disabled",
}

DEFAULT_FEISHU_ALERT_EVENTS = [
    "triggered",
    "skipped_register_config",
    "error",
    "healthy_recovered",
]

DEFAULT_FEISHU_ALERT = {
    "enabled": False,
    "webhook_url": "",
    "secret": "",
    "keyword": "账号池告警",
    "notify_events": DEFAULT_FEISHU_ALERT_EVENTS,
    "alert_cooldown_minutes": 30,
    "recovery_notify": True,
    "include_register_status": True,
    "include_manage_link": True,
}


def _normalize_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _normalize_positive_int(value: object, default: int, minimum: int = 0) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return max(minimum, normalized)


def _normalize_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_backup_include(value: object) -> dict[str, bool]:
    source = value if isinstance(value, dict) else {}
    normalized = dict(DEFAULT_BACKUP_INCLUDE)
    for key in normalized:
        normalized[key] = _normalize_bool(source.get(key), normalized[key])
    return normalized


def _normalize_backup_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    return {
        "enabled": _normalize_bool(source.get("enabled"), False),
        "provider": "cloudflare_r2",
        "account_id": str(source.get("account_id") or "").strip(),
        "access_key_id": str(source.get("access_key_id") or "").strip(),
        "secret_access_key": str(source.get("secret_access_key") or "").strip(),
        "bucket": str(source.get("bucket") or "").strip(),
        "prefix": str(source.get("prefix") or "backups").strip().strip("/") or "backups",
        "interval_minutes": _normalize_positive_int(source.get("interval_minutes"), 360, 1),
        "rotation_keep": _normalize_positive_int(source.get("rotation_keep"), 10, 0),
        "encrypt": _normalize_bool(source.get("encrypt"), False),
        "passphrase": str(source.get("passphrase") or "").strip(),
        "include": _normalize_backup_include(source.get("include")),
    }


def _normalize_backup_state(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    return {
        "last_started_at": str(source.get("last_started_at") or "").strip() or None,
        "last_finished_at": str(source.get("last_finished_at") or "").strip() or None,
        "last_status": str(source.get("last_status") or "idle").strip() or "idle",
        "last_error": str(source.get("last_error") or "").strip() or None,
        "last_object_key": str(source.get("last_object_key") or "").strip() or None,
    }


def _normalize_image_storage_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    mode = str(source.get("mode") or "local").strip().lower()
    if mode not in {"local", "webdav", "both"}:
        mode = "local"
    enabled = _normalize_bool(source.get("enabled"), False)
    if not enabled:
        mode = "local"
    root_path = str(source.get("webdav_root_path") or DEFAULT_IMAGE_STORAGE["webdav_root_path"]).strip().strip("/")
    return {
        "enabled": enabled,
        "mode": mode,
        "webdav_url": str(source.get("webdav_url") or "").strip().rstrip("/"),
        "webdav_username": str(source.get("webdav_username") or "").strip(),
        "webdav_password": str(source.get("webdav_password") or "").strip(),
        "webdav_root_path": root_path or str(DEFAULT_IMAGE_STORAGE["webdav_root_path"]),
        "public_base_url": str(source.get("public_base_url") or "").strip().rstrip("/"),
    }


def _normalize_account_pool_guard_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    register_mode = str(source.get("register_mode") or DEFAULT_ACCOUNT_POOL_GUARD["register_mode"]).strip().lower()
    if register_mode not in {"available", "quota", "total"}:
        register_mode = str(DEFAULT_ACCOUNT_POOL_GUARD["register_mode"])
    return {
        "enabled": _normalize_bool(source.get("enabled"), False),
        "check_interval_minutes": _normalize_positive_int(
            source.get("check_interval_minutes"),
            int(DEFAULT_ACCOUNT_POOL_GUARD["check_interval_minutes"]),
            1,
        ),
        "alive_rate_threshold": min(
            100,
            _normalize_positive_int(
                source.get("alive_rate_threshold"),
                int(DEFAULT_ACCOUNT_POOL_GUARD["alive_rate_threshold"]),
                1,
            ),
        ),
        "min_total_accounts": _normalize_positive_int(
            source.get("min_total_accounts"),
            int(DEFAULT_ACCOUNT_POOL_GUARD["min_total_accounts"]),
            0,
        ),
        "trigger_cooldown_minutes": _normalize_positive_int(
            source.get("trigger_cooldown_minutes"),
            int(DEFAULT_ACCOUNT_POOL_GUARD["trigger_cooldown_minutes"]),
            0,
        ),
        "allow_empty_pool_trigger": _normalize_bool(source.get("allow_empty_pool_trigger"), False),
        "register_mode": register_mode,
        "register_target_available": _normalize_positive_int(
            source.get("register_target_available"),
            int(DEFAULT_ACCOUNT_POOL_GUARD["register_target_available"]),
            1,
        ),
        "register_target_quota": _normalize_positive_int(
            source.get("register_target_quota"),
            int(DEFAULT_ACCOUNT_POOL_GUARD["register_target_quota"]),
            1,
        ),
    }


def _normalize_account_pool_guard_state(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    return {
        "last_checked_at": str(source.get("last_checked_at") or "").strip() or None,
        "last_triggered_at": str(source.get("last_triggered_at") or "").strip() or None,
        "last_alive_rate": _normalize_float(source.get("last_alive_rate"), 0.0),
        "last_total_accounts": _normalize_positive_int(source.get("last_total_accounts"), 0, 0),
        "last_alive_accounts": _normalize_positive_int(source.get("last_alive_accounts"), 0, 0),
        "last_action": str(source.get("last_action") or "idle").strip() or "idle",
        "last_message": str(source.get("last_message") or "").strip(),
    }


def _normalize_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for raw in value if (item := str(raw or "").strip())]
    return []


def _mask_webhook_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    prefix, _, suffix = text.rpartition("/")
    if not prefix:
        return "****"
    tail = suffix[-4:] if len(suffix) >= 4 else suffix
    return f"{prefix}/****{tail}"


def _normalize_feishu_alert_settings(value: object, current: object = None) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    current_source = current if isinstance(current, dict) else {}

    webhook_url = str(source.get("webhook_url") or "").strip()
    if not webhook_url and bool(source.get("webhook_configured")):
        webhook_url = str(current_source.get("webhook_url") or "").strip()

    secret = str(source.get("secret") or "").strip()
    if not secret and bool(source.get("secret_configured")):
        secret = str(current_source.get("secret") or "").strip()
    if _normalize_bool(source.get("clear_secret"), False):
        secret = ""

    keyword = str(source.get("keyword") or DEFAULT_FEISHU_ALERT["keyword"]).strip()
    if len(keyword) > 30:
        keyword = keyword[:30]
    notify_events = [
        event
        for event in _normalize_string_list(source.get("notify_events"))
        if event in SUPPORTED_FEISHU_ALERT_EVENTS
    ] or list(DEFAULT_FEISHU_ALERT_EVENTS)

    return {
        "enabled": _normalize_bool(source.get("enabled"), False),
        "webhook_url": webhook_url,
        "secret": secret,
        "keyword": keyword or str(DEFAULT_FEISHU_ALERT["keyword"]),
        "notify_events": notify_events,
        "alert_cooldown_minutes": _normalize_positive_int(
            source.get("alert_cooldown_minutes"),
            int(DEFAULT_FEISHU_ALERT["alert_cooldown_minutes"]),
            0,
        ),
        "recovery_notify": _normalize_bool(source.get("recovery_notify"), True),
        "include_register_status": _normalize_bool(source.get("include_register_status"), True),
        "include_manage_link": _normalize_bool(source.get("include_manage_link"), True),
    }


def _sanitize_feishu_alert_settings(settings: dict[str, object]) -> dict[str, object]:
    return {
        **{key: value for key, value in settings.items() if key != "secret"},
        "webhook_url": _mask_webhook_url(settings.get("webhook_url")),
        "webhook_configured": bool(str(settings.get("webhook_url") or "").strip()),
        "secret": "",
        "secret_configured": bool(str(settings.get("secret") or "").strip()),
    }


def _validate_feishu_alert_settings(settings: dict[str, object]) -> None:
    if not _normalize_bool(settings.get("enabled"), False):
        return
    webhook_url = str(settings.get("webhook_url") or "").strip()
    if not webhook_url:
        raise ValueError("启用飞书告警后必须填写 Webhook 地址")
    allowed_prefixes = (
        "https://open.feishu.cn/open-apis/bot/v2/hook/",
        "https://open.larksuite.com/open-apis/bot/v2/hook/",
    )
    if not webhook_url.startswith(allowed_prefixes):
        raise ValueError("飞书 Webhook 地址格式不正确")


def _normalize_feishu_alert_state(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    recent = source.get("recent_events")
    recent_events = recent if isinstance(recent, list) else []
    normalized_recent: list[dict[str, object]] = []
    for item in recent_events[-50:]:
        if not isinstance(item, dict):
            continue
        normalized_recent.append(
            {
                "sent_at": str(item.get("sent_at") or "").strip() or None,
                "event_type": str(item.get("event_type") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "fingerprint": str(item.get("fingerprint") or "").strip(),
            }
        )
    return {
        "last_sent_at": str(source.get("last_sent_at") or "").strip() or None,
        "last_event_type": str(source.get("last_event_type") or "").strip(),
        "last_fingerprint": str(source.get("last_fingerprint") or "").strip(),
        "last_status": str(source.get("last_status") or "idle").strip() or "idle",
        "last_error": str(source.get("last_error") or "").strip(),
        "last_response_code": _normalize_positive_int(source.get("last_response_code"), 0, 0),
        "last_response_message": str(source.get("last_response_message") or "").strip(),
        "last_recovered_at": str(source.get("last_recovered_at") or "").strip() or None,
        "recent_events": normalized_recent,
    }


def _validate_image_storage_settings(settings: dict[str, object]) -> None:
    if not _normalize_bool(settings.get("enabled"), False):
        return
    if not str(settings.get("webdav_url") or "").strip():
        raise ValueError("启用 WebDAV 图片存储后必须填写 WebDAV URL")
    if not str(settings.get("webdav_password") or "").strip():
        raise ValueError("启用 WebDAV 图片存储后必须填写 WebDAV 密码")


@dataclass(frozen=True)
class LoadedSettings:
    auth_key: str
    refresh_account_interval_minute: int


def _normalize_auth_key(value: object) -> str:
    return str(value or "").strip()


def _is_invalid_auth_key(value: object) -> bool:
    return _normalize_auth_key(value) == ""


def _read_json_object(path: Path, *, name: str) -> dict[str, object]:
    if not path.exists():
        return {}
    if path.is_dir():
        print(
            f"Warning: {name} at '{path}' is a directory, ignoring it and falling back to other configuration sources.",
            file=sys.stderr,
        )
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_settings() -> LoadedSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_config = _read_json_object(CONFIG_FILE, name="config.json")
    auth_key = _normalize_auth_key(os.getenv("CHATGPT2API_AUTH_KEY") or raw_config.get("auth-key"))
    if _is_invalid_auth_key(auth_key):
        raise ValueError(
            "❌ auth-key 未设置！\n"
            "请在环境变量 CHATGPT2API_AUTH_KEY 中设置，或者在 config.json 中填写 auth-key。"
        )

    try:
        refresh_interval = int(raw_config.get("refresh_account_interval_minute", 5))
    except (TypeError, ValueError):
        refresh_interval = 5

    return LoadedSettings(
        auth_key=auth_key,
        refresh_account_interval_minute=refresh_interval,
    )


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        self._storage_backend: StorageBackend | None = None
        if _is_invalid_auth_key(self.auth_key):
            raise ValueError(
                "❌ auth-key 未设置！\n"
                "请按以下任意一种方式解决：\n"
                "1. 在 Render 的 Environment 变量中添加：\n"
                "   CHATGPT2API_AUTH_KEY = your_real_auth_key\n"
                "2. 或者在 config.json 中填写：\n"
                '   "auth-key": "your_real_auth_key"'
            )

    def _load(self) -> dict[str, object]:
        return _read_json_object(self.path, name="config.json")

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @property
    def auth_key(self) -> str:
        return _normalize_auth_key(os.getenv("CHATGPT2API_AUTH_KEY") or self.data.get("auth-key"))

    @property
    def accounts_file(self) -> Path:
        return DATA_DIR / "accounts.json"

    @property
    def refresh_account_interval_minute(self) -> int:
        try:
            return int(self.data.get("refresh_account_interval_minute", 5))
        except (TypeError, ValueError):
            return 5

    @property
    def image_retention_days(self) -> int:
        try:
            return max(1, int(self.data.get("image_retention_days", 30)))
        except (TypeError, ValueError):
            return 30

    @property
    def image_poll_timeout_secs(self) -> int:
        try:
            return max(1, int(self.data.get("image_poll_timeout_secs", 120)))
        except (TypeError, ValueError):
            return 120

    @property
    def image_poll_interval_secs(self) -> float:
        try:
            return max(0.5, float(self.data.get("image_poll_interval_secs", 10.0)))
        except (TypeError, ValueError):
            return 10.0

    @property
    def image_poll_initial_wait_secs(self) -> float:
        """Image generation upstream takes ~30s; polling immediately wastes requests
        and trips a transient 429. Default 10s gives the conversation document time
        to commit before the first poll."""
        try:
            return max(0.0, float(self.data.get("image_poll_initial_wait_secs", 10.0)))
        except (TypeError, ValueError):
            return 10.0

    @property
    def image_account_concurrency(self) -> int:
        try:
            return max(1, int(self.data.get("image_account_concurrency", 3)))
        except (TypeError, ValueError):
            return 3

    @property
    def auto_remove_invalid_accounts(self) -> bool:
        value = self.data.get("auto_remove_invalid_accounts", False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def auto_remove_rate_limited_accounts(self) -> bool:
        value = self.data.get("auto_remove_rate_limited_accounts", False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def log_levels(self) -> list[str]:
        levels = self.data.get("log_levels")
        if not isinstance(levels, list):
            return []
        allowed = {"debug", "info", "warning", "error"}
        return [level for item in levels if (level := str(item or "").strip().lower()) in allowed]

    @property
    def sensitive_words(self) -> list[str]:
        words = self.data.get("sensitive_words")
        return [word for item in words if (word := str(item or "").strip())] if isinstance(words, list) else []

    @property
    def ai_review(self) -> dict[str, object]:
        value = self.data.get("ai_review")
        return value if isinstance(value, dict) else {}

    @property
    def global_system_prompt(self) -> str:
        return str(self.data.get("global_system_prompt") or "").strip()

    @property
    def images_dir(self) -> Path:
        path = DATA_DIR / "images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def image_thumbnails_dir(self) -> Path:
        path = DATA_DIR / "image_thumbnails"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup_old_images(self) -> int:
        cutoff = time.time() - self.image_retention_days * 86400
        removed = 0
        for path in self.images_dir.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        for path in sorted((p for p in self.images_dir.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass
        return removed

    @property
    def base_url(self) -> str:
        return str(
            os.getenv("CHATGPT2API_BASE_URL")
            or self.data.get("base_url")
            or ""
        ).strip().rstrip("/")

    @property
    def app_version(self) -> str:
        try:
            value = VERSION_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return "0.0.0"
        return value or "0.0.0"

    def get(self) -> dict[str, object]:
        data = dict(self.data)
        data["refresh_account_interval_minute"] = self.refresh_account_interval_minute
        data["image_retention_days"] = self.image_retention_days
        data["image_poll_timeout_secs"] = self.image_poll_timeout_secs
        data["image_poll_interval_secs"] = self.image_poll_interval_secs
        data["image_poll_initial_wait_secs"] = self.image_poll_initial_wait_secs
        data["image_account_concurrency"] = self.image_account_concurrency
        data["auto_remove_invalid_accounts"] = self.auto_remove_invalid_accounts
        data["auto_remove_rate_limited_accounts"] = self.auto_remove_rate_limited_accounts
        data["log_levels"] = self.log_levels
        data["sensitive_words"] = self.sensitive_words
        data["ai_review"] = self.ai_review
        data["global_system_prompt"] = self.global_system_prompt
        data["backup"] = self.get_backup_settings()
        data["image_storage"] = self.get_image_storage_settings()
        data["account_pool_guard"] = self.get_account_pool_guard_settings()
        data["feishu_alert"] = _sanitize_feishu_alert_settings(self.get_feishu_alert_settings(raw=True))
        data.pop("auth-key", None)
        return data

    def get_proxy_settings(self) -> str:
        return str(self.data.get("proxy") or "").strip()

    def update(self, data: dict[str, object]) -> dict[str, object]:
        next_data = dict(self.data)
        next_data.update(dict(data or {}))
        if "backup" in next_data:
            next_data["backup"] = _normalize_backup_settings(next_data.get("backup"))
        if "image_storage" in next_data:
            next_data["image_storage"] = _normalize_image_storage_settings(next_data.get("image_storage"))
            _validate_image_storage_settings(next_data["image_storage"])
        if "account_pool_guard" in next_data:
            next_data["account_pool_guard"] = _normalize_account_pool_guard_settings(next_data.get("account_pool_guard"))
        if "feishu_alert" in next_data:
            next_data["feishu_alert"] = _normalize_feishu_alert_settings(
                next_data.get("feishu_alert"),
                self.data.get("feishu_alert"),
            )
            _validate_feishu_alert_settings(next_data["feishu_alert"])
        next_data.pop("backup_state", None)
        next_data.pop("account_pool_guard_state", None)
        next_data.pop("feishu_alert_state", None)
        self.data = next_data
        self._save()
        return self.get()

    def get_backup_settings(self) -> dict[str, object]:
        return _normalize_backup_settings(self.data.get("backup"))

    def get_image_storage_settings(self) -> dict[str, object]:
        return _normalize_image_storage_settings(self.data.get("image_storage"))

    def get_account_pool_guard_settings(self) -> dict[str, object]:
        return _normalize_account_pool_guard_settings(self.data.get("account_pool_guard"))

    def get_feishu_alert_settings(self, *, raw: bool = False) -> dict[str, object]:
        settings = _normalize_feishu_alert_settings(self.data.get("feishu_alert"), self.data.get("feishu_alert"))
        return settings if raw else _sanitize_feishu_alert_settings(settings)

    def get_storage_backend(self) -> StorageBackend:
        """获取存储后端实例（单例）"""
        if self._storage_backend is None:
            from services.storage.factory import create_storage_backend
            self._storage_backend = create_storage_backend(DATA_DIR)
        return self._storage_backend


def load_backup_state() -> dict[str, object]:
    return _normalize_backup_state(_read_json_object(BACKUP_STATE_FILE, name="backup_state.json"))


def save_backup_state(state: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_backup_state(state)
    BACKUP_STATE_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def load_account_pool_guard_state() -> dict[str, object]:
    return _normalize_account_pool_guard_state(
        _read_json_object(ACCOUNT_POOL_GUARD_STATE_FILE, name="account_pool_guard_state.json")
    )


def save_account_pool_guard_state(state: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_account_pool_guard_state(state)
    ACCOUNT_POOL_GUARD_STATE_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def load_feishu_alert_state() -> dict[str, object]:
    return _normalize_feishu_alert_state(
        _read_json_object(FEISHU_ALERT_STATE_FILE, name="feishu_alert_state.json")
    )


def save_feishu_alert_state(state: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_feishu_alert_state(state)
    FEISHU_ALERT_STATE_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


config = ConfigStore(CONFIG_FILE)
