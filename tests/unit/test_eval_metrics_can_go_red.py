"""Every eval metric is proven able to go RED, per the house rule: a metric that cannot fail,
or that reads the pipeline's own answer, is not a metric.

Each metric is scored against the dataset's independent oracle (the expected band, the expected
review flag, the engine assessment), and each is given a (green, red) pair through
``agent_eval_kit.assert_each_can_go_red`` so a scorer that silently always returns 1.0 fails this
suite rather than passing the gate vacuously.
"""

from __future__ import annotations

from agent_eval_kit import assert_each_can_go_red

from account_takeover_investigator.domain.kernel import Citation, Severity
from account_takeover_investigator.domain.models import (
    ContainmentAction,
    ContainmentRecommendation,
    FusedSignal,
    FusionAssessment,
    RiskBand,
    SignalKind,
)
from account_takeover_investigator.domain.narrative import is_grounded

_ASSESSMENT = FusionAssessment(
    subject_id="acct-takeover",
    session_id="sess-1",
    tenant="demo-bank",
    score=0.85,
    baseline_score=0.0,
    band=RiskBand.CRITICAL,
    severity=Severity.CRITICAL,
    signals=(
        FusedSignal(
            key="device_change:abc",
            kind=SignalKind.DEVICE_CHANGE,
            severity=Severity.HIGH,
            summary="Login from an unrecognised device (dev-xx-99).",
            detail="synthetic",
            uplift=0.35,
            citation=Citation(source_id="c", title="t"),
        ),
    ),
    containments=(
        ContainmentRecommendation(
            action=ContainmentAction.LOCK_SESSION,
            severity=Severity.CRITICAL,
            rationale="synthetic",
            requires_human_review=True,
        ),
    ),
    as_of="2026-03-01T09:00:00+00:00",
)


def _band_match(pair: tuple[str, str]) -> float:
    predicted, expected = pair
    return 1.0 if predicted == expected else 0.0


def _review_match(pair: tuple[bool, bool]) -> float:
    predicted, expected = pair
    return 1.0 if predicted == expected else 0.0


def _grounded(narrative: str) -> float:
    return 1.0 if is_grounded(narrative, _ASSESSMENT) else 0.0


def test_fusion_accuracy_can_go_red() -> None:
    assert_each_can_go_red(
        _band_match,
        {"critical": (("critical", "critical"), ("low", "critical"))},
        threshold=0.80,
        metric="fusion_accuracy",
    )


def test_review_safety_can_go_red() -> None:
    assert_each_can_go_red(
        _review_match,
        {"escalating": ((True, True), (False, True))},
        threshold=1.0,
        metric="review_safety",
    )


def test_groundedness_can_go_red() -> None:
    grounded = "Session sess-1 scored 0.85 with a +0.35 device-change uplift."
    fabricated = "The account lost 999999.99 dollars overnight to the attacker."
    assert_each_can_go_red(
        _grounded,
        {"one": (grounded, fabricated)},
        threshold=0.99,
        metric="groundedness",
    )
