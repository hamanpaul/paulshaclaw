from __future__ import annotations

import os
import threading
from pathlib import Path

from .config import MonitorConfig
from .server import MonitorServer
from .snapshot import ChangeEvent, SnapshotStore
from .watcher import WatchdogFileWatcher, Watcher


class ProjectMonitorService:
    """Stage 9 long-lived service runtime.

    Composes the snapshot store, filesystem watcher, and Unix-socket server.
    State remains in memory; project truth is always re-derived from files.
    """

    def __init__(
        self,
        *,
        config: MonitorConfig,
        watcher: Watcher | None = None,
        store: SnapshotStore | None = None,
        server: MonitorServer | None = None,
    ) -> None:
        self._config = config
        self._store = store or SnapshotStore(config=config)
        self._watcher = watcher or WatchdogFileWatcher(
            debounce_ms=config.watch_debounce_ms
        )
        self._server = server or MonitorServer(
            store=self._store,
            socket_path=config.socket_path,
        )
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._debounce_lock = threading.Lock()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._project_roots: dict[str, Path] = {}
        self._watched_roots: set[Path] = set()

    def run_forever(self) -> None:
        self._prepare_run_dir()
        self._store.load()
        self._sync_project_roots()
        self._install_watches()
        self._start_poll_thread()
        try:
            self._server.serve_forever()
        finally:
            self._shutdown()

    def stop(self) -> None:
        self._stop_event.set()
        self._cancel_debounce_timers()
        self._watcher.stop()
        self._server.stop()

    def _prepare_run_dir(self) -> None:
        run_dir = self._config.socket_path.parent
        run_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(str(run_dir), 0o700)

    def _start_poll_thread(self) -> None:
        if self._poll_thread is not None:
            return
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        interval = max(0.1, float(self._config.poll_interval_seconds))
        while not self._stop_event.wait(interval):
            self._publish_refresh(self._store.refresh())

    def _sync_project_roots(self) -> None:
        self._project_roots = {
            state.project_id: Path(state.path)
            for state in self._store.current_snapshot()
            if not state.legacy
        }

    def _install_watches(self) -> None:
        for project_root in self._project_roots.values():
            if project_root in self._watched_roots:
                continue
            self._watcher.watch(project_root, self._handle_fs_event)
            self._watched_roots.add(project_root)

    def _handle_fs_event(self, path: Path) -> None:
        project_id = self._project_id_for_path(Path(path))
        if project_id is None:
            self._publish_refresh(self._store.refresh())
            return
        self._schedule_project_refresh(project_id)

    def _project_id_for_path(self, path: Path) -> str | None:
        best_match: tuple[str, int] | None = None
        for project_id, project_root in self._project_roots.items():
            try:
                path.relative_to(project_root)
            except ValueError:
                continue
            root_depth = len(project_root.parts)
            if best_match is None or root_depth > best_match[1]:
                best_match = (project_id, root_depth)
        return best_match[0] if best_match is not None else None

    def _schedule_project_refresh(self, project_id: str) -> None:
        delay_seconds = max(0.0, self._config.watch_debounce_ms / 1000.0)
        with self._debounce_lock:
            previous = self._debounce_timers.get(project_id)
            if previous is not None:
                previous.cancel()
            timer = threading.Timer(
                delay_seconds,
                self._flush_project_refresh,
                args=(project_id,),
            )
            timer.daemon = True
            self._debounce_timers[project_id] = timer
            timer.start()

    def _flush_project_refresh(self, project_id: str) -> None:
        with self._debounce_lock:
            self._debounce_timers.pop(project_id, None)
        if self._stop_event.is_set():
            return
        event = self._store.refresh_project(project_id)
        self._sync_project_roots()
        self._install_watches()
        if event is not None:
            self._server.publish_events((event,))

    def _publish_refresh(self, events: tuple[ChangeEvent, ...]) -> None:
        self._sync_project_roots()
        self._install_watches()
        if events:
            self._server.publish_events(events)

    def _cancel_debounce_timers(self) -> None:
        with self._debounce_lock:
            timers = tuple(self._debounce_timers.values())
            self._debounce_timers.clear()
        for timer in timers:
            timer.cancel()

    def _shutdown(self) -> None:
        self._stop_event.set()
        self._cancel_debounce_timers()
        self._watcher.stop()
        self._server.stop()
        if (
            self._poll_thread is not None
            and self._poll_thread.is_alive()
            and threading.current_thread() is not self._poll_thread
        ):
            self._poll_thread.join(timeout=2.0)
