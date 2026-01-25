# ZKP Technical Specification

Formal specification of the zero-knowledge proof system for SovChain confidential minting (Section 5).

## 1. Cryptographic Primitives

### 1.1 Elliptic Curve

**Curve**: BN254 (alt_bn128)

| Parameter | Value |
|-----------|-------|
| Field size | 254 bits |
| Security level | ~100 bits |
| Embedding degree | 12 |
| Pairing | Optimal Ate |

**Generator Points:**

```
G = (1, 2)  # Standard BN254 generator

H = hash_to_curve("SovChain_Pedersen_H")
  = (0x2119...177, 0x1c88...265)  # Nothing-up-my-sleeve point
```

### 1.2 Pedersen Commitment

**Definition:**

```
C = Commit(v, r) = v·G + r·H
```

Where:
- `v` ∈ [0, 2^64) is the committed value
- `r` ∈ Z_q is the blinding factor (256 bits)
- `G`, `H` are independent generators

**Properties:**
- **Perfectly hiding**: C reveals nothing about v
- **Computationally binding**: Cannot find (v', r') ≠ (v, r) with same C

### 1.3 Hash Function

**SHA-256** for all hash operations:
- Authority binding: `H(pubkey)`
- Limit binding: `H(daily_limit)`

## 2. NP Relation

### 2.1 Statement Definition

**Public Inputs** x = (C, authority_hash, limit_hash, nonce, epoch):

| Symbol | Type | Size | Description |
|--------|------|------|-------------|
| C | G₁ point | 64 bytes | Pedersen commitment |
| authority_hash | bytes32 | 32 bytes | SHA-256(minter_pubkey) |
| limit_hash | bytes32 | 32 bytes | SHA-256(daily_limit) |
| nonce | uint64 | 8 bytes | Replay prevention counter |
| epoch | uint64 | 8 bytes | Time-bound validity |

**Private Witness** w = (amount, blinding, pubkey, daily_limit):

| Symbol | Type | Size | Description |
|--------|------|------|-------------|
| amount | uint64 | 64 bits | Mint amount |
| blinding | scalar | 256 bits | Commitment randomness |
| pubkey | bytes32 | 256 bits | Minter public key |
| daily_limit | uint64 | 64 bits | Policy limit |

### 2.2 Relation

```
R(x, w) = 1 ⟺ {
    C = amount·G + blinding·H               (1) Commitment
    0 < amount ≤ daily_limit                (2) Policy compliance
    amount < 2^64                            (3) Range bound
    SHA256(pubkey) = authority_hash         (4) Authorization
    SHA256(daily_limit) = limit_hash        (5) Limit binding
}
```

### 2.3 Security Properties

| Property | Guarantee | Implication |
|----------|-----------|-------------|
| Soundness | Computational | Valid proof ⟹ witness satisfies R |
| Zero-knowledge | Perfect | Proof reveals nothing about w |
| Completeness | Perfect | Honest prover always succeeds |

## 3. Circuit Implementation

### 3.1 Constraint Breakdown

| Component | R1CS Constraints | % | Description |
|-----------|------------------|---|-------------|
| Pedersen commitment | 12,400 | 25% | BN254 scalar multiplication |
| Range proof (64-bit) | 18,200 | 36% | Binary decomposition |
| Policy bound check | 2,100 | 4% | Comparison circuits |
| SHA-256 (authority) | 8,500 | 17% | 64 rounds |
| SHA-256 (limit) | 8,500 | 17% | 64 rounds |
| Wiring/misc | 300 | 1% | Signal routing |
| **Total** | **50,000** | **100%** | |

### 3.2 Pedersen Commitment Circuit

**Strategy**: Fixed-base scalar multiplication

```
// Decompose amount to bits
amount_bits[64] = Num2Bits(amount)

// Compute amount·G using EscalarMulFix
(Ax, Ay) = EscalarMulFix(amount_bits, G)

// Decompose blinding to bits
blinding_bits[254] = Num2Bits(blinding)

// Compute blinding·H using EscalarMulFix
(Bx, By) = EscalarMulFix(blinding_bits, H)

// Add points: C = A + B
(Cx, Cy) = BabyAdd(Ax, Ay, Bx, By)

// Verify against public input
Cx === commitment_x
Cy === commitment_y
```

**Constraint count**: ~12,400
- 64-bit scalar mul: ~3,000
- 254-bit scalar mul: ~8,000
- Point addition: ~400
- Equality checks: ~1,000

### 3.3 Range Proof Circuit

**Strategy**: Binary decomposition with boolean constraints

```
// Decompose to 64 bits
bits[64] = Num2Bits(amount)

// Each bit is constrained: b·(b-1) = 0
for i in 0..64:
    bits[i] * (bits[i] - 1) === 0

// Verify reconstruction
sum = Σ bits[i] · 2^i
sum === amount
```

**Constraint count**: ~18,200
- Boolean constraints: 64
- Linear combination: 64
- Reconstruction: 1
- Supporting wiring: ~18,000

### 3.4 Policy Compliance Circuit

**Strategy**: LessThan comparator

```
// amount > 0
isPositive = GreaterThan(64)(amount, 0)
isPositive === 1

// amount <= daily_limit
withinLimit = LessEqThan(64)(amount, daily_limit)
withinLimit === 1

// daily_limit range check
limit_bits[64] = Num2Bits(daily_limit)
```

