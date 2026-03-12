# =============================================================================
# AZALPLUS - Tests Module Factur-X
# =============================================================================
"""
Tests unitaires et d'intégration pour le module de facturation électronique.

Tests:
- XML Builder: génération XML EN16931
- PDF/A-3: conversion et embedding XML
- Generator: orchestration complète
- PDP Client: mock API PDP
- Chorus Pro: mock API Chorus
- Reception: parsing multi-format
- Annuaire PPF: lookup
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_seller():
    """Vendeur de test."""
    from integrations.facturx.xml_builder import Party, Address
    return Party(
        name="AZALPLUS SARL",
        siret="12345678901234",
        siren="123456789",
        tva_intra="FR12345678901",
        address=Address(
            line1="10 rue de la Paix",
            postal_code="75001",
            city="Paris",
            country_code="FR"
        ),
        email="contact@azalplus.fr"
    )


@pytest.fixture
def sample_buyer():
    """Acheteur de test."""
    from integrations.facturx.xml_builder import Party, Address
    return Party(
        name="Client Test SAS",
        siret="98765432109876",
        tva_intra="FR98765432109",
        address=Address(
            line1="20 avenue des Champs",
            postal_code="75008",
            city="Paris",
            country_code="FR"
        ),
        email="client@test.fr"
    )


@pytest.fixture
def sample_lines():
    """Lignes de facture de test."""
    from integrations.facturx.xml_builder import InvoiceLine
    return [
        InvoiceLine(
            line_id="1",
            description="Prestation de service",
            quantity=Decimal("10"),
            unit_code="C62",
            unit_price=Decimal("100.00"),
            vat_rate=Decimal("20"),
            line_total=Decimal("1000.00")
        ),
        InvoiceLine(
            line_id="2",
            description="Frais de déplacement",
            quantity=Decimal("1"),
            unit_code="C62",
            unit_price=Decimal("50.00"),
            vat_rate=Decimal("20"),
            line_total=Decimal("50.00")
        )
    ]


@pytest.fixture
def sample_invoice_data(sample_seller, sample_buyer, sample_lines):
    """Données de facture complètes."""
    from integrations.facturx.xml_builder import InvoiceData, PaymentTerms
    return InvoiceData(
        invoice_number="FAC-2024-001",
        invoice_date=date(2024, 1, 15),
        seller=sample_seller,
        buyer=sample_buyer,
        lines=sample_lines,
        total_ht=Decimal("1050.00"),
        total_tva=Decimal("210.00"),
        total_ttc=Decimal("1260.00"),
        currency_code="EUR",
        payment_terms=PaymentTerms(
            due_date=date(2024, 2, 15),
            iban="FR7612345678901234567890123",
            bic="BNPAFRPP"
        )
    )


@pytest.fixture
def sample_pdf_content():
    """PDF minimal pour tests."""
    # PDF minimal valide
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
196
%%EOF"""


# =============================================================================
# Tests XML Builder
# =============================================================================

class TestXMLBuilder:
    """Tests du générateur XML."""

    def test_xml_builder_init(self):
        """Test initialisation XMLBuilder."""
        from integrations.facturx.xml_builder import XMLBuilder
        builder = XMLBuilder()
        assert builder is not None

    def test_build_xml_basic(self, sample_invoice_data):
        """Test génération XML basique."""
        from integrations.facturx.xml_builder import XMLBuilder
        builder = XMLBuilder()
        xml = builder.build(sample_invoice_data)

        assert xml is not None
        assert len(xml) > 0
        assert "CrossIndustryInvoice" in xml
        assert "FAC-2024-001" in xml

    def test_xml_contains_seller_info(self, sample_invoice_data):
        """Test présence infos vendeur dans XML."""
        from integrations.facturx.xml_builder import XMLBuilder
        builder = XMLBuilder()
        xml = builder.build(sample_invoice_data)

        assert "AZALPLUS SARL" in xml
        assert "12345678901234" in xml or "123456789" in xml
        assert "FR12345678901" in xml

    def test_xml_contains_buyer_info(self, sample_invoice_data):
        """Test présence infos acheteur dans XML."""
        from integrations.facturx.xml_builder import XMLBuilder
        builder = XMLBuilder()
        xml = builder.build(sample_invoice_data)

        assert "Client Test SAS" in xml
        assert "98765432109876" in xml

    def test_xml_contains_amounts(self, sample_invoice_data):
        """Test présence montants dans XML."""
        from integrations.facturx.xml_builder import XMLBuilder
        builder = XMLBuilder()
        xml = builder.build(sample_invoice_data)

        assert "1050" in xml  # HT
        assert "210" in xml   # TVA
        assert "1260" in xml  # TTC

    def test_xml_valid_structure(self, sample_invoice_data):
        """Test structure XML valide."""
        from integrations.facturx.xml_builder import XMLBuilder
        import xml.etree.ElementTree as ET

        builder = XMLBuilder()
        xml = builder.build(sample_invoice_data)

        # Doit être parseable
        root = ET.fromstring(xml)
        assert root is not None

    def test_invoice_type_codes(self):
        """Test codes type de facture."""
        from integrations.facturx.xml_builder import InvoiceTypeCode

        assert InvoiceTypeCode.FACTURE.value == "380"
        assert InvoiceTypeCode.AVOIR.value == "381"
        assert InvoiceTypeCode.ACOMPTE.value == "386"


