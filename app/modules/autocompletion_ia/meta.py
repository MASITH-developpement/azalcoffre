# AZALPLUS - Module Autocompletion IA - Metadata
"""
Module metadata for autocompletion_ia.
Provides intelligent autocompletion with OpenAI, Anthropic Claude, and local providers.
Includes public endpoints for entreprise lookup (SIRET/SIREN) via gov.fr API.
"""

MODULE_META = {
    "name": "autocompletion_ia",
    "display_name": "Autocompletion IA",
    "description": "Autocompletion intelligente avec IA (OpenAI, Claude) et recherche entreprise (SIRET/SIREN)",
    "version": "1.0.0",
    "category": "core",
    "icon": "sparkles",
    "menu": "Paramètres",

    # Router configuration
    "router_prefix": "/api/autocompletion-ia",
    "router_tags": ["Autocompletion IA"],

    # Public router for entreprise lookup (no auth required)
    "public_router_prefix": "/api/autocompletion-ia",
    "public_router_tags": ["Recherche Entreprise"],
    "has_public_routes": True,

    # Dependencies
    "dependencies": [],
    "optional_dependencies": ["openai", "anthropic"],

    # Features
    "features": [
        "suggestions",           # Suggestions d'autocompletion
        "text_completion",       # Completion de texte long
        "feedback_learning",     # Apprentissage via feedback
        "entreprise_lookup",     # Recherche SIRET/SIREN (API gov.fr)
        "address_lookup",        # Recherche adresse (API adresse gov.fr)
        "product_lookup",        # Recherche produit (OpenFoodFacts)
        "vat_validation",        # Validation TVA (VIES)
        "iban_validation",       # Validation IBAN
        "smart_lookup",          # Detection automatique du type et lookup
    ],

    # Providers supported
    "providers": {
        "openai": {
            "name": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "requires_api_key": True,
            "env_var": "OPENAI_API_KEY",
        },
        "anthropic": {
            "name": "Anthropic Claude",
            "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
            "requires_api_key": True,
            "env_var": "ANTHROPIC_API_KEY",
        },
        "local": {
            "name": "Local Provider",
            "models": [],
            "requires_api_key": False,
            "description": "Fallback provider using local data and patterns",
        },
    },

    # External APIs used
    "external_apis": {
        "recherche_entreprises": {
            "name": "API Recherche Entreprises",
            "url": "https://recherche-entreprises.api.gouv.fr",
            "auth_required": False,
            "description": "API gouvernementale pour recherche SIRET/SIREN",
        },
        "api_adresse": {
            "name": "API Adresse",
            "url": "https://api-adresse.data.gouv.fr",
            "auth_required": False,
            "description": "API gouvernementale pour autocompletion adresse",
        },
        "openfoodfacts": {
            "name": "Open Food Facts",
            "url": "https://world.openfoodfacts.org/api/v2",
            "auth_required": False,
            "description": "Base de donnees produits alimentaires",
        },
        "vies": {
            "name": "VIES VAT Validation",
            "url": "https://ec.europa.eu/taxation_customs/vies",
            "auth_required": False,
            "description": "Validation TVA intracommunautaire",
        },
    },

    # Settings
    "settings": {
        "default_provider": "anthropic",
        "cache_ttl_seconds": 3600,
        "max_suggestions": 10,
        "default_suggestions": 5,
    },

    # Maintenance status
    "status": "ACTIF",
    "maintainer": "AZALPLUS Team",
    "certification": "CERT-B",
}
