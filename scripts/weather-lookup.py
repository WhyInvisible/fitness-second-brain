#!/usr/bin/env python3
"""Fetch current weather from OpenWeatherMap.

Usage:
  python weather-lookup.py                  # uses DEFAULT_LAT/LON from .env, prints summary
  python weather-lookup.py --json           # JSON output (for piping)
  python weather-lookup.py --lat 51.5 --lon -0.1
  python weather-lookup.py --location "Madrid"

Importable:
  from weather_lookup import fetch_current
  w = fetch_current(lat, lon, api_key)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    print("Install python-dotenv: pip install python-dotenv", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_BASE = "https://api.openweathermap.org/data/2.5"
GEO_BASE = "http://api.openweathermap.org/geo/1.0"


def _get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    full = f"{url}?{q}"
    req = urllib.request.Request(full, headers={"User-Agent": "fitness-planner/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def geocode(location: str, api_key: str) -> tuple[float, float, str] | None:
    """Resolve a place name -> (lat, lon, display_name)."""
    data = _get(f"{GEO_BASE}/direct", {"q": location, "limit": 1, "appid": api_key})
    if not data:
        return None
    d = data[0]
    name = ", ".join(filter(None, [d.get("name"), d.get("state"), d.get("country")]))
    return d["lat"], d["lon"], name


def fetch_current(lat: float, lon: float, api_key: str, units: str = "metric") -> dict:
    """Return a flat dict with the key weather fields."""
    raw = _get(f"{API_BASE}/weather", {"lat": lat, "lon": lon, "appid": api_key, "units": units})
    weather = (raw.get("weather") or [{}])[0]
    main = raw.get("main", {})
    wind = raw.get("wind", {})
    return {
        "location": raw.get("name", ""),
        "country": raw.get("sys", {}).get("country", ""),
        "lat": lat,
        "lon": lon,
        "condition": weather.get("main", ""),
        "description": weather.get("description", ""),
        "temp_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity_pct": main.get("humidity"),
        "pressure_hpa": main.get("pressure"),
        "wind_speed_ms": wind.get("speed"),
        "wind_deg": wind.get("deg"),
        "wind_gust_ms": wind.get("gust"),
        "cloud_pct": (raw.get("clouds") or {}).get("all"),
        "visibility_m": raw.get("visibility"),
        "sunrise_utc": (raw.get("sys") or {}).get("sunrise"),
        "sunset_utc": (raw.get("sys") or {}).get("sunset"),
        "timestamp_utc": raw.get("dt"),
    }


def format_summary(w: dict) -> str:
    parts = []
    if w.get("location"):
        parts.append(f"{w['location']}")
    if w.get("temp_c") is not None:
        parts.append(f"{w['temp_c']:.1f}°C (feels {w['feels_like_c']:.1f})")
    if w.get("description"):
        parts.append(w["description"])
    if w.get("humidity_pct") is not None:
        parts.append(f"{w['humidity_pct']}% humidity")
    if w.get("wind_speed_ms") is not None:
        wind_kmh = w["wind_speed_ms"] * 3.6
        parts.append(f"wind {wind_kmh:.1f} km/h")
    return " · ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch current weather from OpenWeatherMap")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--location", help="Place name to geocode (overrides --lat/--lon)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--units", default="metric", choices=["metric", "imperial", "standard"])
    args = ap.parse_args()

    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        print("OPENWEATHERMAP_API_KEY missing — copy .env.example to .env and fill it in",
              file=sys.stderr)
        return 1

    if args.location:
        geo = geocode(args.location, api_key)
        if not geo:
            print(f"Could not geocode: {args.location}", file=sys.stderr)
            return 1
        lat, lon, _ = geo
    elif args.lat is not None and args.lon is not None:
        lat, lon = args.lat, args.lon
    else:
        lat_s = os.getenv("DEFAULT_LAT")
        lon_s = os.getenv("DEFAULT_LON")
        if not lat_s or not lon_s:
            print("No --lat/--lon, no --location, and DEFAULT_LAT/LON not set in .env",
                  file=sys.stderr)
            return 1
        lat, lon = float(lat_s), float(lon_s)

    try:
        w = fetch_current(lat, lon, api_key, units=args.units)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(w, indent=2))
    else:
        print(format_summary(w))
    return 0


if __name__ == "__main__":
    sys.exit(main())
