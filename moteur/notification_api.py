# =============================================================================
# AZALPLUS - Notification API Routes
# =============================================================================
"""
Routes API pour le centre de notifications in-app.

Endpoints:
- GET /notifications/count - Nombre de notifications non lues
- GET /notifications/recent - Notifications recentes (dropdown)
- GET /notifications - Liste complete avec filtres
- POST /notifications/{id}/read - Marquer comme lue
- POST /notifications/{id}/unread - Marquer comme non lue
- POST /notifications/read-all - Tout marquer comme lu
- DELETE /notifications/{id} - Supprimer une notification
- DELETE /notifications/read - Supprimer les lues
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from uuid import UUID

from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth
from .notifier import NotificationService

# Router pour les notifications
notification_router = APIRouter(prefix="/notifications", tags=["notifications"])


@notification_router.get("/count")
async def get_notification_count(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Retourne le nombre de notifications non lues pour l'utilisateur courant.
    Utilise pour le badge dans le header.
    """
    count = NotificationService.get_unread_count(tenant_id, user_id)
    return {"count": count}


@notification_router.get("/recent")
async def get_recent_notifications(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Retourne les notifications recentes pour le dropdown du header.
    """
    notifications = NotificationService.get_recent(tenant_id, user_id, limit=limit)
    return {"items": notifications}


@notification_router.get("")
async def list_notifications(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth),
    type_filter: Optional[str] = Query(None, description="Filtrer par type: info, warning, success, error"),
    read_filter: Optional[bool] = Query(None, description="Filtrer par etat de lecture"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Liste toutes les notifications avec filtres et pagination.
    """
    result = NotificationService.get_all(
        tenant_id=tenant_id,
        user_id=user_id,
        type_filter=type_filter,
        read_filter=read_filter,
        limit=limit,
        offset=skip
    )
    return result


@notification_router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Marque une notification comme lue.
    """
    result = NotificationService.mark_as_read(tenant_id, notification_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Notification non trouvee")
    return {"status": "success", "message": "Notification marquee comme lue"}


@notification_router.post("/{notification_id}/unread")
async def mark_notification_unread(
    notification_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Marque une notification comme non lue.
    """
    result = NotificationService.mark_as_unread(tenant_id, notification_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Notification non trouvee")
    return {"status": "success", "message": "Notification marquee comme non lue"}


@notification_router.post("/read-all")
async def mark_all_notifications_read(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Marque toutes les notifications comme lues.
    """
    count = NotificationService.mark_all_as_read(tenant_id, user_id)
    return {"status": "success", "message": f"{count} notification(s) marquee(s) comme lue(s)"}


@notification_router.delete("/{notification_id}")
async def delete_notification(
    notification_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Supprime une notification.
    """
    success = NotificationService.delete(tenant_id, notification_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification non trouvee")
    return {"status": "success", "message": "Notification supprimee"}


@notification_router.delete("/read")
async def delete_all_read_notifications(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Supprime toutes les notifications lues.
    """
    count = NotificationService.delete_all_read(tenant_id, user_id)
    return {"status": "success", "message": f"{count} notification(s) supprimee(s)"}
