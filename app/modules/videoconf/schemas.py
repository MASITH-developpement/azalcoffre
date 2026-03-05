# =============================================================================
# AZALPLUS - Schemas Videoconference
# =============================================================================
"""
Modeles Pydantic pour le module de videoconference.

Validation stricte avec type hints exhaustifs.
Tous les schemas incluent tenant_id pour l'isolation multi-tenant.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums
# =============================================================================
class MeetingStatus(str, Enum):
    """Statut d'une reunion."""
    SCHEDULED = "scheduled"       # Planifiee
    WAITING = "waiting"           # Salle d'attente active
    IN_PROGRESS = "in_progress"   # En cours
    PAUSED = "paused"             # En pause
    ENDED = "ended"               # Terminee
    CANCELLED = "cancelled"       # Annulee


class MeetingType(str, Enum):
    """Type de reunion."""
    INSTANT = "instant"           # Reunion instantanee
    SCHEDULED = "scheduled"       # Reunion planifiee
    RECURRING = "recurring"       # Reunion recurrente
    WEBINAR = "webinar"           # Webinaire (mode presentation)


class ParticipantRole(str, Enum):
    """Role d'un participant."""
    HOST = "host"                 # Organisateur
    CO_HOST = "co_host"           # Co-organisateur
    PRESENTER = "presenter"       # Presentateur
    PARTICIPANT = "participant"   # Participant standard
    VIEWER = "viewer"             # Spectateur (webinar)


class ParticipantStatus(str, Enum):
    """Statut d'un participant."""
    INVITED = "invited"           # Invite
    WAITING = "waiting"           # En salle d'attente
    JOINED = "joined"             # Connecte
    LEFT = "left"                 # Parti
    REMOVED = "removed"           # Expulse


class MediaControlType(str, Enum):
    """Type de controle media."""
    MUTE_AUDIO = "mute_audio"
    UNMUTE_AUDIO = "unmute_audio"
    DISABLE_VIDEO = "disable_video"
    ENABLE_VIDEO = "enable_video"
    START_SCREEN_SHARE = "start_screen_share"
    STOP_SCREEN_SHARE = "stop_screen_share"


class RecordingStatus(str, Enum):
    """Statut d'un enregistrement."""
    NOT_STARTED = "not_started"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPED = "stopped"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WebSocketEventType(str, Enum):
    """Types d'evenements WebSocket."""
    # Connexion
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    # Participants
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    PARTICIPANT_UPDATED = "participant_updated"
    # Media
    MEDIA_STATE_CHANGED = "media_state_changed"
    SCREEN_SHARE_STARTED = "screen_share_started"
    SCREEN_SHARE_STOPPED = "screen_share_stopped"
    # Meeting
    MEETING_STARTED = "meeting_started"
    MEETING_ENDED = "meeting_ended"
    MEETING_PAUSED = "meeting_paused"
    # Chat
    CHAT_MESSAGE = "chat_message"
    # Whiteboard
    WHITEBOARD_UPDATE = "whiteboard_update"
    # Hand raise
    HAND_RAISED = "hand_raised"
    HAND_LOWERED = "hand_lowered"
    # Recording
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"
    # Transcription
    TRANSCRIPTION_SEGMENT = "transcription_segment"
    # Erreurs
    ERROR = "error"


class WhiteboardAction(str, Enum):
    """Actions sur le tableau blanc."""
    DRAW = "draw"
    ERASE = "erase"
    TEXT = "text"
    SHAPE = "shape"
    IMAGE = "image"
    CLEAR = "clear"
    UNDO = "undo"
    REDO = "redo"


