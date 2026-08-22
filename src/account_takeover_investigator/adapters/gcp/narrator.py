"""GCP NarratorPort: the investigation summary drafted by Gemini (lazy SDK import).

The model is given the engine brief and asked to restate it. The service checks the result for
groundedness and discards it for the deterministic draft on failure, so a fabricated figure never
reaches a reviewer. The ``google-genai`` import is lazy, so the offline profiles import this
module with no SDK present.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.narrative import NarrativeBrief


class CloudNarratorAdapter:
    """Draft the investigation summary with a pinned Gemini model, restating engine facts only."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def narrate(self, brief: NarrativeBrief) -> str:  # pragma: no cover - needs live GCP
        # Lazy import: absent in the offline profile and in CI (hence import-not-found ignore).
        from google import genai

        client = genai.Client(vertexai=True, location=self._settings.region)
        del client  # constructed to prove the SDK path; the call itself is deployment-specific
        raise NotImplementedError(
            "the managed narration path is deployment-specific: bind the pinned Gemini model and "
            f"the region ({self._settings.region}) in infra/terraform. The engine owns every "
            "number; the model only restates the brief"
        )
