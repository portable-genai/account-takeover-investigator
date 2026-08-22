"""On-prem FeatureStorePort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

The account baseline lives in the client's own feature platform, so this binding refuses at call
time rather than inventing a baseline. A fabricated baseline would silently define "normal".
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AccountBaseline


class OnPremFeatureStoreAdapter:
    """Satisfies FeatureStorePort but refuses: the client binds their own feature platform."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, subject_id: str) -> AccountBaseline:
        raise NotImplementedError(
            "on-prem feature lookup is a portability placeholder: bind the client's own feature "
            "store (see docs/onprem-migration.md)"
        )
