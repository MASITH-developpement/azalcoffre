# =============================================================================
# AZALPLUS - VideoConf Media Control Service
# =============================================================================
"""
Service de controle des medias en reunion.

Fonctionnalites:
- Mute/unmute participants (audio/video)
- Controle organizer (mute all, kick)
- Transfert de role organisateur
- Integration LiveKit pour les actions
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from enum import Enum

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger()


class TrackType(str, Enum):
    """Types de tracks media."""
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN = "screen"


class ParticipantRole(str, Enum):
    """Roles des participants."""
    ORGANIZER = "organizer"
    CO_HOST = "co_host"
    PRESENTER = "presenter"
    PARTICIPANT = "participant"


class MediaControlService:
    """Service de controle des medias en reunion."""

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service de controle media.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant (isolation obligatoire)
        """
        self.db = db
        self.tenant_id = tenant_id
        self._livekit_manager: Optional["LiveKitRoomManager"] = None

    # =========================================================================
    # LiveKit Integration
    # =========================================================================
    def _get_livekit_manager(self) -> "LiveKitRoomManager":
        """Obtient ou cree le manager LiveKit."""
        if self._livekit_manager is None:
            try:
                from .livekit_manager import LiveKitRoomManager
                self._livekit_manager = LiveKitRoomManager()
            except ImportError:
                logger.warning("livekit_manager_not_available")
                self._livekit_manager = None
        return self._livekit_manager

    async def _sync_with_livekit(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        action: str,
        track_type: Optional[TrackType] = None
    ) -> bool:
        """
        Synchronise l'action avec le serveur LiveKit.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            action: Action a effectuer (mute, unmute, kick)
            track_type: Type de track concerne

        Returns:
            True si l'action a ete synchronisee
        """
        manager = self._get_livekit_manager()
        if not manager:
            logger.debug("livekit_sync_skipped", reason="manager_unavailable")
            return True  # Continuer sans LiveKit

        try:
            # Recuperer le room name et participant identity
            room_query = text("""
                SELECT r.livekit_room_name, p.livekit_identity
                FROM azalplus.reunions r
                JOIN azalplus.reunion_participants p ON p.reunion_id = r.id
                WHERE r.id = :meeting_id
                AND p.id = :participant_id
                AND r.tenant_id = :tenant_id
            """)
            result = self.db.execute(room_query, {
                "meeting_id": str(meeting_id),
                "participant_id": str(participant_id),
                "tenant_id": str(self.tenant_id)
            })
            row = result.fetchone()

            if not row or not row.livekit_room_name:
                return True  # Pas de room LiveKit active

            room_name = row.livekit_room_name
            identity = row.livekit_identity or str(participant_id)

            if action == "mute":
                await manager.mute_participant(
                    room_name=room_name,
                    identity=identity,
                    track_type=track_type.value if track_type else "audio"
                )
            elif action == "unmute":
                await manager.unmute_participant(
                    room_name=room_name,
                    identity=identity,
                    track_type=track_type.value if track_type else "audio"
                )
            elif action == "kick":
                await manager.remove_participant(
                    room_name=room_name,
                    identity=identity
                )

            return True

        except Exception as e:
            logger.error(
                "livekit_sync_error",
                action=action,
                meeting_id=str(meeting_id),
                participant_id=str(participant_id),
                error=str(e)
            )
            return False

    # =========================================================================
    # Helpers
    # =========================================================================
    def _verify_meeting_access(self, meeting_id: UUID) -> bool:
        """Verifie que la reunion appartient au tenant."""
        query = text("""
            SELECT id FROM azalplus.reunions
            WHERE id = :meeting_id
            AND tenant_id = :tenant_id
            AND deleted_at IS NULL
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        return result.fetchone() is not None

    def _get_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Recupere les informations d'un participant."""
        query = text("""
            SELECT id, nom, email, role, is_muted_audio, is_muted_video,
                   joined_at, left_at, livekit_identity
            FROM azalplus.reunion_participants
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _is_organizer(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> bool:
        """Verifie si le participant est organisateur ou co-host."""
        participant = self._get_participant(meeting_id, participant_id)
        if not participant:
            return False
        return participant.get("role") in [
            ParticipantRole.ORGANIZER.value,
            ParticipantRole.CO_HOST.value
        ]

    def _log_action(
        self,
        meeting_id: UUID,
        action: str,
        target_participant_id: Optional[UUID] = None,
        performed_by: Optional[UUID] = None,
        details: Optional[dict] = None
    ) -> None:
        """Enregistre une action dans l'audit trail."""
        try:
            import json
            query = text("""
                INSERT INTO azalplus.reunion_audit_log
                (id, tenant_id, reunion_id, action, target_participant_id,
                 performed_by, details, created_at)
                VALUES (:id, :tenant_id, :reunion_id, :action, :target_participant_id,
                        :performed_by, :details, :created_at)
            """)
            self.db.execute(query, {
                "id": str(uuid4()),
                "tenant_id": str(self.tenant_id),
                "reunion_id": str(meeting_id),
                "action": action,
                "target_participant_id": str(target_participant_id) if target_participant_id else None,
                "performed_by": str(performed_by) if performed_by else None,
                "details": json.dumps(details) if details else None,
                "created_at": datetime.utcnow()
            })
        except Exception as e:
            logger.warning("audit_log_error", error=str(e))

    # =========================================================================
    # Mute / Unmute
    # =========================================================================
    async def mute_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        track_type: TrackType = TrackType.AUDIO,
        by_organizer: bool = False,
        muted_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Mute un participant (audio ou video).

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant a muter
            track_type: Type de track a muter (audio, video, screen)
            by_organizer: True si mute par l'organisateur (ne peut pas se demuter)
            muted_by: ID de celui qui effectue le mute

        Returns:
            Participant mis a jour

        Raises:
            ValueError: Si reunion/participant non trouve
            PermissionError: Si pas autorise a muter
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Verification participant
        participant = self._get_participant(meeting_id, participant_id)
        if not participant:
            raise ValueError(f"Participant {participant_id} non trouve")

        # Si mute par organisateur, verifier les permissions
        if by_organizer and muted_by:
            if not self._is_organizer(meeting_id, muted_by):
                raise PermissionError("Seul l'organisateur peut muter les autres participants")

        # Mise a jour en base
        column = f"is_muted_{track_type.value}"
        muted_by_column = f"muted_{track_type.value}_by"

        query = text(f"""
            UPDATE azalplus.reunion_participants
            SET {column} = true,
                {muted_by_column} = :muted_by,
                muted_by_organizer = :by_organizer
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "muted_by": str(muted_by) if muted_by else None,
            "by_organizer": by_organizer
        })
        self.db.commit()

        row = result.fetchone()
        updated_participant = dict(row._mapping) if row else None

        # Synchroniser avec LiveKit
        await self._sync_with_livekit(meeting_id, participant_id, "mute", track_type)

        # Audit log
        self._log_action(
            meeting_id=meeting_id,
            action=f"mute_{track_type.value}",
            target_participant_id=participant_id,
            performed_by=muted_by,
            details={"by_organizer": by_organizer}
        )

        logger.info(
            "participant_muted",
            meeting_id=str(meeting_id),
            participant_id=str(participant_id),
            track_type=track_type.value,
            by_organizer=by_organizer
        )

        return updated_participant

    async def unmute_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        track_type: TrackType = TrackType.AUDIO,
        unmuted_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Demute un participant.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            track_type: Type de track
            unmuted_by: ID de celui qui effectue le unmute

        Returns:
            Participant mis a jour

        Raises:
            ValueError: Si reunion/participant non trouve
            PermissionError: Si mute par organisateur et pas autorise
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Verification participant
        participant = self._get_participant(meeting_id, participant_id)
        if not participant:
            raise ValueError(f"Participant {participant_id} non trouve")

        # Verifier si mute par organisateur
        if participant.get("muted_by_organizer"):
            # Seul l'organisateur peut demuter
            if unmuted_by and not self._is_organizer(meeting_id, unmuted_by):
                # Le participant lui-meme peut lever la main pour demander
                if str(unmuted_by) != str(participant_id):
                    raise PermissionError("Mute par l'organisateur - demandez a l'organisateur")

        # Mise a jour en base
        column = f"is_muted_{track_type.value}"

        query = text(f"""
            UPDATE azalplus.reunion_participants
            SET {column} = false,
                muted_by_organizer = false
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        self.db.commit()

        row = result.fetchone()
        updated_participant = dict(row._mapping) if row else None

        # Synchroniser avec LiveKit
        await self._sync_with_livekit(meeting_id, participant_id, "unmute", track_type)

        # Audit log
        self._log_action(
            meeting_id=meeting_id,
            action=f"unmute_{track_type.value}",
            target_participant_id=participant_id,
            performed_by=unmuted_by
        )

        logger.info(
            "participant_unmuted",
            meeting_id=str(meeting_id),
            participant_id=str(participant_id),
            track_type=track_type.value
        )

        return updated_participant

    async def mute_all(
        self,
        meeting_id: UUID,
        except_organizer: bool = True,
        muted_by: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Mute tous les participants (sauf organisateur optionnellement).

        Args:
            meeting_id: ID de la reunion
            except_organizer: Exclure l'organisateur du mute
            muted_by: ID de celui qui effectue le mute

        Returns:
            Liste des participants mutes

        Raises:
            PermissionError: Si pas organisateur
        """
        # Verification permissions
        if muted_by and not self._is_organizer(meeting_id, muted_by):
            raise PermissionError("Seul l'organisateur peut muter tous les participants")

        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Construire la requete
        sql = """
            UPDATE azalplus.reunion_participants
            SET is_muted_audio = true,
                muted_by_organizer = true,
                muted_audio_by = :muted_by
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            AND left_at IS NULL
        """
        params = {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "muted_by": str(muted_by) if muted_by else None
        }

        if except_organizer:
            sql += " AND role NOT IN ('organizer', 'co_host')"

        sql += " RETURNING *"

        result = self.db.execute(text(sql), params)
        self.db.commit()

        muted_participants = [dict(row._mapping) for row in result]

        # Synchroniser avec LiveKit pour chaque participant
        manager = self._get_livekit_manager()
        if manager:
            for p in muted_participants:
                try:
                    await self._sync_with_livekit(
                        meeting_id, UUID(p["id"]), "mute", TrackType.AUDIO
                    )
                except Exception as e:
                    logger.warning(
                        "livekit_mute_all_partial_error",
                        participant_id=p["id"],
                        error=str(e)
                    )

        # Audit log
        self._log_action(
            meeting_id=meeting_id,
            action="mute_all",
            performed_by=muted_by,
            details={
                "except_organizer": except_organizer,
                "count": len(muted_participants)
            }
        )

        logger.info(
            "all_participants_muted",
            meeting_id=str(meeting_id),
            count=len(muted_participants),
            except_organizer=except_organizer
        )

        return muted_participants

    async def disable_camera(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        disabled_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Desactive la camera d'un participant.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            disabled_by: ID de celui qui desactive

        Returns:
            Participant mis a jour
        """
        return await self.mute_participant(
            meeting_id=meeting_id,
            participant_id=participant_id,
            track_type=TrackType.VIDEO,
            by_organizer=True,
            muted_by=disabled_by
        )

    # =========================================================================
    # Kick / Remove participant
    # =========================================================================
    async def kick_participant(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        reason: Optional[str] = None,
        kicked_by: Optional[UUID] = None
    ) -> bool:
        """
        Expulse un participant de la reunion.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant a expulser
            reason: Raison de l'expulsion
            kicked_by: ID de celui qui expulse

        Returns:
            True si expulsion reussie

        Raises:
            PermissionError: Si pas organisateur
            ValueError: Impossible d'expulser l'organisateur principal
        """
        # Verification permissions
        if kicked_by and not self._is_organizer(meeting_id, kicked_by):
            raise PermissionError("Seul l'organisateur peut expulser des participants")

        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Verification participant
        participant = self._get_participant(meeting_id, participant_id)
        if not participant:
            raise ValueError(f"Participant {participant_id} non trouve")

        # Impossible d'expulser l'organisateur principal
        if participant.get("role") == ParticipantRole.ORGANIZER.value:
            raise ValueError("Impossible d'expulser l'organisateur principal")

        # Marquer comme parti (kicked)
        query = text("""
            UPDATE azalplus.reunion_participants
            SET left_at = :now,
                kicked = true,
                kick_reason = :reason,
                kicked_by = :kicked_by
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            AND left_at IS NULL
        """)

        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "now": datetime.utcnow(),
            "reason": reason,
            "kicked_by": str(kicked_by) if kicked_by else None
        })
        self.db.commit()

        success = result.rowcount > 0

        if success:
            # Synchroniser avec LiveKit
            await self._sync_with_livekit(meeting_id, participant_id, "kick")

            # Audit log
            self._log_action(
                meeting_id=meeting_id,
                action="kick_participant",
                target_participant_id=participant_id,
                performed_by=kicked_by,
                details={"reason": reason}
            )

            logger.info(
                "participant_kicked",
                meeting_id=str(meeting_id),
                participant_id=str(participant_id),
                reason=reason
            )

        return success

    # =========================================================================
    # Transfer organizer role
    # =========================================================================
    async def transfer_organizer(
        self,
        meeting_id: UUID,
        new_organizer_id: UUID,
        transferred_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Transfere le role d'organisateur a un autre participant.

        Args:
            meeting_id: ID de la reunion
            new_organizer_id: ID du nouveau organisateur
            transferred_by: ID de l'organisateur actuel

        Returns:
            Nouveau organisateur

        Raises:
            PermissionError: Si pas organisateur actuel
            ValueError: Si nouveau organisateur non valide
        """
        # Verification permissions
        if transferred_by and not self._is_organizer(meeting_id, transferred_by):
            raise PermissionError("Seul l'organisateur peut transferer le role")

        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Verification nouveau organisateur
        new_organizer = self._get_participant(meeting_id, new_organizer_id)
        if not new_organizer:
            raise ValueError(f"Participant {new_organizer_id} non trouve")

        if new_organizer.get("left_at"):
            raise ValueError("Le participant a quitte la reunion")

        # Transaction: changer les roles
        # 1. Ancien organisateur devient co-host
        if transferred_by:
            demote_query = text("""
                UPDATE azalplus.reunion_participants
                SET role = 'co_host'
                WHERE id = :participant_id
                AND reunion_id = :meeting_id
                AND tenant_id = :tenant_id
                AND role = 'organizer'
            """)
            self.db.execute(demote_query, {
                "participant_id": str(transferred_by),
                "meeting_id": str(meeting_id),
                "tenant_id": str(self.tenant_id)
            })

        # 2. Nouveau organisateur
        promote_query = text("""
            UPDATE azalplus.reunion_participants
            SET role = 'organizer'
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            RETURNING *
        """)
        result = self.db.execute(promote_query, {
            "participant_id": str(new_organizer_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })

        # 3. Mettre a jour la reunion
        update_meeting = text("""
            UPDATE azalplus.reunions
            SET organizer_id = :new_organizer_id
            WHERE id = :meeting_id
            AND tenant_id = :tenant_id
        """)
        self.db.execute(update_meeting, {
            "new_organizer_id": str(new_organizer_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })

        self.db.commit()

        row = result.fetchone()
        updated_organizer = dict(row._mapping) if row else None

        # Audit log
        self._log_action(
            meeting_id=meeting_id,
            action="transfer_organizer",
            target_participant_id=new_organizer_id,
            performed_by=transferred_by,
            details={"previous_organizer": str(transferred_by) if transferred_by else None}
        )

        logger.info(
            "organizer_transferred",
            meeting_id=str(meeting_id),
            new_organizer_id=str(new_organizer_id),
            previous_organizer_id=str(transferred_by) if transferred_by else None
        )

        return updated_organizer

    # =========================================================================
    # Raise / Lower hand
    # =========================================================================
    async def raise_hand(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> Dict[str, Any]:
        """
        Lever la main pour demander la parole.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant

        Returns:
            Participant mis a jour
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        query = text("""
            UPDATE azalplus.reunion_participants
            SET hand_raised = true,
                hand_raised_at = :now
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "now": datetime.utcnow()
        })
        self.db.commit()

        row = result.fetchone()

        logger.info(
            "hand_raised",
            meeting_id=str(meeting_id),
            participant_id=str(participant_id)
        )

        return dict(row._mapping) if row else None

    async def lower_hand(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        lowered_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Baisser la main.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant
            lowered_by: ID de celui qui baisse la main (si organisateur)

        Returns:
            Participant mis a jour
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        query = text("""
            UPDATE azalplus.reunion_participants
            SET hand_raised = false,
                hand_raised_at = NULL
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        self.db.commit()

        row = result.fetchone()

        logger.info(
            "hand_lowered",
            meeting_id=str(meeting_id),
            participant_id=str(participant_id),
            lowered_by=str(lowered_by) if lowered_by else None
        )

        return dict(row._mapping) if row else None

    async def lower_all_hands(
        self,
        meeting_id: UUID,
        lowered_by: Optional[UUID] = None
    ) -> int:
        """
        Baisser toutes les mains levees.

        Args:
            meeting_id: ID de la reunion
            lowered_by: ID de l'organisateur

        Returns:
            Nombre de mains baissees
        """
        if lowered_by and not self._is_organizer(meeting_id, lowered_by):
            raise PermissionError("Seul l'organisateur peut baisser toutes les mains")

        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        query = text("""
            UPDATE azalplus.reunion_participants
            SET hand_raised = false,
                hand_raised_at = NULL
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            AND hand_raised = true
        """)

        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        self.db.commit()

        count = result.rowcount

        logger.info(
            "all_hands_lowered",
            meeting_id=str(meeting_id),
            count=count
        )

        return count
