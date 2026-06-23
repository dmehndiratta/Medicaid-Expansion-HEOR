"""Orchestrate the Medicaid-Expansion-HEOR pipeline.

  python run_pipeline.py                 # full: fetch -> clean -> analysis -> export
  python run_pipeline.py --offline       # export-only: rebuild site/data from committed
                                         #   data/processed results (no fetch/R/network)
  python run_pipeline.py --export-only   # alias of --offline
  python run_pipeline.py --stage N       # run a single stage (1 fetch,2 clean,3 analysis,4 export)
  python run_pipeline.py --force         # force-regenerate the synthetic snapshot

Headline DiD runs in R (`did`) when Rscript is on PATH; otherwise the tested Python
implementation runs (pipeline/csa.py). Contrast estimators + wild bootstrap likewise
use R when available, Python otherwise.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PY = sys.executable
A = REPO / "pipeline" / "03_analysis"


def run(script: str, *args: str):
    path = REPO / script
    print(f"\n=== {script} {' '.join(args)} ===")
    r = subprocess.run([PY, str(path), *args], cwd=str(REPO))
    if r.returncode != 0:
        raise SystemExit(f"stage failed: {script} (rc={r.returncode})")


def run_r(script: Path) -> bool:
    rscript = shutil.which("Rscript")
    if not rscript:
        return False
    print(f"\n=== Rscript {script.name} ===")
    r = subprocess.run([rscript, str(script)], cwd=str(REPO))
    return r.returncode == 0


def stage_fetch(force):
    run("pipeline/01_fetch/fetch_brfss.py", *(["--force"] if force else []))
    run("pipeline/01_fetch/fetch_meps.py", *(["--force"] if force else []))


def stage_clean():
    run("pipeline/02_clean/build_brfss_panel.py")
    run("pipeline/02_clean/build_costs.py")


def stage_analysis():
    # Headline (R `did` or Python fallback, handled inside the runner)
    run("pipeline/03_analysis/did_callaway.py")
    # Contrast: prefer R fixest/bacondecomp, else Python
    if not run_r(A / "did_sunab.R"):
        run("pipeline/03_analysis/did_twfe.py")
    # Wild-cluster bootstrap corroboration only exists as an R extra; Python CS already
    # carries its own wild bootstrap, so skip silently when Rscript is absent.
    run_r(A / "inference_boottest.R")
    # HEOR overlay + PSA + refutation
    run("pipeline/03_analysis/heor_icer.py")
    run("pipeline/03_analysis/heor_psa.py")
    run("pipeline/03_analysis/robustness.py")


def stage_export():
    run("pipeline/04_export/export_json.py")
    run("tools/json_guard.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="export-only from committed processed/")
    ap.add_argument("--export-only", action="store_true", help="alias of --offline")
    ap.add_argument("--stage", type=int, choices=[1, 2, 3, 4])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.offline or args.export_only:
        stage_export()
        return
    if args.stage:
        {1: lambda: stage_fetch(args.force), 2: stage_clean,
         3: stage_analysis, 4: stage_export}[args.stage]()
        return
    stage_fetch(args.force)
    stage_clean()
    stage_analysis()
    stage_export()
    print("\n[run_pipeline] complete.")


if __name__ == "__main__":
    main()
