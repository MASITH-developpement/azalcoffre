-- =============================================================================
-- AZALPLUS - Initialisation PostgreSQL
-- =============================================================================

-- Extensions nécessaires
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =============================================================================
-- Schéma principal
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS azalplus;
SET search_path TO azalplus, public;

-- =============================================================================
-- Table TENANTS (Multi-tenant)
-- =============================================================================
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) UNIQUE NOT NULL,
    nom VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,

    -- Informations légales
    siret VARCHAR(14),
    tva_intra VARCHAR(20),
    adresse TEXT,
    code_postal VARCHAR(10),
    ville VARCHAR(100),
    pays VARCHAR(2) DEFAULT 'FR',
    telephone VARCHAR(20),

    -- Configuration
    config JSONB DEFAULT '{}',
    modules_actifs JSONB DEFAULT '["produits", "clients", "devis", "factures", "interventions"]',
    country_pack VARCHAR(20) DEFAULT 'france',
    devise VARCHAR(3) DEFAULT 'EUR',
    langue VARCHAR(5) DEFAULT 'fr',
    timezone VARCHAR(50) DEFAULT 'Europe/Paris',

    -- Limites
    max_utilisateurs INTEGER DEFAULT 5,
    max_stockage_mo INTEGER DEFAULT 1024,

    -- Statut
    actif BOOLEAN DEFAULT TRUE,
    date_creation TIMESTAMP DEFAULT NOW(),
    date_expiration TIMESTAMP,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Table UTILISATEURS
-- =============================================================================
CREATE TABLE utilisateurs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Identité
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nom VARCHAR(100) NOT NULL,
    prenom VARCHAR(100),
    telephone VARCHAR(20),
    fonction VARCHAR(100),
    avatar_url TEXT,

    -- Rôle et permissions
    role VARCHAR(50) DEFAULT 'utilisateur',
    permissions JSONB DEFAULT '{}',

    -- Sécurité
    mfa_secret VARCHAR(100),
    mfa_actif BOOLEAN DEFAULT FALSE,
    derniere_connexion TIMESTAMP,
    tentatives_echouees INTEGER DEFAULT 0,
    verrouille_jusqu TIMESTAMP,

    -- Statut
    actif BOOLEAN DEFAULT TRUE,
    email_verifie BOOLEAN DEFAULT FALSE,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID,

    -- Contraintes
    UNIQUE(tenant_id, email)
);

-- =============================================================================
-- Table SEQUENCES (Numérotation auto)
-- =============================================================================
CREATE TABLE sequences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    entite VARCHAR(50) NOT NULL,        -- 'devis', 'facture', 'intervention'
    prefixe VARCHAR(20) NOT NULL,        -- 'DEV', 'FAC', 'INT'
    separateur VARCHAR(5) DEFAULT '-',   -- '-', '/', '_', '.'
    inclure_annee BOOLEAN DEFAULT TRUE,
    format_annee VARCHAR(4) DEFAULT 'YYYY', -- 'YYYY' ou 'YY'
    padding INTEGER DEFAULT 4,           -- Nombre de chiffres
    reset_annuel BOOLEAN DEFAULT TRUE,

    compteur_actuel INTEGER DEFAULT 0,
    annee_actuelle INTEGER DEFAULT EXTRACT(YEAR FROM NOW()),

    -- Contraintes
    UNIQUE(tenant_id, entite),

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Table AUDIT_LOG (Traçabilité Guardian)
-- =============================================================================
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Action
    action VARCHAR(50) NOT NULL,         -- 'CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'BLOCK'
    entite VARCHAR(100),                 -- 'devis', 'client', etc.
    entite_id UUID,

    -- Utilisateur
    utilisateur_id UUID,
    utilisateur_email VARCHAR(255),

    -- Détails
    donnees_avant JSONB,
    donnees_apres JSONB,
    metadata JSONB DEFAULT '{}',

    -- Contexte
    ip_address INET,
    user_agent TEXT,

    -- Timestamp
    created_at TIMESTAMP DEFAULT NOW()
);

-- Partition par mois pour performance
CREATE INDEX idx_audit_log_tenant_date ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_log_entite ON audit_log(tenant_id, entite, entite_id);

