"""Watch folder service for Pearl's File Tools.

Wraps watchdog (real-time) with a polling fallback when watchdog is not installed.
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    # Stub so the rest of the module can reference the name without crashing
    FileSystemEventHandler = object  # type: ignore


@dataclass
class WatchRule:
    watch_dir: str
    profile_name: str = ""
    enabled: bool = True


if HAS_WATCHDOG:

    class _SettleHandler(FileSystemEventHandler):
        """Debounce file-system events with a 2-second settle timer."""

        def __init__(self, callback: Callable[[Path], None]):
            super().__init__()
            self._callback = callback
            self._timers: Dict[str, threading.Timer] = {}
            self._lock = threading.Lock()

        def _schedule(self, path: str):
            with self._lock:
                existing = self._timers.pop(path, None)
                if existing is not None:
                    existing.cancel()
                t = threading.Timer(2.0, self._fire, args=(path,))
                self._timers[path] = t
                t.start()

        def _fire(self, path: str):
            with self._lock:
                self._timers.pop(path, None)
            self._callback(Path(path))

        def on_created(self, event):
            if not event.is_directory:
                self._schedule(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._schedule(event.dest_path)

        def cancel_all(self):
            with self._lock:
                for t in self._timers.values():
                    t.cancel()
                self._timers.clear()


class WatchService:
    """Start/stop folder watchers; drive a poll fallback when watchdog is absent."""

    # Poll-mode debounce — file must report the same size on this many
    # consecutive polls before its callback is fired. Mirrors the 2-second
    # _SettleHandler used by the watchdog branch.
    POLL_SETTLE_PASSES = 2

    def __init__(self):
        self._observers: List = []  # watchdog Observer instances
        self._handlers: List = []  # _SettleHandler instances
        self._rules: List[WatchRule] = []
        self._callback: Optional[Callable[[Path, str], None]] = None
        self._snapshot: Dict[str, set] = {}
        # rule_dir → {Path: (size, stable_pass_count)}
        self._pending: Dict[str, Dict[Path, tuple]] = {}
        self._active = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, rules: List[WatchRule], callback: Callable[[Path, str], None]):
        """Start watching.  *callback* receives (Path, profile_name)."""
        self._rules = rules
        self._callback = callback
        self._active = True

        if HAS_WATCHDOG:
            self._start_watchdog(rules, callback)
        else:
            self._start_poll_mode(rules)

    def _start_watchdog(self, rules: List[WatchRule], callback: Callable[[Path, str], None]):
        for rule in self._enabled_rules(rules):
            watch_dir = Path(rule.watch_dir)
            if not watch_dir.is_dir():
                continue

            def make_cb(pname: str) -> Callable[[Path], None]:
                def cb(path: Path):
                    callback(path, pname)

                return cb

            handler = _SettleHandler(make_cb(rule.profile_name))
            observer = Observer()
            observer.schedule(handler, str(watch_dir), recursive=False)
            observer.start()
            self._observers.append(observer)
            self._handlers.append(handler)

    def _start_poll_mode(self, rules: List[WatchRule]):
        self._snapshot = {}
        for rule in self._enabled_rules(rules):
            watch_dir = Path(rule.watch_dir)
            if watch_dir.is_dir():
                self._snapshot[rule.watch_dir] = self._scan(watch_dir)

    def stop(self):
        """Stop all observers and cancel pending settle timers."""
        self._active = False
        for handler in self._handlers:
            handler.cancel_all()
        for observer in self._observers:
            observer.stop()
            observer.join()
        self._observers.clear()
        self._handlers.clear()

    def poll_once(self):
        """Compare current file listing against snapshot; debounce by file size.

        A newly-seen file enters a "pending" state and is only emitted via the
        callback once its size stays constant across :data:`POLL_SETTLE_PASSES`
        successive polls. This prevents a downstream ingest from firing on a
        render that's still being written by an NLE.
        """
        if self._callback is None:
            return
        for rule in self._enabled_rules(self._rules):
            watch_dir = Path(rule.watch_dir)
            if not watch_dir.is_dir():
                continue
            current = self._scan(watch_dir)
            prev = self._snapshot.get(rule.watch_dir, set())
            settle = self._pending.setdefault(rule.watch_dir, {})

            for p in current - prev:
                settle.setdefault(p, (-1, 0))

            self._settle_pending(settle, rule.profile_name)
            self._snapshot[rule.watch_dir] = current

    def _settle_pending(self, settle: dict, profile_name: str):
        for p in list(settle.keys()):
            size = self._read_file_size(p)
            if size is None:
                settle.pop(p, None)
                continue
            last_size, passes = settle[p]
            passes = passes + 1 if size == last_size else 0
            if passes >= self.POLL_SETTLE_PASSES:
                self._callback(p, profile_name)
                settle.pop(p, None)
            else:
                settle[p] = (size, passes)

    @property
    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _enabled_rules(rules: List[WatchRule]) -> List[WatchRule]:
        return [r for r in rules if r.enabled]

    @staticmethod
    def _read_file_size(p: Path) -> Optional[int]:
        if not p.exists():
            return None
        try:
            return p.stat().st_size
        except OSError:
            return None

    @staticmethod
    def _scan(directory: Path) -> set:
        """Return the set of file Paths directly inside *directory*."""
        try:
            return {p for p in directory.iterdir() if p.is_file()}
        except PermissionError:
            return set()
