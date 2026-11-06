"""Normalized store for synced training data.

Every provider (Garmin, Apple Health, Strava, FIT/GPX/TCX files) maps its
native format into the SAME two record shapes below. Everything downstream —
the bot, the dashboard, the published pages, the weekly review — reads only
`data/sync-cache.json` and never cares which device the data came from.

Layout:
  data/sources/<provider>.json   accumulated normalized records from one provider
  data/sync-cache.json           merged view across providers (what consumers read)
  data/raw/<provider>/...        raw archives (FIT files, detail streams) — gitignored

Merging rules (rebuild_cache):
  * Activities from different providers that start within DEDUPE_WINDOW_MIN of
    each other with the same canonical type are the same session recorded twice
    (e.g. a watch run that also auto-uploaded to Strava). The provider listed
    first in DATA_SOURCES wins; the loser is noted in `also_in`.
  * Wellness is merged per date, field by field: the first provider (in
    DATA_SOURCES order) with a non-null value for a field wins that field.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SOURCES_DIR = DATA_DIR / "sources"
RAW_DIR = DATA_DIR / "raw"
INBOX_DIR = DATA_DIR / "inbox"
CACHE = DATA_DIR / "sync-cache.json"

SCHEMA_VERSION = 1
DEDUPE_WINDOW_MIN = 3

# The normalized shapes. Providers fill what they can; everything else is None.
ACTIVITY_FIELDS = (
    "id",               # provider-native id as a string, unique within the provider
    "source",           # provider name: garmin | apple_health | strava | files
    "name",             # human label ("Morning Run")
    "type",             # canonical type, see CANONICAL_TYPES
    "subtype",          # provider-native type string, kept for reference
    "start_local",      # ISO 8601 local wall-clock time, no offset: 2026-03-01T07:12:00
    "duration_min",     # moving/timer time in minutes (pauses excluded where the provider knows)
    "distance_km",
    "avg_pace_per_km",  # "m:ss/km" or None
    "avg_hr",
    "max_hr",
    "calories",
    "training_load",    # provider-specific load score (Garmin load, Strava suffer score)
    "vo2max",
    "elevation_gain_m",
)

WELLNESS_FIELDS = (
    "date",             # YYYY-MM-DD — the morning the metrics belong to (sleep ends on this date)
    "sleep_total_min",
    "sleep_deep_min",
    "sleep_rem_min",
    "sleep_score",
    "resting_hr",
    "hrv_last_night_ms",
    "hrv_method",       # "rmssd" (Garmin, most chest straps) or "sdnn" (Apple) — not comparable
    "steps",
    "body_battery_high",
    "body_battery_low",
    "stress_avg",
    "vo2max_running",
    "weight_kg",
    "max_hr",
)

CANONICAL_TYPES = (
    "running", "cycling", "swimming", "walking", "hiking", "strength",
    "yoga", "hiit", "rowing", "climbing", "other",
)

# Substring rules, checked in order, mapping any provider's type string to a canonical type.
_TYPE_RULES = (
    ("run", "running"),
    ("jog", "running"),
    ("cycl", "cycling"), ("ride", "cycling"), ("bik", "cycling"), ("spin", "cycling"),
    ("swim", "swimming"),
    ("hik", "hiking"),
    ("walk", "walking"),
    ("strength", "strength"), ("weight", "strength"), ("functional", "strength"),
    ("crossfit", "strength"), ("traditionalstrength", "strength"),
    ("yoga", "yoga"), ("pilates", "yoga"), ("mobility", "yoga"), ("flexibility", "yoga"),
    ("hiit", "hiit"), ("interval", "hiit"),
    ("row", "rowing"),
    ("climb", "climbing"), ("boulder", "climbing"),
)


def canonical_type(raw: str | None) -> str:
    t = (raw or "").lower().replace(" ", "").replace("_", "")
    for needle, canon in _TYPE_RULES:
        if needle in t:
            return canon
    return "other"


def pace_str(duration_min: float | None, distance_km: float | None) -> str | None:
    if not duration_min or not distance_km or distance_km <= 0:
        return None
    spk = duration_min * 60 / distance_km
    m, s = divmod(int(round(spk)), 60)
    return f"{m}:{s:02d}/km"


def activity(**kw) -> dict:
    """Build a normalized activity record; derives type and pace when possible."""
    rec = {f: kw.get(f) for f in ACTIVITY_FIELDS}
    rec["id"] = str(rec["id"]) if rec["id"] is not None else None
    if not rec["type"]:
        rec["type"] = canonical_type(rec["subtype"] or rec["name"])
    for f in ("duration_min", "distance_km"):
        if rec[f] is not None:
            rec[f] = round(float(rec[f]), 2)
    if rec["avg_pace_per_km"] is None and rec["type"] in ("running", "walking", "hiking"):
        rec["avg_pace_per_km"] = pace_str(rec["duration_min"], rec["distance_km"])
    return rec


def wellness(**kw) -> dict:
    return {f: kw.get(f) for f in WELLNESS_FIELDS}


# ---------- configuration ----------

def load_env() -> None:
    """Load .env without requiring python-dotenv (hooks run on bare python)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        return
    except ImportError:
        pass
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def configured_sources() -> list[str]:
    """DATA_SOURCES from .env, in priority order."""
    raw = os.getenv("DATA_SOURCES", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


# ---------- per-source stores ----------

def _source_path(source: str) -> Path:
    return SOURCES_DIR / f"{source}.json"


def load_source(source: str) -> dict:
    p = _source_path(source)
    if not p.exists():
        return {"source": source, "last_sync": None, "activities": {}, "wellness": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save_source(source: str, activities: list[dict], wellness_days: list[dict]) -> tuple[int, int, list[dict]]:
    """Upsert a provider's records into its store. Returns (n_acts, n_days, newly_seen_activities)."""
    store = load_source(source)
    new = []
    for a in activities:
        a["source"] = source
        if a["id"] not in store["activities"]:
            new.append(a)
        store["activities"][a["id"]] = a
    for w in wellness_days:
        prev = store["wellness"].get(w["date"], {})
        # Keep previously-known values when a later partial sync returns None for a field
        merged = {k: (w.get(k) if w.get(k) is not None else prev.get(k)) for k in WELLNESS_FIELDS}
        store["wellness"][w["date"]] = merged
    store["last_sync"] = dt.datetime.now().isoformat(timespec="seconds")
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    _source_path(source).write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")
    return len(activities), len(wellness_days), new


# ---------- merged cache ----------

def _start(a: dict) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat((a.get("start_local") or "")[:19])
    except ValueError:
        return None


def rebuild_cache(priority: list[str] | None = None) -> dict:
    """Merge every data/sources/*.json into data/sync-cache.json."""
    present = sorted(p.stem for p in SOURCES_DIR.glob("*.json")) if SOURCES_DIR.exists() else []
    priority = [s for s in (priority or []) if s in present] + [s for s in present if s not in (priority or [])]
    stores = {s: load_source(s) for s in priority}

    activities: list[dict] = []
    for s in priority:  # highest priority first, so it claims the slot
        for a in stores[s]["activities"].values():
            st = _start(a)
            dup = None
            if st is not None:
                for kept in activities:
                    kst = _start(kept)
                    if (kst is not None and kept["type"] == a["type"]
                            and abs((kst - st).total_seconds()) <= DEDUPE_WINDOW_MIN * 60):
                        dup = kept
                        break
            if dup is not None:
                dup.setdefault("also_in", [])
                if s not in dup["also_in"]:
                    dup["also_in"].append(s)
                continue
            activities.append(dict(a))
    activities.sort(key=lambda a: a.get("start_local") or "")

    days: dict[str, dict] = {}
    for s in priority:
        for date, w in stores[s]["wellness"].items():
            cur = days.setdefault(date, {"date": date, "sources": []})
            contributed = False
            for k in WELLNESS_FIELDS:
                if k == "date":
                    continue
                if cur.get(k) is None and w.get(k) is not None:
                    cur[k] = w[k]
                    contributed = True
            if contributed and s not in cur["sources"]:
                cur["sources"].append(s)
    wellness_days = [dict({k: None for k in WELLNESS_FIELDS}, **d) for _, d in sorted(days.items())]

    cache = {
        "schema_version": SCHEMA_VERSION,
        "synced_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sources": {s: {"last_sync": stores[s].get("last_sync"),
                        "activities": len(stores[s]["activities"]),
                        "wellness_days": len(stores[s]["wellness"])} for s in priority},
        "activities": activities,
        "wellness": wellness_days,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache


def load_cache() -> dict:
    if not CACHE.exists():
        return {"schema_version": SCHEMA_VERSION, "synced_at": None, "sources": {},
                "activities": [], "wellness": []}
    return json.loads(CACHE.read_text(encoding="utf-8"))


class ProviderAuthError(RuntimeError):
    """Raised when a provider needs the human to re-authenticate. sync.py exits 2."""


class ProviderNotConfigured(RuntimeError):
    """Raised when a provider has no credentials / input files. Skipped, not fatal."""
