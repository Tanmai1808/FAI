# Model and Simulation Design

## 1. Scope and relation to the proposal

This document records the computational interpretation implemented from the project-review proposal. The proposal remains the foundation: a cooperative ambulance fleet, Poisson demand, B1/B2/B3 comparisons, decentralized bids with time/coverage/demand terms, restricted communication, online demand estimates, seven planned experiments, and a restricted unilateral-deviation check. The instructor corrections are applied directly:

- B3 is a **centralized heuristic benchmark**, not a proven centralized optimum.
- The coverage coefficient is written `beta` in the team objective and in bids.
- The demand-away term `gamma D_i` appears in both the common team cost and the bid. The coverage and home-demand terms are partitioned to avoid counting the same zone in both.
- B3 is an empirical heuristic reference, not the centralized optimum. We report a signed empirical cost gap to B3; we do not estimate theoretical PoD against an optimizer that was not implemented.

The city and traffic are synthetic. No inference about real ambulance systems is claimed.

## 2. City, demand, and incident records

Let the synthetic road network be a connected weighted graph `G=(V,E)`. Nodes are service/demand zones. Edge weights are positive travel times in minutes. A deterministic shortest-path routine gives `tau(x,z)` for every pair of nodes. A default city is a 5-by-5 grid; city size and weights are configuration values. A coverage radius `theta` is in the same travel-time units.

For zone `z`, the true rate `lambda_z(t)` is in incidents per hour and is piecewise constant within the configured demand interval. For a time interval of length `Delta` hours, arrivals in zone `z` are Poisson:

```text
N[z, interval] ~ Poisson(lambda_z * Delta)
```

Arrival times are drawn uniformly within each interval. Severity `K` is sampled from a predeclared categorical distribution on `{1,2,3,4,5}`; deadline `delta(K)` and on-scene duration `s` are fixed in the run configuration. Uniform, fixed-hotspot, and midpoint-shifting-hotspot rate maps are generated before policy rollouts. The event tape for a given scenario seed is reused across policies (common random numbers).

An incident record is `(id, arrival_time, zone, K, deadline_time, status)`. Its response time is measured from arrival until the first assigned ambulance reaches the incident. It is served on time iff this time is no greater than `delta(K)`; equality counts as on time. A call that has not reached service by its deadline expires and is counted once.

## 3. Ambulance state and movement

Each ambulance `i` has a unique ID, a fixed home zone `h_i`, a current staging node `x_i`, and one of these states:

- `idle`: available for a dispatch or relocation;
- `response_busy`: dispatched to a call, including outbound travel, on-scene time, and the modeled return;
- `reposition_busy`: traveling to a selected staging node.

### Response and return model

When an idle ambulance at node `x_i` is assigned to incident `e` at `l_e`, its response travel is:

```text
T_i(e) = tau(x_i, l_e)
```

As in the proposal, on-scene duration is `s` and the ambulance returns to its dispatch staging node along the same shortest path. Thus its committed busy duration is:

```text
B_i(e) = 2 * T_i(e) + s
```

It is not counted as covering any zone while busy. At `now + B_i(e)` it becomes idle at the original staging node `x_i`. This is a deliberate round-trip abstraction: the model does not route to hospitals or model hospital queues. Response time for a queued incident assigned at time `t_d` is `t_d - arrival_time + T_i(e)`.

Only ambulances whose predicted response time fits within the incident's remaining deadline are eligible to bid. Incidents with no eligible responder remain pending and may be assigned when an ambulance becomes idle; they expire at their deadline if still unserved. This avoids sending an ambulance that is already known to arrive too late. A queued incident's waiting time is included in both its response time and its feasibility check.

### Repositioning

After a bidding auction, each nonselected idle ambulance independently considers each node `z`. Using its current local demand and position estimates, it chooses the node with the highest demand-weighted coverage gain; ties use ascending node ID. It moves only if the gain exceeds `epsilon`. Multiple agents may choose the same destination because local decisions are not centrally coordinated. Reposition travel time is `tau(x_i,z)`; the ambulance is unavailable while moving and becomes idle at `z` on arrival. B1 and B2 stay in place. B3 repositions greedily one ambulance at a time using global positions and true rates, recomputing gain after each move.

