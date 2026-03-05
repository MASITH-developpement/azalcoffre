# =============================================================================
# AUTOPILOT - Backends de stockage
# =============================================================================
"""
Backends de stockage modulaires pour AutoPilot.
Permet d'utiliser PostgreSQL, SQLite, ou mémoire.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import structlog

from .models import FixProposal, Learning, FixStatus

logger = structlog.get_logger()


class StorageBackend(ABC):
    """Interface abstraite pour le stockage AutoPilot."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialise le backend (crée tables si nécessaire)."""
        pass

    @abstractmethod
    def save_proposal(self, proposal: FixProposal) -> None:
        """Sauvegarde une proposition de fix."""
        pass

    @abstractmethod
    def get_proposal(self, proposal_id: str) -> Optional[FixProposal]:
        """Récupère une proposition par ID."""
        pass

    @abstractmethod
    def get_pending_proposals(self) -> List[FixProposal]:
        """Récupère les propositions en attente."""
        pass

    @abstractmethod
    def update_proposal_status(self, proposal_id: str, status: FixStatus) -> None:
        """Met à jour le statut d'une proposition."""
        pass

    @abstractmethod
    def save_learning(self, learning: Learning) -> None:
        """Sauvegarde un apprentissage."""
        pass

    @abstractmethod
    def get_validated_patterns(self) -> Dict[str, str]:
        """Récupère les patterns validés (pattern -> fix_template)."""
        pass

    @abstractmethod
    def get_rejection_explanations(self, error_pattern: str) -> List[str]:
        """Récupère les explications de rejet pour un pattern."""
        pass

    @abstractmethod
    def get_all_learnings(self, limit: int = 100) -> List[Learning]:
        """Récupère tous les apprentissages."""
        pass

    @abstractmethod
    def increment_times_applied(self, learning_id: str) -> None:
        """Incrémente le compteur d'application d'un learning."""
        pass


class MemoryStorage(StorageBackend):
    """
    Stockage en mémoire (pour tests ou usage temporaire).
    Les données sont perdues au redémarrage.
    """

    def __init__(self):
        self._proposals: Dict[str, FixProposal] = {}
        self._learnings: Dict[str, Learning] = {}

    def initialize(self) -> None:
        logger.info("autopilot_memory_storage_initialized")

    def save_proposal(self, proposal: FixProposal) -> None:
        self._proposals[proposal.id] = proposal

    def get_proposal(self, proposal_id: str) -> Optional[FixProposal]:
        return self._proposals.get(proposal_id)

    def get_pending_proposals(self) -> List[FixProposal]:
        return [p for p in self._proposals.values() if p.status == FixStatus.PENDING]

    def update_proposal_status(self, proposal_id: str, status: FixStatus) -> None:
        if proposal_id in self._proposals:
            self._proposals[proposal_id].status = status

    def save_learning(self, learning: Learning) -> None:
        self._learnings[learning.id] = learning

    def get_validated_patterns(self) -> Dict[str, str]:
        return {
            l.error_pattern: l.fix_template
            for l in self._learnings.values()
            if l.status == "validated" and l.fix_template
        }

    def get_rejection_explanations(self, error_pattern: str) -> List[str]:
        return [
            l.explanation
            for l in self._learnings.values()
            if l.error_pattern == error_pattern and l.status == "rejected"
        ]

    def get_all_learnings(self, limit: int = 100) -> List[Learning]:
        sorted_learnings = sorted(
            self._learnings.values(),
            key=lambda x: x.created_at,
            reverse=True
        )
        return sorted_learnings[:limit]

    def increment_times_applied(self, learning_id: str) -> None:
        if learning_id in self._learnings:
            self._learnings[learning_id].times_applied += 1


