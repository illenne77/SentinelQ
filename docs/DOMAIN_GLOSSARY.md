# DOMAIN_GLOSSARY — Korean Equity Market

**Audience**: SentinelQ LLM agents (Analyst / Screener / Risk Reviewer) and developers.
**Purpose**: Single source of truth for KR-market terms used in prompts, code, and decision artifacts. **All LLM prompts cite this file by section anchor** — never paraphrase definitions inline (drift risk).

**Scope**: KOSPI / KOSDAQ / KONEX cash equities. Out of scope (per plan v2.2 §1A.2): options, futures, FX, crypto, OTC, short selling.

**Update policy**: PR with ADR. Definitions are versioned by file commit hash; prompts pin the hash they reference.

---

## 1. Markets and Indices

| Term | Definition | LLM-relevant note |
|---|---|---|
| **KOSPI** | Korea Composite Stock Price Index. Main board, mostly large-cap. Trading hours 09:00–15:30 KST. | Higher liquidity; tighter spreads; foreign participation high. |
| **KOSDAQ** | Secondary board, growth/SME-oriented. Same hours. | Higher volatility, wider spreads, more retail-driven. |
| **KONEX** | Tier for early-stage SMEs. | Out of universe for SentinelQ Phase 0–1. |
| **KOSPI 200 / KOSDAQ 150** | Headline indices. Membership matters: ETF flows, futures basis. | A2 Sector Rotation and A7 Regime use index returns as inputs. |

## 2. Trading Sessions

| Term | KST window | Definition |
|---|---|---|
| **장 시작 동시호가** | 08:30–09:00 | Opening call auction. Single-price match at 09:00. No continuous trading. |
| **정규장** | 09:00–15:20 | Continuous trading. |
| **장 마감 동시호가** | 15:20–15:30 | Closing call auction. Single-price match at 15:30. |
| **시간외 단일가** | 16:00–18:00 | After-hours single-price auctions every 10 min, ±10% band. |
| **시간외 종가** | 15:40–16:00, 18:00–20:00 (parts) | Closing-price-only off-hours session. |

> **Important for backtests**: bar data labeled "open" is the 09:00 auction print, NOT the first continuous bar. A4 entries scheduled at 10:31 are the first reasonable continuous-session bar after a 10:30 observation cut-off.

## 3. Price Bands and Halts

### 3.1 상하한가 (Daily Price Limit)
- KOSPI / KOSDAQ: **±30%** from previous close (`stck_sdpr`).
- Symbols: `stck_mxpr` (upper limit), `stck_llam` (lower limit).
- Hitting a limit does **not** halt trading; it caps the price. Liquidity often vanishes near the limit.

### 3.2 VI — Volatility Interruption (변동성완화장치)
Two flavors. Both pause the symbol for **2 minutes** then resume via single-price auction.

| Type | Trigger | KIS field |
|---|---|---|
| **동적 VI (Dynamic)** | Single tick deviation ±2–3% (price-band-dependent) from immediate prior price. | `vi_cls_code` |
| **정적 VI (Static)** | ±10% from reference price (open auction or after a static-VI). | `vi_cls_code` |
| **시간외 VI** | Same logic during off-hours single-price sessions. | `ovtm_vi_cls_code` |

**Risk Engine behavior** (per `risk_limits.yaml` `instrument_gates.pause_if_vi_active=true`): when VI active, scanner skips the name; existing positions are NOT auto-liquidated.

### 3.3 거래정지 (Trading Halt)
Multi-hour or multi-day suspension. Causes: pending material disclosure, regulatory inquiry, audit qualification, operational issues. KIS field: `temp_stop_yn`. **Hard block** in Risk Engine.

### 3.4 단기과열 (Short-term Overheating)
Designation when price/volume meet over-heating criteria for 3+ days. Triggers a **3-day single-price auction regime** (10-min auctions instead of continuous). Treat as effective liquidity halt — Phase 0 avoids these names.

## 4. Issue Designations (Risk Gates)

