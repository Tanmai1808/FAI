# Implementation Review

## Components inspected

Reviewed every package module under `src/ambulance_dispatch/`, all five baseline test modules, both configs, all experiment CSVs/manifests/logs, the result validator, plot/table generators, and report source. The baseline run validator passes on the original result directory (verified through a temporary copy so the committed audit artifact was untouched).

## Simulator and event handling

- `City.grid` builds a connected weighted grid and precomputes shortest-path travel times. Zone IDs map to graph nodes. Coverage uses those same path times and the configured radius.
- `demand.py` simulates independent zone-wise Poisson processes with exponential inter-arrival times for each piecewise-constant interval, then sorts and stores one exogenous incident tape per scenario seed. Severity is sampled from the configured five-category distribution. Policies sharing a seed see the same incident tape and starting positions.
- Ambulances have idle, response-busy, and reposition-busy states. A responding unit's scene arrival is scheduled after `T`; it is unavailable through outbound travel, on-scene time, and return, for `2T+s`, and returns to its dispatch node. Repositioning consumes shortest-path travel time and makes the unit unavailable until its destination is reached. Intermediate route locations are not simulated.
- Equal-time priorities are trip completion, scene arrival, learning-bin close/message delivery, deadline expiry, incident arrival, then allocation/reposition after the timestamp batch. Therefore a scene arrival at its deadline is served; an unresolved call is expired at that timestamp. Event ordering was checked in `Simulator._schedule_initial_events`, `_process_event`, and `run`.
- Incidents with no eligible ambulance stay queued; feasibility includes queue wait plus travel and requires scene arrival by the remaining deadline. If a queue is infeasible, the allocator can skip to a younger feasible incident. Unresolved calls expire once. Calls assigned to multiple responders are marked allocated once, the first scene arrival resolves service, and extra arrivals do not earn service credit. Duplicate responders still consume their complete busy intervals.
- Arrivals stop at the configured horizon. Outstanding calls/deadlines/trips drain after the horizon; coverage and utilization are integrated only through the arrival horizon. This separates arrival horizon from result-finalization time.

## Policy and environment decentralization

The event loop is a centralized simulation engine. It creates the common incident tape, advances physical state, checks deadlines, and applies delivered messages. It does not globally rank BID agents and select one winner. Each BID agent computes a local score from its own belief and received bids; every local minimum commits. The engine records the resulting joint actions.

B1 and B2 are computed by a centralized selector over the feasible idle set. B3 is computed centrally using global ambulance state and true demand. B1/B2 are deliberately simple centralized baselines and are unaffected by the BID channel. B3 is a centralized heuristic comparator, not an optimum. The report must not characterize these three baselines as decentralized or information-matched with BID.

## Communication

`CommunicationChannel.send` ignores self and none-regime packets, applies shortest-path radius to reported staging nodes, increments `sent` only for a reachable directed packet attempt, then independently drops lossy packets with probability `p`; `delivered` counts successful packets. Delivery latency is zero. BID emits bid messages, status-change messages, and hourly rate messages. None sends no peer packets. Radius-limited links can fragment views; independent directed packet loss can produce asymmetric views. A disconnected view can produce several local minima and duplicate dispatches.

Every ambulance receives the incident task signal independently of the peer channel, matching the proposal's `e_t` in each observation. Therefore “none” means no ambulance-to-ambulance packets, not total disconnection or failed emergency notification. Since a local minimum always exists among feasible bidders, communication cannot immediately cause a zero-winner auction. Misses arise when no feasible unit arrives by deadline, including indirect capacity loss from duplicates.

## Demand learning and information boundary

Each zone has one fixed owner chosen by nearest home base and ambulance-ID tie-break. Owners count directly observed calls even when their ambulance is busy. At hourly boundaries, the discounted estimate uses only that bin's counts and the previous estimate. Recipients install owner messages once per `(owner, zone, bin)`; dropped or out-of-radius messages leave prior values in place. The known true rate vector is used by the environment to assess RMSE and cost, but BID receives it only when the explicit oracle flag is set. B3 uses true rates by definition.

One reporting limitation remains: oracle-mode BID still runs the learner and sends rate-update packets, even though its bids already use true rates. Its message count is the behavior of that configured implementation and includes those redundant updates; do not interpret oracle-vs-learned message counts as the minimum communication required by each information condition. Oracle RMSE is forced to zero by construction. B1/B2 do not use learned rates for their dispatch rule; their learner RMSE is diagnostic only.

## Randomness and consistency across policies

Incident tapes use a stable seeded generator; channel loss uses a deterministic integer-mixed child seed. The same seed reuses the same arrivals and initial positions across methods. Message delivery can differ by policy because packet attempts differ, but the environment does not regenerate demand based on policy. Cost evaluation uses true rates consistently, while BID action selection uses local estimates unless oracle is enabled.

## Tests and uncovered limits

The baseline suite covers graph shortest paths and weighted coverage; Poisson seed reproducibility and rate shifts; B1/B2 ordering and tie rules; B3 assignment; home/outside coverage-cost partition; full/radius/loss/none packet behavior; rate ownership and deduplication; queueing, deadlines, duplicate responders, full-communication winner behavior, no-communication local minima, deterministic episodes, and deviation reproducibility. The final suite adds tests for independent alpha/beta/gamma design and a small real weight-run output/manifest.

The tests are deterministic unit/integration checks, not a proof of the model or external validity. No route geometry, hospitals, traffic, heterogeneous units, delayed packets, stochastic travel, or real dispatch data are simulated. `mean_response_minutes` is conditional on served calls and must be labeled accordingly.

