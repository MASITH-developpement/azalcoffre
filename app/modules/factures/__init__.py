# =============================================================================
# AZALPLUS - Module Factures
# =============================================================================
"""
Module de gestion des factures.

Fonctionnalités :
- Prévisualisation avant envoi (PDF base64)
- Envoi parallèle (email + dématérialisation)
- Archivage légal AZALCOFFRE (NF Z42-013)
- Certificat d'intégrité (SHA-512 + TSA RFC 3161)

Routes :
- POST /api/v1/factures/preview
- POST /api/v1/factures/send
- GET /api/v1/factures/{id}/archive
- GET /api/v1/factures/{id}/archive/certificate
- GET /api/v1/factures/health

Usage :
    from app.modules.factures import router
    app.include_router(router)
"""

from .router import router
from .service import (
    FacturesService,
    PreviewData,
    PreviewLine,
    SendOptions,
    SendResult,
    SendOption,
)
from .schemas import (
    PreviewRequest,
    PreviewResponse,
    SendRequest,
    SendResponse,
    ArchiveInfoResponse,
)
from .meta import MODULE_META

__all__ = [
    # Router
    "router",

    # Service
    "FacturesService",
    "PreviewData",
    "PreviewLine",
    "SendOptions",
    "SendResult",
    "SendOption",

    # Schemas
    "PreviewRequest",
    "PreviewResponse",
    "SendRequest",
    "SendResponse",
    "ArchiveInfoResponse",

    # Meta
    "MODULE_META",
]
