# =============================================================================
# AZALPLUS - Import/Export CSV
# =============================================================================
"""
Fonctions d'import et export CSV pour tous les modules.
- Export avec mapping automatique depuis YAML
- Import avec validation et création d'enregistrements
- Encodage UTF-8 avec BOM pour compatibilite Excel
"""

import csv
import io
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, date
import structlog

from .parser import ModuleParser, ModuleDefinition, FieldDefinition
from .db import Database

logger = structlog.get_logger()

# BOM UTF-8 pour Excel
UTF8_BOM = '\ufeff'

# Colonnes systeme a exclure de l'export/import standard
SYSTEM_COLUMNS = {'id', 'tenant_id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at'}


def get_module_fields(module_name: str) -> Dict[str, FieldDefinition]:
    """
    Recupere les champs exportables d'un module depuis sa definition YAML.
    Exclut les champs systeme et les champs auto/calcul.
    """
    module = ModuleParser.get(module_name)
    if not module:
        raise ValueError(f"Module '{module_name}' non trouve")

    exportable_fields = {}
    for nom, field_def in module.champs.items():
        # Exclure les champs auto, calcul et systeme
        if field_def.type not in ['auto', 'calcul'] and nom not in SYSTEM_COLUMNS:
            exportable_fields[nom] = field_def

    return exportable_fields


def get_field_label(field_def: FieldDefinition) -> str:
    """Retourne le label d'un champ pour l'en-tete CSV."""
    return field_def.label or field_def.nom.replace('_', ' ').title()


