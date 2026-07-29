from __future__ import annotations

import signal

from app.rq_compat import rq_worker_class
from app.settings import queue_settings


def rq_worker_base_class(worker_class, simple_worker_class):
    if hasattr(signal, "SIGALRM"):
        return worker_class
    return simple_worker_class


def main() -> None:
    settings = queue_settings()
    if settings.backend != "rq":
        raise RuntimeError("RQ worker requires QUEUE_BACKEND=rq")
    if not settings.redis_url:
        raise RuntimeError("RQ worker requires REDIS_URL")
    try:
        from redis import Redis
        from rq import SimpleWorker, Worker
    except ImportError as exc:
        raise RuntimeError("RQ worker requires redis and rq packages") from exc

    worker_class = rq_worker_class(rq_worker_base_class(Worker, SimpleWorker))
    worker = worker_class(["scan"], connection=Redis.from_url(settings.redis_url))
    worker.work()


if __name__ == "__main__":
    main()
