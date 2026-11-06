"""
Fetches energy/oil news from public RSS feeds and stores new articles.

Feeds used (no API key required):
  - EIA (US Energy Information Administration)
  - OilPrice.com
  - Rigzone
  - World Oil

For each article the collector:
  1. Prefers the full-text ``content:encoded`` field included by some feeds.
  2. Falls back to scraping the article page when the feed only supplies a
     truncated snippet (detected by a trailing ellipsis or very short text).
"""

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import SessionLocal
from models import EnergyNews

RSS_FEEDS = [
    {
        "url": "https://www.eia.gov/rss/todayinenergy.xml",
        "source": "EIA",
        # CSS selectors to try when scraping (first match wins)
        "selectors": [".field-items", ".body-copy", "article", ".node__content"],
    },
    {
        "url": "https://oilprice.com/rss/main",
        "source": "OilPrice.com",
        "selectors": [".article-content", "#articleContent", "article"],
    },
    {
        "url": "https://www.rigzone.com/news/rss/rigzone_latest.aspx",
        "source": "Rigzone",
        "selectors": [".news-article-body", ".article-body", "article"],
    },
]

# Trailing characters that indicate a truncated RSS summary
_TRUNCATION_RE = re.compile(r"[\u2026\.]{1,3}\s*$")

# Generic fallback selectors used when a source has no specific config
_GENERIC_SELECTORS = [
    "[itemprop='articleBody']",
    "article",
    ".article-content",
    ".post-content",
    ".entry-content",
    ".story-content",
    "main",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FuelTracker/1.0; +https://github.com/fueltracker)"
    )
}

# Seconds to wait between article-page requests (be polite)
_SCRAPE_DELAY = 1.0


def _parse_date(entry) -> datetime | None:
    """Extract a timezone-aware datetime from a feedparser entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def _strip_html(text: str | None) -> str | None:
    """Remove HTML tags and collapse whitespace."""
    if not text:
        return None
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return clean or None


def _is_truncated(text: str | None) -> bool:
    """Return True if the text looks like a cut-off RSS snippet."""
    if not text:
        return True
    if _TRUNCATION_RE.search(text):
        return True
    # Also treat very short text as truncated
    return len(text) < 300


def _extract_body(html: str, selectors: list[str]) -> str | None:
    """Parse *html* and return the text of the first matching selector."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove boilerplate nodes
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "figure"]):
        tag.decompose()

    for selector in selectors:
        nodes = soup.select(selector)
        if nodes:
            text = " ".join(n.get_text(separator=" ", strip=True) for n in nodes)
            text = re.sub(r"\s{2,}", " ", text).strip()
            if text:
                return text
    return None


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
MAX_TITLE = 1000
MAX_SUMMARY = 20000


def _clean_text(value: str | None, limit: int) -> str | None:
    """PostgreSQL rejects NUL characters; also drop other control characters and cap the length."""
    if value is None:
        return None
    return _CONTROL_CHARS.sub("", value)[:limit]


def clean_article(article: dict) -> dict:
    out = dict(article)
    out["title"] = _clean_text(article.get("title"), MAX_TITLE) or ""
    out["link"] = (_clean_text(article.get("link"), 2000) or "").strip()
    out["summary"] = _clean_text(article.get("summary"), MAX_SUMMARY)
    return out


def dedupe_batch(articles: list[dict]) -> list[dict]:
    """Keep the first article per link. The same link can appear twice in one run (two feeds,
    or twice in one feed), which used to violate the primary key at commit time."""
    seen: set[str] = set()
    out = []
    for article in articles:
        link = (article.get("link") or "").strip()
        if link and link not in seen:
            seen.add(link)
            out.append(article)
    return out


