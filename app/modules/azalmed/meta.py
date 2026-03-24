# =============================================================================
# AZALMED - Métadonnées du module
# =============================================================================

MODULE_META = {
    "name": "azalmed",
    "version": "1.0.0",
    "description": "Plateforme digitale pour professionnels de santé",
    "router_prefix": "/api/azalmed",
    "router_tags": ["AZALMED"],
    "has_public_routes": True,
    "public_router_prefix": "/azalmed",
    "public_router_tags": ["AZALMED Public"],
    "requires_tenant": True,
    "modules": ["SCRIBE", "CONSENT", "VEILLE", "ARCHIVE"],
}
