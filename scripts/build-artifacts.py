#!/usr/bin/env python3
"""Build the published pages (Claude Artifacts) and track what still needs publishing.

Pages:
  training-plan  artifacts/training-plan.html  plan (plans/plan-data.json + plan-meta.json)
                                               with logged actuals laid over each day
  progress       artifacts/progress.html       every run: cardiac cost, pace vs HR, trends

Inputs: plans/plan-data.json, plans/plan-meta.json, plans/session-library.json,
        plans/training-actuals.json (reviewed log entries), data/sync-cache.json
        (synced activities — shown as "synced, not yet reviewed" until logged),
        artifacts/templates/*.html.

Publishing state lives in artifacts/manifest.json (committed, so URLs survive
across machines). A page is STALE when it has data and its built HTML differs
from what was last published.

Usage:
  python scripts/build-artifacts.py                              # build + show status
  python scripts/build-artifacts.py --json                       # status as JSON
  python scripts/build-artifacts.py --mark-published progress --url https://claude.ai/...
  python scripts/build-artifacts.py --mark-local all             # no Artifact tool here; stop nagging

The Claude Code hooks in .claude/settings.json call this automatically after
data changes; the agent then publishes stale pages with the Artifact tool.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "plans"
ART = ROOT / "artifacts"
MANIFEST = ART / "manifest.json"
PLAN = PLANS / "plan-data.json"
META = PLANS / "plan-meta.json"
SESSIONS = PLANS / "session-library.json"
ACTUALS = PLANS / "training-actuals.json"
CACHE = ROOT / "data" / "sync-cache.json"

PAGES = {
    "training-plan": {"title": "Training Plan", "icon": "calendar",
                      "description": "Day-by-day training plan with logged sessions laid over it."},
    "progress": {"title": "Training Progress", "icon": "chart",
                 "description": "Every logged run: heartbeats per km, pace against heart rate, trends."},
}

# Planned day type -> progress-page category
PLAN_TYPE_MAP = {"easy": "easy", "strides": "easy", "rest": "easy", "steady": "quality",
                 "lt1": "quality", "lt2": "quality", "mp": "quality", "race": "quality", "long": "long"}
PACE_RE = re.compile(r"(\d+):(\d{2})\s*/\s*km")


# ---------- input loading ----------

def _json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"! {path.relative_to(ROOT)} is not valid JSON ({e}); treating as empty", file=sys.stderr)
        return default


def _actuals() -> dict:
    return {k: v for k, v in _json(ACTUALS, {}).items() if not k.startswith("_") and isinstance(v, dict)}


def _synced_runs_by_date() -> dict[str, dict]:
    """date -> one aggregated running 'actual' built from synced activities."""
    by_date: dict[str, list[dict]] = {}
    for a in _json(CACHE, {}).get("activities", []):
        if a.get("type") == "running" and (a.get("distance_km") or 0) > 0:
            by_date.setdefault((a.get("start_local") or "")[:10], []).append(a)
    out = {}
    for date, runs in by_date.items():
        km = sum(r["distance_km"] for r in runs)
        mins = sum(r.get("duration_min") or 0 for r in runs)
        hr_w = [(r["avg_hr"], r.get("duration_min") or 0) for r in runs if r.get("avg_hr")]
        hr = round(sum(h * m for h, m in hr_w) / sum(m for _, m in hr_w)) if hr_w and sum(m for _, m in hr_w) else None
        pace = None
        if km and mins:
            m, s = divmod(round(mins * 60 / km), 60)
            pace = f"{m}:{s:02d}/km"
        cals = [r["calories"] for r in runs if r.get("calories")]
        out[date] = {
            "km": round(km, 2),
            "pace": pace,
            "avg_hr": hr,
            "max_hr": max((r["max_hr"] for r in runs if r.get("max_hr")), default=None),
            "cal": round(sum(cals)) if cals else None,
            "vo2max": next((r["vo2max"] for r in runs if r.get("vo2max")), None),
            "source": " + ".join(sorted({r["source"] for r in runs})),
            "auto": True,
        }
    return out


def _enc(obj) -> str:
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def _fill(template: str, values: dict[str, str]) -> str:
    for ph, val in values.items():
        if ph not in template:
            raise SystemExit(f"template is missing the {ph} placeholder")
        template = template.replace(ph, val)
    return template


# ---------- page builders ----------

def build_plan() -> tuple[str, bool, str]:
    weeks = _json(PLAN, [])
    weeks = weeks if isinstance(weeks, list) else []
    meta = _json(META, {})
    sessions = _json(SESSIONS, {})
    sessions = {k: v for k, v in sessions.items() if not k.startswith("_")}

    referenced = {k for w in weeks for d in w.get("days", []) for k in d.get("sessions", [])}
    unknown = referenced - set(sessions)
    if unknown:
        print(f"! plan-data.json references sessions missing from session-library.json: {sorted(unknown)}",
              file=sys.stderr)

    actuals, synced = _actuals(), _synced_runs_by_date()
    logged = auto = 0
    for w in weeks:
        for d in w.get("days", []):
            if d.get("date") in actuals:
                d["actual"] = actuals[d["date"]]
                logged += 1
            elif d.get("date") in synced:
                d["actual"] = synced[d["date"]]
                auto += 1

    page = _fill((ART / "templates" / "training-plan.html").read_text(encoding="utf-8"), {
        "__PAGE_TITLE__": html.escape(meta.get("title") or PAGES["training-plan"]["title"]),
        "__PLAN_DATA__": _enc(weeks),
        "__SESSION_DATA__": _enc(sessions),
        "__PLAN_META__": _enc(meta),
    })
    return page, bool(weeks), f"{len(weeks)} weeks, {logged} reviewed + {auto} synced-only days"


def _pace_min(text: str | None) -> float | None:
    m = PACE_RE.search(text or "")
    return int(m.group(1)) + int(m.group(2)) / 60 if m else None


def build_progress() -> tuple[str, bool, str]:
    meta = _json(META, {})
    long_km = float(meta.get("long_run_km") or 15)
    planned = {}
    for w in _json(PLAN, []) or []:
        for d in w.get("days", []):
            if PLAN_TYPE_MAP.get(d.get("type", "")):
                planned[d["date"]] = PLAN_TYPE_MAP[d["type"]]

    entries = dict(_synced_runs_by_date())
    entries.update(_actuals())  # a reviewed log entry always beats the raw sync

    runs = []
    for date in sorted(entries):
        e = entries[date]
        km, hr, pace = e.get("km") or 0, e.get("avg_hr"), _pace_min(e.get("pace"))
        if km <= 0 or not hr or not pace:
            continue
        explicit = e.get("session_type")
        kind = explicit if explicit in ("easy", "quality", "long") else (
            "long" if km >= long_km else planned.get(date, "easy"))
        runs.append({"date": date, "km": round(km, 2), "pace": round(pace, 4), "hr": int(hr),
                     "cost": round(hr * pace, 1), "type": kind, "reviewed": not e.get("auto")})

    days = []
    if runs:
        by_date = {r["date"]: r for r in runs}
        d, last = dt.date.fromisoformat(runs[0]["date"]), dt.date.fromisoformat(runs[-1]["date"])
        while d <= last:
            iso = d.isoformat()
            days.append({"date": iso, "dow": d.strftime("%a"), "run": by_date.get(iso)})
            d += dt.timedelta(days=1)

    page = _fill((ART / "templates" / "progress.html").read_text(encoding="utf-8"), {
        "__PAGE_TITLE__": html.escape(PAGES["progress"]["title"]),
        "__RUN_DATA__": _enc(runs),
        "__DAY_DATA__": _enc(days),
        "__PLAN_META__": _enc(meta),
    })
    return page, bool(runs), f"{len(runs)} runs"


BUILDERS = {"training-plan": build_plan, "progress": build_progress}


# ---------- manifest ----------

def load_manifest() -> dict:
    m = _json(MANIFEST, {})
    m.setdefault("pages", {})
    for name, info in PAGES.items():
        p = m["pages"].setdefault(name, {})
        p.setdefault("file", f"artifacts/{name}.html")
        for k in ("title", "icon", "description"):
            p.setdefault(k, info[k])
        for k in ("url", "built_hash", "built_at", "published_hash", "published_at", "has_data"):
            p.setdefault(k, None)
    return m


def save_manifest(m: dict) -> None:
    ART.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


def is_stale(p: dict) -> bool:
    return bool(p.get("has_data")) and p.get("built_hash") != p.get("published_hash")


def build_all(verbose: bool = True) -> dict:
    """Rebuild every page; returns the manifest. Writes the manifest only if something changed."""
    m = load_manifest()
    changed = False
    for name, builder in BUILDERS.items():
        page, has_data, summary = builder()
        out = ROOT / m["pages"][name]["file"]
        digest = hashlib.sha256(page.encode("utf-8")).hexdigest()[:16]
        if not out.exists() or out.read_text(encoding="utf-8") != page:
            out.write_text(page, encoding="utf-8")
        p = m["pages"][name]
        if p.get("built_hash") != digest or p.get("has_data") != has_data:
            p.update(built_hash=digest, has_data=has_data,
                     built_at=dt.datetime.now().isoformat(timespec="seconds"))
            changed = True
        p["_summary"] = summary
    summaries = {n: p.pop("_summary") for n, p in m["pages"].items() if "_summary" in p}
    if changed or not MANIFEST.exists():
        save_manifest(m)
    if verbose:
        for name, p in m["pages"].items():
            state = ("no data yet" if not p["has_data"] else
                     "NEEDS PUBLISH" if is_stale(p) else "published, up to date")
            print(f"  {name:<14} {state:<22} {summaries.get(name, '')}"
                  + (f"  {p['url']}" if p.get("url") else ""))
    return m


def publish_instructions(m: dict) -> str:
    """Plain-language instructions for the agent, used by the hooks."""
    lines = []
    for name, p in m["pages"].items():
        if not is_stale(p):
            continue
        how = (f"Artifact tool, action=publish, file_path={p['file']}, url={p['url']}" if p.get("url")
               else f"Artifact tool, action=publish, file_path={p['file']}, icon={p['icon']}, "
                    f"description=\"{p['description']}\" (first publish — creates the URL)")
        lines.append(f"- {name}: {how}\n  then: python scripts/build-artifacts.py --mark-published {name} --url <the artifact URL>")
    if not lines:
        return ""
    return ("Published pages are out of date — new training data has landed. Publish them now "
            "(read the built file first, as the Artifact tool requires):\n" + "\n".join(lines) +
            "\nIf this environment has no Artifact tool, run: python scripts/build-artifacts.py --mark-local all")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mark-published", metavar="PAGE")
    ap.add_argument("--url")
    ap.add_argument("--mark-local", metavar="PAGE|all")
    args = ap.parse_args()

    if args.mark_published:
        if args.mark_published not in PAGES or not args.url:
            raise SystemExit(f"usage: --mark-published {{{','.join(PAGES)}}} --url <artifact url>")
        m = load_manifest()
        p = m["pages"][args.mark_published]
        p.update(url=args.url, published_hash=p.get("built_hash"),
                 published_at=dt.datetime.now().isoformat(timespec="seconds"))
        save_manifest(m)
        print(f"marked {args.mark_published} as published at {args.url}")
        return 0
    if args.mark_local:
        m = load_manifest()
        for name in (PAGES if args.mark_local == "all" else [args.mark_local]):
            m["pages"][name]["published_hash"] = m["pages"][name].get("built_hash")
        save_manifest(m)
        print("acknowledged without publishing; pages will flag again on the next data change")
        return 0

    m = build_all(verbose=not args.json)
    if args.json:
        print(json.dumps({n: {**p, "stale": is_stale(p)} for n, p in m["pages"].items()}, indent=2))
    else:
        text = publish_instructions(m)
        if text:
            print("\n" + text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
