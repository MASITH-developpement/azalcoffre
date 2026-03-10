# =============================================================================
# AZALPLUS - Escalation Handler (Daemon autonome)
# =============================================================================
"""
Daemon qui surveille les escalades Guardian et applique les corrections
automatiquement SANS intervention humaine.

Lance avec: python -m moteur.autopilot.escalation_handler
"""

import time
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
import structlog

logger = structlog.get_logger()

ALERTS_LOG = Path("/home/ubuntu/azalplus/logs/guardian_alerts.log")
FIXES_LOG = Path("/home/ubuntu/azalplus/logs/guardian_fixes.log")
LEARNING_LOG = Path("/home/ubuntu/azalplus/logs/guardian_learning.log")
PROCESSED_FILE = Path("/home/ubuntu/azalplus/logs/.escalations_processed")

# Patterns de fix connus (apprentissage codé)
KNOWN_FIXES = {
    # Pattern: (fix_function, description)
    r"422.*bulk": ("fix_bulk_422", "Erreur 422 sur endpoint bulk"),
    r"404.*/api/v1/": ("fix_api_v1_route", "Route API v1 manquante"),
    r"500.*database": ("fix_database_error", "Erreur base de données"),
    r"ImportError": ("fix_import_error", "Import Python manquant"),
    r"ModuleNotFoundError": ("fix_module_not_found", "Module Python manquant"),
}


