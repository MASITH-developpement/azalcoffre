# =============================================================================
# AZALPLUS - Routes API Notifications (Twilio SMS/WhatsApp)
# =============================================================================
"""
Routes pour les notifications SMS et WhatsApp via Twilio.

Endpoints:
    POST /api/notifications/sms           - Envoyer un SMS
    POST /api/notifications/whatsapp      - Envoyer un WhatsApp
    POST /api/notifications/invoice       - Notification facture
    POST /api/notifications/reminder      - Rappel RDV
    POST /api/notifications/2fa           - Code 2FA
    GET  /api/notifications/{id}          - Statut message
    GET  /api/notifications/history       - Historique
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from integrations.settings import get_settings, Settings
from integrations.twilio_sms import (
    TwilioClient,
    NotificationService,
    MessageChannel,
    MessageStatus,
    TwilioError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# =============================================================================
# Modèles Pydantic
# =============================================================================

class SendSMSRequest(BaseModel):
    """Requête envoi SMS."""
    to: str = Field(..., description="Numéro destinataire (format E.164: +33612345678)")
    body: str = Field(..., min_length=1, max_length=1600, description="Contenu du message")
    status_callback: Optional[str] = Field(None, description="URL webhook statut")


class SendWhatsAppRequest(BaseModel):
    """Requête envoi WhatsApp."""
    to: str = Field(..., description="Numéro destinataire (format E.164)")
    body: str = Field(..., min_length=1, description="Contenu du message")
    media_url: Optional[str] = Field(None, description="URL média (image, PDF)")


class InvoiceNotificationRequest(BaseModel):
    """Requête notification facture."""
    to: str = Field(..., description="Numéro destinataire")
    invoice_number: str
    amount: float
    due_date: str
    payment_url: str
    channel: str = Field("sms", description="sms ou whatsapp")


class ReminderRequest(BaseModel):
    """Requête rappel RDV."""
    to: str
    client_name: str
    appointment_date: str
    appointment_time: str
    service: str
    channel: str = Field("sms", description="sms ou whatsapp")


class TwoFactorRequest(BaseModel):
    """Requête code 2FA."""
    to: str
    user_id: Optional[UUID] = None


class MessageResponse(BaseModel):
    """Réponse envoi message."""
    message_sid: str
    channel: str
    to: str
    status: str
    sent_at: str


class MessageStatusResponse(BaseModel):
    """Statut d'un message."""
    message_sid: str
    channel: str
    to: str
    body: str
    status: str
    price: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class PaymentReminderRequest(BaseModel):
    """Requête relance paiement."""
    facture_id: UUID
    reminder_level: int = Field(1, ge=1, le=3, description="Niveau de relance (1-3)")


# =============================================================================
# Dépendances
# =============================================================================

def get_twilio_client(settings: Settings = Depends(get_settings)) -> TwilioClient:
    """Récupérer le client Twilio."""
    if not settings.twilio.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Twilio non configuré. Vérifiez les variables TWILIO_*"
        )
    return TwilioClient(settings.twilio.to_config())


def validate_phone_number(phone: str) -> str:
    """Valider et normaliser un numéro de téléphone."""
    # Supprimer espaces et tirets
    phone = phone.replace(" ", "").replace("-", "")

    # Format E.164
    if not phone.startswith("+"):
        if phone.startswith("0"):
            phone = "+33" + phone[1:]
        else:
            phone = "+" + phone

    # Validation basique
    if len(phone) < 10 or len(phone) > 15:
        raise HTTPException(status_code=400, detail="Numéro de téléphone invalide")

    return phone


# =============================================================================
# Routes SMS
# =============================================================================

@router.post("/sms", response_model=MessageResponse)
async def send_sms(
    request: SendSMSRequest,
    client: TwilioClient = Depends(get_twilio_client)
):
    """
    Envoyer un SMS.

    Tarification: ~0.065€/SMS (France)
    Longueur max: 1600 caractères (divisé en plusieurs SMS si nécessaire)
    """
    try:
        to = validate_phone_number(request.to)

        msg = await client.send_sms(
            to=to,
            body=request.body,
            status_callback=request.status_callback
        )

        return MessageResponse(
            message_sid=msg.sid,
            channel="sms",
            to=to,
            status=msg.status.value,
            sent_at=msg.sent_at.isoformat() if msg.sent_at else datetime.utcnow().isoformat()
        )

    except TwilioError as e:
        logger.error(f"Erreur Twilio SMS: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/whatsapp", response_model=MessageResponse)
