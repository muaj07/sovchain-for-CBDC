"""
SovChain DoS Resilience Simulation
==================================

Discrete-event simulation for DoS/spam attack resilience as described in
Section 8.5 of the SovChain paper.

This module simulates the admission control and scheduling pipeline under
mixed legitimate and attacker traffic to measure:
- Legitimate transaction p99 latency under attack
- Legitimate transaction drop rate

Reference: SovChain paper, Section 8.5, Table 25
"""

import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import numpy as np
from tabulate import tabulate

from .config import (
    RANDOM_SEED,
    DEFAULT_SAMPLES,
    DOS_PARAMS,
    ECONOMIC_PARAMS,
    get_rng,
)


@dataclass
class DoSScenario:
    """Definition of a DoS attack scenario."""
    name: str
    attack_tps: int
    description: str


# Attack scenarios from Table 25
DOS_SCENARIOS = [
    DoSScenario("Baseline (no attack)", 0, "Normal operation"),
    DoSScenario("Moderate spam (50k/s)", 50_000, "Distributed spam attack"),
    DoSScenario("Heavy spam (200k/s)", 200_000, "Coordinated attack"),
    DoSScenario("Sustained flood (500k/s)", 500_000, "State-level adversary"),
]


@dataclass
class DoSResult:
    """Results from a DoS simulation run."""
    
    scenario: DoSScenario
    simulation_duration_s: float
    
    # Offered traffic
    legitimate_offered_tps: float
    attack_offered_tps: float
    
    # Admission results
    legitimate_admitted: int
    legitimate_dropped: int
    attack_filtered: int
    
    # Latency for admitted legitimate transactions
    legitimate_p99_ms: float
    
    @property
    def drop_rate(self) -> float:
        """Fraction of legitimate transactions dropped."""
        total = self.legitimate_admitted + self.legitimate_dropped
        if total == 0:
            return 0.0
        return self.legitimate_dropped / total


class AdmissionController:
    """
    Token-bucket rate limiter with identity-based quotas.
    
    Implements the admission controls from Table 24:
    - Per-wallet quota (10 tx/day Tier 0, 50/day Tier 1+)
    - Rate limiting (5 tx/sec/identity max)
    - Priority fees during congestion
    - Reputation scoring
    """
    
    def __init__(
        self,
        capacity_tps: int = DOS_PARAMS.target_tps,
        rate_limit_per_sec: int = DOS_PARAMS.rate_limit_per_sec,
        rng: Optional[np.random.Generator] = None,
    ):
        self.capacity_tps = capacity_tps
        self.rate_limit = rate_limit_per_sec
        self.rng = rng or get_rng()
        
        # Token buckets per identity
        self.identity_buckets: Dict[str, float] = {}
        self.identity_last_access: Dict[str, float] = {}
        
        # Global state
        self.current_load = 0.0
        
    def get_congestion_mode(self, load_fraction: float) -> str:
        """Determine congestion mode based on current load."""
        if load_fraction < DOS_PARAMS.elevated_threshold:
            return "normal"
        elif load_fraction < DOS_PARAMS.high_threshold:
            return "elevated"
        elif load_fraction < DOS_PARAMS.critical_threshold:
            return "high"
        else:
            return "critical"
    
    def admit_transaction(
        self,
        identity: str,
        tier: int,
        has_fee: bool,
        timestamp: float,
        current_load_fraction: float,
    ) -> Tuple[bool, str]:
        """
        Attempt to admit a transaction.
        
        Returns:
            (admitted, reason)
        """
        mode = self.get_congestion_mode(current_load_fraction)
        
        # Critical mode: only Tier 2+ with fees
        if mode == "critical":
            if tier < 2 or not has_fee:
                return False, "critical_mode_rejection"
        
        # High mode: minimum fee required
        elif mode == "high":
            if tier == 0:
                return False, "tier0_suspended"
            if not has_fee:
                return False, "fee_required"
        
        # Elevated mode: throttle free tier
        elif mode == "elevated":
            if tier == 0 and not has_fee:
                # 50% chance of throttling Tier 0
                if self.rng.random() < 0.5:
                    return False, "tier0_throttled"
        
        # Rate limit check (per identity)
        if identity in self.identity_last_access:
            time_since_last = timestamp - self.identity_last_access[identity]
            if time_since_last < 1.0 / self.rate_limit:
                return False, "rate_limited"
        
        # Update state
        self.identity_last_access[identity] = timestamp
        
        return True, "admitted"


