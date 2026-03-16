# =============================================================================
# AZALPLUS - Module Factures - Schémas Pydantic
# =============================================================================
"""
Schémas pour les endpoints preview, send, archive.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Preview
# =============================================================================

class PreviewLineSchema(BaseModel):
    """Ligne pour prévisualisation."""
    description: str
    quantity: float
    unit_price: float
    vat_rate: float = 20.0


class PreviewRequest(BaseModel):
    """Requête de prévisualisation."""
    invoice_id: UUID
    invoice_number: str
    invoice_date: str = Field(..., description="Date (YYYY-MM-DD)")
    due_date: Optional[str] = Field(None, description="Date échéance (YYYY-MM-DD)")
    payment_terms: Optional[str] = None
    notes: Optional[str] = None

    # Émetteur (récupéré depuis config tenant si non fourni)
    seller_name: Optional[str] = None
    seller_siret: Optional[str] = None
    seller_tva: Optional[str] = None
    seller_address: Optional[str] = None
    seller_city: Optional[str] = None
    seller_postal_code: Optional[str] = None
    seller_email: Optional[str] = None

    # Acheteur
    buyer_name: str
    buyer_siret: Optional[str] = None
    buyer_tva: Optional[str] = None
    buyer_address: Optional[str] = None
    buyer_city: Optional[str] = None
    buyer_postal_code: Optional[str] = None
    buyer_email: Optional[str] = None

    # Lignes
    lines: List[PreviewLineSchema]


class PreviewResponse(BaseModel):
    """Réponse prévisualisation."""
    success: bool
    invoice_number: str

    # Totaux calculés
    total_ht: float
    total_tva: float
    total_ttc: float

    # PDF (base64 pour affichage web)
    pdf_base64: Optional[str] = None

    # Options d'envoi disponibles
    available_send_options: List[str]
    recommended_send_option: str

    # Validation
    is_valid: bool
    validation_errors: List[str] = []


# =============================================================================
# Send
# =============================================================================

class SendRequest(BaseModel):
    """Requête d'envoi après prévisualisation."""
    invoice_id: UUID

    # Options d'envoi
    send_email: bool = True
    send_demat: bool = True

    # Options email
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_message: Optional[str] = None
    include_payment_link: bool = True

    # Options démat
    demat_channel: str = "AUTO"  # AUTO, CHORUS, PPF


class SendResponse(BaseModel):
    """Réponse envoi."""
    success: bool

    # Résultats email
    email_sent: bool = False
    email_error: Optional[str] = None

    # Résultats démat
    demat_sent: bool = False
    demat_error: Optional[str] = None
    demat_id: Optional[str] = None

    # Archivage
    archived: bool = False
    archive_id: Optional[UUID] = None


# =============================================================================
# Archive
# =============================================================================

class ArchiveInfoResponse(BaseModel):
    """Informations d'archivage AZALCOFFRE."""
    found: bool
    invoice_id: Optional[UUID] = None
    archive_id: Optional[UUID] = None
    archived_at: Optional[datetime] = None

    # Intégrité
    hash_value: Optional[str] = None
    hash_algorithm: str = "SHA-512"
    is_valid: bool = False

    # TSA
    tsa_timestamp: Optional[datetime] = None
    tsa_authority: Optional[str] = None

    # Accès
    coffre_url: Optional[str] = None
    retention_years: int = 10
    expires_at: Optional[str] = None


# =============================================================================
# Health
# =============================================================================

class HealthResponse(BaseModel):
    """État du module."""
    status: str
    module: str
    version: str
    capabilities: dict
