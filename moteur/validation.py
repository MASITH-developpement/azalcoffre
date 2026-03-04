# =============================================================================
# AZALPLUS - Validation Engine
# =============================================================================
"""
Moteur de validation pour les modules AZALPLUS.
Valide les champs selon les regles definies dans le YAML des modules.

Supporte:
- Validations de format: email, phone, url, siret, iban, etc.
- Validations numeriques: min, max, range
- Validations texte: pattern (regex), minLength, maxLength
- Validations specifiques France: siret, siren, code_postal, tva_intra
- Validations metier: unique, required
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID
import structlog
import yaml
from pathlib import Path

from .config import settings

logger = structlog.get_logger()


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class ValidationError:
    """Erreur de validation."""
    field: str
    message: str
    code: str
    value: Any = None


@dataclass
class ValidationResult:
    """Resultat de validation."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)

    def add_error(self, field: str, message: str, code: str, value: Any = None):
        """Ajoute une erreur."""
        self.errors.append(ValidationError(
            field=field,
            message=message,
            code=code,
            value=value
        ))
        self.valid = False

    def merge(self, other: 'ValidationResult'):
        """Fusionne avec un autre resultat."""
        if not other.valid:
            self.valid = False
            self.errors.extend(other.errors)

    def to_dict(self) -> Dict:
        """Convertit en dictionnaire pour API."""
        return {
            "valid": self.valid,
            "errors": [
                {
                    "field": e.field,
                    "message": e.message,
                    "code": e.code,
                    "value": e.value
                }
                for e in self.errors
            ]
        }


@dataclass
class FieldValidation:
    """Configuration de validation d'un champ."""
    # Format
    format: Optional[str] = None  # email, phone, url, siret, iban, etc.
    pattern: Optional[str] = None  # Regex personnalise

    # Numerique
    min: Optional[float] = None
    max: Optional[float] = None

    # Texte
    min_length: Optional[int] = None
    max_length: Optional[int] = None

    # Metier
    unique: bool = False
    allowed_values: Optional[List[str]] = None

    # Message personnalise
    message: Optional[str] = None


