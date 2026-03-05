-- =============================================================================
-- AZALPLUS - Migration 002: Mobile Configuration Tables
-- =============================================================================
-- Description: Creates tables for mobile app configuration and push notifications
-- Author: AZALPLUS Team
-- Date: 2026-03-04
-- Dependencies: 001_init (tenants table must exist)
-- =============================================================================

-- Ensure we're in the correct schema
SET search_path TO azalplus, public;

-- =============================================================================
-- Table: mobile_configurations
-- =============================================================================
-- Stores per-tenant mobile application configuration including:
-- - Internal app settings (employee mobile app)
-- - Portal settings (customer/partner portal)
-- - Offline sync configuration
-- - Push notification settings
-- - Branding/theming options
-- =============================================================================

CREATE TABLE IF NOT EXISTS mobile_configurations (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Tenant isolation (MANDATORY - AZA-TENANT)
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- ==========================================================================
    -- Internal App Configuration (Employee Mobile App)
    -- ==========================================================================
    internal_enabled BOOLEAN DEFAULT TRUE,
    internal_modules JSONB DEFAULT '[]'::jsonb,
    -- Example: ["clients", "factures", "interventions", "projets"]

    internal_dashboard JSONB DEFAULT '{}'::jsonb,
    -- Example: {
    --   "widgets": ["kpi_ca", "tasks_pending", "interventions_today"],
    --   "refresh_interval": 300,
    --   "charts": ["revenue_monthly", "tasks_by_status"]
    -- }

    internal_quick_actions JSONB DEFAULT '[]'::jsonb,
    -- Example: [
    --   {"action": "new_intervention", "icon": "wrench", "label": "Nouvelle intervention"},
    --   {"action": "scan_barcode", "icon": "barcode", "label": "Scanner"}
    -- ]

    -- ==========================================================================
    -- Portal Configuration (Customer/Partner Portal)
    -- ==========================================================================
    portal_enabled BOOLEAN DEFAULT TRUE,
    portal_features JSONB DEFAULT '{}'::jsonb,
    -- Example: {
    --   "invoices": {"view": true, "download": true, "pay_online": false},
    --   "quotes": {"view": true, "accept": true, "comment": true},
    --   "tickets": {"create": true, "view": true, "comment": true},
    --   "documents": {"view": true, "download": true}
    -- }

    -- ==========================================================================
    -- Offline Configuration
    -- ==========================================================================
    offline_enabled BOOLEAN DEFAULT FALSE,
    offline_modules JSONB DEFAULT '[]'::jsonb,
    -- Example: ["clients", "produits", "interventions"]
    -- Only these modules will be available offline

    sync_interval INTEGER DEFAULT 15,
    -- Sync interval in minutes (minimum 5, maximum 1440)
    -- Controls how often the app syncs with the server when online

    -- ==========================================================================
    -- Push Notification Configuration
    -- ==========================================================================
    push_enabled BOOLEAN DEFAULT FALSE,
    push_channels JSONB DEFAULT '{}'::jsonb,
    -- Example: {
    --   "new_quote": {"enabled": true, "roles": ["commercial", "admin"]},
    --   "invoice_paid": {"enabled": true, "roles": ["comptable", "admin"]},
    --   "intervention_assigned": {"enabled": true, "roles": ["technicien"]},
    --   "low_stock": {"enabled": false, "roles": ["gestionnaire_stock"]}
    -- }

    -- ==========================================================================
    -- Branding Configuration
    -- ==========================================================================
    app_name VARCHAR(100),
    -- Custom app name displayed in the mobile app (defaults to tenant name)

    logo_url TEXT,
    -- URL to the tenant's logo for mobile app branding
    -- Should be a square image, minimum 512x512 pixels

    primary_color VARCHAR(7) DEFAULT '#2563EB',
    -- Primary brand color in hex format (e.g., '#2563EB')
    -- Used for buttons, headers, and accent elements

    -- ==========================================================================
    -- Audit Fields
    -- ==========================================================================
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    updated_by UUID,

    -- ==========================================================================
    -- Constraints
    -- ==========================================================================
    -- Ensure one configuration per tenant
    CONSTRAINT uq_mobile_config_tenant UNIQUE(tenant_id),

    -- Validate primary color format (hex color code)
    CONSTRAINT chk_primary_color_format CHECK (
        primary_color IS NULL OR
        primary_color ~ '^#[0-9A-Fa-f]{6}$'
    ),

    -- Validate sync interval range (5 minutes to 24 hours)
    CONSTRAINT chk_sync_interval_range CHECK (
        sync_interval >= 5 AND sync_interval <= 1440
    )
);

-- Add table comment
COMMENT ON TABLE mobile_configurations IS
    'Per-tenant mobile application configuration for internal app, portal, offline sync, and push notifications';

