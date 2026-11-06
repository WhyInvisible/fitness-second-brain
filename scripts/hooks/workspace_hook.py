#!/usr/bin/env python3
"""Claude Code hook entry point (wired in .claude/settings.json). Standard library only.

  session-start  Orients the agent: is setup done, is data stale, unprocessed
                 inbox notes, a pending weekly review, pages waiting to publish.
  post-tool-use  After any Write/Edit/Bash, rebuilds the published pages. If a page
                 just went stale (new data landed), tells the agent to publish it.
  stop           Blocks the turn from ending while a page with new data is still
                 unpublished (once per turn — never loops).

Set AUTO_PUBLISH_ARTIFACTS=false in .env to keep only the session-start report.
The hook always exits 0: a broken hook must never break the session.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP_MARKER = "<!-- setup: pending"  # /setup deletes this comment from profile.md when done
SYNC_STALE_HOURS = 24
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
WATCHED = {
    "plans/plan-data.json", "plans/plan-meta.json", "plans/session-library.json",
    "plans/training-actuals.json", "data/sync-cache.json",
    "artifacts/templates/training-plan.html", "artifacts/templates/progress.html",
}


def _env() -> dict[str, str]:
    out = dict(os.environ)
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return out


def _builder():
    spec = importlib.util.spec_from_file_location("build_artifacts", ROOT / "scripts" / "build-artifacts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stale_names(mod, manifest: dict) -> set[str]:
    return {n for n, p in manifest["pages"].items() if mod.is_stale(p)}


def session_start(env: dict) -> str:
    lines = []
    profile = ROOT / "profile.md"
    if not profile.exists() or SETUP_MARKER in profile.read_text(encoding="utf-8"):
        lines.append("SETUP NOT DONE: profile.md is still the blank template. Before anything else, "
                     "run the onboarding in .claude/commands/setup.md (/setup): interview the user, "
                     "ask whether they already have a training plan to import, connect a data source, "
                     "and publish their pages.")

    sources = [s for s in env.get("DATA_SOURCES", "").split(",") if s.strip()]
    cache_path = ROOT / "data" / "sync-cache.json"
    if sources:
        synced = None
        if cache_path.exists():
            try:
                synced = json.loads(cache_path.read_text(encoding="utf-8")).get("synced_at")
            except json.JSONDecodeError:
                pass
        age = (dt.datetime.now() - dt.datetime.fromisoformat(synced)).total_seconds() / 3600 if synced else None
        if age is None or age > SYNC_STALE_HOURS:
            when = "never" if age is None else f"{age:.0f}h ago"
            lines.append(f"Data last synced {when} (sources: {', '.join(sources)}). "
                         "Run `python scripts/sync.py` before answering questions about recent training.")

    inbox = [p.name for p in (ROOT / "inbox").glob("*.md")] if (ROOT / "inbox").exists() else []
    if inbox:
        lines.append(f"{len(inbox)} unprocessed note(s) in inbox/: {', '.join(sorted(inbox)[:6])}"
                     + (" ..." if len(inbox) > 6 else ""))
    if (ROOT / "plans" / ".pending-review.md").exists():
        lines.append("A weekly review drafted by the bot is awaiting approval (plans/.pending-review.md).")

    mod = _builder()
    manifest = mod.build_all(verbose=False)
    if env.get("AUTO_PUBLISH_ARTIFACTS", "true").lower() != "false":
        text = mod.publish_instructions(manifest)
        if text:
            lines.append(text)
    return "\n\n".join(lines)


def post_tool_use(payload: dict, env: dict) -> str:
    if env.get("AUTO_PUBLISH_ARTIFACTS", "true").lower() == "false":
        return ""
    tool = payload.get("tool_name", "")
    if tool in EDIT_TOOLS:
        fp = (payload.get("tool_input") or {}).get("file_path") or ""
        try:
            rel = Path(fp).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return ""
        if rel not in WATCHED:
            return ""
    elif tool != "Bash":
        return ""
    mod = _builder()
    before = _stale_names(mod, mod.load_manifest())
    manifest = mod.build_all(verbose=False)
    if not (_stale_names(mod, manifest) - before):
        return ""
    return "New training data changed the published pages (rebuilt in artifacts/).\n" + mod.publish_instructions(manifest)


def stop(payload: dict, env: dict) -> str:
    if payload.get("stop_hook_active") or env.get("AUTO_PUBLISH_ARTIFACTS", "true").lower() == "false":
        return ""
    mod = _builder()
    text = mod.publish_instructions(mod.build_all(verbose=False))
    return json.dumps({"decision": "block", "reason": text}) if text else ""


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    try:
        env = _env()
        if event == "session-start":
            out = session_start(env)
            if out:
                print(out)
        elif event == "post-tool-use":
            ctx = post_tool_use(payload, env)
            if ctx:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                         "additionalContext": ctx}}))
        elif event == "stop":
            out = stop(payload, env)
            if out:
                print(out)
    except Exception as e:  # never break the session over a hook
        print(f"workspace_hook {event} error: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
