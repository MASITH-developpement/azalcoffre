# =============================================================================
# AZALPLUS - Module Videoconference
# =============================================================================
"""
Module de videoconference integre pour AZALPLUS.

Fonctionnalites:
- Creation et gestion de reunions video
- Integration LiveKit pour WebRTC
- Enregistrement des sessions
- Transcription IA en temps reel
- Generation de comptes-rendus automatiques
- Chat et partage d'ecran
- Tableau blanc collaboratif
- Appels telephoniques avec transcription
"""

# =============================================================================
# Routers (pour module_loader)
# =============================================================================
try:
    from .router import router
except ImportError as e:
    import structlog
    structlog.get_logger(__name__).warning(
        "videoconf.router not available",
        error=str(e)
    )
    router = None

try:
    from .phone_router import router as phone_router
except ImportError as e:
    import structlog
    structlog.get_logger(__name__).warning(
        "videoconf.phone_router not available",
        error=str(e)
    )
    phone_router = None

try:
    from .websocket_router import websocket_router, generate_videoconf_token
except ImportError as e:
    import structlog
    structlog.get_logger(__name__).warning(
        "videoconf.websocket_router not available",
        error=str(e)
    )
    websocket_router = None
    generate_videoconf_token = None

# =============================================================================
# Services specialises
# =============================================================================
try:
    from .chat import ChatService, MessageType
except ImportError:
    ChatService = None
    MessageType = None

try:
    from .media_control import MediaControlService, TrackType as MediaTrackType, ParticipantRole as MediaParticipantRole
except ImportError:
    MediaControlService = None
    MediaTrackType = None
    MediaParticipantRole = None

try:
    from .recording import RecordingService, RecordingStatus as RecordingServiceStatus, RecordingType
except ImportError:
    RecordingService = None
    RecordingServiceStatus = None
    RecordingType = None

try:
    from .whiteboard import WhiteboardService, WhiteboardTool, OperationType
except ImportError:
    WhiteboardService = None
    WhiteboardTool = None
    OperationType = None

try:
    from .transcription import TranscriptionService, TranscriptionStatus, TranscriptionProvider
except ImportError:
    TranscriptionService = None
    TranscriptionStatus = None
    TranscriptionProvider = None

try:
    from .minutes import MinutesService, MinutesStatus, MinutesProvider
except ImportError:
    MinutesService = None
    MinutesStatus = None
    MinutesProvider = None

try:
    from .phone_call import PhoneCallService, CallStatus, CallDirection, CallProvider, MinutesDeliveryStatus
except ImportError:
    PhoneCallService = None
    CallStatus = None
    CallDirection = None
    CallProvider = None
    MinutesDeliveryStatus = None

# =============================================================================
# Schemas
# =============================================================================
try:
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
        # Media
        MediaControlRequest,
        MediaControlType,
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
        # Whiteboard
        WhiteboardStateResponse,
        WhiteboardAction,
        # Hand raise
        HandRaiseResponse,
        # WebSocket
        WebSocketEvent,
        WebSocketEventType,
    )
except ImportError as e:
    import structlog
    structlog.get_logger(__name__).warning(
        "videoconf.schemas not fully available",
        error=str(e)
    )

# =============================================================================
# Service principal
# =============================================================================
try:
    from .service import VideoconfService
except ImportError as e:
    import structlog
    structlog.get_logger(__name__).warning(
        "videoconf.service not available",
        error=str(e)
    )
    VideoconfService = None

# =============================================================================
# Room Manager (LiveKit)
# =============================================================================
try:
    from .room_manager import (
        LiveKitRoomManager,
        LiveKitConfig,
        RoomInfo,
        RoomOptions,
        ParticipantInfo,
        ParticipantPermissions,
        RecordingOptions,
        RecordingInfo,
        RecordingState,
        TrackType,
        LiveKitError,
        RoomNotFoundError,
        ParticipantNotFoundError,
        RecordingError,
        TenantIsolationError,
    )
except ImportError as e:
    import structlog
    structlog.get_logger(__name__).warning(
        "videoconf.room_manager not available",
        error=str(e)
    )
    LiveKitRoomManager = None
    LiveKitConfig = None
    RoomInfo = None
    RoomOptions = None
    ParticipantInfo = None
    ParticipantPermissions = None
    RecordingOptions = None
    RecordingInfo = None
    RecordingState = None
    TrackType = None
    LiveKitError = None
    RoomNotFoundError = None
    ParticipantNotFoundError = None
    RecordingError = None
    TenantIsolationError = None

__all__ = [
    # Routers (pour module_loader)
    "router",
    "phone_router",
    "websocket_router",
    "generate_videoconf_token",
    # Services principaux
    "VideoconfService",
    # Services specialises
    "ChatService",
    "MessageType",
    "MediaControlService",
    "MediaTrackType",
    "MediaParticipantRole",
    "RecordingService",
    "RecordingServiceStatus",
    "RecordingType",
    "WhiteboardService",
    "WhiteboardTool",
    "OperationType",
    # Transcription & Minutes
    "TranscriptionService",
    "TranscriptionStatus",
    "TranscriptionProvider",
    "MinutesService",
    "MinutesStatus",
    "MinutesProvider",
    # Phone Calls
    "PhoneCallService",
    "CallStatus",
    "CallDirection",
    "CallProvider",
    "MinutesDeliveryStatus",
    # Room Manager
    "LiveKitRoomManager",
    "LiveKitConfig",
    "RoomInfo",
    "RoomOptions",
    "ParticipantInfo",
    "ParticipantPermissions",
    "RecordingOptions",
    "RecordingInfo",
    "RecordingState",
    "TrackType",
    # Exceptions
    "LiveKitError",
    "RoomNotFoundError",
    "ParticipantNotFoundError",
    "RecordingError",
    "TenantIsolationError",
    # Meeting schemas
    "MeetingCreate",
    "MeetingUpdate",
    "MeetingResponse",
    "MeetingListResponse",
    "MeetingStatus",
    "MeetingType",
    # Participant schemas
    "ParticipantCreate",
    "ParticipantResponse",
    "ParticipantRole",
    "ParticipantStatus",
    # Join schemas
    "JoinMeetingRequest",
    "JoinMeetingResponse",
    # Media schemas
    "MediaControlRequest",
    "MediaControlType",
    # Recording schemas
    "RecordingStartRequest",
    "RecordingResponse",
    "RecordingStatus",
    # Transcription schemas
    "TranscriptionResponse",
    "TranscriptionSegment",
    # Minutes schemas
    "MinutesGenerateRequest",
    "MinutesResponse",
    # Chat schemas
    "ChatMessageCreate",
    "ChatMessageResponse",
    # Whiteboard schemas
    "WhiteboardStateResponse",
    "WhiteboardAction",
    # Hand raise schemas
    "HandRaiseResponse",
    # WebSocket schemas
    "WebSocketEvent",
    "WebSocketEventType",
]
