# Baseline Fairness Review

All policies within a scenario group share the same seed, exogenous arrival tape, city graph, base placements, fleet size, deadlines, configuration values, and arrival horizon. The result audit checked 440 matched groups and found the same incident count across all four policies in each group. Cost and service comparisons use the same recorded run definitions.

| Policy | Selection information | Demand knowledge | Communication / repositioning | Fairness interpretation |
|---|---|---|---|---|
| B1 | Central selector sees the feasible idle set and chooses minimum travel time. | No rate input to dispatch. | No peer messages; stays in place. | Simple nearest baseline; not decentralized. |
| B2 | Same feasible set; minimizes `alpha K T_resp`. | No rate input to dispatch. | No peer messages; stays in place. | Mathematically identical to B1 for positive common `alpha K`; not a distinct strategy. |
| B3 | Central Hungarian assignment uses global state and true rates, then greedy relocation. | True-rate oracle. | No peer channel is needed. | Strong information-advantaged centralized heuristic, but not an optimality certificate. |
| BID | Each ambulance uses its own state, rates, and delivered messages; all local minima commit. | Local discounted estimates, except the explicitly labeled oracle BID condition. | Full, radius-limited, lossy, or no peer packets; local relocation. | The method under study; it has less state/demand information than B3 in learned mode. |

The task signal is public to all policies, matching the proposal's incident observation. This means communication experiments isolate peer coordination and rate-sharing, not call-announcement reachability. B1/B2/B3 do not change behavior with BID's communication condition; in experiment 4 they serve as fixed reference rows. The fair claim is a matched-scenario comparison under stated information advantages, not an information-matched algorithm tournament.

Initial placements are deterministic and identical for every policy at a given fleet size. All use the same deadline feasibility rule and patient service rule. The common episode cost is computed by the same cost implementation for each committed dispatch, including B3's precomputed pairwise costs. B3 assignment/repositioning is globally informed and heuristic; BID's cost gap to it can have either sign.

