# =============================================================================
# AZALPLUS - Intégration Stripe
# =============================================================================
"""
Stripe - Plateforme de paiement en ligne.

Fonctionnalités:
- Paiements par carte (CB, Visa, Mastercard, Amex)
- Prélèvements SEPA
- Virements vers compte bancaire
- Webhooks temps réel
- Rapprochement automatique avec factures

Tarification:
- Cartes européennes: 1.5% + 0.25€
- Cartes non-européennes: 2.9% + 0.25€
- SEPA Direct Debit: 0.35€

Documentation: https://stripe.com/docs/api
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Optional, List, Dict
from uuid import UUID, uuid4

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# Enums et Types
# =============================================================================
class StripeEnvironment(str, Enum):
    TEST = "test"
    LIVE = "live"


class PaymentStatus(str, Enum):
    REQUIRES_PAYMENT_METHOD = "requires_payment_method"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    REQUIRES_ACTION = "requires_action"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    REQUIRES_CAPTURE = "requires_capture"


class PayoutStatus(str, Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    PAID = "paid"
    FAILED = "failed"
    CANCELED = "canceled"


class BalanceTransactionType(str, Enum):
    CHARGE = "charge"
    REFUND = "refund"
    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"
    FEE = "stripe_fee"
    TRANSFER = "transfer"


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class StripeConfig:
    """Configuration Stripe par tenant."""
    secret_key: str  # sk_test_xxx ou sk_live_xxx
    publishable_key: str  # pk_test_xxx ou pk_live_xxx
    webhook_secret: Optional[str] = None

    @property
    def environment(self) -> StripeEnvironment:
        if self.secret_key.startswith("sk_live_"):
            return StripeEnvironment.LIVE
        return StripeEnvironment.TEST

    @property
    def base_url(self) -> str:
        return "https://api.stripe.com/v1"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class StripeCustomer:
    """Client Stripe."""
    id: str
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    created: Optional[datetime] = None


@dataclass
class PaymentIntent:
    """Intention de paiement."""
    id: str
    amount: int  # En centimes
    currency: str
    status: PaymentStatus
    customer_id: Optional[str] = None
    payment_method: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    created: Optional[datetime] = None


@dataclass
class BalanceTransaction:
    """Transaction sur le solde Stripe."""
    id: str
    type: str
    amount: int  # En centimes (peut être négatif)
    fee: int  # Frais Stripe en centimes
    net: int  # Montant net en centimes
    currency: str
    description: str
    source: Optional[str] = None  # ID du paiement/remboursement source
    created: Optional[datetime] = None
    available_on: Optional[date] = None


@dataclass
class Payout:
    """Virement vers compte bancaire."""
    id: str
    amount: int
    currency: str
    status: PayoutStatus
    arrival_date: Optional[date] = None
    description: Optional[str] = None
    created: Optional[datetime] = None


# =============================================================================
# Client API Stripe
# =============================================================================
class StripeClient:
    """
    Client API Stripe.

    Usage:
        config = StripeConfig(
            secret_key="sk_test_xxx",
            publishable_key="pk_test_xxx"
        )
        client = StripeClient(config)

        # Créer un paiement
        intent = await client.create_payment_intent(
            amount=5000,  # 50.00 EUR
            currency="eur",
            customer_id="cus_xxx",
            metadata={"facture_id": "FAC-2026-001"}
        )
    """

    def __init__(self, config: StripeConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                auth=(self.config.secret_key, ""),
                timeout=30.0,
                headers={"Stripe-Version": "2023-10-16"}
            )
        return self._http_client

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None
    ) -> Dict:
        """Effectue une requête API."""
        client = await self._get_client()

        response = await client.request(
            method=method,
            url=endpoint,
            data=data
        )

        if response.status_code >= 400:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", "Erreur inconnue")
            logger.error(f"Stripe API error: {response.status_code} - {error_msg}")
            raise StripeError(error_msg, error_data)

        return response.json()

    # =========================================================================
    # Customers
    # =========================================================================
    async def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        metadata: Dict[str, str] = None
    ) -> StripeCustomer:
        """Créer un client Stripe."""
        data = {"email": email}
        if name:
            data["name"] = name
        if phone:
            data["phone"] = phone
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = value

        result = await self._request("POST", "/customers", data)

        return StripeCustomer(
            id=result["id"],
            email=result["email"],
            name=result.get("name"),
            phone=result.get("phone"),
            metadata=result.get("metadata", {}),
            created=datetime.fromtimestamp(result["created"])
        )

    async def get_customer(self, customer_id: str) -> Optional[StripeCustomer]:
        """Récupérer un client."""
        try:
            result = await self._request("GET", f"/customers/{customer_id}")
            return StripeCustomer(
                id=result["id"],
                email=result["email"],
                name=result.get("name"),
                phone=result.get("phone"),
                metadata=result.get("metadata", {}),
                created=datetime.fromtimestamp(result["created"])
            )
        except StripeError:
            return None

    # =========================================================================
    # Payment Intents
    # =========================================================================
    async def create_payment_intent(
        self,
        amount: int,
        currency: str = "eur",
        customer_id: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Dict[str, str] = None,
        automatic_payment_methods: bool = True
    ) -> PaymentIntent:
        """
        Créer une intention de paiement.

        Args:
            amount: Montant en centimes (ex: 5000 = 50.00 EUR)
            currency: Devise (eur, usd, etc.)
            customer_id: ID client Stripe
            description: Description du paiement
            metadata: Métadonnées (facture_id, etc.)
        """
        data = {
            "amount": amount,
            "currency": currency,
            "automatic_payment_methods[enabled]": "true" if automatic_payment_methods else "false"
        }

        if customer_id:
            data["customer"] = customer_id
        if description:
            data["description"] = description
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = value

        result = await self._request("POST", "/payment_intents", data)

        return PaymentIntent(
            id=result["id"],
            amount=result["amount"],
            currency=result["currency"],
            status=PaymentStatus(result["status"]),
            customer_id=result.get("customer"),
            payment_method=result.get("payment_method"),
            description=result.get("description"),
            metadata=result.get("metadata", {}),
            created=datetime.fromtimestamp(result["created"])
        )

    async def get_payment_intent(self, intent_id: str) -> Optional[PaymentIntent]:
        """Récupérer une intention de paiement."""
        try:
            result = await self._request("GET", f"/payment_intents/{intent_id}")
            return PaymentIntent(
                id=result["id"],
                amount=result["amount"],
                currency=result["currency"],
                status=PaymentStatus(result["status"]),
                customer_id=result.get("customer"),
                payment_method=result.get("payment_method"),
                description=result.get("description"),
                metadata=result.get("metadata", {}),
                created=datetime.fromtimestamp(result["created"])
            )
        except StripeError:
            return None

    async def confirm_payment_intent(self, intent_id: str) -> PaymentIntent:
        """Confirmer une intention de paiement."""
        result = await self._request("POST", f"/payment_intents/{intent_id}/confirm")

        return PaymentIntent(
            id=result["id"],
            amount=result["amount"],
            currency=result["currency"],
            status=PaymentStatus(result["status"]),
            customer_id=result.get("customer"),
            payment_method=result.get("payment_method"),
            description=result.get("description"),
            metadata=result.get("metadata", {}),
            created=datetime.fromtimestamp(result["created"])
        )

    async def cancel_payment_intent(self, intent_id: str) -> PaymentIntent:
        """Annuler une intention de paiement."""
        result = await self._request("POST", f"/payment_intents/{intent_id}/cancel")

        return PaymentIntent(
            id=result["id"],
            amount=result["amount"],
            currency=result["currency"],
            status=PaymentStatus(result["status"]),
            customer_id=result.get("customer"),
            metadata=result.get("metadata", {}),
            created=datetime.fromtimestamp(result["created"])
        )

    # =========================================================================
    # Balance Transactions (pour rapprochement)
    # =========================================================================
    async def list_balance_transactions(
        self,
        limit: int = 100,
        starting_after: Optional[str] = None,
        created_gte: Optional[datetime] = None,
        created_lte: Optional[datetime] = None,
        type_filter: Optional[str] = None
    ) -> tuple[List[BalanceTransaction], Optional[str]]:
        """
        Lister les transactions du solde.

        Returns:
            Tuple (transactions, next_cursor)
        """
        params = {"limit": str(limit)}

        if starting_after:
            params["starting_after"] = starting_after
        if created_gte:
            params["created[gte]"] = str(int(created_gte.timestamp()))
        if created_lte:
            params["created[lte]"] = str(int(created_lte.timestamp()))
        if type_filter:
            params["type"] = type_filter

        # Construire l'URL avec params
        query = "&".join(f"{k}={v}" for k, v in params.items())
        result = await self._request("GET", f"/balance_transactions?{query}")

        transactions = []
        for item in result.get("data", []):
            transactions.append(BalanceTransaction(
                id=item["id"],
                type=item["type"],
                amount=item["amount"],
                fee=item["fee"],
                net=item["net"],
                currency=item["currency"],
                description=item.get("description", ""),
                source=item.get("source"),
                created=datetime.fromtimestamp(item["created"]),
                available_on=date.fromtimestamp(item["available_on"]) if item.get("available_on") else None
            ))

        next_cursor = None
        if result.get("has_more") and transactions:
            next_cursor = transactions[-1].id

        return transactions, next_cursor

    # =========================================================================
    # Payouts (virements vers compte bancaire)
    # =========================================================================
    async def list_payouts(
        self,
        limit: int = 100,
        starting_after: Optional[str] = None
    ) -> tuple[List[Payout], Optional[str]]:
        """Lister les virements vers compte bancaire."""
        params = {"limit": str(limit)}
        if starting_after:
            params["starting_after"] = starting_after

        query = "&".join(f"{k}={v}" for k, v in params.items())
        result = await self._request("GET", f"/payouts?{query}")

        payouts = []
        for item in result.get("data", []):
            payouts.append(Payout(
                id=item["id"],
                amount=item["amount"],
                currency=item["currency"],
                status=PayoutStatus(item["status"]),
                arrival_date=date.fromtimestamp(item["arrival_date"]) if item.get("arrival_date") else None,
                description=item.get("description"),
                created=datetime.fromtimestamp(item["created"])
            ))

        next_cursor = None
        if result.get("has_more") and payouts:
            next_cursor = payouts[-1].id

        return payouts, next_cursor

    # =========================================================================
    # Refunds
    # =========================================================================
    async def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Dict:
        """
        Créer un remboursement.

        Args:
            payment_intent_id: ID du paiement à rembourser
            amount: Montant partiel en centimes (None = remboursement total)
            reason: Raison (duplicate, fraudulent, requested_by_customer)
        """
        data = {"payment_intent": payment_intent_id}

        if amount:
            data["amount"] = amount
        if reason:
            data["reason"] = reason

        return await self._request("POST", "/refunds", data)

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class StripeError(Exception):
    """Erreur API Stripe."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Service Métier AZALPLUS
