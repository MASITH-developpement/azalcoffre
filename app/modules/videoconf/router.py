# =============================================================================
# AZALPLUS - Router API Visioconference
# =============================================================================
"""
Endpoints FastAPI pour le module de visioconference.

Fonctionnalites:
- Gestion des reunions (demarrer, rejoindre, terminer)
- Salle d'attente (liste, admettre, rejeter)
- Controles media (mute, video, kick)
- Enregistrement (start, stop, list)
- Transcription temps reel
- Generation de comptes-rendus IA
- Envoi d'invitations
"""

from datetime import datetime
from typing import Any, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

# =============================================================================
# Schemas locaux pour les endpoints
# =============================================================================

class StartMeetingResponse(BaseModel):
    """Reponse au demarrage d'une reunion."""
    meeting_id: UUID
    room_name: str
    room_url: str
    token: str
    started_at: datetime


class JoinMeetingRequest(BaseModel):
    """Requete pour rejoindre une reunion."""
    participant_name: str = Field(..., min_length=1, max_length=100)
    video_enabled: bool = True
    audio_enabled: bool = True


class JoinMeetingResponse(BaseModel):
    """Reponse pour rejoindre une reunion."""
    meeting_id: UUID
    participant_id: UUID
    token: str
    room_url: str
    can_present: bool = False
    waiting_room: bool = False


class EndMeetingResponse(BaseModel):
    """Reponse a la fin d'une reunion."""
    meeting_id: UUID
    ended_at: datetime
    duration_seconds: int
    participant_count: int


class WaitingRoomParticipant(BaseModel):
    """Participant en salle d'attente."""
    participant_id: UUID
    name: str
    email: Optional[str] = None
    joined_at: datetime


class WaitingRoomResponse(BaseModel):
    """Liste des participants en salle d'attente."""
    meeting_id: UUID
    participants: List[WaitingRoomParticipant]
    count: int


class AdmitParticipantResponse(BaseModel):
    """Reponse a l'admission d'un participant."""
    participant_id: UUID
    admitted_at: datetime
    token: str


class RejectParticipantResponse(BaseModel):
    """Reponse au rejet d'un participant."""
    participant_id: UUID
    rejected_at: datetime
    reason: Optional[str] = None


class MediaControlRequest(BaseModel):
    """Requete de controle media."""
    reason: Optional[str] = None


class MediaControlResponse(BaseModel):
    """Reponse au controle media."""
    participant_id: UUID
    action: str
    success: bool
    timestamp: datetime


class MuteAllRequest(BaseModel):
    """Requete pour muter tous les participants."""
    allow_unmute: bool = True
    exclude_hosts: bool = True


class MuteAllResponse(BaseModel):
    """Reponse au mute global."""
    meeting_id: UUID
    muted_count: int
    timestamp: datetime


class KickParticipantResponse(BaseModel):
    """Reponse a l'expulsion d'un participant."""
    participant_id: UUID
    kicked_at: datetime
    reason: Optional[str] = None


class RecordingStartRequest(BaseModel):
    """Requete pour demarrer l'enregistrement."""
    format: str = Field(default="mp4", pattern="^(mp4|webm|mkv)$")
    include_audio: bool = True
    include_video: bool = True
    layout: str = Field(default="grid", pattern="^(grid|speaker|gallery)$")


class RecordingStartResponse(BaseModel):
    """Reponse au demarrage de l'enregistrement."""
    recording_id: UUID
    meeting_id: UUID
    started_at: datetime
    format: str


class RecordingStopResponse(BaseModel):
    """Reponse a l'arret de l'enregistrement."""
    recording_id: UUID
    meeting_id: UUID
    stopped_at: datetime
    duration_seconds: int
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None


class RecordingInfo(BaseModel):
    """Information sur un enregistrement."""
    recording_id: UUID
    meeting_id: UUID
    started_at: datetime
    stopped_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    format: str
    status: str
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None


class RecordingListResponse(BaseModel):
    """Liste des enregistrements."""
    meeting_id: UUID
    recordings: List[RecordingInfo]
    count: int


class TranscriptionStartResponse(BaseModel):
    """Reponse au demarrage de la transcription."""
    meeting_id: UUID
    transcription_id: UUID
    started_at: datetime
    language: str = "fr"


class TranscriptionSegment(BaseModel):
    """Segment de transcription."""
    segment_id: UUID
    speaker: Optional[str] = None
    text: str
    start_time: float
    end_time: float
    confidence: float = 1.0


class TranscriptionResponse(BaseModel):
    """Reponse avec la transcription."""
    meeting_id: UUID
    transcription_id: UUID
    segments: List[TranscriptionSegment]
    language: str = "fr"
    status: str
    last_updated: datetime


