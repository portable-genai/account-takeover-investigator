"""Local FeatureStorePort: deterministic, cited account baseline for the offline profile.

Serves the known-good baseline (devices on file, home geography) from the same in-repo fixtures
the sessions adapter uses, so the snapshot and the baseline a run sees agree. SDK-free.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AccountBaseline
from .fixtures import baseline_for


class LocalFeatureStoreAdapter:
    """Serve the raw, cited account baseline from the in-repo fixtures."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, subject_id: str) -> AccountBaseline:
        return baseline_for(subject_id)