async def send_whatsapp(
    request: SendWhatsAppRequest,
    client: TwilioClient = Depends(get_twilio_client),
    settings: Settings = Depends(get_settings)
):
    """
    Envoyer un message WhatsApp.

    Nécessite un numéro WhatsApp Business configuré.
    Tarification: ~0.05€/message (France)
    Peut inclure des médias (images, PDF).
    """
    if not settings.twilio.whatsapp_enabled:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp non configuré. Ajoutez TWILIO_WHATSAPP_NUMBER"
        )

    try:
        to = validate_phone_number(request.to)

        msg = await client.send_whatsapp(
            to=to,
            body=request.body,
            media_url=request.media_url
        )

        return MessageResponse(
            message_sid=msg.sid,
            channel="whatsapp",
            to=to,
            status=msg.status.value,
            sent_at=msg.sent_at.isoformat() if msg.sent_at else datetime.utcnow().isoformat()
        )

    except TwilioError as e:
        logger.error(f"Erreur Twilio WhatsApp: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


# =============================================================================
# Routes Notifications métier
# =============================================================================

@router.post("/invoice", response_model=MessageResponse)
async def send_invoice_notification(
    request: InvoiceNotificationRequest,
    client: TwilioClient = Depends(get_twilio_client),
    settings: Settings = Depends(get_settings)
):
    """
    Envoyer une notification de facture.

    Inclut:
    - Numéro de facture
    - Montant
    - Date d'échéance
    - Lien de paiement
    """
    try:
        to = validate_phone_number(request.to)
        channel = MessageChannel(request.channel.lower())

        if channel == MessageChannel.WHATSAPP and not settings.twilio.whatsapp_enabled:
            channel = MessageChannel.SMS

        msg = await client.send_invoice_notification(
            to=to,
            invoice_number=request.invoice_number,
            amount=request.amount,
            due_date=request.due_date,
            payment_url=request.payment_url,
            channel=channel
        )

        return MessageResponse(
            message_sid=msg.sid,
            channel=channel.value,
            to=to,
            status=msg.status.value,
            sent_at=datetime.utcnow().isoformat()
        )

    except TwilioError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/reminder", response_model=MessageResponse)
async def send_appointment_reminder(
    request: ReminderRequest,
    client: TwilioClient = Depends(get_twilio_client),
    settings: Settings = Depends(get_settings)
):
    """
    Envoyer un rappel de rendez-vous.

    Message type:
    "Bonjour {client}, rappel: RDV le {date} à {heure} pour {service}.
    Répondez CONFIRMER ou ANNULER"
    """
    try:
        to = validate_phone_number(request.to)
        channel = MessageChannel(request.channel.lower())

        if channel == MessageChannel.WHATSAPP and not settings.twilio.whatsapp_enabled:
            channel = MessageChannel.SMS

        msg = await client.send_appointment_reminder(
            to=to,
            client_name=request.client_name,
            appointment_date=request.appointment_date,
            appointment_time=request.appointment_time,
            service=request.service,
            channel=channel
        )

        return MessageResponse(
            message_sid=msg.sid,
            channel=channel.value,
            to=to,
            status=msg.status.value,
            sent_at=datetime.utcnow().isoformat()
        )

    except TwilioError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/2fa")
async def send_2fa_code(
    request: TwoFactorRequest,
    client: TwilioClient = Depends(get_twilio_client)
):
    """
    Envoyer un code de vérification 2FA par SMS.

    Génère un code à 6 chiffres valable 5 minutes.
    """
    import secrets

    try:
        to = validate_phone_number(request.to)
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

        msg = await client.send_verification_code(to, code)

        # TODO: Sauvegarder le code hashé en base avec expiration

        return {
            "message_sid": msg.sid,
            "status": msg.status.value,
            "to": to,
            "expires_in_seconds": 300,
            # Ne pas retourner le code en production !
            "code": code if not get_settings().is_production else None
        }

    except TwilioError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.post("/payment-reminder")
async def send_payment_reminder(
    request: PaymentReminderRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Envoyer une relance de paiement.

    Niveaux de relance:
    - 1: Rappel amical
    - 2: Deuxième rappel
    - 3: Dernier rappel (ton plus urgent)
    """
    if not settings.twilio.is_configured:
        raise HTTPException(status_code=503, detail="Twilio non configuré")

    # TODO: Injecter DB
    service = NotificationService(db=None, tenant_id=UUID("00000000-0000-0000-0000-000000000000"))

    try:
        msg = await service.send_payment_reminder(
            facture_id=request.facture_id,
            reminder_level=request.reminder_level
        )

        if msg:
            return {
                "message_sid": msg.sid,
                "status": msg.status.value,
                "reminder_level": request.reminder_level
            }
        else:
            raise HTTPException(status_code=400, detail="Impossible d'envoyer la relance")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Routes Statut & Historique
# =============================================================================

@router.get("/{message_sid}", response_model=MessageStatusResponse)
async def get_message_status(
    message_sid: str,
    client: TwilioClient = Depends(get_twilio_client)
):
    """
    Récupérer le statut d'un message.

    Statuts possibles:
    - queued: En file d'attente
    - sending: En cours d'envoi
    - sent: Envoyé
    - delivered: Délivré
    - undelivered: Non délivré
    - failed: Échec
    """
    try:
        msg = await client.get_message_status(message_sid)

        return MessageStatusResponse(
            message_sid=msg.sid,
            channel=msg.channel.value,
            to=msg.to,
            body=msg.body,
            status=msg.status.value,
            price=msg.price,
            error_code=msg.error_code,
            error_message=msg.error_message
        )

    except TwilioError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Message non trouvé")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await client.close()


@router.get("/history")
async def get_notification_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    channel: Optional[str] = Query(None, description="sms ou whatsapp"),
    status: Optional[str] = Query(None, description="Filtrer par statut")
):
    """
    Historique des notifications envoyées.

    Pagination par offset/limit.
    """
    # TODO: Implémenter avec la DB
    return {
        "total": 0,
        "limit": limit,
        "offset": offset,
        "messages": []
    }


# =============================================================================
# Routes Configuration
# =============================================================================

@router.get("/config")
async def get_notification_config(settings: Settings = Depends(get_settings)):
    """
    Configuration des notifications.

    Indique quels canaux sont disponibles.
    """
    return {
        "sms_enabled": settings.twilio.is_configured,
        "whatsapp_enabled": settings.twilio.whatsapp_enabled,
        "phone_number": settings.twilio.phone_number if settings.twilio.is_configured else None,
        "whatsapp_number": settings.twilio.whatsapp_number if settings.twilio.whatsapp_enabled else None,
        "pricing": {
            "sms_france": TwilioClient.PRICE_SMS_FR,
            "whatsapp_france": TwilioClient.PRICE_WHATSAPP_FR
        }
    }


@router.get("/stats")
async def get_notification_stats(
    period: str = Query("month", description="day, week, month, year")
):
    """
    Statistiques des notifications.

    Retourne:
    - Nombre de messages par canal
    - Taux de délivrance
    - Coût total
    """
    # TODO: Implémenter avec la DB
    return {
        "period": period,
        "sms_count": 0,
        "whatsapp_count": 0,
        "delivery_rate": 0,
        "total_cost": 0
    }


# =============================================================================
# Templates de messages
# =============================================================================

@router.get("/templates")
async def get_message_templates():
    """
    Templates de messages prédéfinis.

    Utilisables pour les notifications automatiques.
    """
    return {
        "templates": [
            {
                "id": "invoice_sent",
                "name": "Facture envoyée",
                "body": "Facture {numero} - {montant}€\nÉchéance: {date}\nPayer: {url}",
                "variables": ["numero", "montant", "date", "url"]
            },
            {
                "id": "appointment_reminder",
                "name": "Rappel RDV",
                "body": "Bonjour {nom}, rappel: RDV le {date} à {heure}\n{service}",
                "variables": ["nom", "date", "heure", "service"]
            },
            {
                "id": "payment_received",
                "name": "Paiement reçu",
                "body": "Merci ! Paiement de {montant}€ reçu pour {reference}.",
                "variables": ["montant", "reference"]
            },
            {
                "id": "quote_sent",
                "name": "Devis envoyé",
                "body": "Votre devis {numero} est disponible: {url}\nValable jusqu'au {date}",
                "variables": ["numero", "url", "date"]
            },
            {
                "id": "payment_reminder_1",
                "name": "Relance niveau 1",
                "body": "Rappel: Facture {numero} de {montant}€ à régler.\nPayer: {url}",
                "variables": ["numero", "montant", "url"]
            },
            {
                "id": "payment_reminder_2",
                "name": "Relance niveau 2",
                "body": "2ème rappel: Facture {numero} impayée ({montant}€).\nMerci de régulariser: {url}",
                "variables": ["numero", "montant", "url"]
            },
            {
                "id": "payment_reminder_3",
                "name": "Relance niveau 3",
                "body": "URGENT: Facture {numero} en retard ({montant}€).\nDernier rappel avant procédure.",
                "variables": ["numero", "montant"]
            }
        ]
    }
