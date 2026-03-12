# =============================================================================
# AZALPLUS - Payment Management API
# =============================================================================
"""
Routes API pour la gestion des paiements de factures.

Fonctionnalites:
- Enregistrement de paiements
- Validation / Rejet / Annulation
- Mise a jour automatique des factures
- Dashboard des factures en retard
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import date, datetime
import structlog

from .db import Database
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth
from .constants import get_statuts, get_statut_defaut

logger = structlog.get_logger()

# Statuts de paiement (chargés depuis constants.yml)
STATUT_EN_ATTENTE = "EN_ATTENTE"
STATUT_VALIDE = "VALIDE"
STATUT_ANNULE = "ANNULE"
STATUT_REJETE = "REJETE"

# Router pour les paiements
paiements_router = APIRouter(tags=["Paiements"])


# =============================================================================
# Schemas Pydantic
# =============================================================================

class PaymentCreate(BaseModel):
    """Schema pour la creation d'un paiement."""
    facture_id: str
    montant: float
    date_paiement: Optional[str] = None
    mode: str
    reference_transaction: Optional[str] = None
    banque: Optional[str] = None
    numero_cheque: Optional[str] = None
    compte_bancaire: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    """Schema de reponse pour un paiement."""
    success: bool
    message: str
    paiement_id: Optional[str] = None
    facture_id: Optional[str] = None


# =============================================================================
# Routes de paiements
# =============================================================================

