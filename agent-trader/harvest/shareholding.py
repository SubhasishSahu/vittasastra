"""
Agent_Trader — Shareholding Harvest
Fetches major holders from yfinance with exponential backoff on 429 errors.
Runs monthly (1st of month) or on force flag.
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

log = logging.getLogger(__name__)

_BACKOFF_SECONDS = [5, 15, 45]   # retry delays on 429


def _inspect_holders(tk: yf.Ticker, yf_ticker: str) -> tuple:
    """
    Fetch major_holders and defensive-inspect its shape.
    yfinance has changed the major_holders DataFrame structure across versions.
    We handle all known shapes:
      Shape A (old): 2 columns — [percentage, label]
      Shape B (new): 2 columns — ['Value', 'Breakdown'] with named index
      Shape C: empty or None
    Returns (insider_pct, institution_pct) or (None, None).
    """
    try:
        holders = tk.major_holders
        if holders is None or holders.empty:
            return None, None

        insider = institution = None

        # Normalise — always work with .values to avoid column name dependency
        for _, row in holders.iterrows():
            vals = [v for v in row.values if v is not None]
            if len(vals) < 2:
                continue
            try:
                raw_pct = float(str(vals[0]).replace('%', '').strip())
                # yfinance returns 0.xx (decimal) or xx.xx (percent) depending on version
                pct = raw_pct * 100 if raw_pct <= 1.0 else raw_pct
            except (ValueError, TypeError):
                continue
            label = str(vals[1]).lower()
            if "insider" in label:
                insider = round(pct, 2)
            elif "institution" in label:
                institution = round(pct, 2)

        return insider, institution

    except Exception as e:
        log.warning(f"{yf_ticker} _inspect_holders: {e}")
        return None, None


def run_shareholding(conn: sqlite3.Connection, run_id: str) -> dict:
    """Main entry — fetch shareholding for all active stocks."""
    started = datetime.now()
    updated = 0
    failed  = 0
    errors  = []

    stocks = conn.execute(
        "SELECT ticker, yf_ticker FROM stocks WHERE is_active = 1"
    ).fetchall()

    for i, (ticker, yf_ticker) in enumerate(stocks, 1):
        # Exponential backoff on 429 rate limits
        for attempt, wait in enumerate([0] + _BACKOFF_SECONDS):
            if wait:
                log.info(f"  Rate limit — waiting {wait}s before retry {attempt}")
                time.sleep(wait)
            try:
                tk = yf.Ticker(yf_ticker)
                insider, institution = _inspect_holders(tk, yf_ticker)
                today = datetime.now().strftime("%Y-%m-%d")

                conn.execute("""
                    INSERT OR REPLACE INTO shareholding_pattern
                    (ticker, period_end, promoter_pct, fii_pct, dii_pct,
                     public_pct, insider_pct, institution_pct, source)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (ticker, today,
                      None, None, None, None,
                      insider, institution,
                      "yfinance_major_holders"))
                conn.commit()
                updated += 1
                print(f"  [{i}/{len(stocks)}] {ticker} — "
                      f"insider={insider}% institution={institution}%")
                break   # success — exit retry loop

            except Exception as e:
                if "429" in str(e) and attempt < len(_BACKOFF_SECONDS):
                    log.warning(f"{ticker} rate limited — will retry")
                    continue
                log.error(f"{ticker} shareholding: {e}")
                failed += 1
                errors.append(ticker)
                print(f"  [{i}/{len(stocks)}] {ticker} — failed: {e}")
                break

        time.sleep(1.5)   # polite throttle between stocks

    duration = (datetime.now() - started).total_seconds()
    status   = "success" if failed == 0 else ("partial" if updated > 0 else "failed")
    print(f"✔ shareholding complete in {duration:.0f}s ({updated} updated, {failed} failed)")
    return {
        "job": "shareholding", "run_id": run_id, "status": status,
        "stocks_updated": updated, "stocks_failed": failed,
        "duration_secs": duration, "error_summary": ", ".join(errors[:10]) or None,
    }