-- =============================================================================
-- Table SESSIONS
-- =============================================================================
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    utilisateur_id UUID NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,

    token_hash VARCHAR(255) NOT NULL UNIQUE,
    refresh_token_hash VARCHAR(255) UNIQUE,

    ip_address INET,
    user_agent TEXT,

    expires_at TIMESTAMP NOT NULL,
    refresh_expires_at TIMESTAMP,
    revoked BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sessions_token ON sessions(token_hash) WHERE NOT revoked;
CREATE INDEX idx_sessions_user ON sessions(utilisateur_id) WHERE NOT revoked;

-- =============================================================================
-- Table GUARDIAN_LOG (Logs sécurité - visible Créateur uniquement)
-- =============================================================================
CREATE TABLE guardian_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Action Guardian
    niveau VARCHAR(20) NOT NULL,         -- 'INFO', 'WARNING', 'BLOCK', 'CRITICAL'
    action VARCHAR(50) NOT NULL,         -- 'TENANT_BREACH', 'SQL_INJECTION', 'RATE_LIMIT'

    -- Contexte
    tenant_id UUID,
    utilisateur_id UUID,
    utilisateur_email VARCHAR(255),

    -- Détails
    description TEXT,
    requete_originale TEXT,
    requete_nettoyee TEXT,
    ip_address INET,
    user_agent TEXT,

    -- Résolution
    action_prise VARCHAR(50),            -- 'BLOCKED', 'CLEANED', 'LOGGED', 'ALERTED'

    -- Timestamp
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_guardian_log_date ON guardian_log(created_at DESC);
CREATE INDEX idx_guardian_log_niveau ON guardian_log(niveau, created_at DESC);

-- =============================================================================
-- Table MODULES_DEFINITIONS (No-Code)
-- =============================================================================
CREATE TABLE modules_definitions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    nom VARCHAR(100) NOT NULL UNIQUE,
    definition JSONB NOT NULL,           -- Le YAML parsé en JSON
    version INTEGER DEFAULT 1,

    actif BOOLEAN DEFAULT TRUE,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID
);

-- =============================================================================
-- Table MODULES_DATA (Données dynamiques des modules No-Code)
-- =============================================================================
CREATE TABLE modules_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    module VARCHAR(100) NOT NULL,        -- 'produits', 'clients', etc.
    data JSONB NOT NULL,                 -- Les données du record

    -- Recherche full-text
    search_vector TSVECTOR,

    -- Soft delete
    deleted_at TIMESTAMP,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID,
    updated_by UUID
);

CREATE INDEX idx_modules_data_tenant_module ON modules_data(tenant_id, module) WHERE deleted_at IS NULL;
CREATE INDEX idx_modules_data_search ON modules_data USING GIN(search_vector);
CREATE INDEX idx_modules_data_jsonb ON modules_data USING GIN(data jsonb_path_ops);

-- =============================================================================
-- Table FICHIERS (Stockage)
-- =============================================================================
CREATE TABLE fichiers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    nom_original VARCHAR(255) NOT NULL,
    nom_stockage VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100),
    taille_octets BIGINT,
    checksum_sha256 VARCHAR(64),

    -- Lien avec entité
    entite VARCHAR(100),
    entite_id UUID,

    -- Chiffrement
    chiffre BOOLEAN DEFAULT FALSE,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID
);

CREATE INDEX idx_fichiers_entite ON fichiers(tenant_id, entite, entite_id);

-- =============================================================================
-- Table NOTIFICATIONS
-- =============================================================================
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    utilisateur_id UUID NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,

    type VARCHAR(50) NOT NULL,           -- 'info', 'warning', 'error', 'success'
    titre VARCHAR(255) NOT NULL,
    message TEXT,
    lien VARCHAR(500),

    lu BOOLEAN DEFAULT FALSE,
    lu_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(utilisateur_id, lu, created_at DESC);

-- =============================================================================
-- Table JOBS (Tâches asynchrones)
-- =============================================================================
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,

    type VARCHAR(100) NOT NULL,          -- 'email', 'pdf', 'import', 'export'
    payload JSONB NOT NULL,

    statut VARCHAR(20) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
    priorite INTEGER DEFAULT 0,

    resultat JSONB,
    erreur TEXT,

    tentatives INTEGER DEFAULT 0,
    max_tentatives INTEGER DEFAULT 3,

    scheduled_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_jobs_pending ON jobs(statut, priorite DESC, scheduled_at) WHERE statut = 'pending';

