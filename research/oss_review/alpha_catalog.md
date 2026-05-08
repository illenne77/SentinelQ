# SentinelQ Alpha Catalog — OSS Review

**Generated**: 2025-05  
**Scope**: KR equity (KOSPI/KOSDAQ) daily, free-data-only  
**Sources reviewed**:
- `stefan-jansen/machine-learning-for-trading` Ch.4+24 (alpha factor library)
- `yli188/WorldQuant_alpha101_code` — `101Alpha_code_1.py` (Kakushadze 2016, Wilmott 84:72-80)
- `pst-group/pysystemtrade` — `systems/provided/rules/{ewmac,accel,carry,cs_mr,rel_mom,factors}.py`
- Fama-French (1993, 2015), Novy-Marx (2013) GP/A, Sloan (1996) accruals, Titman et al (2004) asset growth

---

## 1. Executive Summary

Five hypotheses have been killed (A4 liquidity surge, A3 vol compression, A2 sector rotation, A4+A7 regime-overlay, A4/A3 broadened universe) with 2024 as the binding failure year across all. The common thread: **short-horizon price/volume signals with no fundamental anchor**. This catalog pivots to (a) DART-fundamental-driven factors (value, quality, accruals, growth anomaly, PEAD), (b) less-exploited Alpha101 formulas suitable for daily KR data, (c) slow-trend following primitives (EWMAC, acceleration) that ignore intraday mechanics, and (d) macro-regime overlays using ECOS. The 2024 KR structural context is explicitly incorporated: Korea's Corporate Value-up Program (기업가치 제고 프로그램) makes low-PBR/high-ROE selection a government-endorsed narrative; the short-selling ban distorted price reversal dynamics; and USD/KRW volatility created macro regime breaks that blind technical systems. Fundamental-driven alphas are the **highest-priority next wave**.

---

## 2. Top 5 Priority Alphas

| Rank | ID | Name | Class | Data | Why Now |
|------|----|------|-------|------|---------|
| 1 | A-F01 | Book-to-Market Value | Value | KIS fundamental snapshot (PBR) | Corporate Value-up targets low-PBR; deep value spread historically wide in KR |
| 2 | A-F03 | Gross Profitability (GP/A) | Quality | DART quarterly (revenue, COGS, assets) | Orthogonal to value, survives 2024 because it's regime-neutral and fundamental |
| 3 | A-Q01 | ROE Momentum (QoQ EPS) | Quality/Earnings | DART quarterly EPS | Earnings revision effect; Korea Q disclosure lag creates exploitable window |
| 4 | A-F04 | Accruals (Operating) | Earnings Quality | DART quarterly (NI, CFO, TA) | Sloan anomaly under-arbitraged in KR due to low institutional quant coverage |
| 5 | A-FF01 | Fama-French 5-Factor Composite | Multi-Factor | DART + OHLCV | Portfolio-level diversification; each sub-factor tested orthogonally |

---

## 3. Full Alpha Catalog

---

### A-F01 Book-to-Market (B/M) Value

**Class**: Value

**Source**: Fama-French (1992, 1993) "The Cross-Section of Expected Stock Returns", JF; KIS fundamental snapshot provides BPS + close price directly.

**Formula**:
```python
# B/M = Book Value Per Share / Price
BM = BPS / close_price  # higher = cheaper = long

# Cross-sectional z-score within KOSPI200 universe
bm_zscore = (BM - BM.mean()) / BM.std()

# Signal: rank top quintile = 1, bottom = -1 (long-only: take top 20%)
```

**Data needed**:
- [x] KIS OHLCV — close price
- [x] KIS fundamental snapshot — BPS (주당순자산), 시총

**Expected effect size**: Fama-French (1993) HML premium ~4–5% pa US; KR literature (Kim & Kim 2003) reports ~3–6% pa KOSPI spread before transaction costs; post-2016 Corporate Value-up era not separately published.

**KR-specific concerns**: Chaebol holding company discount means book value is artificially inflated by cross-holdings (순환출자). Pure BPS from KIS may overstate true economic book value. Need to cross-check: large caps (Samsung, Hyundai, LG subsidiaries) may have misleading B/M. Filter on parent-only (별도) vs consolidated (연결) financials from DART — use **연결** BPS only.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: The government's Corporate Value-up Program explicitly targets low-PBR companies; long-low-PBR names are getting institutional attention as of 2024, but the *dispersion* of PBR across the market has widened, creating entry opportunities. Buying cheapest 20% by B/M post-Value-up announcement captures a policy-supported re-rating tail.

**Why it might fail**: Value traps are real in KR — many low-PBR stocks are family-controlled chaebols where minority shareholders are structurally diluted. Without a quality screen, raw B/M buys dead companies. Combine with ROE filter.

**Recommended priority for SentinelQ**: P1

---

### A-F02 Earnings Yield (E/P) with Size Filter

**Class**: Value

**Source**: `stefan-jansen/machine-learning-for-trading:04_alpha_factor_research/README.md` (Earnings Yield reference); KIS fundamental snapshot provides EPS + close.

**Formula**:
```python
# E/P = Trailing EPS / close_price
EP = EPS / close_price

# Apply mid-cap filter: market cap 500B–5T KRW to avoid mega-cap distortion
# z-score within filtered universe
ep_zscore = (EP - EP.mean()) / EP.std()

# Size-neutral: within-size-quintile rank
```

**Data needed**:
- [x] KIS OHLCV — close price
- [x] KIS fundamental snapshot — EPS, 시총 (for size filter)

**Expected effect size**: Global E/P spread ~2–4% pa after controlling size. KR evidence suggests slightly stronger given low analyst coverage in mid-cap universe.

**KR-specific concerns**: KIS EPS is trailing-twelve-month (TTM) from the snapshot, not forward. This creates a ~45–90 day stale period after fiscal year-end before new data. Better to use DART most-recent-quarter annualized EPS. EPS can be negative for KOSDAQ names — handle winsorization carefully.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: Mid-cap earnings yield has been suppressed by high rates crowding into fixed income; as rate expectations pivot, cheap-by-earnings names re-rate. The mid-cap segment specifically has underperformed large caps in 2023–2024.

**Why it might fail**: If 2024 structural shift is related to rising cost of capital, high-E/P stocks may be genuinely impaired (earnings at risk) rather than cheap. Needs quality overlay.

**Recommended priority for SentinelQ**: P2

---

### A-F03 Gross Profitability (GP/A)

**Class**: Quality

**Source**: Novy-Marx (2013) "The Other Side of Value: The Gross Profitability Premium", JFE 108(1):1–28. Referenced in `stefan-jansen/machine-learning-for-trading:04_alpha_factor_research/README.md` as quality factor.

