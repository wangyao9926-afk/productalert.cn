from __future__ import annotations

import signal
import unittest

from app import rq_worker


class RqWorkerWindowsTests(unittest.TestCase):
    def test_windows_rq_worker_uses_simple_worker(self) -> None:
        original = getattr(signal, "SIGALRM", None)
        had_sigalrm = hasattr(signal, "SIGALRM")
        if had_sigalrm:
            delattr(signal, "SIGALRM")
        try:
            class FakeWorker:
                pass

            class FakeSimpleWorker:
                pass

            self.assertIs(
                rq_worker.rq_worker_base_class(FakeWorker, FakeSimpleWorker),
                FakeSimpleWorker,
            )
        finally:
            if had_sigalrm:
                setattr(signal, "SIGALRM", original)


if __name__ == "__main__":
    unittest.main()
