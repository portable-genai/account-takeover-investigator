"""Minimal stdlib CLI: investigate a session, or verify the audit chain (argparse, no deps)."""

from __future__ import annotations

import argparse
import sys

from hex_service_kit.logging import configure_logging

from ..adapters.controls import RecordingReviewRouter
from ..config import Container, build_container
from ..domain.errors import GuardrailBlockedError
from ..domain.fusion_engine import FusionEngine
from ..domain.investigation_service import InvestigationService
from ..domain.models import InvestigationRequest


def _service(container: Container) -> InvestigationService:
    return InvestigationService(
        container.sessions,
        container.feature_store,
        container.narrator,
        container.audit,
        guardrail=container.guardrail,
        tracer=container.tracer,
        engine=FusionEngine.from_policy(container.settings.policy),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="account_takeover_investigator")
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("investigate", help="Investigate one account session for takeover risk.")
    inv.add_argument("subject_id")
    inv.add_argument("session_id")
    inv.add_argument("--actor", default="cli-user@bank.example")
    inv.add_argument(
        "--tenant", default="", help="Tenant partition asserted to human-review-console."
    )

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="account-takeover-investigator")

    if args.command == "investigate":
        try:
            result = _service(container).investigate(
                InvestigationRequest(
                    subject_id=args.subject_id, session_id=args.session_id, tenant=args.tenant
                ),
                actor=args.actor,
            )
        except GuardrailBlockedError as exc:
            # Rule R1: already audited BLOCKED inside the service. Never a partial investigation.
            print(f"blocked by guardrail: {exc}", file=sys.stderr)
            return 1
        print(f"{result.subject} / {result.session_id}: {result.band.value} (score {result.score})")
        print(f"  signals: {', '.join(s.kind.value for s in result.signals) or 'none'}")
        print(f"  requires_human_review: {result.requires_human_review}")
        # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
        # only printed the flag would be a second place for an escalation to stop.
        routing = RecordingReviewRouter(container.review_router)
        ref = routing.route(result, maker=args.actor, tenant=args.tenant)
        print(f"  human review hand-off : {routing.outcome.value} {ref}".rstrip())
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
