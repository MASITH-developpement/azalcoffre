# =============================================================================
# AZALPLUS - Routes API Paiements (Fintecture Open Banking)
# =============================================================================
"""
Routes pour les paiements Open Banking via Fintecture.

Endpoints:
    POST /api/paiements/create          - Créer un lien de paiement
    GET  /api/paiements/{id}            - Statut d'un paiement
    GET  /api/paiements/facture/{id}    - Paiements d'une facture
    POST /api/paiements/link            - Générer lien paiement facture
    GET  /api/paiements/banks           - Liste des banques
    GET  /api/paiements/commissions     - Calculer les commissions
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from integrations.settings import get_settings, Settings
from integrations.fintecture import (
    FintectureClient,
    FintecturePaymentService,
    PaymentRequest,
    PaymentStatus,
    FintectureError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paiements", tags=["paiements"])


# =============================================================================
# Modèles Pydantic
# =============================================================================

class CreatePaymentRequest(BaseModel):
    """Requête création paiement."""
    amount: float = Field(..., gt=0, description="Montant en EUR")
    reference: str = Field(..., min_length=1, max_length=35, description="Référence unique")
    description: str = Field("", max_length=140, description="Description")
    beneficiary_name: str = Field(..., min_length=1, description="Nom bénéficiaire")
    beneficiary_iban: str = Field(..., min_length=14, max_length=34, description="IBAN")
    beneficiary_swift: str = Field("", max_length=11, description="BIC/SWIFT")
    customer_email: Optional[str] = Field(None, description="Email client")
    customer_name: Optional[str] = Field(None, description="Nom client")
    redirect_uri: str = Field(..., description="URL redirection succès")
    webhook_uri: Optional[str] = Field(None, description="URL webhook")
    metadata: Optional[dict] = Field(None, description="Métadonnées libres")


class CreatePaymentResponse(BaseModel):
    """Réponse création paiement."""
    payment_id: str
    payment_url: str
    status: str
    created_at: str
    commissions: dict


class InvoicePaymentRequest(BaseModel):
    """Requête paiement facture."""
    facture_id: UUID
    redirect_url: Optional[str] = None


class PaymentStatusResponse(BaseModel):
    """Statut d'un paiement."""
    payment_id: str
    status: str
    amount: float
    currency: str
    reference: str
    execution_date: Optional[str] = None
    bank_name: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class CommissionCalculation(BaseModel):
    """Calcul des commissions."""
    montant_brut: float
    commission_fintecture: float
    commission_fintecture_pct: float
    commission_azalplus: float
    commission_azalplus_pct: float
    commission_totale: float
    commission_totale_pct: float
    montant_net: float


class BankInfo(BaseModel):
    """Information banque."""
    id: str
    name: str
    logo: Optional[str] = None
    country: str
    pis_enabled: bool


# =============================================================================
# Dépendances
# =============================================================================

def get_fintecture_client(settings: Settings = Depends(get_settings)) -> FintectureClient:
    """Récupérer le client Fintecture."""
    if not settings.fintecture.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Fintecture non configuré. Vérifiez les variables FINTECTURE_*"
        )
    return FintectureClient(settings.fintecture.to_config())


# =============================================================================
# Routes
# =============================================================================

