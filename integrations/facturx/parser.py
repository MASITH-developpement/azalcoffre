"""
AZALPLUS - Parser Factur-X
Extraction des données depuis un PDF Factur-X reçu
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Optional
from xml.etree import ElementTree as ET

import pikepdf

logger = logging.getLogger(__name__)

# Namespaces Factur-X / ZUGFeRD
NAMESPACES = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}


@dataclass
class ParsedParty:
    """Partie extraite (vendeur ou acheteur)"""
    name: str
    siret: Optional[str] = None
    tva_intra: Optional[str] = None
    address_line: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country_code: str = "FR"
    email: Optional[str] = None


@dataclass
class ParsedLine:
    """Ligne de facture extraite"""
    line_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    vat_rate: Decimal = Decimal("20")


@dataclass
class ParsedInvoice:
    """Facture extraite d'un Factur-X"""
    # Identifiants
    invoice_number: str
    invoice_date: date
    invoice_type: str = "380"  # 380=Facture, 381=Avoir

    # Parties
    seller: Optional[ParsedParty] = None
    buyer: Optional[ParsedParty] = None

    # Montants
    total_ht: Decimal = Decimal("0")
    total_tva: Decimal = Decimal("0")
    total_ttc: Decimal = Decimal("0")
    currency: str = "EUR"

    # Lignes
    lines: list[ParsedLine] = field(default_factory=list)

    # Métadonnées
    profile: str = "UNKNOWN"
    raw_xml: Optional[str] = None

    # Paiement
    payment_terms: Optional[str] = None
    due_date: Optional[date] = None
    iban: Optional[str] = None
    bic: Optional[str] = None