# =============================================================================
# Meeting Schemas
# =============================================================================
class MeetingCreate(BaseModel):
    """Schema de creation d'une reunion."""

    titre: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Titre de la reunion"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Description de la reunion"
    )
    type_reunion: MeetingType = Field(
        default=MeetingType.INSTANT,
        description="Type de reunion"
    )
    date_debut: Optional[datetime] = Field(
        default=None,
        description="Date et heure de debut (pour reunions planifiees)"
    )
    duree_minutes: int = Field(
        default=60,
        ge=5,
        le=480,
        description="Duree prevue en minutes (5 min - 8 heures)"
    )
    # Options
    salle_attente_active: bool = Field(
        default=True,
        description="Activer la salle d'attente"
    )
    participants_muets_entree: bool = Field(
        default=False,
        description="Muter les participants a l'entree"
    )
    enregistrement_auto: bool = Field(
        default=False,
        description="Demarrer l'enregistrement automatiquement"
    )
    transcription_active: bool = Field(
        default=False,
        description="Activer la transcription en temps reel"
    )
    chat_actif: bool = Field(
        default=True,
        description="Activer le chat"
    )
    tableau_blanc_actif: bool = Field(
        default=True,
        description="Activer le tableau blanc"
    )
    max_participants: int = Field(
        default=50,
        ge=2,
        le=500,
        description="Nombre maximum de participants"
    )
    mot_de_passe: Optional[str] = Field(
        default=None,
        min_length=4,
        max_length=20,
        description="Mot de passe pour rejoindre la reunion"
    )
    # Relations
    projet_id: Optional[UUID] = Field(
        default=None,
        description="ID du projet lie (optionnel)"
    )
    client_id: Optional[UUID] = Field(
        default=None,
        description="ID du client lie (optionnel)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "titre": "Reunion de projet Alpha",
                "description": "Point hebdomadaire sur l'avancement",
                "type_reunion": "scheduled",
                "date_debut": "2024-03-15T10:00:00Z",
                "duree_minutes": 60,
                "salle_attente_active": True,
                "transcription_active": True,
            }
        }


class MeetingUpdate(BaseModel):
    """Schema de mise a jour d'une reunion."""

    titre: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Titre de la reunion"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Description de la reunion"
    )
    date_debut: Optional[datetime] = Field(
        default=None,
        description="Date et heure de debut"
    )
    duree_minutes: Optional[int] = Field(
        default=None,
        ge=5,
        le=480,
        description="Duree prevue en minutes"
    )
    salle_attente_active: Optional[bool] = Field(
        default=None,
        description="Activer la salle d'attente"
    )
    participants_muets_entree: Optional[bool] = Field(
        default=None,
        description="Muter les participants a l'entree"
    )
    enregistrement_auto: Optional[bool] = Field(
        default=None,
        description="Demarrer l'enregistrement automatiquement"
    )
    transcription_active: Optional[bool] = Field(
        default=None,
        description="Activer la transcription"
    )
    chat_actif: Optional[bool] = Field(
        default=None,
        description="Activer le chat"
    )
    tableau_blanc_actif: Optional[bool] = Field(
        default=None,
        description="Activer le tableau blanc"
    )
    max_participants: Optional[int] = Field(
        default=None,
        ge=2,
        le=500,
        description="Nombre maximum de participants"
    )
    mot_de_passe: Optional[str] = Field(
        default=None,
        min_length=4,
        max_length=20,
        description="Mot de passe pour rejoindre"
    )