## 4. Common objective and consistent bidding cost

Let `I` be the set of idle ambulances immediately before a dispatch decision. For true or estimated locations, zone `z` is covered by idle set `I` when:

```text
cover(I,z) = 1[ min over j in I of tau(x_j,z) <= theta ]
```

For a candidate ambulance `i`, its marginal coverage loss in zone `z` is:

```text
L_i(z; I) = cover(I,z) - cover(I without i,z)   # in {0,1}
```

The proposal's terms `R_i` and `D_i` are retained, with a disjoint zone partition. Coverage loss outside ambulance `i`'s fixed home zone is:

```text
R_i(e) = B_i(e) * sum over z != h_i of lambda_z(now) * L_i(z; I)
D_i(e) = B_i(e) * lambda_h_i(now)
```

`R_i` is expected incident demand outside the home zone exposed to loss of idle coverage. `D_i` is expected home-zone demand during the ambulance's absence, as in the proposal, even when another ambulance can still cover that home zone. The terms partition zones: `R_i` excludes `h_i`; `D_i` contains only `h_i`. Rates are in incidents/hour and `B_i` is converted to hours in these products.

If a call has multiple committed responders, every committed pair contributes a dispatch cost and busy interval; the patient receives only one service credit. The additive surrogate can charge overlapping marginal exposure for concurrent assignments. This is an explicit property of the heuristic objective, not an exact integral of unique future uncovered calls.

For a dispatch of incident `e` by `i`, define the common dispatch cost:

```text
c(e,i) = alpha * K_e * response_time(e,i)
          + beta * R_i(e)
          + gamma * D_i(e)
```

The episode cost and identical-interest payoff are:

```text
C(pi) = sum over dispatches (e,i) of c(e,i) + rho * N_expired
u_i = -C_step for every ambulance i
V(pi) = E_pi[sum_t u_i(t)] = -E_pi[C(pi)]
```

`alpha` prices criticality-weighted response minutes; `beta` and `gamma` price expected demand exposed outside and inside the dispatching ambulance's home zone; `rho` is the penalty per expired call. The weights and all rate/time units are recorded in configuration. This is an explicit cooperative **surrogate objective** consistent with the proposal's local bid. It is not presented as the complete monetary or clinical value of ambulance service. The simulator separately measures realized coverage over time, service rate, response, and utilization.

The bid uses each agent's own rate estimates and local state table. Let `I_hat_i` be the idle set agent `i` currently believes available, formed from its own state plus nonstale status messages. Let `lambda_hat^i_z` be its current estimate for zone `z`. For an eligible agent:

```text
J_i(e) = alpha * K_e * (now - arrival_time(e) + T_i(e))
         + beta * B_i(e) * sum over z != h_i of lambda_hat^i_z * L_i(z; I_hat_i)
         + gamma * B_i(e) * lambda_hat^i_h_i
```

Thus `beta` prices coverage loss outside the dispatching unit's home zone, and `gamma D_i` prices home-zone demand while that unit is away. Both terms are present in the common cost and the bid. Under full communication with oracle rates and accurate state, the bid equals the corresponding one-pair dispatch cost before any expiration penalty. The bid is not an exact marginal cost of the full episode: it omits the future expiration term, evaluates a myopic state, and can have stale state or rate estimates; concurrent bids and assignments can interact. B3's matching uses a shared pre-allocation snapshot, so its sum of pairwise costs can also charge overlapping coverage exposures.

B2 is `argmin_i alpha * K_e * response_time(e,i)` among feasible idle ambulances. B1 is `argmin_i response_time(e,i)`. All ties use `(cost, ambulance ID)` ascending.

## 5. Empirical signed gap against B3

