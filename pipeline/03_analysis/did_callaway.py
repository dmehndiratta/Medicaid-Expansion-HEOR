"""Headline estimator runner: Callaway-Sant'Anna group-time ATT -> results_csdid.json.

Prefers R (`Rscript did_callaway.R`, the `did` package) when Rscript is on PATH;
otherwise uses the tested pure-Python implementation in _csa.py. Both write the same
schema (plan §11 Q4 fallback). The data_mode is threaded through.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import PROCESSED, load_config, read_json, write_json  # noqa: E402
from pipeline import csa  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = PROCESSED / "results_csdid.json"


def run_python(config: dict) -> dict:
    panel = pd.read_parquet(PROCESSED / "analysis_panel.parquet")
    meta = read_json(PROCESSED / "data_mode.json")
    outcomes = list(config["outcomes"].keys())
    results = {o: csa.estimate(panel, o, config) for o in outcomes}
    return {
        "method": "callaway_santanna",
        "engine": "python (_csa.py)",
        "data_mode": meta["data_mode"],
        "seed": config["seed"],
        "outcome_labels": config["outcomes"],
        "results": results,
    }


def main():
    config = load_config()
    rscript = shutil.which("Rscript")
    if rscript:
        print("[did_callaway] Rscript found — running R `did` headline path")
        r = subprocess.run([rscript, str(HERE / "did_callaway.R")],
                           capture_output=True, text=True)
        print(r.stdout)
        if r.returncode == 0 and OUT.exists():
            print("[did_callaway] R path wrote results_csdid.json")
            return
        print(f"[did_callaway] R path failed (rc={r.returncode}); "
              f"falling back to Python.\n{r.stderr[:500]}")
    else:
        print("[did_callaway] Rscript not on PATH — using Python implementation "
              "(documented fallback, plan §11 Q4)")
    payload = run_python(config)
    write_json(OUT, payload)
    # quick console summary
    for o, res in payload["results"].items():
        att = res["overall_att"]
        pt = res["pre_trend_test"]
        print(f"[did_callaway] {o}: ATT={att['estimate']:+.4f} "
              f"[{att['ci_low']:+.4f},{att['ci_high']:+.4f}] "
              f"pre-trend p={pt.get('p_value')}")


if __name__ == "__main__":
    main()
