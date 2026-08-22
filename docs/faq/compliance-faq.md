# Compliance FAQ

For compliance, model-risk and privacy teams assessing G4's regulatory posture.
Cross-references: [`../../COMPLIANCE.md`](../../COMPLIANCE.md) (the full P-01 to P-13 and
R1 to R8 mapping with an evidence file per row, plus the adopter-owned crosswalk),
[`../../SPEC.md`](../../SPEC.md) (the locked contracts), [`../model-card.md`](../model-card.md)
(the model boundary), [`../practices-audit.md`](../practices-audit.md) (the per-check verdict).

### Is this system making fraud decisions autonomously?

No. It is decision support with a hard stop. The deterministic engine produces a band and a
set of RECOMMENDED containment actions; everything above `MONITOR` sets
`requires_human_review` and is ROUTED to the Hrz7 human-review console in the same call that
produced it (rule R8), with CRITICAL demanding two approvals rather than one. Nothing is
enacted here: `ports/iam_actions.py` is the named enact seam and `InvestigationService` does
not take it as a dependency, which
`tests/unit/test_investigation_service.py::test_the_investigation_path_never_enacts_a_containment`
asserts. A LOW result is deliberately NOT escalated, because manufacturing a review for a
routine case trains reviewers to rubber-stamp.

### Could a model change a customer's outcome?

No, and the boundary is structural rather than procedural. The score, the band, the severity
and the containment set come from pure standard-library code in `domain/fusion_engine.py`,
which imports no model, no port and no clock. A model only restates the engine's findings in
prose, from a brief that contains an already-masked subject and nothing but engine facts, and
its output is checked by `domain/narrative.py::is_grounded`, which fails any narrative
containing a number the engine did not produce; a failed draft is discarded for the
deterministic one. Same inputs and same policy give a byte-identical assessment, so an
investigator or an auditor can recompute any result without the model. [`../model-card.md`](../model-card.md)
records the full boundary, including the honest state of the managed narration adapter.

### How is personal data handled?

This service does process personal data: an account identifier, device identifiers, IP
addresses and geolocation. It does not get to declare the PII controls not applicable, so it
redacts at every boundary instead. `domain/pii.py` selects and ORDERS the pattern rows from
the shared `pii-kit` for the jurisdictions this deployment serves (`("SG", "HK", "JP", "AU")`
as shipped, national-id rows first and the universal email and phone rows last).
`domain/investigation_service.py` masks the subject before the narrative brief is built and
again before the audit write, including every field of every citation. The outbound review
payload is masked against EVERY jurisdiction's rows rather than only this deployment's,
because the console is a shared sink (`adapters/_review_payload.py`). The trace span carries
structural attributes only, never content. The eval gate scores `pii_safety` two ways, a pack
scan plus an independent planted-literal oracle, and `tests/unit/test_not_falsely_green.py`
proves that metric can go red.

One boundary is honestly NOT closed: the runtime guardrail (**Hrz1**) is not integrated. There
is no `GuardrailPort` in this repo, because no untrusted free text reaches a model on the
shipped path. Rule R1 in [`../../COMPLIANCE.md`](../../COMPLIANCE.md) records that as Partial
and says exactly what to bind, and when.

### How is the work auditable and reproducible?

Every investigation writes an already-redacted `AuditEvent` carrying the action, the verified
actor, the decision, the severity, a redacted summary and the citation set. Every result and
every signal carries a `Citation` back to the session row or login event it came from. The
audit actor is the server-verified `Principal`, never anything the request body asserted. The
local trail is append-only, hash-chained AND externally anchored: `audit_anchor_path` points
at a file on a different volume that every append writes the chain head to, because a
truncated chain still verifies perfectly on its own.
`tests/unit/test_audit_anchor.py` proves the detection, proves the control case goes
undetected without an anchor, and proves an append after a divergence refuses rather than
quietly re-anchoring. In production the immutable record is the locked WORM bucket
(`infra/terraform/logging_worm.tf`, minimum 180 days, and the lock is irreversible) and
ultimately the Hrz5 sink; the in-repo chain is the offline stand-in, and
[security-faq.md](security-faq.md) states its exact limits.

### What is the model-risk story?

