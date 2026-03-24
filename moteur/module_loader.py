# =============================================================================
# AZALPLUS - Module Loader (Auto-discovery)
# =============================================================================
"""
Chargement automatique des modules Python custom.

Scanne le dossier app/modules/ et enregistre automatiquement:
- Les routers FastAPI (router.py, *_router.py)
- Les WebSocket handlers
- Les services

Structure attendue d'un module:
    app/modules/{nom_module}/
    ├── __init__.py          # Requis
    ├── router.py            # Router principal (optionnel)
    ├── *_router.py          # Routers additionnels (optionnel)
    ├── schemas.py           # Pydantic models (optionnel)
    ├── service.py           # Service principal (optionnel)
    └── meta.py              # Metadata du module (optionnel)

Fichier meta.py (optionnel):
    MODULE_META = {
        "name": "Mon Module",
        "version": "1.0.0",
        "prefix": "/api/mon-module",
        "tags": ["Mon Module"],
        "enabled": True,
        "public_routes": ["/public/*"],
    }
"""

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import APIRouter, FastAPI

logger = structlog.get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================
MODULES_DIR = Path(__file__).parent.parent / "app" / "modules"
MOTEUR_DIR = Path(__file__).parent


# =============================================================================
# Module Metadata
# =============================================================================
class ModuleMeta:
    """Metadata d'un module."""

    def __init__(
        self,
        name: str,
        path: Path,
        version: str = "1.0.0",
        prefix: Optional[str] = None,
        tags: Optional[list[str]] = None,
        enabled: bool = True,
        public_routes: Optional[list[str]] = None,
    ):
        self.name = name
        self.path = path
        self.version = version
        self.prefix = prefix or f"/api/{name.lower().replace('_', '-')}"
        self.tags = tags or [name.replace("_", " ").title()]
        self.enabled = enabled
        self.public_routes = public_routes or []
        self.routers: list[tuple[APIRouter, dict]] = []
        self.websocket_routers: list[tuple[APIRouter, dict]] = []


