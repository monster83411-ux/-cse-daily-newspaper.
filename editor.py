"""editor.py - asks the AI to write stories, then CHECKS the AI's work."""

import json
import re

import llm
import prompts


def parse_stories(reply, n_items):
    """Pull the list of stories out of the AI's reply. Raises ValueError if it is unusable."""
    text = re.sub(r"```(?:json)?", "", reply).strip()
    starts = [p for p in (text.find("{"), text.find("[")) if p != -1]
    if not starts:
        raise ValueError("no JSON found")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    data = json.loads(text[start : end + 1])
    if isinstance(data, dict):
        data = data.get("stories")
    if not isinstance(data, list):
        raise ValueError("no stories list")
    good, used = [], set()
    for s in data:
        try:
            i = int(s["id"])
            head, body = str(s["headline"]).strip(), str(s["body"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= i <= n_items and i not in used and head and body:
            used.add(i)
            good.append({"id": i, "headline": head[:140], "body": body[:700]})
    return good


def _numbers(text):
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,.]*", text)}


def numbers_ok(ai_text, item):
    """Guard against invented facts: every number the AI wrote must exist in the source text."""
    return _numbers(ai_text) <= _numbers(item["title"] + " " + item["summary"])


def plain_story(item):
    """Used when the AI is down or breaks a rule: show the original words, shortened."""
    body = item["summary"] or "Open the link to read the full story."
    return {
        "headline": item["title"],
        "body": body,
        "source": item["source"],
        "link": item["link"],
        "ai": False,
        "title_key": item["title"],
    }


def summarise_section(section, items):
    """Return finished stories for one section. Never raises; always returns something."""
    reply = llm.ask_llm(prompts.SYSTEM, prompts.build_user_prompt(section, items))
    stories = []
    try:
        parsed = parse_stories(reply, len(items)) if reply else None
    except (ValueError, json.JSONDecodeError) as e:
        print(f"    could not read AI reply ({e}); using plain text")
        parsed = None
    if parsed is None:
        return [plain_story(it) for it in items]
    for s in parsed:
        item = items[s["id"] - 1]
        if numbers_ok(s["headline"] + " " + s["body"], item):
            stories.append(
                {
                    "headline": s["headline"],
                    "body": s["body"],
                    "source": item["source"],
                    "link": item["link"],
                    "ai": True,
                    "title_key": item["title"],
                }
            )
        else:
            print(f"    number guard blocked an AI story: {item['title'][:50]}")
            stories.append(plain_story(item))
    if (
        not stories
    ):  # AI skipped everything: show the top items rather than an empty section
        stories = [plain_story(it) for it in items[:3]]
    return stories
