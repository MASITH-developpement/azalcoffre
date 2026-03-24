# =============================================================================
# AZALMED - Module principal
# =============================================================================
# Plateforme digitale pour professionnels de santé
# SCRIBE (transcription), CONSENT (signature), VEILLE, ARCHIVE

from .router import router, public_router
from .meta import MODULE_META

__all__ = ["router", "public_router", "MODULE_META"]
