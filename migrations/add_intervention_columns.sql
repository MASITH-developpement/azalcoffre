-- Migration: Ajouter colonnes manquantes a la table interventions
-- Date: 2026-03-10

-- Colonnes rapport/workflow technicien
DO $$
BEGIN
    -- Photos
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='photos_avant') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN photos_avant JSONB DEFAULT '[]';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='photos_apres') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN photos_apres JSONB DEFAULT '[]';
    END IF;

    -- Constat et travaux
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='constat_arrivee') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN constat_arrivee TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='travaux_realises') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN travaux_realises TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='anomalies') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN anomalies TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='recommandations') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN recommandations TEXT;
    END IF;

    -- Materiel structure
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='materiel_utilise_lignes') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN materiel_utilise_lignes JSONB DEFAULT '[]';
    END IF;

    -- Validation client
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='avis_client') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN avis_client INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='appreciation_client') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN appreciation_client TEXT;
    END IF;

    -- Signature
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='signature_client') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN signature_client TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='nom_signataire') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN nom_signataire VARCHAR(255);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='date_signature') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN date_signature TIMESTAMP;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='is_signed') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN is_signed BOOLEAN DEFAULT FALSE;
    END IF;

    -- Facture generee
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='azalplus' AND table_name='interventions' AND column_name='facture_generee_id') THEN
        ALTER TABLE azalplus.interventions ADD COLUMN facture_generee_id UUID;
    END IF;

    RAISE NOTICE 'Migration interventions terminee avec succes';
END $$;
