# Data sources

Training data flows in through **one command**, whatever device recorded it:

```
python scripts/sync.py
```

It runs every source listed in `DATA_SOURCES` in `.env`, maps each one into the same normalized format, and merges them into `data/sync-cache.json`. The bot, the dashboard, the reports, the weekly review and the published pages read only that file, so switching watches later changes one line in `.env`.

```
 Garmin Connect ─┐
 Apple Health ───┤   scripts/providers/*.py      data/sources/<provider>.json   (per-source, accumulates)
 Strava ─────────┼──► normalize ───────────────►            │
 FIT/GPX/TCX ────┘                                           ▼ merge + dedupe
                                                 data/sync-cache.json  ──► bot · dashboard · pages · reviews
```

## Pick your source

| You record with | Set | Activities | Sleep / HRV / resting HR | Runs unattended on the bot? |
|---|---|---|---|---|
| Garmin watch | `DATA_SOURCES=garmin` | ✓ | ✓ | ✓ |
| Apple Watch | `DATA_SOURCES=apple_health` | ✓ | ✓ | – (needs files from the phone) |
| Apple Watch, activities via Strava | `DATA_SOURCES=apple_health,strava` | ✓ | ✓ | Strava part only |
| Coros / Polar / Suunto / Wahoo / Zwift / anything that uploads to Strava | `DATA_SOURCES=strava` | ✓ | – | ✓ |
| Files only (USB export, other apps) | `DATA_SOURCES=files` | ✓ | – | – |
| Nothing | leave empty | log by hand | – | – |

Order matters: when two sources recorded the same session (start times within 3 minutes, same type), **the first source listed wins** and the other is noted in `also_in`. Wellness merges field by field: the first source with a value for a field supplies it.

Install the dependencies once: `python3 -m pip install -r requirements.txt` (into a `.venv` if you use one).

---

## Garmin

1. In `.env`:
   ```
   DATA_SOURCES=garmin
   GARMIN_EMAIL=you@example.com
   GARMIN_PASSWORD=...
   ```
2. Backfill some history so there's a baseline: `python scripts/sync.py --start 2026-01-01`.
3. Daily: `python scripts/sync.py` (last 7 days).

Garmin has no official personal API; [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) logs in as you. Tokens are cached in `~/.garminconnect/` for months.

Extras: `--with-details` saves per-second streams (needed by `scripts/garmin/run-splits.py`, which gives per-km splits on moving time, and `scripts/garmin/garmin-audit.py`, which finds GPS / HR / step recording faults). `--with-fit` saves the original FIT files. `--backfill` does both, plus raw daily wellness. All of it goes to `data/raw/garmin/` (gitignored).

**Auth failures:** log in once at <https://connect.garmin.com> in a browser to clear any MFA / captcha prompt. If tokens went stale after a long gap, delete `~/.garminconnect/` and retry once. Don't sync more than about once an hour; Garmin rate-limits.

## Apple Watch / Apple Health

Apple has no cloud API, so the phone exports files and the provider reads them.

**One-off or backfill:** iPhone Health app → your picture → *Export All Health Data* → save `export.zip` into `data/inbox/apple-health/` (AirDrop it to the Mac, or save to Files). Then:
```
python scripts/sync.py --source apple_health
```
Big exports (years of data) take a minute or two to parse. Re-exporting later is safe: records are keyed, nothing duplicates.

**Daily, automatic:** install the iOS app *Health Auto Export* (third-party, paid), and set up an automation that exports **Workouts** plus the metrics resting heart rate, heart rate variability, step count, sleep analysis, VO2 max and body mass as **JSON**, daily, to an iCloud Drive (or Dropbox) folder that syncs to your computer. Point `.env` at it:
```
DATA_SOURCES=apple_health
APPLE_HEALTH_DIR=~/Library/Mobile Documents/com~apple~CloudDocs/Health Auto Export
```
Every sync reads every file in that folder.

Notes:
- Apple's HRV is **SDNN**; Garmin's is **RMSSD**. They are different statistics, so compare each only with itself. `hrv_method` records which one a day used.
- iPhone and Watch both record steps and sleep. Each day takes the single source with the largest total, so they don't double count.
- The export app's JSON format has changed between versions. If a metric comes through empty, open one export file, compare its keys with `scripts/providers/apple_health.py`, and extend the key lists.

