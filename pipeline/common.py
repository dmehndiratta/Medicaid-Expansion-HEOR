"""Shared helpers for the Medicaid-Expansion-HEOR pipeline.

Single place for: repo paths, config loading, deterministic RNG, and the
browser-parseable JSON writer (the CI guard rejects NaN/Infinity, so we never
emit them). Importable from every stage regardless of CWD.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import yaml

# ---- paths -----------------------------------------------------------------
REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
MANUAL = DATA / "manual"
SITE_DATA = REPO / "site" / "data"
CONFIG_PATH = REPO / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rng(config: dict | None = None) -> np.random.Generator:
    """Seeded NumPy Generator. The single deterministic RNG for the project."""
    cfg = config or load_config()
    return np.random.default_rng(int(cfg["seed"]))


def today() -> str:
    return date.today().isoformat()


# ---- JSON I/O (browser-parseable guarantee) --------------------------------
def _clean(obj: Any) -> Any:
    """Recursively convert numpy types and reject non-finite floats.

    The dashboard parses these files with the browser's JSON.parse, which has no
    NaN/Infinity. Failing loudly here is better than shipping a file the CI guard
    (or the browser) will reject silently.
    """
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        obj = float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("non-finite float would break browser JSON.parse")
        return obj
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    return obj


def write_json(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = _clean(payload)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, indent=2, sort_keys=True)
    tmp.replace(path)
    return path


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def reject_nonfinite(value, _seen=None):
    """parse_constant callback for json.load — used verbatim by the CI guard."""
    raise ValueError(f"non-finite constant in JSON: {value!r}")
