# =============================================================================
# AUTOPILOT - Modèles de données
# =============================================================================
"""
Modèles de données pour le système AutoPilot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import hashlib


class FixStatus(str, Enum):
    """Statut d'un fix proposé."""
    PENDING = "pending"           # En attente de validation simple
    APPROVED = "approved"         # Validé par Claude
    REJECTED = "rejected"         # Rejeté par Claude
    APPLIED = "applied"           # Appliqué avec succès
    FAILED = "failed"             # Échec de l'application
    AUTO_VALIDATED = "auto_validated"  # Validé automatiquement (pattern connu)
    NEEDS_CLAUDE = "needs_claude"      # Bug complexe - Claude doit prendre la main et coder


class ErrorCategory(str, Enum):
    """Catégories d'erreurs."""
    PYTHON = "python"
    YAML = "yaml"
    SQL = "sql"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    IMPORT = "import"
    TYPE = "type"
    UNKNOWN = "unknown"


@dataclass
class FixProposal:
    """
    Proposition de correction par AutoPilot.

    Représente une erreur détectée et le fix proposé.
    """
    id: str
    error_type: str
    error_message: str
    category: ErrorCategory = ErrorCategory.UNKNOWN
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    original_code: Optional[str] = None
    proposed_fix: Optional[str] = None
    confidence: float = 0.5  # 0.0 à 1.0
    created_at: datetime = field(default_factory=datetime.now)
    status: FixStatus = FixStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def generate_id(cls, error_log: str) -> str:
        """Génère un ID unique basé sur l'erreur."""
        timestamp = datetime.now().isoformat()
        return hashlib.md5(f"{error_log}{timestamp}".encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "id": self.id,
            "error_type": self.error_type,
            "error_message": self.error_message[:500],
            "category": self.category.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "original_code": self.original_code,
            "proposed_fix": self.proposed_fix,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "metadata": self.metadata
        }


@dataclass
class Learning:
    """
    Un apprentissage stocké par AutoPilot.

    Représente soit un pattern validé (à réutiliser),
    soit un pattern rejeté (à éviter) avec l'explication.
    """
    id: str
    error_pattern: str           # Pattern d'erreur (regex ou type)
    error_message: str           # Message d'erreur exemple
    fix_template: Optional[str]  # Le fix qui a été proposé
    status: str                  # 'validated' ou 'rejected'
    explanation: str             # Explication (surtout si rejeté)
    file_path: Optional[str] = None
    confidence: float = 0.5
    times_applied: int = 0       # Nombre de fois ce pattern a été utilisé
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def generate_id(cls, error_pattern: str, fix_template: str) -> str:
        """Génère un ID unique basé sur le pattern."""
        return hashlib.md5(f"{error_pattern}{fix_template}".encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "id": self.id,
            "error_pattern": self.error_pattern,
            "error_message": self.error_message[:500],
            "fix_template": self.fix_template,
            "status": self.status,
            "explanation": self.explanation,
            "file_path": self.file_path,
            "confidence": self.confidence,
            "times_applied": self.times_applied,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class ValidationResult:
    """Résultat d'une validation de fix."""
    success: bool
    status: FixStatus
    message: str
    fix: Optional[FixProposal] = None
    learning: Optional[Learning] = None
    applied_changes: Optional[Dict[str, Any]] = None
