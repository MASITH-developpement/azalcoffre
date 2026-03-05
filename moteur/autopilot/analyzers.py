# =============================================================================
# AUTOPILOT - Analyseurs d'erreurs
# =============================================================================
"""
Analyseurs modulaires pour différents types d'erreurs.
Chaque analyseur peut être utilisé indépendamment ou combiné.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
import re
import structlog

from .models import FixProposal, ErrorCategory, FixStatus

logger = structlog.get_logger()


class ErrorAnalyzer(ABC):
    """Interface abstraite pour un analyseur d'erreurs."""

    @property
    @abstractmethod
    def category(self) -> ErrorCategory:
        """Catégorie d'erreurs gérée."""
        pass

    @property
    @abstractmethod
    def patterns(self) -> List[Tuple[str, str, float]]:
        """
        Liste de (pattern_regex, description, confidence_base).
        """
        pass

    @abstractmethod
    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """
        Analyse une erreur et retourne une proposition de fix.

        Args:
            error_log: Le message d'erreur complet

        Returns:
            FixProposal ou None si non reconnu
        """
        pass

    def _extract_file_info(self, error_log: str) -> Tuple[Optional[str], Optional[int]]:
        """Extrait le fichier et la ligne depuis un traceback."""
        match = re.search(r'File "([^"]+)", line (\d+)', error_log)
        if match:
            return match.group(1), int(match.group(2))
        return None, None