@router.post("/create", response_model=CreatePaymentResponse)
async def create_payment(
    request: CreatePaymentRequest,
    client: FintectureClient = Depends(get_fintecture_client),
    settings: Settings = Depends(get_settings)
):
    """
    Créer un lien de paiement Open Banking.

    Le client recevra une URL pour payer via sa banque.
    Commission: 1.29% (Fintecture 0.99% + AZALPLUS 0.30%)
    """
    try:
        # Construire le webhook_uri si non fourni
        webhook_uri = request.webhook_uri or f"{settings.app_url}/api/webhooks/fintecture"

        payment_request = PaymentRequest(
            amount=request.amount,
            reference=request.reference,
            description=request.description,
            beneficiary_name=request.beneficiary_name,
            beneficiary_iban=request.beneficiary_iban,
            beneficiary_swift=request.beneficiary_swift,
            customer_email=request.customer_email,
            customer_name=request.customer_name,
            redirect_uri=request.redirect_uri,
            webhook_uri=webhook_uri,
            metadata=request.metadata
        )

        response = await client.create_payment(payment_request)

        # Calculer les commissions
        commissions = client.calculate_commission(request.amount)

        return CreatePaymentResponse(
            payment_id=response.payment_id,
            payment_url=response.connect_url,
            status=response.status.value,
            created_at=response.created_at.isoformat(),
            commissions=commissions
        )

    except FintectureError as e:
        logger.error(f"Erreur Fintecture: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.get("/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_id: str,
    client: FintectureClient = Depends(get_fintecture_client)
):
    """
    Récupérer le statut d'un paiement.

    Statuts possibles:
    - created: Lien créé
    - pending: En attente de validation
    - processing: En cours de traitement
    - completed: Paiement reçu
    - failed: Échec
    - cancelled: Annulé
    """
    try:
        status = await client.get_payment_status(payment_id)

        return PaymentStatusResponse(
            payment_id=status.payment_id,
            status=status.status.value,
            amount=status.amount,
            currency=status.currency,
            reference=status.reference,
            execution_date=status.execution_date.isoformat() if status.execution_date else None,
            bank_name=status.bank_name,
            error_code=status.error_code,
            error_message=status.error_message
        )

    except FintectureError as e:
        if "non trouvé" in str(e):
            raise HTTPException(status_code=404, detail="Paiement non trouvé")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/facture/{facture_id}/link")
async def create_invoice_payment_link(
    facture_id: UUID,
    redirect_url: Optional[str] = None,
    settings: Settings = Depends(get_settings)
):
    """
    Générer un lien de paiement pour une facture existante.

    Récupère les informations de la facture et crée automatiquement
    le lien de paiement avec les bonnes références.
    """
    if not settings.fintecture.is_configured:
        raise HTTPException(status_code=503, detail="Fintecture non configuré")

    # TODO: Injecter la connexion DB
    service = FintecturePaymentService(db=None, tenant_id=UUID("00000000-0000-0000-0000-000000000000"))

    try:
        result = await service.create_invoice_payment_link(
            facture_id=facture_id,
            redirect_url=redirect_url or f"{settings.app_url}/factures/{facture_id}/paiement/success",
            webhook_url=f"{settings.app_url}/api/webhooks/fintecture"
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Erreur création lien paiement: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


@router.get("/banks", response_model=list[BankInfo])
async def list_banks(
    country: str = Query("FR", description="Code pays ISO"),
    client: FintectureClient = Depends(get_fintecture_client)
):
    """
    Lister les banques disponibles pour le paiement.

    Retourne les banques supportées par Fintecture pour le pays spécifié.
    La plupart des banques françaises sont supportées (~99% couverture).
    """
    try:
        banks = await client.get_banks(country)

        return [
            BankInfo(
                id=bank["id"],
                name=bank["name"],
                logo=bank.get("logo"),
                country=bank["country"],
                pis_enabled=bank["pis_enabled"]
            )
            for bank in banks
            if bank["pis_enabled"]  # Seulement les banques supportant le paiement
        ]

    except FintectureError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.get("/commissions", response_model=CommissionCalculation)
async def calculate_commissions(
    amount: float = Query(..., gt=0, description="Montant en EUR"),
    client: FintectureClient = Depends(get_fintecture_client)
):
    """
    Calculer les commissions sur un montant.

    Commissions:
    - Fintecture: 0.99%
    - AZALPLUS: 0.30%
    - Total: 1.29%

    Exemple pour 100€:
    - Commission totale: 1.29€
    - Montant net: 98.71€
    """
    commissions = client.calculate_commission(amount)
    await client.close()

    return CommissionCalculation(**commissions)


@router.get("/stats")
async def get_payment_stats(
    period: str = Query("month", description="Période: day, week, month, year"),
    settings: Settings = Depends(get_settings)
):
    """
    Statistiques des paiements Open Banking.

    Retourne:
    - Nombre de paiements
    - Montant total
    - Commission totale générée
    - Taux de succès
    """
    # TODO: Implémenter avec la DB
    return {
        "period": period,
        "payments_count": 0,
        "total_amount": 0,
        "total_commission": 0,
        "success_rate": 0,
        "average_amount": 0
    }
