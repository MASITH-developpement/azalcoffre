# =============================================================================
# AZALPLUS - Gestionnaire de Webhooks
# =============================================================================
"""
Gestionnaire centralisé des webhooks pour toutes les intégrations.

Webhooks supportés:
- Fintecture: Paiements Open Banking
- Swan: Événements bancaires
- Twilio: Statuts SMS/Appels
- Transporteurs: Suivi colis

Sécurité:
- Vérification des signatures
- Idempotence (déduplication)
- Retry automatique
- Logging exhaustif
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class WebhookSource(str, Enum):
    FINTECTURE = "fintecture"
    SWAN = "swan"
    TWILIO = "twilio"
    COLISSIMO = "colissimo"
    CHRONOPOST = "chronopost"
    MONDIAL_RELAY = "mondial_relay"
    STRIPE = "stripe"


class WebhookStatus(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


@dataclass
class WebhookEvent:
    """Événement webhook reçu."""
    id: str
    source: WebhookSource
    event_type: str
    payload: dict
    signature: str
    received_at: datetime
    status: WebhookStatus = WebhookStatus.RECEIVED
    processed_at: Optional[datetime] = None
    error: Optional[str] = None
    tenant_id: Optional[UUID] = None


@dataclass
class WebhookConfig:
    """Configuration des webhooks par source."""
    source: WebhookSource
    secret: str
    enabled: bool = True


class WebhookHandler:
    """
    Gestionnaire centralisé des webhooks.

    Usage:
        handler = WebhookHandler(db)

        # Enregistrer les handlers
        handler.register(WebhookSource.FINTECTURE, "payment.successful", handle_payment_success)
        handler.register(WebhookSource.SWAN, "Transaction.Booked", handle_transaction)

        # Dans la route FastAPI
        @app.post("/webhooks/fintecture")
        async def fintecture_webhook(request: Request):
            return await handler.process(WebhookSource.FINTECTURE, request)
    """

    def __init__(self, db):
        self.db = db
        self._handlers: dict[tuple[WebhookSource, str], Callable] = {}
        self._secrets: dict[WebhookSource, str] = {}
        self._processed_ids: set[str] = set()  # Cache idempotence

    def configure(self, source: WebhookSource, secret: str):
        """Configurer le secret d'une source."""
        self._secrets[source] = secret

    def register(
        self,
        source: WebhookSource,
        event_type: str,
        handler: Callable[[WebhookEvent], Any]
    ):
        """
        Enregistrer un handler pour un type d'événement.

        Args:
            source: Source du webhook
            event_type: Type d'événement (ex: "payment.successful")
            handler: Fonction async à appeler
        """
        self._handlers[(source, event_type)] = handler
        logger.info(f"Handler registered: {source.value}/{event_type}")

    async def process(
        self,
        source: WebhookSource,
        request: Request,
        tenant_id: Optional[UUID] = None
    ) -> dict:
        """
        Traiter un webhook entrant.

        Args:
            source: Source attendue
            request: Requête FastAPI
            tenant_id: ID du tenant (si connu)

        Returns:
            dict avec statut du traitement
        """
        # 1. Extraire le payload
        try:
            body = await request.body()
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from {source}")
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # 2. Extraire la signature
        signature = self._extract_signature(source, request)

        # 3. Vérifier la signature
        if not self._verify_signature(source, body, signature):
            logger.warning(f"Invalid signature from {source}")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # 4. Créer l'événement
        event_id = self._extract_event_id(source, payload)
        event_type = self._extract_event_type(source, payload)

        event = WebhookEvent(
            id=event_id,
            source=source,
            event_type=event_type,
            payload=payload,
            signature=signature,
            received_at=datetime.utcnow(),
            tenant_id=tenant_id
        )

        # 5. Vérifier idempotence
        if await self._is_duplicate(event):
            logger.info(f"Duplicate webhook ignored: {event_id}")
            return {"status": "ignored", "reason": "duplicate"}

        # 6. Persister l'événement
        await self._save_event(event)

        # 7. Traiter l'événement
        try:
            event.status = WebhookStatus.PROCESSING
            result = await self._dispatch(event)
            event.status = WebhookStatus.PROCESSED
            event.processed_at = datetime.utcnow()

            await self._update_event(event)
            self._processed_ids.add(event_id)

            return {"status": "processed", "event_id": event_id, "result": result}

        except Exception as e:
            logger.exception(f"Error processing webhook {event_id}: {e}")
            event.status = WebhookStatus.FAILED
            event.error = str(e)
            await self._update_event(event)

            # On retourne 200 quand même pour éviter les retries infinis
            return {"status": "failed", "event_id": event_id, "error": str(e)}

    def _extract_signature(self, source: WebhookSource, request: Request) -> str:
        """Extraire la signature selon la source."""
        headers = request.headers

        signature_headers = {
            WebhookSource.FINTECTURE: "X-Fintecture-Signature",
            WebhookSource.SWAN: "Swan-Signature",
            WebhookSource.TWILIO: "X-Twilio-Signature",
            WebhookSource.STRIPE: "Stripe-Signature",
            WebhookSource.COLISSIMO: "X-Signature",
            WebhookSource.CHRONOPOST: "X-Chronopost-Signature",
            WebhookSource.MONDIAL_RELAY: "X-MR-Signature"
        }

        header = signature_headers.get(source, "X-Signature")
        return headers.get(header, "")

    def _verify_signature(self, source: WebhookSource, body: bytes, signature: str) -> bool:
        """Vérifier la signature du webhook."""
        secret = self._secrets.get(source)

        if not secret:
            logger.warning(f"No secret configured for {source}")
            # En dev, on peut accepter sans signature
            return True  # TODO: False en production

        if source == WebhookSource.STRIPE:
            # Stripe a un format spécial: t=timestamp,v1=signature
            return self._verify_stripe_signature(body, signature, secret)

        # Signature HMAC SHA256 standard
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def _verify_stripe_signature(self, body: bytes, signature: str, secret: str) -> bool:
        """Vérifier signature Stripe (format spécial)."""
        try:
            elements = dict(item.split("=") for item in signature.split(","))
            timestamp = elements.get("t", "")
            sig = elements.get("v1", "")

            signed_payload = f"{timestamp}.{body.decode()}"
            expected = hmac.new(
                secret.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected, sig)
        except Exception:
            return False

    def _extract_event_id(self, source: WebhookSource, payload: dict) -> str:
        """Extraire l'ID unique de l'événement."""
        id_fields = {
            WebhookSource.FINTECTURE: ["meta", "session_id"],
            WebhookSource.SWAN: ["eventId"],
            WebhookSource.TWILIO: ["MessageSid", "CallSid"],
            WebhookSource.STRIPE: ["id"],
        }

        fields = id_fields.get(source, ["id"])

        for field in fields:
            if isinstance(field, str):
                if field in payload:
                    return payload[field]
            elif isinstance(field, list):
                # Nested path
                value = payload
                for key in field:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        value = None
                        break
                if value:
                    return str(value)

        # Fallback: générer un ID
        return str(uuid4())

    def _extract_event_type(self, source: WebhookSource, payload: dict) -> str:
        """Extraire le type d'événement."""
        type_fields = {
            WebhookSource.FINTECTURE: "type",
            WebhookSource.SWAN: "eventType",
            WebhookSource.TWILIO: "EventType",
            WebhookSource.STRIPE: "type",
        }

        field = type_fields.get(source, "type")
        return payload.get(field, "unknown")

    async def _is_duplicate(self, event: WebhookEvent) -> bool:
        """Vérifier si l'événement a déjà été traité."""
        # Cache mémoire
        if event.id in self._processed_ids:
            return True

        # Vérifier en base
        # TODO: SELECT COUNT(*) FROM webhook_events WHERE id = ? AND status = 'processed'
        return False

    async def _dispatch(self, event: WebhookEvent) -> Any:
        """Dispatcher l'événement au bon handler."""
        handler = self._handlers.get((event.source, event.event_type))

        if handler:
            return await handler(event)

        # Handler générique par source
        handler = self._handlers.get((event.source, "*"))
        if handler:
            return await handler(event)

        logger.info(f"No handler for {event.source}/{event.event_type}")
        return {"status": "no_handler"}

    async def _save_event(self, event: WebhookEvent):
        """Persister l'événement en base."""
        # TODO: INSERT INTO webhook_events (...)
        pass

    async def _update_event(self, event: WebhookEvent):
        """Mettre à jour l'événement en base."""
        # TODO: UPDATE webhook_events SET status = ?, processed_at = ?, error = ? WHERE id = ?
        pass


