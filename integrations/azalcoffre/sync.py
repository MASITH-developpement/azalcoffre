"""
AZALPLUS - Synchronisation automatique avec AZALCOFFRE
Archive automatiquement les factures émises/reçues
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Callable, Any
from uuid import UUID

from .client import AzalCoffreClient, AzalCoffreError
from .models import (
    ArchivedDocument,
    ArchiveRequest,
    ArchiveStatus,
    DocumentType,
    IntegrityProof,
)
from ..settings import get_settings, AzalCoffreSettings

logger = logging.getLogger(__name__)


@dataclass
class ArchiveResult:
    """Résultat d'une opération d'archivage"""
    success: bool
    archive_id: Optional[UUID] = None
    status: ArchiveStatus = ArchiveStatus.PENDING
    hash_sha512: Optional[str] = None
    tsa_timestamp: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_archived(self) -> bool:
        return self.success and self.status in (
            ArchiveStatus.ARCHIVED,
            ArchiveStatus.VERIFIED,
        )


class ArchiveSync:
    """
    Service de synchronisation automatique AZALPLUS → AZALCOFFRE.

    Utilisé comme hook après création/envoi de factures pour
    archiver automatiquement dans le coffre-fort légal.

    Utilise la configuration centralisée depuis settings.py
    """

    def __init__(self, settings: Optional[AzalCoffreSettings] = None):
        self._settings = settings or get_settings().azalcoffre
        self._client: Optional[AzalCoffreClient] = None

    def _get_client(self) -> AzalCoffreClient:
        """Lazy loading du client"""
        if self._client is None:
            self._client = AzalCoffreClient(self._settings)
        return self._client

    def is_available(self) -> bool:
        """Vérifie si AZALCOFFRE est disponible et configuré"""
        try:
            if not self._settings.is_configured:
                return False
            return self._get_client().health_check()
        except Exception:
            return False

    # === ARCHIVAGE FACTURES ===

    def archive_invoice_sent(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        invoice_number: str,
        invoice_date: date,
        pdf_content: bytes,
        seller_name: str,
        seller_siret: str,
        buyer_name: str,
        buyer_siret: Optional[str],
        amount_ht: Decimal,
        amount_ttc: Decimal,
    ) -> ArchiveResult:
        """
        Archive une facture émise.

        Appelé automatiquement après envoi réussi d'une facture.
        Le PDF Factur-X est archivé avec horodatage TSA.

        Args:
            tenant_id: ID du tenant
            invoice_id: ID de la facture dans AZALPLUS
            invoice_number: Numéro de facture (FA-2026-001)
            invoice_date: Date de facture
            pdf_content: PDF Factur-X généré
            seller_name: Nom du vendeur
            seller_siret: SIRET du vendeur
            buyer_name: Nom de l'acheteur
            buyer_siret: SIRET de l'acheteur (optionnel B2C)
            amount_ht: Montant HT
            amount_ttc: Montant TTC

        Returns:
            ArchiveResult avec preuve d'archivage
        """
        try:
            request = ArchiveRequest(
                tenant_id=tenant_id,
                source_id=invoice_id,
                source_type=DocumentType.FACTURE_EMISE,
                document_number=invoice_number,
                document_date=invoice_date,
                file_content=pdf_content,
                file_name=f"{invoice_number}.pdf",
                mime_type="application/pdf",
                emitter_name=seller_name,
                emitter_siret=seller_siret,
                recipient_name=buyer_name,
                recipient_siret=buyer_siret,
                amount_ht=amount_ht,
                amount_ttc=amount_ttc,
                retention_years=10,  # Légal factures
                request_tsa=True,
            )

            doc = self._get_client().archive_document(request)

            logger.info(
                f"Facture archivée: {invoice_number} -> {doc.id}",
                extra={
                    "tenant_id": str(tenant_id),
                    "invoice_id": str(invoice_id),
                    "archive_id": str(doc.id),
                },
            )

            return ArchiveResult(
                success=True,
                archive_id=doc.id,
                status=doc.status,
                hash_sha512=doc.integrity_proof.hash_value if doc.integrity_proof else None,
                tsa_timestamp=str(doc.integrity_proof.tsa_timestamp) if doc.integrity_proof else None,
            )

        except AzalCoffreError as e:
            logger.error(f"Erreur archivage facture {invoice_number}: {e}")
            return ArchiveResult(
                success=False,
                status=ArchiveStatus.ERROR,
                error_message=str(e),
            )
        except Exception as e:
            logger.exception(f"Erreur inattendue archivage: {e}")
            return ArchiveResult(
                success=False,
                status=ArchiveStatus.ERROR,
                error_message=f"Erreur interne: {str(e)}",
            )

    def archive_invoice_received(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        invoice_number: str,
        invoice_date: date,
        pdf_content: bytes,
        seller_name: str,
        seller_siret: str,
        buyer_name: str,
        buyer_siret: str,
        amount_ht: Decimal,
        amount_ttc: Decimal,
    ) -> ArchiveResult:
        """
        Archive une facture reçue.

        Appelé automatiquement après réception via PDP/Chorus Pro.
        """
        try:
            request = ArchiveRequest(
                tenant_id=tenant_id,
                source_id=invoice_id,
                source_type=DocumentType.FACTURE_RECUE,
                document_number=invoice_number,
                document_date=invoice_date,
                file_content=pdf_content,
                file_name=f"RECU_{invoice_number}.pdf",
                mime_type="application/pdf",
                emitter_name=seller_name,
                emitter_siret=seller_siret,
                recipient_name=buyer_name,
                recipient_siret=buyer_siret,
                amount_ht=amount_ht,
                amount_ttc=amount_ttc,
                retention_years=10,
                request_tsa=True,
            )

            doc = self._get_client().archive_document(request)

            logger.info(f"Facture reçue archivée: {invoice_number} -> {doc.id}")

            return ArchiveResult(
                success=True,
                archive_id=doc.id,
                status=doc.status,
                hash_sha512=doc.integrity_proof.hash_value if doc.integrity_proof else None,
            )

        except Exception as e:
            logger.error(f"Erreur archivage facture reçue {invoice_number}: {e}")
            return ArchiveResult(
                success=False,
                status=ArchiveStatus.ERROR,
                error_message=str(e),
            )

    def archive_credit_note(
        self,
        tenant_id: UUID,
        credit_note_id: UUID,
        credit_note_number: str,
        credit_note_date: date,
        pdf_content: bytes,
        is_emitted: bool,
        **metadata,
    ) -> ArchiveResult:
        """Archive un avoir (émis ou reçu)"""
        source_type = DocumentType.AVOIR_EMIS if is_emitted else DocumentType.AVOIR_RECU

        try:
            request = ArchiveRequest(
                tenant_id=tenant_id,
                source_id=credit_note_id,
                source_type=source_type,
                document_number=credit_note_number,
                document_date=credit_note_date,
                file_content=pdf_content,
                file_name=f"{credit_note_number}.pdf",
                retention_years=10,
                request_tsa=True,
                **metadata,
            )

            doc = self._get_client().archive_document(request)

            return ArchiveResult(
                success=True,
                archive_id=doc.id,
                status=doc.status,
            )

        except Exception as e:
            logger.error(f"Erreur archivage avoir: {e}")
            return ArchiveResult(success=False, error_message=str(e))

    # === CONSULTATION ===

    def get_archive_info(
        self, tenant_id: UUID, source_id: UUID
    ) -> Optional[ArchivedDocument]:
        """
        Récupère les infos d'archivage pour une facture.

        Utilisé pour afficher le statut d'archivage dans AZALPLUS.
        """
        try:
            return self._get_client().get_document_by_source(tenant_id, source_id)
        except AzalCoffreError as e:
            if e.status_code == 404:
                return None
            raise

    def download_original(self, tenant_id: UUID, archive_id: UUID) -> bytes:
        """Télécharge le fichier original depuis AZALCOFFRE"""
        return self._get_client().download_document(tenant_id, archive_id)

    def verify_and_get_proof(
        self, tenant_id: UUID, archive_id: UUID
    ) -> IntegrityProof:
        """
        Vérifie l'intégrité et retourne la preuve.

        Utile pour audits et contrôles fiscaux.
        """
        return self._get_client().verify_integrity(tenant_id, archive_id)

    def get_integrity_certificate(
        self, tenant_id: UUID, archive_id: UUID
    ) -> bytes:
        """Génère le certificat d'intégrité PDF"""
        return self._get_client().get_integrity_certificate(tenant_id, archive_id)

    # === HOOK SYSTEM ===

    def create_archive_hook(
        self,
        on_success: Optional[Callable[[ArchiveResult], Any]] = None,
        on_error: Optional[Callable[[ArchiveResult], Any]] = None,
    ) -> Callable:
        """
        Crée un hook d'archivage pour les factures.

        Exemple d'utilisation dans le service de facturation :

        ```python
        archive_sync = ArchiveSync()
        archive_hook = archive_sync.create_archive_hook(
            on_success=lambda r: log.info(f"Archivé: {r.archive_id}"),
            on_error=lambda r: notify_admin(r.error_message),
        )

        # Après envoi facture
        archive_hook(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            invoice_number=invoice.numero,
            ...
        )
        ```
        """

        def hook(
            tenant_id: UUID,
            invoice_id: UUID,
            invoice_number: str,
            invoice_date: date,
            pdf_content: bytes,
            is_received: bool = False,
            **metadata,
        ) -> ArchiveResult:
            if is_received:
                result = self.archive_invoice_received(
                    tenant_id=tenant_id,
                    invoice_id=invoice_id,
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    pdf_content=pdf_content,
                    **metadata,
                )
            else:
                result = self.archive_invoice_sent(
                    tenant_id=tenant_id,
                    invoice_id=invoice_id,
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    pdf_content=pdf_content,
                    **metadata,
                )

            if result.success and on_success:
                on_success(result)
            elif not result.success and on_error:
                on_error(result)

            return result

        return hook


# === SINGLETON POUR USAGE GLOBAL ===

_archive_sync: Optional[ArchiveSync] = None


def get_archive_sync() -> ArchiveSync:
    """Retourne l'instance singleton de ArchiveSync"""
    global _archive_sync
    if _archive_sync is None:
        _archive_sync = ArchiveSync()
    return _archive_sync


def archive_invoice_after_send(
    tenant_id: UUID,
    invoice_id: UUID,
    invoice_number: str,
    invoice_date: date,
    pdf_content: bytes,
    seller_name: str,
    seller_siret: str,
    buyer_name: str,
    buyer_siret: Optional[str],
    amount_ht: Decimal,
    amount_ttc: Decimal,
) -> ArchiveResult:
    """
    Fonction utilitaire pour archiver après envoi.

    Usage simplifié sans instanciation explicite.
    """
    return get_archive_sync().archive_invoice_sent(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        pdf_content=pdf_content,
        seller_name=seller_name,
        seller_siret=seller_siret,
        buyer_name=buyer_name,
        buyer_siret=buyer_siret,
        amount_ht=amount_ht,
        amount_ttc=amount_ttc,
    )
