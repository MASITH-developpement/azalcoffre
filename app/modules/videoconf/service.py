# =============================================================================
# AZALPLUS - Service Videoconference
# =============================================================================
"""
Service principal de videoconference pour AZALPLUS.

Gere la creation, gestion et participation aux reunions video.
Integration avec LiveKit pour le WebRTC.

Pattern AZALPLUS:
- tenant_id obligatoire sur chaque methode
- Utilisation de Database.query() avec isolation tenant
- Docstrings en francais
"""

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from moteur.db import Database

from .schemas import (
    # Meeting
    MeetingCreate,
    MeetingUpdate,
    MeetingResponse,
    MeetingListResponse,
    MeetingStatus,
    MeetingType,
    # Participants
    ParticipantCreate,
    ParticipantResponse,
    ParticipantRole,
    ParticipantStatus,
    # Join
    JoinMeetingRequest,
    JoinMeetingResponse,
    # Recording
    RecordingStartRequest,
    RecordingResponse,
    RecordingStatus,
    # Transcription
    TranscriptionResponse,
    TranscriptionSegment,
    # Minutes
    MinutesGenerateRequest,
    MinutesResponse,
    # Chat
    ChatMessageCreate,
    ChatMessageResponse,
)

logger = logging.getLogger(__name__)

# Constantes
TABLE_MEETINGS = "videoconf_meetings"
TABLE_PARTICIPANTS = "videoconf_participants"
TABLE_RECORDINGS = "videoconf_recordings"
TABLE_TRANSCRIPTIONS = "videoconf_transcriptions"
TABLE_CHAT_MESSAGES = "videoconf_chat_messages"
TABLE_MINUTES = "videoconf_minutes"