# =============================================================================
# Handlers spécifiques par source
# =============================================================================

class FintectureWebhookHandlers:
    """Handlers pour les webhooks Fintecture."""

    def __init__(self, db, payment_service):
        self.db = db
        self.payment_service = payment_service

    async def handle_payment_successful(self, event: WebhookEvent) -> dict:
        """Paiement réussi."""
        data = event.payload.get("data", {})
        metadata = data.get("metadata", {})

        facture_id = metadata.get("facture_id")
        if not facture_id:
            return {"status": "error", "message": "No facture_id"}

        # Marquer la facture comme payée
        return await self.payment_service.handle_payment_webhook(
            event.payload,
            event.signature
        )

    async def handle_payment_unsuccessful(self, event: WebhookEvent) -> dict:
        """Paiement échoué."""
        data = event.payload.get("data", {})
        return {
            "status": "payment_failed",
            "error_code": data.get("error_code"),
            "error_message": data.get("error_message")
        }


class SwanWebhookHandlers:
    """Handlers pour les webhooks Swan."""

    def __init__(self, db, banking_service):
        self.db = db
        self.banking_service = banking_service

    async def handle_transaction_booked(self, event: WebhookEvent) -> dict:
        """Nouvelle transaction comptabilisée."""
        transaction = event.payload.get("transaction", {})

        # Synchroniser la transaction
        await self.banking_service.sync_transactions()

        return {
            "status": "synced",
            "transaction_id": transaction.get("id")
        }

    async def handle_account_opened(self, event: WebhookEvent) -> dict:
        """Compte ouvert avec succès."""
        account = event.payload.get("account", {})

        # Enregistrer l'IBAN
        tenant_id = event.tenant_id
        if tenant_id:
            # TODO: UPDATE tenant_settings SET iban = ? WHERE tenant_id = ?
            pass

        return {
            "status": "account_opened",
            "iban": account.get("IBAN")
        }


