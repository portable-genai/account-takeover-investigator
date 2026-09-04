"""The investigation orchestrator: grounded narration, redact-before-audit, always-cited output.

Drives the REAL local adapters. Proves the service composes the deterministic engine with a
grounded narrator, redacts PII before the audit write, always cites, escalates exactly when a
consequential containment is recommended, and discards an ungrounded narration for the
deterministic draft.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from account_takeover_investigator.adapters._review_payload import result_to_review
from account_takeover_investigator.config import Settings, build_container
from account_takeover_investigator.domain.fusion_engine import FusionEngine
from account_takeover_investigator.domain.investigation_service import InvestigationService
from account_takeover_investigator.domain.kernel import Decision
from account_takeover_investigator.domain.models import InvestigationRequest, RiskBand
from account_takeover_investigator.domain.narrative import NarrativeBrief, is_grounded

from tests.fixtures import sample_cases


def _service(**overrides: object) -> tuple[InvestigationService, object]:
    settings = Settings(profile="local", audit_path=":memory:", tenant="demo-bank")
    container = build_container(settings)
    narrator = overrides.get("narrator", container.narrator)
    service = InvestigationService(
        container.sessions,
        container.feature_store,
        narrator,  # type: ignore[arg-type]
        container.audit,
        tracer=container.tracer,
        engine=FusionEngine.from_policy(container.settings.policy),
    )
    return service, container.audit


def _investigate(subject: str, service: InvestigationService) -> object:
    return service.investigate(
        InvestigationRequest(subject_id=subject, session_id="sess-1", tenant="demo-bank"),
        actor=sample_cases.ACTOR,
    )


def test_a_quiet_account_is_low_and_not_escalated() -> None:
    service, _ = _service()
    result = _investigate("acct-quiet", service)
    assert result.band is RiskBand.LOW
    assert result.decision is Decision.ALLOWED
    assert result.requires_human_review is False
    assert result.citations, "even a LOW result must carry a citation"


def test_a_takeover_is_critical_escalated_and_carries_signals() -> None:
    service, _ = _service()
    result = _investigate("acct-takeover", service)
    assert result.band is RiskBand.CRITICAL
    assert result.decision is Decision.ESCALATED
    assert result.requires_human_review is True
    assert result.signals and result.containments
    assert is_grounded(result.narrative, _assessment(result))


def test_the_narrative_is_grounded_in_engine_output() -> None:
    service, _ = _service()
    result = _investigate("acct-takeover", service)
    # Every number in the narrative appears in the engine assessment; there are no invented ones.
    assert is_grounded(result.narrative, _assessment(result))


def test_an_ungrounded_model_draft_is_discarded_for_the_deterministic_one() -> None:
    class _Fabricator:
        def narrate(self, brief: NarrativeBrief) -> str:
            return "The account lost 999999.99 dollars to the attacker overnight."

    service, _ = _service(narrator=_Fabricator())
    result = _investigate("acct-takeover", service)
    assert "999999.99" not in result.narrative, "an invented figure must not survive"
    assert is_grounded(result.narrative, _assessment(result))


def test_pii_in_the_subject_is_redacted_before_the_audit_write() -> None:
    service, audit = _service()
    service.investigate(
        InvestigationRequest(
            subject_id=sample_cases.PII_SUBJECT_ID, session_id="sess-1", tenant="demo-bank"
        ),
        actor=sample_cases.ACTOR,
    )
    records = audit.log.read_all()  # type: ignore[attr-defined]
    assert records
    summary = records[-1]["redacted_summary"]
    assert sample_cases.PLANTED_NRIC not in summary
    assert "REDACTED" in summary


def test_no_planted_identifier_reaches_the_model_the_worm_record_or_the_console() -> None:
    """The three sinks, one test: what the model reads, what the WORM record keeps, what leaves.

    The subject key carries a national id and the session key carries a mailbox, because those
    are two different paths: the subject is masked explicitly before the brief is built, while
    the session id was carried raw into the narrator's brief, into the citation LOCATOR the audit
    record stores, and into the review payload's source key. Scanning the summary alone sees none
    of that, which is the whole reason this test reads the fields beside it.
    """
    seen: list[NarrativeBrief] = []

    class _Tap:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def narrate(self, brief: NarrativeBrief) -> str:
            seen.append(brief)
            return self._inner.narrate(brief)  # type: ignore[attr-defined]

    settings = Settings(profile="local", audit_path=":memory:", tenant=sample_cases.TENANT)
    container = build_container(settings)
    service = InvestigationService(
        container.sessions,
        container.feature_store,
        _Tap(container.narrator),  # type: ignore[arg-type]
        container.audit,
        tracer=container.tracer,
        engine=FusionEngine.from_policy(container.settings.policy),
    )
    result = service.investigate(
        InvestigationRequest(
            subject_id=sample_cases.PII_SUBJECT_ID, session_id=sample_cases.PII_SESSION_ID
        ),
        actor=sample_cases.ACTOR,
    )
    planted = (sample_cases.PLANTED_NRIC, sample_cases.PLANTED_EMAIL)

    # 1. The model. Every field of the brief, not just the one that says "subject".
    assert seen, "the narrator must have been called"
    brief_text = json.dumps(asdict(seen[-1]), default=str)
    for token in planted:
        assert token not in brief_text, f"{token} reached the model in {brief_text!r}"

    # 2. The WORM record. Content fields only: `actor` is the verified principal and is an
    #    address by design, so scanning it would make this unfailable in the wrong direction.
    rows = [dict(row) for row in container.audit.log.read_all()]
    assert rows
    for row in rows:
        stored = row["redacted_summary"] + json.dumps(row["citations"], default=str)
        for token in planted:
            assert token not in stored, f"{token} survived into the WORM record: {stored!r}"

    # 3. What LEAVES for the review console (rule R8), locator and source key included.
    review = result_to_review(result, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)
    outbound = json.dumps(asdict(review), default=str)
    for token in planted:
        assert token not in outbound, f"{token} left for human-review-console in {outbound!r}"


def test_the_investigation_path_never_enacts_a_containment() -> None:
    """Slice 3: a recommended containment yields a routed review and ZERO iam-actions calls."""
    settings = Settings(profile="local", audit_path=":memory:", tenant="demo-bank")
    container = build_container(settings)
    service = InvestigationService(
        container.sessions,
        container.feature_store,
        container.narrator,
        container.audit,
        tracer=container.tracer,
        engine=FusionEngine.from_policy(container.settings.policy),
    )
    result = _investigate("acct-takeover", service)
    assert result.requires_human_review is True
    # The iam-actions adapter exists and is bound, but the investigation path never called it.
    assert container.iam_actions.executed == ()  # type: ignore[attr-defined]


def _assessment(result: object):
    """Rebuild the engine assessment for a result so groundedness can be checked independently."""
    from account_takeover_investigator.domain.models import FusionAssessment

    return FusionAssessment(
        subject_id=result.subject,  # type: ignore[attr-defined]
        session_id=result.session_id,  # type: ignore[attr-defined]
        tenant=result.tenant,  # type: ignore[attr-defined]
        score=result.score,  # type: ignore[attr-defined]
        baseline_score=result.baseline_score,  # type: ignore[attr-defined]
        band=result.band,  # type: ignore[attr-defined]
        severity=result.severity,  # type: ignore[attr-defined]
        signals=result.signals,  # type: ignore[attr-defined]
        containments=result.containments,  # type: ignore[attr-defined]
        as_of=result.as_of,  # type: ignore[attr-defined]
    )
