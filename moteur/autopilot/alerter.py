# =============================================================================
# AUTOPILOT - Alerter: Système d'interpellation Claude
# =============================================================================
"""
Alerter: Notifie Claude quand des erreurs nécessitent son attention.

Fonctionne en background et vérifie périodiquement les propositions en attente.
Quand une erreur importante est détectée, affiche un message clair dans les logs.
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Optional, List, Callable

from .models import FixProposal, FixStatus
from .storage import StorageBackend

logger = structlog.get_logger()


class AutoPilotAlerter:
    """
    Système d'alerte pour interpeller Claude.

    Vérifie les propositions en attente et génère des alertes
    pour celles qui nécessitent une attention immédiate.
    """

    # Seuils de confiance
    AUTO_FIX_THRESHOLD = 0.95      # Auto-correction sans validation
    ALERT_THRESHOLD = 0.40         # Alerter Claude

    # Intervalle de vérification (secondes)
    CHECK_INTERVAL = 30

    # Erreurs déjà alertées (évite le spam)
    _alerted_ids: set = set()

    # Task de background
    _task: Optional[asyncio.Task] = None
    _running: bool = False

    # Storage backend
    _storage: Optional[StorageBackend] = None

    @classmethod
    def initialize(cls, storage: StorageBackend):
        """Initialise l'alerter avec un backend de stockage."""
        cls._storage = storage
        cls._alerted_ids = set()
        logger.info("autopilot_alerter_initialized")

    @classmethod
    async def start(cls):
        """Démarre le monitoring en background."""
        if cls._running:
            return

        cls._running = True
        cls._task = asyncio.create_task(cls._monitor_loop())
        logger.info("autopilot_alerter_started", interval=cls.CHECK_INTERVAL)

    @classmethod
    async def stop(cls):
        """Arrête le monitoring."""
        cls._running = False
        if cls._task:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
        logger.info("autopilot_alerter_stopped")

    @classmethod
    async def _monitor_loop(cls):
        """Boucle de monitoring."""
        while cls._running:
            try:
                await cls._check_and_alert()
            except Exception as e:
                logger.error("autopilot_alerter_error", error=str(e))

            await asyncio.sleep(cls.CHECK_INTERVAL)

    @classmethod
    async def _check_and_alert(cls):
        """Vérifie les propositions et alerte si nécessaire."""
        if not cls._storage:
            return

        try:
            proposals = cls._storage.get_pending_proposals()
        except Exception as e:
            logger.debug("autopilot_alerter_storage_error", error=str(e))
            return

        # Filtrer les propositions non encore alertées
        new_proposals = [
            p for p in proposals
            if p.id not in cls._alerted_ids
        ]

        if not new_proposals:
            return

        # Grouper par priorité
        high_priority = []
        medium_priority = []

        for p in new_proposals:
            # Auto-fix si confiance très haute
            if p.confidence >= cls.AUTO_FIX_THRESHOLD and p.status == FixStatus.PENDING:
                cls._log_auto_fix(p)
                cls._alerted_ids.add(p.id)
                continue

            # Alerter si confiance moyenne ou status NEEDS_CLAUDE
            if p.status == FixStatus.NEEDS_CLAUDE:
                high_priority.append(p)
            elif p.confidence >= cls.ALERT_THRESHOLD:
                medium_priority.append(p)

        # Générer les alertes
        if high_priority:
            cls._alert_claude(high_priority, priority="HIGH")

        if medium_priority:
            cls._alert_claude(medium_priority, priority="MEDIUM")

        # Marquer comme alertées
        for p in high_priority + medium_priority:
            cls._alerted_ids.add(p.id)

    @classmethod
    def _alert_claude(cls, proposals: List[FixProposal], priority: str = "MEDIUM"):
        """
        Génère une alerte visible dans les logs.

        Format conçu pour être immédiatement visible et actionnable.
        """
        separator = "=" * 70

        print(f"\n{separator}")
        print(f"🚨 CLAUDE ACTION REQUIRED - {priority} PRIORITY")
        print(separator)
        print(f"📊 {len(proposals)} erreur(s) en attente de validation")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(separator)

        for i, p in enumerate(proposals, 1):
            print(f"\n[{i}] {p.error_type}")
            print(f"    Status: {p.status.name}")
            print(f"    Confiance: {p.confidence*100:.0f}%")
            if p.file_path:
                print(f"    Fichier: {p.file_path}")

            # Résumé de l'erreur
            error_preview = p.error_message[:150] if p.error_message else "N/A"
            print(f"    Erreur: {error_preview}...")

            # Fix proposé si disponible
            if p.proposed_fix and p.confidence >= 0.5:
                fix_preview = p.proposed_fix[:100].replace('\n', ' ')
                print(f"    Fix proposé: {fix_preview}...")

        print(f"\n{separator}")
        print("💡 Actions possibles:")
        print("   - Valider: autopilot.validate(id, approved=True)")
        print("   - Rejeter: autopilot.validate(id, approved=False, explanation='...')")
        print("   - Voir tout: /guardian/dashboard")
        print(f"{separator}\n")

        # Log structuré pour monitoring
        logger.warning(
            "claude_action_required",
            priority=priority,
            count=len(proposals),
            error_types=[p.error_type for p in proposals],
            proposal_ids=[p.id for p in proposals]
        )

    @classmethod
    def _log_auto_fix(cls, proposal: FixProposal):
        """Log quand un fix est auto-appliqué."""
        print(f"\n{'='*50}")
        print(f"✅ AUTO-FIX APPLIED (confidence: {proposal.confidence*100:.0f}%)")
        print(f"   Type: {proposal.error_type}")
        print(f"   File: {proposal.file_path or 'N/A'}")
        print(f"{'='*50}\n")

        logger.info(
            "autopilot_auto_fix",
            error_type=proposal.error_type,
            file_path=proposal.file_path,
            confidence=proposal.confidence
        )

    @classmethod
    def force_check(cls):
        """Force une vérification immédiate (synchrone)."""
        if not cls._storage:
            logger.warning("autopilot_alerter_not_initialized")
            return

        # Run synchronously
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create task for running loop
                asyncio.create_task(cls._check_and_alert())
            else:
                loop.run_until_complete(cls._check_and_alert())
        except RuntimeError:
            # No event loop
            asyncio.run(cls._check_and_alert())

    @classmethod
    def clear_alerts(cls):
        """Efface l'historique des alertes (pour re-alerter)."""
        cls._alerted_ids.clear()
        logger.info("autopilot_alerts_cleared")
