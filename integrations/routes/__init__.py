# =============================================================================
# AZALPLUS - Routes API des Intégrations
# =============================================================================
"""
Routes FastAPI pour les intégrations externes.

Usage:
    from integrations.routes import setup_integration_routes
    setup_integration_routes(app)

Routes disponibles:
    /api/paiements/*      - Paiements Open Banking (Fintecture)
    /api/banking/*        - Compte bancaire intégré (Swan)
    /api/notifications/*  - SMS/WhatsApp (Twilio)
    /api/expeditions/*    - Multi-transporteurs (Colissimo, Chronopost, etc.)
    /api/webhooks/*       - Callbacks des services externes
"""

import logging
from fastapi import FastAPI

from .paiements import router as paiements_router
from .banking import router as banking_router
from .notifications import router as notifications_router
from .expeditions import router as expeditions_router
from .webhooks import router as webhooks_router

logger = logging.getLogger(__name__)

# Export des routers individuels
__all__ = [
    "paiements_router",
    "banking_router",
    "notifications_router",
    "expeditions_router",
    "webhooks_router",
    "setup_integration_routes"
]


def setup_integration_routes(app: FastAPI) -> int:
    """
    Configurer toutes les routes d'intégration.

    Args:
        app: Application FastAPI

    Returns:
        Nombre de routers configurés
    """
    routers = [
        (paiements_router, "Paiements Open Banking"),
        (banking_router, "Banking (Swan)"),
        (notifications_router, "Notifications (Twilio)"),
        (expeditions_router, "Expéditions Multi-transporteurs"),
        (webhooks_router, "Webhooks"),
    ]

    for router, name in routers:
        app.include_router(router)
        logger.debug(f"integration_router_registered", router=name)

    logger.info("integration_routes_configured", count=len(routers))

    return len(routers)
