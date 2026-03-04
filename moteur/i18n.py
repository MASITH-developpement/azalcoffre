# =============================================================================
# AZALPLUS - Internationalization (i18n) Module
# =============================================================================
"""
Module de gestion des traductions multi-langues.
Supporte le francais (defaut), l'anglais et l'espagnol.

Usage:
    from moteur.i18n import I18n, t, set_language, get_language

    # Obtenir une traduction
    t("common.save")  # "Enregistrer" (fr) / "Save" (en) / "Guardar" (es)

    # Changer la langue
    set_language("en")

    # Obtenir la langue courante
    get_language()  # "en"
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from contextvars import ContextVar
import yaml
import structlog

logger = structlog.get_logger()

# =============================================================================
# Context Variables (thread-safe / async-safe)
# =============================================================================
_current_language: ContextVar[str] = ContextVar('current_language', default='fr')

# =============================================================================
# Constantes
# =============================================================================
DEFAULT_LANGUAGE = "fr"
SUPPORTED_LANGUAGES = ["fr", "en", "es"]
I18N_DIR = Path(__file__).parent.parent / "config" / "i18n"

# =============================================================================
# Cache des traductions
# =============================================================================
_translations_cache: Dict[str, Dict] = {}
_translations_mtime: Dict[str, float] = {}


# =============================================================================
# Classe I18n
# =============================================================================
class I18n:
    """
    Gestionnaire de traductions multi-langues.

    Attributs:
        current_lang: Langue courante (code ISO)
        translations: Cache des traductions chargees

    Exemple:
        i18n = I18n()
        i18n.set_language("en")
        print(i18n.t("common.save"))  # "Save"
    """

    def __init__(self, language: str = DEFAULT_LANGUAGE):
        """
        Initialise le gestionnaire i18n.

        Args:
            language: Code de langue initial (fr, en, es)
        """
        self._language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        self._load_translations(self._language)

    @property
    def current_language(self) -> str:
        """Retourne le code de la langue courante."""
        return self._language

    @property
    def available_languages(self) -> List[Dict[str, str]]:
        """
        Retourne la liste des langues disponibles.

        Returns:
            Liste de dictionnaires avec code, nom et nom natif
        """
        languages = []
        for lang_code in SUPPORTED_LANGUAGES:
            translations = self._load_translations(lang_code)
            meta = translations.get("meta", {})
            languages.append({
                "code": lang_code,
                "name": meta.get("name", lang_code),
                "native_name": meta.get("native_name", lang_code),
                "direction": meta.get("direction", "ltr")
            })
        return languages

    def _load_translations(self, lang: str) -> Dict:
        """
        Charge les traductions depuis le fichier YAML.

        Args:
            lang: Code de langue

        Returns:
            Dictionnaire des traductions
        """
        global _translations_cache, _translations_mtime

        # Verifier le cache
        file_path = I18N_DIR / f"{lang}.yml"

        if not file_path.exists():
            logger.warning("i18n_file_not_found", lang=lang, path=str(file_path))
            # Fallback sur la langue par defaut
            if lang != DEFAULT_LANGUAGE:
                return self._load_translations(DEFAULT_LANGUAGE)
            return {}

        # Verifier si le fichier a ete modifie
        current_mtime = file_path.stat().st_mtime

        if lang in _translations_cache and _translations_mtime.get(lang, 0) >= current_mtime:
            return _translations_cache[lang]

        # Charger et mettre en cache
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                translations = yaml.safe_load(f) or {}
                _translations_cache[lang] = translations
                _translations_mtime[lang] = current_mtime
                logger.debug("i18n_loaded", lang=lang)
                return translations
        except Exception as e:
            logger.error("i18n_load_error", lang=lang, error=str(e))
            return {}

    def set_language(self, lang: str) -> bool:
        """
        Change la langue courante.

        Args:
            lang: Code de langue (fr, en, es)

        Returns:
            True si la langue a ete changee, False sinon
        """
        if lang not in SUPPORTED_LANGUAGES:
            logger.warning("i18n_unsupported_language", lang=lang)
            return False

        self._language = lang
        self._load_translations(lang)
        _current_language.set(lang)

        logger.info("i18n_language_changed", lang=lang)
        return True

    def get_language(self) -> str:
        """
        Retourne le code de la langue courante.

        Returns:
            Code de langue (fr, en, es)
        """
        return self._language

    def t(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """
        Recupere une traduction par sa cle.

        Args:
            key: Cle de traduction (ex: "common.save", "messages.error")
            default: Valeur par defaut si la cle n'existe pas
            **kwargs: Variables a interpoler dans la traduction

        Returns:
            Traduction ou valeur par defaut

        Exemple:
            t("common.save")  # "Enregistrer"
            t("messages.hello", name="Jean")  # "Bonjour Jean" (si defini)
        """
        translations = self._load_translations(self._language)

        # Parcourir la cle (ex: "common.save" -> translations["common"]["save"])
        value = translations
        for part in key.split('.'):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                # Cle non trouvee - fallback sur langue par defaut
                if self._language != DEFAULT_LANGUAGE:
                    fallback_translations = self._load_translations(DEFAULT_LANGUAGE)
                    value = fallback_translations
                    for part2 in key.split('.'):
                        if isinstance(value, dict) and part2 in value:
                            value = value[part2]
                        else:
                            return default if default is not None else key
                else:
                    return default if default is not None else key

        # Interpolation des variables
        if isinstance(value, str) and kwargs:
            try:
                value = value.format(**kwargs)
            except KeyError:
                pass

        return value if isinstance(value, str) else (default if default is not None else key)

    def get_meta(self, key: str, default: Any = None) -> Any:
        """
        Recupere une metadonnee de la langue courante.

        Args:
            key: Cle de metadonnee (ex: "date_format", "currency_format")
            default: Valeur par defaut

        Returns:
            Valeur de la metadonnee
        """
        translations = self._load_translations(self._language)
        meta = translations.get("meta", {})
        return meta.get(key, default)

    def format_date(self, date_obj, format_type: str = "date") -> str:
        """
        Formate une date selon la locale courante.

        Args:
            date_obj: Objet date/datetime
            format_type: Type de format ("date", "datetime")

        Returns:
            Date formatee
        """
        from datetime import datetime, date

        if date_obj is None:
            return ""

        if isinstance(date_obj, str):
            try:
                date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            except ValueError:
                return date_obj

        fmt_key = "datetime_format" if format_type == "datetime" else "date_format"
        fmt = self.get_meta(fmt_key, "DD/MM/YYYY")

        # Convertir le format AZALPLUS vers Python strftime
        fmt = fmt.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
        fmt = fmt.replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")

        if isinstance(date_obj, (datetime, date)):
            return date_obj.strftime(fmt)

        return str(date_obj)

    def format_currency(self, amount: float, currency: str = "EUR") -> str:
        """
        Formate un montant selon la locale courante.

        Args:
            amount: Montant a formater
            currency: Code devise (par defaut EUR)

        Returns:
            Montant formate
        """
        if amount is None:
            amount = 0

        decimal_sep = self.get_meta("decimal_separator", ",")
        thousands_sep = self.get_meta("thousands_separator", " ")

        # Formater le nombre
        try:
            formatted = f"{float(amount):,.2f}"
            # Remplacer les separateurs
            formatted = formatted.replace(",", "TEMP")
            formatted = formatted.replace(".", decimal_sep)
            formatted = formatted.replace("TEMP", thousands_sep)
        except (ValueError, TypeError):
            formatted = "0" + decimal_sep + "00"

        # Appliquer le format de devise
        currency_format = self.get_meta("currency_format", "{amount} EUR")
        return currency_format.format(amount=formatted)

    def reload(self):
        """Force le rechargement des traductions."""
        global _translations_cache, _translations_mtime
        _translations_cache = {}
        _translations_mtime = {}
        self._load_translations(self._language)
        logger.info("i18n_reloaded")


# =============================================================================
# Instance globale
# =============================================================================
_global_i18n: Optional[I18n] = None


def _get_i18n() -> I18n:
    """Retourne l'instance globale i18n."""
    global _global_i18n
    if _global_i18n is None:
        _global_i18n = I18n(_current_language.get())
    return _global_i18n


