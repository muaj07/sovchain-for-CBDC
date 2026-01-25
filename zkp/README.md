# SovChain ZKP Framework

Zero-Knowledge Proof implementation for confidential CBDC minting (Section 5).

## Overview

This module implements the Groth16-based privacy-preserving minting protocol:

- **Pedersen commitments** for amount hiding
- **Range proofs** (64-bit) for value bounds
- **Policy compliance proofs** without revealing amounts
- **FROST threshold signatures** for authorization

## Prerequisites

### Required Software

| Tool | Version | Installation |
|------|---------|--------------|
| Rust | 1.70+ | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Circom | 2.1.6+ | See [Circom Installation](#circom-installation) |
| snarkjs | 0.7+ | `npm install -g snarkjs` |
| Node.js | 18+ | Required for snarkjs |

### Circom Installation

```bash
# Clone and build Circom
git clone https://github.com/iden3/circom.git
cd circom
cargo build --release

# Install globally
sudo cp target/release/circom /usr/local/bin/
circom --version  # Should show 2.1.x
```

## Directory Structure

```
zkp/
├── circuits/
│   ├── mint_circuit.circom    # Main circuit (~50k constraints)
│   ├── pedersen.circom        # Pedersen commitment gadget
│   └── range_proof.circom     # 64-bit range proof gadget
├── src/
│   ├── lib.rs                 # Library entry point
│   ├── prover.rs              # Groth16 proof generation
│   └── verifier.rs            # On-chain verification logic
├── Cargo.toml
└── README.md
```

## Building the Rust Library

```bash
cd zkp

# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Run tests
cargo test

# Generate documentation
cargo doc --open
```

### Build Output

```
target/release/
├── libsovchain_zkp.rlib    # Rust library
└── zkp-cli                 # Command-line tool
```

## Compiling Circom Circuits

### Step 1: Install circomlib Dependencies

```bash
cd circuits
mkdir -p node_modules
npm init -y
npm install circomlib
```

### Step 2: Compile Main Circuit

```bash
# Create build directory
mkdir -p build

# Compile to R1CS, WASM, and symbols
circom mint_circuit.circom \
    --r1cs \
    --wasm \
    --sym \
    --output build/

# Verify constraint count
snarkjs r1cs info build/mint_circuit.r1cs
```

**Expected output:**
```
[INFO]  snarkJS: Curve: bn-128
[INFO]  snarkJS: # of Wires: 50847
[INFO]  snarkJS: # of Constraints: 50000
[INFO]  snarkJS: # of Private Inputs: 4
[INFO]  snarkJS: # of Public Inputs: 6
[INFO]  snarkJS: # of Labels: 51203
[INFO]  snarkJS: # of Outputs: 0
```

### Step 3: Trusted Setup (Development)

For development and testing only. Production requires a proper MPC ceremony.

```bash
# Phase 1: Powers of Tau (universal)
snarkjs powersoftau new bn128 17 pot17_0000.ptau -v
snarkjs powersoftau contribute pot17_0000.ptau pot17_0001.ptau \
    --name="First contribution" -v
snarkjs powersoftau prepare phase2 pot17_0001.ptau pot17_final.ptau -v

# Phase 2: Circuit-specific setup
snarkjs groth16 setup build/mint_circuit.r1cs pot17_final.ptau mint_0000.zkey
snarkjs zkey contribute mint_0000.zkey mint_0001.zkey \
    --name="Circuit contribution" -v

# Export verification key
snarkjs zkey export verificationkey mint_0001.zkey verification_key.json

# Export Solidity verifier (optional)
snarkjs zkey export solidityverifier mint_0001.zkey verifier.sol
```

### Step 4: Generate Test Proof

Create a test input file `input.json`:

```json
{
    "amount": "1000000000",
    "blinding": "12345678901234567890123456789012345678901234567890123456789012345678",
    "pubkey": ["1", "2", "3", "4", "5", "6", "7", "8"],
    "daily_limit": "10000000000",
    "commitment_x": "...",
    "commitment_y": "...",
    "authority_hash": ["...", "...", "...", "...", "...", "...", "...", "..."],
    "limit_hash": ["...", "...", "...", "...", "...", "...", "...", "..."],
    "nonce": "1",
    "epoch": "100"
}
```

Generate and verify:

```bash
# Generate witness
node build/mint_circuit_js/generate_witness.js \
    build/mint_circuit_js/mint_circuit.wasm \
    input.json \
    witness.wtns

# Generate proof
snarkjs groth16 prove mint_0001.zkey witness.wtns proof.json public.json

# Verify proof
snarkjs groth16 verify verification_key.json public.json proof.json
```

**Expected output:**
```
[INFO]  snarkJS: OK!
```

## Circuit Specification

### NP Relation (Section 5.4)

The circuit proves:

```
R(x, w) = 1 ⟺ {
    C = amount·G + blinding·H        (Pedersen commitment)
    0 < amount ≤ daily_limit         (policy compliance)
    amount < 2^64                     (range bound)
    H(pubkey) = authority_hash       (authorization)
    H(daily_limit) = limit_hash      (parameter binding)
}
```

### Public Inputs

| Input | Size | Description |
|-------|------|-------------|
| commitment_x | 32 bytes | Pedersen commitment x-coordinate |
| commitment_y | 32 bytes | Pedersen commitment y-coordinate |
| authority_hash | 32 bytes | SHA-256(minter_pubkey) |
| limit_hash | 32 bytes | SHA-256(daily_limit) |
| nonce | 8 bytes | Monotonic counter |
| epoch | 8 bytes | Current epoch |

### Private Witness

| Input | Size | Description |
|-------|------|-------------|
| amount | 64 bits | Mint amount |
| blinding | 256 bits | Commitment randomness |
| pubkey | 256 bits | Minter public key |
| daily_limit | 64 bits | Policy limit |

### Constraint Breakdown (Table 15)

| Component | Constraints | Notes |
|-----------|-------------|-------|
| Pedersen commitment | 12,400 | BN254 scalar multiplication |
| Range proof | 18,200 | 64-bit binary decomposition |
| Policy check | 2,100 | Comparison circuits |
| SHA-256 (authority) | 8,500 | Hash verification |
| SHA-256 (limit) | 8,500 | Hash verification |
| Wiring | 300 | Signal routing |
| **Total** | **50,000** | |

## Performance Benchmarks

| Operation | Time | Hardware |
|-----------|------|----------|
| Circuit compilation | ~30s | Any |
| Witness generation | ~100ms | Node.js |
| Proof generation | ~2s | 8-core CPU |
| Proof verification | ~1.5ms | Single core |

| Artifact | Size |
|----------|------|
| Proving key | ~45 MB |
| Verification key | ~1 KB |
| Proof | 128 bytes |

## Rust API Usage

```rust
use sovchain_zkp::{MintProver, MintVerifier, MintWitness};

// Create witness
let witness = MintWitness {
    amount: 1_000_000_000,
    blinding: random_blinding(),
    pubkey: minter_pubkey,
    daily_limit: 10_000_000_000,
};

// Load keys
let prover = MintProver::load("mint_0001.zkey")?;
let verifier = MintVerifier::load("verification_key.json")?;

// Generate proof
let commitment = compute_pedersen(witness.amount, witness.blinding);
let (proof, public_inputs) = prover.prove(&witness, commitment, nonce, epoch)?;

// Verify proof
assert!(verifier.verify(&proof, &public_inputs)?);
```

## Security Considerations

### Curve Security

- **BN254**: ~100-bit security level
- Suitable for medium-term deployments
- Migration path to BLS12-381 for higher security

### Trusted Setup

- Production requires 12-party MPC ceremony (Section 5.3)
- Security holds if at least one participant is honest
- Ceremony procedures documented in `docs/CEREMONY_GUIDE.md`

### Known Limitations

1. Trusted setup required (not transparent)
2. Proof generation is sequential (not parallelizable)
3. Circuit modifications require new setup

## Troubleshooting

### "Cannot find module 'circomlib'"

```bash
cd circuits
npm install circomlib
```

### "Constraint count mismatch"

Ensure circomlib version matches (0.5.x recommended):

```bash
npm install circomlib@0.5.5
```

### "Out of memory during compilation"

Increase Node.js memory limit:

```bash
export NODE_OPTIONS="--max-old-space-size=8192"
circom mint_circuit.circom --r1cs --wasm --sym -o build/
```

### "Powers of tau file too small"

Use a larger tau ceremony (17+ for 50k constraints):

```bash
snarkjs powersoftau new bn128 17 pot17_0000.ptau
```

## References

- [Groth16] J. Groth, "On the Size of Pairing-Based Non-interactive Arguments," EUROCRYPT 2016
- [Circom] iden3, "Circom: A Circuit Compiler for zkSNARKs," https://docs.circom.io
- [arkworks] arkworks contributors, "arkworks: An Ecosystem for zkSNARKs," https://arkworks.rs
- [FROST] C. Komlo and I. Goldberg, "FROST: Flexible Round-Optimized Schnorr Threshold Signatures," SAC 2020
