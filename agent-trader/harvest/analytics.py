"""
Agent_Trader — Analytics Engine
Computes all risk/return metrics from the price data already in the DB.
Pure Python + numpy — no network calls. Fast (<5s for 50 stocks).
"""
import sys
import sqlite3
import logging
import math
from pathlib import Path
from datetime import datetime, date

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANALYTICS_MIN_DAYS

log = logging.getLogger(__name__)


def _load_prices(conn: sqlite3.Connection, ticker: str) -> pd.Series | None:
    """Load adj_close series for a ticker, sorted ascending."""
    rows = conn.execute("""
        SELECT price_date, adj_close FROM daily_prices
        WHERE ticker = ? AND adj_close > 0
        ORDER BY price_date ASC
    """, (ticker,)).fetchall()
    if len(rows) < ANALYTICS_MIN_DAYS:
        return None
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    return pd.Series(vals, index=idx, dtype=float)


def _load_benchmark(conn: sqlite3.Connection) -> pd.Series | None:
    """Load Nifty50 close series."""
    rows = conn.execute("""
        SELECT price_date, close_price FROM index_prices
        WHERE index_code = 'NIFTY50' AND close_price > 0
        ORDER BY price_date ASC
    """).fetchall()
    if len(rows) < ANALYTICS_MIN_DAYS:
        return None
    idx  = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    return pd.Series(vals, index=idx, dtype=float)


def _period_return(series: pd.Series, days: int) -> float | None:
    """Return percentage return over last N trading days."""
    if len(series) < days + 1:
        return None
    try:
        return float((series.iloc[-1] / series.iloc[-days]) - 1) * 100
    except Exception:
        return None


def _cagr(series: pd.Series, years: int) -> float | None:
    """Compound annual growth rate over N years."""
    trading_days = years * 252
    if len(series) < trading_days:
        return None
    try:
        r = series.iloc[-1] / series.iloc[-trading_days]
        return float((r ** (1 / years) - 1) * 100)
    except Exception:
        return None


def _beta(stock_ret: pd.Series, bench_ret: pd.Series, window: int = 252) -> float | None:
    """Rolling beta over last N trading days."""
    s = stock_ret.tail(window)
    b = bench_ret.reindex(s.index).dropna()
    s = s.reindex(b.index)
    if len(s) < 30:
        return None
    try:
        cov = np.cov(s.values, b.values)
        var = np.var(b.values)
        if var == 0:
            return None
        return float(cov[0][1] / var)
    except Exception:
        return None


def _var_95(daily_ret: pd.Series, window: int = 252) -> float | None:
    """Historical 95% 1-day VaR (percentage)."""
    r = daily_ret.tail(window).dropna()
    if len(r) < 30:
        return None
    try:
        return float(np.percentile(r.values, 5))   # 5th percentile = 95% VaR loss
    except Exception:
        return None


def _max_drawdown(series: pd.Series) -> float | None:
    """Maximum peak-to-trough drawdown (percentage)."""
    if len(series) < 10:
        return None
    try:
        roll_max = series.cummax()
        drawdown = (series - roll_max) / roll_max
        return float(drawdown.min() * 100)
    except Exception:
        return None


def _sharpe(daily_ret: pd.Series, window: int = 252, rf_daily: float = 0.000268) -> float | None:
    """Annualised Sharpe ratio (rf = ~7% annual / 252)."""
    r = daily_ret.tail(window).dropna()
    if len(r) < 30:
        return None
    try:
        excess = r - rf_daily
        if excess.std() == 0:
            return None
        return float(excess.mean() / excess.std() * math.sqrt(252))
    except Exception:
        return None


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    """RSI(14) on last N prices."""
    if len(series) < period + 5:
        return None
    try:
        delta = series.diff().dropna()
        gain  = delta.where(delta > 0, 0.0)
        loss  = -delta.where(delta < 0, 0.0)
        avg_g = gain.ewm(com=period - 1, adjust=False).mean().iloc[-1]
        avg_l = loss.ewm(com=period - 1, adjust=False).mean().iloc[-1]
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return float(100 - 100 / (1 + rs))
    except Exception:
        return None


def _macd_signal(series: pd.Series) -> str:
    """MACD crossover signal — bullish/bearish/neutral."""
    if len(series) < 35:
        return "neutral"
    try:
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd  = ema12 - ema26
        sig   = macd.ewm(span=9, adjust=False).mean()
        hist  = (macd - sig).iloc[-3:]
        if all(h > 0 for h in hist):
            return "bullish"
        if all(h < 0 for h in hist):
            return "bearish"
        return "neutral"
    except Exception:
        return "neutral"


