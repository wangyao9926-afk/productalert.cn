from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_SQLITE_PATH = DATA_DIR / "monitor.db"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    backend: str
    sqlite_path: Path | None = None


@dataclass(frozen=True)
class QueueSettings:
    backend: str
    redis_url: str | None = None


@dataclass(frozen=True)
class RuntimeSettings:
    start_background_workers: bool
    start_notification_worker: bool


@dataclass(frozen=True)
class WebSecuritySettings:
    environment: str
    allowed_origins: tuple[str, ...]
    session_cookie_secure: bool
    session_cookie_samesite: str


def database_settings() -> DatabaseSettings:
    raw_url = os.getenv("DATABASE_URL", "").strip()
    if not raw_url:
        return DatabaseSettings(
            url=f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}",
            backend="sqlite",
            sqlite_path=DEFAULT_SQLITE_PATH,
        )

    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    if scheme in {"sqlite", "sqlite3"}:
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            raise RuntimeError("Only local sqlite DATABASE_URL values are supported")
        raw_path = unquote(parsed.path or "")
        if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
            path = Path(raw_path.lstrip("/"))
        elif raw_url.startswith("sqlite:////") or raw_url.startswith("sqlite3:////"):
            path = Path(raw_path)
        elif raw_path.startswith("/"):
            path = Path(raw_path.lstrip("/"))
        elif raw_path:
            path = Path(raw_path)
        else:
            path = DEFAULT_SQLITE_PATH
        if not path.is_absolute():
            path = ROOT / path
        return DatabaseSettings(url=raw_url, backend="sqlite", sqlite_path=path)

    if scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        return DatabaseSettings(url=raw_url, backend="postgresql")

    raise RuntimeError(f"Unsupported DATABASE_URL scheme: {scheme or 'empty'}")


def queue_settings() -> QueueSettings:
    backend = os.getenv("QUEUE_BACKEND", "in_process").strip().lower() or "in_process"
    if backend not in {"in_process", "rq"}:
        raise RuntimeError(f"Unsupported QUEUE_BACKEND: {backend}")
    redis_url = os.getenv("REDIS_URL", "").strip() or None
    return QueueSettings(backend=backend, redis_url=redis_url)


def public_app_url() -> str | None:
    raw_url = os.getenv("APP_PUBLIC_URL", "").strip()
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return raw_url.rstrip("/")


def env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, str(default).lower()).strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def normalize_web_origin(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("CORS origins must be absolute HTTP(S) origins")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("CORS origins must not include credentials, paths, queries, or fragments")
    return f"{parsed.scheme}://{parsed.netloc}"


def web_security_settings() -> WebSecuritySettings:
    environment = os.getenv("APP_ENV", "development").strip().lower() or "development"
    default_origins = "" if environment == "production" else "http://127.0.0.1:4175,http://localhost:4175"
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", default_origins)
    origins = tuple(dict.fromkeys(normalize_web_origin(value) for value in raw_origins.split(",") if value.strip()))
    default_secure = environment == "production"
    default_samesite = "none" if environment == "production" else "lax"
    samesite = os.getenv("SESSION_COOKIE_SAMESITE", default_samesite).strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        raise ValueError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
    return WebSecuritySettings(
        environment=environment,
        allowed_origins=origins,
        session_cookie_secure=env_bool("SESSION_COOKIE_SECURE", default_secure),
        session_cookie_samesite=samesite,
    )


def production_web_configuration_errors(settings: WebSecuritySettings | None = None) -> list[str]:
    resolved = settings or web_security_settings()
    if resolved.environment != "production":
        return []
    errors: list[str] = []
    if not resolved.allowed_origins:
        errors.append("CORS_ALLOWED_ORIGINS must list the deployed frontend origin")
    if any(not origin.startswith("https://") for origin in resolved.allowed_origins):
        errors.append("production CORS_ALLOWED_ORIGINS must use HTTPS")
    if not resolved.session_cookie_secure:
        errors.append("SESSION_COOKIE_SECURE must be true in production")
    if resolved.session_cookie_samesite != "none":
        errors.append("SESSION_COOKIE_SAMESITE must be none for a separately hosted frontend")
    return errors


def runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        start_background_workers=env_bool("START_BACKGROUND_WORKERS", True),
        start_notification_worker=env_bool("START_NOTIFICATION_WORKER", True),
    )


def require_sqlite(settings: DatabaseSettings | None = None) -> DatabaseSettings:
    resolved = settings or database_settings()
    if resolved.backend != "sqlite":
        raise RuntimeError(
            "PostgreSQL is configured but this codebase is still in migration-prep mode. "
            "Keep DATABASE_URL unset or sqlite:// for now; see docs/POSTGRESQL_MIGRATION.md."
        )
    return resolved