class EscalationHandler:
    """Gestionnaire autonome des escalades Guardian."""

    def __init__(self):
        self.last_position = self._load_position()
        self._ensure_logs_exist()

    def _ensure_logs_exist(self):
        """Crée les fichiers de log si nécessaire."""
        for log_file in [ALERTS_LOG, FIXES_LOG, LEARNING_LOG]:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            if not log_file.exists():
                log_file.touch()

    def _load_position(self) -> int:
        """Charge la dernière position lue dans le fichier d'alertes."""
        try:
            if PROCESSED_FILE.exists():
                return int(PROCESSED_FILE.read_text().strip())
        except:
            pass
        return 0

    def _save_position(self, position: int):
        """Sauvegarde la position actuelle."""
        PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_FILE.write_text(str(position))

    def _log_fix(self, fix_type: str, message: str):
        """Log une correction appliquée."""
        with open(FIXES_LOG, "a") as f:
            f.write(f"{datetime.now().isoformat()} | FIX | {fix_type} | {message}\n")

    def _log_learning(self, category: str, lesson: str):
        """Log un apprentissage."""
        with open(LEARNING_LOG, "a") as f:
            f.write(f"{datetime.now().isoformat()} | LEARN | {category} | {lesson}\n")

    def check_new_escalations(self) -> list:
        """Vérifie s'il y a de nouvelles escalades."""
        if not ALERTS_LOG.exists():
            return []

        with open(ALERTS_LOG, "r") as f:
            content = f.read()

        # Lire depuis la dernière position
        new_content = content[self.last_position:]
        self.last_position = len(content)
        self._save_position(self.last_position)

        if not new_content.strip():
            return []

        # Parser les nouvelles escalades
        escalations = []
        for line in new_content.strip().split("\n"):
            if "ESCALATION" in line:
                escalations.append(line)

        return escalations

    def handle_escalation(self, escalation: str) -> Tuple[bool, str]:
        """Tente de corriger une escalade automatiquement."""
        logger.info("handling_escalation", escalation=escalation[:100])

        # Chercher un pattern connu
        for pattern, (fix_func, description) in KNOWN_FIXES.items():
            if re.search(pattern, escalation, re.IGNORECASE):
                # Appliquer le fix
                fix_method = getattr(self, fix_func, None)
                if fix_method:
                    try:
                        success, message = fix_method(escalation)
                        if success:
                            self._log_fix(fix_func, message)
                            logger.info("escalation_fixed", fix=fix_func, message=message)
                            return True, message
                    except Exception as e:
                        logger.error("fix_failed", fix=fix_func, error=str(e))

        # Pas de fix connu - log pour apprentissage futur
        logger.warning("no_fix_available", escalation=escalation[:100])
        return False, "Pas de fix automatique disponible"

    # =========================================================================
    # Méthodes de correction
    # =========================================================================

    def fix_bulk_422(self, escalation: str) -> Tuple[bool, str]:
        """Corrige les erreurs 422 sur les endpoints bulk."""
        # Vérifier si les modèles Pydantic sont utilisés
        api_py = Path("/home/ubuntu/azalplus/moteur/api.py")
        api_v1_py = Path("/home/ubuntu/azalplus/moteur/api_v1.py")

        fixed = False

        # Vérifier api.py
        if api_py.exists():
            content = api_py.read_text()
            if "class BulkDeleteRequest" in content and "body: BulkDeleteRequest" in content:
                pass  # Déjà corrigé
            elif "class BulkDeleteRequest" not in content:
                # Besoin d'ajouter le modèle - trop complexe pour auto-fix
                self._log_learning("bulk_422", "api.py nécessite BulkDeleteRequest model")

        # Vérifier api_v1.py
        if api_v1_py.exists():
            content = api_v1_py.read_text()
            if "class BulkDeleteRequestV1" in content and "body: BulkDeleteRequestV1" in content:
                fixed = True

        if fixed:
            # Redémarrer le serveur pour appliquer
            self._reload_server()
            return True, "Modèles Pydantic bulk vérifiés, serveur rechargé"

        return False, "Fix bulk nécessite modification manuelle"

    def fix_api_v1_route(self, escalation: str) -> Tuple[bool, str]:
        """Corrige les routes API v1 manquantes."""
        # Extraire le module concerné
        match = re.search(r'/api/v1/([a-z_]+)', escalation, re.IGNORECASE)
        if not match:
            return False, "Module non identifié"

        module_name = match.group(1)

        # Vérifier si le module YAML existe
        yaml_path = Path(f"/home/ubuntu/azalplus/modules/{module_name}.yml")
        if not yaml_path.exists():
            # Essayer au singulier/pluriel
            if module_name.endswith('s'):
                yaml_path = Path(f"/home/ubuntu/azalplus/modules/{module_name[:-1]}.yml")
            else:
                yaml_path = Path(f"/home/ubuntu/azalplus/modules/{module_name}s.yml")

        if yaml_path.exists():
            self._reload_server()
            self._log_learning("route_v1", f"Module {module_name} existe, rechargement serveur")
            return True, f"Module {module_name} trouvé, serveur rechargé"

        return False, f"Module {module_name} non trouvé"

    def fix_database_error(self, escalation: str) -> Tuple[bool, str]:
        """Corrige les erreurs de base de données."""
        # Reset connection pool
        try:
            from moteur.db import Database
            Database.reset_pool()
            return True, "Pool de connexions DB réinitialisé"
        except:
            pass
        return False, "Impossible de réinitialiser le pool DB"

    def fix_import_error(self, escalation: str) -> Tuple[bool, str]:
        """Tente de corriger les erreurs d'import."""
        # Extraire le module manquant
        match = re.search(r"No module named '([^']+)'", escalation)
        if match:
            module = match.group(1)
            self._log_learning("import", f"Module manquant: {module}")
            # On ne peut pas installer automatiquement pour des raisons de sécurité
            return False, f"Module {module} manquant - installation manuelle requise"
        return False, "Module manquant non identifié"

    def fix_module_not_found(self, escalation: str) -> Tuple[bool, str]:
        """Alias pour fix_import_error."""
        return self.fix_import_error(escalation)

    def _reload_server(self):
        """Envoie un signal de rechargement au serveur uvicorn."""
        try:
            # Touch un fichier pour déclencher le reload de watchfiles
            Path("/home/ubuntu/azalplus/moteur/__reload_trigger__").touch()
            time.sleep(1)
            Path("/home/ubuntu/azalplus/moteur/__reload_trigger__").unlink(missing_ok=True)
            logger.info("server_reload_triggered")
        except Exception as e:
            logger.error("server_reload_failed", error=str(e))

    def run(self, interval: int = 5):
        """Boucle principale du daemon."""
        logger.info("escalation_handler_started", interval=interval)
        print(f"[EscalationHandler] Démarré - vérifie toutes les {interval}s")

        while True:
            try:
                escalations = self.check_new_escalations()

                for esc in escalations:
                    print(f"[EscalationHandler] Nouvelle escalade détectée")
                    success, message = self.handle_escalation(esc)
                    if success:
                        print(f"[EscalationHandler] ✅ Corrigé: {message}")
                    else:
                        print(f"[EscalationHandler] ⚠️ Non corrigé: {message}")

                time.sleep(interval)

            except KeyboardInterrupt:
                print("\n[EscalationHandler] Arrêt...")
                break
            except Exception as e:
                logger.error("escalation_handler_error", error=str(e))
                time.sleep(interval)


def main():
    """Point d'entrée."""
    handler = EscalationHandler()
    handler.run(interval=5)


if __name__ == "__main__":
    main()