class MinutesGenerateRequest(BaseModel):
    """Requete pour generer un compte-rendu."""
    template: str = Field(default="standard", pattern="^(standard|detailed|summary)$")
    include_action_items: bool = True
    include_decisions: bool = True
    include_participants: bool = True
    language: str = "fr"


class MinutesGenerateResponse(BaseModel):
    """Reponse a la generation du compte-rendu."""
    minutes_id: UUID
    meeting_id: UUID
    status: str
    estimated_time_seconds: Optional[int] = None


class MinutesInfo(BaseModel):
    """Information sur un compte-rendu."""
    minutes_id: UUID
    meeting_id: UUID
    title: str
    created_at: datetime
    status: str
    content: Optional[str] = None
    action_items: List[str] = []
    decisions: List[str] = []
    participants: List[str] = []
    approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class MinutesApproveResponse(BaseModel):
    """Reponse a l'approbation du compte-rendu."""
    minutes_id: UUID
    approved_by: UUID
    approved_at: datetime


class MinutesSendRequest(BaseModel):
    """Requete pour envoyer le compte-rendu."""
    recipients: List[str] = Field(default=[], description="Emails des destinataires")
    include_recording_link: bool = False
    custom_message: Optional[str] = None


class MinutesSendResponse(BaseModel):
    """Reponse a l'envoi du compte-rendu."""
    minutes_id: UUID
    sent_to: List[str]
    sent_at: datetime


class InvitationSendRequest(BaseModel):
    """Requete pour envoyer des invitations."""
    recipients: List[str] = Field(..., min_items=1, description="Emails des invites")
    include_calendar_invite: bool = True
    custom_message: Optional[str] = None
    send_reminder: bool = True
    reminder_minutes_before: int = Field(default=15, ge=5, le=1440)


class InvitationSendResponse(BaseModel):
    """Reponse a l'envoi des invitations."""
    meeting_id: UUID
    sent_to: List[str]
    failed: List[str] = []
    sent_at: datetime


class MessageResponse(BaseModel):
    """Reponse simple avec message."""
    success: bool
    message: str


# =============================================================================
# Import des dependances AZALPLUS
# =============================================================================
try:
    from moteur.auth import require_auth
    from moteur.tenant import get_current_tenant, get_current_user_id
    from moteur.db import Database
except ImportError:
    # Fallback si import echoue (developpement/tests)
    require_auth = None
    get_current_tenant = None
    get_current_user_id = None
    Database = None

# =============================================================================
# Router
# =============================================================================
router = APIRouter(prefix="/api/videoconf", tags=["Visioconference"])


# =============================================================================
# Dependances
# =============================================================================
async def get_service(
    user: dict = Depends(require_auth) if require_auth else None,
    tenant_id: UUID = Depends(get_current_tenant) if get_current_tenant else None,
):
    """Cree le service de visioconference."""
    from uuid import uuid4

    if tenant_id is None:
        tenant_id = uuid4()

    # Import du service (sera cree plus tard)
    try:
        from .service import VideoconfService
        return VideoconfService(db=None, tenant_id=tenant_id)
    except ImportError:
        # Service non encore implemente
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Service de visioconference non disponible"
        )


async def get_organizer_service(
    user: dict = Depends(require_auth) if require_auth else None,
    tenant_id: UUID = Depends(get_current_tenant) if get_current_tenant else None,
    user_id: UUID = Depends(get_current_user_id) if get_current_user_id else None,
):
    """
    Cree le service avec verification du role organisateur.
    Utilise pour les actions administratives.
    """
    from uuid import uuid4

    if tenant_id is None:
        tenant_id = uuid4()

    try:
        from .service import VideoconfService
        service = VideoconfService(db=None, tenant_id=tenant_id)
        # Stocker user_id pour verification dans les endpoints
        service._current_user_id = user_id
        return service
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Service de visioconference non disponible"
        )


