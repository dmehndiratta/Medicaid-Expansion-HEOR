"""Build the analysis panel from raw BRFSS (plan §9.5).

Thin orchestrator over pipeline/clean_lib.py (harmonise -> decode -> eligibility ->
collapse). Outputs (committed for --offline):
  data/processed/analysis_panel.parquet      eligible population, weighted state-year means
  data/processed/analysis_panel_all.parquet  all adults (robustness: shows dilution)
  data/interim/brfss_respondent.parquet      decoded respondent level (gitignored)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import INTERIM, PROCESSED, RAW, load_config, read_json  # noqa: E402
from pipeline.clean_lib import ALIASES, collapse, decode  # noqa: E402


def _real_xpts(real_dir: Path) -> list[Path]:
    """Unique XPT paths. Windows globbing is case-insensitive, so *.XPT and *.xpt
    each match every file; dedupe by normalised path or we read each year twice."""
    if not real_dir.exists():
        return []
    seen, out = set(), []
    for p in sorted(list(real_dir.glob("*.XPT")) + list(real_dir.glob("*.xpt"))):
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _load_raw() -> pd.DataFrame:
    """Real XPTs concatenated, else the synthetic parquet.

    Each XPT has ~300-450 columns but we need ~11; read only the alias columns that
    actually exist in that file (per-year coding drifts) so 9 years don't blow up RAM.
    """
    real_dir = RAW / "brfss" / "real"
    xpts = _real_xpts(real_dir)
    if xpts:
        import pyreadstat
        wanted = {a for aliases in ALIASES.values() for a in aliases}
        frames = []
        for x in xpts:
            # BRFSS variable labels carry Windows-1252 bytes (e.g. curly apostrophes);
            # force LATIN1 so readstat doesn't choke decoding them as UTF-8.
            _, meta = pyreadstat.read_xport(str(x), metadataonly=True, encoding="LATIN1")
            usecols = [c for c in meta.column_names if c in wanted]
            d, _ = pyreadstat.read_xport(str(x), encoding="LATIN1", usecols=usecols)
            frames.append(d)
            print(f"[build_brfss_panel] read {x.name}: {len(d):,} rows, {len(usecols)} cols")
        return pd.concat(frames, ignore_index=True)
    syn = RAW / "brfss" / "synthetic" / "brfss_synthetic.parquet"
    if not syn.exists():
        raise FileNotFoundError("No raw BRFSS found. Run pipeline/01_fetch/fetch_brfss.py first.")
    return pd.read_parquet(syn)


def main():
    config = load_config()
    meta = read_json(PROCESSED / "data_mode.json")
    print(f"[build_brfss_panel] data_mode={meta['data_mode']}")
    raw = _load_raw()
    resp = decode(raw, config)
    INTERIM.mkdir(parents=True, exist_ok=True)
    resp.to_parquet(INTERIM / "brfss_respondent.parquet", index=False)

    panel = collapse(resp, config, "eligible")
    panel_all = collapse(resp, config, "all")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(PROCESSED / "analysis_panel.parquet", index=False)
    panel_all.to_parquet(PROCESSED / "analysis_panel_all.parquet", index=False)

    treated = panel[panel["treated_ever"] == 1]
    pre = treated[treated["year"] < 2014]["uninsured"].mean()
    post = treated[treated["year"] >= 2015]["uninsured"].mean()
    print(f"[build_brfss_panel] eligible panel: {len(panel)} state-years, "
          f"{panel['state_fips'].nunique()} states")
    print(f"[build_brfss_panel] sanity — treated-state eligible uninsurance "
          f"pre-2014={pre:.3f} post-2015={post:.3f} (expect a drop)")


if __name__ == "__main__":
    main()
