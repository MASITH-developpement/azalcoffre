# =============================================================================
# AZALPLUS - Service d'intégration AZALCOFFRE
# =============================================================================
"""
Service métier pour l'intégration AZALCOFFRE.
S'intègre avec l'EventBus AZALPLUS pour réagir aux événements.
"""

import os
import logging
from typing import Optional
from uuid import UUID

from .client import AzalCoffreClient, AzalCoffreConfig

logger = logging.getLogger(__name__)


class AzalCoffreService:
    """
    Service d'intégration avec AZALCOFFRE.

    Gère:
    - Archivage automatique des documents générés
    - Signatures électroniques
    - Transmission PDP des factures
    - OCR des documents entrants

    Usage:
        service = AzalCoffreService.from_env()

        # Archiver une facture après génération
        result = await service.archive_invoice(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            pdf_content=pdf_bytes
        )

        # Demander signature d'un devis
        result = await service.request_quote_signature(
            tenant_id=tenant_id,
            quote_id=quote_id,
            client_email="client@example.com"
        )
    """

    def __init__(self, client: AzalCoffreClient, tenant_id: Optional[UUID] = None):
        self.client = client
        self.tenant_id = tenant_id

    @classmethod
    def from_env(cls, tenant_id: Optional[UUID] = None) -> "AzalCoffreService":
        """
        Crée un service depuis les variables d'environnement.

        Variables:
            AZALCOFFRE_URL: URL de l'API (défaut: https://api.azalcoffre.com)
            AZALCOFFRE_API_KEY: Clé API (sk_live_xxx ou sk_sandbox_xxx)
            AZALCOFFRE_TENANT_ID: UUID du tenant AZALCOFFRE
            AZALCOFFRE_TIMEOUT: Timeout en secondes (défaut: 30)
            AZALCOFFRE_VERIFY_SSL: Vérifier SSL (défaut: true)
        """
        config = AzalCoffreConfig(
            base_url=os.getenv("AZALCOFFRE_URL", "https://api.azalcoffre.com"),
            api_key=os.getenv("AZALCOFFRE_API_KEY", ""),
            tenant_id=os.getenv("AZALCOFFRE_TENANT_ID", str(tenant_id) if tenant_id else ""),
            timeout=int(os.getenv("AZALCOFFRE_TIMEOUT", "30")),
            verify_ssl=os.getenv("AZALCOFFRE_VERIFY_SSL", "true").lower() == "true"
        )
        client = AzalCoffreClient(config)
        return cls(client, tenant_id)

    async def close(self):
        """Ferme les connexions."""
        await self.client.close()

    # =========================================================================
    # ARCHIVAGE DOCUMENTS
    # =========================================================================

    async def archive_invoice(
        self,
        invoice_id: str,
        invoice_number: str,
        pdf_content: bytes,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Archive une facture dans le coffre-fort.

        Endpoint utilisé: POST /api/v1/documents/upload

        Args:
            invoice_id: ID de la facture AZALPLUS
            invoice_number: Numéro de facture
            pdf_content: Contenu PDF
            metadata: Métadonnées additionnelles

        Returns:
            dict avec id, hash_sha256, tsa_timestamp
        """
        full_metadata = {
            "source": "AZALPLUS",
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "retention_years": 10,  # Obligation légale factures
            **(metadata or {})
        }

        result = await self.client.upload_document(
            file_content=pdf_content,
            filename=f"FAC_{invoice_number}.pdf",
            document_type="FACTURE",
            metadata=full_metadata,
            encrypt=False  # Les factures doivent rester accessibles
        )

        logger.info(
            f"Facture {invoice_number} archivée",
            extra={
                "invoice_id": invoice_id,
                "document_id": result.get("id"),
                "hash": result.get("hash_sha256")
            }
        )

        return result

    async def archive_quote(
        self,
        quote_id: str,
        quote_number: str,
        pdf_content: bytes,
        metadata: Optional[dict] = None
    ) -> dict:
        """Archive un devis dans le coffre-fort."""
        full_metadata = {
            "source": "AZALPLUS",
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "quote_id": quote_id,
            "quote_number": quote_number,
            "retention_years": 5,
            **(metadata or {})
        }

        return await self.client.upload_document(
            file_content=pdf_content,
            filename=f"DEV_{quote_number}.pdf",
            document_type="DEVIS",
            metadata=full_metadata,
            encrypt=False
        )

    async def archive_contract(
        self,
        contract_id: str,
        contract_number: str,
        pdf_content: bytes,
        encrypt: bool = True,
        metadata: Optional[dict] = None
    ) -> dict:
        """Archive un contrat dans le coffre-fort (chiffré par défaut)."""
        full_metadata = {
            "source": "AZALPLUS",
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "contract_id": contract_id,
            "contract_number": contract_number,
            "retention_years": 10,
            **(metadata or {})
        }

        return await self.client.upload_document(
            file_content=pdf_content,
            filename=f"CONTRAT_{contract_number}.pdf",
            document_type="CONTRAT",
            metadata=full_metadata,
            encrypt=encrypt
        )

    # =========================================================================
    # SIGNATURES ÉLECTRONIQUES
    # =========================================================================

    async def request_quote_signature(
        self,
        quote_id: str,
        document_id: str,
        client_email: str,
        client_name: str,
        message: Optional[str] = None
    ) -> dict:
        """
        Demande la signature électronique d'un devis par le client.

        Args:
            quote_id: ID du devis AZALPLUS
            document_id: ID du document dans AZALCOFFRE
            client_email: Email du client
            client_name: Nom du client
            message: Message personnalisé

        Returns:
            dict avec signature_request_id, signing_url
        """
        signers = [
            {
                "email": client_email,
                "name": client_name,
                "order": 1
            }
        ]

        result = await self.client.request_signature(
            document_id=document_id,
            signers=signers,
            signature_level="SIMPLE",  # Code SMS/email
            expiration_hours=72,
            message=message or f"Merci de signer le devis pour confirmer votre accord."
        )

        logger.info(
            f"Signature demandée pour devis",
            extra={
                "quote_id": quote_id,
                "signature_request_id": result.get("signature_request_id"),
                "client_email": client_email
            }
        )

        return result

    async def request_contract_signature(
        self,
        contract_id: str,
        document_id: str,
        signers: list[dict],
        signature_level: str = "ADVANCED"
    ) -> dict:
        """
        Demande la signature d'un contrat (multi-signataires possible).

        Args:
            contract_id: ID du contrat AZALPLUS
            document_id: ID du document AZALCOFFRE
            signers: Liste [{"email": "...", "name": "...", "order": 1}]
            signature_level: SIMPLE, ADVANCED, QUALIFIED

        Returns:
            dict avec signature_request_id, signing_urls
        """
        result = await self.client.request_signature(
            document_id=document_id,
            signers=signers,
            signature_level=signature_level,
            expiration_hours=168,  # 7 jours pour les contrats
            message="Merci de signer ce contrat."
        )

        logger.info(
            f"Signature contrat demandée",
            extra={
                "contract_id": contract_id,
                "signature_request_id": result.get("signature_request_id"),
                "signers_count": len(signers)
            }
        )

        return result

    # =========================================================================
    # FACTURATION ÉLECTRONIQUE PDP
    # =========================================================================

    async def submit_invoice_to_pdp(
        self,
        invoice_id: str,
        invoice_data: dict,
        pdf_content: Optional[bytes] = None
    ) -> dict:
        """
        Soumet une facture au Portail Public de Facturation.

        Endpoints utilisés:
        - POST /api/v1/invoices/create ou /create-with-pdf
        - POST /api/v1/invoices/{id}/send

        Args:
            invoice_id: ID facture AZALPLUS
            invoice_data: Données structurées de la facture
            pdf_content: PDF (optionnel)

        Returns:
            dict avec id, status
        """
        # Enrichir les données avec le contexte AZALPLUS
        invoice_data["metadata"] = {
            "source": "AZALPLUS",
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "original_invoice_id": invoice_id
        }

        # 1. Créer la facture Factur-X
        if pdf_content:
            result = await self.client.create_invoice_with_pdf(
                invoice_data=invoice_data,
                pdf_content=pdf_content,
                profile="EN16931"
            )
        else:
            result = await self.client.create_invoice(
                invoice_data=invoice_data,
                profile="EN16931"
            )

        coffre_invoice_id = result.get("id")

        # 2. Envoyer au PPF
        send_result = await self.client.send_invoice_to_ppf(coffre_invoice_id)

        logger.info(
            f"Facture soumise au PPF",
            extra={
                "invoice_id": invoice_id,
                "coffre_invoice_id": coffre_invoice_id,
                "status": send_result.get("status")
            }
        )

        return {
            "id": coffre_invoice_id,
            "status": send_result.get("status"),
            "ppf_status": send_result.get("ppf_status"),
            **result
        }

    async def check_pdp_status(self, invoice_id: str) -> dict:
        """Vérifie le statut d'une facture PDP."""
        return await self.client.get_invoice(invoice_id)

    # =========================================================================
    # FACTURES ENTRANTES
    # =========================================================================

    async def receive_incoming_invoice(
        self,
        file_content: bytes,
        filename: str
    ) -> dict:
        """
        Reçoit et parse une facture Factur-X entrante.

        Endpoint utilisé: POST /api/v1/invoices/receive

        L'OCR et l'extraction de données sont gérés côté AZALCOFFRE.

        Retourne:
        - Données de la facture parsée
        - XML Factur-X extrait
        """
        result = await self.client.receive_invoice(file_content)

        logger.info(
            f"Facture entrante reçue",
            extra={
                "filename": filename,
                "invoice_id": result.get("id"),
                "status": result.get("status")
            }
        )

        return result

    # =========================================================================
    # HEALTH
    # =========================================================================

    async def is_available(self) -> bool:
        """Vérifie si AZALCOFFRE est disponible."""
        try:
            await self.client.health_check()
            return True
        except Exception as e:
            logger.warning(f"AZALCOFFRE indisponible: {e}")
            return False
