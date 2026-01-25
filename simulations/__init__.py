"""
SovChain Simulation Package
===========================

Monte Carlo simulations and economic models for the SovChain CBDC architecture.

Modules:
- config: Shared parameters from Table 11 and methodology sections
- latency_simulation: End-to-end confirmation latency (Section 8.3, Table 22)
- execution_cost_model: Compliance/privacy overhead (Section 8.4, Table 23)
- dos_resilience: DoS attack simulation (Section 8.5, Table 25)
- economic_model: Validator economics (Section 9, Tables 28, 31, 32)
"""

from .config import (
    RANDOM_SEED,
    DEFAULT_SAMPLES,
    ConsensusParams,
    ECONOMIC_PARAMS,
    get_rng,
)

__version__ = "1.0.0"
__author__ = "Ajmal Muhammad, Tahir Mahmood"
