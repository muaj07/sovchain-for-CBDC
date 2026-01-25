# Simulation Methodology

This document explains how to reproduce the Monte Carlo simulations from our paper.

## Overview

All simulations use consistent parameters:
- Sample size: n = 100,000
- Random seed: 42 (for reproducibility)
- Implementation: Python 3.10+ with NumPy/SciPy

## Running Simulations

### Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Run all simulations
./scripts/run_all_simulations.sh

# Or run individually
python -m simulations.latency_simulation --samples 100000 --seed 42
python -m simulations.execution_cost_model --samples 100000 --seed 42
python -m simulations.dos_resilience --duration 1000 --seed 42
python -m simulations.economic_model --verbose
```

### Output Directory

Results are written to `results/`:

```
results/
├── latency_results.txt       # Table 22
├── execution_cost_results.txt # Table 23
├── dos_results.txt           # Table 25
└── economic_results.txt      # Tables 28, 31, 32
```

---

## 1. End-to-End Latency Simulation (Section 8.3)

**Source**: `simulations/latency_simulation.py`  
**Output**: Table 22

### Model Architecture

Transaction confirmation traverses five sequential stages:

```
┌─────────┐    ┌─────────┐    ┌───────────┐    ┌───────────┐    ┌─────────┐
│ Client  │───►│ Mempool │───►│ Consensus │───►│ Execution │───►│   Ack   │
│ Submit  │    │ Batch   │    │ (DAG-BFT) │    │   (Move)  │    │ Return  │
└─────────┘    └─────────┘    └───────────┘    └───────────┘    └─────────┘
```

### Distribution Parameters

| Stage | Distribution | Parameters | Rationale |
|-------|--------------|------------|-----------|
| Client→Validator | LogNormal(μ_ln, σ_ln) | μ_ln=3.33, σ_ln=0.56, truncate=200ms | 4G mobile edge; median≈28ms |
| Mempool batching | Uniform(a, b) | a=30ms, b=50ms | Batching window |
| Consensus | 3×LogNormal | μ_ln=3.95, σ_ln=0.45, truncate=250ms | 3 rounds, intercontinental WAN; median≈52ms |
| Move execution | Normal(μ, σ) | μ=3.5ms, σ=0.8ms | Sui benchmark extrapolation |
| Acknowledgment | LogNormal | Same as client→validator | Symmetric |

### Byzantine-Stress Scenario

Models f=9 faulty validators (maximum for n=30):

| Event | Distribution | Trigger |
|-------|--------------|---------|
| Round disruption | Bernoulli(p) | p=0.08 per round |
| Disruption delay | Normal(μ, σ) | μ=150ms, σ=30ms |
| Equivocation handling | Bernoulli(p) | p=0.05 per round |
| Equivocation delay | Constant | 80ms |

### Implementation

```python
# Consensus latency sampling (simplified)
def sample_consensus(n_samples, byzantine=False):
    rounds = 3
    latencies = np.zeros(n_samples)
    
    for _ in range(rounds):
        round_lat = np.random.lognormal(3.95, 0.45, n_samples)
        round_lat = np.minimum(round_lat, 250)  # Truncation
        round_lat *= 1.1  # Quorum overhead
        latencies += round_lat
    
    if byzantine:
        # Inject round disruptions
        disruption_mask = np.random.random(n_samples) < 0.08
        disruption_delay = np.random.normal(150, 30, n_samples)
        disruption_delay = np.maximum(disruption_delay, 0)
        latencies += disruption_mask * disruption_delay
        
        # Equivocation handling
        equiv_mask = np.random.random(n_samples) < 0.05
        latencies += equiv_mask * 80
    
    return latencies
