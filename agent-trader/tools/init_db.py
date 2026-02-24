"""
Agent_Trader — Database Initialisation
Creates all 17 tables across 9 domains and seeds default data.
Safe to run multiple times (CREATE TABLE IF NOT EXISTS everywhere).
"""
import sys
import os
import sqlite3
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, DATA_DIR, NIFTY50_STOCKS, INDEX_TICKERS, RSS_FEEDS

SCHEMA = """
-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 1: Universe
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stocks (
    stock_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL UNIQUE,
    company_name    TEXT NOT NULL,
    sector          TEXT,
    yf_ticker       TEXT NOT NULL,          -- Yahoo Finance symbol e.g. HDFCBANK.NS
    in_nifty50      INTEGER DEFAULT 1,
    in_portfolio    INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    added_date      TEXT DEFAULT (date('now')),
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS indices (
    index_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    index_code      TEXT NOT NULL UNIQUE,
    index_name      TEXT NOT NULL,
    yf_ticker       TEXT NOT NULL,
    is_benchmark    INTEGER DEFAULT 0        -- 1 for Nifty50 (used in alpha calc)
);

CREATE TABLE IF NOT EXISTS index_constituents (
    constituent_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    index_code      TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    weight_pct      REAL,
    effective_date  TEXT DEFAULT (date('now')),
    UNIQUE(index_code, ticker, effective_date)
);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 2: Prices
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS daily_prices (
    price_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    price_date      TEXT NOT NULL,
    open_price      REAL,
    high_price      REAL,
    low_price       REAL,
    close_price     REAL NOT NULL,
    adj_close       REAL,
    volume          INTEGER,
    data_quality    TEXT DEFAULT 'full',    -- full | partial_morphed | data_unavailable
    source          TEXT DEFAULT 'yfinance',
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, price_date)
);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON daily_prices(ticker, price_date DESC);

CREATE TABLE IF NOT EXISTS index_prices (
    index_price_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    index_code      TEXT NOT NULL,
    price_date      TEXT NOT NULL,
    open_price      REAL,
    high_price      REAL,
    low_price       REAL,
    close_price     REAL NOT NULL,
    volume          INTEGER,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(index_code, price_date)
);
CREATE INDEX IF NOT EXISTS idx_idx_prices_code_date ON index_prices(index_code, price_date DESC);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 3: Fundamentals
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS financial_statements (
    statement_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    period_type     TEXT NOT NULL,          -- annual | quarterly
    period_end      TEXT NOT NULL,
    revenue         REAL,
    gross_profit    REAL,
    ebitda          REAL,
    net_income      REAL,
    eps             REAL,
    total_assets    REAL,
    total_debt      REAL,
    total_equity    REAL,
    cash_flow_ops   REAL,
    free_cash_flow  REAL,
    source          TEXT DEFAULT 'yfinance',
    fetched_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, period_type, period_end)
);

CREATE TABLE IF NOT EXISTS valuation_metrics (
    valuation_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    metric_date     TEXT NOT NULL,
    pe_ratio        REAL,
    pb_ratio        REAL,
    ps_ratio        REAL,
    ev_ebitda       REAL,
    roe             REAL,
    roce            REAL,
    debt_equity     REAL,
    dividend_yield  REAL,
    market_cap      REAL,
    enterprise_val  REAL,
    fetched_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, metric_date)
);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 4: Shareholding
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS shareholding_pattern (
    holding_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    promoter_pct    REAL,
    fii_pct         REAL,
    dii_pct         REAL,
    public_pct      REAL,
    insider_pct     REAL,
    institution_pct REAL,
    source          TEXT DEFAULT 'yfinance',
    fetched_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, period_end)
);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 5: Analytics (computed on Mac, pre-baked)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS analytics_snapshot (
    analytics_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL UNIQUE,
    computed_date   TEXT NOT NULL,
    -- Returns
    return_1d       REAL,
    return_1w       REAL,
    return_1m       REAL,
    return_3m       REAL,
    return_6m       REAL,
    return_1y       REAL,
    return_3y       REAL,
    return_5y       REAL,
    cagr_3y         REAL,
    cagr_5y         REAL,
    -- Risk
    beta_1y         REAL,
    beta_3y         REAL,
    volatility_1y   REAL,
    volatility_3y   REAL,
    var_95_1d_pct   REAL,           -- 95% 1-day VaR as percentage
    max_drawdown    REAL,
    sharpe_1y       REAL,
    -- Alpha
    alpha_vs_nifty  REAL,           -- return_1y minus nifty_return_1y
    -- Trend signals
    above_sma50     INTEGER,        -- 1/0
    above_sma200    INTEGER,        -- 1/0
    rsi_14          REAL,
    macd_signal     TEXT,           -- bullish | bearish | neutral
    -- Price levels
    last_close      REAL,
    week52_high     REAL,
    week52_low      REAL,
    pct_from_high   REAL,
    pct_from_low    REAL,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 6: News
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS rss_feeds (
    feed_id         TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    url             TEXT NOT NULL,
    priority        INTEGER DEFAULT 2,      -- 1=exchange 2=news 3=macro
    category        TEXT DEFAULT 'NEWS',
    is_active       INTEGER DEFAULT 1,
    error_count     INTEGER DEFAULT 0,      -- auto-disable after 5
    last_success    TEXT,
    last_checked    TEXT
);

CREATE TABLE IF NOT EXISTS news_items (
    news_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    url             TEXT,
    published_at    TEXT,
    fetched_at      TEXT DEFAULT (datetime('now')),
    tickers_mentioned TEXT,                 -- JSON array e.g. ["HDFCBANK","INFY"]
    news_category   TEXT DEFAULT 'GENERAL', -- EXCHANGE | REGULATOR | MACRO | GENERAL
    sentiment       TEXT DEFAULT 'neutral', -- positive | negative | neutral (Sprint 3)
    UNIQUE(url)
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_feed ON news_items(feed_id, published_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 7: Backtest / Calibration
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS calibration (
    cal_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_date TEXT NOT NULL,
    sc1_weight      REAL DEFAULT 1.0,
    sc2_weight      REAL DEFAULT 0.8,
    sc3_weight      REAL DEFAULT 0.6,
    sc4_weight      REAL DEFAULT 0.9,
    sc5_weight      REAL DEFAULT 0.7,
    sc6_meta_adj    REAL DEFAULT 1.0,
    hit_rate_7d     REAL,
    hit_rate_30d    REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    signal_date     TEXT NOT NULL,
    signal_score    REAL,
    signal_action   TEXT,                   -- BUY | HOLD | REDUCE | AVOID
    outcome_7d      REAL,                   -- actual return after 7 days
    outcome_30d     REAL,                   -- actual return after 30 days
    was_correct_7d  INTEGER,                -- 1/0
    was_correct_30d INTEGER,
    recorded_at     TEXT DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 8: Audit
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS harvest_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    job_name        TEXT NOT NULL,          -- prices | news | fundamentals | shareholding | analytics | export
    status          TEXT NOT NULL,          -- success | partial | failed
    stocks_updated  INTEGER DEFAULT 0,
    stocks_failed   INTEGER DEFAULT 0,
    duration_secs   REAL,
    error_summary   TEXT,
    run_date        TEXT DEFAULT (date('now')),
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_log (
    dq_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    check_date      TEXT NOT NULL,
    check_type      TEXT NOT NULL,          -- ohlc_integrity | missing_days | stale | analytics_range
    result          TEXT NOT NULL,          -- pass | fail | warning
    detail          TEXT,
    logged_at       TEXT DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════
-- DOMAIN 9: Portfolio
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    holding_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL UNIQUE,
    company_name    TEXT,
    quantity        REAL NOT NULL,
    avg_cost        REAL NOT NULL,
    current_price   REAL,
    invested_value  REAL,
    current_value   REAL,
    unrealised_pnl  REAL,
    pnl_pct         REAL,
    last_updated    TEXT DEFAULT (datetime('now'))
);
"""

