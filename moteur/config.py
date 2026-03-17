# =============================================================================
# AZALPLUS - Configuration
# =============================================================================
"""
Configuration centralisée. Toutes les variables d'environnement sont ici.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os

class Settings(BaseSettings):
    """Configuration AZALPLUS."""

    # =========================================================================
    # Environnement
    # =========================================================================
    AZALPLUS_ENV: str = Field(default="development", description="Environnement")
    DEBUG: bool = Field(default=False)

    # =========================================================================
    # Base de données
    # =========================================================================
    DATABASE_URL: str = Field(
        default="postgresql://azalplus:azalplus@localhost:5432/azalplus"
    )
    DB_POOL_SIZE: int = Field(default=5)
    DB_MAX_OVERFLOW: int = Field(default=10)

    # =========================================================================
    # Redis
    # =========================================================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # =========================================================================
    # Sécurité
    # =========================================================================
    SECRET_KEY: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_minimum_32_characters",
        min_length=32
    )
    ENCRYPTION_KEY: str = Field(default="")

    # JWT
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRE_MINUTES: int = Field(default=60 * 24)  # 24 heures
    JWT_REFRESH_EXPIRE_DAYS: int = Field(default=7)

    # =========================================================================
    # CORS (configurable via env var, séparés par virgule)
    # Exemple: CORS_ORIGINS=https://app.example.com,https://admin.example.com
    # =========================================================================
    CORS_ORIGINS: List[str] = Field(default=[
        "http://localhost:3000",
        "http://localhost:5174",
        "http://localhost:8888",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8888",
    ])

    # =========================================================================
    # Créateur (obligatoire en production)
    # =========================================================================
    CREATEUR_EMAIL: str = Field(
        default="",
        description="Email du créateur - accès total à Guardian"
    )

    # =========================================================================
    # Email
    # =========================================================================
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM: str = Field(default="AZALPLUS <noreply@azalplus.com>")

    # =========================================================================
    # IA
    # =========================================================================
    OPENAI_API_KEY: str = Field(default="")
    ANTHROPIC_API_KEY: str = Field(default="")
    ELEVENLABS_API_KEY: str = Field(default="")

    # LLM par défaut
    DEFAULT_LLM: str = Field(default="claude")  # claude | openai

    # =========================================================================
    # Stockage
    # =========================================================================
    UPLOAD_DIR: str = Field(default="/app/data/uploads")
    MAX_UPLOAD_SIZE_MB: int = Field(default=50)

    # =========================================================================
    # Rate Limiting
    # =========================================================================
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(default=5)

    # Rate limiting detaille
    RATE_LIMIT_AUTHENTICATED: int = Field(
        default=100,
        description="Requetes/minute pour utilisateurs authentifies"
    )
    RATE_LIMIT_UNAUTHENTICATED: int = Field(
        default=20,
        description="Requetes/minute pour utilisateurs non authentifies"
    )
    RATE_LIMIT_INTERNAL: int = Field(
        default=1000,
        description="Requetes/minute pour services internes"
    )
    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        description="Fenetre de temps en secondes"
    )
    RATE_LIMIT_PREMIUM_MULTIPLIER: float = Field(
        default=3.0,
        description="Multiplicateur pour tenants premium"
    )

    # =========================================================================
    # Guardian
    # =========================================================================
    GUARDIAN_LOG_LEVEL: str = Field(default="INFO")
    GUARDIAN_AUTO_BLOCK: bool = Field(default=True)
    GUARDIAN_ALERT_EMAIL: str = Field(default="")

    # =========================================================================
    # Modules
    # =========================================================================
    MODULES_DIR: str = Field(default="modules")
    CONFIG_DIR: str = Field(default="config")

    # =========================================================================
    # Firebase (Push Notifications)
    # =========================================================================
    FIREBASE_CREDENTIALS_PATH: str = Field(
        default="",
        description="Chemin vers le fichier JSON des credentials Firebase"
    )
    FIREBASE_PROJECT_ID: str = Field(default="")
    FIREBASE_VAPID_KEY: str = Field(
        default="",
        description="Cle VAPID publique pour les notifications web push"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

# Instance globale
settings = Settings()

# =============================================================================
# Validation au démarrage
# =============================================================================
def validate_settings():
    """Valide la configuration au démarrage."""
    errors = []

    if settings.AZALPLUS_ENV == "production":
        if settings.SECRET_KEY == "CHANGE_ME_IN_PRODUCTION_minimum_32_characters":
            errors.append("SECRET_KEY doit être changé en production")

        if not settings.ENCRYPTION_KEY:
            errors.append("ENCRYPTION_KEY est obligatoire en production")

        if not settings.CREATEUR_EMAIL:
            errors.append("CREATEUR_EMAIL est obligatoire en production")

    if errors:
        raise ValueError(f"Configuration invalide: {', '.join(errors)}")

# Valider au chargement du module
if settings.AZALPLUS_ENV == "production":
    validate_settings()