Let `C_B3(s)` and `C_pi(s)` be costs for policy `pi` and B3 on the same scenario seed `s`. B3 uses global state and true demand but uses a Hungarian assignment over pairwise costs and greedy relocation. Interactions among assignments mean it is not guaranteed to minimize the full episode objective.

For each matched seed, report the signed absolute gap:

```text
Delta_C(pi, B3; s) = C_pi(s) - C_B3(s)
```

Positive means the policy incurred more cost; negative means it beat the B3 heuristic on that seed. Also report the signed relative gap only when `C_B3(s) > 0`:

```text
g_B3(pi; s) = (C_pi(s) - C_B3(s)) / C_B3(s)
```

When B3 cost is zero, the relative ratio is **undefined**; report `Delta_C` and mark the ratio NA (never divide by an arbitrary epsilon). Aggregate paired per-seed differences and their bootstrap confidence intervals. For higher-is-better measures such as service rate and coverage, show the raw signed difference `metric_pi - metric_B3`; if a relative loss ratio is useful, define loss as `1 - metric` and apply the same zero-denominator rule. Do not call utilization or message count a PoD because neither has a universally preferred direction. In paper text, call these values the **empirical signed gap to heuristic B3** (or `PoD_B3` with that definition); make no claim that the gap is nonnegative.

## 6. Observations, communication, and dispatch outcomes

### What each agent can observe

The active incident is a task signal visible to all agents at its arrival, consistent with the proposal's `e_t` in each local observation. This shared task signal is not an inter-agent message. Each agent also observes its own location, status, home zone, learned rates, and its own direct demand-observation partition. Zones are assigned to a unique direct observer by nearest fixed home zone (ties by ambulance ID). That observer sees all arrivals in its partition, even while its vehicle is busy. A responding agent also observes the outcome/response time of its assigned incident.

At time zero, the configured initial ambulance placements are common knowledge. Thereafter, an agent does not receive true demand rates, other agents' current state, bids, or other agents' local observations unless the communication channel delivers a corresponding message. It keeps only the most recently received state per sender; a state older than configured `status_ttl` is stale and excluded from its estimated idle set. B3 alone has global positions/status and true `lambda`.

Status messages are sent when an ambulance becomes busy, returns to idle, or completes a relocation. A state message reports its last staging node, busy/idle flag, and expected free time. Busy units do not send periodic updates while traveling; their last reported staging node is used for link-range checks until the next state change. An auction bid also carries the sender's current state. These messages use the same directed radius/loss rule and are timestamped, so partial communication can leave an agent with stale positions or availability.

### Communication graph and regime table

Two agents can exchange a message only when their last reported staging nodes are within communication radius `r` by shortest-path travel time. Each directed packet is independently delivered with probability `1-p`; delivery has zero latency. Self-information is always available. Bid messages include `(agent ID, bid, staging node, eligible/idle flag, timestamp)`. A rate message contains `(source ID, zone, bin ID, updated rate estimate, timestamp)`. A message is counted only when sent; successful delivery is also recorded.

| Regime | Parameters / rule | Current eligible bids an agent can compare | Expected dispatch behavior |
|---|---|---|---|
| Full | `r = infinity`, `p = 0` | All eligible bids | Exactly one responder if at least one feasible idle ambulance exists; deterministic ID tie-break resolves equal bids. |
| Radius-limited | Finite configured `r`, `p = 0` | Bids from currently reachable agents; distant components cannot compare | Each component may have its own local minimum, so a call can have duplicate responders. A feasible local minimum always responds. |
| Lossy | `r = infinity`, `0 < p < 1` | Self plus successfully received bids; directed losses can create different views | Disconnected views may produce multiple local minima and duplicate responders. |
| None | No inter-agent packets (`p = 1` operationally) | Self bid only | Every feasible idle ambulance responds; one feasible ambulance yields one responder, multiple feasible ambulances yield duplicates. Under "none", no peer messages are sent or delivered (`messages_sent == 0`), but the public call announcement signal remains broadcast. With no peer bids received, every feasible idle ambulance evaluates its own bid as the local minimum and commits. Thus BID under "none" represents a maximally uncoordinated reference condition under the local-minimum protocol. (This applies to BID only; centralized baselines B1, B2, B3 ignore peer communication). |

