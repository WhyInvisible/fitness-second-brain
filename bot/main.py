"""Telegram bot — main entrypoint.

Modes:
  python -m bot.main              # long-polling (works on any host, no webhook needed)
  python -m bot.main --webhook    # webhook mode (production, needs public HTTPS)

Locally, just run polling:
  cd "Fitness Planner"
  copy bot/.env.example bot/.env  # fill in tokens
  & $PY -m bot.main
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load bot/.env (preferred), then workspace .env (for shared creds like ANTHROPIC_API_KEY)
_BOT_ENV = Path(__file__).resolve().parent / ".env"
_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
if _BOT_ENV.exists():
    load_dotenv(_BOT_ENV)
if _ROOT_ENV.exists():
    load_dotenv(_ROOT_ENV, override=False)

from . import agent, schedule, storage, weekly_review

log = logging.getLogger("bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


# ---------- access control ----------

def _allowed_user_id() -> int | None:
    v = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    return int(v) if v.isdigit() else None


def _is_allowed(update: Update) -> bool:
    allowed = _allowed_user_id()
    if allowed is None:
        return True  # No allowlist set: dev mode, accept anyone
    return update.effective_user and update.effective_user.id == allowed


async def _deny(update: Update) -> None:
    user = update.effective_user
    log.warning(f"Denied access: id={user.id if user else '?'} name={user.full_name if user else '?'}")
    user_id = f"`{user.id}`" if user else "(unknown)"
    await update.message.reply_text(
        f"This bot is private. Your user ID: {user_id}\n\n"
        "To grant access, set TELEGRAM_ALLOWED_USER_ID in the bot env.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------- command handlers ----------

WELCOME = """*Fitness Planner bot* — your training inbox + agent.

*Commands:*
/note <text> — log a note (RPE, niggle, how it felt, etc.)
/ask <question> — Q&A over your plans, concepts, exercises
/week — show this week's plan summary
/today — today's plan only
/tomorrow — tomorrow's plan only
/review — draft last week's review (Claude). Add `this` for current week, or a date `YYYY-MM-DD` for any week. Replies with Approve/Reject buttons.
/sync — pull latest workspace from GitHub
/datasync — sync your watch data now

*Free-form messages:* the bot detects intent — short logs go to /note, questions go to /ask.

Notes land in `inbox/phone-YYYY-MM-DD.md` and feed into the Sunday weekly review.
"""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.MARKDOWN)


async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    text = " ".join(ctx.args).strip() if ctx.args else ""
    if not text:
        return await update.message.reply_text(
            "Usage: `/note <text>`  e.g.  `/note RPE 7 on long run, felt heavy last 5k`",
            parse_mode=ParseMode.MARKDOWN,
        )
    path = storage.append_inbox_note(text)
    _ok, info = storage.commit_and_push(f"bot: note {path.name}", paths=[path])
    rel = storage.workspace_root_relative(path)
    await update.message.reply_text(f"✓ Logged to `{rel}` ({info})", parse_mode=ParseMode.MARKDOWN)


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    q = " ".join(ctx.args).strip() if ctx.args else ""
    if not q:
        return await update.message.reply_text(
            "Usage: `/ask <question>`  e.g.  `/ask what is Tuesday's leg day this week?`",
            parse_mode=ParseMode.MARKDOWN,
        )
    await _handle_question(update, q)


async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    root = storage.workspace_root()
    p = root / "plans" / "current-week.md"
    if not p.exists():
        return await update.message.reply_text("No `plans/current-week.md` found.")
    text = p.read_text(encoding="utf-8")
    # Trim to ~3500 chars (Telegram limit ~4096) to leave room
    if len(text) > 3500:
        text = text[:3500] + "\n\n…(truncated — see full in dashboard or repo)"
    await update.message.reply_text(text, parse_mode=None, disable_web_page_preview=True)


async def cmd_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    ok, info = storage.pull_latest()
    icon = "✓" if ok else "✗"
    await update.message.reply_text(f"{icon} {info}")


# ---------- manual triggers for the scheduled jobs (for testing) ----------

async def cmd_morning(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually fire the morning ping. Same content as the 7am scheduled job."""
    if not _is_allowed(update):
        return await _deny(update)
    await schedule.morning_ping_job(ctx)


