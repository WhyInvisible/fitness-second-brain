---
description: Sync data, log new sessions with how they felt, give an honest read, and republish the pages
---

Sync fresh data, log everything since the last entry, give an honest read on it, and republish the pages. Follow this sequence. Don't skip steps and don't invent data.

## 1. Sync

```
python scripts/sync.py            # add --days N if the last sync was more than a week ago
```

It prints `NEW ACTIVITIES` that it hasn't seen before. If `DATA_SOURCES` is empty, skip to step 2 and ask the athlete what they did.

**If a source reports AUTH FAILURE**, follow the fix for that source in [docs/data-sources.md](../../docs/data-sources.md) once (e.g. Garmin: delete `~/.garminconnect/` and retry; still failing → ask them to log in at connect.garmin.com to clear MFA). Don't loop, and never read or echo `.env`. Don't sync more than about once an hour.

## 2. Find what's unlogged

Compare `data/sync-cache.json` with the latest entries in `logs/YYYY-MM.md`, `plans/training-actuals.json` and `plans/strength-log.json`. Also read any `inbox/phone-*.md` notes the bot captured. For each unlogged session:
- Look up what was planned that day in `plans/plan-data.json` / `plans/current-week.md`.
- Pull the real numbers: distance, pace, avg/max HR, load, plus that morning's wellness (sleep, resting HR, HRV) for context.
- On easy days, check HR against the athlete's easy zone (profile / paces MOC). Pace on target with HR in a harder zone is a real signal; flag it.
- **Ask how it felt** (RPE, energy, niggles) instead of inventing it. Log from data alone only if they say so.

For strength / calisthenics sessions, ask for set-by-set detail (or at least loads) and how it felt.

## 3. Write it down

- **Every session:** append to `logs/YYYY-MM.md` in the format in CLAUDE.md (Session / Planned / Actual / Felt / Notes). Create the month file from `templates/log-month.md` if needed.
- **Runs:** add/update `plans/training-actuals.json` keyed by date (schema in the file's `_schema`). `comment` = their words; `notes` = objective flags. This replaces the page's "synced, not yet reviewed" marker with the reviewed entry.
- **Strength / calisthenics:** add to `plans/strength-log.json` set by set, `confidence: reported | prescribed`, and update `_watchpoints`: new weaknesses in, resolved ones out, `live_targets` moved on.
- **New niggle or injury:** add or update its row in `profile.md` → Injuries and niggles.
- **Processed inbox notes:** fold them into the log, then delete the inbox file.

## 4. Publish

The Claude Code hooks rebuild `artifacts/` as soon as the data changes and tell you which pages are stale. Publish each with the Artifact tool, reusing its URL from `artifacts/manifest.json`, then `python scripts/build-artifacts.py --mark-published <page> --url <url>`. If you have no Artifact tool: `python scripts/build-artifacts.py --mark-local all`.

## 5. Give an honest read

Say something useful, not generic encouragement: how the session sits against the plan, whether a pattern is forming across recent sessions (easy-run HR drifting down as it should? a niggle recurring instead of fading?), and whether anything about the coming days should change. Ground it in the numbers. If a change is warranted, propose the edit to `plans/current-week.md`.
