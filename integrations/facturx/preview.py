"""
AZALPLUS - Service de prévisualisation des factures
Génère un aperçu avant envoi
"""

import base64
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from uuid import UUID

logger = logging.getLogger(__name__)


class SendOption(str, Enum):
    """Options d'envoi disponibles"""
    EMAIL = "EMAIL"           # Envoi par email uniquement
    DEMAT = "DEMAT"           # Envoi dématérialisé uniquement (PDP/Chorus)
    EMAIL_AND_DEMAT = "EMAIL_AND_DEMAT"  # Les deux en parallèle
    DOWNLOAD = "DOWNLOAD"     # Téléchargement uniquement (pas d'envoi)


@dataclass
class PreviewLine:
    """Ligne de facture pour prévisualisation"""
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal
    line_total: Decimal

    @property
    def vat_amount(self) -> Decimal:
        return self.line_total * self.vat_rate / 100


@dataclass
class PreviewData:
    """Données de prévisualisation de facture"""
    # Identifiants
    invoice_id: UUID
    invoice_number: str
    invoice_date: date

    # Émetteur
    seller_name: str
    seller_siret: str
    seller_tva: str
    seller_address: str
    seller_city: str
    seller_postal_code: str
    seller_email: str

    # Destinataire
    buyer_name: str
    buyer_siret: Optional[str]
    buyer_tva: Optional[str]
    buyer_address: str
    buyer_city: str
    buyer_postal_code: str
    buyer_email: Optional[str]

    # Lignes
    lines: List[PreviewLine] = field(default_factory=list)

    # Totaux
    total_ht: Decimal = Decimal("0")
    total_tva: Decimal = Decimal("0")
    total_ttc: Decimal = Decimal("0")

    # Options
    due_date: Optional[date] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None

    # PDF généré (base64 pour affichage web)
    pdf_base64: Optional[str] = None
    pdf_content: Optional[bytes] = None

    # Options d'envoi
    available_send_options: List[SendOption] = field(default_factory=list)
    recommended_send_option: SendOption = SendOption.EMAIL_AND_DEMAT

    # Statut
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class SendOptions:
    """Options sélectionnées pour l'envoi"""
    send_email: bool = True
    send_demat: bool = True

    # Email
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_message: Optional[str] = None
    include_payment_link: bool = True

    # Démat
    demat_channel: str = "AUTO"  # AUTO, CHORUS, PPF


@dataclass
class SendPreviewResult:
    """Résultat de l'envoi après prévisualisation"""
    success: bool

    # Résultats par canal
    email_sent: bool = False
    email_error: Optional[str] = None

    demat_sent: bool = False
    demat_error: Optional[str] = None
    demat_id: Optional[str] = None  # ID Chorus/PPF

    archived: bool = False
    archive_id: Optional[UUID] = None

    # PDF final
    pdf_content: Optional[bytes] = None


