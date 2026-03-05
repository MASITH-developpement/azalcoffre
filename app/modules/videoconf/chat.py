# =============================================================================
# AZALPLUS - VideoConf Chat Service
# =============================================================================
"""
Service de gestion du chat en reunion.

Fonctionnalites:
- Envoi et reception de messages
- Reactions (emojis)
- Export du chat
- Historique persistant
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from enum import Enum

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger()


class MessageType(str, Enum):
    """Types de messages chat."""
    TEXT = "text"
    FILE = "file"
    SYSTEM = "system"
    REACTION = "reaction"


class ChatService:
    """Service de gestion du chat en reunion."""

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service chat.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant (isolation obligatoire)
        """
        self.db = db
        self.tenant_id = tenant_id
        self._table_name = "reunion_chat_messages"

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

    def _verify_participant_access(
        self,
        meeting_id: UUID,
        participant_id: UUID
    ) -> bool:
        """Verifie que le participant appartient a la reunion."""
        query = text("""
            SELECT id FROM azalplus.reunion_participants
            WHERE id = :participant_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "participant_id": str(participant_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        return result.fetchone() is not None

    # =========================================================================
    # Messages
    # =========================================================================
    async def send_message(
        self,
        meeting_id: UUID,
        participant_id: UUID,
        content: str,
        message_type: MessageType = MessageType.TEXT,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Envoie un message dans le chat de la reunion.

        Args:
            meeting_id: ID de la reunion
            participant_id: ID du participant emetteur
            content: Contenu du message
            message_type: Type de message (text, file, system)
            metadata: Metadonnees additionnelles (fichier, mentions, etc.)

        Returns:
            Message cree

        Raises:
            ValueError: Si la reunion ou le participant n'existe pas
            PermissionError: Si le participant n'a pas acces
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            logger.warning(
                "chat_meeting_not_found",
                meeting_id=str(meeting_id),
                tenant_id=str(self.tenant_id)
            )
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Verification participant
        if not self._verify_participant_access(meeting_id, participant_id):
            logger.warning(
                "chat_participant_invalid",
                participant_id=str(participant_id),
                meeting_id=str(meeting_id)
            )
            raise PermissionError("Participant non autorise")

        # Validation contenu
        if not content or len(content.strip()) == 0:
            raise ValueError("Message vide")

        if len(content) > 4000:
            raise ValueError("Message trop long (max 4000 caracteres)")

        message_id = uuid4()
        now = datetime.utcnow()

        # Inserer le message
        query = text("""
            INSERT INTO azalplus.reunion_chat_messages
            (id, tenant_id, reunion_id, participant_id, content, message_type, metadata, created_at)
            VALUES (:id, :tenant_id, :reunion_id, :participant_id, :content, :message_type, :metadata, :created_at)
            RETURNING *
        """)

        import json
        result = self.db.execute(query, {
            "id": str(message_id),
            "tenant_id": str(self.tenant_id),
            "reunion_id": str(meeting_id),
            "participant_id": str(participant_id),
            "content": content.strip(),
            "message_type": message_type.value,
            "metadata": json.dumps(metadata) if metadata else None,
            "created_at": now
        })
        self.db.commit()

        row = result.fetchone()
        message = dict(row._mapping) if row else None

        logger.info(
            "chat_message_sent",
            message_id=str(message_id),
            meeting_id=str(meeting_id),
            participant_id=str(participant_id),
            message_type=message_type.value
        )

        return message

    async def get_messages(
        self,
        meeting_id: UUID,
        limit: int = 100,
        offset: int = 0,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupere les messages d'une reunion.

        Args:
            meeting_id: ID de la reunion
            limit: Nombre max de messages (defaut 100, max 500)
            offset: Offset pour pagination
            since: Filtrer les messages apres cette date

        Returns:
            Liste des messages avec informations participant
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Limiter le nombre de messages
        limit = min(limit, 500)

        # Construire la requete
        sql = """
            SELECT
                m.id,
                m.reunion_id,
                m.participant_id,
                m.content,
                m.message_type,
                m.metadata,
                m.created_at,
                p.nom as participant_nom,
                p.email as participant_email,
                p.role as participant_role
            FROM azalplus.reunion_chat_messages m
            LEFT JOIN azalplus.reunion_participants p ON m.participant_id = p.id
            WHERE m.reunion_id = :meeting_id
            AND m.tenant_id = :tenant_id
        """
        params = {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        }

        if since:
            sql += " AND m.created_at > :since"
            params["since"] = since

        sql += " ORDER BY m.created_at ASC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = self.db.execute(text(sql), params)
        messages = [dict(row._mapping) for row in result]

        logger.debug(
            "chat_messages_fetched",
            meeting_id=str(meeting_id),
            count=len(messages)
        )

        return messages

    async def add_reaction(
        self,
        message_id: UUID,
        participant_id: UUID,
        emoji: str
    ) -> Dict[str, Any]:
        """
        Ajoute une reaction a un message.

        Args:
            message_id: ID du message
            participant_id: ID du participant qui reagit
            emoji: Emoji de reaction

        Returns:
            Message mis a jour avec reactions
        """
        # Emojis autorises
        allowed_emojis = ["👍", "👎", "❤️", "😀", "😮", "🎉", "🤔", "👏"]
        if emoji not in allowed_emojis:
            raise ValueError(f"Emoji non autorise. Utiliser: {allowed_emojis}")

        # Verifier que le message existe et appartient au tenant
        query = text("""
            SELECT m.*, r.id as reunion_id
            FROM azalplus.reunion_chat_messages m
            JOIN azalplus.reunions r ON m.reunion_id = r.id
            WHERE m.id = :message_id
            AND m.tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "message_id": str(message_id),
            "tenant_id": str(self.tenant_id)
        })
        message = result.fetchone()

        if not message:
            raise ValueError(f"Message {message_id} non trouve")

        # Verifier que le participant a acces
        if not self._verify_participant_access(message.reunion_id, participant_id):
            raise PermissionError("Participant non autorise")

        # Ajouter la reaction
        reaction_id = uuid4()
        insert_query = text("""
            INSERT INTO azalplus.reunion_chat_reactions
            (id, tenant_id, message_id, participant_id, emoji, created_at)
            VALUES (:id, :tenant_id, :message_id, :participant_id, :emoji, :created_at)
            ON CONFLICT (message_id, participant_id, emoji) DO NOTHING
        """)
        self.db.execute(insert_query, {
            "id": str(reaction_id),
            "tenant_id": str(self.tenant_id),
            "message_id": str(message_id),
            "participant_id": str(participant_id),
            "emoji": emoji,
            "created_at": datetime.utcnow()
        })
        self.db.commit()

        # Recuperer les reactions du message
        reactions_query = text("""
            SELECT emoji, COUNT(*) as count,
                   array_agg(participant_id) as participants
            FROM azalplus.reunion_chat_reactions
            WHERE message_id = :message_id
            GROUP BY emoji
        """)
        reactions_result = self.db.execute(reactions_query, {
            "message_id": str(message_id)
        })
        reactions = [dict(row._mapping) for row in reactions_result]

        logger.info(
            "chat_reaction_added",
            message_id=str(message_id),
            participant_id=str(participant_id),
            emoji=emoji
        )

        return {
            "message_id": str(message_id),
            "reactions": reactions
        }

    async def remove_reaction(
        self,
        message_id: UUID,
        participant_id: UUID,
        emoji: str
    ) -> bool:
        """
        Supprime une reaction d'un message.

        Args:
            message_id: ID du message
            participant_id: ID du participant
            emoji: Emoji a supprimer

        Returns:
            True si la reaction a ete supprimee
        """
        query = text("""
            DELETE FROM azalplus.reunion_chat_reactions
            WHERE message_id = :message_id
            AND participant_id = :participant_id
            AND emoji = :emoji
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "message_id": str(message_id),
            "participant_id": str(participant_id),
            "emoji": emoji,
            "tenant_id": str(self.tenant_id)
        })
        self.db.commit()

        deleted = result.rowcount > 0

        if deleted:
            logger.info(
                "chat_reaction_removed",
                message_id=str(message_id),
                participant_id=str(participant_id),
                emoji=emoji
            )

        return deleted

    async def delete_message(
        self,
        message_id: UUID,
        deleted_by: Optional[UUID] = None
    ) -> bool:
        """
        Supprime un message (soft delete).

        Args:
            message_id: ID du message
            deleted_by: ID de l'utilisateur effectuant la suppression

        Returns:
            True si le message a ete supprime
        """
        query = text("""
            UPDATE azalplus.reunion_chat_messages
            SET deleted_at = :now,
                deleted_by = :deleted_by,
                content = '[Message supprime]'
            WHERE id = :message_id
            AND tenant_id = :tenant_id
            AND deleted_at IS NULL
        """)
        result = self.db.execute(query, {
            "message_id": str(message_id),
            "tenant_id": str(self.tenant_id),
            "now": datetime.utcnow(),
            "deleted_by": str(deleted_by) if deleted_by else None
        })
        self.db.commit()

        deleted = result.rowcount > 0

        if deleted:
            logger.info(
                "chat_message_deleted",
                message_id=str(message_id),
                deleted_by=str(deleted_by) if deleted_by else None
            )

        return deleted

    # =========================================================================
    # Export
    # =========================================================================
    async def export_chat(
        self,
        meeting_id: UUID,
        format: str = "text",
        include_timestamps: bool = True,
        include_system_messages: bool = False
    ) -> str:
        """
        Exporte le chat d'une reunion en texte formate.

        Args:
            meeting_id: ID de la reunion
            format: Format d'export (text, markdown, json)
            include_timestamps: Inclure les horodatages
            include_system_messages: Inclure les messages systeme

        Returns:
            Chat exporte en texte formate
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Recuperer les messages
        sql = """
            SELECT
                m.content,
                m.message_type,
                m.created_at,
                p.nom as participant_nom
            FROM azalplus.reunion_chat_messages m
            LEFT JOIN azalplus.reunion_participants p ON m.participant_id = p.id
            WHERE m.reunion_id = :meeting_id
            AND m.tenant_id = :tenant_id
            AND m.deleted_at IS NULL
        """
        params = {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        }

        if not include_system_messages:
            sql += " AND m.message_type != 'system'"

        sql += " ORDER BY m.created_at ASC"

        result = self.db.execute(text(sql), params)
        messages = [dict(row._mapping) for row in result]

        # Recuperer les infos de la reunion
        reunion_query = text("""
            SELECT titre, date_debut, date_fin
            FROM azalplus.reunions
            WHERE id = :meeting_id AND tenant_id = :tenant_id
        """)
        reunion_result = self.db.execute(reunion_query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        reunion = reunion_result.fetchone()

        # Formater l'export
        if format == "json":
            import json
            return json.dumps({
                "meeting_id": str(meeting_id),
                "title": reunion.titre if reunion else "Reunion",
                "date": reunion.date_debut.isoformat() if reunion and reunion.date_debut else None,
                "messages": messages
            }, ensure_ascii=False, indent=2, default=str)

        # Format texte ou markdown
        lines = []

        if format == "markdown":
            lines.append(f"# Chat - {reunion.titre if reunion else 'Reunion'}")
            if reunion and reunion.date_debut:
                lines.append(f"*{reunion.date_debut.strftime('%d/%m/%Y %H:%M')}*")
            lines.append("")
            lines.append("---")
            lines.append("")
        else:
            lines.append(f"=== CHAT - {reunion.titre if reunion else 'REUNION'} ===")
            if reunion and reunion.date_debut:
                lines.append(f"Date: {reunion.date_debut.strftime('%d/%m/%Y %H:%M')}")
            lines.append("")

        for msg in messages:
            participant = msg.get("participant_nom") or "Inconnu"
            content = msg["content"]
            msg_type = msg.get("message_type", "text")
            timestamp = msg.get("created_at")

            if msg_type == "system":
                if format == "markdown":
                    line = f"*[SYSTEME] {content}*"
                else:
                    line = f"[SYSTEME] {content}"
            else:
                if include_timestamps and timestamp:
                    ts = timestamp.strftime("%H:%M")
                    if format == "markdown":
                        line = f"**[{ts}] {participant}:** {content}"
                    else:
                        line = f"[{ts}] {participant}: {content}"
                else:
                    if format == "markdown":
                        line = f"**{participant}:** {content}"
                    else:
                        line = f"{participant}: {content}"

            lines.append(line)

        export_text = "\n".join(lines)

        logger.info(
            "chat_exported",
            meeting_id=str(meeting_id),
            format=format,
            message_count=len(messages)
        )

        return export_text

    # =========================================================================
    # Messages systeme
    # =========================================================================
    async def send_system_message(
        self,
        meeting_id: UUID,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Envoie un message systeme (sans participant).

        Args:
            meeting_id: ID de la reunion
            content: Contenu du message systeme
            metadata: Metadonnees additionnelles

        Returns:
            Message systeme cree
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        message_id = uuid4()
        now = datetime.utcnow()

        query = text("""
            INSERT INTO azalplus.reunion_chat_messages
            (id, tenant_id, reunion_id, participant_id, content, message_type, metadata, created_at)
            VALUES (:id, :tenant_id, :reunion_id, NULL, :content, 'system', :metadata, :created_at)
            RETURNING *
        """)

        import json
        result = self.db.execute(query, {
            "id": str(message_id),
            "tenant_id": str(self.tenant_id),
            "reunion_id": str(meeting_id),
            "content": content,
            "metadata": json.dumps(metadata) if metadata else None,
            "created_at": now
        })
        self.db.commit()

        row = result.fetchone()
        message = dict(row._mapping) if row else None

        logger.info(
            "chat_system_message_sent",
            message_id=str(message_id),
            meeting_id=str(meeting_id),
            content=content[:50]
        )

        return message
