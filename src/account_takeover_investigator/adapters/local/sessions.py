"""Local SessionSignalPort: deterministic, cited fixtures for the SDK-free offline profile.

Returns byte-identical snapshots on every call for the same subject and session, so a replay
diffs exactly. No cloud SDK, no network: this is the working offline stack the gate and the demo
run on.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SessionSnapshot
from .fixtures import snapshot_for


class LocalSessionAdapter:
    """Serve raw, cited session snapshots from the in-repo fixtures."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, subject_id: str, session_id: str) -> SessionSnapshot:
        return snapshot_for(subject_id, session_id)
