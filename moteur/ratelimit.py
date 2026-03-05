# =============================================================================
# AZALPLUS - Rate Limiting
# =============================================================================
"""
Rate limiting distribue avec Redis et fallback in-memory.
Protection contre les abus et les attaques DDoS.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple
from uuid import UUID

import structlog
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from .config import settings
from .db import Database

logger = structlog.get_logger()


# =============================================================================
# Configuration des limites
# =============================================================================
@dataclass
class RateLimitConfig:
    """Configuration des limites de requetes."""

    # Limites par defaut (requetes par minute)
    # Ces valeurs sont surchargees par settings si disponibles
    DEFAULT_AUTHENTICATED: int = 100
    DEFAULT_UNAUTHENTICATED: int = 20
    DEFAULT_INTERNAL: int = 1000

    # Limites premium (multiplicateur)
    PREMIUM_MULTIPLIER: float = 3.0

    # Fenetre en secondes
    WINDOW_SECONDS: int = 60

    @classmethod
    def get_authenticated_limit(cls) -> int:
        """Retourne la limite pour utilisateurs authentifies."""
        return getattr(settings, "RATE_LIMIT_AUTHENTICATED", cls.DEFAULT_AUTHENTICATED)

    @classmethod
    def get_unauthenticated_limit(cls) -> int:
        """Retourne la limite pour utilisateurs non authentifies."""
        return getattr(settings, "RATE_LIMIT_UNAUTHENTICATED", cls.DEFAULT_UNAUTHENTICATED)

    @classmethod
    def get_internal_limit(cls) -> int:
        """Retourne la limite pour services internes."""
        return getattr(settings, "RATE_LIMIT_INTERNAL", cls.DEFAULT_INTERNAL)

    @classmethod
    def get_window_seconds(cls) -> int:
        """Retourne la fenetre de temps."""
        return getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", cls.WINDOW_SECONDS)

    @classmethod
    def get_premium_multiplier(cls) -> float:
        """Retourne le multiplicateur premium."""
        return getattr(settings, "RATE_LIMIT_PREMIUM_MULTIPLIER", cls.PREMIUM_MULTIPLIER)


# =============================================================================
# RateLimiter Class
# =============================================================================
class RateLimiter:
    """
    Gestionnaire de rate limiting avec Redis et fallback in-memory.

    Utilise l'algorithme Sliding Window Counter pour un controle precis.
    """

    # Cache in-memory pour fallback
    _memory_cache: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
    _memory_lock = asyncio.Lock()

    @classmethod
    async def check_limit(
        cls,
        key: str,
        limit: int,
        window: int = 60
    ) -> Tuple[bool, int, int, int]:
        """
        Verifie si la limite est atteinte.

        Args:
            key: Cle unique (ex: "ratelimit:user:123" ou "ratelimit:ip:192.168.1.1")
            limit: Nombre maximum de requetes autorisees
            window: Fenetre de temps en secondes

        Returns:
            Tuple[allowed, remaining, limit, reset_timestamp]
        """
        try:
            return await cls._check_redis(key, limit, window)
        except Exception as e:
            logger.warning("ratelimit_redis_fallback", error=str(e))
            return await cls._check_memory(key, limit, window)

    @classmethod
    async def _check_redis(
        cls,
        key: str,
        limit: int,
        window: int
    ) -> Tuple[bool, int, int, int]:
        """Verification avec Redis (Sliding Window)."""
        redis = Database.get_redis()
        if not redis:
            raise Exception("Redis not connected")

        now = time.time()
        window_start = now - window

        # Cle Redis pour ce rate limit
        redis_key = f"azalplus:ratelimit:{key}"

        # Pipeline pour operations atomiques
        pipe = redis.pipeline()

        # 1. Supprimer les anciennes entrees hors fenetre
        pipe.zremrangebyscore(redis_key, 0, window_start)

        # 2. Compter les requetes dans la fenetre
        pipe.zcard(redis_key)

        # 3. Ajouter la requete courante
        pipe.zadd(redis_key, {str(now): now})

        # 4. Definir TTL pour auto-nettoyage
        pipe.expire(redis_key, window + 10)

        results = await pipe.execute()

        current_count = results[1]  # Resultat de zcard

        # Calculer les valeurs de reponse
        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1)
        reset_time = int(now) + window

        if not allowed:
            # Retirer la requete qu'on vient d'ajouter car elle est refusee
            await redis.zrem(redis_key, str(now))
            remaining = 0

            logger.warning(
                "ratelimit_exceeded",
                key=key,
                count=current_count,
                limit=limit
            )

        return (allowed, remaining, limit, reset_time)

    @classmethod
    async def _check_memory(
        cls,
        key: str,
        limit: int,
        window: int
    ) -> Tuple[bool, int, int, int]:
        """Verification in-memory (fallback)."""
        now = time.time()

        async with cls._memory_lock:
            count, window_start = cls._memory_cache[key]

            # Si la fenetre a expire, reinitialiser
            if now - window_start > window:
                count = 0
                window_start = now

            # Verifier la limite
            allowed = count < limit

            if allowed:
                cls._memory_cache[key] = (count + 1, window_start)

            remaining = max(0, limit - count - 1) if allowed else 0
            reset_time = int(window_start) + window

            return (allowed, remaining, limit, reset_time)

    @classmethod
    async def reset_limit(cls, key: str) -> bool:
        """Reinitialise le compteur pour une cle."""
        try:
            redis = Database.get_redis()
            if redis:
                await redis.delete(f"azalplus:ratelimit:{key}")

            async with cls._memory_lock:
                if key in cls._memory_cache:
                    del cls._memory_cache[key]

            return True
        except Exception as e:
            logger.error("ratelimit_reset_error", key=key, error=str(e))
            return False

    @classmethod
    async def get_tenant_limit(cls, tenant_id: UUID) -> int:
        """
        Recupere la limite personnalisee pour un tenant.
        Les tenants premium ont des limites plus elevees.
        """
        try:
            redis = Database.get_redis()
            if redis:
                # Verifier le cache Redis d'abord
                cached = await redis.get(f"azalplus:tenant_limit:{tenant_id}")
                if cached:
                    return int(cached)

            # Charger depuis la base de donnees
            from .db import Database
            with Database.get_session() as session:
                from sqlalchemy import text
                result = session.execute(
                    text("""
                        SELECT settings->>'rate_limit' as rate_limit,
                               settings->>'plan' as plan
                        FROM azalplus.tenants
                        WHERE id = :tenant_id AND actif = true
                    """),
                    {"tenant_id": str(tenant_id)}
                )
                row = result.fetchone()

                if row:
                    row_dict = dict(row._mapping)

                    # Limite personnalisee
                    if row_dict.get("rate_limit"):
                        limit = int(row_dict["rate_limit"])
                    else:
                        # Limite basee sur le plan
                        plan = row_dict.get("plan", "standard")
                        if plan in ("premium", "enterprise"):
                            limit = int(
                                RateLimitConfig.get_authenticated_limit()
                                * RateLimitConfig.get_premium_multiplier()
                            )
                        else:
                            limit = RateLimitConfig.get_authenticated_limit()

                    # Mettre en cache
                    if redis:
                        await redis.setex(
                            f"azalplus:tenant_limit:{tenant_id}",
                            300,  # 5 minutes TTL
                            str(limit)
                        )

                    return limit

            return RateLimitConfig.get_authenticated_limit()

        except Exception as e:
            logger.error("get_tenant_limit_error", tenant_id=str(tenant_id), error=str(e))
            return RateLimitConfig.get_authenticated_limit()


# =============================================================================
# Routes exemptees
# =============================================================================
EXEMPT_ROUTES = [
    "/health",
    "/static",
    "/assets",
    "/favicon.ico",
]


def is_route_exempt(path: str) -> bool:
    """Verifie si une route est exemptee du rate limiting."""
    for route in EXEMPT_ROUTES:
        if route == path or path.startswith(route + "/") or path.startswith(route):
            return True
    return False


# =============================================================================
# Middleware Rate Limiting
# =============================================================================
class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware de rate limiting.

    Limites:
    - 100 req/min pour utilisateurs authentifies
    - 20 req/min pour utilisateurs non authentifies
    - 1000 req/min pour services internes
    - Limites configurables par tenant
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Intercepte chaque requete pour appliquer le rate limiting."""

        # Laisser passer les requêtes OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Routes exemptees
        if is_route_exempt(request.url.path):
            return await call_next(request)

        # Determiner la cle et la limite
        key, limit = await self._get_rate_limit_key(request)

        # Verifier la limite
        allowed, remaining, limit_value, reset_time = await RateLimiter.check_limit(
            key=key,
            limit=limit,
            window=RateLimitConfig.get_window_seconds()
        )

        if not allowed:
            # Log usage excessif
            logger.warning(
                "rate_limit_exceeded",
                key=key,
                path=request.url.path,
                client_ip=self._get_client_ip(request),
                user_id=self._get_user_id(request)
            )

            # Retourner 429 Too Many Requests
            retry_after = reset_time - int(time.time())
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Trop de requetes. Veuillez patienter.",
                    "retry_after": max(1, retry_after)
                },
                headers={
                    "X-RateLimit-Limit": str(limit_value),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(max(1, retry_after))
                }
            )

        # Continuer avec la requete
        response = await call_next(request)

        # Ajouter les headers de rate limit
        response.headers["X-RateLimit-Limit"] = str(limit_value)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response

    async def _get_rate_limit_key(self, request: Request) -> Tuple[str, int]:
        """
        Determine la cle de rate limit et la limite applicable.

        Returns:
            Tuple[key, limit]
        """
        # Verifier si c'est un service interne
        internal_header = request.headers.get("X-Internal-Service")
        if internal_header == settings.SECRET_KEY[:16]:  # Token partiel pour verification
            ip = self._get_client_ip(request)
            return (f"internal:{ip}", RateLimitConfig.get_internal_limit())

        # Verifier si utilisateur authentifie
        user = getattr(request.state, "user", None)

        if user:
            user_id = user.get("id")
            tenant_id = user.get("tenant_id")

            # Recuperer la limite du tenant
            if tenant_id:
                try:
                    limit = await RateLimiter.get_tenant_limit(UUID(str(tenant_id)))
                except:
                    limit = RateLimitConfig.get_authenticated_limit()
            else:
                limit = RateLimitConfig.get_authenticated_limit()

            return (f"user:{user_id}", limit)

        # Utilisateur non authentifie - utiliser l'IP
        ip = self._get_client_ip(request)
        return (f"ip:{ip}", RateLimitConfig.get_unauthenticated_limit())

    def _get_client_ip(self, request: Request) -> str:
        """Recupere l'IP du client (avec support proxy)."""
        # Verifier les headers de proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Prendre la premiere IP (client original)
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # IP directe
        if request.client:
            return request.client.host

        return "unknown"

    def _get_user_id(self, request: Request) -> Optional[str]:
        """Recupere l'ID utilisateur si disponible."""
        user = getattr(request.state, "user", None)
        if user:
            return str(user.get("id"))
        return None


