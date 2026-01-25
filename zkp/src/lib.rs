//! # SovChain ZKP Framework
//!
//! Zero-Knowledge Proof implementation for confidential CBDC minting.
//!
//! This crate provides:
//! - Groth16 proof generation for the minting circuit
//! - On-chain compatible verification
//! - Serialization for Move integration
//!
//! ## Example
//!
//! ```rust,ignore
//! use sovchain_zkp::{MintProver, MintVerifier, MintWitness};
//!
//! // Generate witness
//! let witness = MintWitness {
//!     amount: 1_000_000,
//!     blinding: random_scalar(),
//!     pubkey: minter_pubkey,
//!     daily_limit: 10_000_000,
//! };
//!
//! // Generate proof
//! let prover = MintProver::load("proving_key.bin")?;
//! let (proof, public_inputs) = prover.prove(&witness)?;
//!
//! // Verify
//! let verifier = MintVerifier::load("verifying_key.bin")?;
//! assert!(verifier.verify(&proof, &public_inputs)?);
//! ```
//!
//! ## Circuit Specification
//!
//! The minting circuit proves the following NP relation:
//!
//! ```text
//! R(x, w) = 1 ⟺ {
//!     C = amount·G + blinding·H        (Pedersen commitment)
//!     0 < amount ≤ daily_limit         (policy bound)
//!     amount < 2^64                     (range proof)
//!     H(pubkey) = authority_hash       (authorization)
//!     H(daily_limit) = limit_hash      (limit binding)
//! }
//! ```
//!
//! ## Performance
//!
//! | Operation | Time | Size |
//! |-----------|------|------|
//! | Prove | ~2s | - |
//! | Verify | ~1.5ms | - |
//! | Proof size | - | 128 bytes |

pub mod prover;
pub mod verifier;

use ark_bn254::{Bn254, Fr, G1Projective, G2Projective};
use ark_ec::pairing::Pairing;
use ark_ff::PrimeField;
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

/// Re-exports
pub use prover::MintProver;
pub use verifier::MintVerifier;

/// ZKP-related errors
#[derive(Error, Debug)]
pub enum ZkpError {
    #[error("Invalid witness: {0}")]
    InvalidWitness(String),

    #[error("Proof generation failed: {0}")]
    ProvingError(String),

    #[error("Proof verification failed")]
    VerificationFailed,

    #[error("Serialization error: {0}")]
    SerializationError(String),

    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("Invalid public input")]
    InvalidPublicInput,
}

pub type Result<T> = std::result::Result<T, ZkpError>;

/// Private witness for the minting circuit
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MintWitness {
    /// Mint amount (64-bit)
    pub amount: u64,

    /// Commitment blinding factor (256-bit scalar)
    pub blinding: [u8; 32],

    /// Minter public key (256-bit)
    pub pubkey: [u8; 32],

    /// Policy daily limit (64-bit)
    pub daily_limit: u64,
}

impl MintWitness {
    /// Create a new witness with random blinding factor
    pub fn new(amount: u64, pubkey: [u8; 32], daily_limit: u64) -> Self {
        use rand::RngCore;
        let mut blinding = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut blinding);

        Self {
            amount,
            blinding,
            pubkey,
            daily_limit,
        }
    }

    /// Validate witness constraints
    pub fn validate(&self) -> Result<()> {
        if self.amount == 0 {
            return Err(ZkpError::InvalidWitness("amount must be positive".into()));
        }
        if self.amount > self.daily_limit {
            return Err(ZkpError::InvalidWitness(
                "amount exceeds daily limit".into(),
            ));
        }
        Ok(())
    }

    /// Compute the Pedersen commitment C = amount*G + blinding*H
    pub fn compute_commitment(&self) -> (Fr, Fr) {
        // In production, this would use actual BN254 elliptic curve operations
        // For this reference implementation, we return placeholder values
        // The actual computation is done in the circuit
        unimplemented!("Pedersen commitment requires curve operations")
    }

    /// Compute SHA-256(pubkey) for authority binding
    pub fn compute_authority_hash(&self) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(&self.pubkey);
        hasher.finalize().into()
    }

    /// Compute SHA-256(daily_limit) for limit binding
    pub fn compute_limit_hash(&self) -> [u8; 32] {
        let mut hasher = Sha256::new();
        // Zero-pad to 32 bytes, big-endian
        let mut padded = [0u8; 32];
        padded[24..].copy_from_slice(&self.daily_limit.to_be_bytes());
        hasher.update(&padded);
        hasher.finalize().into()
    }
}

/// Public inputs for the minting circuit
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MintPublicInputs {
    /// Pedersen commitment x-coordinate
    pub commitment_x: [u8; 32],

    /// Pedersen commitment y-coordinate
    pub commitment_y: [u8; 32],

    /// SHA-256(pubkey)
    pub authority_hash: [u8; 32],

    /// SHA-256(daily_limit)
    pub limit_hash: [u8; 32],

    /// Monotonic nonce for replay prevention
    pub nonce: u64,

    /// Current epoch number
    pub epoch: u64,
}

