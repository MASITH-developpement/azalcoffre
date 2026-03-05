# =============================================================================
# AZALPLUS - WebSocket Manager pour Visioconferences
# =============================================================================
"""
Infrastructure WebSocket pour les reunions temps reel.

Fonctionnalites:
- Gestion des connexions par meeting_id et tenant_id
- Isolation multi-tenant stricte
- Broadcast et envoi cible aux participants
- Authentification JWT pour WebSocket
- Heartbeat ping/pong pour detection des deconnexions
- Support des evenements temps reel (chat, controles, whiteboard, etc.)
"""

import asyncio
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import jwt, JWTError
import structlog

from .config import settings
from .auth import decode_token

logger = structlog.get_logger()


# =============================================================================
# Types d'evenements WebSocket
# =============================================================================
class WebSocketEventType(str, Enum):
    """Types d'evenements WebSocket pour les reunions."""

    # Connexion
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTED = "reconnected"

    # Participants
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    PARTICIPANT_UPDATED = "participant_updated"
    WAITING_ROOM_JOINED = "waiting_room_joined"
    WAITING_ROOM_ADMITTED = "waiting_room_admitted"
    WAITING_ROOM_REJECTED = "waiting_room_rejected"
    PARTICIPANT_KICKED = "participant_kicked"

    # Media
    AUDIO_TOGGLED = "audio_toggled"
    VIDEO_TOGGLED = "video_toggled"
    SCREEN_SHARE_STARTED = "screen_share_started"
    SCREEN_SHARE_STOPPED = "screen_share_stopped"
    BACKGROUND_CHANGED = "background_changed"

    # Controles organisateur
    MUTE_PARTICIPANT = "mute_participant"
    UNMUTE_PARTICIPANT = "unmute_participant"
    MUTE_ALL = "mute_all"
    DISABLE_VIDEO_PARTICIPANT = "disable_video_participant"
    ENABLE_VIDEO_PARTICIPANT = "enable_video_participant"
    DISABLE_VIDEO_ALL = "disable_video_all"

    # Main levee
    HAND_RAISED = "hand_raised"
    HAND_LOWERED = "hand_lowered"
    HAND_ACKNOWLEDGED = "hand_acknowledged"
    SPEAKING_TURN_GRANTED = "speaking_turn_granted"
    ALL_HANDS_LOWERED = "all_hands_lowered"

    # Reactions
    REACTION = "reaction"

    # Chat
    CHAT_MESSAGE = "chat_message"
    CHAT_MESSAGE_DELETED = "chat_message_deleted"
    CHAT_REACTION = "chat_reaction"
    TYPING_STARTED = "typing_started"
    TYPING_STOPPED = "typing_stopped"

    # Whiteboard
    WHITEBOARD_UPDATE = "whiteboard_update"
    WHITEBOARD_CURSOR = "whiteboard_cursor"
    WHITEBOARD_CLEARED = "whiteboard_cleared"

    # Enregistrement
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"
    RECORDING_PAUSED = "recording_paused"
    RECORDING_RESUMED = "recording_resumed"

    # Transcription
    TRANSCRIPTION_STARTED = "transcription_started"
    TRANSCRIPTION_STOPPED = "transcription_stopped"
    TRANSCRIPTION_CHUNK = "transcription_chunk"

    # Reunion
    MEETING_STARTED = "meeting_started"
    MEETING_PAUSED = "meeting_paused"
    MEETING_RESUMED = "meeting_resumed"
    MEETING_ENDED = "meeting_ended"
    MEETING_SETTINGS_CHANGED = "meeting_settings_changed"

    # Systeme
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    SYNC_STATE = "sync_state"


# =============================================================================
# Roles des participants
# =============================================================================
class ParticipantRole(str, Enum):
    """Roles des participants dans une reunion."""
    ORGANISATEUR = "ORGANISATEUR"
    CO_ORGANISATEUR = "CO_ORGANISATEUR"
    MODERATEUR = "MODERATEUR"
    PARTICIPANT = "PARTICIPANT"
    OBSERVATEUR = "OBSERVATEUR"


