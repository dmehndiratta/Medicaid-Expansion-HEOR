"""MEPS-based incremental-cost parameters for the HEOR overlay.

Computes, from MEPS-like per-person expenditure rows, the incremental *total* annual
medical expenditure of a newly-covered (Medicaid) low-income adult vs an uninsured one,
plus the out-of-pocket share shift. These parameterise the cost side of the ICER and
the budget-impact model. National magnitudes only (MEPS has limited state IDs) -- the
budget impact is therefore a stylised model, flagged as such (plan §10).

Real MEPS Full Year Consolidated files name their variables with a 2-digit year suffix
(TOTEXP19, TOTSLF19, INSCOV19, POVCAT19, AGELAST). We harmonise those to the canonical
{uninsured, TOTEXP, OOP_SHARE} columns the synthetic generator already emits.

NOTE on the MEPS "SAS transport" (.ssp) download: it is CPORT-compressed, which
readstat/pandas cannot read (only SAS PROC CIMPORT can). If only a .ssp is present we
warn and fall back to the synthetic cost frame, stamping cost_data_mode accordingly so
the overlay is never silently mislabelled. Drop a readable MEPS export (Stata .dta,
.sas7bdat, true .xpt, .csv, or .parquet) into data/raw/meps/real/ for a real cost side.

Output: data/processed/cost_params.json
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import PROCESSED, RAW, load_config, write_json  # noqa: E402
from pipeline import synthetic  # noqa: E402

MEPS_REAL = RAW / "meps" / "real"


def _read_any(path: Path) -> pd.DataFrame:
    """Read a MEPS file in whatever readable format it is. Raises on CPORT .ssp."""
    suf = path.suffix.lower()
    if suf == ".parquet":
        return pd.read_parquet(path)
    if suf == ".csv":
        return pd.read_csv(path)
    if suf == ".dta":
        return pd.read_stata(path, convert_categoricals=False)
    if suf == ".sas7bdat":
        import pyreadstat
        df, _ = pyreadstat.read_sas7bdat(str(path))
        return df
    if suf in (".xpt", ".ssp"):
        # MEPS .ssp is usually CPORT (unreadable); a true XPORT .xpt would parse.
        with open(path, "rb") as fh:
            head = fh.read(120)
        if b"COMPRESSED" in head or b"CPORT" in head:
            raise ValueError(
                f"{path.name} is a CPORT-compressed SAS transport, which cannot be read "
                "without SAS (PROC CIMPORT). Re-download the MEPS file in Stata (.dta), "
                "ASCII (.csv after conversion), or .sas7bdat format.")
        import pyreadstat
        df, _ = pyreadstat.read_xport(str(path), encoding="LATIN1")
        return df
    raise ValueError(f"Unrecognised MEPS file type: {path.name}")


def _harmonise_meps(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw MEPS FYC columns -> canonical {uninsured, TOTEXP, OOP_SHARE}, restricted
    to non-elderly (19-64) low-income adults (the policy-relevant comparison)."""
    cols = {c.upper(): c for c in df.columns}

    def find(prefix: str) -> str | None:
        # exact 'PREFIX' or 'PREFIXyy' (2-digit year suffix)
        pat = re.compile(rf"^{prefix}(\d{{2}})?$")
        for up, orig in cols.items():
            if pat.match(up):
                return orig
        return None

    c_totexp = find("TOTEXP")
    c_totslf = find("TOTSLF")          # self/family out-of-pocket
    c_inscov = find("INSCOV")          # 1=any private, 2=public only, 3=uninsured (full yr)
    c_age = cols.get("AGELAST") or find("AGE")
    c_pov = find("POVCAT")             # 1=poor ... 5=high income
    if not (c_totexp and c_inscov):
        raise KeyError(f"MEPS harmonise: need TOTEXP* and INSCOV*; have {list(df.columns)[:40]}")

    out = pd.DataFrame()
    out["TOTEXP"] = pd.to_numeric(df[c_totexp], errors="coerce")
    inscov = pd.to_numeric(df[c_inscov], errors="coerce")
    out["uninsured"] = (inscov == 3).astype(int)
    if c_totslf:
        slf = pd.to_numeric(df[c_totslf], errors="coerce")
        out["OOP_SHARE"] = np.where(out["TOTEXP"] > 0, slf / out["TOTEXP"], np.nan)
    else:
        out["OOP_SHARE"] = np.nan

    mask = pd.Series(True, index=df.index)
    if c_age:
        age = pd.to_numeric(df[c_age], errors="coerce")
        mask &= age.between(19, 64)
    if c_pov:
        pov = pd.to_numeric(df[c_pov], errors="coerce")
        mask &= pov.isin([1, 2, 3])           # poor / near-poor / low-income
    out = out[mask.values]
    out = out.dropna(subset=["TOTEXP"])
    out = out[out["TOTEXP"] >= 0]
    return out


