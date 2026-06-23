"""BRFSS variable harmonisation: the income variable drifts across years (INCOME2 in
early years, _INCOMG later). decode() must resolve either and derive eligibility the
same way, and must fail loudly when a concept is missing entirely.
"""
import numpy as np
import pandas as pd
import pytest

from pipeline.common import load_config
from pipeline.clean_lib import _resolve, decode


def _base_raw(n=200):
    return pd.DataFrame({
        "_STATE": np.full(n, 6), "IYEAR": np.full(n, 2013),
        "_AGE80": np.full(n, 40), "HLTHPLN1": np.full(n, 2),
        "MEDCOST": np.full(n, 1), "GENHLTH": np.full(n, 4),
        "_STSTR": np.arange(n), "_PSU": np.arange(n), "_LLCPWT": np.full(n, 100.0),
    })


def test_resolves_either_income_era():
    cfg = load_config()
    early = _base_raw(); early["INCOME2"] = 2          # low-income bracket (early coding)
    late = _base_raw();  late["_INCOMG"] = 1            # low-income group (later coding)
    de, dl = decode(early, cfg), decode(late, cfg)
    assert de["eligible"].mean() == 1.0                 # 40yo + low income -> eligible
    assert dl["eligible"].mean() == 1.0


def test_high_income_not_eligible():
    cfg = load_config()
    raw = _base_raw(); raw["INCOME2"] = 8               # high bracket
    assert decode(raw, cfg)["eligible"].mean() == 0.0


def test_age_bound_enforced():
    cfg = load_config()
    raw = _base_raw(); raw["INCOME2"] = 2; raw["_AGE80"] = 70   # elderly
    assert decode(raw, cfg)["eligible"].mean() == 0.0


def test_missing_concept_fails_loudly():
    raw = _base_raw().drop(columns=["GENHLTH", "_RFHLTH"], errors="ignore")
    with pytest.raises(KeyError):
        _resolve(raw, "genhlth")
