"""Callaway-Sant'Anna (2021) group-time ATT — pure-Python implementation.

This is the documented fallback for the headline estimator when Rscript/`did` is not
available (plan §11 Q4). It operates on the collapsed state x year panel of weighted
outcome means (one row per state-year), which is the standard aggregation for DiD with
repeated cross-sections; clustering is on state.

Estimands
  ATT(g,t) = [mean change for cohort g from base period (g-1) to t]
           - [same change for the control group]
  control group = not-yet-treated by max(t, g-1)  [config: notyettreated], optionally
  augmented with never-treated; or never-treated only.

Aggregations
  * event-study ATT(e): population-weighted average of ATT(g, g+e) across cohorts.
  * overall ATT: population-weighted average of post-treatment ATT(g, t>=g).

Inference: WILD-CLUSTER (Rademacher) bootstrap on states. Because every estimand is a
*linear* function of the per-state period-differences, each estimand has an exact
state-level influence vector C_s such that a bootstrap replicate is
    theta*_b = theta_hat + sum_s C_s * eta_{s,b},   eta ~ {-1,+1}.
This is a fast, exact wild-cluster bootstrap with one Rademacher weight per state
(cluster) per replicate -- the correct few-clusters fix. Pre-trends are tested jointly
with a Wald statistic using the bootstrap covariance of the lead coefficients.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class Block:
    """One (g, t) building block: per-state period-differences and group membership."""
    g: int
    t: int
    states: np.ndarray          # state ids
    treated_mask: np.ndarray    # bool, treated cohort g
    control_mask: np.ndarray    # bool, control group
    deltas: np.ndarray          # y[s,t] - y[s,g-1]
    w: np.ndarray               # state population weights (raw)
    att: float = 0.0
    influence: dict = field(default_factory=dict)  # state_id -> dC_s for this block


def _state_weights(panel: pd.DataFrame) -> dict:
    return panel.groupby("state_fips")["wsum"].mean().to_dict()


def _build_blocks(panel: pd.DataFrame, outcome: str, control_group: str) -> list[Block]:
    Y = panel.pivot(index="state_fips", columns="year", values=outcome)
    g_by_state = panel.dropna(subset=["expansion_year_eff"]).set_index("state_fips")[
        "expansion_year_eff"].groupby(level=0).first().to_dict()
    sw = _state_weights(panel)
    years = sorted(panel["year"].unique())
    cohorts = sorted({int(g) for g in g_by_state.values()})
    all_states = list(Y.index)

    def is_control(c, t, base):
        gc = g_by_state.get(c, np.nan)
        if np.isnan(gc):
            return True  # never-treated within window
        if control_group == "nevertreated":
            return False
        return gc > max(t, base)  # not-yet-treated by the later of the two periods

    blocks: list[Block] = []
    for g in cohorts:
        base = g - 1
        if base not in years:
            continue
        treated_states = [s for s, gs in g_by_state.items() if int(gs) == g]
        for t in years:
            if t == base:
                continue
            sids, treated_flags, ctrl_flags, deltas, ws = [], [], [], [], []
            # treated cohort g
            for s in treated_states:
                if t in Y.columns and base in Y.columns and not (
                        np.isnan(Y.loc[s, t]) or np.isnan(Y.loc[s, base])):
                    sids.append(s); treated_flags.append(True); ctrl_flags.append(False)
                    deltas.append(Y.loc[s, t] - Y.loc[s, base]); ws.append(sw[s])
            # controls
            for c in all_states:
                if c in treated_states:
                    continue
                if not is_control(c, t, base):
                    continue
                if not (np.isnan(Y.loc[c, t]) or np.isnan(Y.loc[c, base])):
                    sids.append(c); treated_flags.append(False); ctrl_flags.append(True)
                    deltas.append(Y.loc[c, t] - Y.loc[c, base]); ws.append(sw[c])
            tmask = np.array(treated_flags); cmask = np.array(ctrl_flags)
            if tmask.sum() == 0 or cmask.sum() == 0:
                continue
            blk = Block(g=g, t=t, states=np.array(sids), treated_mask=tmask,
                        control_mask=cmask, deltas=np.array(deltas), w=np.array(ws))
            _finalize_block(blk)
            blocks.append(blk)
    return blocks


def _finalize_block(blk: Block) -> None:
    d, w = blk.deltas, blk.w
    wT = w[blk.treated_mask] / w[blk.treated_mask].sum()
    wC = w[blk.control_mask] / w[blk.control_mask].sum()
    mT = float(np.dot(wT, d[blk.treated_mask]))
    mC = float(np.dot(wC, d[blk.control_mask]))
    blk.att = mT - mC
    # per-state influence: C_s such that att* = att + sum_s C_s * eta_s
    infl = {}
    tre = blk.states[blk.treated_mask]; ctr = blk.states[blk.control_mask]
    for s, wi, di in zip(tre, wT, d[blk.treated_mask]):
        infl[s] = infl.get(s, 0.0) + wi * (di - mT)
    for s, wi, di in zip(ctr, wC, d[blk.control_mask]):
        infl[s] = infl.get(s, 0.0) - wi * (di - mC)
    blk.influence = infl


def _agg(blocks, selector, cohort_pop):
    """Weighted aggregation of selected blocks -> (estimate, influence, n_cohorts)."""
    sel = [b for b in blocks if selector(b)]
    if not sel:
        return None
    weights = np.array([cohort_pop[b.g] for b in sel], dtype=float)
    weights = weights / weights.sum()
    est = float(np.dot(weights, [b.att for b in sel]))
    infl: dict = {}
    for wgt, b in zip(weights, sel):
        for s, c in b.influence.items():
            infl[s] = infl.get(s, 0.0) + wgt * c
    return est, infl, len({b.g for b in sel})


def estimate(panel: pd.DataFrame, outcome: str, config: dict) -> dict:
    control_group = config["estimators"]["control_group"]
    reps = int(config["inference"]["wild_bootstrap_reps"])
    ci_level = float(config["inference"]["ci_level"])
    seed = int(config["seed"])

    blocks = _build_blocks(panel, outcome, control_group)
    if not blocks:
        raise RuntimeError(f"no usable (g,t) blocks for outcome {outcome}")
    cohort_pop = panel.dropna(subset=["expansion_year_eff"]).groupby(
        panel["expansion_year_eff"].astype("Int64"))["wsum"].mean().to_dict()
    cohort_pop = {int(k): float(v) for k, v in cohort_pop.items()}
    states = sorted({s for b in blocks for s in b.states})
    sidx = {s: i for i, s in enumerate(states)}

    es_cfg = config.get("event_study", {})
    win_lo = int(es_cfg.get("window_min", -99))
    win_hi = int(es_cfg.get("window_max", 99))
    min_cohorts = int(es_cfg.get("min_cohorts", 1))

    # --- point estimates -----------------------------------------------------
    # Overall ATT aggregates post-treatment blocks only (t >= g), within the lag window.
    overall = _agg(blocks, lambda b: b.t >= b.g and (b.t - b.g) <= win_hi, cohort_pop)
    event_times = sorted({int(b.t - b.g) for b in blocks})
    ref = int(config["window"]["reference_period"])
    es = {}
    for e in event_times:
        if e == ref or e < win_lo or e > win_hi:
            continue
        r = _agg(blocks, lambda b, e=e: int(b.t - b.g) == e, cohort_pop)
        if r is not None and r[2] >= min_cohorts:   # require adequate cohort support
            es[e] = r

    # --- influence -> state vectors -----------------------------------------
    def vec(infl):
        v = np.zeros(len(states))
        for s, c in infl.items():
            v[sidx[s]] = c
        return v

    overall_est, overall_v = overall[0], vec(overall[1])
    es_est = {e: r[0] for e, r in es.items()}
    es_vec = {e: vec(r[1]) for e, r in es.items()}

    # --- wild-cluster bootstrap ---------------------------------------------
    rng = np.random.default_rng(seed)
    eta = rng.choice([-1.0, 1.0], size=(reps, len(states)))   # Rademacher
    alpha = 1 - ci_level

    def ci(est, v):
        draws = est + eta @ v
        se = float(draws.std(ddof=1))
        lo, hi = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
        # bootstrap p-value (H0: theta=0) via symmetric distribution of (draws-est)
        boot_centered = draws - est
        p = float((np.abs(boot_centered) >= abs(est)).mean())
        return {"estimate": round(est, 5), "se": round(se, 5),
                "ci_low": round(float(lo), 5), "ci_high": round(float(hi), 5),
                "p_value": round(p, 4)}

    overall_ci = ci(overall_est, overall_v)
    es_out = {e: {**ci(es_est[e], es_vec[e]), "event_time": e} for e in es_est}

    # --- pre-trend joint Wald test (leads e < ref) --------------------------
    leads = sorted([e for e in es_est if e < ref])
    pretrend = {"leads_tested": leads}
    if len(leads) >= 1:
        M = np.array([es_est[e] for e in leads])
        L = np.array([es_vec[e] for e in leads])           # len(leads) x n_states
        boot = (L @ eta.T)                                  # len(leads) x reps
        cov = np.cov(boot)
        cov = np.atleast_2d(cov)
        try:
            W = float(M @ np.linalg.pinv(cov) @ M)
            pval = float(1 - stats.chi2.cdf(W, df=len(leads)))
        except Exception:
            W, pval = float("nan"), float("nan")
        pretrend.update({"wald_stat": round(W, 4), "p_value": round(pval, 4),
                         "flat": bool(pval > 0.05),
                         "interpretation": ("pre-trends not rejected (identification "
                                            "assumption supported)" if pval > 0.05 else
                                            "PRE-TRENDS REJECTED, identification suspect")})

    return {
        "outcome": outcome,
        "estimator": "callaway_santanna",
        "control_group": control_group,
        "overall_att": overall_ci,
        "event_study": [es_out[e] for e in sorted(es_out)],
        "pre_trend_test": pretrend,
        "n_states": len(states),
        "n_blocks": len(blocks),
        "bootstrap_reps": reps,
        "ci_level": ci_level,
    }
