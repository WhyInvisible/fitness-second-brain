"""Fitness Planner dashboard.

Read-only FastAPI server. Start with:
    python -m uvicorn dashboard.app:app --reload
or use ./serve-dashboard.sh (macOS/Linux) / ./serve-dashboard.ps1 (Windows).

Local-only by default (127.0.0.1:8000). Pass --host 0.0.0.0 to expose on LAN.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import data
from .markdown_render import render as md_render

# Workspace root + .env
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Lazy import of weather-lookup.py (filename has a hyphen so can't `import` directly)
def _load_weather_module():
    path = ROOT / "scripts" / "weather-lookup.py"
    spec = importlib.util.spec_from_file_location("weather_lookup", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["weather_lookup"] = mod
    spec.loader.exec_module(mod)
    return mod


app = FastAPI(title="Fitness Planner Dashboard")

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Custom filters
templates.env.filters["md"] = md_render
templates.env.globals["now"] = dt.datetime.now

# Static files (Tailwind via CDN, but we serve our own CSS too)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------- helpers ----------

def _nav_context() -> dict[str, Any]:
    """Shared context for the nav bar."""
    return {
        "today": dt.date.today(),
        "season_doc": data.season_doc(),
    }


def _week_metrics(start: dt.date, end: dt.date) -> dict[str, Any]:
    """Aggregate synced metrics for a week (or week-shaped range)."""
    acts = data.activities_in(start, end)
    wells = data.wellness_in(start, end)
    by_type: dict[str, list[dict]] = {}
    for a in acts:
        by_type.setdefault(a.get("type") or "unknown", []).append(a)
    run_km = round(sum((a.get("distance_km") or 0) for a in acts if a.get("type") == "running"), 1)
    total_min = round(sum((a.get("duration_min") or 0) for a in acts), 0)

    def _avg(vals: list) -> float | None:
        vals = [v for v in vals if v is not None and v != 0]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "activities": acts,
        "by_type": by_type,
        "run_km": run_km,
        "total_min": int(total_min),
        "wellness": wells,
        "avg_rhr": _avg([w.get("resting_hr") for w in wells]),
        "avg_hrv": _avg([w.get("hrv_last_night_ms") for w in wells]),
        "avg_sleep_min": _avg([w.get("sleep_total_min") for w in wells]),
    }


# ---------- routes ----------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    week_doc = data.current_week_doc()
    mon, sun = data.current_week_bounds()
    metrics = _week_metrics(mon, sun)
    latest_w = data.latest_wellness()
    return templates.TemplateResponse(request, "home.html", {
        "week_doc": week_doc,
        "week_html": md_render(week_doc.body) if week_doc else "<p>No current-week.md found.</p>",
        "week_start": mon,
        "week_end": sun,
        "metrics": metrics,
        "latest_wellness": latest_w,
        **_nav_context(),
    })


@app.get("/week", response_class=HTMLResponse)
async def week(request: Request):
    return await home(request)


@app.get("/week/offset/{offset}", response_class=HTMLResponse)
async def week_offset(request: Request, offset: int):
    """+1 = next week, -1 = last week. Renders synced metrics + season plan excerpt only
    (we only have one current-week.md; other weeks live in season plan + logs)."""
    start, end = data.week_offset(offset)
    metrics = _week_metrics(start, end)
    return templates.TemplateResponse(request, "week_other.html", {
        "offset": offset,
        "start": start,
        "end": end,
        "metrics": metrics,
        **_nav_context(),
    })


@app.get("/season", response_class=HTMLResponse)
async def season(request: Request):
    doc = data.season_doc()
    if not doc:
        raise HTTPException(404, "No season-*.md in plans/")
    return templates.TemplateResponse(request, "doc.html", {
        "doc": doc,
        "body_html": md_render(doc.body),
        "kind": "Season plan",
        **_nav_context(),
    })


@app.get("/exercises", response_class=HTMLResponse)
async def exercises_list(request: Request):
    docs = data.list_exercises()
    # Group by primary pattern for easier browsing
    by_pattern: dict[str, list] = {}
    for d in docs:
        patterns = d.meta.get("patterns") or []
        primary = patterns[0] if patterns else "other"
        by_pattern.setdefault(primary, []).append(d)
    sorted_groups = sorted(by_pattern.items(), key=lambda x: (-len(x[1]), x[0]))
    # Build {slug: has_image} map for thumbnail badges
    has_image = {d.slug: data.exercise_image(d.slug) is not None for d in docs}
    return templates.TemplateResponse(request, "exercises.html", {
        "groups": sorted_groups,
        "total": len(docs),
        "has_image": has_image,
        **_nav_context(),
    })


@app.get("/exercise/{slug}", response_class=HTMLResponse)
async def exercise_detail(request: Request, slug: str):
    doc = data.exercise(slug)
    if not doc:
        raise HTTPException(404, f"Exercise {slug} not found")
    img = data.exercise_image(slug)
    img_url = f"/file/exercises/images/{slug}/{img.name}" if img else None
    return templates.TemplateResponse(request, "exercise.html", {
        "doc": doc,
        "body_html": md_render(doc.body),
        "image_url": img_url,
        **_nav_context(),
    })


@app.get("/concept/{slug}", response_class=HTMLResponse)
async def concept_detail(request: Request, slug: str):
    doc = data.concept(slug)
    if not doc:
        raise HTTPException(404, f"Concept {slug} not found")
    return templates.TemplateResponse(request, "doc.html", {
        "doc": doc,
        "body_html": md_render(doc.body),
        "kind": "Concept",
        **_nav_context(),
    })


@app.get("/moc/{slug}", response_class=HTMLResponse)
async def moc_detail(request: Request, slug: str):
    doc = data.moc(slug)
    if not doc:
        raise HTTPException(404, f"MOC {slug} not found")
    return templates.TemplateResponse(request, "doc.html", {
        "doc": doc,
        "body_html": md_render(doc.body),
        "kind": "Map of content",
        **_nav_context(),
    })


@app.get("/log/{slug}", response_class=HTMLResponse)
async def log_detail(request: Request, slug: str):
    p = data.LOGS_DIR / f"{slug}.md"
    if not p.exists():
        raise HTTPException(404, f"Log {slug} not found")
    doc = data.load_doc(p)
    return templates.TemplateResponse(request, "doc.html", {
        "doc": doc,
        "body_html": md_render(doc.body),
        "kind": "Log",
        **_nav_context(),
    })


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    # Aggregate by month for the last 12 months that have data
    today = dt.date.today()
    cache = data.load_sync_cache()
    all_acts = cache.get("activities", [])
    months: dict[str, dict] = {}
    for a in all_acts:
        sl = a.get("start_local") or ""
        if len(sl) >= 7:
            ym = sl[:7]
            m = months.setdefault(ym, {"count": 0, "km_running": 0.0, "total_min": 0.0, "by_type": {}})
            m["count"] += 1
            if a.get("type") == "running":
                m["km_running"] += a.get("distance_km") or 0
            m["total_min"] += a.get("duration_min") or 0
            m["by_type"][a.get("type") or "unknown"] = m["by_type"].get(a.get("type") or "unknown", 0) + 1
    for m in months.values():
        m["km_running"] = round(m["km_running"], 1)
        m["total_min"] = int(m["total_min"])
    sorted_months = sorted(months.items(), reverse=True)

    # Last 7 days metrics
    last7 = _week_metrics(today - dt.timedelta(days=6), today)
    last30 = _week_metrics(today - dt.timedelta(days=29), today)

    return templates.TemplateResponse(request, "stats.html", {
        "months": sorted_months,
        "last7": last7,
        "last30": last30,
        "cache_meta": {
            "synced_at": cache.get("synced_at"),
            "n_activities": len(all_acts),
            "n_wellness_days": len(data.merged_wellness()),
        },
        **_nav_context(),
    })


# ---------- live data endpoints (HTMX) ----------

@app.get("/api/weather", response_class=HTMLResponse)
async def api_weather():
    """Renders a small HTML snippet for HTMX to inject."""
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return HTMLResponse('<span class="text-stone-500 text-sm">weather: no API key in .env</span>')
    lat = float(os.getenv("DEFAULT_LAT", "51.5074"))
    lon = float(os.getenv("DEFAULT_LON", "-0.1278"))
    try:
        wmod = _load_weather_module()
        w = wmod.fetch_current(lat, lon, api_key)
        bits = []
        if w.get("temp_c") is not None:
            bits.append(f"<strong>{w['temp_c']:.0f}&deg;C</strong> (feels {w['feels_like_c']:.0f})")
        if w.get("description"):
            bits.append(w["description"])
        if w.get("humidity_pct") is not None:
            bits.append(f"{w['humidity_pct']}% rh")
        if w.get("wind_speed_ms") is not None:
            bits.append(f"wind {w['wind_speed_ms']*3.6:.0f} km/h")
        loc = w.get("location") or os.getenv("DEFAULT_LOCATION_NAME", "")
        return HTMLResponse(
            f'<span class="text-stone-700 text-sm">'
            f'<span class="font-medium text-stone-500">{loc}:</span> ' + " &middot; ".join(bits) + "</span>"
        )
    except Exception as e:
        return HTMLResponse(f'<span class="text-rose-500 text-sm">weather error: {str(e)[:80]}</span>')


@app.get("/api/weather.json")
async def api_weather_json():
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return JSONResponse({"error": "no API key"}, status_code=503)
    lat = float(os.getenv("DEFAULT_LAT", "51.5074"))
    lon = float(os.getenv("DEFAULT_LON", "-0.1278"))
    try:
        wmod = _load_weather_module()
        return wmod.fetch_current(lat, lon, api_key)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---------- file passthrough (images/PDFs etc inside workspace) ----------

@app.get("/file/{path:path}")
async def file_passthrough(path: str):
    # Block path traversal: must resolve inside ROOT
    target = (ROOT / path).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        raise HTTPException(403, "Forbidden")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(target)


# ---------- meta ----------

@app.get("/healthz")
async def healthz():
    return {"ok": True, "now": dt.datetime.now().isoformat()}
