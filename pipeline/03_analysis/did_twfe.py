"""Contrast estimators: naive TWFE, Sun-Abraham (interaction-weighted), and a
Goodman-Bacon decomposition -> results_sunab.json.

These exist to *demonstrate the staggered-adoption bias* that motivates Callaway-
Sant'Anna (plan §4): TWFE is shown only for contrast; Goodman-Bacon shows how much of
the TWFE estimate comes from "forbidden" already-treated-as-control 2x2 comparisons;
Sun-Abraham is the interaction-weighted event study that, like CS, avoids them.

All on the collapsed state x year panel; state-clustered (CR1) SEs for the contrast
estimators (the headline wild-cluster inference lives with CS in csa.py).
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import PROCESSED, load_config, read_json, write_json  # noqa: E402


def _ols_cluster(X, y, w, clusters):
    """Weighted OLS with cluster-robust (CR1) covariance. Returns beta, se."""
    sw = np.sqrt(w)
    Xs, ys = X * sw[:, None], y * sw
    XtX_inv = np.linalg.pinv(Xs.T @ Xs)
    beta = XtX_inv @ (Xs.T @ ys)
    resid = ys - Xs @ beta
    # cluster-robust meat
    meat = np.zeros((X.shape[1], X.shape[1]))
    uniq = np.unique(clusters)
    for c in uniq:
        m = clusters == c
        sc = (Xs[m].T @ resid[m])
        meat += np.outer(sc, sc)
    G = len(uniq)
    k = X.shape[1]
    adj = (G / (G - 1)) * ((len(y) - 1) / (len(y) - k)) if G > 1 else 1.0
    cov = XtX_inv @ meat @ XtX_inv * adj
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    return beta, se


def _fe_dummies(panel):
    states = pd.get_dummies(panel["state_fips"], prefix="s", drop_first=True).astype(float)
    years = pd.get_dummies(panel["year"], prefix="y", drop_first=True).astype(float)
    return states, years


def twfe_static(panel, outcome):
    states, years = _fe_dummies(panel)
    const = np.ones((len(panel), 1))
    post = panel["post"].to_numpy(dtype=float)[:, None]
    X = np.hstack([const, states.to_numpy(), years.to_numpy(), post])
    y = panel[outcome].to_numpy(dtype=float)
    w = panel["wsum"].to_numpy(dtype=float)
    beta, se = _ols_cluster(X, y, w, panel["state_fips"].to_numpy())
    return {"estimate": round(float(beta[-1]), 5), "se": round(float(se[-1]), 5),
            "note": "naive two-way FE; biased under staggered timing + heterogeneity"}


def sunab_event_study(panel, outcome, config):
    """Sun-Abraham interaction-weighted event study.

    OLS of y on state FE, year FE, and cohort x relative-time interactions (ref e=-1),
    estimated with never-treated as the clean control (they carry no interaction terms);
    then aggregate cohort-specific coefficients to event time using cohort population
    shares (the IW weights).
    """
    es_cfg = config.get("event_study", {})
    lo, hi = int(es_cfg.get("window_min", -5)), int(es_cfg.get("window_max", 5))
    ref = int(config["window"]["reference_period"])
    df = panel.copy()
    df["cohort"] = df["expansion_year_eff"]
    treated = df[df["cohort"].notna()].copy()
    cohorts = sorted(treated["cohort"].unique())

    # interaction columns
    inter_cols, inter_meta = [], []
    for g in cohorts:
        for e in range(lo, hi + 1):
            if e == ref:
                continue
            col = ((df["cohort"] == g) & ((df["year"] - g) == e)).astype(float)
            if col.sum() > 0:
                inter_cols.append(col.to_numpy())
                inter_meta.append((g, e))
    states, years = _fe_dummies(df)
    const = np.ones((len(df), 1))
    X = np.hstack([const, states.to_numpy(), years.to_numpy(),
                   np.array(inter_cols).T if inter_cols else np.empty((len(df), 0))])
    y = df[outcome].to_numpy(dtype=float)
    w = df["wsum"].to_numpy(dtype=float)
    beta, se = _ols_cluster(X, y, w, df["state_fips"].to_numpy())
    base = 1 + states.shape[1] + years.shape[1]
    coefs = {meta: (beta[base + i], se[base + i]) for i, meta in enumerate(inter_meta)}

    # cohort population shares (IW weights)
    cohort_pop = treated.groupby("cohort")["wsum"].mean()
    es = {}
    for e in range(lo, hi + 1):
        if e == ref:
            continue
        contrib = [(g, coefs[(g, e)][0]) for g in cohorts if (g, e) in coefs]
        if not contrib:
            continue
        gs = [g for g, _ in contrib]
        wts = np.array([cohort_pop[g] for g in gs]); wts = wts / wts.sum()
        est = float(np.dot(wts, [c for _, c in contrib]))
        # approximate IW SE: weighted quadrature of cohort SEs (independent-ish)
        ses = np.array([coefs[(g, e)][1] for g in gs])
        se_e = float(np.sqrt(np.dot(wts ** 2, ses ** 2)))
        es[e] = {"event_time": e, "estimate": round(est, 5), "se": round(se_e, 5),
                 "ci_low": round(est - 1.96 * se_e, 5), "ci_high": round(est + 1.96 * se_e, 5)}
    return [es[e] for e in sorted(es)]


def goodman_bacon(panel, outcome):
    """Goodman-Bacon (2021) decomposition of the TWFE estimate into 2x2 comparisons
    between timing groups, classified into:
      - treated vs never-treated  (clean)
      - earlier vs later (later not-yet-treated as control)  (clean)
      - later vs earlier (earlier ALREADY-treated as control)  (FORBIDDEN -> bias source)
    Reports the weight share and average DiD of each type. Equal-weight balanced-panel
    version on state-year means (the standard Bacon setting).
    """
    df = panel.copy()
    years = sorted(df["year"].unique())
    T = len(years)
    # group means by (cohort, year); never-treated cohort = inf
    df["cohort"] = df["expansion_year_eff"].fillna(np.inf)
    grp = df.groupby(["cohort", "year"])[outcome].mean().unstack("year")
    sizes = df.groupby("cohort")["state_fips"].nunique()
    n = sizes.sum()
    cohorts = list(grp.index)

    def did_2x2(k, l, pre_years, post_years):
        yk = grp.loc[k]; yl = grp.loc[l]
        dk = yk[post_years].mean() - yk[pre_years].mean()
        dl = yl[post_years].mean() - yl[pre_years].mean()
        return float(dk - dl)

    comps = []
    for k, l in combinations(cohorts, 2):
        tk, tl = (k, l) if k < l else (l, k)   # tk earlier
        # never-treated comparison
        if np.isinf(tl):
            post = [y for y in years if y >= tk]
            pre = [y for y in years if y < tk]
            if not pre or not post:
                continue
            d = did_2x2(tk, tl, pre, post)
            wt = (sizes[tk] / n) * (sizes[tl] / n)
            comps.append(("treated_vs_never", wt, d))
        else:
            # window between the two adoption dates: tk treated, tl not yet -> clean
            mid_pre = [y for y in years if y < tk]
            mid_btw = [y for y in years if tk <= y < tl]
            mid_post = [y for y in years if y >= tl]
            if mid_pre and mid_btw:
                d_early = did_2x2(tk, tl, mid_pre, mid_btw)  # early treated vs later (control)
                wt = (sizes[tk] / n) * (sizes[tl] / n) * (len(mid_btw) / T)
                comps.append(("earlier_vs_later_clean", wt, d_early))
            if mid_btw and mid_post:
                # later treated vs earlier ALREADY-treated control -> forbidden
                d_late = did_2x2(tl, tk, mid_btw, mid_post)
                wt = (sizes[tk] / n) * (sizes[tl] / n) * (len(mid_post) / T)
                comps.append(("later_vs_earlier_FORBIDDEN", wt, d_late))

    if not comps:
        return {}
    cdf = pd.DataFrame(comps, columns=["type", "weight", "did"])
    cdf["weight"] /= cdf["weight"].sum()
    by_type = cdf.groupby("type").apply(
        lambda g: pd.Series({"weight_share": g["weight"].sum(),
                             "avg_did": np.average(g["did"], weights=g["weight"])}),
        include_groups=False)
    twfe_implied = float(np.average(cdf["did"], weights=cdf["weight"]))
    forbidden_share = float(by_type.loc["later_vs_earlier_FORBIDDEN", "weight_share"]
                            if "later_vs_earlier_FORBIDDEN" in by_type.index else 0.0)
    return {
        "by_type": {k: {"weight_share": round(float(v["weight_share"]), 4),
                        "avg_did": round(float(v["avg_did"]), 5)}
                    for k, v in by_type.iterrows()},
        "twfe_implied_weighted_avg": round(twfe_implied, 5),
        "forbidden_comparison_weight": round(forbidden_share, 4),
        "interpretation": (f"{forbidden_share:.0%} of the TWFE estimate's weight comes "
                           "from forbidden already-treated-as-control comparisons; their "
                           "bias is why CS is the headline."),
    }


def main():
    config = load_config()
    panel = pd.read_parquet(PROCESSED / "analysis_panel.parquet")
    meta = read_json(PROCESSED / "data_mode.json")
    outcomes = list(config["outcomes"].keys())
    results = {}
    for o in outcomes:
        results[o] = {
            "twfe_static": twfe_static(panel, o),
            "sunab_event_study": sunab_event_study(panel, o, config),
            "goodman_bacon": goodman_bacon(panel, o),
        }
    payload = {"method": "twfe_sunab_bacon", "data_mode": meta["data_mode"],
               "seed": config["seed"], "outcome_labels": config["outcomes"],
               "results": results}
    write_json(PROCESSED / "results_sunab.json", payload)
    for o in outcomes:
        gb = results[o]["goodman_bacon"]
        print(f"[did_twfe] {o}: TWFE={results[o]['twfe_static']['estimate']:+.4f} "
              f"forbidden-weight={gb.get('forbidden_comparison_weight')}")


if __name__ == "__main__":
    main()
