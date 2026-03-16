"""
AZALPLUS - Service Facturation Électronique Unifié
Gère l'émission et la réception des factures pour un tenant

Intégration AZALCOFFRE :
- Archivage automatique des factures émises/reçues
- Conservation légale 10 ans (NF Z42-013)
- Horodatage TSA RFC 3161
- Intégrité SHA-512
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from .generator import FacturXGenerator, FacturXProfile, FacturXResult
from .parser import FacturXParser, ParsedInvoice
from .xml_builder import InvoiceData, Party, Address, InvoiceLine

# Import AZALCOFFRE (optionnel - fonctionne sans)
try:
    from ..azalcoffre import ArchiveSync, ArchiveResult, ArchiveStatus
    AZALCOFFRE_AVAILABLE = True
except ImportError:
    AZALCOFFRE_AVAILABLE = False
    ArchiveSync = None
    ArchiveResult = None

logger = logging.getLogger(__name__)


class DestinationType(str, Enum):
    """Type de destinataire"""
    B2G = "B2G"  # Business to Government (Chorus Pro)
    B2B = "B2B"  # Business to Business (PPF/PDP)
    B2C = "B2C"  # Business to Consumer (Email/PDF)


class SendStatus(str, Enum):
    """Statut d'envoi"""
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PAID = "PAID"
    ERROR = "ERROR"


@dataclass
class TenantConfig:
    """Configuration facturation d'un tenant"""
    tenant_id: UUID
    siret: str
    tva_intra: str
    raison_sociale: str
    adresse_ligne1: str
    code_postal: str
    ville: str
    pays: str = "FR"
    email_facturation: str = ""
    profil_facturx: FacturXProfile = FacturXProfile.EN16931
    chorus_id_structure: Optional[int] = None
    # Archivage AZALCOFFRE
    archivage_actif: bool = True  # Archiver automatiquement dans AZALCOFFRE


@dataclass
class ArchiveInfo:
    """Informations d'archivage AZALCOFFRE"""
    archived: bool = False
    archive_id: Optional[UUID] = None
    hash_sha512: Optional[str] = None
    tsa_timestamp: Optional[str] = None
    expires_at: Optional[date] = None
    error_message: Optional[str] = None


@dataclass
class SendResult:
    """Résultat d'envoi de facture"""
    success: bool
    destination_type: DestinationType
    status: SendStatus
    invoice_id: Optional[str] = None
    external_id: Optional[str] = None  # ID chez Chorus/PPF
    pdf_content: Optional[bytes] = None
    xml_content: Optional[str] = None
    error_message: Optional[str] = None
    # Archivage AZALCOFFRE
    archive_info: Optional[ArchiveInfo] = None


