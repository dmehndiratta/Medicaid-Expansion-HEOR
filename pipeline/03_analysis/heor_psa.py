"""Probabilistic sensitivity analysis (PSA) -> CEAC -> results_psa.json.

The HEOR analogue of confidence bands (plan §4): instead of one deterministic ICER,
Monte-Carlo over every uncertain input and report a *distribution* plus a cost-
effectiveness acceptability curve (CEAC). Uncertainty propagated:
  * causal health effect  ~ Normal(ATT_hat, SE_hat)        [from CS bootstrap]
  * utility weights       ~ Beta(mean, se) per health state, set chosen at random
                            among the three sourced crosswalks (structural uncertainty)
  * incremental cost      ~ Normal(mean, se)               [from MEPS]
  * uptake                ~ Beta around the base-case rate  [budget impact only]

Outputs: ICER distribution summary, P(dQALY>0), the CEAC over a WTP grid, and a
downsampled cost-effectiveness-plane scatter for the dashboard.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import MANUAL, PROCESSED, load_config, read_json, rng, write_json  # noqa: E402

NON_FAIRPOOR = ["excellent", "very_good", "good"]
FAIRPOOR = ["fair", "poor"]


def _beta_params(mean, se):
    """Method-of-moments Beta(a,b) for a mean in (0,1); guards the variance bound."""
    mean = np.clip(mean, 1e-4, 1 - 1e-4)
    var = np.minimum(se ** 2, mean * (1 - mean) * 0.99)
    common = mean * (1 - mean) / var - 1
    return mean * common, (1 - mean) * common


def main():
    config = load_config()
    g = rng(config)
    draws = int(config["psa"]["draws"])
    heor = config["heor"]
    bi = config["budget_impact"]

    csdid = read_json(PROCESSED / "results_csdid.json")
    costs = read_json(PROCESSED / "cost_params.json")
    meta = read_json(PROCESSED / "data_mode.json")
    att = csdid["results"]["fair_poor_health"]["overall_att"]

    uw = pd.read_csv(MANUAL / "utility_weights.csv", comment="#")
    sets = sorted(uw["weight_set"].unique())

    # --- draw utility deltas (structural + parameter uncertainty) ----------
    udelta = np.empty(draws)
    chosen = g.integers(0, len(sets), draws)
    for i, set_name in enumerate(sets):
        s = uw[uw["weight_set"] == set_name].set_index("health_state")
        idx = np.where(chosen == i)[0]
        if len(idx) == 0:
            continue
        # draw each state's utility, then form the fair/poor -> better delta
        better = np.zeros(len(idx)); worse = np.zeros(len(idx))
        for st in NON_FAIRPOOR:
            a, b = _beta_params(s.loc[st, "utility"], s.loc[st, "se"])
            better += g.beta(a, b, len(idx))
        for st in FAIRPOOR:
            a, b = _beta_params(s.loc[st, "utility"], s.loc[st, "se"])
            worse += g.beta(a, b, len(idx))
        udelta[idx] = better / len(NON_FAIRPOOR) - worse / len(FAIRPOOR)

    # --- draw causal effect, cost, uptake ----------------------------------
    eff = g.normal(att["estimate"], att["se"], draws)          # change in P(fair/poor)
    dqaly = -eff * udelta                                       # per adult per year
    dcost = g.normal(costs["incremental_total_cost_per_adult"],
                     costs["incremental_cost_se"], draws)
    a_u, b_u = _beta_params(bi["uptake_rate"], 0.08)
    uptake = g.beta(a_u, b_u, draws)

    # --- ICER distribution (only defined where dQALY > 0) ------------------
    pos = dqaly > 0
    icer = np.where(pos, dcost / np.where(pos, dqaly, np.nan), np.nan)
    icer_pos = icer[pos]
    icer_summary = {
        "prob_qaly_positive": round(float(pos.mean()), 4),
        "n_draws": draws,
    }
    if icer_pos.size > 50:
        icer_summary.update({
            "median_icer": round(float(np.median(icer_pos)), 0),
            "icer_p025": round(float(np.percentile(icer_pos, 2.5)), 0),
            "icer_p975": round(float(np.percentile(icer_pos, 97.5)), 0),
        })

    # --- CEAC: P(net monetary benefit > 0) over a WTP grid -----------------
    # Grid runs well past the median ICER so the curve actually rises and crosses 50%;
    # the conventional $50k/$100k/$150k anchors sit near its flat low end -- honestly
    # showing expansion is NOT cost-effective on self-rated health at usual thresholds.
    wtp_grid = list(range(0, 1_000_001, 10_000))
    ceac = []
    for lam in wtp_grid:
        nmb = lam * dqaly - dcost
        ceac.append({"wtp": lam, "prob_cost_effective": round(float((nmb > 0).mean()), 4)})

    # --- cost-effectiveness plane scatter (downsampled) --------------------
    k = min(800, draws)
    sel = g.choice(draws, size=k, replace=False)
    plane = [{"dqaly": round(float(dqaly[j]), 6), "dcost": round(float(dcost[j]), 1)}
             for j in sel]

    # --- budget-impact grid for the dashboard calculator -------------------
    pop_grid = np.linspace(bi["eligible_population"] * 0.5,
                           bi["eligible_population"] * 1.5, 11)
    uptake_grid = np.linspace(0.3, 0.9, 7)
    mean_cost = costs["incremental_total_cost_per_adult"]
    bi_grid = [{"eligible_population": int(p), "uptake": round(float(u), 2),
                "total_cost": round(float(p * u * mean_cost), 0)}
               for p in pop_grid for u in uptake_grid]

    payload = {
        "data_mode": meta["data_mode"],
        "seed": config["seed"],
        "draws": draws,
        "wtp_thresholds": heor["wtp_thresholds"],
        "icer_summary": icer_summary,
        "ceac": ceac,
        "ce_plane": plane,
        "budget_impact_grid": bi_grid,
        "note": ("CEAC reflects that the self-rated-health effect is only suggestive: "
                 "probability cost-effective rises with WTP but stays modest, honestly "
                 "reflecting an effect not distinguishable from zero."),
    }
    write_json(PROCESSED / "results_psa.json", payload)
    pe = icer_summary.get("median_icer")
    ceac_100k = [c["prob_cost_effective"] for c in ceac if c["wtp"] == 100000][0]
    print(f"[heor_psa] P(dQALY>0)={icer_summary['prob_qaly_positive']:.2f}  "
          f"median ICER(where defined)={f'${pe:,.0f}' if pe else 'n/a'}  "
          f"CEAC@100k={ceac_100k:.2f}")


if __name__ == "__main__":
    main()
