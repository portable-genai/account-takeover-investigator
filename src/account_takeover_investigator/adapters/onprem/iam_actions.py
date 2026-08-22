"""On-prem IamActionsPort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

Containment enactment runs against the client's own identity platform, so this binding refuses at
call time. It is never reached on the investigation path in any profile (containment is routed for
approval first); the exit family refuses here too rather than pretending to have acted.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ContainmentRecommendation


class OnPremIamActionsAdapter:
    """Satisfies IamActionsPort but refuses: the client binds their own identity platform."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def enact(
        self, recommendation: ContainmentRecommendation, *, subject_id: str, actor: str
    ) -> str:
        raise NotImplementedError(
            "on-prem containment enactment is a portability placeholder: bind the client's own "
            "identity platform (see docs/onprem-migration.md). Containment is enacted only after "
            "a human approves the routed review (rule R8)"
        )
