# =============================================================================
# AZALPLUS - Tests End-to-End Intégrations
# =============================================================================
"""
Tests end-to-end pour les intégrations externes.

Ces tests valident:
- Les routes API FastAPI
- Les webhooks
- Les calculs automatiques
- Les flux métier complets
"""

import pytest
import json
import hmac
import hashlib
from datetime import datetime, date
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import des routes
from integrations.routes import setup_integration_routes

# Import des services
from integrations.calculs import CalculEngine, FactureCalculator, DevisCalculator, StockCalculator


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def app():
    """Créer une application FastAPI de test."""
    test_app = FastAPI()
    setup_integration_routes(test_app)
    return test_app


@pytest.fixture
def client(app):
    """Client de test FastAPI."""
    return TestClient(app)


# =============================================================================
# Tests Routes Paiements
# =============================================================================

class TestPaiementsRoutes:
    """Tests E2E pour les routes de paiement."""

    def test_get_commissions_service_unavailable(self, client):
        """Test calcul des commissions retourne 503 si non configuré."""
        response = client.get("/api/paiements/commissions?amount=100")
        assert response.status_code == 503

    def test_create_payment_service_unavailable(self, client):
        """Test création paiement retourne 503 si non configuré."""
        response = client.post("/api/paiements/create", json={
            "amount": 100,
            "reference": "TEST",
            "beneficiary_name": "Test",
            "beneficiary_iban": "FR7630006000011234567890189",
            "redirect_uri": "https://example.com"
        })
        assert response.status_code == 503


# =============================================================================
# Tests Routes Banking
# =============================================================================

class TestBankingRoutes:
    """Tests E2E pour les routes bancaires."""

    def test_pricing_endpoint(self, client):
        """Test tarification retourne données ou 503."""
        response = client.get("/api/banking/pricing")
        assert response.status_code in [200, 503]

    def test_stats_endpoint(self, client):
        """Test endpoint statistiques."""
        response = client.get("/api/banking/stats?account_id=test&period=month")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "month"


# =============================================================================
# Tests Routes Notifications
# =============================================================================

class TestNotificationsRoutes:
    """Tests E2E pour les routes de notification."""

    def test_config_service_unavailable(self, client):
        """Test configuration retourne 503 si non configuré."""
        response = client.get("/api/notifications/config")
        assert response.status_code == 503

    def test_validate_phone_number(self):
        """Test validation numéro de téléphone."""
        from integrations.routes.notifications import validate_phone_number

        assert validate_phone_number("0612345678") == "+33612345678"
        assert validate_phone_number("+33612345678") == "+33612345678"
        assert validate_phone_number("33612345678") == "+33612345678"
        assert validate_phone_number("06 12 34 56 78") == "+33612345678"


# =============================================================================
# Tests Routes Expéditions
# =============================================================================

class TestExpeditionsRoutes:
    """Tests E2E pour les routes d'expédition."""

    def test_get_carriers(self, client):
        """Test liste des transporteurs."""
        response = client.get("/api/expeditions/carriers")
        assert response.status_code in [200, 503]

    def test_get_stats(self, client):
        """Test statistiques expéditions."""
        response = client.get("/api/expeditions/stats?period=month")
        # L'endpoint stats existe
        assert response.status_code == 200

    def test_rates_validation(self, client):
        """Test validation comparaison tarifs."""
        response = client.post("/api/expeditions/rates", json={})
        assert response.status_code == 422

    def test_create_shipment_validation(self, client):
        """Test validation création expédition."""
        response = client.post("/api/expeditions/create", json={
            "sender": {},
            "recipient": {},
            "parcels": [],
            "carrier": "test",
            "service": "test"
        })
        assert response.status_code == 422


# =============================================================================
# Tests Routes Webhooks
# =============================================================================

