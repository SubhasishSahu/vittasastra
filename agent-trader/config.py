"""
Agent_Trader — Central Configuration
All paths, constants, and auth logic in one place.
"""
import os
import hmac
import hashlib
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.resolve()
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = str(DATA_DIR / "market.db")

RESULTS_JSON   = str(DATA_DIR / "results.json")
SNAPSHOT_JSON  = str(DATA_DIR / "snapshot.json")
METADATA_JSON  = str(DATA_DIR / "metadata.json")
NEWS_JSON      = str(DATA_DIR / "rss_news.json")

# ── Environment ────────────────────────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")

USER_EMAIL       = os.environ.get("USER_EMAIL", "")
SECRET_SALT      = os.environ.get("SECRET_SALT", "")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")

# ── Harvest settings ───────────────────────────────────────────────────────────
PRICE_PERIOD     = "5y"       # yfinance period for initial backfill
PRICE_INTERVAL   = "1d"       # daily OHLCV
MAX_STOCKS       = 100        # hard cap on universe size
NEWS_LOOKBACK_DAYS = 14       # keep news items this many days old
ANALYTICS_MIN_DAYS = 60       # minimum price rows needed to compute analytics

# ── Auth ───────────────────────────────────────────────────────────────────────
TOKEN_PREFIX = "at_"          # Agent_Trader prefix (was pf_ in v4)

def generate_token(email: str) -> str:
    """Generate a deterministic HMAC token for a given email + SECRET_SALT."""
    if not SECRET_SALT:
        raise ValueError("SECRET_SALT is not set — check your .env file")
    key   = SECRET_SALT.encode()
    msg   = email.strip().lower().encode()
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"{TOKEN_PREFIX}{digest}"

def validate_token(token: str) -> bool:
    """Return True if the token matches the configured USER_EMAIL."""
    if not USER_EMAIL or not token:
        return False
    try:
        expected = generate_token(USER_EMAIL)
        return hmac.compare_digest(token, expected)
    except Exception:
        return False

# ── Nifty 50 universe (as of Feb 2026) ────────────────────────────────────────
NIFTY50_STOCKS = [
    ("ADANIENT",   "Adani Enterprises",        "Energy",       "ADANIENT.NS"),
    ("ADANIPORTS", "Adani Ports & SEZ",         "Infrastructure","ADANIPORTS.NS"),
    ("APOLLOHOSP", "Apollo Hospitals",          "Healthcare",   "APOLLOHOSP.NS"),
    ("ASIANPAINT", "Asian Paints",              "Materials",    "ASIANPAINT.NS"),
    ("AXISBANK",   "Axis Bank",                 "Financials",   "AXISBANK.NS"),
    ("BAJAJ-AUTO", "Bajaj Auto",                "Auto",         "BAJAJ-AUTO.NS"),
    ("BAJAJFINSV", "Bajaj Finserv",             "Financials",   "BAJAJFINSV.NS"),
    ("BAJFINANCE", "Bajaj Finance",             "Financials",   "BAJFINANCE.NS"),
    ("BHARTIARTL", "Bharti Airtel",             "Telecom",      "BHARTIARTL.NS"),
    ("BPCL",       "BPCL",                      "Energy",       "BPCL.NS"),
    ("BRITANNIA",  "Britannia Industries",      "FMCG",         "BRITANNIA.NS"),
    ("CIPLA",      "Cipla",                     "Healthcare",   "CIPLA.NS"),
    ("COALINDIA",  "Coal India",                "Energy",       "COALINDIA.NS"),
    ("DIVISLAB",   "Divi's Laboratories",       "Healthcare",   "DIVISLAB.NS"),
    ("DRREDDY",    "Dr. Reddy's Laboratories",  "Healthcare",   "DRREDDY.NS"),
    ("EICHERMOT",  "Eicher Motors",             "Auto",         "EICHERMOT.NS"),
    ("GRASIM",     "Grasim Industries",         "Materials",    "GRASIM.NS"),
    ("HCLTECH",    "HCL Technologies",          "IT",           "HCLTECH.NS"),
    ("HDFCBANK",   "HDFC Bank",                 "Financials",   "HDFCBANK.NS"),
    ("HDFCLIFE",   "HDFC Life Insurance",       "Financials",   "HDFCLIFE.NS"),
    ("HEROMOTOCO", "Hero MotoCorp",             "Auto",         "HEROMOTOCO.NS"),
    ("HINDALCO",   "Hindalco Industries",       "Materials",    "HINDALCO.NS"),
    ("HINDUNILVR", "Hindustan Unilever",        "FMCG",         "HINDUNILVR.NS"),
    ("ICICIBANK",  "ICICI Bank",                "Financials",   "ICICIBANK.NS"),
    ("INDUSINDBK", "IndusInd Bank",             "Financials",   "INDUSINDBK.NS"),
    ("INFY",       "Infosys",                   "IT",           "INFY.NS"),
    ("ITC",        "ITC",                       "FMCG",         "ITC.NS"),
    ("JSWSTEEL",   "JSW Steel",                 "Materials",    "JSWSTEEL.NS"),
    ("KOTAKBANK",  "Kotak Mahindra Bank",       "Financials",   "KOTAKBANK.NS"),
    ("LT",         "Larsen & Toubro",           "Infrastructure","LT.NS"),
    ("M&M",        "Mahindra & Mahindra",       "Auto",         "M&M.NS"),
    ("MARUTI",     "Maruti Suzuki",             "Auto",         "MARUTI.NS"),
    ("NESTLEIND",  "Nestle India",              "FMCG",         "NESTLEIND.NS"),
    ("NTPC",       "NTPC",                      "Energy",       "NTPC.NS"),
    ("ONGC",       "ONGC",                      "Energy",       "ONGC.NS"),
    ("POWERGRID",  "Power Grid Corporation",    "Energy",       "POWERGRID.NS"),
    ("RELIANCE",   "Reliance Industries",       "Energy",       "RELIANCE.NS"),
    ("SBILIFE",    "SBI Life Insurance",        "Financials",   "SBILIFE.NS"),
    ("SBIN",       "State Bank of India",       "Financials",   "SBIN.NS"),
    ("SHRIRAMFIN", "Shriram Finance",           "Financials",   "SHRIRAMFIN.NS"),
    ("SUNPHARMA",  "Sun Pharmaceutical",        "Healthcare",   "SUNPHARMA.NS"),
    ("TATACONSUM", "Tata Consumer Products",    "FMCG",         "TATACONSUM.NS"),
    ("TATAMOTORS", "Tata Motors",               "Auto",         "TATAMOTORS.NS"),
    ("TATASTEEL",  "Tata Steel",                "Materials",    "TATASTEEL.NS"),
    ("TCS",        "Tata Consultancy Services", "IT",           "TCS.NS"),
    ("TECHM",      "Tech Mahindra",             "IT",           "TECHM.NS"),
    ("TITAN",      "Titan Company",             "Consumer",     "TITAN.NS"),
    ("ULTRACEMCO", "UltraTech Cement",          "Materials",    "ULTRACEMCO.NS"),
    ("WIPRO",      "Wipro",                     "IT",           "WIPRO.NS"),
    ("ZOMATO",     "Zomato",                    "Consumer",     "ZOMATO.NS"),
]

