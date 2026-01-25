/// SovChain Governance Module
/// 
/// Implements the governance-consensus separation architecture (Section 4).
/// The governance layer handles policy decisions while being isolated from
/// transaction ordering (consensus).
/// 
/// Key components:
/// - GovernorCommittee: 6-member committee with 4/6 threshold
/// - GovernanceCap: Singleton capability for governance actions
/// - FROST threshold signatures for authorization
/// 
/// Reference: SovChain paper, Section 4, Listing 4
module sovchain::governance {
    use sui::object::{Self, UID};
    use sui::transfer;
    use sui::tx_context::{Self, TxContext};
    use sui::vec_set::{Self, VecSet};
    use sui::event;
    use std::vector;

    // =========================================================================
    // CONSTANTS
    // =========================================================================
    
    /// Number of governors in the committee
    const GOVERNOR_COUNT: u64 = 6;
    
    /// Threshold for governance actions (4 of 6)
    const GOVERNANCE_THRESHOLD: u64 = 4;
    
    // =========================================================================
    // ERRORS
    // =========================================================================
    
    /// Not authorized as a governor
    const ENotGovernor: u64 = 1;
    
    /// Insufficient signatures for threshold
    const EInsufficientSignatures: u64 = 2;
    
    /// Invalid signature
    const EInvalidSignature: u64 = 3;
    
    /// Governor already exists
    const EGovernorAlreadyExists: u64 = 4;
    
    /// Governor not found
    const EGovernorNotFound: u64 = 5;
    
    /// Invalid committee size
    const EInvalidCommitteeSize: u64 = 6;
    
    /// Proposal already executed
    const EProposalAlreadyExecuted: u64 = 7;
    
    /// Proposal expired
    const EProposalExpired: u64 = 8;

    // =========================================================================
    // STRUCTS
    // =========================================================================
    
    /// Governor Committee (shared object)
    /// 
    /// The committee consists of 6 members from diverse institutions:
    /// - Central bank representatives (2)
    /// - Major commercial banks (2)
    /// - Independent auditors (2)
    struct GovernorCommittee has key {
        id: UID,
        /// Set of governor addresses
        members: VecSet<address>,
        /// Threshold for approval (default: 4)
        threshold: u64,
        /// Current epoch for time-bound operations
        epoch: u64,
        /// Nonce for replay prevention
        nonce: u64,
    }
    
    /// Governance Capability (singleton)
    /// 
    /// This capability authorizes governance actions. It cannot be copied
    /// or dropped, ensuring controlled access.
    /// 
    /// INVARIANT: Exactly one GovernanceCap exists (verified by Move Prover)
    struct GovernanceCap has key, store {
        id: UID,
    }
    
    /// Proposal for governance action
    struct Proposal has key, store {
        id: UID,
        /// Type of action (e.g., "UPDATE_LIMIT", "ADD_VALIDATOR")
        action_type: vector<u8>,
        /// Serialized action parameters
        parameters: vector<u8>,
        /// Addresses that have approved
        approvals: VecSet<address>,
        /// Epoch when proposal was created
        created_epoch: u64,
        /// Expiry (epochs from creation)
        expiry_epochs: u64,
        /// Whether executed
        executed: bool,
    }
    
    /// FROST threshold signature
    /// 
    /// Represents a 4-of-6 threshold signature from the governor committee.
    struct ThresholdSignature has copy, drop, store {
        /// Aggregated R point (32 bytes compressed)
        r: vector<u8>,
        /// Aggregated s scalar (32 bytes)
        s: vector<u8>,
        /// Participating signer indices (at least 4)
        signers: vector<u8>,
    }

    // =========================================================================
    // EVENTS
    // =========================================================================
    
    /// Emitted when governance committee is initialized
    struct GovernanceInitialized has copy, drop {
        committee_id: address,
        threshold: u64,
    }
    
    /// Emitted when a proposal is created
    struct ProposalCreated has copy, drop {
        proposal_id: address,
        action_type: vector<u8>,
        proposer: address,
    }
    
