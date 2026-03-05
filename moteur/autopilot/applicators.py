# =============================================================================
# AUTOPILOT - Applicateurs de fixes
# =============================================================================
"""
Applicateurs modulaires pour différents types de fixes.
Gèrent l'application sécurisée des corrections.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import shutil
import re
import structlog

from .models import FixProposal, ErrorCategory

logger = structlog.get_logger()


class ApplyResult:
    """Résultat d'une application de fix."""

    def __init__(
        self,
        success: bool,
        message: str,
        changes: Optional[Dict[str, Any]] = None,
        backup_path: Optional[str] = None
    ):
        self.success = success
        self.message = message
        self.changes = changes or {}
        self.backup_path = backup_path

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "changes": self.changes,
            "backup_path": self.backup_path
        }


class FixApplicator(ABC):
    """Interface abstraite pour un applicateur de fixes."""

    # Fichiers protégés - ne jamais modifier sans validation humaine explicite
    PROTECTED_FILES = [
        "guardian.py",
        "auth.py",
        "security.py",
        "db.py",
        "config.py",
        ".env",
        "secrets.py",
    ]

    # Répertoires protégés
    PROTECTED_DIRS = [
        "/etc/",
        "/usr/",
        "/bin/",
        "/sbin/",
        "node_modules/",
        ".git/",
        "__pycache__/",
    ]

    @abstractmethod
    def can_apply(self, proposal: FixProposal) -> bool:
        """Vérifie si ce fix peut être appliqué."""
        pass

    @abstractmethod
    def apply(self, proposal: FixProposal) -> ApplyResult:
        """Applique le fix."""
        pass

    def is_protected(self, file_path: str) -> bool:
        """Vérifie si le fichier est protégé."""
        if not file_path:
            return False

        path = Path(file_path)

        # Vérifier les fichiers protégés
        for protected in self.PROTECTED_FILES:
            if path.name == protected:
                return True

        # Vérifier les répertoires protégés
        for protected_dir in self.PROTECTED_DIRS:
            if protected_dir in str(path):
                return True

        return False

    def create_backup(self, file_path: str) -> Optional[str]:
        """Crée une sauvegarde du fichier."""
        try:
            path = Path(file_path)
            if path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{file_path}.autopilot_backup_{timestamp}"
                shutil.copy2(file_path, backup_path)
                return backup_path
        except Exception as e:
            logger.error("autopilot_backup_failed", file=file_path, error=str(e))
        return None

    def restore_backup(self, backup_path: str, original_path: str) -> bool:
        """Restaure depuis une sauvegarde."""
        try:
            if Path(backup_path).exists():
                shutil.copy2(backup_path, original_path)
                return True
        except Exception as e:
            logger.error("autopilot_restore_failed", backup=backup_path, error=str(e))
        return False


