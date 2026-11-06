# Zettelkasten methodology for interrogating source material

A reusable playbook for taking a corpus of source documents (PDFs, EPUBs, web pages, papers) and turning them into a richly-linked Zettelkasten knowledge base in markdown — the process this workspace is built on. It is written generically, so it applies to any domain, but here the corpus is training books, papers and coaching material.

For the short, workspace-specific version of the distillation steps, see CLAUDE.md → "Distil a source" and `.claude/commands/distill.md`.

## 1. The end state you're aiming for

```
your-workspace/
  README.md           ← what this workspace is
  CLAUDE.md           ← agent instructions (workflow, conventions)
  METHODOLOGY.md      ← this file
  mindmap.md          ← navigation: resulting structure (Mermaid)
  
  resources/          ← raw source corpus (PDFs, EPUBs, papers, web saves)
                        Gitignored if copyrighted. Lives only on your laptop.
  resources/text/     ← extracted plain text per source (output of pdf-to-text.py)
  resources/images/   ← extracted figures per source
  
  references/         ← literature notes (one MD per source)
    mindmap.md        ← corpus map + distillation log
    [author-slug].md  ← per-source distilled note
  
  concepts/           ← ATOMIC permanent notes (one idea per file)
                        Densely cross-linked. The Zettelkasten core.
  
  MOCs/               ← Maps of Content (hub notes grouping concepts by theme)
                        MOC-<theme>.md
  
  inbox/              ← fleeting notes — process within a week
  
  [domain-specific/]  ← e.g. exercises/ here. For law: cases/. For cooking: recipes/.
                        Atomic per-instance reference files.
  
  scripts/            ← utilities for extraction + housekeeping
```

The principle: **information is shredded into atomic ideas** (one per file), **densely linked** between files, and **navigated via MOCs**, not by folder tree.

## 2. The five types of notes

| Type | Folder | Definition | When to write |
|---|---|---|---|
| **Literature** | `references/` | Notes ON a source — the author's claims + your reaction. One per source. | After reading a book/paper/article |
| **Permanent (concept)** | `concepts/` | YOUR OWN atomic idea, extracted from one or more sources, in your own words. | When a discrete idea emerges that's worth keeping forever |
| **MOC (map of content)** | `MOCs/` | A hub that links concepts thematically. Replaces folders for navigation. | When you have ≥5 related concepts and want a curated entry point |
| **Fleeting** | `inbox/` | Quick capture, low effort, expected to be processed or deleted within a week | Throughout the day — voice notes, half-thoughts |
| **Reference / per-instance** | domain-specific (e.g. `exercises/`, `cases/`, `recipes/`) | Atomic files for each concrete instance the corpus discusses. | When a source describes a specific named thing you'll re-look-up |

**The critical distinction**: literature notes capture *what the author said*. Concept notes capture *what you understood, in your own words*. Concept notes can — and should — synthesise across multiple sources.

## 3. The workflow (per source)

When you sit down to distil a new source:

1. **Extract the text.** If PDF: run `pdf-to-text.py`. If EPUB: rename to .zip, extract XHTML, concatenate. If web: copy-paste or use a markdown converter. Output → `resources/text/[source-slug].txt`.

2. **Read it.** Actually read, don't skim. Note in your head: what's the central thesis? What's the unique contribution vs other sources?

3. **Write the literature note** at `references/[author-slug].md`. Use this template (adapt for your domain):
   - **Central thesis** — 1–3 sentences
   - **What's unique** vs other sources you've already distilled
   - **Key principles** — 5–15 bullet ideas worth lifting verbatim
   - **Specific protocols / numbers / templates** — numeric prescriptions, named methods, frameworks
   - **Practical translation** — how this changes what you do
   - **Pages to revisit** — chapter/page numbers you'll re-open
   - **Notable quotes** — short ones, attributed
   - **Mermaid concept map** — visualise the source's internal structure

4. **Extract atomic concepts.** For each NEW idea the source introduces — *one idea per file* — create `concepts/[idea-slug].md`. Each concept note has:
   ```yaml
   ---
   id: [idea-slug]
   type: concept
   domain: [running, criminal-law, ml-systems, etc.]
   subjects: [tag1, tag2]
   sources: [[author-slug]]   # may grow as more sources discuss the same idea
   related: [[other-concept-slug]]
   mocs: [[MOC-name]]
   status: permanent
   created: YYYY-MM-DD
   ---
   # Title in your own words
   
   ## The idea (in your own words)
   1–3 paragraphs explaining the idea such that you'd understand it cold in a year.
   
   ## Practical application
   How this changes what you do.
   
   ## Related concepts
   - [[other-concept-slug]] — agrees / extends / contradicts
   
   ## Sources
   - [[author-slug]] — primary source for this idea
   - [[other-author-slug]] — also discusses; agrees with X, differs on Y
   
   ## MOCs that include this
   - [[MOC-name]]
   ```

