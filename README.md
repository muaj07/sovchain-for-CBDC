# SovChain: Simulation and ZKP Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Rust 1.70+](https://img.shields.io/badge/rust-1.70+-orange.svg)](https://www.rust-lang.org/)

Research artifact repository for our paper on sovereign CBDC blockchain architecture:

> **A Hybrid Permissioned Blockchain Architecture for Sovereign Central Bank Digital Currency**

This repository includes all source code needed to reproduce the simulation results and ZKP implementations from the paper.

---

## Table of Contents

1. [Repository Structure](#repository-structure)
2. [System Requirements](#system-requirements)
3. [Installation](#installation)
4. [Reproducing Paper Results](#reproducing-paper-results)
5. [Module Documentation](#module-documentation)
6. [Verification Checklist](#verification-checklist)
7. [Citation](#citation)
8. [License](#license)

---

## Repository Structure

```
sovchain-artifacts/
├── simulations/                 # Python Monte Carlo simulations
│   ├── config.py                # Parameters from Table 11
│   ├── latency_simulation.py    # Section 8.3, Table 22
│   ├── execution_cost_model.py  # Section 8.4, Table 23
│   ├── dos_resilience.py        # Section 8.5, Table 25
│   └── economic_model.py        # Section 9, Tables 28, 31, 32
│
├── zkp/                         # Zero-Knowledge Proof framework
│   ├── circuits/                # Circom 2.1 circuit definitions
│   │   ├── mint_circuit.circom  # Main minting circuit (~50k constraints)
│   │   ├── pedersen.circom      # Pedersen commitment gadget
│   │   └── range_proof.circom   # 64-bit range proof gadget
│   ├── src/                     # Rust prover/verifier (arkworks)
│   │   ├── lib.rs
│   │   ├── prover.rs
│   │   └── verifier.rs
│   └── Cargo.toml
│
├── move-contracts/              # Sui Move smart contracts
│   ├── sources/
│   │   ├── governance.move      # Governance layer (Section 4)
│   │   ├── cbdc.move            # CBDC token module
│   │   ├── compliance.move      # Compliance enforcement (Section 6)
│   │   └── mint.move            # Confidential minting (Section 5)
│   └── Move.toml
│
├── docs/                        # Extended documentation
│   ├── SIMULATION_METHODOLOGY.md
│   ├── ZKP_SPECIFICATION.md
│   └── CEREMONY_GUIDE.md
│
├── scripts/
│   └── run_all_simulations.sh   # Batch execution script
│
├── requirements.txt             # Python dependencies
├── LICENSE
└── README.md
```

---

## System Requirements

### Minimum Hardware
- CPU: 4 cores (8 recommended for ZKP compilation)
- RAM: 8 GB (16 GB recommended)
- Storage: 2 GB free space

### Software Dependencies

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.10+ | Simulations |
| NumPy | 1.24+ | Numerical computing |
| SciPy | 1.10+ | Statistical distributions |
| Rust | 1.70+ | ZKP prover/verifier |
| Circom | 2.1+ | Circuit compilation |
| snarkjs | 0.7+ | Trusted setup and proving |
| Sui CLI | 1.20+ | Move contract verification |

### Tested Platforms
- Ubuntu 22.04 LTS (primary)
- macOS 13+ (Ventura)
- Windows 11 with WSL2

---

## Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/muaj07/sovchain-for-CBDC.git
cd sovchain-for-CBDC
```

### Step 2: Python Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Quick check
python -c "import numpy; import scipy; print('All set!')"
```

### Step 3: Rust Toolchain (for ZKP components)

```bash
# Install Rust (if not present)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Build ZKP library
cd zkp
cargo build --release
cd ..
```

### Step 4: Circom Installation (for circuit compilation)

```bash
# Install Circom
git clone https://github.com/iden3/circom.git
cd circom
cargo build --release
sudo cp target/release/circom /usr/local/bin/

# Install snarkjs
npm install -g snarkjs

# Verify
circom --version
snarkjs --version
cd ..
```

### Step 5: Sui CLI (for Move contracts)

```bash
# Install Sui CLI
cargo install --locked --git https://github.com/MystenLabs/sui.git --branch mainnet-v1.20.0 sui

# Verify
sui --version
```

---

## Reproducing Paper Results

### Quick Start (All Simulations)

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Run all simulations with paper parameters
./scripts/run_all_simulations.sh
```

Output files are generated in `results/` directory.

### Individual Simulation Commands

#### Table 22: End-to-End Latency Breakdown (Section 8.3)

```bash
python -m simulations.latency_simulation --samples 100000 --seed 42
```

**Expected Output:**
```
Table 22: End-to-End Confirmation Latency Breakdown (ms)
======================================================================
Component              Baseline p50  p95   p99   Byzantine p50  p95   p99
─────────────────────  ────────────────────────  ─────────────────────────
Client → validator     24            62    92    24             62    93
Mempool/batching       38            61    64    41             71    91
Consensus ordering     287           323   348   333            409   435
Move execution         3             4     5     3              4     5
Acknowledgment         19            45    63    19             44    62
─────────────────────  ────────────────────────  ─────────────────────────
**Total**              371           495   572   420            590   686
```

#### Table 23: Execution Cost Overhead (Section 8.4)

```bash
python -m simulations.execution_cost_model --samples 100000 --seed 42
```

**Expected Output:**
```
Table 23: Simulated Execution Costs for Compliance and Privacy Paths
=========================================================================
Transaction Path            Mean (ms)  p99 (ms)  Overhead  Notes
─────────────────────────────────────────────────────────────────────────
Retail transfer (baseline)  2.70       3.93      1.00×     No compliance
Transfer + compliance       3.28       4.54      1.21×     Registry + limits
Confidential mint           5.47       6.90      2.03×     FROST + Groth16
```

#### Table 25: DoS Resilience (Section 8.5)

```bash
python -m simulations.dos_resilience --duration 1000 --seed 42
```

**Expected Output:**
```
Table 25: DoS Mitigation Under Simulated Attack (Model-Based)
======================================================================
Scenario                   Offered Attack TPS  Legitimate p99  Drop Rate
──────────────────────────────────────────────────────────────────────
Baseline (no attack)       0                   572ms           0%
Moderate spam (50k/s)      50,000              645ms           0%
Heavy spam (200k/s)        200,000             890ms           12%
Sustained flood (500k/s)   500,000             1420ms          45%
```

#### Tables 28, 31, 32: Economic Model (Section 9)

```bash
python -m simulations.economic_model --verbose
```

**Expected Output (excerpt):**
```
Table 28: Baseline Fee Revenue Projection (FY25 Workload)
Total fee revenue: PKR 7.381B (≈USD 26.4M)

Table 31: Stake Participation Scenarios
Early (0.1% of M2):    Base APY = 12.91%
Moderate (0.5% of M2): Base APY = 2.58%
Mature (1.0% of M2):   Base APY = 1.29%

Institution-Only Staking (Early Phase):
  Per-validator reward: PKR 196.83M/year
```

---

### ZKP Circuit Compilation

#### Compile Minting Circuit

```bash
cd zkp/circuits

# Compile circuit to R1CS
circom mint_circuit.circom --r1cs --wasm --sym -o build/

# View constraint count (should be ~50,000)
snarkjs r1cs info build/mint_circuit.r1cs
```

**Expected Output:**
```
[INFO]  snarkJS: Curve: bn-128
[INFO]  snarkJS: # of Wires: 50847
[INFO]  snarkJS: # of Constraints: 50000
[INFO]  snarkJS: # of Private Inputs: 4
[INFO]  snarkJS: # of Public Inputs: 6
```

#### Generate Test Proof (Development Only)

```bash
# Powers of tau ceremony (use existing ptau for production)
snarkjs powersoftau new bn128 16 pot16_0000.ptau
snarkjs powersoftau contribute pot16_0000.ptau pot16_0001.ptau --name="Dev contribution"
snarkjs powersoftau prepare phase2 pot16_0001.ptau pot16_final.ptau

# Circuit-specific setup
snarkjs groth16 setup build/mint_circuit.r1cs pot16_final.ptau mint_0000.zkey
snarkjs zkey contribute mint_0000.zkey mint_0001.zkey --name="Dev contribution"
snarkjs zkey export verificationkey mint_0001.zkey verification_key.json

# Generate and verify test proof
snarkjs groth16 prove mint_0001.zkey build/mint_circuit_js/mint_circuit.wasm input.json proof.json public.json
snarkjs groth16 verify verification_key.json public.json proof.json
```

---

### Move Contract Verification

```bash
cd move-contracts

# Build contracts
sui move build

# Run unit tests
sui move test

# Formal verification with Move Prover
sui move prove
```

**Expected Output:**
```
INCLUDING DEPENDENCY Sui
INCLUDING DEPENDENCY MoveStdlib
BUILDING SovChain
Running Move unit tests
[ PASS    ] sovchain::governance::test_threshold
[ PASS    ] sovchain::compliance::test_tier_limits
[ PASS    ] sovchain::cbdc::test_mint_burn
Test result: OK. Total tests: 3; passed: 3; failed: 0
```

---

## Module Documentation

### Simulation Parameters (Table 11)

All parameters are defined in `simulations/config.py`:

| Parameter | Symbol | Value | Reference |
|-----------|--------|-------|-----------|
| Validator count | n_V | 30 | Section 4.4 |
| Byzantine threshold | f | < n_V/3 | BFT requirement |
| Epoch duration | T_epoch | 86,400s | Section 4.3 |
| Block time target | τ | 500ms | Section 8.3 |
| Message delay bound | Δ | 500ms | Post-GST assumption |

### Network Latency Distributions (Section 8.3)

| Component | Distribution | Parameters | Median |
|-----------|--------------|------------|--------|
| Client→Validator | LogNormal | μ_ln=3.33, σ_ln=0.56 | 28ms |
| Inter-Validator | LogNormal | μ_ln=3.95, σ_ln=0.45 | 52ms |

### ZKP Circuit Constraints (Table 15)

| Component | Constraints | Percentage |
|-----------|-------------|------------|
| Pedersen commitment | 12,400 | 25% |
| Range proof (64-bit) | 18,200 | 36% |
| Policy bound check | 2,100 | 4% |
| SHA-256 (×2) | 17,000 | 34% |
| Miscellaneous | 300 | 1% |
| **Total** | **50,000** | **100%** |

---

## Verification Checklist

Use this checklist to verify reproduction of paper results:

| Table | Metric | Expected | Tolerance | Command |
|-------|--------|----------|-----------|---------|
| 22 | Baseline p50 | 371ms | ±5% | `latency_simulation.py` |
| 22 | Baseline p99 | 572ms | ±5% | `latency_simulation.py` |
| 22 | Byzantine p99 | 686ms | ±5% | `latency_simulation.py` |
| 23 | Baseline mean | 2.70ms | ±10% | `execution_cost_model.py` |
| 23 | Compliance overhead | 1.21× | ±10% | `execution_cost_model.py` |
| 23 | Mint overhead | 2.03× | ±10% | `execution_cost_model.py` |
| 25 | Heavy spam p99 | 890ms | ±15% | `dos_resilience.py` |
| 28 | Total fees | PKR 7.381B | ±1% | `economic_model.py` |
| 31 | Early APY | 12.91% | ±1% | `economic_model.py` |
| 31 | Validator reward | PKR 196.83M | ±1% | `economic_model.py` |
| 15 | Circuit constraints | 50,000 | exact | `circom --r1cs` |

Tolerances account for Monte Carlo variance with n=100,000 samples.

---

## Citation

```bibtex
@article{sovchain2026,
  title={SovChain: A Hybrid Permissioned Blockchain Architecture for 
         Sovereign Central Bank Digital Currency},
  author={Muhammad, Ajmal and Mahmood, Tahir},
  journal={ACM Distributed Ledger Technologies},
  year={2026},
  note={Under review}
}
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Contact

Questions or issues? Feel free to reach out:
- Ajmal Muhammad: muaj07@gmail.com
- Tahir Mahmood: tahirmahmood813@gmail.com
