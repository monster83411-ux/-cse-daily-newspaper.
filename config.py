"""config.py - ALL settings live here. Change things here, not in other files."""

import os

# ---- Secrets (read from environment variables; never typed into code) ----
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # GitHub gives this automatically
HEALTHCHECK_URL = os.environ.get(
    "HEALTHCHECK_URL", ""
).strip()  # optional heartbeat monitor


# ---- AI models, tried in this order (first one that works wins) ----
# Model names change over time. You can change them WITHOUT editing code:
# GitHub > Settings > Secrets and variables > Actions > Variables tab >
# New variable named GEMINI_MODELS (or OPENROUTER_MODELS), value = names separated by commas.
# Check current names: https://ai.google.dev/gemini-api/docs/models
def _names(var, default):
    given = [x.strip() for x in os.environ.get(var, "").split(",") if x.strip()]
    return given or default


GEMINI_MODELS = _names(
    "GEMINI_MODELS",
    ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"],
)
# "openrouter/free" is OpenRouter's router: it picks a working free model for each request.
OPENROUTER_MODELS = _names("OPENROUTER_MODELS", ["openrouter/free"])

# ---- Newspaper rules ----
SEEN_DAYS = 4  # do not repeat a story seen in the last N days
PER_SOURCE_CAP = 8  # take at most this many items from one source
MAX_ENRICH = 12  # fetch real article text for at most this many thin items
# Hacker News job posts are kept only if they mention one of these words
JOB_KEYWORDS = (
    r"engineer|developer|software|backend|front.?end|full.?stack|devops|sre|"
    r"machine learning|\bml\b|\bai\b|data|security|intern|platform|infrastructure|mobile|cloud"
)
SECTIONS = [  # the order they appear in the newspaper
    "Companies & Products",
    "Layoffs & Industry Moves",
    "Jobs & Internships",
    "Free Tools & Student Offers",
    "New Inventions & Research",
    "Trending GitHub Repositories",
    "Community Buzz (Social)",
]
MAX_STORIES = {  # max stories per section (default 5)
    "Jobs & Internships": 8,
    "Trending GitHub Repositories": 6,
    "Community Buzz (Social)": 6,
}
SORT_BY_SCORE = {"Trending GitHub Repositories", "Community Buzz (Social)"}


def gnews(query):
    """Build a Google News search address (RSS feed, India edition)."""
    from urllib.parse import quote_plus

    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:2d")
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )


# ---- Where news comes from ----
# Each line: (section, kind, address, label, hours_back)
# The last number = ignore news older than that many hours (30 = 24h + slack for late runs).
# kind: rss | gnews (Google News search) | hn_top | hn_jobs | devto | github
PRODUCTS, LAYOFFS, JOBS, FREE, RESEARCH, GITHUB, BUZZ = SECTIONS
# fmt: off
SOURCES = [
    (PRODUCTS, "rss", "https://techcrunch.com/feed/", "TechCrunch", 30),
    (PRODUCTS, "rss", "https://feeds.arstechnica.com/arstechnica/technology-lab", "Ars Technica", 30),
    (PRODUCTS, "rss", "https://www.theverge.com/rss/index.xml", "The Verge", 30),
    (LAYOFFS, "gnews", gnews("tech layoffs software engineers"), "Google News", 48),
    (LAYOFFS, "gnews", gnews("IT company layoffs hiring freeze"), "Google News", 48),
    (JOBS, "gnews", gnews("software engineering internship students hiring"), "Google News", 72),
    (JOBS, "gnews", gnews("freshers hiring software developer India"), "Google News", 72),
    (JOBS, "gnews", gnews("off campus drive freshers software engineer"), "Google News", 72),
    (JOBS, "gnews", gnews("internship stipend engineering students India"), "Google News", 72),
    (JOBS, "hn_jobs", "", "Hacker News Jobs", 168),
    (FREE, "gnews", gnews('"free for students" OR "free tier" developers'), "Google News", 96),
    (FREE, "gnews", gnews("free course OR free certification computer science"), "Google News", 96),
    (RESEARCH, "rss", "https://arstechnica.com/ai/feed/", "Ars Technica AI", 48),
    (RESEARCH, "gnews", gnews("computer science research breakthrough chip quantum AI"), "Google News", 72),
    (GITHUB, "github", "", "GitHub", 0),
    (BUZZ, "hn_top", "", "Hacker News", 48),
    (BUZZ, "devto", "", "DEV Community", 48),
    (BUZZ, "rss", "https://lobste.rs/rss", "Lobsters", 48),
]
# fmt: on
