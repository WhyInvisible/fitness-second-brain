---
description: Review the week that just ended and draft next week's plan (manual version of the bot's Sunday review)
---

The Telegram bot drafts this automatically every Sunday evening if it's deployed. Run this when it isn't, or when the athlete asks for a review here.

1. **Gather.** `python scripts/sync.py`, then `python scripts/report.py` (last completed Mon–Sun; `--current-week` if it's Sunday and the week isn't over). Read `plans/current-week.md`, this month's `logs/`, `inbox/phone-*.md` for the week, `plans/strength-log.json` entries, `profile.md`, `goals.md`, `plans/season-plan.md`, and every concept with `core: true`.
2. **Write the review** and append it to `logs/YYYY-MM.md` under `## Weekly review (week ending YYYY-MM-DD)`:
   1. **What hit the plan:** sessions completed, anything notable
   2. **What didn't:** skipped / modified / dropped intensity, and why
   3. **Body signals:** every niggle zone in `profile.md`, plus sleep, weight trend, HR drift, resting HR / HRV against baseline
   4. **Read:** one paragraph on what the week's data says
   5. **One adjustment for next week**
3. **Draft next week.** Archive the current file to `plans/archive/week-ending-YYYY-MM-DD.md`, then rewrite `plans/current-week.md` for Mon–Sun: the next week of `plans/plan-data.json`, adjusted by step 5. Keep the `| Mon | ... |` table shape the bot parses. If the adjustment changes planned days, update `plan-data.json` too (set `"revised": true` on the week) and update `plan-meta.json → reality_note` with one honest paragraph on how the block is going.
4. **Apply the principles:** the A-goal wins, no stacked hard days, ~10% ceiling, reduce rather than push through a flare-up, and never invent missing data.
5. Show the athlete the review and next week, apply their changes, then publish the stale pages (the hooks will flag them) and commit.
