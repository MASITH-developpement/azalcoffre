# =============================================================================
# AZALPLUS - Module Import/Export Odoo
# =============================================================================
"""
Module d'import/export Odoo avec support:
- CSV/Excel exportés depuis Odoo
- API XML-RPC directe vers Odoo
- Mapping automatique des champs
- Gestion des relations many2one/many2many
"""

from .router import router
from .service import OdooImportService, OdooExportService, OdooAPIClient

__all__ = [
    "router",
    "OdooImportService",
    "OdooExportService",
    "OdooAPIClient",
]