-- =============================================================================
-- Functions utilitaires
-- =============================================================================

-- Fonction pour générer le prochain numéro de séquence
CREATE OR REPLACE FUNCTION next_sequence(
    p_tenant_id UUID,
    p_entite VARCHAR
) RETURNS VARCHAR AS $$
DECLARE
    v_seq RECORD;
    v_numero VARCHAR;
    v_annee INTEGER;
BEGIN
    v_annee := EXTRACT(YEAR FROM NOW());

    -- Lock et récupère la séquence
    SELECT * INTO v_seq
    FROM sequences
    WHERE tenant_id = p_tenant_id AND entite = p_entite
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Séquence non trouvée: %', p_entite;
    END IF;

    -- Reset si nouvelle année
    IF v_seq.reset_annuel AND v_seq.annee_actuelle < v_annee THEN
        UPDATE sequences
        SET compteur_actuel = 1, annee_actuelle = v_annee, updated_at = NOW()
        WHERE id = v_seq.id;
        v_seq.compteur_actuel := 1;
    ELSE
        UPDATE sequences
        SET compteur_actuel = compteur_actuel + 1, updated_at = NOW()
        WHERE id = v_seq.id;
        v_seq.compteur_actuel := v_seq.compteur_actuel + 1;
    END IF;

    -- Construit le numéro
    v_numero := v_seq.prefixe;

    IF v_seq.inclure_annee THEN
        v_numero := v_numero || v_seq.separateur;
        IF v_seq.format_annee = 'YY' THEN
            v_numero := v_numero || TO_CHAR(v_annee, 'YY');
        ELSE
            v_numero := v_numero || v_annee::TEXT;
        END IF;
    END IF;

    v_numero := v_numero || v_seq.separateur || LPAD(v_seq.compteur_actuel::TEXT, v_seq.padding, '0');

    RETURN v_numero;
END;
$$ LANGUAGE plpgsql;

-- Fonction pour mettre à jour updated_at automatiquement
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Triggers
-- =============================================================================

-- Auto-update updated_at
CREATE TRIGGER trg_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_utilisateurs_updated_at BEFORE UPDATE ON utilisateurs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_sequences_updated_at BEFORE UPDATE ON sequences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_modules_data_updated_at BEFORE UPDATE ON modules_data
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- Row Level Security (RLS) pour isolation multi-tenant
-- =============================================================================

ALTER TABLE utilisateurs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE modules_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE fichiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- Note: Les policies RLS seront créées dynamiquement par le moteur
-- en fonction du contexte d'exécution (current_setting('app.tenant_id'))

-- =============================================================================
-- Données initiales
-- =============================================================================

-- Créateur (super-admin invisible)
-- Note: Le créateur est hardcodé dans le moteur, pas en base

-- Tenant de démonstration (optionnel)
INSERT INTO tenants (code, nom, email, siret, actif) VALUES
('DEMO', 'Entreprise Démo', 'demo@azalplus.local', '12345678901234', TRUE);

-- Séquences par défaut pour le tenant démo
INSERT INTO sequences (tenant_id, entite, prefixe, separateur, padding)
SELECT id, 'devis', 'DEV', '-', 4 FROM tenants WHERE code = 'DEMO'
UNION ALL
SELECT id, 'facture', 'FAC', '-', 4 FROM tenants WHERE code = 'DEMO'
UNION ALL
SELECT id, 'client', 'CLI', '-', 4 FROM tenants WHERE code = 'DEMO'
UNION ALL
SELECT id, 'intervention', 'INT', '-', 4 FROM tenants WHERE code = 'DEMO';

-- =============================================================================
-- Grants
-- =============================================================================
GRANT ALL ON SCHEMA azalplus TO azalplus;
GRANT ALL ON ALL TABLES IN SCHEMA azalplus TO azalplus;
GRANT ALL ON ALL SEQUENCES IN SCHEMA azalplus TO azalplus;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA azalplus TO azalplus;