| Designation | Korean | KIS field | What it means |
|---|---|---|---|
| **Managed Issue** | 관리종목 | `mang_issu_cls_code` | KRX flagged for delisting risk (capital impairment, audit issues, going concern). **Hard block.** |
| **Investment Caution** | 투자주의 | `mrkt_warn_cls_code='01'`, `invt_caful_yn` | Mild warning; abnormal trading. **Hard block** in SentinelQ Phase 0. |
| **Investment Warning** | 투자경고 | `mrkt_warn_cls_code='02'` | Moderate warning. Settlement converts to T+2 → cash. **Hard block.** |
| **Investment Risk** | 투자위험 | `mrkt_warn_cls_code='03'` | Severe. Trading may halt 1 day. **Hard block.** |
| **Settlement Trade** | 정리매매 | `sltr_yn` | 7-day single-price-auction wind-down before delisting. **Hard block.** |
| **Unfaithful Disclosure** | 불성실공시 | (separate filing) | Penalty for late/incorrect disclosure. Track via news; not a hard block by itself but combined with others is. |

> Risk Engine reads these on every snapshot and short-circuits before any sizing or LLM call. Source of truth: `risk_limits.yaml > instrument_gates`.

## 5. Order Mechanics

| Term | Definition | Notes |
|---|---|---|
| **호가단위 (Tick size)** | Minimum price increment. Step function of price (e.g. 1원 < 2,000원, 5원 ≤ 5,000원, 10원 ≤ 20,000원, 50원 ≤ 50,000원, 100원 ≤ 200,000원, 500원 ≤ 500,000원, 1000원 above). KIS field: `aspr_unit`. | Limit prices that don't snap to tick are rejected by KIS. |
| **거래단위 (Lot size)** | Almost always **1 share** for KR equities. KIS field: `hts_deal_qty_unit_val`. | Some ETN/ETFs differ; check field. |
| **시장가 (Market order)** | Executed at best available within current liquidity. | Map to OpenAPI `order_type=MARKET`. |
| **지정가 (Limit order)** | Standard limit. | `order_type=LIMIT`. |
| **IOC / FOK** | Immediate-or-cancel / fill-or-kill. | KIS supports; rare in cash equities Phase 0. |
| **호가잔량** | Bid/ask depth at top-of-book. | Not in `inquire-price`; use orderbook endpoint when needed. |

## 6. Settlement and Costs

| Term | Definition |
|---|---|
| **결제일 (T+2)** | Cash settlement two business days after trade. Affects available cash for re-entry. |
| **위탁수수료** | Broker commission. KIS retail typical: ~0.015% (varies by promo). |
| **증권거래세** | Sell-side tax. Currently **0.20%** on KOSPI/KOSDAQ sells (subject to change; verify before Phase 0.5). |
| **농어촌특별세** | 0.15% on KOSPI sells (already part of the 0.20% bundle on KOSPI). |
| **양도소득세** | Capital gains tax. Generally 0% for retail KR equities below holding/value thresholds; verify case-by-case. |

> Backtest cost model (plan §7.4.1): apply 0.015% per leg + 0.20% on sells + 8 bps slippage as the default. Sensitivity at 0/4/8/15 bps required.

## 7. Corporate Actions

| Term | Korean | Effect on price |
|---|---|---|
| **Stock split** | 액면분할 | Mechanical price/share adjustment. Lean's factor file handles. |
| **Bonus issue** | 무상증자 | New shares free; price ex-bonus. Adjust. |
| **Rights issue** | 유상증자 | Dilutive; ex-rights price drop. Watch for **권리락**. |
| **Ex-dividend** | 배당락 | Price drops by dividend amount on ex-date. Watch for **배당락**. |
| **Spin-off / Merger** | 분할 / 합병 | Symbol may change; halt + re-list. |

> A1 PEAD and A5 News Reversal must distinguish **earnings drift** from **mechanical ex-date drops**. Use the corporate-actions calendar (T-1 fetch).

## 8. Foreign and Program Flow (KR-specific A6 inputs)

