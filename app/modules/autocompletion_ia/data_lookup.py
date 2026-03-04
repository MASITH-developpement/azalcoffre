# AZALPLUS - Lookup multi-sources pour auto-remplissage
"""
APIs intégrées pour l'auto-remplissage intelligent:
- API Adresse (gouv.fr) - Adresses françaises
- Open Food Facts - Produits alimentaires
- VIES - Validation TVA européenne
- OpenStreetMap Nominatim - Géolocalisation
"""

import httpx
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# =============================================================================
# API Adresse (gouv.fr) - Autocomplétion adresses
# =============================================================================
API_ADRESSE_BASE = "https://api-adresse.data.gouv.fr"


async def search_address(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Recherche d'adresses via l'API Adresse du gouvernement français.

    Args:
        query: Texte de recherche (adresse partielle)
        limit: Nombre max de résultats

    Returns:
        Liste d'adresses avec leurs coordonnées
    """
    if len(query) < 3:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_ADRESSE_BASE}/search/",
                params={"q": query, "limit": limit}
            )

            if response.status_code == 200:
                data = response.json()
                return [_parse_adresse(f) for f in data.get("features", [])]

            return []
    except Exception as e:
        logger.error(f"Erreur API Adresse: {e}")
        return []


async def get_city_from_postal_code(code_postal: str) -> Optional[Dict[str, Any]]:
    """
    Récupère la ville à partir d'un code postal.

    Args:
        code_postal: Code postal (5 chiffres)

    Returns:
        Dictionnaire avec ville, département, région
    """
    if len(code_postal) != 5:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_ADRESSE_BASE}/search/",
                params={"q": code_postal, "type": "municipality", "limit": 5}
            )

            if response.status_code == 200:
                data = response.json()
                features = data.get("features", [])

                if features:
                    # Retourner la première correspondance
                    props = features[0].get("properties", {})
                    return {
                        "ville": props.get("city", ""),
                        "code_postal": props.get("postcode", code_postal),
                        "departement": props.get("context", "").split(",")[0] if props.get("context") else "",
                        "region": props.get("context", "").split(",")[-1].strip() if props.get("context") else "",
                        "latitude": features[0].get("geometry", {}).get("coordinates", [None, None])[1],
                        "longitude": features[0].get("geometry", {}).get("coordinates", [None, None])[0],
                    }

            return None
    except Exception as e:
        logger.error(f"Erreur lookup code postal: {e}")
        return None


async def reverse_geocode(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Géocodage inverse: coordonnées → adresse.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_ADRESSE_BASE}/reverse/",
                params={"lat": lat, "lon": lon}
            )

            if response.status_code == 200:
                data = response.json()
                features = data.get("features", [])
                if features:
                    return _parse_adresse(features[0])

            return None
    except Exception as e:
        logger.error(f"Erreur reverse geocode: {e}")
        return None


def _parse_adresse(feature: Dict) -> Dict[str, Any]:
    """Parse une feature GeoJSON de l'API Adresse."""
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [None, None])

    return {
        "adresse_complete": props.get("label", ""),
        "numero": props.get("housenumber", ""),
        "rue": props.get("street", props.get("name", "")),
        "code_postal": props.get("postcode", ""),
        "ville": props.get("city", ""),
        "departement": props.get("context", "").split(",")[0] if props.get("context") else "",
        "longitude": coords[0],
        "latitude": coords[1],
        "score": props.get("score", 0),
    }


# =============================================================================
# Open Food Facts - Produits alimentaires
# =============================================================================
OFF_API_BASE = "https://world.openfoodfacts.org/api/v2"


async def lookup_product_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    """
    Recherche un produit par son code-barres (EAN-13, UPC).

    Args:
        barcode: Code-barres du produit

    Returns:
        Dictionnaire avec les infos produit
    """
    # Nettoyer le code-barres
    barcode = barcode.replace(" ", "").replace("-", "")

    if not barcode.isdigit() or len(barcode) not in [8, 12, 13, 14]:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{OFF_API_BASE}/product/{barcode}.json"
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1:
                    return _parse_product(data.get("product", {}))

            return None
    except Exception as e:
        logger.error(f"Erreur Open Food Facts: {e}")
        return None


