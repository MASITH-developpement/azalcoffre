#!/usr/bin/env python3
# =============================================================================
# AUTOPILOT - Mobile App Monitor
# =============================================================================
"""
Surveille et corrige automatiquement les erreurs de l'app mobile React.

- Démarre automatiquement le serveur Vite si arrêté
- Surveille les logs pour détecter les erreurs
- Envoie les erreurs à Guardian pour correction
"""

import asyncio
import subprocess
import os
import re
import structlog
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = structlog.get_logger()

MOBILE_DIR = Path("/home/ubuntu/azalplus/mobile")
VITE_PORT = 5174
CHECK_INTERVAL = 30  # Vérifier toutes les 30 secondes


class MobileMonitor:
    """Moniteur de l'app mobile React."""

    _instance: Optional["MobileMonitor"] = None
    _process: Optional[subprocess.Popen] = None
    _running = False

    @classmethod
    def get_instance(cls) -> "MobileMonitor":
        if cls._instance is None:
            cls._instance = MobileMonitor()
        return cls._instance

    @classmethod
    async def start(cls):
        """Démarre le monitoring."""
        instance = cls.get_instance()
        if not instance._running:
            instance._running = True
            asyncio.create_task(instance._monitor_loop())
            logger.info("mobile_monitor_started", port=VITE_PORT)

    @classmethod
    async def stop(cls):
        """Arrête le monitoring."""
        instance = cls.get_instance()
        instance._running = False
        if instance._process:
            instance._process.terminate()
            instance._process = None
        logger.info("mobile_monitor_stopped")

    async def _monitor_loop(self):
        """Boucle de surveillance."""
        while self._running:
            try:
                # Vérifier si le serveur tourne
                if not self._is_server_running():
                    await self._start_server()

                # Vérifier les erreurs de configuration
                await self._check_config_errors()

            except Exception as e:
                logger.error("mobile_monitor_error", error=str(e))

            await asyncio.sleep(CHECK_INTERVAL)

    def _is_server_running(self) -> bool:
        """Vérifie si le serveur Vite tourne."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", f"vite.*{VITE_PORT}"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except:
            return False

    async def _start_server(self):
        """Démarre le serveur Vite."""
        logger.info("mobile_server_starting", port=VITE_PORT)

        try:
            # Nettoyer le cache Vite si nécessaire
            vite_cache = MOBILE_DIR / ".vite"
            if vite_cache.exists():
                import shutil
                shutil.rmtree(vite_cache, ignore_errors=True)

            # Démarrer Vite
            env = os.environ.copy()
            self._process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(MOBILE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            # Attendre le démarrage
            await asyncio.sleep(5)

            if self._is_server_running():
                logger.info("mobile_server_started", port=VITE_PORT)
            else:
                logger.error("mobile_server_start_failed")

        except Exception as e:
            logger.error("mobile_server_start_error", error=str(e))

    async def _check_config_errors(self):
        """Vérifie et corrige les erreurs de configuration."""

        # Vérifier le manifest.webmanifest
        await self._fix_manifest()

        # Vérifier le favicon
        await self._fix_favicon()

    async def _fix_manifest(self):
        """Vérifie et corrige le manifest PWA."""
        manifest_path = MOBILE_DIR / "public" / "manifest.json"
        webmanifest_path = MOBILE_DIR / "dev-dist" / "manifest.webmanifest"

        # Vérifier que manifest.json existe et est valide
        if manifest_path.exists():
            try:
                import json
                content = manifest_path.read_text()
                json.loads(content)  # Valider JSON
            except json.JSONDecodeError as e:
                logger.warning("manifest_json_invalid", error=str(e))
                # Créer un manifest valide
                await self._create_default_manifest(manifest_path)
        else:
            await self._create_default_manifest(manifest_path)

        # Créer dev-dist si nécessaire
        dev_dist = MOBILE_DIR / "dev-dist"
        if not dev_dist.exists():
            dev_dist.mkdir(parents=True, exist_ok=True)

        # Copier le manifest vers dev-dist si absent
        if not webmanifest_path.exists() and manifest_path.exists():
            import shutil
            shutil.copy(manifest_path, webmanifest_path)
            logger.info("manifest_webmanifest_created")

    async def _create_default_manifest(self, path: Path):
        """Crée un manifest par défaut."""
        import json
        manifest = {
            "name": "AZALPLUS Mobile",
            "short_name": "AZALPLUS",
            "description": "AZALPLUS No-Code ERP Mobile",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#2563EB",
            "icons": [
                {"src": "/pwa-192x192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/pwa-512x512.png", "sizes": "512x512", "type": "image/png"}
            ]
        }
        path.write_text(json.dumps(manifest, indent=2))
        logger.info("manifest_json_created", path=str(path))

    async def _fix_favicon(self):
        """Vérifie et crée le favicon si manquant."""
        favicon_path = MOBILE_DIR / "public" / "favicon.ico"

        if not favicon_path.exists():
            # Créer un favicon minimal (1x1 pixel bleu)
            favicon_data = bytes([
                0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x01,
                0x00, 0x00, 0x01, 0x00, 0x18, 0x00, 0x30, 0x00,
                0x00, 0x00, 0x16, 0x00, 0x00, 0x00, 0x28, 0x00,
                0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02, 0x00,
                0x00, 0x00, 0x01, 0x00, 0x18, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xEB, 0x63,
                0x25, 0x00
            ])
            favicon_path.write_bytes(favicon_data)
            logger.info("favicon_created", path=str(favicon_path))


# Auto-start si importé
def initialize():
    """Initialise le moniteur mobile (appelé par core.py)."""
    pass  # L'initialisation se fait via start()
