"""
SovChain Economic Model
=======================

Economic analysis for validator profitability and staking dynamics as described
in Section 9 of the SovChain paper.

This module computes:
- Fee revenue projections (Table 28)
- Staking yield scenarios (Table 31)
- Break-even commission analysis (Table 32)
- Validator profitability

Reference: SovChain paper, Section 9, Tables 28, 31, 32
"""

import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
from tabulate import tabulate

from .config import (
    RANDOM_SEED,
    ECONOMIC_PARAMS,
    FEE_TIERS,
    FeeTier,
    ConsensusParams,
    get_rng,
)


@dataclass
class FeeProjection:
    """Fee revenue projection for a tier."""
    tier: FeeTier
    transactions_per_year: float
    revenue_pkr: float


@dataclass
class StakingScenario:
    """Staking participation scenario."""
    name: str
    stake_fraction_of_m2: float
    total_stake_pkr: float
    base_apy: float


@dataclass
class BreakEvenAnalysis:
    """Break-even commission analysis."""
    scenario: StakingScenario
    standalone_opex_pkr: float
    incremental_opex_pkr: float
    breakeven_commission_standalone: float
    breakeven_commission_incremental: float


class EconomicModel:
    """
    Economic model for SovChain validator economics.
    
    Implements the analysis from Section 9 including:
    - Fee schedule (Table 28)
    - Reward allocation (Equation 3)
    - Staking scenarios (Table 31)
    - Break-even analysis (Table 32)
    """
    
    def __init__(self, params: ECONOMIC_PARAMS = ECONOMIC_PARAMS):
        self.params = params
        self.consensus = ConsensusParams()
        
    def compute_fee_revenue(self) -> Tuple[List[FeeProjection], float]:
        """
        Compute annual fee revenue by tier (Table 28).
        
        Returns:
            List of FeeProjection per tier and total revenue
        """
        # CBDC transaction count (with adoption factor)
        n_cbdc = self.params.annual_transactions * self.params.count_capture
        
        projections = []
        total_revenue = 0.0
        
        for tier in FEE_TIERS:
            tx_count = n_cbdc * tier.share
            revenue = tx_count * tier.fee_per_tx_pkr
            
            projections.append(FeeProjection(
                tier=tier,
                transactions_per_year=tx_count,
                revenue_pkr=revenue,
            ))
            total_revenue += revenue
        
        return projections, total_revenue
    
    def compute_reward_pool(self, total_fees: float) -> float:
        """
        Compute staking reward pool (Equation 3).
        
        R_rewards = α · R_fees, α = 0.80
        """
        return self.params.alpha * total_fees
    
    def compute_staking_scenarios(self, reward_pool: float) -> List[StakingScenario]:
        """
        Compute staking yield scenarios (Table 31).
        
        Three scenarios:
        - Early: 0.1% of M2
        - Moderate: 0.5% of M2
        - Mature: 1.0% of M2
        """
        scenarios = []
        
        stake_fractions = [
            ("Early", 0.001),
            ("Moderate", 0.005),
            ("Mature", 0.010),
        ]
        
        for name, fraction in stake_fractions:
            total_stake = self.params.m2_pkr * fraction
            base_apy = reward_pool / total_stake
            
            scenarios.append(StakingScenario(
                name=name,
                stake_fraction_of_m2=fraction,
                total_stake_pkr=total_stake,
                base_apy=base_apy,
            ))
        
        return scenarios
    
    def compute_breakeven_commission(
        self,
        scenarios: List[StakingScenario],
        reward_pool: float,
    ) -> List[BreakEvenAnalysis]:
        """
        Compute break-even commission rates (Table 32).
        
        For each staking scenario, compute the commission rate needed
        for a validator to cover costs.
        """
        n_validators = self.consensus.n_validators
        
        # Costs
        standalone_annual = self.params.annual_validator_cost_pkr
        incremental_annual = 35e6  # PKR 35M for institutions with existing ops
        
        # Per-validator share of reward pool (with equal stake)
        per_validator_base = reward_pool / n_validators
        
        analyses = []
        
        for scenario in scenarios:
            # Under each scenario, validator's stake-proportional share
            # Assuming equal stake distribution
            validator_stake = scenario.total_stake_pkr / n_validators
            stake_share = validator_stake / scenario.total_stake_pkr
            
            # Self-stake earnings (validator keeps 100%)
            self_stake = self.params.min_validator_stake_pkr
            self_stake_earnings = self_stake * scenario.base_apy
            
            # Delegated stake earnings (validator keeps commission c)
            delegated_stake = validator_stake - self_stake
            if delegated_stake > 0:
                delegated_earnings_base = delegated_stake * scenario.base_apy
            else:
                delegated_earnings_base = 0
            
            # Break-even commission: c such that total earnings = costs
            # Earnings = self_stake * APY + c * delegated_stake * APY
            # Cost = annual_cost
            # c* = (Cost - self_stake * APY) / (delegated_stake * APY)
            
            def compute_commission(cost: float) -> float:
                if delegated_earnings_base <= 0:
                    return 0.0
                shortfall = cost - self_stake_earnings
                if shortfall <= 0:
                    return 0.0
                commission = shortfall / delegated_earnings_base
                return min(commission, 1.0)
            
            analyses.append(BreakEvenAnalysis(
                scenario=scenario,
                standalone_opex_pkr=standalone_annual,
                incremental_opex_pkr=incremental_annual,
                breakeven_commission_standalone=compute_commission(standalone_annual),
                breakeven_commission_incremental=compute_commission(incremental_annual),
            ))
        
        return analyses
    
    def compute_validator_profitability(
        self,
        reward_pool: float,
        stake_fraction: float = 0.001,  # Early scenario
    ) -> Dict:
        """
        Compute validator profitability metrics.
        
        For institution-only staking (early deployment).
        """
        n_validators = self.consensus.n_validators
        
        # Total stake and per-validator share
        total_stake = self.params.m2_pkr * stake_fraction
        per_validator_reward = reward_pool / n_validators
        
        # Annual cost
        annual_cost = self.params.annual_validator_cost_pkr
        
        # Net operating surplus
        net_surplus = per_validator_reward - annual_cost
        
        # ROCE (Return on Capital Employed)
        capital_employed = (
            self.params.min_validator_stake_pkr + 
            self.params.validator_capex_pkr
        )
        roce = net_surplus / capital_employed if capital_employed > 0 else 0
        
        return {
            "per_validator_reward_pkr": per_validator_reward,
            "annual_cost_pkr": annual_cost,
            "net_surplus_pkr": net_surplus,
            "capital_employed_pkr": capital_employed,
            "roce": roce,
        }


