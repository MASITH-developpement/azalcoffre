# =============================================================================
# AZALPLUS - Simon (IA Assistant QA)
# =============================================================================
"""
Intégration avec l'API Anthropic pour Simon.
Simon propose uniquement des tests, jamais de code.
"""

import json
from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog
import anthropic

from ..config import settings
from .prompts import (
    SIMON_SYSTEM_PROMPT,
    SIMON_ANALYZE_TICKET_PROMPT,
    SIMON_CHAT_PROMPT,
    SIMON_ANALYZE_ERROR_PROMPT,
    SIMON_MORE_TESTS_PROMPT,
    REFUSAL_MESSAGES
)
from .filters import filter_simon_response, validate_simon_json

logger = structlog.get_logger()


# =============================================================================
# Simon Client
# =============================================================================
class Simon:
    """Assistant QA Simon - Propose uniquement des tests."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-20250514"  # Modèle rapide pour QA

    async def analyze_bug(
        self,
        titre: str,
        description: str,
        logs_texte: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyse un bug et propose des tests (mode ticket).

        Returns:
            {
                "success": bool,
                "message": str,
                "tests": [{"numero": int, "action": str, "resultat_attendu": str}]
            }
        """
        logs_section = f"\nLogs:\n{logs_texte}" if logs_texte else ""

        prompt = SIMON_ANALYZE_TICKET_PROMPT.format(
            titre=titre,
            description=description,
            logs_section=logs_section
        )

        return await self._call_simon(prompt)

    async def chat(
        self,
        titre: str,
        description: str,
        conversation_history: List[Dict[str, str]],
        user_message: str
    ) -> Dict[str, Any]:
        """
        Continue une conversation pour clarifier un bug (mode chat).

        Returns:
            {
                "success": bool,
                "message": str,
                "tests": [...] ou None si question de clarification
            }
        """
        # Formater l'historique
        history_text = ""
        for msg in conversation_history:
            role = "Testeur" if msg["role"] == "user" else "Simon"
            history_text += f"{role}: {msg['message']}\n"

        prompt = SIMON_CHAT_PROMPT.format(
            titre=titre,
            description=description,
            conversation_history=history_text or "(Début de conversation)",
            user_message=user_message
        )

        return await self._call_simon(prompt, allow_question=True)

    async def analyze_error(
        self,
        error_type: str,
        description: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyse une erreur Guardian et propose des tests (mode replay).
        """
        prompt = SIMON_ANALYZE_ERROR_PROMPT.format(
            error_type=error_type,
            description=description,
            context=context or "Pas de contexte supplémentaire"
        )

        return await self._call_simon(prompt)

    async def more_tests(
        self,
        titre: str,
        description: str,
        failed_tests: List[Dict[str, str]],
        comments: List[str]
    ) -> Dict[str, Any]:
        """
        Propose des tests supplémentaires après échecs.
        """
        failed_text = "\n".join([
            f"- Test {t['numero']}: {t['action']} → ÉCHEC"
            for t in failed_tests
        ])

        comments_text = "\n".join([f"- {c}" for c in comments]) or "Aucun commentaire"

        prompt = SIMON_MORE_TESTS_PROMPT.format(
            titre=titre,
            description=description,
            failed_tests=failed_text,
            comments=comments_text
        )

        return await self._call_simon(prompt)

    async def _call_simon(
        self,
        prompt: str,
        allow_question: bool = False
    ) -> Dict[str, Any]:
        """
        Appelle l'API Claude avec le prompt Simon.
        Filtre la réponse pour bloquer tout code.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SIMON_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            raw_response = response.content[0].text

            # Filtrer la réponse
            allowed, filtered_response, violation = filter_simon_response(raw_response)

            if not allowed:
                logger.warning(
                    "simon_response_blocked",
                    violation=violation,
                    prompt_preview=prompt[:100]
                )
                return {
                    "success": False,
                    "message": REFUSAL_MESSAGES.get(violation, "Réponse bloquée."),
                    "tests": []
                }

            # Valider le format JSON
            valid, data, error = validate_simon_json(filtered_response)

            if valid and data:
                return {
                    "success": True,
                    "message": data.get("message", "Analyse terminée."),
                    "tests": data.get("tests", [])
                }

            # Si pas de JSON valide mais question autorisée (mode chat)
            if allow_question and not valid:
                return {
                    "success": True,
                    "message": filtered_response,
                    "tests": None  # Indique une question, pas des tests
                }

            # Erreur de format
            logger.warning("simon_invalid_format", error=error)
            return {
                "success": False,
                "message": "Format de réponse invalide. Réessayez.",
                "tests": []
            }

        except anthropic.APIError as e:
            logger.error("simon_api_error", error=str(e))
            return {
                "success": False,
                "message": "Erreur de communication avec Simon. Réessayez.",
                "tests": []
            }
        except Exception as e:
            logger.error("simon_unexpected_error", error=str(e))
            return {
                "success": False,
                "message": "Une erreur est survenue.",
                "tests": []
            }


# =============================================================================
# Instance globale
# =============================================================================
simon = Simon()
