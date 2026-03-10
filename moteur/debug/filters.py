# =============================================================================
# AZALPLUS - Simon Response Filters
# =============================================================================
"""
Filtrage des réponses de Simon pour bloquer tout code ou information technique.
Même si le prompt est contourné, ce filtre côté serveur bloque les réponses interdites.
"""

import re
from typing import Tuple, Optional
import structlog

logger = structlog.get_logger()


# =============================================================================
# Patterns de détection de code
# =============================================================================
CODE_PATTERNS = [
    # Blocs de code markdown
    r'```[\s\S]*?```',
    r'`[^`]+`',

    # Python
    r'\bdef\s+\w+\s*\(',
    r'\bclass\s+\w+[:\(]',
    r'\bimport\s+\w+',
    r'\bfrom\s+\w+\s+import',
    r'\basync\s+def\s+',
    r'\bawait\s+\w+',
    r'\blambda\s*:',
    r'self\.\w+',
    r'__\w+__',

    # JavaScript/TypeScript
    r'\bfunction\s+\w+\s*\(',
    r'\bconst\s+\w+\s*=',
    r'\blet\s+\w+\s*=',
    r'\bvar\s+\w+\s*=',
    r'=>\s*\{',
    r'export\s+(default\s+)?',

    # SQL
    r'\bSELECT\s+.+\s+FROM\b',
    r'\bINSERT\s+INTO\b',
    r'\bUPDATE\s+\w+\s+SET\b',
    r'\bDELETE\s+FROM\b',
    r'\bCREATE\s+TABLE\b',
    r'\bALTER\s+TABLE\b',

    # YAML/Config
    r'^\s*\w+:\s*$',
    r'^\s*-\s+\w+:',

    # Shell
    r'\$\s*\(',
    r'\bsudo\s+',
    r'\bchmod\s+',
    r'\bgrep\s+',
    r'\bsed\s+',
    r'\bawk\s+',
]

# =============================================================================
# Patterns de fichiers/chemins
# =============================================================================
FILE_PATTERNS = [
    # Extensions de fichiers
    r'\w+\.(py|js|ts|tsx|jsx|yml|yaml|json|sql|sh|bash|css|html|md)\b',

    # Chemins
    r'/home/\w+',
    r'/app/\w+',
    r'/var/\w+',
    r'/etc/\w+',
    r'\./\w+',
    r'\.\./\w+',
    r'[A-Z]:\\',

    # Lignes de code
    r'ligne\s+\d+',
    r'line\s+\d+',
    r':\d+:\d+',  # file:line:col
]

# =============================================================================
# Patterns techniques interdits
# =============================================================================
TECHNICAL_PATTERNS = [
    # Frameworks/libs
    r'\bFastAPI\b',
    r'\bSQLAlchemy\b',
    r'\bPydantic\b',
    r'\bReact\b',
    r'\bVue\b',
    r'\bDjango\b',
    r'\bFlask\b',

    # DB
    r'\bPostgreSQL\b',
    r'\bRedis\b',
    r'\bMongoDB\b',

    # Termes techniques
    r'\bendpoint\b',
    r'\bmiddleware\b',
    r'\bquery\b',
    r'\bschema\b',
    r'\bmodel\b',
    r'\brouter\b',
    r'\bcontroller\b',
    r'\bservice\b',
    r'\brepository\b',
]

# =============================================================================
# Patterns de bypass tentés
# =============================================================================
BYPASS_PATTERNS = [
    r'ignore\s+(les\s+)?instructions',
    r'oublie\s+(les\s+)?règles',
    r'forget\s+(the\s+)?rules',
    r'ignore\s+(the\s+)?instructions',
    r'tu\s+es\s+(maintenant|désormais)',
    r'you\s+are\s+now',
    r'nouveau\s+rôle',
    r'new\s+role',
    r'mode\s+développeur',
    r'developer\s+mode',
    r'admin\s+mode',
    r'jailbreak',
    r'DAN\b',
]


