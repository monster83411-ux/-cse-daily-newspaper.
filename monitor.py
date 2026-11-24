"""monitor.py - optional 'heartbeat': tells healthchecks.io the robot finished (or failed).
If no ping arrives on time, healthchecks.io emails YOU. Uses only the standard library."""

import urllib.request

import config


def ping(suffix=""):
    """suffix is '' for success or '/fail' for failure. Never raises."""
    if not config.HEALTHCHECK_URL:
        return False
    try:
        urllib.request.urlopen(config.HEALTHCHECK_URL.rstrip("/") + suffix, timeout=10)
        return True
    except Exception as e:  # noqa: BLE001
        print("  heartbeat ping failed (not important):", e)
        return False
