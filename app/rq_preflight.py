from __future__ import annotations

import argparse

from app.settings import queue_settings


def check_rq_dependencies() -> None:
    try:
        import redis  # noqa: F401
        import rq  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("RQ preflight requires redis and rq packages") from exc


def check_redis_connection(redis_url: str) -> None:
    from redis import Redis

    client = Redis.from_url(redis_url)
    client.ping()


def run_preflight(check_redis: bool = False) -> dict:
    settings = queue_settings()
    if settings.backend != "rq":
        raise RuntimeError("RQ preflight requires QUEUE_BACKEND=rq")
    if not settings.redis_url:
        raise RuntimeError("RQ preflight requires REDIS_URL")

    check_rq_dependencies()
    if check_redis:
        check_redis_connection(settings.redis_url)

    return {
        "queue_backend": settings.backend,
        "redis_url": settings.redis_url,
        "redis_checked": check_redis,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RQ queue configuration.")
    parser.add_argument("--check-redis", action="store_true", help="Ping Redis after dependency checks.")
    args = parser.parse_args()

    result = run_preflight(check_redis=args.check_redis)
    redis_state = "checked" if result["redis_checked"] else "not_checked"
    print(f"rq preflight ok queue_backend={result['queue_backend']} redis={redis_state}")


if __name__ == "__main__":
    main()