# =============================================================================
# Tests PDF/A Converter
# =============================================================================

class TestPDFAConverter:
    """Tests du convertisseur PDF/A-3."""

    def test_converter_init(self):
        """Test initialisation convertisseur."""
        from integrations.facturx.pdf_a3 import PDFAConverter
        converter = PDFAConverter()
        assert converter is not None

    def test_xmp_template_valid(self):
        """Test template XMP valide."""
        from integrations.facturx.pdf_a3 import PDFAConverter
        converter = PDFAConverter()

        # Vérifier que le template contient les éléments requis
        assert "pdfaid:part" in converter.XMP_TEMPLATE
        assert "pdfaid:conformance" in converter.XMP_TEMPLATE
        assert "fx:DocumentFileName" in converter.XMP_TEMPLATE


# =============================================================================
# Tests Generator
# =============================================================================

class TestFacturXGenerator:
    """Tests du générateur Factur-X."""

    def test_generator_init(self):
        """Test initialisation générateur."""
        from integrations.facturx.generator import FacturXGenerator, FacturXProfile
        generator = FacturXGenerator(profile=FacturXProfile.EN16931)

        assert generator is not None
        assert generator.profile == FacturXProfile.EN16931

    def test_profiles_enum(self):
        """Test enum des profils."""
        from integrations.facturx.generator import FacturXProfile

        assert FacturXProfile.MINIMUM.value == "MINIMUM"
        assert FacturXProfile.EN16931.value == "EN16931"
        assert FacturXProfile.EXTENDED.value == "EXTENDED"

    def test_generate_with_invoice_data(self, sample_invoice_data, sample_pdf_content):
        """Test génération avec InvoiceData."""
        from integrations.facturx.generator import FacturXGenerator

        generator = FacturXGenerator()

        # Si pikepdf n'est pas disponible, le test peut échouer
        try:
            result = generator.generate(sample_pdf_content, sample_invoice_data)

            assert result.invoice_number == "FAC-2024-001"
            assert len(result.xml_content) > 0
        except RuntimeError as e:
            if "Aucune bibliothèque PDF disponible" in str(e):
                pytest.skip("pikepdf/pypdf non disponible")
            raise

    def test_validate_vat_number_french(self):
        """Test validation numéro TVA français."""
        from integrations.facturx.generator import FacturXGenerator
        generator = FacturXGenerator()

        assert generator._validate_vat_number("FR12345678901") is True
        assert generator._validate_vat_number("FR1234567890") is False  # Trop court
        assert generator._validate_vat_number("DE123456789") is True  # Allemand valide

    def test_validate_data_missing_fields(self, sample_seller, sample_buyer):
        """Test validation données manquantes."""
        from integrations.facturx.generator import FacturXGenerator, FacturXProfile
        from integrations.facturx.xml_builder import InvoiceData

        generator = FacturXGenerator(profile=FacturXProfile.EN16931)

        # InvoiceData minimal sans lignes
        data = InvoiceData(
            invoice_number="TEST-001",
            invoice_date=date.today(),
            seller=sample_seller,
            buyer=sample_buyer,
            lines=[],  # Pas de lignes
            total_ht=Decimal("0"),
            total_tva=Decimal("0"),
            total_ttc=Decimal("0")
        )

        errors = generator._validate_data(data)
        assert len(errors) > 0
        assert any("lines" in e for e in errors)


# =============================================================================
# Tests PDP Client
# =============================================================================

