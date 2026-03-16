# =============================================================================
# AZALPLUS - Routes API Banking (Swan BaaS)
# =============================================================================
"""
Routes pour le compte bancaire intégré via Swan.

Endpoints:
    POST /api/banking/onboarding       - Démarrer ouverture compte
    GET  /api/banking/onboarding/{id}  - Statut onboarding
    GET  /api/banking/account          - Infos compte
    GET  /api/banking/balance          - Solde
    GET  /api/banking/transactions     - Historique transactions
    POST /api/banking/transfer         - Effectuer un virement
    GET  /api/banking/cards            - Liste des cartes
    POST /api/banking/cards/virtual    - Créer carte virtuelle
"""

import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from integrations.settings import get_settings, Settings
from integrations.swan import (
    SwanClient,
    SwanBankingService,
    AccountHolder,
    AccountStatus,
    TransactionStatus,
    CardStatus,
    SwanError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/banking", tags=["banking"])


# =============================================================================
# Modèles Pydantic
# =============================================================================

class OnboardingRequest(BaseModel):
    """Requête ouverture de compte."""
    type: str = Field("Company", description="Individual ou Company")
    # Individual
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    # Company
    company_name: Optional[str] = None
    siren: Optional[str] = Field(None, min_length=9, max_length=9)
    # Commun
    email: str
    phone: Optional[str] = None
    redirect_url: Optional[str] = None


class OnboardingResponse(BaseModel):
    """Réponse ouverture compte."""
    onboarding_id: str
    onboarding_url: str
    status: str


class AccountResponse(BaseModel):
    """Informations compte."""
    id: str
    iban: str
    bic: str
    status: str
    name: str
    created_at: Optional[str] = None


class BalanceResponse(BaseModel):
    """Solde du compte."""
    iban: str
    balance_available: float
    balance_pending: float
    balance_reserved: float
    currency: str
    status: str


class TransactionResponse(BaseModel):
    """Transaction bancaire."""
    id: str
    type: str
    status: str
    amount: float
    currency: str
    direction: str
    counterparty_name: str
    reference: str
    label: str
    booked_at: Optional[str] = None
    value_date: Optional[str] = None


class TransferRequest(BaseModel):
    """Requête virement."""
    amount: float = Field(..., gt=0)
    beneficiary_iban: str = Field(..., min_length=14, max_length=34)
    beneficiary_name: str = Field(..., min_length=1)
    reference: str = Field(..., max_length=140)
    label: Optional[str] = Field(None, max_length=140)
    scheduled_date: Optional[date] = None


class TransferResponse(BaseModel):
    """Réponse virement."""
    transfer_id: str
    status: str
    amount: float
    beneficiary_iban: str
    reference: str


class CardResponse(BaseModel):
    """Carte bancaire."""
    id: str
    status: str
    type: str
    last_four_digits: str
    expiry_date: str
    holder_name: str


class CreateVirtualCardRequest(BaseModel):
    """Requête création carte virtuelle."""
    spending_limit: float = Field(1000, gt=0)
    spending_period: str = Field("Monthly", description="Daily, Weekly, Monthly, Always")


# =============================================================================
# Dépendances
# =============================================================================

def get_swan_client(settings: Settings = Depends(get_settings)) -> SwanClient:
    """Récupérer le client Swan."""
    if not settings.swan.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Swan non configuré. Vérifiez les variables SWAN_*"
        )
    return SwanClient(settings.swan.to_config())


async def get_tenant_account_id() -> str:
    """Récupérer l'ID du compte du tenant courant."""
    # TODO: Récupérer depuis le contexte tenant
    # Pour l'instant, retourner une erreur si pas de compte
    raise HTTPException(
        status_code=400,
        detail="Aucun compte bancaire associé. Effectuez d'abord l'onboarding."
    )


# =============================================================================
# Routes Onboarding
# =============================================================================

