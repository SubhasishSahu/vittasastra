"""
Agent_Trader — Sync to GitHub (vittasastra mono-repo)
Stages the four JSON data files from agent-trader/data/,
commits with a harvest summary message, and pushes to origin/main.

vittasastra structure:
  vittasastra/              ← git root (.git lives here)
    agent-trader/
      data/
        results.json        ← staged
        snapshot.json       ← staged
        metadata.json       ← staged
        rss_news.json       ← staged
    agent-macro/            ← future
    ...

Called by scripts/harvest_and_push.sh after validation passes.
"""
import sys
import subprocess
import json
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BASE_DIR, RESULTS_JSON, SNAPSHOT_JSON, METADATA_JSON, NEWS_JSON

# vittasastra root is one level above agent-trader
VITTASASTRA_ROOT = str(BASE_DIR.parent)


def _run(cmd: list[str], cwd: str = None) -> tuple[int, str, str]:
    """Run a shell command, return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, cwd=cwd or VITTASASTRA_ROOT,
                            capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def sync():
    """Commit and push JSON data files to GitHub via vittasastra root."""
    print("Agent_Trader — GitHub Sync (vittasastra mono-repo)")
    print(f"Repo root: {VITTASASTRA_ROOT}")

    # ── Confirm vittasastra is a git repo ─────────────────────────────────────
    rc, out, _ = _run(["git", "rev-parse", "--show-toplevel"])
    if rc != 0:
        print("❌  Not a git repository. Ensure vittasastra/ has been cloned.")
        sys.exit(1)
    git_root = out
    print(f"Git root: {git_root}")

    # ── Read metadata for commit message ──────────────────────────────────────
    try:
        with open(METADATA_JSON) as f:
            meta = json.load(f)
        stocks   = meta.get("stocks_with_prices", "?")
        holdings = meta.get("portfolio_holdings", "?")
        jobs     = meta.get("harvest_jobs", [])
        n_ok     = sum(1 for j in jobs if j.get("status") in ("success", "partial"))
        n_total  = len(jobs)
        msg = (f"agent-trader harvest: {datetime.now().strftime('%Y-%m-%d')} | "
               f"{stocks} stocks | {holdings} holdings | {n_ok}/{n_total} jobs")
    except Exception:
        msg = f"agent-trader harvest: {datetime.now().strftime('%Y-%m-%dT%H:%M')} data sync"

    # ── Stage JSON files using paths relative to vittasastra root ────────────
    files_to_add = [RESULTS_JSON, SNAPSHOT_JSON, METADATA_JSON, NEWS_JSON]
    existing     = [f for f in files_to_add if os.path.exists(f)]

    if not existing:
        print("❌  No JSON files found. Run harvest first.")
        sys.exit(1)

    # Relative paths from vittasastra root for git add
    rel_files = [str(Path(f).relative_to(git_root)) for f in existing]
    rc, out, err = _run(["git", "add"] + rel_files)
    if rc != 0:
        print(f"❌  git add failed: {err}")
        sys.exit(1)
    print(f"✅  Staged: {', '.join(rel_files)}")

    # ── Check if anything actually changed ────────────────────────────────────
    rc, out, _ = _run(["git", "diff", "--cached", "--stat"])
    if not out:
        print("ℹ️   Nothing changed — JSON files unchanged since last push.")
        sys.exit(0)
    print(f"   Changes: {out}")

    # ── Commit ────────────────────────────────────────────────────────────────
    rc, out, err = _run(["git", "commit", "-m", msg])
    if rc != 0:
        print(f"❌  git commit failed: {err}")
        sys.exit(1)
    print(f"✅  Committed: {msg}")

    # ── Push ──────────────────────────────────────────────────────────────────
    rc, out, err = _run(["git", "push", "origin", "main"])
    if rc != 0:
        print(f"❌  git push failed:\n{err}")
        print("   Check: git remote -v  |  ssh -T git@github.com")
        sys.exit(1)

    print("✅  Pushed to GitHub — PythonAnywhere will pull on next schedule.")


if __name__ == "__main__":
    sync()