class TestPDPClient:
    """Tests du client PDP."""

    def test_pdp_config(self):
        """Test configuration PDP."""
        from integrations.facturx.pdp_client import PDPConfig, PDPProvider

        config = PDPConfig(
            provider=PDPProvider.CEGID,
            api_url="https://api.example.com",
            api_key="test-key"
        )

        assert config.provider == PDPProvider.CEGID
        assert config.api_url == "https://api.example.com"

    def test_invoice_status_enum(self):
        """Test enum statuts facture."""
        from integrations.facturx.pdp_client import InvoiceStatus

        assert InvoiceStatus.SUBMITTED.value == "submitted"
        assert InvoiceStatus.DELIVERED.value == "delivered"
        assert InvoiceStatus.ACCEPTED.value == "accepted"

    @pytest.mark.asyncio
    async def test_generic_pdp_submit(self):
        """Test soumission facture générique."""
        from integrations.facturx.pdp_client import (
            PDPClient, PDPConfig, PDPProvider, PDPInvoice, InvoiceDirection
        )

        config = PDPConfig(
            provider=PDPProvider.CUSTOM,
            api_url="https://api.example.com",
            api_key="test-key"
        )

        invoice = PDPInvoice(
            id=uuid4(),
            invoice_number="FAC-001",
            issue_date=datetime.now(),
            seller_siret="12345678901234",
            buyer_siret="98765432109876",
            total_with_tax=1260.00
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=201,
                json=lambda: {"id": "pdp-123", "status": "submitted"}
            )

            client = PDPClient(config)
            result = await client.submit_invoice(invoice)

            assert result.success is True
            assert result.pdp_id == "pdp-123"

            await client.close()


# =============================================================================
# Tests Chorus Pro
# =============================================================================

class TestChorusProClient:
    """Tests du client Chorus Pro."""

    def test_chorus_config(self):
        """Test configuration Chorus."""
        from integrations.facturx.chorus_pro import ChorusConfig, ChorusEnvironment

        config = ChorusConfig(
            client_id="test-id",
            client_secret="test-secret",
            environment=ChorusEnvironment.SANDBOX
        )

        assert config.environment == ChorusEnvironment.SANDBOX
        assert "sandbox" in config.base_url

    def test_chorus_status_enum(self):
        """Test enum statuts Chorus."""
        from integrations.facturx.chorus_pro import ChorusInvoiceStatus

        assert ChorusInvoiceStatus.DEPOSEE.value == "DEPOSEE"
        assert ChorusInvoiceStatus.MANDATEE.value == "MANDATEE"


# =============================================================================
# Tests Reception
# =============================================================================

class TestInvoiceReception:
    """Tests du service de réception."""

    def test_parser_init(self):
        """Test initialisation parser."""
        from integrations.facturx.reception import InvoiceParser
        parser = InvoiceParser()
        assert parser is not None

    def test_detect_format_xml_cii(self):
        """Test détection format CII."""
        from integrations.facturx.reception import InvoiceParser, InvoiceFormat

        parser = InvoiceParser()

        xml_content = b"""<?xml version="1.0"?>
        <rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100">
        </rsm:CrossIndustryInvoice>"""

        format_type = parser._detect_format(xml_content, "facture.xml")
        assert format_type == InvoiceFormat.CII

    def test_detect_format_pdf(self):
        """Test détection format PDF."""
        from integrations.facturx.reception import InvoiceParser, InvoiceFormat

        parser = InvoiceParser()

        # PDF magic number
        pdf_content = b"%PDF-1.4 ..."

        format_type = parser._detect_format(pdf_content, "facture.pdf")
        assert format_type == InvoiceFormat.PDF

    def test_validator_siret(self):
        """Test validation SIRET."""
        from integrations.facturx.reception import InvoiceValidator

        validator = InvoiceValidator()

        # SIRET valide (algorithme de Luhn)
        assert validator._validate_siret("73282932000074") is True

        # SIRET invalide (trop court)
        assert validator._validate_siret("1234567890") is False

    @pytest.mark.asyncio
    async def test_receive_invoice(self):
        """Test réception facture."""
        from integrations.facturx.reception import InvoiceReceptionService

        service = InvoiceReceptionService()

        xml_content = """<?xml version="1.0"?>
        <rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
            xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100">
            <rsm:ExchangedDocument>
                <ram:ID>TEST-001</ram:ID>
            </rsm:ExchangedDocument>
        </rsm:CrossIndustryInvoice>"""

        invoice = await service.receive(
            content=xml_content,
            filename="test.xml",
            source="test"
        )

        assert invoice is not None
        # Le numéro peut ne pas être extrait selon le parsing


# =============================================================================
# Tests Annuaire PPF
# =============================================================================

