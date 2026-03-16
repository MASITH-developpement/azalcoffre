"""
AZALPLUS - Modèles partagés avec AZALCOFFRE
Types de données pour l'archivage légal NF Z42-013
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID


class ArchiveStatus(str, Enum):
    """Statut d'archivage du document"""
    PENDING = "PENDING"          # En attente d'archivage
    ARCHIVED = "ARCHIVED"        # Archivé avec succès
    VERIFIED = "VERIFIED"        # Intégrité vérifiée
    EXPIRED = "EXPIRED"          # Durée de conservation dépassée
    ERROR = "ERROR"              # Erreur d'archivage


class DocumentType(str, Enum):
    """Types de documents archivables"""
    FACTURE_EMISE = "FACTURE_EMISE"
    FACTURE_RECUE = "FACTURE_RECUE"
    AVOIR_EMIS = "AVOIR_EMIS"
    AVOIR_RECU = "AVOIR_RECU"
    DEVIS = "DEVIS"
    BON_COMMANDE = "BON_COMMANDE"
    BON_LIVRAISON = "BON_LIVRAISON"
    CONTRAT = "CONTRAT"
    BULLETIN_PAIE = "BULLETIN_PAIE"


class RetentionPeriod(Enum):
    """Durées de conservation légales"""
    FACTURES = 10           # 10 ans (Code de commerce L123-22)
    BULLETINS_PAIE = 50     # 50 ans (droit du travail)
    CONTRATS = 5            # 5 ans après expiration
    DOCUMENTS_SOCIAUX = 10  # 10 ans


@dataclass
class IntegrityProof:
    """
    Preuve d'intégrité d'un document archivé.
    Conforme NF Z42-013 : authenticité, intégrité, horodatage.
    """
    # Identifiants
    document_id: UUID
    archive_id: UUID

    # Hachage (intégrité)
    hash_algorithm: str = "SHA-512"
    hash_value: str = ""
    hash_computed_at: Optional[datetime] = None

    # Horodatage TSA RFC 3161 (authenticité temporelle)
    tsa_timestamp: Optional[datetime] = None
    tsa_token: Optional[str] = None  # Token base64 du serveur TSA
    tsa_authority: str = "freetsa.org"

    # Signature eIDAS (authenticité origine)
    signature_level: Optional[str] = None  # SIMPLE, ADVANCED, QUALIFIED
    signer_id: Optional[UUID] = None
    signed_at: Optional[datetime] = None

    # Chaînage audit (traçabilité)
    previous_hash: Optional[str] = None
    entry_hash: Optional[str] = None

    # Vérification
    last_verified_at: Optional[datetime] = None
    is_valid: bool = True
    verification_message: Optional[str] = None


@dataclass
class ArchivedDocument:
    """
    Document archivé dans AZALCOFFRE.
    Représentation côté AZALPLUS (métadonnées uniquement).
    """
    # Identifiants
    id: UUID
    tenant_id: UUID
    source_id: UUID              # ID dans AZALPLUS (facture, etc.)
    source_type: DocumentType

    # Métadonnées document
    document_number: str         # N° facture, devis, etc.
    document_date: date
    description: str = ""

    # Parties
    emitter_name: Optional[str] = None
    emitter_siret: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_siret: Optional[str] = None

    # Montants (pour factures)
    amount_ht: Optional[Decimal] = None
    amount_ttc: Optional[Decimal] = None
    currency: str = "EUR"

    # Archivage
    status: ArchiveStatus = ArchiveStatus.PENDING
    archived_at: Optional[datetime] = None
    retention_years: int = 10
    expires_at: Optional[date] = None

    # Preuve d'intégrité
    integrity_proof: Optional[IntegrityProof] = None

    # Accès au fichier (via AZALCOFFRE)
    file_name: str = ""
    file_size: int = 0
    mime_type: str = "application/pdf"
    coffre_url: Optional[str] = None  # URL pour téléchargement

    # Métadonnées techniques
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def is_accessible(self) -> bool:
        """Vérifie si le document est toujours accessible"""
        if self.status == ArchiveStatus.EXPIRED:
            return False
        if self.expires_at and date.today() > self.expires_at:
            return False
        return True

    def days_until_expiry(self) -> Optional[int]:
        """Nombre de jours avant expiration"""
        if not self.expires_at:
            return None
        delta = self.expires_at - date.today()
        return delta.days


@dataclass
class ArchiveRequest:
    """Requête d'archivage vers AZALCOFFRE"""
    tenant_id: UUID
    source_id: UUID
    source_type: DocumentType
    document_number: str
    document_date: date

    # Fichier à archiver
    file_content: bytes
    file_name: str
    mime_type: str = "application/pdf"

    # Métadonnées
    emitter_name: Optional[str] = None
    emitter_siret: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_siret: Optional[str] = None
    amount_ht: Optional[Decimal] = None
    amount_ttc: Optional[Decimal] = None

    # Options
    retention_years: int = 10
    request_tsa: bool = True      # Demander horodatage TSA
    request_signature: bool = False  # Demander signature eIDAS


@dataclass
class ArchiveSearchCriteria:
    """Critères de recherche dans les archives"""
    tenant_id: UUID

    # Filtres
    source_type: Optional[DocumentType] = None
    status: Optional[ArchiveStatus] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    document_number: Optional[str] = None
    emitter_siret: Optional[str] = None
    recipient_siret: Optional[str] = None

    # Pagination
    page: int = 1
    page_size: int = 20

    # Tri
    sort_by: str = "archived_at"
    sort_desc: bool = True
