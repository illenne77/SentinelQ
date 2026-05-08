# SentinelQ

KR equity AI trading agent — design + research + reference implementation.

**Status**: Phase 0 alpha-discovery (data infrastructure complete; ports + paper-trade harness in place; awaiting graduated alpha).
**Phase**: paper (Phase 0). See `Doc/investment_agent_plan_v2.2.docx` §8.0.

## Phase 0 status (2026-05-09)

**Alpha tally**: 8/8 standalone alphas tested → **0 graduated**.

| Alpha | Hypothesis | Result | ADR |
|---|---|---|---|
| A2 | Sector rotation | FAIL | ADR-0006 |
| A3 | (early reject) | FAIL | — |
| A4 | Liquidity surge | FAIL | ADR-0001/2/3 |
| A6 | Foreign/inst. flow bias | BLOCKED (data, daemon now collecting) | — |
| A7 | (combined w/ A4) | FAIL | ADR-0003 |
| A-F01 | Book-to-Market value | FAIL | ADR-0007 |
| A-F03 | Gross-Profit/Assets quality | FAIL | ADR-0008 |
| A-FF01 | Value+Quality rank-sum | FAIL | ADR-0009 |

**Honesty check (ADR-0010)**: Re-priced against KOSPI200 (KODEX 200 ETF
proxy) — all variants FAIL more decisively. Discovery: 2023-26 KR
market is mega-cap concentrated; W3 KOSPI200 CAGR = +165% vs our
EW universe at +76%. **EW basket construction cannot beat the index in
this regime regardless of factor signal.** Future PREREGs must include
weighting (EW vs cap-weighted) as a frozen variant axis.

**Next bet**: A6 (institutional/foreign flow). Daily forward-collect
daemon scheduled for 18:00 KST. ETA to 6-month accumulation: ~5 months.

## Repository layout

```
api/        OpenAPI 3.1 contract for the backend (scanner, decide, order, risk, ops)
docs/       ADRs + pre-registrations + glossary + runbooks
prompts/    LLM prompt templates (analyst, screener, risk_reviewer) + JSON Schemas
research/   Alpha research workspaces (a2_, a4_, a6_, a_f01_, a_f03_, a_ff01_, honesty_check)
scripts/    DART/KIS backfills, paper_trade.py harness, A6 forward-collect daemon
sentinelq/  Phase 1+ modules
  portfolio/  Portfolio bookkeeper (Fill-driven, NAV/peak/MDD)
  risk/       Pre-trade risk engine (deterministic, broker-agnostic)
  research/   Walk-forward harness
  ports/      Hexagonal protocols: DataPort, ClockPort, BrokerPort
  adapters/   KisData, KisBroker (paper-mode default), Sim/RealClock
sql/ddl/    PostgreSQL/TimescaleDB schema (market_quote_snapshot, ...)
tests/      pytest suites (run: py -m pytest tests/ -v)
Doc/        Plan documents (Korean). v2.2 is current.
```

## Hard rules

1. **LONG only, KR cash equities only.** No options/futures/FX/crypto/OTC/short.
   See plan v2.2 §1A.2 (Out of Scope).
2. **No secrets in git.** `.gitignore` blocks `*appkey*`, `*credentials*`,
   `secrets/`, `.env`. Use Git Credential Manager / Vault / `.env.local`.
3. **Risk Engine is deterministic.** LLM never sets risk limits. Source of
   truth: `config/risk_limits.yaml`.
4. **Phase isolation.** Paper API keys must NEVER be used to submit live
   orders. `KisBroker(phase="live", ...)` requires
   `SENTINELQ_LIVE_ALLOW=1` AND `confirm_live=True` AND a graduated alpha
   with risk sign-off.
5. **Pre-registration is mandatory.** Every alpha test is pre-registered
   under `docs/preregistration/` BEFORE running the backtest, with
   frozen variants and KPI gates. No re-tuning post-hoc.

## Phase 2 building blocks (this checkpoint)

- `sentinelq/ports/` — `DataPort`, `ClockPort`, `BrokerPort` Protocol
  interfaces. Strategies depend on these, NOT on concrete adapters.
- `sentinelq/adapters/kis_data.py` — `KisData` reads cached parquet bars,
  optional live REST fallback for `latest_close`.
- `sentinelq/adapters/clock.py` — `SimulatedClock` (backtest, advances
  via `advance_to`) and `RealClock` (KST wall clock).
- `sentinelq/adapters/kis_broker.py` — `KisBroker` paper-mode default
  with idempotent client_order_id, slippage + commission + tax model.
  Live mode locked behind double-gate.
- `scripts/paper_trade.py` — minimal end-to-end harness wiring
  ports + Portfolio. Pluggable strategy callable.
- `tests/test_ports_smoke.py` — 9 tests, integration smoke + safety.

## Anti-goals (we will not chase)

- HFT, scalping, intraday day-trading frequency
- Generic "AI hedge fund" features unrelated to a tested alpha
- LLM as risk gate (it is an evaluator, not an arbiter)
- Cross-broker abstraction (KIS only in Phase 0–1)

## License

Proprietary. All rights reserved.