@router.post("/onboarding", response_model=OnboardingResponse)
async def start_onboarding(
    request: OnboardingRequest,
    client: SwanClient = Depends(get_swan_client),
    settings: Settings = Depends(get_settings)
):
    """
    Démarrer l'ouverture d'un compte bancaire.

    Lance le processus KYC Swan. L'utilisateur sera redirigé vers
    une page Swan pour vérifier son identité et les documents.

    Tarification:
    - Abonnement: 9.90€/mois
    - Virements SEPA: illimités
    - Carte physique: incluse
    """
    try:
        holder = AccountHolder(
            type=request.type,
            first_name=request.first_name,
            last_name=request.last_name,
            birth_date=request.birth_date,
            company_name=request.company_name,
            siren=request.siren,
            email=request.email,
            phone=request.phone or ""
        )

        redirect_url = request.redirect_url or f"{settings.app_url}/compte/ouverture/success"

        result = await client.create_onboarding(holder, redirect_url)

        return OnboardingResponse(
            onboarding_id=result["onboarding_id"],
            onboarding_url=result["onboarding_url"],
            status=result["status"]
        )

    except SwanError as e:
        logger.error(f"Erreur Swan onboarding: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.get("/onboarding/{onboarding_id}")
async def get_onboarding_status(
    onboarding_id: str,
    client: SwanClient = Depends(get_swan_client)
):
    """
    Récupérer le statut d'un onboarding.

    Statuts possibles:
    - Pending: En cours de vérification
    - Valid: Validé, compte créé
    - Invalid: Refusé
    """
    try:
        result = await client.get_onboarding_status(onboarding_id)

        return {
            "onboarding_id": result.get("id"),
            "status": result.get("statusInfo", {}).get("status"),
            "account": result.get("account")
        }

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


# =============================================================================
# Routes Compte
# =============================================================================

@router.get("/account", response_model=AccountResponse)
async def get_account(
    account_id: str = Query(..., description="ID du compte Swan"),
    client: SwanClient = Depends(get_swan_client)
):
    """
    Récupérer les informations du compte bancaire.
    """
    try:
        account = await client.get_account(account_id)

        return AccountResponse(
            id=account.id,
            iban=account.iban,
            bic=account.bic,
            status=account.status.value,
            name=account.name,
            created_at=account.created_at.isoformat() if account.created_at else None
        )

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    account_id: str = Query(..., description="ID du compte Swan"),
    client: SwanClient = Depends(get_swan_client)
):
    """
    Récupérer le solde du compte.

    Retourne:
    - balance_available: Solde disponible
    - balance_pending: Opérations en attente
    - balance_reserved: Montant réservé (autorisations carte)
    """
    try:
        account = await client.get_account(account_id)

        return BalanceResponse(
            iban=account.iban,
            balance_available=account.balance_available,
            balance_pending=account.balance_pending,
            balance_reserved=account.balance_reserved,
            currency=account.currency,
            status=account.status.value
        )

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


# =============================================================================
# Routes Transactions
# =============================================================================

@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    account_id: str = Query(..., description="ID du compte Swan"),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Curseur pagination"),
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    client: SwanClient = Depends(get_swan_client)
):
    """
    Lister les transactions du compte.

    Pagination par curseur. Utilisez `next_cursor` pour la page suivante.
    """
    try:
        tx_status = TransactionStatus(status) if status else None
        transactions, next_cursor = await client.get_transactions(
            account_id,
            first=limit,
            after=cursor,
            status=tx_status
        )

        result = [
            TransactionResponse(
                id=tx.id,
                type=tx.type.value,
                status=tx.status.value,
                amount=tx.amount,
                currency=tx.currency,
                direction=tx.direction,
                counterparty_name=tx.counterparty_name,
                reference=tx.reference,
                label=tx.label,
                booked_at=tx.booked_at.isoformat() if tx.booked_at else None,
                value_date=tx.value_date.isoformat() if tx.value_date else None
            )
            for tx in transactions
        ]

        return result

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


# =============================================================================
# Routes Virements
# =============================================================================