# =============================================================================
# Module Loader
# =============================================================================
class ModuleLoader:
    """
    Charge automatiquement les modules Python custom.

    Usage:
        loader = ModuleLoader()
        loader.discover()
        loader.register_all(app)
    """

    _instance: Optional["ModuleLoader"] = None
    _modules: dict[str, ModuleMeta] = {}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._modules = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ModuleLoader":
        """Retourne l'instance singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def discover(self) -> dict[str, ModuleMeta]:
        """
        Decouvre tous les modules dans app/modules/.

        Returns:
            Dict des modules decouverts {nom: ModuleMeta}
        """
        if not MODULES_DIR.exists():
            logger.warning("modules_dir_not_found", path=str(MODULES_DIR))
            return {}

        for module_path in MODULES_DIR.iterdir():
            if not module_path.is_dir():
                continue

            # Ignorer les dossiers speciaux
            if module_path.name.startswith("_") or module_path.name.startswith("."):
                continue

            # Verifier qu'il y a un __init__.py
            init_file = module_path / "__init__.py"
            if not init_file.exists():
                continue

            try:
                meta = self._load_module(module_path)
                if meta and meta.enabled:
                    self._modules[meta.name] = meta
                    logger.info(
                        "module_discovered",
                        name=meta.name,
                        prefix=meta.prefix,
                        routers=len(meta.routers)
                    )
            except Exception as e:
                logger.error(
                    "module_load_error",
                    module=module_path.name,
                    error=str(e)
                )

        # Decouvrir aussi les routers du moteur (websocket_manager, etc.)
        self._discover_moteur_routers()

        return self._modules

    def _load_module(self, module_path: Path) -> Optional[ModuleMeta]:
        """Charge un module depuis son dossier."""
        module_name = module_path.name
        python_module_path = f"app.modules.{module_name}"

        # Charger les metadata si presentes
        meta = self._load_meta(module_path, module_name)

        if not meta.enabled:
            logger.debug("module_disabled", name=module_name)
            return None

        # Chercher les routers
        self._find_routers(module_path, python_module_path, meta)

        return meta

    def _load_meta(self, module_path: Path, module_name: str) -> ModuleMeta:
        """Charge les metadata du module."""
        meta_file = module_path / "meta.py"

        default_meta = ModuleMeta(
            name=module_name,
            path=module_path
        )

        if not meta_file.exists():
            return default_meta

        try:
            spec = importlib.util.spec_from_file_location(
                f"app.modules.{module_name}.meta",
                meta_file
            )
            if spec and spec.loader:
                meta_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(meta_module)

                if hasattr(meta_module, "MODULE_META"):
                    data = meta_module.MODULE_META
                    # Support both "prefix" and "router_prefix" keys
                    prefix = data.get("prefix") or data.get("router_prefix")
                    tags = data.get("tags") or data.get("router_tags")
                    return ModuleMeta(
                        name=data.get("name", module_name),
                        path=module_path,
                        version=data.get("version", "1.0.0"),
                        prefix=prefix,
                        tags=tags,
                        enabled=data.get("enabled", True),
                        public_routes=data.get("public_routes"),
                    )
        except Exception as e:
            logger.warning("meta_load_error", module=module_name, error=str(e))

        return default_meta

    def _find_routers(
        self,
        module_path: Path,
        python_module_path: str,
        meta: ModuleMeta
    ) -> None:
        """Trouve et charge les routers d'un module."""
        # Chercher router.py et *_router.py
        router_files = list(module_path.glob("*router*.py"))

        # Ajouter router.py s'il existe
        main_router = module_path / "router.py"
        if main_router.exists() and main_router not in router_files:
            router_files.insert(0, main_router)

        for router_file in router_files:
            if router_file.name.startswith("_"):
                continue

            try:
                # Construire le nom du module Python
                file_module_name = router_file.stem
                full_module_path = f"{python_module_path}.{file_module_name}"

                # Importer le module
                module = importlib.import_module(full_module_path)

                # Chercher les routers (router, public_router, etc.)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, APIRouter):
                        # Determiner le prefix
                        if attr_name == "router":
                            prefix = meta.prefix
                        elif attr_name == "public_router":
                            # Utiliser public_router_prefix si défini dans MODULE_META
                            module_meta = getattr(module, "MODULE_META", {})
                            prefix = module_meta.get("public_router_prefix", meta.prefix.replace("/api", ""))
                        elif "_router" in attr_name:
                            # phone_router -> /api/phone
                            route_name = attr_name.replace("_router", "")
                            prefix = f"/api/{route_name.replace('_', '-')}"
                        else:
                            prefix = meta.prefix

                        # Determiner les tags
                        tags = meta.tags.copy()
                        if attr_name != "router":
                            tag_name = attr_name.replace("_router", "").replace("_", " ").title()
                            tags = [tag_name]

                        # Verifier si c'est un WebSocket router
                        is_websocket = "websocket" in attr_name.lower() or "ws" in attr_name.lower()

                        router_info = {
                            "prefix": prefix,
                            "tags": tags,
                            "source": f"{full_module_path}.{attr_name}"
                        }

                        if is_websocket:
                            meta.websocket_routers.append((attr, router_info))
                        else:
                            meta.routers.append((attr, router_info))

                        logger.debug(
                            "router_found",
                            module=meta.name,
                            router=attr_name,
                            prefix=prefix
                        )

            except Exception as e:
                logger.error(
                    "router_load_error",
                    file=str(router_file),
                    error=str(e)
                )

    def _discover_moteur_routers(self) -> None:
        """Decouvre les routers dans le dossier moteur/."""
        # WebSocket manager
        websocket_manager_path = MOTEUR_DIR / "websocket_manager.py"
        if websocket_manager_path.exists():
            try:
                from moteur.websocket_manager import router as ws_router

                meta = ModuleMeta(
                    name="websocket",
                    path=MOTEUR_DIR,
                    prefix="",  # Pas de prefix, routes definies dans le router
                    tags=["WebSocket"],
                )
                meta.websocket_routers.append((ws_router, {
                    "prefix": "",
                    "tags": ["WebSocket"],
                    "source": "moteur.websocket_manager.router"
                }))
                self._modules["_websocket"] = meta

                logger.debug("moteur_router_found", name="websocket_manager")

            except ImportError as e:
                logger.debug("websocket_manager_not_available", error=str(e))

    def register_all(self, app: FastAPI) -> int:
        """
        Enregistre tous les routers decouverts dans l'app FastAPI.

        Args:
            app: Application FastAPI

        Returns:
            Nombre de routers enregistres
        """
        count = 0

        for module_name, meta in self._modules.items():
            # Routers HTTP
            for router, info in meta.routers:
                try:
                    # Eviter les doublons de prefix
                    prefix = info.get("prefix", "")
                    if hasattr(router, "prefix") and router.prefix:
                        # Le router a deja un prefix defini
                        if prefix and not router.prefix.startswith(prefix):
                            prefix = ""  # Ne pas ajouter de prefix supplementaire

                    app.include_router(
                        router,
                        prefix=prefix if not router.prefix else "",
                        tags=info.get("tags", [])
                    )
                    count += 1

                    logger.info(
                        "router_registered",
                        module=module_name,
                        prefix=prefix or router.prefix,
                        source=info.get("source")
                    )
                except Exception as e:
                    logger.error(
                        "router_register_error",
                        module=module_name,
                        error=str(e)
                    )

            # Routers WebSocket
            for router, info in meta.websocket_routers:
                try:
                    app.include_router(
                        router,
                        tags=info.get("tags", [])
                    )
                    count += 1

                    logger.info(
                        "websocket_router_registered",
                        module=module_name,
                        source=info.get("source")
                    )
                except Exception as e:
                    logger.error(
                        "websocket_register_error",
                        module=module_name,
                        error=str(e)
                    )

        return count

    def get_modules(self) -> dict[str, ModuleMeta]:
        """Retourne les modules charges."""
        return self._modules

    def get_module(self, name: str) -> Optional[ModuleMeta]:
        """Retourne un module par son nom."""
        return self._modules.get(name)

    @classmethod
    def count(cls) -> int:
        """Retourne le nombre de modules charges."""
        instance = cls.get_instance()
        return len(instance._modules)


# =============================================================================
# Convenience functions
# =============================================================================
def discover_and_register(app: FastAPI) -> int:
    """
    Fonction utilitaire pour decouvrir et enregistrer tous les modules.

    Args:
        app: Application FastAPI

    Returns:
        Nombre de routers enregistres
    """
    loader = ModuleLoader.get_instance()
    loader.discover()
    return loader.register_all(app)


def get_loaded_modules() -> dict[str, ModuleMeta]:
    """Retourne les modules charges."""
    loader = ModuleLoader.get_instance()
    return loader.get_modules()
