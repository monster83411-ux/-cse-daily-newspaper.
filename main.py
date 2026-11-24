"""main.py - the boss. Runs every step in order.  Usage: python main.py --mode live|demo|test-llm"""

import argparse
import datetime as dt
import os
import sys
import traceback
from zoneinfo import ZoneInfo

import config
import editor
import emailer
import llm
import monitor
import newspaper
import sources


def run(mode, send_email=True):
    if mode == "test-llm":
        return 0 if llm.test_all() else 1

    demo = mode == "demo"
    llm.USE_FAKE = demo
    now = dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    pretty = now.strftime("%A, %d %B %Y")
    print(f"=== CSE Daily | {pretty} | mode={mode} ===")

    # STEP 1 - collect
    print("Step 1: collecting news")
    if demo:
        raw, worked, failed = sources.demo_items(), 1, 0
    else:
        raw, worked, failed = sources.collect_all()
    if sum(len(v) for v in raw.values()) == 0:
        raise RuntimeError("No news could be collected from any source.")

    # STEP 2 - remove repeats
    print("Step 2: removing duplicates")
    seen_data, seen_titles = ({}, []) if demo else sources.load_seen()
    picked = {
        s: sources.pick_items(raw.get(s, []), s, seen_titles) for s in config.SECTIONS
    }

    # STEP 2b - fetch real article text for thin items so the AI has facts to use
    if not demo:
        print("Step 2b: reading article text for thin items")
        print(f"  enriched {sources.enrich_items(picked)} items")

    # STEP 3 - AI writes simple stories
    print("Step 3: writing stories")
    stories = {}
    for section, items in picked.items():
        stories[section] = editor.summarise_section(section, items) if items else []
        n_ai = sum(1 for s in stories[section] if s["ai"])
        print(f"  {section:<30} {len(stories[section])} stories ({n_ai} by AI)")
    total = sum(len(v) for v in stories.values())
    total_ai = sum(1 for v in stories.values() for s in v if s["ai"])

    # STEP 4 - build the PDF
    print("Step 4: building PDF")
    os.makedirs("output", exist_ok=True)
    notes = []
    if total <= 5:
        notes.append(
            "Quiet news day - fewer stories than usual. We do not pad the paper."
        )
    if failed > worked:
        notes.append(
            "Some news sources were unavailable today, so this edition may be thinner than usual."
        )
    if demo:
        notes.append("DEMO EDITION - fake stories used to test the system.")
    pdf = newspaper.build_pdf(
        f"output/CSE_Daily_{now:%Y-%m-%d}.pdf", stories, pretty, notes
    )
    print("  saved", pdf)

    # STEP 5 - email
    if send_email:
        print("Step 5: sending email")
        heads = [s["headline"] for v in stories.values() for s in v][:6]
        body = (
            f"Good morning!\n\nYour CSE Daily for {pretty} is attached as a PDF.\n\nTop headlines:\n"
            + "\n".join(f" - {h}" for h in heads)
            + f"\n\nSources working: {worked} of {worked + failed}. Stories written by AI: {total_ai} of {total}.\n"
        )
        emailer.send_pdf(
            ("[DEMO] " if demo else "") + f"CSE Daily - {now:%d %b %Y}", body, pdf
        )
        print("  email sent")

    # STEP 6 - remember today's stories (only after success, and never in demo)
    if not demo:
        sources.save_seen(
            seen_data,
            dt.date.today().isoformat(),
            [sources.norm(s["title_key"]) for v in stories.values() for s in v],
        )
    if mode == "live":
        monitor.ping()  # heartbeat: "I finished OK" (only if HEALTHCHECK_URL is set)
    print("=== done ===")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="live", choices=["live", "demo", "test-llm"])
    p.add_argument(
        "--no-email", action="store_true", help="build the PDF but do not email it"
    )
    a = p.parse_args()
    try:
        sys.exit(run(a.mode, send_email=not a.no_email))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        if a.mode == "live":
            monitor.ping("/fail")
        if a.mode == "live" and not a.no_email:
            try:
                emailer.send_alert(
                    "CSE Daily FAILED",
                    f"Today's newspaper could not be made.\n\nReason: {e}\n"
                    "Open GitHub > Actions > latest run to see the log.",
                )
            except Exception as e2:  # noqa: BLE001
                print("Could not send alert email either:", e2)
        sys.exit(1)


if __name__ == "__main__":
    main()
