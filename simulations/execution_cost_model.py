"""
SovChain Execution Cost Model
=============================

Monte Carlo simulation for compliance and privacy overhead as described in
Section 8.4 of the SovChain paper.

This module models three representative transaction paths:
1. Baseline retail transfer (simple coin::transfer)
2. Transfer with compliance checks (tier verification, limits)
3. Confidential minting (FROST + Groth16 + Pedersen)

Reference: SovChain paper, Section 8.4, Table 23
"""

import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
from tabulate import tabulate

from .config import (
    RANDOM_SEED,
    DEFAULT_SAMPLES,
    EXECUTION_COSTS,
    get_rng,
)


@dataclass
class ExecutionResult:
    """Results from execution cost simulation."""
    
    path_name: str
    samples: int
    mean_ms: float
    p99_ms: float
    overhead: float  # Relative to baseline
    notes: str


class ExecutionCostSimulator:
    """
    Monte Carlo simulator for transaction execution costs.
    
    Models the execution overhead for different transaction paths
    as described in Section 8.4.
    """
    
    def __init__(self, seed: int = RANDOM_SEED):
        self.rng = get_rng(seed)
        self.costs = EXECUTION_COSTS
        
    def _sample_gaussian(
        self,
        mean: float,
        std: float,
        n: int,
        min_val: float = 0.01,
    ) -> np.ndarray:
        """Sample from Gaussian with lower bound."""
        samples = self.rng.normal(mean, std, n)
        return np.maximum(samples, min_val)
    
    def simulate_baseline_transfer(self, n: int) -> np.ndarray:
        """
        Simulate baseline retail transfer (coin::transfer equivalent).
        
        Components:
        - Move execution
        - State commit
        """
        move_exec = self._sample_gaussian(
            self.costs.move_execution_mean,
            self.costs.move_execution_std,
            n
        )
        state_commit = self._sample_gaussian(
            self.costs.state_commit_mean,
            self.costs.state_commit_std,
            n
        )
        return move_exec + state_commit
    
    def simulate_compliance_transfer(self, n: int) -> np.ndarray:
        """
        Simulate transfer with full compliance checks.
        
        Additional components:
        - Identity registry lookup
        - Tier verification
        - Rolling-volume counter updates
        - Limit verification
        """
        # Base costs
        base = self.simulate_baseline_transfer(n)
        
        # Compliance overhead
        tier_check = self._sample_gaussian(
            self.costs.tier_check_mean,
            self.costs.tier_check_std,
            n
        )
        rolling_volume = self._sample_gaussian(
            self.costs.rolling_volume_mean,
            self.costs.rolling_volume_std,
            n
        )
        limit_verify = self._sample_gaussian(
            self.costs.limit_verification_mean,
            self.costs.limit_verification_std,
            n
        )
        
        return base + tier_check + rolling_volume + limit_verify
    
    def simulate_confidential_mint(self, n: int) -> np.ndarray:
        """
        Simulate confidential minting operation.
        
        Additional components:
        - FROST threshold signature verification (4-of-6)
        - Groth16 ZKP verification
        - Pedersen commitment validation
        """
        # Base costs
        base = self.simulate_baseline_transfer(n)
        
        # Cryptographic verification overhead
        frost_verify = self._sample_gaussian(
            self.costs.frost_verification_mean,
            self.costs.frost_verification_std,
            n
        )
        groth16_verify = self._sample_gaussian(
            self.costs.groth16_verification_mean,
            self.costs.groth16_verification_std,
            n
        )
        pedersen_check = self._sample_gaussian(
            self.costs.pedersen_check_mean,
            self.costs.pedersen_check_std,
            n
        )
        
        return base + frost_verify + groth16_verify + pedersen_check
    
    def run_all(self, n_samples: int = DEFAULT_SAMPLES) -> List[ExecutionResult]:
        """Run simulation for all transaction paths."""
        results = []
        
        # Baseline
        baseline_samples = self.simulate_baseline_transfer(n_samples)
        baseline_mean = np.mean(baseline_samples)
        baseline_p99 = np.percentile(baseline_samples, 99)
        
        results.append(ExecutionResult(
            path_name="Retail transfer (baseline)",
            samples=n_samples,
            mean_ms=baseline_mean,
            p99_ms=baseline_p99,
            overhead=1.0,
            notes="No compliance triggers"
        ))
        
        # Compliance transfer
        compliance_samples = self.simulate_compliance_transfer(n_samples)
        compliance_mean = np.mean(compliance_samples)
        compliance_p99 = np.percentile(compliance_samples, 99)
        
        results.append(ExecutionResult(
            path_name="Transfer + compliance",
            samples=n_samples,
            mean_ms=compliance_mean,
            p99_ms=compliance_p99,
            overhead=compliance_mean / baseline_mean,
            notes="Registry + tier/limits"
        ))
        
        # Confidential mint
        mint_samples = self.simulate_confidential_mint(n_samples)
        mint_mean = np.mean(mint_samples)
        mint_p99 = np.percentile(mint_samples, 99)
        
        results.append(ExecutionResult(
            path_name="Confidential mint",
            samples=n_samples,
            mean_ms=mint_mean,
            p99_ms=mint_p99,
            overhead=mint_mean / baseline_mean,
            notes="Threshold sig + Groth16"
        ))
        
        return results