# =============================================================================
# Endpoints Gestion Salle
# =============================================================================
@router.post(
    "/{meeting_id}/start",
    response_model=StartMeetingResponse,
    summary="Demarrer une reunion",
    description="Demarre une reunion et cree la salle LiveKit correspondante",
)
async def start_meeting(
    meeting_id: UUID,
    service = Depends(get_organizer_service),
) -> StartMeetingResponse:
    """
    Demarre une reunion video.

    - Cree la salle LiveKit
    - Genere le token organisateur
    - Met a jour le statut de la reunion

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.start_meeting(meeting_id)
        return StartMeetingResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du demarrage: {str(e)}"
        )


@router.post(
    "/{meeting_id}/join",
    response_model=JoinMeetingResponse,
    summary="Rejoindre une reunion",
    description="Permet a un participant de rejoindre une reunion en cours",
)
async def join_meeting(
    meeting_id: UUID,
    request: JoinMeetingRequest,
    service = Depends(get_service),
) -> JoinMeetingResponse:
    """
    Rejoindre une reunion video.

    - Verifie que la reunion est en cours
    - Place en salle d'attente si activee
    - Genere le token participant LiveKit
    """
    try:
        result = await service.join_meeting(
            meeting_id=meeting_id,
            participant_name=request.participant_name,
            video_enabled=request.video_enabled,
            audio_enabled=request.audio_enabled,
        )
        return JoinMeetingResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la connexion: {str(e)}"
        )


@router.post(
    "/{meeting_id}/end",
    response_model=EndMeetingResponse,
    summary="Terminer une reunion",
    description="Met fin a la reunion et deconnecte tous les participants",
)
async def end_meeting(
    meeting_id: UUID,
    service = Depends(get_organizer_service),
) -> EndMeetingResponse:
    """
    Terminer une reunion video.

    - Arrete l'enregistrement si en cours
    - Deconnecte tous les participants
    - Supprime la salle LiveKit
    - Met a jour le statut de la reunion

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.end_meeting(meeting_id)
        return EndMeetingResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la fin: {str(e)}"
        )


# =============================================================================
# Endpoints Salle d'Attente
# =============================================================================
@router.get(
    "/{meeting_id}/waiting-room",
    response_model=WaitingRoomResponse,
    summary="Liste salle d'attente",
    description="Liste les participants en attente d'admission",
)
async def get_waiting_room(
    meeting_id: UUID,
    service = Depends(get_organizer_service),
) -> WaitingRoomResponse:
    """
    Recuperer la liste des participants en salle d'attente.

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.get_waiting_room(meeting_id)
        return WaitingRoomResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/waiting-room/{participant_id}/admit",
    response_model=AdmitParticipantResponse,
    summary="Admettre un participant",
    description="Admet un participant depuis la salle d'attente",
)
async def admit_participant(
    meeting_id: UUID,
    participant_id: UUID,
    service = Depends(get_organizer_service),
) -> AdmitParticipantResponse:
    """
    Admettre un participant de la salle d'attente dans la reunion.

    - Genere le token participant
    - Notifie le participant qu'il peut rejoindre

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.admit_participant(meeting_id, participant_id)
        return AdmitParticipantResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/waiting-room/{participant_id}/reject",
    response_model=RejectParticipantResponse,
    summary="Rejeter un participant",
    description="Refuse l'admission d'un participant",
)
async def reject_participant(
    meeting_id: UUID,
    participant_id: UUID,
    reason: Optional[str] = Query(default=None, max_length=255),
    service = Depends(get_organizer_service),
) -> RejectParticipantResponse:
    """
    Rejeter un participant de la salle d'attente.

    - Notifie le participant du refus
    - Optionnellement fournit une raison

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.reject_participant(meeting_id, participant_id, reason)
        return RejectParticipantResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


# =============================================================================
# Endpoints Controles Media
# =============================================================================
@router.post(
    "/{meeting_id}/participants/{participant_id}/mute",
    response_model=MediaControlResponse,
    summary="Muter un participant",
    description="Coupe le micro d'un participant",
)
async def mute_participant(
    meeting_id: UUID,
    participant_id: UUID,
    request: Optional[MediaControlRequest] = None,
    service = Depends(get_organizer_service),
) -> MediaControlResponse:
    """
    Muter le micro d'un participant.

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        reason = request.reason if request else None
        result = await service.mute_participant(meeting_id, participant_id, reason)
        return MediaControlResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/participants/{participant_id}/unmute-request",
    response_model=MediaControlResponse,
    summary="Demander a un participant de se demuter",
    description="Envoie une demande au participant pour qu'il active son micro",
)
async def request_unmute(
    meeting_id: UUID,
    participant_id: UUID,
    service = Depends(get_organizer_service),
) -> MediaControlResponse:
    """
    Envoyer une demande de demute a un participant.

    Le participant recoit une notification et peut choisir d'activer son micro.

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.request_unmute(meeting_id, participant_id)
        return MediaControlResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/mute-all",
    response_model=MuteAllResponse,
    summary="Muter tous les participants",
    description="Coupe le micro de tous les participants",
)
async def mute_all_participants(
    meeting_id: UUID,
    request: Optional[MuteAllRequest] = None,
    service = Depends(get_organizer_service),
) -> MuteAllResponse:
    """
    Muter tous les participants de la reunion.

    Options:
    - allow_unmute: Les participants peuvent se demuter (defaut: true)
    - exclude_hosts: Les co-organisateurs ne sont pas mutes (defaut: true)

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        allow_unmute = request.allow_unmute if request else True
        exclude_hosts = request.exclude_hosts if request else True
        result = await service.mute_all(meeting_id, allow_unmute, exclude_hosts)
        return MuteAllResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/participants/{participant_id}/disable-video",
    response_model=MediaControlResponse,
    summary="Desactiver la video",
    description="Desactive la camera d'un participant",
)
async def disable_participant_video(
    meeting_id: UUID,
    participant_id: UUID,
    request: Optional[MediaControlRequest] = None,
    service = Depends(get_organizer_service),
) -> MediaControlResponse:
    """
    Desactiver la camera d'un participant.

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        reason = request.reason if request else None
        result = await service.disable_video(meeting_id, participant_id, reason)
        return MediaControlResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/participants/{participant_id}/kick",
    response_model=KickParticipantResponse,
    summary="Expulser un participant",
    description="Expulse un participant de la reunion",
)
async def kick_participant(
    meeting_id: UUID,
    participant_id: UUID,
    reason: Optional[str] = Query(default=None, max_length=255),
    service = Depends(get_organizer_service),
) -> KickParticipantResponse:
    """
    Expulser un participant de la reunion.

    - Deconnecte immediatement le participant
    - Optionnellement enregistre une raison

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.kick_participant(meeting_id, participant_id, reason)
        return KickParticipantResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


