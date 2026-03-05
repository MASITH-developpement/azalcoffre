# =============================================================================
# AZALPLUS - Phone Call Service (App Mobile)
# =============================================================================
"""
Service d'appels telephoniques via l'application mobile AZALPLUS.

Fonctionnement:
- Appels WebRTC via LiveKit (app-to-app ou app-to-externe)
- Utilise le telephone portable ou est installee l'app
- Enregistrement automatique
- Transcription IA (Whisper)
- Generation de compte-rendu (Claude)
- Envoi par email (config utilisateur AZALPLUS)
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================
class CallStatus(str, Enum):
    """Statuts d'appel."""
    INITIATING = "initiating"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    MISSED = "missed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CallDirection(str, Enum):
    """Direction de l'appel."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallType(str, Enum):
    """Type d'appel."""
    APP_TO_APP = "app_to_app"      # Entre 2 utilisateurs AZALPLUS (WebRTC)
    APP_TO_PHONE = "app_to_phone"  # App vers numero externe (WebRTC + SIP)
    TWILIO_PSTN = "twilio_pstn"    # Appel PSTN via Twilio (option payante)
    PHONE_TO_APP = "phone_to_app"  # Appel entrant depuis numero externe


class CallProvider(str, Enum):
    """Provider d'appel."""
    APP = "app"          # App AZALPLUS (WebRTC via LiveKit) - Gratuit
    TWILIO = "twilio"    # Twilio PSTN - Option payante


class MinutesDeliveryStatus(str, Enum):
    """Statut d'envoi du compte-rendu."""
    PENDING = "pending"
    GENERATING = "generating"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


