"""Thread-safe control of the running Cursor agent subprocess."""

from __future__ import annotations

import subprocess
import threading
from typing import Any, Callable, Optional


class AgentRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._busy = False
        self._stop_requested = False
        self._process: Optional[subprocess.Popen] = None

    @property
    def stop_requested(self) -> bool:
        with self._lock:
            return self._stop_requested

    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def set_process(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._process = proc

    def begin_run(self) -> None:
        with self._lock:
            self._busy = True
            self._stop_requested = False
            self._process = None

    def clear(self) -> None:
        with self._lock:
            self._busy = False
            self._stop_requested = False
            self._process = None

    def request_stop(self) -> bool:
        """Request cancel; kill subprocess if running. Returns True if a run was active."""
        with self._lock:
            was_busy = self._busy
            self._stop_requested = True
            proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        return was_busy

    def start_job(self, target: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Start agent work in a background thread. Returns False if already busy."""
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._stop_requested = False
            self._process = None

        def worker() -> None:
            try:
                target(*args, **kwargs)
            finally:
                self.clear()

        threading.Thread(target=worker, daemon=False).start()
        return True


_runtime = AgentRuntime()


def get_runtime() -> AgentRuntime:
    return _runtime
