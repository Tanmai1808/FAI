# Cooperative Ambulance Dispatch under Limited Communication and Unknown Demand

Multi-Agent Systems course project, IIT Gandhinagar.

**Team:** Lingala Hasini (24110186) · Poladasu Tanmai Manjula (24110261) · Reddyboina Triveni (24110295)

## Overview

Discrete-event simulation of urban EMS fleet dispatch on a 5×5 Manhattan grid. Five dispatch policies are evaluated under four communication regimes, with optional online demand learning.

**Policies:**
| Policy | Description |
|--------|-------------|
| **B1** | FIFO queue; nearest idle ambulance (min travel time) |
| **B2** | FIFO queue; criticality-weighted nearest (mathematically identical to B1) |
| **B2q** | Criticality-first queue; nearest idle ambulance |
| **B3** | Centralized Hungarian matching heuristic with greedy repositioning |
| **BID** | Decentralized market-based bidding balancing response delay, coverage loss, and home-station vulnerability |

**Communication regimes:** full · radius-limited (r ∈ {2,4,6,8,12} min) · lossy (p ∈ {0,0.1,0.25,0.5,0.75,1}) · none

**Online learning:** EMA demand-rate estimation (η=0.25, hourly bins). Oracle condition uses true rates.

## Repository Structure

```
src/ambulance_dispatch/   Core simulator, policies, demand learning, metrics, CLI
configs/                  default.json, experiment_matrix.json
tests/                    54 unit and integration tests
tools/run_weight_sensitivity.py   One-factor α,β,γ sensitivity runner
report/                   8-page arXiv-style report (main.tex, main.pdf), asset builder, plots
scripts/run_final.sh      One-command full experiment suite runner
results/final_30_seed/    Final 30-seed results (pre-computed; DO NOT rerun)
screenshots/              Generated result figures for reference
```

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -e ".[dev]"
```

## Commands

```bash
# Unit tests
python -m unittest discover -s tests -v

# Single simulation episode
ambulance-dispatch simulate --policy BID --communication full --seed 101 --horizon 600

# Small pilot experiment (2 seeds)
ambulance-dispatch experiments --seeds 2 --horizon 600 --output-dir results/pilot_test

# Weight sensitivity (2-seed pilot)
python tools/run_weight_sensitivity.py --seed-count 2 --output results/pilot_weights --allow-dirty

# Build report assets from existing 30-seed results
python report/build_report_assets.py results/final_30_seed \
  --weight-sensitivity-dir results/final_30_seed/weight_sensitivity \
  --output-dir report/generated

# Compile the report (requires tectonic)
tectonic report/main.tex   # produces report/main.pdf (8 pages)
```

## Configuration

Edit `configs/default.json` or pass CLI flags:
- Ambulances: `--ambulances <N>` (default 5)
- Demand rate: `--rate <λ>` (default 5.0 calls/h), pattern: `--pattern {uniform,hotspots,shifting}`
- Communication: `--communication {full,radius-limited,lossy,none}`, `--comm-radius`, `--loss-prob`
- Weights: `alpha` (1.0), `beta` (8.0), `gamma` (8.0), `rho` (120.0) in `configs/default.json`

## Final Results

The 30-seed final results are already computed in `results/final_30_seed/`. The compiled 8-page report is at `report/main.pdf`.

Do **not** rerun `scripts/run_final.sh` unless you need to reproduce results from scratch (requires ~30-seed compute time).

Key generated figures:
- `results/final_30_seed/report_plots/exp4_communication_service_rate.png` — BID service across communication regimes
- `results/final_30_seed/report_plots/exp4b_communication_radius_service_rate.png` — radius sweep
- `results/final_30_seed/report_plots/exp1_ambulance_count_service_rate.png` — fleet size sweep
- `results/final_30_seed/report_plots/cost_breakdown_stacked_n7_n10.png` — cost decomposition

Screenshots (generated result plots):
- `screenshots/communication_sweep.png` — radius sweep service rate
- `screenshots/policy_comparison.png` — fleet size policy comparison

> **Note:** This project is CLI-only. Screenshots of terminal execution and the compiled PDF must be captured manually.
> To capture a terminal screenshot: run `ambulance-dispatch simulate --policy BID --communication full --seed 101 --horizon 600` and screenshot your terminal.
> To capture the PDF first page: open `report/main.pdf` in any viewer and screenshot page 1.
