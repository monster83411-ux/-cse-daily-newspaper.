"""merge_seen.py - combines two seen.json files (used when GitHub's copy moved ahead of ours).
Usage: python3 merge_seen.py MINE.json THEIRS_AND_OUTPUT.json
Result: for every day, the union of both lists of titles. Old days are dropped.
Uses only the standard library."""

import datetime as dt
import json
import sys

import config


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def merge(a, b):
    cutoff = (dt.date.today() - dt.timedelta(days=config.SEEN_DAYS)).isoformat()
    out = {}
    for day in sorted(set(a) | set(b)):
        if day >= cutoff:
            out[day] = sorted(set(a.get(day, [])) | set(b.get(day, [])))
    return out


if __name__ == "__main__":
    mine, theirs = sys.argv[1], sys.argv[2]
    merged = merge(read(mine), read(theirs))
    with open(theirs, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=1, ensure_ascii=False)
    print(
        f"seen.json merged: {sum(len(v) for v in merged.values())} titles over {len(merged)} days"
    )
