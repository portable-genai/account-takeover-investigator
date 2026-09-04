# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is in G4, and how an off-cloud or sovereign exit would actually work. Cross-references:
[`../../ARCHITECTURE.md`](../../ARCHITECTURE.md), [`../onprem-migration.md`](../onprem-migration.md),
[`../runbook.md`](../runbook.md).

## What is the no-lock-in claim, concretely?

`src/account_takeover_investigator/domain/` is pure standard library. No Google Cloud SDK, no
FastAPI, no httpx, no pydantic. The whole consequential path lives there: the four detectors,
the scoring arithmetic, the band cut-offs and the containment ladder in `fusion_engine.py`,
the brief and groundedness oracle in `narrative.py`, the thresholds in `policy.py`, the
orchestration in `investigation_service.py`. Everything else sits behind a
`@runtime_checkable` `Protocol` in `ports/` and is bound from one settings file. This is not a
convention: `tests/unit/test_core_purity.py` walks the imports of every module in `domain/`
and fails the build on anything the core does not own, with a written exemption list, a
control case proving the scan can see a violation, and a check that every written exemption
still names a file that exists.

## What are the profiles?

One variable, `ATOINVEST_PROFILE`, selects the whole adapter family:

- **`local`** is a real, working, SDK-free offline stack: deterministic session and
  feature-store fixtures, seeded dev personas, a hash-chained SQLite WORM audit log from the
  commons, a review-kit outbox you can inspect, and a narrator that composes the summary from
  engine facts alone. This is the dev, test and CI default and the working proof that the
  domain runs entirely off-cloud.
- **`gcp`** is the managed stack (Cloud Logging WORM, IAP identity, Cloud Trace or an OTLP
  collector, BigQuery sessions, Vertex Feature Store, Gemini narration, the `human-review-console` over
  S2S, the `model-quality-gate` promotion gate). Every cloud import is LAZY, inside the method, so the other
  two profiles import the same modules with no SDK installed.
- **`onprem`** is the exit scaffold: fail-fast placeholders that satisfy the same Protocols and
  RAISE, naming the migration target. They raise on purpose. A review router that silently
  returned would convert every consequential result into an unreviewed one, which is worse
  than a missing feature.

Unset is a fourth state rather than a silent default: the offline adapters still bind, but the
seeded personas are refused, no service-to-service scheme is selected, every relaxation reads
`unconfigured`, and the exposure guard refuses every route to a non-loopback peer. An emptied
or misspelled value raises at import, before the process can serve anything.

## Is the portability claim tested, or just asserted?

Tested, and bounded. `make portability` runs `scripts/portability_demo.py`, which prints a
pass or fail for each of eight named checks and exits non-zero on any failure: `port map
complete`, `adapters construct and conform`, `offline family answers`, `exit family refuses`,
`rewrite detected`, `truncation detected when anchored`, `record leaves intact`, and `no cloud
SDK imported`. It also prints what it does NOT prove, because an unbounded claim is the one an
auditor disproves for you. Inside the offline gate,
`tests/contract/test_port_parity.py` asserts set equality of the port registration across all
five places a port must appear, in both directions, and
`tests/contract/test_behavioral_parity.py` drives one canonical call per port
(`tests/contract/canonical.py`) so the structural and behavioural suites cannot quietly assert
different things.

## Which ports would I have to implement to run this somewhere else?

Eight boundaries, all in `ports/`: `SessionSignalPort` (the session under investigation and
its recent login history), `FeatureStorePort` (the account baseline: devices on file, home
location), `NarratorPort` (prose, and nothing consequential), `AuditSinkPort`,
`ReviewRouterPort` (`human-review-console`), `IamActionsPort` (the enact seam the investigation path never
calls), the commons `IdentityPort`, and the two observability boundaries re-exported in
`ports/observability.py`. The first two are the ones that carry your real data; the rest are
platform plumbing. Nothing in `domain/` changes when you swap any of them, which is the whole
point of the split.

## How would a sovereign or on-premises exit actually go?

The `onprem` family is the scaffold, and each placeholder marks a seam where a client supplies
their own component: their session store, their feature store, their in-tenancy model, their
IdP, their audit store, their review console. Because the domain never changes, the exit is an
adapter exercise rather than a rewrite, and the offline profile already proves the domain runs
with no cloud at all. [`../onprem-migration.md`](../onprem-migration.md) is the migration
guide; [`../runbook.md`](../runbook.md) is the operational half.

## Can the data be exported in an open format?

Yes, and the round trip is one of the eight portability checks. The audit trail exports to
JSON Lines and imports back into a FOREIGN log instance, which then verifies its chain, so the
exit is a file copy rather than a migration project (`check_the_trail_leaves_this_codebase_intact`
in `scripts/portability_demo.py` is the executable form). Investigation results and the agent
card serialise through the commons `to_jsonable` walker into plain JSON: dataclasses, enums,
datetimes and nested containers, no proprietary envelope.

## Is the deployment itself portable, or is the Terraform a lock-in?

The Terraform describes a Google Cloud posture, so it is not portable, but it is also not
load-bearing for the application: `make gate` runs with no cloud SDK, no project and no
network, and the `local` profile is a complete product. What the Terraform does own is the
enforcement of choices you would have to re-make on another platform anyway: the residency
allowlist validated at plan time, CMEK, the locked WORM bucket, a dry-run-first VPC-SC
perimeter, and the opt-in serving edge. Note also `managed_readiness.py`, which lists the four
managed operations still bound to construction-only placeholders (`sessions`,
`feature_store`, `narrator`, `iam_actions`) and refuses API startup on a managed profile that
would select one, so "portable" here does not quietly mean "the cloud half was never
finished and nobody said so".

## What is honestly NOT portable, or not proven?

Tamper-evidence is scoped to what the local sink can prove: an in-place rewrite and, with an
anchor configured, a truncated tail. Production immutability is the managed WORM sink's job
(`agent-observability`, or the locked Cloud Logging bucket in `infra/terraform/logging_worm.tf`), not this
process's. The managed narration path is not a working model call today: see
[`../model-card.md`](../model-card.md). And the golden eval set measures THIS reference
fixture population, so a fork inherits a green gate that is measuring the wrong accounts until
it relabels the set (see [adoption-faq.md](adoption-faq.md)).
