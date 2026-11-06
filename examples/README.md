# Examples (fictional)

A made-up two-week half-marathon block that shows the shape of every plan file. Nothing here is read by the tooling. Copy the shape, never the content.

| File | Real location | What it holds |
|---|---|---|
| `plan-data.example.json` | `plans/plan-data.json` | Weeks → days. Each day: `date`, `dow`, `label`, `km`, `type` (rest, easy, strides, steady, lt1, lt2, mp, long, race), `pace`, optional `sessions` (keys into the session library), `note`, `cal`, `key` (true = show in "Key sessions"). Each week: `week`, `phase`, `start`, `end`, `total`, optional `tag`, `revised`. |
| `plan-meta.example.json` | `plans/plan-meta.json` | Page header and optional extras: event name and date (countdown), stat chips, checkpoints, notes, footer, `long_run_km` (the threshold above which a run counts as "long" on the progress page). Every key is optional. |
| `session-library.example.json` | `plans/session-library.json` | Strength / mobility sessions referenced from the plan. Rendered as clickable chips that open a table. `kind` (legs, upper, stability, skill, yoga) sets the chip colour. |
| `training-actuals.example.json` | `plans/training-actuals.json` | Reviewed runs keyed by date. |

Preview the pages with this data (writes to a scratch copy, touches nothing real):

```bash
python scripts/preview-example.py
```
