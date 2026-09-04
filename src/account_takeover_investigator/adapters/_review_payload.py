"""Shared conversion from an escalated result to an ``review-kit`` Review payload.

Lives in the adapter layer, not the pure domain, because it depends on the kit. The subject, summary
and every citation snippet are redacted BEFORE they leave the process (the same
redact-before-anything rule the audit write obeys), using the shared ``pii-kit``, so no raw
identifier reaches human-review-console over the wire; human-review-console redacts again before its
own audit write (defence in depth). ``maker`` and ``tenant`` are asserted here and trusted by
human-review-console because the caller is an authenticated S2S service; per-hop on-behalf-of token
exchange is the deferred next layer.
"""

from __future__ import annotations

import re

from pii_kit import NATIONAL_ID_PATTERNS, UNIVERSAL_PATTERNS, national_patterns_for
from pii_kit import redact as pii_redact
from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.kernel import Severity
from ..domain.models import Investigation

#: The repository name prefixes every source_key: it is the dedup key the
#: human-review-console stores, so it names the producer.
_REPOSITORY = "account-takeover-investigator"

#: Cap the citations carried on the wire: enough for a reviewer to trace the decision without
#: copying the whole evidence set into the console.
_MAX_CITATIONS = 8

#: The console is a SHARED sink: a case filed in one market may still quote another market's
#: national id, so the payload is scrubbed against every jurisdiction's rows plus the universal
#: email/phone rows, whatever this deployment's own ``domain.pii.JURISDICTIONS`` selects.
_ALL_PATTERNS = (
    *national_patterns_for(tuple(NATIONAL_ID_PATTERNS.keys())),
    *UNIVERSAL_PATTERNS,
)

#: Bands that demand dual control (two approvals) rather than a single checker.
_DUAL_CONTROL = (Severity.CRITICAL,)


def _redact(text: str) -> str:
    """Mask every jurisdiction's identifiers plus email/phone, and normalise whitespace."""
    return re.sub(r"\s+", " ", pii_redact(text, _ALL_PATTERNS)).strip()


def _kit_citations(result: Investigation) -> tuple[KitCitation, ...]:
    """Mask EVERY field, not only the snippet.

    A source_id is a locator, which is exactly why it was left alone, and it is also composed out
    of the identifiers the caller supplied: ``session:<session id>``, ``login:<subject id>:<event
    id>``. The dedupe key is the masked id, so two rows that differ only inside a masked span
    collapse to one rather than shipping the same evidence twice.
    """
    seen: set[str] = set()
    out: list[KitCitation] = []
    for citation in result.citations:
        source_id = _redact(citation.source_id)
        if source_id in seen:
            continue
        seen.add(source_id)
        out.append(
            KitCitation(
                source_id=source_id,
                title=_redact(citation.title),
                snippet=_redact(citation.snippet),
            )
        )
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def result_to_review(result: Investigation, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits to human-review-console when an
    investigation escalates.
    """
    return Review(
        action="account_takeover_investigator:investigate",
        subject=_redact(result.subject),
        maker=maker,
        tenant=tenant,
        summary=_redact(result.summary),
        severity=result.severity.value,
        required_approvals=2 if result.severity in _DUAL_CONTROL else 1,
        sod_group="account_takeover_investigator-maker-checker",
        case_ref=_redact(result.subject),
        # Producer-owned, tenant-scoped key so a retried delivery is idempotent at the console.
        # Both halves are masked: masking is deterministic, so the key stays stable across a
        # retry, and an idempotency key is still a string that lands in another system's store.
        source_key=f"{_REPOSITORY}:{_redact(result.subject)}:{_redact(result.session_id)}",
        citations=_kit_citations(result),
    )