@router.post("/transfer", response_model=TransferResponse)
async def create_transfer(
    request: TransferRequest,
    account_id: str = Query(..., description="ID du compte débiteur"),
    client: SwanClient = Depends(get_swan_client)
):
    """
    Effectuer un virement SEPA.

    Virements instantanés (SEPA Instant) si la banque du bénéficiaire
    le supporte, sinon virement classique J+1.
    """
    try:
        result = await client.create_transfer(
            account_id=account_id,
            amount=request.amount,
            beneficiary_iban=request.beneficiary_iban,
            beneficiary_name=request.beneficiary_name,
            reference=request.reference,
            label=request.label or request.reference,
            scheduled_date=request.scheduled_date
        )

        return TransferResponse(
            transfer_id=result["transfer_id"],
            status=result["status"],
            amount=request.amount,
            beneficiary_iban=request.beneficiary_iban,
            reference=request.reference
        )

    except SwanError as e:
        logger.error(f"Erreur virement: {e}")
        if "InsufficientFunds" in str(e.details):
            raise HTTPException(status_code=400, detail="Solde insuffisant")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/transfer/supplier")
async def pay_supplier_invoice(
    facture_achat_id: UUID,
    scheduled_date: Optional[date] = None,
    settings: Settings = Depends(get_settings)
):
    """
    Payer une facture fournisseur par virement.

    Récupère automatiquement les informations de la facture
    et du fournisseur pour effectuer le virement.
    """
    if not settings.swan.is_configured:
        raise HTTPException(status_code=503, detail="Swan non configuré")

    # TODO: Injecter DB
    service = SwanBankingService(db=None, tenant_id=UUID("00000000-0000-0000-0000-000000000000"))

    try:
        result = await service.pay_supplier(facture_achat_id, scheduled_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Routes Cartes
# =============================================================================

@router.get("/cards", response_model=list[CardResponse])
async def list_cards(
    account_id: str = Query(..., description="ID du compte Swan"),
    client: SwanClient = Depends(get_swan_client)
):
    """
    Lister les cartes bancaires du compte.
    """
    try:
        cards = await client.get_cards(account_id)

        return [
            CardResponse(
                id=card.id,
                status=card.status.value,
                type=card.type,
                last_four_digits=card.last_four_digits,
                expiry_date=card.expiry_date,
                holder_name=card.holder_name
            )
            for card in cards
        ]

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/cards/virtual", response_model=CardResponse)
async def create_virtual_card(
    request: CreateVirtualCardRequest,
    membership_id: str = Query(..., description="ID du membership"),
    client: SwanClient = Depends(get_swan_client)
):
    """
    Créer une carte virtuelle.

    La carte est utilisable immédiatement pour les paiements en ligne.
    Plafond configurable par période.
    """
    try:
        card = await client.create_virtual_card(
            account_membership_id=membership_id,
            spending_limit_amount=request.spending_limit,
            spending_limit_period=request.spending_period
        )

        return CardResponse(
            id=card.id,
            status=card.status.value,
            type=card.type,
            last_four_digits=card.last_four_digits,
            expiry_date=card.expiry_date,
            holder_name=""
        )

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/cards/{card_id}/suspend")
async def suspend_card(
    card_id: str,
    client: SwanClient = Depends(get_swan_client)
):
    """
    Suspendre une carte (blocage temporaire).

    La carte peut être réactivée ultérieurement.
    """
    try:
        success = await client.suspend_card(card_id)

        return {
            "card_id": card_id,
            "suspended": success
        }

    except SwanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


# =============================================================================
# Routes Statistiques
# =============================================================================

@router.get("/stats")
async def get_banking_stats(
    account_id: str = Query(..., description="ID du compte Swan"),
    period: str = Query("month", description="day, week, month, year")
):
    """
    Statistiques du compte bancaire.

    Retourne:
    - Entrées/sorties
    - Solde moyen
    - Top dépenses par catégorie
    """
    # TODO: Implémenter avec la DB
    return {
        "period": period,
        "total_in": 0,
        "total_out": 0,
        "balance_average": 0,
        "transactions_count": 0
    }


@router.get("/pricing")
async def get_pricing(settings: Settings = Depends(get_settings)):
    """
    Tarification du compte bancaire intégré.
    """
    return {
        "monthly_fee": settings.swan.monthly_fee,
        "currency": "EUR",
        "features": {
            "iban_francais": True,
            "virements_sepa": "Illimités",
            "carte_physique": "Incluse",
            "carte_virtuelle": "Illimitées",
            "tap_to_pay": f"{settings.swan.tap_to_pay_pct}%",
            "api_access": True
        }
    }
