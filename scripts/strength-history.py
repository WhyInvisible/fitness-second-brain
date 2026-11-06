#!/usr/bin/env python3
"""Query the structured strength/calisthenics log.

Companion to plans/strength-log.json. Answers the question progressive overload
depends on: what did I do last time, and is it going up?

Usage:
  python scripts/strength-history.py                  # every exercise, most recent first
  python scripts/strength-history.py dip              # one exercise's full history
  python scripts/strength-history.py --last           # the most recent session, in full
  python scripts/strength-history.py --session push   # all sessions of one type
  python scripts/strength-history.py --brief push     # PRE-SESSION BRIEF: last time + weaknesses + targets
  python scripts/strength-history.py --watch          # all standing watchpoints
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "plans" / "strength-log.json"


def load():
    d = json.loads(LOG.read_text(encoding="utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_watchpoints():
    return json.loads(LOG.read_text(encoding="utf-8")).get("_watchpoints", {})


def show_watchpoints(session_key=None):
    """Standing weaknesses. Filtered to one session type if given."""
    w = load_watchpoints()
    shown = 0
    for group, title in (("technique", "TECHNIQUE"), ("running", "RUNNING")):
        items = w.get(group, [])
        if session_key:
            items = [i for i in items if session_key in i.get("applies_to", [])]
        if not items:
            continue
        print(f"\n  {title}")
        for i in items:
            print(f"    ! {i['weakness']}")
            print(f"      -> {i['fix']}")
            shown += 1
    flags = w.get("physical_flags", [])
    if flags and not session_key:
        print("\n  PHYSICAL FLAGS")
        for f in flags:
            print(f"    [{f['status']}] {f['id']}: {f['note']}")
    return shown


def show_brief(data, session_key):
    """What to know before walking into this session."""
    print(f"\n{'=' * 68}\n  PRE-SESSION BRIEF — {session_key}\n{'=' * 68}")

    dates = [d for d in sorted(data, reverse=True)
             if any(s["session"] == session_key for s in data[d])]
    if dates:
        last = dates[0]
        sess = next(s for s in data[last] if s["session"] == session_key)
        print(f"\n  LAST TIME — {last}" + (f"  [RPE {sess['rpe']}]" if sess.get("rpe") is not None else ""))
        if sess.get("felt"):
            print(f'  Felt: "{sess["felt"]}"')
        print()
        for ex in sess["exercises"]:
            print(f"    {ex['name']:<34} {fmt_sets(ex['sets'])}")
            if ex.get("note"):
                print(f"        {ex['note']}")
    else:
        print(f"\n  LAST TIME — no {session_key} session logged yet.")

    show_watchpoints(session_key)

    targets = load_watchpoints().get("live_targets", [])
    if dates:
        names = {e["name"] for s in data[dates[0]] if s["session"] == session_key for e in s["exercises"]}
        targets = [t for t in targets if any(t["exercise"] in n or n in t["exercise"] for n in names)] or targets
    if targets:
        print("\n  LIVE TARGETS")
        for t_ in targets:
            print(f"    {t_['exercise']}: {t_['current']} -> {t_['target']}  ({t_['unlocks']})")
    print()


def fmt_set(s):
    if s.get("hold_s") is not None:
        return f"{s['hold_s']}s"
    reps = s.get("reps", "?")
    load = s.get("load_kg")
    return f"{reps}" + (f"@{load:g}kg" if load else "")


def fmt_sets(sets):
    return " · ".join(fmt_set(s) for s in sets)


def volume(sets):
    """Reps x load, for the exercises where that means anything."""
    return sum((s.get("reps") or 0) * (s.get("load_kg") or 0) for s in sets)


def show_exercise(data, needle):
    needle = needle.lower()
    hits = []
    for date in sorted(data, reverse=True):
        for sess in data[date]:
            for ex in sess["exercises"]:
                if needle in ex["name"].lower():
                    hits.append((date, sess["label"], ex))
    if not hits:
        print(f"No history for '{needle}'.")
        return
    print(f"\n{hits[0][2]['name']} — {len(hits)} session(s)\n")
    for date, label, ex in hits:
        vol = volume(ex["sets"])
        total = sum(s.get("reps") or 0 for s in ex["sets"])
        line = f"  {date}  {fmt_sets(ex['sets']):<34} {total} reps"
        if vol:
            line += f", {vol:g} kg volume"
        print(line)
        if ex.get("note"):
            print(f"             {ex['note']}")
        for s in ex["sets"]:
            if s.get("note"):
                print(f"             · {fmt_set(s)}: {s['note']}")


def show_session(sess, date):
    g = sess.get("garmin") or {}
    bits = []
    if g.get("duration_min"):
        bits.append(f"{g['duration_min']:g} min")
    if g.get("avg_hr"):
        hr = f"HR {g['avg_hr']:g}"
        if g.get("max_hr"):
            hr += f"/{g['max_hr']:g}"
        bits.append(hr)
    if g.get("cal"):
        bits.append(f"{g['cal']:g} kcal")
    head = f"\n{date} — {sess['label']}"
    if sess.get("rpe") is not None:
        head += f"  [RPE {sess['rpe']}]"
    if sess.get("confidence") == "prescribed":
        head += "  (sets assumed from plan)"
    print(head)
    if bits:
        print("  " + " · ".join(bits))
    if sess.get("felt"):
        print(f'  Felt: "{sess["felt"]}"')
    print()
    for ex in sess["exercises"]:
        print(f"  {ex['name']:<34} {fmt_sets(ex['sets'])}")
        if ex.get("note"):
            print(f"      {ex['note']}")
        for s in ex["sets"]:
            if s.get("note"):
                print(f"      · {fmt_set(s)}: {s['note']}")


def main():
    data = load()
    args = sys.argv[1:]

    if not data:
        print("Strength log is empty.")
        return

    if args and args[0] == "--watch":
        show_watchpoints()
        print()
        return

    if args and args[0] == "--brief":
        if len(args) < 2:
            print("Usage: --brief <session-key>   e.g. push, pull, legs-heavy, calisthenics")
            return
        show_brief(data, args[1])
        return

    if args and args[0] == "--last":
        date = max(data)
        for sess in data[date]:
            show_session(sess, date)
        return

    if args and args[0] == "--session":
        want = args[1].lower()
        for date in sorted(data, reverse=True):
            for sess in data[date]:
                if sess["session"].lower() == want:
                    show_session(sess, date)
        return

    if args:
        show_exercise(data, " ".join(args))
        return

    # default: every exercise, latest first
    seen = {}
    for date in sorted(data, reverse=True):
        for sess in data[date]:
            for ex in sess["exercises"]:
                seen.setdefault(ex["name"], []).append((date, ex))
    print(f"\n{len(seen)} exercises logged across {len(data)} session dates\n")
    for name, entries in sorted(seen.items()):
        date, ex = entries[0]
        print(f"  {name:<34} last {date}: {fmt_sets(ex['sets'])}")
    print("\nRun with an exercise name for its history, or --last for the most recent session.")


if __name__ == "__main__":
    main()
