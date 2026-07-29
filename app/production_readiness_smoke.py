from __future__ import annotations

import argparse
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from app.db import DB_BACKEND
from app.db_compat_audit import run_audit
from app.db_preflight import run_preflight
from app.rq_preflight import run_preflight as run_rq_preflight
from app.settings import queue_settings


@dataclass(frozen=True)
class SmokeStep:
    name: str
    check: Callable[[], object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run production readiness smoke checks.")
    parser.add_argument(
        "--require-backend",
        choices=["sqlite", "postgresql"],
        help="Fail before running checks unless the active database backend matches.",
    )
    parser.add_argument(
        "--require-queue",
        choices=["in_process", "rq"],
        help="Fail before running checks unless the active queue backend matches.",
    )
    return parser.parse_args()


def require_backend(expected_backend: str | None) -> None:
    if expected_backend and DB_BACKEND.name != expected_backend:
        raise RuntimeError(f"required database backend {expected_backend}, got {DB_BACKEND.name}")


def require_queue(expected_queue: str | None) -> None:
    settings = queue_settings()
    if expected_queue and settings.backend != expected_queue:
        raise RuntimeError(f"required queue backend {expected_queue}, got {settings.backend}")


def check_rq_preflight() -> object:
    return run_rq_preflight(check_redis=True)


def check_rq_smoke() -> object:
    from app.rq_smoke import run_smoke_test

    return run_smoke_test()


def check_rq_scan_smoke() -> object:
    from app.rq_scan_smoke import run_smoke_test

    return run_smoke_test()


def check_api_smoke() -> object:
    from app.api_smoke import run_smoke_test

    return run_smoke_test()


def check_notification_success_smoke() -> object:
    from app.notification_outbox_smoke import run_smoke_test

    return run_smoke_test()


def check_notification_failure_smoke() -> object:
    from app.notification_outbox_failure_smoke import run_smoke_test

    return run_smoke_test()


def check_notification_retry_smoke() -> object:
    from app.notification_retry_smoke import run_smoke_test

    return run_smoke_test()


def check_notification_isolation_smoke() -> object:
    from app.notification_isolation_smoke import run_smoke_test

    return run_smoke_test()


def check_core_isolation_smoke() -> object:
    from app.core_isolation_smoke import run_smoke_test

    return run_smoke_test()


def check_database_preflight() -> object:
    checks = run_preflight()
    if not checks:
        raise RuntimeError("database preflight returned no migration checks")
    return {"migration_checks": len(checks)}


def check_database_compatibility() -> object:
    findings = run_audit()
    if findings:
        first = findings[0]
        raise RuntimeError(
            f"database compatibility audit found {len(findings)} issue(s); "
            f"first={first.category} {first.path}:{first.line}"
        )
    return {"findings": 0}


def smoke_steps() -> list[SmokeStep]:
    steps = [
        SmokeStep("database preflight", check_database_preflight),
        SmokeStep("database compatibility audit", check_database_compatibility),
        SmokeStep("api smoke", check_api_smoke),
        SmokeStep("notification outbox success", check_notification_success_smoke),
        SmokeStep("notification outbox failure", check_notification_failure_smoke),
        SmokeStep("notification retry", check_notification_retry_smoke),
        SmokeStep("notification tenant isolation", check_notification_isolation_smoke),
        SmokeStep("core tenant isolation", check_core_isolation_smoke),
    ]
    if queue_settings().backend == "rq":
        steps.insert(2, SmokeStep("rq preflight", check_rq_preflight))
        steps.insert(3, SmokeStep("rq queue smoke", check_rq_smoke))
        steps.insert(5, SmokeStep("rq scan smoke", check_rq_scan_smoke))
    return steps


def run_step(check: Callable[[], object]) -> object:
    result = check()
    if inspect.isawaitable(result):
        import asyncio

        return asyncio.run(result)
    return result


def run_smoke_test() -> list[dict]:
    results: list[dict] = []
    for step in smoke_steps():
        started = perf_counter()
        try:
            result = run_step(step.check)
        except Exception as exc:
            raise RuntimeError(f"production readiness failed at {step.name}: {exc}") from exc
        duration_ms = int((perf_counter() - started) * 1000)
        results.append({"name": step.name, "duration_ms": duration_ms, "result": result})
    return results


def main() -> None:
    args = parse_args()
    require_backend(args.require_backend)
    require_queue(args.require_queue)
    results = run_smoke_test()
    for result in results:
        print(f"ok {result['name']} duration_ms={result['duration_ms']}")
    print(f"production readiness smoke ok checks={len(results)}")


if __name__ == "__main__":
    main()