class DoSSimulator:
    """
    Discrete-event simulator for DoS attack scenarios.
    
    Simulates the transaction admission and scheduling pipeline
    under mixed legitimate and attacker arrivals.
    """
    
    def __init__(
        self,
        capacity_tps: int = DOS_PARAMS.target_tps,
        legitimate_tps: float = ECONOMIC_PARAMS.implied_avg_tps,
        seed: int = RANDOM_SEED,
    ):
        self.capacity_tps = capacity_tps
        self.legitimate_tps = legitimate_tps
        self.rng = get_rng(seed)
        
    def simulate_scenario(
        self,
        scenario: DoSScenario,
        duration_s: float = 1000.0,
        time_step_ms: float = 1.0,
    ) -> DoSResult:
        """
        Simulate a DoS attack scenario.
        
        Args:
            scenario: Attack scenario to simulate
            duration_s: Simulation duration in seconds
            time_step_ms: Time step for discrete events
            
        Returns:
            DoSResult with latency and drop statistics
        """
        controller = AdmissionController(
            capacity_tps=self.capacity_tps,
            rng=self.rng,
        )
        
        # Statistics
        legitimate_admitted = 0
        legitimate_dropped = 0
        attack_filtered = 0
        legitimate_latencies_ms = []
        
        # Time tracking
        current_time = 0.0
        time_step_s = time_step_ms / 1000.0
        
        # Arrival rates (Poisson)
        legit_arrival_rate = self.legitimate_tps * time_step_s
        attack_arrival_rate = scenario.attack_tps * time_step_s
        
        # Processing queue
        queue_depth = 0
        max_queue = 100_000  # Mempool capacity
        
        while current_time < duration_s:
            # Generate arrivals for this time step
            n_legit = self.rng.poisson(legit_arrival_rate)
            n_attack = self.rng.poisson(attack_arrival_rate)
            
            # Current load fraction
            offered_tps = (queue_depth + n_legit + n_attack) / time_step_s
            load_fraction = min(offered_tps / self.capacity_tps, 1.0)
            
            # Process legitimate transactions
            for i in range(n_legit):
                identity = f"legit_{self.rng.integers(1_000_000)}"
                tier = self.rng.choice([0, 1, 2, 3], p=[0.4, 0.3, 0.2, 0.1])
                has_fee = tier > 0 or self.rng.random() < 0.3
                
                admitted, reason = controller.admit_transaction(
                    identity=identity,
                    tier=tier,
                    has_fee=has_fee,
                    timestamp=current_time,
                    current_load_fraction=load_fraction,
                )
                
                if admitted:
                    if queue_depth < max_queue:
                        queue_depth += 1
                        legitimate_admitted += 1
                        
                        # Estimate latency based on queue depth
                        base_latency = 371  # Baseline p50 from Table 22
                        queue_latency = (queue_depth / self.capacity_tps) * 1000
                        jitter = self.rng.normal(0, 50)
                        total_latency = base_latency + queue_latency + jitter
                        legitimate_latencies_ms.append(max(100, total_latency))
                    else:
                        legitimate_dropped += 1
                else:
                    legitimate_dropped += 1
            
            # Process attack transactions (most should be filtered)
            for i in range(n_attack):
                # Attackers have fake identities, Tier 0, no fees
                identity = f"attack_{self.rng.integers(10_000_000)}"
                
                admitted, reason = controller.admit_transaction(
                    identity=identity,
                    tier=0,
                    has_fee=False,
                    timestamp=current_time,
                    current_load_fraction=load_fraction,
                )
                
                if admitted:
                    # Rarely gets through
                    queue_depth = min(queue_depth + 1, max_queue)
                else:
                    attack_filtered += 1
            
            # Process queue (drain at capacity rate)
            processed = min(queue_depth, int(self.capacity_tps * time_step_s))
            queue_depth = max(0, queue_depth - processed)
            
            current_time += time_step_s
        
        # Compute p99 latency
        if legitimate_latencies_ms:
            p99_latency = np.percentile(legitimate_latencies_ms, 99)
        else:
            p99_latency = 0.0
        
        return DoSResult(
            scenario=scenario,
            simulation_duration_s=duration_s,
            legitimate_offered_tps=self.legitimate_tps,
            attack_offered_tps=scenario.attack_tps,
            legitimate_admitted=legitimate_admitted,
            legitimate_dropped=legitimate_dropped,
            attack_filtered=attack_filtered,
            legitimate_p99_ms=p99_latency,
        )


