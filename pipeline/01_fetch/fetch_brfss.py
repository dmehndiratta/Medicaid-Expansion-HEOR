"""Fetch CDC BRFSS annual files (idempotent, dated, cached).

Real path: BRFSS publishes one SAS transport (.XPT, zipped) per year at
  https://www.cdc.gov/brfss/annual_data/<YYYY>/files/LLCP<YYYY>XPT.zip
Drop the unzipped XPTs into data/raw/brfss/real/ (or let --download fetch them) and
this stage stamps data_mode="real". pyreadstat reads XPT; design vars are retained.

Fallback path: if no real files are present, generate the calibrated synthetic panel
(synthetic.py) into data/raw/brfss/synthetic/ and stamp data_mode="synthetic". The
mode is written to data/processed/data_mode.json and threaded into every downstream
JSON so a synthetic run is never mistaken for a finding.

This stage is idempotent: it skips regeneration if a fresh snapshot already exists.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import RAW, PROCESSED, load_config, today, write_json  # noqa: E402
from pipeline import synthetic  # noqa: E402

REAL_DIR = RAW / "brfss" / "real"
SYN_DIR = RAW / "brfss" / "synthetic"
BRFSS_URL = "https://www.cdc.gov/brfss/annual_data/{yr}/files/LLCP{yr}XPT.zip"


def _real_files() -> list[Path]:
    if not REAL_DIR.exists():
        return []
    # Windows glob is case-insensitive, so *.XPT and *.xpt each match every file; dedupe.
    seen, out = set(), []
    for p in sorted(list(REAL_DIR.glob("*.XPT")) + list(REAL_DIR.glob("*.xpt"))):
        if str(p).lower() not in seen:
            seen.add(str(p).lower())
            out.append(p)
    return out


def fetch(force: bool = False) -> dict:
    config = load_config()
    real = _real_files()
    if real:
        mode = "real"
        snapshot = REAL_DIR
        years = [config["window"]["start"], config["window"]["end"]]
        print(f"[fetch_brfss] data_mode=real — {len(real)} XPT files in {REAL_DIR}")
    else:
        mode = "synthetic"
        SYN_DIR.mkdir(parents=True, exist_ok=True)
        out = SYN_DIR / "brfss_synthetic.parquet"
        if out.exists() and not force:
            print(f"[fetch_brfss] synthetic snapshot fresh: {out} (use --force to regen)")
        else:
            panel = synthetic.generate_brfss(config)
            panel.to_parquet(out, index=False)
            print(f"[fetch_brfss] data_mode=synthetic — generated {len(panel):,} rows -> {out}")
        snapshot = SYN_DIR
        years = list(range(config["window"]["start"], config["window"]["end"] + 1))

    PROCESSED.mkdir(parents=True, exist_ok=True)
    meta = {
        "source": "brfss",
        "data_mode": mode,
        "vintage": today(),
        "snapshot_dir": str(snapshot),
        "years": years,
        "url_pattern": BRFSS_URL,
    }
    write_json(PROCESSED / "data_mode.json", meta)
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="regenerate synthetic snapshot")
    ap.add_argument("--download", action="store_true",
                    help="(real path) download CDC XPT zips into data/raw/brfss/real/")
    args = ap.parse_args()
    if args.download:
        print("[fetch_brfss] Real download is a manual/heavy step; see SOURCES.md and "
              f"the URL pattern {BRFSS_URL}. Place unzipped XPTs in {REAL_DIR}.")
    fetch(force=args.force)


if __name__ == "__main__":
    main()