async def search_products(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Recherche des produits par nom.
    """
    if len(query) < 2:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{OFF_API_BASE}/search",
                params={
                    "search_terms": query,
                    "page_size": limit,
                    "json": 1
                }
            )

            if response.status_code == 200:
                data = response.json()
                return [_parse_product(p) for p in data.get("products", [])]

            return []
    except Exception as e:
        logger.error(f"Erreur recherche produit: {e}")
        return []


def _parse_product(product: Dict) -> Dict[str, Any]:
    """Parse les données produit d'Open Food Facts."""
    return {
        "code_barres": product.get("code", ""),
        "nom": product.get("product_name_fr", product.get("product_name", "")),
        "marque": product.get("brands", ""),
        "categorie": product.get("categories", ""),
        "quantite": product.get("quantity", ""),
        "nutriscore": product.get("nutriscore_grade", "").upper(),
        "ecoscore": product.get("ecoscore_grade", "").upper(),
        "origine": product.get("origins", ""),
        "image_url": product.get("image_front_url", ""),
        "ingredients": product.get("ingredients_text_fr", product.get("ingredients_text", "")),
        "allergenes": product.get("allergens", ""),
        "labels": product.get("labels", ""),
    }


# =============================================================================
# VIES - Validation TVA européenne
# =============================================================================
VIES_API_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms"


async def validate_vat_number(vat_number: str) -> Optional[Dict[str, Any]]:
    """
    Valide un numéro de TVA européen via VIES.

    Args:
        vat_number: Numéro de TVA (ex: FR12345678901)

    Returns:
        Dictionnaire avec validité et infos entreprise
    """
    # Nettoyer le numéro
    vat_number = vat_number.replace(" ", "").replace(".", "").replace("-", "").upper()

    if len(vat_number) < 4:
        return None

    # Extraire le code pays et le numéro
    country_code = vat_number[:2]
    number = vat_number[2:]

    # Codes pays EU valides
    eu_countries = [
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
        "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI"
    ]

    if country_code not in eu_countries:
        return {"valid": False, "error": "Code pays non EU"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{VIES_API_URL}/{country_code}/vat/{number}"
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "valid": data.get("isValid", False),
                    "numero_tva": f"{country_code}{number}",
                    "pays": country_code,
                    "nom": data.get("name", ""),
                    "adresse": data.get("address", ""),
                    "date_verification": data.get("requestDate", ""),
                }

            return {"valid": False, "error": "Numéro non trouvé"}
    except Exception as e:
        logger.error(f"Erreur VIES: {e}")
        return {"valid": False, "error": str(e)}


# =============================================================================
# Validation IBAN / BIC
# =============================================================================
def validate_iban(iban: str) -> Dict[str, Any]:
    """
    Valide un numéro IBAN et extrait les informations.

    Args:
        iban: Numéro IBAN

    Returns:
        Dictionnaire avec validité et infos bancaires
    """
    # Nettoyer l'IBAN
    iban = iban.replace(" ", "").replace("-", "").upper()

    if len(iban) < 15:
        return {"valid": False, "error": "IBAN trop court"}

    # Extraire les composants
    country_code = iban[:2]
    check_digits = iban[2:4]
    bban = iban[4:]

    # Vérifier le format selon le pays
    iban_lengths = {
        "FR": 27, "DE": 22, "ES": 24, "IT": 27, "BE": 16, "NL": 18,
        "LU": 20, "CH": 21, "GB": 22, "PT": 25, "AT": 20, "IE": 22,
    }

    expected_length = iban_lengths.get(country_code, 0)
    if expected_length and len(iban) != expected_length:
        return {"valid": False, "error": f"Longueur IBAN incorrecte (attendu: {expected_length})"}

    # Validation par modulo 97
    try:
        # Déplacer les 4 premiers caractères à la fin
        rearranged = bban + country_code + check_digits

        # Convertir les lettres en chiffres (A=10, B=11, etc.)
        numeric = ""
        for char in rearranged:
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - 55)

        # Vérifier modulo 97
        is_valid = int(numeric) % 97 == 1

        # Extraire le code banque et code guichet (pour la France)
        bank_info = {}
        if country_code == "FR" and len(bban) >= 10:
            bank_info = {
                "code_banque": bban[:5],
                "code_guichet": bban[5:10],
                "numero_compte": bban[10:-2] if len(bban) > 12 else "",
                "cle_rib": bban[-2:] if len(bban) >= 2 else "",
            }

        return {
            "valid": is_valid,
            "iban_formate": " ".join([iban[i:i+4] for i in range(0, len(iban), 4)]),
            "pays": country_code,
            **bank_info,
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def get_bank_from_bic(bic: str) -> Dict[str, Any]:
    """
    Extrait les informations d'un code BIC/SWIFT.

    Args:
        bic: Code BIC/SWIFT (8 ou 11 caractères)

    Returns:
        Dictionnaire avec les infos bancaires
    """
    bic = bic.replace(" ", "").upper()

    if len(bic) not in [8, 11]:
        return {"valid": False, "error": "BIC doit avoir 8 ou 11 caractères"}

    # Structure BIC: AAAA BB CC DDD
    # AAAA = Code banque
    # BB = Code pays
    # CC = Code localisation
    # DDD = Code branche (optionnel)

    bank_code = bic[:4]
    country_code = bic[4:6]
    location_code = bic[6:8]
    branch_code = bic[8:11] if len(bic) == 11 else "XXX"

    # Mapping des codes banque français courants
    french_banks = {
        "BNPA": "BNP Paribas",
        "SOGEFRPP": "Société Générale",
        "CRLYFRPP": "Crédit Lyonnais (LCL)",
        "CEPAFRPP": "Caisse d'Épargne",
        "CMCIFRPP": "Crédit Mutuel - CIC",
        "AGRIFRPP": "Crédit Agricole",
        "BPCEFRPP": "BPCE (Banque Populaire)",
        "PSSTFRPP": "La Banque Postale",
        "CCBPFRPP": "Banque Populaire",
    }

    bank_name = french_banks.get(bic[:8], french_banks.get(bank_code, ""))

    return {
        "valid": True,
        "bic": bic,
        "code_banque": bank_code,
        "pays": country_code,
        "localisation": location_code,
        "branche": branch_code,
        "nom_banque": bank_name,
    }


# =============================================================================
# API données géographiques (codes INSEE, etc.)
# =============================================================================
GEO_API_BASE = "https://geo.api.gouv.fr"


async def get_communes_by_departement(departement: str) -> List[Dict[str, Any]]:
    """
    Liste les communes d'un département.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{GEO_API_BASE}/departements/{departement}/communes"
            )

            if response.status_code == 200:
                return [
                    {
                        "code_insee": c.get("code", ""),
                        "nom": c.get("nom", ""),
                        "code_postal": c.get("codesPostaux", [""])[0] if c.get("codesPostaux") else "",
                        "population": c.get("population", 0),
                    }
                    for c in response.json()
                ]

            return []
    except Exception as e:
        logger.error(f"Erreur API Geo: {e}")
        return []


async def get_departements() -> List[Dict[str, Any]]:
    """
    Liste tous les départements français.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GEO_API_BASE}/departements")

            if response.status_code == 200:
                return [
                    {
                        "code": d.get("code", ""),
                        "nom": d.get("nom", ""),
                        "code_region": d.get("codeRegion", ""),
                    }
                    for d in response.json()
                ]

            return []
    except Exception as e:
        logger.error(f"Erreur API Geo: {e}")
        return []


