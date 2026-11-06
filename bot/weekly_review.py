"""Sunday weekly review pipeline.

Flow:
  1. Gather data: this week's plan, this week's synced activities + wellness,
     this week's phone-input notes, profile + goals, season plan, key principle concepts.
  2. Call Claude with a structured prompt -> returns (review_md, new_week_md).
  3. Stage as pending files: plans/.pending-review.md + plans/.pending-week.md.
  4. Bot sends Telegram summary with Approve/Reject buttons.
  5. On approve: write review into logs/YYYY-MM.md, write new current-week.md,
     archive old current-week.md to plans/archive/, commit+push, delete pending.
  6. On reject: delete pending files. Done.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic

from . import storage

# Default: Claude Opus 5.5. Override with ANTHROPIC_MODEL (e.g. claude-sonnet-5-5 to cut cost).
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
# Models that take `effort` and server-side refusal fallbacks
_MODERN = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")

# Files staged between draft and approval (single in-flight review at a time)
PENDING_REVIEW = "plans/.pending-review.md"
PENDING_WEEK = "plans/.pending-week.md"
PENDING_META = "plans/.pending-meta.json"

# Where weekly review entries land
ARCHIVE_DIR = "plans/archive"

# Principle concepts that always inform the review: every concept note whose
# frontmatter says `core: true` (the seed principles ship with it set).
def _core_concept_paths(root: Path) -> list[Path]:
    out = []
    for p in sorted((root / "concepts").glob("*.md")):
        head = p.read_text(encoding="utf-8")[:600]
        if re.search(r"^core:\s*true\s*$", head, re.MULTILINE):
            out.append(p)
    return out


# ---------- data gathering ----------

@dataclass
class WeekData:
    start: dt.date
    end: dt.date
    week_plan_md: str
    season_plan_md: str
    profile_md: str
    goals_md: str
    activities: list[dict]
    wellness: list[dict]
    phone_notes: list[tuple[str, str]]  # (date, text)
    recent_log_md: str
    core_concepts_md: str


def _last_completed_week() -> tuple[dt.date, dt.date]:
    """Mon-Sun of the week that just ended.

    If today is Sunday: return this week (today is the last day).
    Otherwise: return the previous Mon-Sun.
    """
    today = dt.date.today()
    if today.weekday() == 6:  # Sunday
        sun = today
    else:
        sun = today - dt.timedelta(days=today.weekday() + 1)
    mon = sun - dt.timedelta(days=6)
    return mon, sun


CACHE_PATH = "data/sync-cache.json"


def cache_age_hours() -> float | None:
    """How old (hours) is data/sync-cache.json? None if missing."""
    p = storage.workspace_root() / CACHE_PATH
    if not p.exists():
        return None
    age = dt.datetime.now() - dt.datetime.fromtimestamp(p.stat().st_mtime)
    return age.total_seconds() / 3600


def refresh_data(days: int = 14) -> tuple[bool, str]:
    """Run scripts/sync.py --cloud for every configured source. Returns (ok, info).

    Exit code 2 from sync.py means a source needs the human to re-authenticate;
    the returned info then starts with "auth" so the scheduler can alert the user.
    """
    root = storage.workspace_root()
    script = root / "scripts" / "sync.py"
    if not script.exists():
        return False, "scripts/sync.py not found"
    if not os.getenv("DATA_SOURCES", "").strip():
        return True, "no DATA_SOURCES configured — nothing to sync"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--cloud", "--days", str(days)],
            cwd=str(root), capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return True, "synced"
        if result.returncode == 2:
            return False, f"auth failure: {result.stderr.strip()[:200]}"
        return False, f"exit {result.returncode}: {result.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        return False, "sync timed out (>300s)"
    except Exception as e:
        return False, f"sync error: {e}"


def gather(start: dt.date | None = None, end: dt.date | None = None) -> WeekData:
    """Pull everything needed for the review."""
    root = storage.workspace_root()
    if start is None or end is None:
        start, end = _last_completed_week()

    def _read(path: str) -> str:
        p = root / path
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # Synced data: filter to this week
    cache_path = root / CACHE_PATH
    activities, wellness = [], []
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        for a in cache.get("activities", []):
            sl = a.get("start_local") or ""
            try:
                d = dt.date.fromisoformat(sl[:10])
            except ValueError:
                continue
            if start <= d <= end:
                activities.append(a)
        for w in cache.get("wellness", []):
            try:
                d = dt.date.fromisoformat(w.get("date", ""))
            except ValueError:
                continue
            if start <= d <= end:
                wellness.append(w)

    # Phone notes for the week
    phone_notes = []
    for p, text in storage.list_inbox_for_week(start, end):
        phone_notes.append((p.stem.removeprefix("phone-"), text))

    # Most recent month log (provides recent history context)
    today = dt.date.today()
    recent_log_md = _read(f"logs/{today:%Y-%m}.md")

    # Find any season plan file
    plans_dir = root / "plans"
    season = next(iter(sorted(plans_dir.glob("season-*.md"))), None)
    season_md = season.read_text(encoding="utf-8") if season else ""

    # Core concepts concatenated
    concept_blocks = []
    for cp in _core_concept_paths(root):
        concept_blocks.append(f"--- {cp.relative_to(root).as_posix()} ---\n{cp.read_text(encoding='utf-8')}")
    core_concepts_md = "\n\n".join(concept_blocks)

    return WeekData(
        start=start,
        end=end,
        week_plan_md=_read("plans/current-week.md"),
        season_plan_md=season_md,
        profile_md=_read("profile.md"),
        goals_md=_read("goals.md"),
        activities=sorted(activities, key=lambda x: x.get("start_local") or ""),
        wellness=sorted(wellness, key=lambda x: x.get("date") or ""),
        phone_notes=phone_notes,
        recent_log_md=recent_log_md,
        core_concepts_md=core_concepts_md,
    )


def _fmt_activities(acts: list[dict]) -> str:
    if not acts:
        return "(no synced activities this week)"
    lines = []
    for a in acts:
        parts = [
            a.get("start_local", "?")[:16].replace("T", " "),
            a.get("type") or "?",
        ]
        if a.get("distance_km"):
            parts.append(f"{a['distance_km']} km")
        if a.get("duration_min"):
            m = int(a["duration_min"])
            parts.append(f"{m//60}h{m%60:02d}" if m >= 60 else f"{m} min")
        if a.get("avg_pace_per_km"):
            parts.append(f"@ {a['avg_pace_per_km']}")
        if a.get("avg_hr"):
            parts.append(f"avg HR {int(a['avg_hr'])}")
        if a.get("training_load"):
            parts.append(f"load {round(a['training_load'])}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def _fmt_wellness(wells: list[dict]) -> str:
    if not wells:
        return "(no wellness data for this week)"
    lines = ["| Date | RHR | HRV ms | Sleep h | Score | BB lo-hi |", "|---|---|---|---|---|---|"]
    for w in wells:
        rhr = w.get("resting_hr") or "-"
        hrv = w.get("hrv_last_night_ms") or "-"
        sleep_h = f"{w['sleep_total_min']/60:.1f}" if w.get("sleep_total_min") else "-"
        score = w.get("sleep_score") or "-"
        bb = (f"{w.get('body_battery_low','-')}-{w.get('body_battery_high','-')}")
        lines.append(f"| {w['date']} | {rhr} | {hrv} | {sleep_h} | {score} | {bb} |")
    return "\n".join(lines)


def _fmt_phone_notes(notes: list[tuple[str, str]]) -> str:
    if not notes:
        return "(no phone-input notes this week)"
    return "\n\n".join(f"### {date}\n{text}" for date, text in notes)


# ---------- prompting ----------

SYSTEM_PROMPT = """You are the athlete's training planner. Who they are, what they are
training for, and their injury / niggle history are in their profile, goals and season
plan below — read those rather than assuming anything.

