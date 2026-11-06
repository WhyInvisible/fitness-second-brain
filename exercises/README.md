# Exercise library

One file per exercise, built up as sources are distilled and as exercises enter the plan. Start from [../templates/exercise.md](../templates/exercise.md). The dashboard's `/exercises` page groups them by movement pattern.

- **Naming:** kebab-case full names (`romanian-deadlift.md`, not `rdl.md`). Separate files for genuinely different movements; one file with an "Equipment variants" section when only the equipment differs.
- **Images:** `exercises/images/<slug>/`. Only images you may republish: your own, public-domain sets, or links. Don't copy figures out of books into a repo you might share.
- **Demo links:** `python scripts/sync-exercisedb.py` fuzzy-matches every exercise file against the public-domain [free-exercise-db](https://github.com/yuhonas/free-exercise-db) and adds a demo-image section to the ones it finds.
- **Sessions:** exercises are grouped into sessions in [../plans/session-library.json](../plans/session-library.json), which the plan page renders as clickable chips.
