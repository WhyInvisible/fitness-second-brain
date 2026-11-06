---
description: Rebuild the published pages (Claude Artifacts) and publish any that are out of date
---

1. `python scripts/build-artifacts.py`. This rebuilds `artifacts/training-plan.html` and `artifacts/progress.html` and lists each page's state.
2. For every page marked **NEEDS PUBLISH**: read the built file, then publish it with the Artifact tool.
   - If `artifacts/manifest.json` has a `url` for it, pass that `url` so the same link updates.
   - Otherwise it's a first publish: pass the `icon` and `description` from the manifest.
3. Record each one: `python scripts/build-artifacts.py --mark-published <page> --url <artifact url>`.
4. Reply with the links.

No Artifact tool in this environment? Run `python scripts/build-artifacts.py --mark-local all` and tell the user they can open the HTML files locally. Details: [docs/artifacts.md](../../docs/artifacts.md).
