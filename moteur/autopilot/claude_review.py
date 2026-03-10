# =============================================================================
# AUTOPILOT - Claude Review: Interface pour que Claude traite les erreurs
# =============================================================================
"""
Claude Review: Permet à Claude de consulter et traiter les erreurs en attente.

Quand Claude est disponible (l'utilisateur lui parle), il peut:
1. Voir toutes les erreurs en attente
2. Décider de les corriger ou rejeter
3. Appliquer les corrections

Usage:
    from moteur.autopilot import ClaudeReview

    # Voir les erreurs en attente
    errors = ClaudeReview.get_pending()

    # Corriger une erreur
    ClaudeReview.fix(error_id)

    # Rejeter une erreur
    ClaudeReview.reject(error_id, reason="...")
"""

import structlog
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .models import FixProposal, FixStatus
from .storage import StorageBackend
from .auto_fixer import AutoFixer

logger = structlog.get_logger()


class ClaudeReview:
    """
    Interface pour que Claude review et corrige les erreurs.
    """

    _storage: Optional[StorageBackend] = None
    _get_session = None

    @classmethod
    def initialize(cls, storage: StorageBackend, get_session_func):
        """Initialise avec le storage et la session DB."""
        cls._storage = storage
        cls._get_session = get_session_func
        logger.info("claude_review_initialized")

    @classmethod
    def get_pending(cls) -> List[Dict[str, Any]]:
        """
        Retourne toutes les erreurs en attente de review.

        Returns:
            Liste de dicts avec les infos de chaque erreur
        """
        if not cls._storage:
            return []

        proposals = cls._storage.get_pending_proposals()
        results = []

        for p in proposals:
            results.append({
                "id": p.id,
                "type": p.error_type,
                "status": p.status.name,
                "confidence": f"{p.confidence*100:.0f}%",
                "file": p.file_path or "N/A",
                "error": p.error_message[:200] if p.error_message else "N/A",
                "fix": p.proposed_fix[:200] if p.proposed_fix else None,
                "created": p.created_at.strftime("%H:%M:%S") if p.created_at else "?"
            })

        return results

    @classmethod
    def fix_sql_error(cls, error_message: str) -> Tuple[bool, str]:
        """
        Corrige une erreur SQL directement.

        Args:
            error_message: Le message d'erreur SQL complet

        Returns:
            (success, message)
        """
        return AutoFixer.try_fix(error_message)

    @classmethod
    def fix_by_id(cls, proposal_id: str) -> Tuple[bool, str]:
        """
        Corrige une erreur par son ID.

        Args:
            proposal_id: ID de la proposition

        Returns:
            (success, message)
        """
        if not cls._storage:
            return False, "Storage non initialisé"

        proposal = cls._storage.get_proposal(proposal_id)
        if not proposal:
            return False, f"Proposition {proposal_id} non trouvée"

        # Essayer de corriger
        success, message = AutoFixer.try_fix(proposal.error_message or "")

        if success:
            cls._storage.update_proposal_status(proposal_id, FixStatus.APPLIED)
            return True, message
        else:
            return False, f"Impossible de corriger automatiquement: {message}"

    @classmethod
    def mark_resolved(cls, proposal_id: str) -> bool:
        """Marque une erreur comme résolue."""
        if not cls._storage:
            return False

        cls._storage.update_proposal_status(proposal_id, FixStatus.APPLIED)
        return True

    @classmethod
    def reject(cls, proposal_id: str, reason: str = "") -> bool:
        """Rejette une proposition de fix."""
        if not cls._storage:
            return False

        cls._storage.update_proposal_status(proposal_id, FixStatus.REJECTED)
        logger.info("claude_rejected_fix", id=proposal_id, reason=reason)
        return True

    @classmethod
    def process_all_sql_errors(cls) -> List[Tuple[str, bool, str]]:
        """
        Traite automatiquement toutes les erreurs SQL en attente.

        Returns:
            Liste de (proposal_id, success, message)
        """
        if not cls._storage:
            return []

        proposals = cls._storage.get_pending_proposals()
        results = []

        for p in proposals:
            if p.error_type == "SQLError" or "SQL" in (p.error_message or ""):
                success, message = cls.fix_by_id(p.id)
                results.append((p.id, success, message))

        return results

    @classmethod
    def add_column(cls, table: str, column: str, col_type: str = "VARCHAR(255)") -> Tuple[bool, str]:
        """
        Ajoute une colonne à une table.

        Args:
            table: Nom de la table
            column: Nom de la colonne
            col_type: Type PostgreSQL

        Returns:
            (success, message)
        """
        if not cls._get_session:
            return False, "Session non initialisée"

        try:
            with cls._get_session() as session:
                from sqlalchemy import text
                sql = f"""
                    ALTER TABLE azalplus.{table}
                    ADD COLUMN IF NOT EXISTS {column} {col_type}
                """
                session.execute(text(sql))
                session.commit()
                return True, f"Colonne '{column}' ajoutée à '{table}'"
        except Exception as e:
            return False, str(e)

    @classmethod
    def set_default(cls, table: str, column: str, default_value: str) -> Tuple[bool, str]:
        """
        Définit une valeur par défaut pour une colonne.

        Args:
            table: Nom de la table
            column: Nom de la colonne
            default_value: Valeur par défaut (SQL)

        Returns:
            (success, message)
        """
        if not cls._get_session:
            return False, "Session non initialisée"

        try:
            with cls._get_session() as session:
                from sqlalchemy import text
                sql = f"""
                    ALTER TABLE azalplus.{table}
                    ALTER COLUMN {column} SET DEFAULT {default_value}
                """
                session.execute(text(sql))
                session.commit()
                return True, f"Défaut '{default_value}' pour '{table}.{column}'"
        except Exception as e:
            return False, str(e)

    @classmethod
    def summary(cls) -> str:
        """
        Retourne un résumé des erreurs en attente.

        Returns:
            String formaté pour affichage
        """
        pending = cls.get_pending()

        if not pending:
            return "✅ Aucune erreur en attente"

        lines = [f"⚠️ {len(pending)} erreur(s) en attente:\n"]
        for i, err in enumerate(pending, 1):
            lines.append(f"[{i}] {err['type']} ({err['confidence']})")
            lines.append(f"    {err['error'][:80]}...")
            if err['fix']:
                lines.append(f"    Fix: {err['fix'][:60]}...")
            lines.append("")

        return "\n".join(lines)
