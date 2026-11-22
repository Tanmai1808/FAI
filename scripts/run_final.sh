#!/usr/bin/env bash
#
# scripts/run_final.sh - One-command reproducible runner for the final experiment suite.
#
# Usage:
#   SEEDS=30 bash scripts/run_final.sh
#

set -euo pipefail

SEEDS="${SEEDS:-30}"
SEED_START=1000
OUTPUT_DIR="results/final_${SEEDS}_seed"

echo "================================================================="
echo "Ambulance Dispatch MAS - Final Run Pipeline"
echo "Seeds:        ${SEEDS} (start=${SEED_START})"
echo "Output:       ${OUTPUT_DIR}"
echo "================================================================="

# Determine python command
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

if command -v ambulance-dispatch >/dev/null 2>&1; then
  DISPATCH_CMD="ambulance-dispatch"
else
  DISPATCH_CMD="${PYTHON} -m ambulance_dispatch.cli"
fi

# Step 1: Pre-flight clean tree check (ONCE at the start)
echo "[1/6] Checking git working tree cleanliness..."
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: Working tree is dirty. Please commit or stash changes before running." >&2
  git status --short >&2
  exit 1
fi
echo "Working tree is clean."

# Step 2: Run test suite
echo "[2/6] Running automated test suite..."
${PYTHON} -m unittest discover -s tests -v

# Step 3: Run full proposal experiments suite (incl. exp4b, exp4c, exp5b)
echo "[3/6] Running full experiment suite (10 families, ${SEEDS} seeds)..."
${DISPATCH_CMD} experiments \
  --profile full \
  --seeds "${SEEDS}" \
  --seed-start "${SEED_START}" \
  --experiment exp1 \
  --experiment exp2 \
  --experiment exp3 \
  --experiment exp4 \
  --experiment exp4b \
  --experiment exp4c \
  --experiment exp5 \
  --experiment exp5b \
  --experiment exp6 \
  --experiment exp7 \
  --output-dir "${OUTPUT_DIR}"

# Step 4: Run weight sensitivity suite
echo "[4/6] Running weight sensitivity suite..."
${PYTHON} tools/run_weight_sensitivity.py \
  --seed-start "${SEED_START}" \
  --seed-count "${SEEDS}" \
  --output "${OUTPUT_DIR}/weight_sensitivity"

# Step 5: Generate plots and report assets
echo "[5/6] Generating high-resolution report plots and LaTeX tables..."
${PYTHON} report/plot_results.py "${OUTPUT_DIR}"
${PYTHON} report/build_report_assets.py "${OUTPUT_DIR}" \
  --weight-sensitivity-dir "${OUTPUT_DIR}/weight_sensitivity" \
  --output-dir report/generated

# Step 6: Validate results and build report PDF
echo "[6/6] Auditing and validating all experimental results..."
${PYTHON} report/validate_results.py "${OUTPUT_DIR}" \
  --weight-sensitivity-dir "${OUTPUT_DIR}/weight_sensitivity"

if command -v tectonic >/dev/null 2>&1; then
  echo "Compiling report with tectonic..."
  tectonic report/main.tex
fi

echo "================================================================="
echo "Final run complete! Assets generated in report/generated and ${OUTPUT_DIR}."
echo "================================================================="