-- Add column comments
COMMENT ON COLUMN mobile_configurations.tenant_id IS 'Foreign key to tenants table - ensures data isolation';
COMMENT ON COLUMN mobile_configurations.internal_enabled IS 'Enable/disable internal employee mobile app';
COMMENT ON COLUMN mobile_configurations.internal_modules IS 'List of modules available in internal app';
COMMENT ON COLUMN mobile_configurations.internal_dashboard IS 'Dashboard widget and chart configuration';
COMMENT ON COLUMN mobile_configurations.internal_quick_actions IS 'Quick action buttons on mobile home screen';
COMMENT ON COLUMN mobile_configurations.portal_enabled IS 'Enable/disable customer/partner portal';
COMMENT ON COLUMN mobile_configurations.portal_features IS 'Feature flags for portal functionality';
COMMENT ON COLUMN mobile_configurations.offline_enabled IS 'Enable/disable offline mode';
COMMENT ON COLUMN mobile_configurations.offline_modules IS 'Modules available in offline mode';
COMMENT ON COLUMN mobile_configurations.sync_interval IS 'Data sync interval in minutes (5-1440)';
COMMENT ON COLUMN mobile_configurations.push_enabled IS 'Enable/disable push notifications';
COMMENT ON COLUMN mobile_configurations.push_channels IS 'Push notification channel configuration per event type';
COMMENT ON COLUMN mobile_configurations.app_name IS 'Custom app name for branding';
COMMENT ON COLUMN mobile_configurations.logo_url IS 'URL to tenant logo (512x512 minimum)';
COMMENT ON COLUMN mobile_configurations.primary_color IS 'Primary brand color in hex format';

-- =============================================================================
-- Table: push_tokens
-- =============================================================================
-- Stores push notification tokens for each user's devices
-- Supports multiple platforms: web (service workers), iOS, and Android
-- =============================================================================

CREATE TABLE IF NOT EXISTS push_tokens (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Tenant isolation (MANDATORY - AZA-TENANT)
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- User reference
    user_id UUID NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,

    -- Push token (Firebase FCM, APNs, or Web Push)
    token TEXT NOT NULL,

    -- Platform identifier
    platform VARCHAR(20) NOT NULL,
    -- Valid values: 'web', 'ios', 'android'

    -- Device information for debugging and analytics
    device_info JSONB,
    -- Example: {
    --   "model": "iPhone 14 Pro",
    --   "os_version": "17.2",
    --   "app_version": "1.2.3",
    --   "device_id": "unique-device-uuid",
    --   "browser": "Chrome 120" (for web)
    -- }

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    -- Updated each time a push is successfully sent to this token

    -- ==========================================================================
    -- Constraints
    -- ==========================================================================
    -- Ensure unique token per tenant/user combination
    CONSTRAINT uq_push_token_tenant_user_token UNIQUE(tenant_id, user_id, token),

    -- Validate platform values
    CONSTRAINT chk_platform_valid CHECK (
        platform IN ('web', 'ios', 'android')
    )
);

-- Add table comment
COMMENT ON TABLE push_tokens IS
    'Push notification tokens for user devices across web, iOS, and Android platforms';

-- Add column comments
COMMENT ON COLUMN push_tokens.tenant_id IS 'Foreign key to tenants table - ensures data isolation';
COMMENT ON COLUMN push_tokens.user_id IS 'Foreign key to utilisateurs table';
COMMENT ON COLUMN push_tokens.token IS 'Push notification token (FCM, APNs, or Web Push endpoint)';
COMMENT ON COLUMN push_tokens.platform IS 'Platform identifier: web, ios, or android';
COMMENT ON COLUMN push_tokens.device_info IS 'Device metadata for debugging and analytics';
COMMENT ON COLUMN push_tokens.last_used_at IS 'Timestamp of last successful push to this token';

-- =============================================================================
-- Indexes for Performance
-- =============================================================================

-- Index on tenant_id for mobile_configurations (fast tenant lookup)
CREATE INDEX IF NOT EXISTS idx_mobile_config_tenant
    ON mobile_configurations(tenant_id);

-- Composite index for push_tokens (common query pattern: get all tokens for a user)
CREATE INDEX IF NOT EXISTS idx_push_tokens_tenant_user
    ON push_tokens(tenant_id, user_id);

-- Index on token for deduplication checks
CREATE INDEX IF NOT EXISTS idx_push_tokens_token
    ON push_tokens(token);

-- Index on platform for analytics queries
CREATE INDEX IF NOT EXISTS idx_push_tokens_platform
    ON push_tokens(tenant_id, platform);

-- =============================================================================
-- Trigger: Auto-update updated_at on mobile_configurations
-- =============================================================================
-- Uses the existing update_updated_at() function from init.sql

CREATE TRIGGER trg_mobile_configurations_updated_at
    BEFORE UPDATE ON mobile_configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- Function: Create default mobile configuration for new tenant
-- =============================================================================
-- This function creates a default mobile configuration when a new tenant is created
-- Should be called from application code or via trigger on tenants table