# =============================================================================
# Endpoints Enregistrement
# =============================================================================
@router.post(
    "/{meeting_id}/recording/start",
    response_model=RecordingStartResponse,
    summary="Demarrer l'enregistrement",
    description="Demarre l'enregistrement de la reunion",
)
async def start_recording(
    meeting_id: UUID,
    request: Optional[RecordingStartRequest] = None,
    service = Depends(get_organizer_service),
) -> RecordingStartResponse:
    """
    Demarrer l'enregistrement de la reunion.

    Options:
    - format: mp4, webm ou mkv (defaut: mp4)
    - include_audio: Inclure l'audio (defaut: true)
    - include_video: Inclure la video (defaut: true)
    - layout: grid, speaker ou gallery (defaut: grid)

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        format = request.format if request else "mp4"
        include_audio = request.include_audio if request else True
        include_video = request.include_video if request else True
        layout = request.layout if request else "grid"

        result = await service.start_recording(
            meeting_id=meeting_id,
            format=format,
            include_audio=include_audio,
            include_video=include_video,
            layout=layout,
        )
        return RecordingStartResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/recording/stop",
    response_model=RecordingStopResponse,
    summary="Arreter l'enregistrement",
    description="Arrete l'enregistrement en cours",
)
async def stop_recording(
    meeting_id: UUID,
    service = Depends(get_organizer_service),
) -> RecordingStopResponse:
    """
    Arreter l'enregistrement de la reunion.

    - Finalise le fichier d'enregistrement
    - Retourne le lien de telechargement

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.stop_recording(meeting_id)
        return RecordingStopResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.get(
    "/{meeting_id}/recordings",
    response_model=RecordingListResponse,
    summary="Liste des enregistrements",
    description="Liste tous les enregistrements d'une reunion",
)
async def list_recordings(
    meeting_id: UUID,
    service = Depends(get_service),
) -> RecordingListResponse:
    """
    Lister tous les enregistrements d'une reunion.

    Accessible aux participants de la reunion.
    """
    try:
        result = await service.list_recordings(meeting_id)
        return RecordingListResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