def run_analytics(conn: sqlite3.Connection, run_id: str) -> dict:
    """Compute analytics for all active stocks and upsert into analytics_snapshot."""
    started = datetime.now()
    updated = 0
    failed  = 0

    bench = _load_benchmark(conn)
    bench_ret = bench.pct_change().dropna() if bench is not None else None
    nifty_1y  = _period_return(bench, 252) if bench is not None else None

    stocks = conn.execute(
        "SELECT ticker FROM stocks WHERE is_active = 1"
    ).fetchall()

    for (ticker,) in stocks:
        try:
            series = _load_prices(conn, ticker)
            if series is None:
                log.info(f"{ticker}: insufficient price data — skipping analytics")
                failed += 1
                continue

            daily_ret = series.pct_change().dropna()
            s_ret_aligned = None
            b_ret_aligned = None
            if bench_ret is not None:
                combined = pd.concat([daily_ret, bench_ret], axis=1, join="inner")
                combined.columns = ["stock", "bench"]
                s_ret_aligned = combined["stock"]
                b_ret_aligned = combined["bench"]

            # SMA
            sma50  = series.rolling(50).mean().iloc[-1]  if len(series) >= 50  else None
            sma200 = series.rolling(200).mean().iloc[-1] if len(series) >= 200 else None
            last   = series.iloc[-1]

            # 52-week
            wk52 = series.tail(252)
            high52 = float(wk52.max())
            low52  = float(wk52.min())

            row = {
                "ticker":         ticker,
                "computed_date":  date.today().isoformat(),
                "return_1d":      _period_return(series, 1),
                "return_1w":      _period_return(series, 5),
                "return_1m":      _period_return(series, 21),
                "return_3m":      _period_return(series, 63),
                "return_6m":      _period_return(series, 126),
                "return_1y":      _period_return(series, 252),
                "return_3y":      _period_return(series, 756),
                "return_5y":      _period_return(series, 1260),
                "cagr_3y":        _cagr(series, 3),
                "cagr_5y":        _cagr(series, 5),
                "beta_1y":        _beta(s_ret_aligned, b_ret_aligned, 252) if s_ret_aligned is not None else None,
                "beta_3y":        _beta(s_ret_aligned, b_ret_aligned, 756) if s_ret_aligned is not None else None,
                "volatility_1y":  float(daily_ret.tail(252).std() * (252 ** 0.5) * 100) if len(daily_ret) >= 60 else None,
                "volatility_3y":  float(daily_ret.tail(756).std() * (252 ** 0.5) * 100) if len(daily_ret) >= 180 else None,
                "var_95_1d_pct":  _var_95(daily_ret),
                "max_drawdown":   _max_drawdown(series),
                "sharpe_1y":      _sharpe(daily_ret),
                "alpha_vs_nifty": (_period_return(series, 252) - nifty_1y)
                                  if (_period_return(series, 252) is not None and nifty_1y is not None) else None,
                "above_sma50":    1 if (sma50 and last > sma50)   else 0,
                "above_sma200":   1 if (sma200 and last > sma200) else 0,
                "rsi_14":         _rsi(series),
                "macd_signal":    _macd_signal(series),
                "last_close":     float(last),
                "week52_high":    high52,
                "week52_low":     low52,
                "pct_from_high":  float((last / high52 - 1) * 100) if high52 else None,
                "pct_from_low":   float((last / low52  - 1) * 100) if low52  else None,
            }

            conn.execute("""
                INSERT OR REPLACE INTO analytics_snapshot
                (ticker, computed_date, return_1d, return_1w, return_1m, return_3m,
                 return_6m, return_1y, return_3y, return_5y, cagr_3y, cagr_5y,
                 beta_1y, beta_3y, volatility_1y, volatility_3y, var_95_1d_pct,
                 max_drawdown, sharpe_1y, alpha_vs_nifty, above_sma50, above_sma200,
                 rsi_14, macd_signal, last_close, week52_high, week52_low,
                 pct_from_high, pct_from_low, updated_at)
                VALUES (:ticker,:computed_date,:return_1d,:return_1w,:return_1m,
                        :return_3m,:return_6m,:return_1y,:return_3y,:return_5y,
                        :cagr_3y,:cagr_5y,:beta_1y,:beta_3y,:volatility_1y,
                        :volatility_3y,:var_95_1d_pct,:max_drawdown,:sharpe_1y,
                        :alpha_vs_nifty,:above_sma50,:above_sma200,:rsi_14,
                        :macd_signal,:last_close,:week52_high,:week52_low,
                        :pct_from_high,:pct_from_low,datetime('now'))
            """, row)
            conn.commit()
            updated += 1

        except Exception as e:
            log.error(f"{ticker} analytics: {e}")
            failed += 1

    duration = (datetime.now() - started).total_seconds()
    print(f"✔ analytics complete in {duration:.0f}s ({updated} updated, {failed} failed)")
    return {
        "job": "analytics", "run_id": run_id,
        "status": "success" if failed == 0 else ("partial" if updated > 0 else "failed"),
        "stocks_updated": updated, "stocks_failed": failed,
        "duration_secs": duration, "error_summary": None,
    }
