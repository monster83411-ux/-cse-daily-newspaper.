"""sources.py - collects raw news and removes duplicates."""

import datetime as dt
import html
import json
import os
import re
import time
from urllib.parse import urlparse
from difflib import SequenceMatcher

import feedparser
import requests

import config

UTC = dt.timezone.utc
HEADERS = {"User-Agent": "CSE-Daily-Newspaper/1.0 (student project)"}
HN = "https://hacker-news.firebaseio.com/v0"
SEEN_FILE = "seen.json"


# ---------- small helpers ----------
def http_get(url, params=None, headers=None, tries=3, timeout=20):
    """Download a web address. Retries up to 3 times, waiting 1s, 2s between tries."""
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2**i)


def clean_text(s, limit=400):
    """Remove HTML tags, fix &amp; style codes, squeeze spaces, cut to a limit."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "..."
    return s


def make_item(section, title, summary, link, source, published, score=0):
    return {
        "section": section,
        "title": clean_text(title, 200),
        "summary": clean_text(summary, 400),
        "link": link,
        "source": source,
        "published": published,
        "score": score,
    }


def _when(entry):
    tm = entry.get("published_parsed") or entry.get("updated_parsed")
    return dt.datetime(*tm[:6], tzinfo=UTC) if tm else dt.datetime.now(UTC)


# ---------- one fetcher per kind of source ----------
def parse_feed(content, section, label, hours, gnews=False):
    """Turn raw RSS/XML text into a list of items (kept separate so it is easy to test)."""
    cutoff = dt.datetime.now(UTC) - dt.timedelta(hours=hours)
    items = []
    for e in feedparser.parse(content).entries[:40]:
        published = _when(e)
        if published < cutoff:
            continue
        title, summary, source = e.get("title", ""), e.get("summary", ""), label
        if (
            gnews
        ):  # Google News: "Headline - Publisher"; its summary just repeats the title
            source = (e.get("source") or {}).get("title") or label
            if title.endswith(" - " + source):
                title = title[: -len(source) - 3]
            summary = ""
        items.append(
            make_item(section, title, summary, e.get("link", ""), source, published)
        )
    return items[: config.PER_SOURCE_CAP]


def fetch_rss(section, url, label, hours, gnews=False):
    return parse_feed(http_get(url).content, section, label, hours, gnews)


def fetch_gnews(section, url, label, hours):
    return fetch_rss(section, url, label, hours, gnews=True)


def fetch_hn(section, url, label, hours, kind="top"):
    ids = http_get(f"{HN}/{'topstories' if kind == 'top' else 'jobstories'}.json").json()[
        :25
    ]
    cutoff = dt.datetime.now(UTC) - dt.timedelta(hours=hours)
    items = []
    for i in ids:
        try:
            d = http_get(f"{HN}/item/{i}.json").json()
        except requests.RequestException:
            continue
        if not d or d.get("dead") or d.get("deleted"):
            continue
        published = dt.datetime.fromtimestamp(d.get("time", 0), UTC)
        if published < cutoff:
            continue
        if kind == "jobs" and not re.search(
            config.JOB_KEYWORDS, d.get("title", ""), re.I
        ):
            continue  # not an engineering job
        link = d.get("url") or f"https://news.ycombinator.com/item?id={i}"
        if kind == "top":
            summary = f"Hacker News post with {d.get('score', 0)} points and {d.get('descendants', 0)} comments."
        else:
            summary = d.get("text") or "Job post from the Hacker News jobs board."
        items.append(
            make_item(
                section,
                d.get("title", ""),
                summary,
                link,
                label,
                published,
                d.get("score", 0),
            )
        )
        if len(items) >= config.PER_SOURCE_CAP:
            break
    return items


def fetch_hn_top(section, url, label, hours):
    return fetch_hn(section, url, label, hours, "top")


def fetch_hn_jobs(section, url, label, hours):
    return fetch_hn(section, url, label, hours, "jobs")


def fetch_devto(section, url, label, hours):
    data = http_get(
        "https://dev.to/api/articles", params={"top": 1, "per_page": 10}
    ).json()
    items = []
    for a in data:
        published = dt.datetime.fromisoformat(
            a["published_timestamp"].replace("Z", "+00:00")
        )
        items.append(
            make_item(
                section,
                a["title"],
                a.get("description", ""),
                a["url"],
                label,
                published,
                a.get("public_reactions_count", 0),
            )
        )
    return items[: config.PER_SOURCE_CAP]


def fetch_github(section, url, label, hours):
    """GitHub has no official 'trending' list, so we ask: which NEW repos got most stars this week?"""
    since = (dt.datetime.now(UTC) - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = "Bearer " + config.GITHUB_TOKEN
    r = http_get(
        "https://api.github.com/search/repositories",
        headers=headers,
        params={
            "q": f"created:>{since} stars:>20",
            "sort": "stars",
            "order": "desc",
            "per_page": 15,
        },
    )
    items = []
    for repo in r.json().get("items", []):
        text = (
            f"{repo.get('description') or 'No description given.'} "
            f"Main language: {repo.get('language') or 'not stated'}. "
            f"Stars so far: {repo.get('stargazers_count', 0)}."
        )
        published = dt.datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
        items.append(
            make_item(
                section,
                repo["full_name"],
                text,
                repo["html_url"],
                "GitHub",
                published,
                repo.get("stargazers_count", 0),
            )
        )
    return items[: config.PER_SOURCE_CAP]


FETCHERS = {
    "rss": fetch_rss,
    "gnews": fetch_gnews,
    "hn_top": fetch_hn_top,
    "hn_jobs": fetch_hn_jobs,
    "devto": fetch_devto,
    "github": fetch_github,
}


def collect_all():
    """Visit every source. One broken source must never stop the others."""
    by_section = {s: [] for s in config.SECTIONS}
    worked, failed = 0, 0
    for section, kind, arg, label, hours in config.SOURCES:
        try:
            got = FETCHERS[kind](section, arg, label, hours)
            by_section[section] += got
            worked += 1
            print(f"  OK     {label:<18} {section:<30} {len(got)} items")
        except (
            Exception
        ) as e:  # noqa: BLE001 - we really do want to catch everything here
            failed += 1
            print(f"  FAILED {label:<18} {section:<30} {type(e).__name__}: {str(e)[:80]}")
    return by_section, worked, failed


# ---------- real article text (so the AI has facts, not just a headline) ----------
def enrich_items(picked, limit=None):
    """For short items, download the article and keep its first ~700 characters.
    Skips Google News links (they are redirect pages) and never stops the run if a page fails.
    """
    try:
        import trafilatura
    except ImportError:
        print("  (trafilatura not installed - skipping article text)")
        return 0
    limit = config.MAX_ENRICH if limit is None else limit
    done = 0
    for items in picked.values():
        for it in items:
            if done >= limit:
                return done
            host = urlparse(it["link"]).netloc
            if (
                len(it["summary"]) >= 200
                or not host
                or "news.google.com" in host
                or host in ("news.ycombinator.com", "github.com")
            ):
                continue
            try:
                text = trafilatura.extract(http_get(it["link"], tries=1, timeout=12).text)
            except Exception:  # noqa: BLE001 - a broken page must never stop the paper
                continue
            if text and len(text) > 200:
                it["summary"] = clean_text(text, 700)
                done += 1
    return done


# ---------- duplicates ----------
def norm(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def is_similar(a, b):
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.8


def load_seen():
    """seen.json looks like {"2026-11-19": ["title one", ...]}. Returns (dict, flat list)."""
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    cutoff = (dt.date.today() - dt.timedelta(days=config.SEEN_DAYS)).isoformat()
    data = {d: t for d, t in data.items() if d >= cutoff}
    return data, [t for titles in data.values() for t in titles]


def save_seen(data, day, new_titles):
    data[day] = sorted(set(data.get(day, []) + new_titles))
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def pick_items(items, section, seen_titles):
    """Sort, drop repeats (today's and earlier days'), keep only the best few."""
    if section in config.SORT_BY_SCORE:
        items = sorted(items, key=lambda x: x["score"], reverse=True)
    else:
        items = sorted(items, key=lambda x: x["published"], reverse=True)
    kept, kept_keys = [], []
    for it in items:
        key = norm(it["title"])
        if not key or any(is_similar(key, k) for k in kept_keys + seen_titles):
            continue
        kept.append(it)
        kept_keys.append(key)
    return kept[: config.MAX_STORIES.get(section, 5)]


# ---------- fake data so you can test without internet or keys ----------
def demo_items():
    now = dt.datetime.now(UTC)

    def d(section, title, text, source="Demo Source"):
        return make_item(
            section, "DEMO: " + title, text, "https://example.com/demo", source, now, 50
        )

    return {
        "Companies & Products": [
            d(
                "Companies & Products",
                "Acme launches a free code editor",
                "Acme Corp released a new code editor. It is free for students. It supports 12 languages.",
            ),
            d(
                "Companies & Products",
                "Café Labs & Co. ships <beta> tool \U0001f680 नमस्ते",
                "This line has an ampersand, angle brackets, an emoji and Hindi text to test the PDF.",
            ),
        ],
        "Layoffs & Industry Moves": [
            d(
                "Layoffs & Industry Moves",
                "Example Tech cuts 500 jobs",
                "Example Tech said it will lay off 500 workers to focus on AI projects.",
            )
        ],
        "Jobs & Internships": [
            d(
                "Jobs & Internships",
                "Sample Inc hires summer interns",
                "Sample Inc is hiring 20 software interns. Skills: Python, SQL. Apply by 30 December.",
            )
        ],
        "Free Tools & Student Offers": [
            d(
                "Free Tools & Student Offers",
                "Cloud provider gives 6 months free to students",
                "Students can get 6 months of free cloud credits with a college email.",
            )
        ],
        "New Inventions & Research": [
            d(
                "New Inventions & Research",
                "Researchers build a faster chip",
                "A university team built a chip that is 3 times faster than older designs.",
            )
        ],
        "Trending GitHub Repositories": [
            d(
                "Trending GitHub Repositories",
                "demo-user/awesome-notes",
                "A small tool to organise study notes. Main language: Python. Stars so far: 420.",
                "GitHub",
            )
        ],
        "Community Buzz (Social)": [
            d(
                "Community Buzz (Social)",
                "Why is my compiler slow? A long discussion",
                "Hacker News post with 310 points and 120 comments.",
                "Hacker News",
            )
        ],
    }
