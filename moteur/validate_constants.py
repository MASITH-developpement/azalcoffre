#!/usr/bin/env python3
# =============================================================================
# AZALPLUS - Validateur de Constantes
# =============================================================================
"""
Valide les constantes centralisées et détecte les problèmes.

Usage:
    python -m moteur.validate_constants
    python -m moteur.validate_constants --fix
    python -m moteur.validate_constants --generate-stub

Vérifications:
    - Syntaxe YAML valide
    - Types corrects (TVA = nombre, etc.)
    - Références croisées (statuts utilisés existent)
    - Constantes orphelines (définies mais jamais utilisées)
    - Doublons
    - Cohérence avec les modules YAML
"""

import os
import sys
import re
import ast
import yaml
import argparse
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json

# =============================================================================
# Configuration
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
MOTEUR_DIR = BASE_DIR / "moteur"
MODULES_DIR = BASE_DIR / "modules"
CONSTANTS_FILE = CONFIG_DIR / "constants.yml"

# Debug: afficher les chemins si problème
if not CONSTANTS_FILE.exists():
    import sys
    print(f"DEBUG: BASE_DIR = {BASE_DIR}", file=sys.stderr)
    print(f"DEBUG: CONSTANTS_FILE = {CONSTANTS_FILE}", file=sys.stderr)
    print(f"DEBUG: exists = {CONSTANTS_FILE.exists()}", file=sys.stderr)

# Couleurs terminal
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def color(text: str, c: str) -> str:
    """Applique une couleur au texte."""
    if not sys.stdout.isatty():
        return text
    return f"{c}{text}{Colors.RESET}"

# =============================================================================
# Structures de données
# =============================================================================
@dataclass
class ValidationError:
    """Erreur de validation."""
    code: str
    message: str
    file: str = ""
    line: int = 0
    severity: str = "error"  # error, warning, info

    def __str__(self):
        loc = f"{self.file}:{self.line}" if self.file else ""
        return f"[{self.code}] {self.message} {loc}".strip()

@dataclass
class ValidationResult:
    """Résultat de validation."""
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    info: List[ValidationError] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, error: ValidationError):
        if error.severity == "error":
            self.errors.append(error)
        elif error.severity == "warning":
            self.warnings.append(error)
        else:
            self.info.append(error)

