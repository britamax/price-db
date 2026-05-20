"""ARQ worker config for batch Excel matching jobs."""
import os
from arq.connections import RedisSettings

from workers.batch import run_batch_match


REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


class WorkerSettings:
    """ARQ worker config — runs registered functions from Redis queue.

    Start with: `arq workers.config.WorkerSettings`
    """
    functions = [run_batch_match]
    redis_settings = RedisSettings(host=REDIS_HOST, port=REDIS_PORT)
    max_jobs = 2           # concurrent jobs per worker process
    job_timeout = 1800     # 30 min per batch
    keep_result = 86400    # keep job result 24h
    max_tries = 1          # batch jobs handle their own retries inside


def get_redis_settings() -> RedisSettings:
    return RedisSettings(host=REDIS_HOST, port=REDIS_PORT)
