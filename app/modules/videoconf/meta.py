# =============================================================================
# AZALPLUS - Videoconf Module Metadata
# =============================================================================
"""
Metadata for automatic module registration.

This module provides:
- Video conferencing with LiveKit
- Phone calls (WebRTC app + Twilio PSTN)
- Recording, transcription, AI minutes
"""

MODULE_META = {
    "name": "Videoconf",
    "version": "1.0.0",
    "prefix": "/api/videoconf",  # Main prefix for videoconf routes
    "tags": ["Videoconference"],
    "enabled": True,
    "public_routes": [],  # No public routes, all require auth
}