def _load_meps() -> tuple[pd.DataFrame, str]:
    """(frame, cost_data_mode). Prefer a readable real MEPS file; else synthetic."""
    config = load_config()
    if MEPS_REAL.exists():
        readable_first = sorted(
            [p for p in MEPS_REAL.iterdir()
             if p.suffix.lower() in (".parquet", ".csv", ".dta", ".sas7bdat", ".xpt")],
            key=lambda p: p.suffix.lower())
        ssp = sorted(MEPS_REAL.glob("*.ssp"))
        for p in readable_first:
            try:
                raw = _read_any(p)
                df = _harmonise_meps(raw) if "TOTEXP" not in raw.columns else raw
                print(f"[build_costs] real MEPS: {p.name} -> {len(df):,} low-income adults")
                return df, "real"
            except Exception as e:  # noqa: BLE001 — try the next candidate, then fall back
                print(f"[build_costs] could not use {p.name}: {e}")
        if ssp:
            print(f"[build_costs] WARNING: only a CPORT .ssp present ({ssp[0].name}); it is "
                  "not machine-readable here. Falling back to synthetic cost magnitudes. "
                  "Re-download MEPS as Stata (.dta) or .sas7bdat for a real cost side.")
            return synthetic.generate_meps(config), "synthetic_meps_cport_unreadable"
    # No real files at all.
    syn = RAW / "meps" / "synthetic" / "meps_synthetic.parquet"
    if syn.exists():
        return pd.read_parquet(syn), "synthetic"
    return synthetic.generate_meps(config), "synthetic"


def main():
    config = load_config()
    df, cost_mode = _load_meps()
    covered = df[df["uninsured"] == 0]
    uninsured = df[df["uninsured"] == 1]

    mean_cov = float(covered["TOTEXP"].mean())
    mean_unins = float(uninsured["TOTEXP"].mean())
    incremental_total = mean_cov - mean_unins   # extra medical spend induced by coverage

    # SE of the difference in means (used to draw the cost in the PSA)
    se = float(np.sqrt(covered["TOTEXP"].var(ddof=1) / len(covered)
                       + uninsured["TOTEXP"].var(ddof=1) / len(uninsured)))

    oop_cov = covered["OOP_SHARE"].mean()
    oop_unins = uninsured["OOP_SHARE"].mean()
    payer_oop_shift = float(oop_unins - oop_cov) if pd.notna(oop_cov) and pd.notna(oop_unins) else 0.0

    params = {
        "cost_data_mode": cost_mode,
        "mean_total_exp_covered": round(mean_cov, 2),
        "mean_total_exp_uninsured": round(mean_unins, 2),
        "incremental_total_cost_per_adult": round(incremental_total, 2),
        "incremental_cost_se": round(se, 2),
        "oop_share_reduction": round(payer_oop_shift, 4),
        "n_covered": int(len(covered)),
        "n_uninsured": int(len(uninsured)),
        "note": ("Incremental TOTAL medical expenditure of a covered vs uninsured "
                 "low-income adult; national MEPS magnitudes, stylised budget-impact input."),
    }
    write_json(PROCESSED / "cost_params.json", params)
    print(f"[build_costs] cost_data_mode={cost_mode}  incremental cost/adult=${incremental_total:,.0f} "
          f"(SE ${se:,.0f}); OOP share reduction={payer_oop_shift:.3f}")


if __name__ == "__main__":
    main()
