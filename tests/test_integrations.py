# =============================================================================
# AZALPLUS - Tests des Intégrations
# =============================================================================
"""
Tests unitaires pour les intégrations API et calculs.

Usage:
    pytest tests/test_integrations.py -v
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Import des modules à tester
import sys
sys.path.insert(0, "/home/ubuntu/azalplus")

from integrations.calculs import (
    FactureCalculator,
    DevisCalculator,
    StockCalculator,
    RentabiliteCalculator,
    ImmobilierCalculator,
    CalculEngine,
    money,
    percentage,
    tva_rate_to_decimal,
)

from integrations.fintecture import (
    FintectureConfig,
    FintectureClient,
    PaymentRequest,
    PaymentStatus,
    FintectureEnvironment,
)

from integrations.swan import (
    SwanConfig,
    SwanClient,
    AccountHolder,
    SwanEnvironment,
)

from integrations.twilio_sms import (
    TwilioConfig,
    TwilioClient,
    MessageChannel,
)

from integrations.transporteurs import (
    Address,
    Parcel,
    Carrier,
    ColissimoConfig,
    ColissimoClient,
    MondialRelayConfig,
    MondialRelayClient,
    TransporteurFactory,
)

from integrations.webhooks import (
    WebhookHandler,
    WebhookSource,
    WebhookEvent,
    WebhookStatus,
)


# =============================================================================
# Tests Calculs
# =============================================================================

class TestMoneyUtils:
    """Tests utilitaires monétaires."""

    def test_money_rounding(self):
        assert money(10.555) == Decimal("10.56")
        assert money(10.554) == Decimal("10.55")
        assert money(100.0) == Decimal("100.00")

    def test_percentage(self):
        assert percentage(25, 100) == 25.0
        assert percentage(1, 3) == 33.33
        assert percentage(0, 100) == 0.0
        assert percentage(50, 0) == 0.0

    def test_tva_rates(self):
        assert tva_rate_to_decimal("TVA_20") == Decimal("0.20")
        assert tva_rate_to_decimal("TVA_10") == Decimal("0.10")
        assert tva_rate_to_decimal("TVA_5_5") == Decimal("0.055")
        assert tva_rate_to_decimal("EXONERE") == Decimal("0")
        assert tva_rate_to_decimal("UNKNOWN") == Decimal("0.20")  # Default


class TestFactureCalculator:
    """Tests calculs factures."""

    def test_calculate_ligne_simple(self):
        ligne = {
            "quantite": 2,
            "prix_unitaire": 100,
            "tva_code": "TVA_20"
        }
        result = FactureCalculator.calculate_ligne(ligne)

        assert result["montant_ht"] == 200.0
        assert result["montant_tva"] == 40.0
        assert result["montant_ttc"] == 240.0
        assert result["montant_remise"] == 0.0

    def test_calculate_ligne_avec_remise(self):
        ligne = {
            "quantite": 1,
            "prix_unitaire": 100,
            "remise_pct": 10,
            "tva_code": "TVA_20"
        }
        result = FactureCalculator.calculate_ligne(ligne)

        assert result["montant_brut"] == 100.0
        assert result["montant_remise"] == 10.0
        assert result["montant_ht"] == 90.0
        assert result["montant_tva"] == 18.0
        assert result["montant_ttc"] == 108.0

    def test_calculate_totaux(self):
        lignes = [
            {"quantite": 2, "prix_unitaire": 100, "tva_code": "TVA_20"},
            {"quantite": 1, "prix_unitaire": 50, "tva_code": "TVA_10"},
        ]
        result = FactureCalculator.calculate_totaux(lignes)

        assert result["sous_total_ht"] == 250.0
        assert result["total_ht"] == 250.0
        assert result["total_ttc"] == 295.0  # 200*1.2 + 50*1.1 = 240 + 55 = 295

    def test_calculate_totaux_avec_remise_globale(self):
        lignes = [
            {"quantite": 1, "prix_unitaire": 100, "tva_code": "TVA_20"},
        ]
        result = FactureCalculator.calculate_totaux(lignes, remise_globale_pct=10)

        assert result["sous_total_ht"] == 100.0
        assert result["remise_globale"] == 10.0
        assert result["total_ht"] == 90.0

    def test_calculate_echeance(self):
        date_facture = date(2024, 3, 15)

        assert FactureCalculator.calculate_echeance(date_facture, "COMPTANT") == date(2024, 3, 15)
        assert FactureCalculator.calculate_echeance(date_facture, "30_JOURS") == date(2024, 4, 14)
        assert FactureCalculator.calculate_echeance(date_facture, "60_JOURS") == date(2024, 5, 14)

    def test_calculate_echeance_fin_mois(self):
        date_facture = date(2024, 3, 15)
        result = FactureCalculator.calculate_echeance(date_facture, "FIN_MOIS")
        assert result == date(2024, 3, 31)


class TestDevisCalculator:
    """Tests calculs devis."""

    def test_calculate_marge(self):
        lignes = [
            {"quantite": 2, "prix_unitaire": 100, "cout_unitaire": 60},
            {"quantite": 1, "prix_unitaire": 50, "cout_unitaire": 30},
        ]
        result = DevisCalculator.calculate_marge(lignes)

        assert result["total_vente_ht"] == 250.0
        assert result["cout_total"] == 150.0
        assert result["marge_brute"] == 100.0
        assert result["marge_pct"] == 40.0


class TestStockCalculator:
    """Tests calculs stock."""

    def test_calculate_cmp(self):
        # Stock initial: 10 unités à 100€
        # Entrée: 5 unités à 120€
        # CMP = (10*100 + 5*120) / 15 = 1600/15 = 106.67
        result = StockCalculator.calculate_cout_moyen_pondere(
            quantite_actuelle=10,
            cout_actuel=100,
            quantite_entree=5,
            cout_entree=120
        )
        assert result == 106.67

    def test_calculate_rotation(self):
        # Stock moyen 10000€, ventes annuelles 60000€
        # Rotation = 6
        result = StockCalculator.calculate_rotation_stock(10000, 60000)
        assert result == 6.0

    def test_calculate_couverture(self):
        # 100 unités, consommation 5/jour = 20 jours
        result = StockCalculator.calculate_couverture_stock(100, 5)
        assert result == 20


class TestRentabiliteCalculator:
    """Tests calculs rentabilité."""

    def test_calculate_rentabilite_client(self):
        result = RentabiliteCalculator.calculate_rentabilite_client(
            ca_ht=10000,
            marge_brute=3000,
            couts_directs=500
        )
        assert result["marge_brute"] == 3000
        assert result["marge_nette"] == 2500
        assert result["taux_marge_brute"] == 30.0
        assert result["taux_marge_nette"] == 25.0

    def test_calculate_rentabilite_projet(self):
        projet = {
            "budget_prevu": 10000,
            "budget_consomme": 8000,
            "ca_facture": 12000,
            "heures_prevues": 100,
            "heures_realisees": 90
        }
        result = RentabiliteCalculator.calculate_rentabilite_projet(projet)

        assert result["ecart_budget"] == 2000.0
        assert result["marge"] == 4000.0
        assert result["rentable"] is True


class TestImmobilierCalculator:
    """Tests calculs immobilier."""

    def test_calculate_loyer_cc(self):
        assert ImmobilierCalculator.calculate_loyer_cc(800, 150) == 950.0

    def test_calculate_rendement(self):
        result = ImmobilierCalculator.calculate_rendement(
            loyer_annuel=12000,
            prix_acquisition=200000,
            charges_annuelles=2000
        )
        assert result["rendement_brut"] == 6.0
        assert result["rendement_net"] == 5.0


class TestCalculEngine:
    """Tests du moteur de calculs."""

    def test_compute_facture(self):
        engine = CalculEngine()

        data = {
            "lignes": [
                {"quantite": 2, "prix_unitaire": 100, "tva_code": "TVA_20"},
            ],
            "date": "2024-03-15",
            "conditions_paiement": "30_JOURS",
            "montant_paye": 0
        }

        result = engine.compute("factures", data)

        assert result["montant_ht"] == 200.0
        assert result["montant_tva"] == 40.0
        assert result["montant_ttc"] == 240.0
        assert result["reste_a_payer"] == 240.0
        assert result["date_echeance"] == "2024-04-14"

    def test_compute_produit(self):
        engine = CalculEngine()

        data = {
            "prix_vente": 100,
            "cout_achat": 60,
            "quantite_stock": 50,
            "cout_moyen": 55
        }

        result = engine.compute("produits", data)

        assert result["marge_unitaire"] == 40.0
        assert result["taux_marge"] == 40.0
        assert result["valeur_stock"] == 2750.0


# =============================================================================
# Tests Fintecture
# =============================================================================

class TestFintectureConfig:
    """Tests configuration Fintecture."""

    def test_sandbox_urls(self):
        config = FintectureConfig(
            app_id="test",
            app_secret="test",
            private_key="test"
        )
        assert "sandbox" in config.base_url
        assert "sandbox" in config.connect_url

    def test_production_urls(self):
        config = FintectureConfig(
            app_id="test",
            app_secret="test",
            private_key="test",
            environment=FintectureEnvironment.PRODUCTION
        )
        assert "sandbox" not in config.base_url


class TestFintectureClient:
    """Tests client Fintecture."""

    def test_calculate_commission(self):
        config = FintectureConfig("id", "secret", "key")
        client = FintectureClient(config)

        result = client.calculate_commission(100.0)

        assert result["montant_brut"] == 100.0
        assert result["commission_fintecture"] == 0.99
        assert result["commission_azalplus"] == 0.30
        assert result["commission_totale"] == 1.29
        assert result["montant_net"] == 98.71


# =============================================================================
# Tests Transporteurs
# =============================================================================

class TestColissimoRates:
    """Tests tarifs Colissimo."""

    @pytest.mark.asyncio
    async def test_get_rates_france(self):
        config = ColissimoConfig("contract", "password")
        client = ColissimoClient(config)

        sender = Address(name="Expéditeur", city="Paris", postal_code="75001")
        recipient = Address(name="Destinataire", city="Lyon", postal_code="69001", country="FR")
        parcels = [Parcel(weight=1.5)]

        rates = await client.get_rates(sender, recipient, parcels)

        assert len(rates) == 2  # DOM et DOS
        assert rates[0].carrier == Carrier.COLISSIMO
        assert rates[0].price > 0

        await client.close()


class TestMondialRelayRates:
    """Tests tarifs Mondial Relay."""

    @pytest.mark.asyncio
    async def test_get_rates_france(self):
        config = MondialRelayConfig("merchant", "key")
        client = MondialRelayClient(config)

        sender = Address(name="Expéditeur", city="Paris", postal_code="75001")
        recipient = Address(name="Destinataire", city="Lyon", postal_code="69001", country="FR")
        parcels = [Parcel(weight=2.0)]

        rates = await client.get_rates(sender, recipient, parcels)

        assert len(rates) == 1
        assert rates[0].carrier == Carrier.MONDIAL_RELAY
        assert rates[0].price == 5.49  # Tarif 1-3kg

        await client.close()


class TestTransporteurFactory:
    """Tests factory transporteurs."""

    @pytest.mark.asyncio
    async def test_get_all_rates(self):
        factory = TransporteurFactory()

        factory.register_colissimo(ColissimoConfig("c", "p"))
        factory.register_mondial_relay(MondialRelayConfig("m", "k"))

        sender = Address(name="Exp", city="Paris", postal_code="75001")
        recipient = Address(name="Dest", city="Lyon", postal_code="69001", country="FR")
        parcels = [Parcel(weight=1.0)]

        rates = await factory.get_all_rates(sender, recipient, parcels)

        # Devrait avoir Colissimo + Mondial Relay
        assert len(rates) >= 2

        # Trié par prix
        prices = [r.price for r in rates]
        assert prices == sorted(prices)

        await factory.close_all()


# =============================================================================
# Tests Webhooks
# =============================================================================

class TestWebhookHandler:
    """Tests gestionnaire webhooks."""

    def test_register_handler(self):
        handler = WebhookHandler(MagicMock())

        async def my_handler(event):
            return {"ok": True}

        handler.register(WebhookSource.FINTECTURE, "payment.successful", my_handler)

        assert (WebhookSource.FINTECTURE, "payment.successful") in handler._handlers

    def test_configure_secret(self):
        handler = WebhookHandler(MagicMock())
        handler.configure(WebhookSource.FINTECTURE, "my_secret")

        assert handler._secrets[WebhookSource.FINTECTURE] == "my_secret"


# =============================================================================
# Tests Twilio
# =============================================================================

class TestTwilioConfig:
    """Tests configuration Twilio."""

    def test_base_url(self):
        config = TwilioConfig(
            account_sid="AC123",
            auth_token="token",
            phone_number="+33123456789"
        )
        assert "AC123" in config.base_url


class TestTwilioPricing:
    """Tests tarification Twilio."""

    def test_sms_price(self):
        assert TwilioClient.PRICE_SMS_FR == 0.065

    def test_whatsapp_price(self):
        assert TwilioClient.PRICE_WHATSAPP_FR == 0.05


# =============================================================================
# Exécution
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