# =============================================================================
# Fonctions raccourcis
# =============================================================================
def t(key: str, default: Optional[str] = None, **kwargs) -> str:
    """
    Raccourci pour obtenir une traduction.

    Args:
        key: Cle de traduction (ex: "common.save")
        default: Valeur par defaut si non trouve
        **kwargs: Variables a interpoler

    Returns:
        Traduction

    Exemple:
        from moteur.i18n import t
        save_text = t("common.save")  # "Enregistrer" (fr)
    """
    return _get_i18n().t(key, default, **kwargs)


def set_language(lang: str) -> bool:
    """
    Change la langue globale.

    Args:
        lang: Code de langue (fr, en, es)

    Returns:
        True si change, False sinon
    """
    result = _get_i18n().set_language(lang)
    if result:
        _current_language.set(lang)
    return result


def get_language() -> str:
    """
    Retourne la langue courante.

    Returns:
        Code de langue
    """
    return _get_i18n().get_language()


def get_available_languages() -> List[Dict[str, str]]:
    """
    Retourne les langues disponibles.

    Returns:
        Liste de langues avec code, nom, nom natif
    """
    return _get_i18n().available_languages


def format_date(date_obj, format_type: str = "date") -> str:
    """
    Formate une date selon la locale.

    Args:
        date_obj: Date a formater
        format_type: "date" ou "datetime"

    Returns:
        Date formatee
    """
    return _get_i18n().format_date(date_obj, format_type)


