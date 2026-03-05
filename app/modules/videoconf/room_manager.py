# =============================================================================
# AZALPLUS - LiveKit Room Manager
# =============================================================================
"""
Gestionnaire de rooms LiveKit pour le module de visioconference.

Responsabilites:
- Creation et suppression de rooms LiveKit
- Generation de tokens JWT pour les participants
- Controle des participants (mute, unmute, kick)
- Gestion des enregistrements (egress)

IMPORTANT: Isolation multi-tenant stricte via prefixage des room_name.
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
import yaml

# LiveKit SDK imports
try:
    from livekit import api as livekit_api
    from livekit.api import AccessToken, VideoGrants
    LIVEKIT_AVAILABLE = True
except ImportError:
    LIVEKIT_AVAILABLE = False

logger = structlog.get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class LiveKitConfig:
    """Configuration LiveKit extraite du fichier videoconf.yml."""

    url: str
    api_url: str
    api_key: str
    api_secret: str
    room_prefix: str
    empty_timeout: int
    max_duration: int

    # Limites
    max_participants_per_meeting: int
    max_participants_default: int
    max_duration_hours: int

    # Enregistrement
    recording_enabled: bool
    recording_storage_backend: str
    recording_s3_endpoint: str
    recording_s3_access_key: str
    recording_s3_secret_key: str
    recording_s3_bucket: str
    recording_s3_region: str
    recording_video_codec: str
    recording_video_width: int
    recording_video_height: int
    recording_video_framerate: int
    recording_video_bitrate: int

    # Securite
    participant_token_expiration_hours: int


def _resolve_env_var(value: str) -> str:
    """Resoud les variables d'environnement dans les valeurs YAML.

    Format: ${VAR_NAME} ou ${VAR_NAME:default}
    """
    if not isinstance(value, str):
        return value

    if not value.startswith("${"):
        return value

    # Extraire le nom de variable et la valeur par defaut
    content = value[2:-1]  # Enlever ${ et }

    if ":" in content:
        var_name, default = content.split(":", 1)
    else:
        var_name = content
        default = ""

    return os.environ.get(var_name, default)


def load_livekit_config() -> LiveKitConfig:
    """Charge la configuration LiveKit depuis videoconf.yml."""
    config_path = Path("/home/ubuntu/azalplus/config/videoconf.yml")

    if not config_path.exists():
        logger.warning("videoconf.yml not found, using defaults")
        return LiveKitConfig(
            url="ws://localhost:7880",
            api_url="http://localhost:7880",
            api_key="devkey",
            api_secret="secret",
            room_prefix="azalplus",
            empty_timeout=300,
            max_duration=28800,
            max_participants_per_meeting=500,
            max_participants_default=50,
            max_duration_hours=8,
            recording_enabled=True,
            recording_storage_backend="minio",
            recording_s3_endpoint="localhost:9000",
            recording_s3_access_key="minioadmin",
            recording_s3_secret_key="minioadmin",
            recording_s3_bucket="azalplus-recordings",
            recording_s3_region="us-east-1",
            recording_video_codec="vp8",
            recording_video_width=1920,
            recording_video_height=1080,
            recording_video_framerate=30,
            recording_video_bitrate=3000000,
            participant_token_expiration_hours=8,
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    vc = raw_config.get("videoconf", {})
    lk = vc.get("livekit", {})
    room_config = lk.get("room", {})
    limits = vc.get("limits", {})
    recording = vc.get("recording", {})
    s3 = recording.get("s3", {})
    video_quality = recording.get("video_quality", {})
    security = vc.get("security", {})

    return LiveKitConfig(
        url=_resolve_env_var(lk.get("url", "ws://localhost:7880")),
        api_url=_resolve_env_var(lk.get("api_url", "http://localhost:7880")),
        api_key=_resolve_env_var(lk.get("api_key", "devkey")),
        api_secret=_resolve_env_var(lk.get("api_secret", "secret")),
        room_prefix=room_config.get("prefix", "azalplus"),
        empty_timeout=room_config.get("empty_timeout", 300),
        max_duration=room_config.get("max_duration", 28800),
        max_participants_per_meeting=limits.get("max_participants_per_meeting", 500),
        max_participants_default=limits.get("max_participants_default", 50),
        max_duration_hours=limits.get("max_duration_hours", 8),
        recording_enabled=recording.get("enabled", True),
        recording_storage_backend=_resolve_env_var(recording.get("storage_backend", "minio")),
        recording_s3_endpoint=_resolve_env_var(s3.get("endpoint", "localhost:9000")),
        recording_s3_access_key=_resolve_env_var(s3.get("access_key", "minioadmin")),
        recording_s3_secret_key=_resolve_env_var(s3.get("secret_key", "minioadmin")),
        recording_s3_bucket=_resolve_env_var(s3.get("bucket", "azalplus-recordings")),
        recording_s3_region=_resolve_env_var(s3.get("region", "us-east-1")),
        recording_video_codec=recording.get("video_codec", "vp8"),
        recording_video_width=video_quality.get("width", 1920),
        recording_video_height=video_quality.get("height", 1080),
        recording_video_framerate=video_quality.get("framerate", 30),
        recording_video_bitrate=video_quality.get("bitrate", 3000000),
        participant_token_expiration_hours=security.get("participant_token_expiration_hours", 8),
    )


# =============================================================================
# Enums
# =============================================================================
class TrackType(str, Enum):
    """Types de tracks media."""
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN_SHARE = "screen_share"


class RecordingState(str, Enum):
    """Etats d'un enregistrement."""
    STARTING = "starting"
    ACTIVE = "active"
    ENDING = "ending"
    COMPLETE = "complete"
    FAILED = "failed"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class RoomInfo:
    """Informations sur une room LiveKit."""
    room_name: str
    room_sid: str
    num_participants: int
    max_participants: int
    creation_time: datetime
    metadata: Optional[str] = None


