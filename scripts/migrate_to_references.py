#!/usr/bin/env python3
"""
AZALPLUS - Migration vers références constants.yml

Ce script analyse les fichiers YAML dans modules/ et identifie les champs
avec des options hardcodées qui pourraient être remplacées par des références
vers config/constants.yml.

Usage:
    python scripts/migrate_to_references.py           # Affiche le rapport
    python scripts/migrate_to_references.py --fix     # Applique les modifications
    python scripts/migrate_to_references.py --verbose # Affiche plus de détails

Auteur: AZALPLUS
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Utiliser ruamel.yaml pour préserver les commentaires si disponible
try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq
    RUAMEL_AVAILABLE = True
except ImportError:
    RUAMEL_AVAILABLE = False
    import yaml


class MigrationReport:
    """Rapport de migration pour un fichier."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.migrations: list[dict[str, Any]] = []
        self.no_match: list[dict[str, Any]] = []
        self.already_referenced: list[dict[str, Any]] = []

    def add_migration(self, field_name: str, current_options: list,
                      reference_path: str, reference_options: list,
                      match_type: str = "exact"):
        """Ajoute une migration possible."""
        self.migrations.append({
            "field": field_name,
            "current": current_options,
            "reference": reference_path,
            "reference_options": reference_options,
            "match_type": match_type
        })

    def add_no_match(self, field_name: str, options: list):
        """Ajoute un champ sans correspondance trouvée."""
        self.no_match.append({
            "field": field_name,
            "options": options
        })

    def add_already_referenced(self, field_name: str, reference: str):
        """Ajoute un champ déjà référencé."""
        self.already_referenced.append({
            "field": field_name,
            "reference": reference
        })


class ConstantsIndex:
    """Index des constantes pour recherche rapide."""

    def __init__(self, constants_data: dict):
        self.constants = constants_data
        self.flat_index: dict[frozenset, list[str]] = {}
        self._build_index(constants_data, "")

    def _build_index(self, data: Any, path: str):
        """Construit l'index récursivement."""
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                self._build_index(value, new_path)

                # Si c'est un dict avec 'valeurs', indexer ce tableau
                if key == "valeurs" and isinstance(value, list):
                    self._index_list(value, path)
        elif isinstance(data, list):
            self._index_list(data, path)

    def _index_list(self, lst: list, path: str):
        """Indexe une liste de valeurs."""
        # Extraire les codes des objets ou garder les strings directes
        values = []
        for item in lst:
            if isinstance(item, dict):
                if "code" in item:
                    values.append(item["code"])
                elif "nom" in item:
                    values.append(item["nom"])
            elif isinstance(item, str):
                values.append(item)

        if values:
            key = frozenset(values)
            if key not in self.flat_index:
                self.flat_index[key] = []
            self.flat_index[key].append(path)

    def find_match(self, options: list) -> list[tuple[str, list, str]]:
        """
        Trouve les correspondances pour une liste d'options.

        Returns:
            Liste de tuples (path, reference_options, match_type)
            match_type: "exact", "subset", "superset"
        """
        if not options:
            return []

        options_set = frozenset(options)
        matches = []

        # Chercher correspondance exacte
        if options_set in self.flat_index:
            for path in self.flat_index[options_set]:
                ref_options = self._get_options_at_path(path)
                matches.append((path, ref_options, "exact"))

        # Chercher correspondance par sous-ensemble ou sur-ensemble
        for indexed_set, paths in self.flat_index.items():
            if indexed_set == options_set:
                continue

            # Options hardcodées sont un sous-ensemble des constantes
            if options_set.issubset(indexed_set):
                for path in paths:
                    ref_options = self._get_options_at_path(path)
                    if len(indexed_set) - len(options_set) <= 3:  # Tolérance
                        matches.append((path, ref_options, "subset"))

            # Options hardcodées contiennent les constantes
            elif options_set.issuperset(indexed_set):
                for path in paths:
                    ref_options = self._get_options_at_path(path)
                    if len(options_set) - len(indexed_set) <= 2:  # Tolérance
                        matches.append((path, ref_options, "superset"))

        return matches

    def _get_options_at_path(self, path: str) -> list:
        """Récupère la liste d'options à un chemin donné."""
        parts = path.split(".")
        data = self.constants

        for part in parts:
            if isinstance(data, dict) and part in data:
                data = data[part]
            else:
                return []

        if isinstance(data, list):
            return [
                item.get("code", item) if isinstance(item, dict) else item
                for item in data
            ]
        return []