**Formula**:
```python
# GP/A = (Revenue - COGS) / Total Assets
# From DART 재무제표: 매출액 - 매출원가 = 매출총이익; 총자산

gross_profit = revenue - cogs          # 매출총이익 from DART IS
gpa = gross_profit / total_assets      # 총자산 from DART BS

# Cross-sectional rank within industry-adjusted universe
gpa_industry_adj = gpa - gpa.groupby(industry).transform('mean')
signal = gpa_industry_adj.rank(pct=True)
```

**Data needed**:
- [ ] DART quarterly: 매출액 (revenue), 매출원가 (COGS), 총자산 (total assets)
- [ ] KIS OHLCV — for return calculation
- [ ] KIS fundamental snapshot — 시총 for universe filter

**Expected effect size**: Novy-Marx (2013): ~0.31% monthly IC; Sharpe ~0.6–0.8 long-short US. KR evidence in academic literature sparse but EM studies show ~2–4% pa spread.

**KR-specific concerns**: Many Korean conglomerates have low gross margins by design (internal transfer pricing between chaebol affiliates distorts COGS). Service companies in KOSDAQ have very different GP/A interpretation than manufacturers. **Industry-neutralize** this factor before ranking. DART 별도 vs 연결 matters — use 연결 consistently.

**Implementation complexity**: Medium (requires DART quarterly scraping + standardization)

**Why it might work in KR 2024+**: GP/A is mean-reverting slowly — it doesn't break on regime changes. High-GP/A companies tend to be capital-light and less sensitive to the rising capex environment that hurt Korean industrials in 2024. The factor is fundamentally orthogonal to the short-term price signals that failed.

**Why it might fail**: COGS classification is inconsistent across DART filings — some companies include D&A in COGS, others don't. Manual standardization or DART FS normalization needed. Without it, the factor is noisy.

**Recommended priority for SentinelQ**: P1

---

### A-F04 Accruals (Operating Accruals)

**Class**: Earnings Quality

**Source**: Sloan (1996) "Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?", TAR 71(3):289–315. Implemented in `stefan-jansen/machine-learning-for-trading:24_alpha_factor_library/02_common_alpha_factors.ipynb`.

**Formula**:
```python
# Operating Accruals = (NI - CFO) / Average Total Assets
# Low accruals = higher earnings quality = long signal

net_income = dart_is['당기순이익']            # DART 손익계산서
cfo = dart_cf['영업활동현금흐름']              # DART 현금흐름표
avg_assets = (dart_bs['총자산'] + dart_bs['총자산'].shift(1)) / 2

accruals = (net_income - cfo) / avg_assets

# Signal: RANK LOW ACCRUALS = high quality
signal = -accruals.rank(pct=True)           # negative = short high-accrual names
```

**Data needed**:
- [ ] DART quarterly: 당기순이익 (NI), 영업활동현금흐름 (CFO from cash flow stmt), 총자산 (TA)

**Expected effect size**: Sloan (1996): 10.4% annual return spread between low/high accrual quintiles US; Richardson et al (2005) confirm. KR: Lee & Jang (2017, KJAF) report ~4–8% pa spread; larger in KOSDAQ.

**KR-specific concerns**: KIS fundamental snapshot does NOT include CFO. This factor is **DART-only**. Quarterly CFO data in DART may have restatements — use point-in-time logic carefully (filing date, not period end date). KOSPI companies file within 45 days of quarter-end; KOSDAQ 90 days. This creates an asymmetric signal delay.

**Implementation complexity**: Medium

**Why it might work in KR 2024+**: Korean companies facing earnings pressure in 2024 (semiconductor cycle, China export slowdown) may have been supporting reported earnings via accruals. Shorting high-accrual names in this environment exploits the reversal when accruals unwind. Long-only version: filter for **negative** accruals (underpromised, overdelivered).

**Why it might fail**: DART filings are in Korean; parseable via OpenAPI but require careful mapping of FS line items. Small/micro-cap KOSDAQ names may omit cash flow statements entirely. Universe contamination is a real risk.

**Recommended priority for SentinelQ**: P1

---

### A-F05 Asset Growth Anomaly

**Class**: Quality / Value

**Source**: Cooper, Gulen & Schill (2008) "Asset Growth and the Cross-Section of Stock Returns", JF 63(4):1609–1651. Referenced in `stefan-jansen/machine-learning-for-trading:04_alpha_factor_research/README.md`.

**Formula**:
```python
# Asset growth rate = (TA_t - TA_{t-4}) / TA_{t-4}  (YoY quarterly)
asset_growth = (total_assets - total_assets.shift(4)) / total_assets.shift(4)

# Low growth firms outperform high growth firms
# Signal: SHORT high asset growth (overinvestment), LONG low/negative
signal = -asset_growth.rank(pct=True)
```

**Data needed**:
- [ ] DART quarterly: 총자산 (total assets, 4 quarters back)

**Expected effect size**: Cooper et al (2008): top-minus-bottom decile ~20% pa US; Lipson et al (2011) confirm globally. Typical IR ~0.3–0.5 in developed markets. EM evidence weaker (~6–10% pa).

**KR-specific concerns**: Korean chaebols go through aggressive investment cycles (반도체 슈퍼사이클 capex). Samsung SDI, LG Energy Solution, POSCO HX had massive asset growth 2020–2023 that **correctly** predicted underperformance in 2023–2024. This suggests the anomaly may be genuine in KR. However, government-directed infrastructure investment (K-chips Act capex) can distort.

**Implementation complexity**: Low (single DART line item, 4-quarter lag)

**Why it might work in KR 2024+**: Post-2024 capex digestion phase — overinvested names (EV battery, display) are underperforming; lean-asset names in pharma/software outperforming. Asset growth signal is directionally correct for this environment.

**Why it might fail**: The signal has a 1-year lookback so it is slow. It won't capture intra-cycle inflections. Combined with momentum, it creates whipsaws.

**Recommended priority for SentinelQ**: P2

---

### A-F06 Net Payout Yield (Dividend + Buyback)

**Class**: Value

**Source**: Boudoukh et al (2007) "Dividend Yield: The New Black"; ML4T Ch.4 references payout-based value factors. DART provides 배당금 (dividend per share) from annual disclosures; buyback from 자기주식취득 filings.

**Formula**:
```python
# Net Payout Yield = (Dividends + Net Buybacks) / Market Cap
dividends = dart_annual['배당금총액']        # DART 사업보고서
net_buybacks = dart_disc['자기주식취득'] - dart_disc['자기주식처분']  # disclosures

npy = (dividends + net_buybacks) / market_cap
signal = npy.rank(pct=True)
```

**Data needed**:
- [ ] DART annual: 배당금총액, 주당배당금
- [ ] DART corporate disclosures: 자기주식취득/처분 (major shareholder disclosures)
- [x] KIS fundamental snapshot — 시총 for market cap

**Expected effect size**: Boudoukh et al (2007): NPY has ~2× higher IC than dividend yield alone. In KR, dividends historically low (<1% average) but buyback activity has surged post-2023 (Corporate Value-up). Expected ~2–4% pa incremental alpha over raw dividend yield.

