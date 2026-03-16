# =============================================================================
# AUTOPILOT - Claude Fixer: Corrections par IA
# =============================================================================
"""
Claude Fixer: Quand AutoFixer échoue, Claude analyse et corrige.

Flux:
1. Guardian détecte erreur
2. AutoFixer tente correction automatique
3. Si échec → ClaudeFixer analyse avec l'API Claude
4. Claude génère la correction
5. ClaudeFixer applique la correction

Ce module utilise l'API Anthropic pour obtenir des corrections intelligentes.
"""

import os
import re
import json
import asyncio
import structlog
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from datetime import datetime

logger = structlog.get_logger()

# Essayer d'importer anthropic
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic_not_installed", message="pip install anthropic")


class ClaudeFixer:
    """
    Utilise Claude pour analyser et corriger les erreurs complexes.
    """

    _client = None
    _enabled = False
    _model = "claude-sonnet-4-20250514"
    _max_tokens = 4096

    # Historique des corrections pour apprentissage
    _corrections_history: list = []
    _max_history = 100

    @classmethod
    def initialize(cls):
        """Initialise le client Anthropic."""
        if not ANTHROPIC_AVAILABLE:
            logger.warning("claude_fixer_disabled", reason="anthropic not installed")
            return False

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            # Essayer de lire depuis la config
            try:
                from ..config import settings
                api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
            except:
                pass

        if not api_key:
            logger.warning("claude_fixer_disabled", reason="ANTHROPIC_API_KEY not set")
            return False

        try:
            cls._client = anthropic.Anthropic(api_key=api_key)
            cls._enabled = True
            cls._corrections_history = []
            logger.info("claude_fixer_initialized")
            return True
        except Exception as e:
            logger.error("claude_fixer_init_failed", error=str(e))
            return False

    @classmethod
    def is_enabled(cls) -> bool:
        """Vérifie si Claude Fixer est activé."""
        return cls._enabled and cls._client is not None

    @classmethod
    async def fix_error(cls, error_context: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        Analyse une erreur et génère une correction.

        Args:
            error_context: Dict contenant:
                - error_log: Le log d'erreur complet
                - error_type: Type d'erreur (http_400, js_error, etc.)
                - source_file: Fichier source si connu
                - attempts: Nombre de tentatives AutoFixer
                - path: Chemin de l'endpoint/fichier concerné

        Returns:
            Tuple[bool, str, Optional[str]]:
                - success: True si correction appliquée
                - message: Description de la correction
                - diff: Le diff de la correction (ou None)
        """
        if not cls.is_enabled():
            return False, "Claude Fixer non activé", None

        error_log = error_context.get("error_log", "")
        error_type = error_context.get("error_type", "unknown")
        path = error_context.get("path", "")

        logger.info("claude_fixer_analyzing", error_type=error_type, path=path)

        try:
            # Construire le prompt pour Claude
            prompt = cls._build_prompt(error_context)

            # Appeler Claude dans un thread séparé pour ne pas bloquer l'event loop
            def _call_claude():
                return cls._client.messages.create(
                    model=cls._model,
                    max_tokens=cls._max_tokens,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    system=cls._get_system_prompt()
                )

            response = await asyncio.to_thread(_call_claude)

            # Parser la réponse
            response_text = response.content[0].text
            success, message, diff = cls._parse_response(response_text, error_context)

            if success:
                # Appliquer la correction
                applied = cls._apply_correction(response_text, error_context)
                if applied:
                    cls._record_correction(error_context, response_text, True)
                    logger.info("claude_fixer_applied", path=path, message=message)
                    return True, message, diff
                else:
                    logger.warning("claude_fixer_apply_failed", path=path)
                    return False, "Correction générée mais non appliquée", diff
            else:
                logger.info("claude_fixer_no_fix", path=path, reason=message)
                return False, message, None

        except Exception as e:
            logger.error("claude_fixer_error", error=str(e))
            return False, f"Erreur Claude Fixer: {str(e)}", None

    @classmethod
    def _get_system_prompt(cls) -> str:
        """Retourne le prompt système pour Claude."""
        return """Tu es un expert en correction de bugs pour AZALPLUS, un ERP No-Code.

CONTEXTE:
- Backend: Python FastAPI, SQLAlchemy, Pydantic
- Frontend: JavaScript généré dans ui.py (pas de fichiers JS séparés)
- L'erreur vient du système Guardian qui surveille l'application

TON RÔLE:
1. Analyser l'erreur
2. Identifier la cause racine
3. Proposer une correction PRÉCISE

FORMAT DE RÉPONSE (JSON strict):
```json
{
    "analysis": "Explication courte du problème",
    "root_cause": "Cause racine identifiée",
    "fix": {
        "file": "/chemin/complet/vers/fichier.py",
        "action": "edit|create|delete",
        "search": "code exact à remplacer (pour action=edit)",
        "replace": "nouveau code",
        "description": "Ce que fait cette correction"
    },
    "confidence": 0.95
}
```

RÈGLES:
- Sois PRÉCIS dans le code à chercher/remplacer
- Utilise les doubles accolades {{ }} pour le JavaScript dans ui.py
- Ne modifie JAMAIS la sécurité existante
- Préfère des corrections minimales et ciblées
- Si tu n'es pas sûr, mets confidence < 0.5"""

    @classmethod
    def _build_prompt(cls, error_context: Dict[str, Any]) -> str:
        """Construit le prompt avec le contexte d'erreur."""
        error_log = error_context.get("error_log", "")
        error_type = error_context.get("error_type", "unknown")
        path = error_context.get("path", "")
        attempts = error_context.get("attempts", 0)
        source_file = error_context.get("source_file", "")

        # Lire le fichier source si disponible
        file_content = ""
        if source_file and Path(source_file).exists():
            try:
                content = Path(source_file).read_text()
                # Limiter à 5000 chars autour de la zone problématique
                if len(content) > 10000:
                    # Essayer de trouver la partie pertinente
                    if path:
                        idx = content.find(path)
                        if idx > 0:
                            start = max(0, idx - 2000)
                            end = min(len(content), idx + 3000)
                            file_content = f"...\n{content[start:end]}\n..."
                        else:
                            file_content = content[:5000] + "\n... (tronqué)"
                    else:
                        file_content = content[:5000] + "\n... (tronqué)"
                else:
                    file_content = content
            except Exception as e:
                file_content = f"Erreur lecture: {e}"

        prompt = f"""ERREUR À CORRIGER:

Type: {error_type}
Path: {path}
Tentatives AutoFixer: {attempts}

LOG D'ERREUR:
```
{error_log[:2000]}
```

"""
        if file_content:
            prompt += f"""FICHIER SOURCE ({source_file}):
```python
{file_content}
```

"""

        prompt += """Analyse cette erreur et propose une correction précise au format JSON."""

        return prompt

    @classmethod
    def _parse_response(cls, response: str, context: Dict) -> Tuple[bool, str, Optional[str]]:
        """Parse la réponse de Claude."""
        try:
            # Extraire le JSON de la réponse
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if not json_match:
                # Essayer de parser directement
                json_match = re.search(r'\{[\s\S]*\}', response)

            if not json_match:
                return False, "Pas de JSON dans la réponse", None

            data = json.loads(json_match.group(1) if '```' in response else json_match.group())

            confidence = data.get("confidence", 0)
            if confidence < 0.5:
                return False, f"Confiance trop basse: {confidence}", None

            fix = data.get("fix", {})
            if not fix or not fix.get("file"):
                return False, "Pas de correction proposée", None

            description = fix.get("description", data.get("analysis", "Correction appliquée"))
            diff = f"File: {fix.get('file')}\n-{fix.get('search', '')[:100]}\n+{fix.get('replace', '')[:100]}"

            return True, description, diff

        except json.JSONDecodeError as e:
            return False, f"JSON invalide: {e}", None
        except Exception as e:
            return False, f"Erreur parsing: {e}", None

    @classmethod
    def _apply_correction(cls, response: str, context: Dict) -> bool:
        """Applique la correction proposée par Claude."""
        try:
            # Extraire le JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if not json_match:
                json_match = re.search(r'\{[\s\S]*\}', response)

            if not json_match:
                return False

            data = json.loads(json_match.group(1) if '```' in response else json_match.group())
            fix = data.get("fix", {})

            file_path = Path(fix.get("file", ""))
            action = fix.get("action", "edit")

            if not file_path.exists() and action != "create":
                logger.warning("claude_fix_file_not_found", file=str(file_path))
                return False

            if action == "edit":
                search = fix.get("search", "")
                replace = fix.get("replace", "")

                if not search or not replace:
                    return False

                content = file_path.read_text()
                if search not in content:
                    logger.warning("claude_fix_search_not_found",
                                 file=str(file_path),
                                 search_preview=search[:50])
                    return False

                new_content = content.replace(search, replace, 1)

                # === VALIDATION SYNTAXE AVANT APPLICATION ===
                if file_path.suffix == ".py":
                    is_valid, syntax_error = cls._validate_python_syntax(new_content)
                    if not is_valid:
                        logger.error("claude_fix_syntax_error",
                                   file=str(file_path),
                                   error=syntax_error)
                        return False

                # Backup avant modification
                backup_path = file_path.with_suffix(file_path.suffix + ".claude_backup")
                file_path.rename(backup_path)

                try:
                    file_path.write_text(new_content)

                    # Double vérification: revalider après écriture
                    if file_path.suffix == ".py":
                        is_valid, syntax_error = cls._validate_python_syntax(new_content)
                        if not is_valid:
                            # Restaurer le backup
                            backup_path.rename(file_path)
                            logger.error("claude_fix_post_write_syntax_error", error=syntax_error)
                            return False

                    backup_path.unlink()  # Supprimer le backup si succès
                    return True
                except Exception as e:
                    # Restaurer le backup
                    if backup_path.exists():
                        backup_path.rename(file_path)
                    logger.error("claude_fix_write_failed", error=str(e))
                    return False

            elif action == "create":
                content = fix.get("replace", "")
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
                return True

            return False

        except Exception as e:
            logger.error("claude_fix_apply_error", error=str(e))
            return False

    @classmethod
    def _validate_python_syntax(cls, code: str) -> Tuple[bool, Optional[str]]:
        """
        Valide la syntaxe Python du code.

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        import ast
        import py_compile
        import tempfile

        try:
            # Méthode 1: ast.parse (rapide, détecte les erreurs de syntaxe)
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            error_msg = f"Ligne {e.lineno}: {e.msg}"
            if e.text:
                error_msg += f" -> {e.text.strip()}"
            return False, error_msg
        except Exception as e:
            return False, f"Erreur de validation: {str(e)}"

    @classmethod
    def _validate_js_syntax(cls, code: str) -> Tuple[bool, Optional[str]]:
        """
        Validation basique de syntaxe JavaScript.
        Vérifie l'équilibre des accolades, parenthèses, etc.
        """
        # Compteurs pour les délimiteurs
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}

        in_string = False
        string_char = None
        escape_next = False

        for i, char in enumerate(code):
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char in '"\'`':
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                continue

            if in_string:
                continue

            if char in '([{':
                stack.append(char)
            elif char in ')]}':
                if not stack or stack[-1] != pairs[char]:
                    return False, f"Délimiteur non équilibré à la position {i}: '{char}'"
                stack.pop()

        if stack:
            return False, f"Délimiteurs non fermés: {stack}"

        return True, None

    @classmethod
    def _record_correction(cls, context: Dict, response: str, success: bool):
        """Enregistre une correction pour apprentissage."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "error_type": context.get("error_type"),
            "path": context.get("path"),
            "success": success,
            "response_preview": response[:500]
        }

        cls._corrections_history.append(record)

        # Limiter la taille
        if len(cls._corrections_history) > cls._max_history:
            cls._corrections_history = cls._corrections_history[-cls._max_history:]

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Retourne les statistiques de corrections."""
        total = len(cls._corrections_history)
        success = sum(1 for r in cls._corrections_history if r.get("success"))

        return {
            "enabled": cls._enabled,
            "total_corrections": total,
            "successful": success,
            "success_rate": (success / total * 100) if total > 0 else 0,
            "model": cls._model
        }