async def get_regions() -> List[Dict[str, Any]]:
    """
    Liste toutes les régions françaises.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GEO_API_BASE}/regions")

            if response.status_code == 200:
                return [
                    {
                        "code": r.get("code", ""),
                        "nom": r.get("nom", ""),
                    }
                    for r in response.json()
                ]

            return []
    except Exception as e:
        logger.error(f"Erreur API Geo: {e}")
        return []


# =============================================================================
# Lookup unifié - détection automatique du type de données
# =============================================================================
async def smart_lookup(value: str, field_type: str = None) -> Optional[Dict[str, Any]]:
    """
    Lookup intelligent qui détecte automatiquement le type de données.

    Args:
        value: Valeur à rechercher
        field_type: Type de champ optionnel (siret, siren, iban, code_barres, etc.)

    Returns:
        Dictionnaire avec les données trouvées et le type détecté
    """
    value = value.strip()

    # Détection par type explicite
    if field_type:
        field_type = field_type.lower()

        if field_type in ["siret", "numero_siret"]:
            from . import entreprise_lookup
            data = await entreprise_lookup.lookup_by_siret(value)
            if data:
                return {"type": "entreprise", "source": "api_gouv", "data": data}

        elif field_type in ["siren", "numero_siren"]:
            from . import entreprise_lookup
            data = await entreprise_lookup.lookup_by_siren(value)
            if data:
                return {"type": "entreprise", "source": "api_gouv", "data": data}

        elif field_type in ["tva", "tva_intracommunautaire", "numero_tva", "vat"]:
            data = await validate_vat_number(value)
            if data and data.get("valid"):
                return {"type": "tva", "source": "vies", "data": data}

        elif field_type in ["iban", "numero_iban"]:
            data = validate_iban(value)
            if data.get("valid"):
                return {"type": "iban", "source": "validation", "data": data}

        elif field_type in ["bic", "swift", "code_bic"]:
            data = get_bank_from_bic(value)
            if data.get("valid"):
                return {"type": "bic", "source": "validation", "data": data}

        elif field_type in ["code_barres", "ean", "upc", "barcode"]:
            data = await lookup_product_barcode(value)
            if data:
                return {"type": "produit", "source": "openfoodfacts", "data": data}

        elif field_type in ["code_postal", "cp"]:
            data = await get_city_from_postal_code(value)
            if data:
                return {"type": "adresse", "source": "api_adresse", "data": data}

        elif field_type in ["adresse", "address"]:
            data = await search_address(value, limit=1)
            if data:
                return {"type": "adresse", "source": "api_adresse", "data": data[0]}

    # Détection automatique par le format de la valeur
    clean_value = value.replace(" ", "").replace(".", "").replace("-", "")

    # SIRET (14 chiffres)
    if clean_value.isdigit() and len(clean_value) == 14:
        from . import entreprise_lookup
        data = await entreprise_lookup.lookup_by_siret(clean_value)
        if data:
            return {"type": "entreprise", "source": "api_gouv", "data": data}

    # SIREN (9 chiffres)
    if clean_value.isdigit() and len(clean_value) == 9:
        from . import entreprise_lookup
        data = await entreprise_lookup.lookup_by_siren(clean_value)
        if data:
            return {"type": "entreprise", "source": "api_gouv", "data": data}

    # Code postal français (5 chiffres)
    if clean_value.isdigit() and len(clean_value) == 5:
        data = await get_city_from_postal_code(clean_value)
        if data:
            return {"type": "adresse", "source": "api_adresse", "data": data}

    # TVA intracommunautaire (commence par 2 lettres)
    if len(value) >= 4 and value[:2].isalpha():
        data = await validate_vat_number(value)
        if data and data.get("valid"):
            return {"type": "tva", "source": "vies", "data": data}

    # IBAN (commence par 2 lettres + 2 chiffres)
    if len(clean_value) >= 15 and clean_value[:2].isalpha() and clean_value[2:4].isdigit():
        data = validate_iban(clean_value)
        if data.get("valid"):
            return {"type": "iban", "source": "validation", "data": data}

    # Code-barres (8, 12, 13 ou 14 chiffres)
    if clean_value.isdigit() and len(clean_value) in [8, 12, 13, 14]:
        data = await lookup_product_barcode(clean_value)
        if data:
            return {"type": "produit", "source": "openfoodfacts", "data": data}

    # BIC (8 ou 11 caractères alphanumériques)
    if clean_value.isalnum() and len(clean_value) in [8, 11]:
        data = get_bank_from_bic(clean_value)
        if data.get("valid"):
            return {"type": "bic", "source": "validation", "data": data}

    return None