## Strava

Strava is the catch-all: Coros, Polar, Suunto, Wahoo, Zwift, Apple Watch (via apps such as HealthFit or WorkOutDoors) and Garmin can all auto-upload to it. It has activities only, no sleep or HRV.

1. <https://www.strava.com/settings/api> → create an app. *Authorization Callback Domain* = `localhost`.
2. In `.env`: `STRAVA_CLIENT_ID=` and `STRAVA_CLIENT_SECRET=`, and add `strava` to `DATA_SOURCES`.
3. `python scripts/sync.py --source strava --auth` → open the URL, approve. The browser lands on a localhost page that fails to load; that's expected. Copy the `code=` value from its address bar and run:
   `python scripts/sync.py --source strava --auth --code <code>`
4. Paste the printed `STRAVA_REFRESH_TOKEN=...` line into `.env` (and into the bot's secrets if you deploy it).

Strava rotates refresh tokens; the newest one is kept in `data/.strava-token.json` (gitignored). If the bot ever reports a Strava auth failure, redo step 3 and update the secret.

## Files (FIT / GPX / TCX)

Drop files into `data/inbox/files/` (or set `ACTIVITY_FILES_DIR`), then `python scripts/sync.py --source files`. Files are identified by content hash, so re-running and renaming are safe. FIT needs `pip install fitparse`; GPX and TCX use the standard library.

## No device

Leave `DATA_SOURCES` empty. Log sessions by telling the agent (`/log-training`) or the bot (`/note ...`). The plan page, logs and reviews all work; only the synced numbers and wellness trends are missing.

---

## Sync on a schedule

- **Telegram bot (recommended if deployed):** runs `scripts/sync.py --cloud` at 06:00 every day for the sources that can run unattended (Garmin, Strava) and commits the result. See [bot.md](bot.md).
- **Your computer:** a cron job (macOS / Linux, `crontab -e`):
  ```
  0 6 * * * cd /path/to/repo && .venv/bin/python scripts/sync.py >> scripts/_sync.log 2>&1
  ```
  On Windows, create the same thing in Task Scheduler.

Either way, the data lands without Claude. The published pages update at the start of your next Claude Code session: the SessionStart hook sees the new data and has the agent republish (see [artifacts.md](artifacts.md)).

## The normalized format

Defined in [scripts/datastore.py](../scripts/datastore.py), which is the source of truth.

**Activity:** `id`, `source`, `name`, `type` (running, cycling, swimming, walking, hiking, strength, yoga, hiit, rowing, climbing, other), `subtype` (provider's own label), `start_local` (local wall-clock ISO time), `duration_min` (moving/timer time), `distance_km`, `avg_pace_per_km`, `avg_hr`, `max_hr`, `calories`, `training_load`, `vo2max`, `elevation_gain_m`, and `also_in` when deduplicated.

**Wellness day:** `date` (the morning the night's sleep ended), `sleep_total_min`, `sleep_deep_min`, `sleep_rem_min`, `sleep_score`, `resting_hr`, `hrv_last_night_ms`, `hrv_method`, `steps`, `body_battery_high/low`, `stress_avg`, `vo2max_running`, `weight_kg`, `max_hr`, `sources`.

## Adding a provider (Oura, Whoop, Polar's own API, Fitbit, ...)

Create `scripts/providers/<name>.py` with:

```python
NAME = "<name>"
CLOUD_SAFE = True          # False if it needs local files

def fetch(start: date, end: date, opts) -> tuple[list[dict], list[dict]]:
    # return ([datastore.activity(...), ...], [datastore.wellness(...), ...])
```

Raise `datastore.ProviderNotConfigured` when credentials or files are missing (the source is skipped) and `datastore.ProviderAuthError` when the human must re-authenticate (sync exits 2 and the bot alerts them). Add the name to `PROVIDERS` in `scripts/sync.py`, document its `.env` keys in `.env.example` and here, and you're done: everything downstream already understands the format.
