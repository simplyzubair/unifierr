"""Background jobs (install, wire, update) with step-by-step progress the UI can poll.

Jobs live in memory: they are short-lived and their outcome is also written to the event log.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.errors import UnifierrError

log = logging.getLogger("unifierr.jobs")

StepStatus = Literal["pending", "running", "ok", "skipped", "failed"]


class JobStep(BaseModel):
    name: str
    status: StepStatus = "pending"
    message: str | None = None
    explanation: str | None = None
    fix: str | None = None


class Job(BaseModel):
    id: str
    kind: str
    status: Literal["running", "done", "failed"] = "running"
    steps: list[JobStep] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)
    result: Any = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    # ---- helpers used by job bodies ----
    def say(self, line: str) -> None:
        if len(self.log) > 2000:
            del self.log[:500]
        self.log.append(line)

    def step(self, name: str) -> JobStep:
        s = JobStep(name=name, status="running")
        self.steps.append(s)
        return s

    def ok(self, s: JobStep, message: str | None = None) -> None:
        s.status, s.message = "ok", message

    def skip(self, s: JobStep, reason: str) -> None:
        s.status, s.message = "skipped", reason

    def fail(self, s: JobStep, exc: Exception) -> None:
        s.status = "failed"
        if isinstance(exc, UnifierrError):
            s.message, s.explanation, s.fix = exc.message, exc.explanation, exc.fix
        else:
            s.message = f"Unexpected error: {exc.__class__.__name__}"
            log.exception("Job step %s failed", s.name, exc_info=exc)


class JobManager:
    def __init__(self, keep: int = 50):
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()
        self._keep = keep

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def any_running(self) -> bool:
        return any(job.status == "running" for job in self._jobs.values())

    def start(self, kind: str, body: Callable[[Job], Awaitable[Any]]) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind)
        self._jobs[job.id] = job
        if len(self._jobs) > self._keep:
            for old in list(self._jobs)[: len(self._jobs) - self._keep]:
                if self._jobs[old].status != "running":
                    del self._jobs[old]

        async def run() -> None:
            try:
                job.result = await body(job)
                job.status = "failed" if any(s.status == "failed" for s in job.steps) else "done"
            except Exception as exc:  # noqa: BLE001 - surface every failure to the UI
                job.status = "failed"
                s = job.step("Unexpected problem")
                job.fail(s, exc)
            finally:
                job.finished_at = datetime.now(UTC)

        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job


jobs = JobManager()
