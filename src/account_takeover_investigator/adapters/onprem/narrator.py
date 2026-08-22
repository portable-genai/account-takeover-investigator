"""On-prem NarratorPort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

The client runs narration against their own in-tenancy model, so this binding refuses at call
time rather than returning ungrounded text. The engine's numbers stand on their own; a placeholder
that returned empty prose would hide that the narration seam was never bound.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.narrative import NarrativeBrief


class OnPremNarratorAdapter:
    """Satisfies NarratorPort but refuses: the client binds their own in-tenancy model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def narrate(self, brief: NarrativeBrief) -> str:
        raise NotImplementedError(
            "on-prem narration is a portability placeholder: bind the client's own in-tenancy "
            "model (see docs/onprem-migration.md)"
        )
