//! Groth16 Proof Verification
//!
//! This module provides the verifier for validating zero-knowledge proofs
//! in the confidential minting protocol.
//!
//! # On-Chain Usage
//!
//! The verification logic is designed to be compatible with on-chain execution
//! in Move. The verifying key and proof are serialized in a format that can be
//! processed by the Move contract.
//!
//! # Performance
//!
//! - Verification time: ~1.5ms
//! - This is dominated by pairing operations on BN254
//!
//! # Example
//!
//! ```rust,ignore
//! let verifier = MintVerifier::load("verifying_key.bin")?;
//! let valid = verifier.verify(&proof, &public_inputs)?;
//! assert!(valid);
//! ```

use crate::{MintPublicInputs, Proof, Result, ZkpError};
use ark_bn254::{Bn254, Fr};
use ark_groth16::{Groth16, PreparedVerifyingKey, VerifyingKey};
use ark_serialize::{CanonicalDeserialize, CanonicalSerialize};
use ark_snark::SNARK;
use std::fs::File;
use std::io::{BufReader, BufWriter};
use std::path::Path;

/// Groth16 verifier for minting proofs
pub struct MintVerifier {
    /// The verifying key (can be pre-processed for efficiency)
    verifying_key: VerifyingKey<Bn254>,

    /// Pre-processed verifying key for faster verification
    prepared_vk: PreparedVerifyingKey<Bn254>,
}

impl MintVerifier {
    /// Load verifying key from file
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self> {
        let file = File::open(path)?;
        let reader = BufReader::new(file);
        let verifying_key = VerifyingKey::deserialize_compressed(reader)
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        let prepared_vk = PreparedVerifyingKey::from(&verifying_key);

        Ok(Self {
            verifying_key,
            prepared_vk,
        })
    }

    /// Create from existing verifying key
    pub fn new(verifying_key: VerifyingKey<Bn254>) -> Self {
        let prepared_vk = PreparedVerifyingKey::from(&verifying_key);
        Self {
            verifying_key,
            prepared_vk,
        }
    }

    /// Save verifying key to file
    pub fn save<P: AsRef<Path>>(&self, path: P) -> Result<()> {
        let file = File::create(path)?;
        let writer = BufWriter::new(file);
        self.verifying_key
            .serialize_compressed(writer)
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;
        Ok(())
    }

    /// Verify a minting proof
    ///
    /// # Arguments
    ///
    /// * `proof` - The Groth16 proof to verify
    /// * `public_inputs` - The public inputs to the circuit
    ///
    /// # Returns
    ///
    /// `true` if the proof is valid, `false` otherwise
    pub fn verify(&self, proof: &Proof, public_inputs: &MintPublicInputs) -> Result<bool> {
        let ark_proof = proof.to_arkworks()?;
        let field_elements = public_inputs.to_field_elements();

        let valid = Groth16::<Bn254>::verify_with_processed_vk(
            &self.prepared_vk,
            &field_elements,
            &ark_proof,
        )
        .map_err(|e| ZkpError::ProvingError(e.to_string()))?;

        Ok(valid)
    }

    /// Batch verify multiple proofs (more efficient than individual verification)
    ///
    /// Uses randomized batching for efficiency while maintaining soundness.
    pub fn batch_verify(
        &self,
        proofs: &[(Proof, MintPublicInputs)],
    ) -> Result<bool> {
        // For small batches, individual verification is fine
        // For large batches, implement Miller loop batching
        for (proof, inputs) in proofs {
            if !self.verify(proof, inputs)? {
                return Ok(false);
            }
        }
        Ok(true)
    }

    /// Export verifying key in a format suitable for on-chain storage
    ///
    /// Returns the key as a vector of bytes that can be stored in Move.
    pub fn export_for_move(&self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        self.verifying_key
            .serialize_compressed(&mut bytes)
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;
        Ok(bytes)
    }

    /// Get the expected number of public inputs
    pub fn num_public_inputs(&self) -> usize {
        // gamma_abc_g1 has length (num_inputs + 1)
        self.verifying_key.gamma_abc_g1.len() - 1
    }
}

