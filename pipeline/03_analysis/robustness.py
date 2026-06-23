"""Robustness + refutation suite -> results_robustness.json (plan §4, §9.12).

  * dilution (all adults vs eligible): estimating on all adults should ATTENUATE the
    effect toward zero -- demonstrates why the eligibility proxy matters.
  * alternative control group: not-yet-treated vs never-treated -- ATT should be stable.
  * drop early adopters (2014 cohort): headline should not hinge on one cohort.
  * exclude COVID: the core window already stops at 2019; recorded explicitly.
  * placebo timing: assign FAKE adoption 3 years early and estimate on pre-adoption
    data only -- expect a null ("effect" before anything happened => no effect).

All run on the Callaway-Sant'Anna estimator (pipeline/csa.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import PROCESSED, load_config, read_json, write_json  # noqa: E402
from pipeline import csa  # noqa: E402


def _att(panel, outcome, config):
    r = csa.estimate(panel, outcome, config)
    return r["overall_att"]


def main():
    config = load_config()
    meta = read_json(PROCESSED / "data_mode.json")
    panel = pd.read_parquet(PROCESSED / "analysis_panel.parquet")
    panel_all = pd.read_parquet(PROCESSED / "analysis_panel_all.parquet")
    outcomes = list(config["outcomes"].keys())
    out = {"data_mode": meta["data_mode"], "seed": config["seed"], "checks": {}}

    # 1. dilution: all adults
    out["checks"]["dilution_all_adults"] = {
        "description": "ATT on ALL adults (expect attenuation vs eligible-only headline)",
        "headline_eligible": {o: _att(panel, o, config) for o in outcomes},
        "all_adults": {o: _att(panel_all, o, config) for o in outcomes},
    }

    # 2. alternative control group
    cfg_alt = {**config, "estimators": {**config["estimators"],
               "control_group": "nevertreated"
               if config["estimators"]["control_group"] == "notyettreated"
               else "notyettreated"}}
    out["checks"]["alt_control_group"] = {
        "description": f"control_group flipped to {cfg_alt['estimators']['control_group']} "
                       "(expect stable ATT)",
        "uninsured": _att(panel, "uninsured", cfg_alt),
    }

    # 3. drop early adopters (2014 cohort)
    drop2014 = panel[~(panel["expansion_year_eff"] == 2014)].copy()
    out["checks"]["drop_2014_cohort"] = {
        "description": "drop the 2014 cohort (expect headline robust)",
        "uninsured": _att(drop2014, "uninsured", config),
    }

    # 4. exclude COVID (already excluded by window)
    out["checks"]["exclude_covid"] = {
        "description": "core window ends 2019 by construction; 2020-21 never enters headline",
        "window": [config["window"]["start"], config["window"]["end"]],
    }

    # 5. placebo timing: fake adoption 3 years early, pre-adoption data only
    pl = panel.copy()
    real_g = pl["expansion_year_eff"]
    pl["expansion_year_eff"] = real_g - 3
    # keep only years strictly before the REAL adoption (so any "effect" is spurious)
    pl = pl[(real_g.isna()) | (pl["year"] < real_g)]
    try:
        placebo = _att(pl, "uninsured", config)
        placebo_null = bool(placebo["ci_low"] <= 0 <= placebo["ci_high"])
    except Exception as e:
        placebo, placebo_null = {"error": str(e)}, None
    out["checks"]["placebo_timing"] = {
        "description": "fake adoption 3 years early, pre-adoption data only (expect NULL)",
        "uninsured": placebo,
        "is_null_as_expected": placebo_null,
    }

    write_json(PROCESSED / "results_robustness.json", out)
    d = out["checks"]["dilution_all_adults"]
    print(f"[robustness] uninsured ATT eligible={d['headline_eligible']['uninsured']['estimate']:+.4f} "
          f"all-adults={d['all_adults']['uninsured']['estimate']:+.4f} (expect attenuation)")
    print(f"[robustness] placebo-timing null as expected: "
          f"{out['checks']['placebo_timing']['is_null_as_expected']}")


if __name__ == "__main__":
    main()