| Term | KIS field | Meaning |
|---|---|---|
| **외국인 보유율** | `hts_frgn_ehrt` | Foreign ownership % of float. |
| **외국인 보유수량** | `frgn_hldn_qty` | Absolute shares. |
| **외국인 순매수** | `frgn_ntby_qty` | Today's net buy by foreigners (intraday updates lagged ~30min). |
| **프로그램 순매수** | `pgtr_ntby_qty` | Program trading net (basket / arbitrage / index ETF flows). Often the leading indicator vs cash flow. |
| **외국인 한도** | (per-symbol regulatory cap) | Defense / utilities have explicit caps (e.g. KEPCO). When near cap, foreigner-driven moves stall. |

## 9. Short Selling (Reference Only — OOS for SentinelQ)

| Term | Note |
|---|---|
| **공매도** | Short selling. SentinelQ is LONG ONLY (plan §1A.2). |
| **공매도 가능 여부** | KIS `ssts_yn`. Informational. |
| **차입공매도 잔량** | `whol_loan_rmnd_rate`. High loan balance can foreshadow squeezes; A6/A7 may consume as feature, but no short positions are taken. |

## 10. Common Acronyms

| Acronym | Expansion |
|---|---|
| **KRX** | Korea Exchange |
| **FSC / FSS** | 금융위원회 / 금융감독원 — regulators |
| **DART** | Disclosure database (dart.fss.or.kr). Source for filings and earnings. |
| **HTS / MTS** | Home / Mobile Trading System. KIS eFriend Plus (HTS), KIS Mobile (MTS). |
| **VI** | Volatility Interruption (see §3.2). |
| **PEAD** | Post-Earnings Announcement Drift (alpha A1). |
| **MDD** | Maximum Drawdown. |
| **OOS** | Out-of-Sample. |
| **ADV** | Average Daily Volume (or Value). |
| **ELW** | Equity Linked Warrant. KIS field `elw_pblc_yn` indicates issuability. Out of universe. |
| **ETN / ETF** | In universe if listed and meeting size floor. |

## 11. Time Zones and Calendars

- **Operational TZ**: KST (UTC+9). All UI and prompts use KST.
- **Storage**: UTC. Convert at the boundary.
- **Holidays**: KRX calendar — Lunar New Year, Chuseok, election days, etc. Markets fully closed. Source: KRX official calendar (refresh annually, T-1 cache).
- **Half-days**: rare in KR; treat as full close for safety.

## 12. Phrases LLM Must Recognize but Not Confuse

| Phrase | What it really means |
|---|---|
| "차트가 좋다" | Price action looks favorable. **Not** an actionable signal — needs structured features. |
| "재료가 있다" | A catalyst (news/event) exists. Always look up the actual disclosure. |
| "상따" | Trying to ride a stock to its upper limit. Speculative; **not aligned** with SentinelQ alphas. |
| "반등" | Bounce/rebound. May map to A5 News Reversal but only with confirming volume + flow. |
| "테마주" | Theme stock. Often violates Investment Warning gates; treat with extra skepticism. |

---

## Appendix A — Field Lookup Table (KIS → Glossary)

| KIS field | Glossary section |
|---|---|
| `vi_cls_code`, `ovtm_vi_cls_code` | §3.2 |
| `mang_issu_cls_code` | §4 |
| `mrkt_warn_cls_code`, `invt_caful_yn` | §4 |
| `sltr_yn` | §4 |
| `temp_stop_yn` | §3.3 |
| `stck_mxpr`, `stck_llam` | §3.1 |
| `aspr_unit`, `hts_deal_qty_unit_val` | §5 |
| `prdy_vrss_vol_rate` | (alpha A4 input — see plan §7.6) |
| `hts_frgn_ehrt`, `frgn_ntby_qty`, `pgtr_ntby_qty` | §8 |

## Appendix B — Sources

- KRX Rulebook (kosdaq/kospi listing rules)
- KIS Open API specification (FHKST01010100)
- DART Electronic Disclosure System
- SentinelQ plan v2.2 §1A.2 (OOS), §7.4.1 (sim realism), §7.6 (alpha catalog)
