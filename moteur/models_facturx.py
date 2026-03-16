# =============================================================================
# AZALPLUS - Factur-X Models (SQLAlchemy)
# =============================================================================
"""
Tables pour le tracking des soumissions et receptions Factur-X.

Tables:
- facturx_submissions : Factures envoyees via PPF/Chorus/PDP
- facturx_receptions  : Factures recues via PPF/Chorus/Email

Normes respectees:
- AZA-COFFRE-TEN-001: tenant_id sur chaque modele
- AZA-COFFRE-INT-001: hash SHA-256 obligatoire
- AZA-COFFRE-PDP-004: statuts facture trackes
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, Date, Numeric, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from uuid import uuid4
import enum


# =============================================================================
# Enums
# =============================================================================
class SubmissionProvider(str, enum.Enum):
    """Fournisseur de soumission Factur-X."""
    PPF = "PPF"           # Portail Public de Facturation
    CHORUS = "CHORUS"     # Chorus Pro
    PDP = "PDP"           # Plateforme de Dematerialisation Partenaire


class SubmissionStatus(str, enum.Enum):
    """Statut de soumission Factur-X (AZA-COFFRE-PDP-004)."""
    PENDING = "PENDING"       # En attente d'envoi
    SUBMITTED = "SUBMITTED"   # Soumis au fournisseur
    DELIVERED = "DELIVERED"   # Livre au destinataire
    ACCEPTED = "ACCEPTED"     # Accepte par le destinataire
    REJECTED = "REJECTED"     # Rejete
    PAID = "PAID"             # Paye


class FacturXProfile(str, enum.Enum):
    """Profils Factur-X supportes (AZA-COFFRE-PDP-001)."""
    MINIMUM = "MINIMUM"
    BASIC_WL = "BASIC_WL"
    BASIC = "BASIC"
    EN16931 = "EN16931"
    EXTENDED = "EXTENDED"


class ReceptionProvider(str, enum.Enum):
    """Source de reception Factur-X."""
    PPF = "PPF"
    CHORUS = "CHORUS"
    EMAIL = "EMAIL"


class ReceptionStatus(str, enum.Enum):
    """Statut de reception Factur-X."""
    RECEIVED = "RECEIVED"     # Recue
    VALIDATED = "VALIDATED"   # Validee (format OK)
    IMPORTED = "IMPORTED"     # Importee dans le systeme
    REJECTED = "REJECTED"     # Rejetee


# =============================================================================
# SQL de creation des tables
# =============================================================================
FACTURX_TABLES_SQL = """
-- Schema azalplus doit exister
CREATE SCHEMA IF NOT EXISTS azalplus;

-- =============================================================================
-- Table des soumissions Factur-X
-- =============================================================================
CREATE TABLE IF NOT EXISTS azalplus.facturx_submissions (
    -- Identifiants
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,

    -- Reference facture source
    invoice_id UUID NOT NULL,
    invoice_number VARCHAR(100) NOT NULL,

    -- Fournisseur et profil
    provider VARCHAR(20) NOT NULL DEFAULT 'PPF',
    profile VARCHAR(20) NOT NULL DEFAULT 'MINIMUM',

    -- Statut (AZA-COFFRE-PDP-004)
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    -- Hashes integrite (AZA-COFFRE-INT-001)
    pdf_hash_sha256 VARCHAR(64) NOT NULL,
    xml_hash_sha256 VARCHAR(64) NOT NULL,

    -- Stockage
    pdf_storage_url VARCHAR(500),
    xml_storage_url VARCHAR(500),

    -- Reference externe (ID retourne par PPF/Chorus)
    external_id VARCHAR(255),

    -- Timestamps de cycle de vie
    submitted_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,

    -- Reponse brute du fournisseur
    response_raw JSONB,

    -- Gestion erreurs
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,

    -- Timestamps systeme
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Contrainte provider valide
    CONSTRAINT chk_submission_provider CHECK (
        provider IN ('PPF', 'CHORUS', 'PDP')
    ),

    -- Contrainte status valide
    CONSTRAINT chk_submission_status CHECK (
        status IN ('PENDING', 'SUBMITTED', 'DELIVERED', 'ACCEPTED', 'REJECTED', 'PAID')
    ),

    -- Contrainte profile valide
    CONSTRAINT chk_submission_profile CHECK (
        profile IN ('MINIMUM', 'BASIC_WL', 'BASIC', 'EN16931', 'EXTENDED')
    )
);