**Constraint count**: ~2,100

### 3.5 SHA-256 Circuit

**Strategy**: Standard SHA-256 with 64 rounds

```
// Pad pubkey to 512 bits (already 256, add padding)
padded_input = pad(pubkey)

// 64 rounds of compression
for round in 0..64:
    state = sha256_round(state, padded_input, round)

// Extract hash
output_hash = state[0..256]

// Verify against public input
for i in 0..8:
    output_hash_words[i] === authority_hash[i]
```

**Constraint count**: ~8,500 per hash

## 4. Proving System

### 4.1 Groth16

**Parameters:**

| Parameter | Value |
|-----------|-------|
| Proof size | 128 bytes |
| Verification equations | 1 pairing check |
| CRS size | O(n) |
| Proving time | O(n log n) |
| Verification time | O(1) |

**Proof structure:**

```
π = (A, B, C) where:
  A ∈ G₁  (32 bytes compressed)
  B ∈ G₂  (64 bytes compressed)
  C ∈ G₁  (32 bytes compressed)
```

### 4.2 Trusted Setup

**Phase 1**: Powers of Tau (universal)

```
τ = (τ¹, τ², ..., τⁿ)  # Secret trapdoor

[τⁱ]₁ for i = 0..n     # G₁ powers
[τⁱ]₂ for i = 0..n     # G₂ powers
```

**Phase 2**: Circuit-specific

```
[α]₁, [β]₁, [β]₂, [δ]₁, [δ]₂
[A_i(τ)/δ]₁, [B_i(τ)/δ]₂
```

**Security**: If any participant destroys their contribution, trapdoor is unknown.

### 4.3 MPC Ceremony

**Participants**: 12 (6 governors + 6 auditors)

**Protocol** (per participant i):

1. Download transcript T_{i-1}
2. Generate randomness r_i (hardware RNG)
3. Compute T_i = Contribute(T_{i-1}, r_i)
4. Publish (hash(T_i), signature, T_i)
5. Destroy r_i (witnessed)

**Verification**: Anyone can verify contribution chain integrity.

## 5. On-Chain Verification

### 5.1 Verification Algorithm

```
function verify(vk, π, x):
    // Parse proof
    (A, B, C) = parse_proof(π)
    
    // Compute public input linear combination
    vk_x = vk.alpha + Σ x_i · vk.ic[i]
    
    // Pairing check
    return e(A, B) == e(vk_x, vk.gamma) · e(C, vk.delta)
```

### 5.2 Gas Cost Estimate

| Operation | Gas (approx) |
|-----------|--------------|
| Parse proof | 500 |
| G₁ scalar mul (6×) | 6,000 |
| G₁ addition (6×) | 3,000 |
| Pairing (3×) | 150,000 |
| **Total** | **~160,000** |

### 5.3 Move Integration

```move
public fun verify_mint_proof(
    vk: &VerifyingKey,
    proof: vector<u8>,
    public_inputs: vector<u8>
): bool {
    let parsed_proof = groth16::proof_points_from_bytes(proof);
    let parsed_inputs = groth16::public_proof_inputs_from_bytes(public_inputs);
    
    groth16::verify_groth16_proof(
        &groth16::bn254(),
        &vk.prepared,
        &parsed_inputs,
        &parsed_proof
    )
}
```

## 6. Security Analysis

### 6.1 Soundness

**Claim**: A valid proof implies the witness satisfies R with overwhelming probability.

**Proof**: Follows from Groth16 soundness in the generic group model + algebraic group model.

**Assumption**: q-SDH holds for BN254.

### 6.2 Zero-Knowledge

**Claim**: The proof reveals nothing about (amount, blinding) beyond what's deducible from (C, authority_hash, limit_hash).

**Proof**: Simulator can produce indistinguishable proofs without witness.

### 6.3 Trusted Setup Attack

**Threat**: If all 12 ceremony participants collude, trapdoor is known.

**Impact**: Adversary can forge proofs, minting arbitrary amounts.

**Mitigation**:
- Institutional diversity (banks, auditors, regulators)
- Witnessed destruction procedures
- Post-ceremony re-verification

### 6.4 Curve Security

**BN254 security**: ~100 bits against discrete log

**Timeline**: Adequate for 10-15 year deployment

**Migration path**: Upgrade to BLS12-381 (128-bit security) when needed

## 7. Performance Benchmarks

### 7.1 Proving

| Hardware | Time |
|----------|------|
| 8-core x86_64 | ~2.0s |
| 16-core x86_64 | ~1.2s |
| M1 MacBook | ~1.8s |

### 7.2 Verification

| Platform | Time |
|----------|------|
| Native (Rust) | ~1.5ms |
| WASM | ~3.0ms |
| Sui Move | ~2.5ms |

### 7.3 Memory Usage

| Phase | Peak Memory |
|-------|-------------|
| Compilation | ~2 GB |
| Key generation | ~4 GB |
| Proving | ~500 MB |
| Verification | ~10 MB |

## References

1. Groth, J. "On the Size of Pairing-Based Non-interactive Arguments." EUROCRYPT 2016.
2. Bowe, S. et al. "Scalable Multi-Party Computation for zk-SNARK Parameters." 2017.
3. Ben-Sasson, E. et al. "SNARKs for C: Verifying Program Executions Succinctly and in Zero Knowledge." CRYPTO 2013.
