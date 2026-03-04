# =============================================================================
# AZALPLUS - Currency Service
# =============================================================================
"""
Service de gestion multi-devises.
Conversion, formatage et mise a jour des taux de change.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from datetime import datetime
import structlog
import httpx

from .config import settings
from .db import Database

logger = structlog.get_logger()

# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class Currency:
    """Representation d'une devise."""
    code: str
    nom: str
    symbole: str
    taux: Decimal
    decimales: int = 2
    position_symbole: str = "APRES"  # AVANT ou APRES
    separateur_milliers: str = " "
    separateur_decimal: str = ","
    actif: bool = True
    date_maj_taux: Optional[datetime] = None


# =============================================================================
# Default Currencies (fallback)
# =============================================================================
DEFAULT_CURRENCIES: Dict[str, Currency] = {
    "EUR": Currency(
        code="EUR",
        nom="Euro",
        symbole="\u20ac",
        taux=Decimal("1.0"),
        decimales=2,
        position_symbole="APRES"
    ),
    "USD": Currency(
        code="USD",
        nom="Dollar americain",
        symbole="$",
        taux=Decimal("1.08"),
        decimales=2,
        position_symbole="AVANT"
    ),
    "GBP": Currency(
        code="GBP",
        nom="Livre sterling",
        symbole="\u00a3",
        taux=Decimal("0.86"),
        decimales=2,
        position_symbole="AVANT"
    ),
    "CHF": Currency(
        code="CHF",
        nom="Franc suisse",
        symbole="CHF",
        taux=Decimal("0.97"),
        decimales=2,
        position_symbole="APRES"
    ),
    "CAD": Currency(
        code="CAD",
        nom="Dollar canadien",
        symbole="CA$",
        taux=Decimal("1.47"),
        decimales=2,
        position_symbole="AVANT"
    ),
    "JPY": Currency(
        code="JPY",
        nom="Yen japonais",
        symbole="\u00a5",
        taux=Decimal("162.50"),
        decimales=0,
        position_symbole="AVANT"
    ),
    "MAD": Currency(
        code="MAD",
        nom="Dirham marocain",
        symbole="DH",
        taux=Decimal("10.85"),
        decimales=2,
        position_symbole="APRES"
    ),
    "XOF": Currency(
        code="XOF",
        nom="Franc CFA (BCEAO)",
        symbole="FCFA",
        taux=Decimal("655.957"),
        decimales=0,
        position_symbole="APRES"
    ),
    "TND": Currency(
        code="TND",
        nom="Dinar tunisien",
        symbole="DT",
        taux=Decimal("3.35"),
        decimales=3,
        position_symbole="APRES"
    ),
    "DZD": Currency(
        code="DZD",
        nom="Dinar algerien",
        symbole="DA",
        taux=Decimal("145.50"),
        decimales=2,
        position_symbole="APRES"
    ),
}

# Base currency for the system
BASE_CURRENCY = "EUR"