# ── Index universe ─────────────────────────────────────────────────────────────
INDEX_TICKERS = [
    ("NIFTY50",      "Nifty 50",              "^NSEI"),
    ("NIFTYMIDCAP",  "Nifty Midcap 100",      "^NSMIDCP"),
    ("BANKNIFTY",    "Nifty Bank",            "^NSEBANK"),
    ("NIFTYIT",      "Nifty IT",              "^CNXIT"),
    ("NIFTYPHARMA",  "Nifty Pharma",          "^CNXPHARMA"),
    ("NIFTYAUTO",    "Nifty Auto",            "^CNXAUTO"),
    ("NIFTYFMCG",    "Nifty FMCG",            "^CNXFMCG"),
    ("NIFTYINFRA",   "Nifty Infrastructure",  "^CNXINFRA"),
    ("NIFTYENERGY",  "Nifty Energy",          "^CNXENERGY"),
    ("NIFTYMETAL",   "Nifty Metal",           "^CNXMETAL"),
    ("NIFTYDEFENCE", "Nifty India Defence",   "NIFTYDEFENCE.NS"),
]

# ── RSS feed registry ──────────────────────────────────────────────────────────
RSS_FEEDS = [
    # (feed_id, display_name, url, priority, category)
    ("nse_ann",   "NSE Corporate Announcements", "https://www.nseindia.com/rss/corporatean.xml",           1, "EXCHANGE"),
    ("bse_corp",  "BSE Corporate Filings",       "https://www.bseindia.com/Rss/RssCorpActions.aspx",       1, "EXCHANGE"),
    ("nse_board", "NSE Board Meeting Notices",   "https://www.nseindia.com/rss/boardmeetings.xml",         1, "EXCHANGE"),
    ("et_mkt",    "ET Markets",                  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", 2, "NEWS"),
    ("bs_mkt",    "Business Standard Markets",   "https://www.business-standard.com/rss/markets-106.rss",  2, "NEWS"),
    ("mint_mkt",  "Mint Markets",                "https://www.livemint.com/rss/markets",                   2, "NEWS"),
    ("mc_mkt",    "Moneycontrol Markets",        "https://www.moneycontrol.com/rss/marketreports.xml",     2, "NEWS"),
    ("rbi",       "RBI Press Releases",          "https://rbi.org.in/scripts/rss.aspx?Id=316",             3, "REGULATOR"),
    ("sebi",      "SEBI Circulars",              "https://www.sebi.gov.in/sebi_data/rss.xml",              3, "REGULATOR"),
    ("pib",       "PIB Government News",         "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", 3, "MACRO"),
]
