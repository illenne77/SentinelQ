-- ============================================================================
-- SentinelQ — DDL 001: market_quote_snapshot
-- ----------------------------------------------------------------------------
-- Source : KIS Open API — /uapi/domestic-stock/v1/quotations/inquire-price
-- TR ID  : FHKST01010100  (현재가 시세)
-- Engine : PostgreSQL 15+ with TimescaleDB extension
-- Phase  : 0 (paper) — schema is identical for 0.5 and 1; only data sources differ
-- ----------------------------------------------------------------------------
-- Design notes
--   * Single hypertable. No premature normalization. Risk Engine reads one row.
--   * Prices : NUMERIC(18,4) — never FLOAT/DOUBLE for monetary values.
--   * Volumes: NUMERIC(20,0) — KRX cumulative volume can exceed INT4 range.
--   * Ratios : NUMERIC(9,4)  — percentages with 4 decimals (e.g. 49.4023).
--   * raw_jsonb preserves the full KIS payload for re-parse on schema evolution.
--   * Risk gate columns are indexed because Risk Engine short-circuits on them.
--   * Column names mirror KIS field names where reasonable to keep ETL trivial;
--     where ambiguous, a clearer name is used and the KIS name is in COMMENT.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------------------
-- 1. Reference table for tickers (small; not a hypertable)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS instrument (
    ticker              VARCHAR(12)  PRIMARY KEY,           -- e.g. '005930'
    name_kr             VARCHAR(64)  NOT NULL,
    market              VARCHAR(16)  NOT NULL,              -- KOSPI / KOSDAQ / KONEX
    market_index_kr     VARCHAR(64),                        -- rprs_mrkt_kor_name
    sector_kr           VARCHAR(64),                        -- bstp_kor_isnm
    listed_shares       NUMERIC(20,0),                      -- lstn_stcn
    face_value          NUMERIC(18,4),                      -- stck_fcam
    is_etf              BOOLEAN      NOT NULL DEFAULT FALSE,
    is_elw_issuable     BOOLEAN,                            -- elw_pblc_yn
    is_credit_eligible  BOOLEAN,                            -- crdt_able_yn
    is_short_eligible   BOOLEAN,                            -- ssts_yn
    delisted_at         DATE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 2. market_quote_snapshot — point-in-time price + risk + valuation snapshot
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_quote_snapshot (
    -- ---- identity --------------------------------------------------------
    observed_at         TIMESTAMPTZ  NOT NULL,              -- ingestion clock (UTC)
    ticker              VARCHAR(12)  NOT NULL REFERENCES instrument(ticker),

    -- ---- core price (won) -----------------------------------------------
    price               NUMERIC(18,4) NOT NULL,             -- stck_prpr        현재가
    open_price          NUMERIC(18,4),                      -- stck_oprc        시가
    high_price          NUMERIC(18,4),                      -- stck_hgpr        고가
    low_price           NUMERIC(18,4),                      -- stck_lwpr        저가
    upper_limit_price   NUMERIC(18,4),                      -- stck_mxpr        상한가
    lower_limit_price   NUMERIC(18,4),                      -- stck_llam        하한가
    base_price          NUMERIC(18,4),                      -- stck_sdpr        기준가(전일종가)
    vwap                NUMERIC(18,4),                      -- wghn_avrg_stck_prc 가중평균
    tick_size           NUMERIC(10,4),                      -- aspr_unit        호가단위
    lot_size            INTEGER,                            -- hts_deal_qty_unit_val
    substitute_price    NUMERIC(18,4),                      -- stck_sspr        대용가

    -- ---- price change ---------------------------------------------------
    prev_close_diff     NUMERIC(18,4),                      -- prdy_vrss        전일대비
    prev_close_sign     SMALLINT,                           -- prdy_vrss_sign   1상한/2상승/3보합/4하한/5하락
    prev_close_rate     NUMERIC(9,4),                       -- prdy_ctrt        전일대비율(%)
    price_restrict_width NUMERIC(18,4),                     -- rstc_wdth_prc

    -- ---- volume / turnover ----------------------------------------------
    cum_volume          NUMERIC(20,0),                      -- acml_vol         누적거래량
    cum_trade_value     NUMERIC(24,0),                      -- acml_tr_pbmn     누적거래대금(원)
    volume_rate_vs_prev NUMERIC(9,4),                       -- prdy_vrss_vol_rate (전일동시간대비%)
    turnover_ratio      NUMERIC(9,4),                       -- vol_tnrt

    -- ---- valuation ------------------------------------------------------
    market_cap_eokwon   NUMERIC(20,0),                      -- hts_avls         시가총액(억원)
    per                 NUMERIC(12,4),                      -- per
    pbr                 NUMERIC(12,4),                      -- pbr
    eps                 NUMERIC(18,4),                      -- eps
    bps                 NUMERIC(18,4),                      -- bps
    fiscal_close_month  SMALLINT,                           -- stac_month
    capital_eokwon      NUMERIC(20,0),                      -- cpfn (자본금, 억원)

    -- ---- pivot points ---------------------------------------------------
    pivot_point         NUMERIC(18,4),                      -- pvt_pont_val
    pivot_r1            NUMERIC(18,4),                      -- pvt_frst_dmrs_prc
    pivot_r2            NUMERIC(18,4),                      -- pvt_scnd_dmrs_prc
    pivot_s1            NUMERIC(18,4),                      -- pvt_frst_dmsp_prc
    pivot_s2            NUMERIC(18,4),                      -- pvt_scnd_dmsp_prc
    demarker_resistance NUMERIC(18,4),                      -- dmrs_val
    demarker_support    NUMERIC(18,4),                      -- dmsp_val

    -- ---- range stats (derived by KIS) -----------------------------------
    hi_250d             NUMERIC(18,4),                      -- d250_hgpr
    hi_250d_date        DATE,                               -- d250_hgpr_date
    hi_250d_rate        NUMERIC(9,4),                       -- d250_hgpr_vrss_prpr_rate
    lo_250d             NUMERIC(18,4),                      -- d250_lwpr
    lo_250d_date        DATE,
    lo_250d_rate        NUMERIC(9,4),
    hi_52w              NUMERIC(18,4),                      -- w52_hgpr
    hi_52w_date         DATE,
    lo_52w              NUMERIC(18,4),
    lo_52w_date         DATE,
    hi_ytd              NUMERIC(18,4),                      -- stck_dryy_hgpr
    hi_ytd_date         DATE,
    lo_ytd              NUMERIC(18,4),
    lo_ytd_date         DATE,

    -- ---- flow (KR-specific, A6 alpha input) -----------------------------
    foreign_holding_qty   NUMERIC(20,0),                    -- frgn_hldn_qty
    foreign_holding_pct   NUMERIC(9,4),                     -- hts_frgn_ehrt
    foreign_net_buy_qty   NUMERIC(20,0),                    -- frgn_ntby_qty
    program_net_buy_qty   NUMERIC(20,0),                    -- pgtr_ntby_qty

    -- ---- short selling --------------------------------------------------
    short_recent_qty      NUMERIC(20,0),                    -- last_ssts_cntg_qty
    loan_balance_rate     NUMERIC(9,4),                     -- whol_loan_rmnd_rate
    short_overhang_flag   BOOLEAN,                          -- short_over_yn

    -- ---- RISK GATES (Risk Engine reads these first) ---------------------
    is_managed_issue        BOOLEAN NOT NULL,               -- mang_issu_cls_code != 'N'
    is_investment_warning   BOOLEAN NOT NULL,               -- invt_caful_yn = 'Y'
    market_warning_code     VARCHAR(4),                     -- mrkt_warn_cls_code  '00'=정상
    vi_active               BOOLEAN NOT NULL,               -- vi_cls_code != 'N'
    vi_active_overtime      BOOLEAN NOT NULL,               -- ovtm_vi_cls_code
    is_trading_halted       BOOLEAN NOT NULL,               -- temp_stop_yn
    open_range_continuous   BOOLEAN,                        -- oprc_rang_cont_yn
    close_range_continuous  BOOLEAN,                        -- clpr_rang_cont_yn
    is_settlement_trade     BOOLEAN,                        -- sltr_yn
    issue_status_code       VARCHAR(4),                     -- iscd_stat_cls_code

    -- ---- raw payload (audit + replay) -----------------------------------
    raw_jsonb           JSONB        NOT NULL,
    source_tr_id        VARCHAR(16)  NOT NULL DEFAULT 'FHKST01010100',
    api_env             VARCHAR(8)   NOT NULL,              -- 'paper' | 'live'

    -- ---- bookkeeping ----------------------------------------------------
    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Hypertable on observed_at (1-day chunks; tune later)
SELECT create_hypertable(
    'market_quote_snapshot',
    'observed_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Composite primary key (hypertable PK must include partitioning column)
ALTER TABLE market_quote_snapshot
    ADD CONSTRAINT pk_market_quote_snapshot PRIMARY KEY (ticker, observed_at);

-- Risk gate index — Risk Engine queries by ticker filtered on gates
CREATE INDEX IF NOT EXISTS idx_mqs_risk_gates
    ON market_quote_snapshot (ticker, observed_at DESC)
    WHERE is_managed_issue = TRUE
       OR is_investment_warning = TRUE
       OR vi_active = TRUE
       OR is_trading_halted = TRUE;

-- Liquidity surge index — A4 alpha scans for high volume_rate_vs_prev
CREATE INDEX IF NOT EXISTS idx_mqs_liquidity_surge
    ON market_quote_snapshot (observed_at DESC, volume_rate_vs_prev DESC)
    WHERE volume_rate_vs_prev IS NOT NULL;

-- Foreign flow index — A6 alpha
CREATE INDEX IF NOT EXISTS idx_mqs_foreign_flow
    ON market_quote_snapshot (ticker, observed_at DESC)
    INCLUDE (foreign_net_buy_qty, program_net_buy_qty, foreign_holding_pct);

-- ----------------------------------------------------------------------------
-- 3. Compression policy (Timescale) — keep last 30d hot, compress older
-- ----------------------------------------------------------------------------
ALTER TABLE market_quote_snapshot SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby   = 'observed_at DESC'
);

SELECT add_compression_policy('market_quote_snapshot', INTERVAL '30 days',
                              if_not_exists => TRUE);

-- ----------------------------------------------------------------------------
-- 4. Retention policy — keep 5 years of snapshots in primary
--    (Phase-0 OK; revisit before Phase 1 if storage grows)
-- ----------------------------------------------------------------------------
SELECT add_retention_policy('market_quote_snapshot', INTERVAL '5 years',
                            if_not_exists => TRUE);

-- ----------------------------------------------------------------------------
-- 5. Comments — schema is the document
-- ----------------------------------------------------------------------------
COMMENT ON TABLE  market_quote_snapshot IS
    'Point-in-time snapshot from KIS inquire-price (FHKST01010100). One row per (ticker, observed_at). Risk Engine and alpha scanners read directly from this table.';
COMMENT ON COLUMN market_quote_snapshot.api_env IS
    'paper = openapivts:29443, live = openapi:9443. Snapshots from different envs MUST NEVER be mixed in backtest input.';
COMMENT ON COLUMN market_quote_snapshot.volume_rate_vs_prev IS
    'KIS prdy_vrss_vol_rate. Same time-of-day vs previous trading day. Primary input for A4 Liquidity Surge alpha.';
COMMENT ON COLUMN market_quote_snapshot.is_managed_issue IS
    'Derived from mang_issu_cls_code != ''N''. Risk Engine MUST block entry on TRUE (risk_limits.gates.block_if_managed).';
COMMENT ON COLUMN market_quote_snapshot.vi_active IS
    'Volatility Interruption active. When TRUE, scanner pauses entries (risk_limits.gates.pause_if_vi_active).';

-- ----------------------------------------------------------------------------
-- 6. View — latest snapshot per ticker (used by Risk Engine for gate check)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_market_quote_latest AS
SELECT DISTINCT ON (ticker) *
FROM market_quote_snapshot
ORDER BY ticker, observed_at DESC;

-- ============================================================================
-- End of 001_market_quote_snapshot.sql
-- ============================================================================
