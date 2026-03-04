# AZALPLUS - Schemas Autocompletion IA
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------
class IAProvider(str):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class CompletionType(str):
    TEXT = "text"
    EMAIL = "email"
    ADRESSE = "adresse"
    NOM_PERSONNE = "nom_personne"
    NOM_ENTREPRISE = "nom_entreprise"
    TELEPHONE = "telephone"
    REFERENCE = "reference"
    DESCRIPTION = "description"
    CODE_POSTAL = "code_postal"
    VILLE = "ville"
    SIRET = "siret"
    TVA_INTRA = "tva_intra"


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------
class SuggestionRequest(BaseModel):
    """Requête de suggestions d'autocomplétion."""

    module: str = Field(..., description="Nom du module (ex: Clients)")
    champ: str = Field(..., description="Nom du champ (ex: nom)")
    valeur: str = Field(..., description="Valeur actuelle saisie")
    contexte: Optional[dict[str, Any]] = Field(
        default=None, description="Contexte additionnel (autres champs)"
    )
    limite: int = Field(default=5, ge=1, le=10, description="Nombre de suggestions")
    type_completion: Optional[str] = Field(
        default=None, description="Type de complétion forcé"
    )
    provider: Optional[str] = Field(
        default=None, description="Provider forcé (openai, anthropic, local)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "module": "Clients",
                "champ": "nom",
                "valeur": "Dup",
                "limite": 5,
            }
        }


class CompletionRequest(BaseModel):
    """Requête de complétion de texte long."""

    module: str = Field(..., description="Nom du module")
    champ: str = Field(..., description="Nom du champ")
    valeur: str = Field(..., description="Texte à compléter")
    contexte: Optional[dict[str, Any]] = Field(
        default=None, description="Contexte de l'enregistrement"
    )
    max_tokens: int = Field(default=100, ge=10, le=500, description="Tokens max")
    provider: Optional[str] = Field(default=None, description="Provider forcé")

    class Config:
        json_schema_extra = {
            "example": {
                "module": "Interventions",
                "champ": "rapport",
                "valeur": "Intervention réalisée le",
                "max_tokens": 200,
            }
        }


class FeedbackRequest(BaseModel):
    """Feedback sur une suggestion."""

    suggestion_id: UUID = Field(..., description="ID de la suggestion")
    accepted: bool = Field(..., description="Suggestion acceptée ou non")
    valeur_finale: Optional[str] = Field(
        default=None, description="Valeur finalement saisie"
    )


class ConfigUpdateRequest(BaseModel):
    """Mise à jour de la configuration."""

    fournisseur_defaut: Optional[str] = None
    modele_defaut: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    mode: Optional[str] = None
    nombre_suggestions: Optional[int] = Field(default=None, ge=1, le=10)
    temperature: Optional[float] = Field(default=None, ge=0, le=1)
    actif: Optional[bool] = None


# -----------------------------------------------------------------------------
# Response Schemas
# -----------------------------------------------------------------------------
class Suggestion(BaseModel):
    """Une suggestion d'autocomplétion."""

    id: UUID = Field(..., description="ID unique de la suggestion")
    texte: str = Field(..., description="Texte suggéré")
    score: float = Field(default=1.0, description="Score de pertinence (0-1)")
    source: str = Field(..., description="Source (ia, historique, api)")
    provider: Optional[str] = Field(default=None, description="Provider IA utilisé")


class SuggestionMeta(BaseModel):
    """Métadonnées de la réponse."""

    provider: Optional[str] = Field(default=None, description="Provider utilisé")
    model: Optional[str] = Field(default=None, description="Modèle utilisé")
    cached: bool = Field(default=False, description="Résultat depuis le cache")
    latency_ms: int = Field(..., description="Latence en millisecondes")
    tokens_used: Optional[int] = Field(default=None, description="Tokens consommés")


class SuggestionResponse(BaseModel):
    """Réponse avec les suggestions."""

    suggestions: list[Suggestion] = Field(default_factory=list)
    meta: SuggestionMeta


class CompletionResponse(BaseModel):
    """Réponse de complétion de texte."""

    completion: str = Field(..., description="Texte complété")
    meta: SuggestionMeta


class ConfigResponse(BaseModel):
    """Configuration actuelle."""

    actif: bool
    fournisseur_defaut: str
    modele_defaut: str
    mode: str
    nombre_suggestions: int
    temperature: float
    openai_configured: bool
    anthropic_configured: bool
    limite_requetes_jour: int
    limite_tokens_jour: int
    requetes_aujourd_hui: int
    tokens_aujourd_hui: int


class StatsResponse(BaseModel):
    """Statistiques d'utilisation."""

    date: datetime
    requetes_total: int
    tokens_total: int
    cout_estime: float
    cache_hits: int
    cache_misses: int
    latence_moyenne_ms: float
    par_provider: dict[str, dict[str, Any]]
    par_module: dict[str, int]


class HealthResponse(BaseModel):
    """État de santé des providers."""

    openai: dict[str, Any]
    anthropic: dict[str, Any]
    local: dict[str, Any]
    cache: dict[str, Any]
