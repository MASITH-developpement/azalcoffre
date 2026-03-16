# AZALPLUS - Guide des Intégrations

## Vue d'ensemble

AZALPLUS intègre plusieurs services tiers pour offrir des fonctionnalités avancées :

| Service | Fonction | Commission/Prix |
|---------|----------|-----------------|
| **Fintecture** | Paiements Open Banking | 0.99% + 0.30% = 1.29% |
| **Swan** | Compte bancaire intégré | 9.90€/mois |
| **Twilio** | SMS, WhatsApp, Téléphonie | ~0.065€/SMS |
| **Transporteurs** | Expéditions multi-transporteurs | Variable |

---

## Configuration

### 1. Copier le fichier d'environnement

```bash
cp .env.example .env
```

### 2. Configurer les services

#### Fintecture (Open Banking)

1. Créer un compte sur [console.fintecture.com](https://console.fintecture.com)
2. Récupérer les clés API dans Settings > API Keys
3. Générer une clé RSA privée (ou utiliser celle fournie)
4. Configurer les webhooks sur `https://votre-domaine.com/api/webhooks/fintecture`

```env
FINTECTURE_APP_ID=your_app_id
FINTECTURE_APP_SECRET=your_secret
FINTECTURE_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----
FINTECTURE_WEBHOOK_SECRET=whsec_xxx
FINTECTURE_ENVIRONMENT=sandbox
```

#### Swan (Banking as a Service)

1. Créer un compte sur [dashboard.swan.io](https://dashboard.swan.io)
2. Créer un projet et récupérer les credentials OAuth2
3. Configurer les webhooks

```env
SWAN_CLIENT_ID=your_client_id
SWAN_CLIENT_SECRET=your_client_secret
SWAN_PROJECT_ID=your_project_id
SWAN_WEBHOOK_SECRET=your_webhook_secret
SWAN_ENVIRONMENT=sandbox
```

#### Twilio (SMS & Téléphonie)

1. Créer un compte sur [console.twilio.com](https://console.twilio.com)
2. Acheter un numéro de téléphone français
3. Optionnel: Configurer WhatsApp Business

```env
TWILIO_ACCOUNT_SID=ACxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+33123456789
TWILIO_WHATSAPP_NUMBER=+33123456789
```

#### Transporteurs

```env
# Colissimo
COLISSIMO_CONTRACT_NUMBER=123456
COLISSIMO_PASSWORD=your_password

# Mondial Relay
MONDIAL_RELAY_MERCHANT_ID=ABCD1234
MONDIAL_RELAY_API_KEY=your_api_key
```

---

## Utilisation

### Vérifier la configuration

```bash
# Démarrer le serveur
python -m uvicorn moteur.core:app --reload

# Vérifier les intégrations configurées
curl http://localhost:8000/api/diagnostics/config

# Tester la santé des services
curl http://localhost:8000/api/diagnostics/health

# Tester un service spécifique
curl http://localhost:8000/api/diagnostics/test/fintecture
```

### Paiements Open Banking (Fintecture)

```python
from integrations import settings, FintectureClient
from integrations.fintecture import PaymentRequest

# Créer le client
client = FintectureClient(settings.fintecture.to_config())

# Créer un lien de paiement
payment = await client.create_payment(PaymentRequest(
    amount=150.00,
    reference="FAC-2024-001",
    description="Facture plomberie",
    beneficiary_name="SARL Dupont",
    beneficiary_iban="FR7630001007941234567890185",
    redirect_uri="https://app.azalplus.fr/paiement/success",
    webhook_uri="https://app.azalplus.fr/api/webhooks/fintecture"
))

# Envoyer l'URL au client
print(f"Lien de paiement: {payment.connect_url}")

# Calculer les commissions
commissions = client.calculate_commission(150.00)
print(f"Commission totale: {commissions['commission_totale']}€")
print(f"Montant net: {commissions['montant_net']}€")
```

### Compte bancaire (Swan)

```python
from integrations import settings, SwanClient
from integrations.swan import AccountHolder

# Créer le client
client = SwanClient(settings.swan.to_config())

# Démarrer l'ouverture de compte
onboarding = await client.create_onboarding(
    AccountHolder(
        type="Company",
        company_name="SARL Dupont Plomberie",
        siren="123456789",
        email="contact@dupont.fr"
    ),
    redirect_url="https://app.azalplus.fr/compte/ouverture/success"
)

# Rediriger vers le KYC
print(f"URL KYC: {onboarding['onboarding_url']}")

# Après ouverture: récupérer le solde
account = await client.get_account(account_id)
print(f"Solde: {account.balance_available}€")

# Effectuer un virement
transfer = await client.create_transfer(
    account_id=account_id,
    amount=500.00,
    beneficiary_iban="FR76...",
    beneficiary_name="Fournisseur SAS",
    reference="FAC-ACHAT-001"
)
```

### SMS & Notifications (Twilio)

```python
from integrations import settings, TwilioClient
from integrations.twilio_sms import MessageChannel

# Créer le client
client = TwilioClient(settings.twilio.to_config())

# Envoyer un SMS
msg = await client.send_sms(
    to="+33612345678",
    body="Votre RDV est confirmé pour demain 10h"
)
print(f"Message SID: {msg.sid}")

# Envoyer un WhatsApp
if settings.twilio.whatsapp_enabled:
    msg = await client.send_whatsapp(
        to="+33612345678",
        body="Votre facture est disponible"
    )

# Notification de facture
await client.send_invoice_notification(
    to="+33612345678",
    invoice_number="FAC-2024-001",
    amount=150.00,
    due_date="15/04/2024",
    payment_url="https://pay.azalplus.fr/xxx"
)

# Rappel de RDV
await client.send_appointment_reminder(
    to="+33612345678",
    client_name="M. Dupont",
    appointment_date="12/03/2024",
    appointment_time="14h00",
    service="Entretien chaudière"
)
```

### Expéditions (Transporteurs)

```python
from integrations import settings, TransporteurFactory
from integrations.transporteurs import Address, Parcel, Carrier

# Créer la factory
factory = TransporteurFactory()

# Enregistrer les transporteurs configurés
if settings.transporteurs.colissimo.is_configured:
    factory.register_colissimo(settings.transporteurs.colissimo.to_config())
if settings.transporteurs.mondial_relay.is_configured:
    factory.register_mondial_relay(settings.transporteurs.mondial_relay.to_config())

# Définir les adresses
sender = Address(
    name="Ma Boutique",
    street1="123 rue du Commerce",
    city="Paris",
    postal_code="75001",
    phone="+33123456789"
)

recipient = Address(
    name="M. Client",
    street1="456 avenue de la Gare",
    city="Lyon",
    postal_code="69001",
    email="client@email.com"
)

parcels = [Parcel(weight=1.5)]

# Comparer les tarifs
rates = await factory.get_all_rates(sender, recipient, parcels)
for rate in rates:
    print(f"{rate.carrier.value}: {rate.price}€ - {rate.delivery_days} jours")

# Créer l'expédition avec le moins cher
best_rate = rates[0]
label = await factory.create_shipment(
    best_rate.carrier,
    sender, recipient, parcels,
    best_rate.service
)
print(f"Tracking: {label.tracking_number}")
print(f"Étiquette: {label.label_url}")

# Suivre le colis
events = await factory.get_tracking(best_rate.carrier, label.tracking_number)
for event in events:
    print(f"{event.timestamp}: {event.description}")
```

### Calculs automatiques

```python
from integrations import get_calcul_engine

engine = get_calcul_engine()

# Calculer les totaux d'une facture
facture = {
    "lignes": [
        {"quantite": 2, "prix_unitaire": 100, "tva_code": "TVA_20"},
        {"quantite": 1, "prix_unitaire": 50, "tva_code": "TVA_10"},
    ],
    "date": "2024-03-15",
    "conditions_paiement": "30_JOURS"
}

facture = engine.compute("factures", facture)
print(f"Total TTC: {facture['montant_ttc']}€")
print(f"Échéance: {facture['date_echeance']}")
```

---

## Webhooks

### Configuration des URLs

| Service | URL Webhook |
|---------|-------------|
| Fintecture | `https://app.azalplus.fr/api/webhooks/fintecture` |
| Swan | `https://app.azalplus.fr/api/webhooks/swan` |
| Twilio | `https://app.azalplus.fr/api/webhooks/twilio` |
| Colissimo | `https://app.azalplus.fr/api/webhooks/transporteurs/colissimo` |

### Événements gérés

#### Fintecture
- `payment.successful` → Marquer facture payée
- `payment.unsuccessful` → Enregistrer l'échec
- `payment.cancelled` → Marquer annulé

#### Swan
- `Transaction.Booked` → Synchroniser transaction
- `Account.Opened` → Enregistrer IBAN

#### Twilio
- `MessageStatus` → Mise à jour statut SMS
- `CallCompleted` → Enregistrer durée appel

---

## Tests

### Exécuter les tests

```bash
# Tous les tests d'intégration
pytest tests/test_integrations.py -v

# Un service spécifique
pytest tests/test_integrations.py::TestFintectureClient -v

# Avec couverture
pytest tests/test_integrations.py --cov=integrations --cov-report=html
```

### Mode sandbox

Tous les services ont un mode sandbox pour les tests :

```env
FINTECTURE_ENVIRONMENT=sandbox
SWAN_ENVIRONMENT=sandbox
```

Les transactions en sandbox ne génèrent pas de vrais paiements.

---

## Dépannage

### Erreurs courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| `Signature invalide` | Mauvais webhook secret | Vérifier `*_WEBHOOK_SECRET` |
| `401 Unauthorized` | Clés API invalides | Régénérer les clés |
| `Connection timeout` | Service indisponible | Vérifier le statut du service |
| `SSL Error` | Certificat invalide | Mettre à jour les certificats |

### Logs

```bash
# Voir les logs en temps réel
tail -f /var/log/azalplus/integrations.log

# Filtrer par service
grep "fintecture" /var/log/azalplus/integrations.log
```

### Support

- Fintecture: support@fintecture.com
- Swan: support@swan.io
- Twilio: support.twilio.com