def load_yaml_file(file_path: Path, use_ruamel: bool = False) -> tuple[Any, str]:
    """
    Charge un fichier YAML.

    Args:
        file_path: Chemin du fichier
        use_ruamel: Utiliser ruamel.yaml (pour préserver commentaires lors de l'écriture)

    Returns:
        Tuple (data, raw_content)
    """
    raw_content = file_path.read_text(encoding="utf-8")

    if use_ruamel and RUAMEL_AVAILABLE:
        yaml_parser = YAML()
        yaml_parser.preserve_quotes = True
        yaml_parser.allow_duplicate_keys = True
        data = yaml_parser.load(raw_content)
    else:
        # Utiliser PyYAML standard (plus tolérant)
        import yaml as pyyaml
        data = pyyaml.safe_load(raw_content)

    return data, raw_content


def find_hardcoded_options(data: dict, module_name: str) -> list[dict]:
    """
    Trouve tous les champs avec des options hardcodées.

    Returns:
        Liste de dicts avec field_name, options, et location info
    """
    fields_with_options = []

    # Parcourir les champs principaux
    if "champs" in data:
        for i, field in enumerate(data["champs"]):
            if isinstance(field, dict) and "options" in field:
                options_value = field["options"]
                field_name = field.get("nom", f"champ_{i}")

                # Vérifier si c'est une référence ou hardcodé
                if isinstance(options_value, str) and options_value.startswith("$"):
                    fields_with_options.append({
                        "field": field_name,
                        "options": options_value,
                        "is_reference": True,
                        "section": "champs",
                        "index": i
                    })
                elif isinstance(options_value, list):
                    fields_with_options.append({
                        "field": field_name,
                        "options": options_value,
                        "is_reference": False,
                        "section": "champs",
                        "index": i
                    })

    # Parcourir les lignes si présentes
    if "lignes" in data and isinstance(data["lignes"], dict):
        if "champs" in data["lignes"]:
            for i, field in enumerate(data["lignes"]["champs"]):
                if isinstance(field, dict) and "options" in field:
                    options_value = field["options"]
                    field_name = field.get("nom", f"ligne_champ_{i}")

                    if isinstance(options_value, str) and options_value.startswith("$"):
                        fields_with_options.append({
                            "field": f"lignes.{field_name}",
                            "options": options_value,
                            "is_reference": True,
                            "section": "lignes.champs",
                            "index": i
                        })
                    elif isinstance(options_value, list):
                        fields_with_options.append({
                            "field": f"lignes.{field_name}",
                            "options": options_value,
                            "is_reference": False,
                            "section": "lignes.champs",
                            "index": i
                        })

    # Parcourir les paiements si présents
    if "paiements" in data and isinstance(data["paiements"], dict):
        if "champs" in data["paiements"]:
            for i, field in enumerate(data["paiements"]["champs"]):
                if isinstance(field, dict) and "options" in field:
                    options_value = field["options"]
                    field_name = field.get("nom", f"paiement_champ_{i}")

                    if isinstance(options_value, str) and options_value.startswith("$"):
                        fields_with_options.append({
                            "field": f"paiements.{field_name}",
                            "options": options_value,
                            "is_reference": True,
                            "section": "paiements.champs",
                            "index": i
                        })
                    elif isinstance(options_value, list):
                        fields_with_options.append({
                            "field": f"paiements.{field_name}",
                            "options": options_value,
                            "is_reference": False,
                            "section": "paiements.champs",
                            "index": i
                        })

    return fields_with_options


def normalize_options(options: list) -> list[str]:
    """Normalise une liste d'options pour la comparaison."""
    normalized = []
    for opt in options:
        if isinstance(opt, str):
            # Normaliser: MAJUSCULES, underscores
            normalized.append(opt.upper().replace("-", "_").replace(" ", "_"))
        elif isinstance(opt, dict):
            if "code" in opt:
                normalized.append(opt["code"].upper().replace("-", "_"))
    return normalized


def generate_reference_path(constant_path: str) -> str:
    """Génère le chemin de référence YAML depuis un chemin de constante."""
    # Ajouter .valeurs si nécessaire
    if not constant_path.endswith(".valeurs"):
        # Vérifier si le chemin pointe vers une liste sous 'valeurs'
        parts = constant_path.split(".")
        if len(parts) >= 2:
            return f"${constant_path}.valeurs"
    return f"${constant_path}"