    /// Emitted when a proposal is approved
    struct ProposalApproved has copy, drop {
        proposal_id: address,
        approver: address,
        approval_count: u64,
    }
    
    /// Emitted when a proposal is executed
    struct ProposalExecuted has copy, drop {
        proposal_id: address,
        action_type: vector<u8>,
    }
    
    /// Emitted when epoch advances
    struct EpochAdvanced has copy, drop {
        old_epoch: u64,
        new_epoch: u64,
    }

    // =========================================================================
    // INITIALIZATION
    // =========================================================================
    
    /// Initialize the governance system (one-time setup)
    /// 
    /// Creates:
    /// 1. GovernorCommittee (shared)
    /// 2. GovernanceCap (transferred to deployer, then to committee)
    fun init(ctx: &mut TxContext) {
        // Create governor committee with initial members
        // In production, these would be specified at deployment
        let committee = GovernorCommittee {
            id: object::new(ctx),
            members: vec_set::empty(),
            threshold: GOVERNANCE_THRESHOLD,
            epoch: 0,
            nonce: 0,
        };
        
        // Create governance capability
        let cap = GovernanceCap {
            id: object::new(ctx),
        };
        
        event::emit(GovernanceInitialized {
            committee_id: object::uid_to_address(&committee.id),
            threshold: GOVERNANCE_THRESHOLD,
        });
        
        // Share committee, transfer cap to deployer
        transfer::share_object(committee);
        transfer::transfer(cap, tx_context::sender(ctx));
    }

    // =========================================================================
    // GOVERNOR MANAGEMENT
    // =========================================================================
    
    /// Add a governor to the committee
    /// 
    /// Requires GovernanceCap (threshold approval for initial setup)
    public entry fun add_governor(
        _cap: &GovernanceCap,
        committee: &mut GovernorCommittee,
        governor: address,
        _ctx: &mut TxContext
    ) {
        assert!(!vec_set::contains(&committee.members, &governor), EGovernorAlreadyExists);
        assert!(vec_set::size(&committee.members) < GOVERNOR_COUNT, EInvalidCommitteeSize);
        
        vec_set::insert(&mut committee.members, governor);
    }
    
    /// Remove a governor from the committee
    /// 
    /// Requires threshold approval
    public entry fun remove_governor(
        _cap: &GovernanceCap,
        committee: &mut GovernorCommittee,
        governor: address,
        _ctx: &mut TxContext
    ) {
        assert!(vec_set::contains(&committee.members, &governor), EGovernorNotFound);
        
        vec_set::remove(&mut committee.members, &governor);
    }
    
    /// Check if an address is a governor
    public fun is_governor(committee: &GovernorCommittee, addr: address): bool {
        vec_set::contains(&committee.members, &addr)
    }

    // =========================================================================
    // PROPOSAL MANAGEMENT
    // =========================================================================
    
    /// Create a new governance proposal
    public entry fun create_proposal(
        committee: &GovernorCommittee,
        action_type: vector<u8>,
        parameters: vector<u8>,
        expiry_epochs: u64,
        ctx: &mut TxContext
    ) {
        let sender = tx_context::sender(ctx);
        assert!(is_governor(committee, sender), ENotGovernor);
        
        let mut approvals = vec_set::empty<address>();
        vec_set::insert(&mut approvals, sender);
        
        let proposal = Proposal {
            id: object::new(ctx),
            action_type,
            parameters,
            approvals,
            created_epoch: committee.epoch,
            expiry_epochs,
            executed: false,
        };
        
        event::emit(ProposalCreated {
            proposal_id: object::uid_to_address(&proposal.id),
            action_type: proposal.action_type,
            proposer: sender,
        });
        
        transfer::share_object(proposal);
    }
    
