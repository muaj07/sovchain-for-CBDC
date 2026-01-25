# SovChain Move Smart Contracts

Sui Move implementation of the SovChain CBDC architecture (Sections 4-6).

## Overview

These contracts implement:

- **Governance isolation** (Section 4) - Separation of governance and consensus
- **CBDC asset management** (Section 4.2) - Token minting, burning, transfers
- **Compliance enforcement** (Section 6) - Tiered KYC and transaction limits
- **Confidential minting** (Section 5) - ZKP-verified private minting

## Prerequisites

### Required Software

| Tool | Version | Installation |
|------|---------|--------------|
| Sui CLI | 1.20+ | See below |
| Rust | 1.70+ | Required for Sui CLI build |
| Git | 2.x | For cloning dependencies |

### Install Sui CLI

**Option 1: Cargo Install (Recommended)**

```bash
cargo install --locked --git https://github.com/MystenLabs/sui.git \
    --branch mainnet-v1.20.0 sui
```

**Option 2: Pre-built Binaries**

Download from [Sui Releases](https://github.com/MystenLabs/sui/releases).

**Verify Installation:**

```bash
sui --version
# Expected: sui 1.20.x
```

## Directory Structure

```
move-contracts/
├── Move.toml              # Package manifest
├── sources/
│   ├── governance.move    # Governance layer (Section 4)
│   ├── cbdc.move          # CBDC token module (Section 4.2)
│   ├── compliance.move    # Compliance enforcement (Section 6)
│   └── mint.move          # Confidential minting (Section 5)
└── README.md
```

## Building

### Step 1: Navigate to Contract Directory

```bash
cd move-contracts
```

### Step 2: Build Contracts

```bash
sui move build
```

**Expected Output:**

```
UPDATING GIT DEPENDENCY https://github.com/MystenLabs/sui.git
INCLUDING DEPENDENCY Sui
INCLUDING DEPENDENCY MoveStdlib
BUILDING SovChain
```

### Step 3: Verify Build Artifacts

```bash
ls -la build/SovChain/
```

Build artifacts include:
- `bytecode_modules/` - Compiled Move bytecode
- `source_maps/` - Debug information
- `BuildInfo.yaml` - Build metadata

## Testing

### Run Unit Tests

```bash
sui move test
```

**Expected Output:**

```
INCLUDING DEPENDENCY Sui
INCLUDING DEPENDENCY MoveStdlib
BUILDING SovChain
Running Move unit tests
[ PASS    ] sovchain::governance::test_committee_initialization
[ PASS    ] sovchain::governance::test_threshold_validation
[ PASS    ] sovchain::compliance::test_tier_limits
[ PASS    ] sovchain::compliance::test_volume_tracking
[ PASS    ] sovchain::cbdc::test_mint_burn
[ PASS    ] sovchain::cbdc::test_transfer
Test result: OK. Total tests: 6; passed: 6; failed: 0
```

### Run Specific Test

```bash
sui move test --filter governance
```

### Test with Gas Profiling

```bash
sui move test --gas-limit 1000000000
```

## Formal Verification

### Install Move Prover

The Move Prover requires additional setup:

```bash
# Install Boogie and Z3 (dependencies)
# Ubuntu/Debian:
sudo apt-get install boogie z3

# macOS:
brew install boogie z3
```

### Run Verification

```bash
sui move prove
```

**Expected Output:**

```
PROVING SovChain
[INFO] Verifying governance module...
[INFO] Verifying compliance module...
[INFO] Verifying cbdc module...
[INFO] Verifying mint module...
[INFO] All proofs verified successfully.
```

### Verified Invariants

| Module | Invariant | Status |
|--------|-----------|--------|
| governance | GovernanceCap uniqueness | ✓ |
| governance | Threshold ≤ committee size | ✓ |
| compliance | Tier bounds (0-3) | ✓ |
| compliance | Volume monotonicity | ✓ |
| cbdc | Supply conservation | ✓ |

## Module Documentation

### governance.move

Implements governance-consensus separation (Section 4).

**Key Structures:**

```move
struct GovernorCommittee has key {
    id: UID,
    members: VecSet<address>,  // 6 governors
    threshold: u64,             // 4-of-6 default
    epoch: u64,
    nonce: u64,
}

struct GovernanceCap has key, store {
    id: UID,
}
```

**Public Functions:**

| Function | Access | Description |
|----------|--------|-------------|
| `add_governor` | GovernanceCap | Add committee member |
| `remove_governor` | GovernanceCap | Remove committee member |
| `create_proposal` | Governor | Create governance proposal |
| `approve_proposal` | Governor | Vote on proposal |
| `advance_epoch` | GovernanceCap | Increment epoch counter |

### cbdc.move

CBDC token with treasury management (Section 4.2).

**Key Structures:**

```move
struct CBDC has drop {}  // Token type

struct Treasury has key {
    id: UID,
    total_minted: u64,
    total_burned: u64,
    cap: TreasuryCap<CBDC>,
}

struct MintLicense has key, store {
    id: UID,
    daily_limit: u64,
    daily_minted: u64,
    minter: address,
    nonce: u64,
}
```

**Public Functions:**

| Function | Access | Description |
|----------|--------|-------------|
| `mint` | MintLicense | Mint CBDC tokens |
| `burn` | Any | Burn owned tokens |
| `transfer` | Any | Transfer tokens |
| `total_supply` | Any | Query current supply |

### compliance.move

Identity registry and tiered limits (Section 6).

**Tier Limits (Table 13):**

| Tier | Balance Limit | Monthly Volume |
|------|---------------|----------------|
| 0 (Anonymous) | PKR 10,000 | PKR 50,000 |
| 1 (Basic) | PKR 50,000 | PKR 500,000 |
| 2 (Standard) | PKR 5,000,000 | PKR 5,000,000 |
| 3 (Full) | Unlimited | Unlimited |

**Public Functions:**

| Function | Access | Description |
|----------|--------|-------------|
| `update_tier` | KYC Provider | Set identity tier |
| `validate_transfer` | Any | Check compliance rules |
| `compliant_transfer` | Any | Transfer with checks |
| `get_tier` | Any | Query address tier |

### mint.move

Confidential minting with ZKP verification (Section 5).

**Public Functions:**

| Function | Access | Description |
|----------|--------|-------------|
| `mint_confidential` | MintLicense + Committee | ZKP-verified mint |
| `init_verifying_key` | GovernanceCap | Set Groth16 vk |

**Verification Steps (Figure 2):**

1. Validate proof format (128 bytes)
2. Check nonce freshness
3. Verify epoch validity
4. Verify FROST 4/6 signature
5. Verify Groth16 ZKP
6. Record confidential mint

## Deployment

### Local Testing Network

```bash
# Start local Sui network
sui start --with-faucet

# Deploy contracts
sui client publish --gas-budget 100000000
```

### Testnet Deployment

```bash
# Switch to testnet
sui client switch --env testnet

# Get testnet tokens
sui client faucet

# Deploy
sui client publish --gas-budget 100000000
```

### Mainnet Deployment (Production)

```bash
# Switch to mainnet
sui client switch --env mainnet

# Deploy with governance approval
sui client publish --gas-budget 500000000 \
    --serialize-unsigned-transaction > deploy_tx.bcs
```

## Gas Costs

| Operation | Gas Units | Notes |
|-----------|-----------|-------|
| Initialize governance | ~50,000 | One-time |
| Simple transfer | ~500 | No compliance |
| Compliant transfer | ~800 | With tier checks |
| Update tier | ~600 | KYC provider only |
| Confidential mint | ~2,500 | ZKP + threshold sig |
| Create proposal | ~400 | Governor only |
| Execute proposal | ~1,000 | After threshold |

## Configuration

### Modify Parameters

Edit `sources/governance.move`:

```move
// Adjust committee size
const GOVERNOR_COUNT: u64 = 6;

// Adjust threshold
const GOVERNANCE_THRESHOLD: u64 = 4;
```

Edit `sources/compliance.move`:

```move
// Adjust tier limits (in base units, 6 decimals)
const TIER0_BALANCE_LIMIT: u64 = 10_000_000_000;  // PKR 10,000
const TIER1_BALANCE_LIMIT: u64 = 50_000_000_000;  // PKR 50,000
```

### Rebuild After Changes

```bash
sui move build
sui move test
```

## Troubleshooting

### "Package not found"

Ensure `Move.toml` has correct Sui dependency:

```toml
[dependencies]
Sui = { git = "https://github.com/MystenLabs/sui.git", subdir = "crates/sui-framework/packages/sui-framework", rev = "mainnet-v1.20.0" }
```

### "Type mismatch" errors

Check Sui SDK version compatibility:

```bash
sui --version
# Ensure matches Move.toml rev
```

### "Verification failed"

Install Move Prover dependencies:

```bash
# Check Boogie installation
boogie /version

# Check Z3 installation  
z3 --version
```

## References

- Sui Move Documentation: https://docs.sui.io/build/move
- Move Language Reference: https://move-language.github.io/move/
- Move Prover: https://github.com/move-language/move/tree/main/language/move-prover
- SovChain Paper: Section 4 (Architecture), Section 5 (ZKP), Section 6 (Compliance)