def format_value_for_csv(value: Any, field_type: str) -> str:
    """
    Formate une valeur pour l'export CSV.
    Gere les types speciaux (dates, booleens, etc.)
    """
    if value is None:
        return ''

    if field_type in ['oui/non', 'booleen']:
        return 'Oui' if value else 'Non'

    if field_type == 'date':
        if isinstance(value, (datetime, date)):
            return value.strftime('%d/%m/%Y')
        return str(value)

    if field_type == 'datetime':
        if isinstance(value, datetime):
            return value.strftime('%d/%m/%Y %H:%M')
        return str(value)

    if field_type in ['monnaie', 'pourcentage', 'nombre']:
        try:
            return str(float(value)).replace('.', ',')
        except (ValueError, TypeError):
            return str(value)

    if field_type == 'json':
        import json
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def parse_value_from_csv(value: str, field_def: FieldDefinition) -> Any:
    """
    Parse une valeur CSV vers le type Python attendu.
    Retourne None si la valeur est vide.
    """
    if not value or value.strip() == '':
        return field_def.defaut

    value = value.strip()
    field_type = field_def.type

    if field_type in ['oui/non', 'booleen']:
        return value.lower() in ['oui', 'yes', 'true', '1', 'vrai']

    if field_type == 'date':
        # Essayer plusieurs formats
        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return value

    if field_type == 'datetime':
        for fmt in ['%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                return datetime.strptime(value, fmt).isoformat()
            except ValueError:
                continue
        return value

    if field_type == 'entier':
        try:
            return int(value.replace(' ', ''))
        except ValueError:
            return None

    if field_type in ['monnaie', 'pourcentage', 'nombre']:
        try:
            # Gerer le format francais avec virgule
            cleaned = value.replace(' ', '').replace(',', '.')
            return float(cleaned)
        except ValueError:
            return None

    if field_type == 'json':
        import json
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None

    return value


# =============================================================================
# Export CSV
# =============================================================================
def export_to_csv(
    module_name: str,
    records: List[Dict[str, Any]],
    include_id: bool = False,
    delimiter: str = ';'
) -> str:
    """
    Exporte une liste d'enregistrements au format CSV.

    Args:
        module_name: Nom du module (pour recuperer les champs YAML)
        records: Liste de dictionnaires a exporter
        include_id: Inclure la colonne ID dans l'export
        delimiter: Delimiteur CSV (defaut: ; pour Excel FR)

    Returns:
        Contenu CSV en string (UTF-8 avec BOM)
    """
    if not records:
        logger.warning("export_csv_empty", module=module_name)
        return UTF8_BOM + f"Aucun enregistrement a exporter pour {module_name}"

    # Recuperer les champs du module
    fields = get_module_fields(module_name)

    if not fields:
        raise ValueError(f"Aucun champ exportable pour le module '{module_name}'")

    # Construire l'ordre des colonnes
    field_names = list(fields.keys())
    if include_id:
        field_names = ['id'] + field_names

    # Buffer pour le CSV
    output = io.StringIO()
    output.write(UTF8_BOM)

    writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

    # En-tetes avec labels
    headers = []
    for field_name in field_names:
        if field_name == 'id':
            headers.append('ID')
        else:
            headers.append(get_field_label(fields[field_name]))

    writer.writerow(headers)

    # Donnees
    for record in records:
        row = []
        for field_name in field_names:
            value = record.get(field_name, '')
            if field_name == 'id':
                row.append(str(value) if value else '')
            else:
                field_type = fields[field_name].type
                row.append(format_value_for_csv(value, field_type))
        writer.writerow(row)

    logger.info("export_csv_success", module=module_name, records=len(records))
    return output.getvalue()


# =============================================================================
# Import CSV
# =============================================================================
def import_from_csv(
    module_name: str,
    csv_content: str,
    tenant_id: UUID,
    user_id: Optional[UUID] = None,
    delimiter: str = ';',
    update_existing: bool = False
) -> Tuple[int, int, List[Dict[str, str]]]:
    """
    Importe des enregistrements depuis un fichier CSV.

    Args:
        module_name: Nom du module cible
        csv_content: Contenu du fichier CSV
        tenant_id: ID du tenant (obligatoire)
        user_id: ID de l'utilisateur effectuant l'import
        delimiter: Delimiteur CSV (detecte automatiquement si possible)
        update_existing: Si True, met a jour les enregistrements avec ID existant

    Returns:
        Tuple (nb_inseres, nb_mis_a_jour, erreurs)
        erreurs = liste de dicts {'ligne': int, 'erreur': str}
    """
    # Recuperer les champs du module
    fields = get_module_fields(module_name)
    module = ModuleParser.get(module_name)

    if not module:
        raise ValueError(f"Module '{module_name}' non trouve")

    # Nettoyer le BOM si present
    if csv_content.startswith(UTF8_BOM):
        csv_content = csv_content[1:]

    # Detecter le delimiteur
    first_line = csv_content.split('\n')[0]
    if ',' in first_line and ';' not in first_line:
        delimiter = ','
    elif '\t' in first_line:
        delimiter = '\t'

    # Lire le CSV
    reader = csv.reader(io.StringIO(csv_content), delimiter=delimiter)

    # Lire les en-tetes
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("Fichier CSV vide")

    # Nettoyer les en-tetes
    headers = [h.strip().lower() for h in headers]

    # Creer le mapping header -> field_name
    header_to_field = {}
    for header_idx, header in enumerate(headers):
        # Chercher par nom exact
        if header in fields:
            header_to_field[header_idx] = header
            continue

        # Chercher par label
        for field_name, field_def in fields.items():
            label = get_field_label(field_def).lower()
            if header == label or header == field_name.lower():
                header_to_field[header_idx] = field_name
                break

        # Gerer la colonne ID
        if header in ['id', 'identifiant']:
            header_to_field[header_idx] = 'id'

    if not header_to_field:
        raise ValueError("Aucune colonne reconnue dans le CSV. Verifiez les en-tetes.")

    # Importer les lignes
    inserted = 0
    updated = 0
    errors = []

    for line_num, row in enumerate(reader, start=2):
        if not row or all(cell.strip() == '' for cell in row):
            continue

        try:
            # Construire le dictionnaire de donnees
            data = {}
            record_id = None

            for header_idx, field_name in header_to_field.items():
                if header_idx >= len(row):
                    continue

                value = row[header_idx].strip()

                if field_name == 'id':
                    if value:
                        record_id = value
                    continue

                field_def = fields.get(field_name)
                if field_def:
                    parsed_value = parse_value_from_csv(value, field_def)
                    if parsed_value is not None or not field_def.requis:
                        data[field_name] = parsed_value

            # Verifier les champs requis
            for field_name, field_def in fields.items():
                if field_def.requis and field_name not in data:
                    raise ValueError(f"Champ requis manquant: {get_field_label(field_def)}")

            # Inserer ou mettre a jour
            if record_id and update_existing:
                try:
                    existing = Database.get_by_id(module_name, tenant_id, UUID(record_id))
                    if existing:
                        Database.update(module_name, tenant_id, UUID(record_id), data, user_id)
                        updated += 1
                        continue
                except Exception:
                    pass

            # Insertion
            Database.insert(module_name, tenant_id, data, user_id)
            inserted += 1

        except Exception as e:
            errors.append({
                'ligne': line_num,
                'erreur': str(e)
            })
            logger.warning("import_csv_line_error", module=module_name, line=line_num, error=str(e))

    logger.info(
        "import_csv_complete",
        module=module_name,
        inserted=inserted,
        updated=updated,
        errors=len(errors)
    )

    return inserted, updated, errors


# =============================================================================
# Template CSV
# =============================================================================
def generate_csv_template(module_name: str, delimiter: str = ';') -> str:
    """
    Genere un template CSV vide pour un module.
    Utile pour que l'utilisateur connaisse le format attendu.

    Args:
        module_name: Nom du module
        delimiter: Delimiteur CSV

    Returns:
        Contenu CSV avec uniquement les en-tetes
    """
    fields = get_module_fields(module_name)

    if not fields:
        raise ValueError(f"Aucun champ exportable pour le module '{module_name}'")

    output = io.StringIO()
    output.write(UTF8_BOM)

    writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

    # En-tetes avec labels
    headers = [get_field_label(field_def) for field_def in fields.values()]
    writer.writerow(headers)

    # Ligne d'exemple avec les types
    example_row = []
    for field_def in fields.values():
        if field_def.type in ['oui/non', 'booleen']:
            example_row.append('Oui/Non')
        elif field_def.type == 'date':
            example_row.append('JJ/MM/AAAA')
        elif field_def.type == 'datetime':
            example_row.append('JJ/MM/AAAA HH:MM')
        elif field_def.type in ['entier', 'nombre', 'monnaie', 'pourcentage']:
            example_row.append('0')
        elif field_def.type == 'email':
            example_row.append('email@exemple.com')
        elif field_def.type == 'telephone':
            example_row.append('+33600000000')
        elif field_def.enum_values:
            example_row.append(' | '.join(field_def.enum_values[:3]))
        else:
            example_row.append('')

    writer.writerow(example_row)

    logger.debug("csv_template_generated", module=module_name)
    return output.getvalue()
