# =============================================================================
# AZALPLUS - WAF (Web Application Firewall)
# =============================================================================
"""
WAF - Protection contre les attaques web courantes.

Patterns de detection pour:
- SQL Injection (15+ patterns)
- XSS (12+ patterns)
- Path Traversal (8+ patterns)
- Command Injection (10+ patterns)
- SSRF (5+ patterns)
- XXE (5+ patterns)
- LDAP Injection (5+ patterns)

Total: 60+ patterns de detection
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class ThreatType(str, Enum):
    """Types de menaces detectees."""
    SQL_INJECTION = "SQL_INJECTION"
    XSS = "XSS"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    COMMAND_INJECTION = "COMMAND_INJECTION"
    SSRF = "SSRF"
    XXE = "XXE"
    LDAP_INJECTION = "LDAP_INJECTION"
    HEADER_INJECTION = "HEADER_INJECTION"
    TEMPLATE_INJECTION = "TEMPLATE_INJECTION"
    NOSQL_INJECTION = "NOSQL_INJECTION"


@dataclass
class ThreatDetection:
    """Resultat de detection de menace."""
    detected: bool
    threat_type: Optional[ThreatType] = None
    pattern_matched: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical
    description: str = ""


# =============================================================================
# SQL INJECTION PATTERNS (15+)
# =============================================================================
SQL_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    # (pattern, severity, description)
    (r"(\%27)|(\')|(\-\-)|(\%23)|(#)", "high", "Basic SQL special chars"),
    (r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))", "high", "SQL assignment injection"),
    (r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))", "critical", "SQL OR injection"),
    (r"((\%27)|(\'))union", "critical", "UNION-based injection"),
    (r"exec(\s|\+)+(s|x)p\w+", "critical", "SQL exec procedure"),
    (r"UNION(\s+)SELECT", "critical", "UNION SELECT injection"),
    (r"INSERT(\s+)INTO", "high", "INSERT injection"),
    (r"DELETE(\s+)FROM", "critical", "DELETE injection"),
    (r"DROP(\s+)(TABLE|DATABASE)", "critical", "DROP injection"),
    (r"UPDATE(\s+)\w+(\s+)SET", "high", "UPDATE injection"),
    (r"SELECT(\s+).+(\s+)FROM", "medium", "SELECT injection"),
    (r"TRUNCATE(\s+)TABLE", "critical", "TRUNCATE injection"),
    (r"ALTER(\s+)TABLE", "critical", "ALTER TABLE injection"),
    (r"GRANT(\s+)ALL", "critical", "GRANT injection"),
    (r"WAITFOR(\s+)DELAY", "high", "Time-based blind SQLi"),
    (r"BENCHMARK\s*\(", "high", "MySQL benchmark injection"),
    (r"SLEEP\s*\(", "high", "Sleep-based blind SQLi"),
    (r"pg_sleep\s*\(", "high", "PostgreSQL sleep injection"),
    (r";\s*--", "medium", "Comment termination"),
    (r"\/\*.*\*\/", "low", "SQL block comment"),
]

# =============================================================================
# XSS PATTERNS (12+)
# =============================================================================
XSS_PATTERNS: List[Tuple[str, str, str]] = [
    (r"<script[^>]*>", "critical", "Script tag injection"),
    (r"javascript\s*:", "high", "JavaScript protocol"),
    (r"on\w+\s*=", "high", "Event handler injection"),
    (r"<iframe[^>]*>", "high", "Iframe injection"),
    (r"<object[^>]*>", "high", "Object tag injection"),
    (r"<embed[^>]*>", "high", "Embed tag injection"),
    (r"<svg[^>]*onload", "high", "SVG onload injection"),
    (r"<img[^>]*onerror", "high", "IMG onerror injection"),
    (r"<body[^>]*onload", "high", "Body onload injection"),
    (r"expression\s*\(", "medium", "CSS expression"),
    (r"vbscript\s*:", "high", "VBScript protocol"),
    (r"data\s*:\s*text\/html", "high", "Data URI HTML"),
    (r"<link[^>]*href\s*=", "medium", "Link injection"),
    (r"<meta[^>]*http-equiv", "medium", "Meta redirect"),
    (r"<base[^>]*href", "high", "Base tag injection"),
]

# =============================================================================
# PATH TRAVERSAL PATTERNS (8+)
# =============================================================================
PATH_TRAVERSAL_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\.\./", "high", "Directory traversal ../"),
    (r"\.\.\\", "high", "Directory traversal ..\\"),
    (r"%2e%2e%2f", "high", "URL encoded ../"),
    (r"%2e%2e/", "high", "Partial URL encoded"),
    (r"\.\.%2f", "high", "Mixed encoding"),
    (r"%252e%252e%252f", "high", "Double URL encoded"),
    (r"/etc/passwd", "critical", "Linux passwd access"),
    (r"/etc/shadow", "critical", "Linux shadow access"),
    (r"c:\\windows", "high", "Windows path access"),
    (r"/proc/self", "high", "Linux proc access"),
    (r"file://", "high", "File protocol"),
]

# =============================================================================
# COMMAND INJECTION PATTERNS (10+)
# =============================================================================
COMMAND_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    (r";\s*\w+", "high", "Command chaining with ;"),
    (r"\|\s*\w+", "high", "Pipe command"),
    (r"&\s*\w+", "high", "Background command"),
    (r"`[^`]+`", "critical", "Backtick execution"),
    (r"\$\([^)]+\)", "critical", "Command substitution"),
    (r"\|\|", "medium", "OR command chaining"),
    (r"&&", "medium", "AND command chaining"),
    (r">\s*/", "high", "Redirect to root"),
    (r"curl\s+", "high", "Curl command"),
    (r"wget\s+", "high", "Wget command"),
    (r"nc\s+-", "critical", "Netcat command"),
    (r"bash\s+-", "critical", "Bash execution"),
    (r"/bin/sh", "critical", "Shell execution"),
    (r"python\s+-c", "high", "Python execution"),
]

# =============================================================================
# SSRF PATTERNS (5+)
# =============================================================================
SSRF_PATTERNS: List[Tuple[str, str, str]] = [
    (r"127\.0\.0\.1", "high", "Localhost IPv4"),
    (r"localhost", "high", "Localhost hostname"),
    (r"0\.0\.0\.0", "high", "All interfaces"),
    (r"169\.254\.", "critical", "AWS metadata IP"),
    (r"metadata\.google", "critical", "GCP metadata"),
    (r"::1", "high", "Localhost IPv6"),
    (r"10\.\d+\.\d+\.\d+", "medium", "Private IP 10.x"),
    (r"172\.(1[6-9]|2\d|3[01])\.", "medium", "Private IP 172.x"),
    (r"192\.168\.", "medium", "Private IP 192.168.x"),
    (r"file:///", "critical", "File protocol SSRF"),
]

# =============================================================================
# XXE PATTERNS (5+)
# =============================================================================
XXE_PATTERNS: List[Tuple[str, str, str]] = [
    (r"<!DOCTYPE[^>]*\[", "critical", "DOCTYPE with DTD"),
    (r"<!ENTITY", "critical", "XML entity definition"),
    (r"SYSTEM\s+['\"]", "critical", "External entity"),
    (r"PUBLIC\s+['\"]", "high", "Public entity"),
    (r"%\w+;", "high", "Parameter entity reference"),
    (r"<!ATTLIST", "medium", "Attribute list declaration"),
]

# =============================================================================
# LDAP INJECTION PATTERNS (5+)
# =============================================================================
LDAP_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\)\s*\(", "high", "LDAP filter injection"),
    (r"\*\)", "high", "LDAP wildcard"),
    (r"\|\s*\(", "high", "LDAP OR operator"),
    (r"&\s*\(", "high", "LDAP AND operator"),
    (r"!\s*\(", "high", "LDAP NOT operator"),
    (r"\\00", "critical", "LDAP null byte"),
]

# =============================================================================
# HEADER INJECTION PATTERNS
# =============================================================================
HEADER_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\r\n", "critical", "CRLF injection"),
    (r"%0d%0a", "critical", "URL encoded CRLF"),
    (r"\\r\\n", "high", "Escaped CRLF"),
    (r"Set-Cookie:", "critical", "Cookie injection"),
    (r"Location:", "high", "Redirect injection"),
]

# =============================================================================
# TEMPLATE INJECTION PATTERNS
# =============================================================================
TEMPLATE_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\{\{.*\}\}", "high", "Jinja2/Twig template"),
    (r"\$\{.*\}", "high", "Expression language"),
    (r"<%.*%>", "high", "JSP/ASP template"),
    (r"#\{.*\}", "high", "Ruby/EL template"),
    (r"\[\[.*\]\]", "medium", "Thymeleaf template"),
]

# =============================================================================
# NOSQL INJECTION PATTERNS
# =============================================================================
NOSQL_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\$where", "critical", "MongoDB $where"),
    (r"\$ne", "high", "MongoDB $ne operator"),
    (r"\$gt", "medium", "MongoDB $gt operator"),
    (r"\$regex", "high", "MongoDB $regex"),
    (r"\$or\s*:", "high", "MongoDB $or"),
    (r"{\s*\$", "high", "MongoDB operator syntax"),
]


# =============================================================================
# WAF CLASS
# =============================================================================
class WAF:
    """Web Application Firewall."""

    # Tous les patterns regroupes
    ALL_PATTERNS: Dict[ThreatType, List[Tuple[str, str, str]]] = {
        ThreatType.SQL_INJECTION: SQL_INJECTION_PATTERNS,
        ThreatType.XSS: XSS_PATTERNS,
        ThreatType.PATH_TRAVERSAL: PATH_TRAVERSAL_PATTERNS,
        ThreatType.COMMAND_INJECTION: COMMAND_INJECTION_PATTERNS,
        ThreatType.SSRF: SSRF_PATTERNS,
        ThreatType.XXE: XXE_PATTERNS,
        ThreatType.LDAP_INJECTION: LDAP_INJECTION_PATTERNS,
        ThreatType.HEADER_INJECTION: HEADER_INJECTION_PATTERNS,
        ThreatType.TEMPLATE_INJECTION: TEMPLATE_INJECTION_PATTERNS,
        ThreatType.NOSQL_INJECTION: NOSQL_INJECTION_PATTERNS,
    }

    # Patterns compiles (cache)
    _compiled_patterns: Dict[ThreatType, List[Tuple[re.Pattern, str, str]]] = {}

    @classmethod
    def initialize(cls):
        """Compile tous les patterns pour de meilleures performances."""
        for threat_type, patterns in cls.ALL_PATTERNS.items():
            cls._compiled_patterns[threat_type] = [
                (re.compile(pattern, re.IGNORECASE), severity, desc)
                for pattern, severity, desc in patterns
            ]

        total = sum(len(p) for p in cls._compiled_patterns.values())
        logger.info("waf_initialized", total_patterns=total)

    @classmethod
    def check(cls, data: str) -> ThreatDetection:
        """
        Verifie une chaine contre tous les patterns WAF.

        Args:
            data: Donnee a verifier (body, query params, headers, etc.)

        Returns:
            ThreatDetection avec le resultat
        """
        if not data:
            return ThreatDetection(detected=False)

        # Verifier chaque categorie de menace
        for threat_type, patterns in cls._compiled_patterns.items():
            for pattern, severity, description in patterns:
                if pattern.search(data):
                    return ThreatDetection(
                        detected=True,
                        threat_type=threat_type,
                        pattern_matched=pattern.pattern,
                        severity=severity,
                        description=description
                    )

        return ThreatDetection(detected=False)

    @classmethod
    def check_specific(cls, data: str, threat_type: ThreatType) -> ThreatDetection:
        """
        Verifie une chaine contre un type specifique de menace.

        Args:
            data: Donnee a verifier
            threat_type: Type de menace a detecter

        Returns:
            ThreatDetection avec le resultat
        """
        if not data or threat_type not in cls._compiled_patterns:
            return ThreatDetection(detected=False)

        for pattern, severity, description in cls._compiled_patterns[threat_type]:
            if pattern.search(data):
                return ThreatDetection(
                    detected=True,
                    threat_type=threat_type,
                    pattern_matched=pattern.pattern,
                    severity=severity,
                    description=description
                )

        return ThreatDetection(detected=False)

    @classmethod
    def sanitize_xss(cls, data: str) -> str:
        """
        Nettoie les tentatives XSS d'une chaine.

        Args:
            data: Donnee a nettoyer

        Returns:
            Donnee nettoyee
        """
        import html
        return html.escape(data)

    @classmethod
    def get_stats(cls) -> Dict[str, int]:
        """Retourne les statistiques des patterns."""
        return {
            threat_type.value: len(patterns)
            for threat_type, patterns in cls._compiled_patterns.items()
        }

    @classmethod
    def get_total_patterns(cls) -> int:
        """Retourne le nombre total de patterns."""
        return sum(len(p) for p in cls._compiled_patterns.values())


# Initialiser au chargement du module
WAF.initialize()
