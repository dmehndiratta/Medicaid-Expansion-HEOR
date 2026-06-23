"""Calibrated synthetic BRFSS/MEPS generator.

Used only when the real bulk files are absent (see fetch_brfss.py). It produces a
respondent-level panel with *raw, un-harmonised BRFSS-like column names that drift
across years* (so the cleaner's harmonisation step does real work), a known planted
ATT among eligible respondents in treated states, and flat pre-trends. The point is
to (a) make the whole chain runnable and (b) let tests verify the estimators recover
the planted effect. Anything produced here is stamped data_mode="synthetic".

Design choices that keep the recovery clean and the diagnostics meaningful:
  * Outcomes generated in probability space (linear, clipped) so a planted effect in
    percentage points is exactly the ATT the estimators should recover.
  * Pre-treatment effect is exactly zero -> event-study leads are flat by construction.
  * A secular nationwide decline in uninsurance (ACA marketplaces) is added to ALL
    states as a co-treatment, so a naive TWFE that mis-times comparisons is biased and
    the Goodman-Bacon / CS contrast has something to show.
  * Effects hit only eligible (low-income, 19-64) respondents; estimating on all adults
    dilutes them -- which the robustness suite demonstrates.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.common import MANUAL, rng  # noqa: E402

# BRFSS-like income coding. Early years use INCOME2 (8 brackets); later years switched
# to the grouped _INCOMG (5 groups). The cleaner harmonises both to an eligibility flag.
INCOME2_EARLY_YEARS = range(2011, 2015)   # use INCOME2
INCOMG_LATER_YEARS = range(2015, 2030)    # use _INCOMG


def _expansion_dates() -> pd.DataFrame:
    df = pd.read_csv(MANUAL / "expansion_dates.csv", comment="#")
    return df


def _ramp(event_time: np.ndarray, full_at: int) -> np.ndarray:
    """0 before treatment; linear ramp to 1.0 reached `full_at` periods after adoption."""
    out = np.zeros_like(event_time, dtype=float)
    post = event_time >= 0
    out[post] = np.clip((event_time[post] + 1) / (full_at + 1), 0.0, 1.0)
    return out


def generate_brfss(config: dict) -> pd.DataFrame:
    syn = config["synthetic"]
    g = rng(config)
    years = list(range(config["window"]["start"], config["window"]["end"] + 1))
    states = _expansion_dates()
    n_per = int(syn["respondents_per_state_year"])
    planted = syn["planted_att"]

    # State random effects on each outcome's baseline level (log-odds-free; prob space).
    n_states = len(states)
    state_re = {
        "uninsured": g.normal(0, 0.05, n_states),
        "cost_barrier": g.normal(0, 0.04, n_states),
        "fair_poor_health": g.normal(0, 0.05, n_states),
    }
    base = {"uninsured": 0.30, "cost_barrier": 0.20, "fair_poor_health": 0.26}
    # Nationwide secular decline in uninsurance (ACA marketplaces) hitting ALL states.
    def secular(o, yr):
        if o == "uninsured":
            return -0.012 * (yr - years[0])
        if o == "cost_barrier":
            return -0.006 * (yr - years[0])
        return -0.002 * (yr - years[0])

    rows = []
    for si, (_, st) in enumerate(states.reset_index(drop=True).iterrows()):
        exp_year = st["expansion_year"]
        treated_state = pd.notna(exp_year)
        exp_year = int(exp_year) if treated_state else None
        for yr in years:
            n = n_per
            age = g.integers(19, 65, n)                      # non-elderly adults only
            # income bracket, coded in the era-appropriate variable
            if yr in INCOME2_EARLY_YEARS:
                income2 = g.integers(1, 9, n)                # 1..8
                incomg = np.full(n, np.nan)
                eligible = income2 <= 4                       # ~<=25k proxy for <=138% FPL
            else:
                incomg = g.integers(1, 6, n)                  # 1..5
                income2 = np.full(n, np.nan)
                eligible = incomg <= 2                         # <=25k group

            # event time for treated states (only matters post-adoption, eligible only)
            if treated_state:
                e = yr - exp_year
                post = (e >= 0) & eligible
            else:
                e = None
                post = np.zeros(n, dtype=bool)

            out = {}
            for o in ("uninsured", "cost_barrier", "fair_poor_health"):
                p = base[o] + state_re[o][si] + secular(o, yr)
                # eligible respondents sit a bit higher (worse) at baseline
                p = p + 0.04 * eligible.astype(float)
                if treated_state and post.any():
                    full_at = 2 if o == "fair_poor_health" else 1   # health is slower
                    et = np.full(n, e, dtype=float)
                    r = _ramp(et, full_at) * post.astype(float)
                    p = p + planted[o] * r
                p = np.clip(p, 0.01, 0.99)
                out[o] = (g.random(n) < p).astype(int)

            # BRFSS design vars: stratum nested in state, PSU, design weight
            ststr = si * 100 + g.integers(1, 6, n)
            psu = g.integers(1, 50, n)
            llcpwt = np.round(g.lognormal(mean=6.0, sigma=0.5, size=n), 2)

            df = pd.DataFrame(
                {
                    "_STATE": st["state_fips"],
                    "state_abbr": st["state_abbr"],
                    "IYEAR": yr,
                    "_AGE80": age,
                    "INCOME2": income2,
                    "_INCOMG": incomg,
                    # raw-style outcome encodings (cleaner decodes these):
                    "HLTHPLN1": np.where(out["uninsured"] == 1, 2, 1),   # 1=has plan,2=no
                    "MEDCOST": np.where(out["cost_barrier"] == 1, 1, 2),  # 1=yes,2=no
                    "GENHLTH": np.where(out["fair_poor_health"] == 1,
                                        g.integers(4, 6, n),               # 4 fair,5 poor
                                        g.integers(1, 4, n)),              # 1-3 good+
                    "_STSTR": ststr,
                    "_PSU": psu,
                    "_LLCPWT": llcpwt,
                }
            )
            rows.append(df)
    panel = pd.concat(rows, ignore_index=True)
    return panel


def generate_meps(config: dict) -> pd.DataFrame:
    """Synthetic MEPS-like per-person annual expenditure rows.

    Used to parameterise the incremental cost of covering a newly-eligible adult:
    the cost side compares total expenditure (and payer mix) for low-income adults who
    gain Medicaid vs remain uninsured. National-level magnitudes only (plan §10).
    """
    g = rng(config)
    n = 20000
    # uninsured low-income adults: lower total spend, high OOP share, deferred care
    uninsured = g.integers(0, 2, n)
    # total annual medical expenditure (TOTEXP-like), right-skewed
    base_spend = np.where(uninsured == 1, 2600.0, 4200.0)
    totexp = np.round(np.clip(g.lognormal(mean=np.log(base_spend) - 0.5, sigma=1.0), 0, None), 0)
    # out-of-pocket share is much higher for the uninsured
    oop_share = np.where(uninsured == 1, g.beta(6, 4, n), g.beta(2, 8, n))
    return pd.DataFrame(
        {
            "DUPERSID": np.arange(n),
            "uninsured": uninsured,
            "TOTEXP": totexp,
            "OOP_SHARE": np.round(oop_share, 3),
            "low_income": 1,
        }
    )
