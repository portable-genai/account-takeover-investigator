"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.models import Investigation


class InvestigateRequest(BaseModel):
    """What the caller asks ABOUT. Never who the caller is.

    There is deliberately no ``tenant`` (and no ``actor``): both come from the verified principal
    the identity adapter resolved. The field used to exist and the route preferred it, so any
    non-empty string a caller wrote displaced the identity that had actually been verified. It is
    REMOVED rather than ignored, because a published schema is a claim about what the service
    accepts, and a service that still advertises the field is still inviting the assertion.
    """

    subject_id: str
    session_id: str


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class SignalModel(BaseModel):
    kind: str
    severity: str
    summary: str
    uplift: float


class ContainmentModel(BaseModel):
    action: str
    severity: str
    rationale: str
    requires_human_review: bool


class InvestigateResponse(BaseModel):
    subject: str
    session_id: str
    severity: str
    decision: str
    band: str
    score: float
    baseline_score: float
    summary: str
    narrative: str
    requires_human_review: bool
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the result did not escalate, so a caller can tell a routed escalation from
    #: a flag that stopped here.
    review_ref: str = ""
    signals: list[SignalModel] = []
    containments: list[ContainmentModel] = []
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, result: Investigation, *, review_ref: str = "") -> InvestigateResponse:
        return cls(
            subject=result.subject,
            session_id=result.session_id,
            severity=result.severity.value,
            decision=result.decision.value,
            band=result.band.value,
            score=result.score,
            baseline_score=result.baseline_score,
            summary=result.summary,
            narrative=result.narrative,
            requires_human_review=result.requires_human_review,
            review_ref=review_ref,
            signals=[
                SignalModel(
                    kind=s.kind.value,
                    severity=s.severity.value,
                    summary=s.summary,
                    uplift=s.uplift,
                )
                for s in result.signals
            ],
            containments=[
                ContainmentModel(
                    action=c.action.value,
                    severity=c.severity.value,
                    rationale=c.rationale,
                    requires_human_review=c.requires_human_review,
                )
                for c in result.containments
            ],
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