class VideoconfService:
    """
    Service principal de videoconference.

    Pattern AZALPLUS standard avec tenant_id obligatoire.
    Toutes les methodes filtrent par tenant_id pour l'isolation multi-tenant.
    """

    def __init__(self, db: Session, tenant_id: UUID, user_id: Optional[UUID] = None):
        """
        Initialise le service de videoconference.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant (OBLIGATOIRE pour isolation)
            user_id: ID de l'utilisateur courant (optionnel)
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._livekit_config: Optional[dict] = None

    # =========================================================================
    # Configuration LiveKit
    # =========================================================================
    def _get_livekit_config(self) -> dict:
        """
        Recupere la configuration LiveKit.

        Returns:
            Configuration LiveKit avec URL, API key et secret
        """
        if self._livekit_config is None:
            try:
                from moteur.config import settings
                self._livekit_config = {
                    "url": getattr(settings, "LIVEKIT_URL", "wss://localhost:7880"),
                    "api_key": getattr(settings, "LIVEKIT_API_KEY", ""),
                    "api_secret": getattr(settings, "LIVEKIT_API_SECRET", ""),
                }
            except ImportError:
                import os
                self._livekit_config = {
                    "url": os.environ.get("LIVEKIT_URL", "wss://localhost:7880"),
                    "api_key": os.environ.get("LIVEKIT_API_KEY", ""),
                    "api_secret": os.environ.get("LIVEKIT_API_SECRET", ""),
                }
        return self._livekit_config

    def _generate_livekit_token(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: str,
        is_host: bool = False,
        ttl_hours: int = 24
    ) -> str:
        """
        Genere un token JWT pour LiveKit.

        Args:
            room_name: Nom de la room LiveKit
            participant_identity: Identite unique du participant
            participant_name: Nom affiche du participant
            is_host: True si le participant est organisateur
            ttl_hours: Duree de validite du token en heures

        Returns:
            Token JWT pour LiveKit
        """
        config = self._get_livekit_config()

        # TODO: Implementer la generation de token LiveKit
        # Pour l'instant, retourne un placeholder
        # En production, utiliser livekit-server-sdk-python

        # Exemple de structure du token:
        # - video grants (canPublish, canSubscribe, canPublishData)
        # - room permission (roomJoin, roomCreate pour host)
        # - metadata (nom, role, tenant_id)

        token_data = {
            "room": room_name,
            "identity": participant_identity,
            "name": participant_name,
            "is_host": is_host,
            "tenant_id": str(self.tenant_id),
            "exp": int(time.time()) + (ttl_hours * 3600),
        }

        # Placeholder - a remplacer par vraie generation JWT
        token_placeholder = f"livekit_token_{secrets.token_urlsafe(32)}"

        logger.debug(
            "livekit_token_generated",
            room=room_name,
            participant=participant_identity,
            is_host=is_host
        )

        return token_placeholder

    # =========================================================================
    # Utilitaires
    # =========================================================================
    def _generate_meeting_code(self) -> str:
        """
        Genere un code de reunion unique (format: ABC-1234-XYZ).

        Returns:
            Code de reunion de 12 caracteres
        """
        # Format: XXX-1234-XXX (lettres majuscules et chiffres)
        import random
        import string

        part1 = ''.join(random.choices(string.ascii_uppercase, k=3))
        part2 = ''.join(random.choices(string.digits, k=4))
        part3 = ''.join(random.choices(string.ascii_uppercase, k=3))

        return f"{part1}-{part2}-{part3}"

    def _generate_room_name(self, meeting_id: UUID) -> str:
        """
        Genere le nom de room LiveKit a partir de l'ID de reunion.

        Args:
            meeting_id: ID de la reunion

        Returns:
            Nom de room unique pour LiveKit
        """
        # Format: tenant_meeting_uuid
        return f"{self.tenant_id}_{meeting_id}".replace("-", "")[:32]

    def _hash_password(self, password: str) -> str:
        """
        Hash le mot de passe de reunion.

        Args:
            password: Mot de passe en clair

        Returns:
            Hash du mot de passe
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, hashed: str) -> bool:
        """
        Verifie le mot de passe de reunion.

        Args:
            password: Mot de passe a verifier
            hashed: Hash stocke

        Returns:
            True si le mot de passe est correct
        """
        return self._hash_password(password) == hashed

    # =========================================================================
    # Gestion des reunions
    # =========================================================================
    async def create_meeting(
        self,
        data: MeetingCreate,
        organisateur_id: UUID,
        organisateur_nom: str
    ) -> MeetingResponse:
        """
        Cree une nouvelle reunion.

        Args:
            data: Donnees de creation de la reunion
            organisateur_id: ID de l'organisateur
            organisateur_nom: Nom de l'organisateur

        Returns:
            Reunion creee
        """
        meeting_id = uuid4()
        code_reunion = self._generate_meeting_code()
        room_name = self._generate_room_name(meeting_id)

        # Construire les donnees de la reunion
        meeting_data = {
            "id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "titre": data.titre,
            "description": data.description,
            "type_reunion": data.type_reunion.value,
            "statut": MeetingStatus.SCHEDULED.value if data.date_debut else MeetingStatus.WAITING.value,
            "date_debut": data.date_debut.isoformat() if data.date_debut else None,
            "duree_minutes": data.duree_minutes,
            "salle_attente_active": data.salle_attente_active,
            "participants_muets_entree": data.participants_muets_entree,
            "enregistrement_auto": data.enregistrement_auto,
            "transcription_active": data.transcription_active,
            "chat_actif": data.chat_actif,
            "tableau_blanc_actif": data.tableau_blanc_actif,
            "max_participants": data.max_participants,
            "code_reunion": code_reunion,
            "room_name": room_name,
            "mot_de_passe_hash": self._hash_password(data.mot_de_passe) if data.mot_de_passe else None,
            "organisateur_id": str(organisateur_id),
            "organisateur_nom": organisateur_nom,
            "projet_id": str(data.projet_id) if data.projet_id else None,
            "client_id": str(data.client_id) if data.client_id else None,
            "nombre_participants": 0,
            "nombre_participants_max_atteint": 0,
            "created_by": str(organisateur_id),
        }

        # Inserer en base
        result = Database.insert(TABLE_MEETINGS, self.tenant_id, meeting_data, organisateur_id)

        logger.info(
            "meeting_created",
            meeting_id=meeting_id,
            tenant_id=self.tenant_id,
            code=code_reunion,
            type=data.type_reunion.value
        )

        # Ajouter l'organisateur comme participant HOST
        await self._add_host_participant(
            meeting_id=meeting_id,
            user_id=organisateur_id,
            nom=organisateur_nom,
            email=""  # A recuperer depuis l'utilisateur
        )

        return self._map_to_meeting_response(result)

    async def update_meeting(
        self,
        meeting_id: UUID,
        data: MeetingUpdate
    ) -> Optional[MeetingResponse]:
        """
        Met a jour une reunion.

        Args:
            meeting_id: ID de la reunion
            data: Donnees de mise a jour

        Returns:
            Reunion mise a jour ou None si non trouvee
        """
        # Verifier que la reunion existe et appartient au tenant
        existing = Database.get_by_id(TABLE_MEETINGS, self.tenant_id, meeting_id)
        if not existing:
            logger.warning(
                "meeting_not_found",
                meeting_id=meeting_id,
                tenant_id=self.tenant_id
            )
            return None

        # Construire les donnees de mise a jour (exclure les None)
        update_data = {}

        if data.titre is not None:
            update_data["titre"] = data.titre
        if data.description is not None:
            update_data["description"] = data.description
        if data.date_debut is not None:
            update_data["date_debut"] = data.date_debut.isoformat()
        if data.duree_minutes is not None:
            update_data["duree_minutes"] = data.duree_minutes
        if data.salle_attente_active is not None:
            update_data["salle_attente_active"] = data.salle_attente_active
        if data.participants_muets_entree is not None:
            update_data["participants_muets_entree"] = data.participants_muets_entree
        if data.enregistrement_auto is not None:
            update_data["enregistrement_auto"] = data.enregistrement_auto
        if data.transcription_active is not None:
            update_data["transcription_active"] = data.transcription_active
        if data.chat_actif is not None:
            update_data["chat_actif"] = data.chat_actif
        if data.tableau_blanc_actif is not None:
            update_data["tableau_blanc_actif"] = data.tableau_blanc_actif
        if data.max_participants is not None:
            update_data["max_participants"] = data.max_participants
        if data.mot_de_passe is not None:
            update_data["mot_de_passe_hash"] = self._hash_password(data.mot_de_passe)

        if not update_data:
            # Aucune modification
            return self._map_to_meeting_response(existing)

        result = Database.update(
            TABLE_MEETINGS,
            self.tenant_id,
            meeting_id,
            update_data,
            self.user_id
        )

        logger.info(
            "meeting_updated",
            meeting_id=meeting_id,
            tenant_id=self.tenant_id,
            fields=list(update_data.keys())
        )

        return self._map_to_meeting_response(result) if result else None

    async def get_meeting(self, meeting_id: UUID) -> Optional[MeetingResponse]:
        """
        Recupere une reunion par son ID.

        Args:
            meeting_id: ID de la reunion

        Returns:
            Reunion ou None si non trouvee
        """
        result = Database.get_by_id(TABLE_MEETINGS, self.tenant_id, meeting_id)

        if not result:
            return None

        return self._map_to_meeting_response(result)

    async def get_meeting_by_code(self, code_reunion: str) -> Optional[MeetingResponse]:
        """
        Recupere une reunion par son code.

        Args:
            code_reunion: Code de la reunion (format XXX-1234-XXX)

        Returns:
            Reunion ou None si non trouvee
        """
        results = Database.query(
            TABLE_MEETINGS,
            self.tenant_id,
            filters={"code_reunion": code_reunion},
            limit=1
        )

        if not results:
            return None

        return self._map_to_meeting_response(results[0])

    async def list_meetings(
        self,
        statut: Optional[MeetingStatus] = None,
        type_reunion: Optional[MeetingType] = None,
        date_debut_min: Optional[datetime] = None,
        date_debut_max: Optional[datetime] = None,
        organisateur_id: Optional[UUID] = None,
        projet_id: Optional[UUID] = None,
        client_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 20
    ) -> MeetingListResponse:
        """
        Liste les reunions avec filtres et pagination.

        Args:
            statut: Filtre par statut
            type_reunion: Filtre par type
            date_debut_min: Date de debut minimale
            date_debut_max: Date de debut maximale
            organisateur_id: Filtre par organisateur
            projet_id: Filtre par projet
            client_id: Filtre par client
            page: Numero de page
            page_size: Taille de page

        Returns:
            Liste paginee des reunions
        """
        filters = {}

        if statut:
            filters["statut"] = statut.value
        if type_reunion:
            filters["type_reunion"] = type_reunion.value
        if organisateur_id:
            filters["organisateur_id"] = str(organisateur_id)
        if projet_id:
            filters["projet_id"] = str(projet_id)
        if client_id:
            filters["client_id"] = str(client_id)

        # Pagination
        offset = (page - 1) * page_size

        # Compter le total
        total = Database.count(TABLE_MEETINGS, self.tenant_id, filters)

        # Recuperer les resultats
        results = Database.query(
            TABLE_MEETINGS,
            self.tenant_id,
            filters=filters,
            order_by="date_debut DESC, created_at DESC",
            limit=page_size,
            offset=offset
        )

        # Mapper les resultats
        items = [self._map_to_meeting_response(r) for r in results]

        # Calculer le nombre de pages
        pages = (total + page_size - 1) // page_size if total > 0 else 1

        return MeetingListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages
        )

    async def start_meeting(self, meeting_id: UUID) -> Optional[MeetingResponse]:
        """
        Demarre une reunion (change le statut a IN_PROGRESS).

        Args:
            meeting_id: ID de la reunion

        Returns:
            Reunion mise a jour ou None si non trouvee
        """
        existing = Database.get_by_id(TABLE_MEETINGS, self.tenant_id, meeting_id)
        if not existing:
            return None

        # Verifier le statut actuel
        current_status = existing.get("statut")
        if current_status == MeetingStatus.IN_PROGRESS.value:
            # Deja en cours
            return self._map_to_meeting_response(existing)

        if current_status in [MeetingStatus.ENDED.value, MeetingStatus.CANCELLED.value]:
            logger.warning(
                "cannot_start_meeting",
                meeting_id=meeting_id,
                current_status=current_status
            )
            return None

        update_data = {
            "statut": MeetingStatus.IN_PROGRESS.value,
            "date_debut_effective": datetime.utcnow().isoformat(),
        }

        result = Database.update(
            TABLE_MEETINGS,
            self.tenant_id,
            meeting_id,
            update_data,
            self.user_id
        )

        logger.info(
            "meeting_started",
            meeting_id=meeting_id,
            tenant_id=self.tenant_id
        )

        return self._map_to_meeting_response(result) if result else None

    async def end_meeting(self, meeting_id: UUID) -> Optional[MeetingResponse]:
        """
        Termine une reunion.

        Args:
            meeting_id: ID de la reunion

        Returns:
            Reunion mise a jour ou None si non trouvee
        """
        existing = Database.get_by_id(TABLE_MEETINGS, self.tenant_id, meeting_id)
        if not existing:
            return None

        now = datetime.utcnow()
        date_debut = existing.get("date_debut_effective")

        # Calculer la duree effective
        duree_effective = 0
        if date_debut:
            if isinstance(date_debut, str):
                date_debut = datetime.fromisoformat(date_debut.replace("Z", "+00:00"))
            duree_effective = int((now - date_debut).total_seconds() / 60)

        update_data = {
            "statut": MeetingStatus.ENDED.value,
            "date_fin": now.isoformat(),
            "duree_effective_minutes": duree_effective,
        }

        result = Database.update(
            TABLE_MEETINGS,
            self.tenant_id,
            meeting_id,
            update_data,
            self.user_id
        )

        logger.info(
            "meeting_ended",
            meeting_id=meeting_id,
            tenant_id=self.tenant_id,
            duration_minutes=duree_effective
        )

        return self._map_to_meeting_response(result) if result else None

    async def delete_meeting(self, meeting_id: UUID) -> bool:
        """
        Supprime une reunion (soft delete).

        Args:
            meeting_id: ID de la reunion

        Returns:
            True si supprimee, False sinon
        """
        result = Database.soft_delete(TABLE_MEETINGS, self.tenant_id, meeting_id)

        if result:
            logger.info(
                "meeting_deleted",
                meeting_id=meeting_id,
                tenant_id=self.tenant_id
            )

        return result

    # =========================================================================
    # Gestion des participants
    # =========================================================================
    async def _add_host_participant(
        self,
        meeting_id: UUID,
        user_id: UUID,
        nom: str,
        email: str
    ) -> dict:
        """
        Ajoute l'organisateur comme participant HOST.

        Args:
            meeting_id: ID de la reunion
            user_id: ID de l'utilisateur
            nom: Nom de l'organisateur
            email: Email de l'organisateur

        Returns:
            Participant cree
        """
        participant_data = {
            "meeting_id": str(meeting_id),
            "user_id": str(user_id),
            "email": email,
            "nom": nom,
            "role": ParticipantRole.HOST.value,
            "statut": ParticipantStatus.INVITED.value,
            "audio_actif": False,
            "video_actif": False,
            "partage_ecran_actif": False,
            "main_levee": False,
            "date_invitation": datetime.utcnow().isoformat(),
            "temps_presence_minutes": 0,
        }

        return Database.insert(
            TABLE_PARTICIPANTS,
            self.tenant_id,
            participant_data,
            user_id
        )

    async def add_participant(
        self,
        data: ParticipantCreate
    ) -> ParticipantResponse:
        """
        Ajoute un participant a une reunion (invitation).

        Args:
            data: Donnees du participant

        Returns:
            Participant cree
        """
        # Verifier que la reunion existe
        meeting = await self.get_meeting(data.meeting_id)
        if not meeting:
            raise ValueError(f"Reunion {data.meeting_id} non trouvee")

        # Verifier si le participant existe deja
        existing = Database.query(
            TABLE_PARTICIPANTS,
            self.tenant_id,
            filters={
                "meeting_id": str(data.meeting_id),
                "email": data.email
            },
            limit=1
        )

        if existing:
            raise ValueError(f"Participant {data.email} deja invite")

        participant_data = {
            "meeting_id": str(data.meeting_id),
            "user_id": str(data.user_id) if data.user_id else None,
            "email": data.email,
            "nom": data.nom,
            "role": data.role.value,
            "statut": ParticipantStatus.INVITED.value,
            "audio_actif": False,
            "video_actif": False,
            "partage_ecran_actif": False,
            "main_levee": False,
            "date_invitation": datetime.utcnow().isoformat(),
            "temps_presence_minutes": 0,
        }

        result = Database.insert(
            TABLE_PARTICIPANTS,
            self.tenant_id,
            participant_data,
            self.user_id
        )

        logger.info(
            "participant_added",
            meeting_id=data.meeting_id,
            email=data.email,
            role=data.role.value
        )

        # TODO: Envoyer l'invitation par email si demande
        if data.envoyer_invitation:
            pass  # await self._send_invitation_email(result, meeting)

        return self._map_to_participant_response(result)

    async def remove_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> bool:
        """
        Retire un participant d'une reunion.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant

        Returns:
            True si retire, False sinon
        """
        # Verifier que le participant appartient a la reunion
        participant = Database.get_by_id(TABLE_PARTICIPANTS, self.tenant_id, participant_id)

        if not participant or str(participant.get("meeting_id")) != str(meeting_id):
            return False

        # Mettre a jour le statut plutot que supprimer
        update_data = {
            "statut": ParticipantStatus.REMOVED.value,
            "date_deconnexion": datetime.utcnow().isoformat(),
        }

        result = Database.update(
            TABLE_PARTICIPANTS,
            self.tenant_id,
            participant_id,
            update_data,
            self.user_id
        )

        logger.info(
            "participant_removed",
            meeting_id=meeting_id,
            participant_id=participant_id
        )

        return result is not None

    async def admit_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> Optional[ParticipantResponse]:
        """
        Admet un participant depuis la salle d'attente.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant

        Returns:
            Participant mis a jour ou None
        """
        participant = Database.get_by_id(TABLE_PARTICIPANTS, self.tenant_id, participant_id)

        if not participant:
            return None

        if str(participant.get("meeting_id")) != str(meeting_id):
            return None

        if participant.get("statut") != ParticipantStatus.WAITING.value:
            logger.warning(
                "participant_not_in_waiting_room",
                participant_id=participant_id,
                current_status=participant.get("statut")
            )
            return None

        update_data = {
            "statut": ParticipantStatus.JOINED.value,
            "date_connexion": datetime.utcnow().isoformat(),
        }

        result = Database.update(
            TABLE_PARTICIPANTS,
            self.tenant_id,
            participant_id,
            update_data,
            self.user_id
        )

        logger.info(
            "participant_admitted",
            meeting_id=meeting_id,
            participant_id=participant_id
        )

        return self._map_to_participant_response(result) if result else None

    async def list_participants(
        self,
        meeting_id: UUID,
        statut: Optional[ParticipantStatus] = None
    ) -> List[ParticipantResponse]:
        """
        Liste les participants d'une reunion.

        Args:
            meeting_id: ID de la reunion
            statut: Filtre par statut (optionnel)

        Returns:
            Liste des participants
        """
        filters = {"meeting_id": str(meeting_id)}

        if statut:
            filters["statut"] = statut.value

        results = Database.query(
            TABLE_PARTICIPANTS,
            self.tenant_id,
            filters=filters,
            order_by="date_invitation ASC"
        )

        return [self._map_to_participant_response(r) for r in results]

    # =========================================================================
    # Rejoindre une reunion
    # =========================================================================
    async def join_meeting(
        self,
        data: JoinMeetingRequest,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None
    ) -> JoinMeetingResponse:
        """
        Rejoindre une reunion.

        Args:
            data: Donnees de connexion
            user_id: ID utilisateur AZALPLUS (optionnel)
            user_email: Email de l'utilisateur (optionnel)

        Returns:
            Reponse avec token LiveKit et infos de connexion

        Raises:
            ValueError: Si la reunion n'existe pas ou mot de passe incorrect
        """
        # Recuperer la reunion
        meeting = None
        if data.meeting_id:
            meeting = await self.get_meeting(data.meeting_id)
        elif data.code_reunion:
            meeting = await self.get_meeting_by_code(data.code_reunion)

        if not meeting:
            raise ValueError("Reunion non trouvee")

        # Verifier le statut
        if meeting.statut in [MeetingStatus.ENDED, MeetingStatus.CANCELLED]:
            raise ValueError(f"Reunion terminee ou annulee")

        # Verifier le mot de passe si requis
        if meeting.mot_de_passe_requis:
            if not data.mot_de_passe:
                raise ValueError("Mot de passe requis")

            # Recuperer le hash stocke
            meeting_data = Database.get_by_id(TABLE_MEETINGS, self.tenant_id, meeting.id)
            if not self._verify_password(data.mot_de_passe, meeting_data.get("mot_de_passe_hash", "")):
                raise ValueError("Mot de passe incorrect")

        # Verifier le nombre de participants
        if meeting.nombre_participants >= meeting.max_participants:
            raise ValueError("Nombre maximum de participants atteint")

        # Chercher ou creer le participant
        participant = None
        if user_id:
            existing = Database.query(
                TABLE_PARTICIPANTS,
                self.tenant_id,
                filters={
                    "meeting_id": str(meeting.id),
                    "user_id": str(user_id)
                },
                limit=1
            )
            if existing:
                participant = existing[0]

        if not participant and user_email:
            existing = Database.query(
                TABLE_PARTICIPANTS,
                self.tenant_id,
                filters={
                    "meeting_id": str(meeting.id),
                    "email": user_email
                },
                limit=1
            )
            if existing:
                participant = existing[0]

        # Determiner le statut d'entree
        en_salle_attente = meeting.salle_attente_active

        if not participant:
            # Creer un nouveau participant
            participant_data = {
                "meeting_id": str(meeting.id),
                "user_id": str(user_id) if user_id else None,
                "email": user_email or "",
                "nom": data.nom_affiche,
                "role": ParticipantRole.PARTICIPANT.value,
                "statut": ParticipantStatus.WAITING.value if en_salle_attente else ParticipantStatus.JOINED.value,
                "audio_actif": data.audio_active and not meeting.participants_muets_entree,
                "video_actif": data.video_active,
                "partage_ecran_actif": False,
                "main_levee": False,
                "date_invitation": datetime.utcnow().isoformat(),
                "date_connexion": None if en_salle_attente else datetime.utcnow().isoformat(),
                "temps_presence_minutes": 0,
            }
            participant = Database.insert(
                TABLE_PARTICIPANTS,
                self.tenant_id,
                participant_data,
                user_id
            )
        else:
            # Mettre a jour le participant existant
            new_status = ParticipantStatus.WAITING.value if en_salle_attente else ParticipantStatus.JOINED.value

            # Si c'est un host/co-host, pas de salle d'attente
            if participant.get("role") in [ParticipantRole.HOST.value, ParticipantRole.CO_HOST.value]:
                new_status = ParticipantStatus.JOINED.value
                en_salle_attente = False

            update_data = {
                "nom": data.nom_affiche,
                "statut": new_status,
                "audio_actif": data.audio_active and not meeting.participants_muets_entree,
                "video_actif": data.video_active,
            }

            if new_status == ParticipantStatus.JOINED.value:
                update_data["date_connexion"] = datetime.utcnow().isoformat()

            participant = Database.update(
                TABLE_PARTICIPANTS,
                self.tenant_id,
                UUID(participant["id"]),
                update_data,
                user_id
            )

        # Mettre a jour le compteur de participants
        if not en_salle_attente:
            meeting_data = Database.get_by_id(TABLE_MEETINGS, self.tenant_id, meeting.id)
            new_count = meeting_data.get("nombre_participants", 0) + 1
            Database.update(
                TABLE_MEETINGS,
                self.tenant_id,
                meeting.id,
                {
                    "nombre_participants": new_count,
                    "nombre_participants_max_atteint": max(
                        new_count,
                        meeting_data.get("nombre_participants_max_atteint", 0)
                    )
                },
                user_id
            )

        # Generer le token LiveKit
        room_name = self._generate_room_name(meeting.id)
        participant_identity = str(participant["id"])
        is_host = participant.get("role") in [ParticipantRole.HOST.value, ParticipantRole.CO_HOST.value]

        livekit_token = self._generate_livekit_token(
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=data.nom_affiche,
            is_host=is_host
        )

        config = self._get_livekit_config()

        logger.info(
            "participant_joined",
            meeting_id=meeting.id,
            participant_id=participant["id"],
            in_waiting_room=en_salle_attente
        )

        return JoinMeetingResponse(
            meeting_id=meeting.id,
            participant_id=UUID(participant["id"]),
            room_name=room_name,
            livekit_url=config["url"],
            livekit_token=livekit_token,
            titre=meeting.titre,
            statut=meeting.statut,
            chat_actif=meeting.chat_actif,
            tableau_blanc_actif=meeting.tableau_blanc_actif,
            transcription_active=meeting.transcription_active,
            enregistrement_en_cours=False,  # TODO: Verifier l'etat reel
            websocket_url=f"wss://api.azalplus.com/ws/videoconf/{meeting.id}",
            en_salle_attente=en_salle_attente
        )

    # =========================================================================
    # Mappers
    # =========================================================================
    def _map_to_meeting_response(self, data: dict) -> MeetingResponse:
        """
        Convertit les donnees brutes en MeetingResponse.

        Args:
            data: Donnees brutes de la base

        Returns:
            MeetingResponse formate
        """
        # Generer le lien de reunion
        code = data.get("code_reunion", "")
        lien_reunion = f"https://app.azalplus.com/meet/{code}"

        return MeetingResponse(
            id=UUID(data["id"]),
            tenant_id=UUID(data["tenant_id"]),
            titre=data.get("titre", ""),
            description=data.get("description"),
            type_reunion=MeetingType(data.get("type_reunion", "instant")),
            statut=MeetingStatus(data.get("statut", "waiting")),
            date_debut=self._parse_datetime(data.get("date_debut")),
            date_debut_effective=self._parse_datetime(data.get("date_debut_effective")),
            date_fin=self._parse_datetime(data.get("date_fin")),
            duree_minutes=data.get("duree_minutes", 60),
            duree_effective_minutes=data.get("duree_effective_minutes"),
            salle_attente_active=data.get("salle_attente_active", True),
            participants_muets_entree=data.get("participants_muets_entree", False),
            enregistrement_auto=data.get("enregistrement_auto", False),
            transcription_active=data.get("transcription_active", False),
            chat_actif=data.get("chat_actif", True),
            tableau_blanc_actif=data.get("tableau_blanc_actif", True),
            max_participants=data.get("max_participants", 50),
            code_reunion=code,
            lien_reunion=lien_reunion,
            mot_de_passe_requis=data.get("mot_de_passe_hash") is not None,
            nombre_participants=data.get("nombre_participants", 0),
            nombre_participants_max_atteint=data.get("nombre_participants_max_atteint", 0),
            organisateur_id=UUID(data["organisateur_id"]),
            organisateur_nom=data.get("organisateur_nom", ""),
            projet_id=UUID(data["projet_id"]) if data.get("projet_id") else None,
            client_id=UUID(data["client_id"]) if data.get("client_id") else None,
            enregistrement_disponible=data.get("enregistrement_disponible", False),
            transcription_disponible=data.get("transcription_disponible", False),
            compte_rendu_disponible=data.get("compte_rendu_disponible", False),
            created_at=self._parse_datetime(data.get("created_at")) or datetime.utcnow(),
            updated_at=self._parse_datetime(data.get("updated_at")),
            created_by=UUID(data["created_by"]) if data.get("created_by") else UUID(data["organisateur_id"]),
        )

    def _map_to_participant_response(self, data: dict) -> ParticipantResponse:
        """
        Convertit les donnees brutes en ParticipantResponse.

        Args:
            data: Donnees brutes de la base

        Returns:
            ParticipantResponse formate
        """
        return ParticipantResponse(
            id=UUID(data["id"]),
            meeting_id=UUID(data["meeting_id"]),
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            email=data.get("email", ""),
            nom=data.get("nom", ""),
            role=ParticipantRole(data.get("role", "participant")),
            statut=ParticipantStatus(data.get("statut", "invited")),
            audio_actif=data.get("audio_actif", False),
            video_actif=data.get("video_actif", False),
            partage_ecran_actif=data.get("partage_ecran_actif", False),
            main_levee=data.get("main_levee", False),
            date_invitation=self._parse_datetime(data.get("date_invitation")) or datetime.utcnow(),
            date_connexion=self._parse_datetime(data.get("date_connexion")),
            date_deconnexion=self._parse_datetime(data.get("date_deconnexion")),
            temps_presence_minutes=data.get("temps_presence_minutes", 0),
        )

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """
        Parse une valeur en datetime.

        Args:
            value: Valeur a parser (str, datetime ou None)

        Returns:
            datetime ou None
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Gerer le format ISO avec ou sans Z
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    # =========================================================================
    # Health check
    # =========================================================================
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifie l'etat du service de videoconference.

        Returns:
            Etat des differents composants
        """
        results = {
            "database": "ok",
            "livekit": "unknown",
            "tenant_id": str(self.tenant_id),
        }

        # Verifier la base de donnees
        try:
            Database.count(TABLE_MEETINGS, self.tenant_id)
        except Exception as e:
            results["database"] = f"error: {str(e)}"

        # Verifier la configuration LiveKit
        config = self._get_livekit_config()
        if config.get("api_key") and config.get("api_secret"):
            results["livekit"] = "configured"
        else:
            results["livekit"] = "not_configured"

        return results