def generate_table_23(results: List[ExecutionResult]) -> str:
    """
    Generate Table 23 from the paper: Simulated Execution Costs.
    """
    headers = ["Transaction Path", "Mean (ms)", "p99 (ms)", "Overhead", "Notes"]
    
    rows = []
    for r in results:
        rows.append([
            r.path_name,
            f"{r.mean_ms:.2f}",
            f"{r.p99_ms:.2f}",
            f"{r.overhead:.2f}×",
            r.notes
        ])
    
    return tabulate(rows, headers=headers, tablefmt="simple")


def main():
    """Run execution cost simulation and output Table 23."""
    parser = argparse.ArgumentParser(
        description="SovChain Execution Cost Simulation (Section 8.4)"
    )
    parser.add_argument(
        "--samples", "-n",
        type=int,
        default=DEFAULT_SAMPLES,
        help=f"Number of Monte Carlo samples (default: {DEFAULT_SAMPLES:,})"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=RANDOM_SEED,
        help=f"Random seed for reproducibility (default: {RANDOM_SEED})"
    )
    
    args = parser.parse_args()
    
    print(f"SovChain Execution Cost Simulation")
    print(f"===================================")
    print(f"Samples: {args.samples:,}")
    print(f"Seed: {args.seed}")
    print(f"Hardware assumption: 64-core server, 512GB RAM")
    print()
    
    # Run simulation
    sim = ExecutionCostSimulator(seed=args.seed)
    results = sim.run_all(n_samples=args.samples)
    
    print("Table 23: Simulated Execution Costs for Compliance and Privacy Paths")
    print("=" * 75)
    print(generate_table_23(results))
    print()
    
    # Summary
    print("Summary:")
    for r in results:
        print(f"  {r.path_name}: {r.mean_ms:.2f}ms mean, {r.p99_ms:.2f}ms p99")
    
    # Verify against paper values
    print()
    print("Verification against paper Table 23:")
    expected = {
        "Retail transfer (baseline)": (2.70, 3.93, 1.00),
        "Transfer + compliance": (3.28, 4.54, 1.21),
        "Confidential mint": (5.47, 6.90, 2.03),
    }
    
    tolerance = 0.15  # 15% tolerance
    
    for r in results:
        if r.path_name in expected:
            exp_mean, exp_p99, exp_overhead = expected[r.path_name]
            mean_diff = abs(r.mean_ms - exp_mean) / exp_mean
            p99_diff = abs(r.p99_ms - exp_p99) / exp_p99
            status = "✓" if mean_diff < tolerance and p99_diff < tolerance else "⚠"
            print(f"  {status} {r.path_name}:")
            print(f"      Mean: {r.mean_ms:.2f}ms (expected ~{exp_mean}ms)")
            print(f"      p99:  {r.p99_ms:.2f}ms (expected ~{exp_p99}ms)")
            print(f"      Overhead: {r.overhead:.2f}× (expected ~{exp_overhead}×)")


if __name__ == "__main__":
    main()
