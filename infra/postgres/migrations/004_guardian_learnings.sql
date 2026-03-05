-- =============================================================================
-- GUARDIAN LEARNINGS - Table d'apprentissage pour AutoPilot
-- =============================================================================

CREATE TABLE IF NOT EXISTS azalplus.guardian_learnings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Pattern d'erreur
    error_pattern VARCHAR(100) NOT NULL,      -- Type d'erreur (ImportError, NameError, etc.)
    error_message TEXT,                        -- Message d'erreur complet

    -- Fix proposé
    fix_template TEXT,                         -- Le fix qui a été proposé

    -- Statut et apprentissage
    status VARCHAR(20) NOT NULL,               -- 'validated', 'rejected', 'pending'
    explanation TEXT,                          -- Explication (si rejeté, pourquoi)

    -- Contexte
    file_path TEXT,                            -- Fichier concerné

    -- Métadonnées
    confidence FLOAT DEFAULT 0.5,              -- Confiance du fix
    times_applied INTEGER DEFAULT 0,           -- Nombre de fois appliqué

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index pour recherche rapide
CREATE INDEX IF NOT EXISTS idx_guardian_learnings_pattern ON azalplus.guardian_learnings(error_pattern);
CREATE INDEX IF NOT EXISTS idx_guardian_learnings_status ON azalplus.guardian_learnings(status);
CREATE INDEX IF NOT EXISTS idx_guardian_learnings_date ON azalplus.guardian_learnings(created_at DESC);

-- Commentaire
COMMENT ON TABLE azalplus.guardian_learnings IS 'Apprentissages de Guardian AutoPilot - stocke les patterns validés/rejetés et les explications';