# =============================================================================
# Endpoints Transcription
# =============================================================================
@router.post(
    "/{meeting_id}/transcription/start",
    response_model=TranscriptionStartResponse,
    summary="Demarrer la transcription",
    description="Demarre la transcription en temps reel de la reunion",
)
async def start_transcription(
    meeting_id: UUID,
    language: str = Query(default="fr", pattern="^[a-z]{2}$"),
    service = Depends(get_organizer_service),
) -> TranscriptionStartResponse:
    """
    Demarrer la transcription en temps reel.

    - Transcription IA en temps reel
    - Detection automatique des locuteurs
    - Support multilingue

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.start_transcription(meeting_id, language)
        return TranscriptionStartResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.get(
    "/{meeting_id}/transcription",
    response_model=TranscriptionResponse,
    summary="Recuperer la transcription",
    description="Recupere la transcription complete de la reunion",
)
async def get_transcription(
    meeting_id: UUID,
    service = Depends(get_service),
) -> TranscriptionResponse:
    """
    Recuperer la transcription de la reunion.

    - Segments avec horodatage
    - Identification des locuteurs
    - Niveau de confiance par segment
    """
    try:
        result = await service.get_transcription(meeting_id)
        return TranscriptionResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


# =============================================================================
# Endpoints Comptes-Rendus (Minutes)
# =============================================================================
@router.post(
    "/{meeting_id}/minutes/generate",
    response_model=MinutesGenerateResponse,
    summary="Generer un compte-rendu",
    description="Genere un compte-rendu IA a partir de la transcription",
)
async def generate_minutes(
    meeting_id: UUID,
    request: Optional[MinutesGenerateRequest] = None,
    service = Depends(get_organizer_service),
) -> MinutesGenerateResponse:
    """
    Generer un compte-rendu automatique.

    Utilise l'IA pour:
    - Resumer les discussions
    - Extraire les decisions prises
    - Identifier les actions a faire
    - Lister les participants

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        template = request.template if request else "standard"
        include_action_items = request.include_action_items if request else True
        include_decisions = request.include_decisions if request else True
        include_participants = request.include_participants if request else True
        language = request.language if request else "fr"

        result = await service.generate_minutes(
            meeting_id=meeting_id,
            template=template,
            include_action_items=include_action_items,
            include_decisions=include_decisions,
            include_participants=include_participants,
            language=language,
        )
        return MinutesGenerateResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.get(
    "/{meeting_id}/minutes",
    response_model=List[MinutesInfo],
    summary="Liste des comptes-rendus",
    description="Liste tous les comptes-rendus d'une reunion",
)
async def list_minutes(
    meeting_id: UUID,
    service = Depends(get_service),
) -> List[MinutesInfo]:
    """
    Lister tous les comptes-rendus d'une reunion.
    """
    try:
        result = await service.list_minutes(meeting_id)
        return [MinutesInfo(**m) for m in result]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/minutes/{minutes_id}/approve",
    response_model=MinutesApproveResponse,
    summary="Approuver un compte-rendu",
    description="Approuve officiellement un compte-rendu",
)
async def approve_minutes(
    meeting_id: UUID,
    minutes_id: UUID,
    service = Depends(get_organizer_service),
) -> MinutesApproveResponse:
    """
    Approuver un compte-rendu.

    Marque le compte-rendu comme officiellement approuve.

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.approve_minutes(meeting_id, minutes_id)
        return MinutesApproveResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post(
    "/{meeting_id}/minutes/{minutes_id}/send",
    response_model=MinutesSendResponse,
    summary="Envoyer le compte-rendu",
    description="Envoie le compte-rendu par email aux participants",
)
async def send_minutes(
    meeting_id: UUID,
    minutes_id: UUID,
    request: Optional[MinutesSendRequest] = None,
    service = Depends(get_organizer_service),
) -> MinutesSendResponse:
    """
    Envoyer le compte-rendu par email.

    Options:
    - recipients: Liste des emails (defaut: tous les participants)
    - include_recording_link: Inclure le lien vers l'enregistrement
    - custom_message: Message personnalise

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        recipients = request.recipients if request else []
        include_recording_link = request.include_recording_link if request else False
        custom_message = request.custom_message if request else None

        result = await service.send_minutes(
            meeting_id=meeting_id,
            minutes_id=minutes_id,
            recipients=recipients,
            include_recording_link=include_recording_link,
            custom_message=custom_message,
        )
        return MinutesSendResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


# =============================================================================
# Endpoints Invitations
# =============================================================================
@router.post(
    "/{meeting_id}/invitations/send",
    response_model=InvitationSendResponse,
    summary="Envoyer des invitations",
    description="Envoie les invitations a la reunion par email",
)
async def send_invitations(
    meeting_id: UUID,
    request: InvitationSendRequest,
    service = Depends(get_organizer_service),
) -> InvitationSendResponse:
    """
    Envoyer des invitations a la reunion.

    Options:
    - recipients: Liste des emails (obligatoire)
    - include_calendar_invite: Inclure fichier ICS (defaut: true)
    - custom_message: Message personnalise
    - send_reminder: Envoyer un rappel (defaut: true)
    - reminder_minutes_before: Minutes avant le rappel (defaut: 15)

    Necessite d'etre l'organisateur de la reunion.
    """
    try:
        result = await service.send_invitations(
            meeting_id=meeting_id,
            recipients=request.recipients,
            include_calendar_invite=request.include_calendar_invite,
            custom_message=request.custom_message,
            send_reminder=request.send_reminder,
            reminder_minutes_before=request.reminder_minutes_before,
        )
        return InvitationSendResponse(**result)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )
