"""Importable BRFSS cleaning library (harmonisation, eligibility, collapse).

Lives in the package root (not the numbered stage dir) so it is importable by the stage
script AND by tests. build_brfss_panel.py is a thin orchestrator over these functions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.common import MANUAL

# Concept -> ordered list of known BRFSS column aliases across years.
ALIASES = {
    "state": ["_STATE", "STATE", "_STATEFIPS"],
    "year": ["IYEAR", "_YEAR", "YEAR"],
    "age": ["_AGE80", "AGE", "_AGEG"],
    "income2": ["INCOME2", "INCOME3"],          # 8-bracket coding (earlier years)
    "incomg": ["_INCOMG", "_INCOMG1"],           # grouped coding (later years)
    "coverage": ["HLTHPLN1", "HLTHPLN", "_HLTHPLN", "HLTHPL_"],
    "medcost": ["MEDCOST", "MEDCOST1"],
    "genhlth": ["GENHLTH", "_RFHLTH"],
    "weight": ["_LLCPWT", "_FINALWT", "_LCPWT"],
    "strata": ["_STSTR", "_STRWT"],
    "psu": ["_PSU", "PSU"],
}


def _resolve(df: pd.DataFrame, concept: str) -> str:
    for alias in ALIASES[concept]:
        if alias in df.columns:
            return alias
    raise KeyError(f"BRFSS harmonisation: no column for '{concept}' "
                   f"(tried {ALIASES[concept]}); columns present: {list(df.columns)[:30]}")


def decode(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    c = {k: _resolve(df, k) for k in ["state", "year", "age", "coverage", "medcost",
                                      "genhlth", "weight", "strata", "psu"]}
    out = pd.DataFrame()
    out["state_fips"] = pd.to_numeric(df[c["state"]], errors="coerce").astype("Int64")
    out["year"] = pd.to_numeric(df[c["year"]], errors="coerce").astype("Int64")
    out["age"] = pd.to_numeric(df[c["age"]], errors="coerce")
    out["weight"] = pd.to_numeric(df[c["weight"]], errors="coerce")
    out["strata"] = df[c["strata"]].values
    out["psu"] = df[c["psu"]].values

    # Outcomes (BRFSS codings): coverage 1=has plan,2=no -> uninsured = (==2)
    cov = pd.to_numeric(df[c["coverage"]], errors="coerce")
    out["uninsured"] = (cov == 2).astype(int)
    med = pd.to_numeric(df[c["medcost"]], errors="coerce")
    out["cost_barrier"] = (med == 1).astype(int)
    gen = pd.to_numeric(df[c["genhlth"]], errors="coerce")
    out["fair_poor_health"] = gen.isin([4, 5]).astype(int)

    # Eligibility proxy: 19-64 AND low income (resolve whichever income var is populated)
    elig = config["eligibility"]
    age_ok = out["age"].between(elig["age_min"], elig["age_max"])
    low_income = pd.Series(False, index=df.index)
    if any(a in df.columns for a in ALIASES["income2"]):
        inc2 = pd.to_numeric(df[_resolve(df, "income2")], errors="coerce")
        low_income = low_income | (inc2 <= 4)          # <=~$25k
    if any(a in df.columns for a in ALIASES["incomg"]):
        incg = pd.to_numeric(df[_resolve(df, "incomg")], errors="coerce")
        low_income = low_income | (incg <= 2)          # <=$25k group
    out["eligible"] = (age_ok & low_income).astype(int)
    out["adult"] = age_ok.astype(int)

    out = out.dropna(subset=["state_fips", "year", "weight"])
    out = out[out["weight"] > 0]
    return out


def _weighted_mean(s: pd.Series, w: pd.Series) -> float:
    w = w.to_numpy(dtype=float); s = s.to_numpy(dtype=float)
    tot = w.sum()
    return float(np.dot(s, w) / tot) if tot > 0 else float("nan")


def collapse(resp: pd.DataFrame, config: dict, population: str) -> pd.DataFrame:
    """Collapse respondent rows to a state x year panel of weighted outcome means."""
    mask = resp["eligible"] == 1 if population == "eligible" else resp["adult"] == 1
    sub = resp[mask]
    outcomes = list(config["outcomes"].keys())
    rows = []
    for (st, yr), g in sub.groupby(["state_fips", "year"]):
        row = {"state_fips": int(st), "year": int(yr), "n": int(len(g)),
               "wsum": float(g["weight"].sum())}
        for o in outcomes:
            row[o] = _weighted_mean(g[o], g["weight"])
        rows.append(row)
    panel = pd.DataFrame(rows).sort_values(["state_fips", "year"]).reset_index(drop=True)

    dates = pd.read_csv(MANUAL / "expansion_dates.csv", comment="#")
    panel = panel.merge(dates[["state_fips", "state_abbr", "expansion_year"]],
                        on="state_fips", how="left")
    end = config["window"]["end"]
    panel["expansion_year_eff"] = panel["expansion_year"].where(
        panel["expansion_year"] <= end, other=np.nan)
    panel["treated_ever"] = panel["expansion_year_eff"].notna().astype(int)
    panel["post"] = ((panel["expansion_year_eff"].notna())
                     & (panel["year"] >= panel["expansion_year_eff"])).astype(int)
    panel["event_time"] = np.where(panel["expansion_year_eff"].notna(),
                                   panel["year"] - panel["expansion_year_eff"], np.nan)
    return panel
