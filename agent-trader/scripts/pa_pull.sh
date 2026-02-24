#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Agent_Trader — PythonAnywhere Pull Script
# Part of the vittasastra mono-repo architecture.
#
# vittasastra structure on PythonAnywhere:
#   /home/SubhasishSahu/vittasastra/           ← cloned once
#   /home/SubhasishSahu/vittasastra/agent-trader/  ← this agent
#
# FIRST-TIME SETUP on PythonAnywhere (run once in Bash console):
#   cd ~
#   git clone https://github.com/SubhasishSahu/vittasastra.git
#   cd vittasastra/agent-trader
#   pip install -r requirements.txt --user
#   cp .env.example .env   # then nano .env to add your values
#
# SCHEDULED TASK (PythonAnywhere Tasks tab):
#   Command: bash /home/SubhasishSahu/vittasastra/agent-trader/scripts/pa_pull.sh
#   Time:    02:00 UTC daily  (= 07:30 IST — 1hr after Mac harvest)
#
# EDIT: replace SubhasishSahu with your actual PythonAnywhere username.
# ═══════════════════════════════════════════════════════════════════════

VITTASASTRA_ROOT="/home/SubhasishSahu/vittasastra"
AGENT_DIR="agent-trader"
AGENT_PATH="$VITTASASTRA_ROOT/$AGENT_DIR"
LOG_FILE="$AGENT_PATH/data/pa_pull.log"

mkdir -p "$AGENT_PATH/data"

echo "" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S UTC') — PA pull started" >> "$LOG_FILE"

# ── Step 1: Pull entire vittasastra repo from repo root ───────────────────────
cd "$VITTASASTRA_ROOT" || {
    echo "❌  vittasastra not found at $VITTASASTRA_ROOT" >> "$LOG_FILE"
    echo "    Run: cd ~ && git clone https://github.com/SubhasishSahu/vittasastra.git" >> "$LOG_FILE"
    exit 1
}

git pull origin main >> "$LOG_FILE" 2>&1
PULL_EXIT=$?

if [ $PULL_EXIT -eq 0 ]; then
    echo "✅  git pull succeeded — vittasastra updated" >> "$LOG_FILE"
else
    echo "❌  git pull failed (exit $PULL_EXIT)" >> "$LOG_FILE"
    exit 1
fi

# ── Step 2: Touch WSGI to trigger Flask reload on PythonAnywhere ──────────────
touch "$AGENT_PATH/wsgi.py"
echo "✅  WSGI reloaded — agent-trader Flask app serving latest data" >> "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S UTC') — PA pull complete" >> "$LOG_FILE"