At an auction, every eligible agent sends its bid once. Agent `i` commits iff its `(J_i, ID_i)` is the minimum of its own bid and all eligible bids it received for that auction. The simulator globally processes task-arrival, travel-completion, deadline, and message-delivery events. For BID, it does not centrally choose the winner: each agent's local minimum decision is evaluated against that agent's delivered view. B1/B2 selection and B3 assignment are centrally computed baseline actions. With a total ordering, at least one feasible agent is a local minimum, so this exact protocol does **not** create an immediate zero-responder call when any feasible agent knows the incident. This corrects the proposal's implication that missed/expired dispatch can arise directly from incomplete bid comparison.

A **duplicate dispatch** occurs when more than one agent commits to the same incident. All committed ambulances make the trip and remain busy for their own `2T+s`; the earliest arrival serves the patient once, and extra units do not add service credit. Ambulances always return to their dispatch node (the staging base from which they were dispatched). The primary duplicate metric is the **duplicate rate**, defined as the number of incidents with more than one ambulance committed divided by total incidents (`duplicate_incidents / n_incidents`). In addition, the simulator records **duplicate commitments** (the sum of extra responder assignments beyond the first across all duplicate incidents, $\sum \max(0, |\text{responders}| - 1)$) and **duplicate scene arrivals** (the count of secondary ambulances that physically reached the scene after the first responder, $\sum \max(0, |\text{scene\_arrivals}| - 1)$).

An **expired dispatch** (formerly termed "missed dispatch") occurs when an incident expires without any ambulance reaching it by its deadline; its rate is the **expired rate**, defined as expired incident count divided by total generated incident count (`expired / n_incidents`). User-facing assets and documentation consistently use the term **expired** instead of "missed". Expiration can occur in every regime when all ambulances are busy, all idle ETAs exceed remaining patience, or a pending call is not served before expiration. Under partial/lossy/no communication, duplicate dispatches can increase later expired-call rates by keeping multiple units busy. The reported counts do not assume call-announcement loss.

## 7. Online demand learning

The primary learner is a discounted rate estimator to handle shifting hotspots. Time is divided into fixed bins of `Delta = 1 hour`. For direct-observer agent `o(z)` and zone `z`, let `N_{z,b}` be its observed count in bin `b`. It updates:

```text
lambda_hat[o(z),z,b] = (1-eta) * lambda_hat[o(z),z,b-1] + eta * (N[z,b] / Delta)
```

Each zone begins at the configured uniform prior `lambda_prior = total_prior_rate / number_of_zones`. It is a prior, not the true rate. At a bin boundary, the zone owner sends the updated estimate to neighboring agents over the same radius/loss channel. A recipient replaces its stale estimate for that zone with the received owner's estimate; it deduplicates `(source, zone, bin)` so retransmissions cannot count the same observation twice. If the rate packet is lost or no path is available, the recipient keeps its prior/latest estimate. Bin boundaries are processed before an incident at the same timestamp, giving a fixed update order.

The oracle condition exposes true `lambda_z(t)` to the bidding policy for the run. The learned condition exposes only the local/received estimate. Both conditions receive the same incident task signals, positions/status rules, and scenario tape. Message counts include rate/status/bid messages and are broken down by type; reports include total messages and messages per incident.

### Time series tracking and shifting demand boundary convention
At every learning-bin boundary, the simulator evaluates demand estimation error and records time series rows in `learning_rmse_timeseries.csv` with fields `(experiment, level, policy, seed, time_minutes, rmse)`.