async def cmd_evening(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually fire the evening ping. Same content as the 8pm scheduled job."""
    if not _is_allowed(update):
        return await _deny(update)
    await schedule.evening_ping_job(ctx)


async def cmd_datasync(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually fire the daily data sync."""
    if not _is_allowed(update):
        return await _deny(update)
    await update.message.reply_text("Syncing data (last 14 days)...")
    await schedule.data_sync_job(ctx)
    await update.message.reply_text("✓ Data sync done")


# ---------- daily ping helpers (extract today/tomorrow from plan) ----------

import datetime as _dt
import re as _re

_DAY_ROW_RE = _re.compile(
    r"^\|\s*\*?\*?(?P<day>Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^|]*\|(?P<rest>.*)\|\s*$",
    _re.MULTILINE,
)


def _extract_day_block(week_md: str, target: _dt.date) -> str | None:
    """Pull the row for `target.weekday()` out of the sessions table in current-week.md."""
    weekday_short = target.strftime("%a")  # Mon, Tue, Wed, ...
    for m in _DAY_ROW_RE.finditer(week_md):
        if m.group("day") == weekday_short:
            cells = [c.strip() for c in m.group("rest").split("|")]
            label = m.group("day")
            return f"*{label} ({target:%d %b})*\n" + "\n".join(f"  • {c}" for c in cells if c and c != "—")
    return None


async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    root = storage.workspace_root()
    p = root / "plans" / "current-week.md"
    if not p.exists():
        return await update.message.reply_text("No `plans/current-week.md` found.")
    today = _dt.date.today()
    block = _extract_day_block(p.read_text(encoding="utf-8"), today)
    if not block:
        return await update.message.reply_text(
            f"Couldn't find a row for {today:%A %d %b} in the plan."
        )
    await update.message.reply_text(f"📅 Today\n\n{block}", parse_mode=ParseMode.MARKDOWN)


async def cmd_tomorrow(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    root = storage.workspace_root()
    p = root / "plans" / "current-week.md"
    if not p.exists():
        return await update.message.reply_text("No `plans/current-week.md` found.")
    tomorrow = _dt.date.today() + _dt.timedelta(days=1)
    block = _extract_day_block(p.read_text(encoding="utf-8"), tomorrow)
    if not block:
        return await update.message.reply_text(
            f"Couldn't find a row for {tomorrow:%A %d %b} in the plan."
        )
    await update.message.reply_text(f"📅 Tomorrow\n\n{block}", parse_mode=ParseMode.MARKDOWN)


# ---------- weekly review command ----------

REVIEW_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("✅ Approve", callback_data="review:approve"),
    InlineKeyboardButton("✏️ Refine", callback_data="review:refine"),
    InlineKeyboardButton("❌ Reject", callback_data="review:reject"),
]])


def _resolve_review_window(arg: str | None) -> tuple[_dt.date, _dt.date] | None:
    """Resolve /review's optional arg to a Mon-Sun window. Returns None for invalid.

    Accepts:
      (none)        -> last completed Mon-Sun (default; what Sunday cron uses)
      'this'        -> current week (Mon-Sun containing today)
      'last'        -> last completed Mon-Sun (same as default)
      'YYYY-MM-DD'  -> the Mon-Sun containing that date
    """
    today = _dt.date.today()
    if not arg or arg.lower() == "last":
        return None  # signals: use gather() default
    if arg.lower() in ("this", "thisweek", "current"):
        mon = today - _dt.timedelta(days=today.weekday())
        return mon, mon + _dt.timedelta(days=6)
    try:
        d = _dt.date.fromisoformat(arg)
    except ValueError:
        return None
    mon = d - _dt.timedelta(days=d.weekday())
    return mon, mon + _dt.timedelta(days=6)