@dataclass
class ParticipantInfo:
    """Informations sur un participant."""
    participant_id: str
    name: str
    is_publisher: bool
    joined_at: datetime
    tracks: List[str]


@dataclass
class RoomOptions:
    """Options de creation de room."""
    max_participants: Optional[int] = None
    empty_timeout: Optional[int] = None
    metadata: Optional[str] = None


@dataclass
class ParticipantPermissions:
    """Permissions d'un participant."""
    can_publish: bool = True
    can_subscribe: bool = True
    can_publish_data: bool = True
    can_update_metadata: bool = False
    hidden: bool = False
    recorder: bool = False


@dataclass
class RecordingOptions:
    """Options d'enregistrement."""
    output_format: str = "mp4"
    audio_only: bool = False
    video_only: bool = False
    custom_base_url: Optional[str] = None


@dataclass
class RecordingInfo:
    """Informations sur un enregistrement."""
    egress_id: str
    room_name: str
    status: RecordingState
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    file_url: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# Exceptions
# =============================================================================
class LiveKitError(Exception):
    """Erreur generique LiveKit."""
    pass


class RoomNotFoundError(LiveKitError):
    """Room non trouvee."""
    pass


class ParticipantNotFoundError(LiveKitError):
    """Participant non trouve."""
    pass


class RecordingError(LiveKitError):
    """Erreur d'enregistrement."""
    pass


class TenantIsolationError(LiveKitError):
    """Violation de l'isolation tenant."""
    pass