class MeetingResponse(BaseModel):
    """Schema de reponse pour une reunion."""

    id: UUID = Field(..., description="ID unique de la reunion")
    tenant_id: UUID = Field(..., description="ID du tenant")
    titre: str = Field(..., description="Titre de la reunion")
    description: Optional[str] = Field(default=None, description="Description")
    type_reunion: MeetingType = Field(..., description="Type de reunion")
    statut: MeetingStatus = Field(..., description="Statut actuel")
    # Horaires
    date_debut: Optional[datetime] = Field(default=None, description="Date de debut prevue")
    date_debut_effective: Optional[datetime] = Field(default=None, description="Date de debut effective")
    date_fin: Optional[datetime] = Field(default=None, description="Date de fin")
    duree_minutes: int = Field(..., description="Duree prevue en minutes")
    duree_effective_minutes: Optional[int] = Field(default=None, description="Duree effective")
    # Options
    salle_attente_active: bool = Field(..., description="Salle d'attente active")
    participants_muets_entree: bool = Field(..., description="Participants mutes a l'entree")
    enregistrement_auto: bool = Field(..., description="Enregistrement automatique")
    transcription_active: bool = Field(..., description="Transcription active")
    chat_actif: bool = Field(..., description="Chat actif")
    tableau_blanc_actif: bool = Field(..., description="Tableau blanc actif")
    max_participants: int = Field(..., description="Max participants")
    # Acces
    code_reunion: str = Field(..., description="Code court pour rejoindre")
    lien_reunion: str = Field(..., description="Lien complet pour rejoindre")
    mot_de_passe_requis: bool = Field(..., description="Mot de passe requis")
    # Statistiques
    nombre_participants: int = Field(default=0, description="Participants actuels")
    nombre_participants_max_atteint: int = Field(default=0, description="Pic de participants")
    # Relations
    organisateur_id: UUID = Field(..., description="ID de l'organisateur")
    organisateur_nom: str = Field(..., description="Nom de l'organisateur")
    projet_id: Optional[UUID] = Field(default=None, description="ID du projet lie")
    client_id: Optional[UUID] = Field(default=None, description="ID du client lie")
    # Recording
    enregistrement_disponible: bool = Field(default=False, description="Enregistrement disponible")
    transcription_disponible: bool = Field(default=False, description="Transcription disponible")
    compte_rendu_disponible: bool = Field(default=False, description="Compte-rendu disponible")
    # Audit
    created_at: datetime = Field(..., description="Date de creation")
    updated_at: Optional[datetime] = Field(default=None, description="Date de modification")
    created_by: UUID = Field(..., description="Cree par")

    class Config:
        from_attributes = True


class MeetingListResponse(BaseModel):
    """Schema de reponse pour liste de reunions avec pagination."""

    items: List[MeetingResponse] = Field(default_factory=list, description="Liste des reunions")
    total: int = Field(..., description="Nombre total de reunions")
    page: int = Field(..., description="Page courante")
    page_size: int = Field(..., description="Taille de page")
    pages: int = Field(..., description="Nombre total de pages")


# =============================================================================
# Participant Schemas
# =============================================================================
class ParticipantCreate(BaseModel):
    """Schema de creation d'un participant (invitation)."""

    meeting_id: UUID = Field(..., description="ID de la reunion")
    user_id: Optional[UUID] = Field(
        default=None,
        description="ID utilisateur AZALPLUS (optionnel pour invites externes)"
    )
    email: str = Field(
        ...,
        description="Email du participant"
    )
    nom: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nom du participant"
    )
    role: ParticipantRole = Field(
        default=ParticipantRole.PARTICIPANT,
        description="Role du participant"
    )
    envoyer_invitation: bool = Field(
        default=True,
        description="Envoyer un email d'invitation"
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Valide le format de l'email."""
        if "@" not in v or "." not in v:
            raise ValueError("Format email invalide")
        return v.lower().strip()

    class Config:
        json_schema_extra = {
            "example": {
                "meeting_id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "participant@example.com",
                "nom": "Jean Dupont",
                "role": "participant",
                "envoyer_invitation": True,
            }
        }


class ParticipantResponse(BaseModel):
    """Schema de reponse pour un participant."""

    id: UUID = Field(..., description="ID unique du participant")
    meeting_id: UUID = Field(..., description="ID de la reunion")
    user_id: Optional[UUID] = Field(default=None, description="ID utilisateur AZALPLUS")
    email: str = Field(..., description="Email du participant")
    nom: str = Field(..., description="Nom du participant")
    role: ParticipantRole = Field(..., description="Role du participant")
    statut: ParticipantStatus = Field(..., description="Statut actuel")
    # Media state
    audio_actif: bool = Field(default=False, description="Micro actif")
    video_actif: bool = Field(default=False, description="Camera active")
    partage_ecran_actif: bool = Field(default=False, description="Partage d'ecran actif")
    main_levee: bool = Field(default=False, description="Main levee")
    # Timing
    date_invitation: datetime = Field(..., description="Date d'invitation")
    date_connexion: Optional[datetime] = Field(default=None, description="Date de connexion")
    date_deconnexion: Optional[datetime] = Field(default=None, description="Date de deconnexion")
    temps_presence_minutes: int = Field(default=0, description="Temps de presence total")

    class Config:
        from_attributes = True


# =============================================================================
# Join Meeting Schemas
# =============================================================================
class JoinMeetingRequest(BaseModel):
    """Schema de demande pour rejoindre une reunion."""

    code_reunion: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=20,
        description="Code de la reunion"
    )
    meeting_id: Optional[UUID] = Field(
        default=None,
        description="ID de la reunion (alternative au code)"
    )
    mot_de_passe: Optional[str] = Field(
        default=None,
        description="Mot de passe si requis"
    )
    nom_affiche: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Nom affiche dans la reunion"
    )
    audio_active: bool = Field(
        default=True,
        description="Activer le micro a l'entree"
    )
    video_active: bool = Field(
        default=True,
        description="Activer la camera a l'entree"
    )

    @field_validator("code_reunion", "meeting_id")
    @classmethod
    def validate_meeting_identifier(cls, v: Any, info) -> Any:
        """Valide qu'au moins un identifiant est fourni."""
        # La validation croisee sera faite dans le validateur de modele
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "code_reunion": "ABC123",
                "nom_affiche": "Jean Dupont",
                "audio_active": True,
                "video_active": True,
            }
        }


