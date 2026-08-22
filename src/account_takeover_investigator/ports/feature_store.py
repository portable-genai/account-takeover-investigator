"""FeatureStorePort: the boundary that returns the account's known-good baseline, cited.

The baseline (the devices on file, the home geography) is what "normal" means for this account,
and the engine measures the current session against it. Like the sessions port, this one returns
raw cited facts and computes no verdict: a baseline is evidence, not a decision.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import AccountBaseline


@runtime_checkable
class FeatureStorePort(Protocol):
    def fetch(self, subject_id: str) -> AccountBaseline:
        """Return the raw, cited known-good baseline for one account (never a verdict)."""
        ...