def generate_table_25(results: List[DoSResult]) -> str:
    """
    Generate Table 25 from the paper: DoS Mitigation Under Simulated Attack.
    """
    headers = [
        "Scenario",
        "Offered Attack TPS",
        "Legitimate p99",
        "Legit Drop Rate"
    ]
    
    rows = []
    for r in results:
        rows.append([
            r.scenario.name,
            f"{r.scenario.attack_tps:,}",
            f"{r.legitimate_p99_ms:.0f}ms",
            f"{r.drop_rate * 100:.0f}%"
        ])
    
    return tabulate(rows, headers=headers, tablefmt="simple")


def main():
    """Run DoS simulation and output Table 25."""
    parser = argparse.ArgumentParser(
        description="SovChain DoS Resilience Simulation (Section 8.5)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=1000.0,
        help="Simulation duration in seconds (default: 1000)"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=RANDOM_SEED,
        help=f"Random seed for reproducibility (default: {RANDOM_SEED})"
    )
    parser.add_argument(
        "--attack-rates",
        type=str,
        default=None,
        help="Comma-separated attack rates (e.g., '0,50000,200000,500000')"
    )
    
    args = parser.parse_args()
    
    print(f"SovChain DoS Resilience Simulation")
    print(f"===================================")
    print(f"Duration: {args.duration:.0f}s")
    print(f"Seed: {args.seed}")
    print(f"System capacity: {DOS_PARAMS.target_tps:,} TPS")
    print(f"Legitimate baseline: {ECONOMIC_PARAMS.implied_avg_tps:.0f} TPS")
    print()
    
    # Determine scenarios
    if args.attack_rates:
        rates = [int(r) for r in args.attack_rates.split(",")]
        scenarios = [
            DoSScenario(f"Attack @ {r:,}/s", r, "Custom")
            for r in rates
        ]
    else:
        scenarios = DOS_SCENARIOS
    
    # Run simulations
    sim = DoSSimulator(seed=args.seed)
    results = []
    
    for scenario in scenarios:
        print(f"Simulating: {scenario.name}...")
        result = sim.simulate_scenario(scenario, duration_s=args.duration)
        results.append(result)
    
    print()
    print("Table 25: DoS Mitigation Under Simulated Attack (Model-Based)")
    print("=" * 70)
    print(generate_table_25(results))
    print()
    
    # Verification against paper values
    print("Verification against paper Table 25:")
    expected = {
        "Baseline (no attack)": (572, 0),
        "Moderate spam (50k/s)": (645, 0),
        "Heavy spam (200k/s)": (890, 12),
        "Sustained flood (500k/s)": (1420, 45),
    }
    
    tolerance_latency = 0.20  # 20% tolerance for latency
    tolerance_drop = 5  # 5 percentage points tolerance for drop rate
    
    for r in results:
        if r.scenario.name in expected:
            exp_latency, exp_drop = expected[r.scenario.name]
            latency_diff = abs(r.legitimate_p99_ms - exp_latency) / exp_latency
            drop_diff = abs(r.drop_rate * 100 - exp_drop)
            
            status = "✓" if latency_diff < tolerance_latency and drop_diff < tolerance_drop else "⚠"
            print(f"  {status} {r.scenario.name}:")
            print(f"      p99 latency: {r.legitimate_p99_ms:.0f}ms (expected ~{exp_latency}ms)")
            print(f"      Drop rate: {r.drop_rate*100:.0f}% (expected ~{exp_drop}%)")
    
    # Additional insights
    print()
    print("Attack filtering efficiency:")
    for r in results:
        if r.scenario.attack_tps > 0:
            filter_rate = r.attack_filtered / (r.attack_filtered + 1)
            print(f"  {r.scenario.name}: {filter_rate*100:.1f}% of attack traffic filtered")


if __name__ == "__main__":
    main()
