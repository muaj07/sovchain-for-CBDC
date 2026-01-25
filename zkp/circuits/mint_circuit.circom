/*
 * SovChain Confidential Minting Circuit
 * =====================================
 * 
 * Groth16 circuit for privacy-preserving CBDC minting.
 * Implements the NP relation from Section 5.4 of the SovChain paper.
 * 
 * Public inputs (x):
 *   - commitment_x, commitment_y: Pedersen commitment C (BN254 point)
 *   - authority_hash[8]: SHA-256 of authorized minter pubkey
 *   - limit_hash[8]: SHA-256 of current daily limit
 *   - nonce: Monotonic counter (64-bit)
 *   - epoch: Current epoch number (64-bit)
 * 
 * Private witness (w):
 *   - amount: Mint amount (64-bit)
 *   - blinding: Commitment randomness (256-bit)
 *   - pubkey[8]: Minter public key (256-bit as 8x32-bit words)
 *   - daily_limit: Policy limit (64-bit)
 * 
 * Constraint budget (Table 15):
 *   - Pedersen commitment: ~12,400
 *   - Range proof (64-bit): ~18,200
 *   - Policy bound check: ~2,100
 *   - SHA-256 (authority): ~8,500
 *   - SHA-256 (limit): ~8,500
 *   - Miscellaneous: ~300
 *   - Total: ~50,000 R1CS constraints
 * 
 * Reference: SovChain paper, Section 5.4
 */

pragma circom 2.1.0;

include "pedersen.circom";
include "range_proof.circom";

// SHA-256 from circomlib
include "circomlib/circuits/sha256/sha256.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

/*
 * Main minting circuit template
 */
template MintCircuit() {
    // =========================================================================
    // PUBLIC INPUTS
    // =========================================================================
    
    // Pedersen commitment C = amount*G + blinding*H (BN254 affine coordinates)
    signal input commitment_x;
    signal input commitment_y;
    
    // SHA-256(pubkey) - authority binding (8 x 32-bit words)
    signal input authority_hash[8];
    
    // SHA-256(daily_limit) - limit binding (8 x 32-bit words)
    signal input limit_hash[8];
    
    // Replay prevention
    signal input nonce;
    signal input epoch;
    
    // =========================================================================
    // PRIVATE WITNESS
    // =========================================================================
    
    // Mint amount (64-bit unsigned)
    signal input amount;
    
    // Commitment blinding factor (256-bit scalar)
    signal input blinding;
    
    // Minter public key (256-bit, as 8 x 32-bit words)
    signal input pubkey[8];
    
    // Policy daily limit (64-bit unsigned)
    signal input daily_limit;
    
    // =========================================================================
    // CONSTRAINT 1: PEDERSEN COMMITMENT VERIFICATION
    // Verify that C = amount*G + blinding*H
    // ~12,400 constraints
    // =========================================================================
    
    component pedersen = PedersenCommitment();
    pedersen.amount <== amount;
    pedersen.blinding <== blinding;
    
    // Verify commitment matches public input
    pedersen.out_x === commitment_x;
    pedersen.out_y === commitment_y;
    
    // =========================================================================
    // CONSTRAINT 2: RANGE PROOF (64-bit)
    // Prove amount < 2^64
    // ~18,200 constraints
    // =========================================================================
    
    component range_amount = RangeProof64();
    range_amount.value <== amount;
    
    // =========================================================================
    // CONSTRAINT 3: POLICY BOUND CHECK
    // Prove 0 < amount <= daily_limit
    // ~2,100 constraints
    // =========================================================================
    
    // amount > 0
    component is_positive = GreaterThan(64);
    is_positive.in[0] <== amount;
    is_positive.in[1] <== 0;
    is_positive.out === 1;
    
    // amount <= daily_limit
    component within_limit = LessEqThan(64);
    within_limit.in[0] <== amount;
    within_limit.in[1] <== daily_limit;
    within_limit.out === 1;
    
    // daily_limit also needs range proof for soundness
    component range_limit = RangeProof64();
    range_limit.value <== daily_limit;
    
    // =========================================================================
    // CONSTRAINT 4: AUTHORITY HASH VERIFICATION
    // Verify H(pubkey) = authority_hash
    // ~8,500 constraints
    // =========================================================================
    
    // Convert pubkey words to bits for SHA-256
    component pubkey_bits[8];
    for (var i = 0; i < 8; i++) {
        pubkey_bits[i] = Num2Bits(32);
        pubkey_bits[i].in <== pubkey[i];
    }
    
    // Compute SHA-256(pubkey)
    component sha_authority = Sha256(256);
    for (var i = 0; i < 8; i++) {
        for (var j = 0; j < 32; j++) {
            sha_authority.in[i * 32 + j] <== pubkey_bits[i].out[31 - j];
        }
    }
    
    // Convert hash output to 32-bit words and verify
    component auth_hash_words[8];
    for (var i = 0; i < 8; i++) {
        auth_hash_words[i] = Bits2Num(32);
        for (var j = 0; j < 32; j++) {
            auth_hash_words[i].in[j] <== sha_authority.out[i * 32 + (31 - j)];
        }
        auth_hash_words[i].out === authority_hash[i];
    }
    
    // =========================================================================
    // CONSTRAINT 5: LIMIT HASH VERIFICATION
    // Verify H(daily_limit) = limit_hash
    // ~8,500 constraints
    // =========================================================================
    
    // Convert daily_limit to bits (64-bit, padded to 256 for SHA-256)
    component limit_bits = Num2Bits(64);
    limit_bits.in <== daily_limit;
    
    // Compute SHA-256(daily_limit) with zero-padding
    component sha_limit = Sha256(256);
    
    // First 192 bits are zero (padding)
    for (var i = 0; i < 192; i++) {
        sha_limit.in[i] <== 0;
    }
    
    // Last 64 bits are the limit (big-endian)
    for (var i = 0; i < 64; i++) {
        sha_limit.in[192 + i] <== limit_bits.out[63 - i];
    }
    
    // Convert hash output to 32-bit words and verify
    component limit_hash_words[8];
    for (var i = 0; i < 8; i++) {
        limit_hash_words[i] = Bits2Num(32);
        for (var j = 0; j < 32; j++) {
            limit_hash_words[i].in[j] <== sha_limit.out[i * 32 + (31 - j)];
        }
        limit_hash_words[i].out === limit_hash[i];
    }
    
    // =========================================================================
    // IMPLICIT CONSTRAINTS
    // nonce and epoch are public inputs bound to the proof but not
    // checked inside the circuit - replay prevention is enforced on-chain
    // by the Move contract (monotonic nonce check, epoch validity)
    // =========================================================================
    
    // These signals are included to bind the proof to specific nonce/epoch
    // The constraint is trivial (0 = 0) but ensures they're part of public inputs
    signal nonce_check;
    signal epoch_check;
    nonce_check <== nonce * 0;
    epoch_check <== epoch * 0;
}

/*
 * Main component instantiation
 */
component main {public [
    commitment_x,
    commitment_y,
    authority_hash,
    limit_hash,
    nonce,
    epoch
]} = MintCircuit();
