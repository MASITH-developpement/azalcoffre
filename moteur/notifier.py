# =============================================================================
# AZALPLUS - Notification Service
# =============================================================================
"""
Service de notifications in-app.
Permet d'envoyer, lire et gerer les notifications utilisateurs.

Fonctionnalites:
- Envoi de notifications avec type, priorite et lien
- Compteur de non-lues pour badge UI
- Marquage lu/non-lu
- Filtrage par type
- Integration avec les workflows
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from enum import Enum
import structlog

from .db import Database

logger = structlog.get_logger()


class NotificationType(str, Enum):
    """Types de notifications."""
    INFO = "info"
    WARNING = "warning"
    SUCCESS = "success"
    ERROR = "error"


class NotificationPriority(str, Enum):
    """Niveaux de priorite."""
    BASSE = "basse"
    NORMALE = "normale"
    HAUTE = "haute"
    URGENTE = "urgente"


class NotificationService:
    """
    Service de gestion des notifications.

    Toutes les operations respectent l'isolation multi-tenant.
    """

    TABLE_NAME = "notifications"

    @classmethod
    def send(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        type: str,
        title: str,
        message: str,
        link: Optional[str] = None,
        module_source: Optional[str] = None,
        record_id: Optional[UUID] = None,
        priority: str = "normale",
        action_type: Optional[str] = None,
        action_data: Optional[Dict] = None,
        expire_at: Optional[datetime] = None
    ) -> Dict:
        """
        Envoie une notification a un utilisateur.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            user_id: ID de l'utilisateur destinataire
            type: Type de notification (info, warning, success, error)
            title: Titre de la notification
            message: Corps du message
            link: Lien optionnel vers une ressource
            module_source: Module ayant genere la notification
            record_id: ID de l'enregistrement source
            priority: Priorite (basse, normale, haute, urgente)
            action_type: Type d'action associee
            action_data: Donnees de l'action
            expire_at: Date d'expiration

        Returns:
            La notification creee
        """
        notification_data = {
            "user_id": str(user_id),
            "type": type,
            "titre": title,
            "message": message,
            "lien": link,
            "module_source": module_source,
            "record_id": str(record_id) if record_id else None,
            "lu": False,
            "priorite": priority,
            "action_type": action_type,
            "action_data": action_data or {},
            "expire_at": expire_at.isoformat() if expire_at else None
        }

        result = Database.insert(
            cls.TABLE_NAME,
            tenant_id,
            notification_data
        )

        logger.info(
            "notification_sent",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            type=type,
            title=title
        )

        return result

    @classmethod
    def send_to_multiple(
        cls,
        tenant_id: UUID,
        user_ids: List[UUID],
        type: str,
        title: str,
        message: str,
        **kwargs
    ) -> List[Dict]:
        """
        Envoie une notification a plusieurs utilisateurs.

        Args:
            tenant_id: ID du tenant
            user_ids: Liste des IDs utilisateurs
            type: Type de notification
            title: Titre
            message: Message
            **kwargs: Arguments supplementaires passes a send()

        Returns:
            Liste des notifications creees
        """
        results = []
        for user_id in user_ids:
            result = cls.send(
                tenant_id=tenant_id,
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                **kwargs
            )
            results.append(result)
        return results

    @classmethod
    def mark_as_read(
        cls,
        tenant_id: UUID,
        notification_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Optional[Dict]:
        """
        Marque une notification comme lue.

        Args:
            tenant_id: ID du tenant
            notification_id: ID de la notification
            user_id: ID utilisateur (verification de propriete)

        Returns:
            La notification mise a jour ou None
        """
        # Verifier que la notification appartient a l'utilisateur
        notification = Database.get_by_id(cls.TABLE_NAME, tenant_id, notification_id)
        if not notification:
            return None

        if user_id and str(notification.get("user_id")) != str(user_id):
            logger.warning(
                "notification_access_denied",
                notification_id=str(notification_id),
                user_id=str(user_id)
            )
            return None

        result = Database.update(
            cls.TABLE_NAME,
            tenant_id,
            notification_id,
            {
                "lu": True,
                "date_lecture": datetime.utcnow().isoformat()
            }
        )

        return result

    @classmethod
    def mark_as_unread(
        cls,
        tenant_id: UUID,
        notification_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Optional[Dict]:
        """
        Marque une notification comme non lue.
        """
        notification = Database.get_by_id(cls.TABLE_NAME, tenant_id, notification_id)
        if not notification:
            return None

        if user_id and str(notification.get("user_id")) != str(user_id):
            return None

        result = Database.update(
            cls.TABLE_NAME,
            tenant_id,
            notification_id,
            {
                "lu": False,
                "date_lecture": None
            }
        )

        return result

    @classmethod
    def mark_all_as_read(
        cls,
        tenant_id: UUID,
        user_id: UUID
    ) -> int:
        """
        Marque toutes les notifications d'un utilisateur comme lues.

        Returns:
            Nombre de notifications mises a jour
        """
        # Recuperer toutes les notifications non lues
        notifications = cls.get_unread(tenant_id, user_id, limit=1000)

        count = 0
        for notif in notifications:
            result = cls.mark_as_read(tenant_id, UUID(notif["id"]), user_id)
            if result:
                count += 1

        logger.info(
            "notifications_marked_read",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            count=count
        )

        return count

    @classmethod
    def get_unread_count(
        cls,
        tenant_id: UUID,
        user_id: UUID
    ) -> int:
        """
        Retourne le nombre de notifications non lues.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur

        Returns:
            Nombre de notifications non lues
        """
        notifications = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"user_id": str(user_id), "lu": False},
            limit=1000
        )

        # Filtrer les notifications expirees
        now = datetime.utcnow()
        valid_notifications = [
            n for n in notifications
            if not n.get("expire_at") or datetime.fromisoformat(n["expire_at"]) > now
        ]

        return len(valid_notifications)

    @classmethod
    def get_unread(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 20
    ) -> List[Dict]:
        """
        Recupere les notifications non lues d'un utilisateur.
        """
        notifications = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"user_id": str(user_id), "lu": False},
            order_by="created_at DESC",
            limit=limit
        )

        # Filtrer les notifications expirees
        now = datetime.utcnow()
        return [
            n for n in notifications
            if not n.get("expire_at") or datetime.fromisoformat(n["expire_at"]) > now
        ]

    @classmethod
    def get_recent(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 10
    ) -> List[Dict]:
        """
        Recupere les notifications recentes (lues et non lues).
        """
        notifications = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"user_id": str(user_id)},
            order_by="created_at DESC",
            limit=limit
        )

        return notifications

    @classmethod
    def get_all(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        type_filter: Optional[str] = None,
        read_filter: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        Recupere toutes les notifications avec filtres et pagination.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            type_filter: Filtrer par type (info, warning, success, error)
            read_filter: Filtrer par etat de lecture (True/False/None)
            limit: Nombre max de resultats
            offset: Decalage pour pagination

        Returns:
            Dict avec items et total
        """
        filters = {"user_id": str(user_id)}

        if type_filter:
            filters["type"] = type_filter

        if read_filter is not None:
            filters["lu"] = read_filter

        notifications = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters=filters,
            order_by="created_at DESC",
            limit=limit,
            offset=offset
        )

        # Compter le total (sans pagination)
        all_notifications = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters=filters,
            limit=10000
        )

        return {
            "items": notifications,
            "total": len(all_notifications),
            "unread_count": sum(1 for n in all_notifications if not n.get("lu"))
        }

    @classmethod
    def delete(
        cls,
        tenant_id: UUID,
        notification_id: UUID,
        user_id: Optional[UUID] = None
    ) -> bool:
        """
        Supprime une notification (soft delete).
        """
        notification = Database.get_by_id(cls.TABLE_NAME, tenant_id, notification_id)
        if not notification:
            return False

        if user_id and str(notification.get("user_id")) != str(user_id):
            return False

        return Database.soft_delete(cls.TABLE_NAME, tenant_id, notification_id)

    @classmethod
    def delete_all_read(
        cls,
        tenant_id: UUID,
        user_id: UUID
    ) -> int:
        """
        Supprime toutes les notifications lues d'un utilisateur.

        Returns:
            Nombre de notifications supprimees
        """
        notifications = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"user_id": str(user_id), "lu": True},
            limit=1000
        )

        count = 0
        for notif in notifications:
            if Database.soft_delete(cls.TABLE_NAME, tenant_id, UUID(notif["id"])):
                count += 1

        return count


