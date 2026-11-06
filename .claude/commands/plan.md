---
description: Import the athlete's existing training plan, or build a new one, into the plan files and publish it
---

Turn a plan into the files the workspace runs on. Use **Import** when the athlete already has a plan; use **Build** when they don't. If you don't know which, ask: "Do you already have a plan — from a coach, an app, a spreadsheet or a book — or shall we build one?"

## The files a plan lives in

| File | What goes in it |
|---|---|
| `plans/season-plan.md` | The macro plan in prose: phases, weekly volume ramp, cutback weeks, tune-up races, checkpoints, and **where the plan came from** |
| `plans/plan-data.json` | Every week and day, machine-readable. Renders the published Training Plan page. Shape: [examples/plan-data.example.json](../../examples/plan-data.example.json) |
| `plans/plan-meta.json` | Page header: event, date, target, stat chips, optional checkpoints and notes. Shape: [examples/plan-meta.example.json](../../examples/plan-meta.example.json) |
| `plans/session-library.json` | Strength / mobility / drill sessions the plan references by key. Shape: [examples/session-library.example.json](../../examples/session-library.example.json) |
| `plans/current-week.md` | This week only, as a Mon–Sun markdown table (`| Mon | ... |` rows). The bot's /today, /tomorrow and the daily pings parse it. |

Day `type` must be one of: `rest`, `easy`, `strides`, `steady`, `lt1`, `lt2`, `mp`, `long`, `race`. Map whatever the source calls things onto these. Examples: recovery → `easy`; tempo → `steady`; cruise intervals / threshold → `lt2`; VO2max intervals → `lt2` (say so in `pace`); goal-pace work → `mp`. Every key in a day's `sessions` must exist in the session library.

The plan page is built around running (km per day). For a strength-, skill- or sport-only goal, use `km: 0`, put the work in `sessions` chips, and use the type to show intensity (`easy` light, `steady` moderate, `lt2` hard). If that doesn't fit, skip `plan-data.json` and keep the plan in `season-plan.md` and `current-week.md`.

## Import

1. **Get the plan in.** Accept pasted text, a file path, an attachment, or a file in `resources/plans/`. For spreadsheets, read them with Python (`openpyxl`/`csv`); for PDFs, `python scripts/pdf-to-text.py`; for screenshots, read the image. If something is ambiguous (units, which week is week 1, rest-day placement), ask. Don't guess.
2. **Keep it faithful.** Transcribe the plan as written: same sessions, same distances, same paces. Convert miles to km if their profile says metric (and note it).
3. **Check it against this athlete** and list conflicts instead of silently fixing them:
   - availability in `profile.md` (sessions on days they can't train)
   - injuries / niggles (e.g. back-to-back impact on a sensitive zone)
   - week-on-week volume jumps over ~10% ([progressive-overload](../../concepts/progressive-overload.md))
   - stacked hard days ([dont-stack-high-intensity](../../concepts/dont-stack-high-intensity.md))
   - start date: a plan already under way starts at the right week, not week 1

   Propose specific changes and apply only the ones they accept.
4. Write the files above. In `season-plan.md` credit the source ("Imported from <coach/app/book>, <date>; changes made: ...").

## Build

1. Ground every choice in `profile.md`, `goals.md` and the notes in `concepts/` and `MOCs/`. Where the knowledge base doesn't cover something, say so and use well-established practice. Don't invent physiology.
2. Shape: weeks available until the A-goal date → phases (base → build → peak → taper), starting volume = what they **actually** ran recently (check `data/sync-cache.json` / `python scripts/report.py --weeks 8`), ~10% weekly ceiling, a cutback every 3–4 weeks, hard days separated, the long session on the day their availability allows.
3. Add checkpoints (a time trial, a tune-up race) that test the target, with what each result means for the target, in `plan-meta.json → checkpoints`.
4. Show them the outline (phases + weekly volumes) and get a yes before writing every day.

## Then, either way

```
python scripts/build-artifacts.py
```

Fix any warning it prints (e.g. unknown session keys). Then publish the Training Plan page with the Artifact tool (the hook will also remind you) and record the URL with `--mark-published`. Commit the plan files with a message naming the source.