**KR-specific concerns**: KR companies pay dividends once/year (or twice); the ex-dividend date seasonality creates a predictable annual bump that may already be arbitraged. Buyback announcements are filed discretely — need DART disclosure parser for 자기주식취득결정 filing type. Chaebol subsidiaries buyback shares for holding company benefit, not minority shareholders.

**Implementation complexity**: Medium-High (requires DART disclosure parsing, multiple filing types)

**Why it might work in KR 2024+**: Corporate Value-up Program explicitly rewards companies doing buybacks + dividend increases; FSC tracking and public disclosure create a transparent signal. Companies announcing buybacks in this program have outperformed.

**Why it might fail**: Signal timing is tricky — buyback *completion* vs *announcement* vs *registration* lag. Announcement effect front-run within days.

**Recommended priority for SentinelQ**: P3

---

### A-Q01 ROE Momentum (Quarter-over-Quarter EPS Change)

**Class**: Quality / Earnings

**Source**: Haugen & Baker (1996) "Commonality in the Determinants of Expected Stock Returns"; Chan, Jegadeesh & Lakonishok (1996) "Momentum Strategies", JF 51(5):1681–1713. DART quarterly provides EPS quarterly series.

**Formula**:
```python
# QoQ EPS Change normalized by price
eps_q = dart_quarterly['EPS']                # quarterly EPS from DART
eps_change = (eps_q - eps_q.shift(4)) / abs(eps_q.shift(4))  # YoY

# Alternatively: standardized unexpected earnings (SUE)
# SUE = (EPS_q - EPS_{q-4}) / std(EPS changes over last 8 quarters)
sue = (eps_q - eps_q.shift(4)) / eps_q.rolling(8).std()

signal = sue.rank(pct=True)
```

**Data needed**:
- [ ] DART quarterly: 주당순이익 (EPS), at least 8 quarters history
- [x] KIS fundamental snapshot — EPS for validation

**Expected effect size**: Chan et al (1996): SUE-based strategy ~4% per quarter in first holding period US. KR studies (Yoon & Lee 2014, KBR) report ~3% per quarter for KOSPI within 60 days of earnings release.

**KR-specific concerns**: DART quarterly EPS filing dates vary. Companies with fiscal year-end != December have shifted disclosure windows. The "quiet period" in KR before earnings is not enforced — management guidance leaks. Large cap KOSPI names have analyst estimates (partially available via Naver); KOSDAQ does not.

**Implementation complexity**: Medium

**Why it might work in KR 2024+**: Semiconductor cycle inflection in late 2024 (SK Hynix, Samsung) means QoQ EPS surprises are directionally large and visible from DART — no consensus needed to compute a surprise signal vs prior year same quarter.