class PythonErrorAnalyzer(ErrorAnalyzer):
    """Analyseur pour les erreurs Python."""

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.PYTHON

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        return [
            # ImportError / ModuleNotFoundError
            (r"ImportError: cannot import name '(\w+)' from '([^']+)'",
             "Import manquant", 0.8),
            (r"ModuleNotFoundError: No module named '([^']+)'",
             "Module non installé", 0.7),

            # NameError
            (r"NameError: name '(\w+)' is not defined",
             "Variable/fonction non définie", 0.75),

            # AttributeError
            (r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
             "Attribut inexistant", 0.6),
            (r"AttributeError: module '([^']+)' has no attribute '(\w+)'",
             "Attribut de module inexistant", 0.65),

            # TypeError
            (r"TypeError: (\w+)\(\) missing (\d+) required positional argument",
             "Arguments manquants", 0.7),
            (r"TypeError: (\w+)\(\) got an unexpected keyword argument '(\w+)'",
             "Argument inconnu", 0.65),
            (r"TypeError: '(\w+)' object is not (callable|iterable|subscriptable)",
             "Type incorrect", 0.5),

            # KeyError
            (r"KeyError: '(\w+)'",
             "Clé manquante dans dict", 0.75),

            # ValueError
            (r"ValueError: (.+)",
             "Valeur invalide", 0.5),

            # IndexError
            (r"IndexError: (list|tuple|string) index out of range",
             "Index hors limites", 0.6),

            # SyntaxError
            (r"SyntaxError: (.+)",
             "Erreur de syntaxe", 0.4),

            # IndentationError
            (r"IndentationError: (.+)",
             "Erreur d'indentation", 0.7),
        ]

    # Mapping des noms vers leurs imports courants
    COMMON_IMPORTS = {
        # Typing
        "Optional": "from typing import Optional",
        "List": "from typing import List",
        "Dict": "from typing import Dict",
        "Union": "from typing import Union",
        "Any": "from typing import Any",
        "Callable": "from typing import Callable",
        "Tuple": "from typing import Tuple",
        "Type": "from typing import Type",
        "Set": "from typing import Set",

        # UUID
        "UUID": "from uuid import UUID",
        "uuid4": "from uuid import uuid4",

        # Datetime
        "datetime": "from datetime import datetime",
        "timedelta": "from datetime import timedelta",
        "date": "from datetime import date",
        "time": "from datetime import time",

        # FastAPI
        "Depends": "from fastapi import Depends",
        "HTTPException": "from fastapi import HTTPException",
        "Request": "from fastapi import Request",
        "Response": "from fastapi import Response",
        "Query": "from fastapi import Query",
        "Path": "from fastapi import Path",
        "Body": "from fastapi import Body",
        "Header": "from fastapi import Header",
        "APIRouter": "from fastapi import APIRouter",
        "FastAPI": "from fastapi import FastAPI",

        # Pydantic
        "BaseModel": "from pydantic import BaseModel",
        "Field": "from pydantic import Field",
        "validator": "from pydantic import validator",

        # SQLAlchemy
        "Session": "from sqlalchemy.orm import Session",
        "text": "from sqlalchemy import text",
        "Column": "from sqlalchemy import Column",
        "Integer": "from sqlalchemy import Integer",
        "String": "from sqlalchemy import String",

        # Dataclasses
        "dataclass": "from dataclasses import dataclass",
        "field": "from dataclasses import field",

        # JSON
        "json": "import json",
        "JSONResponse": "from fastapi.responses import JSONResponse",

        # OS/Path
        "os": "import os",
        "Path": "from pathlib import Path",

        # Re
        "re": "import re",

        # Structlog
        "structlog": "import structlog",
        "logger": "logger = structlog.get_logger()",
    }

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Analyse une erreur Python."""
        file_path, line_num = self._extract_file_info(error_log)

        for pattern, desc, base_confidence in self.patterns:
            match = re.search(pattern, error_log, re.IGNORECASE)
            if match:
                proposal = self._generate_fix(
                    match, pattern, desc, base_confidence,
                    error_log, file_path, line_num
                )
                if proposal:
                    return proposal

        return None

    def _generate_fix(
        self,
        match: re.Match,
        pattern: str,
        desc: str,
        confidence: float,
        error_log: str,
        file_path: Optional[str],
        line_num: Optional[int]
    ) -> Optional[FixProposal]:
        """Génère un fix basé sur le pattern détecté."""

        error_type = pattern.split(":")[0].replace("\\", "").replace("(", "").replace(")", "")
        groups = match.groups()

        proposed_fix = None
        original_code = None

        # NameError - variable non définie
        if "NameError" in error_type:
            name = groups[0]
            if name in self.COMMON_IMPORTS:
                proposed_fix = f"# Ajouter en haut du fichier:\n{self.COMMON_IMPORTS[name]}"
                confidence = 0.9
            else:
                proposed_fix = f"# '{name}' n'est pas défini. Vérifier:\n# 1. L'orthographe\n# 2. Si une variable ou fonction porte ce nom\n# 3. Si un import est manquant"
                confidence = 0.4

        # ImportError
        elif "ImportError" in error_type:
            name = groups[0]
            module = groups[1] if len(groups) > 1 else ""
            if name in self.COMMON_IMPORTS:
                proposed_fix = f"# Utiliser l'import standard:\n{self.COMMON_IMPORTS[name]}"
                confidence = 0.85
            else:
                proposed_fix = f"# Vérifier que '{name}' existe dans '{module}'\n# Ou importer depuis un autre module"

        # ModuleNotFoundError
        elif "ModuleNotFoundError" in error_type:
            module = groups[0]
            proposed_fix = f"# Installer le module:\npip install {module}\n\n# Ou vérifier le nom du module"
            confidence = 0.7

        # KeyError
        elif "KeyError" in error_type:
            key = groups[0]
            proposed_fix = f"# Utiliser .get() avec valeur par défaut:\nvalue = data.get('{key}', None)  # ou autre défaut\n\n# Ou vérifier si la clé existe:\nif '{key}' in data:\n    value = data['{key}']"
            confidence = 0.8

        # AttributeError
        elif "AttributeError" in error_type:
            obj_type = groups[0]
            attr = groups[1] if len(groups) > 1 else ""
            proposed_fix = f"# '{obj_type}' n'a pas d'attribut '{attr}'\n# Options:\n# 1. Vérifier l'orthographe de '{attr}'\n# 2. Utiliser getattr(obj, '{attr}', default)\n# 3. Vérifier le type de l'objet avec type(obj)"
            confidence = 0.5

        # TypeError - arguments manquants
        elif "TypeError" in error_type and "missing" in pattern:
            func = groups[0]
            count = groups[1]
            proposed_fix = f"# La fonction '{func}()' attend {count} argument(s) supplémentaire(s)\n# Vérifier la signature de la fonction et ajouter les arguments manquants"
            confidence = 0.65

        # TypeError - argument inconnu
        elif "TypeError" in error_type and "unexpected" in pattern:
            func = groups[0]
            arg = groups[1]
            proposed_fix = f"# La fonction '{func}()' n'accepte pas l'argument '{arg}'\n# Supprimer ou renommer cet argument"
            confidence = 0.7

        # IndentationError
        elif "IndentationError" in error_type:
            proposed_fix = "# Corriger l'indentation:\n# - Utiliser 4 espaces par niveau\n# - Ne pas mélanger espaces et tabulations\n# - Vérifier les blocs if/for/def/class"
            confidence = 0.75

        # SyntaxError
        elif "SyntaxError" in error_type:
            proposed_fix = "# Erreur de syntaxe - vérifier:\n# - Parenthèses/crochets/accolades fermantes\n# - Virgules entre éléments\n# - Deux-points après if/for/def/class\n# - Guillemets fermants pour les strings"
            confidence = 0.4

        if proposed_fix:
            return FixProposal(
                id=FixProposal.generate_id(error_log),
                error_type=error_type,
                error_message=error_log[:500],
                category=self.category,
                file_path=file_path,
                line_number=line_num,
                original_code=original_code,
                proposed_fix=proposed_fix,
                confidence=confidence,
                created_at=datetime.now(),
                status=FixStatus.PENDING
            )

        return None


class YAMLErrorAnalyzer(ErrorAnalyzer):
    """Analyseur pour les erreurs YAML."""

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.YAML

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        return [
            (r"yaml\.scanner\.ScannerError: (.+)",
             "Erreur de scan YAML", 0.6),
            (r"yaml\.parser\.ParserError: (.+)",
             "Erreur de parsing YAML", 0.6),
            (r"could not determine a constructor for the tag",
             "Tag YAML inconnu", 0.7),
            (r"found character .+ that cannot start any token",
             "Caractère invalide", 0.65),
        ]

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Analyse une erreur YAML."""
        file_path, line_num = self._extract_file_info(error_log)

        for pattern, desc, confidence in self.patterns:
            if re.search(pattern, error_log, re.IGNORECASE):
                proposed_fix = self._generate_yaml_fix(error_log, desc)
                return FixProposal(
                    id=FixProposal.generate_id(error_log),
                    error_type="YAMLError",
                    error_message=error_log[:500],
                    category=self.category,
                    file_path=file_path,
                    line_number=line_num,
                    original_code=None,
                    proposed_fix=proposed_fix,
                    confidence=confidence,
                    created_at=datetime.now(),
                    status=FixStatus.PENDING
                )

        return None

    def _generate_yaml_fix(self, error_log: str, desc: str) -> str:
        """Génère un fix pour erreur YAML."""
        fix_lines = [
            "# Erreur YAML - vérifier:",
            "# 1. Indentation (utiliser 2 espaces)",
            "# 2. Valeurs avec ':' entre guillemets",
            "#    Exemple: description: \"Valeur: avec deux-points\"",
            "# 3. Pas de tabulations",
            "# 4. Listes avec tiret et espace: '- item'"
        ]

        if "mapping" in error_log.lower():
            fix_lines.append("# 5. Structure clé: valeur correcte")

        return "\n".join(fix_lines)


