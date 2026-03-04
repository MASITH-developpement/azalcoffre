# AZALPLUS - Module Autocompletion IA
# Autocompletion intelligente avec OpenAI et Anthropic

from .service import AutocompletionIAService
from .router import router
from .schemas import (
    SuggestionRequest,
    SuggestionResponse,
    CompletionRequest,
    CompletionResponse,
    FeedbackRequest,
)
from .providers import OpenAIProvider, AnthropicProvider, LocalProvider

__all__ = [
    "AutocompletionIAService",
    "router",
    "SuggestionRequest",
    "SuggestionResponse",
    "CompletionRequest",
    "CompletionResponse",
    "FeedbackRequest",
    "OpenAIProvider",
    "AnthropicProvider",
    "LocalProvider",
]
