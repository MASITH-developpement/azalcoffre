# =============================================================================
# AZALPLUS - Intégration Twilio (SMS & Téléphonie)
# =============================================================================
"""
Twilio API - SMS, WhatsApp et Téléphonie

Fonctionnalités:
- Envoi SMS (notifications, rappels, codes 2FA)
- WhatsApp Business
- Répondeur téléphonique IA
- Transcription appels
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class MessageStatus(str, Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"
    FAILED = "failed"


class MessageChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


@dataclass
class TwilioConfig:
    """Configuration Twilio par tenant."""
    account_sid: str
    auth_token: str
    phone_number: str  # Numéro expéditeur
    whatsapp_number: Optional[str] = None
    webhook_url: Optional[str] = None

    @property
    def base_url(self) -> str:
        return f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"


@dataclass
class Message:
    """Message envoyé."""
    sid: str
    channel: MessageChannel
    to: str
    body: str
    status: MessageStatus
    sent_at: Optional[datetime] = None
    price: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class Call:
    """Appel téléphonique."""
    sid: str
    from_number: str
    to_number: str
    status: str
    direction: str  # "inbound" ou "outbound"
    duration: int = 0
    started_at: Optional[datetime] = None
    recording_url: Optional[str] = None
    transcription: Optional[str] = None


class TwilioClient:
    """
    Client API Twilio pour SMS et téléphonie.

    Usage:
        config = TwilioConfig(
            account_sid="ACxxxx",
            auth_token="xxxx",
            phone_number="+33123456789"
        )
        client = TwilioClient(config)

        # Envoyer un SMS
        msg = await client.send_sms(
            to="+33612345678",
            body="Votre RDV est confirmé pour demain 10h"
        )

        # Envoyer un WhatsApp
        msg = await client.send_whatsapp(
            to="+33612345678",
            body="Bonjour ! Votre facture est disponible."
        )
    """

    # Tarifs indicatifs (France)
    PRICE_SMS_FR = 0.065  # EUR par SMS
    PRICE_WHATSAPP_FR = 0.05  # EUR par message

    def __init__(self, config: TwilioConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with auth."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                auth=(self.config.account_sid, self.config.auth_token),
                timeout=30.0
            )
        return self._http_client

    async def send_sms(
        self,
        to: str,
        body: str,
        status_callback: Optional[str] = None
    ) -> Message:
        """
        Envoyer un SMS.

        Args:
            to: Numéro destinataire (format E.164: +33612345678)
            body: Contenu du message (max 1600 chars)
            status_callback: URL webhook pour statut

        Returns:
            Message
        """
        client = await self._get_client()

        data = {
            "To": to,
            "From": self.config.phone_number,
            "Body": body[:1600]
        }

        if status_callback:
            data["StatusCallback"] = status_callback

        response = await client.post(
            "/Messages.json",
            data=data
        )

        if response.status_code >= 400:
            error = response.json()
            logger.error(f"Twilio SMS error: {error}")
            raise TwilioError(
                error.get("message", "Erreur envoi SMS"),
                error.get("code")
            )

        result = response.json()

        return Message(
            sid=result["sid"],
            channel=MessageChannel.SMS,
            to=to,
            body=body,
            status=MessageStatus(result["status"]),
            sent_at=datetime.utcnow()
        )

    async def send_whatsapp(
        self,
        to: str,
        body: str,
        media_url: Optional[str] = None
    ) -> Message:
        """
        Envoyer un message WhatsApp.

        Args:
            to: Numéro destinataire (format E.164)
            body: Contenu du message
            media_url: URL média (image, PDF) optionnel

        Returns:
            Message
        """
        if not self.config.whatsapp_number:
            raise TwilioError("WhatsApp non configuré")

        client = await self._get_client()

        data = {
            "To": f"whatsapp:{to}",
            "From": f"whatsapp:{self.config.whatsapp_number}",
            "Body": body
        }

        if media_url:
            data["MediaUrl"] = media_url

        response = await client.post(
            "/Messages.json",
            data=data
        )

        if response.status_code >= 400:
            error = response.json()
            raise TwilioError(error.get("message"), error.get("code"))

        result = response.json()

        return Message(
            sid=result["sid"],
            channel=MessageChannel.WHATSAPP,
            to=to,
            body=body,
            status=MessageStatus(result["status"]),
            sent_at=datetime.utcnow()
        )

    async def get_message_status(self, message_sid: str) -> Message:
        """Récupérer le statut d'un message."""
        client = await self._get_client()

        response = await client.get(f"/Messages/{message_sid}.json")
        response.raise_for_status()

        result = response.json()

        return Message(
            sid=result["sid"],
            channel=MessageChannel.WHATSAPP if "whatsapp" in result.get("to", "") else MessageChannel.SMS,
            to=result["to"].replace("whatsapp:", ""),
            body=result["body"],
            status=MessageStatus(result["status"]),
            price=float(result.get("price") or 0),
            error_code=result.get("error_code"),
            error_message=result.get("error_message")
        )

    async def send_verification_code(self, to: str, code: str, app_name: str = "AZALPLUS") -> Message:
        """
        Envoyer un code de vérification 2FA.

        Args:
            to: Numéro de téléphone
            code: Code à 6 chiffres
            app_name: Nom de l'application

        Returns:
            Message
        """
        body = f"[{app_name}] Votre code de vérification: {code}. Valable 5 minutes."
        return await self.send_sms(to, body)

    async def send_invoice_notification(
        self,
        to: str,
        invoice_number: str,
        amount: float,
        due_date: str,
        payment_url: str,
        channel: MessageChannel = MessageChannel.SMS
    ) -> Message:
        """
        Envoyer une notification de facture.

        Args:
            to: Numéro destinataire
            invoice_number: Numéro facture
            amount: Montant TTC
            due_date: Date échéance
            payment_url: Lien de paiement

        Returns:
            Message
        """
        body = (
            f"Facture {invoice_number} - {amount:.2f}€\n"
            f"Échéance: {due_date}\n"
            f"Payer maintenant: {payment_url}"
        )

        if channel == MessageChannel.WHATSAPP:
            return await self.send_whatsapp(to, body)
        return await self.send_sms(to, body)

    async def send_appointment_reminder(
        self,
        to: str,
        client_name: str,
        appointment_date: str,
        appointment_time: str,
        service: str,
        channel: MessageChannel = MessageChannel.SMS
    ) -> Message:
        """
        Envoyer un rappel de RDV.

        Args:
            to: Numéro destinataire
            client_name: Nom du client
            appointment_date: Date du RDV
            appointment_time: Heure du RDV
            service: Description du service

        Returns:
            Message
        """
        body = (
            f"Bonjour {client_name},\n"
            f"Rappel: RDV le {appointment_date} à {appointment_time}\n"
            f"Prestation: {service}\n"
            f"Répondez CONFIRMER ou ANNULER"
        )

        if channel == MessageChannel.WHATSAPP:
            return await self.send_whatsapp(to, body)
        return await self.send_sms(to, body)

    # -------------------------------------------------------------------------
    # Téléphonie (appels)
    # -------------------------------------------------------------------------

    async def make_call(
        self,
        to: str,
        twiml_url: str,
        status_callback: Optional[str] = None
    ) -> Call:
        """
        Passer un appel sortant.

        Args:
            to: Numéro à appeler
            twiml_url: URL retournant le TwiML
            status_callback: URL webhook statut

        Returns:
            Call
        """
        client = await self._get_client()

        data = {
            "To": to,
            "From": self.config.phone_number,
            "Url": twiml_url,
            "Record": "true"
        }

        if status_callback:
            data["StatusCallback"] = status_callback

        response = await client.post("/Calls.json", data=data)

        if response.status_code >= 400:
            error = response.json()
            raise TwilioError(error.get("message"), error.get("code"))

        result = response.json()

        return Call(
            sid=result["sid"],
            from_number=self.config.phone_number,
            to_number=to,
            status=result["status"],
            direction="outbound",
            started_at=datetime.utcnow()
        )

    async def get_call(self, call_sid: str) -> Call:
        """Récupérer les détails d'un appel."""
        client = await self._get_client()

        response = await client.get(f"/Calls/{call_sid}.json")
        response.raise_for_status()

        result = response.json()

        return Call(
            sid=result["sid"],
            from_number=result["from"],
            to_number=result["to"],
            status=result["status"],
            direction=result["direction"],
            duration=int(result.get("duration") or 0)
        )

    async def get_recording(self, recording_sid: str) -> dict:
        """Récupérer un enregistrement d'appel."""
        client = await self._get_client()

        response = await client.get(f"/Recordings/{recording_sid}.json")
        response.raise_for_status()

        result = response.json()

        return {
            "sid": result["sid"],
            "call_sid": result["call_sid"],
            "duration": int(result.get("duration") or 0),
            "url": f"https://api.twilio.com{result['uri'].replace('.json', '.mp3')}",
            "status": result["status"]
        }

    async def get_transcription(self, recording_sid: str) -> Optional[str]:
        """
        Récupérer la transcription d'un enregistrement.

        Note: Nécessite que la transcription soit activée.
        """
        client = await self._get_client()

        response = await client.get(
            f"/Recordings/{recording_sid}/Transcriptions.json"
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        result = response.json()

        transcriptions = result.get("transcriptions", [])
        if transcriptions:
            return transcriptions[0].get("transcription_text")

        return None

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class TwilioError(Exception):
    """Erreur API Twilio."""

    def __init__(self, message: str, code: str = None):
        super().__init__(message)
        self.code = code


# =============================================================================
# Service de notifications AZALPLUS
# =============================================================================

class NotificationService:
    """
    Service de notifications multi-canal pour AZALPLUS.

    Gère l'envoi de SMS, WhatsApp et emails pour:
    - Rappels de RDV
    - Notifications de facturation
    - Codes 2FA
    - Alertes métier
    """

    def __init__(self, db, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self._twilio: Optional[TwilioClient] = None

    async def _get_twilio(self) -> TwilioClient:
        """Récupérer le client Twilio configuré."""
        if self._twilio:
            return self._twilio

        import os
        config = TwilioConfig(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            phone_number=os.getenv("TWILIO_PHONE_NUMBER", ""),
            whatsapp_number=os.getenv("TWILIO_WHATSAPP_NUMBER"),
            webhook_url=os.getenv("TWILIO_WEBHOOK_URL")
        )

        self._twilio = TwilioClient(config)
        return self._twilio

    async def notify_invoice_sent(
        self,
        facture_id: UUID,
        client_id: UUID,
        channels: list[MessageChannel] = None
    ) -> list[Message]:
        """
        Notifier un client qu'une facture a été envoyée.

        Args:
            facture_id: ID de la facture
            client_id: ID du client
            channels: Canaux à utiliser (défaut: SMS)

        Returns:
            Liste des messages envoyés
        """
        if channels is None:
            channels = [MessageChannel.SMS]

        facture = await self._get_facture(facture_id)
        client = await self._get_client(client_id)

        if not client.get("telephone"):
            logger.warning(f"Client {client_id} sans téléphone")
            return []

        twilio = await self._get_twilio()
        messages = []

        payment_url = f"https://app.azalplus.fr/p/{facture['payment_token']}"

        for channel in channels:
            try:
                msg = await twilio.send_invoice_notification(
                    to=client["telephone"],
                    invoice_number=facture["numero"],
                    amount=float(facture["montant_ttc"]),
                    due_date=facture["date_echeance"],
                    payment_url=payment_url,
                    channel=channel
                )
                messages.append(msg)

                # Enregistrer en base
                await self._save_notification(
                    type="facture_envoyee",
                    channel=channel.value,
                    recipient=client["telephone"],
                    message_sid=msg.sid,
                    related_id=str(facture_id)
                )

            except TwilioError as e:
                logger.error(f"Erreur notification {channel}: {e}")

        return messages

    async def notify_appointment_reminder(
        self,
        rdv_id: UUID,
        hours_before: int = 24
    ) -> Optional[Message]:
        """
        Envoyer un rappel de RDV.

        Args:
            rdv_id: ID du RDV
            hours_before: Heures avant le RDV

        Returns:
            Message envoyé ou None
        """
        rdv = await self._get_rdv(rdv_id)
        client = await self._get_client(rdv["client_id"])

        if not client.get("telephone"):
            return None

        # Préférer WhatsApp si disponible
        channel = MessageChannel.WHATSAPP if client.get("whatsapp_optin") else MessageChannel.SMS

        twilio = await self._get_twilio()

        try:
            msg = await twilio.send_appointment_reminder(
                to=client["telephone"],
                client_name=client["nom"],
                appointment_date=rdv["date"].strftime("%d/%m/%Y"),
                appointment_time=rdv["heure"],
                service=rdv["description"],
                channel=channel
            )

            await self._save_notification(
                type="rappel_rdv",
                channel=channel.value,
                recipient=client["telephone"],
                message_sid=msg.sid,
                related_id=str(rdv_id)
            )

            return msg

        except TwilioError as e:
            logger.error(f"Erreur rappel RDV: {e}")
            return None

    async def send_2fa_code(self, user_id: UUID, phone: str) -> tuple[str, Message]:
        """
        Envoyer un code 2FA par SMS.

        Args:
            user_id: ID utilisateur
            phone: Numéro de téléphone

        Returns:
            Tuple (code, message)
        """
        import secrets
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

        twilio = await self._get_twilio()
        msg = await twilio.send_verification_code(phone, code)

        # Sauvegarder le code (hashé) en base avec expiration
        await self._save_2fa_code(user_id, code, expires_in_minutes=5)

        return code, msg

    async def send_payment_reminder(
        self,
        facture_id: UUID,
        reminder_level: int = 1
    ) -> Optional[Message]:
        """
        Envoyer une relance de paiement.

        Args:
            facture_id: ID de la facture
            reminder_level: Niveau de relance (1, 2, 3)

        Returns:
            Message ou None
        """
        facture = await self._get_facture(facture_id)
        client = await self._get_client(facture["client_id"])

        if not client.get("telephone"):
            return None

        # Messages selon le niveau
        templates = {
            1: "Rappel: Facture {numero} de {montant}€ à régler. Payez en ligne: {url}",
            2: "2ème rappel: Facture {numero} impayée ({montant}€). Merci de régulariser: {url}",
            3: "URGENT: Facture {numero} en retard ({montant}€). Dernier rappel avant procédure."
        }

        payment_url = f"https://app.azalplus.fr/p/{facture['payment_token']}"
        body = templates.get(reminder_level, templates[1]).format(
            numero=facture["numero"],
            montant=facture["montant_ttc"],
            url=payment_url
        )

        twilio = await self._get_twilio()

        try:
            msg = await twilio.send_sms(client["telephone"], body)

            await self._save_notification(
                type=f"relance_niveau_{reminder_level}",
                channel="sms",
                recipient=client["telephone"],
                message_sid=msg.sid,
                related_id=str(facture_id)
            )

            return msg

        except TwilioError as e:
            logger.error(f"Erreur relance: {e}")
            return None

    # Méthodes DB (à implémenter)
    async def _get_facture(self, facture_id: UUID) -> dict:
        pass

    async def _get_client(self, client_id: UUID) -> dict:
        pass

    async def _get_rdv(self, rdv_id: UUID) -> dict:
        pass

    async def _save_notification(self, **kwargs):
        pass

    async def _save_2fa_code(self, user_id: UUID, code: str, expires_in_minutes: int):
        pass
