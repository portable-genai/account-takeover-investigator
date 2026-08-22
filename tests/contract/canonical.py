"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from account_takeover_investigator.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from account_takeover_investigator.domain.models import (
    ContainmentAction,
    ContainmentRecommendation,
    SessionSnapshot,
)
from account_takeover_investigator.domain.narrative import (
    NarrativeBrief,
)

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="triage",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="Acme Holdings (FICTIONAL): triaged high",
    citations=(Citation(source_id="case:acme", title="Case description", snippet="urgent"),),
)

#: The escalated result every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = sample_cases.make_investigation()

#: The subject and session every session/feature-store call is made for.
CANONICAL_SUBJECT = sample_cases.ESCALATING_REQUEST.subject_id
CANONICAL_SESSION = sample_cases.SESSION_ID

#: The containment every iam-actions implementation is handed (never reached on the real path).
CANONICAL_CONTAINMENT = ContainmentRecommendation(
    action=ContainmentAction.STEP_UP_AUTH,
    severity=Severity.HIGH,
    rationale="synthetic",
    requires_human_review=True,
)

#: The brief every narrator implementation is handed (engine facts only, subject pre-redacted).
CANONICAL_BRIEF = NarrativeBrief(
    subject="acct-REDACTED",
    session_id=CANONICAL_SESSION,
    band="critical",
    score=1.0,
    signal_lines=("impossible_travel: Impossible travel (+0.50)",),
    containment_lines=("suspend_credentials: revoke sessions",),
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _sessions_invoke(adapter: Any) -> Any:
    return adapter.fetch(CANONICAL_SUBJECT, CANONICAL_SESSION)


def _sessions_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, SessionSnapshot) and result.subject_id == CANONICAL_SUBJECT


def _feature_store_invoke(adapter: Any) -> Any:
    return adapter.fetch(CANONICAL_SUBJECT)


def _feature_store_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "known_device_ids", ())) and result.subject_id == CANONICAL_SUBJECT


def _iam_invoke(adapter: Any) -> Any:
    return adapter.enact(
        CANONICAL_CONTAINMENT, subject_id=CANONICAL_SUBJECT, actor=sample_cases.ACTOR
    )


def _iam_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.executed) == 1


def _narrator_invoke(adapter: Any) -> Any:
    return adapter.narrate(CANONICAL_BRIEF)


def _narrator_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, str) and CANONICAL_BRIEF.band in result.lower()


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated result to human review",
    ),
    "sessions": PortCase(
        invoke=_sessions_invoke,
        answered=_sessions_answered,
        # The lazy `google.cloud` BigQuery import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="return a raw, cited session snapshot",
    ),
    "feature_store": PortCase(
        invoke=_feature_store_invoke,
        answered=_feature_store_answered,
        # The lazy `google.cloud` aiplatform import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="return a raw, cited account baseline",
    ),
    "iam_actions": PortCase(
        invoke=_iam_invoke,
        answered=_iam_answered,
        # The lazy `google.auth` import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="record one enacted containment (never reached on the investigation path)",
    ),
    "narrator": PortCase(
        invoke=_narrator_invoke,
        answered=_narrator_answered,
        # The lazy `google.genai` import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="draft a grounded investigation summary",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches Hrz4 over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
