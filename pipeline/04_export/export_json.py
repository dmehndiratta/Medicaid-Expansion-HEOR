"""Assemble site/data/*.json from the committed processed results.

This is the only stage the dashboard depends on. It also computes a descriptive
treated-vs-control trend series for context, stamps meta (data_mode, seed, window,
generated_at), and re-validates every emitted file is browser-parseable.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.common import (PROCESSED, SITE_DATA, load_config, read_json,  # noqa: E402
                             reject_nonfinite, write_json)


def _trends(config):
    panel = pd.read_parquet(PROCESSED / "analysis_panel.parquet")
    panel["group"] = panel["treated_ever"].map({1: "expansion", 0: "non_expansion"})
    rows = []
    for (grp, yr), g in panel.groupby(["group", "year"]):
        row = {"group": grp, "year": int(yr)}
        for o in config["outcomes"]:
            # population-weighted mean across states in the group
            row[o] = round(float((g[o] * g["wsum"]).sum() / g["wsum"].sum()), 5)
        rows.append(row)
    return sorted(rows, key=lambda r: (r["group"], r["year"]))


def main():
    config = load_config()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    csdid = read_json(PROCESSED / "results_csdid.json")
    sunab = read_json(PROCESSED / "results_sunab.json")
    heor = read_json(PROCESSED / "results_heor.json")
    psa = read_json(PROCESSED / "results_psa.json")
    robust = read_json(PROCESSED / "results_robustness.json")
    costs = read_json(PROCESSED / "cost_params.json")
    mode = read_json(PROCESSED / "data_mode.json")

    meta = {
        "project": "Medicaid-Expansion-HEOR",
        "data_mode": mode["data_mode"],
        "seed": config["seed"],
        "window": [config["window"]["start"], config["window"]["end"]],
        "outcomes": config["outcomes"],
        "wtp_thresholds": config["heor"]["wtp_thresholds"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine_causal": csdid.get("engine", "python"),
        "synthetic_warning": (
            "Generated on a calibrated SYNTHETIC panel (no real BRFSS/MEPS present); "
            "figures demonstrate the machinery, not a substantive finding."
            if mode["data_mode"] == "synthetic" else None),
    }

    outputs = {
        "meta.json": meta,
        "did.json": {"csdid": csdid, "contrast": sunab},
        "heor.json": heor,
        "psa.json": psa,
        "robustness.json": robust,
        "cost_params.json": costs,
        "trends.json": {"data_mode": mode["data_mode"], "series": _trends(config)},
    }
    for name, payload in outputs.items():
        write_json(SITE_DATA / name, payload)

    # re-validate browser-parseability (the CI guard does this too)
    import json
    for f in SITE_DATA.glob("*.json"):
        with open(f, encoding="utf-8") as fh:
            json.load(fh, parse_constant=reject_nonfinite)

    # bundle.js: the SAME data assigned to a global, so the dashboard/report also work
    # from file:// (browsers block fetch() of local JSON). JSON files stay the source of
    # truth; this is generated from them.
    from pipeline.common import _clean
    bundle = {k.replace(".json", ""): _clean(v) for k, v in outputs.items()}
    (SITE_DATA / "bundle.js").write_text(
        "window.MEHEOR_DATA = " + json.dumps(bundle, indent=2, sort_keys=True) + ";\n",
        encoding="utf-8")
    print(f"[export_json] wrote + validated {len(outputs)} JSON files + bundle.js to "
          f"{SITE_DATA} (data_mode={mode['data_mode']})")


if __name__ == "__main__":
    main()
