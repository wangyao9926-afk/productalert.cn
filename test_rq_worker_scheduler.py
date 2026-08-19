from __future__ import annotations

import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.rq_worker import recover_pending_scan_jobs, start_scheduler_thread


class RqWorkerSchedulerTests(unittest.TestCase):
    def test_worker_recovery_requeues_persisted_jobs_before_listening(self) -> None:
        recovery = AsyncMock(return_value=3)

        with patch("app.rq_worker.recover_queued_scan_tasks", recovery):
            restored = recover_pending_scan_jobs()

        self.assertEqual(restored, 3)
        recovery.assert_awaited_once_with()

    def test_scheduler_runs_in_daemon_thread_alongside_rq_worker(self) -> None:
        scheduled = threading.Event()

        thread = start_scheduler_thread(lambda: scheduled.set())

        self.assertTrue(thread.daemon)
        self.assertEqual(thread.name, "productalert-scheduler")
        self.assertTrue(scheduled.wait(timeout=1))
        thread.join(timeout=1)

    def test_scheduler_thread_can_use_default_scheduler_runner(self) -> None:
        runner = Mock()

        thread = start_scheduler_thread(runner)

        thread.join(timeout=1)
        runner.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
