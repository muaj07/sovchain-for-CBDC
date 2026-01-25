"""
SovChain End-to-End Latency Simulation
======================================

Monte Carlo simulation for end-to-end confirmation latency as described in
Section 8.3 of the SovChain paper.

This module simulates the five-stage transaction confirmation pipeline:
1. Client submission to validator ingress
2. Mempool admission and batching
3. Consensus ordering and commit (Mysticeti DAG-based BFT)
4. Move execution and state commit
5. Client acknowledgment

Reference: SovChain paper, Section 8.3, Table 22
"""

import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import numpy as np
from tabulate import tabulate

from .config import (
    RANDOM_SEED,
    DEFAULT_SAMPLES,
    ConsensusParams,
    CLIENT_TO_VALIDATOR,
    INTER_VALIDATOR,
    BYZANTINE_PARAMS,
    MEMPOOL_PARAMS,
    EXECUTION_COSTS,
    get_rng,
)


@dataclass
class LatencyResult:
    """Results from a latency simulation run."""
    
    scenario: str
    samples: int
    
    # Per-component statistics (p50, p95, p99)
    client_to_validator: Tuple[float, float, float]
    mempool_batching: Tuple[float, float, float]
    consensus_ordering: Tuple[float, float, float]
    move_execution: Tuple[float, float, float]
    acknowledgment: Tuple[float, float, float]
    
    # Total end-to-end (computed jointly, not summed)
    total: Tuple[float, float, float]
    
    def to_table_row(self) -> List:
        """Format as table row matching Table 22."""
        return [
            self.scenario,
            f"{self.total[0]:.0f}",
            f"{self.total[1]:.0f}",
            f"{self.total[2]:.0f}",
        ]


class LatencySimulator:
    """
    Monte Carlo simulator for end-to-end transaction latency.
    
    Implements the methodology described in Section 8.3:
    - Log-normal distributions for network latencies
    - Gaussian distributions for execution times
    - Byzantine stress scenarios with round disruption events
    """
    
    def __init__(
        self,
        consensus_params: ConsensusParams = ConsensusParams(),
        seed: int = RANDOM_SEED,
    ):
        self.consensus = consensus_params
        self.rng = get_rng(seed)
        
    def _sample_client_to_validator(self, n: int) -> np.ndarray:
        """
        Sample client-to-validator latency.
        
        Distribution: LogNormal(μ=3.33, σ=0.56), truncated at 200ms
        Median ≈ 28ms (4G mobile edge assumption)
        """
        return CLIENT_TO_VALIDATOR.sample(self.rng, n)
    
    def _sample_mempool_batching(self, n: int, byzantine: bool = False) -> np.ndarray:
        """
        Sample mempool batching delay.
        
        Distribution: Uniform(30, 50)ms for baseline
        Byzantine: slight increase due to validation overhead
        """
        base = self.rng.uniform(
            MEMPOOL_PARAMS.batch_delay_min_ms,
            MEMPOOL_PARAMS.batch_delay_max_ms,
            n
        )
        
        if byzantine:
            # Add validation overhead under Byzantine conditions
            overhead = self.rng.normal(5.0, 2.0, n)
            overhead = np.maximum(overhead, 0)  # Non-negative
            base = base + overhead
            
        return base
    
    def _sample_consensus_ordering(self, n: int, byzantine: bool = False) -> np.ndarray:
        """
        Sample consensus ordering latency (Mysticeti DAG-based BFT).
        
        Baseline: ~3 rounds of inter-validator communication
        Byzantine: round disruption events with probability 0.08
        """
        # Base consensus: 3 rounds of inter-validator latency
        # Each round requires quorum (2f+1) responses
        rounds = 3
        round_latencies = np.zeros(n)
        
        for _ in range(rounds):
            # Sample inter-validator latency for quorum gathering
            # We need 2f+1 responses; take the (2f+1)-th order statistic
            # Approximated as slightly above median
            round_lat = INTER_VALIDATOR.sample(self.rng, n)
            round_lat *= 1.1  # Quorum overhead factor
            round_latencies += round_lat
        
        if byzantine:
            # Inject round disruption events (Section 8.3)
            disruption_mask = self.rng.random(n) < BYZANTINE_PARAMS.round_disruption_prob
            disruption_delay = self.rng.normal(
                BYZANTINE_PARAMS.disruption_delay_mean_ms,
                BYZANTINE_PARAMS.disruption_delay_std_ms,
                n
            )
            disruption_delay = np.maximum(disruption_delay, 0)
            round_latencies += disruption_mask * disruption_delay
            
            # Equivocation detection overhead
            equiv_mask = self.rng.random(n) < BYZANTINE_PARAMS.equivocation_prob
            round_latencies += equiv_mask * BYZANTINE_PARAMS.equivocation_delay_ms
            
        return round_latencies
    
    def _sample_move_execution(self, n: int) -> np.ndarray:
        """
        Sample Move VM execution time.
        
        Distribution: N(3.5, 0.8)ms (Section 8.3)
        Consistent with Sui benchmarks for simple transactions.
        """
        execution = self.rng.normal(3.5, 0.8, n)
        return np.maximum(execution, 0.5)  # Minimum 0.5ms
    
    def _sample_acknowledgment(self, n: int) -> np.ndarray:
        """
        Sample acknowledgment latency (validator-to-client).
        
        Uses same distribution as client-to-validator (symmetric).
        """
        return CLIENT_TO_VALIDATOR.sample(self.rng, n)
    
    def simulate(
        self,
        n_samples: int = DEFAULT_SAMPLES,
        byzantine: bool = False,
    ) -> LatencyResult:
        """
        Run Monte Carlo simulation for end-to-end latency.
        
        Args:
            n_samples: Number of simulation samples
            byzantine: Whether to simulate Byzantine-stress scenario
            
        Returns:
            LatencyResult with per-component and total statistics
        """
        # Sample each component
        client_to_val = self._sample_client_to_validator(n_samples)
        mempool = self._sample_mempool_batching(n_samples, byzantine)
        consensus = self._sample_consensus_ordering(n_samples, byzantine)
        execution = self._sample_move_execution(n_samples)
        ack = self._sample_acknowledgment(n_samples)
        
        # Compute total latency (joint, not summed quantiles)
        total = client_to_val + mempool + consensus + execution + ack
        
        # Compute percentiles
        def percentiles(arr: np.ndarray) -> Tuple[float, float, float]:
            return (
                np.percentile(arr, 50),
                np.percentile(arr, 95),
                np.percentile(arr, 99),
            )
        
        scenario = "Byzantine-Stress" if byzantine else "Baseline"
        
        return LatencyResult(
            scenario=scenario,
            samples=n_samples,
            client_to_validator=percentiles(client_to_val),
            mempool_batching=percentiles(mempool),
            consensus_ordering=percentiles(consensus),
            move_execution=percentiles(execution),
            acknowledgment=percentiles(ack),
            total=percentiles(total),
        )


