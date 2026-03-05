# =============================================================================
# AZALPLUS - Icons Manager
# =============================================================================
"""
Gestion centralisée des icônes SVG pour les modules.

Usage:
    - Les modules YAML définissent `icone: nom_icone`
    - Les fichiers SVG sont dans `assets/icons/{nom_icone}.svg`
    - L'API expose `/api/icons/{nom}` pour servir les SVG
"""

from pathlib import Path
from typing import Optional, Dict, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, JSONResponse
import structlog

logger = structlog.get_logger()

# =============================================================================
# Configuration
# =============================================================================
ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"
DEFAULT_ICON = "default"
ICON_CACHE: Dict[str, str] = {}

# =============================================================================
# Router
# =============================================================================
router = APIRouter(tags=["Icons"])


# =============================================================================
# Icon Manager
# =============================================================================
class IconManager:
    """Gestionnaire des icônes SVG."""

    _cache: Dict[str, str] = {}
    _available_icons: List[str] = []

    @classmethod
    def initialize(cls) -> None:
        """Initialise le cache des icônes disponibles."""
        cls._available_icons = []

        if not ICONS_DIR.exists():
            logger.warning("icons_dir_not_found", path=str(ICONS_DIR))
            return

        for svg_file in ICONS_DIR.glob("*.svg"):
            icon_name = svg_file.stem
            cls._available_icons.append(icon_name)

        logger.info("icons_loaded", count=len(cls._available_icons))

    @classmethod
    def get_icon(cls, name: str) -> Optional[str]:
        """
        Récupère le contenu SVG d'une icône.

        Args:
            name: Nom de l'icône (sans extension)

        Returns:
            Contenu SVG ou None si non trouvé
        """
        # Cache hit
        if name in cls._cache:
            return cls._cache[name]

        # Chercher le fichier
        icon_path = ICONS_DIR / f"{name}.svg"

        if not icon_path.exists():
            # Essayer l'icône par défaut
            if name != DEFAULT_ICON:
                return cls.get_icon(DEFAULT_ICON)
            return None

        try:
            content = icon_path.read_text(encoding="utf-8")
            cls._cache[name] = content
            return content
        except Exception as e:
            logger.error("icon_read_error", icon=name, error=str(e))
            return None

    @classmethod
    def get_icon_url(cls, name: str) -> str:
        """Retourne l'URL de l'icône."""
        return f"/api/icons/{name}"

    @classmethod
    def list_icons(cls) -> List[str]:
        """Liste toutes les icônes disponibles."""
        if not cls._available_icons:
            cls.initialize()
        return cls._available_icons

    @classmethod
    def icon_exists(cls, name: str) -> bool:
        """Vérifie si une icône existe."""
        return (ICONS_DIR / f"{name}.svg").exists()

    @classmethod
    def clear_cache(cls) -> None:
        """Vide le cache des icônes."""
        cls._cache.clear()


# =============================================================================
# API Endpoints
# =============================================================================
@router.get("", response_class=JSONResponse)
async def list_icons():
    """Liste toutes les icônes disponibles."""
    icons = IconManager.list_icons()
    return {
        "icons": icons,
        "count": len(icons),
        "base_url": "/api/icons"
    }


@router.get("/{name}", response_class=Response)
async def get_icon(name: str):
    """
    Récupère une icône SVG par son nom.

    Args:
        name: Nom de l'icône (sans .svg)

    Returns:
        Fichier SVG
    """
    # Nettoyer le nom (enlever .svg si présent)
    name = name.replace(".svg", "")

    content = IconManager.get_icon(name)

    if content is None:
        raise HTTPException(status_code=404, detail=f"Icon '{name}' not found")

    return Response(
        content=content,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=86400",  # Cache 24h
            "Content-Disposition": f"inline; filename={name}.svg",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


@router.get("/{name}/data", response_class=JSONResponse)
async def get_icon_data(name: str):
    """
    Récupère les métadonnées d'une icône.

    Args:
        name: Nom de l'icône

    Returns:
        Métadonnées de l'icône (url, exists, svg inline)
    """
    name = name.replace(".svg", "")
    exists = IconManager.icon_exists(name)

    return {
        "name": name,
        "exists": exists,
        "url": IconManager.get_icon_url(name) if exists else IconManager.get_icon_url(DEFAULT_ICON),
        "svg": IconManager.get_icon(name) if exists else None
    }
