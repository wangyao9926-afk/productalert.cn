from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.db import fetchone, get_db, row_to_dict, select_by_id
from app.monitor import create_scan_job, finish_scan_job, scan_site, scan_source
from app.settings import QueueSettings, queue_settings


@dataclass(frozen=True)
class ScanTask:
    job_id: int
    kind: str
    target_id: int
    notify: bool = True
    trigger_type: str = "manual"


class ScanQueueBackend(Protocol):
    name: str

    async def enqueue(self, task: ScanTask) -> None:
        ...

    async def dequeue(self) -> ScanTask:
        ...

    def task_done(self) -> None:
        ...


class InProcessScanQueueBackend:
    name = "in_process"

    def __init__(self) -> None:
        self._queue: asyncio.Queue[ScanTask] = asyncio.Queue()

    async def enqueue(self, task: ScanTask) -> None:
        await self._queue.put(task)

    async def dequeue(self) -> ScanTask:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()


class RQScanQueueBackend:
    name = "rq"

    def __init__(self, redis_url: str | None) -> None:
        if not redis_url:
            raise RuntimeError("QUEUE_BACKEND=rq requires REDIS_URL")
        try:
            from redis import Redis
            from rq import Queue
        except ImportError as exc:
            raise RuntimeError("QUEUE_BACKEND=rq requires redis and rq packages") from exc

        self._queue = Queue("scan", connection=Redis.from_url(redis_url))

    async def enqueue(self, task: ScanTask) -> None:
        self._queue.enqueue(
            "app.task_queue.execute_scan_task",
            task.job_id,
            task.kind,
            task.target_id,
            task.notify,
            task.trigger_type,
        )

    async def dequeue(self) -> ScanTask:
        raise RuntimeError("RQ backend uses external workers; scan_worker_loop is only for in_process queues")

    def task_done(self) -> None:
        return None


def build_scan_queue_backend(settings: QueueSettings | None = None) -> ScanQueueBackend:
    resolved = settings or queue_settings()
    if resolved.backend == "in_process":
        return InProcessScanQueueBackend()
    if resolved.backend == "rq":
        return RQScanQueueBackend(resolved.redis_url)
    raise RuntimeError(f"Unsupported QUEUE_BACKEND: {resolved.backend}")


SCAN_QUEUE_SETTINGS = queue_settings()
scan_queue_backend: ScanQueueBackend = build_scan_queue_backend(SCAN_QUEUE_SETTINGS)


def queue_backend_name() -> str:
    return scan_queue_backend.name


async def recover_queued_scan_tasks(queue: ScanQueueBackend | None = None) -> int:
    """Restore persisted queued jobs after a worker restart.

    RQ job payloads can disappear when Redis is restarted. Re-enqueueing the
    durable database rows is safe because ``claim_scan_job`` lets only one
    delivery transition a job from queued to running.
    """
    target_queue = queue or scan_queue_backend
    with get_db() as db:
        jobs = db.execute(
            """
            SELECT id, site_id, source_id, job_type, trigger_type
            FROM scan_jobs
            WHERE status = 'queued'
            ORDER BY id ASC
            """
        ).fetchall()
    restored = 0
    for job in jobs:
        data = row_to_dict(job)
        if data["job_type"] == "site_scan" and data["site_id"]:
            task = ScanTask(
                job_id=data["id"],
                kind="site",
                target_id=data["site_id"],
                trigger_type=data["trigger_type"],
            )
        elif data["job_type"] == "source_scan" and data["source_id"]:
            task = ScanTask(
                job_id=data["id"],
                kind="source",
                target_id=data["source_id"],
                trigger_type=data["trigger_type"],
            )
        else:
            continue
        await target_queue.enqueue(task)
        restored += 1
    return restored


async def run_scan_task(task: ScanTask) -> None:
    if task.kind == "site":
        await scan_site(task.target_id, notify=task.notify, trigger_type=task.trigger_type, job_id=task.job_id)
    elif task.kind == "source":
        await scan_source(task.target_id, notify=task.notify, trigger_type=task.trigger_type, job_id=task.job_id)
    else:
        finish_scan_job(task.job_id, "failed", error_count=1, message=f"Unknown scan task type: {task.kind}")


def execute_scan_task(job_id: int, kind: str, target_id: int, notify: bool = True, trigger_type: str = "manual") -> None:
    try:
        asyncio.run(run_scan_task(ScanTask(job_id=job_id, kind=kind, target_id=target_id, notify=notify, trigger_type=trigger_type)))
    except Exception as exc:
        finish_scan_job(job_id, "failed", error_count=1, message=str(exc))


def load_scan_job(job_id: int) -> dict | None:
    with get_db() as db:
        row = select_by_id(db, "scan_jobs", job_id)
    if not row:
        return None
    return row_to_dict(row)


def scan_job_row_to_dict(row) -> dict:
    return row_to_dict(row)


def active_site_job(site_id: int) -> dict | None:
    with get_db() as db:
        row = fetchone(
            db,
            """
            SELECT * FROM scan_jobs
            WHERE site_id = ?
              AND source_id IS NULL
              AND job_type = 'site_scan'
              AND status IN ('queued', 'running')
            ORDER BY queued_at DESC, id DESC
            LIMIT 1
            """,
            (site_id,),
        )
    return scan_job_row_to_dict(row) if row else None


def active_source_job(source_id: int) -> dict | None:
    with get_db() as db:
        row = fetchone(
            db,
            """
            SELECT * FROM scan_jobs
            WHERE source_id = ?
              AND job_type = 'source_scan'
              AND status IN ('queued', 'running')
            ORDER BY queued_at DESC, id DESC
            LIMIT 1
            """,
            (source_id,),
        )
    return scan_job_row_to_dict(row) if row else None


async def enqueue_site_scan(site_id: int, notify: bool = True, trigger_type: str = "manual") -> dict:
    existing = active_site_job(site_id)
    if existing:
        return existing
    job_id = create_scan_job(site_id, None, "site_scan", trigger_type)
    await scan_queue_backend.enqueue(
        ScanTask(job_id=job_id, kind="site", target_id=site_id, notify=notify, trigger_type=trigger_type)
    )
    return load_scan_job(job_id) or {"id": job_id, "status": "queued"}


async def enqueue_source_scan(source_id: int, notify: bool = True, trigger_type: str = "manual") -> dict:
    existing = active_source_job(source_id)
    if existing:
        return existing
    with get_db() as db:
        source = fetchone(db, "SELECT site_id FROM monitor_sources WHERE id = ?", (source_id,))
    if not source:
        raise ValueError("鐩戞帶婧愪笉瀛樺湪")
    job_id = create_scan_job(source["site_id"], source_id, "source_scan", trigger_type)
    await scan_queue_backend.enqueue(
        ScanTask(job_id=job_id, kind="source", target_id=source_id, notify=notify, trigger_type=trigger_type)
    )
    return load_scan_job(job_id) or {"id": job_id, "status": "queued"}


async def scan_worker_loop() -> None:
    if scan_queue_backend.name != "in_process":
        raise RuntimeError("scan_worker_loop is only available for QUEUE_BACKEND=in_process")
    while True:
        task = await scan_queue_backend.dequeue()
        try:
            await run_scan_task(task)
        except Exception as exc:
            finish_scan_job(task.job_id, "failed", error_count=1, message=str(exc))
        finally:
            scan_queue_backend.task_done()
