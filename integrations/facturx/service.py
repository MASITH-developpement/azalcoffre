"""
AZALPLUS - Service Facturation Électronique Unifié
Gère l'émission et la réception des factures pour un tenant
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from .generator import FacturXGenerator, FacturXProfile, FacturXResult
from .parser import FacturXParser, ParsedInvoice
from .xml_builder import InvoiceData, Party, Address, InvoiceLine

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


class FacturationService:
    """
    Service unifié de facturation électronique.

    Gère:
    - Émission de factures (Factur-X)
    - Envoi selon destinataire (B2G/B2B/B2C)
    - Réception et parsing de factures
    - Suivi des statuts
    """

    def __init__(self, tenant_config: TenantConfig):
        self.config = tenant_config
        self.generator = FacturXGenerator(profile=tenant_config.profil_facturx)
        self.parser = FacturXParser()

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
    ) -> SendResult:
        """
        Envoie une facture selon le type de destinataire.

        - B2G → Chorus Pro
        - B2B → PPF (à implémenter)
        - B2C → Email (à implémenter)
        """
        destination = self.detect_destination_type(siret_destinataire)

        if destination == DestinationType.B2G:
            return self._send_chorus_pro(pdf_content, invoice_data)
        elif destination == DestinationType.B2B:
            return self._send_ppf(pdf_content, invoice_data)
        else:
            return self._send_email(pdf_content, invoice_data)

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

    def receive_invoice(self, pdf_content: bytes) -> ParsedInvoice:
        """
        Parse une facture Factur-X reçue.

        Args:
            pdf_content: Contenu du PDF Factur-X

        Returns:
            ParsedInvoice avec les données extraites
        """
        return self.parser.parse(pdf_content)

    def receive_invoice_xml(self, xml_content: str) -> ParsedInvoice:
        """Parse un XML Factur-X directement"""
        return self.parser.parse_xml(xml_content)
