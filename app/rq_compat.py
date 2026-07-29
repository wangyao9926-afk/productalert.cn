from __future__ import annotations

import signal


def rq_worker_class(base_worker_class):
    if hasattr(signal, "SIGALRM"):
        return base_worker_class

    from rq.timeouts import TimerDeathPenalty

    class WindowsWorker(base_worker_class):
        death_penalty_class = TimerDeathPenalty

    return WindowsWorker
