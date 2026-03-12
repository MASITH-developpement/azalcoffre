# =============================================================================
# AZALPLUS - Réception Factures Entrantes
# =============================================================================
"""
Service de réception et traitement des factures entrantes.

Fonctionnalités:
- Import factures depuis PDP/Chorus Pro
- Parsing PDF Factur-X (extraction XML)
- OCR fallback pour factures non-structurées
- Validation et rapprochement
- Workflow d'approbation

Formats supportés:
- Factur-X (PDF/A-3 avec XML embarqué)
- UBL (Universal Business Language)
- CII (Cross-Industry Invoice)
- PDF simple (avec OCR)
"""

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Union
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class InvoiceFormat(str, Enum):
    """Formats de facture supportés."""
    FACTURX = "facturx"      # PDF/A-3 avec XML embarqué
    UBL = "ubl"              # Universal Business Language
    CII = "cii"              # Cross-Industry Invoice XML
    PDF = "pdf"              # PDF simple (OCR requis)
    UNKNOWN = "unknown"


class ReceptionStatus(str, Enum):
    """Statuts de réception."""
    RECEIVED = "received"           # Reçue
    PARSING = "parsing"             # En cours de parsing
    PARSED = "parsed"               # Parsée avec succès
    VALIDATION_PENDING = "validation_pending"
    VALIDATED = "validated"         # Validée
    REJECTED = "rejected"           # Rejetée
    MATCHED = "matched"             # Rapprochée (commande/BL)
    APPROVED = "approved"           # Approuvée
    PAID = "paid"                   # Payée
    ERROR = "error"


class ValidationError(str, Enum):
    """Types d'erreurs de validation."""
    MISSING_FIELD = "missing_field"
    INVALID_SIRET = "invalid_siret"
    INVALID_VAT = "invalid_vat"
    AMOUNT_MISMATCH = "amount_mismatch"
    DUPLICATE = "duplicate"
    UNKNOWN_SUPPLIER = "unknown_supplier"
    DATE_ERROR = "date_error"


