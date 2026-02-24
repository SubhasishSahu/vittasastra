# Agent_Trader

NSE/BSE portfolio analytics engine — part of the **vittasastra** financial agent ecosystem.

## vittasastra Mono-Repo Structure

```
vittasastra/                        ← GitHub repo root (.git lives here)
├── agent-trader/                   ← this agent (portfolio analytics)
│   ├── harvest/                    ← data collection pipeline (Mac only)
│   ├── tools/                      ← init, validate, sync utilities
│   ├── core/                       ← scorecards, alerts (Sprint 3)
│   ├── scripts/                    ← Mac cron + PA pull scripts
│   ├── data/                       ← market.db (local, gitignored) + JSON (pushed)
│   ├── app.py                      ← Flask API (serves JSON, zero outbound calls)
│   ├── config.py                   ← all paths, universe, auth
│   └── wsgi.py                     ← PythonAnywhere WSGI entry point
├── agent-macro/                    ← future: RBI/FII/DII macro indicators
├── agent-screener/                 ← future: broader universe screener
└── agent-alerts/                   ← future: WhatsApp/email dispatcher
```

## Architecture

```
YOUR MAC                         GITHUB (vittasastra)           PYTHONANYWHERE
────────────────                 ────────────────────           ──────────────
harvest/ runs daily  ──push──►  agent-trader/data/*.json  ──pull──►  Flask API
yfinance (no proxy)             snapshot.json                        iPad dashboard
market.db stays local           results.json
validate before push            metadata.json
                                rss_news.json
```

**Data flow:** 06:30 IST Mac harvest → validate → git push → 07:30 IST PA pulls → iPad sees latest data.

## Mac — First Harvest

```bash
cd ~/Documents/GitHub/solidity/vittasastra/agent-trader
pip3 install -r requirements.txt
nano .env                                    # type the three lines — do not paste
python3 tools/init_db.py
python3 harvest/scheduler.py --jobs all --force
python3 tools/validate.py
python3 tools/sync.py
python3 tools/generate_token.py             # save this token for iPad
```

`.env` contents (type manually):
```
USER_EMAIL=your@email.com
SECRET_SALT=your-secret-phrase-here
FLASK_SECRET_KEY=your-flask-key-here
```

## Mac — Daily Cron

```bash
crontab -e
```
Add (adjust path if needed):
```
30 1 * * 1-5 /Users/subhasishsahu/Documents/GitHub/solidity/vittasastra/agent-trader/scripts/harvest_and_push.sh
```
01:30 UTC = 06:30 IST, weekdays only.

## PythonAnywhere — One-Time Setup

```bash
# In PythonAnywhere Bash console
cd ~
git clone https://github.com/SubhasishSahu/vittasastra.git
cd vittasastra/agent-trader
pip install -r requirements.txt --user
nano .env                                   # same three lines as Mac
```

**Web App tab:**
| Field | Value |
|-------|-------|
| Source code | `/home/SubhasishSahu/vittasastra/agent-trader` |
| Working directory | `/home/SubhasishSahu/vittasastra/agent-trader` |
| WSGI file | Edit — set `VITTASASTRA_ROOT = '/home/SubhasishSahu/vittasastra'` |

**Scheduled task (Tasks tab):**
```
bash /home/SubhasishSahu/vittasastra/agent-trader/scripts/pa_pull.sh
```
Time: 02:00 UTC daily (07:30 IST).

## API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/status` | Public | Health check |
| `POST /api/auth/verify` | Public | Exchange email → token |
| `GET /api/snapshot` | Token | All 50 stocks analytics |
| `GET /api/portfolio` | Token | Holdings with live P&L |
| `GET /api/news` | Token | Latest RSS news |
| `GET /api/stock/<TICKER>` | Token | Single stock + related news |
| `GET /api/sectors` | Token | Sector aggregates |
| `POST /api/portfolio/upload` | Token | Upload holdings JSON |

Token format: `at_...` — get it from `python3 tools/generate_token.py`.

## Sprint Roadmap

| Sprint | Status | Scope |
|--------|--------|-------|
| 1 | ✅ Complete | DB schema, harvest pipeline, Flask API, validate, sync |
| 2 | 🔜 Next | iPad PWA dashboard |
| 3 | Planned | SC1–SC6 scorecards, Kelly sizing, 10-rule alert engine |
| 4 | Planned | Email alerts, 30-day hardening, backtest calibration |
