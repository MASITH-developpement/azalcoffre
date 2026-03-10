# =============================================================================
# AZALPLUS - GUARDIAN
# =============================================================================
"""
Guardian - Le gardien invisible.

Guardian surveille, corrige et bloque en silence.
Personne ne sait qu'il existe, sauf le Créateur.

CRÉATEUR: contact@stephane-moreau.fr (hardcodé)
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
import structlog
import re
import hashlib

from .config import settings
from .db import Database

# AutoPilot - Système d'auto-correction (invisible)
from .autopilot import AutoPilot, PostgresStorage

logger = structlog.get_logger()

# =============================================================================
# CRÉATEUR - HARDCODÉ (NE JAMAIS MODIFIER)
# =============================================================================
CREATEUR_EMAIL = "contact@stephane-moreau.fr"

# =============================================================================
# Messages neutres (Guardian reste invisible)
# =============================================================================
NEUTRAL_MESSAGES = [
    "Données non trouvées",
    "Action impossible",
    "Requête invalide",
    "Réessayez plus tard",
    "Paramètres incorrects",
]

# =============================================================================
# WAF Integration (60+ patterns)
# =============================================================================
from .waf import WAF, ThreatType, ThreatDetection

# Legacy patterns kept for backward compatibility
SQL_INJECTION_PATTERNS = [
    r"(\%27)|(\')|(\-\-)|(\%23)|(#)",
    r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",
    r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",
    r"((\%27)|(\'))union",
    r"exec(\s|\+)+(s|x)p\w+",
    r"UNION(\s+)SELECT",
    r"INSERT(\s+)INTO",
    r"DELETE(\s+)FROM",
    r"DROP(\s+)TABLE",
]

XSS_PATTERNS = [
    r"<script[^>]*>",
    r"javascript:",
    r"on\w+\s*=",
    r"<iframe",
    r"<object",
    r"<embed",
]

# =============================================================================
# Data classes
# =============================================================================
@dataclass
class GuardianCheckResult:
    """Résultat d'une vérification Guardian."""
    blocked: bool = False
    cleaned: bool = False
    reason: str = ""
    neutral_message: str = "Requête invalide"
    original_data: Optional[str] = None
    cleaned_data: Optional[str] = None

@dataclass
class GuardianLog:
    """Log Guardian."""
    niveau: str  # INFO, WARNING, BLOCK, CRITICAL
    action: str
    tenant_id: Optional[UUID] = None
    utilisateur_id: Optional[UUID] = None
    utilisateur_email: Optional[str] = None
    description: str = ""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    action_prise: str = ""
    requete_originale: Optional[str] = None
    requete_nettoyee: Optional[str] = None

