"""Bank-owned fusion policy: the numbers the deterministic engine reads, lifted out of code.

These are the adopter's numbers, not the engine's. They live in a frozen dataclass populated
from the ``policy:`` block of ``config/settings.yaml`` (see ``config.Settings.load``), so a bank
tunes its own thresholds and per-signal weights without a code edit and an auditor reads the
policy in one place. The engine takes a :class:`FusionPolicy` and contains no literal of its own.

Pure standard library: no ports, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    """Every threshold and weight the fusion engine reads. Defaults are illustrative, not advice."""

    #: The starting score before any signal uplift is added.
    base_score: float = 0.0
    #: Per-signal uplift added to the score when the signal fires (bank-owned weights).
    device_change_uplift: float = 0.35
    impossible_travel_uplift: float = 0.50
    credential_stuffing_uplift: float = 0.30
    biometric_deviation_uplift: float = 0.25
    #: The score is clamped to ``[0, max_score]``.
    max_score: float = 1.0
    #: An implied travel speed above this (km/h) between two logins is physically impossible.
    impossible_speed_kmh: float = 900.0
    #: Two logins closer than this (km) are treated as the same place (GPS jitter), not travel.
    min_travel_km: float = 50.0
    #: Failed logins within this window (minutes) count toward the credential-stuffing signal.
    stuffing_window_minutes: int = 15
    #: This many failed logins in the window fires the credential-stuffing signal.
    stuffing_failure_threshold: int = 5
    #: A behavioural-biometric deviation at or above this (0..1) fires the biometric signal.
    biometric_threshold: float = 0.60
    #: Fused-score cut-offs for the band. Ordered high to low; a score at or above each wins.
    critical_score: float = 0.80
    high_score: float = 0.50
    medium_score: float = 0.25

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> FusionPolicy:
        """Build a policy from the settings ``policy:`` block, ignoring unknown keys.

        A missing block yields the defaults above. Only declared fields are read, so a stray key
        in the file is a no-op here rather than a constructor error, and a typo in a key name
        leaves the default in force (the loader validates the block's presence, not its spelling).
        """
        if not data:
            return cls()
        fields = {f for f in cls.__dataclass_fields__}
        kwargs = {str(k): v for k, v in data.items() if str(k) in fields}
        return cls(**kwargs)
