"""Grounded narration helpers: the brief the narrator reads and the groundedness oracle.

The LLM's ONLY job in this vertical is to restate the engine's findings in prose. So the input
it is given (:class:`NarrativeBrief`) carries engine facts and nothing else, and the output it
returns is checked against the engine assessment before it is kept: :func:`is_grounded` fails any
narrative that states a figure the engine never produced. :func:`draft_narrative` is the
deterministic, grounded-by-construction summary the offline narrator returns and the service
falls back to when a model's draft fails the check, so a takeover investigation never depends on
a model to produce readable output.

Pure standard library; no ports, no I/O, no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import FusionAssessment

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class NarrativeBrief:
    """The engine facts a narrator may restate. Built by the service AFTER PII redaction.

    Nothing here is free-form customer text: ``subject`` arrives already masked, and every other
    field is a number or a label the engine produced. A narrator cannot leak what it never sees.
    """

    subject: str
    session_id: str
    band: str
    score: float
    signal_lines: tuple[str, ...]
    containment_lines: tuple[str, ...]


def brief_from_assessment(
    assessment: FusionAssessment, *, subject: str, session_id: str
) -> NarrativeBrief:
    """Assemble the brief from an engine assessment and already-redacted caller keys.

    Both labels are passed IN rather than read off the assessment, which carries the raw keys the
    engine was given. Reading ``assessment.session_id`` here is how a masked subject sat next to
    an unmasked session id in the same brief: the docstring above says nothing free-form reaches
    the narrator, and only the field somebody remembered to mask actually obeyed it.
    """
    return NarrativeBrief(
        subject=subject,
        session_id=session_id,
        band=assessment.band.value,
        score=assessment.score,
        signal_lines=tuple(
            f"{s.kind.value}: {s.summary} (+{s.uplift:.2f})" for s in assessment.signals
        ),
        containment_lines=tuple(
            f"{c.action.value}: {c.rationale}" for c in assessment.containments
        ),
    )


def draft_narrative(brief: NarrativeBrief) -> str:
    """The deterministic, grounded summary: the offline narrator and the discard-on-failure path.

    Composed only from the brief's engine facts, so :func:`is_grounded` always passes it. A
    managed narrator returns richer prose; this is what ships when there is no model, and what
    the service substitutes when a model's draft states a figure the engine did not.
    """
    lines = [
        f"Session {brief.session_id} for {brief.subject} scored {brief.score:.2f}, "
        f"banded {brief.band.upper()} for account-takeover risk."
    ]
    if brief.signal_lines:
        lines.append("Signals: " + "; ".join(brief.signal_lines) + ".")
    else:
        lines.append("No takeover signals fired; the score reflects the baseline only.")
    if brief.containment_lines:
        lines.append(
            "Recommended containment (pending human approval): "
            + "; ".join(brief.containment_lines)
            + "."
        )
    return " ".join(lines)


def engine_number_tokens(assessment: FusionAssessment) -> frozenset[str]:
    """Every numeric token the engine legitimately produced, for the groundedness check.

    Drawn from the score, each signal's summary, detail and uplift, and each containment
    rationale, plus the subject and session identifiers. A number outside this set in a narrative
    is a figure the model invented.
    """
    texts: list[str] = [
        f"{assessment.score:.2f}",
        assessment.subject_id,
        assessment.session_id,
    ]
    for signal in assessment.signals:
        texts.extend((signal.summary, signal.detail, f"{signal.uplift:.2f}"))
    for containment in assessment.containments:
        texts.append(containment.rationale)
    tokens: set[str] = set()
    for text in texts:
        tokens.update(_NUMBER.findall(text))
    return frozenset(tokens)


def is_grounded(narrative: str, assessment: FusionAssessment) -> bool:
    """True when every number in ``narrative`` is one the engine actually produced."""
    allowed = engine_number_tokens(assessment)
    return all(token in allowed for token in _NUMBER.findall(narrative))