def apply_migration(file_path: Path, report: MigrationReport, verbose: bool = False):
    """
    Applique les migrations à un fichier YAML.
    Utilise la manipulation de texte pour préserver les commentaires.
    """
    content = file_path.read_text(encoding="utf-8")
    modified = False

    for migration in report.migrations:
        if migration["match_type"] != "exact":
            if verbose:
                print(f"    - Ignoré (match {migration['match_type']}): {migration['field']}")
            continue

        field_name = migration["field"]
        current_options = migration["current"]
        reference = migration["reference"]

        # Construire le pattern pour trouver la ligne options
        # On cherche le bloc du champ puis sa ligne options

        # Convertir la liste en représentation YAML
        if isinstance(current_options, list):
            # Format: [VAL1, VAL2, ...] ou format multi-ligne
            options_str_inline = str(current_options).replace("'", "")

            # Pattern pour format inline: options: [VAL1, VAL2]
            pattern_inline = re.compile(
                rf'(\s+-\s+nom:\s+{re.escape(field_name.split(".")[-1])}\s*\n'
                rf'(?:.*\n)*?'
                rf'\s+)options:\s*\[([^\]]+)\]',
                re.MULTILINE
            )

            # Pattern pour format multi-ligne avec tirets
            pattern_multiline = re.compile(
                rf'(\s+-\s+nom:\s+{re.escape(field_name.split(".")[-1])}\s*\n'
                rf'(?:.*\n)*?'
                rf'\s+)options:\s*\n'
                rf'(\s+-\s+\S+\s*\n)+',
                re.MULTILINE
            )

            # Essayer le format inline d'abord
            match = pattern_inline.search(content)
            if match:
                # Remplacer la ligne options
                old_text = match.group(0)
                new_text = f"{match.group(1)}options: ${reference}"
                content = content.replace(old_text, new_text)
                modified = True
                if verbose:
                    print(f"    + Migré: {field_name} -> ${reference}")

    if modified:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def apply_migration_ruamel(file_path: Path, report: MigrationReport, verbose: bool = False):
    """
    Applique les migrations en utilisant ruamel.yaml pour préserver les commentaires.
    """
    yaml_parser = YAML()
    yaml_parser.preserve_quotes = True
    yaml_parser.indent(mapping=2, sequence=4, offset=2)

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml_parser.load(f)

    modified = False

    for migration in report.migrations:
        if migration["match_type"] != "exact":
            if verbose:
                print(f"    - Ignoré (match {migration['match_type']}): {migration['field']}")
            continue

        field_name = migration["field"]
        reference = f"${migration['reference']}"

        # Trouver et modifier le champ
        parts = field_name.split(".")

        if len(parts) == 1:
            # Champ dans la section principale
            if "champs" in data:
                for field in data["champs"]:
                    if isinstance(field, dict) and field.get("nom") == parts[0]:
                        field["options"] = reference
                        modified = True
                        if verbose:
                            print(f"    + Migré: {field_name} -> {reference}")
                        break
        elif len(parts) == 2:
            # Champ dans une sous-section (lignes, paiements)
            section = parts[0]
            field_nom = parts[1]
            if section in data and isinstance(data[section], dict):
                if "champs" in data[section]:
                    for field in data[section]["champs"]:
                        if isinstance(field, dict) and field.get("nom") == field_nom:
                            field["options"] = reference
                            modified = True
                            if verbose:
                                print(f"    + Migré: {field_name} -> {reference}")
                            break

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            yaml_parser.dump(data, f)
        return True
    return False


