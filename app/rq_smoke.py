from __future__ import annotations

from uuid import uuid4

from app.rq_preflight import run_preflight
from app.rq_compat import rq_worker_class


def rq_ping(marker: str) -> str:
    return marker


def run_smoke_test() -> dict:
    result = run_preflight(check_redis=True)

    from redis import Redis
    from rq import Queue, SimpleWorker

    redis_url = result["redis_url"]
    marker = uuid4().hex
    connection = Redis.from_url(redis_url)
    queue = Queue("smoke", connection=connection)
    queue.empty()
    job = queue.enqueue("app.rq_smoke.rq_ping", marker)

    worker_class = rq_worker_class(SimpleWorker)
    worker = worker_class([queue], connection=connection)
    worker.work(burst=True)

    job.refresh()
    if not job.is_finished:
        raise RuntimeError(f"RQ smoke job did not finish: {job.get_status()}")
    if job.return_value() != marker:
        raise RuntimeError("RQ smoke job returned an unexpected value")

    return {
        "queue_backend": result["queue_backend"],
        "queue_name": queue.name,
        "job_id": job.id,
    }


def main() -> None:
    result = run_smoke_test()
    print(
        "rq smoke ok "
        f"queue_backend={result['queue_backend']} "
        f"queue={result['queue_name']} "
        f"job_id={result['job_id']}"
    )


if __name__ == "__main__":
    main()