# =============================================================================
# Currency Service
# =============================================================================
class CurrencyService:
    """
    Service de gestion des devises.

    Responsabilites:
    - Conversion entre devises
    - Formatage des montants
    - Mise a jour des taux de change (optionnel)
    """

    _instance: Optional["CurrencyService"] = None
    _currencies: Dict[str, Currency] = {}
    _base_currency: str = BASE_CURRENCY

    def __new__(cls) -> "CurrencyService":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialise le service (une seule fois)."""
        if self._initialized:
            return

        self._currencies = DEFAULT_CURRENCIES.copy()
        self._initialized = True
        logger.info("currency_service_initialized", base=self._base_currency)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def convert(
        self,
        amount: Union[Decimal, float, int, str],
        from_currency: str,
        to_currency: str,
        rate_override: Optional[Decimal] = None
    ) -> Decimal:
        """
        Convertit un montant d'une devise vers une autre.

        Args:
            amount: Montant a convertir
            from_currency: Code devise source (ex: "USD")
            to_currency: Code devise cible (ex: "EUR")
            rate_override: Taux personnalise (optionnel, pour historique)

        Returns:
            Montant converti en Decimal

        Raises:
            ValueError: Si une devise est inconnue
        """
        # Normaliser le montant
        amount = self._to_decimal(amount)

        # Meme devise = pas de conversion
        if from_currency == to_currency:
            return amount

        # Recuperer les devises
        from_curr = self.get_currency(from_currency)
        to_curr = self.get_currency(to_currency)

        if not from_curr:
            raise ValueError(f"Devise inconnue: {from_currency}")
        if not to_curr:
            raise ValueError(f"Devise inconnue: {to_currency}")

        # Conversion via la devise de base
        # Montant en devise base = montant / taux_source
        # Montant en devise cible = montant_base * taux_cible

        if rate_override is not None:
            # Utiliser le taux personnalise (conversion directe)
            result = amount * rate_override
        else:
            # Conversion via EUR (devise de base)
            amount_in_base = amount / from_curr.taux
            result = amount_in_base * to_curr.taux

        # Arrondir selon les decimales de la devise cible
        return self._round_amount(result, to_curr.decimales)

    def convert_to_base(
        self,
        amount: Union[Decimal, float, int, str],
        from_currency: str,
        rate_override: Optional[Decimal] = None
    ) -> Decimal:
        """
        Convertit un montant vers la devise de base (EUR).

        Args:
            amount: Montant a convertir
            from_currency: Code devise source
            rate_override: Taux personnalise (optionnel)

        Returns:
            Montant en devise de base
        """
        return self.convert(amount, from_currency, self._base_currency, rate_override)

    def convert_from_base(
        self,
        amount: Union[Decimal, float, int, str],
        to_currency: str,
        rate_override: Optional[Decimal] = None
    ) -> Decimal:
        """
        Convertit un montant depuis la devise de base (EUR).

        Args:
            amount: Montant en devise de base
            to_currency: Code devise cible
            rate_override: Taux personnalise (optionnel)

        Returns:
            Montant en devise cible
        """
        return self.convert(amount, self._base_currency, to_currency, rate_override)

    def format_amount(
        self,
        amount: Union[Decimal, float, int, str],
        currency: str,
        show_symbol: bool = True,
        show_code: bool = False
    ) -> str:
        """
        Formate un montant avec le symbole de la devise.

        Args:
            amount: Montant a formater
            currency: Code devise
            show_symbol: Afficher le symbole (defaut: True)
            show_code: Afficher le code ISO (defaut: False)

        Returns:
            Montant formate (ex: "1 234,56 EUR" ou "1 234,56 eur")
        """
        curr = self.get_currency(currency)
        if not curr:
            curr = DEFAULT_CURRENCIES.get(self._base_currency)

        # Normaliser et arrondir
        amount = self._to_decimal(amount)
        amount = self._round_amount(amount, curr.decimales)

        # Formater le nombre
        formatted = self._format_number(
            amount,
            curr.decimales,
            curr.separateur_decimal,
            curr.separateur_milliers
        )

        # Ajouter symbole/code
        if show_symbol and show_code:
            suffix = f"{curr.symbole} ({curr.code})"
        elif show_symbol:
            suffix = curr.symbole
        elif show_code:
            suffix = curr.code
        else:
            return formatted

        # Position du symbole
        if curr.position_symbole == "AVANT":
            return f"{suffix}{formatted}"
        else:
            return f"{formatted} {suffix}"

    def get_currency(self, code: str) -> Optional[Currency]:
        """
        Recupere une devise par son code.

        Args:
            code: Code ISO de la devise (ex: "EUR", "USD")

        Returns:
            Objet Currency ou None si non trouve
        """
        return self._currencies.get(code.upper())

    def get_rate(self, currency: str) -> Optional[Decimal]:
        """
        Recupere le taux de change d'une devise par rapport a la base (EUR).

        Args:
            currency: Code devise

        Returns:
            Taux de change ou None
        """
        curr = self.get_currency(currency)
        return curr.taux if curr else None

    def get_all_currencies(self, active_only: bool = True) -> List[Currency]:
        """
        Recupere toutes les devises.

        Args:
            active_only: Ne retourner que les devises actives

        Returns:
            Liste des devises
        """
        currencies = list(self._currencies.values())
        if active_only:
            currencies = [c for c in currencies if c.actif]
        return sorted(currencies, key=lambda c: c.code)

    def get_base_currency(self) -> str:
        """Retourne le code de la devise de base."""
        return self._base_currency

    def set_rate(self, currency: str, rate: Union[Decimal, float, str]) -> bool:
        """
        Met a jour le taux de change d'une devise.

        Args:
            currency: Code devise
            rate: Nouveau taux

        Returns:
            True si mis a jour, False si devise inconnue
        """
        curr = self.get_currency(currency)
        if not curr:
            return False

        curr.taux = self._to_decimal(rate)
        curr.date_maj_taux = datetime.utcnow()

        logger.info("currency_rate_updated", currency=currency, rate=str(curr.taux))
        return True

    def add_currency(self, currency: Currency) -> None:
        """
        Ajoute une nouvelle devise.

        Args:
            currency: Objet Currency a ajouter
        """
        self._currencies[currency.code.upper()] = currency
        logger.info("currency_added", code=currency.code)

    # -------------------------------------------------------------------------
    # Rate Updates (Optional - External API)
    # -------------------------------------------------------------------------

    async def update_rates(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Met a jour les taux de change depuis une API externe.

        Utilise l'API gratuite de exchangerate-api.com ou frankfurter.app.

        Args:
            api_key: Cle API (optionnel pour les APIs gratuites)

        Returns:
            Dict avec les taux mis a jour et le statut
        """
        result = {
            "success": False,
            "updated": [],
            "errors": [],
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            # Utiliser Frankfurter (gratuit, sans cle API)
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Recuperer tous les taux par rapport a EUR
                response = await client.get(
                    "https://api.frankfurter.app/latest",
                    params={"from": "EUR"}
                )

                if response.status_code != 200:
                    result["errors"].append(f"API error: {response.status_code}")
                    return result

                data = response.json()
                rates = data.get("rates", {})

                # Mettre a jour les devises connues
                for code, rate in rates.items():
                    if code in self._currencies:
                        old_rate = self._currencies[code].taux
                        self._currencies[code].taux = Decimal(str(rate))
                        self._currencies[code].date_maj_taux = datetime.utcnow()
                        result["updated"].append({
                            "code": code,
                            "old_rate": str(old_rate),
                            "new_rate": str(rate)
                        })

                result["success"] = True
                logger.info(
                    "currency_rates_updated",
                    count=len(result["updated"]),
                    source="frankfurter"
                )

        except httpx.TimeoutException:
            result["errors"].append("API timeout")
            logger.warning("currency_api_timeout")
        except Exception as e:
            result["errors"].append(str(e))
            logger.error("currency_api_error", error=str(e))

        return result

    # -------------------------------------------------------------------------
    # Database Integration
    # -------------------------------------------------------------------------

    async def load_from_database(self, tenant_id: str) -> int:
        """
        Charge les devises depuis la base de donnees.

        Args:
            tenant_id: ID du tenant

        Returns:
            Nombre de devises chargees
        """
        try:
            # Requete vers le module Devises
            currencies = Database.query("Devise", tenant_id, limit=100)

            count = 0
            for row in currencies:
                currency = Currency(
                    code=row.get("code", "").upper(),
                    nom=row.get("nom", ""),
                    symbole=row.get("symbole", row.get("code", "")),
                    taux=Decimal(str(row.get("taux", 1.0))),
                    decimales=int(row.get("decimales", 2)),
                    position_symbole=row.get("position_symbole", "APRES"),
                    separateur_milliers=row.get("separateur_milliers", " "),
                    separateur_decimal=row.get("separateur_decimal", ","),
                    actif=row.get("actif", True),
                    date_maj_taux=row.get("date_maj_taux")
                )
                self._currencies[currency.code] = currency
                count += 1

            logger.info("currencies_loaded_from_db", count=count, tenant=tenant_id)
            return count

        except Exception as e:
            logger.warning("currencies_load_failed", error=str(e))
            # Fallback sur les devises par defaut
            return 0

    async def save_to_database(self, tenant_id: str, currency: Currency) -> bool:
        """
        Sauvegarde une devise en base de donnees.

        Args:
            tenant_id: ID du tenant
            currency: Devise a sauvegarder

        Returns:
            True si succes
        """
        try:
            data = {
                "code": currency.code,
                "nom": currency.nom,
                "symbole": currency.symbole,
                "taux": float(currency.taux),
                "decimales": currency.decimales,
                "position_symbole": currency.position_symbole,
                "separateur_milliers": currency.separateur_milliers,
                "separateur_decimal": currency.separateur_decimal,
                "actif": currency.actif,
                "date_maj_taux": currency.date_maj_taux
            }

            # Upsert: update si existe, sinon create
            existing = Database.query(
                "Devise",
                tenant_id,
                filters={"code": currency.code},
                limit=1
            )

            if existing:
                Database.update("Devise", tenant_id, existing[0]["id"], data)
            else:
                Database.create("Devise", tenant_id, data)

            return True

        except Exception as e:
            logger.error("currency_save_failed", code=currency.code, error=str(e))
            return False

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _to_decimal(self, value: Union[Decimal, float, int, str]) -> Decimal:
        """Convertit une valeur en Decimal."""
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _round_amount(self, amount: Decimal, decimals: int) -> Decimal:
        """Arrondit un montant selon le nombre de decimales."""
        quantize_str = "0." + "0" * decimals if decimals > 0 else "1"
        return amount.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)

    def _format_number(
        self,
        amount: Decimal,
        decimals: int,
        decimal_sep: str,
        thousands_sep: str
    ) -> str:
        """Formate un nombre avec separateurs."""
        # Separer partie entiere et decimale
        sign = "-" if amount < 0 else ""
        amount = abs(amount)

        if decimals > 0:
            str_amount = f"{amount:.{decimals}f}"
            integer_part, decimal_part = str_amount.split(".")
        else:
            integer_part = str(int(amount))
            decimal_part = ""

        # Ajouter separateurs de milliers
        formatted_integer = ""
        for i, digit in enumerate(reversed(integer_part)):
            if i > 0 and i % 3 == 0:
                formatted_integer = thousands_sep + formatted_integer
            formatted_integer = digit + formatted_integer

        # Assembler
        if decimal_part:
            return f"{sign}{formatted_integer}{decimal_sep}{decimal_part}"
        return f"{sign}{formatted_integer}"


# =============================================================================
# Global Instance
# =============================================================================
currency_service = CurrencyService()


# =============================================================================
# Convenience Functions (Module-level)
# =============================================================================
def convert(
    amount: Union[Decimal, float, int, str],
    from_currency: str,
    to_currency: str
) -> Decimal:
    """Raccourci pour currency_service.convert()."""
    return currency_service.convert(amount, from_currency, to_currency)


def format_amount(
    amount: Union[Decimal, float, int, str],
    currency: str,
    show_symbol: bool = True
) -> str:
    """Raccourci pour currency_service.format_amount()."""
    return currency_service.format_amount(amount, currency, show_symbol)


def get_rate(currency: str) -> Optional[Decimal]:
    """Raccourci pour currency_service.get_rate()."""
    return currency_service.get_rate(currency)


def convert_to_base(
    amount: Union[Decimal, float, int, str],
    from_currency: str
) -> Decimal:
    """Raccourci pour currency_service.convert_to_base()."""
    return currency_service.convert_to_base(amount, from_currency)
