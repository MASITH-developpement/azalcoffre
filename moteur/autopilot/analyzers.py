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
             "Attribut inexistant sur instance", 0.6),
            (r"AttributeError: type object '(\w+)' has no attribute '(\w+)'",
             "Méthode de classe inexistante", 0.75),
            (r"AttributeError: module '([^']+)' has no attribute '(\w+)'",
             "Attribut de module inexistant", 0.65),

            # TypeError
            (r"TypeError: (\w+)\(\) missing (\d+) required positional argument",
             "Arguments manquants", 0.7),
            (r"TypeError: (\w+)\(\) got an unexpected keyword argument '(\w+)'",
             "Argument inconnu", 0.65),
            (r"TypeError: '(\w+)' object is not (callable|iterable|subscriptable)",
             "Type incorrect", 0.5),
            (r"TypeError: 'NoneType' object is not iterable",
             "Itération sur None", 0.85),
            (r"TypeError: 'NoneType' object is not subscriptable",
             "Indexation sur None", 0.85),
            (r"TypeError: cannot unpack non-iterable NoneType object",
             "Déballage de None", 0.85),
            (r"TypeError: argument of type 'NoneType' is not iterable",
             "Vérification dans None", 0.85),
            (r"TypeError: unsupported operand type\(s\) for (.+): '(\w+)' and '(\w+)'",
             "Opération type incompatible", 0.6),

            # AttributeError NoneType
            (r"AttributeError: 'NoneType' object has no attribute '(\w+)'",
             "Accès attribut sur None", 0.85),

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

    # Mapping des méthodes manquantes vers leurs équivalents
    METHOD_ALIASES = {
        # Database
        "get": "get_by_id",
        "find": "query",
        "find_one": "get_by_id",
        "find_all": "query",
        "fetch": "get_by_id",
        "fetch_one": "get_by_id",
        "fetch_all": "query",
        "delete": "soft_delete",
        "remove": "soft_delete",
        # Collections
        "append": "add",
        "push": "append",
        "pop_front": "popleft",
        "size": "len",
        "length": "len",
        "count": "len",
        "empty": "clear",
        # Strings
        "contains": "__contains__",
        "substr": "substring",
        "index_of": "index",
        # Common
        "to_string": "__str__",
        "to_dict": "dict",
        "to_json": "json",
        "from_dict": "parse_obj",
        "from_json": "parse_raw",
    }

    # Classes connues et leurs méthodes
    KNOWN_CLASS_METHODS = {
        "Database": ["get_by_id", "query", "insert", "update", "soft_delete", "get_session", "create_table"],
        "Session": ["execute", "commit", "rollback", "close", "add", "delete", "query"],
        "Request": ["json", "form", "body", "headers", "cookies", "query_params"],
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

            # Chercher si c'est un alias connu
            if attr in self.METHOD_ALIASES:
                correct_method = self.METHOD_ALIASES[attr]
                proposed_fix = f"# '{obj_type}' n'a pas de méthode '{attr}'\n# Utiliser '{correct_method}' à la place:\n{obj_type}.{correct_method}(...)\n\n# Ou créer un alias dans la classe {obj_type}:\n@classmethod\ndef {attr}(cls, *args, **kwargs):\n    return cls.{correct_method}(*args, **kwargs)"
                confidence = 0.85
            # Chercher dans les méthodes connues de la classe
            elif obj_type in self.KNOWN_CLASS_METHODS:
                known_methods = self.KNOWN_CLASS_METHODS[obj_type]
                # Chercher une méthode similaire
                similar = [m for m in known_methods if attr.lower() in m.lower() or m.lower() in attr.lower()]
                if similar:
                    proposed_fix = f"# '{obj_type}' n'a pas de méthode '{attr}'\n# Méthode(s) similaire(s) disponible(s): {', '.join(similar)}\n# Utiliser: {obj_type}.{similar[0]}(...)"
                    confidence = 0.8
                else:
                    proposed_fix = f"# '{obj_type}' n'a pas de méthode '{attr}'\n# Méthodes disponibles: {', '.join(known_methods)}\n# Vérifier le nom correct de la méthode"
                    confidence = 0.7
            else:
                proposed_fix = f"# '{obj_type}' n'a pas d'attribut '{attr}'\n# Options:\n# 1. Vérifier l'orthographe de '{attr}'\n# 2. Ajouter la méthode à la classe {obj_type}\n# 3. Utiliser getattr(obj, '{attr}', default)\n# 4. Vérifier si '{attr}' existe sous un autre nom"
                confidence = 0.5

        # TypeError - NoneType not iterable
        elif "TypeError" in error_type and "NoneType" in error_log and "iterable" in error_log:
            proposed_fix = """# Variable None utilisée dans une boucle
# Ajouter une valeur par défaut:
items = variable or []
for item in items:
    ...

# Ou dans un template Jinja2:
{% for item in variable or [] %}

# Ou vérifier avant:
if variable is not None:
    for item in variable:
        ..."""
            confidence = 0.85

        # TypeError - NoneType not subscriptable
        elif "TypeError" in error_type and "NoneType" in error_log and "subscriptable" in error_log:
            proposed_fix = """# Variable None utilisée avec index
# Vérifier avant d'accéder:
if variable is not None:
    value = variable[key]

# Ou utiliser une valeur par défaut:
value = (variable or {}).get(key, default)"""
            confidence = 0.85

        # AttributeError - NoneType has no attribute
        elif "AttributeError" in error_type and "NoneType" in error_log:
            attr = groups[0] if groups else "?"
            proposed_fix = f"""# Accès à attribut '{attr}' sur None
# L'objet est None - vérifier avant:
if obj is not None:
    value = obj.{attr}

# Ou utiliser getattr:
value = getattr(obj, '{attr}', default)

# Ou operator walrus:
if (obj := get_object()) is not None:
    value = obj.{attr}"""
            confidence = 0.85

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
    """
    Analyseur pour les erreurs SQL/SQLAlchemy.

    Génère des vrais SQL ALTER TABLE exécutables, pas juste des commentaires.
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.SQL

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        return [
            # NOT NULL violation - très courant, fix simple
            (r'null value in column "(\w+)" of relation "(\w+)" violates not-null',
             "Violation NOT NULL", 0.90),
            # Colonne manquante
            (r'column "(\w+)" of relation "(\w+)" does not exist',
             "Colonne inexistante", 0.85),
            # Colonne manquante (autre format)
            (r'column "(\w+)" does not exist',
             "Colonne inexistante", 0.80),
            # Table manquante
            (r'relation "(\w+)" does not exist',
             "Table inexistante", 0.70),
            # Doublon
            (r"duplicate key value violates unique constraint",
             "Doublon - clé unique", 0.60),
            # Foreign key
            (r"violates foreign key constraint",
             "Violation foreign key", 0.55),
        ]

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Analyse une erreur SQL et propose un fix SQL exécutable."""
        file_path, line_num = self._extract_file_info(error_log)

        # Chercher NOT NULL violation en premier (le plus courant)
        not_null_match = re.search(
            r'null value in column "(\w+)" of relation "(\w+)" violates not-null',
            error_log, re.IGNORECASE
        )
        if not_null_match:
            col, table = not_null_match.groups()
            default_value = self._get_smart_default(col)
            proposed_fix = f"ALTER TABLE azalplus.{table} ALTER COLUMN {col} SET DEFAULT {default_value}"
            return FixProposal(
                id=FixProposal.generate_id(error_log),
                error_type="SQLError",
                error_message=error_log[:500],
                category=self.category,
                file_path=file_path,
                line_number=line_num,
                original_code=None,
                proposed_fix=proposed_fix,
                confidence=0.90,
                created_at=datetime.now(),
                status=FixStatus.PENDING
            )

        # Colonne manquante avec table
        col_match = re.search(
            r'column "(\w+)" of relation "(\w+)" does not exist',
            error_log, re.IGNORECASE
        )
        if col_match:
            col, table = col_match.groups()
            col_type = self._guess_column_type(col)
            proposed_fix = f"ALTER TABLE azalplus.{table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
            return FixProposal(
                id=FixProposal.generate_id(error_log),
                error_type="SQLError",
                error_message=error_log[:500],
                category=self.category,
                file_path=file_path,
                line_number=line_num,
                original_code=None,
                proposed_fix=proposed_fix,
                confidence=0.85,
                created_at=datetime.now(),
                status=FixStatus.PENDING
            )

        # Colonne manquante sans table - chercher la table dans le contexte
        col_only_match = re.search(r'column "(\w+)" does not exist', error_log, re.IGNORECASE)
        if col_only_match:
            col = col_only_match.group(1)
            # Chercher la table dans l'erreur
            table_match = re.search(r'relation "(\w+)"', error_log)
            table = table_match.group(1) if table_match else "UNKNOWN_TABLE"
            col_type = self._guess_column_type(col)
            proposed_fix = f"ALTER TABLE azalplus.{table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
            return FixProposal(
                id=FixProposal.generate_id(error_log),
                error_type="SQLError",
                error_message=error_log[:500],
                category=self.category,
                file_path=file_path,
                line_number=line_num,
                original_code=None,
                proposed_fix=proposed_fix,
                confidence=0.80,
                created_at=datetime.now(),
                status=FixStatus.PENDING
            )

        # Autres patterns avec fixes génériques
        for pattern, desc, confidence in self.patterns:
            match = re.search(pattern, error_log, re.IGNORECASE)
            if match:
                proposed_fix = self._generate_generic_fix(desc, error_log)
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

    def _get_smart_default(self, column_name: str) -> str:
        """Retourne une valeur par défaut intelligente basée sur le nom de colonne."""
        name = column_name.lower()

        # Texte / titres
        if any(x in name for x in ['titre', 'title', 'name', 'nom', 'label']):
            return "'Sans titre'"
        if any(x in name for x in ['description', 'notes', 'comment', 'remarque']):
            return "''"
        # Statut
        if 'statut' in name or 'status' in name:
            return "'BROUILLON'"
        if 'etat' in name or 'state' in name:
            return "'ACTIF'"
        # Civilité
        if 'civilite' in name:
            return "''"
        # Référence / code
        if any(x in name for x in ['reference', 'code', 'ref']):
            return "''"
        # Montants
        if any(x in name for x in ['montant', 'prix', 'total', 'amount', 'price', 'cout']):
            return "0"
        # Quantités
        if any(x in name for x in ['quantite', 'qty', 'nombre', 'count', 'duree']):
            return "0"
        # Booléens
        if any(x in name for x in ['is_', 'has_', 'actif', 'active', 'enabled', 'visible']):
            return "false"
        # Email / contact
        if any(x in name for x in ['email', 'mail', 'telephone', 'tel', 'phone']):
            return "''"
        # Type / catégorie
        if any(x in name for x in ['type', 'categorie', 'category']):
            return "'AUTRE'"
        # Adresse
        if any(x in name for x in ['adresse', 'address', 'ville', 'city', 'pays', 'country']):
            return "''"

        # Défaut générique
        return "''"

    def _guess_column_type(self, column_name: str) -> str:
        """Devine le type PostgreSQL basé sur le nom de colonne."""
        name = column_name.lower()

        # UUID / IDs
        if name.endswith('_id') or name == 'id':
            return "UUID"
        # Dates
        if any(x in name for x in ['date', 'created_at', 'updated_at', 'deleted_at', '_at']):
            return "TIMESTAMP"
        # Booléens
        if any(x in name for x in ['is_', 'has_', 'actif', 'active', 'enabled', 'visible']):
            return "BOOLEAN DEFAULT false"
        # Montants
        if any(x in name for x in ['montant', 'prix', 'total', 'amount', 'price', 'cout', 'taux']):
            return "NUMERIC(15,2) DEFAULT 0"
        # Quantités
        if any(x in name for x in ['quantite', 'qty', 'nombre', 'count', 'duree', 'minutes']):
            return "INTEGER DEFAULT 0"
        # Texte long
        if any(x in name for x in ['description', 'notes', 'content', 'body', 'remarque', 'commentaire']):
            return "TEXT"
        # JSON
        if any(x in name for x in ['data', 'meta', 'config', 'settings', 'json', 'options']):
            return "JSONB DEFAULT '{}'"
        # Tags
        if 'tags' in name:
            return "JSONB DEFAULT '[]'"

        # Défaut: VARCHAR
        return "VARCHAR(255)"

    def _generate_generic_fix(self, desc: str, error_log: str) -> str:
        """Génère un fix générique pour les cas non traités."""
        if "Doublon" in desc:
            return "-- Doublon: vérifier les contraintes UNIQUE ou utiliser ON CONFLICT"
        if "foreign key" in desc.lower():
            return "-- Foreign key: vérifier que l'enregistrement parent existe"
        if "Table inexistante" in desc:
            table_match = re.search(r'relation "(\w+)"', error_log)
            if table_match:
                return f"-- Table '{table_match.group(1)}' manquante: vérifier le module YAML correspondant"
        return "-- Erreur SQL: vérifier la syntaxe et les contraintes"


class JavaScriptErrorAnalyzer(ErrorAnalyzer):
    """
    Analyseur spécialisé pour les erreurs JavaScript.

    Peut détecter et proposer des fixes pour :
    - Fonctions non définies (ReferenceError)
    - Propriétés undefined (TypeError)
    - Problèmes d'API navigateur (clipboard, etc.)
    """

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.UNKNOWN

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        return [
            (r"ReferenceError: (\w+) is not defined", "Fonction/variable JS non définie", 0.95),
            (r"TypeError: Cannot read properties of undefined \(reading '(\w+)'\)", "Propriété undefined", 0.90),
            (r"TypeError: (\w+) is not a function", "Non-fonction appelée", 0.80),
        ]

    # Définitions de fonctions JS communes
    JS_FUNCTION_FIXES = {
        "handleRowClick": '''function handleRowClick(event, id, url) {
    if (event.target.type === 'checkbox' || event.target.tagName === 'BUTTON' || event.target.closest('button')) {
        return;
    }
    window.location.href = url;
}''',
        "copyMobileLink": '''async function copyMobileLink() {
    const link = document.getElementById('mobileLink')?.value || window.location.href;
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(link);
        } else {
            const textarea = document.createElement('textarea');
            textarea.value = link;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
        showNotification('Lien copié !', 'success');
    } catch (err) {
        console.error('Erreur copie:', err);
        showNotification('Erreur lors de la copie', 'error');
    }
}''',
        "showNotification": '''function showNotification(message, type = 'info') {
    const container = document.getElementById('notifications') || document.body;
    const notif = document.createElement('div');
    notif.className = 'notification notification-' + type;
    notif.textContent = message;
    notif.style.cssText = 'position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;z-index:9999;color:white;';
    notif.style.background = type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6';
    container.appendChild(notif);
    setTimeout(() => notif.remove(), 3000);
}''',
        "toggleSelectAll": '''function toggleSelectAll(checkbox) {
    document.querySelectorAll('input[name="selected_ids"]').forEach(cb => cb.checked = checkbox.checked);
    updateBulkActions();
}''',
        "updateBulkActions": '''function updateBulkActions() {
    const selected = document.querySelectorAll('input[name="selected_ids"]:checked').length;
    const bulkBar = document.getElementById('bulkActions');
    if (bulkBar) bulkBar.style.display = selected > 0 ? 'flex' : 'none';
    const countSpan = document.getElementById('selectedCount');
    if (countSpan) countSpan.textContent = selected;
}''',
        "confirmDelete": '''function confirmDelete(id, name) {
    if (confirm('Êtes-vous sûr de vouloir supprimer "' + name + '" ?')) {
        fetch(window.location.pathname + '/' + id, { method: 'DELETE' })
            .then(r => r.ok ? location.reload() : alert('Erreur'))
            .catch(e => alert('Erreur: ' + e));
    }
}''',
        "openModal": '''function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) { modal.style.display = 'flex'; modal.classList.add('active'); }
}''',
        "closeModal": '''function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) { modal.style.display = 'none'; modal.classList.remove('active'); }
}''',
    }

    # Polyfills pour APIs navigateur
    API_POLYFILLS = {
        "writeText": '''// Polyfill clipboard pour HTTP
if (!navigator.clipboard) {
    navigator.clipboard = {
        writeText: async (text) => {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    };
}''',
    }

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Analyse une erreur JavaScript et propose un fix."""

        # ReferenceError: X is not defined
        ref_error = re.search(r"ReferenceError: (\w+) is not defined", error_log)
        if ref_error:
            func_name = ref_error.group(1)
            return self._create_function_fix(func_name, error_log)

        # TypeError: Cannot read properties of undefined (reading 'X')
        type_error = re.search(r"Cannot read properties of undefined \(reading '(\w+)'\)", error_log)
        if type_error:
            prop_name = type_error.group(1)
            return self._create_api_fix(prop_name, error_log)

        return None

    def _create_function_fix(self, func_name: str, error_log: str) -> FixProposal:
        """Crée un fix pour une fonction JS manquante."""
        if func_name in self.JS_FUNCTION_FIXES:
            js_code = self.JS_FUNCTION_FIXES[func_name]
            proposed_fix = f"CODE_JS_ADD:{func_name}\n{js_code}"
            confidence = 0.95
        else:
            proposed_fix = f"CODE_JS_ADD:{func_name}\nfunction {func_name}(...args) {{ console.log('{func_name}', args); }}"
            confidence = 0.60

        return FixProposal(
            id=FixProposal.generate_id(error_log),
            error_type="JSReferenceError",
            error_message=f"Function '{func_name}' is not defined",
            category=self.category,
            file_path="/home/ubuntu/azalplus/moteur/ui.py",
            line_number=None,
            original_code=None,
            proposed_fix=proposed_fix,
            confidence=confidence,
            created_at=datetime.now(),
            status=FixStatus.PENDING,
            metadata={"js_function": func_name, "fix_type": "add_function"}
        )

    def _create_api_fix(self, prop_name: str, error_log: str) -> FixProposal:
        """Crée un fix pour une erreur d'API navigateur."""
        if prop_name in self.API_POLYFILLS:
            js_code = self.API_POLYFILLS[prop_name]
            proposed_fix = f"CODE_JS_ADD:polyfill_{prop_name}\n{js_code}"
            confidence = 0.90
        else:
            proposed_fix = f"CODE_JS_FIX:null_check_{prop_name}\n// Ajouter vérification: if (obj && obj.{prop_name}) {{ ... }}"
            confidence = 0.50

        return FixProposal(
            id=FixProposal.generate_id(error_log),
            error_type="JSTypeError",
            error_message=f"Cannot read property '{prop_name}' of undefined",
            category=self.category,
            file_path="/home/ubuntu/azalplus/moteur/ui.py",
            line_number=None,
            original_code=None,
            proposed_fix=proposed_fix,
            confidence=confidence,
            created_at=datetime.now(),
            status=FixStatus.PENDING,
            metadata={"js_property": prop_name, "fix_type": "api_polyfill"}
        )


class FrontendErrorAnalyzer(ErrorAnalyzer):
    """Analyseur pour les erreurs frontend (404, JS, réseau)."""

    @property
    def category(self) -> ErrorCategory:
        return ErrorCategory.UNKNOWN  # Frontend category

    @property
    def patterns(self) -> List[Tuple[str, str, float]]:
        return [
            (r"FRONTEND ERROR \[404\].*Failed to load.*: (.+)",
             "Ressource 404", 0.9),
            (r"FRONTEND ERROR \[js_error\].*Message: (.+)",
             "Erreur JavaScript", 0.6),
            (r"FRONTEND ERROR \[http_(\d+)\]",
             "Erreur HTTP", 0.7),
            (r"FRONTEND ERROR \[network_error\]",
             "Erreur réseau", 0.5),
            (r"FRONTEND ERROR \[promise_rejection\]",
             "Promise non gérée", 0.5),
        ]

    def analyze(self, error_log: str) -> Optional[FixProposal]:
        """Analyse une erreur frontend."""
        if "FRONTEND ERROR" not in error_log:
            return None

        # Extraire les infos
        url_match = re.search(r"URL: (.+)", error_log)
        source_match = re.search(r"Source: ([^\n:]+)", error_log)
        message_match = re.search(r"Message: (.+)", error_log)

        url = url_match.group(1) if url_match else None
        source = source_match.group(1) if source_match else None
        message = message_match.group(1) if message_match else error_log[:200]

        # Erreur 404 - ressource manquante
        if "[404]" in error_log:
            proposed_fix = self._analyze_404(source, message)
            return FixProposal(
                id=FixProposal.generate_id(error_log),
                error_type="Frontend404",
                error_message=message,
                category=self.category,
                file_path=source,
                line_number=None,
                original_code=None,
                proposed_fix=proposed_fix,
                confidence=0.9,
                created_at=datetime.now(),
                status=FixStatus.PENDING,
                metadata={"url": url, "frontend": True}
            )

        # Erreur JavaScript - utiliser l'analyseur spécialisé
        elif "[js_error]" in error_log or "ReferenceError" in error_log or "TypeError" in error_log:
            js_analyzer = JavaScriptErrorAnalyzer()
            js_proposal = js_analyzer.analyze(error_log)
            if js_proposal:
                return js_proposal
            # Fallback si JS analyzer n'a pas trouvé
            return FixProposal(
                id=FixProposal.generate_id(error_log),
                error_type="FrontendJSError",
                error_message=message,
                category=self.category,
                file_path=source,
                line_number=None,
                original_code=None,
                proposed_fix="# Erreur JavaScript - analyse manuelle requise",
                confidence=0.3,
                created_at=datetime.now(),
                status=FixStatus.NEEDS_CLAUDE,
                metadata={"url": url, "frontend": True}
            )

        return None

    def _analyze_404(self, source: str, message: str) -> str:
        """Génère un fix pour une erreur 404."""
        if not source:
            return "# Ressource manquante - créer le fichier"

        # API path incorrect - HAUTE PRIORITÉ
        if "/api/" in source:
            return self._analyze_api_404(source)

        # Icône manquante
        if "/icons/" in source and source.endswith(".svg"):
            icon_name = source.split("/")[-1]
            return f"# Icône manquante: {icon_name}\n# Créer le fichier dans /assets/icons/{icon_name}\n# Format: SVG Lucide (24x24, stroke)"

        # Image manquante
        if any(ext in source for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
            return f"# Image manquante: {source.split('/')[-1]}\n# Ajouter l'image dans /assets/images/"

        # JS manquant
        if source.endswith(".js"):
            return f"# Script JS manquant: {source.split('/')[-1]}\n# Vérifier le chemin ou créer le fichier"

        # CSS manquant
        if source.endswith(".css"):
            return f"# Feuille de style manquante: {source.split('/')[-1]}\n# Vérifier le chemin ou créer le fichier"

        return f"# Ressource manquante: {source}\n# Créer le fichier ou corriger le chemin"

    def _analyze_api_404(self, api_path: str) -> str:
        """Analyse une erreur 404 sur une API et génère le fix."""
        import os
        from pathlib import Path

        # Extraire le nom du module de l'API
        # /api/Client -> Client
        # /api/v1/clients -> clients
        match = re.search(r'/api/(?:v1/)?(\w+)', api_path)
        if not match:
            return f"# API path incorrect: {api_path}"

        module_name = match.group(1)
        modules_path = Path("/home/ubuntu/azalplus/modules")

        # Convertir CamelCase en snake_case
        def to_snake_case(name):
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        snake_name = to_snake_case(module_name)

        # Chercher le module correct
        correct_module = None

        # 1. Essayer snake_case
        if (modules_path / f"{snake_name}.yml").exists():
            correct_module = snake_name
        # 2. Essayer snake_case pluriel
        elif (modules_path / f"{snake_name}s.yml").exists():
            correct_module = f"{snake_name}s"
        # 3. Essayer lowercase
        elif (modules_path / f"{module_name.lower()}.yml").exists():
            correct_module = module_name.lower()
        # 4. Essayer lowercase pluriel
        elif (modules_path / f"{module_name.lower()}s.yml").exists():
            correct_module = f"{module_name.lower()}s"

        if correct_module:
            # Chercher où ce fetch incorrect est utilisé
            search_pattern = f"fetch.*['\"`]/api/{module_name}['\"`]|fetch.*['\"`]/api/v1/{module_name}['\"`]"

            # Générer un fix exécutable
            fix = f"""AUTO_FIX_API_PATH
old_path: /api/{module_name}
new_path: /api/v1/{correct_module}
search_dirs: moteur,templates
action: replace_in_files"""
            return fix

        # Module non trouvé
        return f"""# API 404: {api_path}
# Module '{module_name}' non trouvé
# Vérifier si le module existe dans /modules/
# Ou créer le fichier: modules/{snake_name}.yml"""


class CompositeAnalyzer(ErrorAnalyzer):
    """
    Analyseur composite qui combine plusieurs analyseurs.
    Essaie chaque analyseur dans l'ordre jusqu'à trouver un match.
    """

    def __init__(self, analyzers: List[ErrorAnalyzer] = None):
        self._analyzers = analyzers or [
            JavaScriptErrorAnalyzer(),  # JS en premier (erreurs frontend courantes)
            FrontendErrorAnalyzer(),    # Frontend général
            SQLErrorAnalyzer(),          # SQL (erreurs DB courantes)
            PythonErrorAnalyzer(),       # Python
            YAMLErrorAnalyzer(),         # YAML
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
