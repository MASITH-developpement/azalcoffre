# =============================================================================
# AZALPLUS - WebSocket Router pour Videoconf
# =============================================================================
"""
Router WebSocket pour les evenements temps reel des reunions video.

Ce router gere les connexions WebSocket pour le module de visioconference.
Il utilise le WebSocketManager central pour la gestion des connexions
et l'isolation multi-tenant.

Fonctionnalites:
- Authentification via token JWT en query parameter
- Integration avec le WebSocketManager central
- Gestion des evenements temps reel (chat, media, whiteboard, etc.)
- Isolation multi-tenant stricte

Endpoint principal: /ws/videoconf/{meeting_id}?token=...
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
import structlog

# Import du WebSocketManager central et des utilitaires
from moteur.websocket_manager import (
    websocket_manager,
    verify_websocket_token,
    create_websocket_token,
    WebSocketMessage,
    WebSocketEventType,
    WebSocketConnection,
    ParticipantRole,
)

logger = structlog.get_logger(__name__)

# =============================================================================
# Router WebSocket Videoconf
# =============================================================================
websocket_router = APIRouter(tags=["WebSocket Videoconf"])


# =============================================================================
# Endpoint principal WebSocket
# =============================================================================
@websocket_router.websocket("/ws/videoconf/{meeting_id}")
async def videoconf_websocket(
    websocket: WebSocket,
    meeting_id: UUID,
    token: str = Query(..., description="JWT token d'authentification WebSocket"),
):
    """
    WebSocket pour les evenements temps reel d'une reunion video.

    Authentification via token JWT passe en query parameter.
    Le token doit contenir:
    - tenant_id: ID du tenant (isolation obligatoire)
    - meeting_id: ID de la reunion (doit correspondre au path)
    - participant_id: ID du participant
    - role: Role du participant (ORGANISATEUR, PARTICIPANT, etc.)
    - display_name: Nom affiche du participant

    Events entrants geres:
    - ping: Heartbeat keepalive
    - audio_toggled: Changement d'etat micro
    - video_toggled: Changement d'etat camera
    - hand_raised/hand_lowered: Main levee
    - chat_message: Message chat
    - reaction: Reaction emoji
    - whiteboard_update: Mise a jour tableau blanc
    - whiteboard_cursor: Position curseur whiteboard
    - typing_started/typing_stopped: Indicateur de saisie

    Events sortants:
    - connected: Confirmation de connexion avec liste participants
    - participant_joined: Nouveau participant
    - participant_left: Depart participant
    - Et tous les autres events WebSocketEventType
    """
    # -------------------------------------------------------------------------
    # Validation du token JWT
    # -------------------------------------------------------------------------
    payload = verify_websocket_token(token)

    if not payload:
        logger.warning(
            "websocket_auth_failed",
            meeting_id=str(meeting_id),
            reason="invalid_or_expired_token",
        )
        await websocket.close(code=4001, reason="Token invalide ou expire")
        return

    # -------------------------------------------------------------------------
    # Verification de correspondance meeting_id
    # -------------------------------------------------------------------------
    if payload.meeting_id != meeting_id:
        logger.warning(
            "websocket_meeting_mismatch",
            token_meeting_id=str(payload.meeting_id),
            url_meeting_id=str(meeting_id),
            participant_id=str(payload.participant_id),
        )
        await websocket.close(code=4003, reason="Token meeting ID ne correspond pas")
        return

    # -------------------------------------------------------------------------
    # Verification du tenant (isolation multi-tenant)
    # -------------------------------------------------------------------------
    if not payload.tenant_id:
        logger.warning(
            "websocket_no_tenant",
            meeting_id=str(meeting_id),
            participant_id=str(payload.participant_id),
        )
        await websocket.close(code=4004, reason="Tenant ID manquant")
        return

    # -------------------------------------------------------------------------
    # Acceptation de la connexion WebSocket
    # -------------------------------------------------------------------------
    await websocket.accept()

    logger.info(
        "websocket_videoconf_accepted",
        meeting_id=str(meeting_id),
        participant_id=str(payload.participant_id),
        tenant_id=str(payload.tenant_id),
        role=payload.role.value,
        display_name=payload.display_name,
    )

    # -------------------------------------------------------------------------
    # Enregistrement de la connexion dans le WebSocketManager
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Envoi de la confirmation de connexion au participant
    # -------------------------------------------------------------------------
    participants = websocket_manager.get_participants(
        meeting_id=payload.meeting_id,
        tenant_id=payload.tenant_id,
    )

    await websocket_manager.send_to_participant(
        meeting_id=payload.meeting_id,
        participant_id=payload.participant_id,
        tenant_id=payload.tenant_id,
        event_type=WebSocketEventType.CONNECTED,
        data={
            "participant_id": str(payload.participant_id),
            "meeting_id": str(payload.meeting_id),
            "role": payload.role.value,
            "display_name": payload.display_name,
            "participants": participants,
            "connected_at": datetime.utcnow().isoformat(),
        },
    )

    # -------------------------------------------------------------------------
    # Notification aux autres participants
    # -------------------------------------------------------------------------
    await websocket_manager.broadcast_to_meeting(
        meeting_id=payload.meeting_id,
        tenant_id=payload.tenant_id,
        event_type=WebSocketEventType.PARTICIPANT_JOINED,
        data=connection.to_dict(),
        exclude_participant_id=payload.participant_id,
    )

    # -------------------------------------------------------------------------
    # Boucle principale de reception des messages
    # -------------------------------------------------------------------------
    try:
        while True:
            try:
                # Reception du message texte
                raw_data = await websocket.receive_text()

                # Parse du message JSON
                try:
                    message = WebSocketMessage.from_json(raw_data)
                except json.JSONDecodeError as e:
                    logger.warning(
                        "websocket_invalid_json",
                        meeting_id=str(meeting_id),
                        participant_id=str(payload.participant_id),
                        error=str(e),
                    )
                    await websocket_manager.send_to_participant(
                        meeting_id=payload.meeting_id,
                        participant_id=payload.participant_id,
                        tenant_id=payload.tenant_id,
                        event_type=WebSocketEventType.ERROR,
                        data={"error": "Format JSON invalide", "code": "INVALID_JSON"},
                    )
                    continue

                # Traitement de l'evenement
                await _handle_videoconf_event(
                    manager=websocket_manager,
                    connection=connection,
                    message=message,
                )

            except json.JSONDecodeError:
                # Deja gere au-dessus, mais au cas ou
                continue

    except WebSocketDisconnect as e:
        logger.info(
            "websocket_client_disconnected",
            meeting_id=str(meeting_id),
            participant_id=str(payload.participant_id),
            code=e.code if hasattr(e, 'code') else None,
        )

    except Exception as e:
        logger.error(
            "websocket_error",
            meeting_id=str(meeting_id),
            participant_id=str(payload.participant_id),
            error=str(e),
            exc_info=True,
        )

    finally:
        # -------------------------------------------------------------------------
        # Deconnexion et nettoyage
        # -------------------------------------------------------------------------
        await websocket_manager.disconnect(
            meeting_id=payload.meeting_id,
            participant_id=payload.participant_id,
            tenant_id=payload.tenant_id,
        )

        # Notification aux autres participants
        await websocket_manager.broadcast_to_meeting(
            meeting_id=payload.meeting_id,
            tenant_id=payload.tenant_id,
            event_type=WebSocketEventType.PARTICIPANT_LEFT,
            data={
                "participant_id": str(payload.participant_id),
                "display_name": payload.display_name,
                "left_at": datetime.utcnow().isoformat(),
            },
        )

        logger.info(
            "websocket_videoconf_cleanup_complete",
            meeting_id=str(meeting_id),
            participant_id=str(payload.participant_id),
        )


# =============================================================================
# Gestionnaire d'evenements entrants
# =============================================================================
async def _handle_videoconf_event(
    manager,
    connection: WebSocketConnection,
    message: WebSocketMessage,
) -> None:
    """
    Traite un evenement WebSocket entrant pour une reunion video.

    Args:
        manager: Instance du WebSocketManager
        connection: Connexion du participant
        message: Message WebSocket recu
    """
    event = message.event_type
    data = message.data

    # -------------------------------------------------------------------------
    # Heartbeat Ping/Pong
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.PING:
        await manager.handle_ping(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
        )
        return

    # -------------------------------------------------------------------------
    # Changement d'etat audio
    # -------------------------------------------------------------------------
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
                "display_name": connection.display_name,
                "enabled": enabled,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # -------------------------------------------------------------------------
    # Changement d'etat video
    # -------------------------------------------------------------------------
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
                "display_name": connection.display_name,
                "enabled": enabled,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # -------------------------------------------------------------------------
    # Partage d'ecran demarre
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.SCREEN_SHARE_STARTED:
        await manager.update_participant_state(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            screen_sharing=True,
        )

        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.SCREEN_SHARE_STARTED,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # -------------------------------------------------------------------------
    # Partage d'ecran arrete
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.SCREEN_SHARE_STOPPED:
        await manager.update_participant_state(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            screen_sharing=False,
        )

        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.SCREEN_SHARE_STOPPED,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # -------------------------------------------------------------------------
    # Main levee
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Main baissee
    # -------------------------------------------------------------------------
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
                "display_name": connection.display_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # -------------------------------------------------------------------------
    # Message chat
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.CHAT_MESSAGE:
        content = data.get("content", "")
        message_type = data.get("type", "TEXT")
        recipient_id = data.get("recipient_id")  # Pour messages prives

        # Validation du contenu
        if not content or len(content) > 2000:
            await manager.send_to_participant(
                meeting_id=connection.meeting_id,
                participant_id=connection.participant_id,
                tenant_id=connection.tenant_id,
                event_type=WebSocketEventType.ERROR,
                data={"error": "Message invalide", "code": "INVALID_MESSAGE"},
            )
            return

        message_data = {
            "participant_id": str(connection.participant_id),
            "display_name": connection.display_name,
            "content": content,
            "type": message_type,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if recipient_id:
            # Message prive
            message_data["is_private"] = True
            message_data["recipient_id"] = recipient_id

            # Envoyer au destinataire
            await manager.send_to_participant(
                meeting_id=connection.meeting_id,
                participant_id=UUID(recipient_id),
                tenant_id=connection.tenant_id,
                event_type=WebSocketEventType.CHAT_MESSAGE,
                data=message_data,
            )
            # Envoyer aussi a l'expediteur (confirmation)
            await manager.send_to_participant(
                meeting_id=connection.meeting_id,
                participant_id=connection.participant_id,
                tenant_id=connection.tenant_id,
                event_type=WebSocketEventType.CHAT_MESSAGE,
                data=message_data,
            )
        else:
            # Message public
            await manager.broadcast_to_meeting(
                meeting_id=connection.meeting_id,
                tenant_id=connection.tenant_id,
                event_type=WebSocketEventType.CHAT_MESSAGE,
                data=message_data,
            )
        return

    # -------------------------------------------------------------------------
    # Reaction emoji
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.REACTION:
        emoji = data.get("emoji", "")

        if emoji:
            await manager.broadcast_to_meeting(
                meeting_id=connection.meeting_id,
                tenant_id=connection.tenant_id,
                event_type=WebSocketEventType.REACTION,
                data={
                    "participant_id": str(connection.participant_id),
                    "display_name": connection.display_name,
                    "emoji": emoji,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        return

    # -------------------------------------------------------------------------
    # Mise a jour tableau blanc
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.WHITEBOARD_UPDATE:
        update_data = data.get("update", {})

        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.WHITEBOARD_UPDATE,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "update": update_data,
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude_participant_id=connection.participant_id,
        )
        return

    # -------------------------------------------------------------------------
    # Position curseur tableau blanc
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.WHITEBOARD_CURSOR:
        x = data.get("x", 0)
        y = data.get("y", 0)

        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.WHITEBOARD_CURSOR,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "x": x,
                "y": y,
            },
            exclude_participant_id=connection.participant_id,
        )
        return

    # -------------------------------------------------------------------------
    # Indicateur de saisie (typing)
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Reaction au chat (like, etc.)
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.CHAT_REACTION:
        message_id = data.get("message_id")
        reaction = data.get("reaction", "")

        if message_id and reaction:
            await manager.broadcast_to_meeting(
                meeting_id=connection.meeting_id,
                tenant_id=connection.tenant_id,
                event_type=WebSocketEventType.CHAT_REACTION,
                data={
                    "participant_id": str(connection.participant_id),
                    "display_name": connection.display_name,
                    "message_id": message_id,
                    "reaction": reaction,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        return

    # -------------------------------------------------------------------------
    # Changement de fond d'ecran
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.BACKGROUND_CHANGED:
        background_type = data.get("type", "none")  # none, blur, image, video
        background_value = data.get("value", "")

        await manager.broadcast_to_meeting(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.BACKGROUND_CHANGED,
            data={
                "participant_id": str(connection.participant_id),
                "display_name": connection.display_name,
                "type": background_type,
                "value": background_value,
            },
        )
        return

    # -------------------------------------------------------------------------
    # Demande de synchronisation d'etat
    # -------------------------------------------------------------------------
    if event == WebSocketEventType.SYNC_STATE:
        participants = manager.get_participants(
            meeting_id=connection.meeting_id,
            tenant_id=connection.tenant_id,
        )

        await manager.send_to_participant(
            meeting_id=connection.meeting_id,
            participant_id=connection.participant_id,
            tenant_id=connection.tenant_id,
            event_type=WebSocketEventType.SYNC_STATE,
            data={
                "participants": participants,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return

    # -------------------------------------------------------------------------
    # Evenement non reconnu
    # -------------------------------------------------------------------------
    logger.debug(
        "websocket_unhandled_event",
        event_type=event.value if hasattr(event, 'value') else str(event),
        meeting_id=str(connection.meeting_id),
        participant_id=str(connection.participant_id),
    )


# =============================================================================
# Fonctions utilitaires d'export
# =============================================================================
def generate_videoconf_token(
    tenant_id: UUID,
    meeting_id: UUID,
    participant_id: UUID,
    role: str = "PARTICIPANT",
    user_id: Optional[UUID] = None,
    email: Optional[str] = None,
    display_name: str = "Participant",
    expires_hours: int = 8,
) -> str:
    """
    Genere un token JWT pour la connexion WebSocket videoconf.

    Cette fonction est un wrapper pour create_websocket_token avec
    des valeurs par defaut adaptees au module videoconf.

    Args:
        tenant_id: ID du tenant (isolation obligatoire)
        meeting_id: ID de la reunion
        participant_id: ID du participant
        role: Role du participant (ORGANISATEUR, CO_ORGANISATEUR, MODERATEUR, PARTICIPANT, OBSERVATEUR)
        user_id: ID utilisateur AZALPLUS (optionnel pour invites externes)
        email: Email du participant (optionnel)
        display_name: Nom affiche du participant
        expires_hours: Duree de validite du token en heures

    Returns:
        Token JWT pour authentification WebSocket
    """
    # Mapper le role string vers l'enum
    try:
        participant_role = ParticipantRole(role.upper())
    except ValueError:
        participant_role = ParticipantRole.PARTICIPANT

    return create_websocket_token(
        tenant_id=tenant_id,
        meeting_id=meeting_id,
        participant_id=participant_id,
        role=participant_role,
        user_id=user_id,
        email=email,
        display_name=display_name,
        expires_hours=expires_hours,
    )


# =============================================================================
# Exports
# =============================================================================
__all__ = [
    "websocket_router",
    "generate_videoconf_token",
]