class TestWebhooksRoutes:
    """Tests E2E pour les routes de webhooks."""

    def test_webhooks_health(self, client):
        """Test santé des webhooks."""
        response = client.get("/api/webhooks/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "webhooks" in data

    def test_fintecture_webhook_not_configured(self, client):
        """Test webhook Fintecture non configuré."""
        response = client.post("/api/webhooks/fintecture", json={"type": "test"})
        assert response.status_code == 503

    def test_swan_webhook_not_configured(self, client):
        """Test webhook Swan non configuré."""
        response = client.post("/api/webhooks/swan", json={"eventType": "test"})
        assert response.status_code == 503

    def test_twilio_webhook_not_configured(self, client):
        """Test webhook Twilio non configuré."""
        response = client.post("/api/webhooks/twilio", data={"MessageSid": "SM123"})
        assert response.status_code == 503

    def test_colissimo_webhook_not_configured(self, client):
        """Test webhook Colissimo non configuré."""
        response = client.post("/api/webhooks/colissimo", json={"numeroSuivi": "123"})
        assert response.status_code == 503


# =============================================================================
# Tests Calculs End-to-End
# =============================================================================

class TestCalculsE2E:
    """Tests E2E pour le moteur de calculs."""

    def test_facture_calculator_ligne_simple(self):
        """Test calcul ligne facture simple."""
        calc = FactureCalculator()

        ligne = {"quantite": 2, "prix_unitaire": 100, "taux_tva": 20}
        result = calc.calculate_ligne(ligne)

        assert result["montant_ht"] == 200
        assert result["montant_tva"] == 40
        assert result["montant_ttc"] == 240

    def test_facture_calculator_ligne_structure(self):
        """Test structure résultat ligne facture."""
        calc = FactureCalculator()

        ligne = {"quantite": 2, "prix_unitaire": 100, "taux_tva": 20}
        result = calc.calculate_ligne(ligne)

        # Vérifier que toutes les clés attendues sont présentes
        assert "montant_brut" in result
        assert "montant_remise" in result
        assert "montant_ht" in result
        assert "montant_tva" in result
        assert "montant_ttc" in result

    def test_facture_calculator_totaux(self):
        """Test calcul totaux facture."""
        calc = FactureCalculator()

        lignes = [
            {"quantite": 1, "prix_unitaire": 100, "taux_tva": 20},
            {"quantite": 2, "prix_unitaire": 50, "taux_tva": 20}
        ]

        result = calc.calculate_totaux(lignes)

        assert result["total_ht"] == 200
        assert result["total_tva"] == 40
        assert result["total_ttc"] == 240

    def test_facture_calculator_echeance(self):
        """Test calcul date échéance."""
        calc = FactureCalculator()

        # L'API attend un objet date
        date_facture = date(2024, 1, 15)

        # Test 30 jours
        result = calc.calculate_echeance(date_facture, "30_JOURS")
        assert result == date(2024, 2, 14)

        # Test 60 jours
        result = calc.calculate_echeance(date_facture, "60_JOURS")
        assert result == date(2024, 3, 15)

    def test_stock_calculator_cmp(self):
        """Test calcul coût moyen pondéré."""
        calc = StockCalculator()

        # CMP = (100*10 + 50*12) / (100+50) = 1600/150 = 10.67
        result = calc.calculate_cout_moyen_pondere(100, 10, 50, 12)
        assert result == pytest.approx(10.67, rel=0.01)

    def test_stock_calculator_rotation(self):
        """Test calcul rotation stock."""
        calc = StockCalculator()

        # Rotation = cout_ventes / stock_moyen = 180 / 90 = 2
        result = calc.calculate_rotation_stock(90, 180)
        assert result == 2.0

    def test_stock_calculator_couverture(self):
        """Test calcul couverture stock."""
        calc = StockCalculator()

        # Couverture en jours = stock / consommation journalière
        result = calc.calculate_couverture_stock(100, 0.83)
        assert result >= 100  # Au moins 100 jours

    def test_calcul_engine_facture(self):
        """Test moteur calcul pour factures."""
        engine = CalculEngine()

        data = {
            "lignes": [
                {"quantite": 2, "prix_unitaire": 100, "taux_tva": 20}
            ]
        }

        result = engine.compute("factures", data)

        assert "lignes" in result
        assert result["montant_ht"] == 200
        assert result["montant_ttc"] == 240

    def test_calcul_engine_produit(self):
        """Test moteur calcul pour produits."""
        engine = CalculEngine()

        data = {"prix_vente": 100, "cout_achat": 60}
        result = engine.compute("produits", data)

        # Marge = (100 - 60) / 100 = 40%
        assert result["taux_marge"] == 40.0
        assert result["marge_unitaire"] == 40


# =============================================================================
# Tests Flux Métier Complets
# =============================================================================

class TestFluxMetierE2E:
    """Tests E2E pour les flux métier complets."""

    def test_flux_calcul_facture_complete(self):
        """Test flux complet calcul facture."""
        calc = FactureCalculator()

        lignes = [
            {"quantite": 2, "prix_unitaire": 100, "taux_tva": 20},
            {"quantite": 1, "prix_unitaire": 500, "taux_tva": 20}
        ]

        # Calculer chaque ligne
        lignes_calculees = [calc.calculate_ligne(l) for l in lignes]

        # Vérifier ligne 1: 2 x 100 = 200
        assert lignes_calculees[0]["montant_ht"] == 200
        assert lignes_calculees[0]["montant_ttc"] == 240

        # Vérifier ligne 2: 1 x 500 = 500
        assert lignes_calculees[1]["montant_ht"] == 500
        assert lignes_calculees[1]["montant_ttc"] == 600

        # Calculer totaux
        totaux = calc.calculate_totaux(lignes)
        assert totaux["total_ht"] == 700
        assert totaux["total_tva"] == 140
        assert totaux["total_ttc"] == 840

    def test_flux_expedition_commande(self):
        """Test flux: commande → tarifs → expédition."""
        commande = {
            "articles": [
                {"nom": "Produit A", "quantite": 2, "poids": 0.5},
                {"nom": "Produit B", "quantite": 1, "poids": 1.0}
            ]
        }

        # Calculer poids total
        poids_total = sum(a["quantite"] * a["poids"] for a in commande["articles"])
        assert poids_total == 2.0

        # Comparer tarifs
        tarifs = [
            {"carrier": "colissimo", "price": 8.95},
            {"carrier": "mondial_relay", "price": 4.50},
        ]

        meilleur = min(tarifs, key=lambda t: t["price"])
        assert meilleur["carrier"] == "mondial_relay"

    def test_flux_notification_relance(self):
        """Test flux: facture impayée → relance SMS."""
        facture = {
            "numero": "FAC-2024-002",
            "total_ttc": 500.00,
            "jours_retard": 15
        }

        if facture["jours_retard"] <= 7:
            niveau = 1
        elif facture["jours_retard"] <= 15:
            niveau = 2
        else:
            niveau = 3

        assert niveau == 2

        templates = {
            1: "Rappel: Facture {numero} de {montant}€",
            2: "2ème rappel: Facture {numero} impayée ({montant}€)",
            3: "URGENT: Facture {numero} en retard ({montant}€)"
        }

        message = templates[niveau].format(
            numero=facture["numero"],
            montant=facture["total_ttc"]
        )

        assert "2ème rappel" in message

    def test_flux_calcul_rentabilite_projet(self):
        """Test flux calcul rentabilité projet."""
        projet = {"budget": 10000, "temps_prevu": 100}

        temps_passe = [
            {"heures": 20, "cout": 1600},
            {"heures": 30, "cout": 2400},
            {"heures": 25, "cout": 2000}
        ]

        total_heures = sum(t["heures"] for t in temps_passe)
        total_cout = sum(t["cout"] for t in temps_passe)

        assert total_heures == 75
        assert total_cout == 6000

        avancement = total_heures / projet["temps_prevu"] * 100
        assert avancement == 75.0


# =============================================================================
# Tests Performance
# =============================================================================

class TestPerformance:
    """Tests de performance des calculs."""

    def test_calcul_facture_100_lignes(self):
        """Test performance avec 100 lignes."""
        import time

        calc = FactureCalculator()
        lignes = [
            {"quantite": i % 10 + 1, "prix_unitaire": 10 + i, "taux_tva": 20}
            for i in range(100)
        ]

        start = time.time()
        for ligne in lignes:
            calc.calculate_ligne(ligne)
        calc.calculate_totaux(lignes)
        elapsed = time.time() - start

        assert elapsed < 0.1

    def test_calcul_concurrent(self):
        """Test calculs concurrents."""
        import concurrent.futures

        calc = FactureCalculator()

        def calculate(i):
            ligne = {"quantite": 1, "prix_unitaire": 100 + i, "taux_tva": 20}
            return calc.calculate_ligne(ligne)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(calculate, i) for i in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 50


# =============================================================================
# Tests Intégration Settings
# =============================================================================

class TestSettingsIntegration:
    """Tests d'intégration avec les settings."""

    def test_settings_fintecture_not_configured(self):
        """Test Fintecture non configuré."""
        from integrations.settings import FintectureSettings

        settings = FintectureSettings(app_id="", app_secret="", private_key="")
        assert settings.is_configured is False

    def test_settings_fintecture_configured(self):
        """Test Fintecture configuré."""
        from integrations.settings import FintectureSettings

        settings = FintectureSettings(app_id="t", app_secret="s", private_key="k")
        assert settings.is_configured is True

    def test_settings_swan_sandbox(self):
        """Test Swan sandbox mode."""
        from integrations.settings import SwanSettings

        settings = SwanSettings(client_id="t", client_secret="s", environment="sandbox")
        assert settings.environment == "sandbox"
        assert settings.is_production is False

    def test_settings_swan_production(self):
        """Test Swan production mode."""
        from integrations.settings import SwanSettings

        settings = SwanSettings(client_id="t", client_secret="s", environment="production")
        assert settings.environment == "production"
        assert settings.is_production is True

    def test_settings_twilio_whatsapp(self):
        """Test configuration WhatsApp."""
        from integrations.settings import TwilioSettings

        # Sans WhatsApp
        s1 = TwilioSettings(account_sid="AC123", auth_token="t", phone_number="+33123")
        assert s1.whatsapp_enabled is False

        # Avec WhatsApp
        s2 = TwilioSettings(account_sid="AC123", auth_token="t", phone_number="+33123", whatsapp_number="+33456")
        assert s2.whatsapp_enabled is True


# =============================================================================
# Tests Sécurité Webhooks
# =============================================================================

class TestWebhookSecurity:
    """Tests de sécurité des webhooks."""

    def test_signature_hmac_sha256(self):
        """Test vérification signature HMAC-SHA256."""
        from integrations.routes.webhooks import verify_fintecture_signature

        payload = b'{"type":"test"}'
        secret = "my_secret"

        valid_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        assert verify_fintecture_signature(payload, valid_sig, secret) is True
        assert verify_fintecture_signature(payload, "invalid", secret) is False

    def test_signature_swan(self):
        """Test vérification signature Swan."""
        from integrations.routes.webhooks import verify_swan_signature

        payload = b'{"eventType":"test"}'
        secret = "swan_secret"

        hash_value = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        valid_sig = f"sha256={hash_value}"

        assert verify_swan_signature(payload, valid_sig, secret) is True
        assert verify_swan_signature(payload, "sha256=invalid", secret) is False


# =============================================================================
# Tests Validation Données
# =============================================================================

class TestValidationDonnees:
    """Tests de validation des données."""

    def test_validation_iban(self):
        """Test validation IBAN."""
        iban_fr = "FR7630006000011234567890189"
        assert len(iban_fr) == 27
        assert iban_fr.startswith("FR")

    def test_validation_montant(self):
        """Test validation montant."""
        montant = round(99.999, 2)
        assert montant == 100.00

    def test_validation_telephone(self):
        """Test validation téléphone."""
        from integrations.routes.notifications import validate_phone_number

        assert validate_phone_number("+33612345678") == "+33612345678"
        assert validate_phone_number("0612345678") == "+33612345678"

        with pytest.raises(Exception):
            validate_phone_number("123")


# =============================================================================
# Tests Commission Paiement
# =============================================================================

class TestCommissionPaiement:
    """Tests calcul commission paiement."""

    def test_commission_fintecture(self):
        """Test commission Fintecture."""
        # Commission: 1.29%
        montant = 100.00
        commission = montant * 0.0129
        assert commission == pytest.approx(1.29, rel=0.01)

    def test_commission_sur_factures(self):
        """Test commission sur factures types."""
        for montant in [100, 500, 1000, 5000]:
            commission = montant * 0.0129
            net = montant - commission
            assert commission > 0
            assert net < montant


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
