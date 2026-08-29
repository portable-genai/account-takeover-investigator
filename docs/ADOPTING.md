# Adopting this repo as your base

This repository (G4, the Account Takeover Investigator) is a **common base** that a bank,
a retailer or any other institution with a login surface forks to build its own
account-takeover investigation service: something that pulls one session's device,
geography, login-history and behavioural-biometric evidence together, fuses it into a
deterministic risk band with one auditable uplift line per signal, drafts a cited summary a
fraud analyst can read, and ROUTES the recommended containment to a human instead of enacting
it. Forking it gives you a working hexagonal core (a pure-stdlib domain, typed ports, three
adapter families, a green offline gate that needs no cloud and no credentials) plus a fully
worked account-takeover vertical, four signals and a four-band containment ladder, that you
can keep, retune, or replace with your own fraud model.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical
rebrand** (one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and the request
> pipeline), [`SPEC.md`](../SPEC.md) (the locked contracts), [`CONTRIBUTING.md`](../CONTRIBUTING.md)
> (the file-by-file touch list for a new port or adapter), [`model-card.md`](model-card.md)
> (what the model does and does not do), and the [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The domain is split so the boundary between reusable machinery and the takeover vertical is a
physical module split, not a convention. `domain/kernel.py` holds the vertical-neutral types
and imports nothing from the vertical; `domain/models.py` holds this vertical's artifacts.
`tests/unit/test_core_purity.py` keeps the whole `domain/` package free of cloud, web and HTTP
imports, so what you inherit really is portable.

| Layer | Where | For a new fraud vertical |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py` (`Citation`, `AuditEvent`, `Severity`, `Decision`, `utcnow`), every Protocol in `ports/`, the `Container` and binding loader in `config.py`, `adapters/_review_payload.py`, `managed_readiness.py` | keep untouched |
| **Policy (your numbers)** | the `policy:` block of `config/settings.yaml`, read into the frozen `FusionPolicy` in `domain/policy.py`: the four per-signal uplifts, the three band cut-offs, `impossible_speed_kmh`, `min_travel_km`, the stuffing window and threshold, `biometric_threshold` | change deliberately (see section 4) |
| **Vertical (the takeover logic itself)** | the artifacts in `domain/models.py` (`SessionSnapshot`, `AccountBaseline`, `LoginEvent`, `FusedSignal`, `ContainmentRecommendation`, `FusionAssessment`, `Investigation`, and the `SignalKind` / `RiskBand` / `ContainmentAction` vocabularies), the detectors and the containment ladder in `domain/fusion_engine.py`, the brief and groundedness oracle in `domain/narrative.py`, the jurisdiction selection in `domain/pii.py`, the offline fixtures in `adapters/local/fixtures.py`, and the eval golden set | rewrite for your model |

If your product is another *deterministic-decision plus grounded-narration* investigator, the
hexagon, the three profiles, the redact-before-anything rule, the citation discipline, the
eval gate and the Hrz7 review routing transfer directly. You replace the detectors and the
containment ladder, and you retune the policy numbers.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, everything in `ports/`,
  `config.py`'s `Container` and `DEFAULT_BINDINGS` machinery, `tests/contract/`, the eval
  harness mechanics in `eval/run_eval.py`, `api/app.py`'s exposure guard and identity wiring,
  `adapters/gcp/identity.py`, the `scripts/` demo surface mechanics, and the CI workflows.
- **Adopter-owned** (yours; expect to edit): the `policy:` values in `config/settings.yaml`,
  the detectors and ladder in `domain/fusion_engine.py`, `domain/models.py`, the
  `JURISDICTIONS` tuple in `domain/pii.py`, every fixture (`adapters/local/fixtures.py`,
  `tests/fixtures/sample_cases.py`), `eval/datasets/golden_cases.jsonl` and the `THRESHOLDS`
  dict beside it, `adapters/onprem/*`, `ui/` theming, `infra/terraform/terraform.tfvars`, and
  the regulator crosswalk section of [`COMPLIANCE.md`](../COMPLIANCE.md).

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously, so conflicts stay inside files you were told to expect them in.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package name (which is also this repo's
console-script name), the `ATOINVEST` environment prefix behind every
`ATOINVEST_PROFILE`-style variable, the distribution and resource id
`account-takeover-investigator`, and the Terraform `name_prefix` default, in one pass. It
prints a plan and writes nothing without `--yes`. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_takeover_investigator \
    --env-prefix ACMEATO --resource acme-takeover-investigator \
    --name-prefix acme-ato --dry-run

# Apply:
python scripts/rename_fork.py --package acme_takeover_investigator \
    --env-prefix ACMEATO --resource acme-takeover-investigator \
    --name-prefix acme-ato --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

Three things about the flags, because they are deliberately fewer than you may expect:

- **There is no `--cli` flag.** The `[project.scripts]` entry point in `pyproject.toml` is
  named after the package (`account_takeover_investigator`), so `--package` renames the CLI
  too, and a second flag could only drift out of step with it.
- **There is no `--dist` flag.** `--resource` is one literal doing four jobs: the distribution
  name in `pyproject.toml`, the GitHub id in `[project.urls]`, the A2A agent-card name in
  `agent/agent_card.py`, and the Hrz4 eval bundle id (`_BUNDLE` in `eval/run_eval.py`). They
  are the same string on purpose, so a fork's promotion record and its discovery card cannot
  disagree about which system they describe.
- **`--name-prefix` is optional and narrowly scoped.** It rewrites the Terraform `name_prefix`
  default (`g4-svc` here) inside its own variable block in `infra/terraform/variables.tf` and
  nowhere else, reading the current value from that file rather than assuming one. Omit it to
  leave the prefix alone.

Add `--include-docs` to sweep Markdown prose too; a default run leaves it alone so the diff
stays reviewable. The script deliberately does NOT touch the human decisions below.

## 4. The human decisions (the script cannot make these)

1. **Region and residency.** The region is chosen once and shared by the runtime and the
   infrastructure. On the application side it is `GCP_REGION` resolved in
   `config/settings.yaml` (default `asia-southeast1`), reported by `/healthz` and printed on
   the agent card. On the deploy side it is the `region` / `allowed_regions` pair in
   `infra/terraform/variables.tf`, both nullable and both defaulting to the region this repo
   was rendered for, which lives in `infra/terraform/render.tf.json` as
   `local.render_region`; `naming.tf` turns the pair into `local.region` and
   `local.allowed_regions`. The pair is validated at `terraform plan` time, so an unapproved
   region fails before anything is created, and `org_policy.tf` pins
   `constraints/gcp.resourceLocations` to that region's location group. To move a fork to
   another jurisdiction, change `render_region` (or set both tfvars), confirm the whole
   managed stack is available there, and re-run
   `terraform -chdir=infra/terraform init -backend=false && terraform -chdir=infra/terraform test`:
   the runs `residency_defaults_are_in_country` and
   `reject_region_outside_the_residency_allowlist` in `infra/terraform/production_edge.tftest.hcl`
   are the executable check, and they need no project and no credentials because the provider
   is mocked. The enforcement ships; what is still missing is the build wiring, since this
   repo has no `tf-check` make target and no `terraform` CI job, so somebody has to type that
   command. Wiring it into your own pipeline is an adoption step. While you are there, decide
   `retention_days` (180 days minimum, and the WORM lock is irreversible). See
   [`docs/runbook.md`](runbook.md).
2. **Identity and the IdP.** This repo owns no login flow, deliberately. Under `gcp` the
   identity adapter (`adapters/gcp/identity.py`) verifies the assertion Identity-Aware Proxy
   injected, checking its signature against IAP's own key set, its issuer, its expiry and its
   audience against the configured `ATOINVEST_IAP_AUDIENCE`; an unset or emptied audience
   REFUSES every caller rather than verifying against nothing. Under `local` the personas are
   seeded dev identities selected with `X-Dev-Persona`, offline demo and test only, and the
   adapter refuses to construct unless `local` was chosen deliberately. Under `onprem` the
   adapter raises, because a placeholder that pretended to authenticate would be worse than a
   missing feature. So the work is: turn on `edge_iap_enabled`, grant `iap_members`, apply
   once, read the `iap_audience` output, set the variable and apply again (the two-apply dance
   is documented on the variable itself, and exists because the backend service is built from
   the Cloud Run service and would otherwise form a cycle). Nothing in `src/` needs editing to
   do that. `tests/unit/test_end_user_auth_posture.py` is the guard that keeps the exposure
   decision derived from the identity binding and never from the
   `ATOINVEST_S2S_TOKEN` service credential.
3. **The policy numbers your fraud and compliance functions own.** Every threshold and weight
   the engine reads lives in the `policy:` block of `config/settings.yaml` and is loaded into
   the frozen `FusionPolicy` in `domain/policy.py`; `domain/fusion_engine.py` contains no
   numeric literal of its own. The ones to argue about with second line are the four uplifts
   (`device_change_uplift` 0.35, `impossible_travel_uplift` 0.50,
   `credential_stuffing_uplift` 0.30, `biometric_deviation_uplift` 0.25), the three band
   cut-offs (`critical_score` 0.80, `high_score` 0.50, `medium_score` 0.25), and the four
   detector thresholds (`impossible_speed_kmh` 900.0, `min_travel_km` 50.0,
   `stuffing_window_minutes` 15 with `stuffing_failure_threshold` 5, and
   `biometric_threshold` 0.60). They set your false-positive rate and your analyst workload.
   The shipped values are illustrative defaults, not advice: change them deliberately and add
   a case to `tests/unit/test_fusion_engine.py` that pins yours.
4. **The containment ladder.** `_CONTAINMENT_LADDER` in `domain/fusion_engine.py` maps a band
   to actions: CRITICAL to `SUSPEND_CREDENTIALS` plus `LOCK_SESSION`, HIGH to `LOCK_SESSION`
   plus `STEP_UP_AUTH`, MEDIUM to `STEP_UP_AUTH`, LOW to `MONITOR`. Everything above `MONITOR`
   is consequential, so it sets `requires_human_review` and escalates. If your institution
   auto-enacts step-up at MEDIUM, that is a policy decision with a human-review consequence,
   and it belongs in a reviewed change to that table rather than in a caller.
5. **The PII jurisdictions.** `domain/pii.py` selects and ORDERS the pattern rows from the
   shared `pii-kit`: national-id rows for `("SG", "HK", "JP", "AU")` first, the universal
   email and phone rows last. Set `JURISDICTIONS` to the markets you actually serve. Order
   matters: a vertical that adds a bare-digit account catch-all must order it last so it does
   not subsume a national id.
6. **Reference data is fictional.** Every fixture is synthetic and obviously so:
   `adapters/local/fixtures.py` uses invented device ids (`dev-sg-01`, `dev-xx-99`), RFC 5737
   and RFC 3849 literals, a fixed `AS_OF` instant so replays diff exactly, and a `demo-bank`
   tenant. The one national id in the set exists solely so the redaction check has an
   independent literal to look for. Replace the lot with your own synthetic data. **Do not run
   against real session or customer data without your own legal, security and model-risk
   sign-off.**
7. **The eval golden set and its thresholds.** `eval/datasets/golden_cases.jsonl` holds
   hand-labelled cases whose `expected_band` and `expected_review` are an INDEPENDENT oracle,
   never read back from pipeline output. The four metrics and their thresholds are the
   `THRESHOLDS` dict at the top of `eval/run_eval.py`: `fusion_accuracy` 0.80,
   `review_safety` 1.0, `groundedness` 0.99, `pii_safety` 0.99. Note that this repo has no
   `eval/rubrics/` directory: the thresholds are that one dict. A fork inherits a green gate
   that measures the WRONG population until you relabel the golden set for your own account
   base; the harness structure is generic, the cases are yours.
   `tests/unit/test_eval_metrics_can_go_red.py` is what stops a rebuilt metric from being
   falsely green.
8. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001,
   `HEALTHCHECK` on `/healthz`) and `infra/terraform/` (Org Policy, CMEK in `kms.tf`, the
   locked WORM bucket in `logging_worm.tf`, the dry-run-first VPC-SC perimeter in `vpc_sc.tf`,
   the alerting in `monitoring.tf`, and the opt-in serving edge in `production_edge.tf`)
   before you expose anything. Note that `managed_readiness.py` lists four managed operations
   that are still construction-only placeholders (`sessions`, `feature_store`, `narrator` and
   `iam_actions` on the `gcp` family) and refuses API startup on a managed profile that would
   bind one, so wiring your real session store and feature store is a prerequisite for a
   managed deploy, not an afterthought. See [`docs/onprem-migration.md`](onprem-migration.md)
   for the sovereign exit path.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches*
are owned by sibling platform services; integrate rather than rebuild them. The full map, with
the honest state of each integration, is in [`faq/features-faq.md`](faq/features-faq.md); the
per-rule evidence is in [`COMPLIANCE.md`](../COMPLIANCE.md).

- **Hrz1** guardrail gateway: **not integrated today.** There is no `GuardrailPort` in
  `ports/`, because no untrusted free text reaches a model on the shipped path (the narrator
  is handed engine facts and an already-masked subject). Rule R1 says bind one the moment
  that changes. In-repo redaction (`domain/pii.py`) is not a substitute for the gateway.
- **Hrz2** governed knowledge base: **not used.** There is no retrieval port, so rule R3 and
  principle P-05 do not apply yet. Add one and both become mandatory together.
- **Hrz3** agent registry: the A2A card is published at `/.well-known/agent-card.json` and
  built from the same tool table the runtime binds (`agent/agent_card.py`). Registering it
  and taking the agent's identity and entitlements from Hrz3 is the adopter's step (rule R4).
- **Hrz4** AI-quality and model-risk gate: `eval/run_eval.py --mode gate` is the client half
  and refuses to run off the managed profile; the bundle id is
  `account-takeover-investigator`. Registering that bundle and its thresholds with Hrz4 is
  the adopter's step (rule R5, principle P-08). The offline `--mode smoke` run mirrors it.
- **Hrz5** observability and immutable WORM audit: the tracer adapter exports OTLP to the Hrz5
  collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and to Cloud Trace when it is not. The
  audit half is local and tamper-evident today (rule R2 is Partial); pointing it at the shared
  sink is yours.
- **Hrz7** human-review and maker-checker console: fully wired (rule R8). Every escalation is
  routed through `ReviewRouterPort` over the shared `review-kit` in the same call that
  produced it, redacted before the wire, with CRITICAL demanding two approvals. You supply
  `HUMAN_REVIEW_URL` and the outbound credentials; you do not re-implement the console.
- **Rsk3** architecture and requirements validator: an intake action, not a code control
  (rule R6). Record your validation reference in `COMPLIANCE.md` when the project passes.
- **Mkt6** marketing compliance gate: not applicable. This service produces no customer-facing
  marketing output (principle P-13, rule R7).

Where this repo's responsibility ends: it investigates ONE session and recommends containment.
It does not enact containment (`ports/iam_actions.py` exists as a named seam and the
investigation path never calls it), it does not own the case-management workflow after the
reviewer picks the item up, and it does not correlate across accounts or campaigns. Adjacent
fraud verticals own their own decisions: **G1** AML alert triage and SAR narrative, **G2**
sanctions and payment-message screening, **G3** scam and authorised-push-payment interdiction
in the payment flow, **G5** the SOC fraud-fusion copilot that bridges cyber and fraud alerts.
None of them is called from here.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py` (preview then apply), recreated the venv, `make gate` green.
- [ ] Set the region in `render.tf.json` / tfvars and `GCP_REGION`, and ran
      `terraform -chdir=infra/terraform test` against your residency choice.
- [ ] Wired `terraform test` into your own build, since this repo ships no `tf-check` target.
- [ ] Enabled IAP, granted `iap_members`, and set `ATOINVEST_IAP_AUDIENCE` from the
      `iap_audience` output on the second apply.
- [ ] Owned the `policy:` numbers (four uplifts, three band cut-offs, four detector
      thresholds) with your fraud and compliance functions, and pinned them in a test.
- [ ] Reviewed the containment ladder in `domain/fusion_engine.py` against your playbook.
- [ ] Set `JURISDICTIONS` in `domain/pii.py` to the markets you serve.
- [ ] Replaced every fixture and the local session and baseline data with your own synthetic set.
- [ ] Relabelled `eval/datasets/golden_cases.jsonl` and reviewed the four `THRESHOLDS`.
- [ ] Wired `HUMAN_REVIEW_URL` plus the outbound Hrz7 credentials, and registered the
      agent card with Hrz3 and the eval bundle with Hrz4.
- [ ] Replaced the four construction-only managed adapters listed in `managed_readiness.py`
      before any managed deploy.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, `retention_days`, bind address).
- [ ] Recorded your baseline upstream tag so you can take future fixes.