# =============================================================================
# Decorateur pour routes specifiques
# =============================================================================
def rate_limit(limit: int = 60, window: int = 60):
    """
    Decorateur pour appliquer un rate limit specifique a une route.

    Usage:
        @router.get("/expensive-operation")
        @rate_limit(limit=10, window=60)  # 10 req/min
        async def expensive_operation():
            ...
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            # Determiner la cle
            user = getattr(request.state, "user", None)
            if user:
                key = f"route:{func.__name__}:user:{user.get('id')}"
            else:
                ip = request.client.host if request.client else "unknown"
                key = f"route:{func.__name__}:ip:{ip}"

            # Verifier la limite
            allowed, remaining, limit_value, reset_time = await RateLimiter.check_limit(
                key=key,
                limit=limit,
                window=window
            )

            if not allowed:
                retry_after = reset_time - int(time.time())
                raise HTTPException(
                    status_code=429,
                    detail=f"Limite atteinte pour cette operation. Reessayez dans {max(1, retry_after)} secondes.",
                    headers={
                        "X-RateLimit-Limit": str(limit_value),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                        "Retry-After": str(max(1, retry_after))
                    }
                )

            return await func(request, *args, **kwargs)

        # Preserver les metadonnees de la fonction
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


# =============================================================================
# Utilitaires
# =============================================================================
async def clear_all_rate_limits():
    """Efface tous les rate limits (admin uniquement)."""
    try:
        redis = Database.get_redis()
        if redis:
            # Supprimer toutes les cles de rate limit
            async for key in redis.scan_iter("azalplus:ratelimit:*"):
                await redis.delete(key)

        # Vider le cache memoire
        async with RateLimiter._memory_lock:
            RateLimiter._memory_cache.clear()

        logger.info("rate_limits_cleared")
        return True
    except Exception as e:
        logger.error("clear_rate_limits_error", error=str(e))
        return False


async def get_rate_limit_stats(key: str) -> Dict:
    """Recupere les statistiques de rate limit pour une cle."""
    try:
        redis = Database.get_redis()
        if redis:
            redis_key = f"azalplus:ratelimit:{key}"

            now = time.time()
            window_start = now - RateLimitConfig.WINDOW_SECONDS

            # Compter les requetes dans la fenetre
            count = await redis.zcount(redis_key, window_start, now)

            return {
                "key": key,
                "current_count": count,
                "window_seconds": RateLimitConfig.WINDOW_SECONDS,
                "timestamp": datetime.utcnow().isoformat()
            }

        return {"key": key, "error": "Redis not available"}
    except Exception as e:
        return {"key": key, "error": str(e)}
