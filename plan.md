# plan-health-policy-heor.md

> Execution plan for Claude Code. Self-contained. See SETUP.md for the shared
> website mechanism and house conventions.
>
> **Repo:** `dmehndiratta/Medicaid-Expansion-HEOR` (new, public, independent)
> **Local path:** `D:\Python Projects\Medicaid-Expansion-HEOR`
> **Site slug:** `medicaid-expansion-heor` → `Website/public/medicaid-expansion-heor/`,
> page `/research/medicaid-expansion-heor`. **Completed** analysis (no cron).

---

## 1. Thesis

**Question:** Did the ACA Medicaid expansions (staggered state adoption from 2014)
causally reduce cost-related barriers to care and improve self-reported health among
low-income adults — and, translated into HEOR terms, what is the implied incremental
cost-effectiveness (cost per QALY) and budget impact of expansion?

**Hypothesis:** Using a staggered difference-in-differences design on BRFSS (with
MEPS for cost/utilisation), expansion caused a statistically and economically
meaningful drop in "could not see a doctor because of cost" and uninsurance among
low-income adults, with a smaller, slower improvement in self-rated health; the
HEOR overlay yields an ICER in a range that is plausibly cost-effective by
conventional US thresholds under transparent assumptions.

**What would falsify it:** If event-study pre-trends are non-flat (treated and
control states were already diverging before adoption), the DiD identification fails
and the causal claim is unsupported. If, under modern staggered-adoption-robust
estimators (Callaway–Sant'Anna), the coverage/cost-barrier effects shrink to
indistinguishable from zero or flip sign, the hypothesis is falsified. If the
self-rated-health effect is null (a very possible, honest result), the HEOR QALY
calc must say so and report the cost-effectiveness as "uncertain / not demonstrated
on this outcome," not manufacture a favourable ICER.

---

## 2. Why it is in the portfolio

**Audience:** economic-consulting and HEOR/market-access teams (the kind that build
cost-effectiveness and budget-impact models for payers, pharma, and governments).

**Skill demonstrated:** a clean natural-experiment causal design (staggered DiD with
the current best-practice estimators and event-study diagnostics) *translated into
the language a health-economics consultancy actually speaks*: **ICER, QALY, budget
impact, willingness-to-pay thresholds**, with explicit, sourced utility weights and
sensitivity analysis. It bridges academic causal inference and applied HEOR — exactly
the hybrid skill the consulting audience values.

---

## 3. Data

### Primary — CDC BRFSS (Behavioral Risk Factor Surveillance System)
- **What:** large annual US state-representative health survey (~400k respondents/yr);
  state-identified; includes insurance coverage, "could not see doctor because of
  cost," general health status, and demographics/income for subgroup targeting.
  **Public, no registration.** Confirmed widely used for exactly this DiD design
  (verified 2026-06-15). Access: CDC BRFSS annual files (SAS/ASCII/CSV) at
  `https://www.cdc.gov/brfss/annual_data/annual_data.htm`.
- **Years:** 2011–2019 core window (pre/post 2014), optionally through 2021 with
  COVID caveats. Use the survey design variables (`_STSTR`, `_PSU`, `_LLCPWT`) and
  the provided weights for representative estimates.

### Secondary — AHRQ MEPS (Medical Expenditure Panel Survey)
- **What:** nationally representative panel of health-care use, **expenditures**, and
  insurance; the source for the *cost* side of the HEOR model (per-capita spending,
  out-of-pocket, utilisation). **Public**, `https://meps.ahrq.gov/`. Note MEPS is
  national (limited state identifiers in public files) — used for cost magnitudes and
  the budget-impact parameterisation, not the state DiD.

### Supporting / labels
- **KFF Medicaid expansion adoption dates** by state (the treatment timing) — encode
  into committed `data/manual/expansion_dates.csv` with source URLs (e.g., KFF
  expansion tracker). This is the treatment calendar.
- **Utility weights for QALYs:** published mappings from self-rated health / health
  status to health utilities (e.g., EQ-5D / SF-6D crosswalks; CDC HRQOL). Encode the
  chosen weights with citations in `data/manual/utility_weights.csv`. These are
  assumptions, sourced and varied in sensitivity analysis — not primary measurement.
- **Cost-effectiveness thresholds:** standard US WTP anchors ($50k, $100k, $150k per
  QALY) for interpretation.

### Access, cadence, size
- BRFSS annual release (~yearly); MEPS annual; both downloadable bulk files (BRFSS
  per-year ~tens–hundreds of MB; MEPS similar). KFF dates static.

### Gotchas to guard against
1. **Staggered-adoption bias:** classic two-way fixed-effects DiD is biased with
   staggered timing and heterogeneous effects (Goodman-Bacon; de Chaisemartin–
   D'Haultfœuille). Use **Callaway–Sant'Anna** (`csdid`/`did`) and/or Sun–Abraham as
   the headline; show the naive TWFE only for contrast.
2. **Survey design:** BRFSS needs design-based SEs (weights, strata, PSU). Ignoring
   the complex design understates SEs and mis-weights. Use survey-aware estimation;
   cluster by state for DiD inference (few clusters → wild-cluster bootstrap).
3. **Treatment definition:** target the **policy-eligible** population (low-income
   adults, ~<138% FPL, non-elderly) — effects are diluted if estimated on all adults.
   Define eligibility from BRFSS income/age variables; document the proxy.
4. **Few treated clusters / inference:** ~50 states; DiD inference with state
   clustering and few clusters needs wild-cluster bootstrap, not naive cluster-robust.
5. **QALY translation is the soft spot:** self-rated health → utility is an
   assumption. Be transparent: present the *causal* effect first (the credible part),
   then the HEOR overlay clearly labelled as model-based with full sensitivity. Do
   not let the QALY headline outrun the evidence.
6. **COVID (2020–21):** breaks comparability and BRFSS mode/coverage; keep the core
   window 2011–2019 and treat later years as a clearly-flagged extension.
7. **Concurrent policies:** ACA marketplaces, woodwork effects, and state-specific
   changes co-occur; the estimand is the *expansion* effect identified off timing
   differences — acknowledge co-treatments.

---

## 4. Method

**Estimand:** the average treatment effect on the treated (ATT) of a state adopting
Medicaid expansion, on (i) uninsurance, (ii) "could not see doctor due to cost,"
(iii) self-rated fair/poor health, among low-income non-elderly adults; reported as
dynamic event-study coefficients (leads/lags) and an aggregate ATT.

**Estimators:**
1. **Headline — Callaway–Sant'Anna** group-time ATT with never-treated (and
   not-yet-treated) controls; aggregate to overall and event-time ATTs.
2. **Corroboration — Sun–Abraham** interaction-weighted event study; **TWFE** shown
   only to illustrate the bias direction (with Goodman-Bacon decomposition).
3. **HEOR overlay (built on the causal estimates):** map the causal change in health
   status to **QALYs** via the sourced utility weights; combine with **MEPS-based
   incremental cost** per newly covered adult to compute an **ICER** (Δcost/ΔQALY);
   build a simple **budget-impact** model (population eligible × uptake × net cost);
   present cost-effectiveness vs $50k/$100k/$150k thresholds.

**Validation, robustness, refutation — "done right":**
- **Parallel-trends evidence:** event-study leads must be flat and near zero;
  formally test pre-trends; show the plot prominently. This is the make-or-break
  diagnostic.
- **Honest DiD inference:** state-clustered SEs with **wild-cluster bootstrap**;
  report CIs, not just stars.
- **Robustness:** alternative eligibility cut-offs; dropping early/late adopters;
  excluding 2020–21; alternative control groups (never- vs not-yet-treated);
  placebo outcomes (an outcome expansion shouldn't affect, e.g., a measure unrelated
  to access) → expect null; **placebo timing** (fake adoption 3 years early) → expect
  null.
- **HEOR sensitivity (mandatory uncertainty):** one-way and **probabilistic
  sensitivity analysis (PSA)** — Monte Carlo over the utility weights, the causal
  effect's sampling distribution, cost parameters, and uptake → an ICER distribution
  and a **cost-effectiveness acceptability curve (CEAC)**, not a single ICER. This is
  the HEOR analogue of confidence bands and is required by the quality bar.
- **Refutation:** Goodman-Bacon decomposition to show TWFE bias; negative-control
  outcome; pre-period placebo.

**What "not credible" looks like:** TWFE-only with staggered timing; non-flat
pre-trends waved away; naive SEs with 50 clusters; a single deterministic ICER with
no PSA; QALY gains asserted from a null health effect; eligibility ignored (all-adult
dilution).

---

## 5. Architecture

```
Medicaid-Expansion-HEOR/
├── README.md
├── CLAUDE.md
├── plan.md
├── requirements.txt              # Python + R (see env)
├── renv.lock / DESCRIPTION        # R deps pinned (did, fixest, boottest)
├── run_pipeline.py               # orchestrates Python + Rscript stages
├── sync_to_website.py
├── .gitignore
├── SOURCES.md                    # BRFSS, MEPS, KFF dates, utility-weight citations
├── config.yaml                   # window, eligibility def, thresholds, seed, PSA draws
├── data/
│   ├── manual/expansion_dates.csv       # treatment timing + source URLs (committed)
│   ├── manual/utility_weights.csv       # health-status→utility map + citations (committed)
│   ├── raw/brfss/<YYYY-MM-DD>/           # annual files (gitignored)
│   ├── raw/meps/<YYYY-MM-DD>/
│   ├── interim/
│   └── processed/                        # analysis panel + results (small ones committed)
├── pipeline/
│   ├── 01_fetch/fetch_brfss.py           # annual files; cache; print vintage
│   ├── 01_fetch/fetch_meps.py            # expenditure/utilisation files
│   ├── 02_clean/build_brfss_panel.py     # harmonise vars across years; eligibility; weights
│   ├── 02_clean/build_costs.py           # MEPS per-capita incremental cost params
│   ├── 03_analysis/did_callaway.R        # did:: group-time ATT + event study → results_csdid.json
│   ├── 03_analysis/did_sunab.R           # fixest::sunab; TWFE + Goodman-Bacon → results_sunab.json
│   ├── 03_analysis/inference_boottest.R  # wild-cluster bootstrap SEs
│   ├── 03_analysis/heor_icer.py          # QALYs, ICER, budget impact → results_heor.json
│   ├── 03_analysis/heor_psa.py           # Monte Carlo PSA → CEAC → results_psa.json
│   └── 04_export/export_json.py
├── site/{report.html,dashboard.html,data/*.json}
├── tests/                        # var-harmonisation, weight handling, JSON schema
└── .github/workflows/medicaid-heor-update.yml
```

- **Environment:** **Python 3.11** for data/HEOR + **R 4.4.x** for the causal
  estimators (the `did` package (Callaway–Sant'Anna), `fixest` (sunab, Goodman-Bacon
  via `bacondecomp`), `fwildclusterboot`/`boottest`). Pin Python:
  `pandas==2.2.*`, `numpy==1.26.*`, `pyreadstat==1.2.*` (read BRFSS/MEPS SAS),
  `pyarrow`, `scipy==1.13.*`, `matplotlib`, `pyyaml`. Pin R via `renv.lock`. CI uses
  `actions/setup-python@v5` + `r-lib/actions/setup-r@v2`.
- **Seeds:** `SEED=20260615` for bootstrap + PSA; recorded in JSON.
- **Why mixed Python+R:** the staggered-DiD frontier lives in R (`did`); doing it
  right matters more than language purity. Python orchestrates and does HEOR/PSA.
- Reuse SETUP.md §7 conventions; raw survey files gitignored; processed panel +
  results committed for `--offline` CI export.

---

## 6. Deliverables

- **Repo** as above; `python run_pipeline.py` runs fetch→clean→(Rscript DiD)→HEOR→
  export; `--offline` rebuilds JSON from committed processed artefacts.
- **Report** `site/report.html`: policy background → identification (staggered DiD,
  why CS over TWFE) → data & eligibility → **event-study pre-trend plot** → ATT
  results → **HEOR section** (QALY mapping, ICER, budget impact, CEAC) → robustness
  & refutation → limitations. HEOR clearly delineated from the causal estimates.
- **Interactive dashboard** `site/dashboard.html` (static; Plotly/D3 from CDN; JSON):
  (a) event-study coefficient plot with CIs (toggle outcome); (b) ATT-by-estimator
  comparison (CS / Sun–Abraham / TWFE); (c) **CEAC explorer** — slider for WTP
  threshold shows probability cost-effective; (d) **budget-impact calculator** —
  sliders for eligible population, uptake, per-capita cost recompute total impact
  from pre-computed grids. No backend.
- **Figures/tables:** event-study plots, ATT table with wild-bootstrap CIs,
  Goodman-Bacon decomposition, ICER plane / CEAC, budget-impact table.
- **Project CLAUDE.md:** eligibility definition, estimator choice rationale, utility-
  weight provenance, "present causal effect before HEOR overlay," seed.

---

## 7. Website integration (Pattern A; see SETUP.md §3–§8)

**Secret in this repo:** `WEBSITE_REPO_TOKEN` (required). No data-source key needed
(BRFSS/MEPS/KFF are public downloads).

**Workflow:** `.github/workflows/medicaid-heor-update.yml` — the two-job shape from
plan-credit-default-pd.md §7, **no schedule** (completed analysis; push/dispatch
only). The `update` job sets up **both** Python and R
(`r-lib/actions/setup-r@v2` + `renv::restore()`), runs
`python run_pipeline.py --offline --export-only`, runs the JSON guard, and commits
regenerated `site/` outputs. `sync-website` copies the full payload into
`website/public/medicaid-expansion-heor/{data/,dashboard.html,report.html}` via the
PAT and pushes (Cloudflare Pages redeploys).

**Human action items (Dhruv):** create repo `Medicaid-Expansion-HEOR`; add
`WEBSITE_REPO_TOKEN`; one-time Website edit — `/research` card +
`src/pages/research/medicaid-expansion-heor.mdx` (status `COMPLETED`, tags
`HEALTH ECONOMICS`, `CAUSAL INFERENCE`, `HEOR`, `POLICY`) embedding
`/medicaid-expansion-heor/dashboard.html`; download BRFSS/MEPS files into `data/raw/`
before the first full local run.

**Verify the deploy:** push; both jobs green; open
`https://dhruv-mehndiratta.com/medicaid-expansion-heor/dashboard.html` and
`/research/medicaid-expansion-heor`; confirm JSON under `/medicaid-expansion-heor/data/`
parses and the CEAC explorer works.

---

## 8. Acceptance criteria

- [ ] BRFSS (2011–2019 core) and MEPS fetched idempotently; survey design vars retained.
- [ ] Expansion timing encoded with per-state source URLs; eligibility (low-income
      non-elderly) defined and documented.
- [ ] Callaway–Sant'Anna group-time ATT + event study implemented (headline);
      Sun–Abraham + TWFE + Goodman-Bacon shown for contrast.
- [ ] **Event-study pre-trends reported and flat-tested**; non-flat → flagged as
      identification failure.
- [ ] Inference uses state clustering + **wild-cluster bootstrap**; CIs reported.
- [ ] HEOR overlay: QALY mapping with sourced weights; ICER; budget impact; vs
      $50k/$100k/$150k thresholds.
- [ ] **PSA / CEAC produced** (Monte Carlo over utilities, effect, cost, uptake) —
      ICER distribution, not a point.
- [ ] Robustness (alt eligibility, drop adopters, exclude COVID, alt controls) +
      refutation (placebo outcome, placebo timing) run and reported.
- [ ] Causal results clearly separated from HEOR model assumptions.
- [ ] JSON guard passes; report numbers trace to JSON; limitations present.

---

## 9. Task sequence

1. Scaffold repo (Python + R env), `config.yaml`, pinned `requirements.txt` +
   `renv.lock`, README/CLAUDE skeletons, `SOURCES.md`. **Verify:** `pip install` and
   `renv::restore()` succeed; `Rscript -e 'library(did)'` works.
2. `data/manual/expansion_dates.csv` (KFF) + `utility_weights.csv` (cited).
   **Verify:** dates match KFF tracker; weights have citations.
3. `fetch_brfss.py`: download 2011–2019 annual files; cache; print vintage.
   **Verify:** files load via `pyreadstat`; design vars present.
4. `fetch_meps.py`: expenditure/utilisation files. **Verify:** per-capita spend
   computable.
5. `build_brfss_panel.py`: harmonise variable names across years (they drift!),
   define eligibility, attach weights/strata/PSU, merge treatment timing. **Verify:**
   var-harmonisation unit test; weighted uninsurance trend looks sane (drops after
   2014 in expansion states).
6. `build_costs.py`: MEPS incremental cost params → `data/processed`. **Verify:**
   magnitudes plausible vs literature.
7. `did_callaway.R` → `results_csdid.json` (group-time + event-study + aggregate ATT).
   **Verify:** event-study leads near zero; ATT signs sensible.
8. `did_sunab.R` → `results_sunab.json` (+ TWFE + Goodman-Bacon). **Verify:** TWFE
   bias direction documented.
9. `inference_boottest.R`: wild-cluster bootstrap CIs. **Verify:** CIs wider than
   naive; reported.
10. `heor_icer.py`: QALYs from effect×utility, ICER from MEPS cost, budget impact →
    `results_heor.json`. **Verify:** arithmetic traceable; null-health-effect path
    handled honestly.
11. `heor_psa.py`: Monte Carlo PSA → CEAC → `results_psa.json`. **Verify:** ICER
    distribution + CEAC emitted; draws = config.
12. Robustness + refutation runs. **Verify:** placebos null; logged.
13. `export_json.py` → `site/data/*.json`. **Verify:** JSON guard passes.
14. Build `report.html` + `dashboard.html` (event-study, estimator comparison, CEAC
    explorer, budget-impact calculator). **Verify:** `file://` load; numbers match JSON.
15. `tests/` green; reproducibility check. 
16. Add workflow (§7) with Python+R setup; commit processed artefacts. **Verify:** CI
    `update` job green.
17. (Dhruv) secret + one-time Website page/card; **verify deploy**.

---

## 10. Limitations and caveats

- **Self-reported outcomes:** BRFSS health and cost-barrier measures are self-
  reported; they capture perceived access, not clinical outcomes or mortality.
- **QALYs are modelled, not measured:** the utility mapping is an assumption layer;
  the ICER is an illustrative HEOR translation, transparent and sensitivity-tested,
  not a primary cost-utility measurement. A null health effect yields no QALY gain —
  reported honestly.
- **External validity / co-treatments:** identified off adoption-timing differences
  amid concurrent ACA changes; the ATT is for adopting states in this period, not a
  universal expansion effect.
- **MEPS is national:** the cost side is parameterised from national data, not state-
  matched; budget impact is a stylised model.
- **Few clusters:** 50 states limit inferential precision despite wild bootstrap.
- **Not policy advocacy:** the analysis estimates effects and cost-effectiveness
  under stated assumptions; it does not argue for or against expansion.

---

## 11. Open questions and risks

1. **Estimator headline:** Callaway–Sant'Anna proposed as primary. Confirm (vs Sun–
   Abraham) — both will be shown regardless.
2. **Outcome set:** uninsurance + cost-barrier (strong, fast) + self-rated health
   (slower, possibly null). Confirm this trio; mortality (CDC WONDER) is a possible
   stretch outcome but weak at state-year level — default: exclude, mention.
3. **Utility-weight source:** which published crosswalk (EQ-5D vs SF-6D vs CDC HRQOL)
   should anchor the base case? Default: use a CDC-HRQOL/EQ-5D-based mapping, vary all
   in PSA. Supply a preference if you have one.
4. **R-in-CI cost:** R setup + `renv` adds CI time. Acceptable? (Alternative: run R
   locally, commit results JSON, keep CI Python-only export — recommended fallback if
   CI R proves flaky.)
5. **Window end:** stop at 2019 (clean) or extend through 2021 with COVID flags?
   Default: core 2011–2019; 2020–21 as flagged appendix.