An offline eval gate runs on every change and a promotion authority owns the go-live verdict.
`eval/run_eval.py --mode smoke` drives the real `InvestigationService` over
`eval/datasets/golden_cases.jsonl` with SDK-free adapters and scores four metrics against the
DATASET's own hand-labelled oracle, never against the pipeline's own verdict:
`fusion_accuracy` at 0.80, `review_safety` at 1.0 (an escalation that should have happened and
did not is not tradeable), `groundedness` at 0.99 and `pii_safety` at 0.99. Every one of them
is proven able to go red in `tests/unit/test_eval_metrics_can_go_red.py`. `--mode gate`
delegates the promotion verdict to the **Hrz4** AI-quality service and refuses to run off the
managed profile, under the bundle id `account-takeover-investigator`. Registering that
bundle and its thresholds with Hrz4 is an open adopter step (principle P-08, rule R5), and a
fork must relabel the golden set for its own account population or the gate measures the wrong
thing.

### Is data residency enforced, or only documented?

Enforced at deploy time, with one honest gap in the build wiring. The region is chosen once
(`asia-southeast1`), carried by `config/settings.yaml`, reported by `/healthz` and printed on
the agent card. On the infrastructure side, `infra/terraform/variables.tf` validates the
EFFECTIVE region against the residency allowlist at `terraform plan` time, the allowlist
defaulting to exactly the region this repo was rendered for
(`infra/terraform/render.tf.json`); `org_policy.tf` pins `constraints/gcp.resourceLocations`
to that region's location group and forbids exportable service-account keys; and every
regional resource is created in it, the CMEK key ring (`kms.tf`), the locked WORM audit bucket
(`logging_worm.tf`) and, when the opt-in serving edge is enabled, the Cloud Run service and
its regional network endpoint group (`production_edge.tf`).
`infra/terraform/production_edge.tftest.hcl` is the executable proof:
`residency_defaults_are_in_country` fails if any of those drifts off region and
`reject_region_outside_the_residency_allowlist` fails if the allowlist stops refusing, both
against a mocked provider so they need no project and no credentials. The gap is that this
repo has no `tf-check` make target and no `terraform` CI job, so those runs only happen when
somebody types `terraform -chdir=infra/terraform test` by hand. Wiring that into a build is an
adoption step, listed in [`../ADOPTING.md`](../ADOPTING.md).

### Which regulators does this map to?

[`../../COMPLIANCE.md`](../../COMPLIANCE.md) maps the catalog's own principles (P-01 to P-13)
and dependency rules (R1 to R8) to concrete controls with an evidence file per row, aligned to
MAS TRM, APRA CPS 234 and CPS 230, HKMA and PDPA-class regimes. The mapping from those rows to
a specific regulation, and the judgement that a control is SUFFICIENT for that regulation, is
explicitly **adopter-owned**: it depends on your risk appetite, your regulator, your licence
conditions and your existing control library. This repo does not make that claim on your
behalf, and no row should be quoted as regulatory assurance. What an adopter adds in their own
library: the crosswalk to their control ids, a risk acceptance for every row still Partial or
TODO at go-live, a second-line review of the deterministic policy in `domain/` (it is
bank-owned logic, not a vendor default to inherit unexamined), and the retention schedule and
legal basis for the audit trail this service writes.

### Which rows are still open, so I know what to ask about?

The status column in [`../../COMPLIANCE.md`](../../COMPLIANCE.md) is the authority, and it is
written to be honest rather than flattering. The ones a compliance reviewer will care about
most: **R1** (bind a `GuardrailPort` to Hrz1 once untrusted text reaches a model), **R2** and
P-07's platform half (send traces and the audit record to the shared Hrz5 sink rather than
only this process), **R4** and **R5** (register the agent card with Hrz3 and the eval bundle
with Hrz4), **P-10** (timeouts, circuit breakers and a documented kill switch per outbound
dependency, plus CPS 230 recovery objectives in the runbook), **P-11** (nothing to budget yet,
because no live model call exists), and tenant isolation (object-level authorisation derived
server-side once this service gains a queryable store). **P-05** and **R3** are dormant rather
than open: there is no retrieval step, and they become mandatory together the moment one
appears.

### Can we run it against real customer sessions today?

Not without your own legal, security and model-risk sign-off. Every fixture is obviously
fictional: invented device ids, RFC 5737 and RFC 3849 literals, a fixed reference instant and a
`demo-bank` tenant, with one planted national id that exists solely so the redaction check has
an independent literal to look for. The adoption checklist in
[`../ADOPTING.md`](../ADOPTING.md) lists what must precede any live use: your residency
decision and its enforcement wired into a build, your IdP, your policy numbers signed off by
second line, your containment ladder reviewed against your playbook, your jurisdictions, your
data, your relabelled golden set, and the four construction-only managed adapters replaced.