async def cmd_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)

    if weekly_review.has_pending():
        return await update.message.reply_text(
            "There's already a pending review. Approve or reject it first.",
            reply_markup=REVIEW_KEYBOARD,
        )

    # Parse optional arg
    arg = ctx.args[0] if ctx.args else None
    if arg and arg.lower() not in ("last",) and arg.lower() not in ("this", "thisweek", "current"):
        # Validate ISO date
        try:
            _dt.date.fromisoformat(arg)
        except ValueError:
            return await update.message.reply_text(
                "Usage: `/review` (last completed week) | `/review this` | `/review YYYY-MM-DD`",
                parse_mode=ParseMode.MARKDOWN,
            )
    window = _resolve_review_window(arg)
    window_text = f"{window[0]} → {window[1]}" if window else "last completed Mon-Sun"

    # Refresh synced data if stale (>6h) so the review sees today's activities
    age = weekly_review.cache_age_hours()
    if os.getenv("DATA_SOURCES", "").strip() and (age is None or age > 6):
        age_txt = "missing" if age is None else f"{age:.1f}h old"
        await update.message.reply_text(f"Syncing data first (cache {age_txt})...")
        ok, info = await asyncio.to_thread(weekly_review.refresh_data, 14)
        if not ok:
            await update.message.reply_text(f"⚠ Sync failed ({info}); continuing with stale data.")

    await update.message.reply_text(f"Drafting weekly review for {window_text} (~30s)...")
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        if window:
            data = await asyncio.to_thread(weekly_review.gather, window[0], window[1])
        else:
            data = await asyncio.to_thread(weekly_review.gather)
        review_md, new_week_md = await asyncio.to_thread(weekly_review.draft_review, data)
    except Exception as e:
        log.exception("review draft failed")
        return await update.message.reply_text(f"Draft failed: {e}")

    weekly_review.stage_pending(review_md, new_week_md, data.start, data.end)

    # One compact summary message with the buttons attached
    summary = weekly_review.short_summary(review_md, new_week_md, data.start, data.end)
    try:
        await update.message.reply_text(
            summary, parse_mode=ParseMode.MARKDOWN, reply_markup=REVIEW_KEYBOARD,
            disable_web_page_preview=True,
        )
    except Exception:
        # Markdown can fail on unbalanced */backticks - fall back to plain
        await update.message.reply_text(summary, reply_markup=REVIEW_KEYBOARD,
                                         disable_web_page_preview=True)


