# =============================================================================
# AZALPLUS - Client Chorus Pro (B2G)
# =============================================================================
"""
Intégration Chorus Pro pour la facturation B2G (Business to Government).

Chorus Pro est le portail de facturation électronique obligatoire pour:
- Factures vers l'État
- Factures vers les collectivités locales
- Factures vers les établissements publics

API Chorus Pro:
- Environnement sandbox: https://sandbox-api.piste.gouv.fr
- Environnement production: https://api.piste.gouv.fr

Documentation: https://communaute.chorus-pro.gouv.fr/documentation/
"""

import httpx
import logging
import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ChorusEnvironment(str, Enum):
    """Environnements Chorus Pro."""
    SANDBOX = "sandbox"
    QUALIFICATION = "qualification"
    PRODUCTION = "production"


class ChorusInvoiceStatus(str, Enum):
    """Statuts Chorus Pro."""
    DEPOSEE = "DEPOSEE"                    # Déposée
    EN_COURS_ACHEMINEMENT = "EN_COURS_ACHEMINEMENT"
    MISE_A_DISPOSITION = "MISE_A_DISPOSITION"
    RECUE_PAR_DESTINATAIRE = "RECUE_PAR_DESTINATAIRE"
    REJETEE = "REJETEE"
    MANDATEE = "MANDATEE"                  # Mandatée pour paiement
    MISE_EN_PAIEMENT = "MISE_EN_PAIEMENT"
    SUSPENDUE = "SUSPENDUE"
    A_RECYCLER = "A_RECYCLER"


class ChorusInvoiceType(str, Enum):
    """Types de factures Chorus."""
    FACTURE = "FACTURE"
    AVOIR = "AVOIR"
    FACTURE_FOURNISSEUR = "FACTURE_FOURNISSEUR"


@dataclass
class ChorusConfig:
    """Configuration Chorus Pro."""
    client_id: str
    client_secret: str
    environment: ChorusEnvironment = ChorusEnvironment.SANDBOX
    timeout: int = 60
    # Identifiants techniques CPP
    tech_login: Optional[str] = None
    tech_password: Optional[str] = None

    @property
    def base_url(self) -> str:
        """URL de base selon l'environnement."""
        urls = {
            ChorusEnvironment.SANDBOX: "https://sandbox-api.piste.gouv.fr/cpro/factures",
            ChorusEnvironment.QUALIFICATION: "https://sandbox-api.piste.gouv.fr/cpro/factures",
            ChorusEnvironment.PRODUCTION: "https://api.piste.gouv.fr/cpro/factures"
        }
        return urls[self.environment]

    @property
    def oauth_url(self) -> str:
        """URL OAuth."""
        if self.environment == ChorusEnvironment.PRODUCTION:
            return "https://oauth.piste.gouv.fr/api/oauth/token"
        return "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"


@dataclass
class ChorusInvoice:
    """Facture pour Chorus Pro."""
    # Identifiants (requis)
    invoice_number: str
    issue_date: datetime

    # Émetteur (fournisseur) - requis
    supplier_siret: str
    supplier_name: str

    # Destinataire (service public) - requis
    buyer_siret: str
    buyer_name: str

    # Champs optionnels
    supplier_address: Optional[str] = None
    service_code: Optional[str] = None      # Code service destinataire
    engagement_number: Optional[str] = None  # Numéro d'engagement juridique

    # Montants
    total_without_tax: float = 0.0
    total_tax: float = 0.0
    total_with_tax: float = 0.0
    currency: str = "EUR"

    # Type
    invoice_type: ChorusInvoiceType = ChorusInvoiceType.FACTURE

    # Pièces jointes
    pdf_content: Optional[bytes] = None
    xml_content: Optional[str] = None       # Factur-X XML

    # Métadonnées
    mode_paiement: str = "VIREMENT"
    iban: Optional[str] = None
    bic: Optional[str] = None
    comment: Optional[str] = None

    # Référence marché public
    numero_marche: Optional[str] = None
    date_marche: Optional[datetime] = None


@dataclass
class ChorusResponse:
    """Réponse Chorus Pro."""
    success: bool
    chorus_id: Optional[str] = None         # Identifiant technique CPP
    numero_flux: Optional[str] = None       # Numéro de flux
    status: Optional[ChorusInvoiceStatus] = None
    message: Optional[str] = None
    errors: list[dict] = field(default_factory=list)
    raw_response: Optional[dict] = None


@dataclass
class ChorusStatusResponse:
    """Réponse statut Chorus."""
    chorus_id: str
    status: ChorusInvoiceStatus
    status_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    payment_date: Optional[datetime] = None
    payment_reference: Optional[str] = None
    lifecycle: list[dict] = field(default_factory=list)


@dataclass
class ChorusStructure:
    """Structure publique (destinataire)."""
    siret: str
    designation: str
    type_identifiant: str = "SIRET"
    code_service: Optional[str] = None
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None


