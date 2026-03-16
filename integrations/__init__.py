# =============================================================================
# AZALPLUS - Intégrations API Externes
# =============================================================================
"""
Intégrations avec services tiers pour AZALPLUS:

Services Bancaires:
- Fintecture: Open Banking (paiements instantanés)
- Swan: Banking as a Service (compte bancaire intégré)

Facturation Électronique:
- Factur-X: Génération/parsing PDF/A-3 avec XML embarqué
- Chorus Pro: API PISTE pour facturation B2G (secteur public)
- AZALCOFFRE: Archivage légal NF Z42-013 (10 ans)

Autres:
- Twilio: SMS et téléphonie
- Transporteurs: Colissimo, Chronopost, Mondial Relay, etc.

Infrastructure:
- Calculs: Logique métier automatique
- Diagnostics: Santé des services
- Routes: Endpoints API FastAPI
- Webhooks: Callbacks des services externes
"""

from .fintecture import FintectureClient, FintecturePaymentService
from .swan import SwanClient, SwanBankingService
from .twilio_sms import TwilioClient, NotificationService
from .transporteurs import TransporteurFactory, ExpeditionService
from .webhooks import WebhookHandler, create_webhook_routes
from .calculs import CalculEngine, get_calcul_engine
from .settings import Settings, get_settings, settings
from .diagnostics import setup_diagnostics
from .routes import setup_integration_routes

# Facturation électronique
from .facturx import (
    FacturXGenerator,
    FacturXParser,
    FacturationService,
    DestinationType,
    SendStatus,
    ArchiveInfo,
)
from .chorus_pro import ChorusProClient
from .settings import ChorusProSettings, AzalCoffreSettings

# Archivage légal AZALCOFFRE
from .azalcoffre import (
    AzalCoffreClient,
    ArchiveSync,
    ArchiveResult,
    ArchivedDocument,
    ArchiveStatus,
)

# Alias pour compatibilité
ChorusProConfig = ChorusProSettings
AzalCoffreConfig = AzalCoffreSettings

__all__ = [
    # Clients API
    "FintectureClient",
    "SwanClient",
    "TwilioClient",
    "TransporteurFactory",

    # Services métier
    "FintecturePaymentService",
    "SwanBankingService",
    "NotificationService",
    "ExpeditionService",

    # Facturation électronique
    "FacturXGenerator",
    "FacturXParser",
    "FacturationService",
    "DestinationType",
    "SendStatus",
    "ArchiveInfo",
    "ChorusProClient",
    "ChorusProConfig",  # Alias -> ChorusProSettings
    "ChorusProSettings",

    # Archivage légal AZALCOFFRE
    "AzalCoffreClient",
    "AzalCoffreConfig",  # Alias -> AzalCoffreSettings
    "AzalCoffreSettings",
    "ArchiveSync",
    "ArchiveResult",
    "ArchivedDocument",
    "ArchiveStatus",

    # Infrastructure
    "WebhookHandler",
    "create_webhook_routes",
    "CalculEngine",
    "get_calcul_engine",

    # Configuration
    "Settings",
    "get_settings",
    "settings",
    "setup_diagnostics",

    # Routes FastAPI
    "setup_integration_routes",
    "setup_integrations",
]


def setup_integrations(app):
    """
    Configurer toutes les intégrations sur l'application FastAPI.

    Cette fonction configure:
    - Routes API (/api/paiements, /api/banking, /api/notifications, /api/expeditions)
    - Routes Webhooks (/api/webhooks/*)
    - Routes Diagnostics (/api/diagnostics/*)

    Usage:
        from integrations import setup_integrations
        setup_integrations(app)

    Returns:
        Tuple (routes_count, webhook_handler)
    """
    import logging
    logger = logging.getLogger(__name__)

    # 1. Ajouter les routes d'intégration
    routes_count = setup_integration_routes(app)
    logger.info(f"integration_routes_configured", count=routes_count)

    # 2. Ajouter les routes de diagnostic
    setup_diagnostics(app)

    # 3. Configurer les webhooks (handler pour logique métier)
    webhook_handler = WebhookHandler(db=None)  # DB injectée plus tard

    # Charger les secrets des webhooks
    s = get_settings()
    if s.fintecture.webhook_secret:
        from .webhooks import WebhookSource
        webhook_handler.configure(WebhookSource.FINTECTURE, s.fintecture.webhook_secret)
    if s.swan.webhook_secret:
        from .webhooks import WebhookSource
        webhook_handler.configure(WebhookSource.SWAN, s.swan.webhook_secret)

    logger.info("integrations_fully_configured")

    return routes_count, webhook_handler
