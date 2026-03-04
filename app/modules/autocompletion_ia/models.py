# AZALPLUS - Models Autocompletion IA
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship

# Importer la base selon votre configuration
# from app.core.database import Base
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AutocompletionConfig(Base):
    """Configuration de l'autocomplétion IA par tenant."""

    __tablename__ = "autocompletion_config"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)

    # Activation
    actif = Column(Boolean, default=True, nullable=False)

    # Provider par défaut
    fournisseur_defaut = Column(String(50), default="anthropic", nullable=False)
    modele_defaut = Column(String(100), default="claude-sonnet-4-20250514", nullable=False)

    # Clés API (chiffrées)
    openai_api_key_encrypted = Column(Text, nullable=True)
    anthropic_api_key_encrypted = Column(Text, nullable=True)

    # Mode de fonctionnement
    mode = Column(String(20), default="suggestions", nullable=False)  # suggestions, completion, hybrid

    # Paramètres
    nombre_suggestions = Column(Integer, default=5, nullable=False)
    delai_declenchement_ms = Column(Integer, default=300, nullable=False)
    longueur_min = Column(Integer, default=2, nullable=False)
    temperature = Column(Float, default=0.3, nullable=False)

    # Contexte
    utiliser_contexte_module = Column(Boolean, default=True, nullable=False)
    utiliser_historique = Column(Boolean, default=True, nullable=False)

    # Cache
    cache_actif = Column(Boolean, default=True, nullable=False)
    cache_duree_minutes = Column(Integer, default=60, nullable=False)

    # Limites
    limite_requetes_jour = Column(Integer, default=1000, nullable=False)
    limite_tokens_jour = Column(Integer, default=100000, nullable=False)

    # Fallback
    fallback_fournisseur = Column(String(50), default="local", nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_autocompletion_config_tenant", "tenant_id"),
    )


class AutocompletionRegle(Base):
    """Règles d'autocomplétion par champ."""

    __tablename__ = "autocompletion_regles"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)

    # Cible
    module = Column(String(100), nullable=False)
    champ = Column(String(100), nullable=False)

    # Type de complétion
    type_completion = Column(String(50), default="text", nullable=False)

    # Override provider
    fournisseur = Column(String(50), nullable=True)  # null = utiliser défaut
    modele = Column(String(100), nullable=True)

    # Prompts personnalisés
    prompt_systeme = Column(Text, nullable=True)
    prompt_utilisateur = Column(Text, nullable=True)
    contexte_supplementaire = Column(Text, nullable=True)

    # Sources de suggestions
    sources_suggestions = Column(JSONB, default=["ia", "historique"], nullable=False)

    # Configuration
    priorite = Column(Integer, default=0, nullable=False)
    conditions = Column(JSONB, nullable=True)
    actif = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_autocompletion_regles_tenant_module", "tenant_id", "module"),
        Index("ix_autocompletion_regles_tenant_module_champ", "tenant_id", "module", "champ"),
    )


class AutocompletionHistorique(Base):
    """Historique des valeurs saisies pour améliorer les suggestions."""

    __tablename__ = "autocompletion_historique"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)

    # Cible
    module = Column(String(100), nullable=False)
    champ = Column(String(100), nullable=False)

    # Valeur
    valeur = Column(Text, nullable=False)
    valeur_hash = Column(String(64), nullable=False)  # Pour déduplication

    # Statistiques
    frequence = Column(Integer, default=1, nullable=False)
    derniere_utilisation = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Contexte
    user_id = Column(PGUUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_autocompletion_hist_tenant_module_champ", "tenant_id", "module", "champ"),
        Index("ix_autocompletion_hist_hash", "tenant_id", "module", "champ", "valeur_hash", unique=True),
    )


class AutocompletionStats(Base):
    """Statistiques d'utilisation journalières."""

    __tablename__ = "autocompletion_stats"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    date = Column(Date, nullable=False)

    # Provider
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=True)

    # Compteurs
    requetes_total = Column(Integer, default=0, nullable=False)
    tokens_input = Column(Integer, default=0, nullable=False)
    tokens_output = Column(Integer, default=0, nullable=False)

    # Performance
    latence_total_ms = Column(Integer, default=0, nullable=False)
    erreurs = Column(Integer, default=0, nullable=False)

    # Cache
    cache_hits = Column(Integer, default=0, nullable=False)
    cache_misses = Column(Integer, default=0, nullable=False)

    # Feedback
    suggestions_acceptees = Column(Integer, default=0, nullable=False)
    suggestions_rejetees = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_autocompletion_stats_tenant_date", "tenant_id", "date"),
        Index("ix_autocompletion_stats_unique", "tenant_id", "date", "provider", unique=True),
    )


class AutocompletionFeedback(Base):
    """Feedback sur les suggestions pour amélioration continue."""

    __tablename__ = "autocompletion_feedback"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)

    # Contexte
    module = Column(String(100), nullable=False)
    champ = Column(String(100), nullable=False)
    valeur_saisie = Column(Text, nullable=False)

    # Suggestion
    suggestion_id = Column(PGUUID(as_uuid=True), nullable=False)
    suggestion_texte = Column(Text, nullable=False)
    suggestion_source = Column(String(50), nullable=False)
    suggestion_provider = Column(String(50), nullable=True)

    # Feedback
    accepted = Column(Boolean, nullable=False)
    valeur_finale = Column(Text, nullable=True)

    # Métadonnées
    user_id = Column(PGUUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_autocompletion_feedback_tenant", "tenant_id"),
        Index("ix_autocompletion_feedback_module_champ", "tenant_id", "module", "champ"),
    )
