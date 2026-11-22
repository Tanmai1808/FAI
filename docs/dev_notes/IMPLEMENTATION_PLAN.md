# Implementation Plan

## Project

**The Price of Decentralization in Ambulance Dispatch: Cooperative Coordination under Limited Communication and Unknown Demand**

**Status:** approved and implemented; local final audit complete. The simulator, seven proposal experiment families, independent coefficient-sensitivity extension, automated tests, report pipeline, README, and eight-page report are present. `MODEL_DESIGN.md` is the frozen definition of the implemented model. External submission items and provenance limitations are documented in `FINAL_ISSUES.md`; the repository has not been pushed.

## Source hierarchy and requirements

The six-page project-review proposal is the research foundation: preserve its problem framing, cooperative Markov-game setup, bidding idea, baselines, seven experiments, metrics, references, and assigned contributions. The instructor feedback and the latest submission guidelines take precedence wherever they refine it.

The implementation and final submission must satisfy all of these:

- The final report is **exactly eight pages** and completes the submitted project-review report rather than becoming an unrelated paper.
- It has detailed **Methodology**, evidence-based **Results**, and a **Contribution** section listing all three members, their original assignments, and whether each assignment was fulfilled.
- The repository has a README covering the project, installation, execution, experiments, and results; the submission includes a working repository link and genuine screenshots of actual results.
- Every reported number and figure is traceable to submitted code and data. No result, screenshot, completed contribution, or repository URL will be invented.
- Apply the instructor's corrections: B3 is a heuristic benchmark, so no theorem that empirical PoD is nonnegative; use consistent beta notation; make the bid terms match the team objective; and use an arXiv-compatible LaTeX manuscript source.

The proposal and feedback identify the three members and their originally assigned tasks. The report lists those assignments and marks individual completion/authorship unverified from repository artifacts rather than assuming it from the proposal.

## Implemented software architecture

The approved architecture is implemented in these modules; the project structure below reflects the repository rather than the initial sketch.

```text
configs/                         default, seven-family, and weight-sensitivity settings
src/ambulance_dispatch/
  graph.py, model.py              weighted city and ambulance/call state
  demand.py, learning.py          Poisson tapes and discounted zone rates
  communication.py                directed radius/loss channels and counters
  simulator.py                    event queue, dispatch, deadlines, movement, outcomes
  policies/baselines.py           B1 and B2
  policies/centralized.py         B3 Hungarian/greedy heuristic
  policies/bidding.py, costs.py   BID score and shared surrogate terms
  metrics.py, experiments.py      signed B3 gaps, paired run suite, bootstrap
  cli.py, plotting.py              command-line runs and plot output
tools/                             independent sensitivity, validation, log recovery
tests/                             deterministic unit/integration tests
report/                            arXiv-style LaTeX source, CSV-backed tables, PDF
results/                           raw CSVs, manifests, logs, plots, screenshots
docs/reference/                    preserved proposal and original guidance
AUDIT/                              baseline and implementation evidence
```

The simulator centrally advances events but BID agents locally score calls and all received-view minima commit. B1/B2 and B3 are central baselines. Every policy in a seed shares the public task signal and exogenous call tape; the peer channel carries bids, status, and rate information only. Oracle rates are explicit. Report tables and plots are regenerated from CSV outputs rather than hand-entered values.

## Mathematical decisions settled in `MODEL_DESIGN.md`

The choices below were implemented after approval and are the definitions used by code, configs, experiments, and report. `MODEL_DESIGN.md` contains the full equations, pseudocode, units, event priorities, and assumptions.

