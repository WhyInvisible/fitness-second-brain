"""Q&A agent over the workspace markdown.

Strategy: ~500 MD files, ~few MB total. Too big for a single LLM call, but small
enough that a smart keyword/path search picks the right ~10 files for any query,
then we send those + the always-on orientation files (CLAUDE.md, profile.md, goals.md,
current-week.md) to Gemini for the answer.

No vector DB. No embedding cost. Just substring + slug matching over filenames
+ first-200-chars of each file. Plenty good for 500 files.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

from . import storage

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# How many context files to send for any single query
MAX_CONTEXT_FILES = 12
# How much of each file to send (chars)
MAX_FILE_CHARS = 8000

# Always-include files: lay the foundation for any answer (plus plans/season-*.md).
ORIENTATION_FILES = [
    "profile.md",
    "goals.md",
    "plans/current-week.md",
]


# ---------- retrieval ----------

_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "but", "for", "to", "in", "on", "at",
    "with", "is", "are", "was", "were", "be", "been", "do", "does", "did",
    "i", "me", "my", "you", "your", "he", "she", "we", "they", "it",
    "this", "that", "these", "those", "what", "when", "where", "why", "how",
    "should", "would", "could", "can", "will", "next", "last", "week",
}


def _tokens(s: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]{3,}", s.lower())
    return {t for t in toks if t not in _STOPWORDS}


def _score_file(query_tokens: set[str], path: Path, body: str) -> float:
    """Higher = more relevant. Weights filename heavily, then folder, then body match count."""
    score = 0.0
    slug_tokens = set(re.split(r"[-_/]", path.stem.lower()))
    # Slug overlap is the strongest signal
    score += 3.0 * len(query_tokens & slug_tokens)
    # Folder hint (concepts/, MOCs/, exercises/, etc.)
    parent_tokens = set(re.split(r"[-_/]", path.parent.name.lower()))
    score += 1.0 * len(query_tokens & parent_tokens)
    # Body — count occurrences of each query token (capped per token to avoid runaways)
    body_lower = body.lower()
    for tok in query_tokens:
        # Word-boundary count, capped at 5 per token
        n = min(5, len(re.findall(rf"\b{re.escape(tok)}\b", body_lower)))
        score += 0.4 * n
    return score


def pick_context(query: str, max_files: int = MAX_CONTEXT_FILES) -> list[Path]:
    """Return the top-N most-likely-relevant files for a query."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    candidates = []
    for p in storage.list_knowledge_files():
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        s = _score_file(q_tokens, p, body)
        if s > 0:
            candidates.append((s, p))

    candidates.sort(key=lambda x: -x[0])
    return [p for _, p in candidates[:max_files]]


# ---------- prompting ----------

SYSTEM_PROMPT = """You are the athlete's fitness planning assistant. Their profile, goals and
current plan are in the context below — read them for who they are and what they're
training for.

You answer questions about THEIR training, plans, and concept notes. You have access to
a curated set of their markdown files included below as context — base your answer on
those, NEVER make up training data, paces, or exercise specifics.

Style:
- Direct, concise. Match the experience level described in their profile.
- Cite the file(s) you drew from at the end like: [plans/current-week.md, MOCs/MOC-running-strength.md]
- If you're unsure or the context doesn't cover it, say so plainly — don't guess.
- For planning judgments (volume, intensity, recovery), defer to the principles in their
  concept notes (recovery-is-part-of-training, dont-stack-high-intensity,
  a-goal-wins-conflicts, progressive-overload, etc).
- For specific exercises, link to the exercise file by slug.

If they ask you to log a session, niggle, or RPE note, reply with the literal text:
LOG_INTENT: <a cleaned-up restatement of what they said, suitable for the inbox file>
and nothing else. The harness will then save it. Use this when their message is clearly
a piece of training data to record (e.g. "RPE 7 on the long run", "shoulder
twinged during pull-ups", "skipped Tuesday leg day, knee was off").
"""


def _build_context_block(files: list[Path]) -> str:
    """Serialize a set of files into a single prompt-friendly context block."""
    blocks = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")[:MAX_FILE_CHARS]
        except OSError:
            continue
        rel = storage.workspace_root_relative(p)
        blocks.append(f"=== FILE: {rel} ===\n{text}\n")
    return "\n".join(blocks)


def answer(user_query: str) -> str:
    """Run a Q&A turn with Gemini. Returns the text reply."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "[bot misconfig: GEMINI_API_KEY not set]"

    # Always include orientation files
    root = storage.workspace_root()
    orientation = [root / f for f in ORIENTATION_FILES if (root / f).exists()]
    orientation += sorted((root / "plans").glob("season-*.md"))[:1]
    retrieved = pick_context(user_query)
    # Dedupe (orientation may overlap retrieved)
    seen = set()
    files: list[Path] = []
    for p in orientation + retrieved:
        if p not in seen:
            files.append(p)
            seen.add(p)
    files = files[:MAX_CONTEXT_FILES]

    context_block = _build_context_block(files)
    today = dt.date.today()
    date_header = (
        f"TODAY IS {today.strftime('%A %d %B %Y')} ({today.isoformat()}). "
        f"Use this to interpret 'today', 'tomorrow', 'this week', etc. "
        f"The week runs Monday-Sunday."
    )
    prompt = f"{date_header}\n\nCONTEXT FROM THEIR WORKSPACE:\n{context_block}\n\nTHEIR MESSAGE:\n{user_query}"

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return resp.text or "[empty reply]"
