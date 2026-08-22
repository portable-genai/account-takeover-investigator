"""Local IamActionsPort: a fixture executor that RECORDS an enacted containment (no real IAM).

The investigation service never calls this: containment is routed for human approval first. The
adapter exists so the enact seam has a working offline implementation for the parity suites and
so an approved-containment flow can be demonstrated end to end without a cloud project. It records
what it was asked to enact and returns a reference; it takes no real action. ``executed`` exposes
the record so a test can assert the service made ZERO calls here on the investigation path.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ContainmentRecommendation


class LocalIamActionsAdapter:
    """Record enacted containments in memory for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._executed: list[tuple[str, str, str]] = []

    def enact(
        self, recommendation: ContainmentRecommendation, *, subject_id: str, actor: str
    ) -> str:
        self._executed.append((recommendation.action.value, subject_id, actor))
        return f"iam-local:{recommendation.action.value}:{len(self._executed)}"

    @property
    def executed(self) -> tuple[tuple[str, str, str], ...]:
        """The containments this adapter was asked to enact (empty on the investigation path)."""
        return tuple(self._executed)
