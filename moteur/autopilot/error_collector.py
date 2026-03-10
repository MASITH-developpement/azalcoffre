# =============================================================================
# AUTOPILOT - Error Collector: Point central de collecte des erreurs
# =============================================================================
"""
Collecteur central d'erreurs.

Toutes les erreurs (frontend, mobile, backend) arrivent ici.
Guardian surveille ce fichier et AutoFixer corrige automatiquement.

Flux:
  Frontend/Mobile → HTTP → ErrorCollector → errors.log → Guardian → AutoFixer
"""

import json
import structlog
from datetime import datetime
from pathlib import Path
from typing import Optional
from threading import Thread, Event
import time

logger = structlog.get_logger()

# Fichier central des erreurs
ERROR_LOG_PATH = Path("/home/ubuntu/azalplus/logs/errors.log")
ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


class ErrorCollector:
    """
    Collecteur central d'erreurs.

    Reçoit les erreurs de toutes les sources et les écrit dans un fichier
    commun que Guardian surveille.
    """

    _instance = None
    _watcher_thread: Optional[Thread] = None
    _stop_event = Event()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def collect(cls, error_data: dict, source: str = "unknown") -> None:
        """
        Collecte une erreur, l'écrit dans le fichier central, et déclenche AutoFixer.

        Args:
            error_data: Dictionnaire contenant les détails de l'erreur
            source: Source de l'erreur (frontend, mobile, backend)
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            **error_data
        }

        # Écrire dans le fichier (append)
        with open(ERROR_LOG_PATH, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.debug("error_collected", source=source, type=error_data.get("error_type"))

        # Déclencher AutoFixer IMMÉDIATEMENT (pas via le watcher)
        try:
            handle_error_for_autofix(entry)
        except Exception as e:
            logger.error("autofix_trigger_failed", error=str(e))

    @classmethod
    def start_watcher(cls, callback) -> None:
        """
        Démarre le watcher qui surveille le fichier d'erreurs.

        Args:
            callback: Fonction à appeler pour chaque nouvelle erreur (reçoit le dict)
        """
        if cls._watcher_thread and cls._watcher_thread.is_alive():
            return

        cls._stop_event.clear()
        cls._watcher_thread = Thread(target=cls._watch_loop, args=(callback,), daemon=True)
        cls._watcher_thread.start()
        logger.info("error_collector_watcher_started")

    @classmethod
    def stop_watcher(cls) -> None:
        """Arrête le watcher."""
        cls._stop_event.set()
        if cls._watcher_thread:
            cls._watcher_thread.join(timeout=2)
        logger.info("error_collector_watcher_stopped")

    @classmethod
    def _watch_loop(cls, callback) -> None:
        """Boucle de surveillance du fichier d'erreurs."""
        # Créer le fichier s'il n'existe pas
        if not ERROR_LOG_PATH.exists():
            ERROR_LOG_PATH.touch()

        # Se positionner à la fin du fichier
        with open(ERROR_LOG_PATH, "r") as f:
            f.seek(0, 2)  # Aller à la fin

            while not cls._stop_event.is_set():
                line = f.readline()

                if line:
                    try:
                        error_data = json.loads(line.strip())
                        callback(error_data)
                    except json.JSONDecodeError:
                        pass
                else:
                    time.sleep(0.5)  # Attendre 500ms avant de relire

    @classmethod
    def get_recent_errors(cls, count: int = 50) -> list:
        """
        Récupère les N dernières erreurs.

        Args:
            count: Nombre d'erreurs à récupérer

        Returns:
            Liste des erreurs (les plus récentes en premier)
        """
        if not ERROR_LOG_PATH.exists():
            return []

        errors = []
        with open(ERROR_LOG_PATH, "r") as f:
            for line in f:
                try:
                    errors.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass

        return errors[-count:][::-1]  # Les plus récentes en premier

    @classmethod
    def clear_old_errors(cls, max_age_hours: int = 24) -> int:
        """
        Supprime les erreurs plus vieilles que max_age_hours.

        Returns:
            Nombre d'erreurs supprimées
        """
        if not ERROR_LOG_PATH.exists():
            return 0

        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        kept = []
        removed = 0

        with open(ERROR_LOG_PATH, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entry_time = datetime.fromisoformat(entry["timestamp"]).timestamp()
                    if entry_time >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    kept.append(line)  # Garder les lignes non parsables

        with open(ERROR_LOG_PATH, "w") as f:
            f.writelines(kept)

        if removed > 0:
            logger.info("old_errors_cleared", count=removed)

        return removed


def handle_error_for_autofix(error_data: dict) -> None:
    """
    Callback appelé pour chaque nouvelle erreur.
    Déclenche AutoFixer si possible.
    """
    from .auto_fixer import AutoFixer

    # Construire le log d'erreur pour AutoFixer
    error_log = f"""
{error_data.get('source', 'UNKNOWN').upper()} ERROR [{error_data.get('error_type', 'unknown')}]
URL: {error_data.get('url', 'N/A')}
Message: {error_data.get('message', 'N/A')}
Source: {error_data.get('source_file', 'unknown')}:{error_data.get('line', '?')}:{error_data.get('column', '?')}
Stack: {error_data.get('stack', 'N/A')}
Timestamp: {error_data.get('timestamp', 'N/A')}
"""

    # Tenter la correction automatique
    success, message = AutoFixer.try_fix(error_log)

    if success:
        logger.info("autofix_applied",
                   error_type=error_data.get('error_type'),
                   fix=message)
    else:
        logger.debug("autofix_not_applicable",
                    error_type=error_data.get('error_type'),
                    reason=message)


def start_error_collector() -> None:
    """Démarre le collecteur d'erreurs avec AutoFixer."""
    ErrorCollector.start_watcher(handle_error_for_autofix)
    logger.info("error_collector_started_with_autofix")


def stop_error_collector() -> None:
    """Arrête le collecteur d'erreurs."""
    ErrorCollector.stop_watcher()
