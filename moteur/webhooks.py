# =============================================================================
# AZALPLUS - Webhook Service
# =============================================================================
"""
Service d'envoi de webhooks pour les integrations externes.
- Envoi asynchrone avec retry automatique
- Signature HMAC-SHA256 pour verification
- Historique des deliveries
"""

import hmac
import hashlib
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
import httpx
import structlog

from .db import Database
from .config import settings

logger = structlog.get_logger()


# =============================================================================
# Exceptions
# =============================================================================
class WebhookError(Exception):
    """Erreur lors de l'envoi d'un webhook."""
    pass


class WebhookConfigurationError(WebhookError):
    """Configuration de webhook invalide."""
    pass


class WebhookDeliveryError(WebhookError):
    """Erreur lors de la livraison du webhook."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


# =============================================================================
# Webhook Event Types
# =============================================================================
class WebhookEvents:
    """Constantes pour les types d'evenements webhook."""

    # Devis
    DEVIS_CREATED = "devis.created"
    DEVIS_UPDATED = "devis.updated"
    DEVIS_ACCEPTED = "devis.accepted"
    DEVIS_REFUSED = "devis.refused"
    DEVIS_SENT = "devis.sent"

    # Factures
    FACTURE_CREATED = "facture.created"
    FACTURE_UPDATED = "facture.updated"
    FACTURE_SENT = "facture.sent"
    FACTURE_PAID = "facture.paid"
    FACTURE_PARTIAL_PAID = "facture.partial_paid"
    FACTURE_OVERDUE = "facture.overdue"

    # Clients
    CLIENT_CREATED = "client.created"
    CLIENT_UPDATED = "client.updated"
    CLIENT_DELETED = "client.deleted"

    # Interventions
    INTERVENTION_CREATED = "intervention.created"
    INTERVENTION_SCHEDULED = "intervention.scheduled"
    INTERVENTION_STARTED = "intervention.started"
    INTERVENTION_COMPLETED = "intervention.completed"
    INTERVENTION_CANCELLED = "intervention.cancelled"

    # Paiements
    PAIEMENT_CREATED = "paiement.created"
    PAIEMENT_VALIDATED = "paiement.validated"
    PAIEMENT_REJECTED = "paiement.rejected"

    @classmethod
    def all_events(cls) -> List[str]:
        """Retourne tous les types d'evenements disponibles."""
        return [
            v for k, v in vars(cls).items()
            if not k.startswith('_') and isinstance(v, str) and '.' in v
        ]


