# =============================================================================
# AZALPLUS - Module Debug avec Simon (Assistant QA)
# =============================================================================
"""
Interface de debug sécurisée pour sous-traitants.

Simon (IA) analyse les bugs et propose des tests de vérification.
Aucun accès au code, aucune solution - uniquement des tests.

Composants:
- models.py    : Tables SQLAlchemy (bugs, tests, conversations, audit)
- schemas.py   : Schemas Pydantic pour validation
- prompts.py   : Prompts système pour Simon
- filters.py   : Filtrage des réponses (blocage code)
- simon.py     : Intégration IA (Anthropic API)
- service.py   : Logique métier
- router.py    : API endpoints /api/debug/*
- ui_routes.py : Pages HTML /debug/*
"""

from .router import router as debug_api_router
from .ui_routes import router as debug_ui_router
from .service import DebugService

__all__ = ["debug_api_router", "debug_ui_router", "DebugService"]
