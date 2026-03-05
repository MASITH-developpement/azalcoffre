# AZALPLUS - Module Autocompletion IA
# Autocompletion intelligente avec OpenAI et Anthropic

from .service import AutocompletionIAService
from .router import router, public_router as entreprise_public_router
from .schemas import (
    SuggestionRequest,
    SuggestionResponse,
    CompletionRequest,
    CompletionResponse,
    FeedbackRequest,
)
from .providers import OpenAIProvider, AnthropicProvider, LocalProvider
from .meta import MODULE_META

__all__ = [
    "AutocompletionIAService",
    "router",
    "entreprise_public_router",
    "MODULE_META",
    "SuggestionRequest",
    "SuggestionResponse",
    "CompletionRequest",
    "CompletionResponse",
    "FeedbackRequest",
    "OpenAIProvider",
    "AnthropicProvider",
    "LocalProvider",
]
