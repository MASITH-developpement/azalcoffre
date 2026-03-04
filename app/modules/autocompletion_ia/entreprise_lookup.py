# AZALPLUS - Recherche d'entreprise par SIRET/SIREN
"""
Utilise l'API gouvernementale française pour récupérer les informations d'entreprise.
API: https://recherche-entreprises.api.gouv.fr
"""

import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

API_BASE = "https://recherche-entreprises.api.gouv.fr"


async def lookup_by_siret(siret: str) -> Optional[Dict[str, Any]]:
    """
    Recherche une entreprise par son numéro SIRET.

    Args:
        siret: Numéro SIRET (14 chiffres)

    Returns:
        Dictionnaire avec les informations de l'entreprise ou None
    """
    # Nettoyer le SIRET (enlever espaces)
    siret = siret.replace(" ", "").replace(".", "")

    if len(siret) != 14:
        logger.warning(f"SIRET invalide: {siret}")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE}/search",
                params={"q": siret, "per_page": 1}
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("results") and len(data["results"]) > 0:
                    return _parse_entreprise(data["results"][0])

            logger.warning(f"Entreprise non trouvée pour SIRET: {siret}")
            return None

    except Exception as e:
        logger.error(f"Erreur lookup SIRET: {e}")
        return None


async def lookup_by_siren(siren: str) -> Optional[Dict[str, Any]]:
    """
    Recherche une entreprise par son numéro SIREN.

    Args:
        siren: Numéro SIREN (9 chiffres)

    Returns:
        Dictionnaire avec les informations de l'entreprise ou None
    """
    siren = siren.replace(" ", "").replace(".", "")

    if len(siren) != 9:
        logger.warning(f"SIREN invalide: {siren}")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE}/search",
                params={"q": siren, "per_page": 1}
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("results") and len(data["results"]) > 0:
                    return _parse_entreprise(data["results"][0])

            return None

    except Exception as e:
        logger.error(f"Erreur lookup SIREN: {e}")
        return None


async def search_by_name(name: str, limit: int = 5) -> list[Dict[str, Any]]:
    """
    Recherche des entreprises par nom.

    Args:
        name: Nom ou partie du nom de l'entreprise
        limit: Nombre max de résultats

    Returns:
        Liste d'entreprises correspondantes
    """
    if len(name) < 3:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE}/search",
                params={"q": name, "per_page": limit}
            )

            if response.status_code == 200:
                data = response.json()
                return [_parse_entreprise(r) for r in data.get("results", [])]

            return []

    except Exception as e:
        logger.error(f"Erreur recherche entreprise: {e}")
        return []


def _parse_entreprise(data: Dict) -> Dict[str, Any]:
    """Parse les données brutes de l'API en format utilisable."""

    # Siège social
    siege = data.get("siege", {})

    # Construire l'adresse
    adresse_parts = []
    if siege.get("numero_voie"):
        adresse_parts.append(siege["numero_voie"])
    if siege.get("type_voie"):
        adresse_parts.append(siege["type_voie"])
    if siege.get("libelle_voie"):
        adresse_parts.append(siege["libelle_voie"])

    adresse = " ".join(adresse_parts) if adresse_parts else ""

    # Extraire le SIREN du SIRET
    siret = siege.get("siret", "")
    siren = siret[:9] if len(siret) >= 9 else data.get("siren", "")

    # Construire le numéro TVA intracommunautaire (FR + clé + SIREN)
    tva_intra = ""
    if siren and len(siren) == 9:
        # Calcul de la clé TVA française
        try:
            cle = (12 + 3 * (int(siren) % 97)) % 97
            tva_intra = f"FR{cle:02d}{siren}"
        except:
            pass

    return {
        "nom": data.get("nom_complet") or "",
        "raison_sociale": data.get("nom_raison_sociale") or "",
        "siret": siret or "",
        "siren": siren or "",
        "tva_intracommunautaire": tva_intra or "",
        "code_naf": data.get("activite_principale") or "",
        "forme_juridique": _get_forme_juridique(data.get("nature_juridique") or ""),
        "adresse": adresse or "",
        "complement_adresse": siege.get("complement_adresse") or "",
        "code_postal": siege.get("code_postal") or "",
        "ville": siege.get("libelle_commune") or "",
        "pays": "France",
        "date_creation": data.get("date_creation") or "",
        "effectif": str(data.get("tranche_effectif_salarie") or ""),
        "categorie_entreprise": data.get("categorie_entreprise") or "",
    }


