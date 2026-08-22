# Security FAQ

For an AppSec reviewer sizing up G4, the Account Takeover Investigator. It says what the
attack surface is, which controls are real and tested, what is deliberately out of scope (and
why that is honest rather than a gap), and where the evidence lives.

## What does this system actually process?

One authentication session at a time, and the evidence around it. `SessionSnapshot` in
`domain/models.py` carries a subject id, a session id, a tenant, a device id, a country and
latitude/longitude, a behavioural-biometric deviation score, and a tuple of recent
`LoginEvent`s (each with its own IP, country, coordinates and success flag).
`AccountBaseline` carries the devices on file and the account's home location. That IS personal
data: an account identifier, device identifiers and geolocation. Unlike some catalog systems,
this repo does not get to declare the PII controls not applicable. It redacts instead.

## Where is redaction applied, and is it tested?

At every boundary the data can cross, not once. `domain/investigation_service.py` masks the
subject with `pii_kit.redact` and the pattern set from `domain/pii.py` BEFORE it builds the
narrative brief the model would read, and again before the audit write, including every field
of every citation (`_redact_citation`, because an intake identifier can embed the subject id).
`adapters/_review_payload.py` redacts the subject, the summary and every citation snippet
before the payload leaves the process for Hrz7, and it does so against EVERY jurisdiction's
rows rather than only this deployment's, because the console is a shared sink. `agent/tools.py`
masks a tool result before it returns, because a tool result becomes model context.
`tests/unit/test_investigation_service.py::test_pii_in_the_subject_is_redacted_before_the_audit_write`
and `tests/unit/test_review_routing.py::test_the_payload_is_redacted_before_it_leaves_the_process`
are the standing gates, and `tests/unit/test_not_falsely_green.py` proves the eval safety
metric can actually go red rather than being green by construction.

## What about the trace backend? Spans leak content in most systems.

Not here, and it is asserted. `InvestigationService.investigate` opens exactly one span,
`ato.investigate`, whose attributes are STRUCTURAL only: the action, the actor and the tenant.
Never the subject id, never the session id, never the narrated summary. The reasoning is
written into the method docstring: a trace backend has no redaction stage, a wider read
audience and no retention rule written against a regulator's requirement, so content-shaped
data reaching a span has left the boundary the redact calls exist to hold, and left it
silently. `tests/unit/test_span_emission.py` pins the attribute set as a fixed allowlist
whatever the verdict, and asserts that no attribute carries the planted identifier.

## How is identity handled? Can a caller spoof the actor?

No. `api/schemas.py::InvestigateRequest` has no `actor` field to spoof, and `api/app.py`
resolves the principal server-side through the bound `IdentityPort` (`get_principal`), 401 on
failure. The resolved `Principal` is what becomes the audit actor and the review maker. Under
`gcp`, `adapters/gcp/identity.py` verifies the Identity-Aware Proxy assertion: signature
against IAP's own key set (`certs_url=`, not google-auth's OAuth2 default), audience against
the configured `ATOINVEST_IAP_AUDIENCE`, plus its own issuer check, because
`verify_token` does not do that one. An unset or emptied audience REFUSES every caller with a
503 naming the fix, because `audience=None` means the audience is not verified and would
accept any Google-signed token from any project. Under `local` the personas are seeded dev
identities on an `X-Dev-Persona` header (offline only, and the adapter refuses to construct
unless `local` was chosen deliberately). Under `onprem` the adapter raises. That one verifying
adapter is the one that may not go untested: `tests/unit/test_iap_identity.py` runs in every
gate, and `tests/unit/test_iap_crypto_matrix.py` drives the REAL verifier over locally minted
assertions, with `tests/unit/test_assertion_pinning.py` pinning the algorithm and claim checks
so an unsigned or symmetric-algorithm assertion is refused.

## What stops an unauthenticated deployment answering the internet?

`add_loopback_exposure_guard` is registered on the app OBJECT at module scope in `api/app.py`,
not inside `main()`, because the Dockerfile `CMD` and `make run-api` serve the object; a bound
that lives only in `main()` never runs in a shipped process. It is registered last, so it is
the outermost middleware and refuses an off-loopback caller before CORS, before the header
baseline and before any dependency runs. What drives it is the IDENTITY BINDING and nothing
else: the route is bounded unless a profile was deliberately chosen AND the bound identity
adapter DECLARES `VERIFIED` (`ports/identity.py`). `ATOINVEST_S2S_TOKEN` takes no
part in that decision, deliberately: it authenticates a calling SERVICE and no end user, and
while it did take part, setting it switched the guard off for the very end-user routes it was
protecting. `tests/unit/test_serving_path_exposure.py` and
`tests/unit/test_end_user_auth_posture.py` are the standing gates, the second walking the
guard's argument through the constants it names so a credential cannot reappear at any depth.
Relatedly, `/docs`, `/redoc` and `/openapi.json` are ABSENT rather than guarded outside the
deliberate `local` profile: a guard the profile has switched off is no guard.

