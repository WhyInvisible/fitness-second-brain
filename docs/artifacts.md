# Published pages (auto-updating Claude Artifacts)

Two pages are built from the workspace and published as private Claude Artifacts. Each gets a link you can keep open on your phone or share with a coach.

| Page | Built from | Shows |
|---|---|---|
| **Training Plan** (`artifacts/training-plan.html`) | `plans/plan-data.json`, `plan-meta.json`, `session-library.json`, `training-actuals.json`, `data/sync-cache.json` | Every week and day of the plan, a countdown to the A-goal, planned against actual volume, key sessions, checkpoints, clickable strength-session cards, and each logged day's actual numbers and how it felt |
| **Training Progress** (`artifacts/progress.html`) | `training-actuals.json`, `data/sync-cache.json`, `plan-data.json` | Every run: cardiac cost (heartbeats per km), pace against heart rate, the HR and pace trends, and a table |

Runs that were **synced but not yet reviewed** appear straight away, labelled "synced, not yet reviewed". Once the agent logs the run with the athlete's own comments (`/log-training`), the reviewed entry replaces it.

## How "automatic" works

Publishing an artifact needs Claude's Artifact tool, so the automation lives in Claude Code hooks ([.claude/settings.json](../.claude/settings.json) → [scripts/hooks/workspace_hook.py](../scripts/hooks/workspace_hook.py)):

1. **New data lands.** `scripts/sync.py` runs (by you, the agent, the bot, or cron), or the agent writes a log entry or a plan change.
2. **PostToolUse hook.** After every Write / Edit / Bash in a Claude Code session, the hook rebuilds both pages (milliseconds, standard library only). If a page's content changed, it tells the agent which pages to publish and how.
3. **The agent publishes.** It uses the Artifact tool, reusing each page's URL from `artifacts/manifest.json` so the links stay the same, then records it: `python scripts/build-artifacts.py --mark-published <page> --url <url>`.
4. **Stop hook.** If the agent tries to finish its turn while a page with new data is still unpublished, the hook blocks once and reminds it. It never loops.
5. **SessionStart hook.** Data that arrived while Claude wasn't running (the bot's 06:00 sync, a cron job) is caught at the start of the next session: the agent's first job is to republish.

`artifacts/manifest.json` is committed, so the page URLs survive across machines. The built HTML files are gitignored because they're derived.

## Controls

| Want | Do |
|---|---|
| Rebuild and see what's stale | `python scripts/build-artifacts.py` |
| Publish now | `/publish` |
| Stop the publish nagging (keep the session-start report) | `AUTO_PUBLISH_ARTIFACTS=false` in `.env` |
| No Artifact tool in this environment (another agent, no claude.ai login) | `python scripts/build-artifacts.py --mark-local all`, then open the HTML files locally |
| Preview with fictional data | `python scripts/preview-example.py --open` |
| Change the layout or wording | edit `artifacts/templates/*.html`. Data is injected at the `__PLACEHOLDER__` markers; `scripts/build-artifacts.py` fills them |

Artifacts are private by default. Sharing a link is your choice, made in claude.ai.