def _get_forme_juridique(code: str) -> str:
    """Convertit le code de nature juridique en forme juridique lisible."""
    formes = {
        "1000": "EI",
        "5410": "SARL",
        "5485": "SARL",
        "5498": "SARL",
        "5499": "SARL",
        "5505": "SA",
        "5510": "SA",
        "5515": "SA",
        "5520": "SA",
        "5522": "SA",
        "5525": "SA",
        "5530": "SA",
        "5531": "SA",
        "5532": "SA",
        "5535": "SA",
        "5538": "SA",
        "5539": "SA",
        "5540": "SA",
        "5543": "SA",
        "5546": "SA",
        "5547": "SA",
        "5548": "SA",
        "5551": "SA",
        "5552": "SA",
        "5553": "SA",
        "5554": "SA",
        "5555": "SA",
        "5558": "SA",
        "5559": "SA",
        "5560": "SA",
        "5570": "SAS",
        "5585": "SAS",
        "5599": "SAS",
        "5610": "SCI",
        "5615": "SCI",
        "5620": "SCI",
        "5631": "SNC",
        "5632": "SNC",
        "5642": "SCS",
        "5643": "SCA",
        "5646": "SCA",
        "5647": "SCA",
        "5649": "SCA",
        "5699": "AUTRE",
        "5710": "SAS",
        "5720": "SASU",
        "5785": "SAS",
        "5800": "SCI",
        "6100": "SCI",
        "6210": "EURL",
        "6220": "EURL",
        "6316": "SCOP",
        "6317": "SCOP",
        "6318": "SCOP",
        "6411": "SARL",
        "6521": "SCI",
        "6532": "SCI",
        "6533": "SCI",
        "6534": "SCI",
        "6535": "SCI",
        "6539": "SCI",
        "6540": "SCI",
        "6541": "SCI",
        "6542": "SCI",
        "6543": "SCI",
        "6544": "SCI",
        "6551": "SCI",
        "6554": "SCI",
        "6558": "SCI",
        "6560": "SCI",
        "6561": "SCI",
        "6562": "SCI",
        "6563": "SCI",
        "6564": "SCI",
        "6565": "SCI",
        "6566": "SCI",
        "6567": "SCI",
        "6568": "SCI",
        "6569": "SCI",
        "6571": "SCI",
        "6572": "SCI",
        "6573": "SCI",
        "6574": "SCI",
        "6575": "SCI",
        "6576": "SCI",
        "6577": "SCI",
        "6578": "SCI",
        "6585": "SCI",
        "6588": "SCI",
        "6589": "SCI",
        "6595": "SCI",
        "6596": "SCI",
        "6597": "SCI",
        "6598": "SCI",
        "6599": "SCI",
        "9210": "ASSOCIATION",
        "9220": "ASSOCIATION",
        "9221": "ASSOCIATION",
        "9222": "ASSOCIATION",
        "9223": "ASSOCIATION",
        "9224": "ASSOCIATION",
        "9230": "ASSOCIATION",
        "9240": "ASSOCIATION",
        "9260": "ASSOCIATION",
        "9300": "ASSOCIATION",
        "1100": "MICRO",
        "1200": "MICRO",
        "1300": "MICRO",
    }
    return formes.get(code, "AUTRE")
