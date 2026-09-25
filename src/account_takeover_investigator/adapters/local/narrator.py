"""Local NarratorPort: the deterministic, grounded-by-construction summary (no model).

Returns the same draft the service falls back to when a managed model's output fails the
groundedness check, so the offline profile produces readable investigation prose with no cloud
SDK and no network, and that prose can never state a figure the engine did not produce.
"""

from __future__ import annotations

from hex_service_kit import provenance

from ...config import Settings
from ...domain.narrative import NarrativeBrief, draft_narrative


class LocalNarratorAdapter:
    """Compose the investigation summary from engine facts alone (SDK-free, grounded)."""

    #: What this narrator answers as, for the console's model pill: the name ``generator_model``
    #: reports under ``local``, so the pill before and after an answer agree.
    MODEL = "deterministic-offline-stub"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def narrate(self, brief: NarrativeBrief) -> str:
        provenance.note_model(self.MODEL)
        return draft_narrative(brief)
