"""
Agent_Trader — News / RSS Harvest
Fetches from 10 RSS feeds. Tracks error_count per feed — auto-disables
feeds that fail 5+ consecutive times so harvest stays fast.
"""
import sys
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NEWS_LOOKBACK_DAYS, NEWS_JSON

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AgentTrader/1.0 (+https://github.com/yourname/agent-trader)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
_TIMEOUT = 15


def _fetch_feed(url: str) -> feedparser.FeedParserDict | None:
    """Fetch and parse a single RSS feed URL."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception as e:
        raise RuntimeError(str(e))


def _ticker_mentions(title: str, summary: str, active_tickers: list[str]) -> list[str]:
    """Return list of tickers mentioned in title or summary."""
    text = (title + " " + (summary or "")).upper()
    return [t for t in active_tickers if t in text]


def _publish_date(entry) -> str | None:
    """Extract and normalise publish date from feed entry."""
    for attr in ("published_parsed", "updated_parsed"):
        ts = getattr(entry, attr, None)
        if ts:
            try:
                import calendar
                dt = datetime.utcfromtimestamp(calendar.timegm(ts))
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def run_news(conn: sqlite3.Connection, run_id: str) -> dict:
    """Main entry — fetch all active RSS feeds and insert new items."""
    started      = datetime.now()
    total_new    = 0
    feeds_ok     = 0
    feeds_failed = 0
    cutoff       = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")

    active_tickers = [
        r[0] for r in conn.execute("SELECT ticker FROM stocks WHERE is_active=1").fetchall()
    ]
    print(f"Portfolio stocks: {len(active_tickers)}")

    existing_count = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE published_at > ?", (cutoff,)
    ).fetchone()[0]
    print(f"Existing news items (last {NEWS_LOOKBACK_DAYS}d): {existing_count}")

    feeds = conn.execute("""
        SELECT feed_id, display_name, url, priority, category, error_count
        FROM rss_feeds
        WHERE is_active = 1 AND (error_count < 5)
        ORDER BY priority, feed_id
    """).fetchall()

    all_items = []   # for JSON export

    for feed_id, name, url, priority, category, err_count in feeds:
        print(f"Fetching [{priority}] {name}…")
        try:
            parsed = _fetch_feed(url)
            entries = parsed.entries if parsed else []
            new_this_feed = 0

            for entry in entries:
                title    = getattr(entry, "title",   "") or ""
                summary  = getattr(entry, "summary", "") or ""
                link     = getattr(entry, "link",    "") or ""
                pub_date = _publish_date(entry)
                mentions = _ticker_mentions(title, summary, active_tickers)

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO news_items
                        (feed_id, title, summary, url, published_at,
                         tickers_mentioned, news_category)
                        VALUES (?,?,?,?,?,?,?)
                    """, (
                        feed_id, title[:500], summary[:2000],
                        link[:1000], pub_date,
                        json.dumps(mentions), category,
                    ))
                    if conn.execute("SELECT changes()").fetchone()[0] > 0:
                        new_this_feed += 1
                        all_items.append({
                            "feed_id": feed_id, "title": title,
                            "url": link, "published_at": pub_date,
                            "tickers_mentioned": mentions, "category": category,
                        })
                except Exception as e:
                    log.warning(f"Insert news item: {e}")

            conn.commit()
            # Reset error count on success
            conn.execute(
                "UPDATE rss_feeds SET error_count=0, last_success=datetime('now'), "
                "last_checked=datetime('now') WHERE feed_id=?", (feed_id,)
            )
            conn.commit()
            feeds_ok += 1
            total_new += new_this_feed
            print(f"  {new_this_feed} new entries")

        except Exception as e:
            log.warning(f"Feed fetch error [{feed_id}]: {e}")
            conn.execute(
                "UPDATE rss_feeds SET error_count=error_count+1, "
                "last_checked=datetime('now') WHERE feed_id=?", (feed_id,)
            )
            conn.commit()
            feeds_failed += 1
            print(f"  Feed error: {e}")

    # ── Write rss_news.json ────────────────────────────────────────────────────
    try:
        recent = conn.execute("""
            SELECT feed_id, title, summary, url, published_at,
                   tickers_mentioned, news_category
            FROM news_items
            WHERE published_at > ?
            ORDER BY published_at DESC
            LIMIT 200
        """, (cutoff,)).fetchall()

        export = [
            {
                "feed_id": r[0], "title": r[1], "summary": r[2],
                "url": r[3], "published_at": r[4],
                "tickers_mentioned": json.loads(r[5] or "[]"),
                "category": r[6],
            }
            for r in recent
        ]
        import os
        os.makedirs(os.path.dirname(NEWS_JSON), exist_ok=True)
        with open(NEWS_JSON, "w") as f:
            json.dump({"generated_at": datetime.now().isoformat(),
                       "count": len(export), "items": export}, f, indent=2)
    except Exception as e:
        log.warning(f"rss_news.json write failed: {e}")

    duration = (datetime.now() - started).total_seconds()
    print(f"News: {total_new} new items inserted")
    print(f"✔ news complete in {duration:.0f}s ({feeds_ok} feeds ok, {feeds_failed} failed)")
    return {
        "job": "news", "run_id": run_id,
        "status": "success" if feeds_failed == 0 else ("partial" if feeds_ok > 0 else "failed"),
        "stocks_updated": total_new, "stocks_failed": feeds_failed,
        "duration_secs": duration, "error_summary": None,
    }