```

### Expected Results (Table 22)

| Component | Baseline p50 | p95 | p99 | Byzantine p50 | p95 | p99 |
|-----------|--------------|-----|-----|---------------|-----|-----|
| Client→Validator | 24 | 62 | 92 | 24 | 62 | 93 |
| Mempool/batching | 38 | 61 | 64 | 41 | 71 | 91 |
| Consensus ordering | 287 | 323 | 348 | 333 | 409 | 435 |
| Move execution | 3 | 4 | 5 | 3 | 4 | 5 |
| Acknowledgment | 19 | 45 | 63 | 19 | 44 | 62 |
| **Total** | **371** | **495** | **572** | **420** | **590** | **686** |

**Note**: Total statistics computed jointly (not by summing quantiles).

---

## 2. Execution Cost Model (Section 8.4)

**Source**: `simulations/execution_cost_model.py`  
**Output**: Table 23

### Transaction Paths

| Path | Components | Description |
|------|------------|-------------|
| Baseline | Move + Commit | Simple coin transfer |
| Compliance | Baseline + Tier + Volume + Limit | Full compliance path |
| Confidential | Baseline + FROST + Groth16 + Pedersen | Privacy-preserving mint |

### Cost Parameters (Gaussian)

| Component | Mean (ms) | Std (ms) | Path |
|-----------|-----------|----------|------|
| Move execution | 0.85 | 0.15 | All |
| State commit | 1.85 | 0.25 | All |
| Tier check | 0.18 | 0.03 | Compliance |
| Rolling volume | 0.28 | 0.05 | Compliance |
| Limit verification | 0.12 | 0.02 | Compliance |
| FROST verification | 0.75 | 0.10 | Confidential |
| Groth16 verification | 1.52 | 0.20 | Confidential |
| Pedersen check | 0.35 | 0.05 | Confidential |

### Expected Results (Table 23)

| Transaction Path | Mean (ms) | p99 (ms) | Overhead |
|------------------|-----------|----------|----------|
| Retail transfer (baseline) | 2.70 | 3.93 | 1.00× |
| Transfer + compliance | 3.28 | 4.54 | 1.21× |
| Confidential mint | 5.47 | 6.90 | 2.03× |

---

## 3. DoS Resilience Simulation (Section 8.5)

**Source**: `simulations/dos_resilience.py`  
**Output**: Table 25

### Attack Scenarios

| Scenario | Attack TPS | Description |
|----------|------------|-------------|
| Baseline | 0 | Normal operation |
| Moderate | 50,000 | Distributed spam |
| Heavy | 200,000 | Coordinated attack |
| Flood | 500,000 | State-level adversary |

### System Parameters

| Parameter | Value | Reference |
|-----------|-------|-----------|
| System capacity | 15,000 TPS | Section 8.2 |
| Legitimate TPS | 289 | Implied from Table 20 |
| Rate limit (per identity) | 5 tx/sec | Table 24 |
| Elevated threshold | 60% load | Table 24 |
| High threshold | 80% load | Table 24 |
| Critical threshold | 95% load | Table 24 |

### Admission Control Logic

```python
def admit_transaction(tier, has_fee, load_fraction):
    mode = get_congestion_mode(load_fraction)
    
    if mode == "critical":
        return tier >= 2 and has_fee
    elif mode == "high":
        return tier >= 1 and has_fee
    elif mode == "elevated":
        if tier == 0 and not has_fee:
            return random.random() > 0.5  # 50% throttle
        return True
    else:  # normal
        return True
