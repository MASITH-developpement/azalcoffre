# =============================================================================
# AZALPLUS - Push Notification Service
# =============================================================================
"""
Service de notifications push via Firebase Cloud Messaging (FCM).

Fonctionnalites:
- Enregistrement de tokens push (web/mobile)
- Envoi de notifications push a un utilisateur
- Envoi de notifications push a tous les utilisateurs d'un tenant
- Nettoyage des tokens expires
- Support multi-plateforme (web, android, ios)

Multi-tenant obligatoire: tenant_id sur chaque operation.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from enum import Enum
import structlog

from .db import Database
from .config import settings

logger = structlog.get_logger()

# Table pour stocker les tokens push
PUSH_TOKENS_TABLE = "push_tokens"


class PushPlatform(str, Enum):
    """Plateformes supportees pour les notifications push."""
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"


class PushService:
    """
    Service de gestion des notifications push.

    Toutes les operations respectent l'isolation multi-tenant.
    Utilise Firebase Cloud Messaging (FCM) pour l'envoi.
    """

    # FCM credentials (initialisees lors du premier envoi)
    _fcm_initialized = False
    _fcm_app = None

    @classmethod
    def _init_fcm(cls) -> bool:
        """
        Initialise Firebase Admin SDK.

        Returns:
            True si l'initialisation reussit, False sinon.
        """
        if cls._fcm_initialized:
            return True

        try:
            import firebase_admin
            from firebase_admin import credentials

            # Chemin vers le fichier de credentials Firebase
            # En production, utiliser une variable d'environnement
            cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)

            if cred_path:
                cred = credentials.Certificate(cred_path)
                cls._fcm_app = firebase_admin.initialize_app(cred)
            else:
                # En mode development, on peut utiliser les credentials par defaut
                # ou simplement logger un warning
                logger.warning("firebase_credentials_not_configured",
                    message="FIREBASE_CREDENTIALS_PATH non configure - mode simulation")
                cls._fcm_initialized = True
                return False

            cls._fcm_initialized = True
            logger.info("fcm_initialized", status="success")
            return True

        except ImportError:
            logger.warning("firebase_admin_not_installed",
                message="Module firebase-admin non installe")
            cls._fcm_initialized = True
            return False

        except Exception as e:
            logger.error("fcm_init_error", error=str(e))
            cls._fcm_initialized = True
            return False

    @classmethod
    def register_token(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        token: str,
        platform: str = "web",
        device_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enregistre un token push pour un utilisateur.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            user_id: ID de l'utilisateur
            token: Token FCM du device
            platform: Plateforme (web, android, ios)
            device_info: Informations supplementaires sur le device

        Returns:
            Le token enregistre
        """
        # Valider la plateforme
        if platform not in [p.value for p in PushPlatform]:
            platform = PushPlatform.WEB.value

        # Verifier si le token existe deja
        existing_tokens = Database.query(
            PUSH_TOKENS_TABLE,
            tenant_id,
            filters={"token": token}
        )

        if existing_tokens:
            # Mettre a jour le token existant
            existing = existing_tokens[0]
            result = Database.update(
                PUSH_TOKENS_TABLE,
                tenant_id,
                UUID(existing["id"]),
                {
                    "user_id": str(user_id),
                    "platform": platform,
                    "device_info": device_info or {},
                    "last_active_at": datetime.utcnow().isoformat(),
                    "is_valid": True
                }
            )
            logger.info("push_token_updated",
                tenant_id=str(tenant_id),
                user_id=str(user_id),
                platform=platform
            )
            return result

        # Creer un nouveau token
        token_data = {
            "user_id": str(user_id),
            "token": token,
            "platform": platform,
            "device_info": device_info or {},
            "is_valid": True,
            "last_active_at": datetime.utcnow().isoformat()
        }

        result = Database.insert(PUSH_TOKENS_TABLE, tenant_id, token_data)

        logger.info("push_token_registered",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            platform=platform
        )

        return result

    @classmethod
    def unregister_token(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        token: str
    ) -> bool:
        """
        Supprime un token push.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            user_id: ID de l'utilisateur
            token: Token a supprimer

        Returns:
            True si la suppression a reussi
        """
        tokens = Database.query(
            PUSH_TOKENS_TABLE,
            tenant_id,
            filters={"token": token, "user_id": str(user_id)}
        )

        if not tokens:
            logger.warning("push_token_not_found",
                tenant_id=str(tenant_id),
                user_id=str(user_id)
            )
            return False

        # Soft delete
        for token_record in tokens:
            Database.soft_delete(PUSH_TOKENS_TABLE, tenant_id, UUID(token_record["id"]))

        logger.info("push_token_unregistered",
            tenant_id=str(tenant_id),
            user_id=str(user_id)
        )

        return True

    @classmethod
    def get_user_tokens(
        cls,
        tenant_id: UUID,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Recupere tous les tokens push d'un utilisateur.

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur

        Returns:
            Liste des tokens
        """
        return Database.query(
            PUSH_TOKENS_TABLE,
            tenant_id,
            filters={"user_id": str(user_id), "is_valid": True}
        )

    @classmethod
    def list_all_tokens(
        cls,
        tenant_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Liste tous les tokens du tenant (admin only).

        Args:
            tenant_id: ID du tenant
            limit: Nombre max de resultats
            offset: Offset pour pagination

        Returns:
            Dict avec items et total
        """
        tokens = Database.query(
            PUSH_TOKENS_TABLE,
            tenant_id,
            filters={"is_valid": True},
            limit=limit,
            offset=offset
        )

        total = Database.count(
            PUSH_TOKENS_TABLE,
            tenant_id,
            filters={"is_valid": True}
        )

        return {
            "items": tokens,
            "total": total
        }

    @classmethod
    def send_notification(
        cls,
        tenant_id: UUID,
        user_ids: List[UUID],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        image_url: Optional[str] = None,
        link: Optional[str] = None,
        badge_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Envoie une notification push a un ou plusieurs utilisateurs.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            user_ids: Liste des IDs utilisateurs
            title: Titre de la notification
            body: Corps du message
            data: Donnees supplementaires (key-value strings)
            image_url: URL de l'image a afficher
            link: URL a ouvrir au clic
            badge_count: Nombre a afficher sur le badge (iOS)

        Returns:
            Resultat de l'envoi avec statistiques
        """
        # Initialiser FCM si necessaire
        fcm_available = cls._init_fcm()

        # Collecter tous les tokens des utilisateurs
        all_tokens = []
        for user_id in user_ids:
            tokens = cls.get_user_tokens(tenant_id, user_id)
            all_tokens.extend(tokens)

        if not all_tokens:
            logger.warning("no_push_tokens_found",
                tenant_id=str(tenant_id),
                user_count=len(user_ids)
            )
            return {
                "success": False,
                "sent": 0,
                "failed": 0,
                "message": "Aucun token push enregistre"
            }

        # Preparer les donnees de notification
        notification_data = data or {}
        if link:
            notification_data["link"] = link
        notification_data["tenant_id"] = str(tenant_id)

        sent = 0
        failed = 0
        invalid_tokens = []

        if fcm_available and cls._fcm_app:
            try:
                from firebase_admin import messaging

                for token_record in all_tokens:
                    try:
                        # Construire le message FCM
                        message = messaging.Message(
                            notification=messaging.Notification(
                                title=title,
                                body=body,
                                image=image_url
                            ),
                            data=notification_data,
                            token=token_record["token"],
                            webpush=messaging.WebpushConfig(
                                notification=messaging.WebpushNotification(
                                    title=title,
                                    body=body,
                                    icon="/icons/icon-192.png",
                                    badge="/icons/badge-72.png",
                                    tag="notification",
                                    renotify=True
                                ),
                                fcm_options=messaging.WebpushFCMOptions(
                                    link=link
                                )
                            )
                        )

                        # Envoyer
                        response = messaging.send(message)
                        sent += 1

                        logger.debug("push_sent",
                            token_id=token_record["id"],
                            response=response
                        )

                    except messaging.UnregisteredError:
                        # Token invalide - marquer pour suppression
                        invalid_tokens.append(token_record["id"])
                        failed += 1

                    except Exception as e:
                        logger.error("push_send_error",
                            token_id=token_record["id"],
                            error=str(e)
                        )
                        failed += 1

            except ImportError:
                logger.warning("firebase_messaging_not_available")
                failed = len(all_tokens)

        else:
            # Mode simulation (development)
            logger.info("push_notification_simulated",
                tenant_id=str(tenant_id),
                title=title,
                body=body,
                token_count=len(all_tokens)
            )
            sent = len(all_tokens)

        # Marquer les tokens invalides
        for token_id in invalid_tokens:
            Database.update(
                PUSH_TOKENS_TABLE,
                tenant_id,
                UUID(token_id),
                {"is_valid": False}
            )

        logger.info("push_notification_sent",
            tenant_id=str(tenant_id),
            sent=sent,
            failed=failed,
            invalid_tokens=len(invalid_tokens)
        )

        return {
            "success": sent > 0,
            "sent": sent,
            "failed": failed,
            "invalid_tokens": len(invalid_tokens),
            "message": f"{sent} notification(s) envoyee(s)"
        }

    @classmethod
    def send_to_all_tenant(
        cls,
        tenant_id: UUID,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        image_url: Optional[str] = None,
        link: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envoie une notification push a tous les utilisateurs d'un tenant.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            title: Titre de la notification
            body: Corps du message
            data: Donnees supplementaires
            image_url: URL de l'image
            link: URL a ouvrir au clic

        Returns:
            Resultat de l'envoi avec statistiques
        """
        # Recuperer tous les tokens valides du tenant
        tokens = Database.query(
            PUSH_TOKENS_TABLE,
            tenant_id,
            filters={"is_valid": True},
            limit=10000
        )

        if not tokens:
            return {
                "success": False,
                "sent": 0,
                "failed": 0,
                "message": "Aucun token push enregistre"
            }

        # Extraire les user_ids uniques
        user_ids = list(set(UUID(t["user_id"]) for t in tokens))

        return cls.send_notification(
            tenant_id=tenant_id,
            user_ids=user_ids,
            title=title,
            body=body,
            data=data,
            image_url=image_url,
            link=link
        )

    @classmethod
    def cleanup_expired_tokens(
        cls,
        tenant_id: UUID,
        days: int = 90
    ) -> int:
        """
        Supprime les tokens inactifs depuis plus de X jours.

        Args:
            tenant_id: ID du tenant
            days: Nombre de jours d'inactivite

        Returns:
            Nombre de tokens supprimes
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Recuperer tous les tokens du tenant
        tokens = Database.query(
            PUSH_TOKENS_TABLE,
            tenant_id,
            limit=10000
        )

        deleted = 0
        for token in tokens:
            last_active = token.get("last_active_at")
            if last_active:
                try:
                    if isinstance(last_active, str):
                        last_active = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    if last_active < cutoff_date:
                        Database.soft_delete(PUSH_TOKENS_TABLE, tenant_id, UUID(token["id"]))
                        deleted += 1
                except (ValueError, TypeError):
                    pass

            # Aussi supprimer les tokens invalides
            if not token.get("is_valid"):
                Database.soft_delete(PUSH_TOKENS_TABLE, tenant_id, UUID(token["id"]))
                deleted += 1

        logger.info("push_tokens_cleanup",
            tenant_id=str(tenant_id),
            deleted=deleted,
            days=days
        )

        return deleted


# =============================================================================
# Fonctions utilitaires pour integration
# =============================================================================

def send_push_for_notification(
    tenant_id: UUID,
    user_id: UUID,
    notification_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    record_id: Optional[UUID] = None
):
    """
    Envoie une notification push correspondant a une notification in-app.

    Utile pour synchroniser les notifications push avec le NotificationService.
    """
    data = {
        "type": notification_type,
        "notification_type": notification_type
    }
    if record_id:
        data["record_id"] = str(record_id)

    return PushService.send_notification(
        tenant_id=tenant_id,
        user_ids=[user_id],
        title=title,
        body=message,
        data=data,
        link=link
    )


def send_urgent_push(
    tenant_id: UUID,
    user_id: UUID,
    title: str,
    message: str,
    link: Optional[str] = None
):
    """Envoie une notification push urgente."""
    return PushService.send_notification(
        tenant_id=tenant_id,
        user_ids=[user_id],
        title=f"[URGENT] {title}",
        body=message,
        data={"priority": "urgent"},
        link=link
    )