# =============================================================================
# LiveKit Room Manager
# =============================================================================
class LiveKitRoomManager:
    """
    Gestionnaire de rooms LiveKit avec isolation multi-tenant.

    Toutes les rooms sont prefixees avec le tenant_id pour garantir
    l'isolation des donnees entre tenants.

    Usage:
        manager = LiveKitRoomManager(tenant_id=UUID("..."))
        room_name, room_sid = await manager.create_room(meeting_id, options)
        token = await manager.create_participant_token(room_name, participant_id, name, role)
    """

    def __init__(self, tenant_id: UUID):
        """
        Initialise le manager LiveKit.

        Args:
            tenant_id: UUID du tenant (OBLIGATOIRE pour isolation)
        """
        if not tenant_id:
            raise ValueError("tenant_id is required for tenant isolation")

        self.tenant_id = tenant_id
        self.config = load_livekit_config()

        self._log = logger.bind(
            tenant_id=str(tenant_id),
            component="livekit_room_manager"
        )

        # Initialiser l'API LiveKit
        if LIVEKIT_AVAILABLE:
            self._api = livekit_api.LiveKitAPI(
                url=self.config.api_url,
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
            )
            self._log.info("LiveKit API initialized", api_url=self.config.api_url)
        else:
            self._api = None
            self._log.warning("LiveKit SDK not available - running in mock mode")

    # -------------------------------------------------------------------------
    # Room Name Generation (Tenant Isolation)
    # -------------------------------------------------------------------------
    def _generate_room_name(self, meeting_id: UUID) -> str:
        """
        Genere un nom de room avec prefixe tenant.

        Format: tenant_{tenant_id}_meeting_{meeting_id}

        Ceci garantit l'isolation multi-tenant car:
        1. Chaque tenant a ses propres rooms
        2. Un tenant ne peut pas acceder aux rooms d'un autre tenant
        3. Le prefixe permet de filtrer les rooms par tenant
        """
        return f"tenant_{self.tenant_id}_meeting_{meeting_id}"

    def _extract_meeting_id_from_room_name(self, room_name: str) -> Optional[UUID]:
        """Extrait le meeting_id d'un nom de room."""
        try:
            # Format: tenant_{tenant_id}_meeting_{meeting_id}
            parts = room_name.split("_")
            if len(parts) >= 4 and parts[0] == "tenant" and parts[2] == "meeting":
                return UUID(parts[3])
        except (ValueError, IndexError):
            pass
        return None

    def _validate_room_ownership(self, room_name: str) -> bool:
        """
        Verifie qu'une room appartient a ce tenant.

        SECURITE: Empeche un tenant d'acceder aux rooms d'un autre tenant.
        """
        expected_prefix = f"tenant_{self.tenant_id}_"
        return room_name.startswith(expected_prefix)

    def _ensure_room_ownership(self, room_name: str) -> None:
        """Leve une exception si la room n'appartient pas au tenant."""
        if not self._validate_room_ownership(room_name):
            self._log.error(
                "Tenant isolation violation attempted",
                room_name=room_name,
                expected_prefix=f"tenant_{self.tenant_id}_"
            )
            raise TenantIsolationError(
                f"Room {room_name} does not belong to tenant {self.tenant_id}"
            )

    # -------------------------------------------------------------------------
    # Room Management
    # -------------------------------------------------------------------------
    async def create_room(
        self,
        meeting_id: UUID,
        options: Optional[RoomOptions] = None
    ) -> tuple[str, str]:
        """
        Cree une room LiveKit pour une reunion.

        Args:
            meeting_id: UUID de la reunion
            options: Options de configuration de la room

        Returns:
            Tuple (room_name, room_sid)

        Raises:
            LiveKitError: Si la creation echoue
        """
        room_name = self._generate_room_name(meeting_id)
        options = options or RoomOptions()

        self._log.info(
            "Creating LiveKit room",
            room_name=room_name,
            meeting_id=str(meeting_id),
            max_participants=options.max_participants
        )

        try:
            if not self._api:
                # Mode mock pour tests sans LiveKit
                room_sid = f"mock_sid_{meeting_id}"
                self._log.debug("Mock room created", room_name=room_name, room_sid=room_sid)
                return room_name, room_sid

            # Creer la room via l'API LiveKit
            room = await self._api.room.create_room(
                livekit_api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=options.empty_timeout or self.config.empty_timeout,
                    max_participants=options.max_participants or self.config.max_participants_default,
                    metadata=options.metadata,
                )
            )

            self._log.info(
                "LiveKit room created",
                room_name=room_name,
                room_sid=room.sid,
                max_participants=room.max_participants
            )

            return room_name, room.sid

        except Exception as e:
            self._log.error(
                "Failed to create LiveKit room",
                room_name=room_name,
                error=str(e)
            )
            raise LiveKitError(f"Failed to create room: {e}") from e

    async def delete_room(self, room_name: str) -> bool:
        """
        Supprime une room LiveKit.

        Args:
            room_name: Nom de la room a supprimer

        Returns:
            True si supprimee, False si n'existait pas

        Raises:
            TenantIsolationError: Si la room n'appartient pas au tenant
        """
        self._ensure_room_ownership(room_name)

        self._log.info("Deleting LiveKit room", room_name=room_name)

        try:
            if not self._api:
                self._log.debug("Mock room deleted", room_name=room_name)
                return True

            await self._api.room.delete_room(
                livekit_api.DeleteRoomRequest(room=room_name)
            )

            self._log.info("LiveKit room deleted", room_name=room_name)
            return True

        except Exception as e:
            # Room n'existe pas
            if "not found" in str(e).lower():
                self._log.warning("Room not found for deletion", room_name=room_name)
                return False

            self._log.error(
                "Failed to delete LiveKit room",
                room_name=room_name,
                error=str(e)
            )
            raise LiveKitError(f"Failed to delete room: {e}") from e

    async def list_rooms(self) -> List[RoomInfo]:
        """
        Liste toutes les rooms du tenant.

        Returns:
            Liste des rooms appartenant a ce tenant
        """
        self._log.debug("Listing rooms for tenant")

        try:
            if not self._api:
                self._log.debug("Mock: returning empty room list")
                return []

            response = await self._api.room.list_rooms(
                livekit_api.ListRoomsRequest()
            )

            # Filtrer par tenant (isolation)
            tenant_prefix = f"tenant_{self.tenant_id}_"
            tenant_rooms = []

            for room in response.rooms:
                if room.name.startswith(tenant_prefix):
                    tenant_rooms.append(RoomInfo(
                        room_name=room.name,
                        room_sid=room.sid,
                        num_participants=room.num_participants,
                        max_participants=room.max_participants,
                        creation_time=datetime.fromtimestamp(room.creation_time),
                        metadata=room.metadata,
                    ))

            self._log.info(
                "Listed tenant rooms",
                count=len(tenant_rooms),
                total_rooms=len(response.rooms)
            )

            return tenant_rooms

        except Exception as e:
            self._log.error("Failed to list rooms", error=str(e))
            raise LiveKitError(f"Failed to list rooms: {e}") from e

    async def get_room_info(self, room_name: str) -> Optional[RoomInfo]:
        """
        Obtient les informations d'une room.

        Args:
            room_name: Nom de la room

        Returns:
            RoomInfo ou None si la room n'existe pas

        Raises:
            TenantIsolationError: Si la room n'appartient pas au tenant
        """
        self._ensure_room_ownership(room_name)

        self._log.debug("Getting room info", room_name=room_name)

        try:
            if not self._api:
                return None

            rooms = await self.list_rooms()
            for room in rooms:
                if room.room_name == room_name:
                    return room

            return None

        except Exception as e:
            self._log.error(
                "Failed to get room info",
                room_name=room_name,
                error=str(e)
            )
            raise LiveKitError(f"Failed to get room info: {e}") from e

    # -------------------------------------------------------------------------
    # Token Generation
    # -------------------------------------------------------------------------
    async def create_participant_token(
        self,
        room_name: str,
        participant_id: UUID,
        name: str,
        role: str = "participant",
        permissions: Optional[ParticipantPermissions] = None
    ) -> str:
        """
        Genere un token JWT pour un participant.

        Args:
            room_name: Nom de la room
            participant_id: UUID du participant
            name: Nom affiche du participant
            role: Role (participant, presenter, moderator)
            permissions: Permissions personnalisees

        Returns:
            Token JWT LiveKit

        Raises:
            TenantIsolationError: Si la room n'appartient pas au tenant
        """
        self._ensure_room_ownership(room_name)

        permissions = permissions or self._get_default_permissions(role)

        self._log.debug(
            "Creating participant token",
            room_name=room_name,
            participant_id=str(participant_id),
            name=name,
            role=role
        )

        try:
            if not LIVEKIT_AVAILABLE:
                # Token mock pour tests
                return f"mock_token_{participant_id}_{int(time.time())}"

            # Creer le token avec les permissions
            token = AccessToken(
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
            )

            token.identity = str(participant_id)
            token.name = name
            token.ttl = timedelta(hours=self.config.participant_token_expiration_hours)

            # Definir les grants video
            grants = VideoGrants(
                room=room_name,
                room_join=True,
                can_publish=permissions.can_publish,
                can_subscribe=permissions.can_subscribe,
                can_publish_data=permissions.can_publish_data,
                can_update_own_metadata=permissions.can_update_metadata,
                hidden=permissions.hidden,
                recorder=permissions.recorder,
            )
            token.video_grants = grants

            jwt_token = token.to_jwt()

            self._log.info(
                "Participant token created",
                room_name=room_name,
                participant_id=str(participant_id),
                role=role,
                ttl_hours=self.config.participant_token_expiration_hours
            )

            return jwt_token

        except Exception as e:
            self._log.error(
                "Failed to create participant token",
                room_name=room_name,
                participant_id=str(participant_id),
                error=str(e)
            )
            raise LiveKitError(f"Failed to create token: {e}") from e

    async def create_organizer_token(
        self,
        room_name: str,
        user_id: UUID,
        name: str
    ) -> str:
        """
        Genere un token JWT avec permissions admin pour l'organisateur.

        L'organisateur a des permissions supplementaires:
        - room_admin: Peut gerer la room
        - room_create: Peut creer des rooms
        - Toutes les permissions standard

        Args:
            room_name: Nom de la room
            user_id: UUID de l'utilisateur organisateur
            name: Nom affiche

        Returns:
            Token JWT LiveKit avec permissions admin
        """
        self._ensure_room_ownership(room_name)

        self._log.debug(
            "Creating organizer token",
            room_name=room_name,
            user_id=str(user_id),
            name=name
        )

        try:
            if not LIVEKIT_AVAILABLE:
                return f"mock_admin_token_{user_id}_{int(time.time())}"

            token = AccessToken(
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
            )

            token.identity = str(user_id)
            token.name = name
            token.ttl = timedelta(hours=self.config.participant_token_expiration_hours)

            # Grants admin complets
            grants = VideoGrants(
                room=room_name,
                room_join=True,
                room_admin=True,
                room_create=True,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_update_own_metadata=True,
                hidden=False,
                recorder=False,
            )
            token.video_grants = grants

            jwt_token = token.to_jwt()

            self._log.info(
                "Organizer token created",
                room_name=room_name,
                user_id=str(user_id),
                is_admin=True
            )

            return jwt_token

        except Exception as e:
            self._log.error(
                "Failed to create organizer token",
                room_name=room_name,
                user_id=str(user_id),
                error=str(e)
            )
            raise LiveKitError(f"Failed to create organizer token: {e}") from e

    def _get_default_permissions(self, role: str) -> ParticipantPermissions:
        """Retourne les permissions par defaut selon le role."""
        if role == "moderator":
            return ParticipantPermissions(
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_update_metadata=True,
                hidden=False,
                recorder=False,
            )
        elif role == "presenter":
            return ParticipantPermissions(
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_update_metadata=False,
                hidden=False,
                recorder=False,
            )
        elif role == "viewer":
            return ParticipantPermissions(
                can_publish=False,
                can_subscribe=True,
                can_publish_data=False,
                can_update_metadata=False,
                hidden=False,
                recorder=False,
            )
        else:  # participant
            return ParticipantPermissions(
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_update_metadata=False,
                hidden=False,
                recorder=False,
            )

    # -------------------------------------------------------------------------
    # Participant Controls
    # -------------------------------------------------------------------------
    async def mute_participant(
        self,
        room_name: str,
        participant_id: str,
        track_type: TrackType
    ) -> bool:
        """
        Mute un participant.

        Args:
            room_name: Nom de la room
            participant_id: ID du participant
            track_type: Type de track a muter (audio, video, screen_share)

        Returns:
            True si succes
        """
        self._ensure_room_ownership(room_name)

        self._log.info(
            "Muting participant",
            room_name=room_name,
            participant_id=participant_id,
            track_type=track_type.value
        )

        try:
            if not self._api:
                return True

            await self._api.room.mute_published_track(
                livekit_api.MuteRoomTrackRequest(
                    room=room_name,
                    identity=participant_id,
                    muted=True,
                    track_sid=None,  # Mute all tracks of type
                )
            )

            self._log.info(
                "Participant muted",
                room_name=room_name,
                participant_id=participant_id,
                track_type=track_type.value
            )
            return True

        except Exception as e:
            self._log.error(
                "Failed to mute participant",
                room_name=room_name,
                participant_id=participant_id,
                error=str(e)
            )
            raise LiveKitError(f"Failed to mute participant: {e}") from e

    async def unmute_participant(
        self,
        room_name: str,
        participant_id: str,
        track_type: TrackType
    ) -> bool:
        """
        Unmute un participant.

        Note: Cette operation ne force pas le unmute cote client,
        elle permet simplement au participant de publier a nouveau.
        """
        self._ensure_room_ownership(room_name)

        self._log.info(
            "Unmuting participant",
            room_name=room_name,
            participant_id=participant_id,
            track_type=track_type.value
        )

        try:
            if not self._api:
                return True

            await self._api.room.mute_published_track(
                livekit_api.MuteRoomTrackRequest(
                    room=room_name,
                    identity=participant_id,
                    muted=False,
                    track_sid=None,
                )
            )

            self._log.info(
                "Participant unmuted",
                room_name=room_name,
                participant_id=participant_id,
                track_type=track_type.value
            )
            return True

        except Exception as e:
            self._log.error(
                "Failed to unmute participant",
                room_name=room_name,
                participant_id=participant_id,
                error=str(e)
            )
            raise LiveKitError(f"Failed to unmute participant: {e}") from e

    async def remove_participant(
        self,
        room_name: str,
        participant_id: str
    ) -> bool:
        """
        Retire un participant de la room.

        Args:
            room_name: Nom de la room
            participant_id: ID du participant a retirer

        Returns:
            True si retire, False si n'existait pas
        """
        self._ensure_room_ownership(room_name)

        self._log.info(
            "Removing participant",
            room_name=room_name,
            participant_id=participant_id
        )

        try:
            if not self._api:
                return True

            await self._api.room.remove_participant(
                livekit_api.RoomParticipantIdentity(
                    room=room_name,
                    identity=participant_id,
                )
            )

            self._log.info(
                "Participant removed",
                room_name=room_name,
                participant_id=participant_id
            )
            return True

        except Exception as e:
            if "not found" in str(e).lower():
                self._log.warning(
                    "Participant not found for removal",
                    room_name=room_name,
                    participant_id=participant_id
                )
                return False

            self._log.error(
                "Failed to remove participant",
                room_name=room_name,
                participant_id=participant_id,
                error=str(e)
            )
            raise LiveKitError(f"Failed to remove participant: {e}") from e

    async def update_participant_permissions(
        self,
        room_name: str,
        participant_id: str,
        permissions: ParticipantPermissions
    ) -> bool:
        """
        Met a jour les permissions d'un participant.

        Args:
            room_name: Nom de la room
            participant_id: ID du participant
            permissions: Nouvelles permissions

        Returns:
            True si succes
        """
        self._ensure_room_ownership(room_name)

        self._log.info(
            "Updating participant permissions",
            room_name=room_name,
            participant_id=participant_id,
            can_publish=permissions.can_publish,
            can_subscribe=permissions.can_subscribe
        )

        try:
            if not self._api:
                return True

            await self._api.room.update_participant(
                livekit_api.UpdateParticipantRequest(
                    room=room_name,
                    identity=participant_id,
                    permission=livekit_api.ParticipantPermission(
                        can_publish=permissions.can_publish,
                        can_subscribe=permissions.can_subscribe,
                        can_publish_data=permissions.can_publish_data,
                        hidden=permissions.hidden,
                        recorder=permissions.recorder,
                    )
                )
            )

            self._log.info(
                "Participant permissions updated",
                room_name=room_name,
                participant_id=participant_id
            )
            return True

        except Exception as e:
            self._log.error(
                "Failed to update participant permissions",
                room_name=room_name,
                participant_id=participant_id,
                error=str(e)
            )
            raise LiveKitError(f"Failed to update permissions: {e}") from e

    async def list_participants(self, room_name: str) -> List[ParticipantInfo]:
        """
        Liste les participants d'une room.

        Args:
            room_name: Nom de la room

        Returns:
            Liste des participants
        """
        self._ensure_room_ownership(room_name)

        self._log.debug("Listing participants", room_name=room_name)

        try:
            if not self._api:
                return []

            response = await self._api.room.list_participants(
                livekit_api.ListParticipantsRequest(room=room_name)
            )

            participants = []
            for p in response.participants:
                tracks = [t.sid for t in p.tracks]
                participants.append(ParticipantInfo(
                    participant_id=p.identity,
                    name=p.name,
                    is_publisher=len([t for t in p.tracks if t.type in (1, 2)]) > 0,  # Audio or Video
                    joined_at=datetime.fromtimestamp(p.joined_at),
                    tracks=tracks,
                ))

            self._log.info(
                "Listed participants",
                room_name=room_name,
                count=len(participants)
            )

            return participants

        except Exception as e:
            self._log.error(
                "Failed to list participants",
                room_name=room_name,
                error=str(e)
            )
            raise LiveKitError(f"Failed to list participants: {e}") from e

    # -------------------------------------------------------------------------
    # Recording (Egress)
    # -------------------------------------------------------------------------
    async def start_recording(
        self,
        room_name: str,
        options: Optional[RecordingOptions] = None
    ) -> str:
        """
        Demarre l'enregistrement d'une room.

        Args:
            room_name: Nom de la room
            options: Options d'enregistrement

        Returns:
            egress_id pour suivi

        Raises:
            RecordingError: Si l'enregistrement echoue
            TenantIsolationError: Si la room n'appartient pas au tenant
        """
        self._ensure_room_ownership(room_name)

        if not self.config.recording_enabled:
            raise RecordingError("Recording is disabled in configuration")

        options = options or RecordingOptions()

        self._log.info(
            "Starting recording",
            room_name=room_name,
            output_format=options.output_format
        )

        try:
            if not self._api:
                egress_id = f"mock_egress_{room_name}_{int(time.time())}"
                self._log.debug("Mock recording started", egress_id=egress_id)
                return egress_id

            # Construire le chemin de sortie S3
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            meeting_id = self._extract_meeting_id_from_room_name(room_name)
            filename = f"recordings/{self.tenant_id}/{meeting_id}/{timestamp}.{options.output_format}"

            # Configuration S3 output
            s3_output = livekit_api.S3Upload(
                access_key=self.config.recording_s3_access_key,
                secret=self.config.recording_s3_secret_key,
                region=self.config.recording_s3_region,
                endpoint=self.config.recording_s3_endpoint,
                bucket=self.config.recording_s3_bucket,
                filepath=filename,
            )

            # Options de sortie video
            file_output = livekit_api.EncodedFileOutput(
                file_type=livekit_api.EncodedFileType.MP4 if options.output_format == "mp4" else livekit_api.EncodedFileType.OGG,
                s3=s3_output,
            )

            # Demarrer l'egress
            egress_info = await self._api.egress.start_room_composite_egress(
                livekit_api.RoomCompositeEgressRequest(
                    room_name=room_name,
                    file=file_output,
                    audio_only=options.audio_only,
                    video_only=options.video_only,
                )
            )

            egress_id = egress_info.egress_id

            self._log.info(
                "Recording started",
                room_name=room_name,
                egress_id=egress_id,
                output_path=filename
            )

            return egress_id

        except Exception as e:
            self._log.error(
                "Failed to start recording",
                room_name=room_name,
                error=str(e)
            )
            raise RecordingError(f"Failed to start recording: {e}") from e

    async def stop_recording(self, egress_id: str) -> RecordingInfo:
        """
        Arrete un enregistrement.

        Args:
            egress_id: ID de l'egress a arreter

        Returns:
            RecordingInfo avec le statut final
        """
        self._log.info("Stopping recording", egress_id=egress_id)

        try:
            if not self._api:
                return RecordingInfo(
                    egress_id=egress_id,
                    room_name="mock_room",
                    status=RecordingState.COMPLETE,
                    ended_at=datetime.now(),
                )

            egress_info = await self._api.egress.stop_egress(
                livekit_api.StopEgressRequest(egress_id=egress_id)
            )

            self._log.info(
                "Recording stopped",
                egress_id=egress_id,
                status=egress_info.status
            )

            return self._egress_to_recording_info(egress_info)

        except Exception as e:
            self._log.error(
                "Failed to stop recording",
                egress_id=egress_id,
                error=str(e)
            )
            raise RecordingError(f"Failed to stop recording: {e}") from e

    async def get_recording_status(self, egress_id: str) -> RecordingInfo:
        """
        Obtient le statut d'un enregistrement.

        Args:
            egress_id: ID de l'egress

        Returns:
            RecordingInfo avec le statut actuel
        """
        self._log.debug("Getting recording status", egress_id=egress_id)

        try:
            if not self._api:
                return RecordingInfo(
                    egress_id=egress_id,
                    room_name="mock_room",
                    status=RecordingState.ACTIVE,
                )

            # Lister les egress pour trouver celui qu'on cherche
            egress_list = await self._api.egress.list_egress(
                livekit_api.ListEgressRequest(egress_id=egress_id)
            )

            if not egress_list.items:
                raise RecordingError(f"Recording {egress_id} not found")

            egress_info = egress_list.items[0]

            return self._egress_to_recording_info(egress_info)

        except RecordingError:
            raise
        except Exception as e:
            self._log.error(
                "Failed to get recording status",
                egress_id=egress_id,
                error=str(e)
            )
            raise RecordingError(f"Failed to get recording status: {e}") from e

    def _egress_to_recording_info(self, egress_info: Any) -> RecordingInfo:
        """Convertit un EgressInfo LiveKit en RecordingInfo."""
        # Mapper le statut LiveKit vers notre enum
        status_map = {
            0: RecordingState.STARTING,  # EGRESS_STARTING
            1: RecordingState.ACTIVE,    # EGRESS_ACTIVE
            2: RecordingState.ENDING,    # EGRESS_ENDING
            3: RecordingState.COMPLETE,  # EGRESS_COMPLETE
            4: RecordingState.FAILED,    # EGRESS_FAILED
        }

        status = status_map.get(egress_info.status, RecordingState.FAILED)

        # Extraire l'URL du fichier si disponible
        file_url = None
        if hasattr(egress_info, 'file_results') and egress_info.file_results:
            file_url = egress_info.file_results[0].location if egress_info.file_results else None

        return RecordingInfo(
            egress_id=egress_info.egress_id,
            room_name=egress_info.room_name,
            status=status,
            started_at=datetime.fromtimestamp(egress_info.started_at) if egress_info.started_at else None,
            ended_at=datetime.fromtimestamp(egress_info.ended_at) if egress_info.ended_at else None,
            file_url=file_url,
            error=egress_info.error if hasattr(egress_info, 'error') else None,
        )

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifie la connexion au serveur LiveKit.

        Returns:
            Dict avec status et details
        """
        try:
            if not self._api:
                return {
                    "status": "mock",
                    "message": "LiveKit SDK not available - running in mock mode",
                    "tenant_id": str(self.tenant_id),
                }

            # Tenter de lister les rooms pour verifier la connexion
            await self._api.room.list_rooms(livekit_api.ListRoomsRequest())

            return {
                "status": "ok",
                "api_url": self.config.api_url,
                "tenant_id": str(self.tenant_id),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "api_url": self.config.api_url,
                "tenant_id": str(self.tenant_id),
            }
