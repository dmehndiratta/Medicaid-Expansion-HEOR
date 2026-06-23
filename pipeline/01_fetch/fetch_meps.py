"""Fetch AHRQ MEPS expenditure/utilisation files (idempotent, dated, cached).

Real path: MEPS Full Year Consolidated files (SAS transport / ASCII) at
  https://meps.ahrq.gov/mepsweb/data_stats/download_data_files.jsp
Place the relevant FYC file(s) in data/raw/meps/real/ and this stage stamps the MEPS
portion as real. MEPS is national (limited state IDs) so it parameterises cost
magnitudes and the budget-impact model, NOT the state DiD (plan §3, §10).

Fallback path: generate a synthetic MEPS-like per-person expenditure table so the
cost side (incremental cost of covering a newly-eligible adult) is computable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import RAW, load_config, today  # noqa: E402
from pipeline import synthetic  # noqa: E402

REAL_DIR = RAW / "meps" / "real"
SYN_DIR = RAW / "meps" / "synthetic"
MEPS_URL = "https://meps.ahrq.gov/mepsweb/data_stats/download_data_files.jsp"


def _real_files() -> list[Path]:
    if not REAL_DIR.exists():
        return []
    return sorted(list(REAL_DIR.glob("*.ssp")) + list(REAL_DIR.glob("*.dat"))
                  + list(REAL_DIR.glob("*.parquet")))


def fetch(force: bool = False) -> dict:
    config = load_config()
    if _real_files():
        print(f"[fetch_meps] real MEPS files present in {REAL_DIR}")
        mode = "real"
    else:
        SYN_DIR.mkdir(parents=True, exist_ok=True)
        out = SYN_DIR / "meps_synthetic.parquet"
        if out.exists() and not force:
            print(f"[fetch_meps] synthetic snapshot fresh: {out} (use --force to regen)")
        else:
            df = synthetic.generate_meps(config)
            df.to_parquet(out, index=False)
            print(f"[fetch_meps] data_mode=synthetic — generated {len(df):,} rows -> {out}")
        mode = "synthetic"
    return {"source": "meps", "data_mode": mode, "vintage": today(), "url": MEPS_URL}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    fetch(force=args.force)


if __name__ == "__main__":
    main()
