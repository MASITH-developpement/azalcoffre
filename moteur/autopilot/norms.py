# =============================================================================
# AUTOPILOT - Système de normes
# =============================================================================
"""
Gestion des normes de code AZALPLUS.
Guardian utilise ces normes pour valider et améliorer ses corrections.

Les normes sont extraites de:
- CLAUDE.md (instructions générales)
- memoire.md (normes AZAP-*)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import re
import structlog

logger = structlog.get_logger()


@dataclass
class Norm:
    """Une norme de code."""
    code: str           # Ex: "AZAP-TENANT-001"
    name: str           # Ex: "Isolation tenant obligatoire"
    description: str    # Description complète
    category: str       # Ex: "tenant", "security", "code"
    level: str          # "critical", "important", "recommended"
    check_pattern: Optional[str] = None  # Regex pour détecter violations
    fix_hint: Optional[str] = None       # Indice pour corriger


# =============================================================================
# NORMES AZALPLUS CODIFIÉES
# =============================================================================

AZALPLUS_NORMS: List[Norm] = [
    # --- TENANT (Critique) ---
    Norm(
        code="AZAP-TENANT-001",
        name="tenant_id obligatoire",
        description="Toute entité doit avoir un tenant_id",
        category="tenant",
        level="critical",
        check_pattern=r"(?:INSERT INTO|CREATE TABLE)(?:(?!tenant_id).)*$",
        fix_hint="Ajouter tenant_id à l'entité"
    ),
    Norm(
        code="AZAP-TENANT-002",
        name="Filtre tenant sur requêtes",
        description="Toute requête SELECT/UPDATE/DELETE doit filtrer par tenant_id",
        category="tenant",
        level="critical",
        check_pattern=r"(?:SELECT|UPDATE|DELETE)(?:(?!tenant_id).)*(?:FROM|SET|WHERE)",
        fix_hint="Ajouter WHERE tenant_id = :tenant_id"
    ),
    Norm(
        code="AZAP-TENANT-003",
        name="TenantContext obligatoire",
        description="Utiliser TenantContext.get_tenant_id() pour obtenir le tenant",
        category="tenant",
        level="critical",
        fix_hint="Utiliser TenantContext.get_tenant_id() au lieu de passer tenant_id manuellement"
    ),

    # --- SÉCURITÉ (Critique) ---
    Norm(
        code="AZAP-SEC-001",
        name="Guardian invisible",
        description="Ne jamais exposer l'existence de Guardian aux utilisateurs",
        category="security",
        level="critical",
        check_pattern=r"(?:guardian|Guardian|GUARDIAN)",
        fix_hint="Utiliser des messages neutres, ne pas mentionner Guardian"
    ),
    Norm(
        code="AZAP-SEC-002",
        name="Pas de secrets en dur",
        description="Aucun secret/mot de passe/clé API en dur dans le code",
        category="security",
        level="critical",
        check_pattern=r"(?:password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]",
        fix_hint="Utiliser variables d'environnement ou settings"
    ),
    Norm(
        code="AZAP-SEC-003",
        name="Validation entrées",
        description="Valider toutes les entrées utilisateur avec Pydantic",
        category="security",
        level="critical",
        fix_hint="Utiliser des schémas Pydantic pour valider les données"
    ),
    Norm(
        code="AZAP-SEC-004",
        name="SQL paramétré",
        description="Jamais de SQL brut avec concaténation de strings",
        category="security",
        level="critical",
        check_pattern=r"f['\"].*(?:SELECT|INSERT|UPDATE|DELETE).*\{",
        fix_hint="Utiliser text() avec des paramètres nommés"
    ),

    # --- CODE (Important) ---
    Norm(
        code="AZAP-CODE-001",
        name="Type hints obligatoires",
        description="Toutes les fonctions doivent avoir des type hints",
        category="code",
        level="important",
        check_pattern=r"def \w+\([^)]*\)(?!\s*->)",
        fix_hint="Ajouter -> ReturnType après les paramètres"
    ),
    Norm(
        code="AZAP-CODE-002",
        name="Pas de print en production",
        description="Utiliser structlog au lieu de print()",
        category="code",
        level="important",
        check_pattern=r"(?<!#)\s*print\s*\(",
        fix_hint="Remplacer print() par logger.info() ou logger.debug()"
    ),
    Norm(
        code="AZAP-CODE-003",
        name="Imports explicites",
        description="Pas d'import * sauf dans __init__.py",
        category="code",
        level="important",
        check_pattern=r"from \S+ import \*",
        fix_hint="Lister explicitement les imports"
    ),

    # --- YAML (Important) ---
    Norm(
        code="AZAP-YAML-001",
        name="Validation YAML stricte",
        description="Valider les fichiers YAML avant chargement",
        category="yaml",
        level="important",
        fix_hint="Utiliser YAMLValidator.validate_file()"
    ),
    Norm(
        code="AZAP-YAML-002",
        name="Guillemets pour valeurs avec ':'",
        description="Les valeurs contenant ':' doivent être entre guillemets",
        category="yaml",
        level="important",
        check_pattern=r":\s+[^'\"\n]*:[^'\"\n]*$",
        fix_hint="Mettre la valeur entre guillemets: \"valeur: avec deux-points\""
    ),

    # --- API (Important) ---
    Norm(
        code="AZAP-API-001",
        name="Authentification requise",
        description="Tous les endpoints API (sauf /health, /login) nécessitent auth",
        category="api",
        level="important",
        fix_hint="Ajouter Depends(require_auth)"
    ),
    Norm(
        code="AZAP-API-002",
        name="Réponses standardisées",
        description="Utiliser les schémas de réponse standard",
        category="api",
        level="recommended",
        fix_hint="Utiliser les modèles Pydantic pour les réponses"
    ),

    # --- MOTEUR (Critique) ---
    Norm(
        code="AZAP-NF-001",
        name="Unicité du moteur",
        description="Le moteur ne doit jamais être dupliqué",
        category="architecture",
        level="critical",
        fix_hint="Modifier le moteur existant, ne pas créer de copie"
    ),
    Norm(
        code="AZAP-NF-002",
        name="Modules subordonnés",
        description="Les modules YAML sont subordonnés au moteur",
        category="architecture",
        level="critical",
        fix_hint="La logique métier va dans modules/, pas dans moteur/"
    ),
]


class NormsChecker:
    """Vérificateur de conformité aux normes."""

    def __init__(self, norms: List[Norm] = None):
        self._norms = norms or AZALPLUS_NORMS
        self._by_code = {n.code: n for n in self._norms}
        self._by_category = {}
        for n in self._norms:
            if n.category not in self._by_category:
                self._by_category[n.category] = []
            self._by_category[n.category].append(n)

    def check_code(self, code: str, file_path: str = None) -> List[Dict]:
        """
        Vérifie un bloc de code contre les normes.

        Returns:
            Liste des violations détectées
        """
        violations = []

        for norm in self._norms:
            if norm.check_pattern:
                if re.search(norm.check_pattern, code, re.MULTILINE | re.IGNORECASE):
                    violations.append({
                        "norm": norm.code,
                        "name": norm.name,
                        "level": norm.level,
                        "description": norm.description,
                        "fix_hint": norm.fix_hint,
                        "file": file_path
                    })

        return violations

    def get_norm(self, code: str) -> Optional[Norm]:
        """Récupère une norme par son code."""
        return self._by_code.get(code)

    def get_norms_by_category(self, category: str) -> List[Norm]:
        """Récupère les normes d'une catégorie."""
        return self._by_category.get(category, [])

    def get_critical_norms(self) -> List[Norm]:
        """Récupère les normes critiques."""
        return [n for n in self._norms if n.level == "critical"]

    def format_violation_message(self, violation: Dict) -> str:
        """Formate un message de violation pour les logs."""
        return (
            f"[{violation['level'].upper()}] {violation['norm']}: {violation['name']}\n"
            f"  {violation['description']}\n"
            f"  Fix: {violation['fix_hint']}"
        )

    def validate_fix_proposal(self, proposed_fix: str) -> List[Dict]:
        """
        Valide qu'un fix proposé respecte les normes.
        Utilisé avant d'appliquer un fix automatiquement.
        """
        return self.check_code(proposed_fix)


# Instance globale
_checker: Optional[NormsChecker] = None


def get_norms_checker() -> NormsChecker:
    """Retourne le vérificateur de normes (singleton)."""
    global _checker
    if _checker is None:
        _checker = NormsChecker()
        logger.info("norms_checker_initialized", norms_count=len(AZALPLUS_NORMS))
    return _checker


def check_against_norms(code: str, file_path: str = None) -> List[Dict]:
    """Vérifie du code contre les normes AZALPLUS."""
    return get_norms_checker().check_code(code, file_path)