1. **Common objective and bid consistency:** response, disjoint non-home coverage-loss demand, home-zone demand-away, and expiration terms form one shared cost. BID uses the same `alpha`, `beta`, and `gamma` terms with local rates and positions; it is explicitly approximate. No `beta'` notation is used.
2. **Empirical comparator:** B3 is a centralized heuristic, not a proven optimum. We report signed per-seed absolute and relative empirical gaps; negative gaps are valid. The relative ratio is undefined at zero B3 cost.
3. **Call visibility and failures:** all policies receive the public task signal in the proposal. Communication controls peer packets only. Agents commit every local minimum; duplicates consume full busy time. Misses are calls expired before scene service, including possible indirect capacity loss from duplicates.
4. **Movement:** responders travel to the scene, spend on-scene time, return to their dispatch node, and then become idle. Busy duration is `2T+s`. Repositioning consumes shortest-path travel and availability; event priorities resolve deadline ties.
5. **City and coverage:** a 5×5 connected weighted grid uses two-minute edges. Coverage is true-demand mass reachable from an idle ambulance within `theta`, integrated over the arrival horizon; it is an availability proxy.
6. **Demand and information:** zone-wise Poisson tapes are paired across policies. Nearest-home-base zone owners observe arrivals while busy, update discounted hourly rates, and transmit estimates. Only B3 and explicit oracle BID use true rates for decisions.
7. **B3:** global Hungarian assignment with dummy choices and greedy coverage-aware repositioning; it uses shared pre-allocation costs and remains a heuristic.
8. **Deviation:** for each agent and seed, one full-episode change to the time-only nearest score is compared with all-BID on the same call tape. The restricted maximum is not an equilibrium proof.

## Staged implementation

### Stage 1 — Freeze model and repository contract [COMPLETE]

Resolve the items above; write the equations, state/observation/action definitions, event ordering, tie-breaking, communication semantics, and metric definitions into a short model specification. Create the package/config skeleton and preserve the supplied source documents unchanged under `docs/reference/`.

**Gate:** a reviewer can determine exactly what each policy knows and what a single simulation step does.

### Stage 2 — Simulator and demand generation [COMPLETE]

Implement the synthetic city, shortest paths, zone-wise Poisson event generation, criticality/deadlines, queues, ambulance status/location, service/busy behavior, and incident tape generation.

**Gate:** fixed seeds reproduce identical city and event tapes; state transitions and deadline handling are covered by deterministic tests.

### Stage 3 — Policies and communication [COMPLETE]

Implement B1, B2, centralized heuristic B3, decentralized bids, winner/tie protocol, four communication regimes, online demand learning, and coverage-aware repositioning. Keep oracle information behind a separate explicit configuration flag.

**Gate:** policy permissions are testable; one selected responder under full communication; duplicate/missed cases arise only under the documented protocol; B3 is described in code and report as heuristic.

### Stage 4 — Metrics and automated tests [COMPLETE; audit suite rerun]

Implement response times (overall and `K >= 4`), service before deadline, demand-weighted coverage over time, utilization, message counts, duplicate/missed rates, demand-estimation error, team cost, signed B3-relative gaps, and the restricted unilateral-deviation analysis. Add deterministic tests for policy choices, communication, learning causality, assignments, metrics, CSV schemas, and PoD sign/zero-denominator behavior.

**Gate:** small hand-constructed scenarios have known expected outputs; test suite passes before full experiments.

### Stage 5 — Seven experiment runs [COMPLETE]

Use one-factor-at-a-time sweeps around a declared default rather than an uncontrolled full Cartesian product:

1. Ambulances: `3, 5, 7, 10`.
2. Total demand: low, medium, high.
3. Demand pattern: uniform, fixed hotspots, shifting hotspots.
4. Communication: full, radius-limited, lossy, none.
5. Knowledge: oracle versus learned; cross this with communication only as needed to isolate their interaction.
6. Criticality mix: low-heavy, balanced, high-heavy.
7. Weight trade-off: the proposal's joint sweep scales `beta` and `gamma` together at fixed `alpha=1`; a separate audit extension independently varies all three coefficients and is reported separately.

Compare B1/B2/B3 and the relevant bidding variants using paired scenario seeds. Initial budget target: about 20 seeds and 500 calls per seed/configuration, then adjust only after a pilot timing run. Store per-run CSVs and use paired bootstrap 95% confidence intervals across seeds. Do not choose weights on the final evaluation seeds. Report all seven experiments, including null or unfavorable findings.

