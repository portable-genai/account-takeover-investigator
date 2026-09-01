# Adoption FAQ

For an engineering lead forking G4 as their institution's account-takeover base. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this page answers the "will it hurt
later?" questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` does the mechanical half in one pass: the python package name, the
`ATOINVEST` environment prefix, the distribution and resource id
`account-takeover-investigator`, and optionally the Terraform `name_prefix` default. It
prints a plan and writes nothing without `--yes`; preview with `--dry-run` first. Then
recreate the venv (the distribution name changed), `make install`, and `make gate`.

Two flags you will look for and not find, deliberately. There is no `--cli`: the
`[project.scripts]` entry point is named after the package, so `--package` renames the console
script too and a second flag could only drift out of step. There is no `--dist`: `--resource`
is one literal doing four jobs (the distribution name, the GitHub id, the A2A agent-card name,
and the Hrz4 eval bundle id), and they are the same string on purpose so a fork's promotion
record and its discovery card cannot disagree about which system they describe. Markdown prose
is left alone unless you pass `--include-docs`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via git **tags** and rebase rather than merging `main` continuously.
[`../ADOPTING.md`](../ADOPTING.md) section 2 draws the core-vs-adopter-owned boundary
explicitly: upstream owns `domain/kernel.py`, `ports/`, the `Container` machinery in
`config.py`, `tests/contract/`, the eval harness mechanics, the exposure guard and identity
wiring in `api/app.py`, and CI; you own the `policy:` values, the detectors and the
containment ladder, `domain/models.py`, the PII jurisdictions, every fixture, the golden eval
set, `adapters/onprem/*`, `ui/` theming and your tfvars. Keep your edits inside that second
list and conflicts stay where you were told to expect them.

### Is there a real kernel module I keep untouched, or is that aspirational?

Real. `domain/kernel.py` holds the vertical-neutral machinery (`Citation`, `AuditEvent`,
`Severity`, `Decision`, `utcnow`) and imports nothing from the takeover vertical, so you can
import it without loading a line of fusion logic. `domain/models.py` holds this vertical's
artifacts and vocabularies. The split is enforced from the other direction too:
`tests/unit/test_core_purity.py` fails the build if anything in `domain/` imports outside what
the core owns, with a written exemption list and a control case proving the scan can see a
violation.

### Can I retune the risk numbers without touching engine code?

Yes, and this repo is deliberate about it. `domain/fusion_engine.py` contains no numeric
literal of its own: every threshold and weight comes from the frozen `FusionPolicy` in
`domain/policy.py`, populated from the `policy:` block of `config/settings.yaml` and threaded
in through `FusionEngine.from_policy`. So an adopter tunes the four uplifts, the three band
cut-offs, the impossible-speed ceiling, the GPS-jitter floor, the stuffing window and
threshold, and the biometric threshold as configuration, and an auditor reads the whole policy
in one place. Unknown keys in the block are ignored rather than fatal, which has one sharp
edge worth knowing: a TYPO in a key name silently leaves the engine default in force, because
the loader validates the block's presence and not its spelling. Pin your values with a test in
`tests/unit/test_fusion_engine.py` and the typo cannot hide.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and the contract suite enforces it in both directions. A port must
be registered in FIVE places or it runs with no enforcement at all: `ports/__init__.py`
(`PORT_PROTOCOLS`), `config.DEFAULT_BINDINGS`, a `Container` accessor, the `adapters:` block
of `config/settings.yaml`, and a `PortCase` in `tests/contract/canonical.py`. Then bind it in
all three families. `tests/contract/test_port_parity.py` asserts set equality across all five,
so a port that is bound but unregistered, or registered but unbound, fails the build. The
file-by-file walkthrough is in [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

### How do I add a new adapter to an existing port?

One class under `adapters/<family>/` with the single constructor shape `Adapter(settings)` and
any cloud import INSIDE the method, the same `module:Class` target in both
`config.DEFAULT_BINDINGS` and `config/settings.yaml` (`tests/unit/test_settings_file.py` fails
if the two disagree), and any new variable documented in `.env.example`. If it is a managed
adapter that is still a placeholder, add it to `INCOMPLETE_MANAGED_OPERATIONS` in
`managed_readiness.py`, which refuses API startup on a managed profile that would bind it.
Removing an entry from that tuple is how you declare the real integration exists, and it is
gated on an integration test proving the response mapping.

### How do I add or change a signal?

A signal is a detector method on `FusionEngine`, a `SignalKind` member in `domain/models.py`,
an uplift field on `FusionPolicy` plus its key in the settings `policy:` block, and a case in
`tests/unit/test_fusion_engine.py`. Give it a `signal_key(...)` fingerprint over the
normalising identity parts so re-runs diff exactly, and a `Citation` so the finding has
provenance; a claim with no provenance is not shippable here. Detection returns signals
sorted by severity then key, so ordering stays deterministic without a caller thinking about
it.

### How do I change the taxonomy?

`SignalKind`, `RiskBand` and `ContainmentAction` are `LenientStrEnum` members, so a member IS
its wire value and the serialised JSON carries the enum strings. You extend a vocabulary
without editing engine code; you do have to extend `_CONTAINMENT_LADDER` and `_BAND_SEVERITY`
together if you add a band, because a band with no ladder entry raises on the first result
that reaches it.

### Will the demo rot after I diverge?

It is guarded from two directions. A demo step exists in exactly two places, `demo.STEPS` and
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two sets equal inside
the offline gate, so a narrated claim nobody verifies cannot exist. `make demo-selftest` then
runs the whole eight-step arc headless against the REAL demo server over loopback HTTP and
asserts that the service actually reached the state each narration claimed, in its own
required CI check (the hosted Cloud Build check) rather than inside `make gate`, because
the gate must stay fast and offline. When you add a step, put the numbers the check reads in
the step's `facts` dict rather than only in rendered prose: a check that parses prose breaks on
a wording change.

### Does CI run for my fork out of the box?

Yes. the hosted Cloud Build check is a thin caller of the shared reusable hard-gate workflow,
pinned to a TAG rather than a branch, and it references no `secrets.` at all. The gate is
offline and credential-free by design: no cloud SDK, no project, no network. The one job that
needs the runtime lockfile is the IAP crypto matrix, and even that stays offline because the
signing key is minted in-process and the key-set fetch is served in-process. You add secrets
only when you wire the `gcp` profile. Note that the eval gate measures the reference fixture
population until you relabel `eval/datasets/golden_cases.jsonl`; that is an explicit adoption
step, not a silent pass.

### What will bite me that is not obvious?

Four things. The four managed adapters listed in `managed_readiness.py` are
construction-only, so a managed deploy is blocked until you implement your session store,
feature store, narrator and IAM-action integrations. The Terraform posture is real and tested
but its test run is not wired into any build here (no `tf-check` target, no `terraform` CI
job), so wire `terraform -chdir=infra/terraform test` into your pipeline yourself. The KMS key
ring created by `kms.tf` can never be deleted, so a destroy-and-redeploy needs a fresh
`name_prefix`. And the WORM bucket lock is irreversible at whatever `retention_days` you
apply, so decide that number before the first apply, not after.
