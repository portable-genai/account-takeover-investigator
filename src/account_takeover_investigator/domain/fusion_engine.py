"""Deterministic signal-fusion engine: the consequential arithmetic, no model in sight.

Four takeover signals (device change, impossible travel, credential-stuffing velocity and
behavioural-biometric deviation) are detected from the raw session snapshot and the account
baseline, each raising the risk score by one auditable per-signal uplift line. The score is
``base + sum(uplifts)`` clamped to the policy range, the band comes from policy cut-offs, and the
containment set is a deterministic function of the band. The engine owns the score, the band and
the recommendation; **the LLM owns nothing here and is not imported by this module.**

Every number is arithmetic over :class:`~account_takeover_investigator.domain.policy.FusionPolicy`.
Given the same snapshot, baseline and policy the whole assessment is byte-identical, so an auditor
can recompute it. ``signal_key`` fingerprints each anomaly (cribbed from the cdd-sow-research
perpetual-KYC engine) so re-runs diff exactly rather than fuzzily.

Pure standard library; no ports, no I/O, no clock of its own (``as_of`` rides on the snapshot).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .kernel import Citation, Severity
from .models import (
    AccountBaseline,
    ContainmentAction,
    ContainmentRecommendation,
    FusedSignal,
    FusionAssessment,
    LoginEvent,
    RiskBand,
    SessionSnapshot,
    SignalKind,
)
from .policy import FusionPolicy

#: Order signals for display and worst-severity selection (most severe first).
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}

#: The band a fused score maps to, and the severity that band carries.
_BAND_SEVERITY: dict[RiskBand, Severity] = {
    RiskBand.CRITICAL: Severity.CRITICAL,
    RiskBand.HIGH: Severity.HIGH,
    RiskBand.MEDIUM: Severity.MEDIUM,
    RiskBand.LOW: Severity.LOW,
}

#: The containment ladder per band. ``MONITOR`` is advisory (no human review); everything above
#: it is consequential, so it sets ``requires_human_review`` and the investigation escalates.
_CONTAINMENT_LADDER: dict[RiskBand, tuple[ContainmentAction, ...]] = {
    RiskBand.CRITICAL: (ContainmentAction.SUSPEND_CREDENTIALS, ContainmentAction.LOCK_SESSION),
    RiskBand.HIGH: (ContainmentAction.LOCK_SESSION, ContainmentAction.STEP_UP_AUTH),
    RiskBand.MEDIUM: (ContainmentAction.STEP_UP_AUTH,),
    RiskBand.LOW: (ContainmentAction.MONITOR,),
}


def signal_key(kind: SignalKind, *parts: str) -> str:
    """A stable fingerprint for one anomaly: ``<kind>:<16 hex>``.

    The digest is taken over the normalised identifying parts (case-folded, whitespace
    collapsed), so cosmetic differences in a provider's rendering do not look like a new signal,
    while a genuine change (a different device, a different origin) does.
    """
    normalised = "|".join(" ".join(part.split()).casefold() for part in parts)
    digest = hashlib.sha256(f"{kind.value}|{normalised}".encode()).hexdigest()[:16]
    return f"{kind.value}:{digest}"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/long points."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True, slots=True)
class FusionEngine:
    """Pure, deterministic detection, scoring, banding and containment recommendation."""

    policy: FusionPolicy = field(default_factory=FusionPolicy)

    @classmethod
    def from_policy(cls, policy: FusionPolicy) -> FusionEngine:
        """Build the engine from the bank-owned policy object (settings-driven)."""
        return cls(policy=policy)

    # ------------------------------------------------------------------ #
    # 1. Detection
    # ------------------------------------------------------------------ #
    def detect(
        self, *, snapshot: SessionSnapshot, baseline: AccountBaseline
    ) -> tuple[FusedSignal, ...]:
        """Detect the four takeover signals, each carrying its own uplift line and citation."""
        signals: list[FusedSignal] = []
        device = self._device_change(snapshot, baseline)
        if device is not None:
            signals.append(device)
        travel = self._impossible_travel(snapshot)
        if travel is not None:
            signals.append(travel)
        stuffing = self._credential_stuffing(snapshot)
        if stuffing is not None:
            signals.append(stuffing)
        biometric = self._biometric_deviation(snapshot)
        if biometric is not None:
            signals.append(biometric)
        return tuple(sorted(signals, key=lambda s: (_SEVERITY_RANK.get(s.severity, 9), s.key)))

    def _device_change(
        self, snapshot: SessionSnapshot, baseline: AccountBaseline
    ) -> FusedSignal | None:
        if snapshot.device_id in baseline.known_device_ids:
            return None
        known = len(baseline.known_device_ids)
        return FusedSignal(
            key=signal_key(SignalKind.DEVICE_CHANGE, snapshot.subject_id, snapshot.device_id),
            kind=SignalKind.DEVICE_CHANGE,
            severity=Severity.HIGH,
            summary=f"Login from an unrecognised device ({snapshot.device_id}).",
            detail=(
                f"Device {snapshot.device_id} is not among the {known} device(s) on file for "
                f"this account."
            ),
            uplift=self.policy.device_change_uplift,
            citation=_snapshot_citation(snapshot),
        )

    def _impossible_travel(self, snapshot: SessionSnapshot) -> FusedSignal | None:
        prior = self._prior_login(snapshot)
        if prior is None:
            return None
        distance = _haversine_km(
            prior.latitude, prior.longitude, snapshot.latitude, snapshot.longitude
        )
        if distance < self.policy.min_travel_km:
            return None
        hours = max((snapshot.as_of - prior.occurred_at).total_seconds() / 3600.0, 1e-9)
        speed = distance / hours
        if speed <= self.policy.impossible_speed_kmh:
            return None
        return FusedSignal(
            key=signal_key(
                SignalKind.IMPOSSIBLE_TRAVEL,
                snapshot.subject_id,
                prior.event_id,
                snapshot.device_id,
            ),
            kind=SignalKind.IMPOSSIBLE_TRAVEL,
            severity=Severity.CRITICAL,
            summary=(
                f"Impossible travel: {prior.country} to {snapshot.country} implies "
                f"{speed:.0f} km/h."
            ),
            detail=(
                f"{distance:.0f} km in {hours:.2f} h between logins ({prior.country} then "
                f"{snapshot.country}) implies {speed:.0f} km/h, above the "
                f"{self.policy.impossible_speed_kmh:.0f} km/h policy ceiling."
            ),
            uplift=self.policy.impossible_travel_uplift,
            citation=prior.citation,
        )

    def _credential_stuffing(self, snapshot: SessionSnapshot) -> FusedSignal | None:
        failures = self._recent_failures(snapshot)
        count = len(failures)
        if count < self.policy.stuffing_failure_threshold:
            return None
        window = self.policy.stuffing_window_minutes
        return FusedSignal(
            key=signal_key(
                SignalKind.CREDENTIAL_STUFFING, snapshot.subject_id, snapshot.session_id
            ),
            kind=SignalKind.CREDENTIAL_STUFFING,
            severity=Severity.HIGH,
            summary=f"Credential-stuffing velocity: {count} failed logins in {window} min.",
            detail=(
                f"{count} failed login attempts within {window} minutes before this session, at "
                f"or above the policy threshold of {self.policy.stuffing_failure_threshold}."
            ),
            uplift=self.policy.credential_stuffing_uplift,
            citation=failures[-1].citation,
        )

    def _biometric_deviation(self, snapshot: SessionSnapshot) -> FusedSignal | None:
        if snapshot.biometric_deviation < self.policy.biometric_threshold:
            return None
        return FusedSignal(
            key=signal_key(
                SignalKind.BIOMETRIC_DEVIATION, snapshot.subject_id, snapshot.session_id
            ),
            kind=SignalKind.BIOMETRIC_DEVIATION,
            severity=Severity.MEDIUM,
            summary=(
                f"Behavioural-biometric deviation {snapshot.biometric_deviation:.2f} from baseline."
            ),
            detail=(
                f"Session behavioural biometrics deviate {snapshot.biometric_deviation:.2f} "
                f"(0..1) from the account baseline, at or above the "
                f"{self.policy.biometric_threshold:.2f} policy threshold."
            ),
            uplift=self.policy.biometric_deviation_uplift,
            citation=_snapshot_citation(snapshot),
        )

    def _prior_login(self, snapshot: SessionSnapshot) -> LoginEvent | None:
        """The most recent SUCCESSFUL login strictly before this session's ``as_of``."""
        prior = [e for e in snapshot.login_events if e.succeeded and e.occurred_at < snapshot.as_of]
        if not prior:
            return None
        return max(prior, key=lambda e: e.occurred_at)

    def _recent_failures(self, snapshot: SessionSnapshot) -> tuple[LoginEvent, ...]:
        window_seconds = self.policy.stuffing_window_minutes * 60
        failures = [
            e
            for e in snapshot.login_events
            if not e.succeeded
            and 0 <= (snapshot.as_of - e.occurred_at).total_seconds() <= window_seconds
        ]
        return tuple(sorted(failures, key=lambda e: e.occurred_at))

    # ------------------------------------------------------------------ #
    # 2. Scoring and banding
    # ------------------------------------------------------------------ #
    def score(self, signals: Sequence[FusedSignal]) -> tuple[float, RiskBand]:
        """``base + sum(uplifts)``, clamped, then mapped to a band by policy cut-offs."""
        raw = self.policy.base_score + sum(s.uplift for s in signals)
        total = round(max(0.0, min(self.policy.max_score, raw)), 4)
        return total, self._band(total)

    def _band(self, score: float) -> RiskBand:
        if score >= self.policy.critical_score:
            return RiskBand.CRITICAL
        if score >= self.policy.high_score:
            return RiskBand.HIGH
        if score >= self.policy.medium_score:
            return RiskBand.MEDIUM
        return RiskBand.LOW

    def _severity(self, band: RiskBand, signals: Sequence[FusedSignal]) -> Severity:
        """The worst signal severity, or the band's own severity when nothing fired."""
        if not signals:
            return _BAND_SEVERITY[band]
        return min((s.severity for s in signals), key=lambda s: _SEVERITY_RANK.get(s, 9))

    # ------------------------------------------------------------------ #
    # 3. Containment (recommendations only; never executed here)
    # ------------------------------------------------------------------ #
    def recommend(
        self, band: RiskBand, signals: Sequence[FusedSignal]
    ) -> tuple[ContainmentRecommendation, ...]:
        """Map a band to a deterministic containment set. Nothing above MONITOR auto-executes."""
        citations = tuple(s.citation for s in signals if s.citation is not None)[:8]
        out: list[ContainmentRecommendation] = []
        for action in _CONTAINMENT_LADDER[band]:
            consequential = action is not ContainmentAction.MONITOR
            out.append(
                ContainmentRecommendation(
                    action=action,
                    severity=_BAND_SEVERITY[band],
                    rationale=_containment_rationale(action, band),
                    requires_human_review=consequential,
                    citations=citations,
                )
            )
        return tuple(out)

    # ------------------------------------------------------------------ #
    # 4. The whole assessment
    # ------------------------------------------------------------------ #
    def assess(self, *, snapshot: SessionSnapshot, baseline: AccountBaseline) -> FusionAssessment:
        """Detect, score, band and recommend in one replayable step (no I/O, no clock)."""
        signals = self.detect(snapshot=snapshot, baseline=baseline)
        score, band = self.score(signals)
        containments = self.recommend(band, signals)
        return FusionAssessment(
            subject_id=snapshot.subject_id,
            session_id=snapshot.session_id,
            tenant=snapshot.tenant,
            score=score,
            baseline_score=round(self.policy.base_score, 4),
            band=band,
            severity=self._severity(band, signals),
            signals=signals,
            containments=containments,
            as_of=snapshot.as_of.isoformat(),
        )


def _snapshot_citation(snapshot: SessionSnapshot) -> Citation:
    """The session's own citation, or a synthesised one naming the session and device."""
    if snapshot.citations:
        return snapshot.citations[0]
    return Citation(
        source_id=f"session:{snapshot.session_id}",
        title="Session under investigation",
        snippet=f"device {snapshot.device_id} from {snapshot.country}",
    )


def _containment_rationale(action: ContainmentAction, band: RiskBand) -> str:
    if action is ContainmentAction.MONITOR:
        return f"{band.value.upper()} risk: no containment recommended; continue monitoring"
    reason = {
        ContainmentAction.SUSPEND_CREDENTIALS: "revoke sessions and force a credential reset",
        ContainmentAction.LOCK_SESSION: "terminate the active session pending review",
        ContainmentAction.STEP_UP_AUTH: "require a stronger authentication factor",
    }[action]
    return f"{band.value.upper()} risk: recommend to {reason} (human approval required to enact)"
