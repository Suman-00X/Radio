"""Runs the test suite in child pytests and streams each result as it lands, for the recruiter tour's live test run.

Order: run_suite first runs a collect-only pytest for the total, then the test files in batches, each
in a fresh pytest, so memory does not pile up across the suite on a small instance. Every child loads
this module as a plugin with a pipe's write end in its environment -> the plugin writes one JSON line
per event to that pipe: the collected total (pytest_collection_finish), each test's outcome
(pytest_runtest_logreport) and the exit status (pytest_sessionfinish) -> run_suite reads the lines
back and yields them as dicts, ending with a summary it counts itself. A child gets no database URL,
key or token from the server's environment (only RADREPORT_TEST_* passes through), so a test can
never reach the deployment's own database or services. Only one run happens at a time across every
server worker (a file lock); a stopped reader kills the running child.

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
_TIMEOUT_SECONDS = 900
_BATCH_FILES = 12
# The child's whole environment, besides RADREPORT_TEST_* and the variables set in _child_env.
_PASSED_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PYTHONPATH", "VIRTUAL_ENV")
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
def _child_env(write_fd: int) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in _PASSED_ENV or key.startswith("RADREPORT_TEST_")}
    return {**env, "RADREPORT_ENVIRONMENT": "test", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", _FD_ENV: str(write_fd)}


def _batches() -> list[list[str]]:
    files = sorted(str(path.relative_to(_ROOT)) for path in (_ROOT / "tests").rglob("test_*.py"))
    return [files[start : start + _BATCH_FILES] for start in range(0, len(files), _BATCH_FILES)]


async def _child(args: list[str], deadline: float) -> AsyncIterator[dict[str, Any]]:
    """The events of one pytest child; raises TimeoutError past the deadline."""
    read_fd, write_fd = os.pipe()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "radreport.devtools.test_stream", *args,
        cwd=_ROOT, env=_child_env(write_fd), pass_fds=(write_fd,), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    os.close(write_fd)
    reader = asyncio.StreamReader(limit=1 << 20)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(read_fd, "rb"))
    try:
        while line := await asyncio.wait_for(reader.readline(), timeout=max(deadline - time.monotonic(), 0.1)):
            yield json.loads(line)
        await proc.wait()
    finally:
        transport.close()
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def run_suite() -> AsyncIterator[dict[str, Any]]:
    """Every event of one full run, then a summary; raises SuiteBusy when a run is already going."""
    lock = open(_LOCK_PATH, "w")  # noqa: SIM115 - held for the whole run, closed in the finally below
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise SuiteBusy("a test run is already in progress") from None
    try:
        started = time.monotonic()
        deadline = started + _TIMEOUT_SECONDS
        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
        exit_status = 0
        try:
            async for event in _child(["--collect-only"], deadline):
                if event["type"] == "start":
                    yield event
            for batch in _batches():
                async for event in _child(batch, deadline):
                    if event["type"] == "test":
                        counts[event["outcome"]] = counts.get(event["outcome"], 0) + 1
                        yield event
                    # 5 is a batch with nothing to run; the run's status is the first real failure.
                    elif event["type"] == "finish" and event["exit"] not in (0, 5) and exit_status == 0:
                        exit_status = event["exit"]
            yield {"type": "done", **counts, "seconds": round(time.monotonic() - started, 1), "exit": exit_status}
        except TimeoutError:
            yield {"type": "done", **counts, "seconds": round(time.monotonic() - started, 1), "exit": None, "timeout": True}
    finally:
        lock.close()
