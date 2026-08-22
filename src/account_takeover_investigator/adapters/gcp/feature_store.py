"""GCP FeatureStorePort: account baseline from the Vertex AI Feature Store (lazy SDK import).

The managed import lives inside the method so the offline profiles import this module with no GCP
SDK present. The adapter returns a raw, cited baseline and computes no verdict.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AccountBaseline


class CloudFeatureStoreAdapter:
    """Read the account's known-good baseline from the Vertex AI Feature Store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, subject_id: str) -> AccountBaseline:  # pragma: no cover - needs live GCP
        # Lazy import: absent in the offline profile and in CI (hence import-not-found ignore).
        from google.cloud import aiplatform

        aiplatform.init(location=self._settings.region)
        raise NotImplementedError(
            "the managed feature-store lookup is deployment-specific: bind the online feature "
            "store and entity type in infra/terraform and implement the feature mapping"
        )
