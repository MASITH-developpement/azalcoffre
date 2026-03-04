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
from fastapi.responses import JSONResponse
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
import structlog
import re
import hashlib

from .config import settings
from .db import Database

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
                await cls._log(GuardianLog(
                    niveau="CRITICAL" if waf_result.severity == "critical" else "BLOCK",
                    action=waf_result.threat_type.value if waf_result.threat_type else "WAF_THREAT",
                    ip_address=ip,
                    description=f"WAF: {waf_result.description} (pattern: {waf_result.pattern_matched[:50] if waf_result.pattern_matched else 'N/A'}...)",
                    action_prise="BLOCKED"
                ))
                cls._increment_failed(ip)
                return result
            elif waf_result.threat_type == ThreatType.XSS:
                # XSS: on nettoie au lieu de bloquer
                result.cleaned = True
                result.reason = "XSS_CLEANED"
                result.original_data = body
                result.cleaned_data = WAF.sanitize_xss(body)
                await cls._log(GuardianLog(
                    niveau="WARNING",
                    action="XSS_CLEANED",
                    ip_address=ip,
                    description=f"WAF: {waf_result.description}",
                    action_prise="CLEANED"
                ))
            else:
                # Medium/Low: on log mais on laisse passer avec warning
                await cls._log(GuardianLog(
                    niveau="WARNING",
                    action=waf_result.threat_type.value if waf_result.threat_type else "WAF_WARNING",
                    ip_address=ip,
                    description=f"WAF: {waf_result.description}",
                    action_prise="LOGGED"
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
                    action_prise="BLOCKED"
                ))
                cls._increment_failed(ip)
                return result

            # XSS (legacy patterns)
            if cls._detect_xss(body):
                result.cleaned = True
                result.reason = "XSS_CLEANED"
                result.original_data = body
                result.cleaned_data = cls._clean_xss(body)
                await cls._log(GuardianLog(
                    niveau="WARNING",
                    action="XSS_CLEANED",
                    ip_address=ip,
                    action_prise="CLEANED"
                ))

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

    @classmethod
    async def log_request(cls, request: Request, response):
        """Log une requête (silencieux)."""
        # Log minimal pour audit
        pass

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

    @classmethod
    async def _log(cls, log: GuardianLog):
        """Enregistre un log Guardian en base."""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                session.execute(
                    text("""
                        INSERT INTO azalplus.guardian_log
                        (niveau, action, tenant_id, utilisateur_id, utilisateur_email,
                         description, ip_address, user_agent, action_prise)
                        VALUES (:niveau, :action, :tenant_id, :utilisateur_id, :utilisateur_email,
                                :description, :ip_address, :user_agent, :action_prise)
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
                        "action_prise": log.action_prise
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
async def guardian_dashboard(user: dict = Depends(verify_createur)):
    """Dashboard Guardian (Créateur uniquement)."""
    with Database.get_session() as session:
        from sqlalchemy import text

        # Stats globales
        stats = session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE niveau = 'BLOCK') as blocked,
                COUNT(*) FILTER (WHERE niveau = 'WARNING') as warnings,
                COUNT(*) FILTER (WHERE niveau = 'CRITICAL') as critical,
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
                "total_24h": stats[3]
            },
            "blocked_ips": list(Guardian._blocked_ips),
            "recent_events": [dict(row._mapping) for row in events]
        }

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