```

### Expected Results (Table 25)

| Scenario | Attack TPS | Legitimate p99 | Drop Rate |
|----------|------------|----------------|-----------|
| Baseline | 0 | 572ms | 0% |
| Moderate | 50,000 | 645ms | 0% |
| Heavy | 200,000 | 890ms | 12% |
| Flood | 500,000 | 1420ms | 45% |

---

## 4. Economic Model (Section 9)

**Source**: `simulations/economic_model.py`  
**Output**: Tables 28, 31, 32

### Data Sources

| Parameter | Value | Source |
|-----------|-------|--------|
| Annual transactions | 9.1B | SBP FY25 Review |
| Annual value | PKR 612T | SBP FY25 Review |
| M2 | PKR 45.73T | SBP Jan 2026 |
| Exchange rate | PKR 279.9116/USD | SBP 20 Jan 2026 |
| CBDC count capture | 60% | Assumption (Section 9.1) |
| CBDC value capture | 50% | Assumption (Section 9.1) |

### Fee Schedule (Table 28)

| Tier | Share | Mean Amount | Fee Rule | Fee/tx |
|------|-------|-------------|----------|--------|
| 0-10k | 60% | PKR 3,000 | Free | PKR 0 |
| 10k-25k | 20% | PKR 17,000 | PKR 1 | PKR 1 |
| 25k-100k | 15% | PKR 55,000 | PKR 2 | PKR 2 |
| >100k | 5% | PKR 851,879 | 0.2 bps, cap 50 | PKR 17.04 |

### Calculations

**Total Fee Revenue:**
```
N_CBDC = 9.1B × 0.60 = 5.46B transactions
R_fees = Σ(share_i × N_CBDC × fee_i)
       = (0.60×0) + (0.20×5.46B×1) + (0.15×5.46B×2) + (0.05×5.46B×17.04)
       = PKR 7.381B
```

**Reward Pool (Equation 3):**
```
R_rewards = α × R_fees = 0.80 × 7.381B = PKR 5.905B
```

**Per-Validator Reward:**
```
R_validator = R_rewards / n_V = 5.905B / 30 = PKR 196.83M
```

**Base APY (Early Scenario):**
```
Stake = 0.001 × M2 = 0.001 × 45.73T = PKR 45.73B
APY = R_rewards / Stake = 5.905B / 45.73B = 12.91%
```

### Expected Results

**Table 28:**
- Total fee revenue: PKR 7.381B (≈USD 26.4M)

**Table 31:**

| Scenario | Stake % of M2 | Total Stake | Base APY |
|----------|---------------|-------------|----------|
| Early | 0.1% | PKR 45.73B | 12.91% |
| Moderate | 0.5% | PKR 228.65B | 2.58% |
| Mature | 1.0% | PKR 457.3B | 1.29% |

**Institution-Only Staking:**
- Per-validator reward: PKR 196.83M/year
- Annual cost: PKR 95.17M/year
- Net surplus: PKR 101.66M/year
- ROCE: ~65%

---

## Reproducibility Notes

### Random Number Generation

All simulations use NumPy's default RNG with explicit seeding:

```python
rng = np.random.default_rng(seed=42)
```

### Statistical Significance

With n=100,000 samples:
- Percentile estimates have ±1-2% relative error
- Mean estimates have <1% relative error
- Results should match paper values within stated tolerances

### Tolerance Thresholds

| Simulation | Tolerance | Rationale |
|------------|-----------|-----------|
| Latency | ±5% | Monte Carlo variance |
| Execution cost | ±10% | Parameter uncertainty |
| DoS resilience | ±15% | Simplified admission model |
| Economic | ±1% | Deterministic calculations |

### Verification

Each simulation prints verification output comparing against expected paper values:

```
Verification against paper Table 22:
  ✓ Baseline p50: 371ms (expected ~371ms, diff=0.1%)
  ✓ Baseline p99: 572ms (expected ~572ms, diff=0.2%)
  ✓ Byzantine p99: 686ms (expected ~686ms, diff=0.3%)
```

---

## Limitations

1. **Network model**: Log-normal distributions are assumptions; real networks may differ
2. **Byzantine model**: Simplified adversary behavior; real attacks may be more sophisticated
3. **Economic projections**: Based on FY25 data; actual adoption patterns may vary
4. **DoS model**: Discrete-event simulation; continuous models may give different results

## References

- Section 8.3: End-to-End Confirmation Latency
- Section 8.4: Compliance and Privacy Overhead
- Section 8.5: DoS Mitigation Results
- Section 9: Economic Analysis
- Table 11: Protocol Parameters
- Table 20: Pakistan FY25 Baseline
