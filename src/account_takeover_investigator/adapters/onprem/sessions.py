"""On-prem SessionSignalPort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

The client's own session and device telemetry lives in their environment, so this binding refuses
at call time rather than fabricating a snapshot. Refusing is the correct failure: a placeholder
that returned an empty snapshot would let the engine score a takeover as quiet.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SessionSnapshot


class OnPremSessionAdapter:
    """Satisfies SessionSignalPort but refuses: the client binds their own telemetry source."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, subject_id: str, session_id: str) -> SessionSnapshot:
        raise NotImplementedError(
            "on-prem session intake is a portability placeholder: bind the client's own session "
            "and device telemetry (see docs/onprem-migration.md)"
        )
