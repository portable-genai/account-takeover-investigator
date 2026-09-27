"""The account-takeover investigation orchestrator: deterministic fusion, then grounded narration.

The consequential outputs (the fused score, the band, the containment set) come from the pure
:class:`~account_takeover_investigator.domain.fusion_engine.FusionEngine`; the model only narrates,
and its narration is checked grounded and discarded on failure. PII is redacted BEFORE the narrator
sees it and BEFORE anything is written to the audit sink (R2/P-04), every result carries a citation,
and any consequential containment escalates: the service marks it ``requires_human_review`` and the
surfaces route it to human-review-console (rule R8). This service NEVER enacts a containment;
``ports/iam_actions.py`` is not one of its dependencies.

Rule R1: the guardrail screens the one generation call this service makes, the narrator
restating the engine brief, in both directions. INPUT, before anything is fetched or scored:
each caller-supplied key on its own (the subject and the session id, already masked, because
each reaches the brief, the headline, the citation and the audit record by itself); then the
PROMPT the narrator receives (:func:`~.narrative.narration_prompt`), which joins those keys with
the engine's lines, so an injection split across the fields or carried in an intake-sourced
signal line is screened as the model would read it. OUTPUT: whichever narrative survives the
groundedness fallback, before it is audited or returned. The text each screen hands back is the
text used from then on, exactly as given.

A refused caller key is audited ``Decision.BLOCKED`` and raises
:class:`~.errors.GuardrailBlockedError`: no investigation is built on a key the screen refused.
Narration is optional by design here (the engine's figures stand without prose), so a refused
prompt or narrative is audited ``Decision.BLOCKED`` and replaced by the fixed
:data:`~.narrative.NARRATION_WITHHELD` text, which quotes nothing refused; the investigation is
then audited as usual. A guardrail that cannot decide (its backend errored or timed out) fails
CLOSED at any step: the refusal is audited BLOCKED when the audit sink can take it, and the
guardrail's own error then reaches the caller.
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.feature_store import FeatureStorePort
from ..ports.guardrail import GuardrailPort
from ..ports.narrator import NarratorPort
from ..ports.observability import ObservabilityTracerPort
from ..ports.sessions import SessionSignalPort
from .errors import GuardrailBlockedError
from .fusion_engine import FusionEngine
from .kernel import (
    AuditEvent,
    Citation,
    Decision,
    Direction,
    GuardrailVerdict,
    Severity,
    utcnow,
)
from .models import FusionAssessment, Investigation, InvestigationRequest
from .narrative import (
    NARRATION_WITHHELD,
    NarrativeBrief,
    brief_from_assessment,
    draft_narrative,
    is_grounded,
    narration_prompt,
)
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
        guardrail: GuardrailPort,
        tracer: ObservabilityTracerPort,
        engine: FusionEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._features = feature_store
        self._narrator = narrator
        self._audit = audit
        self._guardrail = guardrail
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
            return self._investigate(request, actor=actor)

    def _investigate(self, request: InvestigationRequest, *, actor: str) -> Investigation:
        # Redact BOTH caller-supplied keys HERE, where they cross out of the intake edge, so
        # every sink downstream is covered once instead of three times. The session id reaches
        # the narrator's brief, the citation LOCATOR the WORM record stores and the payload the
        # review console renders, exactly as the subject does. Neither key is a locator this
        # service controls: they arrive as free text, and an intake that puts a national id in
        # the account key and the reporting mailbox in the case key is ordinary rather than
        # adversarial (P-04).
        #
        # 1) Guardrail screen (INPUT) of each key, masked, before anything is fetched or scored
        # (rule R1). The masked form is what reaches the model, and it keeps the raw identifier
        # out of the guardrail's own request. A refusal here records NO severity, because
        # nothing has been scored, and no subject, because the subject may be what was refused.
        subject = self._screen_key(redact(request.subject_id, PII_PATTERNS), actor=actor)
        session = self._screen_key(
            redact(request.session_id, PII_PATTERNS), actor=actor, subject=subject
        )

        # The raw keys address the intake ports: a lookup is not a generation call, and a
        # masked key would find nothing.
        snapshot = self._sessions.fetch(request.subject_id, request.session_id)
        baseline = self._features.fetch(request.subject_id)
        assessment = self._engine.assess(snapshot=snapshot, baseline=baseline)

        brief = brief_from_assessment(assessment, subject=subject, session_id=session)
        narrative = self._narrate(brief, assessment, actor=actor, subject=subject)

        decision = Decision.ESCALATED if assessment.requires_human_review else Decision.ALLOWED
        headline = (
            f"{subject}: {assessment.band.value.upper()} account-takeover risk "
            f"({assessment.score:.2f})"
        )
        citations = self._citations(session, subject, assessment)

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

    def _narrate(
        self,
        brief: NarrativeBrief,
        assessment: FusionAssessment,
        *,
        actor: str,
        subject: str,
    ) -> str:
        """The generation step, screened in both directions; the fixed text on a refusal.

        2) INPUT: the prompt the narrator receives, screened as sent, and the screened text is
        what the narrator is handed. 3) The narration, discarded for the deterministic,
        grounded-by-construction draft when it states a figure the engine did not produce.
        4) OUTPUT: whichever narrative survived, before it is audited or returned. Narration
        never blocks the investigation: a refused direction is audited and withheld.
        """
        severity = assessment.severity
        prompt = self._screen_narration(
            narration_prompt(brief),
            Direction.INPUT,
            actor=actor,
            subject=subject,
            severity=severity,
        )
        if prompt is None:
            return NARRATION_WITHHELD
        narrative = self._narrator.narrate(brief, prompt)
        if not is_grounded(narrative, assessment):
            narrative = draft_narrative(brief)
        screened = self._screen_narration(
            narrative, Direction.OUTPUT, actor=actor, subject=subject, severity=severity
        )
        return NARRATION_WITHHELD if screened is None else screened

    def _screen_key(self, text: str, *, actor: str, subject: str | None = None) -> str:
        """Screen one caller key INPUT; return the text to use from here on, or refuse.

        A block raises :class:`GuardrailBlockedError` after an audited BLOCKED record: no
        investigation is built on a key the screen refused.
        """
        verdict = self._screen(text, Direction.INPUT, actor=actor, subject=subject, severity=None)
        if not verdict.allowed or verdict.sanitized_text is None:
            reason = verdict.reason or "investigation input blocked by guardrail"
            self._audit_blocked(actor, Direction.INPUT, reason, subject=subject, severity=None)
            raise GuardrailBlockedError(reason)
        return verdict.sanitized_text

    def _screen_narration(
        self,
        text: str,
        direction: Direction,
        *,
        actor: str,
        subject: str,
        severity: Severity,
    ) -> str | None:
        """Screen the narration prompt or narrative; ``None`` when refused (already audited)."""
        verdict = self._screen(text, direction, actor=actor, subject=subject, severity=severity)
        if not verdict.allowed or verdict.sanitized_text is None:
            reason = verdict.reason or f"narration {direction.value} blocked by guardrail"
            self._audit_blocked(actor, direction, reason, subject=subject, severity=severity)
            return None
        return verdict.sanitized_text

    def _screen(
        self,
        text: str,
        direction: Direction,
        *,
        actor: str,
        subject: str | None,
        severity: Severity | None,
    ) -> GuardrailVerdict:
        """One guardrail call. A guardrail that raised instead of deciding fails CLOSED.

        The refusal is audited BLOCKED first when the sink can take it, and the guardrail's
        own error then propagates, carrying a note when the record could not be written.
        """
        try:
            return self._guardrail.screen(text, direction)
        except Exception as exc:
            reason = f"guardrail unavailable ({type(exc).__name__})"
            try:
                self._audit_blocked(actor, direction, reason, subject=subject, severity=severity)
            except Exception as audit_exc:
                exc.add_note(f"the BLOCKED audit record could not be written: {audit_exc!r}")
            raise

    def _audit_blocked(
        self,
        actor: str,
        direction: Direction,
        reason: str,
        *,
        subject: str | None,
        severity: Severity | None,
    ) -> None:
        """Audit a guardrail refusal (rule R1/R2), never carrying the refused text.

        Only that a refusal happened, in which direction, and why, plus the subject once it has
        itself passed the INPUT screen and the severity once the engine has scored it. A refused
        attempt is a security-relevant event the WORM trail must hold whether or not the
        request goes on to produce an investigation.
        """
        what = f"{subject}: blocked" if subject is not None else "blocked"
        self._audit.record(
            AuditEvent(
                action="investigate",
                actor=actor,
                decision=Decision.BLOCKED,
                severity=severity,
                redacted_summary=redact(f"{what} ({direction.value}): {reason}", PII_PATTERNS),
                citations=(),
                timestamp=utcnow(),
            )
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
