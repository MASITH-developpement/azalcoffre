"""
AZALPLUS - Connecteur AZALCOFFRE
Intégration transparente avec le coffre-fort numérique NF Z42-013

Utilise la configuration centralisée depuis settings.py :
    from integrations.settings import get_settings
    settings = get_settings().azalcoffre
"""

from .client import AzalCoffreClient, AzalCoffreConfig, AzalCoffreError
from .sync import ArchiveSync, ArchiveResult, get_archive_sync, archive_invoice_after_send
from .models import (
    ArchivedDocument,
    ArchiveRequest,
    ArchiveStatus,
    DocumentType,
    IntegrityProof,
)

__all__ = [
    # Client
    "AzalCoffreClient",
    "AzalCoffreConfig",  # Alias -> AzalCoffreSettings
    "AzalCoffreError",
    # Sync
    "ArchiveSync",
    "ArchiveResult",
    "get_archive_sync",
    "archive_invoice_after_send",
    # Models
    "ArchivedDocument",
    "ArchiveRequest",
    "ArchiveStatus",
    "DocumentType",
    "IntegrityProof",
]