-- Index sur tenant_id (AZA-COFFRE-TEN-001: isolation multi-tenant)
CREATE INDEX IF NOT EXISTS idx_facturx_submissions_tenant
    ON azalplus.facturx_submissions(tenant_id);

-- Index sur status (recherche par statut)
CREATE INDEX IF NOT EXISTS idx_facturx_submissions_status
    ON azalplus.facturx_submissions(status);

-- Index sur external_id (lookup par ID externe)
CREATE INDEX IF NOT EXISTS idx_facturx_submissions_external_id
    ON azalplus.facturx_submissions(external_id);

-- Index sur invoice_id (reference facture)
CREATE INDEX IF NOT EXISTS idx_facturx_submissions_invoice
    ON azalplus.facturx_submissions(invoice_id);

-- Index composite tenant + status (requetes frequentes)
CREATE INDEX IF NOT EXISTS idx_facturx_submissions_tenant_status
    ON azalplus.facturx_submissions(tenant_id, status);

-- Index sur created_at (tri chronologique)
CREATE INDEX IF NOT EXISTS idx_facturx_submissions_created
    ON azalplus.facturx_submissions(created_at DESC);

-- =============================================================================
-- Table des receptions Factur-X
-- =============================================================================
CREATE TABLE IF NOT EXISTS azalplus.facturx_receptions (
    -- Identifiants
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,

    -- Source
    provider VARCHAR(20) NOT NULL DEFAULT 'PPF',
    external_id VARCHAR(255),

    -- Informations emetteur
    sender_siret VARCHAR(14),
    sender_name VARCHAR(255),

    -- Informations facture
    invoice_number VARCHAR(100) NOT NULL,
    invoice_date DATE NOT NULL,
    total_ht NUMERIC(15, 2) NOT NULL,
    total_ttc NUMERIC(15, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    profile VARCHAR(20),

    -- Stockage
    pdf_storage_url VARCHAR(500),
    xml_storage_url VARCHAR(500),

    -- Hashes integrite (AZA-COFFRE-INT-001)
    pdf_hash_sha256 VARCHAR(64),
    xml_hash_sha256 VARCHAR(64),

    -- Donnees extraites (OCR/XML)
    extracted_data JSONB,

    -- Statut
    status VARCHAR(20) NOT NULL DEFAULT 'RECEIVED',

    -- Lien vers facture importee (si importe dans le systeme)
    linked_invoice_id UUID,

    -- Timestamps de cycle de vie
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    validated_at TIMESTAMP WITH TIME ZONE,
    imported_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps systeme
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Contrainte provider valide
    CONSTRAINT chk_reception_provider CHECK (
        provider IN ('PPF', 'CHORUS', 'EMAIL')
    ),

    -- Contrainte status valide
    CONSTRAINT chk_reception_status CHECK (
        status IN ('RECEIVED', 'VALIDATED', 'IMPORTED', 'REJECTED')
    ),

    -- Contrainte profile valide (si specifie)
    CONSTRAINT chk_reception_profile CHECK (
        profile IS NULL OR profile IN ('MINIMUM', 'BASIC_WL', 'BASIC', 'EN16931', 'EXTENDED')
    )
);

-- Index sur tenant_id (AZA-COFFRE-TEN-001: isolation multi-tenant)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_tenant
    ON azalplus.facturx_receptions(tenant_id);

-- Index sur status (recherche par statut)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_status
    ON azalplus.facturx_receptions(status);

-- Index sur external_id (lookup par ID externe)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_external_id
    ON azalplus.facturx_receptions(external_id);

-- Index sur sender_siret (recherche par emetteur)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_sender_siret
    ON azalplus.facturx_receptions(sender_siret);

-- Index composite tenant + status (requetes frequentes)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_tenant_status
    ON azalplus.facturx_receptions(tenant_id, status);

-- Index sur received_at (tri chronologique)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_received
    ON azalplus.facturx_receptions(received_at DESC);

-- Index sur invoice_date (recherche par date facture)
CREATE INDEX IF NOT EXISTS idx_facturx_receptions_invoice_date
    ON azalplus.facturx_receptions(invoice_date);

-- =============================================================================
-- Trigger pour updated_at automatique sur submissions
-- =============================================================================
CREATE OR REPLACE FUNCTION azalplus.update_facturx_submissions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_facturx_submissions_updated_at
    ON azalplus.facturx_submissions;

CREATE TRIGGER trg_facturx_submissions_updated_at
    BEFORE UPDATE ON azalplus.facturx_submissions
    FOR EACH ROW
    EXECUTE FUNCTION azalplus.update_facturx_submissions_updated_at();
"""


# =============================================================================
# Fonction d'initialisation des tables
# =============================================================================
async def create_facturx_tables():
    """Cree les tables Factur-X si elles n'existent pas."""
    from sqlalchemy import text
    import structlog

    from .db import Database

    logger = structlog.get_logger()

    try:
        with Database.get_session() as session:
            session.execute(text(FACTURX_TABLES_SQL))
            session.commit()
        logger.info("facturx_tables_created")
    except Exception as e:
        logger.error("facturx_tables_creation_failed", error=str(e))
        raise


# =============================================================================
# Dataclasses pour manipulation en memoire
# =============================================================================
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, Any
from uuid import UUID as PyUUID


@dataclass
class FacturXSubmission:
    """
    Soumission Factur-X.

    Represente une facture envoyee via PPF/Chorus/PDP.
    """
    id: PyUUID
    tenant_id: PyUUID
    invoice_id: PyUUID
    invoice_number: str
    provider: SubmissionProvider
    profile: FacturXProfile
    status: SubmissionStatus
    pdf_hash_sha256: str
    xml_hash_sha256: str
    pdf_storage_url: Optional[str] = None
    xml_storage_url: Optional[str] = None
    external_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    response_raw: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour insertion DB."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "invoice_id": str(self.invoice_id),
            "invoice_number": self.invoice_number,
            "provider": self.provider.value if isinstance(self.provider, enum.Enum) else self.provider,
            "profile": self.profile.value if isinstance(self.profile, enum.Enum) else self.profile,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "pdf_hash_sha256": self.pdf_hash_sha256,
            "xml_hash_sha256": self.xml_hash_sha256,
            "pdf_storage_url": self.pdf_storage_url,
            "xml_storage_url": self.xml_storage_url,
            "external_id": self.external_id,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "response_raw": self.response_raw,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FacturXSubmission":
        """Cree une instance depuis un dictionnaire DB."""
        return cls(
            id=PyUUID(str(data["id"])) if data.get("id") else uuid4(),
            tenant_id=PyUUID(str(data["tenant_id"])),
            invoice_id=PyUUID(str(data["invoice_id"])),
            invoice_number=data["invoice_number"],
            provider=SubmissionProvider(data.get("provider", "PPF")),
            profile=FacturXProfile(data.get("profile", "MINIMUM")),
            status=SubmissionStatus(data.get("status", "PENDING")),
            pdf_hash_sha256=data["pdf_hash_sha256"],
            xml_hash_sha256=data["xml_hash_sha256"],
            pdf_storage_url=data.get("pdf_storage_url"),
            xml_storage_url=data.get("xml_storage_url"),
            external_id=data.get("external_id"),
            submitted_at=data.get("submitted_at"),
            acknowledged_at=data.get("acknowledged_at"),
            delivered_at=data.get("delivered_at"),
            response_raw=data.get("response_raw"),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            created_at=data.get("created_at", datetime.now()),
            updated_at=data.get("updated_at", datetime.now()),
        )


@dataclass
class FacturXReception:
    """
    Reception Factur-X.

    Represente une facture recue via PPF/Chorus/Email.
    """
    id: PyUUID
    tenant_id: PyUUID
    provider: ReceptionProvider
    invoice_number: str
    invoice_date: date
    total_ht: float
    total_ttc: float
    external_id: Optional[str] = None
    sender_siret: Optional[str] = None
    sender_name: Optional[str] = None
    currency: str = "EUR"
    profile: Optional[FacturXProfile] = None
    pdf_storage_url: Optional[str] = None
    xml_storage_url: Optional[str] = None
    pdf_hash_sha256: Optional[str] = None
    xml_hash_sha256: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    status: ReceptionStatus = ReceptionStatus.RECEIVED
    linked_invoice_id: Optional[PyUUID] = None
    received_at: datetime = field(default_factory=datetime.now)
    validated_at: Optional[datetime] = None
    imported_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour insertion DB."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "provider": self.provider.value if isinstance(self.provider, enum.Enum) else self.provider,
            "external_id": self.external_id,
            "sender_siret": self.sender_siret,
            "sender_name": self.sender_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat() if isinstance(self.invoice_date, date) else self.invoice_date,
            "total_ht": float(self.total_ht),
            "total_ttc": float(self.total_ttc),
            "currency": self.currency,
            "profile": self.profile.value if isinstance(self.profile, enum.Enum) else self.profile,
            "pdf_storage_url": self.pdf_storage_url,
            "xml_storage_url": self.xml_storage_url,
            "pdf_hash_sha256": self.pdf_hash_sha256,
            "xml_hash_sha256": self.xml_hash_sha256,
            "extracted_data": self.extracted_data,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "linked_invoice_id": str(self.linked_invoice_id) if self.linked_invoice_id else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "imported_at": self.imported_at.isoformat() if self.imported_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FacturXReception":
        """Cree une instance depuis un dictionnaire DB."""
        # Parse invoice_date
        invoice_date = data["invoice_date"]
        if isinstance(invoice_date, str):
            invoice_date = date.fromisoformat(invoice_date)

        # Parse profile if present
        profile = None
        if data.get("profile"):
            profile = FacturXProfile(data["profile"])

        # Parse linked_invoice_id if present
        linked_invoice_id = None
        if data.get("linked_invoice_id"):
            linked_invoice_id = PyUUID(str(data["linked_invoice_id"]))

        return cls(
            id=PyUUID(str(data["id"])) if data.get("id") else uuid4(),
            tenant_id=PyUUID(str(data["tenant_id"])),
            provider=ReceptionProvider(data.get("provider", "PPF")),
            external_id=data.get("external_id"),
            sender_siret=data.get("sender_siret"),
            sender_name=data.get("sender_name"),
            invoice_number=data["invoice_number"],
            invoice_date=invoice_date,
            total_ht=float(data["total_ht"]),
            total_ttc=float(data["total_ttc"]),
            currency=data.get("currency", "EUR"),
            profile=profile,
            pdf_storage_url=data.get("pdf_storage_url"),
            xml_storage_url=data.get("xml_storage_url"),
            pdf_hash_sha256=data.get("pdf_hash_sha256"),
            xml_hash_sha256=data.get("xml_hash_sha256"),
            extracted_data=data.get("extracted_data"),
            status=ReceptionStatus(data.get("status", "RECEIVED")),
            linked_invoice_id=linked_invoice_id,
            received_at=data.get("received_at", datetime.now()),
            validated_at=data.get("validated_at"),
            imported_at=data.get("imported_at"),
            created_at=data.get("created_at", datetime.now()),
        )


# =============================================================================
# Service CRUD avec isolation tenant
# =============================================================================
class FacturXService:
    """
    Service pour les operations Factur-X.

    Respecte AZA-COFFRE-TEN-004: tenant_id injecte dans le constructeur.
    """

    def __init__(self, tenant_id: PyUUID):
        """
        Initialise le service avec un tenant_id.

        Args:
            tenant_id: UUID du tenant (isolation obligatoire)
        """
        self.tenant_id = tenant_id

    # =========================================================================
    # Submissions
    # =========================================================================
    def create_submission(
        self,
        invoice_id: PyUUID,
        invoice_number: str,
        pdf_hash_sha256: str,
        xml_hash_sha256: str,
        provider: SubmissionProvider = SubmissionProvider.PPF,
        profile: FacturXProfile = FacturXProfile.MINIMUM,
        pdf_storage_url: Optional[str] = None,
        xml_storage_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cree une nouvelle soumission Factur-X.

        Args:
            invoice_id: ID de la facture source
            invoice_number: Numero de facture
            pdf_hash_sha256: Hash SHA-256 du PDF
            xml_hash_sha256: Hash SHA-256 du XML
            provider: Fournisseur (PPF, CHORUS, PDP)
            profile: Profil Factur-X
            pdf_storage_url: URL de stockage du PDF
            xml_storage_url: URL de stockage du XML

        Returns:
            Enregistrement cree
        """
        from sqlalchemy import text
        from .db import Database
        import structlog

        logger = structlog.get_logger()

        submission_id = uuid4()
        now = datetime.now()

        data = {
            "id": str(submission_id),
            "tenant_id": str(self.tenant_id),
            "invoice_id": str(invoice_id),
            "invoice_number": invoice_number,
            "provider": provider.value,
            "profile": profile.value,
            "status": SubmissionStatus.PENDING.value,
            "pdf_hash_sha256": pdf_hash_sha256,
            "xml_hash_sha256": xml_hash_sha256,
            "pdf_storage_url": pdf_storage_url,
            "xml_storage_url": xml_storage_url,
            "retry_count": 0,
            "created_at": now,
            "updated_at": now,
        }

        with Database.get_session() as session:
            sql = text("""
                INSERT INTO azalplus.facturx_submissions (
                    id, tenant_id, invoice_id, invoice_number, provider, profile,
                    status, pdf_hash_sha256, xml_hash_sha256, pdf_storage_url,
                    xml_storage_url, retry_count, created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :invoice_id, :invoice_number, :provider, :profile,
                    :status, :pdf_hash_sha256, :xml_hash_sha256, :pdf_storage_url,
                    :xml_storage_url, :retry_count, :created_at, :updated_at
                )
                RETURNING *
            """)
            result = session.execute(sql, data)
            session.commit()
            row = result.fetchone()

            logger.info(
                "facturx_submission_created",
                submission_id=str(submission_id),
                invoice_number=invoice_number,
                tenant_id=str(self.tenant_id),
            )

            return dict(row._mapping)

    def get_submission(self, submission_id: PyUUID) -> Optional[Dict[str, Any]]:
        """
        Recupere une soumission par ID avec isolation tenant.

        Args:
            submission_id: ID de la soumission

        Returns:
            Soumission ou None
        """
        from sqlalchemy import text
        from .db import Database

        with Database.get_session() as session:
            sql = text("""
                SELECT * FROM azalplus.facturx_submissions
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            result = session.execute(sql, {
                "id": str(submission_id),
                "tenant_id": str(self.tenant_id),
            })
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def list_submissions(
        self,
        status: Optional[SubmissionStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Dict[str, Any]]:
        """
        Liste les soumissions avec filtres.

        Args:
            status: Filtrer par statut
            limit: Limite de resultats
            offset: Offset pour pagination

        Returns:
            Liste des soumissions
        """
        from sqlalchemy import text
        from .db import Database

        params = {
            "tenant_id": str(self.tenant_id),
            "limit": limit,
            "offset": offset,
        }

        sql = """
            SELECT * FROM azalplus.facturx_submissions
            WHERE tenant_id = :tenant_id
        """

        if status:
            sql += " AND status = :status"
            params["status"] = status.value

        sql += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        with Database.get_session() as session:
            result = session.execute(text(sql), params)
            return [dict(row._mapping) for row in result]

    def update_submission_status(
        self,
        submission_id: PyUUID,
        status: SubmissionStatus,
        external_id: Optional[str] = None,
        response_raw: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Met a jour le statut d'une soumission.

        Args:
            submission_id: ID de la soumission
            status: Nouveau statut
            external_id: ID externe (PPF/Chorus)
            response_raw: Reponse brute
            error_message: Message d'erreur

        Returns:
            Soumission mise a jour ou None
        """
        from sqlalchemy import text
        from .db import Database
        import structlog

        logger = structlog.get_logger()

        now = datetime.now()
        params = {
            "id": str(submission_id),
            "tenant_id": str(self.tenant_id),
            "status": status.value,
            "updated_at": now,
        }

        set_clauses = ["status = :status", "updated_at = :updated_at"]

        # Timestamps selon le statut
        if status == SubmissionStatus.SUBMITTED:
            set_clauses.append("submitted_at = :submitted_at")
            params["submitted_at"] = now
        elif status == SubmissionStatus.DELIVERED:
            set_clauses.append("delivered_at = :delivered_at")
            params["delivered_at"] = now
        elif status in (SubmissionStatus.ACCEPTED, SubmissionStatus.REJECTED):
            set_clauses.append("acknowledged_at = :acknowledged_at")
            params["acknowledged_at"] = now

        if external_id:
            set_clauses.append("external_id = :external_id")
            params["external_id"] = external_id

        if response_raw:
            set_clauses.append("response_raw = :response_raw")
            params["response_raw"] = response_raw

        if error_message:
            set_clauses.append("error_message = :error_message")
            params["error_message"] = error_message

        sql = f"""
            UPDATE azalplus.facturx_submissions
            SET {', '.join(set_clauses)}
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """

        with Database.get_session() as session:
            result = session.execute(text(sql), params)
            session.commit()
            row = result.fetchone()

            if row:
                logger.info(
                    "facturx_submission_status_updated",
                    submission_id=str(submission_id),
                    status=status.value,
                    tenant_id=str(self.tenant_id),
                )

            return dict(row._mapping) if row else None

    def increment_retry_count(self, submission_id: PyUUID) -> Optional[Dict[str, Any]]:
        """
        Incremente le compteur de retry.

        Args:
            submission_id: ID de la soumission

        Returns:
            Soumission mise a jour ou None
        """
        from sqlalchemy import text
        from .db import Database

        sql = text("""
            UPDATE azalplus.facturx_submissions
            SET retry_count = retry_count + 1, updated_at = NOW()
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        with Database.get_session() as session:
            result = session.execute(sql, {
                "id": str(submission_id),
                "tenant_id": str(self.tenant_id),
            })
            session.commit()
            row = result.fetchone()
            return dict(row._mapping) if row else None

    # =========================================================================
    # Receptions
    # =========================================================================
    def create_reception(
        self,
        invoice_number: str,
        invoice_date: date,
        total_ht: float,
        total_ttc: float,
        provider: ReceptionProvider = ReceptionProvider.PPF,
        external_id: Optional[str] = None,
        sender_siret: Optional[str] = None,
        sender_name: Optional[str] = None,
        currency: str = "EUR",
        profile: Optional[FacturXProfile] = None,
        pdf_storage_url: Optional[str] = None,
        xml_storage_url: Optional[str] = None,
        pdf_hash_sha256: Optional[str] = None,
        xml_hash_sha256: Optional[str] = None,
        extracted_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Cree une nouvelle reception Factur-X.

        Args:
            invoice_number: Numero de facture
            invoice_date: Date de facture
            total_ht: Montant HT
            total_ttc: Montant TTC
            provider: Source (PPF, CHORUS, EMAIL)
            external_id: ID externe
            sender_siret: SIRET emetteur
            sender_name: Nom emetteur
            currency: Devise
            profile: Profil Factur-X
            pdf_storage_url: URL PDF
            xml_storage_url: URL XML
            pdf_hash_sha256: Hash PDF
            xml_hash_sha256: Hash XML
            extracted_data: Donnees extraites

        Returns:
            Enregistrement cree
        """
        from sqlalchemy import text
        from .db import Database
        import structlog

        logger = structlog.get_logger()

        reception_id = uuid4()
        now = datetime.now()

        data = {
            "id": str(reception_id),
            "tenant_id": str(self.tenant_id),
            "provider": provider.value,
            "external_id": external_id,
            "sender_siret": sender_siret,
            "sender_name": sender_name,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "total_ht": total_ht,
            "total_ttc": total_ttc,
            "currency": currency,
            "profile": profile.value if profile else None,
            "pdf_storage_url": pdf_storage_url,
            "xml_storage_url": xml_storage_url,
            "pdf_hash_sha256": pdf_hash_sha256,
            "xml_hash_sha256": xml_hash_sha256,
            "extracted_data": extracted_data,
            "status": ReceptionStatus.RECEIVED.value,
            "received_at": now,
            "created_at": now,
        }

        with Database.get_session() as session:
            sql = text("""
                INSERT INTO azalplus.facturx_receptions (
                    id, tenant_id, provider, external_id, sender_siret, sender_name,
                    invoice_number, invoice_date, total_ht, total_ttc, currency, profile,
                    pdf_storage_url, xml_storage_url, pdf_hash_sha256, xml_hash_sha256,
                    extracted_data, status, received_at, created_at
                ) VALUES (
                    :id, :tenant_id, :provider, :external_id, :sender_siret, :sender_name,
                    :invoice_number, :invoice_date, :total_ht, :total_ttc, :currency, :profile,
                    :pdf_storage_url, :xml_storage_url, :pdf_hash_sha256, :xml_hash_sha256,
                    :extracted_data, :status, :received_at, :created_at
                )
                RETURNING *
            """)
            result = session.execute(sql, data)
            session.commit()
            row = result.fetchone()

            logger.info(
                "facturx_reception_created",
                reception_id=str(reception_id),
                invoice_number=invoice_number,
                tenant_id=str(self.tenant_id),
            )

            return dict(row._mapping)

    def get_reception(self, reception_id: PyUUID) -> Optional[Dict[str, Any]]:
        """
        Recupere une reception par ID avec isolation tenant.

        Args:
            reception_id: ID de la reception

        Returns:
            Reception ou None
        """
        from sqlalchemy import text
        from .db import Database

        with Database.get_session() as session:
            sql = text("""
                SELECT * FROM azalplus.facturx_receptions
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            result = session.execute(sql, {
                "id": str(reception_id),
                "tenant_id": str(self.tenant_id),
            })
            row = result.fetchone()
            return dict(row._mapping) if row else None

    def list_receptions(
        self,
        status: Optional[ReceptionStatus] = None,
        sender_siret: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Dict[str, Any]]:
        """
        Liste les receptions avec filtres.

        Args:
            status: Filtrer par statut
            sender_siret: Filtrer par SIRET emetteur
            limit: Limite de resultats
            offset: Offset pour pagination

        Returns:
            Liste des receptions
        """
        from sqlalchemy import text
        from .db import Database

        params = {
            "tenant_id": str(self.tenant_id),
            "limit": limit,
            "offset": offset,
        }

        sql = """
            SELECT * FROM azalplus.facturx_receptions
            WHERE tenant_id = :tenant_id
        """

        if status:
            sql += " AND status = :status"
            params["status"] = status.value

        if sender_siret:
            sql += " AND sender_siret = :sender_siret"
            params["sender_siret"] = sender_siret

        sql += " ORDER BY received_at DESC LIMIT :limit OFFSET :offset"

        with Database.get_session() as session:
            result = session.execute(text(sql), params)
            return [dict(row._mapping) for row in result]

    def update_reception_status(
        self,
        reception_id: PyUUID,
        status: ReceptionStatus,
        linked_invoice_id: Optional[PyUUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Met a jour le statut d'une reception.

        Args:
            reception_id: ID de la reception
            status: Nouveau statut
            linked_invoice_id: ID facture liee (si importee)

        Returns:
            Reception mise a jour ou None
        """
        from sqlalchemy import text
        from .db import Database
        import structlog

        logger = structlog.get_logger()

        now = datetime.now()
        params = {
            "id": str(reception_id),
            "tenant_id": str(self.tenant_id),
            "status": status.value,
        }

        set_clauses = ["status = :status"]

        # Timestamps selon le statut
        if status == ReceptionStatus.VALIDATED:
            set_clauses.append("validated_at = :validated_at")
            params["validated_at"] = now
        elif status == ReceptionStatus.IMPORTED:
            set_clauses.append("imported_at = :imported_at")
            params["imported_at"] = now

        if linked_invoice_id:
            set_clauses.append("linked_invoice_id = :linked_invoice_id")
            params["linked_invoice_id"] = str(linked_invoice_id)

        sql = f"""
            UPDATE azalplus.facturx_receptions
            SET {', '.join(set_clauses)}
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """

        with Database.get_session() as session:
            result = session.execute(text(sql), params)
            session.commit()
            row = result.fetchone()

            if row:
                logger.info(
                    "facturx_reception_status_updated",
                    reception_id=str(reception_id),
                    status=status.value,
                    tenant_id=str(self.tenant_id),
                )

            return dict(row._mapping) if row else None