**Why it might fail**: Restatements in quarterly DART filings are common (특히 연결 재무제표 소급 조정). A naive lookback will contaminate signals. Need to use filing-date-sequenced data (DART's rcept_no + bgn_de fields) to avoid look-ahead.

**Recommended priority for SentinelQ**: P1

---

### A-Q02 Post-Earnings Announcement Drift (PEAD) via DART

**Class**: Earnings

**Source**: Ball & Brown (1968); Bernard & Thomas (1989) "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?", JAR. Implementation concept from ML4T Ch.4 `04_alpha_factor_research/README.md`.

**Formula**:
```python
# 1. On DART filing date (rcept_dt), compute SUE (as in A-Q01)
# 2. Enter long if SUE > +1.5σ on day T+1 (filing date + 1)
# 3. Hold for 20 trading days (roughly 1 month post-announcement)
# 4. Optionally: use Naver Finance consensus EPS for "true" surprise (FRAGILE)

# Without Naver:
sue_threshold = 1.5
signal = (sue > sue_threshold).astype(int)   # binary long trigger

# With Naver (fragile, ToS-gray):
consensus_eps = scrape_naver_consensus(ticker)
true_surprise = (eps_q - consensus_eps) / abs(consensus_eps)
```

**Data needed**:
- [ ] DART quarterly: EPS, filing date (rcept_dt)
- [x] KIS OHLCV — price return post-filing
- [ ] (Optional, fragile) Naver Finance consensus EPS scrape

**Expected effect size**: Bernard & Thomas (1989): PEAD drift ~2–4% over 60 days US. Without consensus, using naive SUE is a weaker signal: ~1–2% over 20 days. The drift is systematically documented; likely partially arbed in large KR caps but intact in KOSDAQ mid-cap.

**KR-specific concerns**: KR "보호예수" (lock-up) periods and institutional trading restrictions can delay drift realization. DART filing delays: KOSDAQ companies up to 90 days from quarter-end. The without-consensus version uses QoQ surprise which is noisy. **Mark this alpha as fragile if Naver scrape included.**

**Implementation complexity**: Medium (without Naver) / High + fragile (with Naver)

**Why it might work in KR 2024+**: Post-ban on short-selling (2023–2024), overreaction corrections happened slowly, which should lengthen the PEAD drift window. Less efficient price discovery = longer exploitable window.

**Why it might fail**: Earnings quality in 2024 is poor (see A-F04 accruals) — drift from accruals-inflated earnings reverses quickly. The combination of high-SUE + high-accruals is particularly dangerous.

**Recommended priority for SentinelQ**: P2

---

### A-M01 EWMAC Trend (Exponentially Weighted Moving Average Crossover)

**Class**: Momentum-Variant

**Source**: `pst-group/pysystemtrade:systems/provided/rules/ewmac.py:61-79` (Carver, "Systematic Trading", 2015). Carver's EWMAC(8,32) and EWMAC(16,64) combinations.

**Formula**:
```python
# From pysystemtrade ewmac.py:61-79:
fast_ewma = price.ewm(span=Lfast, min_periods=1).mean()
slow_ewma = price.ewm(span=Lslow, min_periods=1).mean()
raw_ewmac = fast_ewma - slow_ewma

# Vol-normalize (Carver's approach):
vol = robust_vol_calc(price.diff(), vol_days=35)
signal = raw_ewmac / vol

# For KR daily: use Lfast=8, Lslow=32 (medium-speed)
# + Lfast=16, Lslow=64 (slow) as diversifying variant
```

**Data needed**:
- [x] KIS OHLCV — close price, daily

**Expected effect size**: Carver (2015) reports diversified EWMAC across 4 speed variants achieving Sharpe ~0.4–0.6 on futures. For equities, decay faster; expect Sharpe ~0.2–0.4 gross on individual stocks. Better when applied to **index** (KOSPI200) as a regime filter rather than stock-level.

**KR-specific concerns**: KR daily data is T+2 settlement but price impact is same-day; this is fine for daily EWMAC. The 2024 year was characterized by a violent mean-reversion environment (range-bound KOSPI 2400–2800) which kills trend following. EWMAC must be applied with **regime conditioning** (see A-X01).

**Implementation complexity**: Low

**Why it might work in KR 2024+**: Applied as an **index-level overlay** (go long KOSPI200 constituents when KOSPI200 EWMAC positive, go to cash otherwise), not single-stock. This is a market-timing wrapper, not a cross-sectional signal.

**Why it might fail**: KR market was range-bound 2023–2024; any trend system will whipsaw. Standalone EWMAC on individual stocks without macro conditioning is likely dead (already embedded in A4+A7 attempt).

**Recommended priority for SentinelQ**: P2 (as index overlay only; reject as standalone stock signal)

---

### A-M02 Trend Acceleration (EWMAC Second Derivative)

**Class**: Momentum-Variant

**Source**: `pst-group/pysystemtrade:systems/provided/rules/accel.py:1-6` (Carver).

**Formula**:
```python
# From pysystemtrade accel.py:2-6:
def accel(price, vol, Lfast=4):
    Lslow = Lfast * 4
    ewmac_signal = ewmac(price, vol, Lfast, Lslow)
    acceleration = ewmac_signal - ewmac_signal.shift(Lfast)
    return acceleration

# For KR: Lfast=8 → measures change in trend over 8 days
# Positive acceleration = trend strengthening = add to long
```

**Data needed**:
- [x] KIS OHLCV — close price, daily

**Expected effect size**: Carver documents acceleration adds ~0.05–0.1 Sharpe when combined with EWMAC. Standalone acceleration has lower IC but decorrelated from base EWMAC signal. Useful as a secondary signal within a multi-signal blend.

**KR-specific concerns**: Very short-period acceleration (Lfast=4–8) on KR daily data creates high turnover and cost sensitivity. KR transaction cost (0.35% stamp duty + ~0.05% commission) means a signal with ~5–10 day holding period must have high per-trade alpha. This is borderline.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: Captures regime transitions (trend reversals) faster than base EWMAC. In a volatile range-bound market, catching the *early acceleration* of a new trend leg is valuable.

**Why it might fail**: False acceleration signals are frequent in sideways markets. Without a trend-regime gate, acceleration generates lots of noise trades.

**Recommended priority for SentinelQ**: P3 (blend with A-M01 only, not standalone)

---

### A-M03 Alpha001 — SignedPower Reversal

**Class**: Technical / Momentum-Variant

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:285-288` (Kakushadze 2016, Alpha#1).

**Formula**:
```python
# Alpha#1: rank(Ts_ArgMax(SignedPower(if_returns<0: stddev(returns,20) else close, 2), 5))
# Intuition: when returns are negative, substitute stddev for close (vol-adjusted momentum);
# take the argmax position in the last 5 days; rank cross-sectionally.

inner = close.copy()
inner[returns < 0] = stddev(returns, 20)
signal = rank(ts_argmax(inner ** 2, 5))
```

**Data needed**:
- [x] KIS OHLCV — close, returns (daily)

**Expected effect size**: Kakushadze (2016): Alpha101 series average holding period 0.6–6.4 days, average pair-wise correlation 15.9%. Alpha#1 specific Sharpe not disclosed; described as "real-life used in production."

**KR-specific concerns**: 5-day lookback is very short for KR daily data — transaction costs eat most of the gross alpha. The factor is designed for US intraday-ish holding periods. **Extend to 10-day argmax** for KR daily. The substitution of stddev during down markets makes this a mild volatility-adjusted momentum signal.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: The conditional logic (stddev vs price depending on return sign) gives the factor regime-awareness built in. It naturally adapts to volatile regimes by switching to volatility basis.

**Why it might fail**: Short holding period drives high turnover. KR stamp duty makes this expensive. The factor is least useful as a single signal; must be part of a composite.

**Recommended priority for SentinelQ**: P3

---

### A-M04 Alpha043 — Volume-Adjusted Reversal

**Class**: Technical / Momentum-Variant

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:528-531` (Kakushadze 2016, Alpha#43).

**Formula**:
```python
# Alpha#43: ts_rank(volume/adv20, 20) * ts_rank(-delta(close, 7), 8)
# Intuition: stock has recent high relative volume AND has fallen over 7 days → reversal
# Volume-gated short-term reversal

adv20 = close_volume.rolling(20).mean()
signal = (ts_rank(volume / adv20, 20) *
          ts_rank(-delta(close, 7), 8))
```

**Data needed**:
- [x] KIS OHLCV — close, volume, daily

**Expected effect size**: Not individually reported in Kakushadze (2016). Similar to Lehmann (1990) short-term reversal: ~0.5–1% per week gross; ~0 after costs in liquid US markets. May retain alpha in KR mid-cap where liquidity is lower.

**KR-specific concerns**: This is a **NOT** a direct variant of A4 (which was volume×range breakout). Alpha043 is a **reversal** signal (negative delta(close,7)) with volume confirmation. It is orthogonal to the A4 mechanism. However, it is still primarily a short-term mean-reversion signal — similar risk exposure to why A4 failed in 2024 trending environments. **Use with macro regime gate** to disable in trending regimes.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: Range-bound markets in 2024 actually favor reversal signals *within* the range. If the macro overlay (A-X01) correctly identifies range-bound regime, Alpha043 can be active. In trending regimes it is disabled.

**Why it might fail**: 2024 was specifically hard for all short-term price-based signals. Without clear identification of the range-bound regime, this fails.

**Recommended priority for SentinelQ**: P2 (only with macro regime gate A-X01)

---

### A-M05 Alpha053 — Buyer Pressure Change

**Class**: Technical

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:585-588` (Kakushadze 2016, Alpha#53).

**Formula**:
```python
# Alpha#53: -delta(((close-low)-(high-close))/(close-low), 9)
# Measures change in intrabar buyer pressure (Williams %R variant)
# = -change in (buying_pressure / bar_range) over 9 days

inner = (close - low).replace(0, 0.0001)
buyer_pressure = ((close - low) - (high - close)) / inner
signal = -delta(buyer_pressure, 9)
```

**Data needed**:
- [x] KIS OHLCV — open, high, low, close, daily

**Expected effect size**: Intrabar pressure signals have modest IC (~0.02–0.04 IC) but fast decay. Useful in composite. No direct published Sharpe for Alpha#53.

**KR-specific concerns**: For KR daily data, (close-low) is the buying pressure over the full day — this is clean and available. Unlike US high-frequency VWAP data, KR daily OHLCV does not need intraday. This is a legitimate daily OHLCV signal. The 9-day change in buyer pressure is a medium-frequency signal.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: Changes in buyer pressure at day level capture institutional accumulation/distribution patterns. In KR 2024, institutional buying (연기금, 보험사) patterns were the dominant price driver — this signal may partially track that.

**Why it might fail**: Does not distinguish between institutional and retail pressure. KOSDAQ mid-caps with large retail fraction create noisy buyer pressure readings.

**Recommended priority for SentinelQ**: P3

---

### A-M06 Alpha034 — Vol-Ratio Short-Term Reversal

**Class**: Technical / Momentum-Variant

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:483-487` (Kakushadze 2016, Alpha#34).

**Formula**:
```python
# Alpha#34: rank(2 - rank(stddev(returns,2)/stddev(returns,5)) - rank(delta(close,1)))
# Intuition: low short-vol relative to medium-vol + recent price reversal

inner = (stddev(returns, 2) / stddev(returns, 5)).replace([np.inf, -np.inf], 1).fillna(1)
signal = rank(2 - rank(inner) - rank(delta(close, 1)))
```

**Data needed**:
- [x] KIS OHLCV — close, returns, daily

**Expected effect size**: Alpha#34 combines vol-normalization with next-day reversal expectation. Combining these two negative factors (short-term mean reversion + low vol-ratio = low realized vol expansion risk) should produce a weak but stable signal. No individual IR reported.

**KR-specific concerns**: The 2-day vs 5-day vol ratio is a very short measure. In KR, weekend gaps and pre-holiday effects may introduce noise. This is a low-complexity signal that should be tested as part of a basket, not standalone.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: The vol-ratio component detects when realized vol has compressed — historically a precursor to mean-reversion opportunities in range-bound markets.

**Why it might fail**: Extremely short holding period (1-2 days) is cost-prohibitive in KR without very high per-trade alpha.

**Recommended priority for SentinelQ**: P3

---

### A-M07 Alpha019 — Long-Return Reversal with Signal

**Class**: Technical

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:385-388` (Kakushadze 2016, Alpha#19).

**Formula**:
```python
# Alpha#19: -sign((close - delay(close,7)) + delta(close,7)) * (1 + rank(1+sum(returns,250)))
# = A momentum-of-sentiment indicator:
#   If 7-day price direction is negative (double-counted), fade it
#   Weight by 1-year cumulative return rank (strong past winners get lighter fade weight)

signal = ((-1 * sign((close - delay(close, 7)) + delta(close, 7))) *
           (1 + rank(1 + ts_sum(returns, 250))))
```

**Data needed**:
- [x] KIS OHLCV — close, returns (250 trading days = ~1 year needed)

**Expected effect size**: The 250-day component creates a long-term quality tilt (high cumulative returns get less reversal signal). This is implicitly a momentum + mean-reversion hybrid. No direct IR reported in Kakushadze.

**KR-specific concerns**: 250-day returns in KR: available via 5-year OHLCV from KIS API. The sign() + delay(7) double-counting creates a smoothed direction estimate. This is distinct from A4 (no volume) and from A2 (no cross-sectional sector).

**Implementation complexity**: Low

**Why it might work in KR 2024+**: The 1-year cumulative return weighting means this signal rewards stocks that have had good LT performance and are experiencing a short dip — a classic "buy the dip on quality" pattern.

**Why it might fail**: The 7-day reversal component fails in trending environments (same failure mode as all reversal signals in 2024).

**Recommended priority for SentinelQ**: P3

---

### A-M08 Alpha052 — Low Breakout + Medium Return

**Class**: Technical

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:580-583` (Kakushadze 2016, Alpha#52).

**Formula**:
```python
# Alpha#52:
# ((-1 * delta(ts_min(low, 5), 5)) * rank((sum(returns,240)-sum(returns,20))/220)) * ts_rank(vol,5)
#
# Part 1: Low-price breakout from 5-day low (rising floor = bullish)
# Part 2: Returns from 20d to 240d ago (medium-term momentum, skip recent)
# Part 3: Volume rank over 5 days (confirmation)

low_break = -delta(ts_min(low, 5), 5)
med_return = rank((ts_sum(returns, 240) - ts_sum(returns, 20)) / 220)
vol_confirm = ts_rank(volume, 5)

signal = low_break * med_return * vol_confirm
```

**Data needed**:
- [x] KIS OHLCV — low, close (returns), volume (240+ days history)

**Expected effect size**: This composite signal combines 3 independent components. The medium-term return window (20–240 days) is a near-standard momentum skip-the-most-recent-month approach. Combined IC expected ~0.03–0.05. No direct Sharpe reported.

**KR-specific concerns**: This is **NOT** a variant of A4 (no range×volume Z-score; no breakout vs 20-day volume baseline). Part 1 measures whether the low price floor is rising (support building), not volume surge. The medium-return window is distinct from 12-1 momentum. Can be argued as novel enough to test.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: Three-component structure provides natural diversification. The medium-return component (20–240d) corresponds to a 1-month to 1-year window which covers the semiconductor cycle inflection and corporate value-up timeline.

**Why it might fail**: The volume confirmation component is short (5 days) and may reintroduce noise that undermined A4.

**Recommended priority for SentinelQ**: P2

---

### A-M09 Alpha101 — Intrabar Sentiment (Open-to-Close)

**Class**: Technical

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:822-824` (Kakushadze 2016, Alpha#101).

**Formula**:
```python
# Alpha#101: (close - open) / (high - low + 0.001)
# = Normalized intraday return / range
# = Where in the day's range did the stock close?
# +1 = closed at high (bullish), -1 = closed at low (bearish)

signal = (close - open) / (high - low + 0.001)
```

**Data needed**:
- [x] KIS OHLCV — open, high, low, close, daily

**Expected effect size**: This is essentially a normalized Williams %R / stochastic oscillator. As a standalone signal, IC is very low (~0.01–0.02). Value is as a building block in composites. Alpha#101 is listed as one of the simpler formulaic alphas.

**KR-specific concerns**: KR daily OHLCV from KIS includes open — confirmed available. The signal is clean and has no missing data issues. However, KR often has large gap opens (overnight news, foreign sell-off, US Nasdaq direction) that make open price "jump" — the intraday range conditional on the open level may be informative or spurious. **Most useful as a short-term regime indicator** (persistent positive = buyers in control, persistent negative = distribution).

**Implementation complexity**: Low (trivially computed)

**Why it might work in KR 2024+**: In 2024, KR stocks frequently gaped down at open due to overnight foreign selling and then recovered intraday (or vice versa). Alpha101 captures this intraday buying vs selling pattern, which reflects institutional flow on opens.

**Why it might fail**: Alone, this signal has minimal predictive power. It adds value only as an auxiliary signal combined with fundamental or momentum factors.

**Recommended priority for SentinelQ**: P3 (composite ingredient only)

---

### A-M10 Cross-Sectional Mean Reversion (cs_mr)

**Class**: Momentum-Variant / Mean Reversion

**Source**: `pst-group/pysystemtrade:systems/provided/rules/cs_mr.py:1-30` (Carver, "Advanced Futures Trading Strategies", 2023).

**Formula**:
```python
# From pysystemtrade cs_mr.py:1-30
# Cross-sectional mean reversion within asset class
def cross_sectional_mean_reversion(
    normalised_price_this_instrument,
    normalised_price_for_asset_class,
    horizon=250, ewma_span=None):

    if ewma_span is None:
        ewma_span = int(horizon / 4.0)

    outperformance = normalised_price_this - normalised_price_class_avg
    relative_return = outperformance.diff()
    outperformance_over_horizon = relative_return.rolling(horizon).mean()
    forecast = -outperformance_over_horizon.ewm(span=ewma_span).mean()
    return forecast

# Adaptation for KR equities:
# normalised_price = price / price.rolling(252).mean()
# normalised_price_for_asset_class = KOSPI200 normalized price (index series)
# horizon = 60 days (quarterly reversion for KR)
```

**Data needed**:
- [x] KIS OHLCV — close price (daily)
- [x] KIS index series — KOSPI200 index (for class average)

**Expected effect size**: Carver (2023) reports cs_mr Sharpe ~0.2–0.3 standalone for futures, higher when combined with EWMAC. For equities, expected weaker (< 0.2 Sharpe standalone). Decorrelated from time-series trend.

**KR-specific concerns**: This is fundamentally different from A2 (sector rotation). A2 used **cross-sector** momentum ranking (K-best sectors). cs_mr uses **relative-to-index** mean reversion within a single group. It buys stocks that have recently underperformed the index and sells outperformers — a classic contrarian factor. Does **not** pick between sectors.

**Implementation complexity**: Low-Medium

**Why it might work in KR 2024+**: In 2024, KOSPI was driven by a handful of large caps (Samsung, SK). Everything else mean-reverted around the index. A signal that fades single-stock extreme outperformance/underperformance relative to KOSPI200 captures this dynamic.

**Why it might fail**: If the index itself is trending (which it was NOT in 2024), this signal is wrong. It's also quite slow (horizon=250 default means annual reversion expectation). Need to tune to ~60 days for KR quarterly cycle.

**Recommended priority for SentinelQ**: P2

---

### A-X01 USD/KRW Macro Regime Overlay

**Class**: Macro-Overlay

**Source**: ECOS (한국은행) FX daily series. Research concept from `pst-group/pysystemtrade:systems/provided/rules/factors.py:1-20` (conditioned_factor_trading_rule — uses condition_demean_factor_value to sign-condition another signal).

**Formula**:
```python
# ECOS Series: USD/KRW daily (Series ID: 731Y001, Item: 0000001)
usdkrw = ecos.get_series('731Y001', '0000001', freq='D')

# Regime classification:
krw_mom = usdkrw.pct_change(20).rolling(5).mean()   # 20-day KRW momentum smoothed 5d

# KRW WEAKENING (USD/KRW rising) = risk-off = foreign selling pressure = bearish
# KRW STRENGTHENING = risk-on = foreign buying = bullish for KOSPI
regime = np.where(krw_mom < 0, +1, -1)              # +1 = KRW strong = long regime

# Apply as multiplicative overlay:
# final_signal = stock_signal * regime
# (When KRW weak, reduce/cut all long equity signals by 0.5 or 0.0)

# pysystemtrade conditioned_factor_trading_rule (factors.py:12-20):
# sign_condition = krw_mom.apply(np.sign)
# conditioned_signal = normalized_stock_signal * sign_condition
```

**Data needed**:
- [ ] ECOS: USD/KRW daily rate (Series 731Y001)
- [x] KIS OHLCV — for base equity signals

**Expected effect size**: Not directly measured in published literature for KR. Anecdotally, foreign investor flow (외국인 순매수) is highly correlated with KRW/USD direction. Conditioning on KRW reduces drawdown in risk-off episodes (e.g., KRW weakening from 1300 to 1400+ in 2024). Expected: reduce max drawdown by ~3–5% pa, minor IR improvement.

**KR-specific concerns**: USD/KRW is the most important macro variable for KOSPI, more so than rates, because of KOSPI's export-oriented composition (~60% revenue from USD-denominated exports). This is a **KR-specific** structural factor not applicable to other markets. The 2024 failure year had a sustained KRW weakness period (1300 → 1450) which correlates with KOSPI underperformance.

**Implementation complexity**: Low (ECOS API free, single series)

**Why it might work in KR 2024+**: The 2024 structural shift is *partly* FX-driven. USD/KRW was in a persistent weakening regime for much of 2024. Any strategy that was fully long KR equities in that environment was fighting macro headwinds. This overlay would have correctly reduced exposure during the 1380–1450 KRW weakness period.

**Why it might fail**: KRW macro regime has 1–4 week persistence but is not strongly predictive of individual stock returns. It reduces drawdown but not predictive alpha per se. Over-aggressive use kills return in KRW-strong periods.

**Recommended priority for SentinelQ**: P1 (as risk overlay for all strategies, not alpha generator)

---

### A-X02 Rate Regime Factor Rotation (CD 91일 / 기준금리)

**Class**: Macro-Overlay

**Source**: ECOS 한국은행 기준금리 series. Concept from Carver's carry factor (pst-group/pysystemtrade:systems/provided/rules/carry.py) applied to equity risk premium.

**Formula**:
```python
# ECOS: CD91 rate or BoK base rate
# Series candidates: 722Y001 (기준금리), 817Y002 (CD91일 수익률)
cd_rate = ecos.get_series('817Y002', freq='M')    # monthly CD rate

# Rate-regime state:
rate_change_3m = cd_rate.diff(3)    # 3-month change in rate
# Rising rates = value/quality favored over growth
# Falling rates = growth/momentum favored

# Factor tilt signal:
# When rate_change_3m > 0 (rising): overweight A-F01 (BM value), underweight A-M01 (trend)
# When rate_change_3m < 0 (falling): overweight A-M01 trend, underweight value
rate_regime = np.sign(rate_change_3m)   # +1 = rising rates

# Weight vector for multi-factor blend:
weights = {
    'value': 0.5 + 0.3 * rate_regime,    # more value in rising rates
    'momentum': 0.3 - 0.2 * rate_regime, # less momentum in rising rates
    'quality': 0.2                         # constant
}
```

**Data needed**:
- [ ] ECOS: CD91일 수익률 (Series 817Y002) or 기준금리 (722Y001)
- [x] All equity signals for weight scaling

**Expected effect size**: Asness et al (2013) "Value and Momentum Everywhere": value and momentum have negatively correlated returns, especially around rate regime changes. Routing capital correctly between them adds ~0.1–0.2 Sharpe to the combined portfolio.

**KR-specific concerns**: BoK rate cycle in 2024: paused at 3.5% since Jan 2024 (no change for most of year). This means the rate-regime signal was neutral for 2024 — no directional tilt. The signal is most valuable at **rate inflection points** (BoK cut expected in 2025). Currently a forward-looking setup rather than backtest-proven.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: BoK first cut signaled in 2024–2025. Rate-easing environment historically favors growth/momentum revival in KR. Being positioned for this inflection via A-X02 while holding value factors as base positions creates optionality.

**Why it might fail**: Rate regime signal is slow-moving and obvious to all participants — most of the reallocation is front-run. The signal is a coarse blunt instrument.

**Recommended priority for SentinelQ**: P3

---

### A-FF01 Fama-French 5-Factor Composite

**Class**: Multi-Factor

**Source**: Fama-French (2015) "A five-factor asset pricing model", JFE 116(1):1–22. Data from DART + KIS. Implementation architecture from ML4T Ch.4 composite factor construction.

**Formula**:
```python
# FF5 Factors for KR replication:
# MKT = KOSPI200 return - CD91 rate   (from KIS index + ECOS)
# SMB = small-minus-big (size split by 시총 median) (from KIS snapshot)
# HML = high-minus-low B/M (A-F01) (from KIS BPS + OHLCV)
# RMW = robust-minus-weak profitability (GP/A from A-F03) (from DART)
# CMA = conservative-minus-aggressive investment (inverse of A-F05 asset growth) (from DART)

# Monthly rebalance:
# Sort into 2×3 double-sorts: size × (BM, OP, Inv)
# Equal-weight within each cell; compute factor returns

# Long-only implementation:
# Score = w_HML*zscore(BM) + w_RMW*zscore(GPA) + w_CMA*zscore(-asset_growth)
# top_quintile = Score > 80th percentile → buy
score = (0.35 * bm_zscore + 0.35 * gpa_zscore + 0.30 * (-ag_zscore))
signal = score.rank(pct=True)
```

**Data needed**:
- [x] KIS OHLCV — close (for returns and market cap)
- [x] KIS fundamental snapshot — BPS, 시총
- [ ] DART quarterly: 매출총이익, 총자산, 매출원가 (for GP/A = RMW)
- [ ] DART quarterly: 총자산 2 periods (for CMA)
- [ ] ECOS: CD91 rate (risk-free for MKT factor)

**Expected effect size**: FF5 (Fama-French 2015): alpha of remaining anomalies reduced by ~45%. Implementing HML+RMW+CMA composite in KR: based on Kim (2019, Korean Journal of Financial Studies) FF5 applied to KOSPI, 3-factor Sharpe ~0.4–0.5 gross 2000–2018.

**KR-specific concerns**: KR FF5 replication requires careful chaebol handling. Samsung group companies have correlated loading on all 5 factors — diversification is illusory without group exposure caps. The 연결 vs 별도 distinction matters: 연결 inflates assets for holding companies. **Recommend 별도 financials for OP and CMA** to avoid double-counting.

**Implementation complexity**: High (requires full DART pipeline for 3 factor data series, size sorts, monthly rebalance)

**Why it might work in KR 2024+**: Multi-factor composites are more robust to any single regime. 2024 broke short-term technical signals; FF5 equivalent is structural and rebalances quarterly — it inherently avoids the 2024 short-horizon failure. The RMW (profitability) component is particularly well-suited post-2024 as profitability dispersion is wide.

**Why it might fail**: Complexity is high. Implementation errors in DART parsing (wrong line items, restatement timing) will inject noise. Monthly rebalance has meaningful turnover; transaction costs eat Sharpe in KR mid-cap universe.

**Recommended priority for SentinelQ**: P1 (but Phase 2 — requires DART pipeline first)

---

### A-M11 Alpha007 — Regime-Conditioned Close Reversal

**Class**: Technical / Momentum-Variant

**Source**: `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py:313-318` (Kakushadze 2016, Alpha#7).

**Formula**:
```python
# Alpha#7: if adv20 < volume:
#              -ts_rank(abs(delta(close,7)), 60) * sign(delta(close,7))
#          else: -1

adv20 = volume.rolling(20).mean()
alpha = -ts_rank(abs(delta(close, 7)), 60) * sign(delta(close, 7))
alpha[adv20 >= volume] = -1       # when volume below average: flat bearish

# Intuition: only take reversal signal when volume is above 20-day average
# Otherwise: constant -1 (slight bearish)
```

**Data needed**:
- [x] KIS OHLCV — close, volume, daily

**Expected effect size**: Alpha#7 is a volume-gated 7-day close reversal. The conditional structure creates regime sensitivity without requiring explicit macro data. IC expected ~0.02–0.04 conditional on volume gate being open. Not individually benchmarked.

**KR-specific concerns**: The volume gate is a very crude filter — it doesn't distinguish between information-based volume and noise-based volume. This is conceptually similar to A4 in that it conditions on volume, but the **direction** is opposite (A4 = momentum breakout; Alpha#7 = reversal). Distinct enough to test.

**Implementation complexity**: Low

**Why it might work in KR 2024+**: In 2024, high-volume events in KR (foreign sell-off days, KOSPI crash days) were mostly followed by mean reversion. Alpha#7 fades the move when volume is high — this is exactly right for the 2024 environment.

**Why it might fail**: Still fundamentally a short-term reversal signal. In early 2024 Samsung/SK downdraft, fading was wrong for weeks. The volume gate provides some protection but not immunity.

**Recommended priority for SentinelQ**: P2

---

## 4. Specifically Rejected Alphas

The following were considered and explicitly rejected for SentinelQ. Do not re-propose variants of these.

| Alpha | Reason for Rejection |
|-------|---------------------|
| **Cross-sectional sector momentum (A2 variants)** | Dead on 8 KR GICS sectors, walk-forward 2019–2024. Sector count too small; 2024 binding failure. |
| **Volume × Range Z-score breakout (A4 variants)** | Dead standalone and with regime overlay (A4+A7). 2024 W2 was catastrophic. No rescue from KOSDAQ broadening. |
| **Bollinger Band Squeeze (A3 variants)** | Dead. Vol compression followed by vol expansion failed systematically in 2024 KR. |
| **12-1 momentum (classic)** | Implicitly subsumed in multi-factor test. KR momentum documented to underperform globally; 2024 Samsung drag on KOSPI was a momentum-killer. Skip standalone test. |
| **Intraday-only signals** | Out of scope: no intraday/tick data available. |
| **Options-based signals** | Out of scope: no options flow data. |
| **News/NLP sentiment** | Out of scope: no paid newswire. Korean language NLP requires substantial infra investment. |
| **Investor flow (5Y)** | Only 30-day KIS flow available. Cannot back-test. Collect forward from now for 6+ months before using. |
| **Alpha#3 (corr(rank(open), rank(vol), 10))** | Extremely short-horizon, high-volume sensitivity; conceptually overlaps A4 volume-based failure. |
| **Alpha#6 (corr(open, vol, 10))** | Same — open/volume correlation; noise-level signal for daily KR data. |
| **Alpha#22 (delta(corr(high,vol,5),5))** | Volume-sensitivity again; degenerate signal in KR where daily volume is lumpy due to market hours. |
| **Alpha#40 (-rank(std(high,10)) * corr(high,vol,10))** | High-volume correlation; A4 territory. |
| **Carry-based equity signals (pysystemtrade carry.py)** | Designed for futures roll yield; no equivalent in KR equities without futures term structure. |
| **Relative momentum (pysystemtrade rel_mom.py)** | Measures outperformance vs asset class average over 250 days — extremely similar to A2 sector rotation signal. REJECTED. |
| **Pure price breakout (pysystemtrade breakout.py)** | `40 * ((price - roll_mean) / (roll_max - roll_min))` — same breakout mechanism as A4 (volume stripped, range-normalized). REJECTED. |
| **Alpha#48 (indneutralize required)** | Requires industry classification with sufficient depth; 8-sector KR universe too coarse. |
| **Alpha#56 (requires market cap time series)** | KIS snapshot 시총 is point-in-time daily; theoretically available but requires daily cap tracking. Lower priority than fundamentals. |
| **Alpha#58, #59 (IndNeutralize required)** | Require industry neutralization which is degenerate with 8 KR sectors. |
| **Alpha#100 (double IndNeutralize)** | Same issue; designed for US 11-sector GICS universe. |

---

## 5. Notes on Multi-Factor Portfolio Construction (KR FF5 Replication)

### What We'd Need from DART

To fully replicate Fama-French 5-factor for KR, the following DART API endpoints and line items are required:

| Factor | DART Data Required | API / Method |
|--------|-------------------|--------------|
| **HML (B/M)** | BPS (주당순자산) — available in KIS snapshot; or from DART BS: 자기자본 / 발행주식수 | KIS `inquire-price` fundamental fields; or DART `fnlttSinglAcntAll` (재무제표) |
| **RMW (Profitability = GP/A)** | 매출액 (revenue), 매출원가 (COGS), 총자산 | DART `fnlttSinglAcntAll`, IS + BS, 연결 분기보고서 |
| **CMA (Investment = Asset Growth)** | 총자산 at T and T-4 quarters | DART `fnlttSinglAcntAll`, BS, 연결 분기보고서 |
| **SMB (Size)** | 시가총액 daily | KIS `inquire-price` 시총 field |
| **MKT (Market)** | KOSPI200 index return, CD91 rate | KIS index API; ECOS Series 817Y002 |

### DART API Key Endpoints
- `https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json` — 단일회사 전체 재무제표 (FS all accounts)
  - Params: `corp_code`, `bsns_year`, `reprt_code` (11011=사업보고서, 11012=반기, 11013=Q1, 11014=Q3)
- `https://opendart.fss.or.kr/api/fnlttMultiAcnt.json` — 다중회사 재무제표
- Filing date: use `rcept_dt` (접수일) not `bsns_year` to avoid look-ahead bias

### Practical Construction Steps

1. **Universe**: KOSPI200 + KOSDAQ150, exclude financials (SIC banks/insurance — ROE metrics non-comparable)
2. **Rebalancing**: Monthly (calendar month-end, after filing deadline)
3. **Lookback**: Quarterly DART data, 4-quarter rolling for growth/accrual measures
4. **Chaebol Cap**: Max single-ticker weight 5%; single chaebol group exposure (합산) cap 15%
5. **Transaction Costs**: Model at 0.35% stamp duty + 0.05% commission = 0.4% one-way. Round-trip 0.8%. Monthly rebalance turnover ~15–20% → annual cost drag ~1.5–2% (significant but affordable with IR ≥ 0.5)
6. **Combining**: Equal-risk-weighted combination of HML + RMW + CMA via pysystemtrade-style `factor_trading_rule` (normalize by rolling vol, EWM smooth 90 days)

### ECOS Macro Series for Regime Conditioning

| Variable | ECOS Series | Period | Use |
|----------|------------|--------|-----|
| USD/KRW | 731Y001 item 0000001 | Daily | FX regime gate (A-X01) |
| CD 91일 수익률 | 817Y002 | Monthly | Rate regime (A-X02) |
| M2 (광의통화) | 101Y004 | Monthly | Liquidity cycle |
| 광공업생산지수 | 401Y015 | Monthly | Macro momentum |
| 수출증가율 | 311Y001 | Monthly | Trade cycle (KR-specific) |

### Combining Alphas: Recommended Priority Order

**Phase 0 (now)**: Test individual DART-based fundamentals (A-F01, A-F03, A-F04) as standalone monthly-rebalanced long-only quintile strategies. Compute IC, IC_IR, cumulative return per quintile.

**Phase 1**: Add macro overlay A-X01 as risk gate. Measure reduction in max drawdown.

**Phase 2**: Build full FF5 composite (A-FF01) once DART pipeline operational.

**Phase 3**: Add technical signals (A-M04, A-M08, A-M11) as intra-month position refinement on top of fundamental scores.

### 2024 KR Structural Notes

The 2024 failure year for SentinelQ technical signals coincides with several KR structural shifts:
1. **Corporate Value-up Program (기업가치 제고 프로그램)**: FSC initiative from Feb 2024 requiring disclosure of PBR improvement plans. This makes **B/M value** a policy-endorsed factor — unusually strong tailwind.
2. **Short-selling ban extension** (through mid-2024): Removed the arbitrage mechanism that normally keeps short-term reversals disciplined. All reversal signals become riskier.
3. **Samsung Electronics weight drag**: SEC (005930) dropped ~30% in 2024, dragging KOSPI200 and creating false negative signals for any KOSPI200-relative approach.
4. **USD/KRW sustained at 1350–1450**: Foreign investors were net sellers for most of 2024; any fully-long strategy was fighting this macro headwind.
5. **Semiconductor cycle trough → recovery**: SK Hynix outperformed, Samsung lagged. Cross-sectional dispersion was driven by chip cycle, not tradeable by any of our 5 dead alphas. **DART earnings data (SK Hynix ROE surge) was the exploitable signal we missed.**

---

## Appendix: Source Citations

| Code | File | Location |
|------|------|---------|
| Alpha001–Alpha101 implementations | `yli188/WorldQuant_alpha101_code:101Alpha_code_1.py` | Lines 284–824 |
| EWMAC formula | `pst-group/pysystemtrade:systems/provided/rules/ewmac.py` | Lines 61–79 |
| Acceleration formula | `pst-group/pysystemtrade:systems/provided/rules/accel.py` | Lines 2–6 |
| Cross-sectional MR | `pst-group/pysystemtrade:systems/provided/rules/cs_mr.py` | Lines 1–30 |
| Conditioned factor rule | `pst-group/pysystemtrade:systems/provided/rules/factors.py` | Lines 1–20 |
| Alpha factor categories | `stefan-jansen/machine-learning-for-trading:04_alpha_factor_research/README.md` | All |
| Alpha factor library | `stefan-jansen/machine-learning-for-trading:24_alpha_factor_library/README.md` | All |
| Kakushadze (2016) | arXiv:1601.00991v3, Wilmott Magazine 2016(84):72-80 | Paper PDF in repo |
| Fama-French (2015) | JFE 116(1):1–22 | — |
| Novy-Marx (2013) | JFE 108(1):1–28 | — |
| Sloan (1996) | TAR 71(3):289–315 | — |
| Cooper et al (2008) | JF 63(4):1609–1651 | — |
