# =============================================================================
# AZALPLUS - Client PDP (Plateforme de Dématérialisation Partenaire)
# =============================================================================
"""
Intégration avec les PDP agréées pour la facturation électronique française.

Réforme facturation électronique 2024-2026:
- Obligation progressive: grandes entreprises (2024), ETI (2025), PME/TPE (2026)
- Transmission via PDP ou PPF (Portail Public de Facturation)
- Formats: Factur-X, UBL, CII

PDP supportées:
- CEGID
- SAGE
- PENNYLANE
- YOOZ
- GENERIX
- Custom (API générique)
"""

import httpx
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class PDPProvider(str, Enum):
    """PDP agréées supportées."""
    CEGID = "cegid"
    SAGE = "sage"
    PENNYLANE = "pennylane"
    YOOZ = "yooz"
    GENERIX = "generix"
    CUSTOM = "custom"


class InvoiceStatus(str, Enum):
    """Statuts de facture selon la norme."""
    DRAFT = "draft"                   # Brouillon local
    SUBMITTED = "submitted"           # Envoyée à la PDP
    PENDING = "pending"               # En attente de traitement
    DELIVERED = "delivered"           # Livrée au destinataire
    RECEIVED = "received"             # Reçue par le destinataire
    ACCEPTED = "accepted"             # Acceptée
    REJECTED = "rejected"             # Rejetée
    PAID = "paid"                     # Payée
    ERROR = "error"                   # Erreur technique


class InvoiceDirection(str, Enum):
    """Direction de la facture."""
    OUTGOING = "outgoing"  # Facture émise (client)
    INCOMING = "incoming"  # Facture reçue (fournisseur)


@dataclass
class PDPConfig:
    """Configuration PDP."""
    provider: PDPProvider
    api_url: str
    api_key: str
    api_secret: Optional[str] = None
    client_id: Optional[str] = None
    environment: str = "sandbox"  # sandbox ou production
    timeout: int = 30
    retry_count: int = 3
    webhook_url: Optional[str] = None
    extra_config: dict = field(default_factory=dict)


@dataclass
class PDPInvoice:
    """Facture pour envoi PDP."""
    id: UUID
    invoice_number: str
    issue_date: datetime
    seller_siret: str
    buyer_siret: str
    buyer_siren: Optional[str] = None
    total_without_tax: float = 0.0
    total_tax: float = 0.0
    total_with_tax: float = 0.0
    currency: str = "EUR"
    pdf_content: Optional[bytes] = None
    xml_content: Optional[str] = None
    direction: InvoiceDirection = InvoiceDirection.OUTGOING
    metadata: dict = field(default_factory=dict)


@dataclass
class PDPResponse:
    """Réponse PDP."""
    success: bool
    pdp_id: Optional[str] = None         # ID attribué par la PDP
    status: InvoiceStatus = InvoiceStatus.DRAFT
    message: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    raw_response: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PDPStatusResponse:
    """Réponse statut PDP."""
    pdp_id: str
    status: InvoiceStatus
    status_date: Optional[datetime] = None
    recipient_status: Optional[str] = None  # Statut côté destinataire
    rejection_reason: Optional[str] = None
    lifecycle_events: list[dict] = field(default_factory=list)


