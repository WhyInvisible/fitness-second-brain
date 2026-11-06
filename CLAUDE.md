# CLAUDE.md: operating manual for the agent

This repository is a personal **training second brain**: a Zettelkasten knowledge base about training, one athlete's profile, goals, plan and logs, a pipeline that syncs data from their watch, and two pages published as Claude Artifacts that update themselves as training data comes in. Your role is planner, scribe and second opinion. The athlete is the athlete.

Read this file in full before acting. Other agents: [AGENTS.md](AGENTS.md) points here too.

## Start of every session

The SessionStart hook prints the workspace state into your context. Act on it in this order:

1. **"SETUP NOT DONE"** → run [/setup](.claude/commands/setup.md) before anything else, unless the user asked for something specific; in that case do that, then offer setup.
2. **Pages out of date** → publish them (see [Published pages](#published-pages-auto-updating-artifacts)). This is how data that arrived while you weren't running reaches the athlete's links.
3. **Data last synced more than 24 h ago** → run `python scripts/sync.py` before answering anything about recent training.
4. **Unprocessed inbox notes / a pending weekly review** → mention them; process when relevant.

Then orient: [profile.md](profile.md) (who), [goals.md](goals.md) (what for), [plans/season-plan.md](plans/season-plan.md) (the macro plan), [plans/current-week.md](plans/current-week.md) (this week), the latest file in [logs/](logs/) (what actually happened).

## Rules that are never broken

1. **Never invent data.** Unknown mileage, PBs, how a session felt, injury status: read the logs or ask. Mark estimates as estimates.
2. **Credentials stay in `.env` / `bot/.env`, typed by the user.** Never ask for a password or token in chat, never print or echo `.env` contents. To check a key is set, print only its length.
3. **This copy of the repo holds personal health data.** It must only ever be pushed to a **private** repository. Ask before any `git push`, and before creating or changing a remote.
4. **Don't fake the bot.** `inbox/phone-*.md` files and `bot:` / `weekly review:` commits come from the Telegram bot only.
5. **Flag uncertainty.** If you're not sure a piece of training advice is sound, say so. Be conservative with injuries.

## Map

| Path | What it is | Who writes it |
|---|---|---|
| `profile.md`, `goals.md` | The athlete; their A-goal (exactly one), B/C goals, key dates | you, via /setup and as things change |
| `plans/season-plan.md` | Macro plan in prose, with its source credited | you (/plan) |
| `plans/plan-data.json`, `plan-meta.json`, `session-library.json` | The plan day by day, the page header, strength sessions | you (/plan, weekly review) |
| `plans/current-week.md` | This week as a Mon–Sun table (the bot parses the `\| Mon \| ... \|` rows) | you or the bot's approved review |
| `plans/training-actuals.json` | Reviewed runs keyed by date | you (/log-training) |
| `plans/strength-log.json` | Every non-running session, set by set, plus `_watchpoints` | you |
| `plans/body-log.json` | Weigh-ins | you |
| `logs/YYYY-MM.md` | Chronological log, weekly reviews | you, the bot |
| `inbox/` | Fleeting notes (incl. `phone-*.md` from the bot). Process within a week | bot, you |
| `data/sync-cache.json`, `data/sources/` | Synced, normalized device data | `scripts/sync.py` only, never hand-edited |
| `data/raw/`, `data/inbox/` | Raw device archives, dropped-in exports (gitignored) | sync / the user |
| `concepts/` | Atomic permanent notes, one idea each; `core: true` ones bind every review | you |
| `MOCs/` | Maps of Content, the hub notes | you |
| `exercises/` | One file per exercise | you |
| `references/` | Literature notes, one per distilled source | you |
| `resources/` | Source books / PDFs (gitignored, may be copyrighted) | the user |
| `artifacts/` | Page templates, built pages (gitignored), `manifest.json` (URLs, committed) | `scripts/build-artifacts.py` |
| `templates/` | Templates for concept / exercise / reference / MOC / log notes | — |
| `examples/` | Fictional example plan files showing every format | — |
| `scripts/` | sync, providers, build-artifacts, reports, hooks, analysis | — |
| `bot/`, `dashboard/` | Telegram bot (Fly.io), local read-only dashboard | — |
| `docs/` | [data-sources](docs/data-sources.md), [artifacts](docs/artifacts.md), [bot](docs/bot.md), [zettelkasten](docs/zettelkasten.md) | — |

## Slash commands

| Command | Use it when |
|---|---|
| [/setup](.claude/commands/setup.md) | First run, or redoing part of onboarding |
| [/plan](.claude/commands/plan.md) | Importing the athlete's existing plan, or building a new one |
| [/log-training](.claude/commands/log-training.md) | After training: sync, ask how it felt, log, publish, honest read |
| [/weekly-review](.claude/commands/weekly-review.md) | End of week, when the bot isn't doing it |
| [/publish](.claude/commands/publish.md) | Publishing the pages by hand |
| [/distill](.claude/commands/distill.md) | Turning a book / paper in `resources/` into notes |

## Workflows

### The plan: always ask first

**Never assume the athlete's plan.** The template ships with none. Before planning, ask whether they already have one: from a coach, an app (Runna, TrainingPeaks, Garmin Coach...), a spreadsheet, a book. If they do, **import it faithfully** and flag conflicts with their profile rather than silently changing it. If they don't, build one with them. Both paths are in [/plan](.claude/commands/plan.md).

Plan changes: edit `plans/current-week.md` first. Touch `plan-data.json` and `season-plan.md` only when something fundamental shifted (illness, injury, a moved race), mark changed weeks `"revised": true`, and say why in `plan-meta.json → reality_note`. If the bot is deployed, it rewrites `current-week.md` when a Sunday review is approved, so coordinate edits made late in the week.

### Data sync

`python scripts/sync.py` pulls from every source in `DATA_SOURCES` (Garmin, Apple Health, Strava, FIT/GPX/TCX files) into `data/sync-cache.json`. `--status` shows what's configured. Exit code 2 means a source needs the human to re-authenticate: tell them the fix from [docs/data-sources.md](docs/data-sources.md) and don't retry in a loop. To add a device, write a provider; the contract is in that doc. Reports with no API calls: `python scripts/report.py [--current-week | --weeks N | --month YYYY-MM | --archive]`.

### Logging

After any session, log it. Don't ask permission to write the log; do ask how it felt.

Append to `logs/YYYY-MM.md` (create it from `templates/log-month.md`):

```markdown
### 2026-05-22 (Fri)
- **Session**: Easy run / Strength / Yoga / ...
- **Planned**: what plans/current-week.md called for
- **Actual**: distance, time, pace, HR, or sets x reps x load
- **Felt**: RPE, energy, mood, soreness, in their words
- **Notes**: weather, niggles, anything notable
```

Several sessions in one day → several blocks under one date heading. Then also:
- **Runs** → `plans/training-actuals.json` (schema in its `_schema`).
- **Strength / calisthenics** → `plans/strength-log.json`, set by set, `"confidence": "reported"` when they gave set-level detail, `"prescribed"` when only loads were confirmed.
- **New niggle** → its row in `profile.md` → Injuries and niggles.

### Strength and calisthenics: brief before, log after

Before prescribing any strength or calisthenics session, run the pre-session brief:

```
python scripts/strength-history.py --brief <session-key>     # keys from plans/session-library.json
```

It prints what they did last time, how it felt, standing technique weaknesses with their fixes, and live progression targets. **Put the relevant ones into the session you give them.** Weaknesses live in `_watchpoints` in `plans/strength-log.json`: add them as they appear, update them as they improve, delete them when fixed. `--watch` shows all of them. Afterwards, log the session (above).

### Weekly review

The bot drafts it on Sunday evening; [/weekly-review](.claude/commands/weekly-review.md) is the manual version. Template: (1) what hit the plan, (2) what didn't and why, (3) body signals for every niggle zone in the profile plus sleep, weight and HR drift, (4) a one-paragraph read of the data, (5) one adjustment, (6) next week's `current-week.md`.

### Published pages (auto-updating artifacts)

`artifacts/training-plan.html` and `artifacts/progress.html` are built from the plan files plus logged and synced data. Hooks in [.claude/settings.json](.claude/settings.json) rebuild them whenever data changes and tell you which are stale; the Stop hook won't let a turn end with new data unpublished. When told a page is stale:

1. Read the built file, then publish it with the Artifact tool. Pass the page's `url` from `artifacts/manifest.json` if it has one (same link, updated); otherwise pass the manifest's `icon` and `description` (first publish).
2. Record it: `python scripts/build-artifacts.py --mark-published <page> --url <url>`.

No Artifact tool here? `python scripts/build-artifacts.py --mark-local all`. Never put data into the page templates by hand; data flows only through `build-artifacts.py`. Details: [docs/artifacts.md](docs/artifacts.md).

### Knowledge base (Zettelkasten)

1. **Atomic notes.** One idea per file in `concepts/`, in your own words. A new principle gets a new note, not a section appended to an old one.
2. **Dense links.** Every concept links its sources, related concepts and the MOCs that include it, and says where it agrees, extends or conflicts.
3. **MOCs for navigation.** When you'd reach for "a list of X", build or extend a MOC.
4. **Literature vs permanent.** `references/` holds what an author claims; `concepts/` holds the ideas you take from it.
5. **Inbox is fleeting.** Process or delete within a week.
6. **Plans cite concepts.** Ground plan decisions in concept notes and link them. Where the knowledge base doesn't cover something, say so (and offer to distil a source) rather than inventing.

Distilling a source: [/distill](.claude/commands/distill.md). Full method: [docs/zettelkasten.md](docs/zettelkasten.md). For several sources at once, run one subagent per source in parallel; each writes its own literature note and exercise files and *returns* proposed concept / MOC edits as text, which you merge serially.

## Judgement calls

- **The A-goal wins conflicts.** When disciplines collide, the A-goal in `goals.md` wins, and you say so explicitly. See [a-goal-wins-conflicts](concepts/a-goal-wins-conflicts.md).
- **Recovery is the most likely failure mode.** Several disciplines add up to a lot of stress, so be conservative about stacking intensity. See [recovery-is-part-of-training](concepts/recovery-is-part-of-training.md) and [dont-stack-high-intensity](concepts/dont-stack-high-intensity.md).
- **Joint longevity matters as much as performance.** No volume or load jump over ~10% a week. See [progressive-overload](concepts/progressive-overload.md).
- **Trends over single readings.** One bad HRV or resting-HR morning is noise; three is a signal. Never compare Apple's SDNN with Garmin's RMSSD.
- **Check the data before concluding.** Watches record faults (GPS jumps, HR dropouts, auto-pause gaps). With Garmin details synced, `scripts/garmin/garmin-audit.py` finds them and `scripts/garmin/run-splits.py` gives honest per-km splits on moving time.

## Workspace status

> Keep this section current across sessions: setup state, connected sources, open work. Training sessions go in `logs/`, not here.

- Setup: **not done**. Run /setup.
- Data sources: none configured.
- Published pages: none yet (see `artifacts/manifest.json`).
