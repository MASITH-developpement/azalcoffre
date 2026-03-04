# =============================================================================
# AZALPLUS - Service Adresse et SIRET
# =============================================================================
"""
Services d'autocompletion pour:
- Adresses francaises (api-adresse.data.gouv.fr)
- Entreprises via SIRET (api.insee.fr / entreprise.data.gouv.fr)

Usage:
    from .adresse import AdresseService, SiretService

    # Recherche d'adresse
    results = await AdresseService.search_address("15 rue de la paix paris")

    # Recherche d'entreprise par SIRET
    company = await SiretService.lookup_siret("44306184100047")
"""

import httpx
import structlog
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass
from enum import Enum

logger = structlog.get_logger()

# =============================================================================
# Constants
# =============================================================================
ADRESSE_API_BASE = "https://api-adresse.data.gouv.fr"
SIRENE_API_BASE = "https://entreprise.data.gouv.fr/api/sirene/v3"

# Timeout pour les appels API externes
API_TIMEOUT = 10.0  # secondes


# =============================================================================
# Models
# =============================================================================
class AdresseResult(BaseModel):
    """Resultat d'autocompletion d'adresse."""

    adresse: str = Field(..., description="Adresse complete formatee")
    numero: Optional[str] = Field(None, description="Numero de rue")
    rue: Optional[str] = Field(None, description="Nom de la rue")
    code_postal: str = Field(..., description="Code postal")
    ville: str = Field(..., description="Nom de la ville")
    departement: Optional[str] = Field(None, description="Numero de departement")
    region: Optional[str] = Field(None, description="Nom de la region")
    pays: str = Field(default="France", description="Pays")
    latitude: Optional[float] = Field(None, description="Latitude GPS")
    longitude: Optional[float] = Field(None, description="Longitude GPS")
    score: Optional[float] = Field(None, description="Score de pertinence (0-1)")
    type: Optional[str] = Field(None, description="Type de resultat (housenumber, street, municipality)")


class EntrepriseResult(BaseModel):
    """Resultat de recherche d'entreprise par SIRET."""

    siret: str = Field(..., description="Numero SIRET (14 chiffres)")
    siren: str = Field(..., description="Numero SIREN (9 chiffres)")
    nom: str = Field(..., description="Denomination sociale ou nom")
    nom_commercial: Optional[str] = Field(None, description="Nom commercial")
    forme_juridique: Optional[str] = Field(None, description="Forme juridique")
    code_forme_juridique: Optional[str] = Field(None, description="Code forme juridique")

    # Adresse
    adresse: Optional[str] = Field(None, description="Adresse complete")
    code_postal: Optional[str] = Field(None, description="Code postal")
    ville: Optional[str] = Field(None, description="Ville")

    # Activite
    code_naf: Optional[str] = Field(None, description="Code NAF/APE")
    activite: Optional[str] = Field(None, description="Libelle activite")

    # Dates
    date_creation: Optional[str] = Field(None, description="Date de creation")

    # Statut
    actif: bool = Field(default=True, description="Etablissement actif")
    siege_social: bool = Field(default=False, description="Est le siege social")

    # Informations supplementaires
    effectif: Optional[str] = Field(None, description="Tranche d'effectif")
    tva_intra: Optional[str] = Field(None, description="Numero de TVA intracommunautaire")


