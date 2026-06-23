"""The headline estimator must recover the planted ATT on the synthetic panel, and the
pre-trend test must NOT reject (effects are planted only post-adoption).

This is the validation that the whole synthetic->clean->CS chain is wired correctly.
Uses a smaller respondent count for speed.
"""
import copy

import pytest

from pipeline import csa, synthetic
from pipeline.clean_lib import collapse, decode
from pipeline.common import load_config


@pytest.fixture(scope="module")
def panel():
    # Use the configured DGP as-is: recovery and the flat-pre-trend guarantee are
    # properties of the calibrated config, not of an arbitrary smaller sample.
    cfg = copy.deepcopy(load_config())
    raw = synthetic.generate_brfss(cfg)
    resp = decode(raw, cfg)
    return collapse(resp, cfg, "eligible"), cfg


def test_recovers_uninsured_effect(panel):
    p, cfg = panel
    r = csa.estimate(p, "uninsured", cfg)
    planted = cfg["synthetic"]["planted_att"]["uninsured"]   # -0.060
    est = r["overall_att"]["estimate"]
    assert r["overall_att"]["ci_low"] <= planted <= r["overall_att"]["ci_high"], \
        f"planted {planted} not in CI for ATT={est}"
    assert est < -0.03                                       # clearly negative


def test_recovers_cost_barrier_effect(panel):
    p, cfg = panel
    r = csa.estimate(p, "cost_barrier", cfg)
    assert r["overall_att"]["estimate"] < -0.01


def test_pretrends_flat(panel):
    p, cfg = panel
    for o in ("uninsured", "cost_barrier"):
        pt = csa.estimate(p, o, cfg)["pre_trend_test"]
        assert pt["p_value"] > 0.05, f"{o} pre-trend rejected (p={pt['p_value']})"
        assert pt["flat"] is True


def test_wild_bootstrap_widens_ci(panel):
    """Wild-cluster bootstrap SE should be a real, positive number (few-cluster fix)."""
    p, cfg = panel
    r = csa.estimate(p, "uninsured", cfg)
    assert r["overall_att"]["se"] > 0
    assert r["bootstrap_reps"] == cfg["inference"]["wild_bootstrap_reps"]
