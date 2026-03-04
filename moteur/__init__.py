# =============================================================================
# AZALPLUS - Moteur No-Code
# =============================================================================
"""
AZALPLUS Engine - Le cœur du système No-Code

Ce moteur lit les définitions YAML et génère automatiquement :
- Tables SQL (PostgreSQL)
- API REST (FastAPI)
- Interface utilisateur
- Validations
- Workflows
- Permissions
- Traductions i18n

Tout est centralisé. Tout est automatique.
"""

__version__ = "1.0.0"
__author__ = "AZALPLUS"
__createur__ = "contact@stephane-moreau.fr"

# =============================================================================
# i18n exports
# =============================================================================
from .i18n import (
    I18n,
    t,
    set_language,
    get_language,
    get_available_languages,
    format_date,
    format_currency,
    reload_translations,
    temporary_language,
    get_language_from_request,
    preload_translations,
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
)