# =============================================================================
# Service Adresse
# =============================================================================
class AdresseService:
    """
    Service d'autocompletion d'adresses francaises.
    Utilise l'API officielle api-adresse.data.gouv.fr

    API Documentation: https://adresse.data.gouv.fr/api-doc/adresse
    """

    @staticmethod
    async def search_address(
        query: str,
        limit: int = 5,
        autocomplete: bool = True,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        type_filter: Optional[str] = None,
        postcode: Optional[str] = None,
        citycode: Optional[str] = None
    ) -> List[AdresseResult]:
        """
        Recherche d'adresse avec autocompletion.

        Args:
            query: Texte de recherche (min 3 caracteres)
            limit: Nombre max de resultats (1-20, defaut 5)
            autocomplete: Active l'autocompletion (defaut True)
            lat: Latitude pour prioriser les resultats proches
            lon: Longitude pour prioriser les resultats proches
            type_filter: Filtrer par type (housenumber, street, locality, municipality)
            postcode: Filtrer par code postal
            citycode: Filtrer par code INSEE

        Returns:
            Liste de resultats AdresseResult
        """
        if not query or len(query) < 3:
            return []

        # Construire les parametres
        params = {
            "q": query,
            "limit": min(max(1, limit), 20),
            "autocomplete": 1 if autocomplete else 0
        }

        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon

        if type_filter:
            params["type"] = type_filter

        if postcode:
            params["postcode"] = postcode

        if citycode:
            params["citycode"] = citycode

        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.get(
                    f"{ADRESSE_API_BASE}/search/",
                    params=params
                )
                response.raise_for_status()

                data = response.json()
                features = data.get("features", [])

                results = []
                for feature in features:
                    props = feature.get("properties", {})
                    geometry = feature.get("geometry", {})
                    coords = geometry.get("coordinates", [None, None])

                    # Construire l'adresse formatee
                    adresse_parts = []
                    if props.get("housenumber"):
                        adresse_parts.append(props["housenumber"])
                    if props.get("street"):
                        adresse_parts.append(props["street"])
                    elif props.get("name"):
                        adresse_parts.append(props["name"])

                    adresse = " ".join(adresse_parts) if adresse_parts else props.get("label", "")

                    result = AdresseResult(
                        adresse=props.get("label", adresse),
                        numero=props.get("housenumber"),
                        rue=props.get("street") or props.get("name"),
                        code_postal=props.get("postcode", ""),
                        ville=props.get("city", ""),
                        departement=props.get("context", "").split(",")[0] if props.get("context") else None,
                        region=props.get("context", "").split(",")[-1].strip() if props.get("context") else None,
                        pays="France",
                        latitude=coords[1] if len(coords) > 1 else None,
                        longitude=coords[0] if len(coords) > 0 else None,
                        score=props.get("score"),
                        type=props.get("type")
                    )
                    results.append(result)

                logger.debug(
                    "address_search_completed",
                    query=query,
                    results_count=len(results)
                )

                return results

        except httpx.TimeoutException:
            logger.warning("address_api_timeout", query=query)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("address_api_error", status=e.response.status_code, query=query)
            return []
        except Exception as e:
            logger.error("address_search_error", error=str(e), query=query)
            return []

    @staticmethod
    async def reverse_geocode(
        lat: float,
        lon: float,
        type_filter: Optional[str] = None
    ) -> Optional[AdresseResult]:
        """
        Geocodage inverse: coordonnees GPS vers adresse.

        Args:
            lat: Latitude
            lon: Longitude
            type_filter: Filtrer par type

        Returns:
            AdresseResult ou None
        """
        params = {
            "lat": lat,
            "lon": lon
        }

        if type_filter:
            params["type"] = type_filter

        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.get(
                    f"{ADRESSE_API_BASE}/reverse/",
                    params=params
                )
                response.raise_for_status()

                data = response.json()
                features = data.get("features", [])

                if not features:
                    return None

                feature = features[0]
                props = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                coords = geometry.get("coordinates", [lon, lat])

                return AdresseResult(
                    adresse=props.get("label", ""),
                    numero=props.get("housenumber"),
                    rue=props.get("street") or props.get("name"),
                    code_postal=props.get("postcode", ""),
                    ville=props.get("city", ""),
                    departement=props.get("context", "").split(",")[0] if props.get("context") else None,
                    region=props.get("context", "").split(",")[-1].strip() if props.get("context") else None,
                    pays="France",
                    latitude=coords[1] if len(coords) > 1 else lat,
                    longitude=coords[0] if len(coords) > 0 else lon,
                    score=props.get("score"),
                    type=props.get("type")
                )

        except Exception as e:
            logger.error("reverse_geocode_error", error=str(e), lat=lat, lon=lon)
            return None


