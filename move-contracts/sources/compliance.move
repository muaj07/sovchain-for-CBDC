/// SovChain Compliance Module
/// 
/// Implements identity registry and tiered transaction limits (Section 6).
/// 
/// Features:
/// - Tiered KYC (Anonymous, Basic, Standard, Full)
/// - Balance and volume limits per tier
/// - Transfer validation with compliance checks
/// - Rolling volume tracking
/// 
/// Reference: SovChain paper, Section 6, Tables 13-14
module sovchain::compliance {
    use sui::object::{Self, UID};
    use sui::transfer;
    use sui::tx_context::{Self, TxContext};
    use sui::table::{Self, Table};
    use sui::coin::{Self, Coin};
    use sui::event;
    use sui::clock::{Self, Clock};
    use sovchain::cbdc::{Self, CBDC};

    // =========================================================================
    // CONSTANTS - IDENTITY TIERS (Section 6.1)
    // =========================================================================
    
    /// Tier 0: Anonymous - No identity verification
    const TIER_ANONYMOUS: u8 = 0;
    
    /// Tier 1: Basic - Phone verification
    const TIER_BASIC: u8 = 1;
    
    /// Tier 2: Standard - Government ID verification
    const TIER_STANDARD: u8 = 2;
    
    /// Tier 3: Full - Enhanced due diligence
    const TIER_FULL: u8 = 3;

    // =========================================================================
    // CONSTANTS - LIMITS (Table 13, illustrative values)
    // =========================================================================
    
    // Balance limits (in base units, 6 decimals)
    const TIER0_BALANCE_LIMIT: u64 = 10_000_000_000;      // PKR 10,000
    const TIER1_BALANCE_LIMIT: u64 = 50_000_000_000;      // PKR 50,000
    const TIER2_BALANCE_LIMIT: u64 = 5_000_000_000_000;   // PKR 5,000,000
    const TIER3_BALANCE_LIMIT: u64 = 0xFFFFFFFFFFFFFFFF;  // Unlimited
    
    // Monthly volume limits
    const TIER0_MONTHLY_LIMIT: u64 = 50_000_000_000;      // PKR 50,000/month
    const TIER1_MONTHLY_LIMIT: u64 = 500_000_000_000;     // PKR 500,000/month
    const TIER2_MONTHLY_LIMIT: u64 = 5_000_000_000_000;   // PKR 5,000,000/month
    const TIER3_MONTHLY_LIMIT: u64 = 0xFFFFFFFFFFFFFFFF;  // Unlimited
    
    // Rolling window for volume tracking (30 days in seconds)
    const VOLUME_WINDOW_SECONDS: u64 = 30 * 24 * 60 * 60;

    // =========================================================================
    // ERRORS
    // =========================================================================
    
    /// Transfer exceeds balance limit for tier
    const EBalanceLimitExceeded: u64 = 1;
    
    /// Transfer exceeds monthly volume limit for tier
    const EVolumeLimitExceeded: u64 = 2;
    
    /// Identity not found in registry
    const EIdentityNotFound: u64 = 3;
    
    /// Invalid tier value
    const EInvalidTier: u64 = 4;
    
    /// Unauthorized KYC provider
    const EUnauthorizedKYCProvider: u64 = 5;
    
    /// Tier downgrade not allowed
    const ETierDowngradeNotAllowed: u64 = 6;

    // =========================================================================
    // STRUCTS
    // =========================================================================
    
    /// Identity Registry (shared object)
    /// 
    /// Stores tier levels for all registered identities.
    /// Only stores tier level, not PII (privacy-preserving).
    struct IdentityRegistry has key {
        id: UID,
        /// Address -> IdentityRecord mapping
        records: Table<address, IdentityRecord>,
        /// Authorized KYC providers
        kyc_providers: vector<address>,
    }
    