class TwilioWebhookHandlers:
    """Handlers pour les webhooks Twilio."""

    def __init__(self, db):
        self.db = db

    async def handle_message_status(self, event: WebhookEvent) -> dict:
        """Mise à jour statut message."""
        message_sid = event.payload.get("MessageSid")
        status = event.payload.get("MessageStatus")
        error_code = event.payload.get("ErrorCode")

        # Mettre à jour le statut en base
        # TODO: UPDATE notifications SET status = ?, error_code = ? WHERE message_sid = ?

        return {
            "status": "updated",
            "message_sid": message_sid,
            "new_status": status
        }

    async def handle_call_completed(self, event: WebhookEvent) -> dict:
        """Appel terminé."""
        call_sid = event.payload.get("CallSid")
        duration = event.payload.get("CallDuration")
        recording_url = event.payload.get("RecordingUrl")

        # Enregistrer les infos
        # TODO: UPDATE calls SET duration = ?, recording_url = ? WHERE call_sid = ?

        return {
            "status": "call_completed",
            "call_sid": call_sid,
            "duration": duration
        }


class TransporteurWebhookHandlers:
    """Handlers pour les webhooks transporteurs."""

    def __init__(self, db, expedition_service):
        self.db = db
        self.expedition_service = expedition_service

    async def handle_tracking_update(self, event: WebhookEvent) -> dict:
        """Mise à jour suivi colis."""
        tracking_number = event.payload.get("tracking_number")
        status = event.payload.get("status")
        location = event.payload.get("location")

        # Synchroniser le suivi
        # TODO: Récupérer l'expédition et mettre à jour

        # Si livré, notifier le client
        if status == "delivered":
            # TODO: Envoyer notification
            pass

        return {
            "status": "tracking_updated",
            "tracking_number": tracking_number,
            "new_status": status
        }


# =============================================================================
# Routes FastAPI
# =============================================================================

def create_webhook_routes(app, webhook_handler: WebhookHandler):
    """
    Créer les routes webhook dans l'application FastAPI.

    Usage:
        handler = WebhookHandler(db)
        create_webhook_routes(app, handler)
    """
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

    @router.post("/fintecture")
    async def fintecture_webhook(request: Request):
        return await webhook_handler.process(WebhookSource.FINTECTURE, request)

    @router.post("/swan")
    async def swan_webhook(request: Request):
        return await webhook_handler.process(WebhookSource.SWAN, request)

    @router.post("/twilio")
    async def twilio_webhook(request: Request):
        return await webhook_handler.process(WebhookSource.TWILIO, request)

    @router.post("/transporteurs/{carrier}")
    async def transporteur_webhook(carrier: str, request: Request):
        source_map = {
            "colissimo": WebhookSource.COLISSIMO,
            "chronopost": WebhookSource.CHRONOPOST,
            "mondial_relay": WebhookSource.MONDIAL_RELAY
        }
        source = source_map.get(carrier.lower())
        if not source:
            raise HTTPException(status_code=404, detail="Unknown carrier")
        return await webhook_handler.process(source, request)

    @router.post("/stripe")
    async def stripe_webhook(request: Request):
        return await webhook_handler.process(WebhookSource.STRIPE, request)

    app.include_router(router)

    return router
