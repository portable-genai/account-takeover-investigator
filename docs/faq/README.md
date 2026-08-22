# FAQ index

Answers to the questions different teams ask when evaluating, adopting or reviewing this
repository (G4, the Account Takeover Investigator) as a common base for account-takeover
investigation. Each page is written for a specific audience; skim the one that matches your
role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | what the service processes, server-side identity, the exposure guard, secrets, supply chain, the anchored audit chain, what is out of scope |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | how real the no-lock-in claim is, the three profiles, the executable portability check, the sovereign exit, open-format export |
| [features-faq.md](features-faq.md) | Product / fraud / delivery | what the agent produces, what is deterministic vs narrated, and the full "what this repo owns vs what it integrates" map |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rebranding, taking upstream fixes, extension points, retuning the policy numbers, whether the demo rots |
| [compliance-faq.md](compliance-faq.md) | Compliance / model risk / privacy | autonomy and maker-checker, PII handling, auditability, the model-risk story, residency, real-data readiness |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the
catalog. Where a concern belongs to another system (the guardrail gateway Hrz1, the knowledge
base Hrz2, the agent registry Hrz3, the AI-quality gate Hrz4, observability and WORM audit
Hrz5, the human-review console Hrz7), the answer names the owning catalog id and explains the
boundary rather than duplicating it. See [features-faq.md](features-faq.md) for the full map,
and [`../ADOPTING.md`](../ADOPTING.md) for the fork path.