    /// Identity record for a single address
    struct IdentityRecord has store, drop {
        /// KYC tier (0-3)
        tier: u8,
        /// KYC provider that verified this identity
        provider: address,
        /// Timestamp of last verification
        verified_at: u64,
        /// Rolling 30-day volume (updated on each transfer)
        rolling_volume: u64,
        /// Timestamp when rolling volume was last updated
        volume_updated_at: u64,
    }
    
    /// Transfer receipt for audit trail
    struct TransferReceipt has key, store {
        id: UID,
        from: address,
        to: address,
        amount: u64,
        timestamp: u64,
        sender_tier: u8,
        recipient_tier: u8,
    }

    // =========================================================================
    // EVENTS
    // =========================================================================
    
    /// Emitted when identity tier is updated
    struct TierUpdated has copy, drop {
        account: address,
        old_tier: u8,
        new_tier: u8,
        provider: address,
    }
    
    /// Emitted when transfer is validated
    struct TransferValidated has copy, drop {
        from: address,
        to: address,
        amount: u64,
        sender_tier: u8,
        recipient_tier: u8,
    }
    
    /// Emitted when transfer is blocked
    struct TransferBlocked has copy, drop {
        from: address,
        to: address,
        amount: u64,
        reason: vector<u8>,
    }

    // =========================================================================
    // INITIALIZATION
    // =========================================================================
    
    /// Initialize the identity registry
    fun init(ctx: &mut TxContext) {
        let registry = IdentityRegistry {
            id: object::new(ctx),
            records: table::new(ctx),
            kyc_providers: vector::empty(),
        };
        
        transfer::share_object(registry);
    }

    // =========================================================================
    // IDENTITY MANAGEMENT
    // =========================================================================
    
    /// Register or update identity tier
    /// 
    /// Only authorized KYC providers can update tiers.
    public entry fun update_tier(
        registry: &mut IdentityRegistry,
        account: address,
        new_tier: u8,
        clock: &Clock,
        ctx: &mut TxContext
    ) {
        let provider = tx_context::sender(ctx);
        
        // Verify authorized KYC provider
        assert!(is_kyc_provider(registry, provider), EUnauthorizedKYCProvider);
        assert!(new_tier <= TIER_FULL, EInvalidTier);
        
        let now = clock::timestamp_ms(clock) / 1000;
        
        if (table::contains(&registry.records, account)) {
            let record = table::borrow_mut(&mut registry.records, account);
            let old_tier = record.tier;
            
            // Tier downgrade requires special handling (not allowed without governance)
            // In production, this would require governance approval
            // assert!(new_tier >= record.tier, ETierDowngradeNotAllowed);
            
            record.tier = new_tier;
            record.provider = provider;
            record.verified_at = now;
            
            event::emit(TierUpdated {
                account,
                old_tier,
                new_tier,
                provider,
            });
        } else {
            let record = IdentityRecord {
                tier: new_tier,
                provider,
                verified_at: now,
                rolling_volume: 0,
                volume_updated_at: now,
            };
            
            table::add(&mut registry.records, account, record);
            
            event::emit(TierUpdated {
                account,
                old_tier: 0,
                new_tier,
                provider,
            });
        }
    }
    
    /// Add authorized KYC provider (governance action)
    public fun add_kyc_provider(
        registry: &mut IdentityRegistry,
        provider: address,
    ) {
        if (!vector::contains(&registry.kyc_providers, &provider)) {
            vector::push_back(&mut registry.kyc_providers, provider);
        }
    }
    
    /// Check if address is authorized KYC provider
    public fun is_kyc_provider(registry: &IdentityRegistry, addr: address): bool {
        vector::contains(&registry.kyc_providers, &addr)
    }

    // =========================================================================
    // TRANSFER VALIDATION
    // =========================================================================
    
