"""alert.py - used by the workflow when a step BEFORE the robot crashes (for example the install).
Uses only the standard library, so it works even if installing libraries failed.
Usage: python3 alert.py "reason"."""

import os
import sys

import emailer
import monitor


def main():
    reason = " ".join(sys.argv[1:]) or "unknown reason"
    link = os.environ.get("RUN_URL", "")
    monitor.ping("/fail")
    emailer.send_alert(
        "CSE Daily FAILED",
        f"Today's newspaper could not be made.\n\nReason: {reason}\n"
        + (f"Details: {link}\n" if link else ""),
    )
    print("alert email sent")


if __name__ == "__main__":
    main()
