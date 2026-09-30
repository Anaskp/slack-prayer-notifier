"""
Azan reminder for Slack (Workflow Builder webhook).

Sends 2 messages per prayer:
  - Asr Azan     -> 30 min before + 10 min before  (Dhuhr ending)
  - Maghrib Azan -> 30 min before + 10 min before  (Asr ending)

Run once per day, sometime before the first alert (e.g. 2:00 PM IST).
The script fetches today's times, waits until each alert, sends it, and exits.

Env vars:
  SLACK_WEBHOOK_URL  (required) Workflow Builder webhook URL
  DRY_RUN=1          (optional) print messages instead of sending
  TEST_NOW=1         (optional) send all 4 messages immediately (for testing)
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------- CONFIG ----------------
LATITUDE = 11.2588         # Kozhikode
LONGITUDE = 75.7804
METHOD = 1                 # 1 = University of Islamic Sciences, Karachi
SCHOOL = 0                 # 0 = Shafi'i (standard Asr), 1 = Hanafi
ADJUST_MINUTES = 0         # +/- minutes to match your local masjid
TZ = timezone(timedelta(hours=5, minutes=30))  # IST
LATE_GRACE_MINUTES = 5     # if job starts late, still send alerts up to this late
# ----------------------------------------

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
DRY_RUN = os.environ.get("DRY_RUN") == "1"
TEST_NOW = os.environ.get("TEST_NOW") == "1"


def log(msg):
    print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fetch_timings(today):
    url = (
        f"https://api.aladhan.com/v1/timings/{today:%d-%m-%Y}"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&method={METHOD}&school={SCHOOL}&timezonestring=Asia/Kolkata"
    )
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.load(r)
            return data["data"]["timings"]
        except Exception as e:
            log(f"Fetch attempt {attempt} failed: {e}")
            time.sleep(10 * attempt)
    raise SystemExit("Could not fetch prayer times.")


def to_dt(today, hhmm):
    h, m = map(int, hhmm[:5].split(":"))  # handles "15:32" or "15:32 (IST)"
    dt = datetime(today.year, today.month, today.day, h, m, tzinfo=TZ)
    return dt + timedelta(minutes=ADJUST_MINUTES)


def fmt(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def send(message):
    if DRY_RUN:
        log(f"[DRY RUN] {message}")
        return
    body = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        WEBHOOK_URL, data=body, headers={"Content-Type": "application/json"}
    )
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                log(f"Sent ({r.status}): {message}")
                return
        except Exception as e:
            log(f"Send attempt {attempt} failed: {e}")
            time.sleep(5 * attempt)
    log("Giving up on this message.")


def main():
    if not WEBHOOK_URL and not DRY_RUN:
        raise SystemExit("SLACK_WEBHOOK_URL is not set.")

    today = datetime.now(TZ).date()
    t = fetch_timings(today)
    asr = to_dt(today, t["Asr"])
    maghrib = to_dt(today, t["Maghrib"])
    log(f"Today: Asr {fmt(asr)}, Maghrib {fmt(maghrib)}")

    alerts = [
        (asr - timedelta(minutes=30),
         f"🕌 *Asr Azan in 30 minutes* ({fmt(asr)})\nPray Dhuhr if you haven't yet."),
        (asr - timedelta(minutes=10),
         f"⏰ *Only 10 minutes left for Dhuhr!*\nAsr Azan at {fmt(asr)}."),
        (maghrib - timedelta(minutes=30),
         f"🕌 *Maghrib Azan in 30 minutes* ({fmt(maghrib)})\nPray Asr if you haven't yet."),
        (maghrib - timedelta(minutes=10),
         f"⏰ *Only 10 minutes left for Asr!*\nMaghrib Azan at {fmt(maghrib)}."),
    ]

    for when, message in alerts:
        if TEST_NOW:
            send(message)
            continue
        now = datetime.now(TZ)
        if now > when + timedelta(minutes=LATE_GRACE_MINUTES):
            log(f"Skipped (too late): {message.splitlines()[0]}")
            continue
        wait = (when - now).total_seconds()
        if wait > 0:
            log(f"Waiting until {fmt(when)} ({int(wait // 60)} min)")
            time.sleep(wait)
        send(message)

    log("Done for today.")


if __name__ == "__main__":
    main()