5. **Build per-instance reference files** if your domain has concrete recurring objects (exercises, court cases, recipes, software libraries, drugs, etc). One per instance. Include images if relevant.

6. **Update or create MOCs.** If a new concept fits an existing MOC, add a link. If a new theme has emerged that ≥5 concepts share, create a new `MOCs/MOC-[theme].md`.

7. **Update `references/mindmap.md`** — mark this source as distilled, add a Mermaid sub-node listing its unique contributions, append to the "Notes index" with the date, what was created, and which MOCs were updated. (This becomes your audit trail of how the corpus was processed — invaluable later.)

8. **Log the delta** somewhere. In this workspace it's the current month's log. For a knowledge-only workspace, a single `CHANGELOG.md` or appending to the mindmap's Notes index is enough.

**The shift away from beginners' instinct**: when you find a new idea, the temptation is to APPEND it to an existing "list of principles" file. **Stop.** Create a new atomic concept note. Link to it from the existing MOC. The atomicity is what makes the system work over time.

## 4. Naming conventions

| Thing | Convention | Example |
|---|---|---|
| Concept slug | kebab-case, descriptive | `concepts/recovery-is-part-of-training.md` |
| Literature note slug | `[author-lastname]-[short-title]` | `references/daniels-running-formula.md` |
| MOC slug | `MOC-[domain]` | `MOCs/MOC-recovery-prehab.md` |
| Per-instance slug | descriptive kebab-case | `exercises/single-leg-romanian-deadlift.md` |
| Fleeting note slug | date-prefixed | `inbox/2026-05-27-while-running.md` |

**Do not** number concepts (e.g. `principle-15-X.md`). Numbering creates renumbering pain and obscures content. Slug-based naming is permanent and self-describing.

## 5. Linking principles

- **Link liberally** — every concept note should have ≥3 outbound links (to sources, related concepts, MOCs).
- **Use `[[wikilink]]` style** for portability between Obsidian, Foam, and other Z-K tools, or `[label](path/file.md)` for VS Code / GitHub compatibility. Pick one and stick to it.
- **Backlinks emerge from forward links** — a tool like Obsidian's graph view, or simple `grep -r "[[concept-slug]]"`, gives you "what links here".
- **Cross-source linking is the goal** — a concept note that cites 3 sources that disagree is more valuable than one that cites a single source. Synthesise.

## 6. Tools (already in this workspace, copy them)

| Script | Purpose | Adapt for your domain? |
|---|---|---|
| `scripts/pdf-to-text.py` | pypdf-based PDF text extraction. Handles any PDF size, including >10 pages. | No change needed — domain-agnostic |
| `scripts/convert-epubs.ps1` | Native PowerShell ZIP-extract for EPUBs (EPUB = ZIP of XHTML). No Calibre needed. | No change needed |
| `scripts/zk-relink.ps1` | Bulk find-and-replace of link paths after reorganising folder structure. | Use as template if you restructure mid-build |
| `scripts/zk-generate-concepts.ps1` | One-shot bootstrap script that generated initial concept-note skeletons from a principles list. | Adapt per domain. Or skip and write concepts manually |

To run `pdf-to-text.py` from scratch in a new workspace:

```powershell
# 1. Python 3.11 from https://www.python.org/downloads/
# 2. Install pypdf:
python -m pip install pypdf

# 3. Put PDFs in resources/, run:
python scripts/pdf-to-text.py

# Output: resources/text/[filename].txt for each PDF
```

## 7. Parallel distillation pattern (for speed)

When you have ≥4 books to distil, **parallelise via subagents**. Single message, multiple `Agent` tool calls. Each agent:

- Reads ONE source
- Writes its own literature note + creates/updates its own per-instance reference files (these are independent paths — no conflicts)
- RETURNS proposed concept-note + MOC updates as text in its response, rather than writing them directly

The main thread then merges the proposed concept/MOC updates serially — this avoids the cross-agent file-write conflicts that occur when multiple agents try to edit the same MOC file simultaneously.

In this workspace, 12 books were distilled in roughly one extended session via this pattern. Each agent took ~5–10 minutes; in parallel, the total wall-time was ~15 minutes for the longest agent.

## 8. Frontmatter schema (reusable)