# =============================================================================
# Built-in Validators
# =============================================================================
class BuiltinValidators:
    """Validateurs integres."""

    # -------------------------------------------------------------------------
    # Email
    # -------------------------------------------------------------------------
    EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    @classmethod
    def validate_email(cls, value: str) -> Tuple[bool, str]:
        """Valide un email."""
        if not value:
            return True, ""

        if not re.match(cls.EMAIL_PATTERN, value):
            return False, "Email invalide"
        return True, ""

    # -------------------------------------------------------------------------
    # Telephone
    # -------------------------------------------------------------------------
    PHONE_PATTERN = r'^[\+]?[0-9\s\-\.\(\)]{10,}$'
    PHONE_FR_PATTERN = r'^(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}$'

    @classmethod
    def validate_phone(cls, value: str, strict_fr: bool = False) -> Tuple[bool, str]:
        """Valide un numero de telephone."""
        if not value:
            return True, ""

        # Nettoyer le numero
        cleaned = re.sub(r'\s', '', value)

        if strict_fr:
            if not re.match(cls.PHONE_FR_PATTERN, value):
                return False, "Numero de telephone francais invalide (ex: 0612345678)"
        else:
            if not re.match(cls.PHONE_PATTERN, cleaned):
                return False, "Numero de telephone invalide (minimum 10 chiffres)"

        return True, ""

    # -------------------------------------------------------------------------
    # URL
    # -------------------------------------------------------------------------
    URL_PATTERN = r'^https?:\/\/[\w\-]+(\.[\w\-]+)+[/#?]?.*$'

    @classmethod
    def validate_url(cls, value: str) -> Tuple[bool, str]:
        """Valide une URL."""
        if not value:
            return True, ""

        if not re.match(cls.URL_PATTERN, value):
            return False, "URL invalide (doit commencer par http:// ou https://)"
        return True, ""

    # -------------------------------------------------------------------------
    # SIRET (France - 14 chiffres)
    # -------------------------------------------------------------------------
    SIRET_PATTERN = r'^[0-9]{14}$'

    @classmethod
    def validate_siret(cls, value: str) -> Tuple[bool, str]:
        """Valide un SIRET (14 chiffres) avec controle Luhn."""
        if not value:
            return True, ""

        # Nettoyer (enlever espaces)
        cleaned = re.sub(r'\s', '', value)

        # Verifier format
        if not re.match(cls.SIRET_PATTERN, cleaned):
            return False, "SIRET invalide (14 chiffres requis)"

        # Algorithme de Luhn
        if not cls._luhn_check(cleaned):
            return False, "SIRET invalide (verification Luhn echouee)"

        return True, ""

    # -------------------------------------------------------------------------
    # SIREN (France - 9 chiffres)
    # -------------------------------------------------------------------------
    SIREN_PATTERN = r'^[0-9]{9}$'

    @classmethod
    def validate_siren(cls, value: str) -> Tuple[bool, str]:
        """Valide un SIREN (9 chiffres) avec controle Luhn."""
        if not value:
            return True, ""

        cleaned = re.sub(r'\s', '', value)

        if not re.match(cls.SIREN_PATTERN, cleaned):
            return False, "SIREN invalide (9 chiffres requis)"

        if not cls._luhn_check(cleaned):
            return False, "SIREN invalide (verification Luhn echouee)"

        return True, ""

    # -------------------------------------------------------------------------
    # Code Postal France (5 chiffres)
    # -------------------------------------------------------------------------
    CODE_POSTAL_FR_PATTERN = r'^[0-9]{5}$'

    @classmethod
    def validate_code_postal_fr(cls, value: str) -> Tuple[bool, str]:
        """Valide un code postal francais (5 chiffres)."""
        if not value:
            return True, ""

        cleaned = re.sub(r'\s', '', value)

        if not re.match(cls.CODE_POSTAL_FR_PATTERN, cleaned):
            return False, "Code postal invalide (5 chiffres requis)"

        # Verification departement valide (01-95, 971-976, 2A, 2B)
        dept = cleaned[:2]
        if dept == "20":
            return False, "Code postal invalide (utiliser 2A ou 2B pour la Corse)"

        if cleaned[:3] in ["971", "972", "973", "974", "975", "976"]:
            return True, ""

        dept_int = int(dept)
        if dept_int < 1 or (dept_int > 95 and dept_int not in [97]):
            return False, "Code postal invalide (departement inconnu)"

        return True, ""

    # -------------------------------------------------------------------------
    # TVA Intracommunautaire
    # -------------------------------------------------------------------------
    TVA_INTRA_PATTERNS = {
        'FR': r'^FR[0-9A-Z]{2}[0-9]{9}$',
        'DE': r'^DE[0-9]{9}$',
        'BE': r'^BE[0-9]{10}$',
        'ES': r'^ES[A-Z0-9][0-9]{7}[A-Z0-9]$',
        'IT': r'^IT[0-9]{11}$',
        'GB': r'^GB[0-9]{9}([0-9]{3})?$',
    }

    @classmethod
    def validate_tva_intra(cls, value: str) -> Tuple[bool, str]:
        """Valide un numero de TVA intracommunautaire."""
        if not value:
            return True, ""

        cleaned = re.sub(r'\s', '', value).upper()

        if len(cleaned) < 4:
            return False, "Numero TVA intracommunautaire trop court"

        country_code = cleaned[:2]

        if country_code in cls.TVA_INTRA_PATTERNS:
            if not re.match(cls.TVA_INTRA_PATTERNS[country_code], cleaned):
                return False, f"Numero TVA {country_code} invalide"
        else:
            # Format generique pour autres pays
            if not re.match(r'^[A-Z]{2}[A-Z0-9]{2,13}$', cleaned):
                return False, "Numero TVA intracommunautaire invalide"

        return True, ""

    # -------------------------------------------------------------------------
    # IBAN
    # -------------------------------------------------------------------------
    IBAN_PATTERN = r'^[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}$'

    @classmethod
    def validate_iban(cls, value: str) -> Tuple[bool, str]:
        """Valide un IBAN avec controle modulo 97."""
        if not value:
            return True, ""

        cleaned = re.sub(r'\s', '', value).upper()

        if not re.match(cls.IBAN_PATTERN, cleaned):
            return False, "Format IBAN invalide"

        # Verification modulo 97
        if not cls._iban_check(cleaned):
            return False, "IBAN invalide (verification modulo 97 echouee)"

        return True, ""

    @classmethod
    def _iban_check(cls, iban: str) -> bool:
        """Verifie un IBAN avec l'algorithme modulo 97."""
        # Deplacer les 4 premiers caracteres a la fin
        rearranged = iban[4:] + iban[:4]

        # Convertir les lettres en chiffres (A=10, B=11, etc.)
        numeric = ""
        for char in rearranged:
            if char.isalpha():
                numeric += str(ord(char) - ord('A') + 10)
            else:
                numeric += char

        # Verifier modulo 97
        return int(numeric) % 97 == 1

    # -------------------------------------------------------------------------
    # BIC/SWIFT
    # -------------------------------------------------------------------------
    BIC_PATTERN = r'^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$'

    @classmethod
    def validate_bic(cls, value: str) -> Tuple[bool, str]:
        """Valide un code BIC/SWIFT."""
        if not value:
            return True, ""

        cleaned = re.sub(r'\s', '', value).upper()

        if not re.match(cls.BIC_PATTERN, cleaned):
            return False, "Code BIC/SWIFT invalide"

        return True, ""

    # -------------------------------------------------------------------------
    # Code NAF (France)
    # -------------------------------------------------------------------------
    CODE_NAF_PATTERN = r'^[0-9]{4}[A-Z]$'

    @classmethod
    def validate_code_naf(cls, value: str) -> Tuple[bool, str]:
        """Valide un code NAF francais."""
        if not value:
            return True, ""

        cleaned = re.sub(r'\s', '', value).upper()

        if not re.match(cls.CODE_NAF_PATTERN, cleaned):
            return False, "Code NAF invalide (ex: 6201Z)"

        return True, ""

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    @classmethod
    def _luhn_check(cls, number: str) -> bool:
        """Algorithme de Luhn pour verification SIRET/SIREN."""
        total = 0
        for i, char in enumerate(number):
            digit = int(char)
            if i % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0