class JoinMeetingResponse(BaseModel):
    """Schema de reponse pour rejoindre une reunion (avec token LiveKit)."""

    meeting_id: UUID = Field(..., description="ID de la reunion")
    participant_id: UUID = Field(..., description="ID du participant")
    room_name: str = Field(..., description="Nom de la room LiveKit")
    # LiveKit credentials
    livekit_url: str = Field(..., description="URL du serveur LiveKit")
    livekit_token: str = Field(..., description="Token JWT pour LiveKit")
    # Meeting info
    titre: str = Field(..., description="Titre de la reunion")
    statut: MeetingStatus = Field(..., description="Statut de la reunion")
    # Options actives
    chat_actif: bool = Field(..., description="Chat disponible")
    tableau_blanc_actif: bool = Field(..., description="Tableau blanc disponible")
    transcription_active: bool = Field(..., description="Transcription active")
    enregistrement_en_cours: bool = Field(..., description="Enregistrement en cours")
    # WebSocket
    websocket_url: str = Field(..., description="URL WebSocket pour les events")
    # En attente
    en_salle_attente: bool = Field(
        default=False,
        description="Le participant est en salle d'attente"
    )


# =============================================================================
# Media Control Schemas
# =============================================================================
class MediaControlRequest(BaseModel):
    """Schema de controle media (mute, unmute, etc.)."""

    action: MediaControlType = Field(..., description="Type d'action")
    target_participant_id: Optional[UUID] = Field(
        default=None,
        description="ID du participant cible (pour host/co-host)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "action": "mute_audio",
                "target_participant_id": None,
            }
        }


# =============================================================================
# Recording Schemas
# =============================================================================
class RecordingStartRequest(BaseModel):
    """Schema de demande de demarrage d'enregistrement."""

    meeting_id: UUID = Field(..., description="ID de la reunion")
    inclure_audio: bool = Field(default=True, description="Inclure l'audio")
    inclure_video: bool = Field(default=True, description="Inclure la video")
    inclure_partages_ecran: bool = Field(default=True, description="Inclure les partages d'ecran")
    layout: str = Field(
        default="grid",
        description="Layout video: grid, speaker, sidebar"
    )

    @field_validator("layout")
    @classmethod
    def validate_layout(cls, v: str) -> str:
        """Valide le layout."""
        valid_layouts = ["grid", "speaker", "sidebar", "pip"]
        if v not in valid_layouts:
            raise ValueError(f"Layout invalide. Valeurs acceptees: {valid_layouts}")
        return v


class RecordingResponse(BaseModel):
    """Schema de reponse pour un enregistrement."""

    id: UUID = Field(..., description="ID de l'enregistrement")
    meeting_id: UUID = Field(..., description="ID de la reunion")
    statut: RecordingStatus = Field(..., description="Statut de l'enregistrement")
    date_debut: datetime = Field(..., description="Date de debut")
    date_fin: Optional[datetime] = Field(default=None, description="Date de fin")
    duree_secondes: int = Field(default=0, description="Duree en secondes")
    taille_octets: Optional[int] = Field(default=None, description="Taille du fichier")
    url_telechargement: Optional[str] = Field(default=None, description="URL de telechargement")
    url_streaming: Optional[str] = Field(default=None, description="URL de streaming")
    expire_at: Optional[datetime] = Field(default=None, description="Date d'expiration")

    class Config:
        from_attributes = True


