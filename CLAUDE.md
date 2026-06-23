# CLAUDE.md — builder instructions & house rules

Project-specific conventions. Shared stack/website rules live in the portfolio
`SETUP.md`. Read this before changing pipeline logic.

## The one rule that governs everything
**Present the causal effect first; the HEOR overlay is a clearly-labelled model on
top of it.** Never let a QALY/ICER headline outrun the causal evidence. A null
self-rated-health effect → no QALY gain → report "cost-effectiveness not demonstrated
on this outcome," not a manufactured ICER.

## Eligibility proxy (the estimand's target population)
- Target: **non-elderly (19–64) low-income (≤138% FPL) adults** — the policy-eligible
  group. Estimating on all adults dilutes the effect.
- BRFSS has no clean continuous FPL. We proxy from the income bracket variable
  (`INCOME2`/`_INCOMG`, harmonised) combined with household size, mapping the bracket
  whose upper bound sits at/below ~138% FPL for a typical low-income household to
  eligible. The proxy is approximate and documented in `tests/test_eligibility.py`;
  robustness runs vary the cut-off (one bracket tighter/looser).

## Estimator choice
- Headline: **Callaway–Sant'Anna** group-time ATT, not-yet-treated controls
  (config-switchable to never-treated). Aggregated to an overall ATT and to
  event-time dynamics.
- **TWFE is shown only to demonstrate staggered-adoption bias** (with a Goodman-Bacon
  decomposition of the comparisons it averages). Sun–Abraham is the interaction-weighted
  corroboration.
- Inference clusters on **state** with a **wild-cluster (Rademacher) bootstrap** — the
  correct few-clusters fix; naive cluster-robust SEs with ~50 clusters understate.

## Utility-weight provenance
- `data/manual/utility_weights.csv` holds three sourced crosswalks (CDC-HRQOL→EQ-5D,
  US EQ-5D-3L value set, SF-6D). Base case = `config.heor.utility_base_case`.
- These are **assumptions, not measurements.** All three sets + their SEs feed the PSA.

## Determinism
- One seed, `config.seed` (20260615), drives the wild bootstrap and the PSA. It is
  recorded into every results JSON. A clean run reproduces identical JSON.

## R vs Python
- Headline CS runs in R (`did`) when `Rscript` is available; otherwise the tested
  Python implementation (`pipeline/03_analysis/_csa.py`) produces the same schema.
  Keep the two in sync: any schema change touches both and `tests/test_json_schema.py`.

## Data honesty
- `data_mode` ∈ {`real`, `synthetic`} is computed once (presence of raw files) and
  threaded into every JSON, the report, and the dashboard banner. Never strip it.
- Raw survey files are gitignored; processed panel + results JSON are committed so CI
  can `--offline --export-only` without network or R.

## JSON guard
- `site/data/*.json` must be browser-parseable: no `NaN`/`Infinity`. `common.write_json`
  enforces this on write; the CI guard re-checks with `json.load(parse_constant=...)`.
