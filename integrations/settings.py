# =============================================================================
# AZALPLUS - Configuration Centralisée
# =============================================================================
"""
Gestion centralisée de la configuration depuis les variables d'environnement.

Usage:
    from integrations.settings import settings

    # Accès aux paramètres
    print(settings.app_name)
    print(settings.fintecture.app_id)
    print(settings.database_url)

    # Vérifier si une intégration est configurée
    if settings.fintecture.is_configured:
        client = FintectureClient(settings.fintecture.to_config())
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Charger .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# =============================================================================
# Configuration par domaine
# =============================================================================

@dataclass
class DatabaseSettings:
    """Configuration base de données."""
    url: str = ""
    pool_size: int = 10
    max_overflow: int = 20

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        return cls(
            url=os.getenv("DATABASE_URL", "postgresql://localhost/azalplus"),
            pool_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
        )


@dataclass
class RedisSettings:
    """Configuration Redis."""
    url: str = "redis://localhost:6379/0"
    password: Optional[str] = None

    @classmethod
    def from_env(cls) -> "RedisSettings":
        return cls(
            url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            password=os.getenv("REDIS_PASSWORD") or None
        )


@dataclass
class JWTSettings:
    """Configuration JWT."""
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7

    @classmethod
    def from_env(cls) -> "JWTSettings":
        return cls(
            secret_key=os.getenv("JWT_SECRET_KEY", os.getenv("APP_SECRET_KEY", "")),
            algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
            refresh_token_expire_days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        )


@dataclass
class FintectureSettings:
    """Configuration Fintecture (Open Banking)."""
    app_id: str = ""
    app_secret: str = ""
    private_key: str = ""
    webhook_secret: str = ""
    environment: str = "sandbox"
    commission_pct: float = 0.30

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls) -> "FintectureSettings":
        # Gérer la clé privée multi-ligne
        private_key = os.getenv("FINTECTURE_PRIVATE_KEY", "")
        if private_key:
            private_key = private_key.replace("\\n", "\n")

        return cls(
            app_id=os.getenv("FINTECTURE_APP_ID", ""),
            app_secret=os.getenv("FINTECTURE_APP_SECRET", ""),
            private_key=private_key,
            webhook_secret=os.getenv("FINTECTURE_WEBHOOK_SECRET", ""),
            environment=os.getenv("FINTECTURE_ENVIRONMENT", "sandbox"),
            commission_pct=float(os.getenv("FINTECTURE_COMMISSION_PCT", "0.30"))
        )

    def to_config(self):
        """Convertir en FintectureConfig."""
        from integrations.fintecture import FintectureConfig, FintectureEnvironment
        return FintectureConfig(
            app_id=self.app_id,
            app_secret=self.app_secret,
            private_key=self.private_key,
            webhook_secret=self.webhook_secret,
            environment=FintectureEnvironment.PRODUCTION if self.is_production else FintectureEnvironment.SANDBOX
        )


@dataclass
class SwanSettings:
    """Configuration Swan (BaaS)."""
    client_id: str = ""
    client_secret: str = ""
    project_id: str = ""
    webhook_secret: str = ""
    environment: str = "sandbox"
    monthly_fee: float = 9.90
    tap_to_pay_pct: float = 1.20

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.project_id)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls) -> "SwanSettings":
        return cls(
            client_id=os.getenv("SWAN_CLIENT_ID", ""),
            client_secret=os.getenv("SWAN_CLIENT_SECRET", ""),
            project_id=os.getenv("SWAN_PROJECT_ID", ""),
            webhook_secret=os.getenv("SWAN_WEBHOOK_SECRET", ""),
            environment=os.getenv("SWAN_ENVIRONMENT", "sandbox"),
            monthly_fee=float(os.getenv("SWAN_MONTHLY_FEE", "9.90")),
            tap_to_pay_pct=float(os.getenv("SWAN_TAP_TO_PAY_PCT", "1.20"))
        )

    def to_config(self):
        """Convertir en SwanConfig."""
        from integrations.swan import SwanConfig, SwanEnvironment
        return SwanConfig(
            client_id=self.client_id,
            client_secret=self.client_secret,
            project_id=self.project_id,
            webhook_secret=self.webhook_secret,
            environment=SwanEnvironment.PRODUCTION if self.is_production else SwanEnvironment.SANDBOX
        )


@dataclass
class TwilioSettings:
    """Configuration Twilio (SMS/Téléphonie)."""
    account_sid: str = ""
    auth_token: str = ""
    phone_number: str = ""
    whatsapp_number: str = ""
    webhook_url: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.phone_number)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_number)

    @classmethod
    def from_env(cls) -> "TwilioSettings":
        return cls(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            phone_number=os.getenv("TWILIO_PHONE_NUMBER", ""),
            whatsapp_number=os.getenv("TWILIO_WHATSAPP_NUMBER", ""),
            webhook_url=os.getenv("TWILIO_WEBHOOK_URL", "")
        )

    def to_config(self):
        """Convertir en TwilioConfig."""
        from integrations.twilio_sms import TwilioConfig
        return TwilioConfig(
            account_sid=self.account_sid,
            auth_token=self.auth_token,
            phone_number=self.phone_number,
            whatsapp_number=self.whatsapp_number or None,
            webhook_url=self.webhook_url or None
        )


@dataclass
class ColissimoSettings:
    """Configuration Colissimo."""
    contract_number: str = ""
    password: str = ""
    sender_ref: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.contract_number and self.password)

    @classmethod
    def from_env(cls) -> "ColissimoSettings":
        return cls(
            contract_number=os.getenv("COLISSIMO_CONTRACT_NUMBER", ""),
            password=os.getenv("COLISSIMO_PASSWORD", ""),
            sender_ref=os.getenv("COLISSIMO_SENDER_REF", "")
        )

    def to_config(self):
        """Convertir en ColissimoConfig."""
        from integrations.transporteurs import ColissimoConfig
        return ColissimoConfig(
            contract_number=self.contract_number,
            password=self.password,
            sender_parcel_ref=self.sender_ref
        )


@dataclass
class ChronopostSettings:
    """Configuration Chronopost."""
    account_number: str = ""
    password: str = ""
    sub_account: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.account_number and self.password)

    @classmethod
    def from_env(cls) -> "ChronopostSettings":
        return cls(
            account_number=os.getenv("CHRONOPOST_ACCOUNT_NUMBER", ""),
            password=os.getenv("CHRONOPOST_PASSWORD", ""),
            sub_account=os.getenv("CHRONOPOST_SUB_ACCOUNT", "")
        )


@dataclass
class MondialRelaySettings:
    """Configuration Mondial Relay."""
    merchant_id: str = ""
    api_key: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.merchant_id and self.api_key)

    @classmethod
    def from_env(cls) -> "MondialRelaySettings":
        return cls(
            merchant_id=os.getenv("MONDIAL_RELAY_MERCHANT_ID", ""),
            api_key=os.getenv("MONDIAL_RELAY_API_KEY", "")
        )

    def to_config(self):
        """Convertir en MondialRelayConfig."""
        from integrations.transporteurs import MondialRelayConfig
        return MondialRelayConfig(
            merchant_id=self.merchant_id,
            api_key=self.api_key
        )


@dataclass
class TransporteursSettings:
    """Configuration tous transporteurs."""
    colissimo: ColissimoSettings = field(default_factory=ColissimoSettings)
    chronopost: ChronopostSettings = field(default_factory=ChronopostSettings)
    mondial_relay: MondialRelaySettings = field(default_factory=MondialRelaySettings)

    @classmethod
    def from_env(cls) -> "TransporteursSettings":
        return cls(
            colissimo=ColissimoSettings.from_env(),
            chronopost=ChronopostSettings.from_env(),
            mondial_relay=MondialRelaySettings.from_env()
        )

    def get_configured_carriers(self) -> list[str]:
        """Liste des transporteurs configurés."""
        carriers = []
        if self.colissimo.is_configured:
            carriers.append("colissimo")
        if self.chronopost.is_configured:
            carriers.append("chronopost")
        if self.mondial_relay.is_configured:
            carriers.append("mondial_relay")
        return carriers


@dataclass
class AISettings:
    """Configuration IA."""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_org_id: str = ""
    default_model: str = "claude-haiku"
    temperature: float = 0.3
    max_tokens: int = 1000

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @classmethod
    def from_env(cls) -> "AISettings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_org_id=os.getenv("OPENAI_ORG_ID", ""),
            default_model=os.getenv("AI_DEFAULT_MODEL", "claude-haiku"),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("AI_MAX_TOKENS", "1000"))
        )


@dataclass
class EmailSettings:
    """Configuration email."""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = ""
    from_name: str = "AZALPLUS"
    use_tls: bool = True
    sendgrid_api_key: str = ""

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user)

    @property
    def sendgrid_configured(self) -> bool:
        return bool(self.sendgrid_api_key)

    @property
    def is_configured(self) -> bool:
        return self.smtp_configured or self.sendgrid_configured

    @classmethod
    def from_env(cls) -> "EmailSettings":
        return cls(
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            from_email=os.getenv("SMTP_FROM_EMAIL", "noreply@azalplus.fr"),
            from_name=os.getenv("SMTP_FROM_NAME", "AZALPLUS"),
            use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
            sendgrid_api_key=os.getenv("SENDGRID_API_KEY", "")
        )


@dataclass
class StorageSettings:
    """Configuration stockage fichiers."""
    driver: str = "local"  # local | s3 | gcs | azure
    local_path: str = "/var/azalplus/storage"

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "eu-west-3"
    aws_s3_bucket: str = ""

    # Google Cloud Storage
    gcs_project_id: str = ""
    gcs_bucket: str = ""
    gcs_credentials_json: str = ""

    # Azure Blob
    azure_connection_string: str = ""
    azure_container: str = ""

    @property
    def is_cloud(self) -> bool:
        return self.driver in ("s3", "gcs", "azure")

    @classmethod
    def from_env(cls) -> "StorageSettings":
        return cls(
            driver=os.getenv("STORAGE_DRIVER", "local"),
            local_path=os.getenv("STORAGE_LOCAL_PATH", "/var/azalplus/storage"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            aws_region=os.getenv("AWS_REGION", "eu-west-3"),
            aws_s3_bucket=os.getenv("AWS_S3_BUCKET", ""),
            gcs_project_id=os.getenv("GCS_PROJECT_ID", ""),
            gcs_bucket=os.getenv("GCS_BUCKET", ""),
            gcs_credentials_json=os.getenv("GCS_CREDENTIALS_JSON", ""),
            azure_connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING", ""),
            azure_container=os.getenv("AZURE_CONTAINER", "")
        )


@dataclass
class MonitoringSettings:
    """Configuration monitoring."""
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    prometheus_enabled: bool = True
    prometheus_port: int = 9090
    log_level: str = "INFO"
    log_format: str = "json"

    @property
    def sentry_configured(self) -> bool:
        return bool(self.sentry_dsn)

    @classmethod
    def from_env(cls) -> "MonitoringSettings":
        return cls(
            sentry_dsn=os.getenv("SENTRY_DSN", ""),
            sentry_environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
            prometheus_enabled=os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true",
            prometheus_port=int(os.getenv("PROMETHEUS_PORT", "9090")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_format=os.getenv("LOG_FORMAT", "json")
        )


@dataclass
class ChorusProSettings:
    """Configuration Chorus Pro (facturation B2G)."""
    client_id: str = ""
    client_secret: str = ""
    tech_login: str = ""
    tech_password: str = ""
    environment: str = "SANDBOX"  # SANDBOX ou PRODUCTION

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.tech_login)

    @property
    def is_production(self) -> bool:
        return self.environment == "PRODUCTION"

    @classmethod
    def from_env(cls) -> "ChorusProSettings":
        return cls(
            client_id=os.getenv("CHORUS_CLIENT_ID", ""),
            client_secret=os.getenv("CHORUS_CLIENT_SECRET", ""),
            tech_login=os.getenv("CHORUS_TECH_LOGIN", ""),
            tech_password=os.getenv("CHORUS_TECH_PASSWORD", ""),
            environment=os.getenv("CHORUS_ENVIRONMENT", "SANDBOX"),
        )


@dataclass
class AzalCoffreSettings:
    """Configuration AZALCOFFRE (coffre-fort numérique NF Z42-013)."""
    base_url: str = "http://localhost:8001"
    api_key: str = ""
    timeout: int = 30
    verify_ssl: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @classmethod
    def from_env(cls) -> "AzalCoffreSettings":
        return cls(
            base_url=os.getenv("AZALCOFFRE_URL", "http://localhost:8001"),
            api_key=os.getenv("AZALCOFFRE_API_KEY", ""),
            timeout=int(os.getenv("AZALCOFFRE_TIMEOUT", "30")),
            verify_ssl=os.getenv("AZALCOFFRE_VERIFY_SSL", "true").lower() == "true",
        )


# =============================================================================
# Configuration globale
# =============================================================================

@dataclass
class Settings:
    """Configuration globale AZALPLUS."""

    # Application
    app_name: str = "AZALPLUS"
    app_env: Environment = Environment.DEVELOPMENT
    app_debug: bool = True
    app_url: str = "http://localhost:8000"
    app_secret_key: str = ""
    createur_email: str = ""

    # Sous-configurations
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)
    jwt: JWTSettings = field(default_factory=JWTSettings)

    # Intégrations
    fintecture: FintectureSettings = field(default_factory=FintectureSettings)
    swan: SwanSettings = field(default_factory=SwanSettings)
    twilio: TwilioSettings = field(default_factory=TwilioSettings)
    transporteurs: TransporteursSettings = field(default_factory=TransporteursSettings)

    # Facturation électronique
    chorus_pro: ChorusProSettings = field(default_factory=ChorusProSettings)
    azalcoffre: AzalCoffreSettings = field(default_factory=AzalCoffreSettings)

    # Services
    ai: AISettings = field(default_factory=AISettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)

    # Rate limiting
    rate_limit_authenticated: int = 500
    rate_limit_public: int = 100

    # CORS
    cors_origins: list[str] = field(default_factory=list)

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT

    @classmethod
    def from_env(cls) -> "Settings":
        """Charger la configuration depuis les variables d'environnement."""
        env_str = os.getenv("APP_ENV", "development").lower()
        env = Environment.PRODUCTION if env_str == "production" else (
            Environment.STAGING if env_str == "staging" else Environment.DEVELOPMENT
        )

        cors_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")
        cors_origins = [o.strip() for o in cors_str.split(",") if o.strip()]

        return cls(
            app_name=os.getenv("APP_NAME", "AZALPLUS"),
            app_env=env,
            app_debug=os.getenv("APP_DEBUG", "true").lower() == "true",
            app_url=os.getenv("APP_URL", "http://localhost:8000"),
            app_secret_key=os.getenv("APP_SECRET_KEY", ""),
            createur_email=os.getenv("CREATEUR_EMAIL", ""),
            database=DatabaseSettings.from_env(),
            redis=RedisSettings.from_env(),
            jwt=JWTSettings.from_env(),
            fintecture=FintectureSettings.from_env(),
            swan=SwanSettings.from_env(),
            twilio=TwilioSettings.from_env(),
            transporteurs=TransporteursSettings.from_env(),
            chorus_pro=ChorusProSettings.from_env(),
            azalcoffre=AzalCoffreSettings.from_env(),
            ai=AISettings.from_env(),
            email=EmailSettings.from_env(),
            storage=StorageSettings.from_env(),
            monitoring=MonitoringSettings.from_env(),
            rate_limit_authenticated=int(os.getenv("RATE_LIMIT_AUTHENTICATED", "500")),
            rate_limit_public=int(os.getenv("RATE_LIMIT_PUBLIC", "100")),
            cors_origins=cors_origins
        )

    def get_configured_integrations(self) -> dict[str, bool]:
        """Retourner le statut de configuration de chaque intégration."""
        return {
            "fintecture": self.fintecture.is_configured,
            "swan": self.swan.is_configured,
            "twilio": self.twilio.is_configured,
            "colissimo": self.transporteurs.colissimo.is_configured,
            "chronopost": self.transporteurs.chronopost.is_configured,
            "mondial_relay": self.transporteurs.mondial_relay.is_configured,
            "chorus_pro": self.chorus_pro.is_configured,
            "azalcoffre": self.azalcoffre.is_configured,
            "anthropic": self.ai.anthropic_configured,
            "openai": self.ai.openai_configured,
            "email": self.email.is_configured,
            "sentry": self.monitoring.sentry_configured,
        }

    def validate(self) -> list[str]:
        """
        Valider la configuration.

        Returns:
            Liste des erreurs de configuration
        """
        errors = []

        # Clés obligatoires
        if not self.app_secret_key or len(self.app_secret_key) < 32:
            errors.append("APP_SECRET_KEY doit faire au moins 32 caractères")

        if not self.jwt.secret_key or len(self.jwt.secret_key) < 32:
            errors.append("JWT_SECRET_KEY doit faire au moins 32 caractères")

        if not self.database.url:
            errors.append("DATABASE_URL est requis")

        # Warnings en production
        if self.is_production:
            if self.app_debug:
                errors.append("APP_DEBUG doit être false en production")

            if not self.monitoring.sentry_configured:
                errors.append("SENTRY_DSN recommandé en production")

            if self.storage.driver == "local":
                errors.append("Stockage cloud recommandé en production")

        return errors


# =============================================================================
# Singleton
# =============================================================================

@lru_cache()
def get_settings() -> Settings:
    """
    Récupérer l'instance unique des settings.

    Usage:
        from integrations.settings import get_settings
        settings = get_settings()
    """
    return Settings.from_env()


# Alias pour import direct
settings = get_settings()
