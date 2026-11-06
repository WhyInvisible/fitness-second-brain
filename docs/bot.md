# Telegram bot (optional)

A phone interface for the workspace, running 24/7 on Fly.io's smallest machine. It clones your **private** copy of this repo, writes notes back to it, and pushes.

```
 phone (Telegram) ──► bot on Fly.io ──► Gemini Flash (Q&A)  /  Claude (Sunday review)
                          │  ▲
             git push     ▼  │  git pull
                    your private GitHub repo  ◄──►  your computer (Claude Code, dashboard)
```

## What it does

| Command | |
|---|---|
| `/note <text>` | Append a timestamped note to `inbox/phone-YYYY-MM-DD.md` (RPE, niggles, how a session felt) |
| `/ask <question>` | Q&A over your profile, plans, logs and notes (Gemini Flash) |
| `/today`, `/tomorrow`, `/week` | Rows from `plans/current-week.md` |
| `/review [last\|this\|YYYY-MM-DD]` | Draft a weekly review + next week with Claude, with ✅ Approve / ✏️ Refine / ❌ Reject buttons |
| `/datasync` | Run the data sync now |
| `/morning`, `/evening` | Fire the daily pings now |
| `/sync` | `git pull` the latest workspace |
| free text | Questions get answered; training statements get logged as notes |

Scheduled (in `TIMEZONE`):

| Time | Job |
|---|---|
| 06:00 | Data sync (`scripts/sync.py --cloud`: Garmin / Strava), commits `data/`. Alerts you on auth failures. |
| 07:00 | Morning ping: today's sessions, last night's sleep / resting HR / HRV |
| 20:00 | Evening ping: tomorrow's sessions, and a flag if today's planned run wasn't synced |
| Sun 20:15 | Weekly review drafted by Claude, with Approve / Refine / Reject. Approving writes the review to `logs/`, archives the old week and writes the new `plans/current-week.md` |

Approved reviews and synced data change the published pages; the next Claude Code session republishes them (see [artifacts.md](artifacts.md)).

## Set up

You need: a Telegram account, a free [Fly.io](https://fly.io) account (a card on file; the machine costs about $2/month nominal, usually inside the allowance), a [Gemini API key](https://aistudio.google.com/apikey) (free tier), an [Anthropic API key](https://console.anthropic.com/settings/keys) (the Sunday review costs pennies a week), and this workspace pushed to a **private** GitHub repo.

1. **Create the bot.** In Telegram, message @BotFather → `/newbot` → keep the token.
2. **Local test.**
   ```bash
   cp bot/.env.example bot/.env          # fill in TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ANTHROPIC_API_KEY
   python3 -m pip install -r bot/requirements.txt
   python3 -m bot.main
   ```
   Message your bot. It replies with your numeric user ID. Put that in `TELEGRAM_ALLOWED_USER_ID` (the bot then ignores everyone else) and restart. Locally the bot works on this folder directly.
3. **GitHub token.** Create a fine-grained PAT at <https://github.com/settings/personal-access-tokens> scoped to only your workspace repo, Contents: Read and write.
4. **Deploy.**
   ```bash
   # install flyctl: https://fly.io/docs/flyctl/install/
   fly auth login
   fly apps create <your-app-name>
   # edit bot/fly.toml: app = "<your-app-name>", primary_region, TIMEZONE
   ```
   Set secrets without echoing them. `fly secrets import` reads NAME=VALUE lines from stdin:
   ```bash
   grep -v '^#' bot/.env | grep . | fly secrets import --app <your-app-name>
   # data-source credentials, so the 06:00 sync can run in the cloud:
   grep -E '^(DATA_SOURCES|GARMIN_|STRAVA_)' .env | fly secrets import --app <your-app-name>
   fly secrets set --app <your-app-name> WORKSPACE_REPO_URL=https://github.com/<you>/<repo>.git
   ```
   Then deploy (from the repo root):
   ```bash
   fly deploy --app <your-app-name> --config bot/fly.toml --dockerfile bot/Dockerfile --remote-only
   ```
5. **Stop the local copy.** Telegram allows one polling client per bot.

## Operate

| Task | Command |
|---|---|
| Logs | `fly logs --app <app> --no-tail` (they contain the bot token in URLs, so don't share raw output) |
| Is it running? | `fly machines list --app <app>`; start a stopped one with `fly machines start <id> --app <app>` |
| Deploy a change | commit + push, then the `fly deploy` line above |
| Rotate a secret | revoke and recreate it at the provider, update `bot/.env`, re-run the matching `fly secrets import` line (it redeploys) |

## Common issues

- **No replies.** Check the logs. `Conflict: terminated by other getUpdates request` → another copy is polling (probably a local run). `401 Unauthorized` → token revoked; reset `TELEGRAM_BOT_TOKEN`. Nothing recent → machine stopped.
- **"Data sync: auth failure".** Garmin: log in once at connect.garmin.com. Strava: redo the `--auth` step in [data-sources.md](data-sources.md) and update `STRAVA_REFRESH_TOKEN`.
- **Sunday review never arrived.** Check the logs around 20:15 and that the machine was running. Run `/review` to retry.
- **Can't push to GitHub.** The PAT expired or lacks Contents: write. Generate a new one and update `GITHUB_TOKEN`.

## Models

- Q&A: `gemini-2.5-flash` (override with `GEMINI_MODEL`).
- Weekly review: `claude-opus-5-5` with high effort and server-side refusal fallbacks (override with `ANTHROPIC_MODEL`, e.g. `claude-sonnet-5-5` to cut cost).
