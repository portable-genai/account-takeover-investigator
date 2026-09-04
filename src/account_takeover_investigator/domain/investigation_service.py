"""The account-takeover investigation orchestrator: deterministic fusion, then grounded narration.

The consequential outputs (the fused score, the band, the containment set) come from the pure
:class:`~account_takeover_investigator.domain.fusion_engine.FusionEngine`; the model only narrates,
and its narration is checked grounded and discarded on failure. PII is redacted BEFORE the narrator
sees it and BEFORE anything is written to the audit sink (R1/P-04), every result carries a citation,
and any consequential containment escalates: the service marks it ``requires_human_review`` and the
surfaces route it to human-review-console (rule R8). This service NEVER enacts a containment;
``ports/iam_actions.py`` is not one of its dependencies.
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.feature_store import FeatureStorePort
from ..ports.narrator import NarratorPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.sessions import SessionSignalPort
from .fusion_engine import FusionEngine
from .kernel import AuditEvent, Citation, Decision, utcnow
from .models import FusionAssessment, Investigation, InvestigationRequest
from .narrative import brief_from_assessment, draft_narrative, is_grounded
from .pii import PII_PATTERNS

#: One span per investigated session. Structural attributes only: see
#: :meth:`InvestigationService.investigate`.
_INVESTIGATE_SPAN = "ato.investigate"


def _redact_citation(citation: Citation) -> Citation:
    """Mask every field of a citation, since an intake identifier can embed the subject id."""
    return Citation(
        source_id=redact(citation.source_id, PII_PATTERNS),
        title=redact(citation.title, PII_PATTERNS),
        snippet=redact(citation.snippet, PII_PATTERNS),
    )


class InvestigationService:
    """Fetch cited signals, fuse them deterministically, narrate grounded, redact, then audit."""

    def __init__(
        self,
        sessions: SessionSignalPort,
        feature_store: FeatureStorePort,
        narrator: NarratorPort,
        audit: AuditSinkPort,
        *,
        tracer: ObservabilityTracerPort,
        engine: FusionEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._features = feature_store
        self._narrator = narrator
        self._audit = audit
        self._tracer = tracer
        self._engine = engine or FusionEngine()

    def investigate(self, request: InvestigationRequest, *, actor: str) -> Investigation:
        """Investigate one session end to end, inside one span.

        The span's attributes are STRUCTURAL only: the action, the actor and the tenant, never
        the subject id, the session id or the narrated summary. A trace backend is not the WORM
        audit trail: it has no redaction stage, a wider read audience and no retention rule
        written against a regulator's requirement, so anything content-shaped that reaches a
        span has left the boundary the redact calls exist to hold, and left it silently.
        """
        with self._tracer.span(
            _INVESTIGATE_SPAN,
            action="investigate",
            actor=actor,
            tenant=request.tenant,
        ):
            snapshot = self._sessions.fetch(request.subject_id, request.session_id)
            baseline = self._features.fetch(request.subject_id)
            assessment = self._engine.assess(snapshot=snapshot, baseline=baseline)

            # Redact BOTH caller-supplied keys HERE, where they cross out of the intake edge, so
            # every sink downstream is covered once instead of three times. The subject was
            # already masked; the session id was not, and it reaches the narrator's brief, the
            # citation LOCATOR the WORM record stores and the payload the review console renders.
            # Neither key is a locator this service controls: they arrive as free text, and an
            # intake that puts a national id in the account key and the reporting mailbox in the
            # case key is ordinary rather than adversarial (P-04).
            redacted_subject = redact(request.subject_id, PII_PATTERNS)
            redacted_session = redact(request.session_id, PII_PATTERNS)
            brief = brief_from_assessment(
                assessment, subject=redacted_subject, session_id=redacted_session
            )
            narrative = self._narrator.narrate(brief)
            # Discard on failure: a narration that states a figure the engine did not produce is
            # replaced by the deterministic, grounded-by-construction draft. Narration never
            # blocks.
            if not is_grounded(narrative, assessment):
                narrative = draft_narrative(brief)

            decision = Decision.ESCALATED if assessment.requires_human_review else Decision.ALLOWED
            headline = (
                f"{redacted_subject}: {assessment.band.value.upper()} account-takeover risk "
                f"({assessment.score:.2f})"
            )
            citations = self._citations(redacted_session, redacted_subject, assessment)

            # Redact BEFORE the audit write: no raw identifier reaches the immutable record.
            self._audit.record(
                AuditEvent(
                    action="investigate",
                    actor=actor,
                    decision=decision,
                    severity=assessment.severity,
                    redacted_summary=redact(f"{headline} :: {narrative}", PII_PATTERNS),
                    citations=citations,
                    timestamp=utcnow(),
                )
            )

            return Investigation(
                subject=request.subject_id,
                session_id=request.session_id,
                tenant=request.tenant or snapshot.tenant,
                severity=assessment.severity,
                decision=decision,
                band=assessment.band,
                score=assessment.score,
                baseline_score=assessment.baseline_score,
                summary=headline,
                narrative=narrative,
                signals=assessment.signals,
                containments=assessment.containments,
                requires_human_review=assessment.requires_human_review,
                citations=citations,
                as_of=assessment.as_of,
            )

    @staticmethod
    def _citations(
        redacted_session: str, redacted_subject: str, assessment: FusionAssessment
    ) -> tuple[Citation, ...]:
        """A base session citation plus each signal's, redacted and deduped (a LOW result is cited).

        Signal citations come straight from the intake ports, whose identifiers can embed the
        subject id (which may itself carry personal data), so every field is masked here before
        the citation reaches the audit record, the response or the review console. The base
        citation is built from the ALREADY-MASKED session key for the same reason: it is composed
        here rather than fetched, and a locator this method composes out of caller text is caller
        text.
        """
        base = Citation(
            source_id=f"session:{redacted_session}",
            title="Session under investigation",
            snippet=f"subject {redacted_subject}, band {assessment.band.value}",
        )
        out: list[Citation] = [base]
        seen = {base.source_id}
        for signal in assessment.signals:
            if signal.citation is None:
                continue
            citation = _redact_citation(signal.citation)
            if citation.source_id in seen:
                continue
            seen.add(citation.source_id)
            out.append(citation)
        return tuple(out[:8])
