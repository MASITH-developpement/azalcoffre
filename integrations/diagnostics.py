# =============================================================================
# AZALPLUS - Diagnostics et Santé des Intégrations
# =============================================================================
"""
Endpoints de diagnostic pour vérifier l'état des intégrations.

Usage:
    GET /api/diagnostics/config     - Statut configuration
    GET /api/diagnostics/health     - Santé des services
    GET /api/diagnostics/test/{svc} - Test d'une intégration
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from integrations.settings import get_settings, Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@dataclass
class ServiceStatus:
    """Statut d'un service."""
    name: str
    configured: bool
    healthy: bool = False
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Optional[dict] = None


@dataclass
class DiagnosticReport:
    """Rapport de diagnostic complet."""
    timestamp: datetime
    environment: str
    version: str
    services: list[ServiceStatus]
    warnings: list[str]
    errors: list[str]

    @property
    def all_healthy(self) -> bool:
        return all(s.healthy for s in self.services if s.configured)


# =============================================================================
# Vérificateurs de santé
# =============================================================================

async def check_database(settings: Settings) -> ServiceStatus:
    """Vérifier la connexion à la base de données."""
    import time
    try:
        # Import dynamique pour éviter les dépendances circulaires
        from sqlalchemy import create_engine, text

        start = time.time()
        engine = create_engine(settings.database.url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (time.time() - start) * 1000

        return ServiceStatus(
            name="database",
            configured=True,
            healthy=True,
            latency_ms=round(latency, 2)
        )
    except Exception as e:
        return ServiceStatus(
            name="database",
            configured=bool(settings.database.url),
            healthy=False,
            error=str(e)
        )


async def check_redis(settings: Settings) -> ServiceStatus:
    """Vérifier la connexion Redis."""
    import time
    try:
        import redis.asyncio as redis

        start = time.time()
        client = redis.from_url(settings.redis.url)
        await client.ping()
        latency = (time.time() - start) * 1000
        await client.close()

        return ServiceStatus(
            name="redis",
            configured=True,
            healthy=True,
            latency_ms=round(latency, 2)
        )
    except Exception as e:
        return ServiceStatus(
            name="redis",
            configured=bool(settings.redis.url),
            healthy=False,
            error=str(e)
        )


async def check_fintecture(settings: Settings) -> ServiceStatus:
    """Vérifier l'API Fintecture."""
    if not settings.fintecture.is_configured:
        return ServiceStatus(name="fintecture", configured=False)

    import time
    try:
        config = settings.fintecture.to_config()

        start = time.time()
        async with httpx.AsyncClient() as client:
            # Health check endpoint
            response = await client.get(
                f"{config.base_url}/health",
                timeout=5.0
            )
        latency = (time.time() - start) * 1000

        return ServiceStatus(
            name="fintecture",
            configured=True,
            healthy=response.status_code < 500,
            latency_ms=round(latency, 2),
            details={
                "environment": settings.fintecture.environment,
                "status_code": response.status_code
            }
        )
    except Exception as e:
        return ServiceStatus(
            name="fintecture",
            configured=True,
            healthy=False,
            error=str(e)
        )


async def check_swan(settings: Settings) -> ServiceStatus:
    """Vérifier l'API Swan."""
    if not settings.swan.is_configured:
        return ServiceStatus(name="swan", configured=False)

    import time
    try:
        config = settings.swan.to_config()

        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.base_url}/.well-known/openid-configuration",
                timeout=5.0
            )
        latency = (time.time() - start) * 1000

        return ServiceStatus(
            name="swan",
            configured=True,
            healthy=response.status_code == 200,
            latency_ms=round(latency, 2),
            details={
                "environment": settings.swan.environment
            }
        )
    except Exception as e:
        return ServiceStatus(
            name="swan",
            configured=True,
            healthy=False,
            error=str(e)
        )


async def check_twilio(settings: Settings) -> ServiceStatus:
    """Vérifier l'API Twilio."""
    if not settings.twilio.is_configured:
        return ServiceStatus(name="twilio", configured=False)

    import time
    try:
        config = settings.twilio.to_config()

        start = time.time()
        async with httpx.AsyncClient(
            auth=(config.account_sid, config.auth_token)
        ) as client:
            response = await client.get(
                f"{config.base_url}/Messages.json?PageSize=1",
                timeout=5.0
            )
        latency = (time.time() - start) * 1000

        return ServiceStatus(
            name="twilio",
            configured=True,
            healthy=response.status_code == 200,
            latency_ms=round(latency, 2),
            details={
                "whatsapp_enabled": settings.twilio.whatsapp_enabled
            }
        )
    except Exception as e:
        return ServiceStatus(
            name="twilio",
            configured=True,
            healthy=False,
            error=str(e)
        )


async def check_anthropic(settings: Settings) -> ServiceStatus:
    """Vérifier l'API Anthropic."""
    if not settings.ai.anthropic_configured:
        return ServiceStatus(name="anthropic", configured=False)

    import time
    try:
        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": settings.ai.anthropic_api_key,
                    "anthropic-version": "2023-06-01"
                },
                timeout=5.0
            )
        latency = (time.time() - start) * 1000

        return ServiceStatus(
            name="anthropic",
            configured=True,
            healthy=response.status_code in (200, 401),  # 401 = clé invalide mais API OK
            latency_ms=round(latency, 2)
        )
    except Exception as e:
        return ServiceStatus(
            name="anthropic",
            configured=True,
            healthy=False,
            error=str(e)
        )


