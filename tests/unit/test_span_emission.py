"""The investigation path opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit store.
So the value of tracing the investigation path depends entirely on the span carrying structural
attributes only: which action, whose, which tenant, how long. A subject id, a session id or the
narrated summary reaching a span has left the boundary the service's redact calls exist to hold,
and it has left it silently.

The content case drives a request whose subject id embeds a planted NRIC, so the check runs
against input that would actually leak if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from account_takeover_investigator.config import Settings, build_container
from account_takeover_investigator.domain.fusion_engine import FusionEngine
from account_takeover_investigator.domain.investigation_service import InvestigationService
from account_takeover_investigator.domain.models import Investigation, InvestigationRequest

from tests.fixtures import sample_cases

#: Every attribute key the investigate span is allowed to carry. A verdict that started
#: explaining itself on the span (a band, a subject, a narrative fragment) would widen this
#: set, which is the point of asserting on the set rather than on the individual keys.
_INVESTIGATE_KEYS = {"action", "actor", "tenant"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _investigate(request: InvestigationRequest) -> tuple[_RecordingTracer, Investigation]:
    """The REAL local adapters for every port except the tracer under inspection."""
    container = build_container(
        Settings(profile="local", audit_path=":memory:", tenant="demo-bank")
    )
    tracer = _RecordingTracer()
    service = InvestigationService(
        container.sessions,
        container.feature_store,
        container.narrator,
        container.audit,
        tracer=tracer,
        engine=FusionEngine.from_policy(container.settings.policy),
    )
    result = service.investigate(request, actor=sample_cases.ACTOR)
    return tracer, result


def _emitted(tracer: _RecordingTracer) -> str:
    """Every span name, attribute KEY and attribute VALUE, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_investigating_one_session_opens_exactly_one_named_span() -> None:
    tracer, _ = _investigate(sample_cases.ROUTINE_REQUEST)
    assert [name for name, _ in tracer.spans] == ["ato.investigate"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose investigation is slow, in which tenant", and nothing more."""
    tracer, _ = _investigate(sample_cases.ROUTINE_REQUEST)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "investigate"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["tenant"] == sample_cases.TENANT


@pytest.mark.parametrize(
    "request_",
    [sample_cases.ROUTINE_REQUEST, sample_cases.ESCALATING_REQUEST],
    ids=["routine", "takeover"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(
    request_: InvestigationRequest,
) -> None:
    """A takeover must not start attaching its signals to the span to explain itself."""
    tracer, _ = _investigate(request_)
    for _, attributes in tracer.spans:
        assert set(attributes) == _INVESTIGATE_KEYS


def test_no_span_attribute_carries_subject_content_or_the_planted_identifier() -> None:
    """The request used here embeds an NRIC in its subject id, so a leak would show."""
    request = InvestigationRequest(
        subject_id=sample_cases.PII_SUBJECT_ID,
        session_id=sample_cases.SESSION_ID,
        tenant=sample_cases.TENANT,
    )
    tracer, result = _investigate(request)
    emitted = _emitted(tracer)

    forbidden: list[str] = [
        sample_cases.PLANTED_NRIC,
        sample_cases.PII_SUBJECT_ID,
        sample_cases.SESSION_ID,
        # The narrated summary is the other content-shaped value in reach of this call site.
        result.narrative,
        result.summary,
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal not in emitted, f"a span attribute carried {literal!r}"
        assert literal.lower() not in emitted.lower(), f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _investigate(sample_cases.ESCALATING_REQUEST)
    values: list[Any] = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