def format_currency(amount: float, currency: str = "EUR") -> str:
    """
    Formate un montant selon la locale.

    Args:
        amount: Montant
        currency: Code devise

    Returns:
        Montant formate
    """
    return _get_i18n().format_currency(amount, currency)


def reload_translations():
    """Force le rechargement des traductions."""
    _get_i18n().reload()


# =============================================================================
# Context manager pour langue temporaire
# =============================================================================
class temporary_language:
    """
    Context manager pour changer temporairement la langue.

    Exemple:
        with temporary_language("en"):
            print(t("common.save"))  # "Save"
        print(t("common.save"))  # "Enregistrer" (retour au francais)
    """

    def __init__(self, lang: str):
        self.new_lang = lang
        self.old_lang = None

    def __enter__(self):
        self.old_lang = get_language()
        set_language(self.new_lang)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.old_lang:
            set_language(self.old_lang)
        return False


# =============================================================================
# Middleware FastAPI pour langue automatique
# =============================================================================
def get_language_from_request(request) -> str:
    """
    Determine la langue depuis une requete HTTP.

    Priorite:
    1. Query param ?lang=XX
    2. Cookie 'language'
    3. Header Accept-Language
    4. Langue par defaut (fr)

    Args:
        request: Objet Request FastAPI

    Returns:
        Code de langue
    """
    # 1. Query param
    lang = request.query_params.get('lang')
    if lang and lang in SUPPORTED_LANGUAGES:
        return lang

    # 2. Cookie
    lang = request.cookies.get('language')
    if lang and lang in SUPPORTED_LANGUAGES:
        return lang

    # 3. Accept-Language header
    accept_lang = request.headers.get('Accept-Language', '')
    for lang_code in SUPPORTED_LANGUAGES:
        if lang_code in accept_lang.lower():
            return lang_code

    # 4. Default
    return DEFAULT_LANGUAGE


# =============================================================================
# Chargement initial
# =============================================================================
# Precharger les traductions au demarrage
def preload_translations():
    """Precharge toutes les traductions en cache."""
    for lang in SUPPORTED_LANGUAGES:
        I18n(lang)
    logger.info("i18n_preloaded", languages=SUPPORTED_LANGUAGES)


# =============================================================================
# Export
# =============================================================================
__all__ = [
    'I18n',
    't',
    'set_language',
    'get_language',
    'get_available_languages',
    'format_date',
    'format_currency',
    'reload_translations',
    'temporary_language',
    'get_language_from_request',
    'preload_translations',
    'DEFAULT_LANGUAGE',
    'SUPPORTED_LANGUAGES',
]