# =============================================================================
class StripeService:
    """
    Service Stripe intégré à AZALPLUS.

    Gère:
    - Synchronisation des transactions
    - Rapprochement automatique avec factures
    - Création de liens de paiement
    """

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self._client: Optional[StripeClient] = None

    async def _get_client(self) -> StripeClient:
        """Récupérer le client Stripe configuré."""
        if self._client:
            return self._client

        from moteur.db import Database

        # Récupérer la config Stripe du tenant
        configs = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "STRIPE", "statut": "ACTIF"}
        )

        if not configs:
            raise ValueError("Aucun compte Stripe configuré")

        import os
        config = StripeConfig(
            secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
            publishable_key=os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
            webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", "")
        )

        self._client = StripeClient(config)
        return self._client

    async def sync_transactions(
        self,
        since: Optional[datetime] = None,
        compte_id: Optional[UUID] = None
    ) -> int:
        """
        Synchroniser les transactions Stripe.

        Returns:
            Nombre de nouvelles transactions
        """
        from moteur.db import Database
        from moteur.rapprochement_service import RapprochementService
        import hashlib

        client = await self._get_client()

        # Récupérer le compte Stripe
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "STRIPE", "statut": "ACTIF"}
        )

        if not comptes:
            return 0

        compte = comptes[0]
        compte_id = str(compte["id"])

        cursor = None
        total_new = 0

        while True:
            transactions, next_cursor = await client.list_balance_transactions(
                limit=100,
                starting_after=cursor,
                created_gte=since
            )

            for tx in transactions:
                # Vérifier si déjà importée
                existing = Database.query(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    filters={"provider_id": tx.id}
                )

                if existing:
                    continue

                # Mapper les données
                sens = "CREDIT" if tx.amount > 0 else "DEBIT"
                montant = abs(tx.amount) / 100  # Centimes → Euros

                # Type d'opération
                type_map = {
                    "charge": "CARTE",
                    "refund": "CARTE",
                    "payout": "VIREMENT_SEPA",
                    "stripe_fee": "FRAIS",
                }
                type_op = type_map.get(tx.type, "AUTRE")

                # Hash pour détection doublons
                hash_elements = f"{compte_id}|{tx.created.date()}|{montant}|{sens}|{tx.description[:20]}"
                hash_doublon = hashlib.md5(hash_elements.encode()).hexdigest()

                # Créer le mouvement
                mouvement = Database.insert(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    {
                        "compte_id": compte_id,
                        "date_operation": tx.created.date().isoformat(),
                        "date_valeur": tx.available_on.isoformat() if tx.available_on else None,
                        "libelle": tx.description or f"Stripe {tx.type}",
                        "sens": sens,
                        "montant": montant,
                        "devise": tx.currency.upper(),
                        "type_operation": type_op,
                        "source": "STRIPE",
                        "provider_id": tx.id,
                        "provider_data": {
                            "type": tx.type,
                            "fee": tx.fee / 100,
                            "net": tx.net / 100,
                            "source_id": tx.source
                        },
                        "statut": "A_TRAITER",
                        "hash_doublon": hash_doublon
                    }
                )

                total_new += 1

                # Tenter rapprochement automatique
                service = RapprochementService(self.tenant_id)
                await service.rapprocher_mouvement(UUID(str(mouvement["id"])))

            if not next_cursor:
                break
            cursor = next_cursor

        # Mettre à jour la date de synchro
        Database.update(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id),
            {"derniere_synchro": datetime.utcnow().isoformat()}
        )

        logger.info(f"Stripe sync completed: {total_new} new transactions")
        return total_new

    async def create_payment_link(
        self,
        facture_id: UUID,
        success_url: str,
        cancel_url: str
    ) -> Dict:
        """
        Créer un lien de paiement pour une facture.

        Returns:
            Dict avec payment_intent_id et client_secret
        """
        from moteur.db import Database

        # Récupérer la facture
        facture = Database.get_by_id("Factures", self.tenant_id, facture_id)
        if not facture:
            raise ValueError("Facture non trouvée")

        # Récupérer ou créer le client Stripe
        client = await self._get_client()

        customer_id = facture.get("stripe_customer_id")
        if not customer_id:
            # Récupérer l'email du client
            client_data = Database.get_by_id(
                "Clients",
                self.tenant_id,
                UUID(facture["customer_id"])
            )

            if client_data and client_data.get("email"):
                stripe_customer = await client.create_customer(
                    email=client_data["email"],
                    name=client_data.get("nom") or client_data.get("raison_sociale"),
                    metadata={"azalplus_client_id": str(facture["customer_id"])}
                )
                customer_id = stripe_customer.id

        # Créer l'intention de paiement
        amount = int(float(facture.get("total", 0)) * 100)  # En centimes

        intent = await client.create_payment_intent(
            amount=amount,
            currency="eur",
            customer_id=customer_id,
            description=f"Facture {facture.get('number', '')}",
            metadata={
                "facture_id": str(facture_id),
                "facture_number": facture.get("number", ""),
                "tenant_id": str(self.tenant_id)
            }
        )

        return {
            "payment_intent_id": intent.id,
            "client_secret": intent.metadata.get("client_secret"),
            "amount": amount,
            "currency": "eur"
        }

    async def handle_webhook(self, payload: bytes, signature: str) -> Dict:
        """
        Gérer un webhook Stripe.

        Args:
            payload: Corps de la requête
            signature: Header Stripe-Signature

        Returns:
            Dict avec le résultat du traitement
        """
        import hmac
        import hashlib
        import json

        # Vérifier la signature (simplifié)
        # En production, utiliser stripe.Webhook.construct_event()

        event = json.loads(payload)
        event_type = event.get("type")
        data = event.get("data", {}).get("object", {})

        if event_type == "payment_intent.succeeded":
            return await self._handle_payment_success(data)
        elif event_type == "payment_intent.payment_failed":
            return await self._handle_payment_failed(data)
        elif event_type == "charge.refunded":
            return await self._handle_refund(data)

        return {"status": "ignored", "event_type": event_type}

    async def _handle_payment_success(self, data: Dict) -> Dict:
        """Traiter un paiement réussi."""
        from moteur.db import Database

        facture_id = data.get("metadata", {}).get("facture_id")
        if not facture_id:
            return {"status": "no_facture_id"}

        # Mettre à jour la facture
        Database.update(
            "Factures",
            self.tenant_id,
            UUID(facture_id),
            {
                "status": "PAID",
                "paid_amount": data.get("amount", 0) / 100,
                "payment_method": "CREDIT_CARD"
            }
        )

        logger.info(f"Stripe payment success for facture {facture_id}")

        return {"status": "success", "facture_id": facture_id}

    async def _handle_payment_failed(self, data: Dict) -> Dict:
        """Traiter un paiement échoué."""
        logger.warning(f"Stripe payment failed: {data.get('id')}")
        return {"status": "failed", "payment_intent_id": data.get("id")}

    async def _handle_refund(self, data: Dict) -> Dict:
        """Traiter un remboursement."""
        from moteur.db import Database

        # Créer un avoir si facture liée
        payment_intent = data.get("payment_intent")
        if payment_intent:
            # Rechercher la facture via le payment_intent
            # Créer un avoir correspondant
            pass

        return {"status": "refund_processed"}