class NewsCollector:
    """Fetches RSS feeds and persists new energy news articles."""

    async def _fetch_feed(self, url: str, source: str) -> list[dict]:
        """Download and parse a single RSS feed; return list of article dicts."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=HEADERS, follow_redirects=True)
                response.raise_for_status()
                content = response.text
        except Exception as exc:
            print(f"[NewsCollector] Failed to fetch {source} ({url}): {exc}")
            return []

        feed = feedparser.parse(content)
        articles = []
        for entry in feed.entries:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", None)
            if not link or not title:
                continue

            # Prefer content:encoded (full text) when present
            full_via_feed: str | None = None
            for content_item in getattr(entry, "content", []):
                val = _strip_html(content_item.get("value"))
                if val and len(val) > (len(full_via_feed) if full_via_feed else 0):
                    full_via_feed = val

            rss_summary = _strip_html(
                getattr(entry, "summary", None) or getattr(entry, "description", None)
            )

            # Choose the best text available from the feed itself
            feed_text = (
                full_via_feed
                if full_via_feed and not _is_truncated(full_via_feed)
                else rss_summary
            )

            articles.append(
                {
                    "title": title.strip(),
                    "link": link.strip(),
                    "source": source,
                    "published_at": _parse_date(entry),
                    "summary": feed_text,
                    "_needs_scrape": _is_truncated(feed_text),
                }
            )
        return articles

    async def _scrape_article(self, url: str, selectors: list[str]) -> str | None:
        """Fetch an article page and extract its main text body."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=HEADERS, follow_redirects=True)
                response.raise_for_status()
                html = response.text
        except Exception as exc:
            print(f"[NewsCollector] Could not scrape {url}: {exc}")
            return None

        return _extract_body(html, selectors + _GENERIC_SELECTORS)

    async def fetch_and_store(self) -> None:
        """Fetch all feeds, then store every new article independently.

        Network work happens first with no database connection held open (scraping
        sleeps between requests, and an idle connection can be dropped by the server).
        Each article is then written in its own transaction with ON CONFLICT DO NOTHING,
        so a single bad article (duplicate link in the same run, a NUL character in
        scraped text, ...) can never roll back the good ones. Failures are counted and
        logged per source instead of silently losing the whole run.
        """
        fetched: list[tuple[dict, list[str], list[dict]]] = []
        for feed_cfg in RSS_FEEDS:
            selectors: list[str] = feed_cfg.get("selectors", [])  # type: ignore[assignment]
            articles = await self._fetch_feed(feed_cfg["url"], feed_cfg["source"])
            fetched.append((feed_cfg, selectors, articles))
            if not articles:
                print(
                    f"[NewsCollector] {feed_cfg['source']}: feed returned no articles"
                )

        batch = dedupe_batch([a for _, _, arts in fetched for a in arts])
        existing = self._existing_links([a["link"] for a in batch])
        new_articles = [a for a in batch if a["link"] not in existing]

        selectors_by_source = {cfg["source"]: sel for cfg, sel, _ in fetched}
        for article in new_articles:
            if article.pop("_needs_scrape", False):
                await asyncio.sleep(_SCRAPE_DELAY)
                scraped = await self._scrape_article(
                    article["link"], selectors_by_source.get(article["source"], [])
                )
                if scraped and not _is_truncated(scraped):
                    article["summary"] = scraped

        stored: dict[str, int] = defaultdict(int)
        failed: dict[str, int] = defaultdict(int)
        last_error = None
        for article in new_articles:
            try:
                if self._store_one(clean_article(article)):
                    stored[article["source"]] += 1
            except Exception as exc:  # one bad article must not stop the others
                failed[article["source"]] += 1
                last_error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"

        total = sum(stored.values())
        detail = ", ".join(f"{k} {v}" for k, v in sorted(stored.items())) or "none"
        print(f"[NewsCollector] Stored {total} new article(s) ({detail}).")
        if failed:
            print(
                f"[NewsCollector] WARNING: {sum(failed.values())} article(s) could not be "
                f"stored ({dict(failed)}); last error: {last_error}"
            )

    @staticmethod
    def _existing_links(links: list[str]) -> set[str]:
        if not links:
            return set()
        db = SessionLocal()
        try:
            return {
                row[0]
                for row in db.query(EnergyNews.link).filter(EnergyNews.link.in_(links))
            }
        finally:
            db.close()

    @staticmethod
    def _store_one(article: dict) -> bool:
        """Insert one article in its own transaction; False if it already existed."""
        db = SessionLocal()
        try:
            result = db.execute(
                pg_insert(EnergyNews)
                .values(
                    title=article["title"],
                    link=article["link"],
                    source=article["source"],
                    published_at=article["published_at"],
                    summary=article["summary"],
                    fetched_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(index_elements=["link"])
            )
            db.commit()
            return result.rowcount == 1
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
