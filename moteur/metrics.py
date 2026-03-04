# =============================================================================
# AZALPLUS - Metrics Collection
# =============================================================================
"""
Systeme de collecte de metriques pour le dashboard d'administration.
- Metriques systeme (CPU, RAM, Disque)
- Metriques API (temps de reponse, erreurs, requetes)
- Metriques utilisateurs (sessions actives)
- Alertes automatiques
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import asyncio
import psutil
import platform
import sys
import os
import time
import structlog
from uuid import UUID

from .config import settings
from .db import Database
from .auth import require_role

logger = structlog.get_logger()

# =============================================================================
# Configuration
# =============================================================================
# Taille maximale des historiques en memoire
MAX_HISTORY_SIZE = 1000

# Seuils d'alerte
ALERT_THRESHOLDS = {
    "disk_usage_percent": 90,      # Alerte si > 90%
    "memory_usage_percent": 90,    # Alerte si > 90%
    "error_rate_percent": 5,       # Alerte si > 5% des requetes en erreur
    "slow_response_ms": 2000,      # Alerte si temps moyen > 2s
    "db_connections_percent": 80,  # Alerte si > 80% du pool utilise
}

# Version AZALPLUS
AZALPLUS_VERSION = "1.0.0"

# =============================================================================
# Schemas
# =============================================================================
class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    DISK_SPACE = "disk_space"
    MEMORY = "memory"
    ERROR_RATE = "error_rate"
    SLOW_RESPONSE = "slow_response"
    DB_CONNECTION = "db_connection"
    REDIS_CONNECTION = "redis_connection"


@dataclass
class Alert:
    """Alerte systeme."""
    type: AlertType
    severity: AlertSeverity
    message: str
    value: float
    threshold: float
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class RequestMetric:
    """Metrique d'une requete API."""
    path: str
    method: str
    status_code: int
    response_time_ms: float
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class SystemHealth(BaseModel):
    """Etat de sante du systeme."""
    database: bool
    redis: bool
    disk_ok: bool
    memory_ok: bool
    overall: str  # healthy, degraded, critical


class SystemInfo(BaseModel):
    """Informations systeme."""
    python_version: str
    azalplus_version: str
    platform: str
    hostname: str
    uptime_seconds: float
    uptime_human: str
    start_time: datetime


class DiskInfo(BaseModel):
    """Informations disque."""
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float
    total_human: str
    used_human: str
    free_human: str


class MemoryInfo(BaseModel):
    """Informations memoire."""
    total_bytes: int
    available_bytes: int
    used_bytes: int
    usage_percent: float
    total_human: str
    available_human: str
    used_human: str


class APIMetrics(BaseModel):
    """Metriques API aggregees."""
    total_requests: int
    requests_last_hour: int
    requests_last_24h: int
    error_count: int
    error_rate_percent: float
    avg_response_time_ms: float
    p50_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    slowest_endpoints: List[Dict[str, Any]]


class SessionInfo(BaseModel):
    """Informations sur les sessions."""
    active_sessions: int
    sessions_last_hour: int
    unique_users_today: int


