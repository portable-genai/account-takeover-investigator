"""The deterministic fusion engine: per-signal uplift arithmetic, banding, containment.

The engine owns every consequential number. These tests pin the arithmetic (baseline plus summed
uplifts, clamped), the four detectors, the band cut-offs and the rule that nothing above MONITOR
is recommended without setting ``requires_human_review``. They also prove the fingerprint is
stable and that the whole assessment replays byte-identically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from account_takeover_investigator.domain.fusion_engine import FusionEngine, signal_key
from account_takeover_investigator.domain.kernel import Citation, Severity
from account_takeover_investigator.domain.models import (
    AccountBaseline,
    ContainmentAction,
    LoginEvent,
    RiskBand,
    SessionSnapshot,
    SignalKind,
)
from account_takeover_investigator.domain.policy import FusionPolicy

_AS_OF = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
_HOME = (1.29, 103.85)
_REMOTE = (37.77, -122.42)
_CITE = Citation(source_id="c", title="t", snippet="s")


def _baseline(devices: tuple[str, ...] = ("dev-1",)) -> AccountBaseline:
    return AccountBaseline(
        subject_id="acct",
        tenant="demo-bank",
        known_device_ids=devices,
        home_country="SG",
        home_latitude=_HOME[0],
        home_longitude=_HOME[1],
    )


def _login(minutes_ago: int, *, ok: bool, at: tuple[float, float], country: str) -> LoginEvent:
    return LoginEvent(
        event_id=f"e{minutes_ago}",
        occurred_at=_AS_OF - timedelta(minutes=minutes_ago),
        device_id="dev-1",
        ip="192.0.2.1",
        country=country,
        latitude=at[0],
        longitude=at[1],
        succeeded=ok,
        citation=_CITE,
    )


def _snapshot(
    *,
    device: str = "dev-1",
    at: tuple[float, float] = _HOME,
    country: str = "SG",
    biometric: float = 0.0,
    events: tuple[LoginEvent, ...] = (),
) -> SessionSnapshot:
    return SessionSnapshot(
        subject_id="acct",
        session_id="sess-1",
        tenant="demo-bank",
        as_of=_AS_OF,
        device_id=device,
        country=country,
        latitude=at[0],
        longitude=at[1],
        biometric_deviation=biometric,
        login_events=events,
        citations=(_CITE,),
    )


def test_a_quiet_session_fires_nothing_and_bands_low() -> None:
    engine = FusionEngine()
    assessment = engine.assess(snapshot=_snapshot(), baseline=_baseline())
    assert assessment.signals == ()
    assert assessment.score == 0.0
    assert assessment.band is RiskBand.LOW
    assert assessment.requires_human_review is False


def test_device_change_fires_when_the_device_is_not_on_file() -> None:
    engine = FusionEngine()
    signals = engine.detect(snapshot=_snapshot(device="dev-new"), baseline=_baseline())
    kinds = {s.kind for s in signals}
    assert SignalKind.DEVICE_CHANGE in kinds


def test_impossible_travel_fires_on_an_unphysical_speed() -> None:
    engine = FusionEngine()
    prior = _login(60, ok=True, at=_HOME, country="SG")
    snap = _snapshot(at=_REMOTE, country="US", events=(prior,))
    signals = engine.detect(snapshot=snap, baseline=_baseline(("dev-1",)))
    assert any(s.kind is SignalKind.IMPOSSIBLE_TRAVEL for s in signals)


def test_credential_stuffing_fires_at_the_threshold_and_not_below() -> None:
    engine = FusionEngine()
    fails = tuple(_login(i + 1, ok=False, at=_HOME, country="SG") for i in range(5))
    fired = engine.detect(snapshot=_snapshot(events=fails), baseline=_baseline())
    assert any(s.kind is SignalKind.CREDENTIAL_STUFFING for s in fired)

    four = tuple(_login(i + 1, ok=False, at=_HOME, country="SG") for i in range(4))
    below = engine.detect(snapshot=_snapshot(events=four), baseline=_baseline())
    assert not any(s.kind is SignalKind.CREDENTIAL_STUFFING for s in below)


def test_biometric_deviation_fires_at_or_above_the_policy_threshold() -> None:
    engine = FusionEngine()
    fired = engine.detect(snapshot=_snapshot(biometric=0.6), baseline=_baseline())
    assert any(s.kind is SignalKind.BIOMETRIC_DEVIATION for s in fired)
    quiet = engine.detect(snapshot=_snapshot(biometric=0.59), baseline=_baseline())
    assert not any(s.kind is SignalKind.BIOMETRIC_DEVIATION for s in quiet)


def test_the_score_is_baseline_plus_summed_uplifts_clamped() -> None:
    policy = FusionPolicy(device_change_uplift=0.35, biometric_deviation_uplift=0.25)
    engine = FusionEngine.from_policy(policy)
    snap = _snapshot(device="dev-new", biometric=0.7)
    signals = engine.detect(snapshot=snap, baseline=_baseline())
    score, band = engine.score(signals)
    assert score == 0.6  # 0.0 + 0.35 + 0.25
    assert band is RiskBand.HIGH
    # One uplift line per signal, and their sum reproduces the score minus the base.
    assert round(sum(s.uplift for s in signals), 4) == 0.6


def test_the_score_clamps_at_the_policy_ceiling() -> None:
    engine = FusionEngine()
    prior = _login(60, ok=True, at=_HOME, country="SG")
    fails = tuple(_login(i + 1, ok=False, at=_REMOTE, country="US") for i in range(6))
    snap = _snapshot(
        device="dev-new", at=_REMOTE, country="US", biometric=0.9, events=(prior, *fails)
    )
    assessment = engine.assess(snapshot=snap, baseline=_baseline())
    assert assessment.score == 1.0
    assert assessment.band is RiskBand.CRITICAL
    assert len(assessment.signals) == 4


def test_containment_above_monitor_always_demands_human_review() -> None:
    engine = FusionEngine()
    critical = engine.recommend(RiskBand.CRITICAL, ())
    assert all(c.requires_human_review for c in critical)
    assert any(c.action is ContainmentAction.SUSPEND_CREDENTIALS for c in critical)
    low = engine.recommend(RiskBand.LOW, ())
    assert [c.action for c in low] == [ContainmentAction.MONITOR]
    assert all(not c.requires_human_review for c in low)


def test_signal_keys_are_stable_and_the_assessment_replays_identically() -> None:
    engine = FusionEngine()
    snap = _snapshot(device="dev-new", biometric=0.8)
    a = engine.assess(snapshot=snap, baseline=_baseline())
    b = engine.assess(snapshot=snap, baseline=_baseline())
    assert a == b
    assert signal_key(SignalKind.DEVICE_CHANGE, "acct", "dev-new") == signal_key(
        SignalKind.DEVICE_CHANGE, "acct", "dev-new"
    )


def test_worst_signal_severity_wins() -> None:
    engine = FusionEngine()
    prior = _login(60, ok=True, at=_HOME, country="SG")
    snap = _snapshot(at=_REMOTE, country="US", events=(prior,))
    assessment = engine.assess(snapshot=snap, baseline=_baseline())
    assert assessment.severity is Severity.CRITICAL
