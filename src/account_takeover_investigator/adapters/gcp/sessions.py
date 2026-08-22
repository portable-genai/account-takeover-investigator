"""GCP SessionSignalPort: session and device rows from BigQuery (SDK imports stay lazy).

The ``google-cloud-bigquery`` import lives inside the method, so the ``local``/``onprem`` profiles
import this module with no GCP SDK installed (the portability proof). The adapter reads raw rows
and returns a cited snapshot; it computes no verdict.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SessionSnapshot


class CloudSessionAdapter:
    """Read raw session and device signals from the BigQuery warehouse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, subject_id: str, session_id: str) -> SessionSnapshot:  # pragma: no cover
        # Lazy import: absent in the offline profile and in CI (hence import-not-found ignore).
        from google.cloud import bigquery

        client = bigquery.Client(location=self._settings.region)
        raise NotImplementedError(
            "the managed BigQuery session query is deployment-specific: bind the warehouse "
            f"dataset for {client.project!r} in infra/terraform and implement the row mapping"
        )
