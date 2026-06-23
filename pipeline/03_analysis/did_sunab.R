#!/usr/bin/env Rscript
# Contrast estimators (R path): Sun-Abraham interaction-weighted event study + naive
# TWFE + Goodman-Bacon decomposition. Writes results_sunab.json (same schema as the
# Python fallback pipeline/03_analysis/did_twfe.py). Shown only to illustrate the
# staggered-adoption bias that motivates the CS headline.
suppressMessages({
  library(arrow); library(fixest); library(bacondecomp); library(jsonlite); library(yaml)
})

repo <- normalizePath(file.path(dirname(sys.frame(1)$ofile), "..", ".."))
cfg  <- yaml::read_yaml(file.path(repo, "config.yaml"))
panel <- as.data.frame(arrow::read_parquet(file.path(repo, "data/processed/analysis_panel.parquet")))
panel$g <- ifelse(is.na(panel$expansion_year_eff), 10000L, as.integer(panel$expansion_year_eff))
outcomes <- names(cfg$outcomes)
win_lo <- cfg$event_study$window_min; win_hi <- cfg$event_study$window_max

one <- function(y) {
  f <- panel; f$dep <- f[[y]]
  # naive TWFE static (post = treated & year>=g), state-clustered SE
  twfe <- feols(dep ~ post | state_fips + year, data = f, weights = ~wsum, cluster = ~state_fips)
  # Sun-Abraham event study (never-treated = control via g==10000), ref = -1
  sa <- feols(dep ~ sunab(g, year, ref.p = cfg$window$reference_period) | state_fips + year,
              data = f[f$g != 10000 | TRUE, ], weights = ~wsum, cluster = ~state_fips)
  agg <- aggregate(sa, "att")  # event-time aggregation
  es <- lapply(rownames(agg), function(nm) {
    e <- suppressWarnings(as.integer(gsub("[^0-9-]", "", nm)))
    if (is.na(e) || e < win_lo || e > win_hi) return(NULL)
    list(event_time = e, estimate = round(agg[nm, "Estimate"], 5),
         se = round(agg[nm, "Std. Error"], 5),
         ci_low = round(agg[nm, "Estimate"] - 1.96 * agg[nm, "Std. Error"], 5),
         ci_high = round(agg[nm, "Estimate"] + 1.96 * agg[nm, "Std. Error"], 5))
  })
  es <- Filter(Negate(is.null), es)
  # Goodman-Bacon decomposition (drops never-treated handling per package)
  gb <- tryCatch({
    bd <- bacon(dep ~ post, data = f, id_var = "state_fips", time_var = "year", quietly = TRUE)
    w <- tapply(bd$weight, bd$type, sum); d <- tapply(bd$estimate * bd$weight, bd$type, sum) / w
    list(by_type = setNames(lapply(names(w), function(t)
            list(weight_share = round(unname(w[t]) / sum(bd$weight), 4),
                 avg_did = round(unname(d[t]), 5))), names(w)),
         twfe_implied_weighted_avg = round(sum(bd$estimate * bd$weight) / sum(bd$weight), 5))
  }, error = function(e) list(error = conditionMessage(e)))

  list(twfe_static = list(estimate = round(coef(twfe)[["post"]], 5),
                          se = round(se(twfe)[["post"]], 5),
                          note = "naive two-way FE; biased under staggered timing"),
       sunab_event_study = es, goodman_bacon = gb)
}

results <- setNames(lapply(outcomes, one), outcomes)
mode <- fromJSON(file.path(repo, "data/processed/data_mode.json"))$data_mode
out <- list(method = "twfe_sunab_bacon", engine = "R (fixest/bacondecomp)",
            data_mode = mode, seed = cfg$seed, outcome_labels = cfg$outcomes, results = results)
write_json(out, file.path(repo, "data/processed/results_sunab.json"),
           auto_unbox = TRUE, pretty = TRUE, digits = 8)
cat("[did_sunab.R] wrote results_sunab.json (engine=R fixest)\n")