# =============================================================================
# Main Validator Class
# =============================================================================
class Validator:
    """Validateur principal pour les modules AZALPLUS."""

    # Mapping des formats vers les fonctions de validation
    FORMAT_VALIDATORS = {
        'email': BuiltinValidators.validate_email,
        'phone': BuiltinValidators.validate_phone,
        'telephone': BuiltinValidators.validate_phone,
        'tel': BuiltinValidators.validate_phone,
        'url': BuiltinValidators.validate_url,
        'siret': BuiltinValidators.validate_siret,
        'siren': BuiltinValidators.validate_siren,
        'code_postal': BuiltinValidators.validate_code_postal_fr,
        'code_postal_fr': BuiltinValidators.validate_code_postal_fr,
        'tva_intra': BuiltinValidators.validate_tva_intra,
        'iban': BuiltinValidators.validate_iban,
        'bic': BuiltinValidators.validate_bic,
        'code_naf': BuiltinValidators.validate_code_naf,
    }

    # Cache des regles de validation par module
    _validation_rules: Dict[str, Dict[str, FieldValidation]] = {}
    _validations_config: Optional[Dict] = None

    @classmethod
    def load_validation_config(cls):
        """Charge la configuration de validation depuis validations.yml."""
        config_path = Path(settings.CONFIG_DIR) / "validations.yml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._validations_config = yaml.safe_load(f)
                logger.info("validation_config_loaded", path=str(config_path))

    @classmethod
    def register_module_validations(cls, module_name: str, champs: List[Dict]):
        """Enregistre les regles de validation pour un module."""
        cls._validation_rules[module_name] = {}

        for champ in champs:
            if isinstance(champ, dict) and 'nom' in champ:
                nom = champ['nom']
                validation = champ.get('validation', {})

                if validation or champ.get('type') in ['email', 'tel', 'url']:
                    field_validation = FieldValidation(
                        format=validation.get('format') or cls._infer_format(champ.get('type')),
                        pattern=validation.get('pattern'),
                        min=validation.get('min'),
                        max=validation.get('max'),
                        min_length=validation.get('minLength') or validation.get('min_length'),
                        max_length=validation.get('maxLength') or validation.get('max_length'),
                        unique=validation.get('unique', False),
                        allowed_values=validation.get('allowed_values'),
                        message=validation.get('message')
                    )
                    cls._validation_rules[module_name][nom] = field_validation

        logger.debug(
            "module_validations_registered",
            module=module_name,
            fields_count=len(cls._validation_rules[module_name])
        )

    @classmethod
    def _infer_format(cls, field_type: Optional[str]) -> Optional[str]:
        """Infere le format de validation depuis le type de champ."""
        if not field_type:
            return None

        type_to_format = {
            'email': 'email',
            'tel': 'phone',
            'telephone': 'phone',
            'url': 'url',
        }
        return type_to_format.get(field_type)

    @classmethod
    def validate_field(
        cls,
        field_config: Dict,
        value: Any,
        field_name: str = "field"
    ) -> ValidationResult:
        """
        Valide une valeur selon la configuration du champ.

        Args:
            field_config: Configuration du champ (depuis YAML)
            value: Valeur a valider
            field_name: Nom du champ pour les messages d'erreur

        Returns:
            ValidationResult avec valid=True/False et liste d'erreurs
        """
        result = ValidationResult(valid=True)

        # Extraire la validation du config
        validation = field_config.get('validation', {})
        field_type = field_config.get('type', 'text')
        is_required = field_config.get('obligatoire', False) or field_config.get('requis', False)

        # Valeur vide
        is_empty = value is None or (isinstance(value, str) and value.strip() == '')

        # Champ requis
        if is_required and is_empty:
            result.add_error(
                field=field_name,
                message="Ce champ est requis",
                code="required",
                value=value
            )
            return result

        # Si vide et non requis, pas de validation supplementaire
        if is_empty:
            return result

        # Convertir en string pour validation
        str_value = str(value) if value is not None else ""

        # Validation de format
        format_type = validation.get('format') or cls._infer_format(field_type)
        if format_type:
            valid, message = cls._validate_format(format_type, str_value)
            if not valid:
                result.add_error(
                    field=field_name,
                    message=validation.get('message') or message,
                    code=f"format_{format_type}",
                    value=value
                )

        # Validation pattern (regex personnalise)
        pattern = validation.get('pattern')
        if pattern:
            try:
                if not re.match(pattern, str_value):
                    result.add_error(
                        field=field_name,
                        message=validation.get('message') or "Format invalide",
                        code="pattern",
                        value=value
                    )
            except re.error as e:
                logger.warning("invalid_regex_pattern", pattern=pattern, error=str(e))

        # Validation numerique
        if isinstance(value, (int, float)):
            min_val = validation.get('min')
            max_val = validation.get('max')

            if min_val is not None and value < min_val:
                result.add_error(
                    field=field_name,
                    message=validation.get('message') or f"La valeur minimale est {min_val}",
                    code="min_value",
                    value=value
                )

            if max_val is not None and value > max_val:
                result.add_error(
                    field=field_name,
                    message=validation.get('message') or f"La valeur maximale est {max_val}",
                    code="max_value",
                    value=value
                )

        # Validation longueur texte
        if isinstance(value, str):
            min_length = validation.get('minLength') or validation.get('min_length')
            max_length = validation.get('maxLength') or validation.get('max_length')

            if min_length is not None and len(value) < min_length:
                result.add_error(
                    field=field_name,
                    message=validation.get('message') or f"Minimum {min_length} caracteres",
                    code="min_length",
                    value=value
                )

            if max_length is not None and len(value) > max_length:
                result.add_error(
                    field=field_name,
                    message=validation.get('message') or f"Maximum {max_length} caracteres",
                    code="max_length",
                    value=value
                )

        # Validation valeurs autorisees
        allowed = validation.get('allowed_values')
        if allowed and value not in allowed:
            result.add_error(
                field=field_name,
                message=validation.get('message') or f"Valeur non autorisee. Valeurs possibles: {', '.join(map(str, allowed))}",
                code="allowed_values",
                value=value
            )

        return result

    @classmethod
    def _validate_format(cls, format_type: str, value: str) -> Tuple[bool, str]:
        """Valide selon un format predefinit."""
        validator = cls.FORMAT_VALIDATORS.get(format_type.lower())
        if validator:
            return validator(value)

        # Format inconnu - pas d'erreur
        logger.warning("unknown_format_validator", format=format_type)
        return True, ""

    @classmethod
    def validate_record(
        cls,
        module_name: str,
        data: Dict[str, Any],
        champs_config: Optional[List[Dict]] = None
    ) -> ValidationResult:
        """
        Valide un enregistrement complet.

        Args:
            module_name: Nom du module
            data: Donnees a valider
            champs_config: Configuration des champs (depuis YAML)

        Returns:
            ValidationResult avec valid=True/False et liste d'erreurs
        """
        result = ValidationResult(valid=True)

        if not champs_config:
            # Essayer de recuperer depuis le parser
            from .parser import ModuleParser
            module_def = ModuleParser.get_raw(module_name)
            if module_def and 'champs' in module_def:
                champs_config = module_def['champs']

        if not champs_config:
            logger.warning("no_champs_config", module=module_name)
            return result

        # Valider chaque champ
        for champ in champs_config:
            if isinstance(champ, dict) and 'nom' in champ:
                field_name = champ['nom']
                value = data.get(field_name)

                field_result = cls.validate_field(champ, value, field_name)
                result.merge(field_result)

        logger.debug(
            "record_validated",
            module=module_name,
            valid=result.valid,
            error_count=len(result.errors)
        )

        return result

    @classmethod
    async def validate_unique(
        cls,
        module_name: str,
        field_name: str,
        value: Any,
        tenant_id: UUID,
        exclude_id: Optional[UUID] = None
    ) -> ValidationResult:
        """
        Valide l'unicite d'une valeur.

        Args:
            module_name: Nom du module
            field_name: Nom du champ
            value: Valeur a verifier
            tenant_id: ID du tenant
            exclude_id: ID a exclure (pour update)

        Returns:
            ValidationResult
        """
        from .db import Database

        result = ValidationResult(valid=True)

        # Chercher les enregistrements existants avec cette valeur
        filters = {field_name: value}
        existing = Database.query(module_name, tenant_id, filters=filters, limit=1)

        if existing:
            # Verifier si c'est un autre enregistrement
            if exclude_id:
                if str(existing[0].get('id')) != str(exclude_id):
                    result.add_error(
                        field=field_name,
                        message=f"Cette valeur est deja utilisee",
                        code="unique",
                        value=value
                    )
            else:
                result.add_error(
                    field=field_name,
                    message=f"Cette valeur est deja utilisee",
                    code="unique",
                    value=value
                )

        return result


