"""SessionSignalPort: the boundary that returns raw, cited session and device observations.

The port returns what was OBSERVED (the current session, its device and geo, and the recent
login history), each row carrying a citation. It never computes a verdict: fusing those
observations into a risk score is the deterministic engine's job, not the adapter's. Keeping the
adapter free of judgement is what lets the offline family replay byte-identical fixtures and the
managed family stream from the warehouse without the two disagreeing about the answer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import SessionSnapshot


@runtime_checkable
class SessionSignalPort(Protocol):
    def fetch(self, subject_id: str, session_id: str) -> SessionSnapshot:
        """Return the raw, cited snapshot for one session under investigation.

        The snapshot carries the current device, geo and behavioural-biometric deviation plus the
        recent login history. It computes nothing; the engine derives every signal from it.
        """
        ...