# =============================================================================
# Webhook Service
# =============================================================================
class WebhookService:
    """Service de gestion des webhooks."""

    # HTTP client partage
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """Retourne le client HTTP partage."""
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True
            )
        return cls._client

    @classmethod
    async def close_client(cls):
        """Ferme le client HTTP."""
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None

    # =========================================================================
    # Signature HMAC
    # =========================================================================
    @classmethod
    def generate_signature(cls, payload: str, secret: str) -> str:
        """
        Genere une signature HMAC-SHA256 pour le payload.

        Args:
            payload: Payload JSON en string
            secret: Secret du webhook

        Returns:
            Signature au format "sha256=<signature_hex>"
        """
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    @classmethod
    def verify_signature(cls, payload: str, signature: str, secret: str) -> bool:
        """
        Verifie une signature HMAC-SHA256.

        Args:
            payload: Payload JSON recu
            signature: Signature recue (format "sha256=<hex>")
            secret: Secret du webhook

        Returns:
            True si la signature est valide
        """
        expected_signature = cls.generate_signature(payload, secret)
        return hmac.compare_digest(signature, expected_signature)

    # =========================================================================
    # Envoi de webhooks
    # =========================================================================
    @classmethod
    async def trigger(
        cls,
        tenant_id: UUID,
        event: str,
        data: Dict[str, Any],
        record_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Declenche tous les webhooks abonnes a un evenement.

        Args:
            tenant_id: ID du tenant (isolation obligatoire)
            event: Type d'evenement (ex: "facture.paid")
            data: Donnees de l'evenement
            record_id: ID de l'enregistrement concerne (optionnel)

        Returns:
            Liste des resultats d'envoi
        """
        # Recuperer tous les webhooks actifs pour cet evenement
        webhooks = cls._get_webhooks_for_event(tenant_id, event)

        if not webhooks:
            logger.debug("webhook_no_subscribers", event=event, tenant_id=str(tenant_id))
            return []

        # Construire le payload standard
        payload = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data
        }

        if record_id:
            payload["record_id"] = str(record_id)

        # Envoyer a tous les webhooks en parallele
        results = []
        tasks = []

        for webhook in webhooks:
            task = asyncio.create_task(
                cls._send_webhook(tenant_id, webhook, payload)
            )
            tasks.append((webhook, task))

        # Attendre tous les envois
        for webhook, task in tasks:
            try:
                result = await task
                results.append(result)
            except Exception as e:
                logger.error(
                    "webhook_trigger_error",
                    webhook_id=str(webhook.get("id")),
                    event=event,
                    error=str(e)
                )
                results.append({
                    "webhook_id": str(webhook.get("id")),
                    "success": False,
                    "error": str(e)
                })

        return results

    @classmethod
    async def _send_webhook(
        cls,
        tenant_id: UUID,
        webhook: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Envoie un webhook individuel avec gestion des retries.

        Args:
            tenant_id: ID du tenant
            webhook: Configuration du webhook
            payload: Payload a envoyer

        Returns:
            Resultat de l'envoi
        """
        webhook_id = webhook.get("id")
        url = webhook.get("url")
        secret = webhook.get("secret", "")
        timeout = webhook.get("timeout_seconds", 30)
        custom_headers = webhook.get("headers") or {}

        # Serialiser le payload
        payload_str = json.dumps(payload, ensure_ascii=False, default=str)

        # Generer la signature
        signature = cls.generate_signature(payload_str, secret)

        # Headers
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": payload.get("event", ""),
            "X-Webhook-Timestamp": payload.get("timestamp", ""),
            "User-Agent": "AZALPLUS-Webhook/1.0"
        }
        headers.update(custom_headers)

        # Creer l'enregistrement de delivery
        delivery_id = uuid4()
        delivery = {
            "id": str(delivery_id),
            "tenant_id": str(tenant_id),
            "webhook_id": str(webhook_id),
            "event": payload.get("event"),
            "payload": payload,
            "sent_at": datetime.utcnow().isoformat(),
            "attempt": 1,
            "success": False
        }

        start_time = datetime.utcnow()

        try:
            client = await cls.get_client()
            response = await client.post(
                url,
                content=payload_str,
                headers=headers,
                timeout=timeout
            )

            end_time = datetime.utcnow()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Mettre a jour la delivery
            delivery.update({
                "status_code": response.status_code,
                "response_body": response.text[:5000] if response.text else None,
                "response_time_ms": response_time_ms,
                "completed_at": end_time.isoformat(),
                "success": 200 <= response.status_code < 300
            })

            # Sauvegarder la delivery
            cls._save_delivery(tenant_id, delivery)

            # Mettre a jour les stats du webhook
            cls._update_webhook_stats(tenant_id, webhook_id, delivery["success"], response.status_code)

            if not delivery["success"]:
                logger.warning(
                    "webhook_delivery_failed",
                    webhook_id=str(webhook_id),
                    url=url,
                    status_code=response.status_code
                )
            else:
                logger.info(
                    "webhook_delivered",
                    webhook_id=str(webhook_id),
                    event=payload.get("event"),
                    response_time_ms=response_time_ms
                )

            return {
                "webhook_id": str(webhook_id),
                "delivery_id": str(delivery_id),
                "success": delivery["success"],
                "status_code": response.status_code,
                "response_time_ms": response_time_ms
            }

        except httpx.TimeoutException as e:
            delivery.update({
                "status_code": 0,
                "retry_error": f"Timeout: {str(e)}",
                "completed_at": datetime.utcnow().isoformat()
            })
            cls._save_delivery(tenant_id, delivery)
            cls._update_webhook_stats(tenant_id, webhook_id, False, 0, str(e))

            logger.error("webhook_timeout", webhook_id=str(webhook_id), url=url)
            raise WebhookDeliveryError(f"Timeout pour {url}", status_code=0)

        except httpx.RequestError as e:
            delivery.update({
                "status_code": 0,
                "retry_error": f"Request error: {str(e)}",
                "completed_at": datetime.utcnow().isoformat()
            })
            cls._save_delivery(tenant_id, delivery)
            cls._update_webhook_stats(tenant_id, webhook_id, False, 0, str(e))

            logger.error("webhook_request_error", webhook_id=str(webhook_id), url=url, error=str(e))
            raise WebhookDeliveryError(f"Erreur de requete: {str(e)}", status_code=0)

    # =========================================================================
    # Retry des webhooks echoues
    # =========================================================================
    @classmethod
    async def retry_failed(
        cls,
        tenant_id: UUID,
        max_age_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Retente les webhooks echoues.

        Args:
            tenant_id: ID du tenant
            max_age_hours: Age maximum des deliveries a retenter

        Returns:
            Statistiques des retries
        """
        # Recuperer les deliveries echouees
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)

        with Database.get_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text('''
                    SELECT wd.*, w.url, w.secret, w.timeout_seconds, w.retry_count, w.headers
                    FROM azalplus.webhookdeliveries wd
                    JOIN azalplus.webhooks w ON wd.webhook_id = w.id
                    WHERE wd.tenant_id = :tenant_id
                    AND wd.success = false
                    AND wd.sent_at > :cutoff_time
                    AND wd.attempt < w.retry_count
                    AND w.actif = true
                    AND w.deleted_at IS NULL
                    ORDER BY wd.sent_at ASC
                    LIMIT 100
                '''),
                {
                    "tenant_id": str(tenant_id),
                    "cutoff_time": cutoff_time.isoformat()
                }
            )
            failed_deliveries = [dict(row._mapping) for row in result]

        if not failed_deliveries:
            return {"retried": 0, "succeeded": 0, "failed": 0}

        succeeded = 0
        failed = 0

        for delivery in failed_deliveries:
            try:
                # Recreer le webhook config
                webhook = {
                    "id": delivery["webhook_id"],
                    "url": delivery["url"],
                    "secret": delivery["secret"],
                    "timeout_seconds": delivery.get("timeout_seconds", 30),
                    "headers": delivery.get("headers")
                }

                # Retenter l'envoi
                result = await cls._send_webhook(
                    tenant_id,
                    webhook,
                    delivery["payload"]
                )

                if result.get("success"):
                    succeeded += 1
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                logger.error(
                    "webhook_retry_error",
                    delivery_id=str(delivery["id"]),
                    error=str(e)
                )

        logger.info(
            "webhook_retry_completed",
            tenant_id=str(tenant_id),
            total=len(failed_deliveries),
            succeeded=succeeded,
            failed=failed
        )

        return {
            "retried": len(failed_deliveries),
            "succeeded": succeeded,
            "failed": failed
        }

    # =========================================================================
    # Test d'un webhook
    # =========================================================================
    @classmethod
    async def test_webhook(
        cls,
        tenant_id: UUID,
        webhook_id: UUID
    ) -> Dict[str, Any]:
        """
        Teste un webhook avec un payload de test.

        Args:
            tenant_id: ID du tenant
            webhook_id: ID du webhook a tester

        Returns:
            Resultat du test
        """
        # Recuperer le webhook
        webhook = Database.get_by_id("webhooks", tenant_id, webhook_id)
        if not webhook:
            raise WebhookConfigurationError("Webhook non trouve")

        # Payload de test
        test_payload = {
            "event": "test.ping",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": {
                "message": "Test de connexion webhook AZALPLUS",
                "webhook_id": str(webhook_id),
                "test": True
            }
        }

        try:
            result = await cls._send_webhook(tenant_id, webhook, test_payload)
            return {
                "success": result.get("success", False),
                "status_code": result.get("status_code"),
                "response_time_ms": result.get("response_time_ms"),
                "message": "Webhook teste avec succes" if result.get("success") else "Echec du test"
            }
        except WebhookDeliveryError as e:
            return {
                "success": False,
                "status_code": e.status_code,
                "error": str(e),
                "message": "Erreur lors du test du webhook"
            }

    # =========================================================================
    # Helpers prives
    # =========================================================================
    @classmethod
    def _get_webhooks_for_event(cls, tenant_id: UUID, event: str) -> List[Dict]:
        """Recupere tous les webhooks actifs abonnes a un evenement."""
        with Database.get_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text('''
                    SELECT * FROM azalplus.webhooks
                    WHERE tenant_id = :tenant_id
                    AND actif = true
                    AND deleted_at IS NULL
                    AND events @> :event_json
                '''),
                {
                    "tenant_id": str(tenant_id),
                    "event_json": json.dumps([event])
                }
            )
            return [dict(row._mapping) for row in result]

    @classmethod
    def _save_delivery(cls, tenant_id: UUID, delivery: Dict[str, Any]):
        """Sauvegarde un enregistrement de delivery."""
        try:
            Database.insert("webhookdeliveries", tenant_id, delivery)
        except Exception as e:
            logger.error("webhook_delivery_save_error", error=str(e))

    @classmethod
    def _update_webhook_stats(
        cls,
        tenant_id: UUID,
        webhook_id: UUID,
        success: bool,
        status_code: int,
        error_message: Optional[str] = None
    ):
        """Met a jour les statistiques du webhook."""
        try:
            updates = {
                "derniere_execution": datetime.utcnow().isoformat(),
                "dernier_statut": status_code
            }

            if error_message:
                updates["dernier_message"] = error_message[:1000]

            with Database.get_session() as session:
                from sqlalchemy import text

                # Incrementer les compteurs
                if success:
                    session.execute(
                        text('''
                            UPDATE azalplus.webhooks
                            SET total_envois = COALESCE(total_envois, 0) + 1,
                                total_succes = COALESCE(total_succes, 0) + 1,
                                derniere_execution = :derniere_execution,
                                dernier_statut = :dernier_statut
                            WHERE id = :webhook_id AND tenant_id = :tenant_id
                        '''),
                        {
                            "webhook_id": str(webhook_id),
                            "tenant_id": str(tenant_id),
                            "derniere_execution": updates["derniere_execution"],
                            "dernier_statut": status_code
                        }
                    )
                else:
                    session.execute(
                        text('''
                            UPDATE azalplus.webhooks
                            SET total_envois = COALESCE(total_envois, 0) + 1,
                                total_echecs = COALESCE(total_echecs, 0) + 1,
                                derniere_execution = :derniere_execution,
                                dernier_statut = :dernier_statut,
                                dernier_message = :dernier_message
                            WHERE id = :webhook_id AND tenant_id = :tenant_id
                        '''),
                        {
                            "webhook_id": str(webhook_id),
                            "tenant_id": str(tenant_id),
                            "derniere_execution": updates["derniere_execution"],
                            "dernier_statut": status_code,
                            "dernier_message": error_message or ""
                        }
                    )
                session.commit()

        except Exception as e:
            logger.error("webhook_stats_update_error", error=str(e))

    # =========================================================================
    # Liste des webhooks
    # =========================================================================
    @classmethod
    def list_webhooks(cls, tenant_id: UUID, actif_only: bool = False) -> List[Dict]:
        """
        Liste les webhooks d'un tenant.

        Args:
            tenant_id: ID du tenant
            actif_only: Si True, ne retourne que les webhooks actifs

        Returns:
            Liste des webhooks
        """
        filters = {}
        if actif_only:
            filters["actif"] = True

        return Database.query("webhooks", tenant_id, filters=filters)

    @classmethod
    def get_deliveries(
        cls,
        tenant_id: UUID,
        webhook_id: Optional[UUID] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Recupere l'historique des deliveries.

        Args:
            tenant_id: ID du tenant
            webhook_id: Filtrer par webhook (optionnel)
            limit: Nombre max de resultats

        Returns:
            Liste des deliveries
        """
        filters = {}
        if webhook_id:
            filters["webhook_id"] = str(webhook_id)

        return Database.query(
            "webhookdeliveries",
            tenant_id,
            filters=filters,
            limit=limit,
            order_by="sent_at DESC"
        )


# =============================================================================
# Integration avec le moteur d'evenements
# =============================================================================
class WebhookEventIntegration:
    """
    Integration des webhooks avec les evenements du systeme.
    A appeler depuis les services metier lors des operations CRUD.
    """

    @classmethod
    async def on_devis_created(cls, tenant_id: UUID, devis: Dict[str, Any]):
        """Declenche les webhooks pour la creation d'un devis."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.DEVIS_CREATED,
            cls._sanitize_data(devis),
            UUID(devis["id"]) if isinstance(devis.get("id"), str) else devis.get("id")
        )

    @classmethod
    async def on_devis_updated(cls, tenant_id: UUID, devis: Dict[str, Any]):
        """Declenche les webhooks pour la modification d'un devis."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.DEVIS_UPDATED,
            cls._sanitize_data(devis),
            UUID(devis["id"]) if isinstance(devis.get("id"), str) else devis.get("id")
        )

    @classmethod
    async def on_devis_accepted(cls, tenant_id: UUID, devis: Dict[str, Any]):
        """Declenche les webhooks quand un devis est accepte."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.DEVIS_ACCEPTED,
            cls._sanitize_data(devis),
            UUID(devis["id"]) if isinstance(devis.get("id"), str) else devis.get("id")
        )

    @classmethod
    async def on_facture_created(cls, tenant_id: UUID, facture: Dict[str, Any]):
        """Declenche les webhooks pour la creation d'une facture."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.FACTURE_CREATED,
            cls._sanitize_data(facture),
            UUID(facture["id"]) if isinstance(facture.get("id"), str) else facture.get("id")
        )

    @classmethod
    async def on_facture_paid(cls, tenant_id: UUID, facture: Dict[str, Any]):
        """Declenche les webhooks quand une facture est payee."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.FACTURE_PAID,
            cls._sanitize_data(facture),
            UUID(facture["id"]) if isinstance(facture.get("id"), str) else facture.get("id")
        )

    @classmethod
    async def on_client_created(cls, tenant_id: UUID, client: Dict[str, Any]):
        """Declenche les webhooks pour la creation d'un client."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.CLIENT_CREATED,
            cls._sanitize_data(client),
            UUID(client["id"]) if isinstance(client.get("id"), str) else client.get("id")
        )

    @classmethod
    async def on_client_updated(cls, tenant_id: UUID, client: Dict[str, Any]):
        """Declenche les webhooks pour la modification d'un client."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.CLIENT_UPDATED,
            cls._sanitize_data(client),
            UUID(client["id"]) if isinstance(client.get("id"), str) else client.get("id")
        )

    @classmethod
    async def on_intervention_completed(cls, tenant_id: UUID, intervention: Dict[str, Any]):
        """Declenche les webhooks quand une intervention est terminee."""
        await WebhookService.trigger(
            tenant_id,
            WebhookEvents.INTERVENTION_COMPLETED,
            cls._sanitize_data(intervention),
            UUID(intervention["id"]) if isinstance(intervention.get("id"), str) else intervention.get("id")
        )

    @classmethod
    def _sanitize_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Nettoie les donnees sensibles avant envoi.
        Ne pas envoyer: tenant_id, tokens, mots de passe, etc.
        """
        sensitive_fields = {
            "tenant_id", "password", "password_hash", "secret",
            "access_token", "refresh_token", "api_key", "signature_ip"
        }

        sanitized = {}
        for key, value in data.items():
            if key.lower() not in sensitive_fields:
                # Convertir les UUID en strings
                if hasattr(value, 'hex'):  # UUID
                    sanitized[key] = str(value)
                # Convertir les datetime en ISO format
                elif isinstance(value, datetime):
                    sanitized[key] = value.isoformat()
                else:
                    sanitized[key] = value

        return sanitized