Your job each week:
  (1) Write a weekly review of the week that just ended.
  (2) Rewrite plans/current-week.md for the upcoming week.

The review template (see CLAUDE.md):
  1. What hit the plan (sessions completed, anything notable)
  2. What didn't (skipped/modified/dropped intensity, why)
  3. Body signals (each niggle zone listed in their profile, sleep, weight, HR drift)
  4. Read - one paragraph: what does the week's data say?
  5. One adjustment for next week
  6. (the new week itself goes in the second output block)

Hard principles you must apply (from the core concept notes below):
  - The A-goal in goals.md wins conflicts between disciplines.
  - Recovery is part of training. Don't stack high-intensity sessions.
  - Progressive overload: no volume or intensity jump >10% per week.
  - Watch every niggle zone listed in the profile. If something flares: reduce, don't
    push through. Flag it explicitly in the review.
  - Defer to the macro phases in the season plan. Don't invent new phases.
  - Never invent data. If something wasn't logged or synced, say it's missing.
  - Cite reasoning briefly; match the athlete's experience level in the profile.

OUTPUT FORMAT (strict):
Output the review as markdown, then the literal separator line:
===NEW WEEK===
Then the new plans/current-week.md content as markdown. No code fences, no commentary
before or after. The new week file should follow the same structure as the prior one
(header, sessions table, strength details if applicable, what-to-log section).
"""


def _build_user_prompt(d: WeekData) -> str:
    return f"""WEEK BEING REVIEWED: {d.start.isoformat()} to {d.end.isoformat()} (Mon-Sun)
