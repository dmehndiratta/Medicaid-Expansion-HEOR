#!/usr/bin/env Rscript
# Headline estimator (R path): Callaway-Sant'Anna group-time ATT via the `did` package.
# Reads data/processed/analysis_panel.parquet (state x year weighted outcome means) and
# writes data/processed/results_csdid.json in the SAME schema as the Python fallback
# (pipeline/csa.py). run_pipeline.py prefers this when Rscript is on PATH; otherwise the
# tested Python implementation runs (plan §11 Q4).
suppressMessages({
  library(arrow); library(did); library(jsonlite); library(yaml)
})

repo <- normalizePath(file.path(dirname(sys.frame(1)$ofile), "..", ".."))
cfg  <- yaml::read_yaml(file.path(repo, "config.yaml"))
panel <- as.data.frame(arrow::read_parquet(file.path(repo, "data/processed/analysis_panel.parquet")))

# never-treated coded as 0 for did::att_gt; late adopters beyond the window already
# carry NA in expansion_year_eff (treated as not-yet-treated controls inside the window).
panel$g <- ifelse(is.na(panel$expansion_year_eff), 0, as.integer(panel$expansion_year_eff))
outcomes <- names(cfg$outcomes)
ref <- cfg$window$reference_period
win_lo <- cfg$event_study$window_min; win_hi <- cfg$event_study$window_max
set.seed(cfg$seed)

estimate_one <- function(y) {
  m <- att_gt(yname = y, tname = "year", idname = "state_fips", gname = "g",
              weightsname = "wsum", data = panel,
              control_group = ifelse(cfg$estimators$control_group == "nevertreated",
                                     "nevertreated", "notyettreated"),
              bstrap = TRUE, cband = TRUE, clustervars = "state_fips")
  dyn <- aggte(m, type = "dynamic", min_e = win_lo, max_e = win_hi, na.rm = TRUE)
  grp <- aggte(m, type = "group", na.rm = TRUE)             # overall ATT
  z <- qnorm(1 - (1 - cfg$inference$ci_level) / 2)

  es <- lapply(seq_along(dyn$egt), function(i) {
    list(event_time = dyn$egt[i], estimate = round(dyn$att.egt[i], 5),
         se = round(dyn$se.egt[i], 5),
         ci_low = round(dyn$att.egt[i] - z * dyn$se.egt[i], 5),
         ci_high = round(dyn$att.egt[i] + z * dyn$se.egt[i], 5))
  })
  leads <- which(dyn$egt < ref)
  if (length(leads) > 0) {
    M <- dyn$att.egt[leads]; V <- diag(dyn$se.egt[leads]^2, nrow = length(leads))
    W <- as.numeric(t(M) %*% solve(V) %*% M); p <- 1 - pchisq(W, df = length(leads))
  } else { W <- NA; p <- NA }

  list(outcome = y, estimator = "callaway_santanna",
       control_group = cfg$estimators$control_group,
       overall_att = list(estimate = round(grp$overall.att, 5),
                          se = round(grp$overall.se, 5),
                          ci_low = round(grp$overall.att - z * grp$overall.se, 5),
                          ci_high = round(grp$overall.att + z * grp$overall.se, 5),
                          p_value = round(2 * (1 - pnorm(abs(grp$overall.att / grp$overall.se))), 4)),
       event_study = es,
       pre_trend_test = list(leads_tested = dyn$egt[leads], wald_stat = round(W, 4),
                             p_value = round(p, 4), flat = isTRUE(p > 0.05),
                             interpretation = if (isTRUE(p > 0.05))
                               "pre-trends not rejected (identification assumption supported)"
                             else "PRE-TRENDS REJECTED - identification suspect"),
       n_states = length(unique(panel$state_fips)), bootstrap_reps = NA,
       ci_level = cfg$inference$ci_level)
}

results <- setNames(lapply(outcomes, estimate_one), outcomes)
mode <- fromJSON(file.path(repo, "data/processed/data_mode.json"))$data_mode
out <- list(method = "callaway_santanna", engine = "R (did)", data_mode = mode,
            seed = cfg$seed, outcome_labels = cfg$outcomes, results = results)
write_json(out, file.path(repo, "data/processed/results_csdid.json"),
           auto_unbox = TRUE, pretty = TRUE, digits = 8)
cat("[did_callaway.R] wrote results_csdid.json (engine=R did)\n")
