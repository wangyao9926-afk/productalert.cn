from __future__ import annotations

from datetime import datetime, timezone

from app.db import execute_sql, fetchone, get_db, row_to_dict


SCHEDULER_COMPONENT = "scheduler"
SCHEDULER_HEARTBEAT_STALE_SECONDS = 180


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def record_runtime_heartbeat(component: str, recorded_at: datetime | None = None) -> None:
    seen_at = _as_utc(recorded_at or datetime.now(timezone.utc)).isoformat()
    with get_db() as db:
        execute_sql(
            db,
            """
            INSERT INTO runtime_heartbeats (component, last_seen_at)
            VALUES (?, ?)
            ON CONFLICT (component) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (component, seen_at),
        )


def runtime_component_health(
    component: str,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = SCHEDULER_HEARTBEAT_STALE_SECONDS,
) -> dict:
    with get_db() as db:
        row = fetchone(
            db,
            "SELECT component, last_seen_at FROM runtime_heartbeats WHERE component = ?",
            (component,),
        )
    recorded_at = _parse_timestamp(row_to_dict(row).get("last_seen_at")) if row else None
    current_time = _as_utc(now or datetime.now(timezone.utc))
    healthy = bool(
        recorded_at
        and current_time >= recorded_at
        and (current_time - recorded_at).total_seconds() <= stale_after_seconds
    )
    return {
        "component": component,
        "last_seen_at": recorded_at.isoformat() if recorded_at else None,
        "healthy": healthy,
    }
