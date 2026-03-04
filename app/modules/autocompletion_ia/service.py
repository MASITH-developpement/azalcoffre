# AZALPLUS - Service Autocompletion IA
import hashlib
import json
import logging
import time
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from .providers import AnthropicProvider, BaseProvider, LocalProvider, OpenAIProvider, ProviderFactory
from .schemas import (
    CompletionRequest,
    CompletionResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    FeedbackRequest,
    Suggestion,
    SuggestionMeta,
    SuggestionRequest,
    SuggestionResponse,
    StatsResponse,
)

logger = logging.getLogger(__name__)


class AutocompletionIAService:
    """Service principal d'autocomplétion IA."""

    def __init__(self, db: Session, tenant_id: UUID, cache=None):
        self.db = db
        self.tenant_id = tenant_id
        self.cache = cache  # Redis ou cache en mémoire
        self._config: Optional[dict] = None
        self._providers: dict[str, BaseProvider] = {}

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------
    def _get_config(self) -> dict:
        """Récupérer la configuration du tenant."""
        if self._config is None:
            # Charger les clés API depuis la configuration AZALPLUS
            try:
                from moteur.config import settings
                openai_key = settings.OPENAI_API_KEY
                anthropic_key = settings.ANTHROPIC_API_KEY
            except ImportError:
                import os
                openai_key = os.environ.get("OPENAI_API_KEY", "")
                anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

            self._config = {
                "actif": True,
                "fournisseur_defaut": "anthropic",
                "modele_defaut": "claude-sonnet-4-20250514",
                "openai_api_key": openai_key,
                "anthropic_api_key": anthropic_key,
                "mode": "suggestions",
                "nombre_suggestions": 5,
                "delai_declenchement": 300,
                "longueur_min": 2,
                "temperature": 0.3,
                "utiliser_contexte_module": True,
                "utiliser_historique": True,
                "cache_actif": True,
                "cache_duree_minutes": 60,
                "limite_requetes_jour": 1000,
                "limite_tokens_jour": 100000,
                "fallback_fournisseur": "local",
            }
        return self._config

    def _get_provider(self, provider_name: Optional[str] = None) -> BaseProvider:
        """Obtenir un provider IA."""
        config = self._get_config()
        name = provider_name or config["fournisseur_defaut"]

        if name not in self._providers:
            try:
                if name == "openai":
                    api_key = config.get("openai_api_key")
                    model = config.get("modele_defaut") if config["fournisseur_defaut"] == "openai" else "gpt-4o-mini"
                    self._providers[name] = ProviderFactory.create("openai", api_key=api_key, model=model)
                elif name == "anthropic":
                    api_key = config.get("anthropic_api_key")
                    model = config.get("modele_defaut") if config["fournisseur_defaut"] == "anthropic" else "claude-sonnet-4-20250514"
                    self._providers[name] = ProviderFactory.create("anthropic", api_key=api_key, model=model)
                else:
                    self._providers[name] = ProviderFactory.create("local")
            except Exception as e:
                logger.warning(f"Could not create provider {name}: {e}")
                self._providers[name] = LocalProvider()

        return self._providers[name]

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------
    def _build_system_prompt(self, module: str, champ: str, type_completion: Optional[str] = None) -> str:
        """Construire le prompt système."""
        base = """Tu es un assistant d'autocomplétion pour l'ERP AZALPLUS.
Tu dois proposer des suggestions pertinentes, professionnelles et contextuelles.

Règles STRICTES:
- Réponds UNIQUEMENT avec les suggestions, une par ligne
- Pas de numérotation (1., 2., etc.)
- Pas d'explication ni de commentaire
- Langue: français
- Maximum 5 suggestions
"""
        # Ajouter des règles spécifiques selon le type
        type_rules = {
            "nom_personne": "\nContexte: Noms de personnes francophones courants.",
            "nom_entreprise": "\nContexte: Noms d'entreprises françaises avec forme juridique si pertinent.",
            "email": "\nContexte: Adresses email professionnelles, format prenom.nom@domaine.com",
            "adresse": "\nContexte: Adresses françaises, format: numéro rue, code postal ville",
            "telephone": "\nContexte: Numéros de téléphone français, format: 0X XX XX XX XX",
            "reference": f"\nContexte: Références de documents du module {module}",
            "description": "\nContexte: Texte professionnel, compléter de manière cohérente",
        }

        if type_completion and type_completion in type_rules:
            base += type_rules[type_completion]

        return base

    def _build_user_prompt(
        self,
        request: SuggestionRequest,
        historique: list[str],
    ) -> str:
        """Construire le prompt utilisateur."""
        prompt = f"""Module: {request.module}
Champ: {request.champ}
Valeur actuelle: "{request.valeur}"
"""
        if historique:
            prompt += f"\nHistorique récent du champ:\n" + "\n".join(f"- {h}" for h in historique[:5])

        if request.contexte:
            prompt += f"\nContexte additionnel:\n{json.dumps(request.contexte, ensure_ascii=False, indent=2)}"

        prompt += f"\n\nPropose {request.limite} suggestions pertinentes pour compléter cette saisie."

        return prompt

    # -------------------------------------------------------------------------
    # Cache
    # -------------------------------------------------------------------------
    def _cache_key(self, request: SuggestionRequest) -> str:
        """Générer une clé de cache."""
        data = f"{self.tenant_id}:{request.module}:{request.champ}:{request.valeur}"
        return f"autocomplete:{hashlib.md5(data.encode()).hexdigest()}"

    async def _get_from_cache(self, key: str) -> Optional[list[str]]:
        """Récupérer du cache."""
        if not self.cache or not self._get_config()["cache_actif"]:
            return None
        try:
            cached = await self.cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        return None

    async def _set_cache(self, key: str, value: list[str], ttl_minutes: int = 60) -> None:
        """Mettre en cache."""
        if not self.cache or not self._get_config()["cache_actif"]:
            return
        try:
            await self.cache.setex(key, ttl_minutes * 60, json.dumps(value))
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    # -------------------------------------------------------------------------
    # Historique
    # -------------------------------------------------------------------------
    async def _get_historique(self, module: str, champ: str, limit: int = 10) -> list[str]:
        """Récupérer l'historique des valeurs pour ce champ."""
        # TODO: Implémenter la récupération depuis la base
        # Pour l'instant, retourner une liste vide
        return []

    async def _save_to_historique(self, module: str, champ: str, valeur: str) -> None:
        """Sauvegarder une valeur dans l'historique."""
        # TODO: Implémenter la sauvegarde
        pass

    # -------------------------------------------------------------------------
    # Méthodes principales
    # -------------------------------------------------------------------------
    async def get_suggestions(self, request: SuggestionRequest) -> SuggestionResponse:
        """Obtenir des suggestions d'autocomplétion."""
        start_time = time.time()
        config = self._get_config()

        # Vérifier si actif
        if not config["actif"]:
            return SuggestionResponse(
                suggestions=[],
                meta=SuggestionMeta(
                    cached=False,
                    latency_ms=0,
                ),
            )

        # Vérifier longueur minimale
        if len(request.valeur) < config["longueur_min"]:
            return SuggestionResponse(
                suggestions=[],
                meta=SuggestionMeta(
                    cached=False,
                    latency_ms=0,
                ),
            )

        # Vérifier le cache
        cache_key = self._cache_key(request)
        cached_suggestions = await self._get_from_cache(cache_key)
        if cached_suggestions:
            return SuggestionResponse(
                suggestions=[
                    Suggestion(
                        id=uuid4(),
                        texte=s,
                        score=1.0 - (i * 0.1),
                        source="cache",
                    )
                    for i, s in enumerate(cached_suggestions)
                ],
                meta=SuggestionMeta(
                    cached=True,
                    latency_ms=int((time.time() - start_time) * 1000),
                ),
            )

        # Récupérer l'historique
        historique = []
        if config["utiliser_historique"]:
            historique = await self._get_historique(request.module, request.champ)

        # Construire les prompts
        system_prompt = self._build_system_prompt(
            request.module,
            request.champ,
            request.type_completion,
        )
        user_prompt = self._build_user_prompt(request, historique)

        # Appeler le provider
        provider_name = request.provider or config["fournisseur_defaut"]
        provider = self._get_provider(provider_name)
        suggestions_text = []

        try:
            suggestions_text = await provider.get_suggestions(
                prompt=user_prompt,
                system_prompt=system_prompt,
                n=request.limite,
                temperature=config["temperature"],
            )
        except Exception as e:
            logger.error(f"Provider {provider_name} failed: {e}")
            # Fallback
            fallback_name = config["fallback_fournisseur"]
            if fallback_name and fallback_name != provider_name:
                try:
                    provider = self._get_provider(fallback_name)
                    provider_name = fallback_name
                    suggestions_text = await provider.get_suggestions(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        n=request.limite,
                        temperature=config["temperature"],
                    )
                except Exception as e2:
                    logger.error(f"Fallback {fallback_name} also failed: {e2}")

        # Mettre en cache
        if suggestions_text:
            await self._set_cache(cache_key, suggestions_text, config["cache_duree_minutes"])

        # Construire la réponse
        latency_ms = int((time.time() - start_time) * 1000)
        suggestions = [
            Suggestion(
                id=uuid4(),
                texte=s,
                score=1.0 - (i * 0.1),
                source="ia",
                provider=provider_name,
            )
            for i, s in enumerate(suggestions_text)
        ]

        return SuggestionResponse(
            suggestions=suggestions,
            meta=SuggestionMeta(
                provider=provider_name,
                model=getattr(provider, "model", None),
                cached=False,
                latency_ms=latency_ms,
            ),
        )

    async def complete_text(self, request: CompletionRequest) -> CompletionResponse:
        """Compléter un texte long."""
        start_time = time.time()
        config = self._get_config()

        if not config["actif"]:
            return CompletionResponse(
                completion="",
                meta=SuggestionMeta(cached=False, latency_ms=0),
            )

        system_prompt = """Tu es un assistant de rédaction professionnelle pour l'ERP AZALPLUS.
Continue le texte de manière cohérente et professionnelle.
Garde le même ton et style que le début du texte.
Réponds uniquement avec la suite du texte, sans répéter le début."""

        user_prompt = f"""Module: {request.module}
Champ: {request.champ}

Texte à compléter: "{request.valeur}"

Continue ce texte (maximum {request.max_tokens} tokens)."""

        if request.contexte:
            user_prompt += f"\n\nContexte:\n{json.dumps(request.contexte, ensure_ascii=False, indent=2)}"

        provider_name = request.provider or config["fournisseur_defaut"]
        provider = self._get_provider(provider_name)

        try:
            completion = await provider.complete_text(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=request.max_tokens,
            )
        except Exception as e:
            logger.error(f"Completion failed: {e}")
            completion = ""

        latency_ms = int((time.time() - start_time) * 1000)

        return CompletionResponse(
            completion=completion,
            meta=SuggestionMeta(
                provider=provider_name,
                model=getattr(provider, "model", None),
                cached=False,
                latency_ms=latency_ms,
            ),
        )

    async def record_feedback(self, request: FeedbackRequest) -> None:
        """Enregistrer un feedback sur une suggestion."""
        # TODO: Sauvegarder le feedback pour amélioration
        if request.accepted and request.valeur_finale:
            # Ajouter à l'historique
            pass
        logger.info(
            f"Feedback recorded: suggestion={request.suggestion_id}, "
            f"accepted={request.accepted}"
        )

    async def get_config(self) -> ConfigResponse:
        """Obtenir la configuration actuelle."""
        config = self._get_config()
        # TODO: Récupérer les stats d'utilisation
        return ConfigResponse(
            actif=config["actif"],
            fournisseur_defaut=config["fournisseur_defaut"],
            modele_defaut=config["modele_defaut"],
            mode=config["mode"],
            nombre_suggestions=config["nombre_suggestions"],
            temperature=config["temperature"],
            openai_configured=bool(config.get("openai_api_key")),
            anthropic_configured=bool(config.get("anthropic_api_key")),
            limite_requetes_jour=config["limite_requetes_jour"],
            limite_tokens_jour=config["limite_tokens_jour"],
            requetes_aujourd_hui=0,  # TODO
            tokens_aujourd_hui=0,  # TODO
        )

    async def update_config(self, request: ConfigUpdateRequest) -> ConfigResponse:
        """Mettre à jour la configuration."""
        config = self._get_config()

        # Mettre à jour les champs fournis
        if request.actif is not None:
            config["actif"] = request.actif
        if request.fournisseur_defaut is not None:
            config["fournisseur_defaut"] = request.fournisseur_defaut
        if request.modele_defaut is not None:
            config["modele_defaut"] = request.modele_defaut
        if request.mode is not None:
            config["mode"] = request.mode
        if request.nombre_suggestions is not None:
            config["nombre_suggestions"] = request.nombre_suggestions
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.openai_api_key is not None:
            config["openai_api_key"] = request.openai_api_key
            # Réinitialiser le provider pour utiliser la nouvelle clé
            self._providers.pop("openai", None)
        if request.anthropic_api_key is not None:
            config["anthropic_api_key"] = request.anthropic_api_key
            # Réinitialiser le provider pour utiliser la nouvelle clé
            self._providers.pop("anthropic", None)

        # TODO: Sauvegarder en base de données
        logger.info(f"Config updated for tenant {self.tenant_id}")

        return await self.get_config()

    async def get_stats(self, date_debut: date, date_fin: date) -> StatsResponse:
        """Obtenir les statistiques d'utilisation."""
        # TODO: Implémenter les vraies stats
        return StatsResponse(
            date=datetime.now(),
            requetes_total=0,
            tokens_total=0,
            cout_estime=0.0,
            cache_hits=0,
            cache_misses=0,
            latence_moyenne_ms=0.0,
            par_provider={},
            par_module={},
        )

    async def health_check(self) -> dict[str, Any]:
        """Vérifier l'état des providers."""
        results = {}

        for name in ["openai", "anthropic", "local"]:
            try:
                provider = self._get_provider(name)
                results[name] = await provider.health_check()
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}

        # Vérifier le cache
        if self.cache:
            try:
                await self.cache.ping()
                results["cache"] = {"status": "ok"}
            except Exception as e:
                results["cache"] = {"status": "error", "error": str(e)}
        else:
            results["cache"] = {"status": "disabled"}

        return results