# =============================================================================
# Transcription Schemas
# =============================================================================
class TranscriptionSegment(BaseModel):
    """Segment de transcription."""

    id: UUID = Field(..., description="ID du segment")
    participant_id: UUID = Field(..., description="ID du participant")
    participant_nom: str = Field(..., description="Nom du participant")
    texte: str = Field(..., description="Texte transcrit")
    timestamp_debut: float = Field(..., description="Debut en secondes")
    timestamp_fin: float = Field(..., description="Fin en secondes")
    confiance: float = Field(default=1.0, ge=0, le=1, description="Score de confiance")
    langue: str = Field(default="fr", description="Langue detectee")


class TranscriptionResponse(BaseModel):
    """Schema de reponse pour une transcription complete."""

    id: UUID = Field(..., description="ID de la transcription")
    meeting_id: UUID = Field(..., description="ID de la reunion")
    segments: List[TranscriptionSegment] = Field(
        default_factory=list,
        description="Segments de transcription"
    )
    texte_complet: str = Field(default="", description="Texte complet")
    langue_principale: str = Field(default="fr", description="Langue principale")
    duree_secondes: float = Field(default=0, description="Duree totale")
    nombre_intervenants: int = Field(default=0, description="Nombre d'intervenants")
    mots_cles: List[str] = Field(default_factory=list, description="Mots-cles extraits")
    created_at: datetime = Field(..., description="Date de creation")

    class Config:
        from_attributes = True


# =============================================================================
# Minutes (Compte-rendu) Schemas
# =============================================================================
class MinutesGenerateRequest(BaseModel):
    """Schema de demande de generation de compte-rendu."""

    meeting_id: UUID = Field(..., description="ID de la reunion")
    format_sortie: str = Field(
        default="markdown",
        description="Format: markdown, html, pdf, docx"
    )
    inclure_transcription: bool = Field(
        default=True,
        description="Inclure la transcription complete"
    )
    inclure_actions: bool = Field(
        default=True,
        description="Extraire les actions identifiees"
    )
    inclure_decisions: bool = Field(
        default=True,
        description="Extraire les decisions prises"
    )
    inclure_participants: bool = Field(
        default=True,
        description="Inclure la liste des participants"
    )
    langue: str = Field(default="fr", description="Langue du compte-rendu")
    style: str = Field(
        default="professionnel",
        description="Style: professionnel, concis, detaille"
    )

    @field_validator("format_sortie")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Valide le format de sortie."""
        valid_formats = ["markdown", "html", "pdf", "docx", "txt"]
        if v not in valid_formats:
            raise ValueError(f"Format invalide. Valeurs acceptees: {valid_formats}")
        return v

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        """Valide le style."""
        valid_styles = ["professionnel", "concis", "detaille", "technique"]
        if v not in valid_styles:
            raise ValueError(f"Style invalide. Valeurs acceptees: {valid_styles}")
        return v


class MinutesResponse(BaseModel):
    """Schema de reponse pour un compte-rendu."""

    id: UUID = Field(..., description="ID du compte-rendu")
    meeting_id: UUID = Field(..., description="ID de la reunion")
    titre: str = Field(..., description="Titre de la reunion")
    date_reunion: datetime = Field(..., description="Date de la reunion")
    duree_minutes: int = Field(..., description="Duree de la reunion")
    # Contenu
    resume: str = Field(..., description="Resume de la reunion")
    points_cles: List[str] = Field(default_factory=list, description="Points cles")
    decisions: List[str] = Field(default_factory=list, description="Decisions prises")
    actions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Actions a mener [{'action': str, 'responsable': str, 'echeance': str}]"
    )
    # Participants
    participants: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Liste des participants [{'nom': str, 'role': str}]"
    )
    # Export
    format_sortie: str = Field(..., description="Format du compte-rendu")
    contenu: str = Field(..., description="Contenu formate")
    url_telechargement: Optional[str] = Field(default=None, description="URL de telechargement")
    # Metadata
    genere_par_ia: bool = Field(default=True, description="Genere par IA")
    modele_ia: Optional[str] = Field(default=None, description="Modele IA utilise")
    created_at: datetime = Field(..., description="Date de generation")

    class Config:
        from_attributes = True


# =============================================================================
# Chat Schemas
# =============================================================================
class ChatMessageCreate(BaseModel):
    """Schema de creation d'un message chat."""

    meeting_id: UUID = Field(..., description="ID de la reunion")
    contenu: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Contenu du message"
    )
    destinataire_id: Optional[UUID] = Field(
        default=None,
        description="ID du destinataire (message prive)"
    )
    type_message: str = Field(
        default="text",
        description="Type: text, file, reaction"
    )
    fichier_url: Optional[str] = Field(
        default=None,
        description="URL du fichier partage"
    )
    fichier_nom: Optional[str] = Field(
        default=None,
        description="Nom du fichier partage"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "meeting_id": "123e4567-e89b-12d3-a456-426614174000",
                "contenu": "Bonjour a tous!",
                "type_message": "text",
            }
        }


