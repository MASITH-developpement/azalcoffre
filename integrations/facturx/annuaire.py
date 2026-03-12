# =============================================================================
# AZALPLUS - Annuaire PPF (Portail Public de Facturation)
# =============================================================================
"""
Client pour l'annuaire du Portail Public de Facturation.

L'annuaire PPF permet de:
- Vérifier si une entreprise est inscrite à la facturation électronique
- Obtenir le routage (PDP/PPF) pour envoyer une facture
- Consulter les capacités de réception d'un destinataire

API Annuaire PPF:
- Sandbox: https://sandbox-api.piste.gouv.fr/annuaire-ppf
- Production: https://api.piste.gouv.fr/annuaire-ppf

Documentation: https://www.impots.gouv.fr/portail/professionnel/facture-electronique
"""

import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class PPFEnvironment(str, Enum):
    """Environnements PPF."""
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class RoutingType(str, Enum):
    """Types de routage."""
    PPF = "ppf"           # Via Portail Public
    PDP = "pdp"           # Via une PDP agréée
    NOT_REGISTERED = "not_registered"  # Non inscrit


class EntityType(str, Enum):
    """Types d'entités."""
    ENTREPRISE = "entreprise"
    ETABLISSEMENT = "etablissement"
    STRUCTURE_PUBLIQUE = "structure_publique"


class InvoiceCapability(str, Enum):
    """Capacités de facturation."""
    FACTURX = "facturx"
    UBL = "ubl"
    CII = "cii"
    PDF = "pdf"


@dataclass
class PPFConfig:
    """Configuration client PPF."""
    client_id: str
    client_secret: str
    environment: PPFEnvironment = PPFEnvironment.SANDBOX
    timeout: int = 30

    @property
    def base_url(self) -> str:
        if self.environment == PPFEnvironment.PRODUCTION:
            return "https://api.piste.gouv.fr/annuaire-ppf/v1"
        return "https://sandbox-api.piste.gouv.fr/annuaire-ppf/v1"

    @property
    def oauth_url(self) -> str:
        if self.environment == PPFEnvironment.PRODUCTION:
            return "https://oauth.piste.gouv.fr/api/oauth/token"
        return "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"


@dataclass
class RegistrationInfo:
    """Informations d'inscription PPF."""
    siret: str
    siren: str
    is_registered: bool = False
    registration_date: Optional[datetime] = None
    entity_type: EntityType = EntityType.ENTREPRISE
    routing: RoutingType = RoutingType.NOT_REGISTERED

    # PDP si applicable
    pdp_name: Optional[str] = None
    pdp_id: Optional[str] = None

    # Capacités
    supported_formats: list[InvoiceCapability] = field(default_factory=list)
    can_receive_invoices: bool = False
    can_send_invoices: bool = False

    # Informations entreprise
    company_name: Optional[str] = None
    legal_form: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None

    # Métadonnées
    last_updated: Optional[datetime] = None
    raw_data: dict = field(default_factory=dict)


@dataclass
class LookupResult:
    """Résultat de recherche annuaire."""
    success: bool
    registration: Optional[RegistrationInfo] = None
    message: Optional[str] = None
    errors: list[str] = field(default_factory=list)


@dataclass
class RoutingInfo:
    """Informations de routage pour envoi facture."""
    siret: str
    can_receive: bool = False
    routing_type: RoutingType = RoutingType.NOT_REGISTERED

    # Si PDP
    pdp_endpoint: Optional[str] = None
    pdp_id: Optional[str] = None

    # Format préféré
    preferred_format: InvoiceCapability = InvoiceCapability.FACTURX
    supported_formats: list[InvoiceCapability] = field(default_factory=list)

    # Code service (pour B2G)
    service_code: Optional[str] = None