TODAY: {dt.date.today().isoformat()}

=== PROFILE ===
{d.profile_md}

=== GOALS ===
{d.goals_md}

=== SEASON PLAN (macro - do not change) ===
{d.season_plan_md}

=== CORE PRINCIPLES TO APPLY ===
{d.core_concepts_md}

=== THE WEEK'S PLAN (what was prescribed) ===
{d.week_plan_md}

=== SYNCED ACTIVITIES THIS WEEK ===
{_fmt_activities(d.activities)}

=== WELLNESS THIS WEEK ===
{_fmt_wellness(d.wellness)}

=== PHONE NOTES THIS WEEK (RPE, niggles, subjective) ===
{_fmt_phone_notes(d.phone_notes)}

=== RECENT LOG ENTRIES (this month) ===
{d.recent_log_md[-6000:] if d.recent_log_md else '(no log entries yet)'}

=== TASK ===
1. Write the weekly review for {d.start.isoformat()} to {d.end.isoformat()}.
2. Then on a new line write: ===NEW WEEK===
3. Then write the new plans/current-week.md for the upcoming week
   ({(d.end + dt.timedelta(days=1)).isoformat()} to {(d.end + dt.timedelta(days=7)).isoformat()}).

Apply the principles. If any session this week flagged a niggle or RPE > planned,
explicitly carry the adjustment forward into next week (e.g. reduce volume on the
affected day, swap to a lower-impact alternative, add an extra prehab block).
"""


# ---------- LLM call ----------

def _call_claude(user_content: str) -> tuple[str, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    extra = {}
    if CLAUDE_MODEL.startswith(_MODERN):
        # Planning judgement benefits from more thinking than Opus 5.5's `medium` default.
        # `fallbacks="default"` re-runs a safety-classifier false positive on another
        # model server-side instead of failing the Sunday review.
        extra = {"output_config": {"effort": "high"},
                 "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    resp = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        **extra,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the review ({getattr(resp, 'stop_details', None)})")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude hit max_tokens before finishing the review")
    # Thinking blocks come first on current models; only text blocks are the answer.
    text = "".join(b.text for b in resp.content if b.type == "text")
    sep = "===NEW WEEK==="
    if sep not in text:
        raise RuntimeError(f"Claude output missing {sep} separator. Got:\n{text[:500]}")
    review_md, new_week_md = text.split(sep, 1)
    return review_md.strip(), new_week_md.strip()


def draft_review(d: WeekData) -> tuple[str, str]:
    """Call Claude. Returns (review_md, new_week_md)."""
    return _call_claude(_build_user_prompt(d))


def refine_review(d: WeekData, prior_review: str, prior_new_week: str, refinement: str) -> tuple[str, str]:
    """Re-draft a pending review with user-supplied refinement notes."""
    user_content = _build_user_prompt(d) + f"""

=== PRIOR DRAFT (which needs refining) ===

PRIOR REVIEW:
{prior_review}

PRIOR PROPOSED NEW WEEK:
{prior_new_week}

=== USER'S REFINEMENT NOTES ===
The user reviewed the draft above and wants these changes:

{refinement}

