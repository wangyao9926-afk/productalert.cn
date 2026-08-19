from __future__ import annotations

import asyncio
import signal
import threading
from collections.abc import Callable

from app.monitor import scheduler_loop
from app.rq_compat import rq_worker_class
from app.settings import queue_settings
from app.task_queue import recover_queued_scan_tasks


def rq_worker_base_class(worker_class, simple_worker_class):
    if hasattr(signal, "SIGALRM"):
        return worker_class
    return simple_worker_class


def run_scheduler_forever() -> None:
    """Run due-source scheduling independently of RQ's blocking worker loop."""
    asyncio.run(scheduler_loop())


def start_scheduler_thread(runner: Callable[[], None] | None = None) -> threading.Thread:
    thread = threading.Thread(
        target=runner or run_scheduler_forever,
        name="productalert-scheduler",
        daemon=True,
    )
    thread.start()
    return thread


def recover_pending_scan_jobs() -> int:
    """Re-publish persisted queued jobs after Redis or worker restarts."""
    return asyncio.run(recover_queued_scan_tasks())


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
    recover_pending_scan_jobs()
    start_scheduler_thread()
    worker.work()


if __name__ == "__main__":
    main()