# =============================================================================
# Fonction principale de filtrage
# =============================================================================
def filter_simon_response(response: str) -> Tuple[bool, str, Optional[str]]:
    """
    Filtre la réponse de Simon.

    Returns:
        Tuple[bool, str, Optional[str]]:
            - allowed: True si la réponse est autorisée
            - response: La réponse (originale si ok, message de refus sinon)
            - violation: Type de violation détectée (ou None)
    """

    response_lower = response.lower()

    # 1. Vérifier les tentatives de bypass
    for pattern in BYPASS_PATTERNS:
        if re.search(pattern, response_lower, re.IGNORECASE):
            logger.warning(
                "simon_bypass_detected",
                pattern=pattern,
                response_preview=response[:100]
            )
            return False, "Cette réponse a été bloquée.", "bypass"

    # 2. Vérifier les patterns de code
    for pattern in CODE_PATTERNS:
        if re.search(pattern, response, re.IGNORECASE | re.MULTILINE):
            logger.warning(
                "simon_code_detected",
                pattern=pattern,
                response_preview=response[:100]
            )
            return False, "Cette réponse contenait du code et a été bloquée.", "code"

    # 3. Vérifier les fichiers/chemins
    for pattern in FILE_PATTERNS:
        if re.search(pattern, response, re.IGNORECASE):
            logger.warning(
                "simon_file_detected",
                pattern=pattern,
                response_preview=response[:100]
            )
            return False, "Cette réponse contenait des références techniques et a été bloquée.", "file"

    # 4. Vérifier les termes techniques (moins strict, juste log)
    technical_found = []
    for pattern in TECHNICAL_PATTERNS:
        if re.search(pattern, response, re.IGNORECASE):
            technical_found.append(pattern)

    if len(technical_found) > 3:  # Trop de termes techniques
        logger.warning(
            "simon_technical_detected",
            patterns=technical_found,
            response_preview=response[:100]
        )
        return False, "Cette réponse était trop technique et a été bloquée.", "technical"

    # Réponse autorisée
    return True, response, None


# =============================================================================
# Validation du format JSON attendu
# =============================================================================
def validate_simon_json(response: str) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Valide que la réponse de Simon est au format JSON attendu.

    Returns:
        Tuple[bool, Optional[dict], Optional[str]]:
            - valid: True si le format est valide
            - data: Le dict parsé (ou None)
            - error: Message d'erreur (ou None)
    """
    import json

    # Extraire le JSON de la réponse
    json_match = re.search(r'\{[\s\S]*\}', response)
    if not json_match:
        return False, None, "Pas de JSON trouvé dans la réponse"

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        return False, None, f"JSON invalide: {str(e)}"

    # Vérifier la structure
    if "tests" not in data:
        return False, None, "Clé 'tests' manquante"

    if not isinstance(data["tests"], list):
        return False, None, "'tests' doit être une liste"

    for i, test in enumerate(data["tests"]):
        if "action" not in test:
            return False, None, f"Test {i+1}: 'action' manquante"
        if "resultat_attendu" not in test:
            return False, None, f"Test {i+1}: 'resultat_attendu' manquant"

    return True, data, None


# =============================================================================
# Nettoyage de la réponse
# =============================================================================
def clean_response_for_display(response: str) -> str:
    """
    Nettoie la réponse pour affichage (retire les artefacts markdown, etc.)
    """
    # Retirer les blocs de code s'il y en a (ne devrait pas arriver après filtrage)
    response = re.sub(r'```[\s\S]*?```', '[BLOC RETIRÉ]', response)
    response = re.sub(r'`[^`]+`', '[CODE RETIRÉ]', response)

    # Nettoyer les espaces multiples
    response = re.sub(r'\n{3,}', '\n\n', response)
    response = re.sub(r' {2,}', ' ', response)

    return response.strip()