def generate_table_28(projections: List[FeeProjection], total: float) -> str:
    """Generate Table 28: Baseline Fee Revenue Projection."""
    headers = ["Tier (PKR)", "Share", "Tx/yr (B)", "Mean Amt.", "Fee Rule", "Fee/tx", "Rev. (PKR B)"]
    
    rows = []
    for p in projections:
        rows.append([
            p.tier.name,
            f"{p.tier.share*100:.0f}%",
            f"{p.transactions_per_year/1e9:.3f}",
            f"{p.tier.mean_amount_pkr:,.0f}",
            p.tier.fee_rule,
            f"{p.tier.fee_per_tx_pkr:.2f}",
            f"{p.revenue_pkr/1e9:.3f}",
        ])
    
    rows.append(["─" * 10] + ["─" * 8] * 6)
    rows.append(["**Total**", "100%", "", "", "", "", f"{total/1e9:.3f}"])
    
    return tabulate(rows, headers=headers, tablefmt="simple")


def generate_table_31(scenarios: List[StakingScenario]) -> str:
    """Generate Table 31: Stake Participation Scenarios."""
    headers = ["Scenario", "Stake as % of M2", "Total Stake (PKR B)", "Base APY"]
    
    rows = []
    for s in scenarios:
        rows.append([
            s.name,
            f"{s.stake_fraction_of_m2*100:.1f}%",
            f"{s.total_stake_pkr/1e9:.2f}",
            f"{s.base_apy*100:.2f}%",
        ])
    
    return tabulate(rows, headers=headers, tablefmt="simple")


def generate_table_32(analyses: List[BreakEvenAnalysis]) -> str:
    """Generate Table 32: Break-Even Commission Analysis."""
    headers = ["Stake Scenario", "Base APY", "c* @ PKR 95.17M/yr", "c* @ PKR 35M/yr"]
    
    rows = []
    for a in analyses:
        rows.append([
            f"{a.scenario.name} ({a.scenario.stake_fraction_of_m2*100:.1f}% of M2)",
            f"{a.scenario.base_apy*100:.2f}%",
            f"{a.breakeven_commission_standalone*100:.1f}%",
            f"{a.breakeven_commission_incremental*100:.1f}%",
        ])
    
    return tabulate(rows, headers=headers, tablefmt="simple")


