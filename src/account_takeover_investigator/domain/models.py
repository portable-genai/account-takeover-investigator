"""Vertical artifact models: account-takeover intake, fused signals and the investigation.

The artifacts THIS vertical produces and consumes, as opposed to the vertical-neutral machinery
in ``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for no
reason but the length of its name.

Two families live here. The RAW intake types (``LoginEvent``, ``SessionSnapshot``,
``AccountBaseline``) are what the session and feature-store ports return: cited observations,
never a computed verdict. The DERIVED types (``FusedSignal``, ``ContainmentRecommendation``,
``FusionAssessment``, ``Investigation``) are what the deterministic engine and the service
produce. The LLM never produces any figure in either family; it only narrates the finished
assessment, and even that is checked for groundedness against these fields.

A fork building a different vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class SignalKind(LenientStrEnum):
    """The four takeover signals the fusion engine detects. A member IS its wire value."""

    DEVICE_CHANGE = "device_change"
    IMPOSSIBLE_TRAVEL = "impossible_travel"
    CREDENTIAL_STUFFING = "credential_stuffing"
    BIOMETRIC_DEVIATION = "biometric_deviation"


class RiskBand(LenientStrEnum):
    """The fused-score band the engine assigns (policy-owned cut-offs)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContainmentAction(LenientStrEnum):
    """A containment the engine may RECOMMEND. It is never executed here (see ports/iam_actions)."""

    MONITOR = "monitor"
    STEP_UP_AUTH = "step_up_auth"
    LOCK_SESSION = "lock_session"
    SUSPEND_CREDENTIALS = "suspend_credentials"


@dataclass(frozen=True, slots=True)
class LoginEvent:
    """One raw login observation the sessions port returns. It computes nothing; it is cited."""

    event_id: str
    occurred_at: datetime
    device_id: str
    ip: str
    country: str
    latitude: float
    longitude: float
    succeeded: bool
    citation: Citation


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """The current session under investigation plus its recent login history (raw, cited).

    ``biometric_deviation`` is a measured 0..1 distance of this session's behavioural biometrics
    from the account's own baseline, supplied by the upstream feature pipeline; the engine
    thresholds it but never recomputes it.
    """

    subject_id: str
    session_id: str
    tenant: str
    as_of: datetime
    device_id: str
    country: str
    latitude: float
    longitude: float
    biometric_deviation: float
    login_events: tuple[LoginEvent, ...] = ()
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountBaseline:
    """The account's known-good profile from the feature store (raw, cited)."""

    subject_id: str
    tenant: str
    known_device_ids: tuple[str, ...]
    home_country: str
    home_latitude: float
    home_longitude: float
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class FusedSignal:
    """One detected takeover signal with its OWN auditable uplift line and citation.

    ``key`` is a stable content fingerprint (``signal_key``), so the same real-world anomaly
    yields the same key on every run and a replay diffs exactly rather than fuzzily.
    """

    key: str
    kind: SignalKind
    severity: Severity
    summary: str
    detail: str
    uplift: float
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class ContainmentRecommendation:
    """A recommended containment. NEVER executed by this service: it is routed for approval.

    Anything stronger than ``MONITOR`` is consequential, so it sets ``requires_human_review`` and
    the investigation carrying it escalates to Hrz7 (rule R8). The engine recommends; a human,
    through the review console, decides; only then would an IAM action run.
    """

    action: ContainmentAction
    severity: Severity
    rationale: str
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class InvestigationRequest:
    """One account-takeover investigation to run: a subject and the session in question."""

    subject_id: str
    session_id: str
    tenant: str = ""


@dataclass(frozen=True, slots=True)
class FusionAssessment:
    """The engine's replayable output: the score, band, cited signals and containment set.

    Pure arithmetic over the raw intake and bank-owned policy. Given the same snapshot, baseline
    and policy it is byte-identical, so an auditor can recompute it.
    """

    subject_id: str
    session_id: str
    tenant: str
    score: float
    baseline_score: float
    band: RiskBand
    severity: Severity
    signals: tuple[FusedSignal, ...]
    containments: tuple[ContainmentRecommendation, ...]
    as_of: str

    @property
    def requires_human_review(self) -> bool:
        """True when any recommended containment is consequential (rule R8 then routes it)."""
        return any(c.requires_human_review for c in self.containments)


@dataclass(frozen=True, slots=True)
class Investigation:
    """The investigation result: fused score, cited signals, containment set and narrative.

    ``subject`` carries the subject id under the name the shared review payload and demo helpers
    read. ``narrative`` is the LLM-drafted (or deterministic-fallback) summary, checked grounded
    against the engine findings before it is kept; ``summary`` is a one-line headline.
    """

    subject: str
    session_id: str
    tenant: str
    severity: Severity
    decision: Decision
    band: RiskBand
    score: float
    baseline_score: float
    summary: str
    narrative: str
    signals: tuple[FusedSignal, ...]
    containments: tuple[ContainmentRecommendation, ...]
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()
    as_of: str = ""
