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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from bs4 import BeautifulSoup

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
        db = SessionLocal()
        total_new = 0
        try:
            for feed_cfg in RSS_FEEDS:
                selectors: list[str] = feed_cfg.get("selectors", [])  # type: ignore[assignment]
                articles = await self._fetch_feed(feed_cfg["url"], feed_cfg["source"])

                for article in articles:
                    # Deduplicate by link
                    exists = (
                        db.query(EnergyNews)
                        .filter(EnergyNews.link == article["link"])
                        .first()
                    )
                    if exists:
                        continue

                    # Scrape full article when the feed only gave a snippet
                    needs_scrape = article.pop("_needs_scrape", False)
                    if needs_scrape:
                        await asyncio.sleep(_SCRAPE_DELAY)
                        scraped = await self._scrape_article(article["link"], selectors)
                        if scraped and not _is_truncated(scraped):
                            article["summary"] = scraped

                    record = EnergyNews(
                        title=article["title"],
                        link=article["link"],
                        source=article["source"],
                        published_at=article["published_at"],
                        summary=article["summary"],
                        fetched_at=datetime.now(timezone.utc),
                    )
                    db.add(record)
                    total_new += 1

            db.commit()
            print(f"[NewsCollector] Stored {total_new} new article(s).")
        except Exception as exc:
            print(f"[NewsCollector] DB error: {exc}")
            db.rollback()
        finally:
            db.close()
