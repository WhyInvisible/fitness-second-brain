"""Workspace I/O for the bot.

In local dev: workspace = parent dir of bot/.
In cloud deploy: workspace = a git clone managed by this module.

The bot only writes to:
  inbox/phone-YYYY-MM-DD.md   (timestamped notes from Telegram)
  plans/current-week.md       (weekly review pipeline only, after approval)
  logs/YYYY-MM.md             (weekly review pipeline only, after approval)

All other reads are passive.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import git


def _git_url_with_token() -> str | None:
    url = os.getenv("WORKSPACE_REPO_URL", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not url:
        return None
    # https://github.com/user/repo.git -> https://<token>@github.com/user/repo.git
    if token and url.startswith("https://"):
        return url.replace("https://", f"https://{token}@", 1)
    return url


def workspace_root() -> Path:
    """Return path to the workspace.

    - Local dev (no WORKSPACE_REPO_URL): bot/ lives inside the workspace.
    - Cloud: clone the repo to /tmp/workspace and use that.
    """
    repo_url = _git_url_with_token()
    if not repo_url:
        # Local mode — workspace is parent dir of bot/
        return Path(__file__).resolve().parent.parent

    # Cloud mode
    target = Path(os.getenv("WORKSPACE_DIR", "/tmp/workspace"))
    branch = os.getenv("WORKSPACE_REPO_BRANCH", "main")
    if not target.exists():
        git.Repo.clone_from(repo_url, target, branch=branch, depth=50)
    return target


def pull_latest() -> tuple[bool, str]:
    """Pull latest from origin. No-op in local mode."""
    root = workspace_root()
    if not (root / ".git").exists():
        return False, "not a git repo (local dev mode)"
    repo = git.Repo(root)
    try:
        info = repo.remotes.origin.pull()
        return True, str(info[0]) if info else "up-to-date"
    except Exception as e:
        return False, f"pull failed: {e}"


def commit_and_push(message: str, paths: list[Path] | None = None) -> tuple[bool, str]:
    """Commit specified paths (or all changes) and push. Returns (ok, info)."""
    root = workspace_root()
    if not (root / ".git").exists():
        return False, "not a git repo (local dev mode)"
    repo = git.Repo(root)
    if paths:
        repo.index.add([str(p.relative_to(root)) for p in paths])
    else:
        repo.git.add(A=True)
    if not repo.is_dirty(untracked_files=True):
        return True, "no changes"
    repo.index.commit(message)
    try:
        repo.remotes.origin.push()
        return True, "pushed"
    except Exception as e:
        return False, f"commit ok, push failed: {e}"


# ---------- phone-input inbox ----------

def append_inbox_note(text: str, *, when: dt.datetime | None = None) -> Path:
    """Append a timestamped note to inbox/phone-YYYY-MM-DD.md. Returns path written."""
    when = when or dt.datetime.now()
    root = workspace_root()
    inbox = root / "inbox"
    inbox.mkdir(exist_ok=True)
    p = inbox / f"phone-{when:%Y-%m-%d}.md"
    if not p.exists():
        p.write_text(f"# Phone-input notes — {when:%A %d %B %Y}\n\n", encoding="utf-8")
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n### {when:%H:%M}\n{text.strip()}\n")
    return p


def list_inbox_for_week(start: dt.date, end: dt.date) -> list[tuple[Path, str]]:
    """Return [(path, text)] for any phone-YYYY-MM-DD.md inside the date range."""
    root = workspace_root()
    inbox = root / "inbox"
    out: list[tuple[Path, str]] = []
    if not inbox.exists():
        return out
    for p in sorted(inbox.glob("phone-*.md")):
        try:
            d = dt.date.fromisoformat(p.stem.removeprefix("phone-"))
        except ValueError:
            continue
        if start <= d <= end:
            out.append((p, p.read_text(encoding="utf-8")))
    return out


# ---------- MD discovery for agent retrieval ----------

KNOWLEDGE_DIRS = ["concepts", "MOCs", "exercises", "references", "plans", "logs"]


def list_knowledge_files() -> list[Path]:
    """All MD files the agent can search/cite, plus the root-level orientation files."""
    root = workspace_root()
    out: list[Path] = []
    for fname in ("CLAUDE.md", "profile.md", "goals.md", "mindmap.md"):
        if (root / fname).exists():
            out.append(root / fname)
    for d in KNOWLEDGE_DIRS:
        dirp = root / d
        if dirp.exists():
            out.extend(sorted(dirp.glob("*.md")))
    return out


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def workspace_root_relative(path: Path) -> str:
    """File path relative to workspace, for citation."""
    try:
        return str(path.relative_to(workspace_root()))
    except ValueError:
        return str(path)