class ChorusProClient:
    """
    Client API Chorus Pro.

    Usage:
        config = ChorusConfig(
            client_id="xxx",
            client_secret="xxx",
            environment=ChorusEnvironment.SANDBOX
        )

        async with ChorusProClient(config) as client:
            result = await client.submit_invoice(invoice)
            status = await client.get_status(result.chorus_id)
    """

    def __init__(self, config: ChorusConfig):
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
                # Token expire généralement en 1h
                expires_in = data.get("expires_in", 3600)
                from datetime import timedelta
                self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                return self._access_token
            else:
                raise Exception(f"OAuth error: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Erreur OAuth Chorus: {e}")
            raise

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None
    ) -> dict:
        """Effectuer une requête API."""
        token = await self._get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Ajouter les credentials techniques si configurés
        if self.config.tech_login:
            credentials = base64.b64encode(
                f"{self.config.tech_login}:{self.config.tech_password}".encode()
            ).decode()
            headers["cpro-account"] = credentials

        url = f"{self.config.base_url}{endpoint}"

        if method == "GET":
            response = await self.http_client.get(url, headers=headers, params=params)
        elif method == "POST":
            response = await self.http_client.post(url, headers=headers, json=data)
        else:
            raise ValueError(f"Méthode non supportée: {method}")

        return {
            "status_code": response.status_code,
            "data": response.json() if response.content else {}
        }

    async def submit_invoice(self, invoice: ChorusInvoice) -> ChorusResponse:
        """
        Soumettre une facture à Chorus Pro.

        Args:
            invoice: Facture à soumettre

        Returns:
            ChorusResponse avec l'identifiant Chorus
        """
        try:
            # Construire le payload selon l'API Chorus Pro
            payload = {
                "cadreDeFacturation": {
                    "codeCadreFacturation": "A1_FACTURE_FOURNISSEUR",
                    "codeServiceValideur": invoice.service_code
                },
                "references": {
                    "numeroFacture": invoice.invoice_number,
                    "dateFacture": invoice.issue_date.strftime("%Y-%m-%d"),
                    "typeFacture": invoice.invoice_type.value
                },
                "fournisseur": {
                    "typeIdentifiant": "SIRET",
                    "identifiant": invoice.supplier_siret,
                    "raisonSociale": invoice.supplier_name
                },
                "destinataire": {
                    "typeIdentifiant": "SIRET",
                    "identifiant": invoice.buyer_siret,
                    "raisonSociale": invoice.buyer_name,
                    "codeService": invoice.service_code
                },
                "montants": {
                    "montantHT": invoice.total_without_tax,
                    "montantTVA": invoice.total_tax,
                    "montantTTC": invoice.total_with_tax,
                    "devise": invoice.currency
                },
                "modePaiement": {
                    "typePaiement": invoice.mode_paiement
                }
            }

            # Ajouter IBAN/BIC si présent
            if invoice.iban:
                payload["modePaiement"]["compteBancaire"] = {
                    "iban": invoice.iban,
                    "bic": invoice.bic
                }

            # Ajouter référence engagement si présent
            if invoice.engagement_number:
                payload["references"]["numeroEngagement"] = invoice.engagement_number

            # Ajouter référence marché si présent
            if invoice.numero_marche:
                payload["references"]["numeroMarche"] = invoice.numero_marche

            # Ajouter commentaire si présent
            if invoice.comment:
                payload["commentaire"] = invoice.comment

            # Soumettre la facture
            result = await self._request("POST", "/v1/deposer/flux", data=payload)

            if result["status_code"] in (200, 201, 202):
                data = result["data"]
                return ChorusResponse(
                    success=True,
                    chorus_id=data.get("identifiantFacture") or data.get("idFacture"),
                    numero_flux=data.get("numeroFluxDepot"),
                    status=ChorusInvoiceStatus.DEPOSEE,
                    message="Facture déposée avec succès",
                    raw_response=data
                )
            else:
                data = result["data"]
                return ChorusResponse(
                    success=False,
                    message=data.get("message") or data.get("libelle") or "Erreur Chorus",
                    errors=data.get("listeErreurs", []),
                    raw_response=data
                )

        except Exception as e:
            logger.error(f"Erreur soumission Chorus: {e}")
            return ChorusResponse(
                success=False,
                message=str(e),
                errors=[{"code": "INTERNAL", "message": str(e)}]
            )

    async def submit_with_attachment(
        self,
        invoice: ChorusInvoice
    ) -> ChorusResponse:
        """
        Soumettre une facture avec pièce jointe PDF/XML.

        Cette méthode utilise l'API de dépôt de factures avec pièces jointes.
        """
        try:
            # D'abord soumettre la facture
            result = await self.submit_invoice(invoice)

            if not result.success:
                return result

            # Ensuite ajouter les pièces jointes
            if invoice.pdf_content:
                await self._add_attachment(
                    result.chorus_id,
                    "facture.pdf",
                    invoice.pdf_content,
                    "application/pdf"
                )

            if invoice.xml_content:
                await self._add_attachment(
                    result.chorus_id,
                    "factur-x.xml",
                    invoice.xml_content.encode("utf-8"),
                    "text/xml"
                )

            return result

        except Exception as e:
            logger.error(f"Erreur soumission avec pièce jointe: {e}")
            return ChorusResponse(success=False, message=str(e))

    async def _add_attachment(
        self,
        chorus_id: str,
        filename: str,
        content: bytes,
        mime_type: str
    ) -> bool:
        """Ajouter une pièce jointe à une facture."""
        try:
            payload = {
                "idFacture": chorus_id,
                "pieceJointe": {
                    "nomFichier": filename,
                    "typeMime": mime_type,
                    "contenu": base64.b64encode(content).decode()
                }
            }

            result = await self._request("POST", "/v1/ajouter/piece-jointe", data=payload)
            return result["status_code"] in (200, 201)

        except Exception as e:
            logger.error(f"Erreur ajout pièce jointe: {e}")
            return False

    async def get_status(self, chorus_id: str) -> ChorusStatusResponse:
        """
        Obtenir le statut d'une facture.

        Args:
            chorus_id: Identifiant Chorus de la facture

        Returns:
            ChorusStatusResponse
        """
        try:
            result = await self._request(
                "GET",
                f"/v1/consulter/facture",
                params={"idFacture": chorus_id}
            )

            if result["status_code"] == 200:
                data = result["data"]

                # Parser le statut
                status_str = data.get("statutFacture", "DEPOSEE")
                try:
                    status = ChorusInvoiceStatus(status_str)
                except ValueError:
                    status = ChorusInvoiceStatus.DEPOSEE

                # Parser les dates
                status_date = None
                if data.get("dateStatut"):
                    status_date = datetime.fromisoformat(data["dateStatut"].replace("Z", "+00:00"))

                payment_date = None
                if data.get("datePaiement"):
                    payment_date = datetime.fromisoformat(data["datePaiement"].replace("Z", "+00:00"))

                return ChorusStatusResponse(
                    chorus_id=chorus_id,
                    status=status,
                    status_date=status_date,
                    rejection_reason=data.get("motifRejet"),
                    payment_date=payment_date,
                    payment_reference=data.get("referencePaiement"),
                    lifecycle=data.get("historiqueStatuts", [])
                )
            else:
                return ChorusStatusResponse(
                    chorus_id=chorus_id,
                    status=ChorusInvoiceStatus.DEPOSEE
                )

        except Exception as e:
            logger.error(f"Erreur statut Chorus: {e}")
            return ChorusStatusResponse(
                chorus_id=chorus_id,
                status=ChorusInvoiceStatus.DEPOSEE
            )

    async def search_structures(
        self,
        siret: Optional[str] = None,
        designation: Optional[str] = None,
        code_postal: Optional[str] = None
    ) -> list[ChorusStructure]:
        """
        Rechercher des structures publiques.

        Utile pour trouver le code service d'un destinataire.
        """
        try:
            params = {}
            if siret:
                params["identifiant"] = siret
                params["typeIdentifiant"] = "SIRET"
            if designation:
                params["designation"] = designation
            if code_postal:
                params["codePostal"] = code_postal

            result = await self._request(
                "GET",
                "/v1/rechercher/structure",
                params=params
            )

            if result["status_code"] == 200:
                structures = []
                for item in result["data"].get("listeStructures", []):
                    structures.append(ChorusStructure(
                        siret=item.get("identifiant", ""),
                        designation=item.get("designation", ""),
                        type_identifiant=item.get("typeIdentifiant", "SIRET"),
                        code_service=item.get("codeService"),
                        adresse=item.get("adresse"),
                        code_postal=item.get("codePostal"),
                        ville=item.get("ville")
                    ))
                return structures
            return []

        except Exception as e:
            logger.error(f"Erreur recherche structures: {e}")
            return []

    async def get_services(self, siret: str) -> list[dict]:
        """
        Obtenir les services d'une structure publique.

        Retourne les codes service utilisables pour le destinataire.
        """
        try:
            result = await self._request(
                "GET",
                "/v1/rechercher/services",
                params={"identifiant": siret, "typeIdentifiant": "SIRET"}
            )

            if result["status_code"] == 200:
                return result["data"].get("listeServices", [])
            return []

        except Exception as e:
            logger.error(f"Erreur services: {e}")
            return []

    async def list_invoices(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        status: Optional[ChorusInvoiceStatus] = None,
        page: int = 1,
        page_size: int = 50
    ) -> list[dict]:
        """Lister les factures déposées."""
        try:
            params = {
                "pageNumero": page,
                "pageTaille": page_size
            }
            if from_date:
                params["dateDebut"] = from_date.strftime("%Y-%m-%d")
            if to_date:
                params["dateFin"] = to_date.strftime("%Y-%m-%d")
            if status:
                params["statut"] = status.value

            result = await self._request(
                "GET",
                "/v1/rechercher/factures",
                params=params
            )

            if result["status_code"] == 200:
                return result["data"].get("listeFactures", [])
            return []

        except Exception as e:
            logger.error(f"Erreur liste factures: {e}")
            return []

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