class AnnuairePPF:
    """
    Client pour l'annuaire PPF.

    Permet de:
    - Vérifier l'inscription d'une entreprise
    - Obtenir les informations de routage
    - Consulter les capacités de réception

    Usage:
        config = PPFConfig(
            client_id="xxx",
            client_secret="xxx"
        )

        async with AnnuairePPF(config) as annuaire:
            # Vérifier inscription
            result = await annuaire.lookup(siret="12345678901234")

            if result.success and result.registration.is_registered:
                # Obtenir le routage
                routing = await annuaire.get_routing(siret="12345678901234")
    """

    def __init__(self, config: PPFConfig):
        self.config = config
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self.http_client = httpx.AsyncClient(timeout=config.timeout)

    async def _get_token(self) -> str:
        """Obtenir un token OAuth2."""
        if self._access_token and self._token_expires:
            if datetime.utcnow() < self._token_expires:
                return self._access_token

        try:
            response = await self.http_client.post(
                self.config.oauth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "scope": "openid"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code == 200:
                data = response.json()
                self._access_token = data["access_token"]
                from datetime import timedelta
                expires_in = data.get("expires_in", 3600)
                self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                return self._access_token
            else:
                raise Exception(f"OAuth error: {response.status_code}")

        except Exception as e:
            logger.error(f"Erreur OAuth PPF: {e}")
            raise

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None
    ) -> dict:
        """Effectuer une requête API."""
        token = await self._get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        url = f"{self.config.base_url}{endpoint}"

        if method == "GET":
            response = await self.http_client.get(url, headers=headers, params=params)
        elif method == "POST":
            headers["Content-Type"] = "application/json"
            response = await self.http_client.post(url, headers=headers, json=data)
        else:
            raise ValueError(f"Méthode non supportée: {method}")

        return {
            "status_code": response.status_code,
            "data": response.json() if response.content else {}
        }

    async def lookup(
        self,
        siret: Optional[str] = None,
        siren: Optional[str] = None
    ) -> LookupResult:
        """
        Rechercher une entreprise dans l'annuaire.

        Args:
            siret: SIRET de l'entreprise (14 chiffres)
            siren: SIREN de l'entreprise (9 chiffres) - recherche tous les établissements

        Returns:
            LookupResult avec les informations d'inscription
        """
        if not siret and not siren:
            return LookupResult(
                success=False,
                message="SIRET ou SIREN requis",
                errors=["Aucun identifiant fourni"]
            )

        try:
            # Construire les paramètres
            params = {}
            if siret:
                params["siret"] = siret.replace(" ", "")
            elif siren:
                params["siren"] = siren.replace(" ", "")

            result = await self._request("GET", "/entites", params=params)

            if result["status_code"] == 200:
                data = result["data"]

                if not data.get("entites"):
                    return LookupResult(
                        success=True,
                        registration=RegistrationInfo(
                            siret=siret or "",
                            siren=siren or (siret[:9] if siret else ""),
                            is_registered=False
                        ),
                        message="Entreprise non inscrite à la facturation électronique"
                    )

                # Parser la première entité trouvée
                entity = data["entites"][0]
                registration = self._parse_entity(entity)

                return LookupResult(
                    success=True,
                    registration=registration
                )

            elif result["status_code"] == 404:
                return LookupResult(
                    success=True,
                    registration=RegistrationInfo(
                        siret=siret or "",
                        siren=siren or (siret[:9] if siret else ""),
                        is_registered=False
                    ),
                    message="Entreprise non trouvée dans l'annuaire"
                )
            else:
                return LookupResult(
                    success=False,
                    message=result["data"].get("message", f"Erreur {result['status_code']}"),
                    errors=result["data"].get("errors", [])
                )

        except Exception as e:
            logger.error(f"Erreur lookup PPF: {e}")
            return LookupResult(
                success=False,
                message=str(e),
                errors=[str(e)]
            )

    def _parse_entity(self, data: dict) -> RegistrationInfo:
        """Parser les données d'une entité."""
        # SIRET/SIREN
        siret = data.get("siret", "")
        siren = data.get("siren", siret[:9] if siret else "")

        # Routage
        routing_data = data.get("routage", {})
        if routing_data.get("pdp"):
            routing = RoutingType.PDP
        elif routing_data.get("ppf"):
            routing = RoutingType.PPF
        else:
            routing = RoutingType.NOT_REGISTERED

        # Formats supportés
        formats = []
        for fmt in data.get("formatsAcceptes", []):
            try:
                formats.append(InvoiceCapability(fmt.lower()))
            except ValueError:
                pass

        # Date d'inscription
        reg_date = None
        if data.get("dateInscription"):
            try:
                reg_date = datetime.fromisoformat(data["dateInscription"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return RegistrationInfo(
            siret=siret,
            siren=siren,
            is_registered=True,
            registration_date=reg_date,
            entity_type=EntityType(data.get("typeEntite", "entreprise")),
            routing=routing,
            pdp_name=routing_data.get("pdp", {}).get("nom"),
            pdp_id=routing_data.get("pdp", {}).get("id"),
            supported_formats=formats or [InvoiceCapability.FACTURX],
            can_receive_invoices=data.get("peutRecevoirFactures", False),
            can_send_invoices=data.get("peutEmettreFactures", False),
            company_name=data.get("raisonSociale"),
            legal_form=data.get("formeJuridique"),
            address=data.get("adresse"),
            postal_code=data.get("codePostal"),
            city=data.get("ville"),
            last_updated=datetime.utcnow(),
            raw_data=data
        )

    async def get_routing(self, siret: str) -> RoutingInfo:
        """
        Obtenir les informations de routage pour envoyer une facture.

        Args:
            siret: SIRET du destinataire

        Returns:
            RoutingInfo avec les détails de routage
        """
        result = await self.lookup(siret=siret)

        if not result.success or not result.registration:
            return RoutingInfo(
                siret=siret,
                can_receive=False,
                routing_type=RoutingType.NOT_REGISTERED
            )

        reg = result.registration

        return RoutingInfo(
            siret=siret,
            can_receive=reg.can_receive_invoices,
            routing_type=reg.routing,
            pdp_endpoint=reg.raw_data.get("routage", {}).get("pdp", {}).get("endpoint"),
            pdp_id=reg.pdp_id,
            preferred_format=reg.supported_formats[0] if reg.supported_formats else InvoiceCapability.FACTURX,
            supported_formats=reg.supported_formats
        )

    async def verify_siret(self, siret: str) -> dict:
        """
        Vérifier un SIRET via l'API Sirene.

        Retourne les informations de l'entreprise depuis la base Sirene.
        Utile pour vérifier qu'une entreprise existe (même si non inscrite au PPF).
        """
        # Cette méthode pourrait utiliser l'API Sirene de l'INSEE
        # Pour l'instant, utilise le lookup PPF
        result = await self.lookup(siret=siret)

        if result.success and result.registration:
            return {
                "valid": True,
                "siret": siret,
                "siren": result.registration.siren,
                "company_name": result.registration.company_name,
                "address": result.registration.address,
                "is_registered_ppf": result.registration.is_registered
            }

        return {
            "valid": False,
            "siret": siret,
            "message": result.message
        }

    async def search(
        self,
        query: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> list[RegistrationInfo]:
        """
        Rechercher des entreprises dans l'annuaire.

        Args:
            query: Recherche texte (nom, SIRET partiel)
            postal_code: Code postal
            city: Ville
            page: Numéro de page
            page_size: Taille de page

        Returns:
            Liste de RegistrationInfo
        """
        try:
            params = {
                "page": page,
                "taille": page_size
            }
            if query:
                params["recherche"] = query
            if postal_code:
                params["codePostal"] = postal_code
            if city:
                params["ville"] = city

            result = await self._request("GET", "/entites/recherche", params=params)

            if result["status_code"] == 200:
                entities = result["data"].get("entites", [])
                return [self._parse_entity(e) for e in entities]

            return []

        except Exception as e:
            logger.error(f"Erreur recherche PPF: {e}")
            return []

    async def check_eligibility(self, siret: str) -> dict:
        """
        Vérifier l'éligibilité d'une entreprise à la facturation électronique.

        Selon le calendrier de la réforme:
        - 2024: Grandes entreprises (>250 salariés ou CA >50M€)
        - 2025: ETI (50-250 salariés ou CA 10-50M€)
        - 2026: PME et TPE

        Returns:
            Dict avec éligibilité et date d'obligation
        """
        result = await self.lookup(siret=siret)

        response = {
            "siret": siret,
            "is_registered": False,
            "must_register": True,  # Toutes les entreprises devront s'inscrire
            "obligation_date": "2026-01-01",  # Date par défaut (TPE/PME)
            "can_send": False,
            "can_receive": False
        }

        if result.success and result.registration:
            response["is_registered"] = result.registration.is_registered
            response["can_send"] = result.registration.can_send_invoices
            response["can_receive"] = result.registration.can_receive_invoices
            response["company_name"] = result.registration.company_name
            response["routing"] = result.registration.routing.value

        return response

    async def health_check(self) -> bool:
        """Vérifier la connectivité."""
        try:
            await self._get_token()
            return True
        except Exception:
            return False

    async def close(self):
        """Fermer le client."""
        await self.http_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Fonction utilitaire pour vérification rapide
async def check_siret_registration(siret: str, config: PPFConfig) -> dict:
    """
    Vérifier rapidement si un SIRET est inscrit au PPF.

    Usage:
        result = await check_siret_registration("12345678901234", config)
        if result["registered"]:
            print(f"Envoyer via {result['routing']}")
    """
    async with AnnuairePPF(config) as annuaire:
        result = await annuaire.lookup(siret=siret)

        return {
            "siret": siret,
            "registered": result.registration.is_registered if result.registration else False,
            "routing": result.registration.routing.value if result.registration else "not_registered",
            "can_receive": result.registration.can_receive_invoices if result.registration else False,
            "pdp": result.registration.pdp_name if result.registration else None
        }
