# =============================================================================
# AZALPLUS - Debug Models (SQLAlchemy)
# =============================================================================
"""
Tables pour le système de debug Simon.

Tables:
- debug_bugs         : Bugs soumis par les debuggers
- debug_tests        : Tests proposés par Simon
- debug_conversations: Historique des conversations (mode chat)
- debug_audit        : Audit de toutes les actions
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uuid import uuid4
import enum

from ..db import Database


# =============================================================================
# Enums
# =============================================================================
class BugStatut(str, enum.Enum):
    """Statuts possibles d'un bug."""
    NOUVEAU = "nouveau"
    EN_ANALYSE = "en_analyse"
    TESTS_PROPOSES = "tests_proposes"
    EN_TEST = "en_test"
    RESOLU = "resolu"
    FERME = "ferme"


class BugSource(str, enum.Enum):
    """Source de création du bug."""
    TICKET = "ticket"
    CHAT = "chat"
    REPLAY = "replay"


class TestStatut(str, enum.Enum):
    """Statut d'un test."""
    PENDING = "pending"
    OK = "ok"
    KO = "ko"


class ConversationRole(str, enum.Enum):
    """Rôle dans la conversation."""
    USER = "user"
    SIMON = "simon"


# =============================================================================
# SQL de création des tables
# =============================================================================
DEBUG_TABLES_SQL = """
-- Schema azalplus doit exister
CREATE SCHEMA IF NOT EXISTS azalplus;

-- Table des bugs
CREATE TABLE IF NOT EXISTS azalplus.debug_bugs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    numero VARCHAR(20) NOT NULL,
    titre VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    logs_texte TEXT,
    screenshot_url VARCHAR(500),
    source VARCHAR(20) NOT NULL DEFAULT 'ticket',
    guardian_log_id UUID,
    statut VARCHAR(20) NOT NULL DEFAULT 'nouveau',
    cree_par UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT debug_bugs_numero_unique UNIQUE (tenant_id, numero)
);

-- Index pour recherche rapide
CREATE INDEX IF NOT EXISTS idx_debug_bugs_tenant ON azalplus.debug_bugs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_debug_bugs_statut ON azalplus.debug_bugs(statut);
CREATE INDEX IF NOT EXISTS idx_debug_bugs_cree_par ON azalplus.debug_bugs(cree_par);

-- Table des tests proposés par Simon
CREATE TABLE IF NOT EXISTS azalplus.debug_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bug_id UUID NOT NULL REFERENCES azalplus.debug_bugs(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    action TEXT NOT NULL,
    resultat_attendu TEXT NOT NULL,
    statut VARCHAR(10) NOT NULL DEFAULT 'pending',
    commentaire TEXT,
    valide_par UUID,
    valide_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT debug_tests_numero_unique UNIQUE (bug_id, numero)
);

-- Index
CREATE INDEX IF NOT EXISTS idx_debug_tests_bug ON azalplus.debug_tests(bug_id);
CREATE INDEX IF NOT EXISTS idx_debug_tests_statut ON azalplus.debug_tests(statut);

-- Table des conversations (mode chat)
CREATE TABLE IF NOT EXISTS azalplus.debug_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bug_id UUID NOT NULL REFERENCES azalplus.debug_bugs(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS idx_debug_conversations_bug ON azalplus.debug_conversations(bug_id);
CREATE INDEX IF NOT EXISTS idx_debug_conversations_created ON azalplus.debug_conversations(created_at);

-- Table d'audit
CREATE TABLE IF NOT EXISTS azalplus.debug_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    bug_id UUID,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS idx_debug_audit_tenant ON azalplus.debug_audit(tenant_id);
CREATE INDEX IF NOT EXISTS idx_debug_audit_user ON azalplus.debug_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_debug_audit_action ON azalplus.debug_audit(action);
CREATE INDEX IF NOT EXISTS idx_debug_audit_created ON azalplus.debug_audit(created_at);

-- Sequence pour numérotation des bugs (DBG-YYYY-00001)
CREATE SEQUENCE IF NOT EXISTS azalplus.debug_bug_seq START 1;
"""


# =============================================================================
# Fonction d'initialisation des tables
# =============================================================================
async def create_debug_tables():
    """Crée les tables debug si elles n'existent pas."""
    from sqlalchemy import text
    import structlog

    logger = structlog.get_logger()

    try:
        with Database.get_session() as session:
            session.execute(text(DEBUG_TABLES_SQL))
            session.commit()
        logger.info("debug_tables_created")
    except Exception as e:
        logger.error("debug_tables_creation_failed", error=str(e))
        raise


# =============================================================================
# Fonctions utilitaires
# =============================================================================
def generate_bug_numero(tenant_id: str) -> str:
    """Génère un numéro de bug unique: DBG-YYYY-00001."""
    from datetime import datetime
    from sqlalchemy import text

    year = datetime.now().year

    with Database.get_session() as session:
        result = session.execute(
            text("SELECT nextval('azalplus.debug_bug_seq')")
        )
        seq = result.scalar()

    return f"DBG-{year}-{seq:05d}"