1. **RMSE averaging convention**: For each agent `i`, root-mean-square error across all `Z` zones is computed as:
   ```text
   RMSE_i = sqrt( (1 / Z) * sum_{z=1}^Z (lambda_hat_{i,z} - lambda_z)^2 )
   ```
   The reported `rmse` is averaged across all `N` agents:
   ```text
   rmse = (1 / N) * sum_{i=1}^N RMSE_i
   ```
   For oracle demand runs, `rmse` is zero by construction.
2. **Boundary convention at hotspot shift**: Under shifting demand (`demand_pattern="shifting"` in `exp3` and `exp5b`), demand rates switch abruptly from an initial hotspot pattern to a secondary hotspot configuration at the scenario midpoint (`horizon_minutes / 2.0`, minute 3000 in a default 6000-minute run). At the exact shift boundary timestamp (minute 3000), the learner closes the bin covering `[2940, 3000)`. Because this bin's observations were generated entirely under the pre-shift regime, the newly updated estimate is compared against the **OLD** rate schedule (`now - 1e-9`). All subsequent bin boundaries (minute 3060, 3120, etc.) evaluate estimates incorporating post-shift observations against the **NEW** rate schedule.

## 8. Centralized planner and repositioning heuristic

For each pending incident `e` and feasible idle ambulance `i`, B3 constructs the pairwise cost from the same `alpha`, `beta`, `gamma`, `rho`, true `lambda`, global idle set, and expected response/busy times. It adds dummy rows/columns so the Hungarian method can leave ambulances idle or incidents unmatched with the configured miss penalty. It then assigns each incident at most once and each ambulance at most once in that allocation round. This is a centralized **heuristic**: pairwise costs are formed from a common pre-assignment snapshot and do not capture all interaction effects across a whole episode. B3 uses `rho` as the slack cost of leaving a currently pending call unassigned in its one-step Hungarian assignment; this matching penalty is an internal trade-off parameter of the one-step optimizer and is not the same as the actual expiration penalty charged by the simulator when an incident reaches its deadline unresolved. After assignments, B3 greedily moves idle ambulances to maximize true demand-weighted coverage, updating the covered set after each move. Its construction is an implementation choice for a strong comparison, not an optimality proof.

## 9. Event ordering, accounting horizons, and simulator pseudocode

### Accounting horizons and physical assumptions
1. **Accounting horizon**: The simulation generates new exogenous incident arrivals strictly up to `horizon_minutes`. Outstanding trips (response, on-scene, return) and already-generated pending calls are drained after `horizon_minutes` until all events complete, ensuring every incident reaches a definitive terminal outcome (`served` or `expired`). Coverage and fleet utilization integrals stop accumulating at `horizon_minutes` (`min(now, horizon_minutes)`). However, expiration penalties for calls generated before the horizon that expire during or after the horizon drain are still charged in `total_cost`.
2. **Repositioning**: Repositioning moves an idle ambulance to another staging node to improve coverage. While repositioning, an ambulance is unavailable for dispatch and is treated as busy (contributing to fleet utilization), but repositioning travel itself is not charged as an explicit penalty in total cost (`total_cost = dispatch_cost + expiration_cost`).
3. **Coverage definition**: Coverage counts **idle** ambulances only. Any vehicle currently dispatched, on-scene, returning to origin, or repositioning provides zero coverage.
4. **Return origin**: Responding ambulances always return to their dispatch node (the staging base from which they were dispatched).
5. **Fixed zone monitoring**: Each zone observer monitors arrivals in its assigned zone continuously, even while its associated ambulance is busy on a call (fixed infrastructure/sensor feed assumption).

At equal timestamps, the event priorities in code are: (1) finish response-return and reposition trips; (2) record scene arrivals; (3) close hourly learning bins and send/deliver rate messages; (4) expire unresolved calls at their deadline; (5) add incident arrivals; then (6) allocate feasible pending calls and reposition eligible idle units. Thus a scene arrival exactly at its call deadline is processed before expiration and counts as on time; a new arrival at the timestamp is created after deadlines and is allocated after the whole timestamp batch.

