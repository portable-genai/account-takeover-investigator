"""NarratorPort: the boundary the LLM sits behind, given only engine facts to restate.

The narrator turns a :class:`~account_takeover_investigator.domain.narrative.NarrativeBrief` (the
engine's findings, with the subject already PII-redacted) into prose. It produces no number and
no verdict: the service checks its output for groundedness against the engine assessment and
discards it for the deterministic draft on failure. The offline adapter is grounded by
construction; the managed adapter calls a model with a lazy SDK import.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.narrative import NarrativeBrief


@runtime_checkable
class NarratorPort(Protocol):
    def narrate(self, brief: NarrativeBrief, prompt: str) -> str:
        """Return a prose investigation summary restating ONLY the brief's engine facts.

        ``prompt`` is :func:`~..domain.narrative.narration_prompt` of ``brief`` as the guardrail
        handed it back after the INPUT screen (rule R1). A model-backed adapter sends THIS
        string, never one it renders itself, so the text a model reads is the text screened.
        """
        ...
