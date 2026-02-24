"""
Agent_Trader — JSON Export
Reads from local SQLite DB and writes the four JSON files that
PythonAnywhere serves. The DB never leaves the Mac.
"""
import sys
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR, RESULTS_JSON, SNAPSHOT_JSON, METADATA_JSON, NEWS_JSON

log = logging.getLogger(__name__)


def _to_f(v) -> float | None:
    try:
        return round(float(v), 6) if v is not None else None
    except Exception:
        return None


def _to_i(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def run_export(conn: sqlite3.Connection, run_id: str, job_results: list[dict]) -> dict:
    """Write snapshot.json, results.json, metadata.json from DB."""
    started = datetime.now()
    import os
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── snapshot.json — all 50 stocks analytics ───────────────────────────────
    rows = conn.execute("""
        SELECT
            s.ticker, s.company_name, s.sector,
            a.last_close, a.return_1d, a.return_1w, a.return_1m,
            a.return_3m, a.return_6m, a.return_1y, a.return_3y, a.return_5y,
            a.cagr_3y, a.cagr_5y, a.beta_1y, a.beta_3y,
            a.volatility_1y, a.var_95_1d_pct, a.max_drawdown, a.sharpe_1y,
            a.alpha_vs_nifty, a.above_sma50, a.above_sma200,
            a.rsi_14, a.macd_signal, a.week52_high, a.week52_low,
            a.pct_from_high, a.pct_from_low, a.computed_date,
            v.pe_ratio, v.pb_ratio, v.roe, v.debt_equity, v.dividend_yield,
            v.market_cap,
            s.in_portfolio
        FROM stocks s
        LEFT JOIN analytics_snapshot a ON s.ticker = a.ticker
        LEFT JOIN valuation_metrics  v ON s.ticker = v.ticker
        WHERE s.is_active = 1
        ORDER BY a.return_1y DESC NULLS LAST
    """).fetchall()

    snapshot = []
    for r in rows:
        snapshot.append({
            "ticker":        r[0],
            "name":          r[1],
            "sector":        r[2],
            "price":         _to_f(r[3]),
            "ret_1d":        _to_f(r[4]),
            "ret_1w":        _to_f(r[5]),
            "ret_1m":        _to_f(r[6]),
            "ret_3m":        _to_f(r[7]),
            "ret_6m":        _to_f(r[8]),
            "ret_1y":        _to_f(r[9]),
            "ret_3y":        _to_f(r[10]),
            "ret_5y":        _to_f(r[11]),
            "cagr_3y":       _to_f(r[12]),
            "cagr_5y":       _to_f(r[13]),
            "beta_1y":       _to_f(r[14]),
            "beta_3y":       _to_f(r[15]),
            "vol_1y":        _to_f(r[16]),
            "var_95":        _to_f(r[17]),
            "max_dd":        _to_f(r[18]),
            "sharpe":        _to_f(r[19]),
            "alpha":         _to_f(r[20]),
            "above_sma50":   _to_i(r[21]),
            "above_sma200":  _to_i(r[22]),
            "rsi":           _to_f(r[23]),
            "macd":          r[24],
            "high52":        _to_f(r[25]),
            "low52":         _to_f(r[26]),
            "pct_from_high": _to_f(r[27]),
            "pct_from_low":  _to_f(r[28]),
            "computed_date": r[29],
            "pe":            _to_f(r[30]),
            "pb":            _to_f(r[31]),
            "roe":           _to_f(r[32]),
            "de_ratio":      _to_f(r[33]),
            "div_yield":     _to_f(r[34]),
            "mkt_cap":       _to_f(r[35]),
            "in_portfolio":  bool(r[36]),
        })

    with open(SNAPSHOT_JSON, "w") as f:
        json.dump({"generated_at": datetime.now().isoformat(),
                   "count": len(snapshot), "stocks": snapshot}, f, indent=2)
    print(f"snapshot.json: {len(snapshot)} stocks")

    # ── results.json — portfolio holdings with P&L ────────────────────────────
    holdings = conn.execute("""
        SELECT
            ph.ticker, ph.company_name, ph.quantity, ph.avg_cost,
            a.last_close, ph.invested_value,
            ph.quantity * COALESCE(a.last_close, ph.current_price) AS current_value,
            (ph.quantity * COALESCE(a.last_close, ph.current_price)) - ph.invested_value AS upnl,
            ((ph.quantity * COALESCE(a.last_close, ph.current_price)) - ph.invested_value)
              / ph.invested_value * 100 AS pnl_pct,
            a.return_1y, a.beta_1y, a.alpha_vs_nifty, a.rsi_14, a.macd_signal,
            s.sector
        FROM portfolio_holdings ph
        LEFT JOIN analytics_snapshot a ON ph.ticker = a.ticker
        LEFT JOIN stocks s ON ph.ticker = s.ticker
        ORDER BY current_value DESC NULLS LAST
    """).fetchall()

    results = []
    for h in holdings:
        results.append({
            "ticker":      h[0],
            "name":        h[1],
            "qty":         _to_f(h[2]),
            "avg_cost":    _to_f(h[3]),
            "cmp":         _to_f(h[4]),
            "invested":    _to_f(h[5]),
            "current":     _to_f(h[6]),
            "upnl":        _to_f(h[7]),
            "pnl_pct":     _to_f(h[8]),
            "ret_1y":      _to_f(h[9]),
            "beta":        _to_f(h[10]),
            "alpha":       _to_f(h[11]),
            "rsi":         _to_f(h[12]),
            "macd":        h[13],
            "sector":      h[14],
        })

    with open(RESULTS_JSON, "w") as f:
        json.dump({"generated_at": datetime.now().isoformat(),
                   "count": len(results), "holdings": results}, f, indent=2)
    print(f"results.json: {len(results)} holdings")

    # ── metadata.json — harvest health for dashboard staleness indicator ───────
    last_price = conn.execute(
        "SELECT MAX(created_at) FROM daily_prices"
    ).fetchone()[0]
    stocks_full = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM daily_prices WHERE data_quality='full'"
    ).fetchone()[0]
    analytics_count = conn.execute(
        "SELECT COUNT(*) FROM analytics_snapshot"
    ).fetchone()[0]
    news_count = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE date(published_at) >= date('now','-14 days')"
    ).fetchone()[0]

    harvest_jobs = []
    for jr in job_results:
        harvest_jobs.append({
            "job":            jr.get("job"),
            "status":         jr.get("status"),
            "stocks_updated": jr.get("stocks_updated"),
            "stocks_failed":  jr.get("stocks_failed"),
            "duration_secs":  jr.get("duration_secs"),
        })

    meta = {
        "generated_at":       datetime.now().isoformat(),
        "run_id":             run_id,
        "last_price_refresh": last_price,
        "stocks_with_prices": stocks_full,
        "analytics_count":    analytics_count,
        "news_items_14d":     news_count,
        "portfolio_holdings": len(results),
        "harvest_jobs":       harvest_jobs,
        "schema_version":     "1.0.0",
    }
    with open(METADATA_JSON, "w") as f:
        json.dump(meta, f, indent=2)

    duration = (datetime.now() - started).total_seconds()
    print(f"✔ export complete in {duration:.0f}s ({len(snapshot)} updated, 0 failed)")
    return {
        "job": "export", "run_id": run_id, "status": "success",
        "stocks_updated": len(snapshot), "stocks_failed": 0,
        "duration_secs": duration, "error_summary": None,
    }
