"""
Agent_Trader — Harvest Scheduler
Master orchestrator. Run by Mac cron via scripts/harvest_and_push.sh.
Usage:
  python harvest/scheduler.py                    # run all jobs (smart mode)
  python harvest/scheduler.py --jobs all --force  # force all regardless of day
  python harvest/scheduler.py --jobs prices       # prices only
  python harvest/scheduler.py --jobs prices,news  # specific jobs
"""
import sys
import argparse
import logging
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(Path(__file__).parent.parent / "data" / "harvest.log"),
                            mode="a", encoding="utf-8"),
    ]
)
log = logging.getLogger("scheduler")


def _log_job(conn, run_id, result):
    """Write job result to harvest_log."""
    conn.execute("""
        INSERT INTO harvest_log
        (run_id, job_name, status, stocks_updated, stocks_failed, duration_secs,
         error_summary, completed_at)
        VALUES (?,?,?,?,?,?,?,datetime('now'))
    """, (
        run_id,
        result.get("job"),
        result.get("status"),
        result.get("stocks_updated", 0),
        result.get("stocks_failed", 0),
        result.get("duration_secs"),
        result.get("error_summary"),
    ))
    conn.commit()


def _should_run(job: str, today: date, force: bool) -> bool:
    """Smart run logic — fundamentals weekly, shareholding monthly."""
    if force:
        return True
    if job == "fundamentals":
        return today.weekday() == 0   # Monday only
    if job == "shareholding":
        return today.day == 1         # 1st of month only
    return True


def run(jobs_arg: str = "all", force: bool = False):
    """Run the harvest pipeline."""
    run_id = uuid.uuid4().hex[:8]
    today  = date.today()

    # Determine which jobs to run
    all_jobs = ["prices", "news", "fundamentals", "shareholding", "analytics", "export"]
    if jobs_arg == "all":
        requested = all_jobs
    else:
        requested = [j.strip() for j in jobs_arg.split(",")]

    jobs_to_run = [j for j in requested if _should_run(j, today, force)]

    sep = "═" * 60
    print(sep)
    print(f"Agent_Trader — Harvest Run [{run_id}]")
    print(f"Date: {today} | Jobs: {', '.join(jobs_to_run)}")
    print(sep)

    import os
    os.makedirs(str(Path(DB_PATH).parent), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    job_results = []
    succeeded   = 0
    failed_jobs = []

    for job in jobs_to_run:
        print(f"\n▶ {job.upper()} starting…")
        try:
            if job == "prices":
                from harvest.prices import run_prices
                result = run_prices(conn, run_id)
            elif job == "news":
                from harvest.news import run_news
                result = run_news(conn, run_id)
            elif job == "fundamentals":
                from harvest.fundamentals import run_fundamentals
                result = run_fundamentals(conn, run_id)
            elif job == "shareholding":
                from harvest.shareholding import run_shareholding
                result = run_shareholding(conn, run_id)
            elif job == "analytics":
                from harvest.analytics import run_analytics
                result = run_analytics(conn, run_id)
            elif job == "export":
                from harvest.export import run_export
                result = run_export(conn, run_id, job_results)
            else:
                log.warning(f"Unknown job: {job}")
                continue

            _log_job(conn, run_id, result)
            job_results.append(result)

            if result.get("status") in ("success", "partial"):
                succeeded += 1
            else:
                failed_jobs.append(job)

        except Exception as e:
            log.error(f"{job} CRASHED: {e}", exc_info=True)
            failed_jobs.append(job)
            _log_job(conn, run_id, {
                "job": job, "status": "failed",
                "stocks_updated": 0, "stocks_failed": 0,
                "duration_secs": 0, "error_summary": str(e),
            })

    conn.close()

    print(f"\n{'─'*60}")
    print(f"Harvest complete. Job ID: {run_id}")
    if failed_jobs:
        print(f"{succeeded}/{len(jobs_to_run)} jobs succeeded. FAILED: {', '.join(failed_jobs)}")
    else:
        print(f"{succeeded}/{len(jobs_to_run)} jobs succeeded.")
    print(f"{'─'*60}")

    # Exit code for shell script to check
    return len(failed_jobs)


def main():
    parser = argparse.ArgumentParser(description="Agent_Trader Harvest Scheduler")
    parser.add_argument("--jobs",  default="all",
                        help="Comma-separated: prices,news,fundamentals,shareholding,analytics,export or 'all'")
    parser.add_argument("--force", action="store_true",
                        help="Force all jobs regardless of day-of-week/month schedule")
    args = parser.parse_args()
    exit_code = run(jobs_arg=args.jobs, force=args.force)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
