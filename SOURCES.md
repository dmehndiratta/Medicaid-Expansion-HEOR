# SOURCES.md — every headline figure → a primary source

All sources verified 2026-06-15. Public; no registration required.

## Primary data

| Source | What | URL | Vintage / access |
|---|---|---|---|
| CDC BRFSS annual files | State-representative health survey (~400k/yr): coverage, "could not see doctor because of cost," general health, income/age. Provides the DiD outcomes and the eligibility proxy; design vars `_STSTR`, `_PSU`, `_LLCPWT`. | https://www.cdc.gov/brfss/annual_data/annual_data.htm | Annual; SAS XPT bulk per year, 2011–2019 core. |
| AHRQ MEPS | Nationally representative panel of health-care use and **expenditures**; the *cost* side of the HEOR model (per-capita spend, OOP, utilisation). National (limited state IDs) → cost magnitudes & budget-impact parameters, not the state DiD. | https://meps.ahrq.gov/ | Annual. |

## Treatment & assumption inputs (committed in `data/manual/`)

| File | What | Source |
|---|---|---|
| `expansion_dates.csv` | Per-state Medicaid expansion adoption year (treatment timing). | KFF "Status of State Medicaid Expansion Decisions" tracker — https://www.kff.org/medicaid/issue-brief/status-of-state-medicaid-expansion-decisions/ |
| `utility_weights.csv` | Health-status → health-utility (QALY weight) crosswalks. **Assumptions, varied in PSA.** | CDC HRQOL→EQ-5D (Jia et al.); US EQ-5D-3L value set (Shaw, Johnson & Coons 2005, *Medical Care*); SF-6D (Brazier, Roberts & Deverill 2002, *J Health Econ*). |

## Interpretation anchors

| Figure | Value | Source |
|---|---|---|
| WTP thresholds (cost-effectiveness) | $50k / $100k / $150k per QALY | Standard US willingness-to-pay anchors (Neumann et al., *NEJM* 2014; ICER reference case). |
| Expansion FPL threshold | ≤138% FPL | ACA Medicaid eligibility expansion statute. |

## Methods references

- Callaway & Sant'Anna (2021), "Difference-in-Differences with Multiple Time Periods,"
  *J. Econometrics* — headline group-time ATT estimator (R `did`).
- Sun & Abraham (2021), *J. Econometrics* — interaction-weighted event study (`fixest::sunab`).
- Goodman-Bacon (2021), *J. Econometrics* — TWFE decomposition (`bacondecomp`).
- de Chaisemartin & D'Haultfœuille (2020), *AER* — TWFE bias under heterogeneity.
- Roodman et al. (2019), *Stata J.* — wild-cluster bootstrap (`fwildclusterboot`/`boottest`).
