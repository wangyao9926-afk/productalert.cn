from __future__ import annotations

import asyncio
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.monitor import scheduler_loop


@contextmanager
def fake_db():
    yield object()


class SchedulerEnabledQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_expands_enabled_boolean_conditions_before_querying(self) -> None:
        sleep = AsyncMock(side_effect=asyncio.CancelledError)
        with (
            patch("app.monitor.get_db", fake_db),
            patch("app.monitor.fetchall", return_value=[]) as fetchall,
            patch("app.monitor.asyncio.sleep", sleep),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await scheduler_loop()

        query = fetchall.call_args.args[1]
        self.assertNotIn("{boolean_true_sql", query)
        self.assertIn("monitor_sources.enabled", query)
        self.assertIn("sites.enabled", query)


if __name__ == "__main__":
    unittest.main()
