"""Read-only helpers for loading workspace markdown + synced training data.

Dashboard is read-only: never writes to plan / log / concept files.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLANS_DIR = ROOT / "plans"
LOGS_DIR = ROOT / "logs"
EXERCISES_DIR = ROOT / "exercises"
CONCEPTS_DIR = ROOT / "concepts"
MOCS_DIR = ROOT / "MOCs"
SYNC_CACHE = ROOT / "data" / "sync-cache.json"


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Doc:
    """A markdown file split into frontmatter + body + source path."""
    slug: str
    path: Path
    meta: dict
    body: str

    @property
    def title(self) -> str:
        # Prefer first H1 in body, else frontmatter.name, else slug
        m = re.search(r"^#\s+(.+)$", self.body, re.MULTILINE)
        if m:
            return m.group(1).strip()
        return self.meta.get("name") or self.slug


def _parse(path: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = text
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        body = text[m.end():]
    return Doc(slug=path.stem, path=path, meta=meta, body=body)


def load_doc(path: Path) -> Doc | None:
    if not path.exists():
        return None
    return _parse(path)


# ---------- plans ----------

def current_week_doc() -> Doc | None:
    return load_doc(PLANS_DIR / "current-week.md")


def season_doc() -> Doc | None:
    # Find any season-*.md in plans/
    matches = sorted(PLANS_DIR.glob("season-*.md"))
    return _parse(matches[0]) if matches else None


# ---------- logs ----------

def current_month_log() -> Doc | None:
    today = dt.date.today()
    return load_doc(LOGS_DIR / f"{today:%Y-%m}.md")


def all_log_months() -> list[str]:
    return sorted(p.stem for p in LOGS_DIR.glob("*.md") if re.match(r"\d{4}-\d{2}", p.stem))


# ---------- exercises ----------

def list_exercises() -> list[Doc]:
    out: list[Doc] = []
    for p in sorted(EXERCISES_DIR.glob("*.md")):
        if p.stem.lower() == "readme":
            continue
        out.append(_parse(p))
    return out


def exercise(slug: str) -> Doc | None:
    p = EXERCISES_DIR / f"{slug}.md"
    return _parse(p) if p.exists() else None


def exercise_image(slug: str) -> Path | None:
    """First image file for an exercise (used as thumbnail)."""
    img_dir = EXERCISES_DIR / "images" / slug
    if not img_dir.exists():
        return None
    for ext in ("*.gif", "*.png", "*.jpg", "*.jpeg", "*.webp"):
        for p in sorted(img_dir.glob(ext)):
            return p
    return None


# ---------- concepts ----------

def concept(slug: str) -> Doc | None:
    p = CONCEPTS_DIR / f"{slug}.md"
    return _parse(p) if p.exists() else None


def moc(slug: str) -> Doc | None:
    p = MOCS_DIR / f"{slug}.md"
    return _parse(p) if p.exists() else None


# ---------- synced data (data/sync-cache.json, any provider) ----------

def load_sync_cache() -> dict:
    if not SYNC_CACHE.exists():
        return {"activities": [], "wellness": []}
    return json.loads(SYNC_CACHE.read_text(encoding="utf-8"))


def merged_wellness() -> list[dict]:
    """Every synced wellness day, oldest first (the cache accumulates full history)."""
    return sorted((w for w in load_sync_cache().get("wellness", []) if w.get("date")),
                  key=lambda x: x["date"])


def activities_in(start: dt.date, end: dt.date) -> list[dict]:
    cache = load_sync_cache()
    out = []
    for a in cache.get("activities", []):
        sl = a.get("start_local") or ""
        try:
            d = dt.date.fromisoformat(sl[:10])
        except ValueError:
            continue
        if start <= d <= end:
            out.append(a)
    return sorted(out, key=lambda x: x.get("start_local") or "")


def wellness_in(start: dt.date, end: dt.date) -> list[dict]:
    out = []
    for w in merged_wellness():
        try:
            d = dt.date.fromisoformat(w["date"])
        except (KeyError, ValueError):
            continue
        if start <= d <= end:
            out.append(w)
    return out


def latest_wellness() -> dict | None:
    w = merged_wellness()
    return w[-1] if w else None


# ---------- week math ----------

def current_week_bounds() -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    mon = today - dt.timedelta(days=today.weekday())
    return mon, mon + dt.timedelta(days=6)


def week_offset(weeks: int) -> tuple[dt.date, dt.date]:
    """+1 = next week, -1 = last week."""
    mon, sun = current_week_bounds()
    return mon + dt.timedelta(weeks=weeks), sun + dt.timedelta(weeks=weeks)
