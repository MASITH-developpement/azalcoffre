# =============================================================================
# AZALPLUS - Générateur XML Factur-X (EN16931)
# =============================================================================
"""
Génération du XML conforme EN16931 pour Factur-X.

Structure XML:
- CrossIndustryInvoice (racine)
- ExchangedDocumentContext
- ExchangedDocument
- SupplyChainTradeTransaction
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from xml.etree import ElementTree as ET
from uuid import UUID

logger = logging.getLogger(__name__)

# Namespaces Factur-X
NAMESPACES = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


class InvoiceTypeCode(Enum):
    """Codes type de facture (UNTDID 1001)."""
    FACTURE = "380"           # Commercial invoice
    AVOIR = "381"             # Credit note
    FACTURE_RECTIFICATIVE = "384"  # Corrected invoice
    ACOMPTE = "386"           # Prepayment invoice
    AUTOFACTURATION = "389"   # Self-billed invoice


class PaymentMeansCode(Enum):
    """Codes moyens de paiement (UNTDID 4461)."""
    ESPECES = "10"
    CHEQUE = "20"
    VIREMENT = "30"
    VIREMENT_SEPA = "58"
    PRELEVEMENT = "49"
    CARTE = "48"
    COMPENSATION = "97"


class VATCategoryCode(Enum):
    """Codes catégorie TVA."""
    STANDARD = "S"           # Standard rate
    ZERO = "Z"               # Zero rated
    EXEMPT = "E"             # Exempt
    REVERSE_CHARGE = "AE"    # Reverse charge
    INTRA_COMMUNITY = "K"    # Intra-community
    EXPORT = "G"             # Export
    NOT_SUBJECT = "O"        # Not subject to VAT


@dataclass
class Address:
    """Adresse postale."""
    line1: str
    line2: str = ""
    postal_code: str = ""
    city: str = ""
    country_code: str = "FR"


@dataclass
class Party:
    """Partie (vendeur/acheteur)."""
    name: str
    siret: str = ""
    siren: str = ""
    tva_intra: str = ""
    address: Optional[Address] = None
    email: str = ""
    phone: str = ""
    legal_form: str = ""  # SA, SARL, SAS, etc.
    capital: str = ""     # Capital social
    rcs: str = ""         # RCS


@dataclass
class InvoiceLine:
    """Ligne de facture."""
    line_id: str
    description: str
    quantity: Decimal
    unit_code: str = "C62"  # Unit (UNECE Rec 20)
    unit_price: Decimal = Decimal("0")
    vat_rate: Decimal = Decimal("20")
    vat_category: VATCategoryCode = VATCategoryCode.STANDARD
    line_total: Decimal = Decimal("0")
    item_code: str = ""
    buyer_reference: str = ""


@dataclass
class PaymentTerms:
    """Conditions de paiement."""
    due_date: Optional[date] = None
    payment_means_code: PaymentMeansCode = PaymentMeansCode.VIREMENT_SEPA
    iban: str = ""
    bic: str = ""
    mandate_reference: str = ""  # Pour prélèvement
    note: str = ""


@dataclass
class InvoiceData:
    """Données complètes de la facture."""
    # Identification
    invoice_number: str
    invoice_date: date
    invoice_type: InvoiceTypeCode = InvoiceTypeCode.FACTURE
    currency_code: str = "EUR"

    # Parties
    seller: Party = field(default_factory=Party)
    buyer: Party = field(default_factory=Party)

    # Lignes
    lines: List[InvoiceLine] = field(default_factory=list)

    # Totaux
    total_ht: Decimal = Decimal("0")
    total_tva: Decimal = Decimal("0")
    total_ttc: Decimal = Decimal("0")

    # Paiement
    payment_terms: Optional[PaymentTerms] = None

    # Références
    purchase_order_ref: str = ""
    contract_ref: str = ""
    project_ref: str = ""

    # Notes
    notes: List[str] = field(default_factory=list)

    # Factur-X spécifique
    buyer_accounting_ref: str = ""  # Référence comptable acheteur
    payment_reference: str = ""     # Référence paiement


class XMLBuilder:
    """Constructeur XML Factur-X EN16931."""

    def __init__(self):
        # Enregistrer les namespaces
        for prefix, uri in NAMESPACES.items():
            ET.register_namespace(prefix, uri)

    def build(self, data: InvoiceData) -> str:
        """
        Générer le XML Factur-X complet.

        Args:
            data: Données de la facture

        Returns:
            XML string conforme EN16931
        """
        root = self._create_root()

        # ExchangedDocumentContext
        self._add_context(root, data)

        # ExchangedDocument
        self._add_document(root, data)

        # SupplyChainTradeTransaction
        self._add_transaction(root, data)

        # Générer le XML
        return self._to_string(root)

    def _create_root(self) -> ET.Element:
        """Créer l'élément racine."""
        # Note: Les namespaces sont déjà enregistrés via ET.register_namespace()
        # Ne pas ajouter les attributs xmlns manuellement pour éviter les doublons
        root = ET.Element(f"{{{NAMESPACES['rsm']}}}CrossIndustryInvoice")
        return root

    def _add_context(self, root: ET.Element, data: InvoiceData):
        """Ajouter ExchangedDocumentContext."""
        context = ET.SubElement(root, f"{{{NAMESPACES['rsm']}}}ExchangedDocumentContext")

        # BusinessProcessSpecifiedDocumentContextParameter
        bp = ET.SubElement(context, f"{{{NAMESPACES['ram']}}}BusinessProcessSpecifiedDocumentContextParameter")
        bp_id = ET.SubElement(bp, f"{{{NAMESPACES['ram']}}}ID")
        bp_id.text = "urn:cen.eu:en16931:2017"

        # GuidelineSpecifiedDocumentContextParameter
        gl = ET.SubElement(context, f"{{{NAMESPACES['ram']}}}GuidelineSpecifiedDocumentContextParameter")
        gl_id = ET.SubElement(gl, f"{{{NAMESPACES['ram']}}}ID")
        gl_id.text = "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:en16931"

    def _add_document(self, root: ET.Element, data: InvoiceData):
        """Ajouter ExchangedDocument."""
        doc = ET.SubElement(root, f"{{{NAMESPACES['rsm']}}}ExchangedDocument")

        # ID (numéro facture)
        doc_id = ET.SubElement(doc, f"{{{NAMESPACES['ram']}}}ID")
        doc_id.text = data.invoice_number

        # TypeCode
        type_code = ET.SubElement(doc, f"{{{NAMESPACES['ram']}}}TypeCode")
        type_code.text = data.invoice_type.value

        # IssueDateTime
        issue = ET.SubElement(doc, f"{{{NAMESPACES['ram']}}}IssueDateTime")
        issue_date = ET.SubElement(issue, f"{{{NAMESPACES['udt']}}}DateTimeString", format="102")
        issue_date.text = data.invoice_date.strftime("%Y%m%d")

        # Notes
        for note in data.notes:
            inc_note = ET.SubElement(doc, f"{{{NAMESPACES['ram']}}}IncludedNote")
            content = ET.SubElement(inc_note, f"{{{NAMESPACES['ram']}}}Content")
            content.text = note

    def _add_transaction(self, root: ET.Element, data: InvoiceData):
        """Ajouter SupplyChainTradeTransaction."""
        trans = ET.SubElement(root, f"{{{NAMESPACES['rsm']}}}SupplyChainTradeTransaction")

        # Lignes
        for line in data.lines:
            self._add_line_item(trans, line)

        # ApplicableHeaderTradeAgreement
        self._add_agreement(trans, data)

        # ApplicableHeaderTradeDelivery
        self._add_delivery(trans, data)

        # ApplicableHeaderTradeSettlement
        self._add_settlement(trans, data)

    def _add_line_item(self, parent: ET.Element, line: InvoiceLine):
        """Ajouter une ligne de facture."""
        item = ET.SubElement(parent, f"{{{NAMESPACES['ram']}}}IncludedSupplyChainTradeLineItem")

        # AssociatedDocumentLineDocument
        doc = ET.SubElement(item, f"{{{NAMESPACES['ram']}}}AssociatedDocumentLineDocument")
        line_id = ET.SubElement(doc, f"{{{NAMESPACES['ram']}}}LineID")
        line_id.text = line.line_id

        # SpecifiedTradeProduct
        product = ET.SubElement(item, f"{{{NAMESPACES['ram']}}}SpecifiedTradeProduct")

        if line.item_code:
            seller_id = ET.SubElement(product, f"{{{NAMESPACES['ram']}}}SellerAssignedID")
            seller_id.text = line.item_code

        name = ET.SubElement(product, f"{{{NAMESPACES['ram']}}}Name")
        name.text = line.description

        # SpecifiedLineTradeAgreement
        agreement = ET.SubElement(item, f"{{{NAMESPACES['ram']}}}SpecifiedLineTradeAgreement")

        # Prix net
        net_price = ET.SubElement(agreement, f"{{{NAMESPACES['ram']}}}NetPriceProductTradePrice")
        charge_amount = ET.SubElement(net_price, f"{{{NAMESPACES['ram']}}}ChargeAmount")
        charge_amount.text = str(line.unit_price)

        # SpecifiedLineTradeDelivery
        delivery = ET.SubElement(item, f"{{{NAMESPACES['ram']}}}SpecifiedLineTradeDelivery")
        billed_qty = ET.SubElement(delivery, f"{{{NAMESPACES['ram']}}}BilledQuantity", unitCode=line.unit_code)
        billed_qty.text = str(line.quantity)

        # SpecifiedLineTradeSettlement
        settlement = ET.SubElement(item, f"{{{NAMESPACES['ram']}}}SpecifiedLineTradeSettlement")

        # TVA
        tax = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}ApplicableTradeTax")
        tax_type = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}TypeCode")
        tax_type.text = "VAT"
        tax_cat = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}CategoryCode")
        tax_cat.text = line.vat_category.value
        tax_rate = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}RateApplicablePercent")
        tax_rate.text = str(line.vat_rate)

        # Montant ligne
        monetary = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}SpecifiedTradeSettlementLineMonetarySummation")
        line_total = ET.SubElement(monetary, f"{{{NAMESPACES['ram']}}}LineTotalAmount")
        line_total.text = str(line.line_total)

    def _add_agreement(self, parent: ET.Element, data: InvoiceData):
        """Ajouter ApplicableHeaderTradeAgreement (parties)."""
        agreement = ET.SubElement(parent, f"{{{NAMESPACES['ram']}}}ApplicableHeaderTradeAgreement")

        # Référence acheteur
        if data.buyer_accounting_ref:
            buyer_ref = ET.SubElement(agreement, f"{{{NAMESPACES['ram']}}}BuyerReference")
            buyer_ref.text = data.buyer_accounting_ref

        # Vendeur
        self._add_party(agreement, "SellerTradeParty", data.seller)

        # Acheteur
        self._add_party(agreement, "BuyerTradeParty", data.buyer)

        # Référence commande
        if data.purchase_order_ref:
            order_ref = ET.SubElement(agreement, f"{{{NAMESPACES['ram']}}}BuyerOrderReferencedDocument")
            order_id = ET.SubElement(order_ref, f"{{{NAMESPACES['ram']}}}IssuerAssignedID")
            order_id.text = data.purchase_order_ref

        # Référence contrat
        if data.contract_ref:
            contract_ref = ET.SubElement(agreement, f"{{{NAMESPACES['ram']}}}ContractReferencedDocument")
            contract_id = ET.SubElement(contract_ref, f"{{{NAMESPACES['ram']}}}IssuerAssignedID")
            contract_id.text = data.contract_ref

    def _add_party(self, parent: ET.Element, element_name: str, party: Party):
        """Ajouter une partie (vendeur/acheteur)."""
        party_elem = ET.SubElement(parent, f"{{{NAMESPACES['ram']}}}{element_name}")

        # Nom
        name = ET.SubElement(party_elem, f"{{{NAMESPACES['ram']}}}Name")
        name.text = party.name

        # Identifiants légaux
        if party.siret:
            legal_org = ET.SubElement(party_elem, f"{{{NAMESPACES['ram']}}}SpecifiedLegalOrganization")
            siret_elem = ET.SubElement(legal_org, f"{{{NAMESPACES['ram']}}}ID", schemeID="0002")
            siret_elem.text = party.siret

            if party.legal_form:
                trading_name = ET.SubElement(legal_org, f"{{{NAMESPACES['ram']}}}TradingBusinessName")
                trading_name.text = f"{party.name} {party.legal_form}"

        # Adresse
        if party.address:
            postal = ET.SubElement(party_elem, f"{{{NAMESPACES['ram']}}}PostalTradeAddress")

            pc = ET.SubElement(postal, f"{{{NAMESPACES['ram']}}}PostcodeCode")
            pc.text = party.address.postal_code

            line1 = ET.SubElement(postal, f"{{{NAMESPACES['ram']}}}LineOne")
            line1.text = party.address.line1

            if party.address.line2:
                line2 = ET.SubElement(postal, f"{{{NAMESPACES['ram']}}}LineTwo")
                line2.text = party.address.line2

            city = ET.SubElement(postal, f"{{{NAMESPACES['ram']}}}CityName")
            city.text = party.address.city

            country = ET.SubElement(postal, f"{{{NAMESPACES['ram']}}}CountryID")
            country.text = party.address.country_code

        # Contact email
        if party.email:
            contact = ET.SubElement(party_elem, f"{{{NAMESPACES['ram']}}}DefinedTradeContact")
            email_uri = ET.SubElement(contact, f"{{{NAMESPACES['ram']}}}EmailURIUniversalCommunication")
            email_id = ET.SubElement(email_uri, f"{{{NAMESPACES['ram']}}}URIID")
            email_id.text = party.email

        # TVA intracommunautaire
        if party.tva_intra:
            tax_reg = ET.SubElement(party_elem, f"{{{NAMESPACES['ram']}}}SpecifiedTaxRegistration")
            tax_id = ET.SubElement(tax_reg, f"{{{NAMESPACES['ram']}}}ID", schemeID="VA")
            tax_id.text = party.tva_intra

    def _add_delivery(self, parent: ET.Element, data: InvoiceData):
        """Ajouter ApplicableHeaderTradeDelivery."""
        delivery = ET.SubElement(parent, f"{{{NAMESPACES['ram']}}}ApplicableHeaderTradeDelivery")

        # Date de livraison (= date facture par défaut)
        actual = ET.SubElement(delivery, f"{{{NAMESPACES['ram']}}}ActualDeliverySupplyChainEvent")
        occurrence = ET.SubElement(actual, f"{{{NAMESPACES['ram']}}}OccurrenceDateTime")
        occ_date = ET.SubElement(occurrence, f"{{{NAMESPACES['udt']}}}DateTimeString", format="102")
        occ_date.text = data.invoice_date.strftime("%Y%m%d")

    def _add_settlement(self, parent: ET.Element, data: InvoiceData):
        """Ajouter ApplicableHeaderTradeSettlement."""
        settlement = ET.SubElement(parent, f"{{{NAMESPACES['ram']}}}ApplicableHeaderTradeSettlement")

        # Référence paiement
        if data.payment_reference:
            payment_ref = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}PaymentReference")
            payment_ref.text = data.payment_reference

        # Devise
        currency = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}InvoiceCurrencyCode")
        currency.text = data.currency_code

        # Moyens de paiement
        if data.payment_terms:
            payment_means = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}SpecifiedTradeSettlementPaymentMeans")

            type_code = ET.SubElement(payment_means, f"{{{NAMESPACES['ram']}}}TypeCode")
            type_code.text = data.payment_terms.payment_means_code.value

            # Coordonnées bancaires
            if data.payment_terms.iban:
                account = ET.SubElement(payment_means, f"{{{NAMESPACES['ram']}}}PayeePartyCreditorFinancialAccount")
                iban_elem = ET.SubElement(account, f"{{{NAMESPACES['ram']}}}IBANID")
                iban_elem.text = data.payment_terms.iban

                if data.payment_terms.bic:
                    institution = ET.SubElement(payment_means, f"{{{NAMESPACES['ram']}}}PayeeSpecifiedCreditorFinancialInstitution")
                    bic_elem = ET.SubElement(institution, f"{{{NAMESPACES['ram']}}}BICID")
                    bic_elem.text = data.payment_terms.bic

        # TVA
        self._add_tax_summary(settlement, data)

        # Conditions de paiement
        if data.payment_terms and data.payment_terms.due_date:
            terms = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}SpecifiedTradePaymentTerms")
            due_date = ET.SubElement(terms, f"{{{NAMESPACES['ram']}}}DueDateDateTime")
            due_str = ET.SubElement(due_date, f"{{{NAMESPACES['udt']}}}DateTimeString", format="102")
            due_str.text = data.payment_terms.due_date.strftime("%Y%m%d")

        # Totaux
        monetary = ET.SubElement(settlement, f"{{{NAMESPACES['ram']}}}SpecifiedTradeSettlementHeaderMonetarySummation")

        line_total = ET.SubElement(monetary, f"{{{NAMESPACES['ram']}}}LineTotalAmount")
        line_total.text = str(data.total_ht)

        tax_basis = ET.SubElement(monetary, f"{{{NAMESPACES['ram']}}}TaxBasisTotalAmount")
        tax_basis.text = str(data.total_ht)

        tax_total = ET.SubElement(monetary, f"{{{NAMESPACES['ram']}}}TaxTotalAmount", currencyID=data.currency_code)
        tax_total.text = str(data.total_tva)

        grand_total = ET.SubElement(monetary, f"{{{NAMESPACES['ram']}}}GrandTotalAmount")
        grand_total.text = str(data.total_ttc)

        due_payable = ET.SubElement(monetary, f"{{{NAMESPACES['ram']}}}DuePayableAmount")
        due_payable.text = str(data.total_ttc)

    def _add_tax_summary(self, parent: ET.Element, data: InvoiceData):
        """Ajouter le récapitulatif TVA."""
        # Grouper les lignes par taux de TVA
        tax_groups = {}
        for line in data.lines:
            rate = line.vat_rate
            if rate not in tax_groups:
                tax_groups[rate] = {
                    "base": Decimal("0"),
                    "amount": Decimal("0"),
                    "category": line.vat_category
                }
            tax_groups[rate]["base"] += line.line_total
            tax_groups[rate]["amount"] += line.line_total * rate / 100

        # Générer un bloc par taux
        for rate, values in tax_groups.items():
            tax = ET.SubElement(parent, f"{{{NAMESPACES['ram']}}}ApplicableTradeTax")

            calc_amount = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}CalculatedAmount")
            calc_amount.text = str(round(values["amount"], 2))

            type_code = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}TypeCode")
            type_code.text = "VAT"

            basis_amount = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}BasisAmount")
            basis_amount.text = str(values["base"])

            cat_code = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}CategoryCode")
            cat_code.text = values["category"].value

            rate_percent = ET.SubElement(tax, f"{{{NAMESPACES['ram']}}}RateApplicablePercent")
            rate_percent.text = str(rate)

    def _to_string(self, root: ET.Element) -> str:
        """Convertir en string XML avec déclaration."""
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    def validate(self, xml_content: str) -> tuple[bool, list[str]]:
        """
        Valider le XML contre le schéma EN16931.

        Returns:
            (is_valid, list of errors)
        """
        errors = []

        try:
            root = ET.fromstring(xml_content)

            # Vérifications basiques
            ns = NAMESPACES

            # Vérifier les éléments obligatoires
            required = [
                f".//{{{ns['rsm']}}}ExchangedDocumentContext",
                f".//{{{ns['rsm']}}}ExchangedDocument",
                f".//{{{ns['ram']}}}ID",
                f".//{{{ns['ram']}}}TypeCode",
                f".//{{{ns['ram']}}}SellerTradeParty",
                f".//{{{ns['ram']}}}BuyerTradeParty",
            ]

            for xpath in required:
                if root.find(xpath) is None:
                    errors.append(f"Élément obligatoire manquant: {xpath}")

            return len(errors) == 0, errors

        except ET.ParseError as e:
            return False, [f"XML invalide: {e}"]