@paiements_router.post("/Factures/{facture_id}/paiements", status_code=201)
async def enregistrer_paiement(
    facture_id: UUID,
    paiement: PaymentCreate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Enregistre un paiement pour une facture.

    - Met a jour automatiquement le statut de paiement de la facture
    - Calcule le reste a payer
    - Cree une entree dans le module Paiements

    Le paiement est cree avec le statut EN_ATTENTE par defaut.
    """
    # Verifier que la facture existe
    facture = Database.get_by_id("factures", tenant_id, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")

    # Verifier que le montant est valide
    if paiement.montant <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit etre superieur a 0")

    total_ttc = float(facture.get("total", 0) or 0)
    paid_amount = float(facture.get("paid_amount", 0) or 0)
    remaining = total_ttc - paid_amount

    if paiement.montant > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Le montant ({paiement.montant}) depasse le reste a payer ({remaining})"
        )

    # Creer le paiement
    paiement_data = {
        "facture_id": str(facture_id),
        "client_id": facture.get("customer_id"),
        "montant": paiement.montant,
        "date_paiement": paiement.date_paiement or str(date.today()),
        "mode": paiement.mode,
        "reference_transaction": paiement.reference_transaction,
        "banque": paiement.banque,
        "numero_cheque": paiement.numero_cheque,
        "compte_bancaire": paiement.compte_bancaire,
        "notes": paiement.notes,
        "statut": STATUT_EN_ATTENTE
    }

    new_paiement = Database.insert("paiements", tenant_id, paiement_data, user_id)

    logger.info(
        "paiement_created",
        tenant_id=str(tenant_id),
        facture_id=str(facture_id),
        paiement_id=new_paiement.get("id"),
        montant=paiement.montant,
        mode=paiement.mode
    )

    return {
        "paiement": new_paiement,
        "message": "Paiement enregistre. En attente de validation."
    }


@paiements_router.post("/Paiements/{paiement_id}/valider")
async def valider_paiement(
    paiement_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Valide un paiement et met a jour la facture associee.

    - Change le statut du paiement a VALIDE
    - Met a jour paid_amount de la facture
    - Met a jour payment_status et status de la facture
    """
    # Recuperer le paiement
    paiement = Database.get_by_id("paiements", tenant_id, paiement_id)
    if not paiement:
        raise HTTPException(status_code=404, detail="Paiement non trouve")

    if paiement.get("statut") != STATUT_EN_ATTENTE:
        raise HTTPException(status_code=400, detail="Ce paiement ne peut pas etre valide")

    facture_id = paiement.get("facture_id")
    if not facture_id:
        raise HTTPException(status_code=400, detail="Paiement non lie a une facture")

    # Recuperer la facture
    facture = Database.get_by_id("factures", tenant_id, UUID(facture_id))
    if not facture:
        raise HTTPException(status_code=404, detail="Facture associee non trouvee")

    # Mettre a jour le paiement
    Database.update("paiements", tenant_id, paiement_id, {
        "statut": STATUT_VALIDE,
        "date_validation": datetime.now().isoformat(),
        "valide_par": str(user_id)
    }, user_id)

    # Calculer les nouveaux montants
    montant_paiement = float(paiement.get("montant", 0))
    total_ttc = float(facture.get("total", 0) or 0)
    paid_amount = float(facture.get("paid_amount", 0) or 0)
    payment_count = int(facture.get("payment_count", 0) or 0)

    new_paid_amount = paid_amount + montant_paiement
    new_remaining = total_ttc - new_paid_amount

    # Determiner les nouveaux statuts
    if new_remaining <= 0:
        payment_status = "PAID"
        status = "PAID"
    elif new_paid_amount > 0:
        payment_status = "PARTIAL"
        status = "PARTIALLY_PAID"
    else:
        payment_status = "UNPAID"
        status = facture.get("status", "SENT")

    # Mettre a jour la facture
    facture_update = {
        "paid_amount": new_paid_amount,
        "remaining_amount": max(0, new_remaining),
        "payment_status": payment_status,
        "status": status,
        "last_payment_date": paiement.get("date_paiement"),
        "payment_count": payment_count + 1
    }

    Database.update("factures", tenant_id, UUID(facture_id), facture_update, user_id)

    logger.info(
        "paiement_validated",
        tenant_id=str(tenant_id),
        paiement_id=str(paiement_id),
        facture_id=facture_id,
        new_paid_amount=new_paid_amount,
        new_status=status
    )

    return {
        "success": True,
        "paiement_id": str(paiement_id),
        "facture_id": facture_id,
        "paid_amount": new_paid_amount,
        "remaining_amount": max(0, new_remaining),
        "payment_status": payment_status,
        "facture_status": status
    }


@paiements_router.post("/Paiements/{paiement_id}/rejeter")
async def rejeter_paiement(
    paiement_id: UUID,
    motif: str = Query(..., min_length=5, description="Motif du rejet"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Rejette un paiement.

    - Change le statut du paiement a REJETE
    - Enregistre le motif de rejet
    """
    paiement = Database.get_by_id("paiements", tenant_id, paiement_id)
    if not paiement:
        raise HTTPException(status_code=404, detail="Paiement non trouve")

    if paiement.get("statut") != STATUT_EN_ATTENTE:
        raise HTTPException(status_code=400, detail="Ce paiement ne peut pas etre rejete")

    Database.update("paiements", tenant_id, paiement_id, {
        "statut": "REJETE",
        "motif_rejet": motif,
        "date_rejet": datetime.now().isoformat()
    }, user_id)

    logger.info(
        "paiement_rejected",
        tenant_id=str(tenant_id),
        paiement_id=str(paiement_id),
        motif=motif
    )

    return {"success": True, "message": "Paiement rejete"}


@paiements_router.post("/Paiements/{paiement_id}/annuler")
async def annuler_paiement(
    paiement_id: UUID,
    motif: str = Query(..., min_length=5, description="Motif de l'annulation"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Annule un paiement valide.

    - Change le statut du paiement a ANNULE
    - Recalcule les montants de la facture
    """
    paiement = Database.get_by_id("paiements", tenant_id, paiement_id)
    if not paiement:
        raise HTTPException(status_code=404, detail="Paiement non trouve")

    statut_actuel = paiement.get("statut")
    if statut_actuel not in [STATUT_EN_ATTENTE, STATUT_VALIDE]:
        raise HTTPException(status_code=400, detail="Ce paiement ne peut pas etre annule")

    # Si le paiement etait valide, recalculer les montants de la facture
    if statut_actuel == STATUT_VALIDE:
        facture_id = paiement.get("facture_id")
        if facture_id:
            facture = Database.get_by_id("factures", tenant_id, UUID(facture_id))
            if facture:
                montant_paiement = float(paiement.get("montant", 0))
                total_ttc = float(facture.get("total", 0) or 0)
                paid_amount = float(facture.get("paid_amount", 0) or 0)
                payment_count = int(facture.get("payment_count", 0) or 0)

                new_paid_amount = max(0, paid_amount - montant_paiement)
                new_remaining = total_ttc - new_paid_amount

                # Determiner les nouveaux statuts
                if new_paid_amount <= 0:
                    payment_status = "UNPAID"
                    status = "SENT" if facture.get("status") not in ["DRAFT", "PENDING", "VALIDATED"] else facture.get("status")
                elif new_paid_amount < total_ttc:
                    payment_status = "PARTIAL"
                    status = "PARTIALLY_PAID"
                else:
                    payment_status = "PAID"
                    status = "PAID"

                Database.update("factures", tenant_id, UUID(facture_id), {
                    "paid_amount": new_paid_amount,
                    "remaining_amount": new_remaining,
                    "payment_status": payment_status,
                    "status": status,
                    "payment_count": max(0, payment_count - 1)
                }, user_id)

    Database.update("paiements", tenant_id, paiement_id, {
        "statut": STATUT_ANNULE,
        "motif_rejet": motif,
        "date_rejet": datetime.now().isoformat()
    }, user_id)

    logger.info(
        "paiement_cancelled",
        tenant_id=str(tenant_id),
        paiement_id=str(paiement_id),
        was_validated=(statut_actuel == STATUT_VALIDE)
    )

    return {"success": True, "message": "Paiement annule"}


@paiements_router.get("/Factures/{facture_id}/paiements")
async def get_paiements_facture(
    facture_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Recupere tous les paiements d'une facture.

    Retourne egalement un resume des montants.
    """
    # Verifier que la facture existe
    facture = Database.get_by_id("factures", tenant_id, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")

    # Recuperer les paiements
    paiements = Database.query(
        "paiements",
        tenant_id,
        filters={"facture_id": str(facture_id)},
        order_by="date_paiement DESC"
    )

    # Calculer les totaux
    total_valide = sum(
        float(p.get("montant", 0))
        for p in paiements
        if p.get("statut") == STATUT_VALIDE
    )
    total_en_attente = sum(
        float(p.get("montant", 0))
        for p in paiements
        if p.get("statut") == STATUT_EN_ATTENTE
    )

    total_ttc = float(facture.get("total", 0) or 0)

    return {
        "facture_id": str(facture_id),
        "facture_numero": facture.get("number"),
        "total_ttc": total_ttc,
        "paid_amount": total_valide,
        "remaining_amount": max(0, total_ttc - total_valide),
        "pending_amount": total_en_attente,
        "paiements": paiements,
        "count": len(paiements)
    }


@paiements_router.post("/Factures/{facture_id}/marquer-payee")
async def marquer_facture_payee(
    facture_id: UUID,
    mode: str = Query("CASH", description="Mode de paiement"),
    reference: Optional[str] = Query(None, description="Reference du paiement"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Action rapide pour marquer une facture comme entierement payee.

    Cree automatiquement un paiement valide pour le montant restant.
    """
    facture = Database.get_by_id("factures", tenant_id, facture_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")

    total_ttc = float(facture.get("total", 0) or 0)
    paid_amount = float(facture.get("paid_amount", 0) or 0)
    remaining = total_ttc - paid_amount

    if remaining <= 0:
        raise HTTPException(status_code=400, detail="Facture deja entierement payee")

    # Creer un paiement valide pour le reste
    paiement_data = {
        "facture_id": str(facture_id),
        "client_id": facture.get("customer_id"),
        "montant": remaining,
        "date_paiement": str(date.today()),
        "mode": mode,
        "reference_transaction": reference,
        "statut": STATUT_VALIDE,
        "date_validation": datetime.now().isoformat(),
        "valide_par": str(user_id),
        "notes": "Paiement cree via action rapide 'Marquer comme payee'"
    }

    new_paiement = Database.insert("paiements", tenant_id, paiement_data, user_id)

    # Mettre a jour la facture
    payment_count = int(facture.get("payment_count", 0) or 0)
    Database.update("factures", tenant_id, facture_id, {
        "paid_amount": total_ttc,
        "remaining_amount": 0,
        "payment_status": "PAID",
        "status": "PAID",
        "last_payment_date": str(date.today()),
        "payment_count": payment_count + 1
    }, user_id)

    logger.info(
        "facture_marked_paid",
        tenant_id=str(tenant_id),
        facture_id=str(facture_id),
        amount=remaining
    )

    return {
        "success": True,
        "facture_id": str(facture_id),
        "paiement_id": new_paiement.get("id"),
        "amount_paid": remaining,
        "message": "Facture marquee comme payee"
    }


# =============================================================================
# Routes Dashboard
# =============================================================================

@paiements_router.get("/dashboard/factures-en-retard", tags=["Dashboard"])
async def get_factures_en_retard(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Recupere les factures en retard de paiement pour le dashboard.

    Retourne les factures dont la date d'echeance est depassee
    et qui ne sont pas entierement payees.
    """
    today = str(date.today())

    # Requete pour les factures en retard
    factures = Database.query(
        "factures",
        tenant_id,
        limit=100,  # Charger plus pour filtrer
        order_by="due_date ASC"
    )

    # Filtrer les factures en retard (payment_status != PAID et due_date < today)
    factures_en_retard = []
    for f in factures:
        due_date = f.get("due_date")
        payment_status = f.get("payment_status", "UNPAID")
        status = f.get("status", "")

        if (due_date and str(due_date) < today and
            payment_status != "PAID" and
            status not in ["DRAFT", "CANCELLED", "PAID"]):

            # Calculer le nombre de jours de retard
            try:
                due_dt = datetime.strptime(str(due_date), "%Y-%m-%d").date()
                today_dt = datetime.strptime(today, "%Y-%m-%d").date()
                days_overdue = (today_dt - due_dt).days
            except:
                days_overdue = 0

            f["days_overdue"] = days_overdue
            factures_en_retard.append(f)

    # Trier par jours de retard decroissant
    factures_en_retard.sort(key=lambda x: x.get("days_overdue", 0), reverse=True)

    # Calculer le total en retard
    total_en_retard = sum(
        float(f.get("remaining_amount", 0) or f.get("total", 0) or 0)
        for f in factures_en_retard
    )

    return {
        "count": len(factures_en_retard),
        "total_en_retard": total_en_retard,
        "factures": factures_en_retard[:limit]
    }


@paiements_router.get("/dashboard/paiements-en-attente", tags=["Dashboard"])
async def get_paiements_en_attente(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Recupere les paiements en attente de validation.
    """
    paiements = Database.query(
        "paiements",
        tenant_id,
        filters={"statut": STATUT_EN_ATTENTE},
        order_by="date_paiement ASC",
        limit=limit
    )

    total_en_attente = sum(float(p.get("montant", 0)) for p in paiements)

    return {
        "count": len(paiements),
        "total_en_attente": total_en_attente,
        "paiements": paiements
    }


@paiements_router.get("/dashboard/resume-paiements", tags=["Dashboard"])
async def get_resume_paiements(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Retourne un resume global des paiements et factures.
    """
    today = str(date.today())

    # Recuperer toutes les factures actives
    factures = Database.query("factures", tenant_id, limit=1000)

    # Calculer les statistiques
    total_factures = 0
    total_paye = 0
    total_en_attente = 0
    factures_en_retard = 0
    montant_en_retard = 0

    for f in factures:
        status = f.get("status", "")
        if status in ["DRAFT", "CANCELLED"]:
            continue

        total = float(f.get("total", 0) or 0)
        paid = float(f.get("paid_amount", 0) or 0)
        due_date = f.get("due_date")
        payment_status = f.get("payment_status", "UNPAID")

        total_factures += total
        total_paye += paid

        if payment_status != "PAID":
            total_en_attente += (total - paid)

            if due_date and str(due_date) < today:
                factures_en_retard += 1
                montant_en_retard += (total - paid)

    # Paiements en attente de validation
    paiements_pending = Database.query(
        "paiements",
        tenant_id,
        filters={"statut": STATUT_EN_ATTENTE}
    )
    total_paiements_pending = sum(float(p.get("montant", 0)) for p in paiements_pending)

    return {
        "total_factures": total_factures,
        "total_paye": total_paye,
        "total_en_attente": total_en_attente,
        "taux_recouvrement": round((total_paye / total_factures * 100) if total_factures > 0 else 0, 1),
        "factures_en_retard": factures_en_retard,
        "montant_en_retard": montant_en_retard,
        "paiements_a_valider": len(paiements_pending),
        "montant_paiements_a_valider": total_paiements_pending
    }
