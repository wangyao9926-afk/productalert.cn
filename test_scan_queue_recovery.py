from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.task_queue import ScanTask, recover_queued_scan_tasks


class RecordingQueue:
    name = "in_process"

    def __init__(self) -> None:
        self.tasks: list[ScanTask] = []

    async def enqueue(self, task: ScanTask) -> None:
        self.tasks.append(task)

    async def dequeue(self) -> ScanTask:
        raise AssertionError("not used by recovery")

    def task_done(self) -> None:
        return None


class RecordingRqQueue(RecordingQueue):
    name = "rq"


class ScanQueueRecoveryTests(unittest.TestCase):
    def test_requeues_only_pending_tasks_after_in_process_restart(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"queue-recovery-{marker}@monitor.internal"
        with get_db() as db:
            user_id = insert_row(
                db,
                "users",
                {"email": email, "password_hash": "not-used"},
            )
            site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": user_id,
                    "name": "Queue recovery site",
                    "url": f"https://queue-recovery-{marker}.example.com",
                    "scan_interval_minutes": 60,
                    "notification_events": json_dumps(["product_new"]),
                },
            )
            source_id = insert_row(
                db,
                "monitor_sources",
                {
                    "site_id": site_id,
                    "source_type": "homepage",
                    "url": f"https://queue-recovery-{marker}.example.com",
                    "scan_interval_minutes": 60,
                },
            )
            queued_site_job = insert_row(
                db,
                "scan_jobs",
                {"site_id": site_id, "job_type": "site_scan", "trigger_type": "manual", "status": "queued"},
            )
            queued_source_job = insert_row(
                db,
                "scan_jobs",
                {
                    "site_id": site_id,
                    "source_id": source_id,
                    "job_type": "source_scan",
                    "trigger_type": "scheduled",
                    "status": "queued",
                },
            )
            insert_row(
                db,
                "scan_jobs",
                {"site_id": site_id, "job_type": "site_scan", "trigger_type": "manual", "status": "running"},
            )

        try:
            queue = RecordingQueue()
            restored = asyncio.run(recover_queued_scan_tasks(queue))

            self.assertEqual(restored, 2)
            self.assertEqual(
                queue.tasks,
                [
                    ScanTask(job_id=queued_site_job, kind="site", target_id=site_id, trigger_type="manual"),
                    ScanTask(
                        job_id=queued_source_job,
                        kind="source",
                        target_id=source_id,
                        trigger_type="scheduled",
                    ),
                ],
            )
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))

    def test_requeues_persisted_tasks_when_rq_worker_restarts(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"rq-queue-recovery-{marker}@monitor.internal"
        with get_db() as db:
            user_id = insert_row(db, "users", {"email": email, "password_hash": "not-used"})
            site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": user_id,
                    "name": "RQ Queue recovery site",
                    "url": f"https://rq-queue-recovery-{marker}.example.com",
                    "scan_interval_minutes": 60,
                    "notification_events": json_dumps(["product_new"]),
                },
            )
            queued_job = insert_row(
                db,
                "scan_jobs",
                {"site_id": site_id, "job_type": "site_scan", "trigger_type": "scheduled", "status": "queued"},
            )

        try:
            queue = RecordingRqQueue()
            restored = asyncio.run(recover_queued_scan_tasks(queue))

            self.assertEqual(restored, 1)
            self.assertEqual(queue.tasks[0].job_id, queued_job)
            self.assertEqual(queue.tasks[0].trigger_type, "scheduled")
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
