"""The ProPresenter Bible panel as a Python object: look verses up, click a result card, switch views.

The work is done by `vvbible`, a small macOS program that stays running and takes one command per line (see node/vvbible.swift).
Staying alive is what makes a click take ~10-50 ms instead of ~400 ms of start-up per command.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Protocol

PP = "http://127.0.0.1:1025"


class BibleUI(Protocol):
    def lookup(self, text: str) -> dict: ...
    def click(self, card: int) -> dict: ...
    def show(self) -> dict: ...
    def version(self, name: str) -> dict: ...
    def add(self) -> dict: ...
    def close(self) -> None: ...


class VVBible:
    """Talks to a running vvbible process. Restarts it if it died. One command at a time."""

    def __init__(self, binary: Path, timeout: float = 15.0):
        self.binary = binary
        self.timeout = timeout
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None

    def _start(self) -> None:
        self.proc = subprocess.Popen([str(self.binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def command(self, line: str) -> dict:
        with self.lock:
            for attempt in (1, 2):
                if self.proc is None or self.proc.poll() is not None:
                    self._start()
                try:
                    assert self.proc and self.proc.stdin and self.proc.stdout
                    self.proc.stdin.write(line + "\n")
                    self.proc.stdin.flush()
                    answer = self._readline()
                    if answer:
                        return json.loads(answer)
                except (BrokenPipeError, OSError, ValueError, AssertionError):
                    pass
                self._kill()
            return {"ok": False, "error": "the Bible helper did not answer"}

    def _readline(self) -> str:
        """A line from the helper, but never wait forever."""
        result: list[str] = []
        done = threading.Event()

        def read() -> None:
            try:
                result.append(self.proc.stdout.readline())      # type: ignore[union-attr]
            finally:
                done.set()

        threading.Thread(target=read, daemon=True).start()
        if not done.wait(self.timeout):
            return ""
        return result[0] if result else ""

    def _kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def lookup(self, text: str) -> dict:
        return self.command(f"lookup {text}")

    def click(self, card: int) -> dict:
        return self.command(f"click {card}")

    def show(self) -> dict:
        return self.command("show")

    def version(self, name: str) -> dict:
        return self.command(f"version {name}")

    def add(self) -> dict:
        return self.command("add")

    def close(self) -> None:
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.stdin.write("quit\n"); self.proc.stdin.flush(); self.proc.wait(timeout=2)       # type: ignore[union-attr]
        except Exception:
            pass
        self._kill()


def pp_get(path: str, timeout: float = 3.0):
    import httpx
    r = httpx.get(PP + path, timeout=timeout)
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None


def live_slide() -> tuple[str, str]:
    """(text of the slide on the output, text of the next one) from /v1/status/slide. Line breaks become newlines."""
    try:
        d = pp_get("/v1/status/slide") or {}
        cur = (d.get("current") or {}).get("text", "") or ""
        nxt = (d.get("next") or {}).get("text", "") or ""
        return cur.replace("\r", "\n"), nxt.replace("\r", "\n")
    except Exception:
        return "", ""


def live_set() -> list[str]:
    """Text of every slide of the set on the output (the whole Bible lookup, once one of its cards is live)."""
    try:
        d = (pp_get("/v1/presentation/active") or {}).get("presentation") or {}
        return [(sl.get("text") or "").replace("\r", "\n") for g in d.get("groups", []) for sl in g.get("slides", [])]
    except Exception:
        return []


def clear_output() -> None:
    try:
        pp_get("/v1/clear/layer/slide")
    except Exception:
        pass


def wait_for(predicate, limit: float = 1.0, step: float = 0.01) -> bool:
    end = time.time() + limit
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return False
