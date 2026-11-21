"""Drives a command in a hidden terminal: types keys at set moments and records what it draws.

The README pictures record Claude Code this way, and the model level of the end-to-end scenarios
types the turns of an interactive session with it, because the reading of sessions passes over
every headless transcript.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import signal
import struct
import termios
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# What a terminal takes as a command, not as text: a title, a color or a cursor move, a single key.
ESCAPES = re.compile(rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")
_CURSOR_POSITION_QUERY = b"\x1b[6n"
_POLL_SECONDS = 0.1


class TerminalError(Exception):
    """A wait did not see what it waited for; the message says what and for how long, and ``drawn``
    holds the text the command drew until then, which is where a command says why it stopped."""

    def __init__(self, message: str, drawn: str = "") -> None:
        super().__init__(message)
        self.drawn = drawn


@dataclass(frozen=True)
class Wait:
    """Read what the command draws for ``seconds``, or only until it drew ``until`` or ``done`` says
    so, then type ``keys``. ``until`` is looked for in the text alone: a shell with line editing draws
    an escape sequence between a line's end and its prompt. ``done`` is asked between reads, for a
    sign the command leaves elsewhere than on the screen, such as a line in a file; ``waits_for``
    names that sign in the error when it never comes."""

    seconds: float
    keys: str = ""
    until: bytes = b""
    done: Callable[[], bool] | None = None
    waits_for: str = ""


@dataclass(frozen=True)
class Recording:
    """What a command drew, each chunk with the seconds since its start, and the moment each wait ended."""

    chunks: tuple[tuple[float, bytes], ...]
    typed_at: tuple[float, ...]

    def text(self) -> str:
        """What it drew without the escape sequences."""
        drawn = b"".join(chunk for _, chunk in self.chunks)
        return ESCAPES.sub(b"", drawn).decode("utf-8", errors="replace")


def record_timed(
    command: Sequence[str], cwd: Path, environ: Mapping[str, str], rows: int, columns: int, waits: Sequence[Wait]
) -> Recording:
    """What the command draws in a terminal of ``columns`` x ``rows`` while the waits pass and their
    keys are typed, with its times. It ends early when the command does, and fails when a wait does
    not see what it waits for."""
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        # A child that cannot start the command must not unwind into the parent's cleanup.
        try:
            os.chdir(cwd)
            os.execvpe(command[0], list(command), dict(environ))
        finally:
            os._exit(127)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    start = time.monotonic()
    chunks: list[tuple[float, bytes]] = []
    typed_at: list[float] = []
    try:
        for wait in waits:
            if not _read_for(fd, wait, rows, start, chunks):
                break
            typed_at.append(time.monotonic() - start)
            if wait.keys:
                os.write(fd, wait.keys.encode())
    except TerminalError as error:
        raise TerminalError(str(error), Recording(tuple(chunks), ()).text()) from None
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(fd)
    return Recording(tuple(chunks), tuple(typed_at))


def _read_for(fd: int, wait: Wait, rows: int, start: float, chunks: list[tuple[float, bytes]]) -> bool:
    """Reads until the wait is over, answering cursor position queries; False once the command has ended."""
    end = time.monotonic() + wait.seconds
    seen = b""
    while time.monotonic() < end:
        if wait.done is not None and wait.done():
            return True
        ready, _, _ = select.select([fd], [], [], _POLL_SECONDS)
        if not ready:
            continue
        try:
            data = os.read(fd, 65536)
        except OSError:
            return False
        if not data:
            return False
        chunks.append((time.monotonic() - start, data))
        if _CURSOR_POSITION_QUERY in data:
            os.write(fd, f"\x1b[{rows};1R".encode())
        if wait.until:
            seen += data
            if wait.until in ESCAPES.sub(b"", seen):
                return True
    if wait.until:
        raise TerminalError(f"the terminal did not draw {wait.until!r} within {wait.seconds:g} seconds")
    if wait.done is not None:
        raise TerminalError(f"no {wait.waits_for or 'sign of the end'} within {wait.seconds:g} seconds")
    return True
