#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Agent_Trader — Harvest and Push Script
# Mac cron target. Runs daily at 06:30 IST.
#
# vittasastra mono-repo structure on Mac:
#   ~/Documents/GitHub/solidity/vittasastra/           ← git repo root
#   ~/Documents/GitHub/solidity/vittasastra/agent-trader/ ← this agent
#
# Add to crontab (run: crontab -e):
#   30 1 * * 1-5 /Users/subhasishsahu/Documents/GitHub/solidity/vittasastra/agent-trader/scripts/harvest_and_push.sh
#   (01:00 UTC = 06:30 IST, weekdays Mon-Fri only)
#
# EDIT: Update PROJECT_DIR to match your actual Mac path.
# ═══════════════════════════════════════════════════════════════════════

set -e

# ── Config — edit PROJECT_DIR if your path differs ────────────────────────────
PROJECT_DIR="/Users/subhasishsahu/Documents/GitHub/solidity/vittasastra/agent-trader"
VITTASASTRA_ROOT="/Users/subhasishsahu/Documents/GitHub/solidity/vittasastra"
PYTHON="python3"
LOG_FILE="$PROJECT_DIR/data/cron.log"
# ──────────────────────────────────────────────────────────────────────────────

cd "$PROJECT_DIR"
mkdir -p data

echo "" >> "$LOG_FILE"
echo "═══════════════════════════════════════════" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Harvest started" >> "$LOG_FILE"

# Load .env (agent-trader's own secrets)
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# ── Step 1: Run harvest ────────────────────────────────────────────────────────
echo "Step 1: Running harvest…" | tee -a "$LOG_FILE"
$PYTHON harvest/scheduler.py --jobs all 2>&1 | tee -a "$LOG_FILE"
HARVEST_EXIT=${PIPESTATUS[0]}

if [ $HARVEST_EXIT -ne 0 ]; then
    echo "⚠  Harvest finished with errors (exit $HARVEST_EXIT) — continuing to validate" | tee -a "$LOG_FILE"
fi

# ── Step 2: Validate ──────────────────────────────────────────────────────────
echo "" | tee -a "$LOG_FILE"
echo "Step 2: Validating…" | tee -a "$LOG_FILE"
$PYTHON tools/validate.py 2>&1 | tee -a "$LOG_FILE"
VALIDATE_EXIT=${PIPESTATUS[0]}

if [ $VALIDATE_EXIT -ne 0 ]; then
    echo "❌  Validation FAILED — skipping push. Check $LOG_FILE" | tee -a "$LOG_FILE"
    exit 1
fi

# ── Step 3: Push vittasastra repo to GitHub ───────────────────────────────────
# git push from agent-trader/ walks up to vittasastra root automatically.
# Only the 4 JSON data files are staged by tools/sync.py.
echo "" | tee -a "$LOG_FILE"
echo "Step 3: Pushing to GitHub (vittasastra)…" | tee -a "$LOG_FILE"
$PYTHON tools/sync.py 2>&1 | tee -a "$LOG_FILE"
SYNC_EXIT=${PIPESTATUS[0]}

if [ $SYNC_EXIT -ne 0 ]; then
    echo "❌  Git push FAILED — data current locally but not on GitHub" | tee -a "$LOG_FILE"
    exit 1
fi

echo "" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') — Harvest complete ✅" >> "$LOG_FILE"
echo "✅  All steps complete."
