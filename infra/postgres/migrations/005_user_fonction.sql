-- =============================================================================
-- AZALPLUS - Migration 005: User Fonction Column
-- =============================================================================
-- Description: Adds fonction (job title/position) column to utilisateurs
-- Author: AZALPLUS Team
-- Date: 2026-03-23
-- Dependencies: init.sql (utilisateurs table must exist)
-- =============================================================================

-- Ensure we're in the correct schema
SET search_path TO azalplus, public;

-- =============================================================================
-- Add fonction column to utilisateurs table
-- =============================================================================
-- Purpose: Store the user's job title/position (e.g., "Directeur", "Technicien")
--
-- This allows users to specify their position in the company,
-- which can be displayed in documents, emails, and reports.
-- =============================================================================

ALTER TABLE utilisateurs
    ADD COLUMN IF NOT EXISTS fonction VARCHAR(100) DEFAULT NULL;

-- Add column comment
COMMENT ON COLUMN utilisateurs.fonction IS
    'Job title/position of the user (e.g., Directeur, Technicien, Comptable)';

-- =============================================================================
-- Migration complete
-- =============================================================================
-- To apply this migration:
-- psql -U azalplus -d azalplus -f 005_user_fonction.sql
-- =============================================================================
