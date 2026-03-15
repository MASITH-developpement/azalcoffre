"""
AZALPLUS - Client API Chorus Pro
Connexion et appels à l'API Chorus Pro via PISTE
"""

import base64
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .models import ChorusInvoice, ChorusStructure, InvoiceStatus

logger = logging.getLogger(__name__)


@dataclass
class ChorusProConfig:
    """Configuration Chorus Pro"""
    client_id: str
    client_secret: str
    tech_login: str
    tech_password: str
    environment: str = "SANDBOX"  # SANDBOX ou PRODUCTION

    @classmethod
    def from_env(cls) -> "ChorusProConfig":
        """Charge depuis les variables d'environnement"""
        return cls(
            client_id=os.getenv("CHORUS_CLIENT_ID", ""),
            client_secret=os.getenv("CHORUS_CLIENT_SECRET", ""),
            tech_login=os.getenv("CHORUS_TECH_LOGIN", ""),
            tech_password=os.getenv("CHORUS_TECH_PASSWORD", ""),
            environment=os.getenv("CHORUS_ENVIRONMENT", "SANDBOX"),
        )

    @property
    def oauth_url(self) -> str:
        if self.environment == "PRODUCTION":
            return "https://oauth.piste.gouv.fr/api/oauth/token"
        return "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"

    @property
    def api_url(self) -> str:
        if self.environment == "PRODUCTION":
            return "https://api.piste.gouv.fr"
        return "https://sandbox-api.piste.gouv.fr"

    @property
    def cpro_account(self) -> str:
        """Header cpro-account encodé en base64"""
        credentials = f"{self.tech_login}:{self.tech_password}"
        return base64.b64encode(credentials.encode()).decode()


class ChorusProClient:
    """Client API Chorus Pro"""

    def __init__(self, config: Optional[ChorusProConfig] = None):
        self.config = config or ChorusProConfig.from_env()
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._client = httpx.Client(timeout=30)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.close()

    def _get_token(self) -> str:
        """Obtient ou rafraîchit le token OAuth2"""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        resp = self._client.post(
            self.config.oauth_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "openid",
            },
        )
        resp.raise_for_status()

        data = resp.json()
        self._token = data["access_token"]
        # Token expire généralement en 1h, on prend 50min par sécurité
        self._token_expires = datetime.now() + timedelta(minutes=50)

        logger.info("Token Chorus Pro obtenu")
        return self._token

    def _headers(self) -> dict:
        """Headers pour les requêtes API"""
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "cpro-account": self.config.cpro_account,
            "Content-Type": "application/json",
        }

    def _post(self, endpoint: str, data: dict) -> dict:
        """POST vers l'API Chorus Pro"""
        url = f"{self.config.api_url}{endpoint}"
        resp = self._client.post(url, json=data, headers=self._headers())

        if resp.status_code == 200:
            return resp.json()

        logger.error(f"Erreur API Chorus Pro: {resp.status_code} - {resp.text}")
        raise ChorusProError(resp.status_code, resp.text)

    def _get(self, endpoint: str) -> dict:
        """GET vers l'API Chorus Pro"""
        url = f"{self.config.api_url}{endpoint}"
        resp = self._client.get(url, headers=self._headers())

        if resp.status_code == 200:
            return resp.json()

        logger.error(f"Erreur API Chorus Pro: {resp.status_code} - {resp.text}")
        raise ChorusProError(resp.status_code, resp.text)

    # === STRUCTURES ===

    def rechercher_structure(self, siret: str) -> Optional[ChorusStructure]:
        """Recherche une structure par SIRET"""
        try:
            data = self._post(
                "/cpro/structures/v1/rechercher",
                {"structure": {"identifiantStructure": siret}},
            )

            structures = data.get("listeStructures", [])
            if structures:
                return ChorusStructure.from_api(structures[0])
            return None

        except ChorusProError as e:
            logger.error(f"Erreur recherche structure {siret}: {e}")
            return None

    def get_id_structure(self, siret: str) -> Optional[int]:
        """Retourne l'ID Chorus Pro d'une structure"""
        structure = self.rechercher_structure(siret)
        return structure.id_cpp if structure else None

    # === FACTURES ===

    def soumettre_facture(self, facture: ChorusInvoice) -> dict:
        """Soumet une facture à Chorus Pro (format JSON)"""
        try:
            data = self._post(
                "/cpro/factures/v1/soumettre",
                facture.to_api(),
            )

            if data.get("codeRetour") == 0:
                facture.id_facture_cpp = data.get("numeroFluxDepot")
                facture.statut = InvoiceStatus.SUBMITTED
                logger.info(f"Facture {facture.numero_facture} soumise: {facture.id_facture_cpp}")

            return data

        except ChorusProError as e:
            logger.error(f"Erreur soumission facture {facture.numero_facture}: {e}")
            raise

    def deposer_facturx(self, pdf_content: bytes, nom_fichier: str) -> dict:
        """
        Dépose un fichier Factur-X (PDF/A-3 avec XML embarqué).

        C'est la méthode recommandée pour soumettre des factures.

        Args:
            pdf_content: Contenu binaire du PDF Factur-X
            nom_fichier: Nom du fichier (ex: "FA-2026-001.pdf")

        Returns:
            dict avec numeroFluxDepot, dateDepot, etc.
        """
        import base64

        pdf_base64 = base64.b64encode(pdf_content).decode()

        data = self._post(
            "/cpro/factures/v1/deposer/flux",
            {
                "fichierFlux": pdf_base64,
                "nomFichier": nom_fichier,
                "syntaxeFlux": "IN_DP_E2_CII_FACTURX",
                "avecSignature": False,
            },
        )

        if data.get("codeRetour") == 0:
            logger.info(f"Factur-X déposé: {data.get('numeroFluxDepot')}")

        return data

    def consulter_facture(self, id_facture: int) -> dict:
        """Consulte le statut d'une facture"""
        return self._post(
            "/cpro/factures/v1/consulter",
            {"idFacture": id_facture},
        )

    def rechercher_factures_fournisseur(
        self,
        id_structure: int,
        page: int = 1,
        nb_resultats: int = 10,
    ) -> dict:
        """Recherche les factures d'un fournisseur"""
        return self._post(
            "/cpro/factures/v1/rechercher/fournisseur",
            {
                "rechercherFactureParFournisseur": {
                    "idStructure": id_structure,
                    "pageResultatDemandee": page,
                    "nbResultatsParPage": nb_resultats,
                }
            },
        )

    # === HEALTH CHECK ===

    def health_check(self) -> bool:
        """Vérifie la connexion à Chorus Pro"""
        try:
            # Test simple : rechercher une structure connue
            structure = self.rechercher_structure("35084241449050")
            return structure is not None
        except Exception as e:
            logger.error(f"Health check Chorus Pro failed: {e}")
            return False


class ChorusProError(Exception):
    """Erreur API Chorus Pro"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Chorus Pro API Error {status_code}: {message}")
