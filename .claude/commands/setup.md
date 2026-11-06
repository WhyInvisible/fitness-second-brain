---
description: First-run onboarding — interview the athlete, import or build their plan, connect their watch, publish their pages
---

Onboard a new athlete into this workspace. Work through the steps in order, a few questions at a time (use AskUserQuestion where the answer is a choice). Never invent their data: an unknown is written as "unknown" and asked about later.

If `profile.md` no longer contains `<!-- setup: pending`, setup has already run. Ask what they want to change and redo only those steps.

## 1. Say what's about to happen (two sentences)

You'll ask about them and their goals, find out whether they already have a plan, connect their watch if they have one, and publish two private pages (their plan, and their progress) that update themselves as training data comes in.

## 2. Profile interview → `profile.md`

The concept notes and MOCs are deliberately generic. They say things like "if the athlete has a hamstring history" or "from a recent benchmark", and **this interview is what personalises them**. Ask about every area below and fill in the matching section of `profile.md`. Take it a few questions at a time. If something is unknown, write "unknown" and move on; if they'd rather not say, respect that. If a sync is already possible (step 5), you can come back and fill benchmarks from data instead of asking.

1. **Basics:** age, height, current weight (and when / how measured), units, timezone, resting HR, max HR (measured or estimated?). Sex is optional; ask only if relevant.
2. **Running benchmarks:** recent 5K / 10K / half / marathon results with dates and conditions, PBs, average weekly distance over the last 4–8 weeks, longest recent run, easy pace and the HR it comes at, threshold pace / HR if known, the watch's VO2max estimate, and whether fitness is rising, flat, or returning after a break.
3. **Strength:** current working loads or recent best lifts (squat, hinge / deadlift, split squat, press, row), or none, and any lift they avoid and why.
4. **Calisthenics and skills:** max strict pull-ups, push-ups, dips, pistols, holds (L-sit, handstand), and the skills they're working toward.
5. **Mobility / yoga and other sports:** how often, what style, tight areas; climbing, cycling, swimming or team sports and how much recovery they take.
6. **Training history:** years in each discipline, peak volumes, past races and **how they went**: where it fell apart, cramping, pacing or fuelling problems, what they'd change. Breaks and layoffs (when, why, what was maintained). What has and hasn't worked for them before.
7. **Injuries and niggles: one table row per body part.** Ask about current *and past* injuries: when and how it happened, diagnosis and treatment, current status, what aggravates it, what helps, what to watch for. Probe: "anything that flares up when volume goes up?", "any lift or movement you avoid?", "any cramping in races?". Also ask (optional) about health conditions or medications that affect training, such as anything that changes heart rate. The weekly review checks every row each week.
8. **Equipment and access:** shoes, watch / HR strap, gym, home kit, routes / track / hills / pool.
9. **Weekly schedule:** for each day, fixed commitments, best training window and max session length; where the long session fits; upcoming travel, holidays or busy periods, with dates and what's possible while away.
10. **Nutrition and body composition:** diet style and restrictions, rough intake, protein habits, fuelling on long sessions and gut tolerance, sweat / hydration and any cramping history, and whether they have a weight or body-composition goal (current, target, by when), or none.
11. **Recovery and lifestyle:** typical sleep, job (desk, on feet, shifts), stress, anything else that regularly affects recovery.
12. **Coaching preferences:** blunt or gentle, how much detail, sessions they love or hate, how often they want check-ins.

## 3. Goals → `goals.md`

- Exactly one **A-goal**: what, when, target, a fallback target if a checkpoint says the main one isn't on, and why it matters. If they name two, explain [a-goal-wins-conflicts](../../concepts/a-goal-wins-conflicts.md) and ask them to pick one.
- **Supporting goals** (VO2max, calisthenics base, strength, mobility, a climbing grade...): the target, how it's measured, and whether it's maintained or progressed during the A-goal build.
- **Why this ordering:** what gets cut first when a week gets squeezed.
- **Body composition:** a target and approach if they want one; otherwise write "no weight goal".
- **Key dates:** races, tune-ups, checkpoints, travel, planned breaks.
- **Longer term:** the 1–3 year direction.

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