## Can this service lock an account or revoke credentials?

No, and that is enforced rather than promised. Containment is RECOMMENDED. `ports/iam_actions.py`
exists so the enact seam is named, typed and swappable, but `InvestigationService` does not
take it as a dependency at all, and
`tests/unit/test_investigation_service.py::test_the_investigation_path_never_enacts_a_containment`
asserts that a run producing a containment recommendation makes zero calls to it. An adapter
is not the same as an action taken.

## What about outbound service-to-service calls?

The one outbound call on the shipped path is the review submission to Hrz7, built on the
shared `review-kit` client, which refuses a plaintext non-loopback URL and a missing
bearer at construction. Its credentials (`HRZ7_S2S_TOKEN`, `HRZ7_S2S_SIGNING_KEY`) are
deliberately distinct variables from this service's own inbound
`ATOINVEST_S2S_TOKEN`: mixing inbound and outbound credentials into one
variable is how a compromise of one direction becomes a compromise of both.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` holds environment variable NAMES and
non-secret defaults resolved through `${VAR:-default}`, `.env.example` documents the
non-secret variables, and `.env.secrets.example` carries placeholder values for the secret
names only. On the deploy side, `infra/terraform` never writes a secret value either: the
`additional_secret_env` variable maps an environment variable name to an existing Secret
Manager secret and a NUMERIC version, refusing `latest` (a moving version is a payload nobody
reviewed) and refusing any name this stack sets itself, so a secret cannot silently shadow the
residency, identity or routing wiring.

## What is the supply-chain posture?

Committed lockfiles (`requirements-dev.lock`, `requirements-gcp.lock`), installed with
`--no-deps` by `make install`, by CI and by the Dockerfile. The four catalog commons
(`pii-kit`, `hex-service-kit`, `agent-eval-kit`, `review-kit`) are declared by tag in
`pyproject.toml` and pinned in the lockfiles to the 40-character COMMIT each tag resolved to,
because a tag can be moved and a commit cannot;
`tests/unit/test_repo_artifacts.py` asserts that three-way agreement offline. Add a
digest-pinned base image, `USER appuser` at uid 10001, SHA-pinned GitHub Actions, per-ecosystem
dependabot, and `pip-audit` (`make audit`) plus `npm audit` for `ui/` as hard CI failures.

## Is the audit trail tamper-evident?

Yes, with an honest limit that is itself tested. The local sink wraps the commons
hash-chained log, and it is ANCHORED as well as chained: `audit_anchor_path`
(`ATOINVEST_AUDIT_ANCHOR`) points at a file on a different volume that every
append writes the chain head to. The chain alone catches an edit, a deletion or a reorder; only
the anchor catches a truncated tail, because a truncated chain still verifies perfectly.
`tests/unit/test_audit_anchor.py` proves the detection, proves the control case goes
UNDETECTED without an anchor, and proves that an append after a divergence refuses rather than
quietly re-anchoring. This is a stand-in for the managed WORM sink, not a replacement: in
production the locked Cloud Logging bucket (`infra/terraform/logging_worm.tf`) and Hrz5 are
what make the record immutable.

## What is explicitly out of scope for this repo?

The prompt-injection and output-screening gateway (**Hrz1**), which this repo does NOT
integrate today and honestly says so: there is no `GuardrailPort`, because no untrusted free
text reaches a model on the shipped path. The governed knowledge base (**Hrz2**), unused
because there is no retrieval step. Agent registration and entitlements (**Hrz3**), where this
repo only publishes the card. Promotion and model documentation (**Hrz4**). The enterprise WORM
sink and trace collector (**Hrz5**). The reviewer's console and its workflow (**Hrz7**), which
this repo routes to and does not re-implement. Case management after the reviewer picks the
item up is nobody's job in this repo either. See [features-faq.md](features-faq.md) for the
full boundary map and [`../../COMPLIANCE.md`](../../COMPLIANCE.md) for the per-rule status.
