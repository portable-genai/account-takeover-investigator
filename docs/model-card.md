# Model card: Account Takeover Investigator (G4)

This is a STARTER model card. It records the model boundary as built and the controls that must
be completed before a managed deployment. The deterministic engine is the system of record; the
model is a bounded, replaceable component, and today it is a component that no profile actually
calls out to a hosted model for.

There is exactly one model-shaped seam in this repository: `NarratorPort` (`ports/narrator.py`),
bound per profile in `config/settings.yaml` and implemented under
`adapters/{local,gcp,onprem}/narrator.py`. There is no retrieval port, no classification port,
no extraction port and no speech port; nothing in this service transcribes, embeds or reasons
over audio.

## What the model does, and does not do

- **Does**: turn a `NarrativeBrief` (`domain/narrative.py`) into a prose investigation summary.
  The brief carries an already-masked subject label, the session id, the band, the score, one
  line per fired signal (`kind: summary (+uplift)`) and one line per recommended containment.
  Nothing in it is free-form customer text, so the narrator restates engine facts and has
  nothing else to restate.
- **Does NOT**: produce any number, band, severity, containment recommendation or escalation
  decision. Every one of those is computed in pure standard library by
  `domain/fusion_engine.py`: the four detectors, the score as `base + sum(uplifts)` clamped to
  the policy range, the band from the `FusionPolicy` cut-offs, the worst-severity selection, and
  the containment ladder that decides what `requires_human_review` is set on. That module
  imports no model, no port, no HTTP client and no clock (`as_of` rides on the snapshot), so the
  same snapshot, baseline and policy replay byte-identically. With the narrator swapped for a
  stub, or for the deterministic local adapter, every figure and every verdict is unchanged: a
  model change cannot move a number.

## Boundary and validation

- **Redaction happens before the model sees anything.** In
  `domain/investigation_service.py::investigate` the subject is masked with `pii_kit.redact`
  and the pattern set from `domain/pii.py` on the line BEFORE `brief_from_assessment` builds the
  brief, and the brief is what the narrator is handed. The same redaction runs again before the
  audit write, over the headline, the narrative and every field of every citation, and
  `tests/unit/test_investigation_service.py::test_pii_in_the_subject_is_redacted_before_the_audit_write`
  is the standing gate on that half. Note honestly that there is no spy-adapter test asserting
  that no raw identifier reaches the narrator port itself; today that claim rests on the call
  order and on the brief's shape. See the TODO list below.
- **The output is validated against the engine, and a bad output is discarded rather than
  repaired.** `domain/narrative.py::is_grounded` collects every numeric token the engine
  legitimately produced (the score, each signal's summary, detail and uplift, each containment
  rationale, plus the subject and session identifiers) and fails any narrative containing a
  number outside that set. A failed draft is replaced by `draft_narrative`, the deterministic
  summary composed from the brief alone, which is grounded by construction. Narration never
  blocks an investigation and never delays one.
  `tests/unit/test_investigation_service.py::test_an_ungrounded_model_draft_is_discarded_for_the_deterministic_one`
  drives a fabricating narrator and asserts the invented figure does not survive; the eval gate
  scores the same property as `groundedness` at a 0.99 threshold.
- **Nothing the model touches auto-executes (rule R8).** A consequential band sets
  `requires_human_review` AND the surface routes the result through `ReviewRouterPort` to the
  `human-review-console` in the same call, on the API, the CLI and the agent tool alike, with the payload
  redacted before the wire and CRITICAL demanding two approvals
  (`adapters/_review_payload.py`). Containment is recommended, never enacted:
  `InvestigationService` does not depend on `IamActionsPort` at all.
- **What reaches a trace is narrower still.** The one span per investigation carries the action,
  the actor and the tenant. Never the subject, the session id or the narrated summary
  (`tests/unit/test_span_emission.py`).

## Adapters and profiles

| Profile | Narrator adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/narrator.py` | `LocalNarratorAdapter`: returns `draft_narrative(brief)`, the deterministic grounded-by-construction summary. **No model, no SDK, no network.** This is what the offline gate, the eval harness and the demo all run. |
| `gcp` | `adapters/gcp/narrator.py` | `CloudNarratorAdapter`: lazily imports `google.genai`, constructs a Vertex client pinned to the configured region, and then raises `NotImplementedError` naming what a deployment must bind. **There is no live model call today.** |
| `onprem` | `adapters/onprem/narrator.py` | `OnPremNarratorAdapter`: raises, because the client runs narration against their own in-tenancy model. A placeholder returning empty prose would hide that the seam was never bound. |

So the honest summary of the shipped state is: **no profile in this repository performs an
inference call.** The `gcp` adapter is a construction-only placeholder, and the repo says so in
more than one place rather than only here: `managed_readiness.py` lists
`narrator.CloudNarratorAdapter.narrate` among the four incomplete managed operations and
refuses API startup on a managed profile that would bind one, and
[`../COMPLIANCE.md`](../COMPLIANCE.md) rows P-05 and P-11 record the same fact from the
principle side.

## Remaining controls (TODO, repo owner)

- **Model id, version and prompt, for the `gcp` adapter** (P-07). Pin the exact model and
  record it in this card, wire the prompt that instructs the model to restate the brief and
  nothing else, and map the response. Note the one place a model name is already written down
  is the `model-quality-gate` promotion client in `eval/run_eval.py` (`model="gemini-3.5-flash"`); that string
  is what the gate is asked about, not what any adapter calls, and the two must be reconciled
  when the adapter is implemented.
- **A spy-adapter test on the narrator boundary** (P-04). Assert directly that a
  `NarrativeBrief` handed to the port contains no raw subject identifier, with a planted
  literal, so the redact-before-the-model claim is enforced rather than inferred from call
  order.
- **Budget, rate control and a kill switch** (P-10, P-11). A per-request token budget, a request
  rate limit, timeouts and a circuit breaker on the narration call, and a switch that forces
  deterministic-only operation with the model disabled. Because narration already falls back to
  `draft_narrative`, the kill switch is cheap: it is a binding change, not a rewrite. Report
  spend through `agent-observability`.
- **A managed-profile eval run through the `model-quality-gate`** (P-08, R5). The offline eval scores the
  deterministic local narrator, so `groundedness` currently measures a path that cannot
  fabricate. Add a managed-profile run that scores real narration groundedness against the same
  golden cases, and register the bundle `account-takeover-investigator` and its thresholds
  with `model-quality-gate` so `--mode gate` has an authority to ask.
- **Prompt-injection screening through `agent-guardrail-gateway`** (R1). Not required by the shipped path, because
  the brief contains only engine-produced labels and numbers. It becomes required the moment
  any free-form text (an analyst note, a device-intelligence vendor's description, a customer
  message) is added to the brief: bind a `GuardrailPort`, screen input and output, and fail
  closed to deterministic-only when the screen is unavailable.

Until these are complete the system is safe to run offline: the deterministic engine plus the
grounded local narrator produce the full cited investigation, the escalation is really routed,
and no model influences any figure. The managed narration path is not production-cleared, and
`managed_readiness.py` refuses to let a managed deployment pretend otherwise.
