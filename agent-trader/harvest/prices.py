"""
Agent_Trader — Price Harvest
Fetches daily OHLCV from yfinance for all stocks and indices.
Runs on Mac only — no network restrictions apply here.
"""
import sys
import sqlite3
import time
import logging
from pathlib import Path
from datetime import datetime, date, timedelta

import yfinance as yf
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, PRICE_PERIOD, PRICE_INTERVAL, NIFTY50_STOCKS, INDEX_TICKERS

log = logging.getLogger(__name__)


def _get_last_price_date(conn: sqlite3.Connection, ticker: str, table: str = "daily_prices") -> str | None:
    """Return the most recent price_date in the DB for this ticker, or None."""
    col = "ticker" if table == "daily_prices" else "index_code"
    row = conn.execute(
        f"SELECT MAX(price_date) FROM {table} WHERE {col} = ?", (ticker,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _fetch_yf(yf_ticker: str, period: str, interval: str) -> pd.DataFrame | None:
    """
    Download OHLCV from yfinance, return clean DataFrame or None.
    Fallback chain:
      1. Try requested period (e.g. '5y')
      2. If empty → retry with 'max' (catches recently-listed stocks like ZOMATO)
      3. If NSE ticker (.NS) still fails → retry with BSE equivalent (.BO)
    """
    def _clean(df) -> pd.DataFrame | None:
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize(None)
        return df

    # Attempt 1 — requested period
    try:
        tk = yf.Ticker(yf_ticker)
        df = _clean(tk.history(period=period, interval=interval, auto_adjust=True))
        if df is not None:
            return df
    except Exception as e:
        log.warning(f"yfinance fetch failed for {yf_ticker} (period={period}): {e}")

    # Attempt 2 — fallback to 'max' (handles recently-listed stocks)
    if period != "max":
        try:
            log.info(f"{yf_ticker}: retrying with period='max'")
            tk = yf.Ticker(yf_ticker)
            df = _clean(tk.history(period="max", interval=interval, auto_adjust=True))
            if df is not None:
                log.info(f"{yf_ticker}: period='max' returned {len(df)} rows")
                return df
        except Exception as e:
            log.warning(f"yfinance fetch failed for {yf_ticker} (period=max): {e}")

    # Attempt 3 — BSE fallback for NSE tickers that return 404
    if yf_ticker.endswith(".NS"):
        bse_ticker = yf_ticker.replace(".NS", ".BO")
        try:
            log.info(f"{yf_ticker}: retrying with BSE fallback {bse_ticker}")
            tk = yf.Ticker(bse_ticker)
            df = _clean(tk.history(period="max", interval=interval, auto_adjust=True))
            if df is not None:
                log.info(f"{yf_ticker}: BSE fallback {bse_ticker} returned {len(df)} rows")
                return df
        except Exception as e:
            log.warning(f"BSE fallback failed for {bse_ticker}: {e}")

    return None


def _incremental_period(last_date_str: str) -> str:
    """Convert a last-seen date string to a yfinance period string for incremental fetch."""
    if not last_date_str:
        return "5y"
    last = date.fromisoformat(last_date_str)
    gap  = (date.today() - last).days
    if gap <= 7:
        return "5d"
    if gap <= 30:
        return "1mo"
    if gap <= 90:
        return "3mo"
    if gap <= 365:
        return "1y"
    return "5y"


def run_prices(conn: sqlite3.Connection, run_id: str) -> dict:
    """Main entry point — fetch prices for all 50 stocks + 11 indices."""
    started = datetime.now()
    stocks_updated = 0
    stocks_failed  = 0
    errors = []

    stocks = conn.execute(
        "SELECT ticker, yf_ticker FROM stocks WHERE is_active = 1"
    ).fetchall()

    print(f"Fetching prices for {len(stocks)} stocks…")

    for i, (ticker, yf_ticker) in enumerate(stocks, 1):
        last_date = _get_last_price_date(conn, ticker, "daily_prices")
        period    = _incremental_period(last_date)
        df        = _fetch_yf(yf_ticker, period, PRICE_INTERVAL)

        if df is None or df.empty:
            log.warning(f"Failed to get ticker '{yf_ticker}' — no data returned")
            stocks_failed += 1
            errors.append(ticker)
            print(f"  [{i}/{len(stocks)}] {ticker} FAILED")
            continue

        # Filter to only new rows
        if last_date:
            df = df[df.index.strftime("%Y-%m-%d") > last_date]

        rows_added = 0
        for ts, row in df.iterrows():
            price_date = ts.strftime("%Y-%m-%d")
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO daily_prices
                    (ticker, price_date, open_price, high_price, low_price,
                     close_price, adj_close, volume, data_quality, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'full', 'yfinance')
                """, (
                    ticker, price_date,
                    float(row.get("Open",  0) or 0),
                    float(row.get("High",  0) or 0),
                    float(row.get("Low",   0) or 0),
                    float(row.get("Close", 0) or 0),
                    float(row.get("Close", 0) or 0),   # adj_close same as close after auto_adjust
                    int(row.get("Volume", 0) or 0),
                ))
                rows_added += 1
            except Exception as e:
                log.warning(f"{ticker} {price_date} insert error: {e}")

        conn.commit()
        stocks_updated += 1
        print(f"  [{i}/{len(stocks)}] {ticker} — {rows_added} new rows")
        time.sleep(0.15)   # polite throttle for Yahoo Finance

    # ── Indices ────────────────────────────────────────────────────────────────
    indices = conn.execute("SELECT index_code, yf_ticker FROM indices").fetchall()
    print(f"\nFetching {len(indices)} index price series…")

    idx_updated = 0
    for code, yf_ticker in indices:
        last_date = _get_last_price_date(conn, code, "index_prices")
        period    = _incremental_period(last_date)
        df        = _fetch_yf(yf_ticker, period, PRICE_INTERVAL)

        if df is None or df.empty:
            log.warning(f"Index {code} ({yf_ticker}) — no data")
            print(f"  {code} FAILED")
            continue

        if last_date:
            df = df[df.index.strftime("%Y-%m-%d") > last_date]

        for ts, row in df.iterrows():
            price_date = ts.strftime("%Y-%m-%d")
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO index_prices
                    (index_code, price_date, open_price, high_price, low_price,
                     close_price, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    code, price_date,
                    float(row.get("Open",   0) or 0),
                    float(row.get("High",   0) or 0),
                    float(row.get("Low",    0) or 0),
                    float(row.get("Close",  0) or 0),
                    int(row.get("Volume",   0) or 0),
                ))
            except Exception as e:
                log.warning(f"Index {code} {price_date}: {e}")

        conn.commit()
        idx_updated += 1
        print(f"  {code} — updated")
        time.sleep(0.1)

    print(f"Indices: {idx_updated}/{len(indices)} updated")

    duration = (datetime.now() - started).total_seconds()
    status   = "success" if stocks_failed == 0 else ("partial" if stocks_updated > 0 else "failed")
    error_summary = ", ".join(errors[:10]) if errors else None

    print(f"✔ prices complete in {duration:.0f}s ({stocks_updated} updated, {stocks_failed} failed)")
    return {
        "job": "prices", "run_id": run_id, "status": status,
        "stocks_updated": stocks_updated, "stocks_failed": stocks_failed,
        "duration_secs": duration, "error_summary": error_summary,
    }