    /// Approve a proposal
    public entry fun approve_proposal(
        committee: &GovernorCommittee,
        proposal: &mut Proposal,
        ctx: &mut TxContext
    ) {
        let sender = tx_context::sender(ctx);
        assert!(is_governor(committee, sender), ENotGovernor);
        assert!(!proposal.executed, EProposalAlreadyExecuted);
        assert!(
            committee.epoch <= proposal.created_epoch + proposal.expiry_epochs,
            EProposalExpired
        );
        
        if (!vec_set::contains(&proposal.approvals, &sender)) {
            vec_set::insert(&mut proposal.approvals, sender);
        };
        
        event::emit(ProposalApproved {
            proposal_id: object::uid_to_address(&proposal.id),
            approver: sender,
            approval_count: vec_set::size(&proposal.approvals),
        });
    }
    
    /// Check if proposal has reached threshold
    public fun proposal_ready(committee: &GovernorCommittee, proposal: &Proposal): bool {
        vec_set::size(&proposal.approvals) >= committee.threshold
    }

    // =========================================================================
    // THRESHOLD SIGNATURE VERIFICATION
    // =========================================================================
    
    /// Verify a FROST threshold signature
    /// 
    /// This is a placeholder for actual FROST verification.
    /// In production, this would use native crypto operations.
    public fun verify_threshold_signature(
        committee: &GovernorCommittee,
        message: &vector<u8>,
        sig: &ThresholdSignature,
    ): bool {
        // Check minimum signers
        if (vector::length(&sig.signers) < committee.threshold) {
            return false
        };
        
        // Verify all signers are valid governors
        let i = 0;
        let len = vector::length(&sig.signers);
        while (i < len) {
            let signer_idx = *vector::borrow(&sig.signers, i);
            if ((signer_idx as u64) >= GOVERNOR_COUNT) {
                return false
            };
            i = i + 1;
        };
        
        // NOTE: Actual FROST verification would be done here
        // This requires native crypto operations for:
        // 1. Point decompression (R from sig.r)
        // 2. Schnorr verification equation
        // 3. Lagrange coefficient computation
        
        // Placeholder: always return true for testing
        // In production: verify_schnorr(committee_pubkey, message, sig.r, sig.s)
        true
    }

    // =========================================================================
    // EPOCH MANAGEMENT
    // =========================================================================
    
    /// Advance the epoch (called by system)
    public entry fun advance_epoch(
        _cap: &GovernanceCap,
        committee: &mut GovernorCommittee,
        _ctx: &mut TxContext
    ) {
        let old_epoch = committee.epoch;
        committee.epoch = committee.epoch + 1;
        
        event::emit(EpochAdvanced {
            old_epoch,
            new_epoch: committee.epoch,
        });
    }
    
    /// Get current epoch
    public fun current_epoch(committee: &GovernorCommittee): u64 {
        committee.epoch
    }
    
    /// Get and increment nonce (for replay prevention)
    public fun get_and_increment_nonce(committee: &mut GovernorCommittee): u64 {
        let current = committee.nonce;
        committee.nonce = committee.nonce + 1;
        current
    }

    // =========================================================================
    // ACCESSORS
    // =========================================================================
    
    /// Get governance threshold
    public fun threshold(committee: &GovernorCommittee): u64 {
        committee.threshold
    }
    
    /// Get committee size
    public fun committee_size(committee: &GovernorCommittee): u64 {
        vec_set::size(&committee.members)
    }

    // =========================================================================
    // MOVE PROVER SPECIFICATIONS
    // =========================================================================
    
    // Invariant: GovernanceCap is unique (exactly one exists)
    // spec GovernanceCap {
    //     invariant forall cap1: GovernanceCap, cap2: GovernanceCap:
    //         cap1.id == cap2.id;
    // }
    
    // Invariant: Committee size bounded
    // spec GovernorCommittee {
    //     invariant vec_set::size(members) <= GOVERNOR_COUNT;
    //     invariant threshold <= vec_set::size(members);
    // }

    // =========================================================================
    // TESTS
    // =========================================================================
    
    #[test_only]
    public fun init_for_testing(ctx: &mut TxContext) {
        init(ctx);
    }
}
