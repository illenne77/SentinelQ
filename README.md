# SentinelQ

KR equity AI trading agent — design + research + reference implementation.

**Status**: Sprint 0 (spec-filling). No production code yet.
**Phase**: paper (Phase 0). See `Doc/investment_agent_plan_v2.2.docx` §8.0.

## Repository layout

```
api/        OpenAPI 3.1 contract for the backend (scanner, decide, order, risk, ops)
docs/       Domain glossary + (future) ADRs, runbooks, severity matrix
prompts/    LLM prompt templates (analyst, screener, risk_reviewer) + JSON Schemas
research/   Alpha research workspaces (one folder per hypothesis A1..A7)
sql/ddl/    PostgreSQL/TimescaleDB schema (market_quote_snapshot, ...)
Doc/        Plan documents (Korean). v2.2 is current.
```

## Hard rules

1. **LONG only, KR cash equities only.** No options/futures/FX/crypto/OTC/short.
   See plan v2.2 §1A.2 (Out of Scope).
2. **No secrets in git.** `.gitignore` blocks `*appkey*`, `*credentials*`,
   `secrets/`, `.env`. Use Git Credential Manager / Vault / `.env.local`.
3. **Risk Engine is deterministic.** LLM never sets risk limits. Source of
   truth: `config/risk_limits.yaml` (currently in session workspace; will
   land here in Sprint 1).
4. **Phase isolation.** Paper API keys must NEVER be used to submit live
   orders. The OpenAPI `X-Phase` header enforces this server-side.

## Sprint 0 deliverables (this commit)

- [x] Plan v2.2 in `Doc/`
- [x] DDL: `market_quote_snapshot` hypertable
- [x] OpenAPI v0 contract
- [x] DOMAIN_GLOSSARY (KR market terms)
- [x] LLM prompt templates v0 + JSON Schemas
- [x] A4 Liquidity Surge backtest skeleton (Lean)

## Coming in Sprint 1

- [ ] Severity matrix + 4 runbooks
- [ ] A4 main.py implementation (volume-by-1030 calculation)
- [ ] Walk-forward harness + grid_search.yaml
- [ ] FastAPI scaffold implementing `api/openapi.yaml`
- [ ] Risk Engine package with the gate evaluator
- [ ] Earnings/dividend/halt calendar ETL

## Anti-goals (we will not chase)

- HFT, scalping, intraday day-trading frequency
- Generic "AI hedge fund" features unrelated to a tested alpha
- LLM as risk gate (it is an evaluator, not an arbiter)
- Cross-broker abstraction (KIS only in Phase 0–1)

## License

Proprietary. All rights reserved.
