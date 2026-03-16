# =============================================================================
# AZALPLUS - Routes API Webhooks (Réception callbacks externes)
# =============================================================================
"""
Routes pour recevoir les webhooks des services externes.

Endpoints:
    POST /api/webhooks/fintecture    - Callback paiement Fintecture
    POST /api/webhooks/swan          - Callback banking Swan
    POST /api/webhooks/twilio        - Callback SMS/WhatsApp Twilio
    POST /api/webhooks/colissimo     - Callback expédition Colissimo
    POST /api/webhooks/mondial_relay - Callback Mondial Relay
"""

import logging
import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from integrations.settings import get_settings, Settings
from integrations.webhooks import WebhookHandler, WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# =============================================================================
# Modèles
# =============================================================================

class WebhookResponse(BaseModel):
    """Réponse standard webhook."""
    received: bool = True
    event_id: Optional[str] = None
    processed: bool = False


# =============================================================================
# Vérification des signatures
# =============================================================================

def verify_fintecture_signature(
    payload: bytes,
    signature: str,
    secret: str
) -> bool:
    """Vérifier la signature Fintecture (HMAC-SHA256)."""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_swan_signature(
    payload: bytes,
    signature: str,
    secret: str
) -> bool:
    """Vérifier la signature Swan (HMAC-SHA256)."""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def verify_twilio_signature(
    url: str,
    params: dict,
    signature: str,
    auth_token: str
) -> bool:
    """Vérifier la signature Twilio."""
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)
    except ImportError:
        # Sans twilio SDK, vérification manuelle
        sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
        data = url + sorted_params
        expected = hmac.new(
            auth_token.encode(),
            data.encode(),
            hashlib.sha1
        ).digest()
        import base64
        return hmac.compare_digest(
            base64.b64encode(expected).decode(),
            signature
        )


# =============================================================================
# Routes Fintecture (Open Banking)
# =============================================================================

