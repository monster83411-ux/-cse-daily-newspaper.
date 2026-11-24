"""llm.py - talks to the AI services. Tries Gemini first, then OpenRouter's free models (fallback chain)."""

import json
import re
import time

import requests

import config

USE_FAKE = False  # demo mode switches this on so no keys are needed
_dead = set()  # providers whose key was rejected (do not retry them)
_exhausted = False  # True once EVERY model has failed (circuit breaker)


class LLMError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _post(url, headers, body):
    r = requests.post(url, headers=headers, json=body, timeout=90)
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}", r.status_code)
    return r.json()


def call_gemini(model, system, prompt):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    headers = {
        "x-goog-api-key": config.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    data = _post(url, headers, body)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError):
        raise LLMError("Unexpected Gemini reply: " + str(data)[:200])


def call_openrouter(model, system, prompt):
    """OpenRouter's free models. We put the rules and the news into ONE user message,
    because some free models refuse a separate 'system' message."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": "Bearer " + config.OPENROUTER_API_KEY,
        "Content-Type": "application/json",
        "X-Title": "CSE Daily Newspaper",
    }
    body = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": system + "\n\n" + prompt}],
    }
    data = _post(url, headers, body)
    if data.get("error"):  # OpenRouter sometimes reports errors inside a normal 200 reply
        err = data["error"]
        code = err.get("code") if isinstance(err, dict) else None
        raise LLMError(
            "OpenRouter error: " + str(err)[:200], code if isinstance(code, int) else None
        )
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError("Unexpected OpenRouter reply: " + str(data)[:200])


def free_openrouter_models(limit=12):
    """Names of the models that are free right now (the list changes often). No key needed."""
    r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
    r.raise_for_status()
    free = [
        m
        for m in r.json().get("data", [])
        if str(m.get("pricing", {}).get("prompt")) == "0"
        and str(m.get("pricing", {}).get("completion")) == "0"
    ]
    free.sort(key=lambda m: m.get("context_length") or 0, reverse=True)
    return [m["id"] for m in free[:limit]]


def chain():
    """The ordered list of (provider, model, function, pause_seconds_after_success)."""
    c = []
    if config.GEMINI_API_KEY:
        c += [("Gemini", m, call_gemini, 7) for m in config.GEMINI_MODELS]
    if config.OPENROUTER_API_KEY:  # free models: 20 requests/minute, 50 per day
        c += [("OpenRouter", m, call_openrouter, 4) for m in config.OPENROUTER_MODELS]
    return c


def _fake_reply(prompt):
    ids = re.findall(r"^\[(\d+)\] TITLE: (.*)$", prompt, flags=re.M)
    return json.dumps(
        {
            "stories": [
                {
                    "id": int(i),
                    "headline": t.replace("DEMO: ", "")[:80],
                    "body": "This is a demo story. The real AI writes a few simple sentences here.",
                }
                for i, t in ids
            ]
        }
    )


def ask_llm(system, prompt):
    """Return the AI's text, or None if every model failed."""
    global _exhausted
    if USE_FAKE:
        return _fake_reply(prompt)
    if _exhausted:  # AI is down: do not waste minutes retrying for each section
        return None
    for provider, model, fn, pause in chain():
        if provider in _dead:
            continue
        for attempt in (1, 2):
            try:
                text = fn(model, system, prompt)
                if not text.strip():
                    raise LLMError("empty reply")
                time.sleep(pause)
                return text
            except LLMError as e:
                print(f"    {provider}/{model} attempt {attempt}: {e}")
                if e.status in (401, 402, 403):  # key is wrong -> skip this provider
                    _dead.add(provider)
                    break
                if e.status in (400, 404):  # bad model name -> try next model
                    break
            except requests.RequestException as e:
                print(f"    {provider}/{model} attempt {attempt}: network error {e}")
            time.sleep(10 * attempt)  # wait 10s, then 20s (backoff)
    print("    all AI models failed - the rest of today's paper will use plain text")
    _exhausted = True
    return None


def test_all():
    """'test-llm' mode: ask every model to say OK and print what happened."""
    if not chain():
        print(
            "No API keys found. Add GEMINI_API_KEY and/or OPENROUTER_API_KEY as secrets."
        )
        return False
    good = 0
    for provider, model, fn, _ in chain():
        try:
            out = fn(model, "Reply with the single word OK.", "ping").strip()[:30]
            print(f"  WORKS   {provider:<7} {model}  -> {out!r}")
            good += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED  {provider:<7} {model}  -> {str(e)[:150]}")
    if config.GEMINI_API_KEY:
        try:
            r = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": config.GEMINI_API_KEY},
                timeout=30,
            )
            names = [m["name"].replace("models/", "") for m in r.json().get("models", [])]
            print(
                "  Gemini models your key can use:",
                ", ".join(n for n in names if "flash" in n)[:600],
            )
        except Exception as e:  # noqa: BLE001
            print("  Could not list Gemini models:", str(e)[:100])
    if config.OPENROUTER_API_KEY:
        try:
            print(
                "  Free OpenRouter models right now:",
                ", ".join(free_openrouter_models())[:600],
            )
        except Exception as e:  # noqa: BLE001
            print("  Could not list OpenRouter free models:", str(e)[:100])
    print(f"{good} model(s) working.")
    return good > 0
