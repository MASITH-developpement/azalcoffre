-- =============================================================================
-- AZALPLUS - Migration 001: Mobile Configuration Table
-- =============================================================================
-- This migration creates the mobile_config table for storing tenant-specific
-- mobile application configuration.
--
-- Run this migration:
--   psql -U azalplus -d azalplus -f 001_mobile_config.sql
-- =============================================================================

-- Ensure schema exists
CREATE SCHEMA IF NOT EXISTS azalplus;

-- Create mobile_config table
CREATE TABLE IF NOT EXISTS azalplus.mobile_config (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Tenant isolation (REQUIRED - multi-tenant)
    tenant_id UUID NOT NULL UNIQUE,

    -- Configuration data stored as JSONB
    config_data JSONB DEFAULT '{}'::jsonb,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by UUID,

    -- Foreign key to tenants table
    CONSTRAINT fk_mobile_config_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES azalplus.tenants(id)
        ON DELETE CASCADE
);

-- Create index on tenant_id for fast lookups
CREATE INDEX IF NOT EXISTS idx_mobile_config_tenant_id
    ON azalplus.mobile_config(tenant_id);

-- Add comment
COMMENT ON TABLE azalplus.mobile_config IS
    'Mobile application configuration per tenant';

COMMENT ON COLUMN azalplus.mobile_config.config_data IS
    'JSONB containing all mobile config: theme, offline, modules, notifications, security, performance';

-- =============================================================================
-- Default config JSON structure reference:
-- {
--   "theme": "system",
--   "primary_color": "#1976d2",
--   "logo_url": null,
--   "offline_enabled": true,
--   "sync_interval_minutes": 15,
--   "max_offline_days": 7,
--   "enabled_modules": [],
--   "push_notifications_enabled": true,
--   "notification_types": ["urgent", "mention", "assignment"],
--   "biometric_auth_enabled": false,
--   "session_timeout_minutes": 30,
--   "pin_required": false,
--   "cache_ttl_minutes": 5,
--   "max_items_per_page": 25
-- }
-- =============================================================================