async def check_smtp(settings: Settings) -> ServiceStatus:
    """Vérifier la connexion SMTP."""
    if not settings.email.smtp_configured:
        return ServiceStatus(name="smtp", configured=False)

    import time
    try:
        import smtplib

        start = time.time()
        if settings.email.use_tls:
            server = smtplib.SMTP(settings.email.smtp_host, settings.email.smtp_port, timeout=5)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.email.smtp_host, settings.email.smtp_port, timeout=5)

        server.login(settings.email.smtp_user, settings.email.smtp_password)
        server.quit()
        latency = (time.time() - start) * 1000

        return ServiceStatus(
            name="smtp",
            configured=True,
            healthy=True,
            latency_ms=round(latency, 2)
        )
    except Exception as e:
        return ServiceStatus(
            name="smtp",
            configured=True,
            healthy=False,
            error=str(e)
        )


# =============================================================================
# Routes API
# =============================================================================

@router.get("/config")
async def get_config_status(settings: Settings = Depends(get_settings)):
    """
    Récupérer le statut de configuration des intégrations.

    Retourne quelles intégrations sont configurées (sans révéler les secrets).
    """
    integrations = settings.get_configured_integrations()
    validation_errors = settings.validate()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.app_env.value,
        "app_url": settings.app_url,
        "integrations": integrations,
        "configured_count": sum(1 for v in integrations.values() if v),
        "total_count": len(integrations),
        "validation_errors": validation_errors,
        "transporteurs": settings.transporteurs.get_configured_carriers(),
        "storage_driver": settings.storage.driver,
        "ai_model": settings.ai.default_model
    }


@router.get("/health")
async def get_health_status(settings: Settings = Depends(get_settings)):
    """
    Vérifier la santé de tous les services.

    Teste la connectivité à chaque service configuré.
    """
    # Lancer les vérifications en parallèle
    checks = await asyncio.gather(
        check_database(settings),
        check_redis(settings),
        check_fintecture(settings),
        check_swan(settings),
        check_twilio(settings),
        check_anthropic(settings),
        check_smtp(settings),
        return_exceptions=True
    )

    services = []
    for check in checks:
        if isinstance(check, Exception):
            services.append(ServiceStatus(
                name="unknown",
                configured=False,
                healthy=False,
                error=str(check)
            ))
        else:
            services.append(check)

    # Construire le rapport
    warnings = settings.validate()
    errors = [s.error for s in services if s.error and s.configured]

    # Calcul santé globale
    configured_services = [s for s in services if s.configured]
    healthy_services = [s for s in configured_services if s.healthy]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.app_env.value,
        "healthy": len(errors) == 0 and len(healthy_services) == len(configured_services),
        "services": [
            {
                "name": s.name,
                "configured": s.configured,
                "healthy": s.healthy,
                "latency_ms": s.latency_ms,
                "error": s.error,
                "details": s.details
            }
            for s in services
        ],
        "summary": {
            "total": len(services),
            "configured": len(configured_services),
            "healthy": len(healthy_services),
            "unhealthy": len(configured_services) - len(healthy_services)
        },
        "warnings": warnings,
        "errors": errors
    }


@router.get("/test/{service}")
async def test_service(service: str, settings: Settings = Depends(get_settings)):
    """
    Tester une intégration spécifique.

    Args:
        service: Nom du service (fintecture, swan, twilio, etc.)
    """
    check_functions = {
        "database": check_database,
        "redis": check_redis,
        "fintecture": check_fintecture,
        "swan": check_swan,
        "twilio": check_twilio,
        "anthropic": check_anthropic,
        "smtp": check_smtp,
    }

    if service not in check_functions:
        raise HTTPException(
            status_code=404,
            detail=f"Service inconnu: {service}. Disponibles: {list(check_functions.keys())}"
        )

    status = await check_functions[service](settings)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "service": service,
        "configured": status.configured,
        "healthy": status.healthy,
        "latency_ms": status.latency_ms,
        "error": status.error,
        "details": status.details
    }


@router.post("/test/send-sms")
async def test_send_sms(
    phone: str,
    message: str = "Test AZALPLUS",
    settings: Settings = Depends(get_settings)
):
    """
    Envoyer un SMS de test.

    Nécessite que Twilio soit configuré.
    """
    if not settings.twilio.is_configured:
        raise HTTPException(status_code=400, detail="Twilio non configuré")

    try:
        from integrations.twilio_sms import TwilioClient

        client = TwilioClient(settings.twilio.to_config())
        msg = await client.send_sms(phone, f"[TEST] {message}")
        await client.close()

        return {
            "success": True,
            "message_sid": msg.sid,
            "status": msg.status.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/env")
async def get_env_info(settings: Settings = Depends(get_settings)):
    """
    Informations sur l'environnement (sans secrets).
    """
    import platform
    import sys

    return {
        "app_name": settings.app_name,
        "environment": settings.app_env.value,
        "debug": settings.app_debug,
        "url": settings.app_url,
        "python_version": sys.version,
        "platform": platform.platform(),
        "storage_driver": settings.storage.driver,
        "log_level": settings.monitoring.log_level
    }


# =============================================================================
# Fonction d'initialisation
# =============================================================================

def setup_diagnostics(app):
    """
    Ajouter les routes de diagnostic à l'application FastAPI.

    Usage:
        from integrations.diagnostics import setup_diagnostics
        setup_diagnostics(app)
    """
    app.include_router(router)

    # Ajouter aussi un endpoint /health simple à la racine
    @app.get("/health")
    async def simple_health():
        return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
