"""
SovChain Simulation Configuration
=================================

Central configuration for all simulation parameters as specified in the paper.
All values correspond to Table 11 (Protocol Parameters) and Section 8 methodology.

Reference: SovChain paper, Sections 8.3, 8.4, 8.5, 9
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import numpy as np


# =============================================================================
# REPRODUCIBILITY
# =============================================================================

RANDOM_SEED = 42  # Fixed seed for reproducibility (Section 8.3)
DEFAULT_SAMPLES = 100_000  # Monte Carlo sample count (n = 100,000)


# =============================================================================
# CONSENSUS PARAMETERS (Table 11)
# =============================================================================

@dataclass(frozen=True)
class ConsensusParams:
    """Consensus layer parameters from Table 11."""
    
    n_validators: int = 30              # Validator count (n_V)
    byzantine_threshold: int = 9        # f < n_V/3, max tolerable = 9
    epoch_duration_s: int = 86_400      # T_epoch in seconds (1 day)
    block_time_ms: int = 500            # τ target block time
    message_delay_bound_ms: int = 500   # Δ_max post-GST
    clock_skew_bound_ms: int = 100      # ε via NTP
    
    def validate(self) -> bool:
        """Verify BFT threshold constraint."""
        return self.byzantine_threshold < self.n_validators / 3


# =============================================================================
# NETWORK LATENCY PARAMETERS (Section 8.3)
# =============================================================================

@dataclass
class LatencyDistribution:
    """
    Log-normal latency distribution parameters.
    
    X ~ LogNormal(μ_ln, σ_ln) where ln(X) ~ N(μ_ln, σ_ln²)
    Median = exp(μ_ln)
    """
    mu_ln: float        # Log-space mean
    sigma_ln: float     # Log-space std dev
    truncate_ms: float  # Upper truncation bound
    
    @property
    def median_ms(self) -> float:
        """Compute median in milliseconds."""
        return np.exp(self.mu_ln)
    
    def sample(self, rng: np.random.Generator, n: int = 1) -> np.ndarray:
        """Generate n samples from truncated log-normal distribution."""
        samples = rng.lognormal(self.mu_ln, self.sigma_ln, n)
        return np.minimum(samples, self.truncate_ms)


# Client-to-validator latency (4G mobile edge assumption)
CLIENT_TO_VALIDATOR = LatencyDistribution(
    mu_ln=3.33,         # ln(28) ≈ 3.33
    sigma_ln=0.56,
    truncate_ms=200.0
)

# Inter-validator latency (intercontinental WAN assumption)
INTER_VALIDATOR = LatencyDistribution(
    mu_ln=3.95,         # ln(52) ≈ 3.95
    sigma_ln=0.45,
    truncate_ms=250.0
)


# =============================================================================
# EXECUTION COST PARAMETERS (Section 8.4)
# =============================================================================

@dataclass
class ExecutionCostParams:
    """
    Per-component execution cost distributions (Gaussian).
    All values in milliseconds.
    """
    # Baseline Move execution
    move_execution_mean: float = 0.85
    move_execution_std: float = 0.15
    
    # State commit
    state_commit_mean: float = 1.85
    state_commit_std: float = 0.25
    
    # Compliance checks (additional)
    tier_check_mean: float = 0.18
    tier_check_std: float = 0.03
    
    rolling_volume_mean: float = 0.28
    rolling_volume_std: float = 0.05
    
    limit_verification_mean: float = 0.12
    limit_verification_std: float = 0.02
    
    # Cryptographic verification (confidential minting)
    frost_verification_mean: float = 0.75
    frost_verification_std: float = 0.10
    
    groth16_verification_mean: float = 1.52
    groth16_verification_std: float = 0.20
    
    pedersen_check_mean: float = 0.35
    pedersen_check_std: float = 0.05


EXECUTION_COSTS = ExecutionCostParams()


# =============================================================================
# BYZANTINE SCENARIO PARAMETERS (Section 8.3)
# =============================================================================

@dataclass
class ByzantineParams:
    """Parameters for Byzantine-stress simulation scenario."""
    
    # Round disruption probability (Bernoulli)
    round_disruption_prob: float = 0.08
    
    # Disruption delay distribution (Gaussian)
    disruption_delay_mean_ms: float = 150.0
    disruption_delay_std_ms: float = 30.0
    
    # Equivocation handling
    equivocation_prob: float = 0.05
    equivocation_delay_ms: float = 80.0
    
    # Message omission rate for faulty validators
    omission_rate: float = 0.20


BYZANTINE_PARAMS = ByzantineParams()


# =============================================================================
# MEMPOOL PARAMETERS (Section 8.3)
# =============================================================================

@dataclass
class MempoolParams:
    """Mempool batching parameters."""
    
    # Batching delay (Uniform distribution)
    batch_delay_min_ms: float = 30.0
    batch_delay_max_ms: float = 50.0
    
    # Capacity
    max_transactions: int = 100_000


MEMPOOL_PARAMS = MempoolParams()


# =============================================================================
# DOS MITIGATION PARAMETERS (Table 24, Section 8.5)
# =============================================================================

@dataclass
class DoSParams:
    """Anti-spam and DoS mitigation parameters."""
    
    # System capacity
    target_tps: int = 15_000
    
    # Per-identity rate limits
    tier0_daily_quota: int = 10
    tier1_daily_quota: int = 50
    rate_limit_per_sec: int = 5
    
    # Congestion thresholds
    elevated_threshold: float = 0.60
    high_threshold: float = 0.80
    critical_threshold: float = 0.95


DOS_PARAMS = DoSParams()


# =============================================================================
# ECONOMIC PARAMETERS (Section 9)
# =============================================================================

@dataclass
class EconomicParams:
    """Economic model parameters from Section 9."""
    
    # Pakistan FY25 baseline (Table 20)
    annual_transactions: float = 9.1e9       # 9.1 billion
    annual_value_pkr: float = 612e12         # PKR 612 trillion
    
    # Adoption assumptions (Section 9.1)
    count_capture: float = 0.60              # a_N = 60%
    value_capture: float = 0.50              # a_V = 50%
    
    # Monetary aggregates (SBP Jan 2026)
    m2_pkr: float = 45.73e12                 # PKR 45.73 trillion
    exchange_rate: float = 279.9116          # PKR per USD
    
    # Reward allocation (Equation 3)
    alpha: float = 0.80                      # 80% to staking rewards
    
    # Validator costs (Table 30)
    validator_capex_pkr: float = 55.98e6     # PKR 55.98M
    validator_opex_pkr: float = 83.97e6      # PKR 83.97M/year
    depreciation_years: int = 5
    
    # Staking parameters
    min_validator_stake_pkr: float = 100e6   # PKR 100M
    max_stake_ratio: float = 0.10            # 10% cap
    
    @property
    def implied_avg_tps(self) -> float:
        """Calculate implied average TPS from annual transactions."""
        seconds_per_year = 365 * 24 * 3600
        return self.annual_transactions / seconds_per_year
    
    @property
    def annual_validator_cost_pkr(self) -> float:
        """Total annual cost including depreciation."""
        return self.validator_opex_pkr + (self.validator_capex_pkr / self.depreciation_years)


ECONOMIC_PARAMS = EconomicParams()


# =============================================================================
# FEE SCHEDULE (Table 28)
# =============================================================================

@dataclass
class FeeTier:
    """Fee tier specification."""
    name: str
    amount_min_pkr: float
    amount_max_pkr: float
    share: float              # Share of transactions
    mean_amount_pkr: float    # Mean transaction amount
    fee_rule: str             # Description
    fee_per_tx_pkr: float     # Fee amount


FEE_TIERS: List[FeeTier] = [
    FeeTier("0-10k", 0, 10_000, 0.60, 3_000, "Free", 0.0),
    FeeTier("10k-25k", 10_000, 25_000, 0.20, 17_000, "PKR 1", 1.0),
    FeeTier("25k-100k", 25_000, 100_000, 0.15, 55_000, "PKR 2", 2.0),
    FeeTier(">100k", 100_000, float('inf'), 0.05, 851_879, "0.2 bps, cap 50", 17.04),
]


# =============================================================================
# ZKP CIRCUIT PARAMETERS (Table 15)
# =============================================================================

@dataclass
class CircuitParams:
    """ZKP circuit constraint breakdown from Table 15."""
    
    pedersen_constraints: int = 12_400       # 25%
    range_proof_constraints: int = 18_200    # 36%
    policy_check_constraints: int = 2_100    # 4%
    sha256_authority_constraints: int = 8_500  # 17%
    sha256_limit_constraints: int = 8_500    # 17%
    misc_constraints: int = 300              # 1%
    
    @property
    def total_constraints(self) -> int:
        return (self.pedersen_constraints + 
                self.range_proof_constraints +
                self.policy_check_constraints +
                self.sha256_authority_constraints +
                self.sha256_limit_constraints +
                self.misc_constraints)


CIRCUIT_PARAMS = CircuitParams()


# =============================================================================
# OFFLINE PAYMENT PARAMETERS (Table 18)
# =============================================================================

@dataclass
class OfflineTierParams:
    """Offline AML policy envelope by tier."""
    tier: int
    max_balance_pkr: float
    max_duration_hours: int
    max_recipients: int
    reconciliation_deadline_hours: int


OFFLINE_TIERS: List[OfflineTierParams] = [
    OfflineTierParams(0, 5_000, 24, 3, 48),
    OfflineTierParams(1, 20_000, 48, 10, 72),
    OfflineTierParams(2, 50_000, 72, 50, 168),    # 7 days
    OfflineTierParams(3, 100_000, 72, 999_999, 168),  # Unlimited recipients
]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_rng(seed: int = RANDOM_SEED) -> np.random.Generator:
    """Get a reproducible random number generator."""
    return np.random.default_rng(seed)


def validate_all_params() -> bool:
    """Validate all parameter constraints."""
    consensus = ConsensusParams()
    assert consensus.validate(), "BFT threshold constraint violated"
    assert CIRCUIT_PARAMS.total_constraints == 50_000, "Circuit constraint mismatch"
    assert abs(ECONOMIC_PARAMS.implied_avg_tps - 289) < 1, "TPS calculation mismatch"
    return True


if __name__ == "__main__":
    # Validate parameters on import
    validate_all_params()
    print("✓ All parameters validated successfully")
    print(f"  - Implied TPS: {ECONOMIC_PARAMS.implied_avg_tps:.1f}")
    print(f"  - Circuit constraints: {CIRCUIT_PARAMS.total_constraints:,}")
    print(f"  - Client-to-validator median: {CLIENT_TO_VALIDATOR.median_ms:.1f} ms")
    print(f"  - Inter-validator median: {INTER_VALIDATOR.median_ms:.1f} ms")