class InvoicePreviewService:
    """
    Service de prévisualisation et envoi des factures.

    Workflow :
    1. generate_preview() → Génère le PDF et retourne PreviewData
    2. User visualise et ajuste les options
    3. send_with_options() → Envoie selon les options choisies
    """

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id

    def generate_preview(
        self,
        invoice_id: UUID,
        invoice_data: dict,
        lines: List[dict],
        seller_config: dict,
        buyer_data: dict,
    ) -> PreviewData:
        """
        Génère une prévisualisation de facture.

        Args:
            invoice_id: ID de la facture
            invoice_data: Données de la facture (numéro, date, etc.)
            lines: Lignes de facture
            seller_config: Config vendeur (SIRET, TVA, adresse)
            buyer_data: Données acheteur

        Returns:
            PreviewData avec PDF base64 pour affichage
        """
        # Parser les lignes
        preview_lines = []
        total_ht = Decimal("0")
        total_tva = Decimal("0")

        for line in lines:
            qty = Decimal(str(line.get("quantity", 1)))
            price = Decimal(str(line.get("unit_price", 0)))
            vat_rate = Decimal(str(line.get("vat_rate", 20)))
            line_total = qty * price

            preview_lines.append(PreviewLine(
                description=line.get("description", ""),
                quantity=qty,
                unit_price=price,
                vat_rate=vat_rate,
                line_total=line_total,
            ))

            total_ht += line_total
            total_tva += line_total * vat_rate / 100

        total_ttc = total_ht + total_tva

        # Déterminer les options d'envoi disponibles
        available_options = [SendOption.DOWNLOAD]
        recommended = SendOption.DOWNLOAD

        buyer_siret = buyer_data.get("siret")
        buyer_email = buyer_data.get("email")

        # Email disponible si on a l'adresse
        if buyer_email:
            available_options.append(SendOption.EMAIL)
            recommended = SendOption.EMAIL

        # Démat disponible si SIRET
        if buyer_siret:
            available_options.append(SendOption.DEMAT)
            # B2G ou B2B → démat recommandé
            if buyer_siret[0] in ("1", "2"):  # Secteur public
                recommended = SendOption.EMAIL_AND_DEMAT
            else:
                recommended = SendOption.EMAIL_AND_DEMAT

        # Les deux disponibles
        if buyer_email and buyer_siret:
            available_options.append(SendOption.EMAIL_AND_DEMAT)
            recommended = SendOption.EMAIL_AND_DEMAT

        # Validation
        validation_errors = []
        if not seller_config.get("siret"):
            validation_errors.append("SIRET émetteur manquant")
        if not seller_config.get("tva_intra"):
            validation_errors.append("N° TVA émetteur manquant")
        if total_ttc <= 0:
            validation_errors.append("Montant TTC doit être positif")

        # Créer la prévisualisation
        preview = PreviewData(
            invoice_id=invoice_id,
            invoice_number=invoice_data.get("number", ""),
            invoice_date=invoice_data.get("date", date.today()),
            seller_name=seller_config.get("name", ""),
            seller_siret=seller_config.get("siret", ""),
            seller_tva=seller_config.get("tva_intra", ""),
            seller_address=seller_config.get("address", ""),
            seller_city=seller_config.get("city", ""),
            seller_postal_code=seller_config.get("postal_code", ""),
            seller_email=seller_config.get("email", ""),
            buyer_name=buyer_data.get("name", ""),
            buyer_siret=buyer_siret,
            buyer_tva=buyer_data.get("tva_intra"),
            buyer_address=buyer_data.get("address", ""),
            buyer_city=buyer_data.get("city", ""),
            buyer_postal_code=buyer_data.get("postal_code", ""),
            buyer_email=buyer_email,
            lines=preview_lines,
            total_ht=total_ht,
            total_tva=total_tva,
            total_ttc=total_ttc,
            due_date=invoice_data.get("due_date"),
            payment_terms=invoice_data.get("payment_terms"),
            notes=invoice_data.get("notes"),
            available_send_options=available_options,
            recommended_send_option=recommended,
            is_valid=len(validation_errors) == 0,
            validation_errors=validation_errors,
        )

        # Générer le PDF
        pdf_content = self._generate_preview_pdf(preview)
        preview.pdf_content = pdf_content
        preview.pdf_base64 = base64.b64encode(pdf_content).decode()

        return preview

    def send_with_options(
        self,
        preview: PreviewData,
        options: SendOptions,
    ) -> SendPreviewResult:
        """
        Envoie la facture selon les options choisies.

        Exécute en parallèle :
        - Envoi email (si activé)
        - Envoi démat (si activé)
        - Archivage AZALCOFFRE (toujours)

        Args:
            preview: Données de prévisualisation
            options: Options d'envoi sélectionnées

        Returns:
            SendPreviewResult avec statuts de chaque canal
        """
        import concurrent.futures

        result = SendPreviewResult(success=True)
        pdf_content = preview.pdf_content

        if not pdf_content:
            pdf_content = self._generate_preview_pdf(preview)

        result.pdf_content = pdf_content

        # Exécution parallèle
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            # Email
            if options.send_email and preview.buyer_email:
                futures["email"] = executor.submit(
                    self._send_email,
                    preview,
                    options,
                    pdf_content,
                )

            # Démat
            if options.send_demat and preview.buyer_siret:
                futures["demat"] = executor.submit(
                    self._send_demat,
                    preview,
                    options,
                    pdf_content,
                )

            # Archivage (toujours)
            futures["archive"] = executor.submit(
                self._archive,
                preview,
                pdf_content,
            )

            # Récupérer les résultats
            for name, future in futures.items():
                try:
                    res = future.result(timeout=30)

                    if name == "email":
                        result.email_sent = res.get("success", False)
                        result.email_error = res.get("error")

                    elif name == "demat":
                        result.demat_sent = res.get("success", False)
                        result.demat_error = res.get("error")
                        result.demat_id = res.get("external_id")

                    elif name == "archive":
                        result.archived = res.get("success", False)
                        result.archive_id = res.get("archive_id")

                except Exception as e:
                    logger.error(f"Erreur {name}: {e}")
                    if name == "email":
                        result.email_error = str(e)
                    elif name == "demat":
                        result.demat_error = str(e)

        # Succès global si au moins un canal a fonctionné
        result.success = result.email_sent or result.demat_sent

        return result

    def _generate_preview_pdf(self, preview: PreviewData) -> bytes:
        """
        Génère le PDF de prévisualisation.

        Utilise le générateur PDF de moteur/pdf.py qui :
        - Charge le thème depuis config/theme.yml
        - Récupère les infos entreprise depuis la base
        - Gère le multi-tenant
        """
        try:
            # Import du générateur PDF (chemin absolu depuis moteur)
            import sys
            from pathlib import Path

            # Ajouter le chemin moteur si nécessaire
            moteur_path = Path(__file__).parent.parent.parent / "moteur"
            if str(moteur_path) not in sys.path:
                sys.path.insert(0, str(moteur_path.parent))

            from moteur.pdf import PDFGenerator

            # Le générateur requiert tenant_id pour le multi-tenant
            generator = PDFGenerator(tenant_id=self.tenant_id)

            # Construire les données de facture au format attendu par le générateur
            # Le générateur utilise _get_client_info et _get_tenant_info depuis la base
            # Donc on doit passer les données dans le format qu'il attend
            facture_data = {
                "numero": preview.invoice_number,
                "date": preview.invoice_date.isoformat(),
                "echeance": preview.due_date.isoformat() if preview.due_date else None,
                "notes": preview.notes,
                "conditions": preview.payment_terms,
                "total_ht": float(preview.total_ht),
                "total_tva": float(preview.total_tva),
                "total_ttc": float(preview.total_ttc),
                # Client sera récupéré via client_id si présent
                "client": None,  # Pas d'ID client, on fournit les données manuellement
                "lignes": [
                    {
                        "description": line.description,
                        "quantite": float(line.quantity),
                        "prix_unitaire": float(line.unit_price),
                        "taux_tva": float(line.vat_rate),
                        "total_ht_ligne": float(line.line_total),
                    }
                    for line in preview.lines
                ],
            }

            # Générer le PDF
            return generator.generate_facture_pdf(facture_data)

        except ImportError as e:
            logger.error(f"Import PDFGenerator échoué: {e}")
            return self._generate_minimal_pdf(preview)
        except Exception as e:
            logger.error(f"Erreur génération PDF preview: {e}")
            return self._generate_minimal_pdf(preview)

    def _generate_minimal_pdf(self, preview: PreviewData) -> bytes:
        """Génère un PDF minimal en cas d'erreur"""
        # Placeholder - retourne un PDF vide
        # En production, utiliser reportlab ou weasyprint
        return b"%PDF-1.4 minimal"

    def _send_email(
        self,
        preview: PreviewData,
        options: SendOptions,
        pdf_content: bytes,
    ) -> dict:
        """Envoie par email"""
        try:
            from .email_sender import (
                InvoiceEmailSender,
                InvoiceEmailData,
            )

            sender = InvoiceEmailSender()

            email_data = InvoiceEmailData(
                to_email=options.email_to or preview.buyer_email,
                to_name=preview.buyer_name,
                invoice_number=preview.invoice_number,
                invoice_date=preview.invoice_date.strftime("%d/%m/%Y"),
                amount_ttc=f"{preview.total_ttc:,.2f}".replace(",", " "),
                due_date=preview.due_date.strftime("%d/%m/%Y") if preview.due_date else None,
                company_name=preview.seller_name,
                company_email=preview.seller_email,
                custom_message=options.email_message,
                # TODO: Générer lien paiement Fintecture
                payment_link=None if not options.include_payment_link else None,
            )

            result = sender.send_invoice(
                email_data=email_data,
                pdf_content=pdf_content,
                pdf_filename=f"{preview.invoice_number}.pdf",
            )

            return {
                "success": result.success,
                "error": result.error_message,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _send_demat(
        self,
        preview: PreviewData,
        options: SendOptions,
        pdf_content: bytes,
    ) -> dict:
        """Envoie en dématérialisé (Chorus Pro / PPF)"""
        try:
            from .service import FacturationService, TenantConfig
            from .xml_builder import InvoiceData, Party, Address, InvoiceLine

            # Créer les données Factur-X
            invoice_data = InvoiceData(
                invoice_number=preview.invoice_number,
                invoice_date=preview.invoice_date,
                seller=Party(
                    name=preview.seller_name,
                    siret=preview.seller_siret,
                    tva_intra=preview.seller_tva,
                    address=Address(
                        line1=preview.seller_address,
                        city=preview.seller_city,
                        postal_code=preview.seller_postal_code,
                        country_code="FR",
                    ),
                    email=preview.seller_email,
                ),
                buyer=Party(
                    name=preview.buyer_name,
                    siret=preview.buyer_siret,
                    tva_intra=preview.buyer_tva,
                    address=Address(
                        line1=preview.buyer_address,
                        city=preview.buyer_city,
                        postal_code=preview.buyer_postal_code,
                        country_code="FR",
                    ),
                    email=preview.buyer_email,
                ),
                lines=[
                    InvoiceLine(
                        line_id=str(i + 1),
                        description=line.description,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        vat_rate=line.vat_rate,
                        line_total=line.line_total,
                    )
                    for i, line in enumerate(preview.lines)
                ],
                total_ht=preview.total_ht,
                total_tva=preview.total_tva,
                total_ttc=preview.total_ttc,
            )

            # Config tenant
            config = TenantConfig(
                tenant_id=self.tenant_id,
                siret=preview.seller_siret,
                tva_intra=preview.seller_tva,
                raison_sociale=preview.seller_name,
                adresse_ligne1=preview.seller_address,
                code_postal=preview.seller_postal_code,
                ville=preview.seller_city,
                email_facturation=preview.seller_email,
            )

            service = FacturationService(config)

            result = service.send_invoice(
                pdf_content=pdf_content,
                invoice_data=invoice_data,
                siret_destinataire=preview.buyer_siret or "",
                invoice_id=preview.invoice_id,
            )

            return {
                "success": result.success,
                "error": result.error_message,
                "external_id": result.external_id,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _archive(self, preview: PreviewData, pdf_content: bytes) -> dict:
        """Archive dans AZALCOFFRE"""
        try:
            from ..azalcoffre import ArchiveSync

            sync = ArchiveSync()

            if not sync.is_available():
                return {"success": False, "error": "AZALCOFFRE non disponible"}

            result = sync.archive_invoice_sent(
                tenant_id=self.tenant_id,
                invoice_id=preview.invoice_id,
                invoice_number=preview.invoice_number,
                invoice_date=preview.invoice_date,
                pdf_content=pdf_content,
                seller_name=preview.seller_name,
                seller_siret=preview.seller_siret,
                buyer_name=preview.buyer_name,
                buyer_siret=preview.buyer_siret,
                amount_ht=preview.total_ht,
                amount_ttc=preview.total_ttc,
            )

            return {
                "success": result.success,
                "archive_id": result.archive_id,
                "error": result.error_message,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
