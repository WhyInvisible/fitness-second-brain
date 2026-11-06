---
description: First-run onboarding — interview the athlete, import or build their plan, connect their watch, publish their pages
---

Onboard a new athlete into this workspace. Work through the steps in order, a few questions at a time (use AskUserQuestion where the answer is a choice). Never invent their data: an unknown is written as "unknown" and asked about later.

If `profile.md` no longer contains `<!-- setup: pending`, setup has already run. Ask what they want to change and redo only those steps.

## 1. Say what's about to happen (two sentences)

You'll ask about them and their goals, find out whether they already have a plan, connect their watch if they have one, and publish two private pages (their plan, and their progress) that update themselves as training data comes in.

## 2. Profile → `profile.md`

Ask about, then fill in every section of `profile.md`:
- basics (age, height/weight, metric or imperial, timezone)
- training history: years per discipline, peak volumes, past races and results, long breaks
- current fitness: recent race or time-trial results, max/resting HR if known. Mark estimates as estimates.
- availability: days per week, minutes per session, fixed days, where the long session fits, upcoming travel
- equipment and facilities
- injuries and niggles: **one table row per zone**. The weekly review checks each row every week, so probe for this: "anything that flares up when volume goes up?"
- coaching preferences

## 3. Goals → `goals.md`

Exactly one A-goal (what, when, target, and a fallback target), then B/C goals and key dates. If they name two A-goals, explain [a-goal-wins-conflicts](../../concepts/a-goal-wins-conflicts.md) and ask them to pick one.

## 4. Do they already have a plan?

Ask this directly; never assume. Offer these options:

1. **Yes: I have a plan.** It could come from a coach, an app (Runna, TrainingPeaks, Garmin Coach, Nike Run Club...), a spreadsheet, a book or a PDF. Ask them to paste it, attach the file, give a path, or drop it into `resources/plans/` (gitignored). Then follow **Import** in [plan.md](plan.md).
2. **Sort of.** They have a target event and a rough idea, or a plan they want changed. Import what exists, then build the rest with them.
3. **No, build me one.** Follow **Build** in [plan.md](plan.md), grounded in their profile, goals and the concepts in this workspace.
4. **Not training for anything specific.** Build a rolling 4-week general-fitness block, set up the same way, and re-plan every 4 weeks.

Show them the plan (or the first weeks of it) and get a yes before writing it as final.

## 5. Connect their data → `.env`

Ask what they record training with, then configure it. Full instructions per device are in [docs/data-sources.md](../../docs/data-sources.md).

| They use | `DATA_SOURCES` | What they need to do |
|---|---|---|
| Garmin watch | `garmin` | put `GARMIN_EMAIL` / `GARMIN_PASSWORD` in `.env` |
| Apple Watch | `apple_health` (+ `strava` for activities, optional) | Health app → Export All Health Data → `data/inbox/apple-health/`; for daily automation, the Health Auto Export app writing to a synced folder set as `APPLE_HEALTH_DIR` |
| Coros, Polar, Suunto, Wahoo, Fitbit, Zwift... | `strava` | create a Strava API app, run `python scripts/sync.py --source strava --auth` |
| Exports files only | `files` | drop .fit / .gpx / .tcx into `data/inbox/files/` |
| Nothing | (empty) | manual logging. Everything still works except auto-sync. |

Rules:
- **Credentials go in `.env`, typed by the user, never pasted into chat.** Copy `.env.example` to `.env` if it's missing, tell them which keys to fill in, and wait. To verify, print only whether each key is set and its length, never the value.
- Install what's needed: `python3 -m pip install -r requirements.txt` (into `.venv` if one exists).
- First sync with a backfill so there's a baseline: `python scripts/sync.py --start <8–12 weeks ago>`. If it fails with an auth error, follow the fix in docs/data-sources.md. Don't retry in a loop.

## 6. Baselines from the data

If a sync brought history in, read `data/sync-cache.json` (and `python scripts/report.py --weeks 8`) and add to `profile.md` → Current fitness: recent weekly volume, typical easy-run pace and HR, resting HR and HRV baselines (note which HRV method). Label them "from synced data, <date range>".

## 7. Publish their pages

```
python scripts/build-artifacts.py
```

Publish each page it lists as NEEDS PUBLISH with the Artifact tool (read the built file first). Then record each URL:

```
python scripts/build-artifacts.py --mark-published training-plan --url <url>
python scripts/build-artifacts.py --mark-published progress --url <url>
```

A page with no data yet (e.g. no runs logged) is skipped until it has data. Tell them the links are private until they choose to share them, and that the pages republish automatically whenever new data lands (see [docs/artifacts.md](../../docs/artifacts.md)).

## 8. Finish

- Delete the `<!-- setup: pending ... -->` line from `profile.md`, `goals.md`, `plans/current-week.md` and `plans/season-plan.md`.
- Offer the optional extras, one line each: the Telegram bot for phone logging and daily pings ([docs/bot.md](../../docs/bot.md)), the local dashboard (`./serve-dashboard.sh`), scheduled syncing (docs/data-sources.md → "Sync on a schedule").
- If this folder isn't yet their own **private** GitHub repo, offer to create one. Their copy now holds personal data, so it must never be public.
- Commit locally with a clear message. Ask before pushing.
- End with a short summary: their A-goal, this week's sessions, which data source is connected, and the two page links.