SEED_STOCKS = """
INSERT OR IGNORE INTO stocks (ticker, company_name, sector, yf_ticker, in_nifty50)
VALUES (?, ?, ?, ?, 1)
"""

SEED_INDICES = """
INSERT OR IGNORE INTO indices (index_code, index_name, yf_ticker, is_benchmark)
VALUES (?, ?, ?, ?)
"""

SEED_FEEDS = """
INSERT OR IGNORE INTO rss_feeds (feed_id, display_name, url, priority, category)
VALUES (?, ?, ?, ?, ?)
"""

SEED_CALIBRATION = """
INSERT OR IGNORE INTO calibration (calibration_date, notes)
VALUES (date('now'), 'Initial calibration — all weights at design defaults')
"""


def init_db(db_path: str = DB_PATH) -> None:
    """Initialise the database — create tables and seed default data."""
    print("Agent_Trader — Database Init")
    print(f"Target: {db_path}")

    # Ensure data directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        # Create all tables
        conn.executescript(SCHEMA)
        conn.commit()
        print("Schema created / verified")

        # Seed stocks
        from config import NIFTY50_STOCKS
        for ticker, name, sector, yf in NIFTY50_STOCKS:
            conn.execute(SEED_STOCKS, (ticker, name, sector, yf))
        conn.commit()

        # Seed indices
        from config import INDEX_TICKERS
        for code, name, yf in INDEX_TICKERS:
            is_bm = 1 if code == "NIFTY50" else 0
            conn.execute(SEED_INDICES, (code, name, yf, is_bm))
        conn.commit()

        # Seed RSS feeds
        from config import RSS_FEEDS
        for fid, name, url, priority, cat in RSS_FEEDS:
            conn.execute(SEED_FEEDS, (fid, name, url, priority, cat))
        conn.commit()

        # Seed calibration
        conn.execute(SEED_CALIBRATION)
        conn.commit()

        # Report
        n_stocks  = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        n_indices = conn.execute("SELECT COUNT(*) FROM indices").fetchone()[0]
        n_feeds   = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
        db_size   = os.path.getsize(db_path) / 1024
        print(f"Seeded {n_stocks} stocks, {n_indices} indices, {n_feeds} RSS feeds")
        print(f"Database ready — {db_size:.1f} KB")

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
