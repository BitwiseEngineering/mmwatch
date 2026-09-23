"""Fetch the EagleHerald PUBLIC MEETINGS digests.

Kept deliberately small and separate from parsing so the parser can be tested
without a network, and so a second meeting source (a city calendar, a county
calendar) slots in beside this one later.

Politeness: the paper rate-limits bursts of article fetches with a 429, so body
requests are paced and retried once. This mirrors civic-watch's rss adapter.
"""
import datetime
import html as html_mod
import re
import time

import feedparser
import requests

FEED_URL = ("https://www.ehextra.com/search/"
            "?f=rss&t=article&c=records&l=50&s=start_time&sd=desc")

# A UA that names the project and a contact. Municipal and news WAFs reject
# UA strings carrying a bare URL, so this is plain text on purpose.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) mmwatch/0.1 (civic transparency project)"

TIMEOUT = 30
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_DELAY = 5
BODY_DELAY = 4.0

_SESSION = requests.Session()

_DROP = re.compile(r"<(script|style|nav|footer|aside)\b.*?</\1>", re.S | re.I)
_ASSET_OPEN = re.compile(
    r"""<div[^>]*\bclass\s*=\s*["']?[^"'>]*asset-content[^"'>]*["']?[^>]*>""", re.I)
_DIV = re.compile(r"<(/?)div\b[^>]*>", re.I)
_TAGS = re.compile(r"<[^>]+>")


def _get(url):
    problem = None
    for attempt in (0, 1):
        try:
            resp = _SESSION.get(url, headers={"User-Agent": USER_AGENT},
                                timeout=TIMEOUT)
        except Exception as exc:
            problem = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code == 200:
                return resp
            problem = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUSES:
                break
        if attempt == 0:
            time.sleep(RETRY_DELAY)
    raise RuntimeError(f"fetch failed for {url}: {problem}")


def article_text(markup):
    """Story text only.

    The article block is followed, inside the same page, by a "Trending Now"
    rail of unrelated headlines. Walking div tags to the matching close keeps
    those headlines out -- they would otherwise read as meeting topics.
    """
    open_tag = _ASSET_OPEN.search(markup)
    if open_tag:
        depth, start = 1, open_tag.end()
        body = markup[start:]
        for tag in _DIV.finditer(markup, start):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                body = markup[start:tag.start()]
                break
    else:
        body = markup
    text = _TAGS.sub(" ", _DROP.sub(" ", body))
    return " ".join(html_mod.unescape(text).split())


def recent_digests(limit=1):
    """Yield (published_date, url, body_text) for recent PUBLIC MEETINGS items.

    Newest first. **The default is one article per run, on purpose.**

    The EagleHerald meters article access by session: the first article read
    returns the full text and later ones in the same session come back
    truncated to a preview (measured 2026-09-23 -- 1,910 characters vs 178).
    A daily build only needs the newest digest anyway, and the store accumulates
    history across runs, so reading one article a day is both sufficient and a
    normal amount of use. Raise `limit` only for a deliberate backfill, and
    expect the extra items to be previews.
    """
    feed = feedparser.parse(_get(FEED_URL).content)
    if not feed.entries:
        raise RuntimeError("records feed parsed but contained no entries")

    seen = 0
    for entry in feed.entries:
        if entry.get("title", "").strip().upper() != "PUBLIC MEETINGS":
            continue
        if seen >= limit:
            break
        url = entry.get("link", "")
        if not url:
            continue
        published = _entry_date(entry)
        if published is None:
            continue
        if seen:
            time.sleep(BODY_DELAY)
        seen += 1
        try:
            yield published, url, article_text(_get(url).text)
        except Exception as exc:
            print(f"warn: could not fetch digest body {url} ({exc})")


def _entry_date(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
    return None