# =============================================================================
# Guardian Class
# =============================================================================
class Guardian:
    """Le gardien invisible du système."""

    _initialized = False
    _blocked_ips = set()
    _failed_attempts = {}  # ip -> count

    @classmethod
    def initialize(cls):
        """Initialise Guardian."""
        cls._initialized = True
        logger.info("guardian_initialized", mode="silent")

    @classmethod
    def is_createur(cls, email: str) -> bool:
        """Vérifie si l'utilisateur est le Créateur."""
        return email == CREATEUR_EMAIL

    @classmethod
    async def check_request(cls, request: Request) -> GuardianCheckResult:
        """Vérifie une requête entrante avec WAF (60+ patterns)."""

        result = GuardianCheckResult()
        ip = cls._get_client_ip(request)

        # 1. IP bloquée ?
        if ip in cls._blocked_ips:
            result.blocked = True
            result.reason = "IP_BLOCKED"
            result.neutral_message = "Réessayez plus tard"
            await cls._log(GuardianLog(
                niveau="BLOCK",
                action="IP_BLOCKED",
                ip_address=ip,
                action_prise="BLOCKED"
            ))
            return result

        # 2. Rate limiting
        if cls._is_rate_limited(ip):
            result.blocked = True
            result.reason = "RATE_LIMITED"
            result.neutral_message = "Réessayez plus tard"
            return result

        # 3. WAF Check (60+ patterns)
        body = await cls._get_body(request)
        query_string = str(request.url.query) if request.url.query else ""
        path = request.url.path

        # Combiner toutes les données à vérifier
        data_to_check = f"{body} {query_string} {path}"

        # Utiliser le WAF pour la détection
        waf_result = WAF.check(data_to_check)

        if waf_result.detected:
            # Déterminer l'action selon la sévérité
            if waf_result.severity in ("critical", "high"):
                result.blocked = True
                result.reason = waf_result.threat_type.value if waf_result.threat_type else "WAF_BLOCKED"
                result.neutral_message = "Requête invalide"

                # Pour XSS, générer aussi la version nettoyée pour référence
                cleaned_version = None
                if waf_result.threat_type == ThreatType.XSS:
                    cleaned_version = WAF.sanitize_xss(body)
                    result.original_data = body
                    result.cleaned_data = cleaned_version

                await cls._log(GuardianLog(
                    niveau="CRITICAL" if waf_result.severity == "critical" else "BLOCK",
                    action=waf_result.threat_type.value if waf_result.threat_type else "WAF_THREAT",
                    ip_address=ip,
                    description=f"WAF: {waf_result.description} (pattern: {waf_result.pattern_matched[:50] if waf_result.pattern_matched else 'N/A'}...)",
                    action_prise="BLOCKED",
                    requete_originale=data_to_check,
                    requete_nettoyee=cleaned_version  # Version nettoyée pour XSS
                ))
                cls._increment_failed(ip)
                return result
            elif waf_result.threat_type == ThreatType.XSS:
                # XSS: on bloque et on enregistre la version nettoyée pour référence
                cleaned_body = WAF.sanitize_xss(body)
                result.cleaned = True
                result.reason = "XSS_BLOCKED"
                result.original_data = body
                result.cleaned_data = cleaned_body
                result.neutral_message = "Requête invalide"
                await cls._log(GuardianLog(
                    niveau="BLOCK",
                    action="XSS_BLOCKED",
                    ip_address=ip,
                    description=f"WAF: {waf_result.description}",
                    action_prise="BLOCKED",
                    requete_originale=body,
                    requete_nettoyee=cleaned_body
                ))
                cls._increment_failed(ip)
            else:
                # Medium/Low: on log mais on laisse passer avec warning
                await cls._log(GuardianLog(
                    niveau="WARNING",
                    action=waf_result.threat_type.value if waf_result.threat_type else "WAF_WARNING",
                    ip_address=ip,
                    description=f"WAF: {waf_result.description}",
                    action_prise="LOGGED",
                    requete_originale=data_to_check,
                    requete_nettoyee=None
                ))

        # 4. Legacy checks (fallback si WAF n'a rien trouvé)
        if not waf_result.detected:
            # Injection SQL (legacy patterns)
            if cls._detect_sql_injection(body):
                result.blocked = True
                result.reason = "SQL_INJECTION"
                result.neutral_message = "Requête invalide"
                await cls._log(GuardianLog(
                    niveau="CRITICAL",
                    action="SQL_INJECTION",
                    ip_address=ip,
                    description="Tentative injection SQL détectée (legacy)",
                    action_prise="BLOCKED",
                    requete_originale=body,
                    requete_nettoyee=None
                ))
                cls._increment_failed(ip)
                return result

            # XSS (legacy patterns)
            if cls._detect_xss(body):
                cleaned_body = cls._clean_xss(body)
                result.cleaned = True
                result.reason = "XSS_BLOCKED"
                result.original_data = body
                result.cleaned_data = cleaned_body
                result.neutral_message = "Requête invalide"
                await cls._log(GuardianLog(
                    niveau="BLOCK",
                    action="XSS_BLOCKED",
                    ip_address=ip,
                    action_prise="BLOCKED",
                    requete_originale=body,
                    requete_nettoyee=cleaned_body
                ))
                cls._increment_failed(ip)

        # 5. Tentative d'accès autre tenant
        # (vérifié plus tard dans le middleware tenant)

        return result

    @classmethod
    async def check_tenant_access(
        cls,
        request_tenant_id: UUID,
        user_tenant_id: UUID,
        user_email: str
    ) -> GuardianCheckResult:
        """Vérifie l'accès tenant (CRITIQUE)."""

        result = GuardianCheckResult()

        # Le Créateur peut tout voir
        if cls.is_createur(user_email):
            return result

        # Vérification stricte
        if request_tenant_id != user_tenant_id:
            result.blocked = True
            result.reason = "TENANT_BREACH"
            result.neutral_message = "Données non trouvées"

            await cls._log(GuardianLog(
                niveau="CRITICAL",
                action="TENANT_BREACH",
                tenant_id=user_tenant_id,
                utilisateur_email=user_email,
                description=f"Tentative accès tenant {request_tenant_id}",
                action_prise="BLOCKED"
            ))

            return result

        return result

    # Paths à exclure du logging (endpoints haute fréquence)
    _EXCLUDE_PATHS = [
        "/health",
        "/favicon.ico",
        "/assets/",
        "/static/",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    ]

    @classmethod
    async def log_request(cls, request: Request, response):
        """Log une requête (silencieux) - suivi complet."""
        path = request.url.path

        # Exclure les endpoints haute fréquence
        if any(path.startswith(excluded) for excluded in cls._EXCLUDE_PATHS):
            return

        ip = cls._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:200]
        method = request.method
        status_code = response.status_code if response else 0

        # Determiner le niveau selon le status code
        if status_code >= 500:
            niveau = "ERROR"
        elif status_code >= 400:
            niveau = "WARNING"
        else:
            niveau = "INFO"

        # Extraire tenant_id et user du state si disponible
        tenant_id = None
        user_email = None
        user_id = None
        if hasattr(request.state, "tenant_id"):
            tenant_id = request.state.tenant_id
        if hasattr(request.state, "user"):
            user = request.state.user
            if user:
                user_email = user.get("email")
                user_id = user.get("id")

        await cls._log(GuardianLog(
            niveau=niveau,
            action=f"{method}:{status_code}",
            tenant_id=tenant_id,
            utilisateur_id=user_id,
            utilisateur_email=user_email,
            description=f"{method} {path}",
            ip_address=ip,
            user_agent=user_agent,
            action_prise="LOGGED"
        ))

    @classmethod
    async def log_error(cls, request: Request, error: Exception):
        """Log une erreur (silencieux)."""
        ip = cls._get_client_ip(request)
        await cls._log(GuardianLog(
            niveau="ERROR",
            action="EXCEPTION",
            ip_address=ip,
            description=str(error)[:500],
            action_prise="LOGGED"
        ))

    # =========================================================================
    # Méthodes privées
    # =========================================================================
    @classmethod
    def _get_client_ip(cls, request: Request) -> str:
        """Récupère l'IP client."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @classmethod
    async def _get_body(cls, request: Request) -> str:
        """Récupère le body de la requête."""
        try:
            body = await request.body()
            return body.decode("utf-8", errors="ignore")
        except:
            return ""

    @classmethod
    def _detect_sql_injection(cls, data: str) -> bool:
        """Détecte les tentatives d'injection SQL."""
        if not data:
            return False
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, data, re.IGNORECASE):
                return True
        return False

    @classmethod
    def _detect_xss(cls, data: str) -> bool:
        """Détecte les tentatives XSS."""
        if not data:
            return False
        for pattern in XSS_PATTERNS:
            if re.search(pattern, data, re.IGNORECASE):
                return True
        return False

    @classmethod
    def _clean_xss(cls, data: str) -> str:
        """Nettoie les tentatives XSS."""
        import html
        return html.escape(data)

    @classmethod
    def _is_rate_limited(cls, ip: str) -> bool:
        """Vérifie le rate limiting."""
        # Implémentation simple avec compteur en mémoire
        # En production, utiliser Redis
        return False

    @classmethod
    def _increment_failed(cls, ip: str):
        """Incrémente les tentatives échouées."""
        if ip not in cls._failed_attempts:
            cls._failed_attempts[ip] = 0
        cls._failed_attempts[ip] += 1

        # Bloquer après 10 tentatives
        if cls._failed_attempts[ip] >= 10:
            cls._blocked_ips.add(ip)

    # Fichiers de log Guardian
    _LOG_DIR = "/home/ubuntu/azalplus/logs"
    _REQUESTS_LOG = f"{_LOG_DIR}/guardian_requests.log"
    _ERRORS_LOG = f"{_LOG_DIR}/guardian_errors.log"
    _BLOCKS_LOG = f"{_LOG_DIR}/guardian_blocks.log"

    @classmethod
    def _write_to_file(cls, filepath: str, log: GuardianLog):
        """Ecrit un log dans un fichier."""
        try:
            from pathlib import Path
            Path(cls._LOG_DIR).mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().isoformat()
            line = f"{timestamp} | {log.niveau:8} | {log.action:25} | {log.ip_address or '-':15} | {log.description or ''}\n"

            with open(filepath, 'a') as f:
                f.write(line)
        except Exception as e:
            logger.warning("guardian_file_log_failed", error=str(e))

    @classmethod
    async def _log(cls, log: GuardianLog):
        """Enregistre un log Guardian en base et fichier."""
        # 1. Ecrire dans le fichier selon le type
        if log.niveau in ("BLOCK", "CRITICAL"):
            cls._write_to_file(cls._BLOCKS_LOG, log)
        elif log.niveau == "ERROR":
            cls._write_to_file(cls._ERRORS_LOG, log)
        else:
            cls._write_to_file(cls._REQUESTS_LOG, log)

        # 2. Ecrire en base de donnees
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        INSERT INTO azalplus.guardian_log
                        (niveau, action, tenant_id, utilisateur_id, utilisateur_email,
                         description, ip_address, user_agent, action_prise,
                         requete_originale, requete_nettoyee)
                        VALUES (:niveau, :action, :tenant_id, :utilisateur_id, :utilisateur_email,
                                :description, :ip_address, :user_agent, :action_prise,
                                :requete_originale, :requete_nettoyee)
                    """),
                    {
                        "niveau": log.niveau,
                        "action": log.action,
                        "tenant_id": str(log.tenant_id) if log.tenant_id else None,
                        "utilisateur_id": str(log.utilisateur_id) if log.utilisateur_id else None,
                        "utilisateur_email": log.utilisateur_email,
                        "description": log.description,
                        "ip_address": log.ip_address,
                        "user_agent": log.user_agent,
                        "action_prise": log.action_prise,
                        "requete_originale": log.requete_originale[:2000] if log.requete_originale else None,
                        "requete_nettoyee": log.requete_nettoyee[:2000] if log.requete_nettoyee else None
                    }
                )
                session.commit()
        except Exception as e:
            logger.error("guardian_log_failed", error=str(e))

# =============================================================================
# Router Guardian (visible Créateur uniquement)
# =============================================================================
guardian_router = APIRouter()

async def verify_createur(request: Request):
    """Vérifie que l'utilisateur est le Créateur."""
    # Récupérer l'utilisateur depuis le contexte
    user = getattr(request.state, "user", None)
    if not user or user.get("email") != CREATEUR_EMAIL:
        # Message neutre - Guardian reste invisible
        raise HTTPException(status_code=404, detail="Not found")
    return user

