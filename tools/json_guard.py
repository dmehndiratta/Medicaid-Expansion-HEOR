"""Browser-parseable JSON guard (reused by CI, verbatim spirit of the World-Cup check).

Every file the dashboard reads must survive the browser's JSON.parse, which has no
NaN/Infinity. This rejects them by loading each site/data/*.json with a parse_constant
hook that raises. Exit code 1 on any failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SITE_DATA = Path(__file__).resolve().parents[1] / "site" / "data"


def _reject(value):
    raise ValueError(f"non-finite JSON constant: {value!r}")


def main() -> int:
    files = sorted(SITE_DATA.glob("*.json"))
    if not files:
        print(f"[json_guard] no JSON in {SITE_DATA}", file=sys.stderr)
        return 1
    bad = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                json.load(fh, parse_constant=_reject)
            print(f"[json_guard] OK  {f.name}")
        except Exception as e:  # noqa: BLE001
            print(f"[json_guard] FAIL {f.name}: {e}", file=sys.stderr)
            bad += 1
    if bad:
        print(f"[json_guard] {bad} file(s) failed", file=sys.stderr)
        return 1
    print(f"[json_guard] all {len(files)} files browser-parseable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