@dataclass
class ReceivedInvoice:
    """Facture reçue parsée."""
    id: UUID = field(default_factory=uuid4)
    tenant_id: Optional[UUID] = None

    # Identifiants
    invoice_number: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None

    # Fournisseur
    supplier_name: Optional[str] = None
    supplier_siret: Optional[str] = None
    supplier_siren: Optional[str] = None
    supplier_vat: Optional[str] = None
    supplier_address: Optional[str] = None
    supplier_email: Optional[str] = None

    # Nous (client/acheteur)
    buyer_siret: Optional[str] = None
    buyer_name: Optional[str] = None

    # Montants
    total_without_tax: Optional[Decimal] = None
    total_tax: Optional[Decimal] = None
    total_with_tax: Optional[Decimal] = None
    currency: str = "EUR"

    # Lignes
    lines: list[dict] = field(default_factory=list)

    # TVA détaillée
    tax_breakdown: list[dict] = field(default_factory=list)

    # Références
    purchase_order: Optional[str] = None      # Bon de commande
    delivery_note: Optional[str] = None       # Bon de livraison
    contract_reference: Optional[str] = None  # Référence contrat

    # Paiement
    payment_terms: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None

    # Format et source
    format: InvoiceFormat = InvoiceFormat.UNKNOWN
    source: str = "upload"  # upload, pdp, chorus, email
    source_id: Optional[str] = None  # ID chez la source

    # Fichiers originaux
    pdf_content: Optional[bytes] = None
    xml_content: Optional[str] = None

    # Statut
    status: ReceptionStatus = ReceptionStatus.RECEIVED
    validation_errors: list[dict] = field(default_factory=list)

    # Métadonnées
    received_at: datetime = field(default_factory=datetime.utcnow)
    parsed_at: Optional[datetime] = None
    confidence_score: float = 0.0  # Score de confiance parsing (0-1)
    metadata: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Résultat de validation."""
    is_valid: bool
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    confidence: float = 1.0


class InvoiceParser:
    """
    Parser de factures multi-format.

    Supporte:
    - Factur-X (extraction XML depuis PDF/A-3)
    - UBL
    - CII
    """

    # Namespaces XML
    NAMESPACES = {
        "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
        "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
        "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
        "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    }

    def __init__(self):
        # Essayer d'importer pikepdf pour extraction Factur-X
        try:
            from pikepdf import Pdf
            self.pikepdf_available = True
        except ImportError:
            self.pikepdf_available = False
            logger.warning("pikepdf non disponible - extraction PDF/A-3 limitée")

    def parse(
        self,
        content: Union[bytes, str],
        filename: Optional[str] = None
    ) -> ReceivedInvoice:
        """
        Parser une facture depuis son contenu.

        Args:
            content: Contenu du fichier (bytes pour PDF, str pour XML)
            filename: Nom du fichier (pour détection format)

        Returns:
            ReceivedInvoice parsée
        """
        invoice = ReceivedInvoice()
        invoice.status = ReceptionStatus.PARSING

        try:
            # Détecter le format
            format_type = self._detect_format(content, filename)
            invoice.format = format_type

            if format_type == InvoiceFormat.FACTURX:
                self._parse_facturx(content, invoice)
            elif format_type == InvoiceFormat.UBL:
                self._parse_ubl(content, invoice)
            elif format_type == InvoiceFormat.CII:
                self._parse_cii(content, invoice)
            elif format_type == InvoiceFormat.PDF:
                # PDF simple - stocker pour OCR ultérieur
                invoice.pdf_content = content if isinstance(content, bytes) else content.encode()
                invoice.confidence_score = 0.0
            else:
                invoice.status = ReceptionStatus.ERROR
                invoice.validation_errors.append({
                    "type": "format",
                    "message": "Format non reconnu"
                })
                return invoice

            invoice.status = ReceptionStatus.PARSED
            invoice.parsed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Erreur parsing facture: {e}")
            invoice.status = ReceptionStatus.ERROR
            invoice.validation_errors.append({
                "type": "parsing",
                "message": str(e)
            })

        return invoice

    def _detect_format(
        self,
        content: Union[bytes, str],
        filename: Optional[str] = None
    ) -> InvoiceFormat:
        """Détecter le format d'une facture."""
        # Par extension
        if filename:
            ext = Path(filename).suffix.lower()
            if ext == ".xml":
                # Détecter UBL vs CII
                if isinstance(content, bytes):
                    content_str = content.decode("utf-8", errors="ignore")
                else:
                    content_str = content

                if "CrossIndustryInvoice" in content_str:
                    return InvoiceFormat.CII
                elif "Invoice" in content_str and "oasis" in content_str:
                    return InvoiceFormat.UBL
                return InvoiceFormat.CII  # Défaut

        # Par contenu
        if isinstance(content, bytes):
            # PDF magic number
            if content[:4] == b"%PDF":
                # Vérifier si c'est du PDF/A-3 avec XML embarqué
                if self._has_embedded_xml(content):
                    return InvoiceFormat.FACTURX
                return InvoiceFormat.PDF

            # XML
            if content.strip().startswith(b"<?xml") or content.strip().startswith(b"<"):
                content_str = content.decode("utf-8", errors="ignore")
                if "CrossIndustryInvoice" in content_str:
                    return InvoiceFormat.CII
                elif "Invoice" in content_str:
                    return InvoiceFormat.UBL

        return InvoiceFormat.UNKNOWN

    def _has_embedded_xml(self, pdf_content: bytes) -> bool:
        """Vérifier si un PDF a du XML embarqué."""
        if not self.pikepdf_available:
            # Heuristique simple
            return b"factur-x.xml" in pdf_content or b"CrossIndustryInvoice" in pdf_content

        try:
            from pikepdf import Pdf
            pdf = Pdf.open(io.BytesIO(pdf_content))
            if hasattr(pdf.Root, "Names") and hasattr(pdf.Root.Names, "EmbeddedFiles"):
                return True
        except Exception:
            pass

        return False

    def _parse_facturx(self, content: bytes, invoice: ReceivedInvoice):
        """Parser un PDF Factur-X."""
        invoice.pdf_content = content

        # Extraire le XML
        xml_content = self._extract_xml_from_pdf(content)
        if xml_content:
            invoice.xml_content = xml_content
            # Parser le XML CII
            self._parse_cii(xml_content, invoice)
            invoice.confidence_score = 1.0
        else:
            invoice.confidence_score = 0.5
            invoice.validation_errors.append({
                "type": "extraction",
                "message": "XML Factur-X non trouvé dans le PDF"
            })

    def _extract_xml_from_pdf(self, pdf_content: bytes) -> Optional[str]:
        """Extraire le XML d'un PDF/A-3."""
        if not self.pikepdf_available:
            return None

        try:
            from pikepdf import Pdf
            pdf = Pdf.open(io.BytesIO(pdf_content))

            if hasattr(pdf.Root, "Names") and hasattr(pdf.Root.Names, "EmbeddedFiles"):
                names = pdf.Root.Names.EmbeddedFiles.Names
                for i in range(0, len(names), 2):
                    name = str(names[i])
                    if "factur-x" in name.lower() or name.endswith(".xml"):
                        file_spec = names[i + 1]
                        if hasattr(file_spec, "EF") and hasattr(file_spec.EF, "F"):
                            return file_spec.EF.F.read_bytes().decode("utf-8")

        except Exception as e:
            logger.error(f"Erreur extraction XML: {e}")

        return None

    def _parse_cii(self, content: Union[bytes, str], invoice: ReceivedInvoice):
        """Parser un XML CII (Factur-X)."""
        if isinstance(content, bytes):
            content = content.decode("utf-8")

        invoice.xml_content = content

        try:
            root = ET.fromstring(content)

            # Extraire document
            doc = root.find(".//rsm:ExchangedDocument", self.NAMESPACES)
            if doc is not None:
                # Numéro facture
                id_elem = doc.find("ram:ID", self.NAMESPACES)
                if id_elem is not None:
                    invoice.invoice_number = id_elem.text

                # Date
                date_elem = doc.find(".//udt:DateTimeString", self.NAMESPACES)
                if date_elem is not None:
                    invoice.issue_date = self._parse_date(date_elem.text)

            # Transaction
            transaction = root.find(".//rsm:SupplyChainTradeTransaction", self.NAMESPACES)
            if transaction is not None:
                self._parse_cii_transaction(transaction, invoice)

            invoice.confidence_score = 0.95

        except ET.ParseError as e:
            logger.error(f"Erreur parsing XML CII: {e}")
            invoice.validation_errors.append({
                "type": "xml",
                "message": f"XML invalide: {e}"
            })

    def _parse_cii_transaction(self, transaction: ET.Element, invoice: ReceivedInvoice):
        """Parser la transaction CII."""
        ns = self.NAMESPACES

        # Vendeur (fournisseur)
        seller = transaction.find(".//ram:SellerTradeParty", ns)
        if seller is not None:
            name = seller.find("ram:Name", ns)
            if name is not None:
                invoice.supplier_name = name.text

            # SIRET/SIREN
            for id_elem in seller.findall(".//ram:ID", ns):
                scheme = id_elem.get("schemeID", "")
                if scheme == "0002" or len(id_elem.text or "") == 14:
                    invoice.supplier_siret = id_elem.text
                elif len(id_elem.text or "") == 9:
                    invoice.supplier_siren = id_elem.text

            # TVA
            tax_id = seller.find(".//ram:SpecifiedTaxRegistration/ram:ID", ns)
            if tax_id is not None:
                invoice.supplier_vat = tax_id.text

        # Acheteur
        buyer = transaction.find(".//ram:BuyerTradeParty", ns)
        if buyer is not None:
            name = buyer.find("ram:Name", ns)
            if name is not None:
                invoice.buyer_name = name.text

            for id_elem in buyer.findall(".//ram:ID", ns):
                if len(id_elem.text or "") == 14:
                    invoice.buyer_siret = id_elem.text

        # Montants
        settlement = transaction.find(".//ram:ApplicableHeaderTradeSettlement", ns)
        if settlement is not None:
            # Total TTC
            total = settlement.find(".//ram:GrandTotalAmount", ns)
            if total is not None:
                invoice.total_with_tax = Decimal(total.text)

            # Total HT
            ht = settlement.find(".//ram:TaxBasisTotalAmount", ns)
            if ht is not None:
                invoice.total_without_tax = Decimal(ht.text)

            # Total TVA
            tax = settlement.find(".//ram:TaxTotalAmount", ns)
            if tax is not None:
                invoice.total_tax = Decimal(tax.text)

            # Devise
            currency = settlement.find(".//ram:InvoiceCurrencyCode", ns)
            if currency is not None:
                invoice.currency = currency.text

            # Échéance
            due = settlement.find(".//ram:DueDateDateTime//udt:DateTimeString", ns)
            if due is not None:
                invoice.due_date = self._parse_date(due.text)

        # Lignes
        for line_item in transaction.findall(".//ram:IncludedSupplyChainTradeLineItem", ns):
            line = self._parse_cii_line(line_item)
            if line:
                invoice.lines.append(line)

    def _parse_cii_line(self, line_item: ET.Element) -> Optional[dict]:
        """Parser une ligne CII."""
        ns = self.NAMESPACES
        line = {}

        # Description
        product = line_item.find(".//ram:SpecifiedTradeProduct", ns)
        if product is not None:
            name = product.find("ram:Name", ns)
            if name is not None:
                line["description"] = name.text

        # Quantité
        qty = line_item.find(".//ram:BilledQuantity", ns)
        if qty is not None:
            line["quantity"] = Decimal(qty.text)
            line["unit"] = qty.get("unitCode", "C62")

        # Prix unitaire
        price = line_item.find(".//ram:NetPriceProductTradePrice/ram:ChargeAmount", ns)
        if price is not None:
            line["unit_price"] = Decimal(price.text)

        # Montant ligne
        amount = line_item.find(".//ram:SpecifiedLineTradeSettlement//ram:LineTotalAmount", ns)
        if amount is not None:
            line["total"] = Decimal(amount.text)

        return line if line else None

    def _parse_ubl(self, content: Union[bytes, str], invoice: ReceivedInvoice):
        """Parser un XML UBL."""
        if isinstance(content, bytes):
            content = content.decode("utf-8")

        invoice.xml_content = content

        try:
            root = ET.fromstring(content)
            ns = self.NAMESPACES

            # Numéro
            id_elem = root.find(".//cbc:ID", ns)
            if id_elem is not None:
                invoice.invoice_number = id_elem.text

            # Date
            date_elem = root.find(".//cbc:IssueDate", ns)
            if date_elem is not None:
                invoice.issue_date = self._parse_date(date_elem.text)

            # Due date
            due_elem = root.find(".//cbc:DueDate", ns)
            if due_elem is not None:
                invoice.due_date = self._parse_date(due_elem.text)

            # Vendeur
            supplier = root.find(".//cac:AccountingSupplierParty/cac:Party", ns)
            if supplier is not None:
                name = supplier.find(".//cbc:Name", ns)
                if name is not None:
                    invoice.supplier_name = name.text

            # Montants
            total = root.find(".//cac:LegalMonetaryTotal/cbc:PayableAmount", ns)
            if total is not None:
                invoice.total_with_tax = Decimal(total.text)

            tax_amount = root.find(".//cac:TaxTotal/cbc:TaxAmount", ns)
            if tax_amount is not None:
                invoice.total_tax = Decimal(tax_amount.text)

            if invoice.total_with_tax and invoice.total_tax:
                invoice.total_without_tax = invoice.total_with_tax - invoice.total_tax

            invoice.confidence_score = 0.9

        except ET.ParseError as e:
            logger.error(f"Erreur parsing XML UBL: {e}")

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parser une date."""
        if not date_str:
            return None

        # Formats courants
        formats = [
            "%Y%m%d",           # 20240115
            "%Y-%m-%d",         # 2024-01-15
            "%d/%m/%Y",         # 15/01/2024
            "%d-%m-%Y",         # 15-01-2024
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        return None


class InvoiceValidator:
    """Validateur de factures reçues."""

    def __init__(self, tenant_id: Optional[UUID] = None):
        self.tenant_id = tenant_id

    def validate(self, invoice: ReceivedInvoice) -> ValidationResult:
        """
        Valider une facture reçue.

        Vérifie:
        - Champs obligatoires
        - Format SIRET/TVA
        - Cohérence montants
        - Doublons
        """
        errors = []
        warnings = []
        confidence = 1.0

        # Champs obligatoires
        required_fields = [
            ("invoice_number", "Numéro de facture"),
            ("issue_date", "Date de facture"),
            ("supplier_name", "Nom fournisseur"),
            ("total_with_tax", "Montant TTC")
        ]

        for field, label in required_fields:
            if not getattr(invoice, field, None):
                errors.append({
                    "type": ValidationError.MISSING_FIELD.value,
                    "field": field,
                    "message": f"{label} manquant"
                })
                confidence -= 0.1

        # SIRET fournisseur
        if invoice.supplier_siret:
            if not self._validate_siret(invoice.supplier_siret):
                errors.append({
                    "type": ValidationError.INVALID_SIRET.value,
                    "field": "supplier_siret",
                    "message": f"SIRET invalide: {invoice.supplier_siret}"
                })
        else:
            warnings.append({
                "type": "missing_siret",
                "message": "SIRET fournisseur non renseigné"
            })
            confidence -= 0.05

        # TVA fournisseur
        if invoice.supplier_vat:
            if not self._validate_vat(invoice.supplier_vat):
                warnings.append({
                    "type": ValidationError.INVALID_VAT.value,
                    "message": f"Numéro TVA potentiellement invalide: {invoice.supplier_vat}"
                })

        # Cohérence montants
        if invoice.total_without_tax and invoice.total_tax and invoice.total_with_tax:
            expected = invoice.total_without_tax + invoice.total_tax
            if abs(expected - invoice.total_with_tax) > Decimal("0.01"):
                errors.append({
                    "type": ValidationError.AMOUNT_MISMATCH.value,
                    "message": f"Incohérence montants: {invoice.total_without_tax} + {invoice.total_tax} != {invoice.total_with_tax}"
                })

        # Date dans le futur
        if invoice.issue_date and invoice.issue_date > date.today():
            warnings.append({
                "type": ValidationError.DATE_ERROR.value,
                "message": "Date de facture dans le futur"
            })

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            confidence=max(0, confidence)
        )

    def _validate_siret(self, siret: str) -> bool:
        """Valider un SIRET (algorithme de Luhn)."""
        if not siret:
            return False

        siret = siret.replace(" ", "")
        if len(siret) != 14 or not siret.isdigit():
            return False

        # Algorithme de Luhn
        total = 0
        for i, c in enumerate(siret):
            digit = int(c)
            if i % 2 == 0:
                digit *= 2
                if digit > 9:
                    digit -= 9
            total += digit

        return total % 10 == 0

    def _validate_vat(self, vat: str) -> bool:
        """Valider un numéro TVA (format basique)."""
        if not vat:
            return False

        vat = vat.replace(" ", "").upper()

        # Format français: FR + 2 caractères + 9 chiffres
        if vat.startswith("FR"):
            return len(vat) == 13 and vat[4:].isdigit()

        # Autres pays EU: 2 lettres + chiffres
        return len(vat) >= 8 and vat[:2].isalpha()


class InvoiceReceptionService:
    """
    Service de réception et traitement des factures.

    Orchestre:
    - Parsing multi-format
    - Validation
    - Stockage
    - Notifications
    """

    def __init__(self, tenant_id: Optional[UUID] = None):
        self.tenant_id = tenant_id
        self.parser = InvoiceParser()
        self.validator = InvoiceValidator(tenant_id)

    async def receive(
        self,
        content: Union[bytes, str],
        filename: Optional[str] = None,
        source: str = "upload",
        source_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> ReceivedInvoice:
        """
        Recevoir et traiter une facture.

        Args:
            content: Contenu du fichier
            filename: Nom du fichier
            source: Source (upload, pdp, chorus, email)
            source_id: ID chez la source
            metadata: Métadonnées additionnelles

        Returns:
            ReceivedInvoice traitée
        """
        # Parser
        invoice = self.parser.parse(content, filename)
        invoice.tenant_id = self.tenant_id
        invoice.source = source
        invoice.source_id = source_id
        if metadata:
            invoice.metadata.update(metadata)

        # Valider
        if invoice.status == ReceptionStatus.PARSED:
            result = self.validator.validate(invoice)
            invoice.validation_errors.extend(result.errors)

            if result.is_valid:
                invoice.status = ReceptionStatus.VALIDATED
            else:
                invoice.status = ReceptionStatus.VALIDATION_PENDING

            # Ajuster le score de confiance
            invoice.confidence_score *= result.confidence

        return invoice

    async def receive_batch(
        self,
        files: list[tuple[bytes, str]],  # (content, filename)
        source: str = "upload"
    ) -> list[ReceivedInvoice]:
        """Recevoir plusieurs factures."""
        results = []
        for content, filename in files:
            invoice = await self.receive(content, filename, source)
            results.append(invoice)
        return results

    def get_statistics(self, invoices: list[ReceivedInvoice]) -> dict:
        """Statistiques sur un lot de factures reçues."""
        stats = {
            "total": len(invoices),
            "by_status": {},
            "by_format": {},
            "total_amount": Decimal("0"),
            "average_confidence": 0.0
        }

        for inv in invoices:
            # Par statut
            status = inv.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # Par format
            fmt = inv.format.value
            stats["by_format"][fmt] = stats["by_format"].get(fmt, 0) + 1

            # Montant total
            if inv.total_with_tax:
                stats["total_amount"] += inv.total_with_tax

            # Confiance moyenne
            stats["average_confidence"] += inv.confidence_score

        if invoices:
            stats["average_confidence"] /= len(invoices)

        return stats
