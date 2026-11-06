"""Scheduled jobs for the bot.

Three daily jobs + one weekly:
  06:00 — Data auto-sync (scripts/sync.py --cloud -> data/; commit if changed)
  07:00 — Morning ping: today's plan + last-night sleep / HRV / RHR
  20:00 — Evening ping: tomorrow's plan + flag if today's session looks missed
  20:00 Sun — Sunday auto-review: drafts a review, sends with Approve/Refine/Reject buttons

All times are in TIMEZONE (default Europe/London) which Fly.io respects via the env var.

The bot must be the only sender into the user chat for these to be useful; that means
the Fly.io deployment is the canonical home (local laptop runs are dev-only).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

from . import storage, weekly_review

log = logging.getLogger("bot.schedule")


# ---------- shared helpers ----------

def _tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))


def _chat_id() -> int | None:
    v = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    return int(v) if v.isdigit() else None


_DAY_ROW_RE = re.compile(
    r"^\|\s*\*?\*?(?P<day>Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^|]*\|(?P<rest>.*)\|\s*$",
    re.MULTILINE,
)


def _day_block(week_md: str, target: dt.date) -> str | None:
    """Pull the row for `target.weekday()` out of the sessions table in current-week.md."""
    weekday_short = target.strftime("%a")
    for m in _DAY_ROW_RE.finditer(week_md):
        if m.group("day") == weekday_short:
            cells = [c.strip() for c in m.group("rest").split("|")]
            return "\n".join(f"  • {c}" for c in cells if c and c != "—")
    return None


def _current_week_md() -> str:
    p = storage.workspace_root() / "plans" / "current-week.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_cache() -> dict:
    p = storage.workspace_root() / "data" / "sync-cache.json"
    if not p.exists():
        return {"activities": [], "wellness": []}
    import json
    return json.loads(p.read_text(encoding="utf-8"))


def _activities_on(date: dt.date) -> list[dict]:
    cache = _read_cache()
    out = []
    for a in cache.get("activities", []):
        sl = a.get("start_local") or ""
        try:
            d = dt.date.fromisoformat(sl[:10])
        except ValueError:
            continue
        if d == date:
            out.append(a)
    return out


def _wellness_for(date: dt.date) -> dict | None:
    for w in _read_cache().get("wellness", []):
        if w.get("date") == date.isoformat():
            return w
    return None


# ---------- jobs ----------

async def data_sync_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """6am: sync every cloud-safe data source + commit data/ if anything changed.

    On auth-related failures (token expired, MFA prompt), notify the user via Telegram
    so they can re-authenticate. Network/transient errors are just logged.
    """
    log.info("[data_sync_job] starting")
    ok, info = await asyncio.to_thread(weekly_review.refresh_data, 14)
    if not ok:
        log.warning(f"[data_sync_job] sync failed: {info}")
        # Detect auth failures specifically — these are user-actionable
        info_low = (info or "").lower()
        is_auth = any(s in info_low for s in (
            "auth", "401", "unauthorized", "login", "captcha", "mfa", "credential",
        ))
        if is_auth:
            chat = _chat_id()
            if chat:
                await ctx.bot.send_message(
                    chat,
                    "⚠️ *Data sync: auth failure*\n\n"
                    "The daily sync couldn't log in to one of your data sources.\n\n"
                    "*Fix:*\n"
                    "  • Garmin: log in at https://connect.garmin.com once (clears MFA / captcha)\n"
                    "  • Strava: re-run `python scripts/sync.py --source strava --auth` and "
                    "update the STRAVA_REFRESH_TOKEN secret\n"
                    "The bot retries on the next sync.\n\n"
                    f"_Details: {info[:200]}_",
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
        return
    # Commit + push the synced data so every machine (and the published pages) see it.
    data_dir = storage.workspace_root() / "data"
    paths = [p for p in [data_dir / "sync-cache.json", *sorted((data_dir / "sources").glob("*.json"))]
             if p.exists()]
    if paths:
        _commit_ok, _commit_info = await asyncio.to_thread(
            storage.commit_and_push,
            f"bot: daily data sync {dt.date.today().isoformat()}",
            paths,
        )
        log.info(f"[data_sync_job] {info}; commit: {_commit_info}")


async def morning_ping_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """7am: today's plan + last night's sleep/HRV/RHR."""
    chat = _chat_id()
    if not chat:
        return log.warning("[morning_ping_job] no TELEGRAM_ALLOWED_USER_ID set")

    today = dt.date.today()
    week_md = _current_week_md()
    block = _day_block(week_md, today)

    yesterday = today - dt.timedelta(days=1)
    w_last_night = _wellness_for(today) or _wellness_for(yesterday)

    parts = [f"☀️ *Morning — {today:%A %d %b}*", ""]

    if w_last_night:
        bits = []
        if w_last_night.get("sleep_total_min"):
            h = w_last_night["sleep_total_min"] / 60
            bits.append(f"sleep {h:.1f}h" + (f" (score {w_last_night['sleep_score']})" if w_last_night.get("sleep_score") else ""))
        if w_last_night.get("resting_hr"):
            bits.append(f"RHR {w_last_night['resting_hr']}")
        if w_last_night.get("hrv_last_night_ms"):
            bits.append(f"HRV {w_last_night['hrv_last_night_ms']} ms")
        if bits:
            parts.append("*Body:* " + " | ".join(bits))
            parts.append("")

    if block:
        parts.append("*Today:*")
        parts.append(block)
    else:
        parts.append(f"_No row for {today:%a} in current-week.md._")

    try:
        await ctx.bot.send_message(chat, "\n".join(parts), parse_mode=ParseMode.MARKDOWN,
                                    disable_web_page_preview=True)
    except Exception as e:
        log.exception(f"[morning_ping_job] send failed: {e}")


async def evening_ping_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """8pm: tomorrow's plan + flag if today's planned session looks missed."""
    chat = _chat_id()
    if not chat:
        return log.warning("[evening_ping_job] no TELEGRAM_ALLOWED_USER_ID set")

    today = dt.date.today()
    tomorrow = today + dt.timedelta(days=1)
    week_md = _current_week_md()

    parts = [f"🌙 *Evening — {today:%A %d %b}*", ""]

    # Missed-workout check: planned today vs synced activities today
    today_block = _day_block(week_md, today)
    today_acts = _activities_on(today)
    if today_block:
        planned_has_run = bool(re.search(r"\b(km|easy|run|long|tempo|strides|fartlek|threshold)\b",
                                          today_block, re.IGNORECASE))
        had_running = any(a.get("type") == "running" for a in today_acts)
        had_any = bool(today_acts)
        if planned_has_run and not had_running:
            parts.append("⚠️ *Today:* run was planned, no run synced yet.")
            if had_any:
                acts_str = ", ".join(f"{a.get('type','?')} {a.get('distance_km',0)}km" for a in today_acts)
                parts.append(f"   (You did: {acts_str})")
            parts.append("")
        elif had_any:
            acts_str = ", ".join(
                f"{a.get('type','?').replace('_',' ')} {a.get('distance_km',0)}km"
                for a in today_acts if a.get("type") != "unknown"
            )
            parts.append(f"✓ *Today logged:* {acts_str}")
            parts.append("")

    tomorrow_block = _day_block(week_md, tomorrow)
    if tomorrow_block:
        parts.append(f"*Tomorrow ({tomorrow:%a %d %b}):*")
        parts.append(tomorrow_block)
    else:
        parts.append(f"_No row for {tomorrow:%a} in current-week.md._")

    try:
        await ctx.bot.send_message(chat, "\n".join(parts), parse_mode=ParseMode.MARKDOWN,
                                    disable_web_page_preview=True)
    except Exception as e:
        log.exception(f"[evening_ping_job] send failed: {e}")


REVIEW_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("✅ Approve", callback_data="review:approve"),
    InlineKeyboardButton("✏️ Refine", callback_data="review:refine"),
    InlineKeyboardButton("❌ Reject", callback_data="review:reject"),
]])


async def sunday_review_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Sunday 8pm: auto-draft the weekly review and send with buttons."""
    chat = _chat_id()
    if not chat:
        return log.warning("[sunday_review_job] no TELEGRAM_ALLOWED_USER_ID set")

    if weekly_review.has_pending():
        await ctx.bot.send_message(
            chat,
            "🗓️ Sunday review time — but there's already a pending draft. Resolve it first.",
            reply_markup=REVIEW_KEYBOARD,
        )
        return

    await ctx.bot.send_message(chat, "🗓️ Auto-drafting Sunday weekly review (~30s)...")
    try:
        # Sunday end-of-week = today is Sunday; gather() picks Mon-Sun ending today.
        data = await asyncio.to_thread(weekly_review.gather)
        review_md, new_week_md = await asyncio.to_thread(weekly_review.draft_review, data)
    except Exception as e:
        log.exception("[sunday_review_job] draft failed")
        await ctx.bot.send_message(chat, f"Sunday review draft failed: {e}")
        return

    weekly_review.stage_pending(review_md, new_week_md, data.start, data.end)
    summary = weekly_review.short_summary(review_md, new_week_md, data.start, data.end)
    try:
        await ctx.bot.send_message(chat, summary, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=REVIEW_KEYBOARD, disable_web_page_preview=True)
    except Exception:
        await ctx.bot.send_message(chat, summary, reply_markup=REVIEW_KEYBOARD,
                                    disable_web_page_preview=True)


# ---------- registration ----------

def register_jobs(app: Application) -> None:
    """Wire all scheduled jobs into the bot's JobQueue."""
    tz = _tz()
    jq = app.job_queue
    if jq is None:
        log.warning("JobQueue not available — install python-telegram-bot[job-queue]")
        return

    # Daily data sync (6am)
    jq.run_daily(data_sync_job, time=dt.time(6, 0, tzinfo=tz), name="data_sync")
    # Morning ping (7am)
    jq.run_daily(morning_ping_job, time=dt.time(7, 0, tzinfo=tz), name="morning_ping")
    # Evening ping (8pm)
    jq.run_daily(evening_ping_job, time=dt.time(20, 0, tzinfo=tz), name="evening_ping")
    # Sunday review (Sunday 8:15pm, after the evening ping)
    jq.run_daily(sunday_review_job, time=dt.time(20, 15, tzinfo=tz),
                 days=(6,), name="sunday_review")  # 6 = Sunday in PTB's enum

    log.info(f"Scheduled jobs registered (TZ={tz.key}): data_sync 06:00, "
             f"morning_ping 07:00, evening_ping 20:00, sunday_review Sun 20:15")