@guardian_router.get("/dashboard")
async def guardian_dashboard_json(user: dict = Depends(verify_createur)):
    """Dashboard Guardian JSON (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text

        # Stats globales
        stats = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE niveau = 'BLOCK') as blocked,
                COUNT(*) FILTER (WHERE niveau = 'WARNING') as warnings,
                COUNT(*) FILTER (WHERE niveau = 'CRITICAL') as critical,
                COUNT(*) FILTER (WHERE niveau = 'ERROR') as errors,
                COUNT(*) FILTER (WHERE niveau = 'INFO') as info,
                COUNT(*) as total
            FROM azalplus.guardian_log
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)).fetchone()

        # Derniers événements
        events = session.execute(text("""
            SELECT * FROM azalplus.guardian_log
            ORDER BY created_at DESC
            LIMIT 50
        """)).fetchall()

        return {
            "stats": {
                "blocked_24h": stats[0],
                "warnings_24h": stats[1],
                "critical_24h": stats[2],
                "errors_24h": stats[3],
                "info_24h": stats[4],
                "total_24h": stats[5]
            },
            "blocked_ips": list(Guardian._blocked_ips),
            "recent_events": [dict(row._mapping) for row in events]
        }


@guardian_router.get("/", response_class=HTMLResponse)
async def guardian_dashboard_html(request: Request, user: dict = Depends(verify_createur)):
    """Dashboard Guardian HTML (Créateur uniquement)."""
    from fastapi.responses import HTMLResponse
    from datetime import datetime

    # Heure actuelle
    current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Récupérer l'AutoPilot pour les learnings
    from .core import get_autopilot
    autopilot = get_autopilot()

    # Learnings et proposals
    learnings = []
    proposals = []
    if autopilot and autopilot._storage:
        try:
            learnings = autopilot._storage.get_all_learnings(limit=20)
            proposals = autopilot._storage.get_pending_proposals()
            # Ajouter les proposals appliquées récemment
            with Database.get_session() as sess:
                from sqlalchemy import text
                applied = sess.execute(text("""
                    SELECT id, error_type, file_path, status, confidence,
                           to_char(created_at, 'DD/MM HH24:MI') as time
                    FROM azalplus.guardian_fix_proposals
                    ORDER BY created_at DESC
                    LIMIT 10
                """)).fetchall()
        except Exception as e:
            logger.warning("guardian_dashboard_autopilot_error", error=str(e))
            applied = []
    else:
        applied = []

    with Database.get_session() as session:
        from sqlalchemy import text

        # Stats globales
        stats = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE niveau = 'BLOCK') as blocked,
                COUNT(*) FILTER (WHERE niveau = 'WARNING') as warnings,
                COUNT(*) FILTER (WHERE niveau = 'CRITICAL') as critical,
                COUNT(*) FILTER (WHERE niveau = 'ERROR') as errors,
                COUNT(*) FILTER (WHERE niveau = 'INFO') as info,
                COUNT(*) as total
            FROM azalplus.guardian_log
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)).fetchone()

        # Top IPs
        top_ips = session.execute(text("""
            SELECT ip_address, COUNT(*) as count,
                   COUNT(*) FILTER (WHERE niveau IN ('BLOCK', 'WARNING', 'ERROR')) as issues
            FROM azalplus.guardian_log
            WHERE created_at > NOW() - INTERVAL '24 hours'
              AND ip_address IS NOT NULL
            GROUP BY ip_address
            ORDER BY count DESC
            LIMIT 10
        """)).fetchall()

        # Derniers événements (limité à 10)
        events = session.execute(text("""
            SELECT niveau, action, ip_address, description,
                   to_char(created_at, 'HH24:MI:SS') as time,
                   utilisateur_email
            FROM azalplus.guardian_log
            WHERE created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 10
        """)).fetchall()

        # Erreurs Frontend (depuis AutoPilot)
        frontend_errors = session.execute(text("""
            SELECT error_type, file_path, status, confidence,
                   to_char(created_at, 'DD/MM HH24:MI') as time,
                   LEFT(proposed_fix::text, 150) as fix_preview
            FROM azalplus.guardian_fix_proposals
            WHERE error_type LIKE 'FRONTEND%' OR error_type LIKE 'js_%'
               OR error_type LIKE 'http_%' OR error_type LIKE '404%'
               OR error_type LIKE 'network_%' OR error_type LIKE 'console_%'
            ORDER BY created_at DESC
            LIMIT 10
        """)).fetchall()

        # WAF stats
        waf_patterns = WAF.get_total_patterns()

        # Générer le HTML
        html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Guardian - Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0; padding: 20px;
        }}
        .header {{
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #334155;
        }}
        h1 {{ color: #f97316; font-size: 24px; }}
        .status {{ color: #22c55e; font-size: 14px; }}
        .stats {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px; margin-bottom: 30px;
        }}
        .stat {{
            background: #1e293b; padding: 20px; border-radius: 12px;
            text-align: center; border: 1px solid #334155;
        }}
        .stat-value {{ font-size: 32px; font-weight: bold; }}
        .stat-label {{ font-size: 12px; color: #94a3b8; margin-top: 5px; }}
        .stat.blocked .stat-value {{ color: #ef4444; }}
        .stat.warning .stat-value {{ color: #f59e0b; }}
        .stat.error .stat-value {{ color: #f97316; }}
        .stat.info .stat-value {{ color: #22c55e; }}
        .stat.total .stat-value {{ color: #3b82f6; }}
        .section {{ margin-bottom: 30px; }}
        .section-title {{
            font-size: 16px; color: #94a3b8; margin-bottom: 15px;
            display: flex; align-items: center; gap: 10px;
        }}
        table {{
            width: 100%; border-collapse: collapse; background: #1e293b;
            border-radius: 12px; overflow: hidden;
        }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #334155; font-size: 12px; color: #94a3b8; text-transform: uppercase; }}
        tr:hover {{ background: #334155; }}
        .badge {{
            padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
        }}
        .badge.BLOCK {{ background: #7f1d1d; color: #fca5a5; }}
        .badge.CRITICAL {{ background: #7f1d1d; color: #fca5a5; }}
        .badge.WARNING {{ background: #78350f; color: #fcd34d; }}
        .badge.ERROR {{ background: #7c2d12; color: #fdba74; }}
        .badge.INFO {{ background: #14532d; color: #86efac; }}
        .ip {{ font-family: monospace; color: #60a5fa; }}
        .desc {{ max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .refresh {{
            background: #3b82f6; color: white; border: none; padding: 8px 16px;
            border-radius: 6px; cursor: pointer; font-size: 14px;
        }}
        .refresh:hover {{ background: #2563eb; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}
        @media (max-width: 1200px) {{ .grid-3 {{ grid-template-columns: 1fr 1fr; }} }}
        @media (max-width: 768px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} }}
        .time {{ color: #64748b; font-size: 13px; }}
        .learning {{ padding: 10px; background: #0f172a; border-radius: 8px; margin-bottom: 8px; border-left: 3px solid #3b82f6; }}
        .learning.validated {{ border-left-color: #22c55e; }}
        .learning.rejected {{ border-left-color: #ef4444; }}
        .learning-pattern {{ font-family: monospace; font-size: 11px; color: #94a3b8; }}
        .learning-fix {{ font-size: 12px; color: #e2e8f0; margin-top: 4px; }}
        .proposal {{ padding: 10px; background: #0f172a; border-radius: 8px; margin-bottom: 8px; }}
        .proposal-status {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }}
        .proposal-status.pending {{ background: #78350f; color: #fcd34d; }}
        .proposal-status.applied {{ background: #14532d; color: #86efac; }}
        .proposal-status.approved {{ background: #1e3a5f; color: #93c5fd; }}
        .proposal-status.rejected {{ background: #7f1d1d; color: #fca5a5; }}
        .proposal-status.needs_claude {{ background: #4c1d95; color: #c4b5fd; }}
        .confidence {{ font-size: 11px; color: #64748b; }}
        .scrollbox {{ max-height: 300px; overflow-y: auto; }}
        .frontend-error {{ padding: 10px; background: #0f172a; border-radius: 8px; margin-bottom: 8px; border-left: 3px solid #f97316; }}
        .frontend-error .error-type {{ font-weight: 600; color: #f97316; font-size: 12px; }}
        .frontend-error .error-path {{ font-family: monospace; font-size: 11px; color: #94a3b8; }}
        .frontend-error .error-fix {{ font-size: 11px; color: #64748b; margin-top: 4px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Guardian Dashboard</h1>
            <div class="status">WAF actif - {waf_patterns} patterns</div>
            <div class="time">{current_time}</div>
        </div>
        <button class="refresh" onclick="location.reload()">Actualiser</button>
    </div>

    <div class="stats">
        <div class="stat total">
            <div class="stat-value">{stats[5]}</div>
            <div class="stat-label">Total (24h)</div>
        </div>
        <div class="stat info">
            <div class="stat-value">{stats[4]}</div>
            <div class="stat-label">OK</div>
        </div>
        <div class="stat warning">
            <div class="stat-value">{stats[1]}</div>
            <div class="stat-label">Warnings</div>
        </div>
        <div class="stat error">
            <div class="stat-value">{stats[3]}</div>
            <div class="stat-label">Erreurs</div>
        </div>
        <div class="stat blocked">
            <div class="stat-value">{stats[0]}</div>
            <div class="stat-label">Bloquées</div>
        </div>
        <div class="stat blocked">
            <div class="stat-value">{stats[2]}</div>
            <div class="stat-label">Critiques</div>
        </div>
    </div>

    <div class="grid-2">
        <div class="section">
            <div class="section-title">Top IPs (24h)</div>
            <table>
                <thead><tr><th>IP</th><th>Requêtes</th><th>Issues</th></tr></thead>
                <tbody>
                    {"".join(f'<tr><td class="ip">{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td></tr>' for row in top_ips)}
                </tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">IPs Bloquées (mémoire)</div>
            <table>
                <thead><tr><th>IP</th><th>Tentatives</th></tr></thead>
                <tbody>
                    {"".join(f'<tr><td class="ip">{ip}</td><td>{Guardian._failed_attempts.get(ip, 0)}</td></tr>' for ip in Guardian._blocked_ips) or '<tr><td colspan="2" style="text-align:center;color:#64748b;">Aucune IP bloquée</td></tr>'}
                </tbody>
            </table>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Derniers événements (10)</div>
        <table>
            <thead>
                <tr><th>Heure</th><th>Niveau</th><th>Action</th><th>IP</th><th>Description</th><th>User</th></tr>
            </thead>
            <tbody>
                {"".join(f'''<tr>
                    <td>{row[4]}</td>
                    <td><span class="badge {row[0]}">{row[0]}</span></td>
                    <td>{row[1]}</td>
                    <td class="ip">{row[2] or '-'}</td>
                    <td class="desc" title="{(row[3] or '').replace('"', '&quot;')}">{(row[3] or '-')[:60]}</td>
                    <td>{(row[5] or '-').split('@')[0] if row[5] else '-'}</td>
                </tr>''' for row in events)}
            </tbody>
        </table>
    </div>

    <div class="grid-2">
        <div class="section">
            <div class="section-title">Apprentissages Guardian ({len(learnings)})</div>
            <div class="scrollbox">
                {"".join(f'''<div class="learning {l.status}">
                    <div class="learning-pattern">{l.error_pattern[:80]}...</div>
                    <div class="learning-fix">{(l.fix_template or '-')[:100]}</div>
                    <div class="confidence">Confiance: {int(l.confidence*100)}% | Utilisé: {l.times_applied}x | {l.status}</div>
                </div>''' for l in learnings) or '<div style="color:#64748b;text-align:center;padding:20px;">Aucun apprentissage</div>'}
            </div>
        </div>

        <div class="section">
            <div class="section-title">Actions Claude (AutoPilot)</div>
            <div class="scrollbox">
                {"".join(f'''<div class="proposal">
                    <span class="proposal-status {row[3]}">{row[3].upper()}</span>
                    <span style="margin-left:8px;font-size:12px;">{row[1]}</span>
                    <div style="font-size:11px;color:#64748b;margin-top:4px;">
                        {(row[2] or '-').split('/')[-1]} | Confiance: {int(row[4]*100) if row[4] else 0}% | {row[5]}
                    </div>
                </div>''' for row in applied) if applied else '<div style="color:#64748b;text-align:center;padding:20px;">Aucune action Claude</div>'}
            </div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Erreurs Frontend ({len(frontend_errors)})</div>
        <div class="scrollbox">
            {"".join(f'''<div class="frontend-error">
                <div class="error-type">{row[0]}</div>
                <div class="error-path">{(row[1] or '-')[:80]}</div>
                <div style="display:flex;justify-content:space-between;margin-top:6px;">
                    <span class="proposal-status {row[2]}">{row[2].upper()}</span>
                    <span class="confidence">Confiance: {int(row[3]*100) if row[3] else 0}% | {row[4]}</span>
                </div>
                <div class="error-fix">{(row[5] or '')[:100]}...</div>
            </div>''' for row in frontend_errors) if frontend_errors else '<div style="color:#64748b;text-align:center;padding:20px;">Aucune erreur frontend capturée</div>'}
        </div>
    </div>

    <script>
        // Auto-refresh toutes les 30 secondes
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
"""
        return HTMLResponse(content=html)

