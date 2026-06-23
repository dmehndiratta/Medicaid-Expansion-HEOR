"""Local convenience: copy the static payload into the Astro site's public/<slug>/.

Mirrors the CI sync-website step (SETUP.md §3) for local preview. Copies the WHOLE
site/ payload (dashboard.html, report.html, data/*.json) into
<website-dir>/public/medicaid-expansion-heor/. Never used in CI; the workflow does the
cross-repo push via WEBSITE_REPO_TOKEN.

  python sync_to_website.py [--website-dir D:/Website]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent
SLUG = "medicaid-expansion-heor"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--website-dir", default="D:/Website")
    args = ap.parse_args()
    dest = Path(args.website_dir) / "public" / SLUG
    src = REPO / "site"
    (dest / "data").mkdir(parents=True, exist_ok=True)
    for name in ("dashboard.html", "report.html"):
        if (src / name).exists():
            shutil.copy2(src / name, dest / name)
    for j in (src / "data").glob("*.json"):
        shutil.copy2(j, dest / "data" / j.name)
    print(f"[sync] copied site/ -> {dest}")
    print("[sync] run `astro build` in the Website repo (or push to trigger Cloudflare).")


if __name__ == "__main__":
    main()
