#!/usr/bin/env python3
"""Sync exercises/ files with the free-exercise-db dataset.

For each .md file in exercises/, find the best fuzzy match in the public-domain
free-exercise-db (yuhonas/free-exercise-db on GitHub). If confidence > threshold,
add frontmatter fields (exercisedb_id, exercisedb_match_score) and append a
"## Reference demonstration" section with the image URL.

No API key needed. No rate limits. Public-domain Unlicense data.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from rapidfuzz import fuzz, process

DATA_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMG_BASE = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
MATCH_THRESHOLD = 80  # 0-100, anything below skipped. token_set_ratio is strict-by-design (requires actual word overlap), no partial substring matching

ROOT = Path(__file__).resolve().parent.parent
EX_DIR = ROOT / "exercises"
CACHE = ROOT / "scripts" / "_exercisedb-cache.json"


def fetch_data() -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    print(f"Downloading {DATA_URL}...")
    req = urllib.request.Request(DATA_URL, headers={"User-Agent": "fitness-planner/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    CACHE.write_text(json.dumps(data), encoding="utf-8")
    print(f"  cached {len(data)} exercises -> {CACHE.relative_to(ROOT)}")
    return data


def slug_to_query(slug: str) -> str:
    """Convert 'mcgill-curl-up' -> 'curl up' (strip author prefixes + normalise)."""
    for prefix in ("mcgill-", "sommer-", "dicharry-", "pavel-", "daniels-",
                   "pfitz-", "low-", "lecorre-", "matthews-"):
        if slug.startswith(prefix):
            slug = slug[len(prefix):]
    s = slug.replace("-", " ")
    # Normalise plurals/possessives that wreck token matching
    tokens = []
    for t in s.split():
        # Strip simple trailing 's' on words >3 chars (aparts -> apart, raises -> raise)
        # Don't touch short words (us, is, abs).
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        tokens.append(t)
    return " ".join(tokens)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, body). frontmatter is '' if none."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    fm_end = end + 4  # past the closing ---
    # advance past trailing newline
    while fm_end < len(text) and text[fm_end] in "\n\r":
        fm_end += 1
    return text[:fm_end], text[fm_end:]


def upsert_frontmatter_field(fm: str, key: str, value: str) -> str:
    """Insert or replace a YAML field in a frontmatter block. Crude but ok."""
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", re.MULTILINE)
    line = f"{key}: {value}"
    if pattern.search(fm):
        return pattern.sub(line, fm)
    # Insert before the closing ---
    lines = fm.rstrip().split("\n")
    if lines and lines[-1].strip() == "---":
        lines.insert(-1, line)
        return "\n".join(lines) + "\n"
    return fm.rstrip() + f"\n{line}\n"


def reference_section(ex: dict) -> str:
    name = ex.get("name", "")
    eid = ex.get("id", "")
    images = ex.get("images") or []
    image_urls = [IMG_BASE + p for p in images]
    primary = ", ".join(ex.get("primaryMuscles") or []) or "?"
    equip = ex.get("equipment") or "?"
    level = ex.get("level") or "?"
    mechanic = ex.get("mechanic") or "?"
    cat = ex.get("category") or "?"
    instr = ex.get("instructions") or []

    md = ["## Reference demonstration (free-exercise-db)\n",
          f"- **Matched:** *{name}* (id `{eid}`)",
          f"- **Primary muscles:** {primary}",
          f"- **Equipment:** {equip}",
          f"- **Level / mechanic / category:** {level} / {mechanic} / {cat}\n"]
    if image_urls:
        md.append("**Demonstration images:**\n")
        for url in image_urls:
            md.append(f"![{name}]({url})")
        md.append("")
    if instr:
        md.append("**Reference instructions (free-exercise-db):**")
        for i, step in enumerate(instr, 1):
            md.append(f"{i}. {step}")
        md.append("")
    md.append(f"_Source: [free-exercise-db]({DATA_URL}) (Unlicense / public domain)._\n")
    return "\n".join(md)


def has_existing_section(body: str) -> bool:
    return "## Reference demonstration (free-exercise-db)" in body


def remove_existing_section(body: str) -> str:
    marker = "## Reference demonstration (free-exercise-db)"
    idx = body.find(marker)
    if idx < 0:
        return body
    # Find next "## " heading at same level (not "### "), to end the section
    next_h = re.search(r"^## (?!Reference demonstration)", body[idx + 1:], re.MULTILINE)
    if next_h:
        end = idx + 1 + next_h.start()
        return body[:idx].rstrip() + "\n\n" + body[end:]
    return body[:idx].rstrip() + "\n"


def main() -> int:
    if not EX_DIR.exists():
        print(f"No exercises/ dir at {EX_DIR}", file=sys.stderr)
        return 1
    data = fetch_data()
    # Build name -> exercise lookup; pre-normalise names for matching
    name_to_ex = {d["name"]: d for d in data if "name" in d}
    norm_names = {n: slug_to_query(n.lower().replace(" ", "-")) for n in name_to_ex}
    # Reverse: normalised -> original
    norm_to_orig: dict[str, list[str]] = {}
    for orig, norm in norm_names.items():
        norm_to_orig.setdefault(norm, []).append(orig)
    norm_choices = list(norm_to_orig.keys())

    md_files = sorted(EX_DIR.glob("*.md"))
    if not md_files:
        print(f"No .md files in {EX_DIR}", file=sys.stderr)
        return 1
    print(f"\n{len(md_files)} exercise files to match against {len(name_to_ex)} db entries\n")

    matched = 0
    skipped = 0
    weak = []

    for f in md_files:
        if f.name == "README.md":
            continue
        slug = f.stem
        query = slug_to_query(slug)
        # token_set_ratio: word-overlap based, no partial substring (avoids "curl up" -> "wrist curl over a bench"-style false positives).
        # Also require query tokens to substantially overlap with the candidate tokens.
        r = process.extractOne(query, norm_choices, scorer=fuzz.token_set_ratio)
        text = f.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)

        if not r or r[1] < MATCH_THRESHOLD:
            if r:
                weak.append((slug, query, r[0], r[1]))
            # Clean up any previous bad section + frontmatter (from earlier runs)
            cleaned_body = remove_existing_section(body)
            cleaned_fm = fm
            for key in ("exercisedb_id", "exercisedb_match", "exercisedb_score"):
                cleaned_fm = re.sub(rf"^{key}:\s*.*\n", "", cleaned_fm, flags=re.MULTILINE)
            if cleaned_body != body or cleaned_fm != fm:
                f.write_text(cleaned_fm + cleaned_body, encoding="utf-8", newline="\n")
                print(f"  - {slug:50s} (cleared previous mismatch)")
            skipped += 1
            continue

        best_norm, score, _ = r
        # Two precision guards on top of the fuzzy score:
        # (A) length-ratio: reject when candidate has >2.5x more tokens than query
        #     (token_set_ratio gives 100 for subset matches regardless of candidate length)
        # (B) shared-tokens: require min(query_tokens, 2) tokens overlap
        #     (rejects "back extension" -> "leg extension" type matches where only one token overlaps)
        q_tokens = set(query.split())
        c_tokens = set(best_norm.split())
        shared = q_tokens & c_tokens
        required_shared = min(len(q_tokens), 2)
        too_long = len(c_tokens) > len(q_tokens) * 2.5
        too_few_shared = len(shared) < required_shared
        if too_long or too_few_shared:
            reason = "too-generic" if too_long else "too-few-shared-tokens"
            weak.append((slug, query, best_norm, score))
            cleaned_body = remove_existing_section(body)
            cleaned_fm = fm
            for key in ("exercisedb_id", "exercisedb_match", "exercisedb_score"):
                cleaned_fm = re.sub(rf"^{key}:\s*.*\n", "", cleaned_fm, flags=re.MULTILINE)
            if cleaned_body != body or cleaned_fm != fm:
                f.write_text(cleaned_fm + cleaned_body, encoding="utf-8", newline="\n")
                print(f"  - {slug:50s} (cleared -- {reason})")
            skipped += 1
            continue
        # Pick the first original name mapping to that normalised form
        name = norm_to_orig[best_norm][0]
        ex = name_to_ex[name]

        fm = upsert_frontmatter_field(fm, "exercisedb_id", f'"{ex.get("id","")}"')
        fm = upsert_frontmatter_field(fm, "exercisedb_match", f'"{name}"')
        fm = upsert_frontmatter_field(fm, "exercisedb_score", str(score))
        body = remove_existing_section(body).rstrip() + "\n\n" + reference_section(ex)
        new_text = fm + body
        f.write_text(new_text, encoding="utf-8", newline="\n")
        matched += 1
        print(f"  + {slug:50s} -> {name}  ({score:.0f})")

    print(f"\nMatched: {matched}  Skipped: {skipped}")
    if weak:
        print("\nWeak matches (below threshold, NOT applied) -- review manually if any look right:")
        for slug, query, name, score in weak[:30]:
            print(f"  {slug:40s}  '{query}'  ~  '{name}'  ({score:.0f})")
        if len(weak) > 30:
            print(f"  ... and {len(weak) - 30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
