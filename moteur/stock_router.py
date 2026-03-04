# =============================================================================
# AZALPLUS - Stock Router
# =============================================================================
"""
Routes API pour la gestion des stocks.
A inclure dans le router principal.

Routes disponibles:
- GET  /stock/alertes        - Alertes de stock actives
- GET  /stock/dashboard      - KPIs et dashboard stock
- POST /stock/ajuster        - Ajuster le stock d'un produit
- POST /stock/mouvement      - Creer un mouvement de stock
- GET  /stock/produit/{id}/mouvements - Historique mouvements produit
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel
from decimal import Decimal
import structlog

from .db import Database
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth
from .stock import (
    StockService,
    TypeMouvement,
    SousTypeMouvement,
    LigneMouvement,
    hook_facture_validee,
    hook_intervention_terminee,
    hook_ajustement_stock,
    get_alertes_stock
)

logger = structlog.get_logger()

# =============================================================================
# Router
# =============================================================================
stock_router = APIRouter(prefix="/stock", tags=["Stock"])


# =============================================================================
# Schemas Pydantic
# =============================================================================
class AjustementStockRequest(BaseModel):
    """Schema pour ajustement de stock."""
    produit_id: str
    nouvelle_quantite: int
    motif: str


class MouvementStockRequest(BaseModel):
    """Schema pour creation de mouvement de stock."""
    type: str  # ENTREE, SORTIE, AJUSTEMENT, TRANSFERT, INVENTAIRE
    sous_type: str
    motif: str
    lignes: List[Dict[str, Any]]
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None


# =============================================================================
# Routes
# =============================================================================

@stock_router.get("/alertes")
async def get_stock_alertes(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Recupere toutes les alertes de stock actives.

    Retourne les produits en rupture, stock bas, ou seuil de reapprovisionnement atteint.
    """
    alertes = get_alertes_stock(tenant_id)

    return {
        "alertes": [
            {
                "produit_id": str(a.produit_id),
                "produit_nom": a.produit_nom,
                "type": a.type_alerte,
                "stock_actuel": a.stock_actuel,
                "stock_minimum": a.stock_minimum,
                "message": a.message
            }
            for a in alertes
        ],
        "total": len(alertes),
        "ruptures": len([a for a in alertes if a.type_alerte == "RUPTURE"]),
        "stock_bas": len([a for a in alertes if a.type_alerte == "STOCK_BAS"])
    }


