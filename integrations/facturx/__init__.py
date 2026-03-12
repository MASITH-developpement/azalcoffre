# =============================================================================
# AZALPLUS - Facturation Électronique (Factur-X / Chorus Pro / PDP)
# =============================================================================
"""
Module de facturation électronique conforme aux normes françaises.

Fonctionnalités:
- Génération PDF/A-3 (archivable)
- XML Factur-X (EN16931) embarqué
- Intégration PDP (Plateforme de Dématérialisation Partenaire)
- Chorus Pro (B2G - facturation secteur public)
- Réception factures entrantes
- Annuaire PPF (lookup destinataires)

Normes:
- Factur-X 1.0.06 (profil EN16931)
- PDF/A-3b ISO 19005-3
- EN16931 (norme européenne)

Usage:
    from integrations.facturx import FacturXGenerator, FacturXProfile

    # Générer une facture Factur-X
    generator = FacturXGenerator(profile=FacturXProfile.EN16931)
    result = generator.generate(pdf_bytes, invoice_data)

    if result.is_valid:
        # PDF/A-3 avec XML embarqué
        save(result.pdf_content)
"""

# Générateur principal
from .generator import FacturXGenerator, FacturXProfile, FacturXResult, generate_facturx

# PDF/A-3
from .pdf_a3 import PDFAConverter, create_facturx_pdf

# XML Builder
from .xml_builder import (
    XMLBuilder,
    InvoiceData,
    Party,
    Address,
    InvoiceLine,
    PaymentTerms,
    InvoiceTypeCode,
    PaymentMeansCode,
    VATCategoryCode,
    from_facture
)

# PDP Client
from .pdp_client import (
    PDPClient,
    PDPConfig,
    PDPProvider,
    PDPInvoice,
    PDPResponse,
    PDPStatusResponse,
    InvoiceStatus,
    InvoiceDirection
)

# Chorus Pro
from .chorus_pro import (
    ChorusProClient,
    ChorusConfig,
    ChorusEnvironment,
    ChorusInvoice,
    ChorusInvoiceStatus,
    ChorusInvoiceType,
    ChorusResponse,
    ChorusStatusResponse,
    ChorusStructure
)

# Réception factures
from .reception import (
    InvoiceReceptionService,
    InvoiceParser,
    InvoiceValidator,
    ReceivedInvoice,
    InvoiceFormat,
    ReceptionStatus,
    ValidationResult
)

# Annuaire PPF
from .annuaire import (
    AnnuairePPF,
    PPFConfig,
    PPFEnvironment,
    RegistrationInfo,
    RoutingInfo,
    LookupResult,
    RoutingType,
    check_siret_registration
)

__all__ = [
    # Générateur
    "FacturXGenerator",
    "FacturXProfile",
    "FacturXResult",
    "generate_facturx",

    # PDF/A-3
    "PDFAConverter",
    "create_facturx_pdf",

    # XML Builder
    "XMLBuilder",
    "InvoiceData",
    "Party",
    "Address",
    "InvoiceLine",
    "PaymentTerms",
    "InvoiceTypeCode",
    "PaymentMeansCode",
    "VATCategoryCode",
    "from_facture",

    # PDP
    "PDPClient",
    "PDPConfig",
    "PDPProvider",
    "PDPInvoice",
    "PDPResponse",
    "PDPStatusResponse",
    "InvoiceStatus",
    "InvoiceDirection",

    # Chorus Pro
    "ChorusProClient",
    "ChorusConfig",
    "ChorusEnvironment",
    "ChorusInvoice",
    "ChorusInvoiceStatus",
    "ChorusInvoiceType",
    "ChorusResponse",
    "ChorusStatusResponse",
    "ChorusStructure",

    # Réception
    "InvoiceReceptionService",
    "InvoiceParser",
    "InvoiceValidator",
    "ReceivedInvoice",
    "InvoiceFormat",
    "ReceptionStatus",
    "ValidationResult",

    # Annuaire PPF
    "AnnuairePPF",
    "PPFConfig",
    "PPFEnvironment",
    "RegistrationInfo",
    "RoutingInfo",
    "LookupResult",
    "RoutingType",
    "check_siret_registration",
]