# =============================================================================
# Phone Call Service
# =============================================================================
class PhoneCallService:
    """
    Service de gestion des appels telephoniques via l'app AZALPLUS.

    Architecture:
    - Appels WebRTC via LiveKit (meme infra que videoconf)
    - Le telephone portable sert de client (app mobile)
    - Enregistrement cote serveur (LiveKit Egress)
    - Email envoye via config utilisateur AZALPLUS

    Flux:
    1. Utilisateur initie appel depuis app mobile
    2. LiveKit cree une room audio-only
    3. Destinataire recoit notification push
    4. Conversation enregistree automatiquement
    5. Fin d'appel -> transcription + compte-rendu
    6. Email envoye a l'utilisateur
    """

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service d'appels.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant pour l'isolation
        """
        self.db = db
        self.tenant_id = tenant_id

    # =========================================================================
    # Helpers - User Info & Settings
    # =========================================================================
    def _get_user_info(self, user_id: UUID) -> Optional[dict]:
        """Recupere les informations utilisateur avec ses parametres email."""
        query = text("""
            SELECT u.id, u.email, u.nom, u.prenom, u.telephone,
                   u.telephone_verified, u.device_token,
                   -- Parametres email utilisateur (depuis parametres/utilisateur)
                   COALESCE(p.email_smtp_host, s.default_smtp_host) as smtp_host,
                   COALESCE(p.email_smtp_port, s.default_smtp_port) as smtp_port,
                   COALESCE(p.email_smtp_user, u.email) as smtp_user,
                   p.email_smtp_password as smtp_password,
                   COALESCE(p.email_from_address, u.email) as email_from,
                   COALESCE(p.email_from_name, CONCAT(u.prenom, ' ', u.nom)) as email_from_name,
                   p.email_signature as email_signature,
                   -- Preferences notifications
                   COALESCE(p.notify_call_minutes, true) as notify_call_minutes,
                   COALESCE(p.auto_send_minutes, true) as auto_send_minutes
            FROM azalplus.users u
            LEFT JOIN azalplus.user_settings p ON u.id = p.user_id AND p.tenant_id = :tenant_id
            LEFT JOIN azalplus.tenant_settings s ON s.tenant_id = :tenant_id
            WHERE u.id = :user_id
            AND u.tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "user_id": str(user_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _get_user_by_phone(self, phone_number: str) -> Optional[dict]:
        """Trouve un utilisateur par son numero de telephone."""
        # Normaliser le numero
        normalized = self._normalize_phone(phone_number)

        query = text("""
            SELECT id, email, nom, prenom, telephone, device_token
            FROM azalplus.users
            WHERE tenant_id = :tenant_id
            AND (telephone = :phone OR telephone = :normalized)
            AND telephone_verified = true
            LIMIT 1
        """)
        result = self.db.execute(query, {
            "tenant_id": str(self.tenant_id),
            "phone": phone_number,
            "normalized": normalized
        })
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _get_user_by_email(self, email: str) -> Optional[dict]:
        """Trouve un utilisateur par email."""
        query = text("""
            SELECT id, email, nom, prenom, telephone, device_token
            FROM azalplus.users
            WHERE tenant_id = :tenant_id
            AND LOWER(email) = LOWER(:email)
            LIMIT 1
        """)
        result = self.db.execute(query, {
            "tenant_id": str(self.tenant_id),
            "email": email
        })
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _normalize_phone(self, phone: str) -> str:
        """Normalise un numero de telephone."""
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        if not cleaned.startswith("+"):
            if cleaned.startswith("0"):
                cleaned = "+33" + cleaned[1:]
            else:
                cleaned = "+" + cleaned
        return cleaned

    # =========================================================================
    # Initiate Call (App ou Twilio)
    # =========================================================================
    async def initiate_call(
        self,
        caller_id: UUID,
        callee_identifier: str,
        subject: Optional[str] = None,
        provider: CallProvider = CallProvider.APP,
        auto_record: bool = True,
        auto_transcribe: bool = True,
        auto_minutes: bool = True
    ) -> Dict[str, Any]:
        """
        Initie un appel telephonique.

        Args:
            caller_id: ID de l'utilisateur qui appelle
            callee_identifier: Email, telephone ou ID utilisateur du destinataire
            subject: Sujet de l'appel (pour le compte-rendu)
            provider: Mode d'appel
                - APP: Via l'app AZALPLUS (WebRTC, gratuit)
                - TWILIO: Via Twilio PSTN (option payante)
            auto_record: Enregistrer l'appel
            auto_transcribe: Transcrire automatiquement
            auto_minutes: Generer compte-rendu

        Returns:
            Informations sur l'appel initie
        """
        if provider == CallProvider.TWILIO:
            return await self._initiate_twilio_call(
                caller_id, callee_identifier, subject,
                auto_record, auto_transcribe, auto_minutes
            )

        # Default: App AZALPLUS (WebRTC)
        return await self._initiate_app_call(
            caller_id, callee_identifier, subject,
            auto_record, auto_transcribe, auto_minutes
        )

    async def _initiate_app_call(
        self,
        caller_id: UUID,
        callee_identifier: str,
        subject: Optional[str],
        auto_record: bool,
        auto_transcribe: bool,
        auto_minutes: bool
    ) -> Dict[str, Any]:
        """Initie un appel via l'app AZALPLUS (WebRTC/LiveKit)."""
        caller = self._get_user_info(caller_id)
        if not caller:
            raise ValueError(f"Utilisateur {caller_id} non trouve")

        # Trouver le destinataire
        if "@" in callee_identifier:
            callee = self._get_user_by_email(callee_identifier)
        else:
            callee = self._get_user_by_phone(callee_identifier)

        if not callee:
            raise ValueError(f"Destinataire non trouve: {callee_identifier}")

        # Creer l'appel en base
        call_id = uuid4()
        room_name = f"phone_{self.tenant_id}_{call_id}"
        now = datetime.utcnow()

        insert_query = text("""
            INSERT INTO azalplus.phone_calls
            (id, tenant_id, user_id, callee_id, call_type, direction, status,
             from_number, to_number, to_email, subject, room_name,
             auto_record, auto_transcribe, auto_minutes,
             initiated_at, created_at)
            VALUES (:id, :tenant_id, :user_id, :callee_id, :call_type, :direction, :status,
                    :from_number, :to_number, :to_email, :subject, :room_name,
                    :auto_record, :auto_transcribe, :auto_minutes,
                    :initiated_at, :created_at)
            RETURNING *
        """)

        result = self.db.execute(insert_query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "user_id": str(caller_id),
            "callee_id": str(callee["id"]),
            "call_type": CallType.APP_TO_APP.value,
            "direction": CallDirection.OUTBOUND.value,
            "status": CallStatus.INITIATING.value,
            "from_number": caller.get("telephone"),
            "to_number": callee.get("telephone"),
            "to_email": callee.get("email"),
            "subject": subject,
            "room_name": room_name,
            "auto_record": auto_record,
            "auto_transcribe": auto_transcribe,
            "auto_minutes": auto_minutes,
            "initiated_at": now,
            "created_at": now
        })
        self.db.commit()

        call = dict(result.fetchone()._mapping)

        # Creer la room LiveKit (audio only)
        from .room_manager import LiveKitRoomManager

        room_manager = LiveKitRoomManager(self.tenant_id)

        room_options = {
            "max_participants": 2,
            "empty_timeout": 60,
            "metadata": json.dumps({
                "type": "phone_call",
                "call_id": str(call_id),
                "caller_id": str(caller_id),
                "callee_id": str(callee["id"])
            })
        }

        await room_manager.create_room(
            meeting_id=call_id,
            options=room_options
        )

        # Generer les tokens pour les 2 participants
        caller_token = await room_manager.create_participant_token(
            room_name=room_name,
            participant_id=str(caller_id),
            name=f"{caller.get('prenom', '')} {caller.get('nom', '')}".strip(),
            role="organizer"
        )

        callee_token = await room_manager.create_participant_token(
            room_name=room_name,
            participant_id=str(callee["id"]),
            name=f"{callee.get('prenom', '')} {callee.get('nom', '')}".strip(),
            role="participant"
        )

        # Demarrer l'enregistrement si active
        if auto_record:
            try:
                await room_manager.start_recording(
                    room_name=room_name,
                    options={"audio_only": True}
                )
            except Exception as e:
                logger.warning("recording_start_failed", error=str(e))

        # Envoyer notification push au destinataire
        await self._send_incoming_call_notification(callee, caller, call_id)

        # Mettre a jour le statut
        update_query = text("""
            UPDATE azalplus.phone_calls
            SET status = :status
            WHERE id = :id AND tenant_id = :tenant_id
        """)
        self.db.execute(update_query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "status": CallStatus.RINGING.value
        })
        self.db.commit()

        logger.info(
            "call_initiated",
            call_id=str(call_id),
            caller_id=str(caller_id),
            callee_id=str(callee["id"]),
            room_name=room_name
        )

        return {
            **call,
            "status": CallStatus.RINGING.value,
            "room_name": room_name,
            "caller_token": caller_token,
            "callee_token": callee_token,
            "callee_info": {
                "id": str(callee["id"]),
                "nom": callee.get("nom"),
                "prenom": callee.get("prenom"),
                "email": callee.get("email")
            }
        }

    async def _send_incoming_call_notification(
        self,
        callee: dict,
        caller: dict,
        call_id: UUID
    ) -> None:
        """Envoie une notification push d'appel entrant."""
        device_token = callee.get("device_token")
        if not device_token:
            logger.warning("no_device_token", callee_id=str(callee["id"]))
            return

        caller_name = f"{caller.get('prenom', '')} {caller.get('nom', '')}".strip()

        # TODO: Integrer avec Firebase Cloud Messaging ou APNs
        # Pour l'instant, log seulement
        logger.info(
            "incoming_call_notification",
            callee_id=str(callee["id"]),
            caller_name=caller_name,
            call_id=str(call_id),
            device_token=device_token[:20] + "..."
        )

        # Structure de la notification push:
        # {
        #     "notification": {
        #         "title": "Appel entrant",
        #         "body": f"{caller_name} vous appelle"
        #     },
        #     "data": {
        #         "type": "incoming_call",
        #         "call_id": str(call_id),
        #         "caller_name": caller_name,
        #         "caller_id": str(caller["id"])
        #     },
        #     "android": {
        #         "priority": "high",
        #         "notification": {"channel_id": "calls"}
        #     },
        #     "apns": {
        #         "payload": {"aps": {"sound": "ringtone.caf"}}
        #     }
        # }

    # =========================================================================
    # Twilio PSTN Call (Option payante)
    # =========================================================================
    async def _initiate_twilio_call(
        self,
        caller_id: UUID,
        to_number: str,
        subject: Optional[str],
        auto_record: bool,
        auto_transcribe: bool,
        auto_minutes: bool
    ) -> Dict[str, Any]:
        """
        Initie un appel PSTN via Twilio (option payante).

        Permet d'appeler n'importe quel numero de telephone,
        pas uniquement les utilisateurs AZALPLUS.
        """
        caller = self._get_user_info(caller_id)
        if not caller:
            raise ValueError(f"Utilisateur {caller_id} non trouve")

        # Verifier la config Twilio
        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_number = os.environ.get("TWILIO_PHONE_NUMBER")

        if not all([twilio_sid, twilio_token, twilio_number]):
            raise ValueError("Option Twilio non configuree. Utilisez l'appel via app.")

        # Normaliser le numero
        formatted_number = self._normalize_phone(to_number)

        # Creer l'appel en base
        call_id = uuid4()
        now = datetime.utcnow()

        insert_query = text("""
            INSERT INTO azalplus.phone_calls
            (id, tenant_id, user_id, call_type, call_provider, direction, status,
             from_number, to_number, subject,
             auto_record, auto_transcribe, auto_minutes,
             initiated_at, created_at)
            VALUES (:id, :tenant_id, :user_id, :call_type, :call_provider, :direction, :status,
                    :from_number, :to_number, :subject,
                    :auto_record, :auto_transcribe, :auto_minutes,
                    :initiated_at, :created_at)
            RETURNING *
        """)

        result = self.db.execute(insert_query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "user_id": str(caller_id),
            "call_type": CallType.TWILIO_PSTN.value,
            "call_provider": CallProvider.TWILIO.value,
            "direction": CallDirection.OUTBOUND.value,
            "status": CallStatus.INITIATING.value,
            "from_number": twilio_number,
            "to_number": formatted_number,
            "subject": subject,
            "auto_record": auto_record,
            "auto_transcribe": auto_transcribe,
            "auto_minutes": auto_minutes,
            "initiated_at": now,
            "created_at": now
        })
        self.db.commit()

        call = dict(result.fetchone()._mapping)

        # Initier l'appel Twilio
        try:
            from twilio.rest import Client

            client = Client(twilio_sid, twilio_token)

            callback_url = os.environ.get(
                "TWILIO_CALLBACK_URL",
                "https://api.azalplus.com/api/phone"
            )

            twilio_call = client.calls.create(
                to=formatted_number,
                from_=twilio_number,
                url=f"{callback_url}/twilio-webhook/twiml/{call_id}",
                status_callback=f"{callback_url}/twilio-webhook/status/{call_id}",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                record=auto_record,
                recording_status_callback=f"{callback_url}/twilio-webhook/recording/{call_id}"
            )

            # Mettre a jour avec le SID Twilio
            update_query = text("""
                UPDATE azalplus.phone_calls
                SET external_call_id = :sid, status = :status
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            self.db.execute(update_query, {
                "id": str(call_id),
                "tenant_id": str(self.tenant_id),
                "sid": twilio_call.sid,
                "status": CallStatus.RINGING.value
            })
            self.db.commit()

            call["external_call_id"] = twilio_call.sid
            call["status"] = CallStatus.RINGING.value

            logger.info(
                "twilio_call_initiated",
                call_id=str(call_id),
                twilio_sid=twilio_call.sid,
                to_number=formatted_number
            )

        except ImportError:
            logger.error("twilio_sdk_not_installed")
            raise ValueError("SDK Twilio non installe")
        except Exception as e:
            logger.error("twilio_call_error", error=str(e))
            raise ValueError(f"Erreur Twilio: {str(e)}")

        return call

    # =========================================================================
    # Answer / Decline Call
    # =========================================================================
    async def answer_call(
        self,
        call_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Repond a un appel entrant.

        Args:
            call_id: ID de l'appel
            user_id: ID de l'utilisateur qui repond

        Returns:
            Informations de l'appel avec token LiveKit
        """
        call = await self.get_call(call_id)

        # Verifier que c'est bien le destinataire
        if str(call.get("callee_id")) != str(user_id):
            raise ValueError("Cet appel n'est pas pour vous")

        if call["status"] != CallStatus.RINGING.value:
            raise ValueError(f"Appel non en attente: {call['status']}")

        now = datetime.utcnow()

        update_query = text("""
            UPDATE azalplus.phone_calls
            SET status = :status, answered_at = :answered_at
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "status": CallStatus.IN_PROGRESS.value,
            "answered_at": now
        })
        self.db.commit()

        updated_call = dict(result.fetchone()._mapping)

        # Generer le token pour rejoindre
        from .room_manager import LiveKitRoomManager

        user = self._get_user_info(user_id)
        room_manager = LiveKitRoomManager(self.tenant_id)

        token = await room_manager.create_participant_token(
            room_name=call["room_name"],
            participant_id=str(user_id),
            name=f"{user.get('prenom', '')} {user.get('nom', '')}".strip() if user else "Participant",
            role="participant"
        )

        logger.info("call_answered", call_id=str(call_id), user_id=str(user_id))

        return {
            **updated_call,
            "token": token
        }

    async def decline_call(
        self,
        call_id: UUID,
        user_id: UUID,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Decline un appel entrant."""
        call = await self.get_call(call_id)

        if str(call.get("callee_id")) != str(user_id):
            raise ValueError("Cet appel n'est pas pour vous")

        update_query = text("""
            UPDATE azalplus.phone_calls
            SET status = :status, ended_at = :ended_at, decline_reason = :reason
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "status": CallStatus.MISSED.value,
            "ended_at": datetime.utcnow(),
            "reason": reason
        })
        self.db.commit()

        # Supprimer la room LiveKit
        from .room_manager import LiveKitRoomManager
        room_manager = LiveKitRoomManager(self.tenant_id)
        try:
            await room_manager.delete_room(call["room_name"])
        except Exception:
            pass

        logger.info("call_declined", call_id=str(call_id), user_id=str(user_id))

        return dict(result.fetchone()._mapping)

    # =========================================================================
    # End Call
    # =========================================================================
    async def end_call(
        self,
        call_id: UUID,
        ended_by: UUID
    ) -> Dict[str, Any]:
        """
        Termine un appel en cours.

        Declenche automatiquement:
        - Arret enregistrement
        - Transcription
        - Generation compte-rendu
        - Envoi email
        """
        call = await self.get_call(call_id)

        if call["status"] not in [
            CallStatus.RINGING.value,
            CallStatus.IN_PROGRESS.value,
            CallStatus.ON_HOLD.value
        ]:
            raise ValueError(f"Appel non en cours: {call['status']}")

        now = datetime.utcnow()

        # Calculer la duree
        duration = None
        if call.get("answered_at"):
            answered = call["answered_at"]
            if isinstance(answered, str):
                answered = datetime.fromisoformat(answered)
            duration = int((now - answered).total_seconds())

        # Mettre a jour
        update_query = text("""
            UPDATE azalplus.phone_calls
            SET status = :status, ended_at = :ended_at, ended_by = :ended_by,
                duration_seconds = :duration
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "status": CallStatus.COMPLETED.value,
            "ended_at": now,
            "ended_by": str(ended_by),
            "duration": duration
        })
        self.db.commit()

        updated_call = dict(result.fetchone()._mapping)

        # Arreter l'enregistrement et fermer la room
        from .room_manager import LiveKitRoomManager
        room_manager = LiveKitRoomManager(self.tenant_id)

        recording_info = None
        try:
            # Recuperer l'URL d'enregistrement
            recording_info = await room_manager.stop_recording(call["room_name"])
            await room_manager.delete_room(call["room_name"])
        except Exception as e:
            logger.warning("room_cleanup_failed", error=str(e))

        logger.info(
            "call_ended",
            call_id=str(call_id),
            duration_seconds=duration,
            ended_by=str(ended_by)
        )

        # Declencher le traitement automatique
        if call.get("auto_transcribe") or call.get("auto_minutes"):
            asyncio.create_task(self._process_call_recording(
                updated_call,
                recording_info
            ))

        return updated_call

    # =========================================================================
    # Processing Pipeline
    # =========================================================================
    async def _process_call_recording(
        self,
        call: dict,
        recording_info: Optional[dict] = None
    ) -> None:
        """
        Pipeline de traitement post-appel:
        1. Telecharge l'enregistrement
        2. Transcrit avec Whisper
        3. Genere le compte-rendu avec Claude
        4. Envoie par email (config utilisateur)
        """
        call_id = call["id"]

        try:
            # Attendre que l'enregistrement soit disponible
            await asyncio.sleep(30)

            self._update_minutes_status(call_id, MinutesDeliveryStatus.GENERATING)

            # 1. Recuperer l'enregistrement
            recording_path = await self._get_recording_file(call, recording_info)

            if not recording_path:
                logger.warning("no_recording_available", call_id=str(call_id))
                self._update_minutes_status(call_id, MinutesDeliveryStatus.FAILED)
                return

            # 2. Transcrire
            transcription = None
            if call.get("auto_transcribe"):
                from .transcription import TranscriptionService

                trans_service = TranscriptionService(self.db, self.tenant_id)
                result = await trans_service.transcribe_audio(
                    audio_path=recording_path,
                    meeting_id=UUID(str(call_id)),
                    language="fr"
                )
                transcription = result.get("text", "")

                # Sauvegarder
                self._save_transcription(call_id, transcription)

            # 3. Generer le compte-rendu
            minutes_content = None
            if call.get("auto_minutes") and transcription:
                minutes_content = await self._generate_call_minutes(call, transcription)
                self._save_minutes(call_id, minutes_content)

            # 4. Envoyer par email (config utilisateur)
            user = self._get_user_info(UUID(str(call["user_id"])))

            if user and user.get("auto_send_minutes") and minutes_content:
                self._update_minutes_status(call_id, MinutesDeliveryStatus.SENDING)
                success = await self._send_minutes_email_user_config(
                    user, call, minutes_content
                )
                if success:
                    self._update_minutes_status(call_id, MinutesDeliveryStatus.SENT)
                else:
                    self._update_minutes_status(call_id, MinutesDeliveryStatus.FAILED)
            else:
                self._update_minutes_status(call_id, MinutesDeliveryStatus.PENDING)

            logger.info(
                "call_processing_completed",
                call_id=str(call_id),
                transcription_length=len(transcription) if transcription else 0,
                minutes_length=len(minutes_content) if minutes_content else 0
            )

        except Exception as e:
            logger.error("call_processing_error", call_id=str(call_id), error=str(e))
            self._update_minutes_status(call_id, MinutesDeliveryStatus.FAILED)

    async def _get_recording_file(
        self,
        call: dict,
        recording_info: Optional[dict]
    ) -> Optional[str]:
        """Recupere le fichier d'enregistrement."""
        # Chemin local pour les enregistrements
        recordings_dir = "/home/ubuntu/azalplus/uploads/phone_recordings"
        os.makedirs(recordings_dir, exist_ok=True)

        call_id = call["id"]
        local_path = os.path.join(recordings_dir, f"{call_id}.wav")

        # Si recording_info contient l'URL, telecharger
        if recording_info and recording_info.get("url"):
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(recording_info["url"])
                    if response.status_code == 200:
                        with open(local_path, "wb") as f:
                            f.write(response.content)
                        return local_path
            except Exception as e:
                logger.error("recording_download_error", error=str(e))

        # Verifier si fichier existe deja (enregistrement local)
        if os.path.exists(local_path):
            return local_path

        return None

    def _save_transcription(self, call_id: str, transcription: str) -> None:
        """Sauvegarde la transcription."""
        query = text("""
            UPDATE azalplus.phone_calls
            SET transcription = :transcription
            WHERE id = :id AND tenant_id = :tenant_id
        """)
        self.db.execute(query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "transcription": transcription
        })
        self.db.commit()

    def _save_minutes(self, call_id: str, minutes: str) -> None:
        """Sauvegarde le compte-rendu."""
        query = text("""
            UPDATE azalplus.phone_calls
            SET minutes_content = :minutes
            WHERE id = :id AND tenant_id = :tenant_id
        """)
        self.db.execute(query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "minutes": minutes
        })
        self.db.commit()

    def _update_minutes_status(self, call_id: str, status: MinutesDeliveryStatus) -> None:
        """Met a jour le statut d'envoi."""
        query = text("""
            UPDATE azalplus.phone_calls
            SET minutes_status = :status
            WHERE id = :id AND tenant_id = :tenant_id
        """)
        self.db.execute(query, {
            "id": str(call_id),
            "tenant_id": str(self.tenant_id),
            "status": status.value
        })
        self.db.commit()

    async def _generate_call_minutes(
        self,
        call: dict,
        transcription: str
    ) -> str:
        """Genere le compte-rendu avec Claude."""
        caller = self._get_user_info(UUID(str(call["user_id"])))
        caller_name = f"{caller.get('prenom', '')} {caller.get('nom', '')}".strip() if caller else "Appelant"

        # Recuperer info destinataire
        callee_name = "Destinataire"
        if call.get("callee_id"):
            callee = self._get_user_info(UUID(str(call["callee_id"])))
            if callee:
                callee_name = f"{callee.get('prenom', '')} {callee.get('nom', '')}".strip()

        system_prompt = """Tu es un assistant expert en redaction de comptes-rendus d'appels telephoniques.
A partir de la transcription fournie, genere un compte-rendu structure et concis:

1. RESUME (2-3 phrases)
2. POINTS CLES (liste des sujets abordes)
3. DECISIONS/ENGAGEMENTS (si mentionnes)
4. ACTIONS A SUIVRE (si mentionnees)

Garde un ton professionnel et factuel. Sois concis."""

        # Formater la date
        call_date = call.get("initiated_at")
        if isinstance(call_date, datetime):
            date_str = call_date.strftime("%d/%m/%Y a %H:%M")
        else:
            date_str = str(call_date) if call_date else "Non specifie"

        user_prompt = f"""# Appel telephonique
- Date: {date_str}
- De: {caller_name}
- A: {callee_name}
- Sujet: {call.get('subject', 'Non specifie')}
- Duree: {call.get('duration_seconds', 0)} secondes

## Transcription:
{transcription}
"""

        try:
            import anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                return f"# Compte-rendu\n\n{transcription}"

            client = anthropic.Anthropic(api_key=api_key)

            message = client.messages.create(
                model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                max_tokens=2000,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            return message.content[0].text

        except Exception as e:
            logger.error("minutes_generation_error", error=str(e))
            return f"# Compte-rendu\n\n{transcription}"

    # =========================================================================
    # Send Email (User Config)
    # =========================================================================
    async def _send_minutes_email_user_config(
        self,
        user: dict,
        call: dict,
        minutes_content: str
    ) -> bool:
        """
        Envoie le compte-rendu par email en utilisant
        les parametres SMTP configures par l'utilisateur.
        """
        # Recuperer la config email de l'utilisateur
        smtp_host = user.get("smtp_host")
        smtp_port = user.get("smtp_port", 587)
        smtp_user = user.get("smtp_user")
        smtp_password = user.get("smtp_password")
        email_from = user.get("email_from") or user.get("email")
        email_from_name = user.get("email_from_name") or f"{user.get('prenom', '')} {user.get('nom', '')}"
        signature = user.get("email_signature", "")

        if not smtp_host or not smtp_user:
            # Fallback: utiliser config systeme si dispo
            smtp_host = os.environ.get("SMTP_HOST")
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            smtp_user = os.environ.get("SMTP_USER")
            smtp_password = os.environ.get("SMTP_PASSWORD")

            if not smtp_host:
                logger.warning("no_email_config", user_id=str(user["id"]))
                return False

        # Formater la date
        call_date = call.get("initiated_at")
        if isinstance(call_date, datetime):
            date_str = call_date.strftime("%d/%m/%Y a %H:%M")
        else:
            date_str = str(call_date) if call_date else "Non specifie"

        subject = f"Compte-rendu de votre appel du {date_str}"

        # Corps de l'email
        email_body = f"""Bonjour,

Voici le compte-rendu automatique de votre appel telephonique du {date_str}.

---

{minutes_content}

---

{signature}

---
Cet email a ete genere automatiquement par AZALPLUS.
"""

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.utils import formataddr

            msg = MIMEMultipart()
            msg["From"] = formataddr((email_from_name, email_from))
            msg["To"] = user["email"]
            msg["Subject"] = subject

            msg.attach(MIMEText(email_body, "plain", "utf-8"))

            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls()
                if smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)

            # Enregistrer l'envoi
            query = text("""
                UPDATE azalplus.phone_calls
                SET minutes_sent_at = :sent_at, minutes_sent_to = :sent_to
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            self.db.execute(query, {
                "id": str(call["id"]),
                "tenant_id": str(self.tenant_id),
                "sent_at": datetime.utcnow(),
                "sent_to": user["email"]
            })
            self.db.commit()

            logger.info(
                "minutes_email_sent",
                call_id=str(call["id"]),
                to_email=user["email"],
                smtp_host=smtp_host
            )

            return True

        except Exception as e:
            logger.error("email_send_error", error=str(e))
            return False

    # =========================================================================
    # CRUD Operations
    # =========================================================================
    async def get_call(self, call_id: UUID) -> Dict[str, Any]:
        """Recupere un appel par ID."""
        query = text("""
            SELECT c.*,
                   caller.nom as caller_nom, caller.prenom as caller_prenom,
                   callee.nom as callee_nom, callee.prenom as callee_prenom
            FROM azalplus.phone_calls c
            LEFT JOIN azalplus.users caller ON c.user_id = caller.id
            LEFT JOIN azalplus.users callee ON c.callee_id = callee.id
            WHERE c.id = :call_id
            AND c.tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "call_id": str(call_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            raise ValueError(f"Appel {call_id} non trouve")

        return dict(row._mapping)

    async def list_calls(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[CallStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Liste les appels."""
        sql = """
            SELECT c.*,
                   caller.nom as caller_nom, caller.prenom as caller_prenom,
                   callee.nom as callee_nom, callee.prenom as callee_prenom
            FROM azalplus.phone_calls c
            LEFT JOIN azalplus.users caller ON c.user_id = caller.id
            LEFT JOIN azalplus.users callee ON c.callee_id = callee.id
            WHERE c.tenant_id = :tenant_id
        """
        params = {"tenant_id": str(self.tenant_id)}

        if user_id:
            sql += " AND (c.user_id = :user_id OR c.callee_id = :user_id)"
            params["user_id"] = str(user_id)

        if status:
            sql += " AND c.status = :status"
            params["status"] = status.value

        sql += " ORDER BY c.created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = self.db.execute(text(sql), params)
        return [dict(r._mapping) for r in result]

    async def get_incoming_calls(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Recupere les appels entrants en attente."""
        query = text("""
            SELECT c.*, u.nom as caller_nom, u.prenom as caller_prenom
            FROM azalplus.phone_calls c
            JOIN azalplus.users u ON c.user_id = u.id
            WHERE c.tenant_id = :tenant_id
            AND c.callee_id = :user_id
            AND c.status = :status
            ORDER BY c.created_at DESC
        """)
        result = self.db.execute(query, {
            "tenant_id": str(self.tenant_id),
            "user_id": str(user_id),
            "status": CallStatus.RINGING.value
        })
        return [dict(r._mapping) for r in result]

    # =========================================================================
    # Resend / Regenerate
    # =========================================================================
    async def resend_minutes(
        self,
        call_id: UUID,
        user_id: UUID,
        to_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """Renvoie le compte-rendu par email."""
        call = await self.get_call(call_id)

        if not call.get("minutes_content"):
            raise ValueError("Aucun compte-rendu disponible")

        user = self._get_user_info(user_id)
        if not user:
            raise ValueError("Utilisateur non trouve")

        # Utiliser email alternatif si fourni
        if to_email:
            user["email"] = to_email

        success = await self._send_minutes_email_user_config(
            user, call, call["minutes_content"]
        )

        return {
            "success": success,
            "call_id": str(call_id),
            "sent_to": user["email"]
        }

    async def regenerate_minutes(
        self,
        call_id: UUID
    ) -> Dict[str, Any]:
        """Regenere le compte-rendu."""
        call = await self.get_call(call_id)

        if not call.get("transcription"):
            raise ValueError("Aucune transcription disponible")

        minutes = await self._generate_call_minutes(call, call["transcription"])
        self._save_minutes(call_id, minutes)

        return {
            "call_id": str(call_id),
            "minutes": minutes,
            "status": MinutesDeliveryStatus.PENDING.value
        }