# =============================================================================
# Structure de connexion WebSocket
# =============================================================================
@dataclass
class WebSocketConnection:
    """Represente une connexion WebSocket active."""

    websocket: WebSocket
    meeting_id: UUID
    participant_id: UUID
    user_id: Optional[UUID]
    tenant_id: UUID
    role: ParticipantRole
    email: Optional[str]
    display_name: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_ping: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True

    # Etat media
    audio_enabled: bool = False
    video_enabled: bool = False
    screen_sharing: bool = False
    hand_raised: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour serialisation."""
        return {
            "participant_id": str(self.participant_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "role": self.role.value,
            "email": self.email,
            "display_name": self.display_name,
            "connected_at": self.connected_at.isoformat(),
            "audio_enabled": self.audio_enabled,
            "video_enabled": self.video_enabled,
            "screen_sharing": self.screen_sharing,
            "hand_raised": self.hand_raised,
        }


# =============================================================================
# Message WebSocket
# =============================================================================
@dataclass
class WebSocketMessage:
    """Structure d'un message WebSocket."""

    event_type: WebSocketEventType
    data: Dict[str, Any]
    sender_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    meeting_id: Optional[str] = None

    def to_json(self) -> str:
        """Serialise en JSON."""
        return json.dumps({
            "event": self.event_type.value,
            "data": self.data,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp.isoformat(),
            "meeting_id": self.meeting_id,
        })

    @classmethod
    def from_json(cls, json_str: str) -> "WebSocketMessage":
        """Deserialise depuis JSON."""
        data = json.loads(json_str)
        return cls(
            event_type=WebSocketEventType(data.get("event", "error")),
            data=data.get("data", {}),
            sender_id=data.get("sender_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            meeting_id=data.get("meeting_id"),
        )


# =============================================================================
# WebSocket Manager
# =============================================================================
class WebSocketManager:
    """
    Gestionnaire central des connexions WebSocket pour les reunions.

    Structure de stockage:
    - _connections: Dict[meeting_id, Dict[participant_id, WebSocketConnection]]
    - _tenant_meetings: Dict[tenant_id, Set[meeting_id]] (pour isolation)
    """

    def __init__(self):
        # Connexions par meeting puis par participant
        self._connections: Dict[UUID, Dict[UUID, WebSocketConnection]] = {}

        # Meetings par tenant (pour isolation)
        self._tenant_meetings: Dict[UUID, Set[UUID]] = {}

        # Lock pour operations thread-safe
        self._lock = asyncio.Lock()

        # Configuration heartbeat
        self.heartbeat_interval: int = 30  # secondes
        self.heartbeat_timeout: int = 90  # secondes avant deconnexion

        # Task de nettoyage
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info("websocket_manager_initialized")

    # =========================================================================
    # Gestion des connexions
    # =========================================================================

    async def connect(
        self,
        websocket: WebSocket,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        role: ParticipantRole = ParticipantRole.PARTICIPANT,
        email: Optional[str] = None,
        display_name: str = "Participant",
    ) -> WebSocketConnection:
        """
        Enregistre une nouvelle connexion WebSocket.

        Args:
            websocket: Instance WebSocket FastAPI
            meeting_id: ID de la reunion
            participant_id: ID du participant
            tenant_id: ID du tenant (isolation obligatoire)
            user_id: ID utilisateur (optionnel pour invites externes)
            role: Role du participant
            email: Email du participant
            display_name: Nom affiche

        Returns:
            WebSocketConnection creee
        """
        async with self._lock:
            # Creer la structure si necessaire
            if meeting_id not in self._connections:
                self._connections[meeting_id] = {}

            # Enregistrer le meeting pour le tenant
            if tenant_id not in self._tenant_meetings:
                self._tenant_meetings[tenant_id] = set()
            self._tenant_meetings[tenant_id].add(meeting_id)

            # Creer la connexion
            connection = WebSocketConnection(
                websocket=websocket,
                meeting_id=meeting_id,
                participant_id=participant_id,
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
                email=email,
                display_name=display_name,
            )

            # Deconnecter l'ancienne connexion si existante
            if participant_id in self._connections[meeting_id]:
                old_conn = self._connections[meeting_id][participant_id]
                try:
                    await old_conn.websocket.close(code=4001, reason="Reconnected from another location")
                except Exception:
                    pass
                logger.info(
                    "websocket_reconnection",
                    meeting_id=str(meeting_id),
                    participant_id=str(participant_id),
                )

            # Enregistrer la nouvelle connexion
            self._connections[meeting_id][participant_id] = connection

            logger.info(
                "websocket_connected",
                meeting_id=str(meeting_id),
                participant_id=str(participant_id),
                tenant_id=str(tenant_id),
                role=role.value,
                participants_count=len(self._connections[meeting_id]),
            )

            return connection

    async def disconnect(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """
        Deconnecte un participant.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            tenant_id: ID du tenant (verification)

        Returns:
            True si deconnexion reussie
        """
        async with self._lock:
            # Verifier que le meeting appartient au tenant
            if not self._verify_tenant_access(meeting_id, tenant_id):
                logger.warning(
                    "websocket_disconnect_denied",
                    meeting_id=str(meeting_id),
                    tenant_id=str(tenant_id),
                    reason="tenant_mismatch",
                )
                return False

            if meeting_id not in self._connections:
                return False

            if participant_id not in self._connections[meeting_id]:
                return False

            connection = self._connections[meeting_id][participant_id]
            connection.is_active = False

            try:
                await connection.websocket.close()
            except Exception:
                pass

            del self._connections[meeting_id][participant_id]

            # Nettoyer si plus de participants
            if not self._connections[meeting_id]:
                del self._connections[meeting_id]

                # Retirer du tenant
                if tenant_id in self._tenant_meetings:
                    self._tenant_meetings[tenant_id].discard(meeting_id)

            logger.info(
                "websocket_disconnected",
                meeting_id=str(meeting_id),
                participant_id=str(participant_id),
            )

            return True

    def _verify_tenant_access(self, meeting_id: UUID, tenant_id: UUID) -> bool:
        """Verifie qu'un meeting appartient a un tenant."""
        if tenant_id not in self._tenant_meetings:
            return False
        return meeting_id in self._tenant_meetings[tenant_id]

    # =========================================================================
    # Envoi de messages
    # =========================================================================

    async def broadcast_to_meeting(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        event_type: WebSocketEventType,
        data: Dict[str, Any],
        exclude_participant_id: Optional[UUID] = None,
    ) -> int:
        """
        Envoie un message a tous les participants d'une reunion.

        Args:
            meeting_id: ID de la reunion
            tenant_id: ID du tenant (verification obligatoire)
            event_type: Type d'evenement
            data: Donnees a envoyer
            exclude_participant_id: Participant a exclure (optionnel)

        Returns:
            Nombre de messages envoyes
        """
        # Verifier l'isolation tenant
        if not self._verify_tenant_access(meeting_id, tenant_id):
            logger.warning(
                "websocket_broadcast_denied",
                meeting_id=str(meeting_id),
                tenant_id=str(tenant_id),
                reason="tenant_mismatch",
            )
            return 0

        if meeting_id not in self._connections:
            return 0

        message = WebSocketMessage(
            event_type=event_type,
            data=data,
            meeting_id=str(meeting_id),
        )

        sent_count = 0
        disconnected: List[UUID] = []

        for participant_id, connection in self._connections[meeting_id].items():
            if exclude_participant_id and participant_id == exclude_participant_id:
                continue

            if not connection.is_active:
                continue

            try:
                await connection.websocket.send_text(message.to_json())
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    participant_id=str(participant_id),
                    error=str(e),
                )
                disconnected.append(participant_id)

        # Nettoyer les connexions mortes
        for participant_id in disconnected:
            await self.disconnect(meeting_id, participant_id, tenant_id)

        logger.debug(
            "websocket_broadcast",
            meeting_id=str(meeting_id),
            event_type=event_type.value,
            sent_count=sent_count,
        )

        return sent_count

    async def send_to_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
        event_type: WebSocketEventType,
        data: Dict[str, Any],
    ) -> bool:
        """
        Envoie un message a un participant specifique.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant cible
            tenant_id: ID du tenant (verification obligatoire)
            event_type: Type d'evenement
            data: Donnees a envoyer

        Returns:
            True si envoi reussi
        """
        # Verifier l'isolation tenant
        if not self._verify_tenant_access(meeting_id, tenant_id):
            logger.warning(
                "websocket_send_denied",
                meeting_id=str(meeting_id),
                tenant_id=str(tenant_id),
                reason="tenant_mismatch",
            )
            return False

        if meeting_id not in self._connections:
            return False

        if participant_id not in self._connections[meeting_id]:
            return False

        connection = self._connections[meeting_id][participant_id]

        if not connection.is_active:
            return False

        message = WebSocketMessage(
            event_type=event_type,
            data=data,
            meeting_id=str(meeting_id),
        )

        try:
            await connection.websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.warning(
                "websocket_send_failed",
                participant_id=str(participant_id),
                error=str(e),
            )
            await self.disconnect(meeting_id, participant_id, tenant_id)
            return False

    async def send_event(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        event_type: WebSocketEventType,
        data: Dict[str, Any],
        exclude_participant_id: Optional[UUID] = None,
    ) -> int:
        """
        Alias pour broadcast_to_meeting.
        Envoie un evenement a tous les participants d'une reunion.
        """
        return await self.broadcast_to_meeting(
            meeting_id=meeting_id,
            tenant_id=tenant_id,
            event_type=event_type,
            data=data,
            exclude_participant_id=exclude_participant_id,
        )

    # =========================================================================
    # Requetes d'etat
    # =========================================================================

    def get_participants(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Retourne la liste des participants connectes.

        Args:
            meeting_id: ID de la reunion
            tenant_id: ID du tenant (verification obligatoire)

        Returns:
            Liste des participants sous forme de dict
        """
        if not self._verify_tenant_access(meeting_id, tenant_id):
            return []

        if meeting_id not in self._connections:
            return []

        return [
            conn.to_dict()
            for conn in self._connections[meeting_id].values()
            if conn.is_active
        ]

    def get_participant_count(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
    ) -> int:
        """Retourne le nombre de participants connectes."""
        if not self._verify_tenant_access(meeting_id, tenant_id):
            return 0

        if meeting_id not in self._connections:
            return 0

        return sum(1 for conn in self._connections[meeting_id].values() if conn.is_active)

    def get_connection(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
    ) -> Optional[WebSocketConnection]:
        """Retourne une connexion specifique."""
        if not self._verify_tenant_access(meeting_id, tenant_id):
            return None

        if meeting_id not in self._connections:
            return None

        return self._connections[meeting_id].get(participant_id)

    def is_connected(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Verifie si un participant est connecte."""
        conn = self.get_connection(meeting_id, participant_id, tenant_id)
        return conn is not None and conn.is_active

    # =========================================================================
    # Mise a jour d'etat
    # =========================================================================

    async def update_participant_state(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
        **updates: Any,
    ) -> bool:
        """
        Met a jour l'etat d'un participant.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            tenant_id: ID du tenant
            **updates: Champs a mettre a jour (audio_enabled, video_enabled, etc.)

        Returns:
            True si mise a jour reussie
        """
        conn = self.get_connection(meeting_id, participant_id, tenant_id)
        if not conn:
            return False

        # Appliquer les mises a jour
        for key, value in updates.items():
            if hasattr(conn, key):
                setattr(conn, key, value)

        return True

    # =========================================================================
    # Heartbeat
    # =========================================================================

    async def handle_ping(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """
        Gere un ping heartbeat.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            tenant_id: ID du tenant

        Returns:
            True si pong envoye
        """
        conn = self.get_connection(meeting_id, participant_id, tenant_id)
        if not conn:
            return False

        conn.last_ping = datetime.utcnow()

        return await self.send_to_participant(
            meeting_id=meeting_id,
            participant_id=participant_id,
            tenant_id=tenant_id,
            event_type=WebSocketEventType.PONG,
            data={"timestamp": datetime.utcnow().isoformat()},
        )

    async def cleanup_stale_connections(self) -> int:
        """
        Nettoie les connexions inactives.

        Returns:
            Nombre de connexions nettoyees
        """
        now = datetime.utcnow()
        timeout = timedelta(seconds=self.heartbeat_timeout)
        cleaned = 0

        # Copier les cles pour eviter modification pendant iteration
        meeting_ids = list(self._connections.keys())

        for meeting_id in meeting_ids:
            if meeting_id not in self._connections:
                continue

            participant_ids = list(self._connections[meeting_id].keys())

            for participant_id in participant_ids:
                if participant_id not in self._connections.get(meeting_id, {}):
                    continue

                conn = self._connections[meeting_id][participant_id]

                if now - conn.last_ping > timeout:
                    logger.info(
                        "websocket_stale_cleanup",
                        meeting_id=str(meeting_id),
                        participant_id=str(participant_id),
                        last_ping=conn.last_ping.isoformat(),
                    )
                    await self.disconnect(meeting_id, participant_id, conn.tenant_id)
                    cleaned += 1

        if cleaned > 0:
            logger.info("websocket_cleanup_completed", cleaned_count=cleaned)

        return cleaned

    async def start_cleanup_task(self) -> None:
        """Demarre la tache de nettoyage periodique."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                try:
                    await self.cleanup_stale_connections()
                except Exception as e:
                    logger.error("websocket_cleanup_error", error=str(e))

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("websocket_cleanup_task_started")

    async def stop_cleanup_task(self) -> None:
        """Arrete la tache de nettoyage."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("websocket_cleanup_task_stopped")

    # =========================================================================
    # Fermeture d'une reunion
    # =========================================================================

    async def close_meeting(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        reason: str = "Meeting ended",
    ) -> int:
        """
        Ferme toutes les connexions d'une reunion.

        Args:
            meeting_id: ID de la reunion
            tenant_id: ID du tenant
            reason: Raison de la fermeture

        Returns:
            Nombre de connexions fermees
        """
        if not self._verify_tenant_access(meeting_id, tenant_id):
            return 0

        if meeting_id not in self._connections:
            return 0

        # Envoyer l'evenement de fin
        await self.broadcast_to_meeting(
            meeting_id=meeting_id,
            tenant_id=tenant_id,
            event_type=WebSocketEventType.MEETING_ENDED,
            data={"reason": reason},
        )

        # Fermer toutes les connexions
        closed_count = 0
        async with self._lock:
            if meeting_id in self._connections:
                for connection in self._connections[meeting_id].values():
                    try:
                        await connection.websocket.close(code=1000, reason=reason)
                        closed_count += 1
                    except Exception:
                        pass

                del self._connections[meeting_id]

                if tenant_id in self._tenant_meetings:
                    self._tenant_meetings[tenant_id].discard(meeting_id)

        logger.info(
            "websocket_meeting_closed",
            meeting_id=str(meeting_id),
            closed_count=closed_count,
        )

        return closed_count


# =============================================================================
# Verification JWT pour WebSocket
# =============================================================================
@dataclass
class WebSocketTokenPayload:
    """Payload d'un token JWT WebSocket."""

    user_id: Optional[UUID]
    tenant_id: UUID
    meeting_id: UUID
    participant_id: UUID
    role: ParticipantRole
    email: Optional[str]
    display_name: str
    exp: datetime


def create_websocket_token(
    tenant_id: UUID,
    meeting_id: UUID,
    participant_id: UUID,
    role: ParticipantRole,
    user_id: Optional[UUID] = None,
    email: Optional[str] = None,
    display_name: str = "Participant",
    expires_hours: int = 8,
) -> str:
    """
    Cree un token JWT pour l'authentification WebSocket.

    Args:
        tenant_id: ID du tenant
        meeting_id: ID de la reunion
        participant_id: ID du participant
        role: Role du participant
        user_id: ID utilisateur (optionnel)
        email: Email (optionnel)
        display_name: Nom affiche
        expires_hours: Duree de validite en heures

    Returns:
        Token JWT
    """
    expire = datetime.utcnow() + timedelta(hours=expires_hours)

    payload = {
        "type": "websocket",
        "tenant_id": str(tenant_id),
        "meeting_id": str(meeting_id),
        "participant_id": str(participant_id),
        "role": role.value,
        "display_name": display_name,
        "exp": expire,
    }

    if user_id:
        payload["user_id"] = str(user_id)
    if email:
        payload["email"] = email

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_websocket_token(token: str) -> Optional[WebSocketTokenPayload]:
    """
    Verifie un token JWT WebSocket.

    Args:
        token: Token JWT a verifier

    Returns:
        Payload decode ou None si invalide
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        # Verifier le type
        if payload.get("type") != "websocket":
            logger.warning("websocket_token_invalid_type", type=payload.get("type"))
            return None

        # Verifier l'expiration
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            logger.warning("websocket_token_expired")
            return None

        return WebSocketTokenPayload(
            user_id=UUID(payload["user_id"]) if payload.get("user_id") else None,
            tenant_id=UUID(payload["tenant_id"]),
            meeting_id=UUID(payload["meeting_id"]),
            participant_id=UUID(payload["participant_id"]),
            role=ParticipantRole(payload["role"]),
            email=payload.get("email"),
            display_name=payload.get("display_name", "Participant"),
            exp=datetime.utcfromtimestamp(payload["exp"]),
        )

    except JWTError as e:
        logger.warning("websocket_token_decode_error", error=str(e))
        return None
    except (KeyError, ValueError) as e:
        logger.warning("websocket_token_invalid_payload", error=str(e))
        return None


# =============================================================================
# Instance globale du manager
# =============================================================================
websocket_manager = WebSocketManager()


# =============================================================================
# Router FastAPI WebSocket
# =============================================================================
router = APIRouter()


@router.websocket("/ws/videoconf/{meeting_id}")
async def websocket_videoconf_endpoint(
    websocket: WebSocket,
    meeting_id: str,
    token: str = Query(..., description="JWT token d'authentification"),
):
    """
    Endpoint WebSocket pour les reunions de visioconference.

    Authentification via token JWT en query parameter.

    Events entrants geres:
    - ping: Heartbeat
    - audio_toggled: Changement d'etat audio
    - video_toggled: Changement d'etat video
    - hand_raised/hand_lowered: Main levee
    - chat_message: Message chat
    - reaction: Reaction emoji
    - whiteboard_update: Mise a jour whiteboard

    Events sortants:
    - Tous les events WebSocketEventType
    """
    # Verifier le token
    payload = verify_websocket_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # Verifier que le meeting_id correspond
    try:
        meeting_uuid = UUID(meeting_id)
    except ValueError:
        await websocket.close(code=4002, reason="Invalid meeting ID")
        return

    if payload.meeting_id != meeting_uuid:
        await websocket.close(code=4003, reason="Token meeting ID mismatch")
        return

    # Accepter la connexion
    await websocket.accept()

    # Enregistrer la connexion
    connection = await websocket_manager.connect(
        websocket=websocket,
        meeting_id=payload.meeting_id,
        participant_id=payload.participant_id,
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        role=payload.role,
        email=payload.email,
        display_name=payload.display_name,
    )

    # Envoyer confirmation de connexion
    await websocket_manager.send_to_participant(
        meeting_id=payload.meeting_id,
        participant_id=payload.participant_id,
        tenant_id=payload.tenant_id,
        event_type=WebSocketEventType.CONNECTED,
        data={
            "participant_id": str(payload.participant_id),
            "role": payload.role.value,
            "display_name": payload.display_name,
            "participants": websocket_manager.get_participants(
                payload.meeting_id, payload.tenant_id
            ),
        },
    )

    # Notifier les autres participants
    await websocket_manager.broadcast_to_meeting(
        meeting_id=payload.meeting_id,
        tenant_id=payload.tenant_id,
        event_type=WebSocketEventType.PARTICIPANT_JOINED,
        data=connection.to_dict(),
        exclude_participant_id=payload.participant_id,
    )

    try:
        # Boucle de reception des messages
        while True:
            try:
                data = await websocket.receive_text()
                message = WebSocketMessage.from_json(data)

                # Traiter selon le type d'evenement
                await _handle_incoming_event(
                    manager=websocket_manager,
                    connection=connection,
                    message=message,
                )

            except json.JSONDecodeError:
                logger.warning(
                    "websocket_invalid_json",
                    participant_id=str(payload.participant_id),
                )
                await websocket_manager.send_to_participant(
                    meeting_id=payload.meeting_id,
                    participant_id=payload.participant_id,
                    tenant_id=payload.tenant_id,
                    event_type=WebSocketEventType.ERROR,
                    data={"error": "Invalid JSON format"},
                )

    except WebSocketDisconnect:
        logger.info(
            "websocket_client_disconnected",
            meeting_id=str(payload.meeting_id),
            participant_id=str(payload.participant_id),
        )
    except Exception as e:
        logger.error(
            "websocket_error",
            meeting_id=str(payload.meeting_id),
            participant_id=str(payload.participant_id),
            error=str(e),
        )
    finally:
        # Deconnecter et notifier
        await websocket_manager.disconnect(
            meeting_id=payload.meeting_id,
            participant_id=payload.participant_id,
            tenant_id=payload.tenant_id,
        )

        # Notifier les autres participants
        await websocket_manager.broadcast_to_meeting(
            meeting_id=payload.meeting_id,
            tenant_id=payload.tenant_id,
            event_type=WebSocketEventType.PARTICIPANT_LEFT,
            data={
                "participant_id": str(payload.participant_id),
                "display_name": payload.display_name,
            },
        )


async def _handle_incoming_event(
    manager: WebSocketManager,
    connection: WebSocketConnection,
    message: WebSocketMessage,
) -> None:
    """
    Traite un evenement entrant.

    Args:
        manager: Instance du WebSocketManager
        connection: Connexion du participant
        message: Message recu
    """
    event = message.event_type
    data = message.data

    # Heartbeat
    if event == WebSocketEventType.PING:
        await manager.handle_ping(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
        )
        return

    # Changement d'etat audio
    if event == WebSocketEventType.AUDIO_TOGGLED:
        enabled = data.get("enabled", False)
        await manager.update_participant_state(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            audio_enabled=enabled,
        )
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.AUDIO_TOGGLED,
            data={
                "participant_id": str(connection.participant_id),
                "enabled": enabled,
            },
        )
        return

    # Changement d'etat video
    if event == WebSocketEventType.VIDEO_TOGGLED:
        enabled = data.get("enabled", False)
        await manager.update_participant_state(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            video_enabled=enabled,
        )
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.VIDEO_TOGGLED,
            data={
                "participant_id": str(connection.participant_id),
                "enabled": enabled,
            },
        )
        return

    # Main levee
    if event == WebSocketEventType.HAND_RAISED:
        await manager.update_participant_state(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            hand_raised=True,
        )
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.HAND_RAISED,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    if event == WebSocketEventType.HAND_LOWERED:
        await manager.update_participant_state(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            hand_raised=False,
        )
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.HAND_LOWERED,
            data={
                "participant_id": str(connection.participant_id),
            },
        )
        return

    # Message chat
    if event == WebSocketEventType.CHAT_MESSAGE:
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.CHAT_MESSAGE,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "content": data.get("content", ""),
                "type": data.get("type", "TEXT"),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # Reaction
    if event == WebSocketEventType.REACTION:
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.REACTION,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "emoji": data.get("emoji", ""),
            },
        )
        return

    # Whiteboard update
    if event == WebSocketEventType.WHITEBOARD_UPDATE:
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.WHITEBOARD_UPDATE,
            data={
                "participant_id": str(connection.participant_id),
                "update": data.get("update", {}),
            },
            exclude_participant_id=connection.participant_id,
        )
        return

    # Whiteboard cursor (mouvement souris)
    if event == WebSocketEventType.WHITEBOARD_CURSOR:
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.WHITEBOARD_CURSOR,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "x": data.get("x", 0),
                "y": data.get("y", 0),
            },
            exclude_participant_id=connection.participant_id,
        )
        return

    # Typing indicator
    if event in (WebSocketEventType.TYPING_STARTED, WebSocketEventType.TYPING_STOPPED):
        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=event,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
            },
            exclude_participant_id=connection.participant_id,
        )
        return

    # Evenement non reconnu
    logger.debug(
        "websocket_unhandled_event",
        event_type=event.value if hasattr(event, 'value') else str(event),
        participant_id=str(connection.participant_id),
    )


# =============================================================================
# Fonctions utilitaires pour l'integration
# =============================================================================

async def notify_meeting_started(
    meeting_id: UUID,
    tenant_id: UUID,
    started_by: str,
) -> int:
    """Notifie tous les participants qu'une reunion a demarre."""
    return await websocket_manager.send_event(
        meeting_id=meeting_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.MEETING_STARTED,
        data={
            "started_by": started_by,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


async def notify_meeting_ended(
    meeting_id: UUID,
    tenant_id: UUID,
    ended_by: str,
    reason: str = "Meeting ended by host",
) -> int:
    """Notifie tous les participants qu'une reunion est terminee."""
    result = await websocket_manager.send_event(
        meeting_id=meeting_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.MEETING_ENDED,
        data={
            "ended_by": ended_by,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    # Fermer toutes les connexions
    await websocket_manager.close_meeting(meeting_id, tenant_id, reason)

    return result


async def notify_recording_started(
    meeting_id: UUID,
    tenant_id: UUID,
    recording_type: str = "video",
) -> int:
    """Notifie le debut d'un enregistrement."""
    return await websocket_manager.send_event(
        meeting_id=meeting_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.RECORDING_STARTED,
        data={
            "type": recording_type,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


async def notify_recording_stopped(
    meeting_id: UUID,
    tenant_id: UUID,
    recording_type: str = "video",
) -> int:
    """Notifie la fin d'un enregistrement."""
    return await websocket_manager.send_event(
        meeting_id=meeting_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.RECORDING_STOPPED,
        data={
            "type": recording_type,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


async def kick_participant(
    meeting_id: UUID,
    participant_id: UUID,
    tenant_id: UUID,
    reason: str = "Removed by host",
) -> bool:
    """Expulse un participant d'une reunion."""
    # Notifier le participant
    await websocket_manager.send_to_participant(
        meeting_id=meeting_id,
        participant_id=participant_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.PARTICIPANT_KICKED,
        data={"reason": reason},
    )

    # Deconnecter
    result = await websocket_manager.disconnect(
        meeting_id=meeting_id,
        participant_id=participant_id,
        tenant_id=tenant_id,
    )

    # Notifier les autres
    if result:
        conn = websocket_manager.get_connection(meeting_id, participant_id, tenant_id)
        display_name = conn.display_name if conn else "Participant"

        await websocket_manager.broadcast_to_meeting(
            meeting_id=meeting_id,
            tenant_id=tenant_id,
            event_type=WebSocketEventType.PARTICIPANT_KICKED,
            data={
                "participant_id": str(participant_id),
                "display_name": display_name,
                "reason": reason,
            },
        )

    return result


async def mute_participant(
    meeting_id: UUID,
    participant_id: UUID,
    tenant_id: UUID,
    muted_by: str,
) -> bool:
    """Mute un participant (par l'organisateur)."""
    await websocket_manager.update_participant_state(
        meeting_id=meeting_id,
        participant_id=participant_id,
        tenant_id=tenant_id,
        audio_enabled=False,
    )

    # Notifier le participant
    await websocket_manager.send_to_participant(
        meeting_id=meeting_id,
        participant_id=participant_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.MUTE_PARTICIPANT,
        data={"muted_by": muted_by},
    )

    # Notifier tous les autres
    return await websocket_manager.broadcast_to_meeting(
        meeting_id=meeting_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.AUDIO_TOGGLED,
        data={
            "participant_id": str(participant_id),
            "enabled": False,
            "by_host": True,
        },
    ) > 0


async def mute_all(
    meeting_id: UUID,
    tenant_id: UUID,
    muted_by: str,
    exclude_organizers: bool = True,
) -> int:
    """Mute tous les participants."""
    if meeting_id not in websocket_manager._connections:
        return 0

    muted_count = 0
    for participant_id, connection in websocket_manager._connections[meeting_id].items():
        # Exclure les organisateurs si demande
        if exclude_organizers and connection.role in (
            ParticipantRole.ORGANISATEUR,
            ParticipantRole.CO_ORGANISATEUR,
        ):
            continue

        await websocket_manager.update_participant_state(
            meeting_id=meeting_id,
            participant_id=participant_id,
            tenant_id=tenant_id,
            audio_enabled=False,
        )
        muted_count += 1

    # Notifier tous
    await websocket_manager.broadcast_to_meeting(
        meeting_id=meeting_id,
        tenant_id=tenant_id,
        event_type=WebSocketEventType.MUTE_ALL,
        data={"muted_by": muted_by},
    )

    return muted_count
