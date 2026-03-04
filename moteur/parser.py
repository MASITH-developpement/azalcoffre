# =============================================================================
# AZALPLUS - Module Parser
# =============================================================================
"""
Parse les fichiers YAML de définition de modules.
Transforme le YAML en structures utilisables par le moteur.
Inclut le support des champs personnalises (custom fields).
Inclut la validation YAML stricte pour éviter les erreurs de syntaxe.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from uuid import UUID as PyUUID
import structlog
import re

from .config import settings
from .db import Database

logger = structlog.get_logger()

# =============================================================================
# YAML Validation
# =============================================================================
class YAMLValidationError(Exception):
    """Erreur de validation YAML avec contexte détaillé."""
    def __init__(self, file_path: str, message: str, line: int = None, suggestion: str = None):
        self.file_path = file_path
        self.line = line
        self.suggestion = suggestion
        full_message = f"[{file_path}]"
        if line:
            full_message += f" ligne {line}"
        full_message += f": {message}"
        if suggestion:
            full_message += f"\n  Suggestion: {suggestion}"
        super().__init__(full_message)


class YAMLValidator:
    """Validateur YAML strict pour les modules AZALPLUS."""

    # Patterns problématiques connus
    PROBLEMATIC_PATTERNS = [
        # Deux-points non quotés dans les descriptions
        (r'description:\s*[^"\']*\([^)]*:[^)]*\)',
         "Deux-points dans une description avec parenthèses - utilisez des guillemets"),
        # Strings avec : non quotées
        (r':\s+[A-Za-z][^:"\'\n]*:[^\n]*$',
         "Deux-points dans une valeur - utilisez des guillemets"),
    ]

    # Champs obligatoires pour un module (nom optionnel car peut venir du filename)
    REQUIRED_FIELDS = []  # Rendu flexible car nom peut être déduit du fichier

    # Types de champs valides (étendu pour supporter tous les alias)
    VALID_FIELD_TYPES = [
        'text', 'texte', 'string', 'varchar',
        'number', 'nombre', 'entier', 'integer', 'int', 'float', 'decimal',
        'date', 'datetime', 'timestamp', 'time',
        'boolean', 'booleen', 'bool', 'oui/non',
        'select', 'enum', 'choice', 'options',
        'relation', 'lien', 'reference', 'foreign_key',
        'textarea', 'longtext', 'text_long', 'texte_long',
        'email', 'tel', 'telephone', 'phone', 'url', 'uri',
        'json', 'jsonb', 'array', 'list', 'tags',
        'file', 'fichier', 'image', 'attachment', 'document',
        'money', 'montant', 'currency', 'amount', 'price', 'prix',
        'percent', 'percentage', 'pourcentage',
        'color', 'colour', 'couleur',
        'password', 'secret', 'mot_de_passe',
        'rich_text', 'html', 'markdown', 'wysiwyg',
        'signature', 'signature_pad',
        'address', 'adresse', 'location',
        'coordinates', 'gps', 'geo',
        'uuid', 'id', 'identifier'
    ]

    @classmethod
    def validate_file(cls, path: Path) -> Tuple[bool, List[str]]:
        """
        Valide un fichier YAML de module.

        Returns:
            Tuple (is_valid, list_of_errors)
        """
        errors = []

        # 1. Vérifier que le fichier existe
        if not path.exists():
            return False, [f"Fichier non trouvé: {path}"]

        # 2. Lire le contenu brut pour analyse
        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            return False, [f"Erreur lecture fichier: {e}"]

        # 3. Vérifier les patterns problématiques avant parsing
        line_errors = cls._check_problematic_patterns(content, path)
        errors.extend(line_errors)

        # 4. Essayer de parser le YAML
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            error_msg = str(e)
            # Extraire le numéro de ligne si disponible
            line_match = re.search(r'line (\d+)', error_msg)
            line_num = int(line_match.group(1)) if line_match else None

            suggestion = cls._suggest_fix(content, line_num) if line_num else None
            errors.append(f"Erreur YAML ligne {line_num or '?'}: {error_msg}")
            if suggestion:
                errors.append(f"  → Suggestion: {suggestion}")
            return False, errors

        # 5. Valider la structure du module
        if data:
            structure_errors = cls._validate_structure(data, path)
            errors.extend(structure_errors)

        return len(errors) == 0, errors

    @classmethod
    def _check_problematic_patterns(cls, content: str, path: Path) -> List[str]:
        """Vérifie les patterns problématiques connus."""
        errors = []
        lines = content.split('\n')

        in_multiline_block = False
        multiline_indent = 0

        for line_num, line in enumerate(lines, 1):
            # Ignorer les commentaires et lignes vides
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue

            # Calculer l'indentation de la ligne actuelle
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
                # On reste dans le bloc tant que l'indentation est supérieure
                if current_indent > multiline_indent:
                    continue  # Ignorer le contenu du bloc multiligne
                else:
                    # Sortie du bloc multiligne
                    in_multiline_block = False

            # Vérifier : dans les valeurs non quotées
            if ':' in line and not in_multiline_block:
                # Après le premier :, s'il y a un autre : non quoté
                parts = line.split(':', 1)
                if len(parts) > 1:
                    value_part = parts[1].strip()
                    # Si la valeur contient : et n'est pas quotée
                    if ':' in value_part and not (
                        value_part.startswith('"') or
                        value_part.startswith("'") or
                        value_part.startswith('[') or
                        value_part.startswith('{') or
                        value_part in ('|', '>', '|-', '>-', '|+', '>+')
                    ):
                        # Exceptions: URLs, timestamps, lignes avec pipe
                        if not re.match(r'^\d{2}:\d{2}', value_part):  # pas une heure
                            if not value_part.startswith('http'):  # pas une URL
                                if '|' not in value_part:  # pas un indicateur multiligne
                                    errors.append(
                                        f"Ligne {line_num}: Deux-points dans la valeur - "
                                        f"utilisez des guillemets: {line.strip()}"
                                    )

        return errors

    @classmethod
    def _suggest_fix(cls, content: str, line_num: int) -> Optional[str]:
        """Suggère une correction pour une ligne problématique."""
        lines = content.split('\n')
        if line_num <= 0 or line_num > len(lines):
            return None

        line = lines[line_num - 1]

        # Si c'est un problème de : non quoté
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) > 1:
                key = parts[0]
                value = parts[1].strip()
                if value and not (value.startswith('"') or value.startswith("'")):
                    return f'{key}: "{value}"'

        return None

    @classmethod
    def _validate_structure(cls, data: Dict, path: Path) -> List[str]:
        """Valide la structure du module."""
        errors = []

        # Si c'est un dict avec une seule clé (format enveloppé)
        if isinstance(data, dict) and len(data) == 1:
            data = list(data.values())[0]

        if not isinstance(data, dict):
            errors.append("Le module doit être un dictionnaire YAML")
            return errors

        # Vérifier les champs obligatoires
        for field_name in cls.REQUIRED_FIELDS:
            if field_name not in data:
                errors.append(f"Champ obligatoire manquant: '{field_name}'")

        # Valider les champs si présents
        if 'champs' in data:
            champs = data['champs']
            if isinstance(champs, list):
                for i, champ in enumerate(champs):
                    if isinstance(champ, dict):
                        field_errors = cls._validate_field(champ, i + 1)
                        errors.extend(field_errors)
            elif isinstance(champs, dict):
                for nom, config in champs.items():
                    if isinstance(config, dict):
                        field_errors = cls._validate_field(config, nom)
                        errors.extend(field_errors)

        return errors

    @classmethod
    def _validate_field(cls, field_config: Dict, field_id) -> List[str]:
        """Valide la configuration d'un champ."""
        errors = []

        # Le type est requis
        field_type = field_config.get('type')
        if field_type and field_type not in cls.VALID_FIELD_TYPES:
            # Vérifier si c'est un type avec modificateurs
            base_type = field_type.split()[0] if isinstance(field_type, str) else field_type
            if base_type not in cls.VALID_FIELD_TYPES:
                errors.append(
                    f"Champ {field_id}: Type '{field_type}' non reconnu. "
                    f"Types valides: {', '.join(cls.VALID_FIELD_TYPES[:10])}..."
                )

        return errors

    @classmethod
    def validate_all_modules(cls, modules_dir: Path) -> Dict[str, List[str]]:
        """
        Valide tous les modules d'un répertoire.

        Returns:
            Dict mapping file_path -> list_of_errors (vide si valide)
        """
        results = {}

        if not modules_dir.exists():
            return {"_error": [f"Répertoire non trouvé: {modules_dir}"]}

        for yaml_file in modules_dir.glob("**/*.yml"):
            is_valid, errors = cls.validate_file(yaml_file)
            if not is_valid:
                results[str(yaml_file)] = errors

        return results

    @classmethod
    def print_validation_report(cls, modules_dir: Path) -> bool:
        """
        Affiche un rapport de validation et retourne True si tout est valide.
        """
        results = cls.validate_all_modules(modules_dir)

        if not results:
            logger.info("yaml_validation_success", message="Tous les modules YAML sont valides")
            return True

        logger.error("yaml_validation_failed",
                    invalid_count=len(results),
                    message="Erreurs de validation YAML détectées")

        for file_path, errors in results.items():
            for error in errors:
                logger.error("yaml_error", file=file_path, error=error)

        return False

# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class FieldValidationConfig:
    """Configuration de validation d'un champ."""
    format: Optional[str] = None  # email, phone, url, siret, iban, code_postal, tva_intra, siren, code_naf, bic
    pattern: Optional[str] = None  # Regex personnalise
    min: Optional[float] = None  # Valeur minimale (numerique)
    max: Optional[float] = None  # Valeur maximale (numerique)
    min_length: Optional[int] = None  # Longueur minimale (texte)
    max_length: Optional[int] = None  # Longueur maximale (texte)
    unique: bool = False  # Valeur unique dans le module
    message: Optional[str] = None  # Message d'erreur personnalise

@dataclass
class FieldDefinition:
    """Définition d'un champ."""
    nom: str
    type: str
    requis: bool = False
    defaut: Any = None
    unique: bool = False
    index: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    enum_values: List[str] = field(default_factory=list)
    lien_vers: Optional[str] = None
    label: Optional[str] = None
    aide: Optional[str] = None
    # Validation avancee
    validation: Optional[FieldValidationConfig] = None
    # Champs personnalises
    is_custom: bool = False
    custom_field_id: Optional[str] = None
    ordre: int = 0
    groupe: Optional[str] = None
    placeholder: Optional[str] = None
    afficher_liste: bool = False
    afficher_recherche: bool = False
    afficher_filtre: bool = False
    regex: Optional[str] = None
    message_erreur: Optional[str] = None
    autocompletion: bool = False  # Autocomplétion IA

