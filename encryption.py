"""Database encryption manifest and SQLCipher helper utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from .filesystem import ensure_private_directory, ensure_private_file

try:
    import sqlite3 as _stdlib_sqlite
except Exception:
    _stdlib_sqlite = None

try:
    from sqlcipher3 import dbapi2 as _sqlcipher
except Exception:
    _sqlcipher = None

try:
    import keyring as _keyring
except Exception:
    _keyring = None


@dataclass
class DatabaseEncryptionConfig:
    """Persisted settings for database encryption."""

    enabled: bool = False
    provider: str = ""
    key_salt: str = ""
    key_iterations: int = 120_000
    keyring_service: str = "anamnesis"
    keyring_key_name: str = "index-encryption-secret"
    created_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DatabaseEncryptionConfig":
        return cls(
            enabled=bool(payload.get("enabled", False)),
            provider=str(payload.get("provider", "")),
            key_salt=str(payload.get("key_salt", "")),
            key_iterations=int(payload.get("key_iterations", 120_000)),
            keyring_service=str(payload.get("keyring_service", "anamnesis")),
            keyring_key_name=str(payload.get("keyring_key_name", "index-encryption-secret")),
            created_at=str(payload.get("created_at", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def supports_sqlcipher() -> bool:
    return _sqlcipher is not None


def supports_keyring() -> bool:
    return _keyring is not None


def _new_salt() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_key(password: str, salt: str, *, iterations: int = 120_000) -> str:
    """Derive a stable SQLCipher passphrase from master material."""

    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        base64.urlsafe_b64decode(salt),
        iterations,
        dklen=32,
    ).hex()


def _quote_pragma_value(value: str) -> str:
    return value.replace("'", "''")


def open_sqlcipher_connection(path: Path, key: str):
    if _sqlcipher is None:
        raise RuntimeError("SQLCipher runtime dependency is not available.")
    conn = _sqlcipher.connect(str(path))
    conn.execute(f"PRAGMA key = '{_quote_pragma_value(key)}'")
    conn.execute("PRAGMA kdf_iter = 120000")
    conn.execute("PRAGMA cipher_page_size = 4096")
    return conn


def probe_sqlcipher_connection(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    try:
        with open_sqlcipher_connection(path, key) as conn:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1")
    except Exception:
        return False
    return True


def copy_plain_to_sqlcipher_database(
    plain_path: Path,
    encrypted_path: Path,
    key: str,
) -> None:
    if _stdlib_sqlite is None:
        raise RuntimeError("sqlite3 runtime dependency is not available.")
    with open_sqlcipher_connection(encrypted_path, key) as encrypted_conn:
        encrypted_conn.execute("PRAGMA cipher_memory_security = ON")
        if not plain_path.exists():
            return
        with _stdlib_sqlite.connect(plain_path) as plain_conn:
            dump = "\n".join(plain_conn.iterdump())
        encrypted_conn.executescript(dump)
        encrypted_conn.commit()


class DatabaseEncryptionManager:
    """Persist and resolve database encryption settings for Anamnesis."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.config = self._load()

    def _load(self) -> DatabaseEncryptionConfig:
        if not self.path.exists():
            return DatabaseEncryptionConfig()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return DatabaseEncryptionConfig()
        return DatabaseEncryptionConfig.from_dict(payload)

    def save(self) -> None:
        ensure_private_directory(self.path.parent)
        self.path.write_text(
            json.dumps(self.config.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ensure_private_file(self.path)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "provider": self.config.provider,
            "key_salt_present": bool(self.config.key_salt),
            "key_iterations": self.config.key_iterations,
            "keyring_service": self.config.keyring_service,
            "sqlcipher_available": supports_sqlcipher(),
            "keyring_available": supports_keyring(),
        }

    def requires_user_secret(self) -> bool:
        return self.config.enabled and self.config.provider == "password"

    def resolve_key(self, *, password: str | None = None) -> str | None:
        if not self.config.enabled:
            return None
        if self.config.provider == "keyring":
            if _keyring is None:
                return None
            token = _keyring.get_password(
                self.config.keyring_service,
                self.config.keyring_key_name,
            )
            if not token:
                return None
            return derive_key(token, self.config.key_salt, iterations=self.config.key_iterations)

        if self.config.provider != "password":
            return None
        if password is None:
            return None
        return derive_key(password, self.config.key_salt, iterations=self.config.key_iterations)

    def build_password_setup(self, password: str) -> str:
        if not password:
            raise ValueError("password required")
        self.config = DatabaseEncryptionConfig(
            enabled=True,
            provider="password",
            key_salt=_new_salt(),
            key_iterations=120_000,
            created_at=_now_utc_iso(),
        )
        return derive_key(password, self.config.key_salt, iterations=self.config.key_iterations)

    def build_keyring_setup(self, *, service_name: str = "anamnesis") -> str:
        if _keyring is None:
            raise RuntimeError("keyring runtime dependency is not installed")
        self.config = DatabaseEncryptionConfig(
            enabled=True,
            provider="keyring",
            key_salt=_new_salt(),
            key_iterations=120_000,
            keyring_service=service_name,
            created_at=_now_utc_iso(),
        )
        token = secrets.token_urlsafe(32)
        _keyring.set_password(
            self.config.keyring_service,
            self.config.keyring_key_name,
            token,
        )
        return derive_key(token, self.config.key_salt, iterations=self.config.key_iterations)

    def set_enabled(self, enabled: bool) -> None:
        self.config.enabled = enabled

