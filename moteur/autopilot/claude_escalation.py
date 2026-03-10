# =============================================================================
# AZALPLUS - Claude Escalation Handler
# =============================================================================
"""
Appelle Claude uniquement après 3 escalades sur le même problème.
Économise les tokens tout en gardant l'intelligence de Claude.
"""

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional, Tuple, Dict
import structlog

# Charger .env si présent
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/azalplus/.env")

logger = structlog.get_logger()

# Fichiers
ALERTS_LOG = Path("/home/ubuntu/azalplus/logs/errors.log")  # Fichier central où ErrorCollector écrit
FIXES_LOG = Path("/home/ubuntu/azalplus/logs/guardian_fixes.log")
LEARNING_LOG = Path("/home/ubuntu/azalplus/logs/guardian_learning.log")
PROCESSED_FILE = Path("/home/ubuntu/azalplus/logs/.escalations_processed")
COUNTS_FILE = Path("/home/ubuntu/azalplus/logs/.escalation_counts.json")
TOKENS_FILE = Path("/home/ubuntu/azalplus/logs/guardian_tokens.log")

# Seuil avant d'appeler Claude
ESCALATION_THRESHOLD = 3


class ClaudeEscalationHandler:
    """Gestionnaire d'escalades avec appel Claude après seuil."""

    def __init__(self):
        self.last_position = self._load_position()
        self.escalation_counts: Dict[str, int] = self._load_counts()
        self.processed_keys: set = set()
        self._ensure_logs_exist()

    def _ensure_logs_exist(self):
        """Crée les fichiers de log si nécessaire."""
        for log_file in [ALERTS_LOG, FIXES_LOG, LEARNING_LOG]:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            if not log_file.exists():
                log_file.touch()

    def _load_position(self) -> int:
        """Charge la dernière position lue."""
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

    def _load_counts(self) -> Dict[str, int]:
        """Charge les compteurs d'escalades."""
        try:
            if COUNTS_FILE.exists():
                return json.loads(COUNTS_FILE.read_text())
        except:
            pass
        return {}

    def _save_counts(self):
        """Sauvegarde les compteurs."""
        COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        COUNTS_FILE.write_text(json.dumps(self.escalation_counts))

    def _get_error_key(self, escalation) -> str:
        """Extrait une clé unique pour grouper les erreurs similaires."""
        # Format dict (JSON from errors.log)
        if isinstance(escalation, dict):
            error_type = escalation.get("error_type", "unknown")
            source_file = escalation.get("source_file", "")
            message = escalation.get("message", "")
            # Créer une clé basée sur le type et le fichier source
            if source_file:
                error_key = f"{error_type}:{source_file}"
            else:
                error_key = f"{error_type}:{message[:50]}"
            return error_key[:100]

        # Format string (ancien format texte)
        parts = str(escalation).split("|")
        if len(parts) >= 3:
            error_info = parts[2].strip()
            # Normaliser: enlever les UUIDs, timestamps, etc.
            error_key = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID', error_info)
            error_key = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', error_key)
            error_key = re.sub(r'\d+', 'N', error_key)
            return error_key[:100]
        return str(escalation)[:50]

    def _log_fix(self, fix_type: str, message: str):
        """Log une correction."""
        with open(FIXES_LOG, "a") as f:
            f.write(f"{datetime.now().isoformat()} | FIX | {fix_type} | {message}\n")

    def _log_learning(self, category: str, lesson: str):
        """Log un apprentissage."""
        with open(LEARNING_LOG, "a") as f:
            f.write(f"{datetime.now().isoformat()} | LEARN | {category} | {lesson}\n")

    def _log_tokens(self, action: str, input_tokens: int, output_tokens: int, error_key: str):
        """Log les tokens utilisés."""
        total = input_tokens + output_tokens
        with open(TOKENS_FILE, "a") as f:
            f.write(f"{datetime.now().isoformat()} | {action} | input:{input_tokens} | output:{output_tokens} | total:{total} | {error_key[:50]}\n")
        logger.info("tokens_logged", action=action, input=input_tokens, output=output_tokens, total=total)

    def check_new_escalations(self) -> list:
        """Vérifie les nouvelles erreurs dans errors.log (format JSON)."""
        if not ALERTS_LOG.exists():
            return []

        with open(ALERTS_LOG, "r") as f:
            content = f.read()

        new_content = content[self.last_position:]
        self.last_position = len(content)
        self._save_position(self.last_position)

        if not new_content.strip():
            return []

        escalations = []
        for line in new_content.strip().split("\n"):
            if not line.strip():
                continue
            try:
                # Parser la ligne JSON
                error_data = json.loads(line)
                # Toutes les erreurs sont des escalades potentielles
                if error_data.get("error_type"):
                    escalations.append(error_data)
            except json.JSONDecodeError:
                # Ancien format texte (fallback)
                if "ERROR" in line or "ESCALATION" in line:
                    escalations.append({"raw": line, "error_type": "unknown"})

        return escalations

    def process_escalation(self, escalation: str) -> Optional[str]:
        """
        Traite une escalade.
        Retourne le error_key si le seuil est atteint, None sinon.
        """
        error_key = self._get_error_key(escalation)

        # Incrémenter le compteur
        self.escalation_counts[error_key] = self.escalation_counts.get(error_key, 0) + 1
        self._save_counts()

        count = self.escalation_counts[error_key]
        logger.info("escalation_counted", error_key=error_key, count=count, threshold=ESCALATION_THRESHOLD)

        # Appeler Claude si:
        # 1. Seuil atteint pour la première fois (count == THRESHOLD)
        # 2. OU erreur persiste après fix (tous les THRESHOLD*2 = 6 occurrences)
        should_call = (
            (count == ESCALATION_THRESHOLD) or
            (count > ESCALATION_THRESHOLD and count % (ESCALATION_THRESHOLD * 2) == 0)
        )

        if should_call:
            logger.info("calling_claude", error_key=error_key, count=count, reason="threshold_reached" if count == ESCALATION_THRESHOLD else "error_persists")
            return error_key

        return None

    def call_claude(self, error_key: str, escalations: list) -> Tuple[bool, str]:
        """
        Appelle Claude pour analyser et corriger le problème.
        """
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic_not_installed")
            return False, "Module anthropic non installé"

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("anthropic_api_key_missing")
            return False, "ANTHROPIC_API_KEY non défini"

        # Identifier le fichier concerné et lire son contenu
        file_content = ""
        target_file = ""
        if "/api/" in error_key and "bulk" in error_key.lower():
            target_file = "/home/ubuntu/azalplus/moteur/api.py"
        elif "ui" in error_key.lower():
            target_file = "/home/ubuntu/azalplus/moteur/ui.py"
        elif "422" in error_key or "validation" in error_key.lower():
            target_file = "/home/ubuntu/azalplus/moteur/api.py"

        if target_file:
            try:
                # Lire les 200 premières lignes du fichier pertinent
                with open(target_file, "r") as f:
                    lines = f.readlines()[:200]
                    file_content = f"\n\nCONTENU ACTUEL DE {target_file} (200 premières lignes):\n```python\n{''.join(lines)}```"
            except:
                pass

        # Formater les escalations (dict ou string)
        escalation_lines = []
        for esc in escalations[-5:]:
            if isinstance(esc, dict):
                escalation_lines.append(f"- Type: {esc.get('error_type')} | Source: {esc.get('source_file')} | Message: {esc.get('message')}")
            else:
                escalation_lines.append(f"- {esc}")

        # Construire le contexte pour Claude
        context = f"""Tu es le garant de Guardian, le système de protection d'AZALPLUS.

ERREUR RÉCURRENTE ({len(escalations)} occurrences):
{chr(10).join(escalation_lines)}

Clé d'erreur: {error_key}
{file_content}

INSTRUCTIONS:
1. Analyse l'erreur
2. Identifie la cause racine dans le code RÉEL ci-dessus
3. Propose un fix PRÉCIS - le old_code DOIT correspondre EXACTEMENT au code actuel
4. Indique l'apprentissage pour Guardian

IMPORTANT: Le old_code doit être une copie EXACTE du code existant, caractère pour caractère.

Réponds en JSON:
{{
    "cause": "description courte",
    "fix_file": "/chemin/fichier.py",
    "fix_code": "nouveau code complet",
    "old_code": "code EXACT à remplacer (copié du contenu ci-dessus)",
    "learning": "ce que Guardian doit retenir"
}}
"""

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": context}]
            )

            # Extraire les tokens utilisés
            input_tokens = response.usage.input_tokens if hasattr(response, 'usage') else 0
            output_tokens = response.usage.output_tokens if hasattr(response, 'usage') else 0

            response_text = response.content[0].text
            logger.info("claude_response_received", length=len(response_text), input_tokens=input_tokens, output_tokens=output_tokens)

            # Parser la réponse JSON
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                fix_data = json.loads(json_match.group())
                success, message = self._apply_claude_fix(fix_data)

                # Log tokens selon le résultat
                if success:
                    self._log_tokens("CORRECTION", input_tokens, output_tokens, error_key)
                else:
                    self._log_tokens("APPRENTISSAGE", input_tokens, output_tokens, error_key)

                return success, message
            else:
                # Pas de fix mais on a appris quelque chose
                self._log_tokens("APPRENTISSAGE", input_tokens, output_tokens, error_key)
                logger.error("claude_response_not_json", response=response_text[:200])
                return False, "Réponse Claude non parseable"

        except Exception as e:
            logger.error("claude_call_failed", error=str(e))
            return False, f"Erreur appel Claude: {str(e)}"

    def _apply_claude_fix(self, fix_data: dict) -> Tuple[bool, str]:
        """Applique le fix suggéré par Claude."""
        try:
            fix_file = fix_data.get("fix_file")
            fix_code = fix_data.get("fix_code")
            old_code = fix_data.get("old_code")
            learning = fix_data.get("learning", "")
            cause = fix_data.get("cause", "")

            if not fix_file or not fix_code:
                return False, "Fix incomplet de Claude"

            file_path = Path(fix_file)
            if not file_path.exists():
                return False, f"Fichier {fix_file} non trouvé"

            content = file_path.read_text()

            # Appliquer le fix
            if old_code and old_code in content:
                # Remplacement
                new_content = content.replace(old_code, fix_code)
                file_path.write_text(new_content)
                self._log_fix("claude_replace", f"{cause} - {fix_file}")
            elif old_code:
                # old_code non trouvé
                logger.warning("old_code_not_found", file=fix_file)
                return False, "Code à remplacer non trouvé"
            else:
                # Ajout (append au fichier - à améliorer)
                logger.warning("fix_mode_append_not_supported")
                return False, "Mode ajout non supporté"

            # Log l'apprentissage
            if learning:
                self._log_learning("claude_fix", learning)

            # Trigger reload serveur
            Path("/home/ubuntu/azalplus/moteur/__reload_trigger__").touch()
            time.sleep(0.5)
            Path("/home/ubuntu/azalplus/moteur/__reload_trigger__").unlink(missing_ok=True)

            # Reset le compteur pour cette erreur
            error_keys_to_reset = [k for k in self.escalation_counts.keys() if cause.lower() in k.lower()]
            for k in error_keys_to_reset:
                self.escalation_counts[k] = 0
            self._save_counts()

            return True, f"Fix Claude appliqué: {cause}"

        except Exception as e:
            logger.error("apply_claude_fix_failed", error=str(e))
            return False, f"Erreur application fix: {str(e)}"

    def run(self, interval: int = 10):
        """Boucle principale."""
        logger.info("claude_escalation_handler_started", threshold=ESCALATION_THRESHOLD)
        print(f"[ClaudeEscalation] Démarré - seuil: {ESCALATION_THRESHOLD} escalades")
        print(f"[ClaudeEscalation] Vérifie toutes les {interval}s")

        # Collecter les escalades par error_key
        pending_escalations: Dict[str, list] = defaultdict(list)

        while True:
            try:
                new_escalations = self.check_new_escalations()

                for esc in new_escalations:
                    error_key = self._get_error_key(esc)
                    pending_escalations[error_key].append(esc)

                    result = self.process_escalation(esc)
                    if result:
                        # Seuil atteint - appeler Claude
                        print(f"[ClaudeEscalation] 🚨 Seuil atteint pour: {result[:50]}")
                        print(f"[ClaudeEscalation] 📞 Appel Claude...")

                        success, message = self.call_claude(result, pending_escalations[result])

                        if success:
                            print(f"[ClaudeEscalation] ✅ {message}")
                            pending_escalations[result] = []  # Reset
                        else:
                            print(f"[ClaudeEscalation] ❌ {message}")

                time.sleep(interval)

            except KeyboardInterrupt:
                print("\n[ClaudeEscalation] Arrêt...")
                break
            except Exception as e:
                logger.error("handler_error", error=str(e))
                time.sleep(interval)


def main():
    handler = ClaudeEscalationHandler()
    handler.run(interval=10)


if __name__ == "__main__":
    main()
