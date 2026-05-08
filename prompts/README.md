# LLM Prompts — SentinelQ

**Version**: v0 (Sprint 0).
**Roles**: 3 — `analyst`, `screener`, `risk_reviewer`.

## Design rules

1. **Structured output only.** Every response is JSON validated against a schema in `schemas/`. No free-form prose.
2. **Cite, don't paraphrase.** Definitions of KR market terms are pulled from `docs/DOMAIN_GLOSSARY.md` by section anchor (e.g. §3.2). Prompt never restates them — drift risk.
3. **Pin the glossary commit.** Each prompt header records the glossary file commit hash it was authored against.
4. **No hidden context.** Whatever the model needs is in the prompt. No retrieval at inference time in v0.
5. **Tier-aware.** Default tier per role (see table). Risk Engine may downgrade per `risk_limits.operational_limits.llm_*`.
6. **Idempotency.** Same input + same prompt version → same output (temperature 0). Reproducibility is a unit test.
7. **Bias mitigation.** Each prompt explicitly instructs the model to flag survivorship/lookahead/hindsight risks in its `risk_flags`.

## Tier defaults

| Role            | Default tier | Rationale |
|-----------------|--------------|-----------|
| screener        | haiku        | High volume, low per-call value. |
| analyst         | sonnet       | Single high-value call per decision. |
| risk_reviewer   | sonnet       | Adversarial check; same tier as analyst. |
| (escalation)    | opus         | Only on contested decisions or post-incident review. |

## Versioning

`<role>_v<MAJOR>.<MINOR>.md`. Bump MINOR for prompt edits, MAJOR for output schema changes (breaks consumers).

## Files

```
prompts/
├── README.md                  ← this file
├── analyst_v0.md
├── screener_v0.md
├── risk_reviewer_v0.md
└── schemas/
    ├── analyst_output.json
    ├── screener_output.json
    └── risk_reviewer_output.json
```
