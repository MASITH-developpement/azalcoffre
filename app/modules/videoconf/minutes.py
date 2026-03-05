# =============================================================================
# AZALPLUS - Minutes Service (Claude AI)
# =============================================================================
"""
Service de generation de comptes-rendus de reunion via IA.
Utilise Claude pour synthetiser les transcriptions.
"""

import os
import json
from datetime import datetime
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
class MinutesStatus(str, Enum):
    """Statuts de compte-rendu."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SENT = "sent"
    REJECTED = "rejected"


class MinutesProvider(str, Enum):
    """Providers IA pour la generation."""
    CLAUDE = "claude"
    OPENAI = "openai"


# =============================================================================
# Minutes Service
# =============================================================================
class MinutesService:
    """
    Service de generation de comptes-rendus de reunion.

    Fonctionnalites:
    - Generation automatique depuis transcription
    - Structure professionnelle (resume, decisions, actions)
    - Workflow de validation
    - Envoi aux participants

    Utilise Claude (Anthropic) ou GPT-4 (OpenAI) pour la synthese.
    """

    DEFAULT_SYSTEM_PROMPT = """Tu es un assistant expert en redaction de comptes-rendus de reunions professionnelles.
A partir de la transcription fournie, genere un compte-rendu structure comprenant:

1. RESUME EXECUTIF (3-5 points cles)
2. PARTICIPANTS (liste des intervenants identifies)
3. POINTS ABORDES (resume de chaque sujet discute)
4. DECISIONS PRISES (avec responsable si mentionne)
5. ACTIONS A SUIVRE (avec responsable et deadline si mentionnes)
6. POINTS REPORTES (sujets a traiter lors d'une prochaine reunion)

Utilise un ton professionnel et concis. Structure le document avec des titres clairs.
Si des informations manquent, indique-le clairement."""

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service de comptes-rendus.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant pour l'isolation
        """
        self.db = db
        self.tenant_id = tenant_id
        self._config: Optional[dict] = None

    def _get_config(self) -> dict:
        """Charge la configuration."""
        if self._config is None:
            self._config = {
                "provider": os.environ.get("MINUTES_PROVIDER", "claude"),
                "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
                "claude_model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                "openai_model": "gpt-4o",
                "max_tokens": 4000,
                "temperature": 0.3,
                "system_prompt": self.DEFAULT_SYSTEM_PROMPT,
                "auto_generate_delay": 300,
                "notify_organizer": True,
            }
        return self._config

    # =========================================================================
    # Helpers
    # =========================================================================
    def _verify_meeting_access(self, meeting_id: UUID) -> Optional[dict]:
        """Verifie que la reunion appartient au tenant."""
        query = text("""
            SELECT r.id, r.titre, r.organisateur_id, r.statut,
                   u.email as organisateur_email, u.nom as organisateur_nom
            FROM azalplus.reunions r
            LEFT JOIN azalplus.users u ON r.organisateur_id = u.id
            WHERE r.id = :meeting_id
            AND r.tenant_id = :tenant_id
            AND r.deleted_at IS NULL
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def _get_transcription_text(self, meeting_id: UUID) -> str:
        """Recupere le texte complet de la transcription."""
        query = text("""
            SELECT s.text, s.speaker_id, s.start_time
            FROM azalplus.reunion_transcription_segments s
            JOIN azalplus.reunion_transcriptions t ON s.transcription_id = t.id
            WHERE t.reunion_id = :meeting_id
            AND t.tenant_id = :tenant_id
            ORDER BY s.start_time ASC
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })

        segments = []
        for row in result:
            speaker = row.speaker_id or "Participant"
            text_content = row.text.strip()
            if text_content:
                segments.append(f"[{speaker}]: {text_content}")

        return "\n".join(segments)

    async def _get_meeting_context(self, meeting_id: UUID) -> dict:
        """Recupere le contexte de la reunion."""
        meeting = self._verify_meeting_access(meeting_id)
        if not meeting:
            return {}

        # Participants
        part_query = text("""
            SELECT nom, role FROM azalplus.reunion_participants
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """)
        part_result = self.db.execute(part_query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        participants = [dict(r._mapping) for r in part_result]

        return {
            "titre": meeting.get("titre", "Reunion"),
            "organisateur": meeting.get("organisateur_nom", ""),
            "participants": participants
        }

    # =========================================================================
    # Generate Minutes
    # =========================================================================
    async def generate(
        self,
        meeting_id: UUID,
        custom_prompt: Optional[str] = None,
        generated_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Genere un compte-rendu a partir de la transcription.

        Args:
            meeting_id: ID de la reunion
            custom_prompt: Prompt personnalise (optionnel)
            generated_by: ID de l'utilisateur qui genere

        Returns:
            Compte-rendu genere
        """
        meeting = self._verify_meeting_access(meeting_id)
        if not meeting:
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Recuperer la transcription
        transcription_text = await self._get_transcription_text(meeting_id)
        if not transcription_text:
            raise ValueError("Aucune transcription disponible")

        # Contexte de la reunion
        context = await self._get_meeting_context(meeting_id)

        # Construire le prompt
        config = self._get_config()
        system_prompt = custom_prompt or config["system_prompt"]

        user_prompt = f"""# Reunion: {context.get('titre', 'Sans titre')}
# Organisateur: {context.get('organisateur', 'Non specifie')}
# Participants: {', '.join(p['nom'] for p in context.get('participants', []))}

## Transcription:
{transcription_text}
"""

        # Generer avec l'IA
        provider = config["provider"]
        if provider == MinutesProvider.CLAUDE.value:
            content = await self._generate_with_claude(system_prompt, user_prompt)
        elif provider == MinutesProvider.OPENAI.value:
            content = await self._generate_with_openai(system_prompt, user_prompt)
        else:
            raise ValueError(f"Provider non supporte: {provider}")

        # Creer le compte-rendu en base
        minutes_id = uuid4()
        now = datetime.utcnow()

        insert_query = text("""
            INSERT INTO azalplus.reunion_minutes
            (id, tenant_id, reunion_id, content, status, provider, model,
             prompt_used, generated_at, generated_by, created_at)
            VALUES (:id, :tenant_id, :reunion_id, :content, :status, :provider, :model,
                    :prompt_used, :generated_at, :generated_by, :created_at)
            RETURNING *
        """)

        result = self.db.execute(insert_query, {
            "id": str(minutes_id),
            "tenant_id": str(self.tenant_id),
            "reunion_id": str(meeting_id),
            "content": content,
            "status": MinutesStatus.DRAFT.value,
            "provider": provider,
            "model": config["claude_model"] if provider == "claude" else config["openai_model"],
            "prompt_used": system_prompt,
            "generated_at": now,
            "generated_by": str(generated_by) if generated_by else None,
            "created_at": now
        })
        self.db.commit()

        minutes = dict(result.fetchone()._mapping)

        logger.info(
            "minutes_generated",
            minutes_id=str(minutes_id),
            meeting_id=str(meeting_id),
            provider=provider,
            content_length=len(content)
        )

        return minutes

    async def _generate_with_claude(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """Genere avec Claude (Anthropic)."""
        config = self._get_config()
        api_key = config["anthropic_api_key"]

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY non configure")

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)

            message = client.messages.create(
                model=config["claude_model"],
                max_tokens=config["max_tokens"],
                temperature=config["temperature"],
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            return message.content[0].text

        except ImportError:
            raise ValueError("anthropic package non installe")
        except Exception as e:
            logger.error("claude_generation_error", error=str(e))
            raise ValueError(f"Erreur generation Claude: {str(e)}")

    async def _generate_with_openai(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """Genere avec GPT-4 (OpenAI)."""
        config = self._get_config()
        api_key = config["openai_api_key"]

        if not api_key:
            raise ValueError("OPENAI_API_KEY non configure")

        try:
            import openai

            client = openai.OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model=config["openai_model"],
                max_tokens=config["max_tokens"],
                temperature=config["temperature"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            return response.choices[0].message.content

        except ImportError:
            raise ValueError("openai package non installe")
        except Exception as e:
            logger.error("openai_generation_error", error=str(e))
            raise ValueError(f"Erreur generation OpenAI: {str(e)}")

    # =========================================================================
    # CRUD Operations
    # =========================================================================
    async def get(self, minutes_id: UUID) -> Dict[str, Any]:
        """
        Recupere un compte-rendu par ID.

        Args:
            minutes_id: ID du compte-rendu

        Returns:
            Compte-rendu
        """
        query = text("""
            SELECT m.*, r.titre as reunion_titre
            FROM azalplus.reunion_minutes m
            JOIN azalplus.reunions r ON m.reunion_id = r.id
            WHERE m.id = :minutes_id
            AND m.tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "minutes_id": str(minutes_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            raise ValueError(f"Compte-rendu {minutes_id} non trouve")

        return dict(row._mapping)

    async def list(
        self,
        meeting_id: UUID,
        status: Optional[MinutesStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Liste les comptes-rendus d'une reunion.

        Args:
            meeting_id: ID de la reunion
            status: Filtrer par statut

        Returns:
            Liste des comptes-rendus
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        sql = """
            SELECT * FROM azalplus.reunion_minutes
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """
        params = {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        }

        if status:
            sql += " AND status = :status"
            params["status"] = status.value

        sql += " ORDER BY created_at DESC"

        result = self.db.execute(text(sql), params)
        return [dict(r._mapping) for r in result]

    async def update(
        self,
        minutes_id: UUID,
        content: Optional[str] = None,
        updated_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Met a jour le contenu d'un compte-rendu.

        Args:
            minutes_id: ID du compte-rendu
            content: Nouveau contenu
            updated_by: ID de l'utilisateur

        Returns:
            Compte-rendu mis a jour
        """
        # Verifier que le CR existe et appartient au tenant
        existing = await self.get(minutes_id)

        if existing["status"] in [MinutesStatus.SENT.value]:
            raise ValueError("Impossible de modifier un compte-rendu deja envoye")

        update_query = text("""
            UPDATE azalplus.reunion_minutes
            SET content = COALESCE(:content, content),
                updated_at = :updated_at,
                updated_by = :updated_by
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(minutes_id),
            "tenant_id": str(self.tenant_id),
            "content": content,
            "updated_at": datetime.utcnow(),
            "updated_by": str(updated_by) if updated_by else None
        })
        self.db.commit()

        return dict(result.fetchone()._mapping)

    # =========================================================================
    # Workflow
    # =========================================================================
    async def approve(
        self,
        minutes_id: UUID,
        approved_by: UUID
    ) -> Dict[str, Any]:
        """
        Approuve un compte-rendu.

        Args:
            minutes_id: ID du compte-rendu
            approved_by: ID de l'approbateur

        Returns:
            Compte-rendu approuve
        """
        existing = await self.get(minutes_id)

        if existing["status"] not in [MinutesStatus.DRAFT.value, MinutesStatus.PENDING_REVIEW.value]:
            raise ValueError(f"Statut invalide pour approbation: {existing['status']}")

        update_query = text("""
            UPDATE azalplus.reunion_minutes
            SET status = :status,
                approved_at = :approved_at,
                approved_by = :approved_by
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(minutes_id),
            "tenant_id": str(self.tenant_id),
            "status": MinutesStatus.APPROVED.value,
            "approved_at": datetime.utcnow(),
            "approved_by": str(approved_by)
        })
        self.db.commit()

        minutes = dict(result.fetchone()._mapping)

        logger.info(
            "minutes_approved",
            minutes_id=str(minutes_id),
            approved_by=str(approved_by)
        )

        return minutes

    async def reject(
        self,
        minutes_id: UUID,
        rejected_by: UUID,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Rejette un compte-rendu.

        Args:
            minutes_id: ID du compte-rendu
            rejected_by: ID de l'utilisateur
            reason: Raison du rejet

        Returns:
            Compte-rendu rejete
        """
        existing = await self.get(minutes_id)

        update_query = text("""
            UPDATE azalplus.reunion_minutes
            SET status = :status,
                rejection_reason = :reason,
                rejected_at = :rejected_at,
                rejected_by = :rejected_by
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(minutes_id),
            "tenant_id": str(self.tenant_id),
            "status": MinutesStatus.REJECTED.value,
            "reason": reason,
            "rejected_at": datetime.utcnow(),
            "rejected_by": str(rejected_by)
        })
        self.db.commit()

        minutes = dict(result.fetchone()._mapping)

        logger.info(
            "minutes_rejected",
            minutes_id=str(minutes_id),
            rejected_by=str(rejected_by),
            reason=reason
        )

        return minutes

    async def submit_for_review(
        self,
        minutes_id: UUID,
        submitted_by: UUID
    ) -> Dict[str, Any]:
        """
        Soumet un compte-rendu pour validation.

        Args:
            minutes_id: ID du compte-rendu
            submitted_by: ID de l'utilisateur

        Returns:
            Compte-rendu soumis
        """
        existing = await self.get(minutes_id)

        if existing["status"] != MinutesStatus.DRAFT.value:
            raise ValueError("Seuls les brouillons peuvent etre soumis")

        update_query = text("""
            UPDATE azalplus.reunion_minutes
            SET status = :status,
                submitted_at = :submitted_at,
                submitted_by = :submitted_by
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(minutes_id),
            "tenant_id": str(self.tenant_id),
            "status": MinutesStatus.PENDING_REVIEW.value,
            "submitted_at": datetime.utcnow(),
            "submitted_by": str(submitted_by)
        })
        self.db.commit()

        return dict(result.fetchone()._mapping)

    # =========================================================================
    # Send to Participants
    # =========================================================================
    async def send(
        self,
        minutes_id: UUID,
        recipient_ids: Optional[List[UUID]] = None,
        include_organizer: bool = True,
        sent_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Envoie le compte-rendu aux participants.

        Args:
            minutes_id: ID du compte-rendu
            recipient_ids: IDs des destinataires (tous si None)
            include_organizer: Inclure l'organisateur
            sent_by: ID de l'expediteur

        Returns:
            Compte-rendu avec informations d'envoi
        """
        minutes = await self.get(minutes_id)

        if minutes["status"] != MinutesStatus.APPROVED.value:
            raise ValueError("Le compte-rendu doit etre approuve avant envoi")

        meeting_id = minutes["reunion_id"]

        # Recuperer les destinataires
        if recipient_ids:
            recipients = recipient_ids
        else:
            # Tous les participants
            part_query = text("""
                SELECT DISTINCT email
                FROM azalplus.reunion_participants
                WHERE reunion_id = :meeting_id
                AND tenant_id = :tenant_id
                AND email IS NOT NULL
            """)
            part_result = self.db.execute(part_query, {
                "meeting_id": str(meeting_id),
                "tenant_id": str(self.tenant_id)
            })
            recipients = [r.email for r in part_result]

        # Ajouter l'organisateur
        if include_organizer:
            meeting = self._verify_meeting_access(UUID(meeting_id))
            if meeting and meeting.get("organisateur_email"):
                recipients.append(meeting["organisateur_email"])

        recipients = list(set(recipients))  # Deduplicate

        # TODO: Integrer avec le service de notifications pour envoyer les emails
        # Pour l'instant, on marque juste comme envoye

        now = datetime.utcnow()
        update_query = text("""
            UPDATE azalplus.reunion_minutes
            SET status = :status,
                sent_at = :sent_at,
                sent_by = :sent_by,
                sent_to = :sent_to
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(update_query, {
            "id": str(minutes_id),
            "tenant_id": str(self.tenant_id),
            "status": MinutesStatus.SENT.value,
            "sent_at": now,
            "sent_by": str(sent_by) if sent_by else None,
            "sent_to": json.dumps(recipients)
        })
        self.db.commit()

        updated_minutes = dict(result.fetchone()._mapping)

        logger.info(
            "minutes_sent",
            minutes_id=str(minutes_id),
            recipient_count=len(recipients)
        )

        return {
            **updated_minutes,
            "recipients": recipients,
            "recipient_count": len(recipients)
        }

    # =========================================================================
    # Export
    # =========================================================================
    async def export(
        self,
        minutes_id: UUID,
        format: str = "markdown"
    ) -> Dict[str, Any]:
        """
        Exporte le compte-rendu dans un format specifique.

        Args:
            minutes_id: ID du compte-rendu
            format: Format d'export (markdown, html, pdf, docx)

        Returns:
            Contenu exporte
        """
        minutes = await self.get(minutes_id)
        content = minutes["content"]

        if format == "markdown":
            return {
                "content": content,
                "format": "markdown",
                "filename": f"compte_rendu_{minutes_id}.md"
            }

        elif format == "html":
            # Conversion simple markdown vers HTML
            html_content = self._markdown_to_html(content)
            return {
                "content": html_content,
                "format": "html",
                "filename": f"compte_rendu_{minutes_id}.html"
            }

        elif format == "pdf":
            # TODO: Integrer WeasyPrint pour generation PDF
            raise ValueError("Export PDF non encore implemente")

        elif format == "docx":
            # TODO: Integrer python-docx
            raise ValueError("Export DOCX non encore implemente")

        else:
            raise ValueError(f"Format non supporte: {format}")

    def _markdown_to_html(self, markdown_text: str) -> str:
        """Conversion basique markdown vers HTML."""
        try:
            import markdown
            return markdown.markdown(markdown_text)
        except ImportError:
            # Conversion manuelle basique
            html = markdown_text
            # Titres
            import re
            html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
            html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
            html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
            # Paragraphes
            html = re.sub(r'\n\n', '</p><p>', html)
            html = f"<p>{html}</p>"
            # Listes
            html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
            return html
