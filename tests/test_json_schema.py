"""The site/data/*.json the dashboard reads must exist, carry the expected keys, and be
browser-parseable (no NaN/Infinity). Mirrors the CI guard.
"""
import json

import pytest

from pipeline.common import SITE_DATA, reject_nonfinite

REQUIRED = {
    "meta.json": ["data_mode", "seed", "window", "outcomes", "wtp_thresholds"],
    "did.json": ["csdid", "contrast"],
    "heor.json": ["base_case", "thresholds", "budget_impact"],
    "psa.json": ["icer_summary", "ceac", "ce_plane", "budget_impact_grid"],
    "robustness.json": ["checks"],
    "trends.json": ["series"],
}


@pytest.mark.parametrize("fname,keys", REQUIRED.items())
def test_required_keys_present(fname, keys):
    path = SITE_DATA / fname
    if not path.exists():
        pytest.skip(f"{fname} not built yet (run run_pipeline.py)")
    data = json.load(open(path, encoding="utf-8"))
    for k in keys:
        assert k in data, f"{fname} missing key '{k}'"


@pytest.mark.parametrize("fname", REQUIRED.keys())
def test_browser_parseable(fname):
    path = SITE_DATA / fname
    if not path.exists():
        pytest.skip(f"{fname} not built yet")
    with open(path, encoding="utf-8") as fh:
        json.load(fh, parse_constant=reject_nonfinite)   # raises on NaN/Infinity


def test_did_event_study_shape():
    path = SITE_DATA / "did.json"
    if not path.exists():
        pytest.skip("did.json not built yet")
    did = json.load(open(path, encoding="utf-8"))
    u = did["csdid"]["results"]["uninsured"]
    assert "overall_att" in u and "event_study" in u and "pre_trend_test" in u
    es0 = u["event_study"][0]
    for k in ("event_time", "estimate", "ci_low", "ci_high"):
        assert k in es0