The minimum useful frontmatter for each note type:

**Concept note:**
```yaml
---
id: concept-slug
type: concept
domain: [running, criminal-law, ml-systems, ...]
subjects: [tag1, tag2]
sources: [author-slug, another-author-slug]
related: [other-concept-slug]
mocs: [MOC-name]
status: permanent
created: 2026-05-27
---
```

**Literature note:**
```yaml
---
id: author-source-slug
type: literature
authors: [Last F.]
year: 2024
title: Full Title
domain: [...]
status: distilled        # values: pending, in-progress, distilled
distilled_date: 2026-05-27
---
```

**MOC:**
```yaml
---
id: MOC-name
type: moc
domain: [...]
status: active
---
```

**Per-instance reference (e.g. exercise / case / recipe):**
```yaml
---
id: instance-slug
type: [exercise | case | recipe | drug | ...]
domain: [...]
subjects: [...]
sources: [author-slug]
related: [related-instance-slug]
mocs: [MOC-name]
---
```

The `status` field is what powers a Dataview query in Obsidian like *"show me all concepts pending review"* or *"all literature notes still to distil"*.

## 9. The mindmap files

Two Mermaid-mindmap markdown files document the structure:

**`mindmap.md` (root)** — the visual map of the RESULTING knowledge base. MOCs and concepts they group, the disciplines covered, the personal / operational layout. Updated when a new MOC or a new domain emerges.

**`references/mindmap.md`** — the source corpus map + distillation log. Each branch is a source; sub-nodes are its key contributions. The "Notes index" at the bottom is a chronological record of distillation events:

> *"2026-05-22 — Daniels (2022) — Running Formula 4th ed. Drove updates to MOC-workout-types (added Daniels caps to T/I, added R workout type), MOC-paces-zones (anchored to VDOT 46 current / 49 target), MOC-training-principles (added principles 29–31). Created 4 exercise files: strides.md, daniels-circuit.md, high-knees.md, squat-thrust.md."*

This index is your audit trail of HOW you processed the corpus. Future-you will thank you for keeping it current.

## 10. Suggested first session for a new workspace

When you sit down to build a fresh knowledge base:

1. **`git init`** and add the standard `.gitignore` (exclude `resources/` if your sources are copyrighted, exclude `.env`, exclude `__pycache__/`).
2. **Create the folder skeleton**: `concepts/`, `references/`, `MOCs/`, `inbox/`, `resources/`, `scripts/`, and whatever domain-specific folder you need.
3. **Copy `scripts/pdf-to-text.py`** and `scripts/convert-epubs.ps1` from this workspace.
4. **Write `README.md`** — one paragraph: what's this workspace about, who's it for, when did you start it.
5. **Write `CLAUDE.md`** — adapt this workspace's CLAUDE.md to your domain. Key sections: workspace structure, what to read to orient, Zettelkasten principles, distillation workflow, domain-specific judgement calls.
6. **Write `mindmap.md`** — start with a thin Mermaid mindmap of just the root + a few placeholder MOCs. It'll grow.
7. **Drop your first 1–2 sources into `resources/`**, run pdf-to-text, write your first literature note + first 3–5 concepts to get the feel.
8. **Build your first MOC** when you have ≥5 related concepts.
9. **Update `references/mindmap.md`** after each source. Treat the Notes index as your changelog.

## 11. What this methodology is NOT

- **Not a research methodology** — this is a synthesis + retention system. The actual reading + critical thinking is on you.
- **Not a project management system** — for that, use a separate plans/ folder with operational state (week plans, milestones).
- **Not a CRM / database** — concepts are prose-first, not row-first. If your domain is fundamentally tabular, consider a database instead.
- **Not LLM-replaceable** — an LLM can help draft and link, but the judgement call of *what is atomic enough to deserve its own note* requires you. Atomicity is a craft, not an algorithm.

## 12. References for the methodology itself

- Sönke Ahrens — *How to Take Smart Notes* (2017) — the canonical English-language explanation of Luhmann's Zettelkasten + how to adapt it for digital workflows
- Andy Matuschak — [andymatuschak.org/notes](https://andymatuschak.org/notes) — particularly his evergreen notes essays
- Maggie Appleton — *A brief history of evergreen notes* — useful framing
- This workspace's own `CLAUDE.md` — the methodology applied to a training corpus

---

*Proven on a 12-source training corpus (running, strength, mobility, calisthenics, recovery) distilled into 60+ atomic concepts, ~180 exercise files and 15+ MOCs. The same shape works for any field where you want to keep accumulating ideas from sources for years without losing them.*
