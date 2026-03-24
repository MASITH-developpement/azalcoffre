#!/usr/bin/env python3
"""
Applique l'attribut 'groupe' à tous les champs des modules YAML.
Usage: python3 scripts/apply_groupe.py [--dry-run] [module1.yml module2.yml ...]
"""

import sys
import re
from pathlib import Path

# Règles de classification des champs en groupes
GROUPE_RULES = {
    "Identification": [
        r"^(code|nom|name|ref|reference|numero|num|titre|title|libelle|label|slug)$",
        r"^(code_|nom_|ref_|num_)",
        r"_(code|nom|ref|numero)$",
    ],
    "Informations": [
        r"^(description|desc|type|categorie|category|nature|famille|genre|classe|kind)$",
        r"^(type_|categorie_)",
        r"_(type|categorie|nature)$",
    ],
    "Contact": [
        r"^(email|mail|telephone|tel|phone|mobile|fax|adresse|address|ville|city|code_postal|cp|pays|country|region)$",
        r"^(email_|tel_|adresse_|address_)",
        r"_(email|tel|phone|adresse|address)$",
    ],
    "Relations": [
        r"_id$",
        r"^(client|fournisseur|projet|employe|user|contact|societe|entreprise|tenant)_",
        r"^(parent|enfant|lie_a|associe_a)",
    ],
    "Montants": [
        r"^(prix|price|montant|amount|total|tva|ht|ttc|cout|cost|tarif|rate|remise|discount|marge|commission|solde|balance)$",
        r"^(prix_|montant_|total_|tva_|cout_|tarif_)",
        r"_(prix|montant|total|ht|ttc|tva|cout|tarif)$",
        r"^(taux_|pourcentage_|percent)",
    ],
    "Quantites": [
        r"^(quantite|quantity|qty|qte|nombre|nb|count|stock|unite|unit)$",
        r"^(quantite_|nb_|stock_)",
        r"_(quantite|qty|qte|nombre|stock)$",
    ],
    "Dates": [
        r"^(date|datetime|timestamp|created|updated|deleted|archived)$",
        r"^(date_|heure_|time_)",
        r"_(date|at|le|depuis|jusqua)$",
        r"^(debut|fin|start|end|echeance|deadline|expiration|validite)$",
    ],
    "Statut": [
        r"^(statut|status|etat|state|actif|active|archive|deleted|valide|validated|approuve|approved|publie|published)$",
        r"^(is_|est_|has_|a_)",
        r"^(statut_|etat_)",
    ],
    "Fichiers": [
        r"^(fichier|file|document|doc|piece|attachment|photo|image|logo|avatar|pdf)$",
        r"^(fichier_|file_|doc_|photo_|image_)",
        r"_(fichier|file|doc|path|url|uri)$",
        r"^(mime|extension|taille|size)$",
    ],
    "Configuration": [
        r"^(config|configuration|settings|parametres|options|preferences|reglages)$",
        r"^(config_|param_|option_)",
        r"_(config|settings|params|options)$",
        r"^(activer_|enable_|disable_|mode_)",
    ],
    "Securite": [
        r"^(password|mot_de_passe|token|secret|api_key|cle|hash|signature|certificat)$",
        r"^(password_|token_|secret_|key_)",
        r"_(password|token|secret|key|hash)$",
    ],
    "Metadata": [
        r"^(metadata|meta|tags|labels|keywords|custom_fields|extra|data|json)$",
        r"^(meta_|custom_|extra_)",
        r"_(meta|data|json|extra)$",
    ],
    "Notes": [
        r"^(notes|note|commentaire|comment|remarque|observation|memo|details|info|instructions)$",
        r"^(notes_|comment_)",
        r"_(notes|commentaire|remarque|memo)$",
    ],
}