def generate_table_22(
    baseline: LatencyResult,
    byzantine: LatencyResult,
) -> str:
    """
    Generate Table 22 from the paper: End-to-End Confirmation Latency Breakdown.
    """
    headers = [
        "Component",
        "Baseline p50", "Baseline p95", "Baseline p99",
        "Byzantine p50", "Byzantine p95", "Byzantine p99",
    ]
    
    def fmt(vals: Tuple[float, float, float]) -> List[str]:
        return [f"{v:.0f}" for v in vals]
    
    rows = [
        ["Client → validator"] + fmt(baseline.client_to_validator) + fmt(byzantine.client_to_validator),
        ["Mempool/batching"] + fmt(baseline.mempool_batching) + fmt(byzantine.mempool_batching),
        ["Consensus ordering"] + fmt(baseline.consensus_ordering) + fmt(byzantine.consensus_ordering),
        ["Move execution"] + fmt(baseline.move_execution) + fmt(byzantine.move_execution),
        ["Acknowledgment"] + fmt(baseline.acknowledgment) + fmt(byzantine.acknowledgment),
        ["─" * 18] + ["─" * 8] * 6,  # Separator
        ["**Total**"] + fmt(baseline.total) + fmt(byzantine.total),
    ]
    
    return tabulate(rows, headers=headers, tablefmt="simple")


def main():
    """Run latency simulation and output Table 22."""
    parser = argparse.ArgumentParser(
        description="SovChain End-to-End Latency Simulation (Section 8.3)"
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
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed component statistics"
    )
    
    args = parser.parse_args()
    
    print(f"SovChain Latency Simulation")
    print(f"===========================")
    print(f"Samples: {args.samples:,}")
    print(f"Seed: {args.seed}")
    print()
    
    # Create simulator
    sim = LatencySimulator(seed=args.seed)
    
    # Run baseline scenario
    print("Running baseline scenario...")
    baseline = sim.simulate(n_samples=args.samples, byzantine=False)
    
    # Reset RNG for fair comparison
    sim.rng = get_rng(args.seed)
    
    # Run Byzantine-stress scenario
    print("Running Byzantine-stress scenario (f=9 faulty validators)...")
    byzantine = sim.simulate(n_samples=args.samples, byzantine=True)
    
    print()
    print("Table 22: End-to-End Confirmation Latency Breakdown (ms)")
    print("=" * 70)
    print(generate_table_22(baseline, byzantine))
    print()
    
    # Summary statistics
    print("Summary:")
    print(f"  Baseline:  p50={baseline.total[0]:.0f}ms, p95={baseline.total[1]:.0f}ms, p99={baseline.total[2]:.0f}ms")
    print(f"  Byzantine: p50={byzantine.total[0]:.0f}ms, p95={byzantine.total[1]:.0f}ms, p99={byzantine.total[2]:.0f}ms")
    print(f"  p99 increase: {(byzantine.total[2] - baseline.total[2]) / baseline.total[2] * 100:.1f}%")
    print()
    
    # Verify against paper values
    expected_baseline_p50 = 371
    expected_baseline_p99 = 572
    expected_byzantine_p99 = 686
    
    tolerance = 0.10  # 10% tolerance for stochastic variation
    
    def check(name: str, actual: float, expected: float):
        pct_diff = abs(actual - expected) / expected
        status = "✓" if pct_diff < tolerance else "⚠"
        print(f"  {status} {name}: {actual:.0f}ms (expected ~{expected}ms, diff={pct_diff*100:.1f}%)")
    
    print("Verification against paper Table 22:")
    check("Baseline p50", baseline.total[0], expected_baseline_p50)
    check("Baseline p99", baseline.total[2], expected_baseline_p99)
    check("Byzantine p99", byzantine.total[2], expected_byzantine_p99)
    
    if args.verbose:
        print()
        print("Detailed Component Statistics:")
        print(f"  Client-to-validator: median={CLIENT_TO_VALIDATOR.median_ms:.1f}ms")
        print(f"  Inter-validator: median={INTER_VALIDATOR.median_ms:.1f}ms")
        print(f"  Byzantine disruption prob: {BYZANTINE_PARAMS.round_disruption_prob}")
        print(f"  Byzantine disruption delay: N({BYZANTINE_PARAMS.disruption_delay_mean_ms}, {BYZANTINE_PARAMS.disruption_delay_std_ms})ms")


if __name__ == "__main__":
    main()
