# =============================================================================
# AZALPLUS - Métadonnées module AZALCOFFRE Integration
# =============================================================================
"""
Métadonnées pour l'auto-discovery du module.
"""

MODULE_META = {
    "name": "azalcoffre_integration",
    "version": "1.0.0",
    "description": "Intégration avec AZALCOFFRE (coffre-fort, signatures, PDP)",
    "router_prefix": "/api/coffre",
    "router_tags": ["AZALCOFFRE Integration"],
    "has_public_routes": False,
    "dependencies": ["httpx"],
    "env_vars": [
        "AZALCOFFRE_URL",       # URL de l'API AZALCOFFRE (défaut: https://api.azalcoffre.com)
        "AZALCOFFRE_API_KEY",   # Clé API (format: sk_live_xxx ou sk_sandbox_xxx)
        "AZALCOFFRE_TENANT_ID", # UUID du tenant AZALCOFFRE
    ],
    "features": [
        "archive",      # Archivage coffre-fort (POST /api/v1/documents/upload)
        "signature",    # Signatures électroniques eIDAS (POST /api/v1/signatures/request)
        "pdp",          # Facturation électronique PDP/PPF (POST /api/v1/invoices/*)
        "verify",       # Vérification intégrité documents
        "audit",        # Chaîne d'audit
    ],
    "urls": {
        "production": "https://api.azalcoffre.com",
        "sandbox": "https://sandbox.azalcoffre.com",
    },
    "azalcoffre_endpoints": {
        "documents": "/api/v1/documents",
        "signatures": "/api/v1/signatures",
        "invoices": "/api/v1/invoices",
        "audit": "/api/v1/audit",
        "health": "/health",
    }
}