class FacturXParser:
    """Parse un PDF Factur-X pour extraire les données"""

    def parse(self, pdf_content: bytes) -> ParsedInvoice:
        """
        Parse un PDF Factur-X et retourne les données structurées.

        Args:
            pdf_content: Contenu binaire du PDF

        Returns:
            ParsedInvoice avec toutes les données extraites
        """
        # Extraire le XML embarqué
        xml_content = self._extract_xml(pdf_content)
        if not xml_content:
            raise ValueError("Aucun XML Factur-X trouvé dans le PDF")

        # Parser le XML
        return self._parse_xml(xml_content)

    def parse_xml(self, xml_content: str) -> ParsedInvoice:
        """Parse directement un XML Factur-X"""
        return self._parse_xml(xml_content)

    def _extract_xml(self, pdf_content: bytes) -> Optional[str]:
        """Extrait le XML embarqué dans le PDF"""
        try:
            with pikepdf.open(BytesIO(pdf_content)) as pdf:
                # Chercher dans les pièces jointes
                if "/Names" in pdf.Root and "/EmbeddedFiles" in pdf.Root.Names:
                    ef = pdf.Root.Names.EmbeddedFiles
                    if "/Names" in ef:
                        names = list(ef.Names)
                        for i in range(0, len(names), 2):
                            name = str(names[i])
                            if "factur-x" in name.lower() or "zugferd" in name.lower():
                                filespec = names[i + 1]
                                if "/EF" in filespec and "/F" in filespec.EF:
                                    stream = filespec.EF.F
                                    return stream.read_bytes().decode("utf-8")

                # Chercher dans pdf.attachments (pikepdf moderne)
                for name, content in pdf.attachments.items():
                    if "factur-x" in name.lower() or "zugferd" in name.lower():
                        return content.get_file().read_bytes().decode("utf-8")

        except Exception as e:
            logger.error(f"Erreur extraction XML: {e}")

        return None

    def _parse_xml(self, xml_content: str) -> ParsedInvoice:
        """Parse le XML Factur-X"""
        root = ET.fromstring(xml_content)

        invoice = ParsedInvoice(
            invoice_number="",
            invoice_date=date.today(),
            raw_xml=xml_content,
        )

        # Détecter le profil
        invoice.profile = self._detect_profile(root)

        # Document header
        header = root.find(".//rsm:ExchangedDocument", NAMESPACES)
        if header is not None:
            invoice.invoice_number = self._get_text(header, "ram:ID")
            invoice.invoice_type = self._get_text(header, "ram:TypeCode") or "380"

            date_str = self._get_text(header, ".//udt:DateTimeString")
            if date_str:
                invoice.invoice_date = self._parse_date(date_str)

        # Transaction
        transaction = root.find(".//rsm:SupplyChainTradeTransaction", NAMESPACES)
        if transaction is not None:
            # Parties
            agreement = transaction.find("ram:ApplicableHeaderTradeAgreement", NAMESPACES)
            if agreement is not None:
                invoice.seller = self._parse_party(
                    agreement.find("ram:SellerTradeParty", NAMESPACES)
                )
                invoice.buyer = self._parse_party(
                    agreement.find("ram:BuyerTradeParty", NAMESPACES)
                )

            # Lignes
            for item in transaction.findall("ram:IncludedSupplyChainTradeLineItem", NAMESPACES):
                line = self._parse_line(item)
                if line:
                    invoice.lines.append(line)

            # Totaux
            settlement = transaction.find("ram:ApplicableHeaderTradeSettlement", NAMESPACES)
            if settlement is not None:
                invoice.currency = self._get_text(settlement, "ram:InvoiceCurrencyCode") or "EUR"

                # Paiement
                payment = settlement.find("ram:SpecifiedTradePaymentTerms", NAMESPACES)
                if payment is not None:
                    invoice.payment_terms = self._get_text(payment, "ram:Description")
                    due_str = self._get_text(payment, ".//udt:DateTimeString")
                    if due_str:
                        invoice.due_date = self._parse_date(due_str)

                # Montants
                monetary = settlement.find("ram:SpecifiedTradeSettlementHeaderMonetarySummation", NAMESPACES)
                if monetary is not None:
                    invoice.total_ht = self._get_decimal(monetary, "ram:TaxBasisTotalAmount")
                    invoice.total_tva = self._get_decimal(monetary, "ram:TaxTotalAmount")
                    invoice.total_ttc = self._get_decimal(monetary, "ram:GrandTotalAmount")

                # Coordonnées bancaires
                bank = settlement.find(".//ram:PayeePartyCreditorFinancialAccount", NAMESPACES)
                if bank is not None:
                    invoice.iban = self._get_text(bank, "ram:IBANID")

                bank_inst = settlement.find(".//ram:PayeeSpecifiedCreditorFinancialInstitution", NAMESPACES)
                if bank_inst is not None:
                    invoice.bic = self._get_text(bank_inst, "ram:BICID")

        return invoice

    def _detect_profile(self, root: ET.Element) -> str:
        """Détecte le profil Factur-X"""
        ctx = root.find(".//rsm:ExchangedDocumentContext", NAMESPACES)
        if ctx is not None:
            guide = ctx.find(".//ram:GuidelineSpecifiedDocumentContextParameter", NAMESPACES)
            if guide is not None:
                profile_id = self._get_text(guide, "ram:ID")
                if profile_id:
                    if "minimum" in profile_id.lower():
                        return "MINIMUM"
                    elif "basicwl" in profile_id.lower():
                        return "BASIC_WL"
                    elif "basic" in profile_id.lower():
                        return "BASIC"
                    elif "en16931" in profile_id.lower():
                        return "EN16931"
                    elif "extended" in profile_id.lower():
                        return "EXTENDED"
        return "UNKNOWN"

    def _parse_party(self, element: Optional[ET.Element]) -> Optional[ParsedParty]:
        """Parse une partie (vendeur/acheteur)"""
        if element is None:
            return None

        party = ParsedParty(
            name=self._get_text(element, "ram:Name") or "",
        )

        # IDs (SIRET, TVA)
        for global_id in element.findall("ram:GlobalID", NAMESPACES):
            scheme = global_id.get("schemeID", "")
            value = global_id.text or ""
            if scheme == "0002":  # SIRET
                party.siret = value
            elif scheme == "VA":  # TVA
                party.tva_intra = value

        # TVA spécifique
        tax_reg = element.find(".//ram:SpecifiedTaxRegistration/ram:ID", NAMESPACES)
        if tax_reg is not None and tax_reg.get("schemeID") == "VA":
            party.tva_intra = tax_reg.text

        # Adresse
        address = element.find("ram:PostalTradeAddress", NAMESPACES)
        if address is not None:
            party.postal_code = self._get_text(address, "ram:PostcodeCode")
            party.address_line = self._get_text(address, "ram:LineOne")
            party.city = self._get_text(address, "ram:CityName")
            party.country_code = self._get_text(address, "ram:CountryID") or "FR"

        # Email
        email_elem = element.find(".//ram:URIID", NAMESPACES)
        if email_elem is not None:
            party.email = email_elem.text

        return party

    def _parse_line(self, element: ET.Element) -> Optional[ParsedLine]:
        """Parse une ligne de facture"""
        try:
            doc = element.find("ram:AssociatedDocumentLineDocument", NAMESPACES)
            line_id = self._get_text(doc, "ram:LineID") if doc else "1"

            product = element.find("ram:SpecifiedTradeProduct", NAMESPACES)
            description = self._get_text(product, "ram:Name") if product else ""

            delivery = element.find("ram:SpecifiedLineTradeDelivery", NAMESPACES)
            quantity = self._get_decimal(delivery, "ram:BilledQuantity") if delivery else Decimal("1")

            settlement = element.find("ram:SpecifiedLineTradeSettlement", NAMESPACES)
            if settlement is not None:
                price = settlement.find(".//ram:SpecifiedTradeSettlementLineMonetarySummation", NAMESPACES)
                line_total = self._get_decimal(price, "ram:LineTotalAmount") if price else Decimal("0")

                trade_price = element.find(".//ram:NetPriceProductTradePrice", NAMESPACES)
                unit_price = self._get_decimal(trade_price, "ram:ChargeAmount") if trade_price else Decimal("0")

                tax = settlement.find(".//ram:ApplicableTradeTax", NAMESPACES)
                vat_rate = self._get_decimal(tax, "ram:RateApplicablePercent") if tax else Decimal("20")
            else:
                line_total = Decimal("0")
                unit_price = Decimal("0")
                vat_rate = Decimal("20")

            return ParsedLine(
                line_id=line_id or "1",
                description=description or "",
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
                vat_rate=vat_rate,
            )
        except Exception as e:
            logger.warning(f"Erreur parsing ligne: {e}")
            return None

    def _get_text(self, element: Optional[ET.Element], path: str) -> Optional[str]:
        """Récupère le texte d'un élément"""
        if element is None:
            return None
        found = element.find(path, NAMESPACES)
        return found.text if found is not None else None

    def _get_decimal(self, element: Optional[ET.Element], path: str) -> Decimal:
        """Récupère une valeur décimale"""
        text = self._get_text(element, path)
        if text:
            try:
                return Decimal(text)
            except:
                pass
        return Decimal("0")

    def _parse_date(self, date_str: str) -> date:
        """Parse une date au format YYYYMMDD ou YYYY-MM-DD"""
        date_str = date_str.strip()
        try:
            if "-" in date_str:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            else:
                return datetime.strptime(date_str[:8], "%Y%m%d").date()
        except:
            return date.today()
