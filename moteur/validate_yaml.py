#!/usr/bin/env python3
# =============================================================================
# AZALPLUS - Validateur YAML CLI
# =============================================================================
"""
Script de validation des fichiers YAML de modules.
Usage: python -m moteur.validate_yaml [--fix] [--verbose]
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple

# Couleurs ANSI pour le terminal
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def fix_yaml_line(line: str) -> str:
    """
    Tente de corriger automatiquement une ligne YAML problématique.
    """
    # Ignorer les commentaires et lignes vides
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return line

    # Ignorer les lignes qui sont juste une clé (finissent par :)
    if stripped.endswith(':'):
        return line

    # Ignorer les valeurs déjà quotées ou structurées
    if ':' in line:
        parts = line.split(':', 1)
        if len(parts) > 1:
            key_part = parts[0]
            value_part = parts[1].strip()

            # Si la valeur est vide, quotée, ou structurée, ne pas modifier
            if not value_part:
                return line
            if value_part.startswith('"') or value_part.startswith("'"):
                return line
            if value_part.startswith('[') or value_part.startswith('{'):
                return line
            if value_part in ('true', 'false', 'null', 'True', 'False'):
                return line
            # Si c'est un nombre
            try:
                float(value_part)
                return line
            except ValueError:
                pass

            # Si la valeur contient des caractères spéciaux, la quoter
            special_chars = [':', '#', '{', '}', '[', ']', ',', '&', '*', '!', '|', '>', "'", '"', '%', '@', '`']
            needs_quoting = any(char in value_part for char in special_chars)

            # Aussi quoter si ça commence par des caractères spéciaux
            if value_part and value_part[0] in ['@', '`', '|', '>', '-', '?']:
                needs_quoting = True

            if needs_quoting:
                # Échapper les guillemets existants
                escaped_value = value_part.replace('"', '\\"')
                indent = len(line) - len(line.lstrip())
                return ' ' * indent + key_part.strip() + ': "' + escaped_value + '"'

    return line


def validate_yaml_file(path: Path, verbose: bool = False) -> Tuple[bool, List[str], List[Tuple[int, str, str]]]:
    """
    Valide un fichier YAML et retourne les erreurs et corrections suggérées.

    Returns:
        (is_valid, errors, fixes) où fixes est une liste de (line_num, original, fixed)
    """
    errors = []
    fixes = []

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        return False, [f"Erreur lecture: {e}"], []

    lines = content.split('\n')

    in_multiline_block = False
    multiline_indent = 0

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Ignorer commentaires et lignes vides
        if not stripped or stripped.startswith('#'):
            continue

        # Calculer l'indentation
        current_indent = len(line) - len(line.lstrip())

        # Détection de bloc multiligne (| ou >)
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) > 1:
                value_part = parts[1].strip()
                if value_part in ('|', '>', '|-', '>-', '|+', '>+'):
                    in_multiline_block = True
                    multiline_indent = current_indent
                    continue

        # Si on est dans un bloc multiligne
        if in_multiline_block:
            if current_indent > multiline_indent:
                continue  # Ignorer le contenu du bloc multiligne
            else:
                in_multiline_block = False

        # Vérifier les deux-points non quotés dans les valeurs
        if ':' in line and not in_multiline_block:
            parts = line.split(':', 1)
            if len(parts) > 1:
                value_part = parts[1].strip()
                # Vérifier si la valeur contient : et n'est pas quotée
                if value_part and ':' in value_part:
                    if not (value_part.startswith('"') or
                            value_part.startswith("'") or
                            value_part.startswith('[') or
                            value_part.startswith('{') or
                            value_part in ('|', '>', '|-', '>-', '|+', '>+')):
                        # Exceptions
                        if not re.match(r'^\d{2}:\d{2}', value_part):  # pas une heure
                            if not value_part.startswith('http'):  # pas une URL
                                errors.append(f"Ligne {line_num}: Deux-points dans la valeur: {stripped}")
                                fixed = fix_yaml_line(line)
                                if fixed != line:
                                    fixes.append((line_num, line, fixed))

        # Vérifier les caractères spéciaux non quotés
        if ':' in line and not in_multiline_block:
            parts = line.split(':', 1)
            if len(parts) > 1:
                value_part = parts[1].strip()
                if value_part and not (value_part.startswith('"') or value_part.startswith("'")):
                    # Parenthèses avec potentiel problème
                    if '(' in value_part and ')' in value_part and ':' in value_part:
                        errors.append(f"Ligne {line_num}: Parenthèses avec deux-points: {stripped}")
                        fixed = fix_yaml_line(line)
                        if fixed != line:
                            fixes.append((line_num, line, fixed))

    # Essayer de parser avec PyYAML pour validation complète
    try:
        import yaml
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        error_str = str(e)
        # Extraire le numéro de ligne
        line_match = re.search(r'line (\d+)', error_str)
        if line_match:
            error_line = int(line_match.group(1))
            errors.append(f"Ligne {error_line}: Erreur de syntaxe YAML")
            if error_line <= len(lines):
                original = lines[error_line - 1]
                fixed = fix_yaml_line(original)
                if fixed != original:
                    fixes.append((error_line, original, fixed))
        else:
            errors.append(f"Erreur YAML: {e}")

    return len(errors) == 0, errors, fixes


def fix_yaml_file(path: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """
    Corrige automatiquement un fichier YAML.

    Args:
        path: Chemin du fichier
        dry_run: Si True, affiche les corrections sans les appliquer

    Returns:
        (success, message)
    """
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        return False, f"Erreur lecture: {e}"

    lines = content.split('\n')
    modified = False
    new_lines = []

    for line in lines:
        fixed = fix_yaml_line(line)
        new_lines.append(fixed)
        if fixed != line:
            modified = True

    if not modified:
        return True, "Aucune correction nécessaire"

    new_content = '\n'.join(new_lines)

    if dry_run:
        return True, f"Corrections suggérées (dry-run)"

    try:
        path.write_text(new_content, encoding='utf-8')
        return True, "Fichier corrigé avec succès"
    except Exception as e:
        return False, f"Erreur écriture: {e}"


def main():
    """Point d'entrée CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validateur YAML pour les modules AZALPLUS"
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help="Corrige automatiquement les erreurs"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Avec --fix, affiche les corrections sans les appliquer"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Affiche plus de détails"
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='/home/ubuntu/azalplus/modules',
        help="Chemin du répertoire ou fichier à valider"
    )

    args = parser.parse_args()
    target = Path(args.path)

    if not target.exists():
        print(f"{Colors.RED}Erreur: {target} n'existe pas{Colors.RESET}")
        sys.exit(1)

    # Collecter les fichiers à valider
    if target.is_file():
        yaml_files = [target]
    else:
        yaml_files = sorted(target.glob("**/*.yml"))

    if not yaml_files:
        print(f"{Colors.YELLOW}Aucun fichier YAML trouvé dans {target}{Colors.RESET}")
        sys.exit(0)

    print(f"\n{Colors.BOLD}=== Validation YAML AZALPLUS ==={Colors.RESET}")
    print(f"Fichiers à valider: {len(yaml_files)}\n")

    valid_count = 0
    error_count = 0
    fixed_count = 0

    for yaml_file in yaml_files:
        relative_path = yaml_file.relative_to(target.parent) if target.is_dir() else yaml_file.name

        is_valid, errors, fixes = validate_yaml_file(yaml_file, args.verbose)

        if is_valid:
            valid_count += 1
            if args.verbose:
                print(f"  {Colors.GREEN}✓{Colors.RESET} {relative_path}")
        else:
            error_count += 1
            print(f"\n  {Colors.RED}✗{Colors.RESET} {Colors.BOLD}{relative_path}{Colors.RESET}")
            for error in errors:
                print(f"    {Colors.RED}→ {error}{Colors.RESET}")

            if fixes:
                print(f"    {Colors.BLUE}Corrections suggérées:{Colors.RESET}")
                for line_num, original, fixed in fixes:
                    print(f"      Ligne {line_num}:")
                    print(f"        {Colors.RED}- {original.strip()}{Colors.RESET}")
                    print(f"        {Colors.GREEN}+ {fixed.strip()}{Colors.RESET}")

                if args.fix:
                    success, msg = fix_yaml_file(yaml_file, dry_run=args.dry_run)
                    if success and not args.dry_run:
                        fixed_count += 1
                        print(f"    {Colors.GREEN}✓ {msg}{Colors.RESET}")

    # Résumé
    print(f"\n{Colors.BOLD}=== Résumé ==={Colors.RESET}")
    print(f"  {Colors.GREEN}Valides: {valid_count}{Colors.RESET}")
    if error_count > 0:
        print(f"  {Colors.RED}Erreurs: {error_count}{Colors.RESET}")
    if fixed_count > 0:
        print(f"  {Colors.BLUE}Corrigés: {fixed_count}{Colors.RESET}")

    if error_count > 0 and not args.fix:
        print(f"\n{Colors.YELLOW}Conseil: Utilisez --fix pour corriger automatiquement{Colors.RESET}")

    sys.exit(0 if error_count == 0 else 1)


if __name__ == "__main__":
    main()