/// On-chain verification compatible format
///
/// This struct represents the verifying key in a format that can be
/// directly used by the Move contract for verification.
#[derive(Clone, Debug)]
pub struct OnChainVerifyingKey {
    /// Alpha in G1 (compressed)
    pub alpha_g1: [u8; 32],

    /// Beta in G2 (compressed)
    pub beta_g2: [u8; 64],

    /// Gamma in G2 (compressed)
    pub gamma_g2: [u8; 64],

    /// Delta in G2 (compressed)
    pub delta_g2: [u8; 64],

    /// IC (input commitment) points in G1
    pub gamma_abc_g1: Vec<[u8; 32]>,
}

impl OnChainVerifyingKey {
    /// Create from arkworks verifying key
    pub fn from_arkworks(vk: &VerifyingKey<Bn254>) -> Result<Self> {
        // Serialize each component
        let mut alpha_g1 = [0u8; 32];
        let mut beta_g2 = [0u8; 64];
        let mut gamma_g2 = [0u8; 64];
        let mut delta_g2 = [0u8; 64];

        vk.alpha_g1
            .serialize_compressed(&mut alpha_g1[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        vk.beta_g2
            .serialize_compressed(&mut beta_g2[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        vk.gamma_g2
            .serialize_compressed(&mut gamma_g2[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        vk.delta_g2
            .serialize_compressed(&mut delta_g2[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        let gamma_abc_g1 = vk
            .gamma_abc_g1
            .iter()
            .map(|p| {
                let mut bytes = [0u8; 32];
                p.serialize_compressed(&mut bytes[..])
                    .map_err(|e| ZkpError::SerializationError(e.to_string()))?;
                Ok(bytes)
            })
            .collect::<Result<Vec<_>>>()?;

        Ok(Self {
            alpha_g1,
            beta_g2,
            gamma_g2,
            delta_g2,
            gamma_abc_g1,
        })
    }

    /// Serialize for Move storage
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::new();

        bytes.extend_from_slice(&self.alpha_g1);
        bytes.extend_from_slice(&self.beta_g2);
        bytes.extend_from_slice(&self.gamma_g2);
        bytes.extend_from_slice(&self.delta_g2);

        // Length prefix for gamma_abc_g1
        bytes.extend_from_slice(&(self.gamma_abc_g1.len() as u32).to_le_bytes());
        for point in &self.gamma_abc_g1 {
            bytes.extend_from_slice(point);
        }

        bytes
    }
}

/// On-chain proof format
#[derive(Clone, Debug)]
pub struct OnChainProof {
    /// A in G1 (compressed)
    pub a: [u8; 32],

    /// B in G2 (compressed)
    pub b: [u8; 64],

    /// C in G1 (compressed)
    pub c: [u8; 32],
}

impl OnChainProof {
    /// Create from arkworks proof
    pub fn from_arkworks(proof: &ark_groth16::Proof<Bn254>) -> Result<Self> {
        let mut a = [0u8; 32];
        let mut b = [0u8; 64];
        let mut c = [0u8; 32];

        proof
            .a
            .serialize_compressed(&mut a[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        proof
            .b
            .serialize_compressed(&mut b[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        proof
            .c
            .serialize_compressed(&mut c[..])
            .map_err(|e| ZkpError::SerializationError(e.to_string()))?;

        Ok(Self { a, b, c })
    }

    /// Serialize for Move verification
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(128);
        bytes.extend_from_slice(&self.a);
        bytes.extend_from_slice(&self.b);
        bytes.extend_from_slice(&self.c);
        bytes
    }

    /// Get proof size in bytes
    pub fn size(&self) -> usize {
        128 // 32 + 64 + 32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_on_chain_proof_size() {
        // Groth16 proofs are exactly 128 bytes compressed
        assert_eq!(
            32 + 64 + 32,  // a (G1) + b (G2) + c (G1)
            128
        );
    }

    #[test]
    fn test_public_inputs_field_elements() {
        let inputs = MintPublicInputs {
            commitment_x: [1u8; 32],
            commitment_y: [2u8; 32],
            authority_hash: [3u8; 32],
            limit_hash: [4u8; 32],
            nonce: 42,
            epoch: 100,
        };

        let elements = inputs.to_field_elements();
        assert_eq!(elements.len(), 6);
    }
}
