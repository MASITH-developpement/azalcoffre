# AZALPLUS - Service Autocompletion IA
import hashlib
import json
import logging
import time
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
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
    def _ensure_historique_table(self) -> None:
        """S'assurer que la table autocompletion_historique existe."""
        try:
            from moteur.db import Database

            with Database.get_session() as session:
                check_sql = text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'azalplus'
                        AND table_name = 'autocompletion_historique'
                    )
                """)
                result = session.execute(check_sql)
                exists = result.scalar()

                if not exists:
                    create_sql = text("""
                        CREATE TABLE IF NOT EXISTS azalplus.autocompletion_historique (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            tenant_id UUID NOT NULL,
                            module TEXT NOT NULL,
                            champ TEXT NOT NULL,
                            valeur TEXT NOT NULL,
                            valeur_hash TEXT NOT NULL,
                            frequence INTEGER DEFAULT 1,
                            derniere_utilisation TIMESTAMP DEFAULT NOW(),
                            user_id UUID,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    session.execute(create_sql)

                    index_sql = text("""
                        CREATE INDEX IF NOT EXISTS ix_autocompletion_hist_tenant_module_champ
                            ON azalplus.autocompletion_historique(tenant_id, module, champ);
                        CREATE UNIQUE INDEX IF NOT EXISTS ix_autocompletion_hist_unique
                            ON azalplus.autocompletion_historique(tenant_id, module, champ, valeur_hash);
                    """)
                    session.execute(index_sql)
                    session.commit()
                    logger.info("Created autocompletion_historique table")
        except Exception as e:
            logger.warning(f"Could not ensure historique table: {e}")

    async def _get_historique(self, module: str, champ: str, limit: int = 10) -> list[str]:
        """Récupérer l'historique des valeurs pour ce champ."""
        try:
            from moteur.db import Database

            self._ensure_historique_table()

            with Database.get_session() as session:
                query_sql = text("""
                    SELECT valeur
                    FROM azalplus.autocompletion_historique
                    WHERE tenant_id = :tenant_id
                    AND module = :module
                    AND champ = :champ
                    ORDER BY frequence DESC, derniere_utilisation DESC
                    LIMIT :limit
                """)
                result = session.execute(query_sql, {
                    "tenant_id": str(self.tenant_id),
                    "module": module,
                    "champ": champ,
                    "limit": limit,
                })
                return [row[0] for row in result.fetchall()]
        except ImportError:
            logger.warning("Database not available for historique")
            return []
        except Exception as e:
            logger.warning(f"Could not get historique: {e}")
            return []

    async def _save_to_historique(self, module: str, champ: str, valeur: str) -> None:
        """Sauvegarder une valeur dans l'historique."""
        if not valeur or not valeur.strip():
            return

        try:
            from moteur.db import Database

            self._ensure_historique_table()

            valeur_hash = hashlib.sha256(valeur.lower().encode()).hexdigest()[:32]

            with Database.get_session() as session:
                # Upsert: insérer ou mettre à jour la fréquence
                upsert_sql = text("""
                    INSERT INTO azalplus.autocompletion_historique
                    (id, tenant_id, module, champ, valeur, valeur_hash, frequence, derniere_utilisation)
                    VALUES (
                        :id, :tenant_id, :module, :champ, :valeur, :valeur_hash, 1, NOW()
                    )
                    ON CONFLICT (tenant_id, module, champ, valeur_hash)
                    DO UPDATE SET
                        frequence = autocompletion_historique.frequence + 1,
                        derniere_utilisation = NOW()
                """)
                session.execute(upsert_sql, {
                    "id": str(uuid4()),
                    "tenant_id": str(self.tenant_id),
                    "module": module,
                    "champ": champ,
                    "valeur": valeur,
                    "valeur_hash": valeur_hash,
                })
                session.commit()

            logger.debug(f"Saved to historique: {module}.{champ} -> {valeur[:30]}...")
        except ImportError:
            logger.warning("Database not available for saving historique")
        except Exception as e:
            logger.warning(f"Could not save to historique: {e}")

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

        # =====================================================================
        # PRIORITÉ 1: Récupérer les suggestions apprises (feedback utilisateur)
        # =====================================================================
        learned_suggestions = await self.get_learned_suggestions(
            module=request.module,
            champ=request.champ,
            prefix=request.valeur,
            limit=request.limite,
            min_acceptance_rate=0.5,
            min_total_count=2,
        )

        # Si on a assez de suggestions apprises de qualité, les utiliser en priorité
        if len(learned_suggestions) >= request.limite:
            latency_ms = int((time.time() - start_time) * 1000)
            return SuggestionResponse(
                suggestions=learned_suggestions[:request.limite],
                meta=SuggestionMeta(
                    cached=False,
                    latency_ms=latency_ms,
                ),
            )

        # =====================================================================
        # PRIORITÉ 2: Récupérer l'historique pour enrichir le contexte
        # =====================================================================
        historique = []
        if config["utiliser_historique"]:
            historique = await self._get_historique(request.module, request.champ)

        # =====================================================================
        # PRIORITÉ 3: Appeler l'IA pour compléter
        # =====================================================================
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

        # =====================================================================
        # Fusionner les suggestions apprises et les suggestions IA
        # =====================================================================
        # Construire la réponse finale
        latency_ms = int((time.time() - start_time) * 1000)

        # Commencer par les suggestions apprises (plus fiables)
        all_suggestions = list(learned_suggestions)
        seen_texts = {s.texte.lower() for s in all_suggestions}

        # Ajouter les suggestions IA (sans doublons)
        for i, s in enumerate(suggestions_text):
            if s.lower() not in seen_texts:
                all_suggestions.append(Suggestion(
                    id=uuid4(),
                    texte=s,
                    score=0.9 - (i * 0.1),  # Score légèrement inférieur aux suggestions apprises
                    source="ia",
                    provider=provider_name,
                ))
                seen_texts.add(s.lower())

        # Limiter au nombre demandé
        final_suggestions = all_suggestions[:request.limite]

        # Mettre en cache les textes
        if final_suggestions:
            cache_texts = [s.texte for s in final_suggestions]
            await self._set_cache(cache_key, cache_texts, config["cache_duree_minutes"])

        return SuggestionResponse(
            suggestions=final_suggestions,
            meta=SuggestionMeta(
                provider=provider_name if suggestions_text else None,
                model=getattr(provider, "model", None) if suggestions_text else None,
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

    async def record_feedback(
        self,
        request: FeedbackRequest,
        module: Optional[str] = None,
        champ: Optional[str] = None,
        suggestion_texte: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """
        Enregistrer un feedback sur une suggestion.

        Args:
            request: Les données du feedback
            module: Nom du module (ex: Clients)
            champ: Nom du champ (ex: nom)
            suggestion_texte: Texte de la suggestion
            user_id: ID de l'utilisateur (optionnel)
        """
        try:
            # Importer Database depuis moteur
            from moteur.db import Database

            # Créer la table si elle n'existe pas
            self._ensure_feedback_table()

            # Préparer les données pour l'insertion
            feedback_data = {
                "suggestion_id": str(request.suggestion_id),
                "accepted": request.accepted,
                "module": module or "",
                "champ": champ or "",
                "suggestion": suggestion_texte or "",
            }

            if request.valeur_finale:
                feedback_data["valeur_finale"] = request.valeur_finale

            if user_id:
                feedback_data["user_id"] = str(user_id)

            # Insérer le feedback
            with Database.get_session() as session:
                insert_sql = text("""
                    INSERT INTO azalplus.autocompletion_feedback
                    (id, tenant_id, suggestion_id, module, champ, suggestion, accepted, user_id, created_at)
                    VALUES (
                        :id,
                        :tenant_id,
                        :suggestion_id,
                        :module,
                        :champ,
                        :suggestion,
                        :accepted,
                        :user_id,
                        NOW()
                    )
                """)
                session.execute(insert_sql, {
                    "id": str(uuid4()),
                    "tenant_id": str(self.tenant_id),
                    "suggestion_id": feedback_data["suggestion_id"],
                    "module": feedback_data["module"],
                    "champ": feedback_data["champ"],
                    "suggestion": feedback_data["suggestion"],
                    "accepted": feedback_data["accepted"],
                    "user_id": feedback_data.get("user_id"),
                })
                session.commit()

            # Mettre à jour les statistiques de suggestions
            if module and champ and suggestion_texte:
                await self._update_suggestion_stats(
                    module=module,
                    champ=champ,
                    suggestion=suggestion_texte,
                    accepted=request.accepted,
                )

            # Ajouter à l'historique si accepté
            if request.accepted and request.valeur_finale and module and champ:
                await self._save_to_historique(module, champ, request.valeur_finale)

            logger.info(
                f"Feedback recorded: suggestion={request.suggestion_id}, "
                f"accepted={request.accepted}, module={module}, champ={champ}"
            )
        except ImportError:
            # Fallback si Database non disponible
            logger.warning("Database not available, feedback not persisted")
            logger.info(
                f"Feedback recorded (memory only): suggestion={request.suggestion_id}, "
                f"accepted={request.accepted}"
            )
        except Exception as e:
            logger.error(f"Error recording feedback: {e}")
            raise

    def _ensure_feedback_table(self) -> None:
        """S'assurer que la table autocompletion_feedback existe."""
        try:
            from moteur.db import Database

            with Database.get_session() as session:
                # Vérifier si la table existe
                check_sql = text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'azalplus'
                        AND table_name = 'autocompletion_feedback'
                    )
                """)
                result = session.execute(check_sql)
                exists = result.scalar()

                if not exists:
                    # Créer la table
                    create_sql = text("""
                        CREATE TABLE IF NOT EXISTS azalplus.autocompletion_feedback (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            tenant_id UUID NOT NULL,
                            suggestion_id TEXT NOT NULL,
                            module TEXT NOT NULL DEFAULT '',
                            champ TEXT NOT NULL DEFAULT '',
                            suggestion TEXT NOT NULL DEFAULT '',
                            accepted BOOLEAN NOT NULL,
                            valeur_finale TEXT,
                            user_id UUID,
                            created_at TIMESTAMP DEFAULT NOW(),
                            CONSTRAINT fk_autocompletion_feedback_tenant
                                FOREIGN KEY (tenant_id) REFERENCES azalplus.tenants(id)
                        )
                    """)
                    session.execute(create_sql)

                    # Créer les index
                    index_sql = text("""
                        CREATE INDEX IF NOT EXISTS ix_autocompletion_feedback_tenant
                            ON azalplus.autocompletion_feedback(tenant_id);
                        CREATE INDEX IF NOT EXISTS ix_autocompletion_feedback_module_champ
                            ON azalplus.autocompletion_feedback(tenant_id, module, champ);
                        CREATE INDEX IF NOT EXISTS ix_autocompletion_feedback_suggestion
                            ON azalplus.autocompletion_feedback(tenant_id, module, champ, suggestion);
                    """)
                    session.execute(index_sql)
                    session.commit()
                    logger.info("Created autocompletion_feedback table")
        except Exception as e:
            logger.warning(f"Could not ensure feedback table: {e}")

    def _ensure_suggestion_stats_table(self) -> None:
        """S'assurer que la table autocompletion_suggestion_stats existe."""
        try:
            from moteur.db import Database

            with Database.get_session() as session:
                # Vérifier si la table existe
                check_sql = text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'azalplus'
                        AND table_name = 'autocompletion_suggestion_stats'
                    )
                """)
                result = session.execute(check_sql)
                exists = result.scalar()

                if not exists:
                    # Créer la table pour les statistiques de suggestions
                    create_sql = text("""
                        CREATE TABLE IF NOT EXISTS azalplus.autocompletion_suggestion_stats (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            tenant_id UUID NOT NULL,
                            module TEXT NOT NULL,
                            champ TEXT NOT NULL,
                            suggestion TEXT NOT NULL,
                            suggestion_hash TEXT NOT NULL,
                            accepted_count INTEGER DEFAULT 0,
                            rejected_count INTEGER DEFAULT 0,
                            total_count INTEGER DEFAULT 0,
                            acceptance_rate NUMERIC(5,4) DEFAULT 0,
                            last_used_at TIMESTAMP DEFAULT NOW(),
                            created_at TIMESTAMP DEFAULT NOW(),
                            CONSTRAINT fk_autocompletion_stats_tenant
                                FOREIGN KEY (tenant_id) REFERENCES azalplus.tenants(id),
                            CONSTRAINT uq_suggestion_stats_unique
                                UNIQUE (tenant_id, module, champ, suggestion_hash)
                        )
                    """)
                    session.execute(create_sql)

                    # Créer les index
                    index_sql = text("""
                        CREATE INDEX IF NOT EXISTS ix_suggestion_stats_tenant_module_champ
                            ON azalplus.autocompletion_suggestion_stats(tenant_id, module, champ);
                        CREATE INDEX IF NOT EXISTS ix_suggestion_stats_acceptance_rate
                            ON azalplus.autocompletion_suggestion_stats(tenant_id, module, champ, acceptance_rate DESC);
                    """)
                    session.execute(index_sql)
                    session.commit()
                    logger.info("Created autocompletion_suggestion_stats table")
        except Exception as e:
            logger.warning(f"Could not ensure suggestion stats table: {e}")

    async def _update_suggestion_stats(
        self,
        module: str,
        champ: str,
        suggestion: str,
        accepted: bool,
    ) -> None:
        """Mettre à jour les statistiques pour une suggestion."""
        try:
            from moteur.db import Database

            self._ensure_suggestion_stats_table()

            suggestion_hash = hashlib.sha256(suggestion.lower().encode()).hexdigest()[:32]

            with Database.get_session() as session:
                # Upsert: insérer ou mettre à jour
                upsert_sql = text("""
                    INSERT INTO azalplus.autocompletion_suggestion_stats
                    (id, tenant_id, module, champ, suggestion, suggestion_hash,
                     accepted_count, rejected_count, total_count, acceptance_rate, last_used_at)
                    VALUES (
                        :id, :tenant_id, :module, :champ, :suggestion, :suggestion_hash,
                        :accepted_count, :rejected_count, 1, :acceptance_rate, NOW()
                    )
                    ON CONFLICT (tenant_id, module, champ, suggestion_hash)
                    DO UPDATE SET
                        accepted_count = autocompletion_suggestion_stats.accepted_count + :accepted_delta,
                        rejected_count = autocompletion_suggestion_stats.rejected_count + :rejected_delta,
                        total_count = autocompletion_suggestion_stats.total_count + 1,
                        acceptance_rate = (autocompletion_suggestion_stats.accepted_count + :accepted_delta)::NUMERIC /
                                         NULLIF(autocompletion_suggestion_stats.total_count + 1, 0),
                        last_used_at = NOW()
                """)

                session.execute(upsert_sql, {
                    "id": str(uuid4()),
                    "tenant_id": str(self.tenant_id),
                    "module": module,
                    "champ": champ,
                    "suggestion": suggestion,
                    "suggestion_hash": suggestion_hash,
                    "accepted_count": 1 if accepted else 0,
                    "rejected_count": 0 if accepted else 1,
                    "acceptance_rate": 1.0 if accepted else 0.0,
                    "accepted_delta": 1 if accepted else 0,
                    "rejected_delta": 0 if accepted else 1,
                })
                session.commit()

            logger.debug(f"Updated suggestion stats: {module}.{champ} -> {suggestion[:30]}...")
        except Exception as e:
            logger.warning(f"Could not update suggestion stats: {e}")

    async def get_learned_suggestions(
        self,
        module: str,
        champ: str,
        prefix: str = "",
        limit: int = 5,
        min_acceptance_rate: float = 0.5,
        min_total_count: int = 2,
    ) -> list[Suggestion]:
        """
        Récupérer les suggestions apprises basées sur le feedback utilisateur.

        Args:
            module: Nom du module (ex: Clients)
            champ: Nom du champ (ex: nom)
            prefix: Préfixe pour filtrer (optionnel)
            limit: Nombre maximum de suggestions
            min_acceptance_rate: Taux d'acceptation minimum (0-1)
            min_total_count: Nombre minimum d'utilisations

        Returns:
            Liste de Suggestions triées par taux d'acceptation et fréquence
        """
        try:
            from moteur.db import Database

            self._ensure_suggestion_stats_table()

            with Database.get_session() as session:
                # Requête pour récupérer les suggestions les plus acceptées
                if prefix:
                    query_sql = text("""
                        SELECT suggestion, accepted_count, total_count, acceptance_rate
                        FROM azalplus.autocompletion_suggestion_stats
                        WHERE tenant_id = :tenant_id
                        AND module = :module
                        AND champ = :champ
                        AND LOWER(suggestion) LIKE :prefix
                        AND acceptance_rate >= :min_rate
                        AND total_count >= :min_count
                        ORDER BY acceptance_rate DESC, accepted_count DESC, total_count DESC
                        LIMIT :limit
                    """)
                    params = {
                        "tenant_id": str(self.tenant_id),
                        "module": module,
                        "champ": champ,
                        "prefix": f"{prefix.lower()}%",
                        "min_rate": min_acceptance_rate,
                        "min_count": min_total_count,
                        "limit": limit,
                    }
                else:
                    query_sql = text("""
                        SELECT suggestion, accepted_count, total_count, acceptance_rate
                        FROM azalplus.autocompletion_suggestion_stats
                        WHERE tenant_id = :tenant_id
                        AND module = :module
                        AND champ = :champ
                        AND acceptance_rate >= :min_rate
                        AND total_count >= :min_count
                        ORDER BY acceptance_rate DESC, accepted_count DESC, total_count DESC
                        LIMIT :limit
                    """)
                    params = {
                        "tenant_id": str(self.tenant_id),
                        "module": module,
                        "champ": champ,
                        "min_rate": min_acceptance_rate,
                        "min_count": min_total_count,
                        "limit": limit,
                    }

                result = session.execute(query_sql, params)
                rows = result.fetchall()

                suggestions = []
                for row in rows:
                    suggestion_text = row[0]
                    acceptance_rate = float(row[3]) if row[3] else 0.0

                    suggestions.append(Suggestion(
                        id=uuid4(),
                        texte=suggestion_text,
                        score=acceptance_rate,
                        source="learned",
                    ))

                logger.debug(
                    f"Retrieved {len(suggestions)} learned suggestions "
                    f"for {module}.{champ} (prefix='{prefix}')"
                )
                return suggestions

        except ImportError:
            logger.warning("Database not available for learned suggestions")
            return []
        except Exception as e:
            logger.warning(f"Could not get learned suggestions: {e}")
            return []

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