class BasePDPClient(ABC):
    """Client PDP abstrait."""

    def __init__(self, config: PDPConfig):
        self.config = config
        self.http_client = httpx.AsyncClient(
            timeout=config.timeout,
            headers=self._build_headers()
        )

    def _build_headers(self) -> dict:
        """Construire les headers HTTP."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AZALPLUS/1.0"
        }

    @abstractmethod
    async def submit_invoice(self, invoice: PDPInvoice) -> PDPResponse:
        """Soumettre une facture à la PDP."""
        pass

    @abstractmethod
    async def get_status(self, pdp_id: str) -> PDPStatusResponse:
        """Obtenir le statut d'une facture."""
        pass

    @abstractmethod
    async def cancel_invoice(self, pdp_id: str, reason: str) -> PDPResponse:
        """Annuler une facture."""
        pass

    @abstractmethod
    async def list_invoices(
        self,
        direction: InvoiceDirection = InvoiceDirection.OUTGOING,
        status: Optional[InvoiceStatus] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> list[dict]:
        """Lister les factures."""
        pass

    async def health_check(self) -> bool:
        """Vérifier la connectivité PDP."""
        try:
            response = await self.http_client.get(f"{self.config.api_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"PDP health check failed: {e}")
            return False

    async def close(self):
        """Fermer le client HTTP."""
        await self.http_client.aclose()


class GenericPDPClient(BasePDPClient):
    """
    Client PDP générique pour API REST standard.

    Supporte les endpoints:
    - POST /invoices - Soumettre facture
    - GET /invoices/{id} - Obtenir statut
    - DELETE /invoices/{id} - Annuler
    - GET /invoices - Lister
    """

    def _build_headers(self) -> dict:
        headers = super()._build_headers()
        headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.client_id:
            headers["X-Client-ID"] = self.config.client_id
        return headers

    async def submit_invoice(self, invoice: PDPInvoice) -> PDPResponse:
        """Soumettre une facture."""
        try:
            # Préparer le payload
            payload = {
                "invoice_number": invoice.invoice_number,
                "issue_date": invoice.issue_date.isoformat(),
                "seller_siret": invoice.seller_siret,
                "buyer_siret": invoice.buyer_siret,
                "total_ht": invoice.total_without_tax,
                "total_tva": invoice.total_tax,
                "total_ttc": invoice.total_with_tax,
                "currency": invoice.currency,
                "direction": invoice.direction.value,
                "metadata": invoice.metadata
            }

            # Ajouter PDF en base64 si présent
            if invoice.pdf_content:
                import base64
                payload["pdf_base64"] = base64.b64encode(invoice.pdf_content).decode()

            # Ajouter XML si présent
            if invoice.xml_content:
                payload["xml_content"] = invoice.xml_content

            # Envoyer
            response = await self.http_client.post(
                f"{self.config.api_url}/invoices",
                json=payload
            )

            if response.status_code in (200, 201):
                data = response.json()
                return PDPResponse(
                    success=True,
                    pdp_id=data.get("id") or data.get("pdp_id"),
                    status=InvoiceStatus(data.get("status", "submitted")),
                    message="Facture soumise avec succès",
                    raw_response=data
                )
            else:
                error_data = response.json() if response.content else {}
                return PDPResponse(
                    success=False,
                    status=InvoiceStatus.ERROR,
                    message=error_data.get("message", f"Erreur HTTP {response.status_code}"),
                    errors=error_data.get("errors", []),
                    raw_response=error_data
                )

        except Exception as e:
            logger.error(f"Erreur soumission PDP: {e}")
            return PDPResponse(
                success=False,
                status=InvoiceStatus.ERROR,
                message=str(e),
                errors=[str(e)]
            )

    async def get_status(self, pdp_id: str) -> PDPStatusResponse:
        """Obtenir le statut d'une facture."""
        try:
            response = await self.http_client.get(
                f"{self.config.api_url}/invoices/{pdp_id}"
            )

            if response.status_code == 200:
                data = response.json()
                return PDPStatusResponse(
                    pdp_id=pdp_id,
                    status=InvoiceStatus(data.get("status", "pending")),
                    status_date=datetime.fromisoformat(data["status_date"]) if data.get("status_date") else None,
                    recipient_status=data.get("recipient_status"),
                    rejection_reason=data.get("rejection_reason"),
                    lifecycle_events=data.get("lifecycle_events", [])
                )
            else:
                return PDPStatusResponse(
                    pdp_id=pdp_id,
                    status=InvoiceStatus.ERROR
                )

        except Exception as e:
            logger.error(f"Erreur statut PDP: {e}")
            return PDPStatusResponse(
                pdp_id=pdp_id,
                status=InvoiceStatus.ERROR
            )

    async def cancel_invoice(self, pdp_id: str, reason: str) -> PDPResponse:
        """Annuler une facture."""
        try:
            response = await self.http_client.delete(
                f"{self.config.api_url}/invoices/{pdp_id}",
                json={"reason": reason}
            )

            if response.status_code in (200, 204):
                return PDPResponse(
                    success=True,
                    pdp_id=pdp_id,
                    status=InvoiceStatus.REJECTED,
                    message="Facture annulée"
                )
            else:
                error_data = response.json() if response.content else {}
                return PDPResponse(
                    success=False,
                    pdp_id=pdp_id,
                    status=InvoiceStatus.ERROR,
                    message=error_data.get("message", f"Erreur annulation"),
                    errors=error_data.get("errors", [])
                )

        except Exception as e:
            logger.error(f"Erreur annulation PDP: {e}")
            return PDPResponse(
                success=False,
                pdp_id=pdp_id,
                status=InvoiceStatus.ERROR,
                message=str(e)
            )

    async def list_invoices(
        self,
        direction: InvoiceDirection = InvoiceDirection.OUTGOING,
        status: Optional[InvoiceStatus] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> list[dict]:
        """Lister les factures."""
        try:
            params = {
                "direction": direction.value,
                "page": page,
                "page_size": page_size
            }
            if status:
                params["status"] = status.value
            if from_date:
                params["from_date"] = from_date.isoformat()
            if to_date:
                params["to_date"] = to_date.isoformat()

            response = await self.http_client.get(
                f"{self.config.api_url}/invoices",
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("invoices", data.get("items", []))
            else:
                return []

        except Exception as e:
            logger.error(f"Erreur liste PDP: {e}")
            return []


class CegidPDPClient(BasePDPClient):
    """Client spécifique CEGID."""

    def _build_headers(self) -> dict:
        headers = super()._build_headers()
        # Auth CEGID spécifique
        headers["X-API-Key"] = self.config.api_key
        if self.config.api_secret:
            headers["X-API-Secret"] = self.config.api_secret
        return headers

    async def submit_invoice(self, invoice: PDPInvoice) -> PDPResponse:
        """Soumettre à CEGID."""
        # Format CEGID spécifique
        payload = {
            "document": {
                "type": "FACTURE",
                "numero": invoice.invoice_number,
                "date": invoice.issue_date.strftime("%Y-%m-%d"),
                "emetteur": {"siret": invoice.seller_siret},
                "destinataire": {"siret": invoice.buyer_siret},
                "montants": {
                    "ht": invoice.total_without_tax,
                    "tva": invoice.total_tax,
                    "ttc": invoice.total_with_tax
                },
                "devise": invoice.currency
            }
        }

        if invoice.pdf_content:
            import base64
            payload["document"]["pdf"] = base64.b64encode(invoice.pdf_content).decode()

        if invoice.xml_content:
            payload["document"]["facturx"] = invoice.xml_content

        try:
            response = await self.http_client.post(
                f"{self.config.api_url}/v1/documents/invoices",
                json=payload
            )

            if response.status_code in (200, 201, 202):
                data = response.json()
                return PDPResponse(
                    success=True,
                    pdp_id=data.get("documentId"),
                    status=InvoiceStatus.SUBMITTED,
                    message="Document transmis à CEGID",
                    raw_response=data
                )
            else:
                data = response.json() if response.content else {}
                return PDPResponse(
                    success=False,
                    status=InvoiceStatus.ERROR,
                    message=data.get("error", {}).get("message", "Erreur CEGID"),
                    errors=data.get("error", {}).get("details", []),
                    raw_response=data
                )

        except Exception as e:
            logger.error(f"Erreur CEGID: {e}")
            return PDPResponse(success=False, status=InvoiceStatus.ERROR, message=str(e))

    async def get_status(self, pdp_id: str) -> PDPStatusResponse:
        """Statut CEGID."""
        try:
            response = await self.http_client.get(
                f"{self.config.api_url}/v1/documents/{pdp_id}/status"
            )

            if response.status_code == 200:
                data = response.json()
                status_map = {
                    "EN_COURS": InvoiceStatus.PENDING,
                    "TRANSMIS": InvoiceStatus.DELIVERED,
                    "ACCEPTE": InvoiceStatus.ACCEPTED,
                    "REFUSE": InvoiceStatus.REJECTED,
                    "ERREUR": InvoiceStatus.ERROR
                }
                return PDPStatusResponse(
                    pdp_id=pdp_id,
                    status=status_map.get(data.get("statut"), InvoiceStatus.PENDING),
                    status_date=datetime.fromisoformat(data["dateStatut"]) if data.get("dateStatut") else None,
                    rejection_reason=data.get("motifRefus"),
                    lifecycle_events=data.get("historique", [])
                )

            return PDPStatusResponse(pdp_id=pdp_id, status=InvoiceStatus.ERROR)

        except Exception as e:
            logger.error(f"Erreur statut CEGID: {e}")
            return PDPStatusResponse(pdp_id=pdp_id, status=InvoiceStatus.ERROR)

    async def cancel_invoice(self, pdp_id: str, reason: str) -> PDPResponse:
        """Annulation CEGID."""
        try:
            response = await self.http_client.post(
                f"{self.config.api_url}/v1/documents/{pdp_id}/cancel",
                json={"motif": reason}
            )

            if response.status_code in (200, 204):
                return PDPResponse(
                    success=True,
                    pdp_id=pdp_id,
                    status=InvoiceStatus.REJECTED,
                    message="Document annulé"
                )

            return PDPResponse(success=False, status=InvoiceStatus.ERROR)

        except Exception as e:
            return PDPResponse(success=False, status=InvoiceStatus.ERROR, message=str(e))

    async def list_invoices(
        self,
        direction: InvoiceDirection = InvoiceDirection.OUTGOING,
        status: Optional[InvoiceStatus] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> list[dict]:
        """Liste CEGID."""
        try:
            params = {
                "type": "FACTURE",
                "sens": "EMISSION" if direction == InvoiceDirection.OUTGOING else "RECEPTION",
                "page": page,
                "limite": page_size
            }

            response = await self.http_client.get(
                f"{self.config.api_url}/v1/documents",
                params=params
            )

            if response.status_code == 200:
                return response.json().get("documents", [])
            return []

        except Exception as e:
            logger.error(f"Erreur liste CEGID: {e}")
            return []


class PDPClient:
    """
    Client PDP principal avec sélection automatique du provider.

    Usage:
        config = PDPConfig(
            provider=PDPProvider.CEGID,
            api_url="https://api.cegid.com",
            api_key="xxx"
        )
        client = PDPClient(config)
        result = await client.submit_invoice(invoice)
    """

    def __init__(self, config: PDPConfig):
        self.config = config
        self._client = self._create_client(config)

    def _create_client(self, config: PDPConfig) -> BasePDPClient:
        """Créer le client approprié selon le provider."""
        if config.provider == PDPProvider.CEGID:
            return CegidPDPClient(config)
        # Autres providers à implémenter...
        # elif config.provider == PDPProvider.SAGE:
        #     return SagePDPClient(config)
        else:
            return GenericPDPClient(config)

    async def submit_invoice(self, invoice: PDPInvoice) -> PDPResponse:
        """Soumettre une facture."""
        return await self._client.submit_invoice(invoice)

    async def get_status(self, pdp_id: str) -> PDPStatusResponse:
        """Obtenir le statut."""
        return await self._client.get_status(pdp_id)

    async def cancel_invoice(self, pdp_id: str, reason: str) -> PDPResponse:
        """Annuler une facture."""
        return await self._client.cancel_invoice(pdp_id, reason)

    async def list_invoices(
        self,
        direction: InvoiceDirection = InvoiceDirection.OUTGOING,
        status: Optional[InvoiceStatus] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> list[dict]:
        """Lister les factures."""
        return await self._client.list_invoices(
            direction, status, from_date, to_date, page, page_size
        )

    async def health_check(self) -> bool:
        """Vérifier la connectivité."""
        return await self._client.health_check()

    async def close(self):
        """Fermer le client."""
        await self._client.close()

    # Context manager
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
