# Fitness second brain

A training workspace you run with an AI agent (built for [Claude Code](https://claude.com/claude-code)). It combines:

- **A second brain:** a Zettelkasten knowledge base of training principles, workouts and exercises, grown by distilling the books and plans you trust.
- **Your plan:** imported from wherever you already have one (a coach, Runna, a spreadsheet, a book) or built with you from your goals.
- **Your data:** synced from a Garmin, Apple Watch, Strava (Coros, Polar, Suunto, Wahoo...) or plain FIT/GPX/TCX files, into one format.
- **Two live pages:** your plan with actual sessions laid over it, and your progress (heartbeats per km, pace against heart rate). They are published as private Claude Artifacts and republish themselves when new data comes in.
- **Optional:** a Telegram bot for logging from your phone, daily pings and an approve-or-refine Sunday review, plus a local dashboard.

It ships empty: no plan, no data, no one's profile. The agent sets it up by interviewing you.

## Quick start

1. **Make your own private copy.** On GitHub: *Use this template → Create a new repository → Private*. Your copy will hold your health data, so **keep it private**.
2. Clone it and open the folder in Claude Code:
   ```bash
   git clone https://github.com/<you>/<your-repo>.git && cd <your-repo>
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
   claude
   ```
3. Type **`/setup`**. The agent will:
   - ask about you: history, current fitness, availability, injuries;
   - ask about your goal: one A-goal, plus the rest;
   - **ask whether you already have a plan**, and import it or build one with you;
   - help you connect your watch (you type credentials into `.env` yourself; they never go in chat);
   - backfill a few weeks of data and publish your two pages.

After that, say "log today's run" (or `/log-training`) after sessions, and `/weekly-review` at the end of the week if you're not running the bot.

## Requirements

- Python 3.10+
- Claude Code with a claude.ai account (for the Artifact pages). Any other agent can use everything except publishing; the pages build locally.
- Optional: a Garmin / Apple Watch / Strava account; Telegram + Fly.io + Gemini and Anthropic API keys for the bot; an OpenWeatherMap key for weather.

## Connecting your data

| You use | In `.env` | Details |
|---|---|---|
| Garmin | `DATA_SOURCES=garmin` + login | [docs/data-sources.md#garmin](docs/data-sources.md#garmin) |
| Apple Watch | `DATA_SOURCES=apple_health` | Health export, or the Health Auto Export app for daily automation: [docs](docs/data-sources.md#apple-watch--apple-health) |
| Coros / Polar / Suunto / Wahoo / Zwift | `DATA_SOURCES=strava` | one-time Strava OAuth: [docs](docs/data-sources.md#strava) |
| Exported files | `DATA_SOURCES=files` | drop .fit/.gpx/.tcx in `data/inbox/files/` |
| Nothing | leave empty | log by hand; everything else still works |

Then `python scripts/sync.py`. Sources can be combined (`apple_health,strava`); the first one listed wins when two record the same session.

## How the pages stay up to date

Claude Code hooks (in `.claude/settings.json`) rebuild the pages whenever a sync, a log entry or a plan change touches their data, and make the agent republish them, to the same links, before it finishes. Data that arrives while Claude isn't running (the bot's 06:00 sync, a cron job) is picked up at the start of your next session. More detail: [docs/artifacts.md](docs/artifacts.md). To see the pages with fictional data: `python scripts/preview-example.py --open`.

## Layout

```
profile.md  goals.md          who you are, what you're training for (filled in by /setup)
plans/                        season plan, day-by-day plan, this week, run / strength / body logs
logs/                         monthly training log + weekly reviews
inbox/                        quick notes (incl. from the Telegram bot)
concepts/  MOCs/              atomic training principles + maps of content
exercises/  references/       exercise library, literature notes on sources
data/                         synced device data (normalized); raw archives are gitignored
artifacts/                    published-page templates + manifest of their URLs
scripts/                      sync + providers, page builder, reports, hooks, analysis
bot/  dashboard/              Telegram bot (Fly.io), local read-only dashboard
docs/  templates/  examples/  guides, note templates, fictional example plan files
CLAUDE.md                     the agent's operating manual
```

## Privacy

- `.env`, `bot/.env`, raw device archives, dropped-in exports and `resources/` (your books) are gitignored.
- Profile, plans, logs and synced summaries **are** committed. That's what lets the bot and your other machines see them, and it's why your copy must be a private repo.
- Artifact pages are private to your claude.ai account until you share them.

## For AI agents

Read [CLAUDE.md](CLAUDE.md) before doing anything: it has the session-start checklist, the rules (never invent data, never handle credentials in chat, private repo only), every workflow, and how publishing works. If `profile.md` still contains `<!-- setup: pending`, start with `/setup` ([.claude/commands/setup.md](.claude/commands/setup.md)).
