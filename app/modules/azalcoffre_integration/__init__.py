# =============================================================================
# AZALPLUS - Module d'intégration AZALCOFFRE
# =============================================================================
"""
Intégration avec AZALCOFFRE pour:
- Archivage coffre-fort (NF Z42-013)
- Signatures électroniques (eIDAS)
- Facturation électronique PDP (Factur-X)
"""

from .client import AzalCoffreClient
from .service import AzalCoffreService

__all__ = ["AzalCoffreClient", "AzalCoffreService"]