# =============================================================================
# Validateur principal
# =============================================================================
class ConstantsValidator:
    """Validateur de constantes."""

    def __init__(self):
        self.constants: Dict[str, Any] = {}
        self.result = ValidationResult()
        self.usages: Dict[str, List[Tuple[str, int]]] = defaultdict(list)  # path -> [(file, line)]
        self.definitions: Set[str] = set()  # Chemins définis

    def load_constants(self) -> bool:
        """Charge le fichier constants.yml."""
        if not CONSTANTS_FILE.exists():
            self.result.add(ValidationError(
                code="YAML001",
                message=f"Fichier constants.yml introuvable: {CONSTANTS_FILE}",
                severity="error"
            ))
            return False

        try:
            with open(CONSTANTS_FILE, "r", encoding="utf-8") as f:
                self.constants = yaml.safe_load(f)
            self.result.stats["yaml_loaded"] = 1
            return True
        except yaml.YAMLError as e:
            self.result.add(ValidationError(
                code="YAML002",
                message=f"Erreur de syntaxe YAML: {e}",
                file=str(CONSTANTS_FILE),
                severity="error"
            ))
            return False

    def validate_structure(self):
        """Valide la structure du fichier."""
        required_sections = [
            "statuts", "tva", "devises", "limites",
            "types_champs", "colonnes_systeme", "messages", "systeme"
        ]

        for section in required_sections:
            if section not in self.constants:
                self.result.add(ValidationError(
                    code="STRUCT001",
                    message=f"Section obligatoire manquante: {section}",
                    severity="error"
                ))

        # Version
        if "version" not in self.constants:
            self.result.add(ValidationError(
                code="STRUCT002",
                message="Version manquante",
                severity="warning"
            ))

    def validate_types(self):
        """Valide les types des valeurs."""
        # TVA doit être des nombres
        tva = self.constants.get("tva", {})
        for pays, config in tva.items():
            if pays in ("defaut",):
                continue
            if isinstance(config, dict):
                for type_tva, valeur in config.items():
                    if type_tva == "defaut":
                        continue
                    if not isinstance(valeur, (int, float)):
                        self.result.add(ValidationError(
                            code="TYPE001",
                            message=f"tva.{pays}.{type_tva} doit être un nombre, reçu: {type(valeur).__name__} ({valeur})",
                            severity="error"
                        ))

        # Limites doivent être des entiers positifs
        limites = self.constants.get("limites", {})
        self._validate_limits_recursive(limites, "limites")

        # Décimales devises
        devises = self.constants.get("devises", {})
        for code, config in devises.items():
            if code in ("defaut", "base"):
                continue
            if isinstance(config, dict):
                decimales = config.get("decimales")
                if decimales is not None and not isinstance(decimales, int):
                    self.result.add(ValidationError(
                        code="TYPE002",
                        message=f"devises.{code}.decimales doit être un entier",
                        severity="error"
                    ))

    def _validate_limits_recursive(self, obj: Any, path: str):
        """Valide les limites récursivement."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}"
                if key in ("min", "max", "defaut") and isinstance(value, (int, float)):
                    if value < 0:
                        self.result.add(ValidationError(
                            code="TYPE003",
                            message=f"{new_path} ne devrait pas être négatif: {value}",
                            severity="warning"
                        ))
                else:
                    self._validate_limits_recursive(value, new_path)

    def validate_statuts(self):
        """Valide les statuts."""
        statuts = self.constants.get("statuts", {})

        for module, config in statuts.items():
            if module == "generiques":
                continue

            # Vérifier que c'est une liste ou un dict avec des statuts
            if isinstance(config, list):
                if len(config) == 0:
                    self.result.add(ValidationError(
                        code="STATUT001",
                        message=f"statuts.{module} est vide",
                        severity="error"
                    ))
                # Vérifier les doublons
                if len(config) != len(set(config)):
                    self.result.add(ValidationError(
                        code="STATUT002",
                        message=f"statuts.{module} contient des doublons",
                        severity="error"
                    ))
            elif isinstance(config, dict):
                # Nouveau format avec "valeurs"
                if "valeurs" in config:
                    valeurs = config["valeurs"]
                    if len(valeurs) == 0:
                        self.result.add(ValidationError(
                            code="STATUT001",
                            message=f"statuts.{module}.valeurs est vide",
                            severity="error"
                        ))
                    if len(valeurs) != len(set(valeurs)):
                        self.result.add(ValidationError(
                            code="STATUT002",
                            message=f"statuts.{module}.valeurs contient des doublons",
                            severity="error"
                        ))
                else:
                    # Ancien format
                    statuts_list = [k for k in config.keys() if k != "defaut"]
                    if len(statuts_list) == 0:
                        self.result.add(ValidationError(
                            code="STATUT001",
                            message=f"statuts.{module} est vide",
                            severity="error"
                        ))

        # Vérifier que les couleurs de statuts existent
        couleurs = self.constants.get("couleurs_statuts", {})
        all_statuts = set()
        for module, config in statuts.items():
            if isinstance(config, list):
                all_statuts.update(config)
            elif isinstance(config, dict):
                if "valeurs" in config:
                    all_statuts.update(config["valeurs"])
                else:
                    all_statuts.update(k for k in config.keys() if k not in ("defaut", "valeurs"))

        for statut in all_statuts:
            if statut not in couleurs and statut != "valeurs":
                self.result.add(ValidationError(
                    code="STATUT003",
                    message=f"Couleur manquante pour statut: {statut}",
                    severity="warning"
                ))

    def collect_definitions(self, obj: Any = None, path: str = ""):
        """Collecte tous les chemins définis dans constants.yml."""
        if obj is None:
            obj = self.constants

        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                self.definitions.add(new_path)
                self.collect_definitions(value, new_path)
        elif isinstance(obj, list):
            self.definitions.add(path)

    def scan_python_files(self):
        """Scanne les fichiers Python pour trouver les usages de constantes."""
        patterns = [
            r'get\(["\']([^"\']+)["\']\)',  # get("chemin.vers.valeur")
            r'CONSTANTS\[["\']([^"\']+)["\']\]',  # CONSTANTS["section"]
            r'get_statuts\(["\']([^"\']+)["\']\)',  # get_statuts("module")
            r'get_tva\(["\']([^"\']+)["\']',  # get_tva("pays"
            r'get_limite\(["\']([^"\']+)["\']',  # get_limite("categorie"
            r'\$([a-z_\.]+)',  # $statuts.factures (dans les strings)
        ]

        # Patterns à ignorer (exemples dans docstrings)
        ignore_values = {"chemin.vers.valeur", "section.key", "module.name"}

        for py_file in MOTEUR_DIR.glob("**/*.py"):
            if py_file.name == "validate_constants.py":
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                lines = content.split("\n")

                in_docstring = False
                for line_num, line in enumerate(lines, 1):
                    # Détecter les docstrings (simpliste mais suffisant)
                    if '"""' in line or "'''" in line:
                        in_docstring = not in_docstring

                    # Ignorer les commentaires et docstrings
                    if in_docstring or line.strip().startswith("#"):
                        continue

                    for pattern in patterns:
                        matches = re.findall(pattern, line)
                        for match in matches:
                            if match not in ignore_values:
                                self.usages[match].append((str(py_file), line_num))

            except Exception as e:
                self.result.add(ValidationError(
                    code="SCAN001",
                    message=f"Erreur lecture {py_file}: {e}",
                    severity="warning"
                ))

        self.result.stats["python_files_scanned"] = len(list(MOTEUR_DIR.glob("**/*.py")))

    def scan_yaml_modules(self):
        """Scanne les modules YAML pour trouver les références."""
        pattern = r'\$([a-z_\.]+)'

        for yaml_file in MODULES_DIR.glob("*.yml"):
            try:
                content = yaml_file.read_text(encoding="utf-8")
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    matches = re.findall(pattern, line)
                    for match in matches:
                        self.usages[match].append((str(yaml_file), line_num))

            except Exception as e:
                self.result.add(ValidationError(
                    code="SCAN002",
                    message=f"Erreur lecture {yaml_file}: {e}",
                    severity="warning"
                ))

        self.result.stats["yaml_modules_scanned"] = len(list(MODULES_DIR.glob("*.yml")))

    def validate_references(self):
        """Valide que les références utilisées existent."""
        # Mots à ignorer (trop courts, mots-clés communs, chemins API)
        ignore_patterns = {
            "id", "ids", "db", "ok", "no", "on", "or", "to", "is", "it", "if",
            "tenant_id", "user_id", "record_id", "module", "data", "item",
            "error", "result", "value", "key", "name", "type", "status",
        }

        for path, locations in self.usages.items():
            # Ignorer les chemins courts ou communs
            if len(path) < 4:
                continue
            if path.lower() in ignore_patterns:
                continue
            if path.startswith("/"):  # Chemins API
                continue
            if path.startswith("http"):  # URLs
                continue
            if "." not in path:  # Pas un chemin de constante
                continue

            # Vérifier si le chemin existe
            if not self._path_exists(path):
                # Peut-être un chemin partiel (ex: "statuts" au lieu de "statuts.factures")
                if not any(d.startswith(path + ".") for d in self.definitions):
                    for file, line in locations[:3]:  # Max 3 occurrences
                        self.result.add(ValidationError(
                            code="REF001",
                            message=f"Référence non trouvée: {path}",
                            file=file,
                            line=line,
                            severity="error"
                        ))

    def _path_exists(self, path: str) -> bool:
        """Vérifie si un chemin existe dans les constantes."""
        keys = path.split(".")
        obj = self.constants

        try:
            for key in keys:
                if isinstance(obj, dict):
                    obj = obj[key]
                elif isinstance(obj, list) and key.isdigit():
                    obj = obj[int(key)]
                else:
                    return False
            return True
        except (KeyError, IndexError, TypeError):
            return False

    def find_orphans(self):
        """Trouve les constantes définies mais jamais utilisées."""
        used_paths = set(self.usages.keys())

        # Exclure les chemins internes
        excluded_prefixes = ("version", "derniere_modification", "_", "defaut")

        for definition in self.definitions:
            # Ne pas signaler les sections principales
            if "." not in definition:
                continue

            # Vérifier si utilisé directement ou comme préfixe
            is_used = False
            for used in used_paths:
                if used == definition or used.startswith(definition + ".") or definition.startswith(used + "."):
                    is_used = True
                    break

            if not is_used:
                # Vérifier les exclusions
                parts = definition.split(".")
                if any(p.startswith(prefix) for p in parts for prefix in excluded_prefixes):
                    continue

                self.result.add(ValidationError(
                    code="ORPHAN001",
                    message=f"Constante définie mais jamais utilisée: {definition}",
                    severity="info"
                ))

    def validate_modules_consistency(self):
        """Vérifie la cohérence entre constants.yml et les modules YAML."""
        # Charger les statuts utilisés dans les modules
        module_statuts = defaultdict(set)

        for yaml_file in MODULES_DIR.glob("*.yml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    module = yaml.safe_load(f)

                if not module:
                    continue

                module_name = yaml_file.stem

                # Chercher les champs de type select avec options
                champs = module.get("champs", [])
                if isinstance(champs, list):
                    for champ in champs:
                        if isinstance(champ, dict):
                            if champ.get("type") in ("select", "enum") and champ.get("nom") == "statut":
                                options = champ.get("options", [])
                                if isinstance(options, list):
                                    # Normaliser en majuscules
                                    module_statuts[module_name].update(s.upper() for s in options)

            except Exception:
                pass

        # Comparer avec constants.yml
        constants_statuts = self.constants.get("statuts", {})

        for module, statuts in module_statuts.items():
            if module in constants_statuts:
                const_statuts = constants_statuts[module]
                if isinstance(const_statuts, list):
                    const_set = set(s.upper() for s in const_statuts)
                elif isinstance(const_statuts, dict):
                    # Nouveau format avec "valeurs"
                    if "valeurs" in const_statuts:
                        const_set = set(s.upper() for s in const_statuts["valeurs"])
                    else:
                        const_set = set(k.upper() for k in const_statuts.keys() if k not in ("defaut", "valeurs"))
                else:
                    continue

                # Statuts dans le module mais pas dans constants (comparaison insensible à la casse)
                diff = statuts - const_set
                if diff:
                    self.result.add(ValidationError(
                        code="CONSIST001",
                        message=f"Statuts dans {module}.yml mais pas dans constants.yml: {diff}",
                        file=f"modules/{module}.yml",
                        severity="warning"
                    ))

    def generate_stub(self) -> str:
        """Génère un fichier .pyi pour l'autocomplétion IDE."""
        lines = [
            '"""',
            'AZALPLUS Constants - Type Stubs',
            'Auto-generated by validate_constants.py',
            '"""',
            '',
            'from typing import Any, Dict, List, Optional, Union',
            '',
            '# Constantes principales',
            f'VERSION: str',
            f'CONSTANTS: Dict[str, Any]',
            '',
        ]

        # Sections principales
        for section in self.constants.keys():
            if section.startswith("_") or section in ("version", "derniere_modification"):
                continue
            lines.append(f'{section.upper()}: Dict[str, Any]')

        lines.extend([
            '',
            '# Fonctions d\'accès',
            'def get(path: str, default: Any = None) -> Any: ...',
            'def get_or_raise(path: str) -> Any: ...',
            'def get_statuts(module: str) -> List[str]: ...',
            'def get_statut_defaut(module: str) -> str: ...',
            'def get_couleur_statut(statut: str) -> str: ...',
            'def get_tva(pays: str = "france", type_tva: str = "normal") -> float: ...',
            'def get_tva_options(pays: str = "france") -> Dict[str, float]: ...',
            'def get_devise(code: str = None) -> Dict[str, Any]: ...',
            'def get_devises_disponibles() -> List[str]: ...',
            'def get_limite(categorie: str, cle: str = None) -> Union[int, Dict[str, Any]]: ...',
            'def get_format(type_format: str, variante: str = "affichage") -> str: ...',
            'def get_message(code: str) -> str: ...',
            'def get_roles() -> Dict[str, Dict[str, Any]]: ...',
            'def get_role(code: str) -> Dict[str, Any]: ...',
            'def get_type_champ(type_yaml: str) -> Dict[str, Any]: ...',
            'def get_colonnes_systeme() -> List[Dict[str, Any]]: ...',
            'def resolve_reference(ref: str) -> Any: ...',
            'def reload_constants() -> None: ...',
            'def validate() -> Dict[str, Any]: ...',
            '',
        ])

        # Statuts disponibles (pour autocomplétion)
        lines.append('# Statuts disponibles')
        statuts = self.constants.get("statuts", {})
        for module, config in statuts.items():
            if isinstance(config, list):
                values = config
            elif isinstance(config, dict):
                values = [k for k in config.keys() if k != "defaut"]
            else:
                continue
            lines.append(f'# {module}: {", ".join(values)}')

        return "\n".join(lines)

    def run(self, fix: bool = False, generate_stub: bool = False) -> ValidationResult:
        """Exécute toutes les validations."""
        print(color("\n=== AZALPLUS Constants Validator ===\n", Colors.BOLD))

        # 1. Charger le fichier
        print("1. Chargement de constants.yml...", end=" ")
        if not self.load_constants():
            print(color("ERREUR", Colors.RED))
            return self.result
        print(color("OK", Colors.GREEN))

        # 2. Valider la structure
        print("2. Validation de la structure...", end=" ")
        self.validate_structure()
        print(color("OK", Colors.GREEN))

        # 3. Valider les types
        print("3. Validation des types...", end=" ")
        self.validate_types()
        print(color("OK", Colors.GREEN))

        # 4. Valider les statuts
        print("4. Validation des statuts...", end=" ")
        self.validate_statuts()
        print(color("OK", Colors.GREEN))

        # 5. Collecter les définitions
        print("5. Collecte des définitions...", end=" ")
        self.collect_definitions()
        self.result.stats["definitions"] = len(self.definitions)
        print(color(f"OK ({len(self.definitions)} chemins)", Colors.GREEN))

        # 6. Scanner les fichiers Python
        print("6. Scan des fichiers Python...", end=" ")
        self.scan_python_files()
        print(color(f"OK ({self.result.stats.get('python_files_scanned', 0)} fichiers)", Colors.GREEN))

        # 7. Scanner les modules YAML
        print("7. Scan des modules YAML...", end=" ")
        self.scan_yaml_modules()
        print(color(f"OK ({self.result.stats.get('yaml_modules_scanned', 0)} modules)", Colors.GREEN))

        # 8. Valider les références
        print("8. Validation des références...", end=" ")
        self.validate_references()
        print(color("OK", Colors.GREEN))

        # 9. Trouver les orphelins
        print("9. Détection des orphelins...", end=" ")
        self.find_orphans()
        print(color("OK", Colors.GREEN))

        # 10. Cohérence modules
        print("10. Vérification cohérence modules...", end=" ")
        self.validate_modules_consistency()
        print(color("OK", Colors.GREEN))

        # Générer le stub si demandé
        if generate_stub:
            print("\n11. Génération du stub .pyi...", end=" ")
            stub_content = self.generate_stub()
            stub_file = MOTEUR_DIR / "constants.pyi"
            stub_file.write_text(stub_content, encoding="utf-8")
            print(color(f"OK ({stub_file})", Colors.GREEN))

        # Résumé
        print("\n" + "=" * 50)
        self._print_summary()

        return self.result

    def _print_summary(self):
        """Affiche le résumé de la validation."""
        total_errors = len(self.result.errors)
        total_warnings = len(self.result.warnings)
        total_info = len(self.result.info)

        if total_errors == 0:
            print(color("✓ Validation réussie!", Colors.GREEN + Colors.BOLD))
        else:
            print(color(f"✗ {total_errors} erreur(s) trouvée(s)", Colors.RED + Colors.BOLD))

        if total_warnings > 0:
            print(color(f"⚠ {total_warnings} avertissement(s)", Colors.YELLOW))

        if total_info > 0:
            print(color(f"ℹ {total_info} info(s)", Colors.BLUE))

        # Détails des erreurs
        if self.result.errors:
            print(color("\nErreurs:", Colors.RED + Colors.BOLD))
            for err in self.result.errors[:10]:  # Max 10
                print(color(f"  ✗ {err}", Colors.RED))
            if len(self.result.errors) > 10:
                print(f"  ... et {len(self.result.errors) - 10} autres")

        # Détails des warnings
        if self.result.warnings:
            print(color("\nAvertissements:", Colors.YELLOW + Colors.BOLD))
            for warn in self.result.warnings[:10]:
                print(color(f"  ⚠ {warn}", Colors.YELLOW))
            if len(self.result.warnings) > 10:
                print(f"  ... et {len(self.result.warnings) - 10} autres")

        # Stats
        print(f"\nStatistiques:")
        print(f"  Définitions: {self.result.stats.get('definitions', 0)}")
        print(f"  Fichiers Python scannés: {self.result.stats.get('python_files_scanned', 0)}")
        print(f"  Modules YAML scannés: {self.result.stats.get('yaml_modules_scanned', 0)}")
        print(f"  Usages trouvés: {len(self.usages)}")

# =============================================================================
# Point d'entrée
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Validateur de constantes AZALPLUS")
    parser.add_argument("--fix", action="store_true", help="Corriger les problèmes automatiquement")
    parser.add_argument("--generate-stub", action="store_true", help="Générer le fichier .pyi pour IDE")
    parser.add_argument("--json", action="store_true", help="Sortie au format JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Mode silencieux")

    args = parser.parse_args()

    validator = ConstantsValidator()
    result = validator.run(fix=args.fix, generate_stub=args.generate_stub)

    if args.json:
        output = {
            "status": "ok" if result.is_valid else "error",
            "errors": [str(e) for e in result.errors],
            "warnings": [str(w) for w in result.warnings],
            "info": [str(i) for i in result.info],
            "stats": result.stats
        }
        print(json.dumps(output, indent=2))

    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
