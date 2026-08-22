"""IamActionsPort: the boundary that WOULD enact a containment, and that this service never calls.

Containment is consequential, so the investigation service does not execute it. It routes every
recommended containment to a human through the review console (rule R8), and only an approved
containment would ever reach this port. The port exists so the enact seam is named, typed and
swappable (a managed MCP IAM adapter, a local fixture executor, an on-premises placeholder), and
``tests/unit/test_containment_never_executes.py`` asserts that a run producing a containment
recommendation makes ZERO calls here. An adapter is not the same as an action taken.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ContainmentRecommendation


@runtime_checkable
class IamActionsPort(Protocol):
    def enact(
        self, recommendation: ContainmentRecommendation, *, subject_id: str, actor: str
    ) -> str:
        """Enact one APPROVED containment and return an execution reference.

        Never called from the investigation path: a recommendation is routed for human approval
        first. ``actor`` is the verified approver, never a client-asserted one.
        """
        ...