def print_report(reports: list[MigrationReport], verbose: bool = False):
    """Affiche le rapport de migration."""
    total_migrations = 0
    total_no_match = 0
    total_already_ref = 0

    print("\n" + "=" * 80)
    print("RAPPORT DE MIGRATION VERS RÉFÉRENCES constants.yml")
    print("=" * 80 + "\n")

    for report in reports:
        if not report.migrations and not report.no_match and not verbose:
            continue

        module_name = report.file_path.stem
        print(f"\n{'─' * 60}")
        print(f"Module: {module_name}")
        print(f"{'─' * 60}")

        if report.migrations:
            print(f"\n  Migrations possibles ({len(report.migrations)}):")
            for m in report.migrations:
                match_indicator = "✓" if m["match_type"] == "exact" else f"~{m['match_type']}"
                print(f"    [{match_indicator}] {m['field']}")
                print(f"        Options actuelles: {m['current']}")
                print(f"        Référence: ${m['reference']}")
                if verbose:
                    print(f"        Options référence: {m['reference_options']}")
            total_migrations += len(report.migrations)

        if report.no_match and verbose:
            print(f"\n  Sans correspondance ({len(report.no_match)}):")
            for n in report.no_match:
                print(f"    - {n['field']}: {n['options']}")
            total_no_match += len(report.no_match)

        if report.already_referenced:
            total_already_ref += len(report.already_referenced)
            if verbose:
                print(f"\n  Déjà référencés ({len(report.already_referenced)}):")
                for a in report.already_referenced:
                    print(f"    - {a['field']}: {a['reference']}")

    # Résumé
    print("\n" + "=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"  Migrations possibles (exact): {sum(1 for r in reports for m in r.migrations if m['match_type'] == 'exact')}")
    print(f"  Migrations possibles (partiel): {sum(1 for r in reports for m in r.migrations if m['match_type'] != 'exact')}")
    print(f"  Champs sans correspondance: {sum(len(r.no_match) for r in reports)}")
    print(f"  Champs déjà référencés: {total_already_ref}")
    print("\n")

    if total_migrations > 0:
        print("Utilisez --fix pour appliquer les migrations exactes automatiquement.")
        print("Les migrations partielles (subset/superset) nécessitent une vérification manuelle.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Migration des options hardcodées vers références constants.yml"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Appliquer les modifications (uniquement les correspondances exactes)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Afficher plus de détails"
    )
    parser.add_argument(
        "--module",
        type=str,
        help="Analyser uniquement un module spécifique"
    )

    args = parser.parse_args()

    # Chemins
    base_path = Path(__file__).parent.parent
    modules_path = base_path / "modules"
    constants_path = base_path / "config" / "constants.yml"

    # Vérifications
    if not modules_path.exists():
        print(f"Erreur: Dossier modules non trouvé: {modules_path}")
        sys.exit(1)

    if not constants_path.exists():
        print(f"Erreur: Fichier constants.yml non trouvé: {constants_path}")
        sys.exit(1)

    # Charger les constantes (utiliser PyYAML pour éviter les erreurs de clés dupliquées)
    print("Chargement des constantes...")
    constants_data, _ = load_yaml_file(constants_path, use_ruamel=False)
    constants_index = ConstantsIndex(constants_data)

    if args.verbose:
        print(f"  Index construit: {len(constants_index.flat_index)} ensembles de valeurs")

    # Trouver les fichiers modules
    if args.module:
        module_files = list(modules_path.glob(f"{args.module}.yml"))
        if not module_files:
            print(f"Erreur: Module '{args.module}' non trouvé")
            sys.exit(1)
    else:
        module_files = sorted(modules_path.glob("*.yml"))

    print(f"Analyse de {len(module_files)} modules...")

    # Analyser chaque module
    reports = []

    for module_file in module_files:
        try:
            data, raw_content = load_yaml_file(module_file)
        except Exception as e:
            print(f"  Erreur lecture {module_file.name}: {e}")
            continue

        if data is None:
            continue

        module_name = data.get("nom", module_file.stem)
        report = MigrationReport(module_file)

        # Trouver les champs avec options
        fields = find_hardcoded_options(data, module_name)

        for field_info in fields:
            if field_info["is_reference"]:
                report.add_already_referenced(
                    field_info["field"],
                    field_info["options"]
                )
            else:
                # Chercher correspondance
                options = field_info["options"]
                normalized = normalize_options(options)
                matches = constants_index.find_match(normalized)

                if matches:
                    # Prendre la meilleure correspondance
                    # Priorité: exact > subset > superset
                    best_match = None
                    for path, ref_opts, match_type in matches:
                        if match_type == "exact":
                            best_match = (path, ref_opts, match_type)
                            break
                        elif best_match is None or (best_match[2] != "exact" and match_type == "subset"):
                            best_match = (path, ref_opts, match_type)

                    if best_match:
                        report.add_migration(
                            field_info["field"],
                            options,
                            best_match[0],
                            best_match[1],
                            best_match[2]
                        )
                    else:
                        report.add_no_match(field_info["field"], options)
                else:
                    report.add_no_match(field_info["field"], options)

        reports.append(report)

    # Afficher le rapport
    print_report(reports, args.verbose)

    # Appliquer les modifications si demandé
    if args.fix:
        print("\nApplication des migrations...")
        files_modified = 0

        for report in reports:
            exact_migrations = [m for m in report.migrations if m["match_type"] == "exact"]
            if not exact_migrations:
                continue

            print(f"\n  {report.file_path.name}:")

            try:
                if RUAMEL_AVAILABLE:
                    modified = apply_migration_ruamel(report.file_path, report, args.verbose)
                else:
                    modified = apply_migration(report.file_path, report, args.verbose)

                if modified:
                    files_modified += 1
                    print(f"    ✓ {len(exact_migrations)} migration(s) appliquée(s)")
                else:
                    print(f"    - Aucune modification (vérifier manuellement)")
            except Exception as e:
                print(f"    ✗ Erreur: {e}")

        print(f"\n{files_modified} fichier(s) modifié(s)")

        if not RUAMEL_AVAILABLE:
            print("\nNote: Installez ruamel.yaml pour une meilleure préservation des commentaires:")
            print("  pip install ruamel.yaml")


if __name__ == "__main__":
    main()
