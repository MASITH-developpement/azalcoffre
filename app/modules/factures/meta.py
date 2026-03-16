# =============================================================================
# AZALPLUS - Module Factures - Metadata
# =============================================================================
"""
Metadata pour le module Factures.
Découvert automatiquement par ModuleLoader.
"""

MODULE_META = {
    "name": "factures",
    "version": "1.0.0",
    "description": "Gestion complète des factures : création, prévisualisation, envoi et archivage",
    "router_prefix": "/api/v1/factures",
    "router_tags": ["Factures"],
    "has_public_routes": False,
    "capabilities": [
        "preview",      # Prévisualisation avant envoi
        "send_email",   # Envoi par email
        "send_demat",   # Envoi dématérialisé (PDP/Chorus)
        "archive",      # Archivage légal AZALCOFFRE
    ],
}
