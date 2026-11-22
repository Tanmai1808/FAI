# Preserved initial sensitivity attempt (do not use for final comparisons)

This folder preserves the first 720-episode alpha/beta/gamma sensitivity run. Its raw `raw_results.csv` records are valid simulator outputs for seeds 1000–1019, but the first `b3_comparisons.csv` join incorrectly required `demand_condition` to match. B3 was labeled oracle while B1, B2, and BID were labeled learned, so the non-B3 B3-gap fields were blank and the resulting summary/plots were not valid comparisons.

The join key was corrected to match experiment, weight level, and seed, which are the shared call-tape keys. The full 720 episodes were rerun into the sibling `weight_sensitivity/` directory. Only that corrected run is used by the report. This folder is retained for audit transparency; its summary and plots must not be cited.