def main():
    """Run economic model and output Tables 28, 31, 32."""
    parser = argparse.ArgumentParser(
        description="SovChain Economic Model (Section 9)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed calculations"
    )
    
    args = parser.parse_args()
    
    print(f"SovChain Economic Model")
    print(f"=======================")
    print(f"Base year: FY25 (Pakistan)")
    print(f"M2: PKR {ECONOMIC_PARAMS.m2_pkr/1e12:.2f}T")
    print(f"Exchange rate: PKR {ECONOMIC_PARAMS.exchange_rate:.2f}/USD")
    print()
    
    model = EconomicModel()
    
    # Fee revenue (Table 28)
    projections, total_fees = model.compute_fee_revenue()
    
    print("Table 28: Baseline Fee Revenue Projection (FY25 Workload)")
    print("=" * 80)
    print(generate_table_28(projections, total_fees))
    print()
    print(f"Total fee revenue: PKR {total_fees/1e9:.3f}B (≈USD {total_fees/ECONOMIC_PARAMS.exchange_rate/1e6:.1f}M)")
    print()
    
    # Reward pool (Equation 3)
    reward_pool = model.compute_reward_pool(total_fees)
    print(f"Staking reward pool (α={ECONOMIC_PARAMS.alpha}): PKR {reward_pool/1e9:.3f}B")
    print()
    
    # Staking scenarios (Table 31)
    scenarios = model.compute_staking_scenarios(reward_pool)
    
    print("Table 31: Stake Participation Scenarios")
    print("=" * 60)
    print(generate_table_31(scenarios))
    print()
    
    # Break-even analysis (Table 32)
    analyses = model.compute_breakeven_commission(scenarios, reward_pool)
    
    print("Table 32: Retail Staking: Break-Even Commission")
    print("=" * 70)
    print(generate_table_32(analyses))
    print()
    
    # Validator profitability (institution-only, early scenario)
    profitability = model.compute_validator_profitability(reward_pool)
    
    print("Institution-Only Staking (Early Phase):")
    print("-" * 40)
    print(f"  Per-validator reward: PKR {profitability['per_validator_reward_pkr']/1e6:.2f}M/year")
    print(f"  Annual cost: PKR {profitability['annual_cost_pkr']/1e6:.2f}M/year")
    print(f"  Net surplus: PKR {profitability['net_surplus_pkr']/1e6:.2f}M/year")
    print(f"  ROCE: {profitability['roce']*100:.1f}%")
    print()
    
    # Verification
    print("Verification against paper values:")
    
    expected_fee_total = 7.381e9  # PKR 7.381B
    expected_reward_pool = 5.905e9  # PKR 5.905B
    expected_early_apy = 0.1291  # 12.91%
    expected_validator_reward = 196.83e6  # PKR 196.83M
    
    tolerance = 0.05  # 5% tolerance
    
    def check(name: str, actual: float, expected: float):
        pct_diff = abs(actual - expected) / expected
        status = "✓" if pct_diff < tolerance else "⚠"
        print(f"  {status} {name}: {actual:,.0f} (expected ~{expected:,.0f}, diff={pct_diff*100:.1f}%)")
    
    check("Total fees (PKR)", total_fees, expected_fee_total)
    check("Reward pool (PKR)", reward_pool, expected_reward_pool)
    check("Early APY", scenarios[0].base_apy, expected_early_apy)
    check("Per-validator reward (PKR)", profitability['per_validator_reward_pkr'], expected_validator_reward)
    
    if args.verbose:
        print()
        print("Detailed Calculations:")
        print(f"  Annual transactions: {ECONOMIC_PARAMS.annual_transactions:,.0f}")
        print(f"  Count capture: {ECONOMIC_PARAMS.count_capture*100:.0f}%")
        print(f"  CBDC transactions: {ECONOMIC_PARAMS.annual_transactions * ECONOMIC_PARAMS.count_capture:,.0f}")
        print(f"  Validators: {ConsensusParams().n_validators}")
        print(f"  Min stake: PKR {ECONOMIC_PARAMS.min_validator_stake_pkr/1e6:.0f}M")


if __name__ == "__main__":
    main()