@stock_router.get("/dashboard")
async def get_stock_dashboard(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Dashboard stock avec KPIs.

    Retourne:
    - Valeur totale du stock
    - Nombre de produits en stock
    - Nombre de ruptures
    - Nombre de stocks bas
    - Derniers mouvements
    """
    # Recuperer les produits avec gestion de stock
    produits = Database.query(
        "Produit",
        tenant_id,
        filters={"gestion_stock": True, "is_active": True}
    )

    # Calculer les KPIs
    valeur_totale = 0
    produits_en_stock = 0
    ruptures = 0
    stock_bas = 0

    for p in produits:
        stock = p.get("stock_actuel", 0) or 0
        cout = p.get("standard_cost", 0) or p.get("average_cost", 0) or 0
        valeur_totale += stock * cout

        if stock > 0:
            produits_en_stock += 1
        elif stock <= 0:
            ruptures += 1

        stock_min = p.get("stock_minimum", 5) or 5
        if 0 < stock <= stock_min:
            stock_bas += 1

    # Derniers mouvements
    mouvements = Database.query(
        "MouvementStock",
        tenant_id,
        limit=10,
        order_by="date DESC"
    )

    return {
        "kpis": {
            "valeur_totale": valeur_totale,
            "produits_geres": len(produits),
            "produits_en_stock": produits_en_stock,
            "ruptures": ruptures,
            "stock_bas": stock_bas
        },
        "derniers_mouvements": mouvements
    }


@stock_router.post("/ajuster")
async def ajuster_stock(
    data: AjustementStockRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Ajuste le stock d'un produit (inventaire/correction).

    Cree automatiquement un mouvement d'ajustement.
    """
    logger.info(
        "ajustement_stock_api",
        tenant_id=str(tenant_id),
        produit_id=data.produit_id,
        nouvelle_quantite=data.nouvelle_quantite
    )

    result = hook_ajustement_stock(
        tenant_id=tenant_id,
        produit_id=UUID(data.produit_id),
        nouvelle_quantite=data.nouvelle_quantite,
        motif=data.motif,
        user_id=user_id
    )

    return result


@stock_router.post("/mouvement")
async def creer_mouvement_stock(
    data: MouvementStockRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Cree un mouvement de stock manuel.

    Types: ENTREE, SORTIE, AJUSTEMENT, TRANSFERT, INVENTAIRE

    Sous-types disponibles:
    - Entrees: ACHAT, RETOUR_CLIENT, PRODUCTION, TRANSFERT_ENTRANT, AJUSTEMENT_POSITIF, INVENTAIRE_POSITIF
    - Sorties: VENTE, RETOUR_FOURNISSEUR, CONSOMMATION, PERTE, CASSE, TRANSFERT_SORTANT, AJUSTEMENT_NEGATIF, INVENTAIRE_NEGATIF, INTERVENTION
    """
    logger.info(
        "creation_mouvement_stock_api",
        tenant_id=str(tenant_id),
        type=data.type,
        sous_type=data.sous_type
    )

    service = StockService(tenant_id, user_id)

    # Convertir les lignes
    lignes = []
    for l in data.lignes:
        lignes.append(LigneMouvement(
            produit_id=UUID(l["produit_id"]),
            quantite=Decimal(str(l["quantite"])),
            cout_unitaire=Decimal(str(l.get("cout_unitaire", 0))) if l.get("cout_unitaire") else None,
            lot=l.get("lot"),
            numero_serie=l.get("numero_serie"),
            emplacement=l.get("emplacement"),
            notes=l.get("notes")
        ))

    result = service.creer_mouvement(
        type_mvt=TypeMouvement(data.type),
        sous_type=SousTypeMouvement(data.sous_type),
        lignes=lignes,
        motif=data.motif,
        reference_type=data.reference_type,
        reference_id=UUID(data.reference_id) if data.reference_id else None,
        notes=data.notes,
        valider_auto=True
    )

    return result


@stock_router.get("/produit/{produit_id}/mouvements")
async def get_mouvements_produit(
    produit_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Recupere l'historique des mouvements pour un produit.
    """
    # Recuperer les mouvements
    mouvements = Database.query(
        "MouvementStock",
        tenant_id,
        filters={"produit_id": str(produit_id)},
        limit=limit,
        order_by="date DESC"
    )

    return {
        "produit_id": str(produit_id),
        "mouvements": mouvements,
        "total": len(mouvements)
    }


@stock_router.get("/produit/{produit_id}")
async def get_stock_produit(
    produit_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Recupere les informations de stock d'un produit.
    """
    # Recuperer le produit
    produit = Database.get_by_id("Produit", tenant_id, produit_id)
    if not produit:
        raise HTTPException(status_code=404, detail="Produit non trouve")

    return {
        "produit_id": str(produit_id),
        "nom": produit.get("name") or produit.get("nom"),
        "gestion_stock": produit.get("gestion_stock", True),
        "stock_actuel": produit.get("stock_actuel", 0),
        "stock_reserve": produit.get("stock_reserve", 0),
        "stock_disponible": produit.get("stock_disponible", 0),
        "stock_minimum": produit.get("stock_minimum", 5),
        "stock_maximum": produit.get("stock_maximum"),
        "seuil_reapprovisionnement": produit.get("seuil_reapprovisionnement"),
        "statut_stock": produit.get("statut_stock", "NON_GERE"),
        "valeur_stock": (produit.get("stock_actuel", 0) or 0) * (produit.get("standard_cost", 0) or 0)
    }


# =============================================================================
# Hooks internes pour triggers automatiques (workflow)
# =============================================================================

async def trigger_stock_on_facture_validee(tenant_id: UUID, facture_id: UUID, user_id: Optional[UUID] = None):
    """
    Hook interne appele lors de la validation d'une facture.
    Declenche automatiquement la sortie de stock.
    """
    try:
        result = hook_facture_validee(tenant_id, facture_id, user_id)
        logger.info(
            "stock_mis_a_jour_facture",
            tenant_id=str(tenant_id),
            facture_id=str(facture_id),
            result=result
        )
        return result
    except Exception as e:
        logger.error(
            "erreur_stock_facture",
            tenant_id=str(tenant_id),
            facture_id=str(facture_id),
            error=str(e)
        )
        return {"error": str(e)}


async def trigger_stock_on_intervention_terminee(tenant_id: UUID, intervention_id: UUID, user_id: Optional[UUID] = None):
    """
    Hook interne appele lors de la terminaison d'une intervention.
    Declenche automatiquement la sortie de stock pour les pieces utilisees.
    """
    try:
        result = hook_intervention_terminee(tenant_id, intervention_id, user_id)
        logger.info(
            "stock_mis_a_jour_intervention",
            tenant_id=str(tenant_id),
            intervention_id=str(intervention_id),
            result=result
        )
        return result
    except Exception as e:
        logger.error(
            "erreur_stock_intervention",
            tenant_id=str(tenant_id),
            intervention_id=str(intervention_id),
            error=str(e)
        )
        return {"error": str(e)}
