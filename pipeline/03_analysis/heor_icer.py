"""HEOR overlay: translate the CAUSAL estimates into QALYs, an ICER, and a budget
impact -> results_heor.json.

GOVERNING RULE (CLAUDE.md): the causal effect is reported first; this overlay is a
clearly-labelled model on top of it. The QALY gain is derived from the *causal* change
in self-rated health. If that effect is null, the QALY gain is ~zero and the ICER is
reported as "cost-effectiveness not demonstrated on this outcome" -- never massaged.

Per-adult, per-year base case:
  dQALY  = -ATT(fair/poor health) * (mean utility of non-fair/poor - mean utility of fair/poor)
  dCost  = incremental total medical expenditure of a covered vs uninsured adult (MEPS)
  ICER   = dCost / dQALY
  NMB(λ) = λ*dQALY - dCost           (cost-effective if NMB > 0)
Budget impact = eligible_population * uptake * dCost  (stylised; MEPS is national).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import MANUAL, PROCESSED, load_config, read_json, write_json  # noqa: E402

NON_FAIRPOOR = ["excellent", "very_good", "good"]
FAIRPOOR = ["fair", "poor"]


def utility_delta(weight_set: str) -> float:
    """Mean utility gain from moving out of fair/poor into the non-fair/poor pool."""
    uw = pd.read_csv(MANUAL / "utility_weights.csv", comment="#")
    s = uw[uw["weight_set"] == weight_set].set_index("health_state")["utility"]
    return float(s[NON_FAIRPOOR].mean() - s[FAIRPOOR].mean())


def main():
    config = load_config()
    heor = config["heor"]
    csdid = read_json(PROCESSED / "results_csdid.json")
    costs = read_json(PROCESSED / "cost_params.json")
    meta = read_json(PROCESSED / "data_mode.json")

    health_res = csdid["results"]["fair_poor_health"]
    att_health = health_res["overall_att"]
    pt_health = health_res["pre_trend_test"]
    eff = att_health["estimate"]                     # change in P(fair/poor)
    u_delta = utility_delta(heor["utility_base_case"])
    dqaly = -eff * u_delta                            # >0 if health improved
    dcost = costs["incremental_total_cost_per_adult"]

    # The QALY/ICER overlay may only rest on a CREDIBLY IDENTIFIED health effect:
    # it must be statistically distinguishable from zero AND survive the event-study
    # pre-trend diagnostic (parallel trends). A significant ATT sitting on a rejected
    # pre-trend is not causal evidence (CLAUDE.md governing rule), so no ICER is issued.
    health_significant = not (att_health["ci_low"] <= 0 <= att_health["ci_high"])
    pretrend_ok = bool(pt_health.get("flat", False))
    health_credible = health_significant and pretrend_ok

    if dqaly > 1e-9 and health_credible:
        icer = dcost / dqaly
        icer_status = "estimated"
    else:
        icer = None
        if not health_significant:
            reason = ("self-rated-health effect is statistically indistinguishable from "
                      "zero, so no QALY gain is credibly established")
        elif not pretrend_ok:
            reason = (f"self-rated-health effect fails the parallel-trends diagnostic "
                      f"(event-study pre-trend p={pt_health.get('p_value')}); the ATT is "
                      "not credibly causal, so a cost-per-QALY would overstate the evidence")
        else:
            reason = "no positive QALY gain"
        icer_status = f"not_demonstrated: {reason}; cost-per-QALY on this outcome is not demonstrated"

    thresholds = {}
    for lam in heor["wtp_thresholds"]:
        nmb = lam * dqaly - dcost
        thresholds[str(lam)] = {"nmb": round(nmb, 2),
                                "cost_effective": bool(nmb > 0)}

    bi = config["budget_impact"]
    newly_covered = bi["eligible_population"] * bi["uptake_rate"]
    budget = {
        "eligible_population": bi["eligible_population"],
        "uptake_rate": bi["uptake_rate"],
        "newly_covered": int(newly_covered),
        "total_incremental_cost": round(newly_covered * dcost, 0),
        "total_qaly_gain": round(newly_covered * dqaly, 1),
        "note": "Stylised: per-adult cost is national MEPS magnitude, not state-matched.",
    }

    payload = {
        "data_mode": meta["data_mode"],
        "cost_data_mode": costs.get("cost_data_mode", "unknown"),
        "seed": config["seed"],
        "base_case": {
            "utility_set": heor["utility_base_case"],
            "utility_delta_fairpoor_to_better": round(u_delta, 4),
            "health_att": att_health,
            "health_effect_significant": health_significant,
            "health_pretrend_flat": pretrend_ok,
            "health_effect_credible": health_credible,
            "dqaly_per_adult_year": round(dqaly, 6),
            "dcost_per_adult": round(dcost, 2),
            "icer": (round(icer, 0) if icer is not None else None),
            "icer_status": icer_status,
        },
        "thresholds": thresholds,
        "budget_impact": budget,
        "coverage_findings_note": (
            "The most credible causal result is the coverage effect (ATT on uninsurance), "
            "whose pre-trends are not rejected. The QALY/ICER overlay rests on the "
            "self-rated-health effect, which "
            + ("is statistically significant but FAILS the parallel-trends diagnostic, so it "
               "is not treated as credibly causal here"
               if (health_significant and not pretrend_ok)
               else "is statistically indistinguishable from zero")
            + ", reported honestly rather than converted into a headline ICER."),
    }
    write_json(PROCESSED / "results_heor.json", payload)
    icer_str = f"${icer:,.0f}/QALY" if icer is not None else "NOT DEMONSTRATED"
    print(f"[heor_icer] dQALY/adult/yr={dqaly:.6f}  dCost/adult=${dcost:,.0f}  ICER={icer_str}")


if __name__ == "__main__":
    main()
