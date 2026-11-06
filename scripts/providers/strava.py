"""Strava provider — the catch-all for watches without their own provider.

Coros, Polar, Suunto, Wahoo, Zwift, Apple Watch (via WorkOutDoors / HealthFit
etc.) and Garmin itself can all auto-upload to Strava, so connecting Strava
gets you activities from nearly any device. Strava has no sleep / HRV /
resting-HR data, so pair it with another provider if you want wellness.

One-time setup (about 5 minutes):
  1. https://www.strava.com/settings/api -> create an app.
     "Authorization Callback Domain" = localhost
  2. Put the Client ID + Client Secret in .env:
       STRAVA_CLIENT_ID=
       STRAVA_CLIENT_SECRET=
  3. python scripts/sync.py --source strava --auth
     Open the printed URL, approve, then copy the `code=` value from the
     address bar of the (failed-to-load) localhost page and run:
     python scripts/sync.py --source strava --auth --code <code>
     It prints a STRAVA_REFRESH_TOKEN line — paste it into .env.

Strava rotates refresh tokens; the newest one is kept in data/.strava-token.json
(gitignored). On the cloud bot, set STRAVA_REFRESH_TOKEN as a secret — if it is
ever rejected, re-run step 3 and update the secret.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datastore import (DATA_DIR, ProviderAuthError, ProviderNotConfigured,  # noqa: E402
                       activity)

NAME = "strava"
CLOUD_SAFE = True
API = "https://www.strava.com/api/v3"
TOKEN_URL = "https://www.strava.com/oauth/token"
TOKEN_FILE = DATA_DIR / ".strava-token.json"


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        raise ProviderNotConfigured("pip install requests")


def _client() -> tuple[str, str]:
    cid, secret = os.getenv("STRAVA_CLIENT_ID", "").strip(), os.getenv("STRAVA_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise ProviderNotConfigured("STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET not set in .env")
    return cid, secret


def auth(code: str | None) -> None:
    """Interactive one-time OAuth: print the URL, or exchange a code for a refresh token."""
    cid, secret = _client()
    if not code:
        print("Open this URL, approve access, then re-run with --code <value from the redirect URL>:\n")
        print(f"https://www.strava.com/oauth/authorize?client_id={cid}&response_type=code"
              "&redirect_uri=http://localhost/exchange_token&approval_prompt=force"
              "&scope=read,activity:read_all")
        return
    r = _requests().post(TOKEN_URL, data={"client_id": cid, "client_secret": secret,
                                          "code": code, "grant_type": "authorization_code"}, timeout=30)
    if r.status_code != 200:
        raise ProviderAuthError(f"Strava code exchange failed ({r.status_code}): {r.text[:200]}")
    tok = r.json()
    _store(tok)
    print("Success. Add this line to .env (and to your bot's secrets if you deploy it):\n")
    print(f"STRAVA_REFRESH_TOKEN={tok['refresh_token']}")


def _store(tok: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({k: tok.get(k) for k in ("refresh_token", "access_token", "expires_at")}),
                          encoding="utf-8")


def _access_token() -> str:
    cid, secret = _client()
    saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8")) if TOKEN_FILE.exists() else {}
    if saved.get("access_token") and (saved.get("expires_at") or 0) > time.time() + 120:
        return saved["access_token"]
    refresh = saved.get("refresh_token") or os.getenv("STRAVA_REFRESH_TOKEN", "").strip()
    if not refresh:
        raise ProviderNotConfigured("no Strava refresh token — run: python scripts/sync.py --source strava --auth")
    r = _requests().post(TOKEN_URL, data={"client_id": cid, "client_secret": secret,
                                          "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30)
    if r.status_code in (400, 401):
        raise ProviderAuthError(f"Strava refresh token rejected ({r.status_code}) — re-run --auth")
    r.raise_for_status()
    tok = r.json()
    _store(tok)
    return tok["access_token"]


def fetch(start: dt.date, end: dt.date, opts) -> tuple[list[dict], list[dict]]:
    token = _access_token()
    req = _requests()
    after = int(dt.datetime.combine(start, dt.time()).timestamp())
    before = int(dt.datetime.combine(end + dt.timedelta(days=1), dt.time()).timestamp())
    acts, page = [], 1
    while True:
        r = req.get(f"{API}/athlete/activities", headers={"Authorization": f"Bearer {token}"},
                    params={"after": after, "before": before, "per_page": 100, "page": page}, timeout=30)
        if r.status_code == 401:
            raise ProviderAuthError("Strava access token rejected — re-run --auth")
        if r.status_code == 429:
            raise RuntimeError("Strava rate limit hit (100 requests / 15 min) — try again later")
        r.raise_for_status()
        batch = r.json()
        for a in batch:
            kj = a.get("kilojoules")
            acts.append(activity(
                id=a.get("id"),
                name=a.get("name"),
                subtype=a.get("sport_type") or a.get("type"),
                # Strava's start_date_local is local wall-clock time with a misleading "Z"
                start_local=(a.get("start_date_local") or "").rstrip("Z"),
                duration_min=(a.get("moving_time") or 0) / 60,
                distance_km=(a.get("distance") or 0) / 1000,
                avg_hr=a.get("average_heartrate"),
                max_hr=a.get("max_heartrate"),
                # Work in kJ ~= kcal burned (human efficiency ~24% cancels the 4.184 factor)
                calories=round(kj) if kj else None,
                training_load=a.get("suffer_score"),
                elevation_gain_m=a.get("total_elevation_gain"),
            ))
        if len(batch) < 100:
            break
        page += 1
    return acts, []
