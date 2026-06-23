"""One-off: report which harmonisation-relevant columns exist in each raw file.

Reads metadata only (no data rows) so it's fast even on multi-GB XPTs. Lets us catch
year-to-year column drift BEFORE the full concat->decode run, where a missing alias
would silently coerce a whole year's rows to NaN.
"""
import sys
from pathlib import Path

import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.clean_lib import ALIASES  # noqa: E402

BRFSS = ROOT / "data" / "raw" / "brfss" / "real"
MEPS = ROOT / "data" / "raw" / "meps" / "real"


def cols(path: Path) -> list[str]:
    _, meta = pyreadstat.read_xport(str(path), metadataonly=True, encoding="LATIN1")
    return list(meta.column_names)


def main():
    print("=== BRFSS per-file alias resolution ===")
    concepts = ["state", "year", "age", "income2", "incomg",
                "coverage", "medcost", "genhlth", "weight", "strata", "psu"]
    for x in sorted(BRFSS.glob("*.XPT")) + sorted(BRFSS.glob("*.xpt")):
        c = set(cols(x))
        hits = {}
        for concept in concepts:
            found = next((a for a in ALIASES[concept] if a in c), None)
            hits[concept] = found or "** MISSING **"
        print(f"\n{x.name}  ({len(c)} cols)")
        for k, v in hits.items():
            flag = "" if "MISSING" not in v else "   <-- !!"
            print(f"  {k:10s} -> {v}{flag}")

    print("\n=== MEPS columns of interest ===")
    for s in sorted(MEPS.glob("*.ssp")):
        c = cols(s)
        print(f"\n{s.name} ({len(c)} cols)")
        for tok in ("TOTEXP", "TOTSLF", "INSCOV", "UNINS", "PERWT", "AGELAST",
                    "AGE", "POVCAT", "POVLEV"):
            matches = [col for col in c if col.upper().startswith(tok)]
            if matches:
                print(f"  {tok:8s} -> {matches}")


if __name__ == "__main__":
    main()
