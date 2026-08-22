"""GCP IamActionsPort: containment enacted through an MCP IAM tool server (lazy SDK import).

Never called on the investigation path (containment is routed for approval first). When an
approved containment is enacted, it runs through a governed MCP IAM tool rather than a raw IAM
call, so every action is itself audited and policy-checked at the tool boundary. The MCP client
import is lazy, so the offline profiles import this module with no SDK present.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ContainmentRecommendation


class CloudIamActionsAdapter:
    """Enact an approved containment through the managed MCP IAM tool server."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def enact(
        self, recommendation: ContainmentRecommendation, *, subject_id: str, actor: str
    ) -> str:  # pragma: no cover - needs live GCP
        # Lazy import: absent in the offline profile and in CI (hence import-not-found ignore).
        from google.auth import default as google_auth_default

        google_auth_default()
        raise NotImplementedError(
            "the managed MCP IAM enact path is deployment-specific: bind the MCP tool server "
            "endpoint and the IAM roles in infra/terraform. Containment is enacted only after a "
            "human approves the routed review (rule R8), never from the investigation path"
        )