CREATE OR REPLACE FUNCTION create_default_mobile_config(
    p_tenant_id UUID,
    p_created_by UUID DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_config_id UUID;
BEGIN
    -- Check if configuration already exists
    SELECT id INTO v_config_id
    FROM mobile_configurations
    WHERE tenant_id = p_tenant_id;

    IF FOUND THEN
        RETURN v_config_id;
    END IF;

    -- Create default configuration
    INSERT INTO mobile_configurations (
        tenant_id,
        internal_enabled,
        internal_modules,
        internal_dashboard,
        internal_quick_actions,
        portal_enabled,
        portal_features,
        offline_enabled,
        offline_modules,
        sync_interval,
        push_enabled,
        push_channels,
        primary_color,
        created_by
    ) VALUES (
        p_tenant_id,
        TRUE,
        '["clients", "factures", "devis", "interventions"]'::jsonb,
        '{
            "widgets": ["kpi_ca_mois", "taches_en_cours", "factures_impayees"],
            "refresh_interval": 300
        }'::jsonb,
        '[
            {"action": "new_client", "icon": "user-plus", "label": "Nouveau client"},
            {"action": "new_intervention", "icon": "wrench", "label": "Intervention"},
            {"action": "scan", "icon": "qrcode", "label": "Scanner"}
        ]'::jsonb,
        TRUE,
        '{
            "invoices": {"view": true, "download": true, "pay_online": false},
            "quotes": {"view": true, "accept": true},
            "tickets": {"create": true, "view": true}
        }'::jsonb,
        FALSE,
        '[]'::jsonb,
        15,
        FALSE,
        '{}'::jsonb,
        '#2563EB',
        p_created_by
    )
    RETURNING id INTO v_config_id;

    RETURN v_config_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_default_mobile_config IS
    'Creates default mobile configuration for a new tenant with sensible defaults';

-- =============================================================================
-- Function: Register or update push token
-- =============================================================================
-- Handles token registration with upsert logic
-- Updates last_used_at if token already exists

CREATE OR REPLACE FUNCTION register_push_token(
    p_tenant_id UUID,
    p_user_id UUID,
    p_token TEXT,
    p_platform VARCHAR(20),
    p_device_info JSONB DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_token_id UUID;
BEGIN
    -- Validate platform
    IF p_platform NOT IN ('web', 'ios', 'android') THEN
        RAISE EXCEPTION 'Invalid platform: %. Must be web, ios, or android', p_platform;
    END IF;

    -- Upsert token
    INSERT INTO push_tokens (
        tenant_id,
        user_id,
        token,
        platform,
        device_info,
        last_used_at
    ) VALUES (
        p_tenant_id,
        p_user_id,
        p_token,
        p_platform,
        p_device_info,
        NOW()
    )
    ON CONFLICT (tenant_id, user_id, token)
    DO UPDATE SET
        platform = EXCLUDED.platform,
        device_info = COALESCE(EXCLUDED.device_info, push_tokens.device_info),
        last_used_at = NOW()
    RETURNING id INTO v_token_id;

    RETURN v_token_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION register_push_token IS
    'Registers or updates a push notification token for a user device';

-- =============================================================================
-- Function: Cleanup expired/unused push tokens
-- =============================================================================
-- Removes tokens that haven't been used in the specified number of days
-- Should be called periodically via a scheduled job

CREATE OR REPLACE FUNCTION cleanup_expired_push_tokens(
    p_days_inactive INTEGER DEFAULT 90
) RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
BEGIN
    DELETE FROM push_tokens
    WHERE last_used_at IS NULL
       OR last_used_at < NOW() - (p_days_inactive || ' days')::INTERVAL;

    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;

    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_push_tokens IS
    'Removes push tokens that have not been used in the specified number of days (default 90)';

-- =============================================================================
-- Row Level Security (RLS)
-- =============================================================================
-- Enable RLS for tenant isolation

ALTER TABLE mobile_configurations ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_tokens ENABLE ROW LEVEL SECURITY;

-- Note: RLS policies are created dynamically by the moteur based on
-- current_setting('app.tenant_id') - see init.sql for pattern

-- =============================================================================
-- Create default mobile config for existing DEMO tenant
-- =============================================================================

DO $$
DECLARE
    v_demo_tenant_id UUID;
BEGIN
    -- Get DEMO tenant ID
    SELECT id INTO v_demo_tenant_id
    FROM tenants
    WHERE code = 'DEMO';

    IF FOUND THEN
        PERFORM create_default_mobile_config(v_demo_tenant_id, NULL);
        RAISE NOTICE 'Created default mobile configuration for DEMO tenant';
    END IF;
END $$;

-- =============================================================================
-- Grants
-- =============================================================================

GRANT ALL ON TABLE mobile_configurations TO azalplus;
GRANT ALL ON TABLE push_tokens TO azalplus;
GRANT EXECUTE ON FUNCTION create_default_mobile_config TO azalplus;
GRANT EXECUTE ON FUNCTION register_push_token TO azalplus;
GRANT EXECUTE ON FUNCTION cleanup_expired_push_tokens TO azalplus;

-- =============================================================================
-- Migration complete
-- =============================================================================
-- To apply this migration:
-- psql -U azalplus -d azalplus -f 002_mobile_config.sql
-- =============================================================================