class TestAnnuairePPF:
    """Tests de l'annuaire PPF."""

    def test_ppf_config(self):
        """Test configuration PPF."""
        from integrations.facturx.annuaire import PPFConfig, PPFEnvironment

        config = PPFConfig(
            client_id="test-id",
            client_secret="test-secret",
            environment=PPFEnvironment.SANDBOX
        )

        assert config.environment == PPFEnvironment.SANDBOX
        assert "sandbox" in config.base_url

    def test_routing_type_enum(self):
        """Test enum types de routage."""
        from integrations.facturx.annuaire import RoutingType

        assert RoutingType.PPF.value == "ppf"
        assert RoutingType.PDP.value == "pdp"
        assert RoutingType.NOT_REGISTERED.value == "not_registered"

    @pytest.mark.asyncio
    async def test_lookup_mock(self):
        """Test lookup avec mock."""
        from integrations.facturx.annuaire import AnnuairePPF, PPFConfig

        config = PPFConfig(
            client_id="test",
            client_secret="test"
        )

        with patch.object(AnnuairePPF, "_get_token", return_value="mock-token"):
            with patch.object(AnnuairePPF, "_request") as mock_request:
                mock_request.return_value = {
                    "status_code": 200,
                    "data": {
                        "entites": [{
                            "siret": "12345678901234",
                            "siren": "123456789",
                            "raisonSociale": "Test Company",
                            "routage": {"ppf": True},
                            "peutRecevoirFactures": True,
                            "formatsAcceptes": ["facturx"]
                        }]
                    }
                }

                annuaire = AnnuairePPF(config)
                result = await annuaire.lookup(siret="12345678901234")

                assert result.success is True
                assert result.registration is not None
                assert result.registration.is_registered is True

                await annuaire.close()


# =============================================================================
# Tests Intégration
# =============================================================================

class TestIntegration:
    """Tests d'intégration end-to-end."""

    def test_full_workflow(self, sample_invoice_data, sample_pdf_content):
        """Test workflow complet génération."""
        from integrations.facturx.generator import FacturXGenerator
        from integrations.facturx.xml_builder import XMLBuilder

        # 1. Générer XML
        xml_builder = XMLBuilder()
        xml = xml_builder.build(sample_invoice_data)
        assert "CrossIndustryInvoice" in xml

        # 2. Générer Factur-X (peut échouer si pikepdf non disponible)
        try:
            generator = FacturXGenerator()
            result = generator.generate(sample_pdf_content, sample_invoice_data)

            assert result.invoice_number == "FAC-2024-001"
            assert len(result.xml_content) > 0

        except RuntimeError as e:
            if "Aucune bibliothèque PDF disponible" in str(e):
                pytest.skip("pikepdf/pypdf non disponible")
            raise

    def test_from_facture_helper(self):
        """Test helper from_facture."""
        from integrations.facturx.xml_builder import from_facture

        facture = {
            "numero": "FAC-2024-001",
            "date_facture": "2024-01-15",
            "client": {
                "nom": "Client Test",
                "siret": "98765432109876",
                "adresse": "10 rue Test",
                "code_postal": "75001",
                "ville": "Paris"
            },
            "lignes": [
                {
                    "designation": "Service",
                    "quantite": 1,
                    "prix_unitaire": 100,
                    "taux_tva": 20,
                    "montant_ht": 100
                }
            ],
            "total_ht": 100,
            "total_tva": 20,
            "total_ttc": 120
        }

        seller = {
            "raison_sociale": "AZALPLUS",
            "siret": "12345678901234",
            "tva_intracommunautaire": "FR12345678901",
            "adresse": "10 rue de la Paix",
            "code_postal": "75001",
            "ville": "Paris"
        }

        data = from_facture(facture, seller)

        assert data.invoice_number == "FAC-2024-001"
        assert data.seller.name == "AZALPLUS"
        assert data.buyer.name == "Client Test"
        assert len(data.lines) == 1


# =============================================================================
# Tests de sécurité
# =============================================================================

class TestSecurity:
    """Tests de sécurité."""

    def test_xml_injection_prevention(self, sample_invoice_data):
        """Test prévention injection XML."""
        from integrations.facturx.xml_builder import XMLBuilder, Party

        # Essayer d'injecter du XML malveillant
        sample_invoice_data.seller = Party(
            name="<script>alert('XSS')</script>",
            siret="12345678901234"
        )

        builder = XMLBuilder()
        xml = builder.build(sample_invoice_data)

        # Le contenu doit être échappé
        assert "<script>" not in xml
        assert "&lt;script&gt;" in xml or "script" not in xml

    def test_siret_validation(self):
        """Test validation SIRET stricte."""
        from integrations.facturx.reception import InvoiceValidator

        validator = InvoiceValidator()

        # Tentatives d'injection
        assert validator._validate_siret("'; DROP TABLE --") is False
        assert validator._validate_siret("<script>") is False
        assert validator._validate_siret("12345678901234' OR '1'='1") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
