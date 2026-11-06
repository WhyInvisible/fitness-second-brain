---
description: Distil a book, paper or plan in resources/ into the knowledge base (literature note + atomic concepts + exercises + MOCs)
---

Distil the source the user names (or ask which one) following the Zettelkasten rules in CLAUDE.md. Full method: [docs/zettelkasten.md](../../docs/zettelkasten.md).

1. **Read it.** Sources live in `resources/` (gitignored). PDFs: `python scripts/pdf-to-text.py "<part of filename>"` → `resources/text/`. Long books: read in chunks, or fan out one subagent per part. Each subagent returns proposed notes as text, and you merge them serially.
2. **Literature note** → `references/<author-slug>.md` from `templates/reference.md`: central thesis, specific protocols and numbers, key principles, what's unique against the existing notes, practical translation for this athlete, pages to revisit, a few **short** quotes, a Mermaid concept map. Summaries in your own words, not copies.
3. **Atomic concepts** → `concepts/<slug>.md` from `templates/concept.md`: one new idea per file, in your words, densely linked to existing concepts. Say explicitly where it agrees with, extends or conflicts with them. Before creating a note, search `concepts/` for one that already covers the idea and extend that instead. Mark `core: true` only for principles that should bind every weekly review (keep that set small).
4. **Exercises** → `exercises/<slug>.md` from `templates/exercise.md` for every exercise worth recommending. No copied book figures; use your own images, public-domain ones, or links. Run `python scripts/sync-exercisedb.py` afterwards for free demo images.
5. **MOCs.** Link new concepts from the relevant `MOCs/MOC-*.md`; create a new MOC once a theme has five or more notes. Add a row to `MOCs/MOC-sources.md`.
6. **Log it** in this month's `logs/YYYY-MM.md`: what was distilled and which files changed.
7. If the source changes how this athlete should train, say so and propose the plan edit. Don't apply it unasked.