class SQLErrorAnalyzer(ErrorAnalyzer):
    """Analyseur pour les erreurs SQL/SQLAlchemy."""

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.SQL

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        return [
            (r"sqlalchemy\.exc\.IntegrityError: (.+)",
             "Violation de contrainte", 0.6),
            (r"sqlalchemy\.exc\.OperationalError: (.+)",
             "Erreur opérationnelle", 0.5),
            (r"sqlalchemy\.exc\.ProgrammingError: (.+)",
             "Erreur de programmation SQL", 0.55),
            (r"duplicate key value violates unique constraint",
             "Doublon - clé unique", 0.75),
            (r"violates foreign key constraint",
             "Violation foreign key", 0.7),
            (r"column \"(\w+)\" (does not exist|of relation)",
             "Colonne inexistante", 0.65),
            (r"relation \"(\w+)\" does not exist",
             "Table inexistante", 0.7),
        ]

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Analyse une erreur SQL."""
        file_path, line_num = self._extract_file_info(error_log)

        for pattern, desc, confidence in self.patterns:
            match = re.search(pattern, error_log, re.IGNORECASE)
            if match:
                proposed_fix = self._generate_sql_fix(match, pattern, error_log)
                return FixProposal(
                    id=FixProposal.generate_id(error_log),
                    error_type="SQLError",
                    error_message=error_log[:500],
                    category=self.category,
                    file_path=file_path,
                    line_number=line_num,
                    original_code=None,
                    proposed_fix=proposed_fix,
                    confidence=confidence,
                    created_at=datetime.now(),
                    status=FixStatus.PENDING
                )

        return None

    def _generate_sql_fix(self, match: re.Match, pattern: str, error_log: str) -> str:
        """Génère un fix pour erreur SQL."""
        if "duplicate key" in pattern:
            return "# Doublon détecté - options:\n# 1. Vérifier si l'entrée existe avant INSERT\n# 2. Utiliser ON CONFLICT DO UPDATE (upsert)\n# 3. Générer un nouvel ID unique"

        if "foreign key" in pattern:
            return "# Violation de clé étrangère - options:\n# 1. Vérifier que l'enregistrement parent existe\n# 2. Créer l'enregistrement parent d'abord\n# 3. Utiliser ON DELETE CASCADE si approprié"

        if "column" in pattern and "does not exist" in pattern:
            groups = match.groups()
            col = groups[0] if groups else "?"
            return f"# La colonne '{col}' n'existe pas:\n# 1. Vérifier l'orthographe\n# 2. Exécuter la migration pour ajouter la colonne\n# 3. Vérifier le schéma de la table"

        if "relation" in pattern and "does not exist" in pattern:
            groups = match.groups()
            table = groups[0] if groups else "?"
            return f"# La table '{table}' n'existe pas:\n# 1. Exécuter les migrations\n# 2. Vérifier le nom du schéma (azalplus.table)\n# 3. Créer la table si nécessaire"

        return "# Erreur SQL - vérifier:\n# 1. La syntaxe de la requête\n# 2. Les noms de tables/colonnes\n# 3. La connexion à la base de données"


class CompositeAnalyzer(ErrorAnalyzer):
    """
    Analyseur composite qui combine plusieurs analyseurs.
    Essaie chaque analyseur dans l'ordre jusqu'à trouver un match.
    """

    def __init__(self, analyzers: List[ErrorAnalyzer] = None):
        self._analyzers = analyzers or [
            PythonErrorAnalyzer(),
            YAMLErrorAnalyzer(),
            SQLErrorAnalyzer(),
        ]

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.UNKNOWN

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        # Combine tous les patterns
        all_patterns = []
        for analyzer in self._analyzers:
            all_patterns.extend(analyzer.patterns)
        return all_patterns

    def add_analyzer(self, analyzer: ErrorAnalyzer) -> None:
        """Ajoute un analyseur."""
        self._analyzers.append(analyzer)

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Essaie chaque analyseur jusqu'à trouver un match."""
        for analyzer in self._analyzers:
            proposal = analyzer.analyze(error_log)
            if proposal:
                # Si confiance trop basse, escalader à Claude
                if proposal.confidence < 0.5:
                    proposal.status = FixStatus.NEEDS_CLAUDE
                    proposal.metadata["reason"] = "Confiance trop basse, Claude doit analyser"
                return proposal

        # Aucun analyseur n'a pu traiter l'erreur -> Claude doit prendre la main
        file_path, line_num = self._extract_file_info(error_log)
        return FixProposal(
            id=FixProposal.generate_id(error_log),
            error_type="ComplexError",
            error_message=error_log[:500],
            category=ErrorCategory.UNKNOWN,
            file_path=file_path,
            line_number=line_num,
            original_code=None,
            proposed_fix=None,  # Pas de fix proposé
            confidence=0.0,
            created_at=datetime.now(),
            status=FixStatus.NEEDS_CLAUDE,
            metadata={"reason": "Erreur non reconnue, Claude doit analyser et corriger"}
        )
