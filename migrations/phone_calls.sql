-- =============================================================================
-- AZALPLUS - Table Appels Telephoniques
-- =============================================================================
-- Module d'appels telephoniques avec:
-- - Appels via app AZALPLUS (WebRTC/LiveKit) - Gratuit
-- - Appels via Twilio PSTN - Option payante
-- - Transcription automatique (Whisper)
-- - Compte-rendu automatique (Claude)
-- - Email via config utilisateur
-- =============================================================================

-- Table principale des appels
CREATE TABLE IF NOT EXISTS azalplus.phone_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES azalplus.tenants(id),
    user_id UUID NOT NULL REFERENCES azalplus.users(id),
    callee_id UUID REFERENCES azalplus.users(id),  -- Destinataire (si utilisateur AZALPLUS)

    -- Type et provider
    call_type VARCHAR(20) NOT NULL DEFAULT 'app_to_app',  -- app_to_app, app_to_phone, twilio_pstn
    call_provider VARCHAR(20) NOT NULL DEFAULT 'app',      -- app, twilio
    direction VARCHAR(20) NOT NULL DEFAULT 'outbound',     -- inbound, outbound
    status VARCHAR(20) NOT NULL DEFAULT 'initiating',      -- initiating, ringing, in_progress, on_hold, completed, missed, failed, cancelled

    -- Numeros et identifiants
    from_number VARCHAR(20),
    to_number VARCHAR(20),
    to_email VARCHAR(255),
    external_call_id VARCHAR(100),  -- SID Twilio ou autre

    -- LiveKit (pour appels app)
    room_name VARCHAR(100),

    -- Metadata
    subject VARCHAR(500),
    decline_reason TEXT,

    -- Options
    auto_record BOOLEAN DEFAULT true,
    auto_transcribe BOOLEAN DEFAULT true,
    auto_minutes BOOLEAN DEFAULT true,

    -- Timestamps
    initiated_at TIMESTAMP,
    answered_at TIMESTAMP,
    ended_at TIMESTAMP,
    ended_by UUID REFERENCES azalplus.users(id),
    duration_seconds INTEGER,

    -- Enregistrement
    recording_url TEXT,
    recording_path TEXT,
    recording_size_bytes BIGINT,

    -- Transcription
    transcription TEXT,
    transcription_language VARCHAR(10) DEFAULT 'fr',

    -- Compte-rendu
    minutes_content TEXT,
    minutes_status VARCHAR(20) DEFAULT 'pending',  -- pending, generating, sending, sent, failed
    minutes_sent_at TIMESTAMP,
    minutes_sent_to VARCHAR(255),

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    deleted_at TIMESTAMP,

    -- Constraints
    CONSTRAINT fk_phone_calls_tenant FOREIGN KEY (tenant_id) REFERENCES azalplus.tenants(id),
    CONSTRAINT fk_phone_calls_user FOREIGN KEY (user_id) REFERENCES azalplus.users(id),
    CONSTRAINT fk_phone_calls_callee FOREIGN KEY (callee_id) REFERENCES azalplus.users(id)
);

-- Index
CREATE INDEX IF NOT EXISTS idx_phone_calls_tenant ON azalplus.phone_calls(tenant_id);
CREATE INDEX IF NOT EXISTS idx_phone_calls_user ON azalplus.phone_calls(user_id);
CREATE INDEX IF NOT EXISTS idx_phone_calls_callee ON azalplus.phone_calls(callee_id);
CREATE INDEX IF NOT EXISTS idx_phone_calls_status ON azalplus.phone_calls(status);
CREATE INDEX IF NOT EXISTS idx_phone_calls_created ON azalplus.phone_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phone_calls_external_id ON azalplus.phone_calls(external_call_id);
CREATE INDEX IF NOT EXISTS idx_phone_calls_room ON azalplus.phone_calls(room_name);

-- Trigger updated_at
CREATE OR REPLACE FUNCTION azalplus.update_phone_calls_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_phone_calls_updated_at ON azalplus.phone_calls;
CREATE TRIGGER trg_phone_calls_updated_at
    BEFORE UPDATE ON azalplus.phone_calls
    FOR EACH ROW
    EXECUTE FUNCTION azalplus.update_phone_calls_updated_at();

-- =============================================================================
-- Table des parametres utilisateur (extension)
-- =============================================================================
-- Ajouter colonnes pour config email si elles n'existent pas

DO $$
BEGIN
    -- Verifier si la table user_settings existe, sinon la creer
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'azalplus' AND table_name = 'user_settings') THEN
        CREATE TABLE azalplus.user_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES azalplus.tenants(id),
            user_id UUID NOT NULL REFERENCES azalplus.users(id) UNIQUE,

            -- Config email (pour envoi compte-rendu)
            email_smtp_host VARCHAR(255),
            email_smtp_port INTEGER DEFAULT 587,
            email_smtp_user VARCHAR(255),
            email_smtp_password VARCHAR(255),  -- Chiffre en production
            email_from_address VARCHAR(255),
            email_from_name VARCHAR(255),
            email_signature TEXT,

            -- Preferences notifications
            notify_call_minutes BOOLEAN DEFAULT true,
            auto_send_minutes BOOLEAN DEFAULT true,

            -- Audit
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP
        );

        CREATE INDEX idx_user_settings_tenant ON azalplus.user_settings(tenant_id);
        CREATE INDEX idx_user_settings_user ON azalplus.user_settings(user_id);
    END IF;

    -- Ajouter colonnes manquantes a users
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'azalplus' AND table_name = 'users'
                   AND column_name = 'telephone_verified') THEN
        ALTER TABLE azalplus.users ADD COLUMN telephone_verified BOOLEAN DEFAULT false;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'azalplus' AND table_name = 'users'
                   AND column_name = 'device_token') THEN
        ALTER TABLE azalplus.users ADD COLUMN device_token VARCHAR(255);
    END IF;
END $$;

-- =============================================================================
-- Commentaires
-- =============================================================================
COMMENT ON TABLE azalplus.phone_calls IS 'Appels telephoniques avec transcription et compte-rendu automatique';
COMMENT ON COLUMN azalplus.phone_calls.call_type IS 'Type: app_to_app (WebRTC), app_to_phone (SIP), twilio_pstn (PSTN)';
COMMENT ON COLUMN azalplus.phone_calls.call_provider IS 'Provider: app (gratuit) ou twilio (option payante)';
COMMENT ON COLUMN azalplus.phone_calls.room_name IS 'Nom de la room LiveKit pour les appels app';
COMMENT ON COLUMN azalplus.phone_calls.auto_record IS 'Enregistrer automatiquement';
COMMENT ON COLUMN azalplus.phone_calls.auto_transcribe IS 'Transcrire automatiquement apres la fin';
COMMENT ON COLUMN azalplus.phone_calls.auto_minutes IS 'Generer compte-rendu automatiquement';
COMMENT ON COLUMN azalplus.phone_calls.minutes_status IS 'Statut: pending, generating, sending, sent, failed';

COMMENT ON TABLE azalplus.user_settings IS 'Parametres utilisateur incluant config email';
COMMENT ON COLUMN azalplus.user_settings.email_smtp_host IS 'Serveur SMTP pour envoi emails';