# =============================================================================
# Validation Schemas for UI
# =============================================================================
def get_validation_schema(module_name: str) -> Dict:
    """
    Retourne le schema de validation pour l'UI.
    Format compatible avec les bibliotheques JS de validation.
    """
    from .parser import ModuleParser

    module_def = ModuleParser.get_raw(module_name)
    if not module_def or 'champs' not in module_def:
        return {"fields": {}}

    schema = {"fields": {}}

    for champ in module_def['champs']:
        if isinstance(champ, dict) and 'nom' in champ:
            field_name = champ['nom']
            field_schema = {
                "type": champ.get('type', 'text'),
                "required": champ.get('obligatoire', False) or champ.get('requis', False),
            }

            # Ajouter les regles de validation
            validation = champ.get('validation', {})
            if validation:
                field_schema["validation"] = validation

            # Inferer le format depuis le type
            if champ.get('type') == 'email':
                field_schema.setdefault("validation", {})["format"] = "email"
            elif champ.get('type') in ['tel', 'telephone']:
                field_schema.setdefault("validation", {})["format"] = "phone"
            elif champ.get('type') == 'url':
                field_schema.setdefault("validation", {})["format"] = "url"

            schema["fields"][field_name] = field_schema

    return schema


# =============================================================================
# API Helper Functions
# =============================================================================
def validate_request_data(
    module_name: str,
    data: Dict[str, Any],
    is_update: bool = False,
    existing_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None
) -> ValidationResult:
    """
    Fonction helper pour valider les donnees d'une requete API.

    Args:
        module_name: Nom du module
        data: Donnees a valider
        is_update: True si c'est une mise a jour (champs non requis)
        existing_id: ID existant pour exclure de la verification d'unicite
        tenant_id: ID du tenant pour verification d'unicite

    Returns:
        ValidationResult
    """
    return Validator.validate_record(module_name, data)
