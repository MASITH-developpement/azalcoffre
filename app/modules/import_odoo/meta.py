# =============================================================================
# AZALPLUS - Import/Export Odoo - Metadata
# =============================================================================
"""
Metadata pour le module Import/Export Odoo.
"""

MODULE_META = {
    "name": "import_odoo",
    "display_name": "Import/Export Odoo",
    "description": "Synchronisation bidirectionnelle avec Odoo (CSV + API XML-RPC)",
    "version": "1.0.0",
    "router_prefix": "/api/odoo",
    "router_tags": ["Import/Export Odoo"],
    "has_public_routes": False,
    "icon": "refresh-cw",
    "menu": "Systeme",
    "features": [
        "Import CSV depuis Odoo",
        "Import API XML-RPC",
        "Export vers format Odoo",
        "Mapping automatique des champs",
        "Support multi-modèles"
    ],
    "supported_odoo_models": [
        "res.partner",
        "product.product",
        "product.template",
        "sale.order",
        "purchase.order",
        "account.move",
        "stock.picking",
        "hr.employee",
        "project.project",
        "project.task",
        "crm.lead",
    ],
    "dependencies": [],
}