@router.post("/fintecture")
async def fintecture_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_fintecture_signature: Optional[str] = Header(None)
):
    """
    Recevoir les webhooks Fintecture.

    Événements:
    - payment.created: Paiement initié
    - payment.pending: En attente de validation
    - payment.payment_executed: Paiement réussi
    - payment.failed: Échec du paiement
    - payment.cancelled: Paiement annulé
    """
    settings = get_settings()

    if not settings.fintecture.is_configured:
        raise HTTPException(status_code=503, detail="Fintecture non configuré")

    try:
        body = await request.body()

        # Vérifier la signature si configurée
        if settings.fintecture.webhook_secret and x_fintecture_signature:
            if not verify_fintecture_signature(
                body,
                x_fintecture_signature,
                settings.fintecture.webhook_secret
            ):
                logger.warning("fintecture_webhook_invalid_signature")
                raise HTTPException(status_code=401, detail="Signature invalide")

        data = json.loads(body)

        event_type = data.get("type", "unknown")
        payment_data = data.get("data", {})

        logger.info(
            "fintecture_webhook_received",
            event_type=event_type,
            payment_id=payment_data.get("id")
        )

        # Traiter en arrière-plan
        handler = WebhookHandler(db=None)
        event = WebhookEvent(
            source="fintecture",
            event_type=event_type,
            payload=data,
            signature=x_fintecture_signature,
            received_at=datetime.utcnow()
        )

        background_tasks.add_task(handler.process_fintecture_event, event)

        return WebhookResponse(
            received=True,
            event_id=payment_data.get("id"),
            processed=False  # Traitement asynchrone
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalide")
    except Exception as e:
        logger.error(f"Erreur webhook Fintecture: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


# =============================================================================
# Routes Swan (Banking)
# =============================================================================

@router.post("/swan")
async def swan_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_swan_signature: Optional[str] = Header(None)
):
    """
    Recevoir les webhooks Swan.

    Événements:
    - Transaction.Booked: Transaction comptabilisée
    - Transaction.Pending: Transaction en attente
    - Transaction.Rejected: Transaction rejetée
    - Card.Spending: Dépense carte
    - AccountMembership.Updated: Changement membership
    """
    settings = get_settings()

    if not settings.swan.is_configured:
        raise HTTPException(status_code=503, detail="Swan non configuré")

    try:
        body = await request.body()

        # Vérifier la signature
        if settings.swan.webhook_secret and x_swan_signature:
            if not verify_swan_signature(
                body,
                x_swan_signature,
                settings.swan.webhook_secret
            ):
                logger.warning("swan_webhook_invalid_signature")
                raise HTTPException(status_code=401, detail="Signature invalide")

        data = json.loads(body)

        event_type = data.get("eventType", "unknown")
        resource = data.get("resource", {})

        logger.info(
            "swan_webhook_received",
            event_type=event_type,
            resource_id=resource.get("id")
        )

        # Traiter en arrière-plan
        handler = WebhookHandler(db=None)
        event = WebhookEvent(
            source="swan",
            event_type=event_type,
            payload=data,
            signature=x_swan_signature,
            received_at=datetime.utcnow()
        )

        background_tasks.add_task(handler.process_swan_event, event)

        return WebhookResponse(
            received=True,
            event_id=data.get("eventId"),
            processed=False
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalide")
    except Exception as e:
        logger.error(f"Erreur webhook Swan: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


# =============================================================================
# Routes Twilio (SMS/WhatsApp)
# =============================================================================

@router.post("/twilio")
async def twilio_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Recevoir les webhooks Twilio.

    Événements:
    - MessageStatus: Changement de statut SMS/WhatsApp
    - IncomingMessage: Message entrant
    """
    settings = get_settings()

    if not settings.twilio.is_configured:
        raise HTTPException(status_code=503, detail="Twilio non configuré")

    try:
        # Twilio envoie en form-urlencoded
        form_data = await request.form()
        data = dict(form_data)

        # Vérifier la signature Twilio
        twilio_signature = request.headers.get("X-Twilio-Signature", "")
        if twilio_signature and settings.twilio.auth_token:
            url = str(request.url)
            if not verify_twilio_signature(
                url,
                data,
                twilio_signature,
                settings.twilio.auth_token
            ):
                logger.warning("twilio_webhook_invalid_signature")
                raise HTTPException(status_code=401, detail="Signature invalide")

        message_sid = data.get("MessageSid", data.get("SmsSid", ""))
        message_status = data.get("MessageStatus", data.get("SmsStatus", ""))
        from_number = data.get("From", "")

        logger.info(
            "twilio_webhook_received",
            message_sid=message_sid,
            status=message_status,
            from_number=from_number
        )

        # Traiter en arrière-plan
        handler = WebhookHandler(db=None)
        event = WebhookEvent(
            source="twilio",
            event_type=f"message.{message_status.lower()}" if message_status else "message.received",
            payload=data,
            signature=twilio_signature,
            received_at=datetime.utcnow()
        )

        background_tasks.add_task(handler.process_twilio_event, event)

        # Twilio attend une réponse TwiML vide
        return PlainTextResponse(content="", media_type="text/xml")

    except Exception as e:
        logger.error(f"Erreur webhook Twilio: {e}")
        return PlainTextResponse(content="", media_type="text/xml")


@router.post("/twilio/status")
async def twilio_status_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Recevoir les callbacks de statut Twilio.

    URL de callback pour StatusCallback lors de l'envoi.
    """
    return await twilio_webhook(request, background_tasks)


# =============================================================================
# Routes Colissimo
# =============================================================================

@router.post("/colissimo")
async def colissimo_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Recevoir les webhooks Colissimo.

    Événements de suivi colis:
    - PRIS_EN_CHARGE: Colis pris en charge
    - EN_COURS_LIVRAISON: En cours de livraison
    - LIVRE: Livré
    - PROBLEME: Problème de livraison
    """
    settings = get_settings()

    if not settings.transporteurs.colissimo.is_configured:
        raise HTTPException(status_code=503, detail="Colissimo non configuré")

    try:
        data = await request.json()

        tracking_number = data.get("numeroSuivi", data.get("trackingNumber", ""))
        event_code = data.get("codeEvenement", data.get("eventCode", ""))

        logger.info(
            "colissimo_webhook_received",
            tracking_number=tracking_number,
            event_code=event_code
        )

        # Traiter en arrière-plan
        handler = WebhookHandler(db=None)
        event = WebhookEvent(
            source="colissimo",
            event_type=f"tracking.{event_code.lower()}" if event_code else "tracking.update",
            payload=data,
            received_at=datetime.utcnow()
        )

        background_tasks.add_task(handler.process_carrier_event, event)

        return WebhookResponse(
            received=True,
            event_id=tracking_number,
            processed=False
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalide")
    except Exception as e:
        logger.error(f"Erreur webhook Colissimo: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


# =============================================================================
# Routes Mondial Relay
# =============================================================================

@router.post("/mondial_relay")
async def mondial_relay_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Recevoir les webhooks Mondial Relay.

    Événements de suivi:
    - DEPOT: Déposé en point relais
    - EN_TRANSIT: En transit
    - DISPONIBLE: Disponible en point relais
    - LIVRE: Récupéré par le client
    """
    settings = get_settings()

    if not settings.transporteurs.mondial_relay.is_configured:
        raise HTTPException(status_code=503, detail="Mondial Relay non configuré")

    try:
        data = await request.json()

        tracking_number = data.get("NumeroExpedition", data.get("expeditionNumber", ""))
        status = data.get("Statut", data.get("status", ""))

        logger.info(
            "mondial_relay_webhook_received",
            tracking_number=tracking_number,
            status=status
        )

        # Traiter en arrière-plan
        handler = WebhookHandler(db=None)
        event = WebhookEvent(
            source="mondial_relay",
            event_type=f"tracking.{status.lower()}" if status else "tracking.update",
            payload=data,
            received_at=datetime.utcnow()
        )

        background_tasks.add_task(handler.process_carrier_event, event)

        return WebhookResponse(
            received=True,
            event_id=tracking_number,
            processed=False
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalide")
    except Exception as e:
        logger.error(f"Erreur webhook Mondial Relay: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


# =============================================================================
# Routes Chronopost
# =============================================================================

@router.post("/chronopost")
async def chronopost_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Recevoir les webhooks Chronopost.

    Événements de suivi express.
    """
    settings = get_settings()

    if not settings.transporteurs.chronopost.is_configured:
        raise HTTPException(status_code=503, detail="Chronopost non configuré")

    try:
        data = await request.json()

        tracking_number = data.get("numeroSuivi", data.get("skybillNumber", ""))
        event_code = data.get("codeEvenement", data.get("eventCode", ""))

        logger.info(
            "chronopost_webhook_received",
            tracking_number=tracking_number,
            event_code=event_code
        )

        # Traiter en arrière-plan
        handler = WebhookHandler(db=None)
        event = WebhookEvent(
            source="chronopost",
            event_type=f"tracking.{event_code.lower()}" if event_code else "tracking.update",
            payload=data,
            received_at=datetime.utcnow()
        )

        background_tasks.add_task(handler.process_carrier_event, event)

        return WebhookResponse(
            received=True,
            event_id=tracking_number,
            processed=False
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalide")
    except Exception as e:
        logger.error(f"Erreur webhook Chronopost: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


# =============================================================================
# Route de test (développement)
# =============================================================================

@router.post("/test")
async def test_webhook(request: Request):
    """
    Endpoint de test pour les webhooks (développement uniquement).
    """
    settings = get_settings()

    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        content_type = request.headers.get("content-type", "")

        if "json" in content_type:
            data = await request.json()
        elif "form" in content_type:
            data = dict(await request.form())
        else:
            data = (await request.body()).decode()

        logger.info("test_webhook_received", data=data)

        return {
            "received": True,
            "content_type": content_type,
            "headers": dict(request.headers),
            "data": data
        }

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Route de vérification
# =============================================================================

@router.get("/health")
async def webhooks_health():
    """
    Vérifier que les webhooks sont configurés.
    """
    settings = get_settings()

    return {
        "status": "ok",
        "webhooks": {
            "fintecture": settings.fintecture.is_configured,
            "swan": settings.swan.is_configured,
            "twilio": settings.twilio.is_configured,
            "colissimo": settings.transporteurs.colissimo.is_configured,
            "mondial_relay": settings.transporteurs.mondial_relay.is_configured,
            "chronopost": settings.transporteurs.chronopost.is_configured
        }
    }
