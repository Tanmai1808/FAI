# Cooperative Ambulance Dispatch under Limited Communication and Unknown Demand

Multi-Agent Systems course project, IIT Gandhinagar.
Team: Lingala Hasini (24110186), Poladasu Tanmai Manjula (24110261), Reddyboina Triveni (24110295).

## Overview & Methods
Cooperative Dec-POMDP simulation of urban EMS fleet dispatch on a 5×5 grid. Evaluates decentralized market-inspired bidding (BID) against centralized and greedy baselines:
- **B1**: FIFO arrival queue, nearest idle ambulance ($\min \tau(x_i, \ell_e)$).
- **B2**: FIFO arrival queue, weighted nearest ($\min \alpha K_e \tau(x_i, \ell_e)$; mathematically identical to B1).
- **B2q**: Criticality-first queue priority ($(-K_e, t_e, \text{ID}_e)$), nearest idle ambulance.
- **B3**: Centralized Hungarian bipartite matching heuristic with greedy idle repositioning.
- **BID**: Decentralized bidding balancing travel delay, external coverage loss, and home station vulnerability across 4 communication regimes (full, radius-limited, lossy, none) with online EMA demand learning.

## Repository Structure
- `src/ambulance_dispatch/`: Core discrete-event simulator, policies, demand learning, metrics, runner.
- `configs/`: Baseline and experiment matrix JSON definitions (`default.json`, `experiment_matrix.json`).
- `tests/`: 54 deterministic unit and integration tests (`python -m unittest discover -s tests`).
- `tools/run_weight_sensitivity.py`: Independent one-factor $\alpha, \beta, \gamma$ weight sensitivity runner.
- `report/`: 8-page arXiv-style report (`main.tex`, `main.pdf`), asset builder, and plotting scripts.
- `scripts/run_final.sh`: One-command suite runner with fail-fast execution and clean-tree guard.

## Installation
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -e ".[dev]"
```

## Verified Commands
- **Unit Tests**: `python -m unittest discover -s tests -v`
- **Simulate single episode**: `ambulance-dispatch simulate --policy BID --communication full --seed 101 --horizon 600`
- **Experiment suite (pilot)**: `ambulance-dispatch experiments --seeds 2 --horizon 600 --output-dir results/pilot_test`
- **Weight sensitivity**: `python tools/run_weight_sensitivity.py --seed-count 2 --output results/pilot_weights --allow-dirty`
- **Build report assets**: `python report/build_report_assets.py results/final_30_seed --weight-sensitivity-dir results/final_30_seed/weight_sensitivity --output-dir report/generated`
- **Compile report**: `tectonic report/main.tex` (produces 8-page `report/main.pdf`)
- **Full one-command final run**: `SEEDS=30 bash scripts/run_final.sh`

## Configuration
Edit `configs/default.json` or pass CLI flags to configure scenario parameters:
- Ambulances ($N$): `--ambulances <int>` (default 5, sweep 3, 5, 7, 10).
- Demand rate ($\Lambda$): `--rate <float>` (default 5.0, sweep 2.5, 5.0, 10.0 calls/h) and pattern (`--pattern {uniform,hotspots,shifting}`).
- Communication: `--communication {full,radius-limited,lossy,none}`, radius $r \in \{2,4,6,8,12\}$ min, loss $p \in [0, 1]$.
- Demand learning: `--oracle-demand` flag (or EMA with `learning_eta: 0.25`, `learning_bin_minutes: 60.0`).
- Objective weights: `configs/default.json` keys `alpha` (1.0), `beta` (8.0), `gamma` (8.0), `rho` (120.0).

## Results & Reproducibility
Final outputs reside in `results/final_${SEEDS}_seed/` using paired scenario seeds $1000 \dots 1000+S-1$:
- Communication & Service: `results/final_30_seed/plots/exp4_communication_service_rate.png`
- Duplicate Dispatches: `results/final_30_seed/plots/exp4_communication_missed_dispatch_rate.png`
- Demand RMSE Convergence: `results/final_30_seed/plots/exp5_demand_knowledge_demand_rmse.png`
- Weight Trade-offs: `results/final_30_seed/weight_sensitivity/report_plots/exp8_weight_sensitivity_alpha_b3_cost_gap_relative.png`

Screenshots: `screenshots/simulator_run.png`, `screenshots/final_plots.png`.
After the final suite run, commit generated assets with: `git add -f results/final_30_seed && git commit -m "Results: 30-seed final run"` (excluding `*.csv.gz` via `.gitignore`).