def from_facture(facture: dict, seller: dict, config: dict = None) -> InvoiceData:
    """
    Convertir une facture AZALPLUS en InvoiceData.

    Args:
        facture: Données facture depuis la base
        seller: Données vendeur (tenant)
        config: Configuration optionnelle

    Returns:
        InvoiceData prêt pour XML
    """
    config = config or {}

    # Adresse vendeur
    seller_address = Address(
        line1=seller.get("adresse", ""),
        line2=seller.get("adresse2", ""),
        postal_code=seller.get("code_postal", ""),
        city=seller.get("ville", ""),
        country_code=seller.get("pays", "FR")
    )

    # Vendeur
    seller_party = Party(
        name=seller.get("raison_sociale", ""),
        siret=seller.get("siret", ""),
        siren=seller.get("siret", "")[:9] if seller.get("siret") else "",
        tva_intra=seller.get("tva_intracommunautaire", ""),
        address=seller_address,
        email=seller.get("email", ""),
        legal_form=seller.get("forme_juridique", ""),
        capital=seller.get("capital", ""),
        rcs=seller.get("rcs", "")
    )

    # Client (acheteur)
    client = facture.get("client", {})
    buyer_address = Address(
        line1=client.get("adresse", ""),
        line2=client.get("adresse2", ""),
        postal_code=client.get("code_postal", ""),
        city=client.get("ville", ""),
        country_code=client.get("pays", "FR")
    )

    buyer_party = Party(
        name=client.get("nom", client.get("raison_sociale", "")),
        siret=client.get("siret", ""),
        tva_intra=client.get("tva_intracommunautaire", ""),
        address=buyer_address,
        email=client.get("email", "")
    )

    # Lignes
    lines = []
    for i, ligne in enumerate(facture.get("lignes", []), 1):
        lines.append(InvoiceLine(
            line_id=str(i),
            description=ligne.get("designation", ""),
            quantity=Decimal(str(ligne.get("quantite", 1))),
            unit_price=Decimal(str(ligne.get("prix_unitaire", 0))),
            vat_rate=Decimal(str(ligne.get("taux_tva", 20))),
            line_total=Decimal(str(ligne.get("montant_ht", 0))),
            item_code=ligne.get("reference", "")
        ))

    # Conditions de paiement
    payment_terms = None
    if facture.get("date_echeance") or seller.get("iban"):
        due_date = None
        if facture.get("date_echeance"):
            if isinstance(facture["date_echeance"], str):
                due_date = datetime.strptime(facture["date_echeance"], "%Y-%m-%d").date()
            else:
                due_date = facture["date_echeance"]

        payment_terms = PaymentTerms(
            due_date=due_date,
            iban=seller.get("iban", ""),
            bic=seller.get("bic", "")
        )

    # Date facture
    invoice_date = facture.get("date_facture", date.today())
    if isinstance(invoice_date, str):
        invoice_date = datetime.strptime(invoice_date, "%Y-%m-%d").date()

    # Type de document
    invoice_type = InvoiceTypeCode.FACTURE
    if facture.get("type") == "avoir":
        invoice_type = InvoiceTypeCode.AVOIR

    return InvoiceData(
        invoice_number=facture.get("numero", ""),
        invoice_date=invoice_date,
        invoice_type=invoice_type,
        seller=seller_party,
        buyer=buyer_party,
        lines=lines,
        total_ht=Decimal(str(facture.get("total_ht", 0))),
        total_tva=Decimal(str(facture.get("total_tva", 0))),
        total_ttc=Decimal(str(facture.get("total_ttc", 0))),
        payment_terms=payment_terms,
        purchase_order_ref=facture.get("reference_commande", ""),
        payment_reference=facture.get("numero", ""),
        notes=[facture.get("notes", "")] if facture.get("notes") else []
    )
