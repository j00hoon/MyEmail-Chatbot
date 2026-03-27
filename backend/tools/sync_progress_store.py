from dataclasses import asdict, dataclass
from threading import Lock

from schemas import SyncStatusResponse


@dataclass
class SyncProgressState:
    state: str = "idle"
    stage: str = "Ready"
    progress: int = 0
    detail: str = "No sync in progress."
    fetched_count: int = 0
    saved_count: int = 0
    indexed_count: int = 0


class SyncProgressStore:
    def __init__(self):
        self._lock = Lock()
        self._state = SyncProgressState()

    def snapshot(self):
        with self._lock:
            return SyncStatusResponse(**asdict(self._state))

    def start(self, requested_count: int):
        with self._lock:
            self._state = SyncProgressState(
                state="running",
                stage="Connecting to Gmail",
                progress=5,
                detail=f"Preparing to sync up to {requested_count} recent emails.",
            )

    def update(
        self,
        *,
        stage: str | None = None,
        progress: int | None = None,
        detail: str | None = None,
        fetched_count: int | None = None,
        saved_count: int | None = None,
        indexed_count: int | None = None,
    ):
        with self._lock:
            if stage is not None:
                self._state.stage = stage
            if progress is not None:
                self._state.progress = max(0, min(100, progress))
            if detail is not None:
                self._state.detail = detail
            if fetched_count is not None:
                self._state.fetched_count = fetched_count
            if saved_count is not None:
                self._state.saved_count = saved_count
            if indexed_count is not None:
                self._state.indexed_count = indexed_count

    def finish(self, *, fetched_count: int, saved_count: int, indexed_count: int):
        with self._lock:
            self._state = SyncProgressState(
                state="completed",
                stage="Sync complete",
                progress=100,
                detail="Gmail sync and indexing completed.",
                fetched_count=fetched_count,
                saved_count=saved_count,
                indexed_count=indexed_count,
            )

    def fail(self, detail: str):
        with self._lock:
            self._state.state = "failed"
            self._state.stage = "Sync failed"
            self._state.progress = 100
            self._state.detail = detail