The seven proposal families ran with 20 seeds (1000–1019), four policies, and 1,760 policy episodes. A separate approved audit extension varied alpha, beta, and gamma independently at nine levels for another 720 episodes, with matched seeds and 2,000 paired-seed bootstrap resamples. The corrected run is `results/improvements_20261121/weight_sensitivity/`; its first unmatched comparison attempt is preserved and explicitly marked in README/AUDIT.

### Stage 6 — Results and reproducibility artifacts [COMPLETE WITH ONE METADATA LIMITATION]

The configured experiment commands and CSV/plot generation commands are in README.md. The original seven-family manifest records seeds, config, environment, and source hashes, but `git_revision` is null and communication defaults were omitted from its original run record; this history is not rewritten. The separate sensitivity manifest records its commit and channel settings. The original run's exact source defaults are documented in an audit addendum. Matched tapes and deterministic child streams are used. A genuine desktop screenshot of the real result plot is retained with the source plot.

### Stage 7 — Eight-page report and local delivery [COMPLETE; external submission items disclosed]

The project-review report is complete in the included community arXiv preprint style, retaining the proposal's motivation, formulation, and relevant references while adding detailed Methodology, actual Results, Limitations, and the three original contribution assignments with personal fulfillment marked unverified. CSVs, plots, code, configs, README, genuine current-results screenshot, and eight-page A4 PDF are present and audited. The local branch remains unpublished and no remote is configured. The final evidence, impact matrix, screenshot provenance, claim map, and outstanding external items are recorded in `FINAL_AUDIT.md`, `CHANGE_IMPACT.md`, `AUDIT/REPORT_CLAIMS.md`, `AUDIT/SCREENSHOT_REPLACEMENT.md`, and `FINAL_ISSUES.md`. Do not create/push a GitHub repository until the user explicitly requests publication.

**Final gates completed locally:** compile and visually inspect the PDF; verify exactly eight pages; map every numerical claim/table/plot to CSVs and generating code; rerun tests and both result validators; verify README paths; confirm contribution uncertainty and repository status are stated factually. A clean-clone reproduction was not possible because the repository has no remote/public URL; this and the remaining confirmations are listed in `FINAL_ISSUES.md`.

## Runtime and computational budget

A 5×5 city and fleets up to 10 keep the shortest-path and assignment computations small. Recorded baseline runtime is 584.463 seconds summed across the 1,760 original episodes; corrected sensitivity runtime is recorded in its manifest. The total is an episode-time sum, not wall-clock time. Use the actual manifest rather than the earlier planning estimate for runtime claims. The implementation uses the Python standard library for simulation, Pillow for report plots/screenshots, and an in-repository Hungarian solver; it does not require NumPy, SciPy, or Matplotlib.

## Reproducibility and submission checks

- Fixed master seed plus recorded child-seed derivation; identical exogenous arrival streams across policies within each paired seed.
- Machine-readable configuration and manifest for each batch; no hidden manual edits to result tables.
- CSV records retain policy, scenario, seed, metrics, and configuration identifiers. Plot/table generation reads those records directly.
- Automated checks validate schemas, aggregates, confidence intervals, and the denominator/interpretation of every benchmark-relative gap.
- README documents environment setup, test command, fast smoke run, full seven-experiment run, result regeneration, and artifact locations.
- Report values are generated from the same CSV summaries used by the plots. A final audit script or checklist maps each report claim to a CSV column and generating command.
- Preserve the original proposal, instructor feedback, and guidelines as reference inputs; keep the final source PDF and LaTeX source together.
- The official arXiv TeX guidance requires authors to verify the processed PDF and include required source/figure files. The local source and figures compile with the included community `arxiv.sty`; it is not presented as a universal official arXiv class: [arXiv TeX submission guidance](https://info.arxiv.org/help/submit_tex.html).

The plan was approved before implementation. Current completion and remaining external-verification items are recorded in `FINAL_AUDIT.md` and `FINAL_ISSUES.md`; do not treat this historical plan as a substitute for that final evidence.
