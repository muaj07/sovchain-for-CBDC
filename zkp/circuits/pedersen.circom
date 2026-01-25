/*
 * Pedersen Commitment Gadget for BN254
 * =====================================
 * 
 * Computes C = amount * G + blinding * H where:
 *   - G is the BN254 generator point
 *   - H is an independently chosen base point (nothing-up-my-sleeve)
 *   - amount is a 64-bit value
 *   - blinding is a 256-bit scalar
 * 
 * The commitment is computationally binding and perfectly hiding.
 * 
 * Constraint count: ~12,400
 * 
 * Reference: SovChain paper, Section 5.4
 */

pragma circom 2.1.0;

include "circomlib/circuits/escalarmulfix.circom";
include "circomlib/circuits/escalarmulany.circom";
include "circomlib/circuits/babyjub.circom";
include "circomlib/circuits/bitify.circom";

/*
 * BN254 Generator Point G (standard)
 * These are the BabyJubJub base point coordinates
 */
function getGeneratorG() {
    return [
        5299619240641551281634865583518297030282874472190772894086521144482721001553,
        16950150798460657717958625567821834550301663161624707787222815936182638968203
    ];
}

/*
 * Independent Base Point H (nothing-up-my-sleeve)
 * Derived as H = hash_to_curve("SovChain_Pedersen_H")
 */
function getBasePointH() {
    return [
        15112221349535807912866137220509078935008241517919253295095014876837728449177,
        8142132682448941793285283228962552395738629330747836901965167458809664746265
    ];
}

/*
 * Pedersen Commitment Template
 * 
 * Inputs:
 *   - amount: 64-bit unsigned integer
 *   - blinding: 256-bit scalar
 * 
 * Outputs:
 *   - out_x, out_y: Affine coordinates of commitment point
 */
template PedersenCommitment() {
    signal input amount;
    signal input blinding;
    
    signal output out_x;
    signal output out_y;
    
    // Get base points
    var G[2] = getGeneratorG();
    var H[2] = getBasePointH();
    
    // =========================================================================
    // Step 1: Compute amount * G using fixed-base scalar multiplication
    // This is more efficient when the base point is known at compile time
    // ~3,000 constraints for 64-bit scalar
    // =========================================================================
    
    // Convert amount to bits
    component amount_bits = Num2Bits(64);
    amount_bits.in <== amount;
    
    // Fixed-base multiplication: amount * G
    // We use EscalarMulFix which is optimized for fixed base points
    component mulG = EscalarMulFix(64, G);
    for (var i = 0; i < 64; i++) {
        mulG.e[i] <== amount_bits.out[i];
    }
    
    // =========================================================================
    // Step 2: Compute blinding * H using fixed-base scalar multiplication
    // ~8,000 constraints for 256-bit scalar
    // =========================================================================
    
    // Convert blinding to bits
    component blinding_bits = Num2Bits(254);  // BN254 scalar field
    blinding_bits.in <== blinding;
    
    // Fixed-base multiplication: blinding * H
    component mulH = EscalarMulFix(254, H);
    for (var i = 0; i < 254; i++) {
        mulH.e[i] <== blinding_bits.out[i];
    }
    
    // =========================================================================
    // Step 3: Add the two points: C = (amount * G) + (blinding * H)
    // ~400 constraints for point addition
    // =========================================================================
    
    component adder = BabyAdd();
    adder.x1 <== mulG.out[0];
    adder.y1 <== mulG.out[1];
    adder.x2 <== mulH.out[0];
    adder.y2 <== mulH.out[1];
    
    // Output the commitment
    out_x <== adder.xout;
    out_y <== adder.yout;
}

/*
 * Pedersen commitment verification (for use in other circuits)
 * Verifies that a given point is a valid commitment to known values
 */
template VerifyPedersenCommitment() {
    signal input amount;
    signal input blinding;
    signal input expected_x;
    signal input expected_y;
    
    signal output valid;
    
    component pedersen = PedersenCommitment();
    pedersen.amount <== amount;
    pedersen.blinding <== blinding;
    
    // Check equality
    component eq_x = IsEqual();
    eq_x.in[0] <== pedersen.out_x;
    eq_x.in[1] <== expected_x;
    
    component eq_y = IsEqual();
    eq_y.in[0] <== pedersen.out_y;
    eq_y.in[1] <== expected_y;
    
    valid <== eq_x.out * eq_y.out;
}

/*
 * Commitment opening proof
 * Proves knowledge of (amount, blinding) that opens commitment C
 */
template CommitmentOpening() {
    signal input commitment_x;
    signal input commitment_y;
    signal input amount;
    signal input blinding;
    
    component verify = VerifyPedersenCommitment();
    verify.amount <== amount;
    verify.blinding <== blinding;
    verify.expected_x <== commitment_x;
    verify.expected_y <== commitment_y;
    
    verify.valid === 1;
}
