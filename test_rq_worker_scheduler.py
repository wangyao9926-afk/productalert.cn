from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock

from app.rq_worker import start_scheduler_thread


class RqWorkerSchedulerTests(unittest.TestCase):
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
