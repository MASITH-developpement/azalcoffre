# =============================================================================
# AZALPLUS - Push Notification API Routes
# =============================================================================
"""
Routes API pour la gestion des notifications push.

Endpoints:
- POST /push/register - Enregistrer un token push
- DELETE /push/unregister - Supprimer un token push
- POST /push/test - Envoyer une notification de test
- GET /push/tokens - Lister les tokens enregistres (admin)
- POST /push/broadcast - Envoyer a tous les utilisateurs (admin)
- POST /push/cleanup - Nettoyer les tokens expires (admin)

Multi-tenant obligatoire: isolation par tenant_id.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from uuid import UUID
import structlog

from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth, require_role
from .push_service import PushService, PushPlatform

logger = structlog.get_logger()

# Router pour les notifications push
push_router = APIRouter(prefix="/push", tags=["push-notifications"])


# =============================================================================
# Schemas Pydantic
# =============================================================================

class PushTokenRegisterRequest(BaseModel):
    """Schema pour l'enregistrement d'un token push."""
    token: str = Field(..., min_length=10, max_length=500, description="Token FCM")
    platform: str = Field(default="web", description="Plateforme (web, android, ios)")
    device_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Informations sur le device"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "token": "cTZ8H9_pRaC...",
                "platform": "web",
                "device_info": {
                    "user_agent": "Mozilla/5.0...",
                    "language": "fr-FR"
                }
            }
        }


class PushTokenUnregisterRequest(BaseModel):
    """Schema pour la suppression d'un token push."""
    token: str = Field(..., min_length=10, max_length=500, description="Token FCM")


class PushTestRequest(BaseModel):
    """Schema pour l'envoi d'une notification de test."""
    title: Optional[str] = Field(default="Test AZALPLUS", description="Titre")
    body: Optional[str] = Field(
        default="Cette notification confirme que les push sont actives.",
        description="Message"
    )


class PushBroadcastRequest(BaseModel):
    """Schema pour l'envoi de notifications a tous les utilisateurs."""
    title: str = Field(..., min_length=1, max_length=100, description="Titre")
    body: str = Field(..., min_length=1, max_length=500, description="Message")
    data: Optional[Dict[str, str]] = Field(default=None, description="Donnees supplementaires")
    image_url: Optional[str] = Field(default=None, description="URL image")
    link: Optional[str] = Field(default=None, description="Lien a ouvrir")


class PushSendRequest(BaseModel):
    """Schema pour l'envoi d'une notification a des utilisateurs specifiques."""
    user_ids: List[str] = Field(..., min_length=1, description="IDs des utilisateurs")
    title: str = Field(..., min_length=1, max_length=100, description="Titre")
    body: str = Field(..., min_length=1, max_length=500, description="Message")
    data: Optional[Dict[str, str]] = Field(default=None, description="Donnees supplementaires")
    image_url: Optional[str] = Field(default=None, description="URL image")
    link: Optional[str] = Field(default=None, description="Lien a ouvrir")


# =============================================================================
# Endpoints publics (utilisateur authentifie)
# =============================================================================