impl MintPublicInputs {
    /// Serialize for on-chain verification
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(144);
        bytes.extend_from_slice(&self.commitment_x);
        bytes.extend_from_slice(&self.commitment_y);
        bytes.extend_from_slice(&self.authority_hash);
        bytes.extend_from_slice(&self.limit_hash);
        bytes.extend_from_slice(&self.nonce.to_le_bytes());
        bytes.extend_from_slice(&self.epoch.to_le_bytes());
        bytes
    }

    /// Deserialize from bytes
    pub fn from_bytes(bytes: &[u8]) -> Result<Self> {
        if bytes.len() != 144 {
            return Err(ZkpError::InvalidPublicInput);
        }

        Ok(Self {
            commitment_x: bytes[0..32].try_into().unwrap(),
            commitment_y: bytes[32..64].try_into().unwrap(),
            authority_hash: bytes[64..96].try_into().unwrap(),
            limit_hash: bytes[96..128].try_into().unwrap(),
            nonce: u64::from_le_bytes(bytes[128..136].try_into().unwrap()),
            epoch: u64::from_le_bytes(bytes[136..144].try_into().unwrap()),
        })
    }

    /// Convert to field elements for circuit verification
    pub fn to_field_elements(&self) -> Vec<Fr> {
        // Convert each 32-byte array to a field element
        let mut elements = Vec::with_capacity(6);

        // Helper to convert bytes to field element
        let to_fr = |bytes: &[u8; 32]| -> Fr { Fr::from_le_bytes_mod_order(bytes) };

        elements.push(to_fr(&self.commitment_x));
        elements.push(to_fr(&self.commitment_y));
        elements.push(to_fr(&self.authority_hash));
        elements.push(to_fr(&self.limit_hash));
        elements.push(Fr::from(self.nonce));
        elements.push(Fr::from(self.epoch));

        elements
    }
}

/// Groth16 proof (128 bytes compressed)
#[derive(Clone, Debug)]
pub struct Proof {
    /// Serialized proof bytes
    pub bytes: Vec<u8>,
}

impl Proof {
    /// Create from arkworks proof
    pub fn from_arkworks(proof: &ark_groth16::Proof<Bn254>) -> Result<Self> {
        let mut bytes = Vec::new();
        proof
            .serialize_compressed(&mut bytes)
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;
        Ok(Self { bytes })
    }

    /// Convert to arkworks proof
    pub fn to_arkworks(&self) -> Result<ark_groth16::Proof<Bn254>> {
        ark_groth16::Proof::deserialize_compressed(&self.bytes[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))
    }

    /// Get proof size in bytes
    pub fn size(&self) -> usize {
        self.bytes.len()
    }

    /// Serialize for on-chain storage
    pub fn to_bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// Deserialize from bytes
    pub fn from_bytes(bytes: Vec<u8>) -> Self {
        Self { bytes }
    }
}

/// Circuit constraint count (from Table 15)
pub mod constraints {
    pub const PEDERSEN_COMMITMENT: usize = 12_400;
    pub const RANGE_PROOF_64: usize = 18_200;
    pub const POLICY_CHECK: usize = 2_100;
    pub const SHA256_AUTHORITY: usize = 8_500;
    pub const SHA256_LIMIT: usize = 8_500;
    pub const MISC: usize = 300;

    pub const TOTAL: usize = PEDERSEN_COMMITMENT
        + RANGE_PROOF_64
        + POLICY_CHECK
        + SHA256_AUTHORITY
        + SHA256_LIMIT
        + MISC;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_constraint_count() {
        assert_eq!(constraints::TOTAL, 50_000);
    }

    #[test]
    fn test_witness_validation() {
        let witness = MintWitness {
            amount: 1_000_000,
            blinding: [0u8; 32],
            pubkey: [1u8; 32],
            daily_limit: 10_000_000,
        };
        assert!(witness.validate().is_ok());

        let invalid = MintWitness {
            amount: 0,
            ..witness.clone()
        };
        assert!(invalid.validate().is_err());

        let over_limit = MintWitness {
            amount: 20_000_000,
            ..witness
        };
        assert!(over_limit.validate().is_err());
    }

    #[test]
    fn test_authority_hash() {
        let witness = MintWitness {
            amount: 1_000_000,
            blinding: [0u8; 32],
            pubkey: [0xab; 32],
            daily_limit: 10_000_000,
        };

        let hash = witness.compute_authority_hash();
        assert_eq!(hash.len(), 32);

        // Same pubkey should give same hash
        let hash2 = witness.compute_authority_hash();
        assert_eq!(hash, hash2);
    }

    #[test]
    fn test_public_inputs_serialization() {
        let inputs = MintPublicInputs {
            commitment_x: [1u8; 32],
            commitment_y: [2u8; 32],
            authority_hash: [3u8; 32],
            limit_hash: [4u8; 32],
            nonce: 42,
            epoch: 100,
        };

        let bytes = inputs.to_bytes();
        assert_eq!(bytes.len(), 144);

        let recovered = MintPublicInputs::from_bytes(&bytes).unwrap();
        assert_eq!(recovered.nonce, 42);
        assert_eq!(recovered.epoch, 100);
    }
}
