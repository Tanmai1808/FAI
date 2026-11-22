# Metric Review

| Metric | Implemented calculation / denominator | Interpretation and caveat |
|---|---|---|
| Service rate | Incidents with first scene arrival by deadline divided by all generated incidents. | Complements missed-call rate; 1.0 when a tape has no incidents. |
| Mean response | Mean arrival-to-first-scene time for incidents with scene-arrival events only. | Must be called **mean response among served incidents**. Missed calls are excluded; a high miss rate can make a policy's conditional mean look favorable. No arbitrary latency is imputed. |
| Critical response | Same conditional mean restricted to `K >= 4`. | Also excludes missed critical calls; read with service/missed rates. |
| Demand-weighted coverage | Time integral over the arrival horizon of the fraction of true-rate mass in zones covered by at least one idle ambulance within `theta`. | Availability proxy under synthetic demand; it is not actual geographical reach, scene-service probability, or clinical coverage. Busy/repositioning units do not cover. |
| Utilization | Busy ambulance-minutes over `n_ambulances × arrival_horizon_minutes`. | Counts response, on-scene, return, and reposition states. Numerator is clipped to the same horizon for all policies. |
| Messages sent/delivered | Reachable directed peer packets attempted / successfully delivered. Unreachable radius pairs and self-messages are not attempted; dropped lossy packets count as sent. | Message-type counters include bid, state, and rate packets. The environmental call signal is not counted. |
| Messages per incident | Sent directed packet attempts divided by generated call count. | Zero when no calls. Counts offered attempts only when a radio link is in range. |
| Duplicate rate | Distinct calls with more than one commitment divided by all calls. | A duplicate ambulance remains busy, but contributes no second service credit. |
| Missed rate | Calls expired without scene service divided by all calls. | A call with an arrival exactly at deadline is served because scene-arrival events precede expiry. |
| Demand RMSE | At each hourly boundary, mean per-agent zone-vector RMSE against simulator true rates; then averaged over boundaries. | B1/B2 values are diagnostics, not inputs to their selectors. B3 and oracle BID RMSE=0 by construction, not a learned result. The metric is time-averaged; it does not expose a pre/post-shift adaptation curve. |
| Dispatch cost | Sum of per-committed-pair response/coverage/home-demand surrogate terms. | Uses true rates and idle positions for environment cost accounting. Duplicates create multiple dispatch costs. Weights are arbitrary surrogate scales. |
| Expiration cost / total cost | `rho × expired` / dispatch cost plus expiration cost. | Lower is preferred under the declared surrogate only. |
| Absolute B3 gap | `C_policy - C_B3` per matched seed. | Signed; positive means higher cost than B3. |
| Relative B3 gap | `(C_policy-C_B3)/C_B3` only when B3 cost is positive. | Empirical signed gap to a heuristic, not theoretical PoD. At zero reference cost the ratio is undefined. |

The committed raw records do not contain incident-level response samples, so medians and percentiles cannot be reconstructed from the aggregated response means. The report uses conditional means plus service/miss rates and does not claim tail-response quantiles.

