-- =============================================================================
-- AZALPLUS - Migration 003: User Mobile Modules Column
-- =============================================================================
-- Description: Adds per-user mobile module access configuration
-- Author: AZALPLUS Team
-- Date: 2026-03-04
-- Dependencies: init.sql (utilisateurs table must exist)
-- =============================================================================

-- Ensure we're in the correct schema
SET search_path TO azalplus, public;

-- =============================================================================
-- Add modules_mobile column to utilisateurs table
-- =============================================================================
-- Purpose: Store an array of module names the user can access on mobile.
--
-- Behavior:
--   - NULL: Use role-based defaults from mobile_configurations.internal_modules
--   - []: Empty array means NO mobile access (user is restricted from mobile)
--   - ["clients", "factures", ...]: Explicit list of allowed modules
--
-- This allows per-user customization of mobile access, overriding the
-- tenant-wide defaults defined in mobile_configurations.internal_modules.
--
-- Examples:
--   - NULL: User sees all modules allowed by their role/tenant config
--   - []: User cannot access the mobile app
--   - ["clients", "factures", "interventions"]: User can only access these 3 modules
-- =============================================================================

ALTER TABLE utilisateurs
    ADD COLUMN IF NOT EXISTS modules_mobile JSONB DEFAULT NULL;

-- Add column comment
COMMENT ON COLUMN utilisateurs.modules_mobile IS
    'Per-user mobile module access list. NULL = use role defaults, [] = no mobile access, ["module1", "module2"] = explicit access list';

-- =============================================================================
-- Index for performance (optional - for queries filtering by mobile access)
-- =============================================================================
-- This index helps when querying users by their mobile access configuration
-- e.g., finding all users with no mobile access, or users with specific module access

CREATE INDEX IF NOT EXISTS idx_utilisateurs_modules_mobile
    ON utilisateurs USING GIN(modules_mobile jsonb_path_ops)
    WHERE modules_mobile IS NOT NULL;

-- =============================================================================
-- Migration complete
-- =============================================================================
-- To apply this migration:
-- psql -U azalplus -d azalplus -f 003_user_mobile_modules.sql
-- =============================================================================
