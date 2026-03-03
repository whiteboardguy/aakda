import asyncio
from typing import Dict


_jobs: Dict[str, asyncio.Queue] = {}


def create_job(job_id: str) -> asyncio.Queue:
    """Register a new job and return its queue."""
    q: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = q
    return q


def get_job(job_id: str) -> "asyncio.Queue | None":
    """Return the queue for an existing job, or None if not found."""
    return _jobs.get(job_id)


def remove_job(job_id: str) -> None:
    """Remove a job from the registry. Called by the SSE generator after completion."""
    _jobs.pop(job_id, None)
