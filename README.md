# Medicaid-Expansion-HEOR

**Did the ACA Medicaid expansions causally reduce cost-related barriers to care and
improve self-reported health among low-income adults — and what does that imply, in
HEOR terms, for cost-effectiveness (cost per QALY) and budget impact?**

A staggered difference-in-differences study (Callaway–Sant'Anna group-time ATT, with
Sun–Abraham and naive TWFE shown for contrast) on CDC BRFSS, translated into the
language a health-economics consultancy speaks: **ICER, QALYs, budget impact, and a
probabilistic sensitivity analysis / cost-effectiveness acceptability curve (CEAC)**.

The causal estimate is presented first and on its own merits; the HEOR overlay is
clearly delineated as a transparent, sensitivity-tested *model* built on top of it.

🔗 Live: `https://dhruv-mehndiratta.com/research/medicaid-expansion-heor`

---

## Identification & honesty, up front

- **Estimand:** ATT of a state adopting Medicaid expansion on (i) uninsurance,
  (ii) "could not see a doctor because of cost," (iii) fair/poor self-rated health,
  among **policy-eligible** low-income (≤138% FPL) non-elderly (19–64) adults.
- **Why Callaway–Sant'Anna:** classic two-way fixed-effects DiD is biased under
  staggered timing with heterogeneous effects (Goodman-Bacon; de Chaisemartin–
  D'Haultfœuille). CS group-time ATTs with not-yet/never-treated controls fix this;
  TWFE is shown only to *demonstrate* the bias.
- **Falsification:** non-flat event-study pre-trends ⇒ identification fails and we say
  so. If the coverage/cost effects vanish or flip under CS, the hypothesis is falsified.
  A null self-rated-health effect yields **no QALY gain** and is reported as such — the
  ICER calc never manufactures a favourable number from a null.
- **Uncertainty is built in:** state-clustered **wild-cluster bootstrap** CIs (few
  clusters), and a Monte-Carlo **PSA → CEAC** for the HEOR layer — never a bare point.

---

## ⚠️ Data status: real-data path + synthetic demo fallback

BRFSS and MEPS are **public bulk downloads** (no key), but they are large
(tens–hundreds of MB/year) and are **not** committed. The fetchers
(`pipeline/01_fetch/`) download the real files into `data/raw/<source>/<date>/`.

If the raw files are absent, the pipeline builds a **calibrated synthetic panel** with
a *known* planted ATT (`config.yaml → synthetic`) so the entire chain
(clean → DiD → HEOR → PSA → export → dashboard) runs, is unit-tested, and reproduces
identical JSON. **Every JSON, the report, and the dashboard are stamped
`"data_mode": "synthetic"` or `"real"`** so a synthetic run is never mistaken for a
finding. The synthetic mode exists to prove the machinery and to validate that the
estimators recover the planted effect — not to make a substantive claim.

To run on real data: see `pipeline/01_fetch/fetch_brfss.py --help` and `SOURCES.md`.

---

## The R question (headline estimator)

The plan's headline estimator is Callaway–Sant'Anna via R's `did` package. **R is
optional here.** `run_pipeline.py` uses the R scripts in `pipeline/03_analysis/*.R`
when `Rscript` is on `PATH`; otherwise it falls back to the tested pure-Python
implementation in `pipeline/03_analysis/_csa.py`, which implements the same group-time
ATT estimator with not-yet/never-treated controls and event-study aggregation. This is
the plan's own recommended fallback (plan §11 Q4: "run R locally, commit results, keep
CI Python-only"). Both paths write the same `results_csdid.json` schema.

---

## Reproduce

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt   # Windows
python run_pipeline.py            # full: fetch -> clean -> DiD -> HEOR -> PSA -> export
python run_pipeline.py --offline  # rebuild JSON from committed processed artefacts
python run_pipeline.py --stage 3  # run a single stage (1 fetch, 2 clean, 3 analysis, 4 export)
python -m pytest tests/           # data-harmonisation, eligibility, estimator-recovery, JSON schema
```

Open `site/dashboard.html` directly (`file://`) or via the live page. The dashboard
reads only `site/data/*.json` — no backend.

## Layout

```
pipeline/01_fetch     idempotent, dated, cached fetchers (+ synthetic generator)
pipeline/02_clean     harmonise BRFSS vars across years, eligibility, weights; MEPS costs
pipeline/03_analysis  CS / Sun-Abraham / TWFE / Goodman-Bacon / wild bootstrap; ICER; PSA/CEAC
pipeline/04_export    site/data/*.json (the only thing the dashboard reads)
site/                 report.html, dashboard.html, data/*.json
data/manual/          expansion_dates.csv (KFF), utility_weights.csv (cited)
```

See `SOURCES.md` for every figure → primary source, and `CLAUDE.md` for the eligibility
proxy, estimator rationale, utility-weight provenance, and house rules.
