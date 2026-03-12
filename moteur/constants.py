# =============================================================================
# AZALPLUS - Constants Loader
# =============================================================================
"""
Charge et expose les constantes depuis config/constants.yml

Usage:
    from moteur.constants import CONSTANTS, get, get_statuts, get_tva

    # Accès direct
    statuts = CONSTANTS["statuts"]["factures"]

    # Accès par chemin (notation pointée)
    tva_normal = get("tva.france.normal")  # 20.0

    # Helpers typés
    statuts = get_statuts("factures")  # ["BROUILLON", "VALIDEE", ...]
    tva = get_tva("france", "normal")  # 20.0
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from functools import lru_cache
import structlog

logger = structlog.get_logger()

# =============================================================================
# Chemins
# =============================================================================
CONFIG_DIR = Path(__file__).parent.parent / "config"
CONSTANTS_FILE = CONFIG_DIR / "constants.yml"

# =============================================================================
# Chargement du fichier YAML
# =============================================================================
def _load_constants() -> Dict[str, Any]:
    """Charge le fichier constants.yml."""
    if not CONSTANTS_FILE.exists():
        logger.error("constants_file_not_found", path=str(CONSTANTS_FILE))
        raise FileNotFoundError(f"Fichier constants.yml introuvable: {CONSTANTS_FILE}")

    with open(CONSTANTS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    logger.info("constants_loaded",
                version=data.get("version", "unknown"),
                sections=list(data.keys()))
    return data

# Instance globale (chargée une seule fois)
CONSTANTS: Dict[str, Any] = _load_constants()

# =============================================================================
# Fonctions d'accès
# =============================================================================
def get(path: str, default: Any = None) -> Any:
    """
    Accès par chemin avec notation pointée.

    Args:
        path: Chemin vers la valeur (ex: "tva.france.normal")
        default: Valeur par défaut si non trouvé

    Returns:
        La valeur ou default

    Examples:
        >>> get("tva.france.normal")
        20.0
        >>> get("statuts.factures")
        ['BROUILLON', 'VALIDEE', 'ENVOYEE', ...]
        >>> get("inexistant", "valeur_defaut")
        'valeur_defaut'
    """
    keys = path.split(".")
    value = CONSTANTS

    try:
        for key in keys:
            if isinstance(value, dict):
                value = value[key]
            elif isinstance(value, list) and key.isdigit():
                value = value[int(key)]
            else:
                return default
        return value
    except (KeyError, IndexError, TypeError):
        return default


def get_or_raise(path: str) -> Any:
    """
    Accès par chemin, lève une exception si non trouvé.

    Args:
        path: Chemin vers la valeur

    Raises:
        KeyError: Si le chemin n'existe pas
    """
    value = get(path, default=KeyError)
    if value is KeyError:
        raise KeyError(f"Constante non trouvée: {path}")
    return value


# =============================================================================
# Helpers spécialisés
# =============================================================================
def get_statuts(module: str) -> List[str]:
    """
    Retourne la liste des statuts pour un module.

    Args:
        module: Nom du module (factures, devis, interventions...)

    Returns:
        Liste des statuts ou statuts génériques si module inconnu

    Examples:
        >>> get_statuts("factures")
        ['BROUILLON', 'VALIDEE', 'ENVOYEE', 'PAYEE', ...]
    """
    statuts = get(f"statuts.{module}")

    if statuts is None:
        return get("statuts.generiques", [])

    # Si c'est un dict avec "valeurs", extraire la liste
    if isinstance(statuts, dict):
        if "valeurs" in statuts:
            return statuts["valeurs"]
        return [s for s in statuts.keys() if s not in ("defaut", "valeurs")]

    return statuts if isinstance(statuts, list) else []


def get_statut_defaut(module: str) -> str:
    """
    Retourne le statut par défaut pour un module.

    Args:
        module: Nom du module

    Returns:
        Statut par défaut ou "BROUILLON"
    """
    statuts = get(f"statuts.{module}")

    if isinstance(statuts, dict) and "defaut" in statuts:
        return statuts["defaut"]

    # Si c'est un dict avec "valeurs", retourne le premier
    if isinstance(statuts, dict) and "valeurs" in statuts:
        valeurs = statuts["valeurs"]
        if valeurs:
            return valeurs[0]

    # Retourne le premier statut ou BROUILLON
    if isinstance(statuts, list) and statuts:
        return statuts[0]

    return "BROUILLON"


def get_couleur_statut(statut: str) -> str:
    """
    Retourne la couleur associée à un statut.

    Args:
        statut: Nom du statut (BROUILLON, PAYEE, etc.)

    Returns:
        Nom de la couleur (primary, success, warning, error, info, gray)
    """
    return get(f"couleurs_statuts.{statut}", "gray")


def get_code_couleur(couleur: str) -> str:
    """
    Retourne le code hexadécimal d'une couleur.

    Args:
        couleur: Nom de la couleur (primary, success, etc.)

    Returns:
        Code hex (#3454D1, #10b981, etc.)
    """
    return get(f"couleurs_statuts._codes.{couleur}", "#6b7280")


def get_tva(pays: str = "france", type_tva: str = "normal") -> float:
    """
    Retourne un taux de TVA.

    Args:
        pays: Code pays (france, belgique, suisse)
        type_tva: Type de TVA (normal, reduit, intermediaire, etc.)

    Returns:
        Taux de TVA (ex: 20.0)
    """
    taux = get(f"tva.{pays}.{type_tva}")
    if taux is None:
        taux = get(f"tva.{pays}.defaut", 20.0)
    return float(taux)


def get_tva_options(pays: str = "france") -> Dict[str, float]:
    """
    Retourne tous les taux de TVA pour un pays.

    Args:
        pays: Code pays

    Returns:
        Dict {type: taux} ex: {"normal": 20.0, "reduit": 5.5}
    """
    tva_pays = get(f"tva.{pays}", {})
    return {k: v for k, v in tva_pays.items() if k not in ("defaut",) and isinstance(v, (int, float))}


def get_devise(code: str = None) -> Dict[str, Any]:
    """
    Retourne les informations d'une devise.

    Args:
        code: Code devise (EUR, USD, GBP) ou None pour la devise par défaut

    Returns:
        Dict avec code, symbole, position, decimales, nom
    """
    if code is None:
        code = get("devises.defaut", "EUR")

    return get(f"devises.{code}", {
        "code": code,
        "symbole": code,
        "position": "after",
        "decimales": 2,
        "nom": code
    })


def get_devises_disponibles() -> List[str]:
    """Retourne la liste des codes devises disponibles."""
    devises = get("devises", {})
    return [k for k in devises.keys() if k not in ("defaut", "base")]


def get_limite(categorie: str, cle: str = None) -> Union[int, Dict[str, Any]]:
    """
    Retourne une limite système.

    Args:
        categorie: Catégorie (pagination, upload, export, etc.)
        cle: Clé spécifique ou None pour toute la catégorie

    Returns:
        Valeur de la limite ou dict de la catégorie

    Examples:
        >>> get_limite("pagination", "max")
        500
        >>> get_limite("upload", "max_taille_mb")
        50
    """
    if cle:
        return get(f"limites.{categorie}.{cle}")
    return get(f"limites.{categorie}", {})


def get_format(type_format: str, variante: str = "affichage") -> str:
    """
    Retourne un format de date/nombre.

    Args:
        type_format: Type (date, heure, datetime, nombre)
        variante: Variante (affichage, stockage, iso, complet)

    Returns:
        Format string
    """
    return get(f"formats.{type_format}.{variante}", "")


def get_message(code: str) -> str:
    """
    Retourne un message système par son code.

    Args:
        code: Code du message (E001, S001, I001, etc.)

    Returns:
        Message ou le code si non trouvé
    """
    # Déterminer la catégorie
    if code.startswith("E"):
        return get(f"messages.erreurs.{code}", code)
    elif code.startswith("S"):
        return get(f"messages.succes.{code}", code)
    elif code.startswith("I"):
        return get(f"messages.info.{code}", code)
    return code


def get_roles() -> Dict[str, Dict[str, Any]]:
    """Retourne tous les rôles avec leurs configurations."""
    return get("roles", {})


def get_role(code: str) -> Dict[str, Any]:
    """Retourne la configuration d'un rôle."""
    return get(f"roles.{code}", {"nom": code, "niveau": 0})


def get_type_champ(type_yaml: str) -> Dict[str, Any]:
    """
    Retourne la configuration d'un type de champ.

    Args:
        type_yaml: Type YAML (texte, nombre, date, relation, etc.)

    Returns:
        Dict avec sql, python, alias, etc.
    """
    # Normaliser le type
    type_lower = type_yaml.lower().replace(" ", "_")

    # Chercher directement
    config = get(f"types_champs.{type_lower}")
    if config:
        return config

    # Chercher dans les alias
    types_champs = get("types_champs", {})
    for type_name, type_config in types_champs.items():
        if isinstance(type_config, dict):
            aliases = type_config.get("alias", [])
            if type_lower in aliases or type_yaml in aliases:
                return type_config

    # Type par défaut
    return get("types_champs.texte", {"sql": "VARCHAR(255)", "python": "str"})


def get_colonnes_systeme() -> List[Dict[str, Any]]:
    """Retourne la liste des colonnes système automatiques."""
    return get("colonnes_systeme", [])


def get_conditions_paiement() -> List[Dict[str, Any]]:
    """Retourne la liste des conditions de paiement."""
    return get("conditions_paiement", [])


def get_condition_paiement(code: str) -> Dict[str, Any]:
    """Retourne une condition de paiement par son code."""
    conditions = get_conditions_paiement()
    for cond in conditions:
        if isinstance(cond, dict) and cond.get("code") == code:
            return cond
    return {"code": code, "nom": code, "jours": 30}


def get_frequences() -> List[Dict[str, Any]]:
    """Retourne la liste des fréquences."""
    return get("frequences", [])


def get_unites(categorie: str = None) -> Union[Dict, List]:
    """
    Retourne les unités de mesure.

    Args:
        categorie: Catégorie (longueur, poids, volume, temps, quantite) ou None pour tout
    """
    if categorie:
        return get(f"unites.{categorie}", [])
    return get("unites", {})


# =============================================================================
# Référence dynamique pour les modules YAML
# =============================================================================
def resolve_reference(ref: str) -> Any:
    """
    Résout une référence de type $chemin.vers.valeur dans les YAML.

    Args:
        ref: Référence commençant par $ (ex: "$statuts.factures")

    Returns:
        Valeur résolue ou la référence originale si non trouvée
    """
    if not ref or not isinstance(ref, str):
        return ref

    if ref.startswith("$"):
        path = ref[1:]  # Enlever le $
        value = get(path)
        if value is not None:
            return value
        logger.warning("reference_not_found", ref=ref)

    return ref


# =============================================================================
# Rechargement (pour développement)
# =============================================================================
def reload_constants() -> None:
    """Recharge les constantes depuis le fichier YAML."""
    global CONSTANTS
    CONSTANTS = _load_constants()
    logger.info("constants_reloaded")


# =============================================================================
# Validation (appelé par validate_constants.py)
# =============================================================================
def validate() -> Dict[str, Any]:
    """
    Valide la structure des constantes.

    Returns:
        Dict avec status, errors, warnings
    """
    errors = []
    warnings = []

    # Vérifier les sections obligatoires
    required_sections = [
        "statuts", "tva", "devises", "limites",
        "types_champs", "colonnes_systeme", "messages"
    ]

    for section in required_sections:
        if section not in CONSTANTS:
            errors.append(f"Section obligatoire manquante: {section}")

    # Vérifier les statuts ont un défaut
    statuts = CONSTANTS.get("statuts", {})
    for module, config in statuts.items():
        if module == "generiques":
            continue
        if isinstance(config, list) and len(config) == 0:
            errors.append(f"statuts.{module} est vide")

    # Vérifier les taux TVA sont des nombres
    tva = CONSTANTS.get("tva", {})
    for pays, taux in tva.items():
        if pays == "defaut":
            continue
        if isinstance(taux, dict):
            for type_tva, valeur in taux.items():
                if type_tva != "defaut" and not isinstance(valeur, (int, float)):
                    errors.append(f"tva.{pays}.{type_tva} doit être un nombre, reçu: {type(valeur)}")

    # Vérifier les limites sont des entiers positifs
    limites = CONSTANTS.get("limites", {})
    for cat, config in limites.items():
        if isinstance(config, dict):
            for key, val in config.items():
                if key in ("min", "max", "defaut") and isinstance(val, int) and val < 0:
                    warnings.append(f"limites.{cat}.{key} est négatif: {val}")

    return {
        "status": "ok" if not errors else "error",
        "errors": errors,
        "warnings": warnings,
        "sections": list(CONSTANTS.keys()),
        "version": CONSTANTS.get("version", "unknown")
    }


# =============================================================================
# Export pour IDE (autocomplétion)
# =============================================================================
# Ces constantes sont exposées pour l'autocomplétion IDE
VERSION = CONSTANTS.get("version", "1.0.0")
STATUTS = CONSTANTS.get("statuts", {})
TVA = CONSTANTS.get("tva", {})
DEVISES = CONSTANTS.get("devises", {})
LIMITES = CONSTANTS.get("limites", {})
TYPES_CHAMPS = CONSTANTS.get("types_champs", {})
COLONNES_SYSTEME = CONSTANTS.get("colonnes_systeme", [])
MESSAGES = CONSTANTS.get("messages", {})
ROLES = CONSTANTS.get("roles", {})
FORMATS = CONSTANTS.get("formats", {})