    /// Validate a transfer against compliance rules
    /// 
    /// Checks:
    /// 1. Sender and recipient tiers
    /// 2. Balance limits for recipient
    /// 3. Volume limits for sender
    public fun validate_transfer(
        registry: &mut IdentityRegistry,
        from: address,
        to: address,
        amount: u64,
        recipient_balance: u64,
        clock: &Clock,
    ): bool {
        let now = clock::timestamp_ms(clock) / 1000;
        
        // Get sender tier (default to Tier 0 if not registered)
        let sender_tier = get_tier(registry, from);
        let recipient_tier = get_tier(registry, to);
        
        // Check recipient balance limit
        let balance_limit = get_balance_limit(recipient_tier);
        if (recipient_balance + amount > balance_limit) {
            event::emit(TransferBlocked {
                from,
                to,
                amount,
                reason: b"BALANCE_LIMIT_EXCEEDED",
            });
            return false
        };
        
        // Check sender volume limit
        let volume_limit = get_volume_limit(sender_tier);
        
        if (table::contains(&registry.records, from)) {
            let record = table::borrow_mut(&mut registry.records, from);
            
            // Reset rolling volume if window expired
            if (now - record.volume_updated_at > VOLUME_WINDOW_SECONDS) {
                record.rolling_volume = 0;
            };
            
            if (record.rolling_volume + amount > volume_limit) {
                event::emit(TransferBlocked {
                    from,
                    to,
                    amount,
                    reason: b"VOLUME_LIMIT_EXCEEDED",
                });
                return false
            };
            
            // Update rolling volume
            record.rolling_volume = record.rolling_volume + amount;
            record.volume_updated_at = now;
        };
        
        event::emit(TransferValidated {
            from,
            to,
            amount,
            sender_tier,
            recipient_tier,
        });
        
        true
    }
    
    /// Transfer with compliance enforcement
    public entry fun compliant_transfer(
        registry: &mut IdentityRegistry,
        coin: Coin<CBDC>,
        recipient: address,
        recipient_balance: u64,  // Current balance of recipient
        clock: &Clock,
        ctx: &mut TxContext
    ) {
        let sender = tx_context::sender(ctx);
        let amount = coin::value(&coin);
        
        // Validate transfer
        let valid = validate_transfer(
            registry,
            sender,
            recipient,
            amount,
            recipient_balance,
            clock,
        );
        
        assert!(valid, EBalanceLimitExceeded);
        
        // Execute transfer
        transfer::public_transfer(coin, recipient);
    }

    // =========================================================================
    // LIMIT LOOKUPS
    // =========================================================================
    
    /// Get balance limit for tier
    public fun get_balance_limit(tier: u8): u64 {
        if (tier == TIER_ANONYMOUS) {
            TIER0_BALANCE_LIMIT
        } else if (tier == TIER_BASIC) {
            TIER1_BALANCE_LIMIT
        } else if (tier == TIER_STANDARD) {
            TIER2_BALANCE_LIMIT
        } else {
            TIER3_BALANCE_LIMIT
        }
    }
    
    /// Get monthly volume limit for tier
    public fun get_volume_limit(tier: u8): u64 {
        if (tier == TIER_ANONYMOUS) {
            TIER0_MONTHLY_LIMIT
        } else if (tier == TIER_BASIC) {
            TIER1_MONTHLY_LIMIT
        } else if (tier == TIER_STANDARD) {
            TIER2_MONTHLY_LIMIT
        } else {
            TIER3_MONTHLY_LIMIT
        }
    }
    
    /// Get tier for an address
    public fun get_tier(registry: &IdentityRegistry, addr: address): u8 {
        if (table::contains(&registry.records, addr)) {
            table::borrow(&registry.records, addr).tier
        } else {
            TIER_ANONYMOUS
        }
    }
    
    /// Get rolling volume for an address
    public fun get_rolling_volume(registry: &IdentityRegistry, addr: address): u64 {
        if (table::contains(&registry.records, addr)) {
            table::borrow(&registry.records, addr).rolling_volume
        } else {
            0
        }
    }

    // =========================================================================
    // TESTS
    // =========================================================================
    
    #[test_only]
    public fun init_for_testing(ctx: &mut TxContext) {
        init(ctx);
    }
}
