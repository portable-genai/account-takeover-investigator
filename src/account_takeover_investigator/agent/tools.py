"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** An escalated investigation is ROUTED from inside the
  tool, in the same call that produced it. An agent surface that only returned the flag would be
  a third place an escalation can quietly stop, after the API and the CLI.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with no
  ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.fusion_engine import FusionEngine
from ..domain.investigation_service import InvestigationService
from ..domain.models import InvestigationRequest
from ..domain.pii import PII_PATTERNS

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "account-takeover-investigator-agent"


def _resolve(container: Container | None, settings: Settings | None) -> Container:
    return container if container is not None else build_container(settings)


def _service(container: Container) -> InvestigationService:
    return InvestigationService(
        container.sessions,
        container.feature_store,
        container.narrator,
        container.audit,
        tracer=container.tracer,
        engine=FusionEngine.from_policy(container.settings.policy),
    )


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result is not an API response. The API returns to the authenticated caller the data
    that caller asked about; a TOOL result goes into a model's context, and P-04 says minimise
    the data that reaches a model. Walking the whole structure rather than a few named fields
    means a future field cannot arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def investigate_session(
    subject_id: str,
    session_id: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
    container: Container | None = None,
) -> dict[str, Any]:
    """Investigate one account session for takeover risk and route it when it escalates.

    Fuses the session's device, travel, credential-stuffing and behavioural-biometric signals
    into a deterministic risk band, writes an already-redacted audit event, and, when the
    recommended containment is consequential, routes the result to the human-review console
    (rule R8). Containment is never enacted here; it is recommended and routed for approval.

    Args:
      subject_id: The account under investigation.
      session_id: The session to assess.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on an outbound review.

    Returns:
      A JSON-safe result dict with every string masked for personal data (P-04: a tool result
      goes into a model's context), plus ``review_ref``: where the escalation WENT. It is empty
      only when the result did not escalate.
    """
    resolved = _resolve(container, settings)
    result = _service(resolved).investigate(
        InvestigationRequest(subject_id=subject_id, session_id=session_id, tenant=tenant),
        actor=actor,
    )
    review_ref = ""
    if result.requires_human_review:
        review_ref = resolved.review_router.route(result, maker=actor, tenant=tenant)
    payload = _redacted(to_jsonable(result))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("an investigation result must serialise to a JSON object")
    # Attached after the redaction pass: it is a routing reference, not narrative text.
    payload["review_ref"] = review_ref
    return payload


def list_ato_queue(
    settings: Settings | None = None,
    container: Container | None = None,
) -> dict[str, Any]:
    """List the account-takeover reviews this process has routed but not yet flushed to Hrz7.

    Reads the review router's outbox, so a reviewer or an operator can see what is queued for
    human disposition. Every payload is already redacted on the wire; this masks again on the way
    to a model. Where the bound router keeps no local queue (the managed and on-premises
    families), the list is empty and the note says so.

    Returns:
      A JSON-safe dict with ``pending`` (the count) and ``items`` (the queued reviews, masked).
    """
    resolved = _resolve(container, settings)
    outbox = getattr(resolved.review_router, "outbox", None)
    if outbox is None:
        return {"pending": 0, "items": [], "note": "the bound review router keeps no local queue"}
    entries = list(outbox.pending())
    items = _redacted(to_jsonable([entry.review for entry in entries]))
    return {"pending": len(entries), "items": items}


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (investigate_session, list_ato_queue)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path).

    The import is deliberately here rather than at module scope: without it this module, the
    card and every tool would need an agent runtime installed to be imported at all, and the
    offline gate installs none.
    """
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
