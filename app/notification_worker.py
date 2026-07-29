from __future__ import annotations

import argparse
import asyncio

from app.db import init_db
from app.notifier import notification_worker_loop, process_pending_notifications


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the notification outbox worker.")
    parser.add_argument("--once", action="store_true", help="Process pending notifications once and exit.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum notifications to claim when using --once.")
    return parser.parse_args()


async def run_once(limit: int) -> int:
    init_db()
    return await process_pending_notifications(limit=limit)


async def run_forever() -> None:
    init_db()
    await notification_worker_loop()


def main() -> None:
    args = parse_args()
    if args.once:
        count = asyncio.run(run_once(args.limit))
        print(f"notification worker processed {count} pending notifications")
        return
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