# =============================================================================
# Fonctions utilitaires pour integration workflows
# =============================================================================

def notify_devis_assigned(
    tenant_id: UUID,
    user_id: UUID,
    devis_numero: str,
    client_nom: str,
    devis_id: UUID
):
    """Notifie qu'un nouveau devis a ete assigne."""
    NotificationService.send(
        tenant_id=tenant_id,
        user_id=user_id,
        type=NotificationType.INFO.value,
        title="Nouveau devis assigne",
        message=f"Le devis {devis_numero} pour {client_nom} vous a ete assigne.",
        link=f"/ui/devis/{devis_id}",
        module_source="devis",
        record_id=devis_id,
        priority=NotificationPriority.NORMALE.value
    )


def notify_payment_received(
    tenant_id: UUID,
    user_id: UUID,
    facture_numero: str,
    montant: float,
    facture_id: UUID
):
    """Notifie qu'un paiement a ete recu."""
    NotificationService.send(
        tenant_id=tenant_id,
        user_id=user_id,
        type=NotificationType.SUCCESS.value,
        title="Paiement recu",
        message=f"Paiement de {montant:.2f} EUR recu pour la facture {facture_numero}.",
        link=f"/ui/factures/{facture_id}",
        module_source="paiements",
        record_id=facture_id,
        priority=NotificationPriority.HAUTE.value
    )


def notify_intervention_scheduled(
    tenant_id: UUID,
    user_id: UUID,
    intervention_ref: str,
    date_intervention: str,
    client_nom: str,
    intervention_id: UUID
):
    """Notifie qu'une intervention a ete planifiee."""
    NotificationService.send(
        tenant_id=tenant_id,
        user_id=user_id,
        type=NotificationType.INFO.value,
        title="Intervention planifiee",
        message=f"Intervention {intervention_ref} planifiee le {date_intervention} chez {client_nom}.",
        link=f"/ui/interventions/{intervention_id}",
        module_source="interventions",
        record_id=intervention_id,
        priority=NotificationPriority.NORMALE.value
    )


def notify_error(
    tenant_id: UUID,
    user_id: UUID,
    title: str,
    message: str,
    link: Optional[str] = None,
    record_id: Optional[UUID] = None
):
    """Envoie une notification d'erreur."""
    NotificationService.send(
        tenant_id=tenant_id,
        user_id=user_id,
        type=NotificationType.ERROR.value,
        title=title,
        message=message,
        link=link,
        record_id=record_id,
        priority=NotificationPriority.URGENTE.value
    )


def notify_warning(
    tenant_id: UUID,
    user_id: UUID,
    title: str,
    message: str,
    link: Optional[str] = None,
    record_id: Optional[UUID] = None
):
    """Envoie une notification d'avertissement."""
    NotificationService.send(
        tenant_id=tenant_id,
        user_id=user_id,
        type=NotificationType.WARNING.value,
        title=title,
        message=message,
        link=link,
        record_id=record_id,
        priority=NotificationPriority.HAUTE.value
    )