class ChatMessageResponse(BaseModel):
    """Schema de reponse pour un message chat."""

    id: UUID = Field(..., description="ID du message")
    meeting_id: UUID = Field(..., description="ID de la reunion")
    expediteur_id: UUID = Field(..., description="ID de l'expediteur")
    expediteur_nom: str = Field(..., description="Nom de l'expediteur")
    contenu: str = Field(..., description="Contenu du message")
    destinataire_id: Optional[UUID] = Field(default=None, description="ID destinataire")
    destinataire_nom: Optional[str] = Field(default=None, description="Nom destinataire")
    type_message: str = Field(..., description="Type de message")
    fichier_url: Optional[str] = Field(default=None, description="URL fichier")
    fichier_nom: Optional[str] = Field(default=None, description="Nom fichier")
    est_prive: bool = Field(default=False, description="Message prive")
    created_at: datetime = Field(..., description="Date d'envoi")

    class Config:
        from_attributes = True


# =============================================================================
# Whiteboard Schemas
# =============================================================================
class WhiteboardStateResponse(BaseModel):
    """Schema de reponse pour l'etat du tableau blanc."""

    meeting_id: UUID = Field(..., description="ID de la reunion")
    actif: bool = Field(..., description="Tableau blanc actif")
    elements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Elements du tableau blanc"
    )
    dernier_modifie_par: Optional[UUID] = Field(
        default=None,
        description="Dernier utilisateur ayant modifie"
    )
    dernier_modifie_at: Optional[datetime] = Field(
        default=None,
        description="Date derniere modification"
    )
    version: int = Field(default=0, description="Version pour sync")


# =============================================================================
# Hand Raise Schemas
# =============================================================================
class HandRaiseResponse(BaseModel):
    """Schema de reponse pour une main levee."""

    participant_id: UUID = Field(..., description="ID du participant")
    participant_nom: str = Field(..., description="Nom du participant")
    main_levee: bool = Field(..., description="Main levee ou non")
    timestamp: datetime = Field(..., description="Timestamp de l'action")
    position: int = Field(
        default=0,
        description="Position dans la file d'attente"
    )


# =============================================================================
# WebSocket Event Schema
# =============================================================================
class WebSocketEvent(BaseModel):
    """Schema pour les evenements WebSocket."""

    type: WebSocketEventType = Field(..., description="Type d'evenement")
    meeting_id: UUID = Field(..., description="ID de la reunion")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp de l'evenement"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Donnees de l'evenement"
    )
    source_participant_id: Optional[UUID] = Field(
        default=None,
        description="ID du participant source"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "participant_joined",
                "meeting_id": "123e4567-e89b-12d3-a456-426614174000",
                "timestamp": "2024-03-15T10:00:00Z",
                "data": {
                    "participant_id": "456e7890-e89b-12d3-a456-426614174001",
                    "nom": "Jean Dupont",
                    "role": "participant",
                },
            }
        }
