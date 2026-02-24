"""
Agent_Trader — Fundamentals Harvest
Fetches financial statements and valuation metrics from yfinance.
Runs weekly on Monday (or force-flag). Mac only.
"""
import sys
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime

import yfinance as yf
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

log = logging.getLogger(__name__)

# Suppress yfinance's internal WARNING logs for Timestamp serialisation noise
logging.getLogger("yfinance").setLevel(logging.ERROR)


def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return None if pd.isna(v) else v
    except Exception:
        return None


def _fetch_statements(tk: yf.Ticker, ticker: str, conn: sqlite3.Connection) -> int:
    """Fetch annual and quarterly income/balance sheet/cashflow. Returns rows inserted."""
    rows = 0
    for period_type, inc_attr, bs_attr, cf_attr in [
        ("annual",    "financials",            "balance_sheet",            "cashflow"),
        ("quarterly", "quarterly_financials",  "quarterly_balance_sheet",  "quarterly_cashflow"),
    ]:
        try:
            inc = getattr(tk, inc_attr, None)
            bs  = getattr(tk, bs_attr, None)
            cf  = getattr(tk, cf_attr, None)

            if inc is None or inc.empty:
                continue

            for col in inc.columns:
                try:
                    period_end = pd.Timestamp(col).strftime("%Y-%m-%d")
                except Exception:
                    log.info(f"{ticker} {period_type}: skipping non-date column {col}")
                    continue

                def g(df, *keys):
                    if df is None or df.empty:
                        return None
                    for k in keys:
                        if k in df.index:
                            return _safe_float(df.loc[k, col])
                    return None

                conn.execute("""
                    INSERT OR REPLACE INTO financial_statements
                    (ticker, period_type, period_end, revenue, gross_profit,
                     ebitda, net_income, eps, total_assets, total_debt,
                     total_equity, cash_flow_ops, free_cash_flow)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    ticker, period_type, period_end,
                    g(inc,  "Total Revenue", "Revenue"),
                    g(inc,  "Gross Profit"),
                    g(inc,  "EBITDA", "Normalized EBITDA"),
                    g(inc,  "Net Income", "Net Income Common Stockholders"),
                    g(inc,  "Diluted EPS", "Basic EPS"),
                    g(bs,   "Total Assets"),
                    g(bs,   "Total Debt", "Long Term Debt"),
                    g(bs,   "Total Equity Gross Minority Interest", "Stockholders Equity"),
                    g(cf,   "Operating Cash Flow", "Cash From Operating Activities"),
                    g(cf,   "Free Cash Flow"),
                ))
                rows += 1
        except Exception as e:
            log.warning(f"{ticker} {period_type} statements: {e}")

    return rows


def _fetch_valuation(tk: yf.Ticker, ticker: str, conn: sqlite3.Connection) -> bool:
    """Fetch key valuation ratios from yfinance info. Returns True if inserted."""
    try:
        info = tk.info or {}
        today = datetime.now().strftime("%Y-%m-%d")

        conn.execute("""
            INSERT OR REPLACE INTO valuation_metrics
            (ticker, metric_date, pe_ratio, pb_ratio, ps_ratio, ev_ebitda,
             roe, debt_equity, dividend_yield, market_cap, enterprise_val)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ticker, today,
            _safe_float(info.get("trailingPE") or info.get("forwardPE")),
            _safe_float(info.get("priceToBook")),
            _safe_float(info.get("priceToSalesTrailing12Months")),
            _safe_float(info.get("enterpriseToEbitda")),
            _safe_float(info.get("returnOnEquity")),
            _safe_float(info.get("debtToEquity")),
            _safe_float(info.get("dividendYield")),
            _safe_float(info.get("marketCap")),
            _safe_float(info.get("enterpriseValue")),
        ))
        return True
    except Exception as e:
        log.warning(f"{ticker} valuation: {e}")
        return False


def run_fundamentals(conn: sqlite3.Connection, run_id: str) -> dict:
    """Main entry — fetch fundamentals for all active stocks."""
    started = datetime.now()
    updated = 0
    failed  = 0
    errors  = []

    stocks = conn.execute(
        "SELECT ticker, yf_ticker FROM stocks WHERE is_active = 1"
    ).fetchall()

    for i, (ticker, yf_ticker) in enumerate(stocks, 1):
        try:
            tk = yf.Ticker(yf_ticker)
            r1 = _fetch_statements(tk, ticker, conn)
            r2 = _fetch_valuation(tk, ticker, conn)
            conn.commit()
            updated += 1
            print(f"  [{i}/{len(stocks)}] {ticker} — {r1} statement rows, valuation={'ok' if r2 else 'partial'}")
        except Exception as e:
            log.error(f"{ticker} fundamentals failed: {e}")
            failed += 1
            errors.append(ticker)
            print(f"  [{i}/{len(stocks)}] {ticker} FAILED: {e}")
        time.sleep(0.3)

    duration = (datetime.now() - started).total_seconds()
    status   = "success" if failed == 0 else ("partial" if updated > 0 else "failed")
    print(f"✔ fundamentals complete in {duration:.0f}s ({updated} updated, {failed} failed)")
    return {
        "job": "fundamentals", "run_id": run_id, "status": status,
        "stocks_updated": updated, "stocks_failed": failed,
        "duration_secs": duration, "error_summary": ", ".join(errors[:10]) or None,
    }