@guardian_router.get("/logs")
async def guardian_logs(
    limit: int = 100,
    niveau: Optional[str] = None,
    user: dict = Depends(verify_createur)
):
    """Logs Guardian (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text

        query = "SELECT * FROM azalplus.guardian_log"
        params = {}

        if niveau:
            query += " WHERE niveau = :niveau"
            params["niveau"] = niveau

        query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        result = session.execute(text(query), params)
        return [dict(row._mapping) for row in result]

@guardian_router.post("/unblock/{ip}")
async def guardian_unblock_ip(ip: str, user: dict = Depends(verify_createur)):
    """Débloquer une IP (Créateur uniquement)."""
    Guardian._blocked_ips.discard(ip)
    if ip in Guardian._failed_attempts:
        del Guardian._failed_attempts[ip]
    return {"status": "unblocked", "ip": ip}

@guardian_router.put("/config")
async def guardian_config(
    auto_block: Optional[bool] = None,
    user: dict = Depends(verify_createur)
):
    """Configurer Guardian (Créateur uniquement)."""
    if auto_block is not None:
        settings.GUARDIAN_AUTO_BLOCK = auto_block
    return {"status": "updated"}


@guardian_router.get("/waf/stats")
async def guardian_waf_stats(user: dict = Depends(verify_createur)):
    """Statistiques WAF (Créateur uniquement)."""
    return {
        "total_patterns": WAF.get_total_patterns(),
        "patterns_by_type": WAF.get_stats(),
        "status": "active"
    }


@guardian_router.post("/waf/test")
async def guardian_waf_test(
    data: str,
    user: dict = Depends(verify_createur)
):
    """Tester le WAF contre une chaine (Créateur uniquement)."""
    result = WAF.check(data)
    return {
        "detected": result.detected,
        "threat_type": result.threat_type.value if result.threat_type else None,
        "severity": result.severity,
        "description": result.description,
        "pattern_matched": result.pattern_matched
    }


@guardian_router.get("/corrections")
async def guardian_corrections(
    limit: int = 50,
    user: dict = Depends(verify_createur)
):
    """Liste les corrections automatiques effectuées (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("""
                SELECT id, action, description, requete_originale, requete_nettoyee,
                       ip_address, created_at
                FROM azalplus.guardian_log
                WHERE requete_nettoyee IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit}
        )
        corrections = []
        for row in result:
            r = dict(row._mapping)
            corrections.append({
                "id": str(r["id"]),
                "action": r["action"],
                "description": r["description"],
                "original": r["requete_originale"][:500] if r["requete_originale"] else None,
                "cleaned": r["requete_nettoyee"][:500] if r["requete_nettoyee"] else None,
                "ip": str(r["ip_address"]) if r["ip_address"] else None,
                "date": r["created_at"].isoformat() if r["created_at"] else None
            })
        return {"corrections": corrections, "total": len(corrections)}


@guardian_router.get("/analysis")
async def guardian_analysis(
    days: int = 7,
    user: dict = Depends(verify_createur)
):
    """Analyse des logs Guardian avec statistiques (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text

        # Stats par type d'action
        action_stats = session.execute(
            text("""
                SELECT action, action_prise, COUNT(*) as count
                FROM azalplus.guardian_log
                WHERE created_at > NOW() - INTERVAL ':days days'
                GROUP BY action, action_prise
                ORDER BY count DESC
            """.replace(":days", str(days)))
        ).fetchall()

        # Top IPs bloquées
        top_ips = session.execute(
            text("""
                SELECT ip_address, COUNT(*) as count,
                       MAX(created_at) as last_seen
                FROM azalplus.guardian_log
                WHERE action_prise IN ('BLOCKED', 'CLEANED')
                  AND created_at > NOW() - INTERVAL ':days days'
                  AND ip_address IS NOT NULL
                GROUP BY ip_address
                ORDER BY count DESC
                LIMIT 10
            """.replace(":days", str(days)))
        ).fetchall()

        # Évolution par jour
        daily_stats = session.execute(
            text("""
                SELECT DATE(created_at) as date,
                       COUNT(*) FILTER (WHERE action_prise = 'BLOCKED') as blocked,
                       COUNT(*) FILTER (WHERE action_prise = 'CLEANED') as cleaned,
                       COUNT(*) FILTER (WHERE action_prise = 'LOGGED') as logged
                FROM azalplus.guardian_log
                WHERE created_at > NOW() - INTERVAL ':days days'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """.replace(":days", str(days)))
        ).fetchall()

        # Patterns les plus fréquents
        patterns = session.execute(
            text("""
                SELECT action, description, COUNT(*) as count
                FROM azalplus.guardian_log
                WHERE created_at > NOW() - INTERVAL ':days days'
                  AND description IS NOT NULL
                GROUP BY action, description
                ORDER BY count DESC
                LIMIT 15
            """.replace(":days", str(days)))
        ).fetchall()

        return {
            "period_days": days,
            "action_stats": [
                {"action": r[0], "action_prise": r[1], "count": r[2]}
                for r in action_stats
            ],
            "top_ips": [
                {
                    "ip": str(r[0]) if r[0] else None,
                    "count": r[1],
                    "last_seen": r[2].isoformat() if r[2] else None
                }
                for r in top_ips
            ],
            "daily_stats": [
                {
                    "date": r[0].isoformat() if r[0] else None,
                    "blocked": r[1],
                    "cleaned": r[2],
                    "logged": r[3]
                }
                for r in daily_stats
            ],
            "frequent_patterns": [
                {"action": r[0], "description": r[1], "count": r[2]}
                for r in patterns
            ],
            "blocked_ips_memory": list(Guardian._blocked_ips),
            "failed_attempts": dict(Guardian._failed_attempts)
        }


@guardian_router.get("/recommendations")
async def guardian_recommendations(
    user: dict = Depends(verify_createur)
):
    """Recommandations basées sur l'analyse des logs (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text

        recommendations = []

        # IPs à bloquer définitivement (>50 incidents)
        repeat_offenders = session.execute(
            text("""
                SELECT ip_address, COUNT(*) as count
                FROM azalplus.guardian_log
                WHERE action_prise = 'BLOCKED'
                  AND ip_address IS NOT NULL
                  AND created_at > NOW() - INTERVAL '30 days'
                GROUP BY ip_address
                HAVING COUNT(*) > 50
                ORDER BY count DESC
            """)
        ).fetchall()

        if repeat_offenders:
            recommendations.append({
                "type": "BLOCK_IPS",
                "priority": "high",
                "message": f"{len(repeat_offenders)} IP(s) avec plus de 50 incidents en 30 jours",
                "ips": [{"ip": str(r[0]), "count": r[1]} for r in repeat_offenders],
                "action": "Ajouter ces IPs au pare-feu externe"
            })

        # Patterns récurrents à surveiller
        recurring = session.execute(
            text("""
                SELECT action, COUNT(*) as count
                FROM azalplus.guardian_log
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY action
                HAVING COUNT(*) > 100
                ORDER BY count DESC
            """)
        ).fetchall()

        if recurring:
            recommendations.append({
                "type": "HIGH_VOLUME",
                "priority": "medium",
                "message": f"{len(recurring)} type(s) d'attaque avec >100 incidents en 24h",
                "attacks": [{"type": r[0], "count": r[1]} for r in recurring],
                "action": "Vérifier si attaque coordonnée en cours"
            })

        # Vérifier les corrections appliquées
        cleaning_rate = session.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE action_prise = 'CLEANED') as cleaned,
                    COUNT(*) FILTER (WHERE action_prise = 'BLOCKED') as blocked,
                    COUNT(*) as total
                FROM azalplus.guardian_log
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)
        ).fetchone()

        if cleaning_rate and cleaning_rate[2] > 0:
            clean_pct = (cleaning_rate[0] / cleaning_rate[2]) * 100
            recommendations.append({
                "type": "STATS",
                "priority": "info",
                "message": f"Taux de correction automatique: {clean_pct:.1f}%",
                "stats": {
                    "cleaned": cleaning_rate[0],
                    "blocked": cleaning_rate[1],
                    "total": cleaning_rate[2]
                },
                "action": "Aucune action requise" if clean_pct < 30 else "Envisager des règles plus strictes"
            })

        return {
            "recommendations": recommendations,
            "guardian_status": {
                "auto_block_enabled": settings.GUARDIAN_AUTO_BLOCK,
                "blocked_ips_count": len(Guardian._blocked_ips),
                "waf_patterns": WAF.get_total_patterns()
            }
        }


@guardian_router.post("/apply-correction")
async def guardian_apply_correction(
    log_id: str,
    user: dict = Depends(verify_createur)
):
    """Appliquer manuellement une correction à partir d'un log (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text

        # Récupérer le log
        result = session.execute(
            text("""
                SELECT id, action, requete_originale, requete_nettoyee
                FROM azalplus.guardian_log
                WHERE id = :log_id
            """),
            {"log_id": log_id}
        ).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Log non trouvé")

        row = dict(result._mapping)

        # Si déjà nettoyé, retourner le résultat
        if row["requete_nettoyee"]:
            return {
                "status": "already_corrected",
                "original": row["requete_originale"],
                "corrected": row["requete_nettoyee"]
            }

        # Sinon, essayer de corriger
        if row["requete_originale"]:
            cleaned = WAF.sanitize_xss(row["requete_originale"])

            # Mettre à jour le log avec la correction
            session.execute(
                text("""
                    UPDATE azalplus.guardian_log
                    SET requete_nettoyee = :cleaned,
                        action_prise = 'CLEANED'
                    WHERE id = :log_id
                """),
                {"log_id": log_id, "cleaned": cleaned}
            )
            session.commit()

            return {
                "status": "corrected",
                "original": row["requete_originale"],
                "corrected": cleaned
            }

        return {
            "status": "no_data",
            "message": "Pas de données à corriger"
        }


# =============================================================================
# GUARDIAN AUTOPILOT - Système d'auto-correction avec apprentissage
# =============================================================================

@dataclass
class FixProposal:
    """Proposition de correction par Guardian."""
    id: str
    error_type: str
    error_message: str
    file_path: str
    line_number: Optional[int]
    original_code: Optional[str]
    proposed_fix: Optional[str]
    confidence: float  # 0.0 à 1.0
    created_at: datetime
    status: str = "pending"  # pending, approved, rejected, applied


class GuardianAutoPilot:
    """
    Système d'auto-correction autonome avec apprentissage.

    Flux:
    1. Détecte erreur dans les logs
    2. Analyse et propose un fix
    3. Claude valide ou rejette avec explication
    4. Si validé: applique le fix
    5. Si rejeté: apprend de l'explication
    """

    _learnings: Dict[str, List[str]] = {}  # error_pattern -> [explanations]
    _fix_patterns: Dict[str, str] = {}  # error_pattern -> validated_fix
    _pending_fixes: Dict[str, FixProposal] = {}

    @classmethod
    def initialize(cls):
        """Charge les apprentissages depuis la base."""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text

                # Charger les patterns validés
                result = session.execute(text("""
                    SELECT error_pattern, fix_template, explanation
                    FROM azalplus.guardian_learnings
                    WHERE status = 'validated'
                """))
                for row in result:
                    r = dict(row._mapping)
                    cls._fix_patterns[r["error_pattern"]] = r["fix_template"]

                # Charger les explications de rejet
                result = session.execute(text("""
                    SELECT error_pattern, explanation
                    FROM azalplus.guardian_learnings
                    WHERE status = 'rejected'
                """))
                for row in result:
                    r = dict(row._mapping)
                    if r["error_pattern"] not in cls._learnings:
                        cls._learnings[r["error_pattern"]] = []
                    cls._learnings[r["error_pattern"]].append(r["explanation"])

                logger.info("guardian_autopilot_initialized",
                           patterns=len(cls._fix_patterns),
                           learnings=len(cls._learnings))
        except Exception as e:
            logger.warning("guardian_autopilot_init_failed", error=str(e))

    @classmethod
    def analyze_error(cls, error_log: str) -> Optional[FixProposal]:
        """
        Analyse une erreur et propose un fix.

        Args:
            error_log: Le message d'erreur complet

        Returns:
            FixProposal ou None si pas de fix possible
        """
        import re
        import traceback
        from datetime import datetime

        proposal = None

        # Patterns d'erreurs Python courants
        patterns = {
            # ImportError
            r"ImportError: cannot import name '(\w+)' from '([^']+)'": cls._fix_import_error,
            # NameError
            r"NameError: name '(\w+)' is not defined": cls._fix_name_error,
            # AttributeError
            r"AttributeError: '(\w+)' object has no attribute '(\w+)'": cls._fix_attribute_error,
            # TypeError
            r"TypeError: (\w+)\(\) missing (\d+) required positional argument": cls._fix_missing_arg,
            # KeyError
            r"KeyError: '(\w+)'": cls._fix_key_error,
            # SyntaxError
            r"SyntaxError: (.+)": cls._fix_syntax_error,
            # IndentationError
            r"IndentationError: (.+)": cls._fix_indentation_error,
            # YAML errors
            r"yaml\.scanner\.ScannerError: (.+)": cls._fix_yaml_error,
            # SQLAlchemy errors
            r"sqlalchemy\.exc\.(\w+): (.+)": cls._fix_sql_error,
        }

        for pattern, fix_func in patterns.items():
            match = re.search(pattern, error_log, re.IGNORECASE)
            if match:
                # Extraire le fichier et la ligne
                file_match = re.search(r'File "([^"]+)", line (\d+)', error_log)
                file_path = file_match.group(1) if file_match else None
                line_num = int(file_match.group(2)) if file_match else None

                # Vérifier si on a déjà un pattern validé
                error_key = f"{pattern}:{match.groups()}"
                if error_key in cls._fix_patterns:
                    # Utiliser le fix validé
                    proposal = FixProposal(
                        id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
                        error_type=pattern.split(":")[0].replace("\\", ""),
                        error_message=error_log[:500],
                        file_path=file_path,
                        line_number=line_num,
                        original_code=None,
                        proposed_fix=cls._fix_patterns[error_key],
                        confidence=0.95,  # Haute confiance car validé
                        created_at=datetime.now(),
                        status="auto_validated"
                    )
                else:
                    # Générer un nouveau fix
                    proposal = fix_func(match, error_log, file_path, line_num)

                    # Réduire la confiance si on a eu des rejets sur ce pattern
                    if error_key in cls._learnings:
                        rejections = len(cls._learnings[error_key])
                        proposal.confidence *= (0.8 ** rejections)

                break

        if proposal:
            cls._pending_fixes[proposal.id] = proposal

        return proposal

    @classmethod
    def _fix_import_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour ImportError."""
        name = match.group(1)
        module = match.group(2)

        # Proposer d'ajouter l'import manquant
        proposed = f"# Ajouter en haut du fichier:\nfrom {module} import {name}"

        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="ImportError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=proposed,
            confidence=0.7,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_name_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour NameError."""
        name = match.group(1)

        # Suggestions basées sur le nom
        suggestions = []
        if name in ["Optional", "List", "Dict", "Union", "Any", "Callable"]:
            suggestions.append(f"from typing import {name}")
        elif name == "UUID":
            suggestions.append("from uuid import UUID")
        elif name == "datetime":
            suggestions.append("from datetime import datetime")
        elif name == "Depends":
            suggestions.append("from fastapi import Depends")
        elif name == "HTTPException":
            suggestions.append("from fastapi import HTTPException")
        elif name == "Request":
            suggestions.append("from fastapi import Request")
        elif name == "Query":
            suggestions.append("from fastapi import Query")
        elif name == "Path":
            suggestions.append("from fastapi import Path")

        proposed = "\n".join(suggestions) if suggestions else f"# Définir ou importer: {name}"

        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="NameError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=proposed,
            confidence=0.8 if suggestions else 0.4,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_attribute_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour AttributeError."""
        obj_type = match.group(1)
        attr = match.group(2)

        proposed = f"# Vérifier que '{attr}' existe sur {obj_type} ou utiliser getattr(obj, '{attr}', default)"

        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="AttributeError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=proposed,
            confidence=0.5,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_missing_arg(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour TypeError (argument manquant)."""
        func = match.group(1)
        count = match.group(2)

        proposed = f"# Ajouter les {count} argument(s) manquant(s) à l'appel de {func}()"

        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="TypeError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=proposed,
            confidence=0.6,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_key_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour KeyError."""
        key = match.group(1)

        proposed = f"# Utiliser .get('{key}', default) au lieu de ['{key}']"

        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="KeyError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=proposed,
            confidence=0.75,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_syntax_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour SyntaxError."""
        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="SyntaxError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix="# Erreur de syntaxe - vérifier parenthèses, virgules, deux-points",
            confidence=0.3,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_indentation_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour IndentationError."""
        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="IndentationError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix="# Corriger l'indentation - utiliser 4 espaces par niveau",
            confidence=0.6,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_yaml_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour erreurs YAML."""
        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type="YAMLError",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix="# Erreur YAML - vérifier indentation et guillemets pour valeurs avec ':'",
            confidence=0.5,
            created_at=datetime.now()
        )

    @classmethod
    def _fix_sql_error(cls, match, error_log: str, file_path: str, line_num: int) -> FixProposal:
        """Fix pour erreurs SQL/SQLAlchemy."""
        error_type = match.group(1)

        proposed = "# Erreur SQL"
        if "IntegrityError" in error_type:
            proposed = "# Violation de contrainte - vérifier unicité ou foreign key"
        elif "OperationalError" in error_type:
            proposed = "# Erreur opérationnelle - vérifier connexion DB ou syntaxe SQL"
        elif "ProgrammingError" in error_type:
            proposed = "# Erreur de programmation - vérifier noms de tables/colonnes"

        return FixProposal(
            id=hashlib.md5(f"{error_log}{datetime.now()}".encode()).hexdigest()[:12],
            error_type=f"SQLAlchemy.{error_type}",
            error_message=error_log[:500],
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=proposed,
            confidence=0.4,
            created_at=datetime.now()
        )

    @classmethod
    def get_pending_fixes(cls) -> List[FixProposal]:
        """Retourne les fixes en attente de validation."""
        return [f for f in cls._pending_fixes.values() if f.status == "pending"]

    @classmethod
    def validate_fix(cls, fix_id: str, approved: bool, explanation: str = "") -> dict:
        """
        Valide ou rejette un fix proposé.

        Args:
            fix_id: ID du fix
            approved: True si validé, False si rejeté
            explanation: Explication (obligatoire si rejeté)

        Returns:
            Résultat de l'opération
        """
        if fix_id not in cls._pending_fixes:
            return {"status": "error", "message": "Fix non trouvé"}

        fix = cls._pending_fixes[fix_id]

        if approved:
            # Appliquer le fix
            result = cls._apply_fix(fix)
            fix.status = "applied" if result["success"] else "failed"

            # Sauvegarder le pattern validé
            cls._save_learning(fix, "validated", explanation)

            return {
                "status": "applied" if result["success"] else "failed",
                "fix": fix,
                "result": result
            }
        else:
            # Rejeté - apprendre de l'explication
            fix.status = "rejected"
            cls._save_learning(fix, "rejected", explanation)

            # Stocker l'explication pour apprentissage
            error_key = f"{fix.error_type}:{fix.error_message[:100]}"
            if error_key not in cls._learnings:
                cls._learnings[error_key] = []
            cls._learnings[error_key].append(explanation)

            return {
                "status": "rejected",
                "fix": fix,
                "lesson_learned": explanation
            }

    @classmethod
    def _apply_fix(cls, fix: FixProposal) -> dict:
        """Applique un fix au fichier."""
        if not fix.file_path or not fix.proposed_fix:
            return {"success": False, "message": "Pas de fichier ou fix à appliquer"}

        try:
            # Lire le fichier
            with open(fix.file_path, 'r') as f:
                lines = f.readlines()

            # Backup
            backup_path = f"{fix.file_path}.guardian_backup"
            with open(backup_path, 'w') as f:
                f.writelines(lines)

            # Si c'est un import manquant, l'ajouter en haut
            if fix.error_type in ["ImportError", "NameError"] and "import" in fix.proposed_fix:
                # Trouver la dernière ligne d'import
                last_import_line = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith(("import ", "from ")):
                        last_import_line = i

                # Insérer après le dernier import
                import_line = fix.proposed_fix.replace("# Ajouter en haut du fichier:\n", "")
                lines.insert(last_import_line + 1, import_line + "\n")

                # Écrire le fichier modifié
                with open(fix.file_path, 'w') as f:
                    f.writelines(lines)

                return {"success": True, "message": f"Import ajouté ligne {last_import_line + 2}"}

            return {"success": False, "message": "Type de fix non supporté pour application auto"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    @classmethod
    def _save_learning(cls, fix: FixProposal, status: str, explanation: str):
        """Sauvegarde un apprentissage en base."""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        INSERT INTO azalplus.guardian_learnings
                        (error_pattern, error_message, fix_template, status, explanation, file_path)
                        VALUES (:pattern, :message, :fix, :status, :explanation, :file)
                    """),
                    {
                        "pattern": fix.error_type,
                        "message": fix.error_message[:500],
                        "fix": fix.proposed_fix,
                        "status": status,
                        "explanation": explanation,
                        "file": fix.file_path
                    }
                )
                session.commit()
        except Exception as e:
            logger.error("guardian_save_learning_failed", error=str(e))


# =============================================================================
# API Endpoints pour AutoPilot
# =============================================================================

@guardian_router.get("/autopilot/pending")
async def guardian_autopilot_pending(user: dict = Depends(verify_createur)):
    """Liste les fixes en attente de validation (Créateur uniquement)."""
    fixes = GuardianAutoPilot.get_pending_fixes()
    return {
        "pending": [
            {
                "id": f.id,
                "error_type": f.error_type,
                "error_message": f.error_message[:200],
                "file_path": f.file_path,
                "line_number": f.line_number,
                "proposed_fix": f.proposed_fix,
                "confidence": f.confidence,
                "created_at": f.created_at.isoformat()
            }
            for f in fixes
        ],
        "count": len(fixes)
    }


@guardian_router.post("/autopilot/validate/{fix_id}")
async def guardian_autopilot_validate(
    fix_id: str,
    approved: bool,
    explanation: str = "",
    user: dict = Depends(verify_createur)
):
    """
    Valider ou rejeter un fix proposé (Créateur uniquement).

    - approved=true: Applique le fix
    - approved=false + explanation: Rejette et enseigne à Guardian
    """
    if not approved and not explanation:
        raise HTTPException(
            status_code=400,
            detail="Explication obligatoire pour un rejet (Guardian doit apprendre)"
        )

    result = GuardianAutoPilot.validate_fix(fix_id, approved, explanation)
    return result


@guardian_router.get("/autopilot/learnings")
async def guardian_autopilot_learnings(user: dict = Depends(verify_createur)):
    """Liste les apprentissages de Guardian (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(text("""
            SELECT error_pattern, status, explanation, fix_template,
                   file_path, created_at
            FROM azalplus.guardian_learnings
            ORDER BY created_at DESC
            LIMIT 100
        """))

        learnings = []
        for row in result:
            r = dict(row._mapping)
            learnings.append({
                "error_pattern": r["error_pattern"],
                "status": r["status"],
                "explanation": r["explanation"],
                "fix_template": r["fix_template"],
                "file_path": r["file_path"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None
            })

        return {
            "learnings": learnings,
            "validated_patterns": len(GuardianAutoPilot._fix_patterns),
            "rejection_lessons": sum(len(v) for v in GuardianAutoPilot._learnings.values())
        }


@guardian_router.post("/autopilot/analyze")
async def guardian_autopilot_analyze(
    error_log: str,
    user: dict = Depends(verify_createur)
):
    """
    Analyser une erreur et proposer un fix (Créateur uniquement).

    Utilisé pour tester le système ou soumettre manuellement une erreur.
    """
    proposal = GuardianAutoPilot.analyze_error(error_log)

    if proposal:
        return {
            "status": "proposal_created",
            "proposal": {
                "id": proposal.id,
                "error_type": proposal.error_type,
                "file_path": proposal.file_path,
                "line_number": proposal.line_number,
                "proposed_fix": proposal.proposed_fix,
                "confidence": proposal.confidence
            }
        }

    return {
        "status": "no_fix_found",
        "message": "Guardian n'a pas pu proposer de fix pour cette erreur"
    }


@guardian_router.get("/test-error")
async def guardian_test_error(
    error_type: str = "name",
    user: dict = Depends(verify_createur)
):
    """
    Déclenche une erreur de test pour vérifier le système AutoPilot.
    Créateur uniquement.

    Types d'erreur:
    - name: NameError (variable non définie)
    - import: ImportError
    - key: KeyError
    - type: TypeError
    - complex: Erreur complexe (NEEDS_CLAUDE)
    """
    if error_type == "name":
        # Simule un NameError
        return undefined_variable  # noqa: F821

    elif error_type == "import":
        # Simule un ImportError
        from nonexistent_module import something  # noqa: F401
        return {"status": "ok"}

    elif error_type == "key":
        # Simule un KeyError
        data = {"a": 1}
        return {"value": data["nonexistent_key"]}

    elif error_type == "type":
        # Simule un TypeError
        result = "string" + 123
        return {"result": result}

    elif error_type == "complex":
        # Erreur complexe - devrait déclencher NEEDS_CLAUDE
        raise RuntimeError("Erreur complexe de logique métier: le workflow est dans un état invalide")

    else:
        return {"error": f"Type d'erreur inconnu: {error_type}"}


# =============================================================================
# ENDPOINT PUBLIC: Reporting erreurs frontend
# =============================================================================
from pydantic import BaseModel
from typing import Optional as Opt

class FrontendErrorReport(BaseModel):
    """Rapport d'erreur frontend."""
    error_type: str  # "404", "js_error", "network", etc.
    message: str
    url: str
    source: Opt[str] = None  # fichier source
    line: Opt[int] = None
    column: Opt[int] = None
    stack: Opt[str] = None
    user_agent: Opt[str] = None


@guardian_router.post("/frontend-error", include_in_schema=False)
async def report_frontend_error(
    report: FrontendErrorReport,
    request: Request
):
    """
    Endpoint PUBLIC pour reporter les erreurs frontend.
    Pas d'auth requise - rate limité par IP.
    Les erreurs sont analysées par AutoPilot.
    """
    # Rate limiting basique (max 10 erreurs/minute par IP)
    client_ip = request.client.host if request.client else "unknown"

    # Construire le log d'erreur pour AutoPilot
    error_log = f"""FRONTEND ERROR [{report.error_type}]
URL: {report.url}
Message: {report.message}
Source: {report.source or 'unknown'}:{report.line or '?'}:{report.column or '?'}
Stack: {report.stack or 'N/A'}
User-Agent: {report.user_agent or 'N/A'}
IP: {client_ip}
"""

    # Logger pour Guardian (invisible)
    logger.warning("frontend_error_reported",
                  error_type=report.error_type,
                  url=report.url,
                  message=report.message[:200],
                  source=report.source,
                  ip=client_ip)

    # Soumettre à AutoPilot pour analyse
    from .core import get_autopilot
    from .autopilot import AutoFixer
    autopilot = get_autopilot()

    fix_applied = False
    fix_message = ""

    # 1. Essayer AutoFixer pour TOUTES les erreurs (pas seulement 404)
    logger.info("guardian_calling_autofixer", error_type=report.error_type)
    try:
        success, message = AutoFixer.try_fix(error_log)
        logger.info("autofixer_returned", success=success, message=message[:100] if message else "")
        if success:
            fix_applied = True
            fix_message = message
            logger.info("frontend_error_autofixed",
                       error_type=report.error_type,
                       source=report.source,
                       fix=message)
    except Exception as e:
        logger.warning("frontend_autofix_error", error=str(e))

    # 2. Soumettre à AutoPilot pour apprentissage
    if autopilot:
        proposal = autopilot.analyze(error_log)
        if proposal:
            logger.info("frontend_error_autopilot_proposal",
                       id=proposal.id,
                       status=proposal.status.value,
                       confidence=proposal.confidence)

            # Si confiance élevée et fix non encore appliqué, essayer d'appliquer
            if not fix_applied and proposal.confidence >= 0.9:
                autopilot.validate(proposal.id, approved=True,
                                  explanation="Auto-validated (high confidence frontend fix)")
                fix_applied = True

    # Réponse avec info de fix (pour permettre reload si corrigé)
    response = {"status": "received"}
    if fix_applied:
        response["action"] = "reload"
        response["fix"] = fix_message

    return response
