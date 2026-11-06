"""Garmin Connect provider.

Uses python-garminconnect, which logs in with your normal Garmin Connect
email + password (there is no official personal-use API). Tokens are cached in
~/.garminconnect so you only log in again when they expire (months).

.env:
  GARMIN_EMAIL=
  GARMIN_PASSWORD=

Extra flags (via scripts/sync.py):
  --with-details   per-second streams -> data/raw/garmin/details/{id}.json
                   (needed by scripts/garmin/run-splits.py and garmin-audit.py)
  --with-fit       original FIT files -> data/raw/garmin/fit/{id}.fit
  --backfill       both of the above + raw daily wellness JSON, with polite delays

If Garmin asks for MFA / captcha, log in once at https://connect.garmin.com in
a browser, then re-run. If tokens go stale after a long gap, delete
~/.garminconnect/ and retry once.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datastore import (RAW_DIR, ProviderAuthError, ProviderNotConfigured,  # noqa: E402
                       activity, wellness)

NAME = "garmin"
CLOUD_SAFE = True  # can run unattended on the bot host
TOKEN_DIR = Path.home() / ".garminconnect"
ARCHIVE = RAW_DIR / "garmin"
DETAILS_DIR = ARCHIVE / "details"
FIT_DIR = ARCHIVE / "fit"
WELLNESS_DIR = ARCHIVE / "wellness"
DELAY_SEC = 1.5  # polite gap between detail/FIT calls


def _login():
    email, password = os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise ProviderNotConfigured("GARMIN_EMAIL / GARMIN_PASSWORD not set in .env")
    try:
        from garminconnect import (Garmin, GarminConnectAuthenticationError,
                                   GarminConnectConnectionError,
                                   GarminConnectTooManyRequestsError)
    except ImportError:
        raise ProviderNotConfigured("pip install garminconnect")
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        client = Garmin(email=email, password=password)
        client.login(str(TOKEN_DIR))
        return client
    except GarminConnectAuthenticationError as e:
        raise ProviderAuthError(f"Garmin auth failed: {e}")
    except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as e:
        msg = str(e).lower()
        if any(s in msg for s in ("401", "403", "auth", "login", "mfa", "captcha", "profile")):
            raise ProviderAuthError(f"Garmin login rejected: {e}")
        raise RuntimeError(f"Garmin connection error: {e}")


def _activities(client, start: dt.date, end: dt.date) -> list[dict]:
    out = []
    for a in client.get_activities_by_date(start.isoformat(), end.isoformat()):
        out.append(activity(
            id=a.get("activityId"),
            name=a.get("activityName"),
            subtype=(a.get("activityType") or {}).get("typeKey"),
            start_local=(a.get("startTimeLocal") or "").replace(" ", "T"),
            duration_min=(a.get("duration") or 0) / 60,
            distance_km=(a.get("distance") or 0) / 1000,
            avg_hr=a.get("averageHR"),
            max_hr=a.get("maxHR"),
            calories=a.get("calories"),
            training_load=a.get("activityTrainingLoad"),
            vo2max=a.get("vO2MaxValue"),
            elevation_gain_m=a.get("elevationGain"),
        ))
    return out


def _wellness(client, start: dt.date, end: dt.date, archive: bool) -> list[dict]:
    out = []
    if archive:
        WELLNESS_DIR.mkdir(parents=True, exist_ok=True)
    day = end
    while day >= start:
        date = day.isoformat()
        day -= dt.timedelta(days=1)
        try:
            sleep = client.get_sleep_data(date) or {}
            stats = client.get_stats(date) or {}
            hrv = client.get_hrv_data(date) or {}
        except Exception as e:  # one bad day shouldn't sink the sync
            print(f"  ! garmin {date}: {e}", file=sys.stderr)
            continue
        if archive:
            (WELLNESS_DIR / f"{date}.json").write_text(
                json.dumps({"date": date, "sleep": sleep, "stats": stats, "hrv": hrv},
                           indent=1, default=str), encoding="utf-8")
        sl = sleep.get("dailySleepDTO") or {}
        vo2 = None
        try:
            mm = client.get_max_metrics(date) or []
            if isinstance(mm, list) and mm:
                vo2 = (mm[0].get("generic") or {}).get("vo2MaxValue")
        except Exception:
            pass
        mins = lambda k: round((sl.get(k) or 0) / 60, 1) or None  # noqa: E731
        out.append(wellness(
            date=date,
            sleep_total_min=mins("sleepTimeSeconds"),
            sleep_deep_min=mins("deepSleepSeconds"),
            sleep_rem_min=mins("remSleepSeconds"),
            sleep_score=((sl.get("sleepScores") or {}).get("overall") or {}).get("value"),
            resting_hr=stats.get("restingHeartRate"),
            max_hr=stats.get("maxHeartRate"),
            steps=stats.get("totalSteps"),
            body_battery_high=stats.get("bodyBatteryHighestValue"),
            body_battery_low=stats.get("bodyBatteryLowestValue"),
            stress_avg=stats.get("averageStressLevel"),
            hrv_last_night_ms=(hrv.get("hrvSummary") or {}).get("lastNightAvg"),
            hrv_method="rmssd",
            vo2max_running=vo2,
        ))
    return out


def _save_details(client, aid: str) -> None:
    path = DETAILS_DIR / f"{aid}.json"
    if path.exists():
        return
    path.write_text(json.dumps(client.get_activity_details(aid), indent=1, default=str), encoding="utf-8")


def _save_fit(client, aid: str) -> bool:
    path = FIT_DIR / f"{aid}.fit"
    if path.exists():
        return True
    try:
        try:
            from garminconnect import Garmin
            fmt = Garmin.ActivityDownloadFormat.ORIGINAL
        except AttributeError:
            fmt = "ORIGINAL"
        blob = client.download_activity(aid, dl_fmt=fmt)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            fits = [n for n in z.namelist() if n.lower().endswith(".fit")]
            if not fits:
                return False
            path.write_bytes(z.read(fits[0]))
        return True
    except Exception as e:
        print(f"  ! FIT download failed for {aid}: {e}", file=sys.stderr)
        return False


def fetch(start: dt.date, end: dt.date, opts) -> tuple[list[dict], list[dict]]:
    client = _login()
    acts = _activities(client, start, end)
    days = _wellness(client, start, end, archive=getattr(opts, "backfill", False))

    with_details = getattr(opts, "with_details", False) or getattr(opts, "backfill", False)
    with_fit = getattr(opts, "with_fit", False) or getattr(opts, "backfill", False)
    if with_details or with_fit:
        DETAILS_DIR.mkdir(parents=True, exist_ok=True)
        FIT_DIR.mkdir(parents=True, exist_ok=True)
        for i, a in enumerate(acts, 1):
            label = f"  [{i}/{len(acts)}] {a['type']} {a['start_local']}"
            if with_details and not (DETAILS_DIR / f"{a['id']}.json").exists():
                try:
                    _save_details(client, a["id"])
                    print(f"{label} details ok")
                except Exception as e:
                    print(f"{label} details FAIL: {e}", file=sys.stderr)
                time.sleep(DELAY_SEC)
            if with_fit and not (FIT_DIR / f"{a['id']}.fit").exists():
                print(f"{label} FIT {'ok' if _save_fit(client, a['id']) else 'skipped'}")
                time.sleep(DELAY_SEC)
    return acts, days


def dump_activity(activity_id: str) -> dict:
    """Debug helper: one activity's raw detail JSON."""
    return _login().get_activity_details(activity_id)