class PostgresStorage(StorageBackend):
    """
    Stockage PostgreSQL pour production.
    Utilise la connexion existante d'AZALPLUS.
    """

    def __init__(self, get_session_func=None):
        """
        Args:
            get_session_func: Fonction qui retourne une session DB
                              (ex: Database.get_session)
        """
        self._get_session = get_session_func

    def set_session_factory(self, get_session_func):
        """Configure la factory de session (lazy initialization)."""
        self._get_session = get_session_func

    def initialize(self) -> None:
        """Crée les tables si elles n'existent pas."""
        if not self._get_session:
            logger.warning("autopilot_postgres_no_session_factory")
            return

        try:
            with self._get_session() as session:
                from sqlalchemy import text

                # Créer la table guardian_learnings si elle n'existe pas
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS azalplus.guardian_learnings (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        error_pattern VARCHAR(100) NOT NULL,
                        error_message TEXT,
                        fix_template TEXT,
                        status VARCHAR(20) NOT NULL,
                        explanation TEXT,
                        file_path TEXT,
                        confidence FLOAT DEFAULT 0.5,
                        times_applied INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))

                # Créer la table guardian_fix_proposals si elle n'existe pas
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS azalplus.guardian_fix_proposals (
                        id VARCHAR(20) PRIMARY KEY,
                        error_type VARCHAR(100) NOT NULL,
                        error_message TEXT,
                        category VARCHAR(50),
                        file_path TEXT,
                        line_number INTEGER,
                        original_code TEXT,
                        proposed_fix TEXT,
                        confidence FLOAT DEFAULT 0.5,
                        status VARCHAR(20) DEFAULT 'pending',
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))

                session.commit()
                logger.info("autopilot_postgres_initialized")

        except Exception as e:
            logger.error("autopilot_postgres_init_failed", error=str(e))

    def save_proposal(self, proposal: FixProposal) -> None:
        if not self._get_session:
            return

        try:
            with self._get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        INSERT INTO azalplus.guardian_fix_proposals
                        (id, error_type, error_message, category, file_path, line_number,
                         original_code, proposed_fix, confidence, status, metadata)
                        VALUES (:id, :error_type, :error_message, :category, :file_path,
                                :line_number, :original_code, :proposed_fix, :confidence,
                                :status, :metadata)
                        ON CONFLICT (id) DO UPDATE SET
                            status = :status,
                            proposed_fix = :proposed_fix
                    """),
                    {
                        "id": proposal.id,
                        "error_type": proposal.error_type,
                        "error_message": proposal.error_message[:2000],
                        "category": proposal.category.value,
                        "file_path": proposal.file_path,
                        "line_number": proposal.line_number,
                        "original_code": proposal.original_code,
                        "proposed_fix": proposal.proposed_fix,
                        "confidence": proposal.confidence,
                        "status": proposal.status.value,
                        "metadata": json.dumps(proposal.metadata)
                    }
                )
                session.commit()
        except Exception as e:
            logger.error("autopilot_save_proposal_failed", error=str(e))

    def get_proposal(self, proposal_id: str) -> Optional[FixProposal]:
        if not self._get_session:
            return None

        try:
            with self._get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT * FROM azalplus.guardian_fix_proposals
                        WHERE id = :id
                    """),
                    {"id": proposal_id}
                ).fetchone()

                if result:
                    r = dict(result._mapping)
                    return FixProposal(
                        id=r["id"],
                        error_type=r["error_type"],
                        error_message=r["error_message"],
                        file_path=r["file_path"],
                        line_number=r["line_number"],
                        original_code=r["original_code"],
                        proposed_fix=r["proposed_fix"],
                        confidence=r["confidence"],
                        status=FixStatus(r["status"]),
                        created_at=r["created_at"]
                    )
        except Exception as e:
            logger.error("autopilot_get_proposal_failed", error=str(e))

        return None

    def get_pending_proposals(self) -> List[FixProposal]:
        if not self._get_session:
            return []

        proposals = []
        try:
            with self._get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT * FROM azalplus.guardian_fix_proposals
                        WHERE status IN ('pending', 'needs_claude')
                        ORDER BY
                            CASE WHEN status = 'needs_claude' THEN 0 ELSE 1 END,
                            created_at DESC
                    """)
                )
                for row in result:
                    r = dict(row._mapping)
                    metadata = r.get("metadata", {})
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata) if metadata else {}
                    proposals.append(FixProposal(
                        id=r["id"],
                        error_type=r["error_type"],
                        error_message=r["error_message"],
                        file_path=r["file_path"],
                        line_number=r["line_number"],
                        original_code=r["original_code"],
                        proposed_fix=r["proposed_fix"],
                        confidence=r["confidence"],
                        status=FixStatus(r["status"]),
                        created_at=r["created_at"],
                        metadata=metadata
                    ))
        except Exception as e:
            logger.error("autopilot_get_pending_failed", error=str(e))

        return proposals

    def update_proposal_status(self, proposal_id: str, status: FixStatus) -> None:
        if not self._get_session:
            return

        try:
            with self._get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        UPDATE azalplus.guardian_fix_proposals
                        SET status = :status
                        WHERE id = :id
                    """),
                    {"id": proposal_id, "status": status.value}
                )
                session.commit()
        except Exception as e:
            logger.error("autopilot_update_status_failed", error=str(e))

    def save_learning(self, learning: Learning) -> None:
        if not self._get_session:
            return

        try:
            with self._get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        INSERT INTO azalplus.guardian_learnings
                        (error_pattern, error_message, fix_template, status,
                         explanation, file_path, confidence, times_applied)
                        VALUES (:pattern, :message, :fix, :status,
                                :explanation, :file_path, :confidence, :times_applied)
                    """),
                    {
                        "pattern": learning.error_pattern,
                        "message": learning.error_message[:2000],
                        "fix": learning.fix_template,
                        "status": learning.status,
                        "explanation": learning.explanation,
                        "file_path": learning.file_path,
                        "confidence": learning.confidence,
                        "times_applied": learning.times_applied
                    }
                )
                session.commit()
        except Exception as e:
            logger.error("autopilot_save_learning_failed", error=str(e))

    def get_validated_patterns(self) -> Dict[str, str]:
        if not self._get_session:
            return {}

        patterns = {}
        try:
            with self._get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT error_pattern, fix_template
                        FROM azalplus.guardian_learnings
                        WHERE status = 'validated' AND fix_template IS NOT NULL
                    """)
                )
                for row in result:
                    r = dict(row._mapping)
                    patterns[r["error_pattern"]] = r["fix_template"]
        except Exception as e:
            logger.error("autopilot_get_patterns_failed", error=str(e))

        return patterns

    def get_rejection_explanations(self, error_pattern: str) -> List[str]:
        if not self._get_session:
            return []

        explanations = []
        try:
            with self._get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT explanation
                        FROM azalplus.guardian_learnings
                        WHERE error_pattern = :pattern AND status = 'rejected'
                    """),
                    {"pattern": error_pattern}
                )
                explanations = [dict(row._mapping)["explanation"] for row in result]
        except Exception as e:
            logger.error("autopilot_get_rejections_failed", error=str(e))

        return explanations

    def get_all_learnings(self, limit: int = 100) -> List[Learning]:
        if not self._get_session:
            return []

        learnings = []
        try:
            with self._get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT * FROM azalplus.guardian_learnings
                        ORDER BY created_at DESC
                        LIMIT :limit
                    """),
                    {"limit": limit}
                )
                for row in result:
                    r = dict(row._mapping)
                    learnings.append(Learning(
                        id=str(r["id"]),
                        error_pattern=r["error_pattern"],
                        error_message=r["error_message"] or "",
                        fix_template=r["fix_template"],
                        status=r["status"],
                        explanation=r["explanation"] or "",
                        file_path=r["file_path"],
                        confidence=r["confidence"] or 0.5,
                        times_applied=r["times_applied"] or 0,
                        created_at=r["created_at"],
                        updated_at=r["updated_at"] or r["created_at"]
                    ))
        except Exception as e:
            logger.error("autopilot_get_learnings_failed", error=str(e))

        return learnings

    def increment_times_applied(self, learning_id: str) -> None:
        if not self._get_session:
            return

        try:
            with self._get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        UPDATE azalplus.guardian_learnings
                        SET times_applied = times_applied + 1,
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {"id": learning_id}
                )
                session.commit()
        except Exception as e:
            logger.error("autopilot_increment_failed", error=str(e))