The global event loop is the environment implementation, not an operational centralized dispatcher for BID. It generates the common incident signal, advances the shared physical state, enforces deadlines, and delivers channel packets. BID agents privately estimate rates, calculate bids, and independently commit local minima. The environment records those decisions and their physical consequences. The B1/B2 selectors and B3 assignment are centralized baseline policies and must be described as such.

```text
build city and all-pairs travel times; generate exogenous tape from the scenario seed
initialize base positions, per-agent rate priors/state tables, queue, metrics, and RNG streams

while scheduled events remain:
    now = next event time; integrate coverage and busy time up to min(now, arrival_horizon)
    finish response-return and reposition trips
    mark first scene arrivals as served; record secondary duplicate arrivals without credit
    at each hourly boundary, update owner estimates and deliver rate packets
    expire unresolved calls whose deadline is now
    add calls arriving now; update only their direct-observer learner
    if now <= arrival_horizon:
        while any pending call has a feasible idle responder:
            choose oldest call (for B2q: highest criticality first; otherwise oldest arrival)
            evaluate B1/B2/B2q/B3 or local BID actions, according to policy
            for BID, apply each agent's delivered bid view and commit every local minimum
            record each commitment; add cost; schedule scene arrival and trip completion
            reposition the permitted remaining idle units (B3 only)
finalize per-seed service, expirations, exposures, utilization, messages, and costs
```

## 10. Metrics and experiment contract

The stored overall, median, 90th percentile, and `K >= 4` response times are conditional on a scene-arrival service event; they do not include expired calls (expired calls never have a response time of 0). For duplicate dispatches, the recorded response time is strictly the first scene arrival. Report response metrics alongside service and expired rates. Coverage is the integral of the share of true rate mass in zones reachable within `theta` from idle ambulance positions; it is a demand-weighted availability proxy, not a geographical or clinical coverage guarantee. Utilization is busy ambulance-minutes divided by fleet size times the arrival horizon; response-return and reposition periods count as busy. Message counts distinguish eligible directed packet attempts (`sent`), deliveries (`delivered`), and dropped packets (`dropped = sent - delivered`), broken down by message kind (`bid`, `status`, `rate`). In addition to run-level summaries in `raw_results.csv`, per-incident records are written to compressed `incident_outcomes.csv.gz` containing `(seed, policy, experiment, level, incident_id, criticality, arrival_time, deadline, response_time, responder_count, outcome)`. Demand RMSE is computed against true rates at hourly learning boundaries. Oracle RMSE is zero by construction; B1/B2/B2q do not use estimated rates for dispatch and B3 receives true rates, so their RMSE is a diagnostic, not a policy-performance measure.

Report raw metrics for all policies; report signed B3-relative gaps only for defined cost/loss measures. Estimate uncertainty by resampling scenario seeds; for matched policy contrasts, first calculate the per-seed difference and then bootstrap those differences. Calls within one tape are not treated as independent replicates. The original seven one-factor experiment families and parameter values live in versioned config files. The independent alpha/beta/gamma sensitivity extension has its own configuration and result directory.

Automated tests cover: shortest paths; Poisson-tape reproducibility; response/return timing; deadlines and queues; B1/B2 tie-breaking; B3 one-to-one assignment; full/radius/loss/no-message delivery; exactly-one full-communication winner; duplicate counts for disconnected local minima and no-message; misses from infeasibility/expiration; home/outside zone partition in `R_i` and `D_i`; rate learning with loss/stale updates; signed-gap direction and zero denominator; and deterministic end-to-end runs. The test command and latest outcome are recorded in `FINAL_AUDIT.md`.

## 11. Deliberate limitations

The simulator uses synthetic travel times, deterministic shortest paths, constant speed, a round-trip-to-origin response abstraction, no hospital capacity, no traffic, no message latency, and a fixed zone-observation partition. The common payoff is a transparent surrogate. B3 is heuristic, and the unilateral deviation check covers only named alternate rules. These limits are stated in the final report.
