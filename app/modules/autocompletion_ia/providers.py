# AZALPLUS - Providers IA pour Autocompletion
import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Classe de base pour les providers IA."""

    name: str = "base"

    @abstractmethod
    async def get_suggestions(
        self,
        prompt: str,
        system_prompt: str,
        n: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 100,
    ) -> list[str]:
        """Obtenir des suggestions depuis le provider."""
        pass

    @abstractmethod
    async def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 200,
    ) -> str:
        """Compléter un texte."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Vérifier l'état du provider."""
        pass


class OpenAIProvider(BaseProvider):
    """Provider OpenAI (ChatGPT)."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        self.timeout = 30.0

    async def get_suggestions(
        self,
        prompt: str,
        system_prompt: str,
        n: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 100,
    ) -> list[str]:
        """Obtenir des suggestions via OpenAI."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "n": 1,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Parser les suggestions (une par ligne)
                content = data["choices"][0]["message"]["content"]
                suggestions = [
                    line.strip()
                    for line in content.strip().split("\n")
                    if line.strip() and not line.strip().startswith(("-", "*", "•"))
                ]

                # Nettoyer les numérotations éventuelles
                cleaned = []
                for s in suggestions[:n]:
                    # Enlever "1.", "1)", etc.
                    if len(s) > 2 and s[0].isdigit() and s[1] in ".):":
                        s = s[2:].strip()
                    elif len(s) > 3 and s[:2].isdigit() and s[2] in ".):":
                        s = s[3:].strip()
                    if s:
                        cleaned.append(s)

                return cleaned[:n]

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            raise

    async def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 200,
    ) -> str:
        """Compléter un texte via OpenAI."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logger.error(f"OpenAI completion error: {e}")
            raise

    async def health_check(self) -> dict[str, Any]:
        """Vérifier la connexion OpenAI."""
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                latency = int((time.time() - start) * 1000)
                return {
                    "status": "ok" if response.status_code == 200 else "error",
                    "latency_ms": latency,
                    "model": self.model,
                    "error": None if response.status_code == 200 else response.text,
                }
        except Exception as e:
            return {"status": "error", "error": str(e), "model": self.model}


class AnthropicProvider(BaseProvider):
    """Provider Anthropic (Claude)."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://api.anthropic.com/v1/messages"
        self.version = "2023-06-01"
        self.timeout = 30.0

    async def get_suggestions(
        self,
        prompt: str,
        system_prompt: str,
        n: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 100,
    ) -> list[str]:
        """Obtenir des suggestions via Anthropic Claude."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.version,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Parser les suggestions
                content = data["content"][0]["text"]
                suggestions = [
                    line.strip()
                    for line in content.strip().split("\n")
                    if line.strip() and not line.strip().startswith(("-", "*", "•"))
                ]

                # Nettoyer les numérotations
                cleaned = []
                for s in suggestions[:n]:
                    if len(s) > 2 and s[0].isdigit() and s[1] in ".):":
                        s = s[2:].strip()
                    elif len(s) > 3 and s[:2].isdigit() and s[2] in ".):":
                        s = s[3:].strip()
                    if s:
                        cleaned.append(s)

                return cleaned[:n]

        except httpx.HTTPStatusError as e:
            logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
            raise

    async def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 200,
    ) -> str:
        """Compléter un texte via Claude."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.version,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["content"][0]["text"].strip()

        except Exception as e:
            logger.error(f"Anthropic completion error: {e}")
            raise

    async def health_check(self) -> dict[str, Any]:
        """Vérifier la connexion Anthropic."""
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test simple avec un message minimal
                response = await client.post(
                    self.endpoint,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.version,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "test"}],
                    },
                )
                latency = int((time.time() - start) * 1000)
                return {
                    "status": "ok" if response.status_code == 200 else "error",
                    "latency_ms": latency,
                    "model": self.model,
                    "error": None if response.status_code == 200 else response.text,
                }
        except Exception as e:
            return {"status": "error", "error": str(e), "model": self.model}


class LocalProvider(BaseProvider):
    """Provider local basé sur l'historique (fallback sans IA)."""

    name = "local"

    def __init__(self, historique_service=None):
        self.historique_service = historique_service
        # Suggestions de base par type
        self.suggestions_base = {
            "nom_personne": [
                "Martin", "Bernard", "Dubois", "Thomas", "Robert",
                "Richard", "Petit", "Durand", "Leroy", "Moreau",
            ],
            "nom_entreprise": [
                "ACME SARL", "Solutions Tech SAS", "Groupe Martin SA",
                "Digital Services", "Conseil & Stratégie",
            ],
            "email_domain": [
                "gmail.com", "outlook.com", "yahoo.fr", "orange.fr", "free.fr",
            ],
            "ville": [
                "Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux",
                "Lille", "Nantes", "Strasbourg", "Nice", "Rennes",
            ],
        }

    async def get_suggestions(
        self,
        prompt: str,
        system_prompt: str,
        n: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 100,
    ) -> list[str]:
        """Suggestions basées sur l'historique local."""
        # Extraire le type de complétion du prompt
        suggestions = []

        # Chercher dans l'historique si disponible
        if self.historique_service:
            historique = await self.historique_service.get_recent(n * 2)
            suggestions.extend(historique)

        # Compléter avec des suggestions de base si nécessaire
        if len(suggestions) < n:
            if "nom" in prompt.lower() and "entreprise" in prompt.lower():
                suggestions.extend(self.suggestions_base["nom_entreprise"])
            elif "nom" in prompt.lower() or "personne" in prompt.lower():
                suggestions.extend(self.suggestions_base["nom_personne"])
            elif "ville" in prompt.lower():
                suggestions.extend(self.suggestions_base["ville"])
            elif "email" in prompt.lower():
                suggestions.extend(
                    [f"contact@{d}" for d in self.suggestions_base["email_domain"]]
                )

        return suggestions[:n]

    async def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 200,
    ) -> str:
        """Complétion locale (limitée)."""
        # Le provider local ne peut pas vraiment compléter du texte
        return ""

    async def health_check(self) -> dict[str, Any]:
        """Toujours disponible."""
        return {
            "status": "ok",
            "latency_ms": 0,
            "model": "local",
            "error": None,
        }


class ProviderFactory:
    """Factory pour créer les providers."""

    @staticmethod
    def create(
        provider_name: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> BaseProvider:
        """Créer un provider selon le nom."""
        if provider_name == "openai":
            if not api_key:
                raise ValueError("OpenAI API key required")
            return OpenAIProvider(
                api_key=api_key,
                model=model or "gpt-4o-mini",
            )
        elif provider_name == "anthropic":
            if not api_key:
                raise ValueError("Anthropic API key required")
            return AnthropicProvider(
                api_key=api_key,
                model=model or "claude-sonnet-4-20250514",
            )
        elif provider_name == "local":
            return LocalProvider(**kwargs)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
