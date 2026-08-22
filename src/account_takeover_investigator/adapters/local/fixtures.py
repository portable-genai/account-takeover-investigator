"""Deterministic, obviously-fictional session fixtures for the offline profile.

One dataset feeds both the sessions and the feature-store adapters, so the snapshot and the
baseline a run sees are consistent. Every value is synthetic: RFC 5737 / RFC 3849 literals,
``.example`` context, invented device ids, and a fixed ``as_of`` so a replay is byte-identical.
The scenarios are chosen to exercise each branch of the fusion engine (a quiet account, a
full takeover, a credential-stuffing burst, and one carrying a planted identifier to prove
redaction). An unknown subject falls back to the quiet baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ...domain.kernel import Citation
from ...domain.models import AccountBaseline, LoginEvent, SessionSnapshot

#: The single reference instant every fixture is stamped at, so replays diff exactly.
AS_OF = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)

#: The account's home city and the devices on file (shared baseline for every fixture subject).
_HOME_COUNTRY = "SG"
_HOME_LAT, _HOME_LON = 1.29, 103.85
_KNOWN_DEVICES: tuple[str, ...] = ("dev-sg-01", "dev-sg-02")

#: A remote origin used by the takeover scenarios (a different hemisphere from home).
_REMOTE_COUNTRY = "US"
_REMOTE_LAT, _REMOTE_LON = 37.77, -122.42

_TENANT = "demo-bank"


@dataclass(frozen=True, slots=True)
class _Scenario:
    device_id: str
    country: str
    latitude: float
    longitude: float
    biometric: float
    prior_from_home: bool
    failures: int


#: subject id -> scenario. The keys are the subjects the eval golden set and the demo reference.
_SCENARIOS: dict[str, _Scenario] = {
    "acct-quiet": _Scenario("dev-sg-01", _HOME_COUNTRY, _HOME_LAT, _HOME_LON, 0.10, False, 0),
    "acct-takeover": _Scenario(
        "dev-xx-99", _REMOTE_COUNTRY, _REMOTE_LAT, _REMOTE_LON, 0.82, True, 0
    ),
    "acct-stuffing": _Scenario("dev-sg-01", _HOME_COUNTRY, _HOME_LAT, _HOME_LON, 0.20, False, 6),
    "acct-biometric": _Scenario("dev-sg-02", _HOME_COUNTRY, _HOME_LAT, _HOME_LON, 0.71, False, 0),
}

#: The quiet scenario is the fallback for any subject the dataset does not name.
_DEFAULT = _SCENARIOS["acct-quiet"]


def _login_citation(subject_id: str, event_id: str) -> Citation:
    return Citation(
        source_id=f"login:{subject_id}:{event_id}",
        title="Login event",
        snippet=f"event {event_id}",
    )


def _scenario(subject_id: str) -> _Scenario:
    """Exact match, else the longest scenario key that prefixes the id (so a demo subject that
    appends a planted identifier still maps to its scenario), else the quiet default."""
    if subject_id in _SCENARIOS:
        return _SCENARIOS[subject_id]
    for key in sorted(_SCENARIOS, key=len, reverse=True):
        if subject_id.startswith(key + "-"):
            return _SCENARIOS[key]
    return _DEFAULT


def snapshot_for(subject_id: str, session_id: str) -> SessionSnapshot:
    """Build the raw, cited snapshot for one session (deterministic, replayable)."""
    scenario = _scenario(subject_id)
    events: list[LoginEvent] = []
    if scenario.prior_from_home:
        events.append(
            LoginEvent(
                event_id="prior-1",
                occurred_at=AS_OF - timedelta(minutes=60),
                device_id="dev-sg-01",
                ip="192.0.2.10",
                country=_HOME_COUNTRY,
                latitude=_HOME_LAT,
                longitude=_HOME_LON,
                succeeded=True,
                citation=_login_citation(subject_id, "prior-1"),
            )
        )
    for i in range(scenario.failures):
        events.append(
            LoginEvent(
                event_id=f"fail-{i + 1}",
                occurred_at=AS_OF - timedelta(minutes=10 - i),
                device_id=scenario.device_id,
                ip="198.51.100.23",
                country=scenario.country,
                latitude=scenario.latitude,
                longitude=scenario.longitude,
                succeeded=False,
                citation=_login_citation(subject_id, f"fail-{i + 1}"),
            )
        )
    citation = Citation(
        source_id=f"session:{session_id}",
        title="Session snapshot",
        snippet=f"device {scenario.device_id} from {scenario.country}",
    )
    return SessionSnapshot(
        subject_id=subject_id,
        session_id=session_id,
        tenant=_TENANT,
        as_of=AS_OF,
        device_id=scenario.device_id,
        country=scenario.country,
        latitude=scenario.latitude,
        longitude=scenario.longitude,
        biometric_deviation=scenario.biometric,
        login_events=tuple(events),
        citations=(citation,),
    )


def baseline_for(subject_id: str) -> AccountBaseline:
    """Build the raw, cited known-good baseline for one account (deterministic)."""
    return AccountBaseline(
        subject_id=subject_id,
        tenant=_TENANT,
        known_device_ids=_KNOWN_DEVICES,
        home_country=_HOME_COUNTRY,
        home_latitude=_HOME_LAT,
        home_longitude=_HOME_LON,
        citations=(
            Citation(
                source_id=f"baseline:{subject_id}",
                title="Account baseline",
                snippet=f"home {_HOME_COUNTRY}, {len(_KNOWN_DEVICES)} device(s) on file",
            ),
        ),
    )
