"""
Agent_Trader — WSGI Entry Point
Used by PythonAnywhere.

vittasastra mono-repo structure on PythonAnywhere:
  /home/SubhasishSahu/vittasastra/          ← git clone of vittasastra repo
  /home/SubhasishSahu/vittasastra/agent-trader/  ← this agent
  /home/SubhasishSahu/vittasastra/agent-macro/   ← future agent
  ...

Edit project_path below to match your PythonAnywhere username.
The vittasastra repo root and agent subfolder are both needed.
"""
import sys
import os

# ── EDIT THIS — replace SubhasishSahu with your PythonAnywhere username ────────
VITTASASTRA_ROOT = '/home/SubhasishSahu/vittasastra'
AGENT_DIR        = 'agent-trader'
# ──────────────────────────────────────────────────────────────────────────────

project_path = os.path.join(VITTASASTRA_ROOT, AGENT_DIR)

# Add agent-trader to Python path so imports resolve correctly
if project_path not in sys.path:
    sys.path.insert(0, project_path)

# Set working directory to agent-trader so relative paths (data/, templates/) work
os.chdir(project_path)

# Load .env from agent-trader folder before Flask starts
from dotenv import load_dotenv
load_dotenv(os.path.join(project_path, '.env'))

# Auto-init DB on first cold start (milliseconds on subsequent starts)
from config import DB_PATH
if not os.path.exists(DB_PATH):
    try:
        from tools.init_db import init_db
        init_db()
    except Exception:
        pass

# WSGI callable — must be named 'application'
from app import app as application
