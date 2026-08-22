#!/usr/bin/env python3
"""Evaluation gate for Account Takeover Investigator (G4).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``InvestigationService`` against a golden set with SDK-free local adapters and scores four
  metrics against the DATASET'S OWN expected outcome, never the pipeline's own verdict.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp`` profile),
  via ``agent_eval_kit.PromotionGateClient``.

Every metric is proven able to go red in ``tests/unit/test_eval_metrics_can_go_red.py``. Exit is
``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from account_takeover_investigator.config import Settings, build_container
from account_takeover_investigator.domain.fusion_engine import FusionEngine
from account_takeover_investigator.domain.investigation_service import InvestigationService
from account_takeover_investigator.domain.models import InvestigationRequest
from account_takeover_investigator.domain.narrative import is_grounded
from account_takeover_investigator.domain.pii import PII_PATTERNS

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "fusion_accuracy": 0.80,
    "review_safety": 1.0,
    "groundedness": 0.99,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "account-takeover-investigator"


def _load(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def audit_surfaces(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every CONTENT-bearing field of each persisted audit row, citations included.

    ``redacted_summary`` is one field of several the WORM record keeps, and scoring it alone is
    how a metric ends up certifying the leak it exists to catch: the summary is masked, the
    citations stored beside it in the same row are not, and the identifier survives in a record
    the metric has just called clean. A citation's ``source_id`` is content here, not a bare
    locator, because an intake locator is built out of the caller's own identifiers.

    ``actor`` is deliberately absent. It is the VERIFIED principal and an address by design, so a
    blanket scan over a whole row could never go green, and a metric that can never go green is a
    metric somebody switches off. Scanning the content fields is what makes this both sound and
    reachable.
    """
    out: list[str] = []
    for row in rows:
        out.append(str(row.get("redacted_summary", "")))
        out.append(json.dumps(row.get("citations", []), sort_keys=True, default=str))
    return out


def pii_safety(surfaces: Sequence[str], planted: Sequence[str]) -> float:
    """1.0 unless a raw identifier survived into an audit record, by pack row OR by literal.

    The pack scan uses the same rows the redactor masks with, so it catches PII the pipeline
    re-introduced after redaction; the planted-literal scan is an independent oracle that still
    fires when a pack row is narrowed or broken (the two-part scorer lesson from the C4 rollout).
    Feed it :func:`audit_surfaces`, never the summary alone.
    """
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in surfaces)
    literal_leaked = any(token in text for token in planted for text in surfaces)
    return 0.0 if (pack_leaked or literal_leaked) else 1.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    container = build_container(
        Settings(profile="local", audit_path=":memory:", tenant="demo-bank")
    )
    engine = FusionEngine.from_policy(container.settings.policy)
    service = InvestigationService(
        container.sessions,
        container.feature_store,
        container.narrator,
        container.audit,
        tracer=container.tracer,
        engine=engine,
    )

    fusion: list[float] = []
    review: list[float] = []
    grounded: list[float] = []
    for case in cases:
        subject = str(case["subject_id"])
        session = str(case["session_id"])
        result = service.investigate(
            InvestigationRequest(subject_id=subject, session_id=session), actor="eval-bot"
        )
        # Scored against the DATASET's independent oracle, never against the pipeline's verdict.
        fusion.append(1.0 if result.band.value == case["expected_band"] else 0.0)
        review.append(1.0 if result.requires_human_review == case["expected_review"] else 0.0)
        # Groundedness: recompute the engine assessment from the same raw inputs, so the check
        # has an independent reference for what numbers the narrative may state.
        snapshot = container.sessions.fetch(subject, session)
        baseline = container.feature_store.fetch(subject)
        assessment = engine.assess(snapshot=snapshot, baseline=baseline)
        grounded.append(1.0 if is_grounded(result.narrative, assessment) else 0.0)

    # pii_safety: no raw identifier may survive into any audit record.
    surfaces = audit_surfaces(container.audit.log.read_all())
    planted = [str(case["planted"]) for case in cases if case.get("planted")]

    results = (
        EvalMetricResult.scored("fusion_accuracy", _mean(fusion), THRESHOLDS["fusion_accuracy"]),
        EvalMetricResult.scored("review_safety", _mean(review), THRESHOLDS["review_safety"]),
        EvalMetricResult.scored("groundedness", _mean(grounded), THRESHOLDS["groundedness"]),
        EvalMetricResult.scored(
            "pii_safety", pii_safety(surfaces, planted), THRESHOLDS["pii_safety"]
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"ATOINVEST_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("ATOINVEST_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for G4.",
        )
    )