async def on_review_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not _is_allowed(update):
        return
    await q.answer()
    action = q.data.split(":", 1)[1] if ":" in q.data else ""

    if action == "approve":
        ok, info = await asyncio.to_thread(weekly_review.approve_pending)
        icon = "✅" if ok else "⚠️"
        await q.edit_message_text(f"{icon} Approved — committed to repo ({info})")
        ctx.chat_data.pop("awaiting_refinement", None)
    elif action == "reject":
        await asyncio.to_thread(weekly_review.discard_pending)
        await q.edit_message_text("❌ Rejected — pending draft discarded")
        ctx.chat_data.pop("awaiting_refinement", None)
    elif action == "refine":
        ctx.chat_data["awaiting_refinement"] = True
        await q.edit_message_text(
            "✏️ *Refining.* Send your notes as the next message — e.g.:\n\n"
            "  • _drop Thursday strides — shoulder tight_\n"
            "  • _replace Saturday long run with rest, sick_\n"
            "  • _add Wednesday MP miles + lower Tuesday volume_\n\n"
            "I'll re-draft and send a new summary.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _handle_refinement(update: Update, refinement_text: str) -> None:
    """User tapped Refine; this is their follow-up message with notes."""
    if not weekly_review.has_pending():
        return await update.message.reply_text(
            "No pending draft to refine. Send `/review this` to start a new one.",
            parse_mode=ParseMode.MARKDOWN,
        )

    await update.message.reply_text("Re-drafting with your refinement (~30s)...")
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        pending = weekly_review.load_pending()
        if pending is None:
            return await update.message.reply_text("No pending draft.")
        prior_review, prior_week, meta = pending
        start = _dt.date.fromisoformat(meta["week_reviewed_start"])
        end = _dt.date.fromisoformat(meta["week_reviewed_end"])
        revision = (meta.get("revision") or 1) + 1

        data = await asyncio.to_thread(weekly_review.gather, start, end)
        review_md, new_week_md = await asyncio.to_thread(
            weekly_review.refine_review, data, prior_review, prior_week, refinement_text,
        )
    except Exception as e:
        log.exception("review refine failed")
        return await update.message.reply_text(f"Refine failed: {e}")

    weekly_review.stage_pending(review_md, new_week_md, start, end, revision=revision)
    summary = weekly_review.short_summary(review_md, new_week_md, start, end)
    header = f"_Revision {revision}_\n\n"
    try:
        await update.message.reply_text(
            header + summary, parse_mode=ParseMode.MARKDOWN,
            reply_markup=REVIEW_KEYBOARD, disable_web_page_preview=True,
        )
    except Exception:
        await update.message.reply_text(
            f"Revision {revision}\n\n" + summary,
            reply_markup=REVIEW_KEYBOARD, disable_web_page_preview=True,
        )


# ---------- free-form handler ----------

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return await _deny(update)
    text = update.message.text.strip()
    if not text:
        return

    # If user just tapped Refine, treat this message as the refinement notes.
    if ctx.chat_data.pop("awaiting_refinement", False):
        return await _handle_refinement(update, text)

    # Heuristic intent: if it ends with ? or starts with a question word, treat as a Q.
    # Otherwise, ASK the LLM to decide (it returns LOG_INTENT: prefix when it's a log).
    if _looks_like_question(text):
        return await _handle_question(update, text)
    return await _handle_ambiguous(update, text)


_QUESTION_STARTS = ("what", "how", "when", "where", "why", "is ", "are ", "should",
                    "will ", "can ", "could ", "do ", "does ", "did ", "tell me",
                    "explain", "show", "list", "give me")


def _looks_like_question(text: str) -> bool:
    t = text.lower().strip()
    if t.endswith("?"):
        return True
    return any(t.startswith(s) for s in _QUESTION_STARTS)


async def _handle_question(update: Update, q: str) -> None:
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        reply = await asyncio.to_thread(agent.answer, q)
    except Exception as e:
        log.exception("agent.answer failed")
        return await update.message.reply_text(f"Agent error: {e}")
    # Telegram limit ~4096; chunk if needed
    for chunk in _chunk(reply, 4000):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def _handle_ambiguous(update: Update, text: str) -> None:
    """Run through agent — it'll return LOG_INTENT: prefix if it's a log entry."""
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        reply = await asyncio.to_thread(agent.answer, text)
    except Exception as e:
        log.exception("agent.answer failed")
        return await update.message.reply_text(f"Agent error: {e}")

    if reply.startswith("LOG_INTENT:"):
        cleaned = reply[len("LOG_INTENT:"):].strip()
        path = storage.append_inbox_note(cleaned)
        ok, info = storage.commit_and_push(f"bot: note {path.name}", paths=[path])
        rel = storage.workspace_root_relative(path)
        return await update.message.reply_text(
            f"✓ Logged to `{rel}` ({info})\n> {cleaned}",
            parse_mode=ParseMode.MARKDOWN,
        )
    for chunk in _chunk(reply, 4000):
        await update.message.reply_text(chunk, disable_web_page_preview=True)


def _chunk(s: str, size: int):
    for i in range(0, len(s), size):
        yield s[i:i + size]


# ---------- main ----------

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set in bot/.env", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("tomorrow", cmd_tomorrow))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("morning", cmd_morning))
    app.add_handler(CommandHandler("evening", cmd_evening))
    app.add_handler(CommandHandler("datasync", cmd_datasync))
    app.add_handler(CallbackQueryHandler(on_review_button, pattern=r"^review:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    # Register scheduled jobs (data sync, morning + evening pings, Sunday review)
    schedule.register_jobs(app)

    log.info("Bot starting (polling mode)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
