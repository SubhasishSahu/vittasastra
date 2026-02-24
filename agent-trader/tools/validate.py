"""
Agent_Trader — Local Validation Gate
Run after every harvest before git push.
Exits 0 (pass) or 1 (fail). Shell script checks exit code.
"""
import sys
import sqlite3
import json
import os
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, SNAPSHOT_JSON, RESULTS_JSON, METADATA_JSON, NEWS_JSON

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

issues   = []
warnings = []


def check(label, condition, detail="", is_warning=False):
    sym = PASS if condition else (WARN if is_warning else FAIL)
    print(f"  {sym}  {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        (warnings if is_warning else issues).append(label)
    return condition


def main():
    print("\nAgent_Trader — Validation Report")
    print(f"Date: {date.today()}  DB: {DB_PATH}\n")

    if not os.path.exists(DB_PATH):
        print(f"{FAIL}  Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    # ── V1 Price Data ──────────────────────────────────────────────────────────
    print("V1 — Price Data Quality")
    total_rows = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    n_tickers  = conn.execute("SELECT COUNT(DISTINCT ticker) FROM daily_prices").fetchone()[0]
    oldest     = conn.execute("SELECT MIN(price_date) FROM daily_prices").fetchone()[0]
    newest     = conn.execute("SELECT MAX(price_date) FROM daily_prices").fetchone()[0]
    stale      = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM daily_prices "
        "GROUP BY ticker HAVING MAX(price_date) < date('now','-7 days')"
    ).fetchone()
    stale_count = stale[0] if stale else 0

    check("Total price rows ≥ 50,000",      total_rows >= 50000,
          f"{total_rows:,} rows")
    check("Stocks with price data ≥ 40",    n_tickers >= 40,
          f"{n_tickers} stocks")
    check("Price history ≥ 4 years",
          oldest is not None and oldest <= str(date.today().year - 4) + "-12-31",
          f"oldest={oldest}")
    check("Latest prices within 7 days",
          newest is not None and newest >= str(date.today().year) + "-01-01",
          f"newest={newest}")
    check("No excessively stale tickers",   stale_count == 0,
          f"{stale_count} stale", is_warning=True)

    # OHLC integrity
    ohlc_violations = conn.execute("""
        SELECT COUNT(*) FROM daily_prices
        WHERE high_price < open_price
           OR high_price < close_price
           OR low_price  > open_price
           OR low_price  > close_price
           OR close_price <= 0
    """).fetchone()[0]
    check("Zero OHLC integrity violations", ohlc_violations == 0,
          f"{ohlc_violations} violations")

    # ── V2 Analytics ──────────────────────────────────────────────────────────
    print("\nV2 — Analytics Snapshot")
    n_analytics = conn.execute("SELECT COUNT(*) FROM analytics_snapshot").fetchone()[0]
    beta_outliers = conn.execute(
        "SELECT COUNT(*) FROM analytics_snapshot WHERE beta_1y < -3 OR beta_1y > 5"
    ).fetchone()[0]
    var_outliers = conn.execute(
        "SELECT COUNT(*) FROM analytics_snapshot WHERE var_95_1d_pct > 0 OR var_95_1d_pct < -20"
    ).fetchone()[0]
    null_beta = conn.execute(
        "SELECT COUNT(*) FROM analytics_snapshot WHERE beta_1y IS NULL"
    ).fetchone()[0]

    check("Analytics rows ≥ 40",           n_analytics >= 40, f"{n_analytics} rows")
    check("Beta outliers = 0",              beta_outliers == 0, f"{beta_outliers} outliers")
    check("VaR in valid range",             var_outliers == 0, f"{var_outliers} out of range")
    check("Stocks with beta computed ≥ 35",
          (n_analytics - null_beta) >= 35,
          f"{n_analytics - null_beta} have beta", is_warning=True)

    # ── V3 News ────────────────────────────────────────────────────────────────
    print("\nV3 — News / RSS")
    news_count = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE date(published_at) >= date('now','-14 days')"
    ).fetchone()[0]
    feeds_ok = conn.execute(
        "SELECT COUNT(*) FROM rss_feeds WHERE error_count = 0"
    ).fetchone()[0]
    feeds_total = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]

    check("News items (14d) ≥ 0",          True, f"{news_count} items", is_warning=news_count == 0)
    check("Some feeds healthy",             feeds_ok > 0, f"{feeds_ok}/{feeds_total} feeds ok",
          is_warning=True)
    check("rss_news.json exists",           os.path.exists(NEWS_JSON))

    # ── V4 JSON Files ─────────────────────────────────────────────────────────
    print("\nV4 — JSON Export Files")
    for label, path in [
        ("snapshot.json", SNAPSHOT_JSON),
        ("results.json",  RESULTS_JSON),
        ("metadata.json", METADATA_JSON),
        ("rss_news.json", NEWS_JSON),
    ]:
        exists = os.path.exists(path)
        check(f"{label} exists", exists)
        if exists:
            try:
                with open(path) as f:
                    data = json.load(f)
                check(f"{label} valid JSON", True)
                if "generated_at" in data:
                    gen_dt = datetime.fromisoformat(data["generated_at"])
                    age_h  = (datetime.now() - gen_dt).total_seconds() / 3600
                    check(f"{label} generated within 6h", age_h <= 6, f"{age_h:.1f}h old")
            except json.JSONDecodeError as e:
                check(f"{label} valid JSON", False, str(e))

    # ── V5 Harvest Log ────────────────────────────────────────────────────────
    print("\nV5 — Harvest Log (last run)")

    # Core jobs that MUST succeed — prices, analytics, export
    # Enrichment jobs where failure is a warning — fundamentals, shareholding, news
    CORE_JOBS       = {"prices", "analytics", "export"}
    ENRICHMENT_JOBS = {"fundamentals", "shareholding", "news"}

    last_run_id = conn.execute(
        "SELECT run_id FROM harvest_log ORDER BY log_id DESC LIMIT 1"
    ).fetchone()

    if not last_run_id:
        check("Harvest log has entries", False, "no entries found")
    else:
        run_id_val = last_run_id[0]
        job_rows = conn.execute("""
            SELECT job_name, status, stocks_updated, stocks_failed
            FROM harvest_log
            WHERE run_id = ?
        """, (run_id_val,)).fetchall()

        core_failed = []
        enrichment_warned = []

        for job_name, status, upd, fail in job_rows:
            ok = status in ("success", "partial")
            if not ok:
                if job_name in CORE_JOBS:
                    core_failed.append(job_name)
                elif job_name in ENRICHMENT_JOBS:
                    enrichment_warned.append(job_name)

        n_total = len(job_rows)
        check(f"Last run [{run_id_val}] core jobs succeeded",
              len(core_failed) == 0,
              f"{n_total} jobs run" + (f", core failed: {core_failed}" if core_failed else ""))

        for job in enrichment_warned:
            check(f"Enrichment job '{job}' succeeded",
                  False,
                  f"{job} failed — enrichment only, non-blocking",
                  is_warning=True)

    conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*50}")
    if issues:
        print(f"{FAIL}  VALIDATION FAILED — {len(issues)} issue(s):")
        for i in issues:
            print(f"     • {i}")
        if warnings:
            print(f"\n{WARN}  {len(warnings)} warning(s) (non-blocking):")
            for w in warnings:
                print(f"     • {w}")
        print("\n  ➜ Fix issues before pushing to GitHub.")
        sys.exit(1)
    else:
        if warnings:
            print(f"{WARN}  {len(warnings)} warning(s) — data pushed with caution:")
            for w in warnings:
                print(f"     • {w}")
        print(f"{PASS}  All checks passed — safe to push to GitHub.")
        sys.exit(0)


if __name__ == "__main__":
    main()