class PythonFixApplicator(FixApplicator):
    """Applicateur pour les fixes Python."""

    def can_apply(self, proposal: FixProposal) -> bool:
        """Vérifie si ce fix Python peut être appliqué."""
        if not proposal.file_path:
            return False

        if not proposal.proposed_fix:
            return False

        if self.is_protected(proposal.file_path):
            logger.warning("autopilot_protected_file", file=proposal.file_path)
            return False

        # Vérifier que c'est un fichier Python
        if not proposal.file_path.endswith(".py"):
            return False

        # Vérifier que le fichier existe
        if not Path(proposal.file_path).exists():
            return False

        # Vérifier que c'est un type de fix qu'on sait appliquer
        applicable_types = ["NameError", "ImportError"]
        return any(t in proposal.error_type for t in applicable_types)

    def apply(self, proposal: FixProposal) -> ApplyResult:
        """Applique un fix Python."""
        if not self.can_apply(proposal):
            return ApplyResult(
                success=False,
                message="Fix non applicable automatiquement"
            )

        try:
            # Créer backup
            backup_path = self.create_backup(proposal.file_path)
            if not backup_path:
                return ApplyResult(
                    success=False,
                    message="Impossible de créer la sauvegarde"
                )

            # Lire le fichier
            with open(proposal.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Appliquer selon le type d'erreur
            if "NameError" in proposal.error_type or "ImportError" in proposal.error_type:
                result = self._apply_import_fix(lines, proposal)
            else:
                return ApplyResult(
                    success=False,
                    message=f"Type de fix non supporté: {proposal.error_type}",
                    backup_path=backup_path
                )

            if result.success:
                # Écrire le fichier modifié
                with open(proposal.file_path, 'w', encoding='utf-8') as f:
                    f.writelines(result.changes.get("new_lines", lines))

                return ApplyResult(
                    success=True,
                    message=result.message,
                    changes=result.changes,
                    backup_path=backup_path
                )
            else:
                return result

        except Exception as e:
            logger.error("autopilot_apply_failed", error=str(e))
            return ApplyResult(
                success=False,
                message=f"Erreur: {str(e)}"
            )

    def _apply_import_fix(
        self,
        lines: List[str],
        proposal: FixProposal
    ) -> ApplyResult:
        """Applique un fix d'import."""

        # Extraire la ligne d'import du fix proposé
        import_match = re.search(
            r"(from .+ import .+|import .+)",
            proposal.proposed_fix
        )
        if not import_match:
            return ApplyResult(
                success=False,
                message="Impossible d'extraire l'import du fix"
            )

        new_import = import_match.group(1)

        # Vérifier si l'import existe déjà
        for line in lines:
            if new_import in line:
                return ApplyResult(
                    success=False,
                    message="L'import existe déjà"
                )

        # Trouver le bon endroit pour insérer l'import
        # Après le dernier import existant
        last_import_idx = 0
        in_docstring = False
        docstring_char = None

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Gérer les docstrings
            if '"""' in stripped or "'''" in stripped:
                if not in_docstring:
                    in_docstring = True
                    docstring_char = '"""' if '"""' in stripped else "'''"
                    # Vérifier si docstring sur une seule ligne
                    if stripped.count(docstring_char) >= 2:
                        in_docstring = False
                elif docstring_char in stripped:
                    in_docstring = False
                continue

            if in_docstring:
                continue

            # Chercher les imports
            if stripped.startswith(("import ", "from ")):
                last_import_idx = i

        # Insérer après le dernier import (ou au début si pas d'import)
        insert_idx = last_import_idx + 1 if last_import_idx > 0 else 0

        # Si pas d'imports, insérer après les docstrings/comments initiaux
        if last_import_idx == 0:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith(('"""', "'''")):
                    insert_idx = i
                    break

        # Insérer l'import
        new_lines = lines.copy()
        new_lines.insert(insert_idx, new_import + "\n")

        return ApplyResult(
            success=True,
            message=f"Import ajouté ligne {insert_idx + 1}",
            changes={
                "type": "import_added",
                "import": new_import,
                "line": insert_idx + 1,
                "new_lines": new_lines
            }
        )


class CompositeApplicator(FixApplicator):
    """Applicateur composite qui délègue au bon applicateur."""

    def __init__(self, applicators: List[FixApplicator] = None):
        self._applicators = applicators or [
            PythonFixApplicator(),
        ]

    def add_applicator(self, applicator: FixApplicator) -> None:
        """Ajoute un applicateur."""
        self._applicators.append(applicator)

    def can_apply(self, proposal: FixProposal) -> bool:
        """Vérifie si un applicateur peut gérer ce fix."""
        return any(a.can_apply(proposal) for a in self._applicators)

    def apply(self, proposal: FixProposal) -> ApplyResult:
        """Applique le fix avec le bon applicateur."""
        for applicator in self._applicators:
            if applicator.can_apply(proposal):
                return applicator.apply(proposal)

        return ApplyResult(
            success=False,
            message="Aucun applicateur ne peut gérer ce fix"
        )
