#!/usr/bin/env Rscript
# Wild-cluster bootstrap inference (R path) for the static DiD coefficient, via
# fwildclusterboot::boottest -- the correct few-clusters (50 states) fix. Corroborates
# the CS bootstrap CIs. Writes data/processed/results_boottest.json.
# In the Python path the wild-cluster bootstrap is built into pipeline/csa.py, so this
# script is only invoked when Rscript is available.
suppressMessages({
  library(arrow); library(fixest); library(fwildclusterboot); library(jsonlite); library(yaml)
})

repo <- normalizePath(file.path(dirname(sys.frame(1)$ofile), "..", ".."))
cfg  <- yaml::read_yaml(file.path(repo, "config.yaml"))
panel <- as.data.frame(arrow::read_parquet(file.path(repo, "data/processed/analysis_panel.parquet")))
outcomes <- names(cfg$outcomes)
B <- cfg$inference$wild_bootstrap_reps
set.seed(cfg$seed)

one <- function(y) {
  f <- panel; f$dep <- f[[y]]
  m <- feols(dep ~ post | state_fips + year, data = f, weights = ~wsum)
  bt <- boottest(m, param = "post", clustid = "state_fips", B = B, type = "rademacher")
  list(estimate = round(unname(coef(m)[["post"]]), 5),
       wild_ci_low = round(bt$conf_int[1], 5), wild_ci_high = round(bt$conf_int[2], 5),
       wild_p_value = round(bt$p_val, 4), B = B)
}

results <- setNames(lapply(outcomes, one), outcomes)
out <- list(method = "wild_cluster_bootstrap_twfe", engine = "R (fwildclusterboot)",
            seed = cfg$seed, results = results)
write_json(out, file.path(repo, "data/processed/results_boottest.json"),
           auto_unbox = TRUE, pretty = TRUE, digits = 8)
cat("[inference_boottest.R] wrote results_boottest.json\n")
