"""Canonical synthetic cases, shared by the unit and contract suites.

Every party is obviously fictional and every identifier is invented or an RFC 5737 / RFC 3849
literal. The subject ids match the offline fixtures in ``adapters/local/fixtures.py``: one quiet
account, one full takeover. One canonical :class:`Investigation` is enough for the contract
suite, because parity means the SAME request through every implementation, so the request has to
have one home rather than being retyped per test.
"""

from __future__ import annotations

from account_takeover_investigator.domain.kernel import Citation, Decision, Severity
from account_takeover_investigator.domain.models import (
    ContainmentAction,
    ContainmentRecommendation,
    FusedSignal,
    Investigation,
    InvestigationRequest,
    RiskBand,
    SignalKind,
)

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: The canonical session id every request in the suite uses.
SESSION_ID = "sess-001"

#: A subject whose fixture MUST escalate: a takeover with impossible travel and a new device.
ESCALATING_REQUEST = InvestigationRequest(
    subject_id="acct-takeover", session_id=SESSION_ID, tenant=TENANT
)

#: A subject whose fixture must NOT escalate: a quiet account on a known device.
ROUTINE_REQUEST = InvestigationRequest(
    subject_id="acct-quiet", session_id=SESSION_ID, tenant=TENANT
)

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

#: A second planted identifier, in the SESSION key rather than the subject key. An intake that
#: carries the reporting mailbox in its case reference is ordinary, and the session id reaches
#: sinks the subject id does not (the narrator's brief, the citation locator, the Hrz7 payload),
#: so a redaction proof that only plants in the subject cannot see those paths at all.
PLANTED_EMAIL = "mallory.tan@example.com"

#: A subject id that carries personal data, for the redact-before-anything proofs.
PII_SUBJECT_ID = f"acct-{PLANTED_NRIC}"

#: A session id that carries personal data, for the same proofs on the other identifier path.
PII_SESSION_ID = f"sess-{PLANTED_EMAIL}"


def make_investigation(
    *,
    subject: str = "acct-takeover",
    severity: Severity = Severity.CRITICAL,
    band: RiskBand = RiskBand.CRITICAL,
    requires_human_review: bool = True,
) -> Investigation:
    """A canonical escalated investigation, for the review-router contract call (rule R8)."""
    citation = Citation(
        source_id=f"session:{SESSION_ID}", title="Session under investigation", snippet="takeover"
    )
    signal = FusedSignal(
        key="impossible_travel:deadbeefdeadbeef",
        kind=SignalKind.IMPOSSIBLE_TRAVEL,
        severity=Severity.CRITICAL,
        summary="Impossible travel: SG to US implies 13585 km/h.",
        detail="synthetic",
        uplift=0.5,
        citation=citation,
    )
    containment = ContainmentRecommendation(
        action=ContainmentAction.SUSPEND_CREDENTIALS,
        severity=severity,
        rationale="CRITICAL risk: recommend to revoke sessions (human approval required to enact)",
        requires_human_review=True,
        citations=(citation,),
    )
    return Investigation(
        subject=subject,
        session_id=SESSION_ID,
        tenant=TENANT,
        severity=severity,
        decision=Decision.ESCALATED if requires_human_review else Decision.ALLOWED,
        band=band,
        score=1.0,
        baseline_score=0.0,
        summary=f"{subject}: {band.value.upper()} account-takeover risk (1.00)",
        narrative="synthetic grounded narrative",
        signals=(signal,),
        containments=(containment,),
        requires_human_review=requires_human_review,
        citations=(citation,),
        as_of="2026-03-01T09:00:00+00:00",
    )
