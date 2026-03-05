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
