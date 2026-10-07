"""Runs the test suite in a child pytest and streams each result as it lands, for the recruiter tour's live test run.

Order: run_suite starts pytest with this module loaded as a plugin and a pipe's write end in its
environment -> the plugin writes one JSON line per event to that pipe: the collected total
(pytest_collection_finish), each test's outcome (pytest_runtest_logreport) and the exit status
(pytest_sessionfinish) -> run_suite reads the lines back and yields them as dicts, ending with a
summary it counts itself. Only one run happens at a time across every server worker (a file lock);
a stopped reader kills the child.

Defines: run_suite, SuiteBusy.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

_FD_ENV = "RADREPORT_TEST_STREAM_FD"
_ROOT = Path(__file__).resolve().parents[2]
_TIMEOUT_SECONDS = 600
_LOCK_PATH = Path(tempfile.gettempdir()) / "radreport-test-run.lock"


class SuiteBusy(RuntimeError):
    """Another run is still in progress."""


# ---------------------------------------------------------------- plugin ---
_out = None


def _emit(event: dict[str, Any]) -> None:
    if _out is not None:
        _out.write(json.dumps(event) + "\n")
        _out.flush()


def pytest_configure(config: Any) -> None:
    """Open the pipe the parent passed down; without one the plugin stays silent."""
    global _out
    fd = os.environ.get(_FD_ENV)
    if fd and fd.isdigit() and _out is None:
        _out = os.fdopen(int(fd), "w", buffering=1)


def pytest_collection_finish(session: Any) -> None:
    """The number of tests about to run, and the files they live in."""
    files = sorted({item.nodeid.split("::", 1)[0] for item in session.items})
    _emit({"type": "start", "total": len(session.items), "files": files})


def pytest_runtest_logreport(report: Any) -> None:
    """One event per test: its call outcome, or the setup or teardown outcome that replaced it."""
    if report.when == "call" or (report.when == "setup" and not report.passed) or (report.when == "teardown" and report.failed):
        outcome = "error" if report.when != "call" and report.failed else report.outcome
        _emit({"type": "test", "id": report.nodeid, "outcome": outcome, "seconds": round(report.duration, 4)})


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """The child's exit status, so the parent can tell a clean run from a broken one."""
    _emit({"type": "finish", "exit": int(exitstatus)})


# ---------------------------------------------------------------- runner ---
async def run_suite() -> AsyncIterator[dict[str, Any]]:
    """Every event of one full run, then a summary; raises SuiteBusy when a run is already going."""
    lock = open(_LOCK_PATH, "w")  # noqa: SIM115 - held for the whole run, closed in the finally below
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise SuiteBusy("a test run is already in progress") from None
    try:
        read_fd, write_fd = os.pipe()
        env = {**os.environ, _FD_ENV: str(write_fd), "PYTHONUNBUFFERED": "1"}
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "radreport.devtools.test_stream",
            cwd=_ROOT, env=env, pass_fds=(write_fd,), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        os.close(write_fd)
        reader = asyncio.StreamReader(limit=1 << 20)
        loop = asyncio.get_running_loop()
        transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(read_fd, "rb"))
        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
        exit_status: int | None = None
        try:
            while True:
                remaining = _TIMEOUT_SECONDS - (time.monotonic() - started)
                line = await asyncio.wait_for(reader.readline(), timeout=max(remaining, 0.1))
                if not line:
                    break
                event = json.loads(line)
                if event["type"] == "test":
                    counts[event["outcome"]] = counts.get(event["outcome"], 0) + 1
                elif event["type"] == "finish":
                    exit_status = event["exit"]
                    continue
                yield event
            await proc.wait()
            yield {"type": "done", **counts, "seconds": round(time.monotonic() - started, 1), "exit": exit_status if exit_status is not None else proc.returncode}
        except TimeoutError:
            yield {"type": "done", **counts, "seconds": round(time.monotonic() - started, 1), "exit": None, "timeout": True}
        finally:
            transport.close()
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
    finally:
        lock.close()