# =============================================================================
# Metrics Collector (Singleton)
# =============================================================================
class MetricsCollector:
    """Collecteur de metriques systeme."""

    _instance = None
    _start_time: datetime = None
    _request_history: deque = None
    _alerts: List[Alert] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialise le collecteur."""
        self._start_time = datetime.now()
        self._request_history = deque(maxlen=MAX_HISTORY_SIZE)
        self._alerts = []
        logger.info("metrics_collector_initialized")

    @classmethod
    def get_instance(cls) -> "MetricsCollector":
        """Retourne l'instance singleton."""
        return cls()

    # =========================================================================
    # Collecte des metriques de requetes
    # =========================================================================
    def record_request(self, metric: RequestMetric):
        """Enregistre une metrique de requete."""
        self._request_history.append(metric)

    def record_request_from_data(
        self,
        path: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None
    ):
        """Enregistre une metrique depuis des donnees brutes."""
        metric = RequestMetric(
            path=path,
            method=method,
            status_code=status_code,
            response_time_ms=response_time_ms,
            user_id=user_id,
            tenant_id=tenant_id
        )
        self.record_request(metric)

    # =========================================================================
    # Informations systeme
    # =========================================================================
    def get_system_info(self) -> SystemInfo:
        """Retourne les informations systeme."""
        uptime = datetime.now() - self._start_time
        uptime_seconds = uptime.total_seconds()

        # Formatage humain de l'uptime
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        if days > 0:
            uptime_human = f"{days}j {hours}h {minutes}m"
        elif hours > 0:
            uptime_human = f"{hours}h {minutes}m"
        else:
            uptime_human = f"{minutes}m"

        return SystemInfo(
            python_version=sys.version,
            azalplus_version=AZALPLUS_VERSION,
            platform=platform.platform(),
            hostname=platform.node(),
            uptime_seconds=uptime_seconds,
            uptime_human=uptime_human,
            start_time=self._start_time
        )

    # =========================================================================
    # Informations disque
    # =========================================================================
    def get_disk_info(self, path: str = "/") -> DiskInfo:
        """Retourne les informations disque."""
        usage = psutil.disk_usage(path)

        return DiskInfo(
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            usage_percent=usage.percent,
            total_human=self._format_bytes(usage.total),
            used_human=self._format_bytes(usage.used),
            free_human=self._format_bytes(usage.free)
        )

    # =========================================================================
    # Informations memoire
    # =========================================================================
    def get_memory_info(self) -> MemoryInfo:
        """Retourne les informations memoire."""
        mem = psutil.virtual_memory()

        return MemoryInfo(
            total_bytes=mem.total,
            available_bytes=mem.available,
            used_bytes=mem.used,
            usage_percent=mem.percent,
            total_human=self._format_bytes(mem.total),
            available_human=self._format_bytes(mem.available),
            used_human=self._format_bytes(mem.used)
        )

    # =========================================================================
    # Etat de sante
    # =========================================================================
    async def get_health(self) -> SystemHealth:
        """Retourne l'etat de sante global du systeme."""
        # Verifier la base de donnees
        db_healthy = await Database.is_healthy()

        # Verifier Redis
        redis_healthy = await Database.cache_healthy()

        # Verifier le disque
        disk_info = self.get_disk_info()
        disk_ok = disk_info.usage_percent < ALERT_THRESHOLDS["disk_usage_percent"]

        # Verifier la memoire
        memory_info = self.get_memory_info()
        memory_ok = memory_info.usage_percent < ALERT_THRESHOLDS["memory_usage_percent"]

        # Determiner l'etat global
        if not db_healthy or not redis_healthy:
            overall = "critical"
        elif not disk_ok or not memory_ok:
            overall = "degraded"
        else:
            overall = "healthy"

        return SystemHealth(
            database=db_healthy,
            redis=redis_healthy,
            disk_ok=disk_ok,
            memory_ok=memory_ok,
            overall=overall
        )

    # =========================================================================
    # Metriques API
    # =========================================================================
    def get_api_metrics(self) -> APIMetrics:
        """Retourne les metriques API aggregees."""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(hours=24)

        # Filtrer les requetes
        all_requests = list(self._request_history)
        requests_last_hour = [r for r in all_requests if r.timestamp > one_hour_ago]
        requests_last_24h = [r for r in all_requests if r.timestamp > one_day_ago]

        # Calculer les erreurs (status >= 400)
        error_count = len([r for r in all_requests if r.status_code >= 400])
        error_rate = (error_count / len(all_requests) * 100) if all_requests else 0

        # Calculer les temps de reponse
        response_times = sorted([r.response_time_ms for r in all_requests]) if all_requests else [0]

        avg_response = sum(response_times) / len(response_times) if response_times else 0
        p50 = response_times[len(response_times) // 2] if response_times else 0
        p95_idx = int(len(response_times) * 0.95)
        p99_idx = int(len(response_times) * 0.99)
        p95 = response_times[p95_idx] if p95_idx < len(response_times) else response_times[-1] if response_times else 0
        p99 = response_times[p99_idx] if p99_idx < len(response_times) else response_times[-1] if response_times else 0

        # Endpoints les plus lents
        endpoint_times: Dict[str, List[float]] = {}
        for r in all_requests:
            key = f"{r.method} {r.path}"
            if key not in endpoint_times:
                endpoint_times[key] = []
            endpoint_times[key].append(r.response_time_ms)

        slowest = []
        for endpoint, times in endpoint_times.items():
            avg = sum(times) / len(times)
            slowest.append({
                "endpoint": endpoint,
                "avg_time_ms": round(avg, 2),
                "count": len(times)
            })

        slowest.sort(key=lambda x: x["avg_time_ms"], reverse=True)

        return APIMetrics(
            total_requests=len(all_requests),
            requests_last_hour=len(requests_last_hour),
            requests_last_24h=len(requests_last_24h),
            error_count=error_count,
            error_rate_percent=round(error_rate, 2),
            avg_response_time_ms=round(avg_response, 2),
            p50_response_time_ms=round(p50, 2),
            p95_response_time_ms=round(p95, 2),
            p99_response_time_ms=round(p99, 2),
            slowest_endpoints=slowest[:10]
        )

    # =========================================================================
    # Sessions actives
    # =========================================================================
    async def get_session_info(self) -> SessionInfo:
        """Retourne les informations sur les sessions actives."""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text

                # Sessions actives (connexion < 24h)
                result = session.execute(text("""
                    SELECT
                        COUNT(*) FILTER (WHERE derniere_connexion > NOW() - INTERVAL '24 hours') as active_24h,
                        COUNT(*) FILTER (WHERE derniere_connexion > NOW() - INTERVAL '1 hour') as active_1h,
                        COUNT(DISTINCT id) FILTER (WHERE derniere_connexion::date = CURRENT_DATE) as unique_today
                    FROM azalplus.utilisateurs
                    WHERE actif = true
                """))
                row = result.fetchone()

                return SessionInfo(
                    active_sessions=row[0] or 0,
                    sessions_last_hour=row[1] or 0,
                    unique_users_today=row[2] or 0
                )
        except Exception as e:
            logger.error("session_info_error", error=str(e))
            return SessionInfo(
                active_sessions=0,
                sessions_last_hour=0,
                unique_users_today=0
            )

    # =========================================================================
    # Alertes
    # =========================================================================
    async def check_alerts(self) -> List[Alert]:
        """Verifie et retourne les alertes actives."""
        alerts = []

        # Verifier l'espace disque
        disk = self.get_disk_info()
        if disk.usage_percent >= ALERT_THRESHOLDS["disk_usage_percent"]:
            alerts.append(Alert(
                type=AlertType.DISK_SPACE,
                severity=AlertSeverity.CRITICAL if disk.usage_percent >= 95 else AlertSeverity.WARNING,
                message=f"Espace disque faible: {disk.usage_percent:.1f}% utilise",
                value=disk.usage_percent,
                threshold=ALERT_THRESHOLDS["disk_usage_percent"]
            ))

        # Verifier la memoire
        memory = self.get_memory_info()
        if memory.usage_percent >= ALERT_THRESHOLDS["memory_usage_percent"]:
            alerts.append(Alert(
                type=AlertType.MEMORY,
                severity=AlertSeverity.CRITICAL if memory.usage_percent >= 95 else AlertSeverity.WARNING,
                message=f"Memoire elevee: {memory.usage_percent:.1f}% utilisee",
                value=memory.usage_percent,
                threshold=ALERT_THRESHOLDS["memory_usage_percent"]
            ))

        # Verifier le taux d'erreur
        api_metrics = self.get_api_metrics()
        if api_metrics.error_rate_percent >= ALERT_THRESHOLDS["error_rate_percent"]:
            alerts.append(Alert(
                type=AlertType.ERROR_RATE,
                severity=AlertSeverity.CRITICAL if api_metrics.error_rate_percent >= 10 else AlertSeverity.WARNING,
                message=f"Taux d'erreur eleve: {api_metrics.error_rate_percent:.1f}%",
                value=api_metrics.error_rate_percent,
                threshold=ALERT_THRESHOLDS["error_rate_percent"]
            ))

        # Verifier les temps de reponse
        if api_metrics.avg_response_time_ms >= ALERT_THRESHOLDS["slow_response_ms"]:
            alerts.append(Alert(
                type=AlertType.SLOW_RESPONSE,
                severity=AlertSeverity.WARNING,
                message=f"Temps de reponse lent: {api_metrics.avg_response_time_ms:.0f}ms en moyenne",
                value=api_metrics.avg_response_time_ms,
                threshold=ALERT_THRESHOLDS["slow_response_ms"]
            ))

        # Verifier la connexion DB
        db_healthy = await Database.is_healthy()
        if not db_healthy:
            alerts.append(Alert(
                type=AlertType.DB_CONNECTION,
                severity=AlertSeverity.CRITICAL,
                message="Connexion a la base de donnees perdue",
                value=0,
                threshold=1
            ))

        # Verifier Redis
        redis_healthy = await Database.cache_healthy()
        if not redis_healthy:
            alerts.append(Alert(
                type=AlertType.REDIS_CONNECTION,
                severity=AlertSeverity.WARNING,
                message="Connexion a Redis perdue",
                value=0,
                threshold=1
            ))

        self._alerts = alerts
        return alerts

    # =========================================================================
    # Donnees pour les graphiques
    # =========================================================================
    def get_requests_over_time(self, hours: int = 24, interval_minutes: int = 60) -> List[Dict[str, Any]]:
        """Retourne les requetes groupees par intervalle de temps."""
        now = datetime.now()
        start_time = now - timedelta(hours=hours)

        # Creer les buckets
        buckets = []
        current = start_time
        while current < now:
            buckets.append({
                "timestamp": current.isoformat(),
                "requests": 0,
                "errors": 0
            })
            current += timedelta(minutes=interval_minutes)

        # Remplir les buckets
        for req in self._request_history:
            if req.timestamp < start_time:
                continue

            # Trouver le bon bucket
            bucket_idx = int((req.timestamp - start_time).total_seconds() / (interval_minutes * 60))
            if 0 <= bucket_idx < len(buckets):
                buckets[bucket_idx]["requests"] += 1
                if req.status_code >= 400:
                    buckets[bucket_idx]["errors"] += 1

        return buckets

    # =========================================================================
    # Actions admin
    # =========================================================================
    async def clear_cache(self) -> Dict[str, Any]:
        """Vide le cache Redis."""
        try:
            redis = Database.get_redis()
            await redis.flushdb()
            logger.info("cache_cleared")
            return {"status": "success", "message": "Cache vide avec succes"}
        except Exception as e:
            logger.error("cache_clear_error", error=str(e))
            return {"status": "error", "message": str(e)}

    # =========================================================================
    # Utilitaires
    # =========================================================================
    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        """Formate une taille en bytes en format lisible."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"


# =============================================================================
# Middleware pour collecter les metriques
# =============================================================================
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware pour collecter les metriques de chaque requete."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()

        response = await call_next(request)

        # Calculer le temps de reponse
        response_time_ms = (time.perf_counter() - start_time) * 1000

        # Enregistrer la metrique
        collector = MetricsCollector.get_instance()

        # Extraire user_id et tenant_id si disponibles
        user = getattr(request.state, "user", None)
        user_id = str(user.get("id")) if user and user.get("id") else None
        tenant_id = str(user.get("tenant_id")) if user and user.get("tenant_id") else None

        collector.record_request_from_data(
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            user_id=user_id,
            tenant_id=tenant_id
        )

        return response


# =============================================================================
# API Router
# =============================================================================
metrics_router = APIRouter()


@metrics_router.get("/health")
async def get_system_health(user: dict = Depends(require_role("admin"))):
    """Retourne l'etat de sante du systeme."""
    collector = MetricsCollector.get_instance()
    return await collector.get_health()


@metrics_router.get("/info")
async def get_system_info(user: dict = Depends(require_role("admin"))):
    """Retourne les informations systeme."""
    collector = MetricsCollector.get_instance()
    return collector.get_system_info()


@metrics_router.get("/disk")
async def get_disk_info(user: dict = Depends(require_role("admin"))):
    """Retourne les informations disque."""
    collector = MetricsCollector.get_instance()
    return collector.get_disk_info()


@metrics_router.get("/memory")
async def get_memory_info(user: dict = Depends(require_role("admin"))):
    """Retourne les informations memoire."""
    collector = MetricsCollector.get_instance()
    return collector.get_memory_info()


@metrics_router.get("/api")
async def get_api_metrics(user: dict = Depends(require_role("admin"))):
    """Retourne les metriques API."""
    collector = MetricsCollector.get_instance()
    return collector.get_api_metrics()


@metrics_router.get("/sessions")
async def get_sessions(user: dict = Depends(require_role("admin"))):
    """Retourne les informations sur les sessions."""
    collector = MetricsCollector.get_instance()
    return await collector.get_session_info()


@metrics_router.get("/alerts")
async def get_alerts(user: dict = Depends(require_role("admin"))):
    """Retourne les alertes actives."""
    collector = MetricsCollector.get_instance()
    alerts = await collector.check_alerts()
    return {
        "alerts": [
            {
                "type": a.type.value,
                "severity": a.severity.value,
                "message": a.message,
                "value": a.value,
                "threshold": a.threshold,
                "created_at": a.created_at.isoformat()
            }
            for a in alerts
        ],
        "count": len(alerts)
    }


@metrics_router.get("/requests-chart")
async def get_requests_chart(
    hours: int = 24,
    interval: int = 60,
    user: dict = Depends(require_role("admin"))
):
    """Retourne les donnees pour le graphique des requetes."""
    collector = MetricsCollector.get_instance()
    return collector.get_requests_over_time(hours=hours, interval_minutes=interval)


@metrics_router.get("/dashboard")
async def get_dashboard(user: dict = Depends(require_role("admin"))):
    """Retourne toutes les donnees du dashboard en une seule requete."""
    collector = MetricsCollector.get_instance()

    health = await collector.get_health()
    system_info = collector.get_system_info()
    disk = collector.get_disk_info()
    memory = collector.get_memory_info()
    api_metrics = collector.get_api_metrics()
    sessions = await collector.get_session_info()
    alerts = await collector.check_alerts()
    requests_chart = collector.get_requests_over_time(hours=24, interval_minutes=60)

    return {
        "health": health.model_dump(),
        "system": system_info.model_dump(),
        "disk": disk.model_dump(),
        "memory": memory.model_dump(),
        "api": api_metrics.model_dump(),
        "sessions": sessions.model_dump(),
        "alerts": [
            {
                "type": a.type.value,
                "severity": a.severity.value,
                "message": a.message,
                "value": a.value,
                "threshold": a.threshold
            }
            for a in alerts
        ],
        "requests_chart": requests_chart
    }


@metrics_router.post("/cache/clear")
async def clear_cache(user: dict = Depends(require_role("admin"))):
    """Vide le cache Redis."""
    collector = MetricsCollector.get_instance()
    return await collector.clear_cache()


@metrics_router.get("/logs")
async def get_recent_logs(
    limit: int = 100,
    level: Optional[str] = None,
    user: dict = Depends(require_role("admin"))
):
    """Retourne les logs recents depuis guardian_log."""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text

            query = """
                SELECT * FROM azalplus.guardian_log
            """
            params = {"limit": limit}

            if level:
                query += " WHERE niveau = :level"
                params["level"] = level.upper()

            query += " ORDER BY created_at DESC LIMIT :limit"

            result = session.execute(text(query), params)
            logs = [dict(row._mapping) for row in result]

            return {"logs": logs, "count": len(logs)}
    except Exception as e:
        logger.error("get_logs_error", error=str(e))
        return {"logs": [], "count": 0, "error": str(e)}