class FacturationService:
    """
    Service unifié de facturation électronique.

    Gère:
    - Émission de factures (Factur-X)
    - Envoi selon destinataire (B2G/B2B/B2C)
    - Réception et parsing de factures
    - Suivi des statuts
    - Archivage automatique AZALCOFFRE (NF Z42-013)
    """

    def __init__(self, tenant_config: TenantConfig):
        self.config = tenant_config
        self.generator = FacturXGenerator(profile=tenant_config.profil_facturx)
        self.parser = FacturXParser()

        # Archivage AZALCOFFRE (optionnel)
        self._archive_sync: Optional[ArchiveSync] = None
        if AZALCOFFRE_AVAILABLE and tenant_config.archivage_actif:
            try:
                self._archive_sync = ArchiveSync()
                if not self._archive_sync.is_available():
                    logger.warning("AZALCOFFRE non disponible - archivage désactivé")
                    self._archive_sync = None
            except Exception as e:
                logger.warning(f"Erreur init AZALCOFFRE: {e}")
                self._archive_sync = None

    @property
    def archivage_disponible(self) -> bool:
        """Vérifie si l'archivage AZALCOFFRE est disponible"""
        return self._archive_sync is not None

    def detect_destination_type(self, siret_destinataire: str) -> DestinationType:
        """
        Détecte le type de destinataire selon le SIRET.

        - SIRET commençant par 1 ou 2 → Secteur public (B2G)
        - Autres → Entreprise privée (B2B)
        - Pas de SIRET → Particulier (B2C)
        """
        if not siret_destinataire:
            return DestinationType.B2C

        # Les SIRET du secteur public commencent par 1 ou 2
        # (simplification - en réalité il faut consulter l'annuaire)
        first_digit = siret_destinataire[0] if siret_destinataire else ""
        if first_digit in ("1", "2"):
            return DestinationType.B2G

        return DestinationType.B2B

    def create_invoice_data(
        self,
        numero_facture: str,
        date_facture: date,
        destinataire_siret: str,
        destinataire_nom: str,
        destinataire_adresse: str,
        destinataire_cp: str,
        destinataire_ville: str,
        lignes: list[dict],
        destinataire_tva: Optional[str] = None,
        destinataire_email: Optional[str] = None,
    ) -> InvoiceData:
        """Crée les données de facture depuis les paramètres"""

        # Calculer les totaux
        total_ht = Decimal("0")
        total_tva = Decimal("0")
        invoice_lines = []

        for i, ligne in enumerate(lignes, 1):
            qty = Decimal(str(ligne.get("quantite", 1)))
            prix = Decimal(str(ligne.get("prix_unitaire", 0)))
            taux_tva = Decimal(str(ligne.get("taux_tva", 20)))

            montant_ht = qty * prix
            montant_tva = montant_ht * taux_tva / 100

            total_ht += montant_ht
            total_tva += montant_tva

            invoice_lines.append(InvoiceLine(
                line_id=str(i),
                description=ligne.get("description", ""),
                quantity=qty,
                unit_price=prix,
                vat_rate=taux_tva,
                line_total=montant_ht,
            ))

        total_ttc = total_ht + total_tva

        return InvoiceData(
            invoice_number=numero_facture,
            invoice_date=date_facture,
            seller=Party(
                name=self.config.raison_sociale,
                siret=self.config.siret,
                tva_intra=self.config.tva_intra,
                address=Address(
                    line1=self.config.adresse_ligne1,
                    city=self.config.ville,
                    postal_code=self.config.code_postal,
                    country_code=self.config.pays,
                ),
                email=self.config.email_facturation,
            ),
            buyer=Party(
                name=destinataire_nom,
                siret=destinataire_siret,
                tva_intra=destinataire_tva,
                address=Address(
                    line1=destinataire_adresse,
                    city=destinataire_ville,
                    postal_code=destinataire_cp,
                    country_code="FR",
                ),
                email=destinataire_email,
            ),
            lines=invoice_lines,
            total_ht=total_ht,
            total_tva=total_tva,
            total_ttc=total_ttc,
            currency_code="EUR",
        )

    def generate_facturx(
        self,
        pdf_source: bytes,
        invoice_data: InvoiceData,
    ) -> FacturXResult:
        """Génère un PDF Factur-X"""
        return self.generator.generate(pdf_source, invoice_data)

    def send_invoice(
        self,
        pdf_content: bytes,
        invoice_data: InvoiceData,
        siret_destinataire: str,
        invoice_id: Optional[UUID] = None,
    ) -> SendResult:
        """
        Envoie une facture selon le type de destinataire.

        - B2G → Chorus Pro
        - B2B → PPF (à implémenter)
        - B2C → Email (à implémenter)

        Après envoi réussi, archive automatiquement dans AZALCOFFRE.
        """
        destination = self.detect_destination_type(siret_destinataire)

        if destination == DestinationType.B2G:
            result = self._send_chorus_pro(pdf_content, invoice_data)
        elif destination == DestinationType.B2B:
            result = self._send_ppf(pdf_content, invoice_data)
        else:
            result = self._send_email(pdf_content, invoice_data)

        # Archivage automatique AZALCOFFRE après envoi réussi
        if result.success and self._archive_sync and invoice_id:
            archive_info = self._archive_invoice(
                invoice_id=invoice_id,
                invoice_data=invoice_data,
                pdf_content=pdf_content,
                is_received=False,
            )
            result.archive_info = archive_info

        return result

    def _send_chorus_pro(
        self,
        pdf_content: bytes,
        invoice_data: InvoiceData,
    ) -> SendResult:
        """Envoie via Chorus Pro (B2G)"""
        try:
            from ..chorus_pro import ChorusProClient

            with ChorusProClient() as client:
                # Vérifier que la connexion fonctionne
                if not client.health_check():
                    return SendResult(
                        success=False,
                        destination_type=DestinationType.B2G,
                        status=SendStatus.ERROR,
                        error_message="Connexion Chorus Pro impossible",
                    )

                # TODO: Soumettre la facture quand l'API sera disponible
                # Pour l'instant, on retourne un statut "pending"
                return SendResult(
                    success=True,
                    destination_type=DestinationType.B2G,
                    status=SendStatus.PENDING,
                    invoice_id=invoice_data.invoice_number,
                    pdf_content=pdf_content,
                    xml_content=None,  # Sera extrait du PDF
                )

        except Exception as e:
            logger.error(f"Erreur envoi Chorus Pro: {e}")
            return SendResult(
                success=False,
                destination_type=DestinationType.B2G,
                status=SendStatus.ERROR,
                error_message=str(e),
            )

    def _send_ppf(
        self,
        pdf_content: bytes,
        invoice_data: InvoiceData,
    ) -> SendResult:
        """Envoie via PPF (B2B) - À implémenter"""
        # PPF sera disponible en septembre 2026
        # Pour l'instant, on génère juste le Factur-X
        return SendResult(
            success=True,
            destination_type=DestinationType.B2B,
            status=SendStatus.DRAFT,
            invoice_id=invoice_data.invoice_number,
            pdf_content=pdf_content,
            error_message="PPF non encore disponible - Factur-X généré pour envoi manuel",
        )

    def _send_email(
        self,
        pdf_content: bytes,
        invoice_data: InvoiceData,
    ) -> SendResult:
        """Envoie par email (B2C) - À implémenter"""
        return SendResult(
            success=True,
            destination_type=DestinationType.B2C,
            status=SendStatus.DRAFT,
            invoice_id=invoice_data.invoice_number,
            pdf_content=pdf_content,
            error_message="Envoi email à implémenter",
        )

    def receive_invoice(
        self,
        pdf_content: bytes,
        invoice_id: Optional[UUID] = None,
    ) -> tuple[ParsedInvoice, Optional[ArchiveInfo]]:
        """
        Parse une facture Factur-X reçue et l'archive dans AZALCOFFRE.

        Args:
            pdf_content: Contenu du PDF Factur-X
            invoice_id: ID de la facture (pour archivage)

        Returns:
            Tuple (ParsedInvoice, ArchiveInfo optionnel)
        """
        parsed = self.parser.parse(pdf_content)

        # Archivage automatique AZALCOFFRE
        archive_info = None
        if self._archive_sync and invoice_id:
            archive_info = self._archive_received_invoice(
                invoice_id=invoice_id,
                parsed=parsed,
                pdf_content=pdf_content,
            )

        return parsed, archive_info

    def receive_invoice_xml(self, xml_content: str) -> ParsedInvoice:
        """Parse un XML Factur-X directement"""
        return self.parser.parse_xml(xml_content)

    # === ARCHIVAGE AZALCOFFRE ===

    def _archive_invoice(
        self,
        invoice_id: UUID,
        invoice_data: InvoiceData,
        pdf_content: bytes,
        is_received: bool,
    ) -> ArchiveInfo:
        """Archive une facture émise dans AZALCOFFRE"""
        if not self._archive_sync:
            return ArchiveInfo(archived=False, error_message="AZALCOFFRE non configuré")

        try:
            result = self._archive_sync.archive_invoice_sent(
                tenant_id=self.config.tenant_id,
                invoice_id=invoice_id,
                invoice_number=invoice_data.invoice_number,
                invoice_date=invoice_data.invoice_date,
                pdf_content=pdf_content,
                seller_name=invoice_data.seller.name,
                seller_siret=invoice_data.seller.siret or "",
                buyer_name=invoice_data.buyer.name,
                buyer_siret=invoice_data.buyer.siret,
                amount_ht=invoice_data.total_ht,
                amount_ttc=invoice_data.total_ttc,
            )

            if result.success:
                # Calculer date expiration (10 ans)
                from datetime import timedelta
                expires = invoice_data.invoice_date + timedelta(days=365 * 10)

                return ArchiveInfo(
                    archived=True,
                    archive_id=result.archive_id,
                    hash_sha512=result.hash_sha512,
                    tsa_timestamp=result.tsa_timestamp,
                    expires_at=expires,
                )
            else:
                return ArchiveInfo(
                    archived=False,
                    error_message=result.error_message,
                )

        except Exception as e:
            logger.error(f"Erreur archivage facture {invoice_id}: {e}")
            return ArchiveInfo(archived=False, error_message=str(e))

    def _archive_received_invoice(
        self,
        invoice_id: UUID,
        parsed: ParsedInvoice,
        pdf_content: bytes,
    ) -> ArchiveInfo:
        """Archive une facture reçue dans AZALCOFFRE"""
        if not self._archive_sync:
            return ArchiveInfo(archived=False, error_message="AZALCOFFRE non configuré")

        try:
            result = self._archive_sync.archive_invoice_received(
                tenant_id=self.config.tenant_id,
                invoice_id=invoice_id,
                invoice_number=parsed.invoice_number,
                invoice_date=parsed.invoice_date,
                pdf_content=pdf_content,
                seller_name=parsed.seller.name if parsed.seller else "",
                seller_siret=parsed.seller.siret if parsed.seller else "",
                buyer_name=parsed.buyer.name if parsed.buyer else self.config.raison_sociale,
                buyer_siret=parsed.buyer.siret if parsed.buyer else self.config.siret,
                amount_ht=parsed.total_ht,
                amount_ttc=parsed.total_ttc,
            )

            if result.success:
                from datetime import timedelta
                expires = parsed.invoice_date + timedelta(days=365 * 10)

                return ArchiveInfo(
                    archived=True,
                    archive_id=result.archive_id,
                    hash_sha512=result.hash_sha512,
                    expires_at=expires,
                )
            else:
                return ArchiveInfo(archived=False, error_message=result.error_message)

        except Exception as e:
            logger.error(f"Erreur archivage facture reçue {invoice_id}: {e}")
            return ArchiveInfo(archived=False, error_message=str(e))

    def get_archive_info(self, invoice_id: UUID) -> Optional[ArchiveInfo]:
        """
        Récupère les informations d'archivage d'une facture.

        Utile pour afficher le statut d'archivage dans l'UI AZALPLUS.
        """
        if not self._archive_sync:
            return None

        try:
            doc = self._archive_sync.get_archive_info(
                tenant_id=self.config.tenant_id,
                source_id=invoice_id,
            )

            if doc:
                return ArchiveInfo(
                    archived=True,
                    archive_id=doc.id,
                    hash_sha512=doc.integrity_proof.hash_value if doc.integrity_proof else None,
                    tsa_timestamp=str(doc.integrity_proof.tsa_timestamp) if doc.integrity_proof else None,
                    expires_at=doc.expires_at,
                )
            return None

        except Exception as e:
            logger.error(f"Erreur récupération archive {invoice_id}: {e}")
            return None

    def download_archived_invoice(self, archive_id: UUID) -> Optional[bytes]:
        """Télécharge le PDF original depuis AZALCOFFRE"""
        if not self._archive_sync:
            return None

        try:
            return self._archive_sync.download_original(
                tenant_id=self.config.tenant_id,
                archive_id=archive_id,
            )
        except Exception as e:
            logger.error(f"Erreur téléchargement archive {archive_id}: {e}")
            return None

    def get_integrity_certificate(self, archive_id: UUID) -> Optional[bytes]:
        """
        Génère un certificat d'intégrité PDF.

        Attestation de :
        - Authenticité de l'origine
        - Intégrité du contenu
        - Horodatage certifié

        Utile pour contrôles fiscaux et audits.
        """
        if not self._archive_sync:
            return None

        try:
            return self._archive_sync.get_integrity_certificate(
                tenant_id=self.config.tenant_id,
                archive_id=archive_id,
            )
        except Exception as e:
            logger.error(f"Erreur génération certificat {archive_id}: {e}")
            return None
