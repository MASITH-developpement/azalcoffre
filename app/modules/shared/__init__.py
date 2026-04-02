# =============================================================================
# AZALPLUS - Modules Partagés
# =============================================================================
"""
Modules partagés entre les différents composants d'AZALPLUS.

RÈGLES DE SÉCURITÉ:
- Les services partagés respectent l'isolation multi-tenant (AZAP-TENANT-001)
- Les connaissances techniques sont globales
- Les données métier sont TOUJOURS tenant-specific
- Guardian n'accède JAMAIS aux données tenant de Marceau
"""

from .knowledge_service import (
    SharedKnowledgeService,
    KnowledgeEntry,
    SearchResult,
    get_system_knowledge,
    get_tenant_knowledge,
)

__all__ = [
    "SharedKnowledgeService",
    "KnowledgeEntry",
    "SearchResult",
    "get_system_knowledge",
    "get_tenant_knowledge",
]
