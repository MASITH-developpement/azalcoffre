# =============================================================================
# AUTOPILOT - Cœur du système
# =============================================================================
"""
Classe principale AutoPilot qui orchestre l'analyse, la validation et
l'application des fixes.

Usage:
    autopilot = AutoPilot(storage=PostgresStorage(get_session))
    autopilot.initialize()

    # Analyser une erreur
    proposal = autopilot.analyze(error_log)

    # Valider (Claude approuve)
    result = autopilot.validate(proposal.id, approved=True)

    # Ou rejeter avec explication (Guardian apprend)
    result = autopilot.validate(
        proposal.id,
        approved=False,
        explanation="Le problème n'est pas l'import mais..."
    )
"""

from typing import Optional, List, Dict, Callable, Any
from datetime import datetime
import structlog
import threading
import queue
import re

from .models import FixProposal, Learning, FixStatus, ValidationResult
from .storage import StorageBackend, MemoryStorage
from .analyzers import ErrorAnalyzer, CompositeAnalyzer
from .applicators import FixApplicator, CompositeApplicator, ApplyResult

logger = structlog.get_logger()


class AutoPilot:
    """
    Système d'auto-correction autonome avec apprentissage.

    Invisible pour tous sauf le créateur.
    Apprend de ses erreurs grâce aux explications.
    """

    def __init__(
        self,
        storage: StorageBackend = None,
        analyzer: ErrorAnalyzer = None,
        applicator: FixApplicator = None,
        auto_apply_threshold: float = 0.95,  # Confiance minimale pour auto-apply
        protected_paths: List[str] = None
    ):
        """
        Initialise AutoPilot.

        Args:
            storage: Backend de stockage (défaut: MemoryStorage)
            analyzer: Analyseur d'erreurs (défaut: CompositeAnalyzer)
            applicator: Applicateur de fixes (défaut: CompositeApplicator)
            auto_apply_threshold: Seuil de confiance pour application auto
            protected_paths: Chemins supplémentaires à protéger
        """
        self._storage = storage or MemoryStorage()
        self._analyzer = analyzer or CompositeAnalyzer()
        self._applicator = applicator or CompositeApplicator()
        self._auto_apply_threshold = auto_apply_threshold
        self._protected_paths = protected_paths or []

        # Cache des patterns validés
        self._validated_patterns: Dict[str, str] = {}
        # Cache des explications de rejet
        self._rejection_lessons: Dict[str, List[str]] = {}

        # Queue pour traitement asynchrone
        self._error_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        # Callbacks
        self._on_proposal_created: Optional[Callable[[FixProposal], None]] = None
        self._on_fix_applied: Optional[Callable[[FixProposal, ApplyResult], None]] = None

    def initialize(self) -> None:
        """Initialise AutoPilot et charge les apprentissages."""
        self._storage.initialize()
        self._load_learnings()
        logger.info("autopilot_initialized",
                   patterns=len(self._validated_patterns),
                   lessons=len(self._rejection_lessons))

    def _load_learnings(self) -> None:
        """Charge les apprentissages depuis le stockage."""
        # Patterns validés
        self._validated_patterns = self._storage.get_validated_patterns()

        # Explications de rejet (pour éviter de refaire les mêmes erreurs)
        learnings = self._storage.get_all_learnings()
        for learning in learnings:
            if learning.status == "rejected":
                key = learning.error_pattern
                if key not in self._rejection_lessons:
                    self._rejection_lessons[key] = []
                self._rejection_lessons[key].append(learning.explanation)

    def set_callbacks(
        self,
        on_proposal: Callable[[FixProposal], None] = None,
        on_applied: Callable[[FixProposal, ApplyResult], None] = None
    ) -> None:
        """Configure les callbacks."""
        self._on_proposal_created = on_proposal
        self._on_fix_applied = on_applied

    # =========================================================================
    # Analyse
    # =========================================================================

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """
        Analyse une erreur et génère une proposition de fix.

        Args:
            error_log: Le message d'erreur complet

        Returns:
            FixProposal ou None si pas de fix possible
        """
        if not error_log:
            return None

        # Utiliser l'analyseur pour générer une proposition
        proposal = self._analyzer.analyze(error_log)

        if proposal:
            # Vérifier si on a un pattern validé
            pattern_key = f"{proposal.error_type}:{proposal.error_message[:100]}"

            if pattern_key in self._validated_patterns:
                # Utiliser le fix validé avec haute confiance
                proposal.proposed_fix = self._validated_patterns[pattern_key]
                proposal.confidence = 0.95
                proposal.status = FixStatus.AUTO_VALIDATED

            # Réduire la confiance si on a eu des rejets similaires
            if proposal.error_type in self._rejection_lessons:
                rejections = len(self._rejection_lessons[proposal.error_type])
                proposal.confidence *= (0.8 ** rejections)
                # Ajouter les leçons au metadata
                proposal.metadata["past_rejections"] = self._rejection_lessons[proposal.error_type][-3:]

            # Sauvegarder la proposition
            self._storage.save_proposal(proposal)

            # Callback
            if self._on_proposal_created:
                self._on_proposal_created(proposal)

            logger.debug("autopilot_proposal_created",
                        id=proposal.id,
                        type=proposal.error_type,
                        confidence=proposal.confidence)

        return proposal

    # =========================================================================
    # Validation
    # =========================================================================

    def validate(
        self,
        proposal_id: str,
        approved: bool,
        explanation: str = ""
    ) -> ValidationResult:
        """
        Valide ou rejette une proposition de fix.

        Args:
            proposal_id: ID de la proposition
            approved: True si validé, False si rejeté
            explanation: Explication (obligatoire si rejeté)

        Returns:
            ValidationResult
        """
        proposal = self._storage.get_proposal(proposal_id)
        if not proposal:
            return ValidationResult(
                success=False,
                status=FixStatus.FAILED,
                message="Proposition non trouvée"
            )

        if approved:
            return self._apply_validated_fix(proposal, explanation)
        else:
            return self._learn_from_rejection(proposal, explanation)

    def _apply_validated_fix(
        self,
        proposal: FixProposal,
        explanation: str
    ) -> ValidationResult:
        """Applique un fix validé."""

        # Vérifier si on peut appliquer
        if not self._applicator.can_apply(proposal):
            # Sauvegarder quand même le pattern pour référence future
            self._save_as_validated(proposal, explanation)
            return ValidationResult(
                success=True,
                status=FixStatus.APPROVED,
                message="Fix validé mais non applicable automatiquement",
                fix=proposal
            )

        # Appliquer le fix
        result = self._applicator.apply(proposal)

        if result.success:
            proposal.status = FixStatus.APPLIED
            self._storage.update_proposal_status(proposal.id, FixStatus.APPLIED)

            # Sauvegarder le pattern validé
            learning = self._save_as_validated(proposal, explanation)

            # Callback
            if self._on_fix_applied:
                self._on_fix_applied(proposal, result)

            logger.info("autopilot_fix_applied",
                       id=proposal.id,
                       type=proposal.error_type,
                       changes=result.changes)

            return ValidationResult(
                success=True,
                status=FixStatus.APPLIED,
                message=result.message,
                fix=proposal,
                learning=learning,
                applied_changes=result.changes
            )
        else:
            proposal.status = FixStatus.FAILED
            self._storage.update_proposal_status(proposal.id, FixStatus.FAILED)

            return ValidationResult(
                success=False,
                status=FixStatus.FAILED,
                message=result.message,
                fix=proposal
            )

    def _learn_from_rejection(
        self,
        proposal: FixProposal,
        explanation: str
    ) -> ValidationResult:
        """Apprend d'un rejet."""

        if not explanation:
            return ValidationResult(
                success=False,
                status=FixStatus.PENDING,
                message="Explication obligatoire pour un rejet"
            )

        # Mettre à jour le statut
        proposal.status = FixStatus.REJECTED
        self._storage.update_proposal_status(proposal.id, FixStatus.REJECTED)

        # Créer un learning de type rejected
        learning = Learning(
            id=Learning.generate_id(proposal.error_type, proposal.proposed_fix or ""),
            error_pattern=proposal.error_type,
            error_message=proposal.error_message,
            fix_template=proposal.proposed_fix,
            status="rejected",
            explanation=explanation,
            file_path=proposal.file_path,
            confidence=proposal.confidence
        )

        self._storage.save_learning(learning)

        # Ajouter au cache local
        if proposal.error_type not in self._rejection_lessons:
            self._rejection_lessons[proposal.error_type] = []
        self._rejection_lessons[proposal.error_type].append(explanation)

        logger.info("autopilot_learned_rejection",
                   id=proposal.id,
                   type=proposal.error_type,
                   explanation=explanation[:100])

        return ValidationResult(
            success=True,
            status=FixStatus.REJECTED,
            message="Rejet enregistré, Guardian a appris",
            fix=proposal,
            learning=learning
        )

    def _save_as_validated(self, proposal: FixProposal, explanation: str) -> Learning:
        """Sauvegarde un pattern validé."""
        pattern_key = f"{proposal.error_type}:{proposal.error_message[:100]}"

        learning = Learning(
            id=Learning.generate_id(proposal.error_type, proposal.proposed_fix or ""),
            error_pattern=pattern_key,
            error_message=proposal.error_message,
            fix_template=proposal.proposed_fix,
            status="validated",
            explanation=explanation,
            file_path=proposal.file_path,
            confidence=proposal.confidence
        )

        self._storage.save_learning(learning)

        # Ajouter au cache local
        if proposal.proposed_fix:
            self._validated_patterns[pattern_key] = proposal.proposed_fix

        return learning

    # =========================================================================
    # Accès aux données
    # =========================================================================

    def get_pending_proposals(self) -> List[FixProposal]:
        """Retourne les propositions en attente."""
        return self._storage.get_pending_proposals()

    def get_learnings(self, limit: int = 100) -> List[Learning]:
        """Retourne les apprentissages."""
        return self._storage.get_all_learnings(limit)

    def get_stats(self) -> dict:
        """Retourne les statistiques."""
        learnings = self._storage.get_all_learnings(1000)

        validated = sum(1 for l in learnings if l.status == "validated")
        rejected = sum(1 for l in learnings if l.status == "rejected")
        total_applied = sum(l.times_applied for l in learnings if l.status == "validated")

        return {
            "validated_patterns": validated,
            "rejection_lessons": rejected,
            "total_fixes_applied": total_applied,
            "pending_proposals": len(self.get_pending_proposals()),
            "auto_apply_threshold": self._auto_apply_threshold
        }

    # =========================================================================
    # Mode autonome (background processing)
    # =========================================================================

    def start_watching(self) -> None:
        """Démarre le worker de traitement en arrière-plan."""
        if self._running:
            return

        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("autopilot_watcher_started")

    def stop_watching(self) -> None:
        """Arrête le worker."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("autopilot_watcher_stopped")

    def submit_error(self, error_log: str) -> None:
        """Soumet une erreur pour traitement asynchrone."""
        self._error_queue.put(error_log)

    def _worker_loop(self) -> None:
        """Boucle de traitement des erreurs."""
        while self._running:
            try:
                error_log = self._error_queue.get(timeout=1)
                proposal = self.analyze(error_log)

                if proposal and proposal.confidence >= self._auto_apply_threshold:
                    # Auto-apply si confiance suffisante
                    self.validate(proposal.id, approved=True,
                                 explanation="Auto-validated (high confidence)")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error("autopilot_worker_error", error=str(e))