@dataclass
class WorkflowTransition:
    """Transition de workflow."""
    de: str
    vers: str
    condition: Optional[str] = None
    action: Optional[str] = None

@dataclass
class ModuleDefinition:
    """Définition complète d'un module."""
    nom: str
    nom_affichage: str
    icone: str = "file"
    menu: str = "Général"
    description: str = ""

    champs: Dict[str, FieldDefinition] = field(default_factory=dict)
    workflow: List[WorkflowTransition] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    marceau: Dict[str, Any] = field(default_factory=dict)

    # Métadonnées
    version: int = 1
    actif: bool = True

# =============================================================================
# Module Parser
# =============================================================================
class ModuleParser:
    """Parse et stocke les définitions de modules."""

    _modules: Dict[str, ModuleDefinition] = {}
    _raw_definitions: Dict[str, Dict] = {}

    @classmethod
    def load_all_modules(cls, validate_first: bool = True):
        """
        Charge tous les modules depuis le répertoire modules/.

        Args:
            validate_first: Si True, valide tous les fichiers YAML avant de charger
        """
        modules_dir = Path(settings.MODULES_DIR)

        if not modules_dir.exists():
            logger.warning("modules_dir_not_found", path=str(modules_dir))
            return

        # Validation préalable si demandée
        if validate_first:
            validation_results = YAMLValidator.validate_all_modules(modules_dir)
            if validation_results:
                # Log les erreurs mais continue le chargement des modules valides
                logger.warning("yaml_validation_warnings",
                             invalid_count=len(validation_results),
                             message="Certains modules ont des erreurs YAML")
                for file_path, errors in validation_results.items():
                    for error in errors:
                        logger.warning("yaml_warning", file=file_path, error=error)

        # Charger chaque fichier YAML
        loaded_count = 0
        error_count = 0
        for yaml_file in modules_dir.glob("**/*.yml"):
            try:
                # Validation individuelle avant chargement
                is_valid, errors = YAMLValidator.validate_file(yaml_file)
                if not is_valid:
                    logger.warning("module_skipped_invalid",
                                 file=str(yaml_file),
                                 errors=errors[:3])  # Max 3 erreurs loggées
                    error_count += 1
                    continue

                cls.load_module(yaml_file)
                loaded_count += 1
            except Exception as e:
                logger.error("module_load_error", file=str(yaml_file), error=str(e))
                error_count += 1

        logger.info("modules_loaded",
                   count=loaded_count,
                   errors=error_count,
                   total=len(cls._modules))

    @classmethod
    def load_module(cls, path: Path, skip_validation: bool = False) -> Optional[ModuleDefinition]:
        """
        Charge un module depuis un fichier YAML.

        Args:
            path: Chemin vers le fichier YAML
            skip_validation: Si True, ignore la validation (pour performance)

        Returns:
            ModuleDefinition ou None si erreur

        Raises:
            YAMLValidationError: Si le fichier YAML est invalide
        """
        # Validation préalable
        if not skip_validation:
            is_valid, errors = YAMLValidator.validate_file(path)
            if not is_valid:
                error_msg = "; ".join(errors[:3])  # Max 3 erreurs
                raise YAMLValidationError(
                    file_path=str(path),
                    message=error_msg,
                    suggestion="Vérifiez que les valeurs contenant ':' sont entre guillemets"
                )

        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise YAMLValidationError(
                file_path=str(path),
                message=f"Erreur de syntaxe YAML: {e}",
                suggestion="Utilisez des guillemets pour les valeurs contenant des caractères spéciaux"
            )

        if not raw:
            return None

        # Le nom du module est la première clé ou le nom du fichier
        module_name = path.stem
        if isinstance(raw, dict) and len(raw) == 1:
            first_key = list(raw.keys())[0]
            # Vérifier si c'est un wrapper
            if isinstance(raw[first_key], dict):
                module_name = first_key
                raw = raw[first_key]

        # Parser la définition
        definition = cls._parse_definition(module_name, raw)

        # Stocker
        cls._modules[module_name] = definition
        cls._raw_definitions[module_name] = raw

        # Créer la table en base si le moteur DB est initialisé
        if Database._engine is not None:
            try:
                Database.create_table_from_definition(module_name.lower(), raw)
            except Exception as e:
                logger.warning("table_creation_skipped", module=module_name, error=str(e))

        # Enregistrer les champs encryptés pour ce module
        encrypted_fields = cls._extract_encrypted_fields(raw)
        if encrypted_fields:
            Database.register_encrypted_fields(module_name.lower(), encrypted_fields)
            logger.debug("encrypted_fields_registered", module=module_name, count=len(encrypted_fields))

        logger.debug("module_loaded", name=module_name, fields=len(definition.champs))
        return definition

    @classmethod
    def _extract_encrypted_fields(cls, raw: Dict) -> List[str]:
        """Extrait la liste des champs marqués comme encryptés (chiffre: true)."""
        encrypted = []
        champs = raw.get("champs", [])

        if isinstance(champs, list):
            for field_config in champs:
                if isinstance(field_config, dict):
                    nom = field_config.get("nom")
                    if nom and (field_config.get("chiffre") or field_config.get("encrypted")):
                        encrypted.append(nom)
        elif isinstance(champs, dict):
            for nom, config in champs.items():
                if isinstance(config, dict):
                    if config.get("chiffre") or config.get("encrypted"):
                        encrypted.append(nom)

        return encrypted

    @classmethod
    def _parse_definition(cls, nom: str, raw: Dict) -> ModuleDefinition:
        """Parse une définition brute en ModuleDefinition."""

        definition = ModuleDefinition(
            nom=nom,
            nom_affichage=raw.get("nom", nom.title()),
            icone=raw.get("icone", "file"),
            menu=raw.get("menu", "Général"),
            description=raw.get("description", "")
        )

        # Parser les champs
        # Parser les champs - supporte les deux formats (liste ou dict)
        champs_raw = raw.get("champs", {})
        if isinstance(champs_raw, list):
            # Format liste: [{nom: ..., type: ...}, ...]
            for field_config in champs_raw:
                if isinstance(field_config, dict) and "nom" in field_config:
                    nom_champ = field_config["nom"]
                    field_def = cls._parse_field(nom_champ, field_config)
                    definition.champs[nom_champ] = field_def
        elif isinstance(champs_raw, dict):
            # Format dict: {nom_champ: config, ...}
            for nom_champ, config in champs_raw.items():
                field_def = cls._parse_field(nom_champ, config)
                definition.champs[nom_champ] = field_def

        # Parser le workflow - supporte les formats dict, list, et string
        workflow_raw = raw.get("workflow", {})
        if isinstance(workflow_raw, dict):
            for transition_str, config in workflow_raw.items():
                transitions = cls._parse_workflow(transition_str, config)
                definition.workflow.extend(transitions)
        elif isinstance(workflow_raw, list):
            # Format liste: ["ETAT1 -> ETAT2", ...]
            for item in workflow_raw:
                if isinstance(item, str):
                    transitions = cls._parse_workflow(item, None)
                    definition.workflow.extend(transitions)
                elif isinstance(item, dict):
                    for transition_str, config in item.items():
                        transitions = cls._parse_workflow(transition_str, config)
                        definition.workflow.extend(transitions)

        # Actions
        definition.actions = raw.get("actions", [])

        # Marceau
        definition.marceau = raw.get("marceau", {})

        return definition

    @classmethod
    def _parse_field(cls, nom: str, config) -> FieldDefinition:
        """Parse une définition de champ."""

        field_def = FieldDefinition(nom=nom, type="texte")

        # Config peut être une string simple, un dict, ou une liste (embedded)
        if isinstance(config, list):
            # Champs imbriqués (ex: lignes de facture) -> type json
            field_def.type = "json"
            field_def.defaut = []
            return field_def

        if isinstance(config, str):
            parts = config.split()
            field_def.type = parts[0]

            for part in parts[1:]:
                if part == "requis":
                    field_def.requis = True
                elif part == "unique":
                    field_def.unique = True
                elif part.startswith("defaut="):
                    field_def.defaut = part.split("=", 1)[1]
                elif part.startswith("min="):
                    field_def.min = float(part.split("=", 1)[1])
                elif part.startswith("max="):
                    field_def.max = float(part.split("=", 1)[1])
                elif part.startswith("vers="):
                    field_def.lien_vers = part.split("=", 1)[1]

        elif isinstance(config, dict):
            field_def.type = config.get("type", "texte")
            field_def.requis = config.get("requis", False) or config.get("obligatoire", False)
            field_def.defaut = config.get("defaut")
            field_def.unique = config.get("unique", False)
            field_def.min = config.get("min")
            field_def.max = config.get("max")
            field_def.lien_vers = config.get("vers") or config.get("relation")
            field_def.label = config.get("label") or config.get("description")
            field_def.aide = config.get("aide")
            field_def.autocompletion = config.get("autocompletion", False)

            if "enum" in config:
                field_def.enum_values = config["enum"]
            elif "options" in config:
                field_def.enum_values = config["options"]

            # Parser la section validation
            validation_config = config.get("validation", {})
            if validation_config:
                field_def.validation = FieldValidationConfig(
                    format=validation_config.get("format"),
                    pattern=validation_config.get("pattern"),
                    min=validation_config.get("min"),
                    max=validation_config.get("max"),
                    min_length=validation_config.get("minLength") or validation_config.get("min_length"),
                    max_length=validation_config.get("maxLength") or validation_config.get("max_length"),
                    unique=validation_config.get("unique", False),
                    message=validation_config.get("message")
                )
                # Propager unique au niveau du champ
                if validation_config.get("unique"):
                    field_def.unique = True

        # Parser les enums inline: "enum [A, B, C]"
        if field_def.type.startswith("enum"):
            import re
            match = re.search(r'\[(.*?)\]', field_def.type)
            if match:
                values = [v.strip() for v in match.group(1).split(',')]
                field_def.enum_values = values
                field_def.type = "enum"

        # Parser les liens: "lien vers=Module"
        if field_def.type.startswith("lien"):
            parts = field_def.type.split()
            for part in parts:
                if part.startswith("vers="):
                    field_def.lien_vers = part.split("=", 1)[1]
            field_def.type = "lien"

        return field_def

    @classmethod
    def _parse_workflow(cls, transition_str: str, config) -> List[WorkflowTransition]:
        """Parse une transition de workflow."""

        transitions = []

        # Format: "ETAT1 -> ETAT2"
        if "->" in transition_str:
            parts = transition_str.split("->")
            de = parts[0].strip()
            vers = parts[1].strip()

            condition = None
            action = None

            if isinstance(config, str):
                if config.startswith("si "):
                    condition = config[3:]
                elif config.startswith("action "):
                    action = config[7:]
            elif isinstance(config, dict):
                condition = config.get("si") or config.get("condition")
                action = config.get("action")

            transitions.append(WorkflowTransition(
                de=de,
                vers=vers,
                condition=condition,
                action=action
            ))

        return transitions

    @classmethod
    def get(cls, name: str) -> Optional[ModuleDefinition]:
        """Récupère une définition de module."""
        return cls._modules.get(name)

    @classmethod
    def get_raw(cls, name: str) -> Optional[Dict]:
        """Récupère la définition brute (YAML parsé)."""
        return cls._raw_definitions.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """Liste tous les modules chargés."""
        return list(cls._modules.keys())

    @classmethod
    def count(cls) -> int:
        """Nombre de modules chargés."""
        return len(cls._modules)

    @classmethod
    def reload(cls):
        """Recharge tous les modules."""
        cls._modules.clear()
        cls._raw_definitions.clear()
        cls.load_all_modules()

    # =========================================================================
    # Support des champs personnalises (Custom Fields)
    # =========================================================================
    @classmethod
    def get_custom_fields_for_module(cls, module_name: str, tenant_id: PyUUID) -> List[FieldDefinition]:
        """
        Recupere les champs personnalises definis pour un module.

        Args:
            module_name: Nom du module cible
            tenant_id: ID du tenant (isolation obligatoire)

        Returns:
            Liste des FieldDefinition pour les champs personnalises actifs
        """
        if Database._engine is None:
            return []

        try:
            # Recuperer les champs personnalises depuis la base
            custom_fields = Database.query(
                "champpersonnalise",
                tenant_id,
                filters={"module": module_name, "actif": True},
                order_by="ordre ASC"
            )

            fields = []
            for cf in custom_fields:
                field_def = cls._custom_field_to_definition(cf)
                if field_def:
                    fields.append(field_def)

            return fields

        except Exception as e:
            logger.debug("custom_fields_load_error", module=module_name, error=str(e))
            return []

    @classmethod
    def _custom_field_to_definition(cls, custom_field: Dict) -> Optional[FieldDefinition]:
        """
        Convertit un enregistrement de champ personnalise en FieldDefinition.

        Args:
            custom_field: Dictionnaire contenant les donnees du champ personnalise

        Returns:
            FieldDefinition ou None si invalide
        """
        nom_technique = custom_field.get("nom_technique")
        if not nom_technique:
            return None

        # Mapping des types custom vers types internes
        type_mapping = {
            "text": "texte",
            "number": "nombre",
            "date": "date",
            "select": "enum",
            "checkbox": "booleen",
            "textarea": "texte long",
            "email": "email",
            "tel": "telephone",
            "url": "url"
        }

        field_type = type_mapping.get(custom_field.get("type", "text"), "texte")

        # Parser les options si c'est un select
        enum_values = []
        if field_type == "enum" and custom_field.get("options"):
            options_str = custom_field.get("options", "")
            if isinstance(options_str, str):
                enum_values = [opt.strip() for opt in options_str.split("\n") if opt.strip()]
            elif isinstance(options_str, list):
                enum_values = options_str

        return FieldDefinition(
            nom=nom_technique,
            type=field_type,
            requis=custom_field.get("obligatoire", False),
            defaut=custom_field.get("valeur_defaut"),
            min=custom_field.get("min"),
            max=custom_field.get("max"),
            enum_values=enum_values,
            label=custom_field.get("nom_affichage"),
            aide=custom_field.get("aide"),
            is_custom=True,
            custom_field_id=str(custom_field.get("id")),
            ordre=custom_field.get("ordre", 100),
            groupe=custom_field.get("groupe"),
            placeholder=custom_field.get("placeholder"),
            afficher_liste=custom_field.get("afficher_liste", False),
            afficher_recherche=custom_field.get("afficher_recherche", False),
            afficher_filtre=custom_field.get("afficher_filtre", False),
            regex=custom_field.get("regex"),
            message_erreur=custom_field.get("message_erreur")
        )

    @classmethod
    def get_with_custom_fields(cls, name: str, tenant_id: PyUUID) -> Optional[ModuleDefinition]:
        """
        Recupere une definition de module avec les champs personnalises fusionnes.

        Args:
            name: Nom du module
            tenant_id: ID du tenant

        Returns:
            ModuleDefinition avec les champs personnalises inclus
        """
        module = cls.get(name)
        if not module:
            return None

        # Creer une copie pour ne pas modifier l'original
        from copy import deepcopy
        module_copy = deepcopy(module)

        # Ajouter les champs personnalises
        custom_fields = cls.get_custom_fields_for_module(name, tenant_id)
        for cf in custom_fields:
            # Prefixer avec cf_ pour eviter les collisions
            field_key = f"cf_{cf.nom}" if not cf.nom.startswith("cf_") else cf.nom
            module_copy.champs[field_key] = cf

        return module_copy

    @classmethod
    def get_list_fields(cls, module: ModuleDefinition) -> List[FieldDefinition]:
        """
        Retourne les champs a afficher dans les listes.
        Inclut les champs de base + les champs personnalises avec afficher_liste=True.

        Args:
            module: Definition du module

        Returns:
            Liste des champs a afficher
        """
        list_fields = []

        for nom, field_def in module.champs.items():
            # Champs standards: prendre les 5 premiers non-custom
            if not field_def.is_custom:
                if len([f for f in list_fields if not f.is_custom]) < 5:
                    list_fields.append(field_def)
            # Champs personnalises: seulement si afficher_liste
            elif field_def.afficher_liste:
                list_fields.append(field_def)

        # Trier par ordre
        list_fields.sort(key=lambda f: f.ordre)

        return list_fields

    @classmethod
    def get_search_fields(cls, module: ModuleDefinition) -> List[str]:
        """
        Retourne les noms des champs a inclure dans la recherche.

        Args:
            module: Definition du module

        Returns:
            Liste des noms de champs
        """
        search_fields = ["nom", "reference", "raison_sociale", "email", "numero", "titre", "description"]

        # Ajouter les champs personnalises avec afficher_recherche=True
        for nom, field_def in module.champs.items():
            if field_def.is_custom and field_def.afficher_recherche:
                search_fields.append(nom)

        return search_fields
