# =============================================================================
# AZALPLUS - Prometheus Metrics Export
# =============================================================================
"""
Export des métriques au format Prometheus.
Endpoint: /metrics (accessible localhost + réseau Docker uniquement)
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse
import psutil
import time
import sys
import structlog

logger = structlog.get_logger()

# =============================================================================
# Router
# =============================================================================
prometheus_router = APIRouter(tags=["Monitoring"])

# Métriques en mémoire (simple, sans dépendance prometheus_client)
_metrics_data = {
    "requests_total": 0,
    "requests_by_status": {},
    "request_duration_sum": 0.0,
    "request_count": 0,
    "errors_total": 0,
    "last_update": 0,
}

# IPs autorisées
ALLOWED_IPS = ["127.0.0.1", "::1", "localhost", "172.18.0.1", "57.128.7.20"]


def is_allowed(request: Request) -> bool:
    """Vérifie si l'IP est autorisée."""
    client_ip = request.client.host if request.client else None

    # Check X-Forwarded-For and X-Real-IP headers (from nginx)
    forwarded = request.headers.get("X-Forwarded-For", "")
    real_ip = request.headers.get("X-Real-IP", "")

    for ip in [client_ip, forwarded.split(",")[0].strip() if forwarded else "", real_ip]:
        if ip and (ip in ALLOWED_IPS or ip.startswith("172.") or ip.startswith("10.")):
            return True
    return False


def record_request(status_code: int, duration: float):
    """Enregistre une requête (appelé par middleware)."""
    _metrics_data["requests_total"] += 1
    _metrics_data["request_duration_sum"] += duration
    _metrics_data["request_count"] += 1

    status_key = str(status_code)
    _metrics_data["requests_by_status"][status_key] = \
        _metrics_data["requests_by_status"].get(status_key, 0) + 1

    if status_code >= 400:
        _metrics_data["errors_total"] += 1


def generate_metrics() -> str:
    """Génère les métriques au format Prometheus."""
    lines = []

    # Info application
    lines.append("# HELP azalplus_info Application information")
    lines.append("# TYPE azalplus_info gauge")
    lines.append(f'azalplus_info{{version="1.0.0",python="{sys.version_info.major}.{sys.version_info.minor}"}} 1')

    # Requêtes totales
    lines.append("# HELP azalplus_http_requests_total Total HTTP requests")
    lines.append("# TYPE azalplus_http_requests_total counter")
    lines.append(f"azalplus_http_requests_total {_metrics_data['requests_total']}")

    # Requêtes par status
    lines.append("# HELP azalplus_http_requests_by_status HTTP requests by status code")
    lines.append("# TYPE azalplus_http_requests_by_status counter")
    for status, count in _metrics_data["requests_by_status"].items():
        lines.append(f'azalplus_http_requests_by_status{{status="{status}"}} {count}')

    # Erreurs
    lines.append("# HELP azalplus_errors_total Total errors (4xx + 5xx)")
    lines.append("# TYPE azalplus_errors_total counter")
    lines.append(f"azalplus_errors_total {_metrics_data['errors_total']}")

    # Durée moyenne
    avg_duration = 0
    if _metrics_data["request_count"] > 0:
        avg_duration = _metrics_data["request_duration_sum"] / _metrics_data["request_count"]
    lines.append("# HELP azalplus_request_duration_avg_seconds Average request duration")
    lines.append("# TYPE azalplus_request_duration_avg_seconds gauge")
    lines.append(f"azalplus_request_duration_avg_seconds {avg_duration:.6f}")

    # Métriques système
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    lines.append("# HELP azalplus_memory_usage_bytes Memory usage")
    lines.append("# TYPE azalplus_memory_usage_bytes gauge")
    lines.append(f'azalplus_memory_usage_bytes{{type="total"}} {mem.total}')
    lines.append(f'azalplus_memory_usage_bytes{{type="used"}} {mem.used}')
    lines.append(f'azalplus_memory_usage_bytes{{type="available"}} {mem.available}')

    lines.append("# HELP azalplus_memory_usage_percent Memory usage percentage")
    lines.append("# TYPE azalplus_memory_usage_percent gauge")
    lines.append(f"azalplus_memory_usage_percent {mem.percent}")

    lines.append("# HELP azalplus_disk_usage_percent Disk usage percentage")
    lines.append("# TYPE azalplus_disk_usage_percent gauge")
    lines.append(f"azalplus_disk_usage_percent {disk.percent}")

    lines.append("# HELP azalplus_cpu_usage_percent CPU usage percentage")
    lines.append("# TYPE azalplus_cpu_usage_percent gauge")
    lines.append(f"azalplus_cpu_usage_percent {psutil.cpu_percent(interval=None)}")

    # Process info
    try:
        process = psutil.Process()
        lines.append("# HELP azalplus_process_memory_bytes Process memory usage")
        lines.append("# TYPE azalplus_process_memory_bytes gauge")
        lines.append(f"azalplus_process_memory_bytes {process.memory_info().rss}")

        lines.append("# HELP azalplus_process_cpu_percent Process CPU usage")
        lines.append("# TYPE azalplus_process_cpu_percent gauge")
        lines.append(f"azalplus_process_cpu_percent {process.cpu_percent()}")
    except:
        pass

    return "\n".join(lines) + "\n"


@prometheus_router.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint(request: Request):
    """Endpoint Prometheus pour scraping."""
    if not is_allowed(request):
        return PlainTextResponse("Forbidden", status_code=403)

    return PlainTextResponse(
        content=generate_metrics(),
        media_type="text/plain; charset=utf-8"
    )