# =============================================================================
# Service SIRET
# =============================================================================
class SiretService:
    """
    Service de recherche d'entreprises par SIRET/SIREN.
    Utilise l'API publique entreprise.data.gouv.fr

    API Documentation: https://entreprise.data.gouv.fr/
    """

    @staticmethod
    def validate_siret(siret: str) -> bool:
        """
        Valide un numero SIRET avec l'algorithme de Luhn.

        Args:
            siret: Numero SIRET (14 chiffres)

        Returns:
            True si valide, False sinon
        """
        # Nettoyer le SIRET
        siret = siret.replace(" ", "").replace("-", "")

        if not siret.isdigit() or len(siret) != 14:
            return False

        # Algorithme de Luhn
        total = 0
        for i, digit in enumerate(siret):
            d = int(digit)
            if i % 2 == 0:  # Position paire (0, 2, 4...)
                d *= 2
                if d > 9:
                    d -= 9
            total += d

        return total % 10 == 0

    @staticmethod
    def validate_siren(siren: str) -> bool:
        """
        Valide un numero SIREN avec l'algorithme de Luhn.

        Args:
            siren: Numero SIREN (9 chiffres)

        Returns:
            True si valide, False sinon
        """
        siren = siren.replace(" ", "").replace("-", "")

        if not siren.isdigit() or len(siren) != 9:
            return False

        # Algorithme de Luhn
        total = 0
        for i, digit in enumerate(siren):
            d = int(digit)
            if i % 2 == 1:  # Position impaire (1, 3, 5, 7)
                d *= 2
                if d > 9:
                    d -= 9
            total += d

        return total % 10 == 0

    @staticmethod
    def calculate_tva_intra(siren: str) -> Optional[str]:
        """
        Calcule le numero de TVA intracommunautaire a partir du SIREN.

        Args:
            siren: Numero SIREN (9 chiffres)

        Returns:
            Numero de TVA (format FR XX XXXXXXXXX) ou None
        """
        siren = siren.replace(" ", "").replace("-", "")

        if not siren.isdigit() or len(siren) != 9:
            return None

        # Cle = (12 + 3 * (SIREN modulo 97)) modulo 97
        key = (12 + 3 * (int(siren) % 97)) % 97

        return f"FR{key:02d}{siren}"

    @staticmethod
    async def lookup_siret(siret: str) -> Optional[EntrepriseResult]:
        """
        Recherche une entreprise par son SIRET.

        Args:
            siret: Numero SIRET (14 chiffres)

        Returns:
            EntrepriseResult ou None si non trouve
        """
        # Nettoyer et valider
        siret = siret.replace(" ", "").replace("-", "")

        if not SiretService.validate_siret(siret):
            logger.warning("invalid_siret", siret=siret)
            return None

        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.get(
                    f"{SIRENE_API_BASE}/etablissements/{siret}"
                )

                if response.status_code == 404:
                    logger.info("siret_not_found", siret=siret)
                    return None

                response.raise_for_status()

                data = response.json()
                etablissement = data.get("etablissement", {})

                if not etablissement:
                    return None

                # Extraire les informations
                unite_legale = etablissement.get("unite_legale", {})
                adresse = etablissement.get("adresse", {})

                # Construire le nom
                nom = (
                    unite_legale.get("denomination") or
                    unite_legale.get("denomination_usuelle_1") or
                    f"{unite_legale.get('prenom_1', '')} {unite_legale.get('nom', '')}".strip() or
                    "Inconnu"
                )

                # Construire l'adresse complete
                adresse_parts = []
                if adresse.get("numero_voie"):
                    adresse_parts.append(adresse["numero_voie"])
                if adresse.get("type_voie"):
                    adresse_parts.append(adresse["type_voie"])
                if adresse.get("libelle_voie"):
                    adresse_parts.append(adresse["libelle_voie"])
                adresse_complete = " ".join(adresse_parts) if adresse_parts else None

                # SIREN
                siren = siret[:9]

                return EntrepriseResult(
                    siret=siret,
                    siren=siren,
                    nom=nom,
                    nom_commercial=unite_legale.get("denomination_usuelle_1"),
                    forme_juridique=unite_legale.get("categorie_juridique"),
                    code_forme_juridique=unite_legale.get("categorie_juridique"),
                    adresse=adresse_complete,
                    code_postal=adresse.get("code_postal"),
                    ville=adresse.get("libelle_commune"),
                    code_naf=etablissement.get("activite_principale") or unite_legale.get("activite_principale"),
                    activite=etablissement.get("libelle_activite_principale"),
                    date_creation=etablissement.get("date_creation"),
                    actif=etablissement.get("etat_administratif") == "A",
                    siege_social=etablissement.get("etablissement_siege") == "true",
                    effectif=unite_legale.get("tranche_effectifs"),
                    tva_intra=SiretService.calculate_tva_intra(siren)
                )

        except httpx.TimeoutException:
            logger.warning("siret_api_timeout", siret=siret)
            return None
        except httpx.HTTPStatusError as e:
            logger.error("siret_api_error", status=e.response.status_code, siret=siret)
            return None
        except Exception as e:
            logger.error("siret_lookup_error", error=str(e), siret=siret)
            return None

    @staticmethod
    async def search_entreprise(
        query: str,
        limit: int = 5,
        only_active: bool = True
    ) -> List[EntrepriseResult]:
        """
        Recherche d'entreprises par nom.

        Args:
            query: Texte de recherche
            limit: Nombre max de resultats
            only_active: Ne retourner que les entreprises actives

        Returns:
            Liste de resultats EntrepriseResult
        """
        if not query or len(query) < 2:
            return []

        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                params = {
                    "q": query,
                    "per_page": limit
                }

                if only_active:
                    params["etat_administratif"] = "A"

                response = await client.get(
                    f"{SIRENE_API_BASE}/etablissements",
                    params=params
                )
                response.raise_for_status()

                data = response.json()
                etablissements = data.get("etablissements", [])

                results = []
                for etab in etablissements:
                    unite_legale = etab.get("unite_legale", {})
                    adresse = etab.get("adresse", {})

                    nom = (
                        unite_legale.get("denomination") or
                        unite_legale.get("denomination_usuelle_1") or
                        f"{unite_legale.get('prenom_1', '')} {unite_legale.get('nom', '')}".strip() or
                        "Inconnu"
                    )

                    siret = etab.get("siret", "")
                    siren = siret[:9] if siret else ""

                    adresse_parts = []
                    if adresse.get("numero_voie"):
                        adresse_parts.append(adresse["numero_voie"])
                    if adresse.get("type_voie"):
                        adresse_parts.append(adresse["type_voie"])
                    if adresse.get("libelle_voie"):
                        adresse_parts.append(adresse["libelle_voie"])
                    adresse_complete = " ".join(adresse_parts) if adresse_parts else None

                    result = EntrepriseResult(
                        siret=siret,
                        siren=siren,
                        nom=nom,
                        nom_commercial=unite_legale.get("denomination_usuelle_1"),
                        forme_juridique=unite_legale.get("categorie_juridique"),
                        code_forme_juridique=unite_legale.get("categorie_juridique"),
                        adresse=adresse_complete,
                        code_postal=adresse.get("code_postal"),
                        ville=adresse.get("libelle_commune"),
                        code_naf=etab.get("activite_principale"),
                        activite=etab.get("libelle_activite_principale"),
                        date_creation=etab.get("date_creation"),
                        actif=etab.get("etat_administratif") == "A",
                        siege_social=etab.get("etablissement_siege") == "true",
                        effectif=unite_legale.get("tranche_effectifs"),
                        tva_intra=SiretService.calculate_tva_intra(siren) if siren else None
                    )
                    results.append(result)

                logger.debug(
                    "entreprise_search_completed",
                    query=query,
                    results_count=len(results)
                )

                return results

        except httpx.TimeoutException:
            logger.warning("entreprise_api_timeout", query=query)
            return []
        except httpx.HTTPStatusError as e:
            logger.error("entreprise_api_error", status=e.response.status_code, query=query)
            return []
        except Exception as e:
            logger.error("entreprise_search_error", error=str(e), query=query)
            return []


# =============================================================================
# Export
# =============================================================================
__all__ = [
    "AdresseService",
    "AdresseResult",
    "SiretService",
    "EntrepriseResult"
]
