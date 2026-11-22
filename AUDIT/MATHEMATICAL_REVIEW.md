# Mathematical Review

## Scope and source comparison

Reviewed `MODEL_DESIGN.md`, `src/ambulance_dispatch/policies/costs.py`, `policies/bidding.py`, `policies/baselines.py`, `policies/centralized.py`, and the preserved six-page `docs/reference/original-proposal.pdf`. The original proposal, pages 3–5, defines a common response/coverage/expiration payoff and a bid containing response, `beta R_i`, and `gamma D_i`; the team payoff omits the explicit home-demand term. The instructor feedback explicitly asks for consistent beta notation and alignment of the bid and team payoff. The implementation adopts the smallest explicit alignment: one additive common surrogate cost includes the same `beta R_i` and `gamma D_i` terms used by the BID score. It does not rewrite the proposal PDF.

## Objective and symbols

The implementation uses

\[
C(\pi)=\sum_{(e,i)\in\mathcal D(\pi)}
\left[\alpha K_e T^{\rm resp}_{i,e}+\beta R_{i,e}+\gamma D_{i,e}\right]
+\rho N_{\rm expired}(\pi), \qquad u_i=-C_{\rm step}.
\]

`T_resp` is queue wait plus shortest-path response travel, in minutes; `K` is the incident severity category. `B_i=2T_i+s` is round-trip busy time in minutes and is converted to hours before multiplication by zone rates in calls/hour. `R_i` is expected calls during that busy interval in zones outside `h_i` for which removing `i` changes idle coverage from covered to uncovered. `D_i` is expected calls in its home zone during that interval, charged regardless of whether another idle ambulance covers the home zone. Since the home zone is omitted from `R_i`, the two demand terms are disjoint. `rho` is cost per incident that expires before scene service.

The weights convert unlike quantities into an arbitrary common surrogate cost: response is severity-weighted minutes; exposure terms are expected calls. The weights are not clinically calibrated, normalized, or estimated from data. The common objective is an explicit modeling choice and does not claim monetary or clinical units. Duplicate commitments contribute one dispatch cost per committed ambulance; one patient receives at most one service credit.

## Bid alignment and approximation boundary

`compute_bid` evaluates the same weighted formula using the agent's belief set, estimated rates (or oracle rates), its current wait/travel response estimate, and `B_i`. Therefore the instructor's beta notation and `gamma D_i` consistency corrections are satisfied. In the special case of one dispatch, exact state, true rates, and no estimation or interaction discrepancy, the BID score equals that pair's common dispatch cost.

This is not an exact global marginal-cost bidding mechanism. The bid omits the expiration penalty (infeasible bids are removed by a deadline filter), ignores later calls and action sequences, and may use stale positions, message-filtered demand estimates, or a simultaneous local view. B3 likewise evaluates assignments from one pre-allocation snapshot. With multiple assignments, additive per-pair coverage charges can overlap. These are explicit surrogate/heuristic limits; neither the code nor the report claims an optimal team policy.

## Theoretical PoD and reported comparator

The proposal's nonnegative theoretical argument applies only when the centralized policy is the optimum over a policy set containing all decentralized policies. Implemented B3 is a Hungarian pairwise assignment plus greedy relocation heuristic, not that optimum. The repository therefore does **not** report theoretical PoD. It computes the per-seed signed empirical gap

\[
\Delta_C(\pi,B3;s)=C_\pi(s)-C_{B3}(s),\qquad
g_{B3}(\pi;s)=\frac{C_\pi(s)-C_{B3}(s)}{C_{B3}(s)}
\quad\text{when }C_{B3}(s)>0.
\]

Positive means higher cost than B3; negative means lower observed cost than this heuristic. At zero B3 cost the relative value is undefined and the absolute difference remains defined. This is consistent with instructor feedback.

## B1 and B2

The preserved proposal specifies B1 as `argmin T_i` and B2 as `argmin alpha K T_i`. For a fixed call, positive common `alpha K` preserves ordering, so B1 and B2 are mathematically equivalent. Code uses the same feasible candidate set and ascending ambulance-ID tie-break. Result audit found exact equality in all 440 matched experiment/level/seed/knowledge groups over service, response, coverage, utilization, cost, and messages. Option A from the audit brief is retained: no silent B2 redefinition and no claim that B1/B2 are distinct strategies.

## Weight evidence

Original `exp7_weight_tradeoff` holds `alpha=1` and changes `beta` and `gamma` together at `(4,4)`, `(8,8)`, and `(16,16)`. It changes the ratio of coverage/demand terms to response but cannot identify independent beta and gamma effects. The separately configured `exp8_weight_sensitivity` varies each coefficient around the same default while holding the other two fixed. Its results are separate from, and do not replace, the original seven-family run. Neither sweep establishes a generally optimal weight choice or estimates interactions.

## Decision

The mathematical model is consistent with the instructor's requested correction and preserves the proposal's intended time/criticality/coverage/home-demand trade-off. The home-zone term is intentionally a proxy even when backup coverage exists. No science-changing equation or policy definition was altered during the audit; changes so far clarify units, approximation limits, labels, and evaluation of independent weight sensitivity.

