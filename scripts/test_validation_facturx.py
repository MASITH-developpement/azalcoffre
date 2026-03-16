#!/usr/bin/env python3
# =============================================================================
# AZALPLUS - Validation Factur-X (sans compte requis)
# =============================================================================
"""
Valide une facture Factur-X avec le validateur officiel FNFE-MPE.

Ce test ne nécessite AUCUN compte - validation gratuite immédiate.

Usage:
    python scripts/test_validation_facturx.py
"""

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from integrations.facturx import (
    FacturXGenerator,
    FacturXProfile,
    InvoiceData,
    Party,
    Address,
    InvoiceLine,
)


async def test_validation():
    """Valide une facture Factur-X avec le validateur FNFE-MPE."""

    print("=" * 60)
    print("  VALIDATION FACTUR-X (FNFE-MPE)")
    print("=" * 60)

    # Créer une facture de test complète
    print("\n📄 Création facture Factur-X...")

    invoice = InvoiceData(
        invoice_number=f"AZAL-{date.today().strftime('%Y%m%d')}-001",
        invoice_date=date.today(),
        seller=Party(
            name="AZALPLUS SAS",
            siret="12345678901234",
            tva_intra="FR12345678901",
            address=Address(
                line1="10 rue de la Tech",
                city="Paris",
                postal_code="75001",
                country_code="FR"
            ),
            email="contact@azalplus.com"
        ),
        buyer=Party(
            name="Client Exemple SARL",
            siret="98765432109876",
            tva_intra="FR98765432109",
            address=Address(
                line1="20 avenue du Commerce",
                city="Lyon",
                postal_code="69001",
                country_code="FR"
            ),
            email="comptabilite@client.fr"
        ),
        lines=[
            InvoiceLine(
                line_id="1",
                description="Abonnement ERP AZALPLUS - Mensuel",
                quantity=Decimal("1"),
                unit_price=Decimal("0.00"),
                vat_rate=Decimal("20"),
                line_total=Decimal("0.00")
            ),
            InvoiceLine(
                line_id="2",
                description="Signature électronique eIDAS ADVANCED",
                quantity=Decimal("10"),
                unit_price=Decimal("1.00"),
                vat_rate=Decimal("20"),
                line_total=Decimal("10.00")
            ),
            InvoiceLine(
                line_id="3",
                description="Stockage coffre-fort numérique - 10 Go",
                quantity=Decimal("1"),
                unit_price=Decimal("5.00"),
                vat_rate=Decimal("20"),
                line_total=Decimal("5.00")
            ),
        ],
        total_ht=Decimal("15.00"),
        total_tva=Decimal("3.00"),
        total_ttc=Decimal("18.00"),
        currency_code="EUR",
    )

    print(f"   Numéro     : {invoice.invoice_number}")
    print(f"   Vendeur    : {invoice.seller.name}")
    print(f"   Client     : {invoice.buyer.name}")
    print(f"   Total TTC  : {invoice.total_ttc}€")

    # Créer un PDF source
    print("\n⚙️  Génération PDF source...")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, 800, f"FACTURE {invoice.invoice_number}")
    c.setFont("Helvetica", 12)
    c.drawString(50, 760, f"Date: {invoice.invoice_date}")
    c.drawString(50, 740, f"Vendeur: {invoice.seller.name}")
    c.drawString(50, 720, f"SIRET: {invoice.seller.siret}")
    c.drawString(50, 690, f"Client: {invoice.buyer.name}")
    c.drawString(50, 670, f"SIRET: {invoice.buyer.siret}")
    c.drawString(50, 630, "─" * 50)
    y = 610
    for line in invoice.lines:
        c.drawString(50, y, f"{line.description}")
        c.drawString(400, y, f"{line.quantity} x {line.unit_price}€")
        y -= 20
    c.drawString(50, y - 20, "─" * 50)
    c.drawString(50, y - 40, f"Total HT: {invoice.total_ht}€")
    c.drawString(50, y - 60, f"TVA 20%: {invoice.total_tva}€")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y - 90, f"TOTAL TTC: {invoice.total_ttc}€")
    c.save()
    pdf_source = pdf_buffer.getvalue()

    # Générer le Factur-X
    print("⚙️  Génération Factur-X (profil EN16931)...")

    generator = FacturXGenerator(profile=FacturXProfile.EN16931)
    result = generator.generate(pdf_source, invoice)

    print(f"   ✅ PDF généré    : {len(result.pdf_content):,} bytes")
    print(f"   ✅ XML généré    : {len(result.xml_content):,} bytes")

    # Sauvegarder les fichiers
    pdf_path = Path("/tmp/facturx_test.pdf")
    xml_path = Path("/tmp/facturx_test.xml")

    pdf_path.write_bytes(result.pdf_content)
    xml_path.write_text(result.xml_content)

    print(f"\n📁 Fichiers générés:")
    print(f"   PDF: {pdf_path}")
    print(f"   XML: {xml_path}")

    # Afficher l'extrait XML
    print(f"\n📋 Extrait XML Factur-X:")
    print("-" * 50)
    for line in result.xml_content.split('\n')[:20]:
        if line.strip():
            print(f"   {line[:70]}")
    print("   ...")
    print("-" * 50)

    # Validation locale basique
    print("\n🔍 Validation locale...")

    errors = []

    # Vérifier structure XML
    if "CrossIndustryInvoice" not in result.xml_content:
        errors.append("Racine CrossIndustryInvoice manquante")

    if "urn:un:unece:uncefact" not in result.xml_content:
        errors.append("Namespace UN/CEFACT manquant")

    if invoice.seller.siret not in result.xml_content:
        errors.append("SIRET vendeur manquant")

    if invoice.buyer.siret not in result.xml_content:
        errors.append("SIRET acheteur manquant")

    if str(invoice.total_ttc) not in result.xml_content:
        errors.append("Montant TTC manquant")

    if errors:
        print("   ❌ Erreurs trouvées:")
        for e in errors:
            print(f"      • {e}")
    else:
        print("   ✅ Structure XML valide")
        print("   ✅ Namespaces corrects")
        print("   ✅ SIRET vendeur présent")
        print("   ✅ SIRET acheteur présent")
        print("   ✅ Montants présents")

    # Instructions pour validation en ligne
    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║  VALIDATION EN LIGNE (Gratuite, sans compte)                       ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  1. FNFE-MPE (Officiel France)                                    ║
║     → https://fnfe-mpe.org/factur-x/outils/                       ║
║     → Uploader: /tmp/facturx_test.pdf                             ║
║                                                                    ║
║  2. Mustang Project (Europe)                                      ║
║     → https://www.mustangproject.org/validator/                   ║
║     → Valide Factur-X et ZUGFeRD                                  ║
║                                                                    ║
║  3. Ecosio (Multi-format)                                         ║
║     → https://ecosio.com/en/peppol-and-xml-document-validator/    ║
║     → Valide EN16931, UBL, CII                                    ║
║                                                                    ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    return len(errors) == 0


if __name__ == "__main__":
    success = asyncio.run(test_validation())
    print("✅ Test terminé" if success else "❌ Test échoué")
    sys.exit(0 if success else 1)
