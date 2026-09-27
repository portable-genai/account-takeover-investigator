"""Domain exceptions for Account Takeover Investigator.

Pure-Python exception hierarchy raised by the domain services. The domain layer never imports a
cloud SDK or a web framework; these errors let callers (the API, the CLI, the agent tool) react
to domain-level failures without coupling to any vendor SDK error type.
"""

from __future__ import annotations


class InvestigationError(Exception):
    """Base class for all domain-level errors this service raises."""


class GuardrailBlockedError(InvestigationError):
    """Raised when the guardrail refuses a caller-supplied key (rule R1).

    A refused key must never yield a partial or substitute investigation: the domain service
    audits the attempt as ``Decision.BLOCKED`` and then raises this. A refused NARRATION does not
    raise, because narration is optional by design: it is audited the same way and withheld.
    """
