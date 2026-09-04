# Features FAQ

For product, fraud-operations and delivery teams: what G4 produces, what is deterministic
versus narrated, and where its responsibilities **stop** and a sibling catalog system takes
over. Cross-references: [`../../README.md`](../../README.md), [`../../DEMO.md`](../../DEMO.md),
[`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

### What does G4 actually produce?

A cited **account-takeover investigation** for one session. Given a subject id and a session
id it fetches the session snapshot (device, country, coordinates, behavioural-biometric
deviation, recent login history) and the account baseline (devices on file, home location),
fuses four signals into a risk score and a band, and returns an `Investigation`: the band and
score, one `FusedSignal` per detected anomaly with its own summary, detail, severity and
uplift, a set of recommended containment actions with rationales, a readable narrative
summary, the citations behind all of it, and a `review_ref` saying where the escalation WENT.

The four signals in `domain/fusion_engine.py` are:

| Signal | Fires when | Default severity |
|---|---|---|
| `device_change` | the session's device is not among the account's known devices | HIGH |
| `impossible_travel` | the implied speed from the last successful login exceeds the policy ceiling (900 km/h), over a distance above the GPS-jitter floor (50 km) | CRITICAL |
| `credential_stuffing` | failed logins in the window (15 minutes) reach the threshold (5) | HIGH |
| `biometric_deviation` | the session's behavioural-biometric deviation reaches the threshold (0.60) | MEDIUM |

### What is deterministic, and what does the model do?

The consequential decision is deterministic and replayable, and the split is physical. The
score is `base + sum(uplifts)` clamped to the policy range; the band comes from policy
cut-offs (CRITICAL at 0.80, HIGH at 0.50, MEDIUM at 0.25); the containment set is a
deterministic function of the band through `_CONTAINMENT_LADDER`. All of that is pure stdlib
in `domain/fusion_engine.py`, which does not import a model, a port or a clock (`as_of` rides
on the snapshot), so the same snapshot, baseline and policy give a byte-identical assessment
and an auditor can recompute it. `signal_key` fingerprints each anomaly so re-runs diff
exactly rather than fuzzily.

The model's only job is prose. It is handed a `NarrativeBrief` (`domain/narrative.py`) that
carries an already-masked subject and nothing but engine facts: the band, the score, one line
per signal and one per containment. Its output is checked by `is_grounded`, which fails any
narrative containing a number the engine did not produce, and a failed draft is silently
replaced by the deterministic `draft_narrative`. Narration never blocks and never decides. See
[`../model-card.md`](../model-card.md) for the full boundary, including the honest state of the
managed narration adapter.

### Is anything auto-approved? Does it lock accounts?

No, on both counts. Containment is RECOMMENDED, never enacted. Everything above `MONITOR`
sets `requires_human_review`, and the flag is not the escalation: the result is ROUTED through
`ReviewRouterPort` to the `human-review-console` in the same call that produced it, on the API, the CLI
and the agent tool alike (rule R8). CRITICAL demands two approvals rather than one
(`adapters/_review_payload.py`). The port that WOULD enact a containment
(`ports/iam_actions.py`) is not even a dependency of `InvestigationService`, and
`tests/unit/test_investigation_service.py::test_the_investigation_path_never_enacts_a_containment`
asserts zero calls to it. The agent proposes; a fraud analyst disposes.

### How many ways can I call it, and do they behave the same?

Five, and they share the domain service rather than reimplementing it: the FastAPI app
(`POST /v1/investigate`), the argparse CLI
(`account_takeover_investigator investigate <subject> <session>`), the two agent tools
(`investigate_session` and `list_ato_queue`, advertised on the A2A card at
`/.well-known/agent-card.json`), the embeddable `ui/` micro-frontend, and the eval harness.
Each routes an escalation in the same call that produced the result, so rule R8 does not hold
on four surfaces out of five. One difference is deliberate: an agent tool result is masked for
personal data before it returns and an API response to the caller who supplied the identifier
is not, because a tool result becomes model context and P-04 is about what reaches a model.

### Which capabilities does this repo own vs integrate from the catalog?

This is one system in a catalog of composable systems. It **owns** the takeover fusion logic
and its outputs. Everything cross-cutting belongs to a sibling, and the honest state of each
integration is below. Do not rebuild these in a fork.

| Concern | Owned by | G4's role today |
|---|---|---|
| Runtime guardrail: prompt-injection defence, output screening | `agent-guardrail-gateway` | **not integrated.** No `GuardrailPort` exists, because no untrusted free text reaches a model on the shipped path. Rule R1 requires one the moment that changes. |
| Governed, ACL-aware knowledge base with citations | `enterprise-knowledge-base` | **not used.** There is no retrieval step, so rule R3 and principle P-05 are dormant. Add retrieval and both apply. |
| Agent registry, versioning, identity, entitlements | `agent-registry` | publishes its A2A card, built from the same tool table the runtime binds. Registering it is the adopter's step (R4). |
| AI-quality, eval and model-risk promotion gate | `model-quality-gate` | `eval/run_eval.py --mode gate` is the client half and refuses to run off the managed profile; bundle id `account-takeover-investigator`. Registering the bundle is the adopter's step (R5). |
| Observability, tracing, immutable WORM audit | `agent-observability` | emits one structural span per investigation and exports OTLP to the `agent-observability` collector when configured. The audit half is local and tamper-evident today (R2 Partial). |
| Human review and maker-checker console | `human-review-console` | fully wired (R8): every escalation routed over `review-kit`, redacted before the wire, CRITICAL demanding dual control. This repo does not re-implement the console or its workflow. |
| Architecture and requirements validation at intake | `architecture-validator` | an intake action, not a code control (R6). |
| Customer-facing marketing and financial-promotions checks | `marketing-compliance-gate` | not applicable: this service produces no marketing output (P-13, R7). |

### How does this relate to the other financial-crime systems?

G4 is the account-takeover step: one session, one deterministic band, one recommended
containment, one routed escalation. Adjacent systems in the same tier own different decisions
and should not be duplicated here: **G1** AML alert triage and the SAR narrative, **G2**
sanctions, PEP and payment-message screening, **G3** scam and authorised-push-payment
interdiction inside the payment flow, **G5** the SOC fraud-fusion copilot that bridges cyber
and fraud alerts into an incident summary and a draft response runbook. None of them is called
from this repo, and this repo is not called from them; a deployment that wants cross-system
correlation builds that above all of them rather than inside one.

### Where exactly does this repo's responsibility end?

Three places, and it is worth being blunt about each. It ends at the RECOMMENDATION: enacting
a lock, a step-up or a credential suspension is somebody else's action, taken after a human
approves. It ends at the ROUTE: once the escalation reaches `human-review-console`, the queue, the reviewer
assignment, the disposition and any four-eyes workflow are `human-review-console`'s, and this repo only knows
the `review_ref` it got back. And it ends at ONE SESSION: there is no cross-account campaign
detection, no case management, and no feedback loop that retrains anything.

### Can I use this outside banking?

Yes. Nothing in the engine is bank-specific: the four signals are generic to any authenticated
consumer account, and the vertical shows up only in the vocabulary
(`SignalKind` / `RiskBand` / `ContainmentAction` in `domain/models.py`), the containment ladder,
the policy numbers and the fixtures. A retail or telco fork keeps the hexagon, the citation and
redaction discipline, the eval gate and the review routing, and replaces the detectors it does
not need. See [`../ADOPTING.md`](../ADOPTING.md) and [adoption-faq.md](adoption-faq.md).

### How do I see it working?

`make demo` runs the presenter-paced walkthrough: eight steps over the REAL services on the
`local` profile, from binding the stack through a routine case, a consequential case that gets
routed, a planted national id proved masked before the audit write, the reviewer's queue, an
audit verify and export, a tampered record detected, and a swap to the exit profile where
every seam refuses. `make demo-selftest` is the same arc headless and asserting every step;
`make demo-static` renders the audit-first panels to static HTML for screenshots. Everything
is synthetic, offline, and needs no cloud, no credentials and no browser engine. See
[`../../DEMO.md`](../../DEMO.md).