# Règles par type de champ (fallback)
TYPE_TO_GROUPE = {
    "money": "Montants",
    "montant": "Montants",
    "currency": "Montants",
    "date": "Dates",
    "datetime": "Dates",
    "timestamp": "Dates",
    "email": "Contact",
    "tel": "Contact",
    "telephone": "Contact",
    "phone": "Contact",
    "file": "Fichiers",
    "image": "Fichiers",
    "document": "Fichiers",
    "password": "Securite",
    "json": "Metadata",
    "tags": "Metadata",
    "textarea": "Notes",
    "text_long": "Notes",
}


def determine_groupe(field_name: str, field_type: str = None) -> str:
    """Détermine le groupe approprié pour un champ."""
    field_name_lower = field_name.lower()

    # 1. Vérifier les patterns de nom
    for groupe, patterns in GROUPE_RULES.items():
        for pattern in patterns:
            if re.search(pattern, field_name_lower):
                return groupe

    # 2. Vérifier le type de champ
    if field_type:
        field_type_lower = field_type.lower()
        if field_type_lower in TYPE_TO_GROUPE:
            return TYPE_TO_GROUPE[field_type_lower]

    # 3. Fallback
    return "Informations"


def process_module(file_path: Path, dry_run: bool = False) -> dict:
    """Traite un module YAML et ajoute les attributs groupe."""
    content = file_path.read_text(encoding='utf-8')
    original_content = content

    stats = {"fields": 0, "added": 0, "skipped": 0}

    # Pattern pour trouver les champs avec leur nom et type
    # Capture le bloc complet d'un champ
    field_pattern = re.compile(
        r'^(\s*-\s*nom:\s*)(\S+)\s*\n((?:\s+\S+:.*\n)*)',
        re.MULTILINE
    )

    def process_field(match):
        indent = match.group(1)
        field_name = match.group(2)
        rest = match.group(3)

        stats["fields"] += 1

        # Vérifier si groupe existe déjà
        if re.search(r'^\s+groupe:', rest, re.MULTILINE):
            stats["skipped"] += 1
            return match.group(0)

        # Extraire le type si présent
        type_match = re.search(r'^\s+type:\s*(\S+)', rest, re.MULTILINE)
        field_type = type_match.group(1) if type_match else None

        # Déterminer le groupe
        groupe = determine_groupe(field_name, field_type)

        # Trouver où insérer le groupe (après type si présent, sinon après nom)
        if type_match:
            # Insérer après la ligne type
            type_line_end = rest.find('\n', type_match.start()) + 1
            new_rest = rest[:type_line_end] + f"    groupe: {groupe}\n" + rest[type_line_end:]
        else:
            # Insérer au début du bloc
            new_rest = f"    groupe: {groupe}\n" + rest

        stats["added"] += 1
        return indent + field_name + "\n" + new_rest

    new_content = field_pattern.sub(process_field, content)

    if not dry_run and new_content != original_content:
        file_path.write_text(new_content, encoding='utf-8')

    return stats


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")

    modules_dir = Path(__file__).parent.parent / "modules"

    if args:
        # Modules spécifiques
        files = [modules_dir / f for f in args if (modules_dir / f).exists()]
    else:
        # Tous les modules
        files = sorted(modules_dir.glob("*.yml"))

    total_stats = {"files": 0, "fields": 0, "added": 0, "skipped": 0}

    print(f"{'[DRY-RUN] ' if dry_run else ''}Traitement de {len(files)} modules...\n")

    for file_path in files:
        stats = process_module(file_path, dry_run)
        if stats["added"] > 0 or stats["skipped"] > 0:
            print(f"  {file_path.name}: +{stats['added']} groupes ({stats['skipped']} existants)")
            total_stats["files"] += 1
        total_stats["fields"] += stats["fields"]
        total_stats["added"] += stats["added"]
        total_stats["skipped"] += stats["skipped"]

    print(f"\n{'='*60}")
    print(f"RÉSUMÉ")
    print(f"{'='*60}")
    print(f"  Fichiers modifiés: {total_stats['files']}")
    print(f"  Champs traités: {total_stats['fields']}")
    print(f"  Groupes ajoutés: {total_stats['added']}")
    print(f"  Groupes existants: {total_stats['skipped']}")


if __name__ == "__main__":
    main()