Re-draft both the review and the new week incorporating this feedback. Keep what's still
correct from the prior draft; only change what the user's notes call for. Use the same
output format (review, then `===NEW WEEK===`, then new current-week.md content).
"""
    return _call_claude(user_content)


# ---------- pending state ----------

def stage_pending(review_md: str, new_week_md: str, week_start: dt.date, week_end: dt.date,
                   *, revision: int = 1) -> None:
    """Write the drafted review + new week to pending files in plans/."""
    root = storage.workspace_root()
    (root / PENDING_REVIEW).write_text(review_md, encoding="utf-8", newline="\n")
    (root / PENDING_WEEK).write_text(new_week_md, encoding="utf-8", newline="\n")
    (root / PENDING_META).write_text(json.dumps({
        "drafted_at": dt.datetime.now().isoformat(),
        "week_reviewed_start": week_start.isoformat(),
        "week_reviewed_end": week_end.isoformat(),
        "revision": revision,
    }, indent=2), encoding="utf-8", newline="\n")


def has_pending() -> bool:
    root = storage.workspace_root()
    return (root / PENDING_REVIEW).exists() and (root / PENDING_WEEK).exists()


def load_pending() -> tuple[str, str, dict] | None:
    root = storage.workspace_root()
    if not has_pending():
        return None
    review = (root / PENDING_REVIEW).read_text(encoding="utf-8")
    week = (root / PENDING_WEEK).read_text(encoding="utf-8")
    meta_path = root / PENDING_META
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return review, week, meta


def discard_pending() -> None:
    root = storage.workspace_root()
    for p in (PENDING_REVIEW, PENDING_WEEK, PENDING_META):
        f = root / p
        if f.exists():
            f.unlink()


# ---------- approval (commit the pending) ----------

def approve_pending() -> tuple[bool, str]:
    """Apply the staged review + new week: write log + new current-week.md,
    archive old current-week.md, commit + push, then clear pending."""
    pending = load_pending()
    if pending is None:
        return False, "no pending review to approve"
    review_md, new_week_md, meta = pending

    root = storage.workspace_root()
    today = dt.date.today()
    week_end_iso = meta.get("week_reviewed_end", today.isoformat())

    # 1. Append review to logs/YYYY-MM.md
    log_path = root / "logs" / f"{today:%Y-%m}.md"
    log_path.parent.mkdir(exist_ok=True)
    if not log_path.exists():
        log_path.write_text(f"# Log -- {today:%B %Y}\n\n", encoding="utf-8", newline="\n")
    with log_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n## Weekly review (week ending {week_end_iso})\n\n{review_md}\n")

    # 2. Archive old current-week.md
    old_week = root / "plans" / "current-week.md"
    archive = root / ARCHIVE_DIR
    archive.mkdir(parents=True, exist_ok=True)
    if old_week.exists():
        archive_path = archive / f"week-ending-{week_end_iso}.md"
        archive_path.write_text(old_week.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    # 3. Write new current-week.md
    old_week.write_text(new_week_md, encoding="utf-8", newline="\n")

    # 4. Discard pending FIRST so they don't sneak into the commit
    discard_pending()

    # 5. Commit + push
    ok, info = storage.commit_and_push(
        f"weekly review: week ending {week_end_iso}",
        paths=None,  # add everything tracked
    )
    return ok, info


# ---------- short Telegram summary ----------

_HEADER_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _extract_section(md: str, *needles: str) -> str | None:
    """Find a section whose header contains any needle; return its body up to the next header."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^#{1,4}\s+(.+)$", line)
        if not m:
            continue
        h = m.group(1).lower()
        if any(n.lower() in h for n in needles):
            # Capture body until next header
            body = []
            for j in range(i + 1, len(lines)):
                if re.match(r"^#{1,4}\s+", lines[j]):
                    break
                body.append(lines[j])
            return "\n".join(body).strip()
    return None


def _trim(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def short_summary(review_md: str, new_week_md: str, reviewed_start, reviewed_end) -> str:
    """Compact 1-message Telegram summary. Hits only the high-level decisions."""
    next_start = reviewed_end + dt.timedelta(days=1)
    next_end = reviewed_end + dt.timedelta(days=7)

    parts = [f"📋 *Review: {reviewed_start:%a %d %b} → {reviewed_end:%a %d %b}*", ""]

    # The "Read" paragraph — Claude's actual judgement (most important, biggest budget)
    read = _extract_section(review_md, "read", "4.")
    if read:
        parts.append("*Read:*")
        parts.append(_trim(read, 1500))
        parts.append("")

    # The "Adjustment" — what's changing
    adj = _extract_section(review_md, "adjustment", "5.")
    if adj:
        parts.append("*Adjustment:*")
        parts.append(_trim(adj, 800))
        parts.append("")

    # Body-signals section: first 3 bullet/lines so all four niggle zones can show
    body = _extract_section(review_md, "body signals", "3.")
    if body:
        snippets = [l.strip("-* ").strip() for l in body.splitlines() if l.strip()][:3]
        if snippets:
            parts.append("*Body:*")
            for s in snippets:
                parts.append(f"  • {_trim(s, 200)}")
            parts.append("")

    # Next week's volume header (just the mileage target / phase line)
    header_block = _extract_section(new_week_md, "current week", "rebuild", "base build",
                                     "marathon build", "peak", "taper")
    if header_block:
        head = "\n".join(header_block.splitlines()[:6]).strip()
        parts.append(f"*Next week ({next_start:%d %b} → {next_end:%d %b}):*")
        parts.append(_trim(head, 600))
        parts.append("")

    parts.append("Full draft in `plans/.pending-*.md`.")
    out = "\n".join(parts)
    # Hard-cap at Telegram's per-message limit, leaving headroom for the button row
    return out[:3900]
