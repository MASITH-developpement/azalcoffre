#!/usr/bin/env python3
# =============================================================================
# AZALPLUS - Test réel Chorus Pro (Qualification)
# =============================================================================
"""
Test d'envoi réel de facture sur Chorus Pro Qualification.

Prérequis:
1. Compte PISTE : https://piste.gouv.fr
2. Activer API "Chorus Pro Qualification"
3. Configurer .env avec CHORUS_CLIENT_ID et CHORUS_CLIENT_SECRET

Usage:
    python scripts/test_chorus_reel.py
"""

import asyncio
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Ajouter le répertoire racine au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.facturx import (
    FacturXGenerator,
    FacturXProfile,
    InvoiceData,
    Party,
    Address,
    InvoiceLine,
    ChorusProClient,
    ChorusConfig,
    ChorusEnvironment,
    ChorusInvoice,
)


async def test_chorus_reel():
    """Test d'envoi réel sur Chorus Pro Qualification."""

    print("=" * 60)
    print("  TEST RÉEL CHORUS PRO (Qualification)")
    print("=" * 60)

    # Vérifier les credentials
    client_id = os.getenv("CHORUS_CLIENT_ID")
    client_secret = os.getenv("CHORUS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("""
❌ Credentials manquants!

Configurez votre fichier .env :

    CHORUS_CLIENT_ID=votre_client_id
    CHORUS_CLIENT_SECRET=votre_secret

Pour obtenir ces credentials:
1. Créer un compte sur https://piste.gouv.fr
2. Activer l'API "Chorus Pro Qualification"
3. Copier le Client ID et Secret
        """)
        return False

    print(f"\n✅ Credentials trouvés (ID: {client_id[:8]}...)")

    # Configuration Chorus Pro Sandbox
    config = ChorusConfig(
        client_id=client_id,
        client_secret=client_secret,
        environment=ChorusEnvironment.SANDBOX,
        # SIRET de test fourni par Chorus Pro
        technical_id="0000000000",  # Remplacer par votre ID technique
    )

    print(f"✅ Environnement: {config.environment.value}")
    print(f"✅ URL API: {config.api_url}")

    # Créer une facture de test
    print("\n📄 Création facture de test...")

    invoice = InvoiceData(
        invoice_number=f"TEST-{date.today().strftime('%Y%m%d')}-001",
        invoice_date=date.today(),
        seller=Party(
            name="AZALPLUS TEST",
            siret="00000000000000",  # SIRET de test
            tva_intra="FR00000000000",
            address=Address(
                line1="1 rue du Test",
                city="Paris",
                postal_code="75001",
                country_code="FR"
            )
        ),
        buyer=Party(
            name="ADMINISTRATION TEST",
            siret="11111111111111",  # SIRET admin de test
            address=Address(
                line1="1 place de la République",
                city="Paris",
                postal_code="75011",
                country_code="FR"
            )
        ),
        lines=[
            InvoiceLine(
                line_id="1",
                description="Prestation de test AZALPLUS",
                quantity=Decimal("1"),
                unit_price=Decimal("100.00"),
                vat_rate=Decimal("20"),
                line_total=Decimal("100.00")
            )
        ],
        total_ht=Decimal("100.00"),
        total_tva=Decimal("20.00"),
        total_ttc=Decimal("120.00"),
        purchase_order_ref="MARCHE-TEST-2026",  # Référence engagement (obligatoire B2G)
    )

    print(f"   Numéro: {invoice.invoice_number}")
    print(f"   Total: {invoice.total_ttc}€ TTC")

    # Générer le Factur-X
    print("\n⚙️  Génération Factur-X...")
    generator = FacturXGenerator(profile=FacturXProfile.EN16931)
    result = generator.generate(None, invoice)

    print(f"   ✅ PDF: {len(result.pdf_content):,} bytes")
    print(f"   ✅ XML: {len(result.xml_content):,} bytes")

    # Envoyer sur Chorus Pro
    print("\n📤 Envoi sur Chorus Pro Qualification...")

    async with ChorusProClient(config) as client:
        # Vérifier la connexion
        print("   → Authentification...")
        is_connected = await client.test_connection()

        if not is_connected:
            print("   ❌ Échec connexion Chorus Pro")
            return False

        print("   ✅ Connecté à Chorus Pro")

        # Préparer la facture Chorus
        chorus_invoice = ChorusInvoice(
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            seller_siret=invoice.seller.siret,
            buyer_siret=invoice.buyer.siret,
            total_ht=float(invoice.total_ht),
            total_ttc=float(invoice.total_ttc),
            engagement_reference=invoice.purchase_order_ref,
            pdf_content=result.pdf_content,
            xml_content=result.xml_content.encode(),
        )

        # Soumettre
        print("   → Soumission facture...")
        response = await client.submit_invoice(chorus_invoice)

        if response.success:
            print(f"""
   ╔════════════════════════════════════════════════════╗
   ║  ✅ FACTURE ENVOYÉE AVEC SUCCÈS!                   ║
   ╠════════════════════════════════════════════════════╣
   ║  ID Chorus    : {response.chorus_id:<30} ║
   ║  Numéro flux  : {response.flux_number:<30} ║
   ║  Statut       : {response.status.value:<30} ║
   ╚════════════════════════════════════════════════════╝
            """)

            # Sauvegarder les références
            with open("/tmp/chorus_test_result.txt", "w") as f:
                f.write(f"chorus_id={response.chorus_id}\n")
                f.write(f"flux_number={response.flux_number}\n")
                f.write(f"status={response.status.value}\n")

            print(f"   📁 Références sauvegardées: /tmp/chorus_test_result.txt")

            # Vérifier le statut après quelques secondes
            print("\n   → Vérification statut (attente 5s)...")
            await asyncio.sleep(5)

            status = await client.get_invoice_status(response.chorus_id)
            print(f"   📊 Statut actuel: {status.status.value}")

            return True
        else:
            print(f"   ❌ Erreur: {response.error_message}")
            return False


if __name__ == "__main__":
    # Charger .env si disponible
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    success = asyncio.run(test_chorus_reel())
    sys.exit(0 if success else 1)
