#!/usr/bin/env python3
"""Build the published pages from the fictional data in examples/, in a temp copy.

Shows what the Training Plan and Progress pages look like before you have any
data of your own. Touches nothing in the real workspace.

  python scripts/preview-example.py            # prints the paths of the built pages
  python scripts/preview-example.py --open     # and opens them in the browser
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="fitness-preview-"))
    (tmp / "scripts").mkdir()
    (tmp / "plans").mkdir()
    shutil.copy(ROOT / "scripts" / "build-artifacts.py", tmp / "scripts")
    shutil.copytree(ROOT / "artifacts" / "templates", tmp / "artifacts" / "templates")
    for name in ("plan-data", "plan-meta", "session-library", "training-actuals"):
        shutil.copy(ROOT / "examples" / f"{name}.example.json", tmp / "plans" / f"{name}.json")
    subprocess.run([sys.executable, str(tmp / "scripts" / "build-artifacts.py")], check=True)
    pages = [tmp / "artifacts" / "training-plan.html", tmp / "artifacts" / "progress.html"]
    print("\nPreview pages:\n" + "\n".join(f"  {p}" for p in pages))
    if "--open" in sys.argv:
        for p in pages:
            webbrowser.open(p.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
