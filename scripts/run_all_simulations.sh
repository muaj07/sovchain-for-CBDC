#!/usr/bin/env bash
#
# SovChain Simulation Suite
# Reproduces Tables 22, 23, 25, 28, 31, 32 from the manuscript
#
# Usage:
#   ./scripts/run_all_simulations.sh [--quick]
#
# Options:
#   --quick    Use n=10000 samples (faster, less accurate)
#
# Requirements:
#   - Python 3.10+
#   - NumPy, SciPy, tabulate (pip install -r requirements.txt)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${PROJECT_DIR}/results"

# Default parameters from paper
SAMPLES=100000
SEED=42

# Parse arguments
if [[ "${1:-}" == "--quick" ]]; then
    SAMPLES=10000
    echo "Quick mode: using n=${SAMPLES} samples"
fi

# Create output directory
mkdir -p "${OUTPUT_DIR}"

echo "============================================================"
echo "SovChain Simulation Suite"
echo "============================================================"
echo ""
echo "Configuration:"
echo "  Project directory: ${PROJECT_DIR}"
echo "  Output directory:  ${OUTPUT_DIR}"
echo "  Sample size (n):   ${SAMPLES}"
echo "  Random seed:       ${SEED}"
echo "  Timestamp:         $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
echo ""

# Verify Python environment
echo "Checking Python environment..."
cd "${PROJECT_DIR}"

if ! python3 -c "import numpy; import scipy" 2>/dev/null; then
    echo "ERROR: Missing dependencies. Install with:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
NUMPY_VERSION=$(python3 -c "import numpy; print(numpy.__version__)")
echo "  Python:  ${PYTHON_VERSION}"
echo "  NumPy:   ${NUMPY_VERSION}"
echo ""

# Run simulations
echo "============================================================"
echo "1. End-to-End Latency Simulation (Section 8.3 / Table 22)"
echo "============================================================"
python3 -m simulations.latency_simulation \
    --samples "${SAMPLES}" \
    --seed "${SEED}" \
    2>&1 | tee "${OUTPUT_DIR}/latency_results.txt"
echo ""

echo "============================================================"
echo "2. Execution Cost Model (Section 8.4 / Table 23)"
echo "============================================================"
python3 -m simulations.execution_cost_model \
    --samples "${SAMPLES}" \
    --seed "${SEED}" \
    2>&1 | tee "${OUTPUT_DIR}/execution_cost_results.txt"
echo ""

echo "============================================================"
echo "3. DoS Resilience Simulation (Section 8.5 / Table 25)"
echo "============================================================"
python3 -m simulations.dos_resilience \
    --duration 1000 \
    --seed "${SEED}" \
    2>&1 | tee "${OUTPUT_DIR}/dos_results.txt"
echo ""

echo "============================================================"
echo "4. Economic Model (Section 9 / Tables 28, 31, 32)"
echo "============================================================"
python3 -m simulations.economic_model \
    --verbose \
    2>&1 | tee "${OUTPUT_DIR}/economic_results.txt"
echo ""

# Summary
echo "============================================================"
echo "Summary"
echo "============================================================"
echo ""
echo "All simulations completed successfully."
echo ""
echo "Output files:"
ls -la "${OUTPUT_DIR}/"
echo ""
echo "Verification:"
echo "  Compare results against paper values in the 'Verification'"
echo "  section of each output file. Expected tolerances:"
echo "    - Latency:    ±5%  (Monte Carlo variance)"
echo "    - Exec cost:  ±10% (Parameter uncertainty)"
echo "    - DoS:        ±15% (Simplified model)"
echo "    - Economic:   ±1%  (Deterministic)"
echo ""
echo "For detailed methodology, see docs/SIMULATION_METHODOLOGY.md"
