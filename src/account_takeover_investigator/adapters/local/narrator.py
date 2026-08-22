"""Local NarratorPort: the deterministic, grounded-by-construction summary (no model).

Returns the same draft the service falls back to when a managed model's output fails the
groundedness check, so the offline profile produces readable investigation prose with no cloud
SDK and no network, and that prose can never state a figure the engine did not produce.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.narrative import NarrativeBrief, draft_narrative


class LocalNarratorAdapter:
    """Compose the investigation summary from engine facts alone (SDK-free, grounded)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def narrate(self, brief: NarrativeBrief) -> str:
        return draft_narrative(brief)