@push_router.post("/register")
async def register_push_token(
    data: PushTokenRegisterRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Enregistre un token push pour l'utilisateur courant.

    Appele par le client apres obtention du token FCM.
    Le token est associe a l'utilisateur et au device.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="Utilisateur non identifie")

    # Valider la plateforme
    valid_platforms = [p.value for p in PushPlatform]
    platform = data.platform if data.platform in valid_platforms else "web"

    result = PushService.register_token(
        tenant_id=tenant_id,
        user_id=user_id,
        token=data.token,
        platform=platform,
        device_info=data.device_info
    )

    return {
        "status": "success",
        "message": "Token enregistre",
        "token_id": result.get("id")
    }


@push_router.delete("/unregister")
async def unregister_push_token(
    data: PushTokenUnregisterRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Supprime un token push de l'utilisateur courant.

    Appele lors de la deconnexion ou desactivation des notifications.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="Utilisateur non identifie")

    success = PushService.unregister_token(
        tenant_id=tenant_id,
        user_id=user_id,
        token=data.token
    )

    if not success:
        raise HTTPException(status_code=404, detail="Token non trouve")

    return {
        "status": "success",
        "message": "Token supprime"
    }


@push_router.post("/test")
async def send_test_notification(
    data: PushTestRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Envoie une notification de test a l'utilisateur courant.

    Permet de verifier que les notifications push fonctionnent.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="Utilisateur non identifie")

    result = PushService.send_notification(
        tenant_id=tenant_id,
        user_ids=[user_id],
        title=data.title or "Test AZALPLUS",
        body=data.body or "Les notifications push sont actives.",
        data={"type": "test"}
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Impossible d'envoyer la notification")
        )

    return {
        "status": "success",
        "message": result.get("message"),
        "sent": result.get("sent", 0)
    }


@push_router.get("/status")
async def get_push_status(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Retourne le statut des notifications push pour l'utilisateur.

    Indique si l'utilisateur a des tokens enregistres.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="Utilisateur non identifie")

    tokens = PushService.get_user_tokens(tenant_id, user_id)

    return {
        "enabled": len(tokens) > 0,
        "device_count": len(tokens),
        "platforms": list(set(t.get("platform", "web") for t in tokens))
    }


# =============================================================================
# Endpoints admin (role admin requis)
# =============================================================================

@push_router.get("/tokens")
async def list_push_tokens(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_role("admin")),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Liste tous les tokens push du tenant (admin uniquement).

    Permet de visualiser les devices enregistres.
    """
    result = PushService.list_all_tokens(
        tenant_id=tenant_id,
        limit=limit,
        offset=skip
    )

    return {
        "items": result.get("items", []),
        "total": result.get("total", 0),
        "skip": skip,
        "limit": limit
    }


@push_router.post("/send")
async def send_push_to_users(
    data: PushSendRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_role("admin"))
):
    """
    Envoie une notification push a des utilisateurs specifiques (admin uniquement).
    """
    try:
        user_ids = [UUID(uid) for uid in data.user_ids]
    except ValueError:
        raise HTTPException(status_code=400, detail="Format d'ID utilisateur invalide")

    result = PushService.send_notification(
        tenant_id=tenant_id,
        user_ids=user_ids,
        title=data.title,
        body=data.body,
        data=data.data,
        image_url=data.image_url,
        link=data.link
    )

    return {
        "status": "success" if result.get("success") else "partial",
        "sent": result.get("sent", 0),
        "failed": result.get("failed", 0),
        "message": result.get("message")
    }


@push_router.post("/broadcast")
async def broadcast_push_notification(
    data: PushBroadcastRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_role("admin"))
):
    """
    Envoie une notification push a tous les utilisateurs du tenant (admin uniquement).

    Attention: Cette operation peut etre couteuse en ressources.
    """
    result = PushService.send_to_all_tenant(
        tenant_id=tenant_id,
        title=data.title,
        body=data.body,
        data=data.data,
        image_url=data.image_url,
        link=data.link
    )

    logger.info("push_broadcast_sent",
        tenant_id=str(tenant_id),
        admin_user=user.get("email"),
        sent=result.get("sent", 0)
    )

    return {
        "status": "success" if result.get("success") else "partial",
        "sent": result.get("sent", 0),
        "failed": result.get("failed", 0),
        "message": result.get("message")
    }


@push_router.post("/cleanup")
async def cleanup_expired_tokens(
    days: int = Query(90, ge=7, le=365, description="Jours d'inactivite"),
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_role("admin"))
):
    """
    Nettoie les tokens push expires (admin uniquement).

    Supprime les tokens inactifs depuis plus de X jours.
    """
    deleted = PushService.cleanup_expired_tokens(
        tenant_id=tenant_id,
        days=days
    )

    logger.info("push_tokens_cleanup_triggered",
        tenant_id=str(tenant_id),
        admin_user=user.get("email"),
        deleted=deleted
    )

    return {
        "status": "success",
        "deleted": deleted,
        "message": f"{deleted} token(s) supprime(s)"
    }


# =============================================================================
# Health check endpoint
# =============================================================================

@push_router.get("/health")
async def push_health_check():
    """
    Verifie le statut du service de notifications push.
    """
    fcm_status = "configured" if PushService._fcm_app else "not_configured"

    return {
        "status": "ok",
        "fcm": fcm_status,
        "message": "Service push operationnel"
    }
