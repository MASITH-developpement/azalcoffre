# =============================================================================
# AZALPLUS - Intégration SumUp
# =============================================================================
"""
SumUp - Solution de paiement par carte (TPE mobile).

Fonctionnalités:
- Encaissement par carte (lecteur physique)
- Paiements à distance (liens de paiement)
- Terminal virtuel
- Factures avec paiement intégré
- Versements automatiques sur compte bancaire

Tarification:
- Transactions: 1.75% (cartes EU) / 2.75% (autres)
- Pas d'abonnement mensuel obligatoire

Documentation: https://developer.sumup.com/
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
class SumUpEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class TransactionType(str, Enum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    PAYOUT = "PAYOUT"
    CHARGE_BACK = "CHARGE_BACK"


class PayoutStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"


class CheckoutStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class SumUpConfig:
    """Configuration SumUp par tenant."""
    client_id: str
    client_secret: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    merchant_code: Optional[str] = None
    environment: SumUpEnvironment = SumUpEnvironment.SANDBOX

    @property
    def base_url(self) -> str:
        return "https://api.sumup.com/v0.1"

    @property
    def oauth_url(self) -> str:
        return "https://api.sumup.com/authorize"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class Merchant:
    """Marchand SumUp."""
    merchant_code: str
    company_name: str
    country_code: str
    currency: str
    payout_type: str
    iban: Optional[str] = None
    bic: Optional[str] = None


@dataclass
class SumUpTransaction:
    """Transaction SumUp."""
    id: str
    transaction_code: str
    amount: float
    currency: str
    status: TransactionStatus
    type: TransactionType
    timestamp: datetime
    payment_type: Optional[str] = None
    card_type: Optional[str] = None
    card_last_4: Optional[str] = None
    product_summary: Optional[str] = None
    internal_id: Optional[str] = None
    payout_date: Optional[date] = None


@dataclass
class Checkout:
    """Lien de paiement SumUp."""
    id: str
    checkout_reference: str
    amount: float
    currency: str
    status: CheckoutStatus
    pay_to_email: str
    description: Optional[str] = None
    redirect_url: Optional[str] = None
    checkout_url: Optional[str] = None
    valid_until: Optional[datetime] = None
    date: Optional[datetime] = None


@dataclass
class Payout:
    """Versement SumUp."""
    id: str
    amount: float
    currency: str
    status: PayoutStatus
    payout_date: date
    reference: Optional[str] = None
    transaction_count: int = 0


# =============================================================================
# Client API SumUp
# =============================================================================
class SumUpClient:
    """
    Client API SumUp.

    Usage:
        config = SumUpConfig(
            client_id="xxx",
            client_secret="xxx",
            access_token="xxx"
        )
        client = SumUpClient(config)

        # Créer un lien de paiement
        checkout = await client.create_checkout(
            amount=50.00,
            currency="EUR",
            description="Facture FAC-001"
        )
    """

    def __init__(self, config: SumUpConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            headers = {
                "Content-Type": "application/json"
            }
            if self.config.access_token:
                headers["Authorization"] = f"Bearer {self.config.access_token}"

            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0,
                headers=headers
            )
        return self._http_client

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        json_data: Dict = None
    ) -> Dict:
        """Effectue une requête API."""
        client = await self._get_client()

        response = await client.request(
            method=method,
            url=endpoint,
            params=params,
            json=json_data
        )

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("message", f"Erreur {response.status_code}")
            logger.error(f"SumUp API error: {response.status_code} - {error_msg}")
            raise SumUpError(error_msg, error_data)

        if response.status_code == 204:
            return {}

        return response.json()

    async def refresh_access_token(self) -> str:
        """Rafraîchir le token d'accès."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sumup.com/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "refresh_token": self.config.refresh_token
                }
            )

            if response.status_code != 200:
                raise SumUpError("Failed to refresh token")

            data = response.json()
            self.config.access_token = data["access_token"]
            if "refresh_token" in data:
                self.config.refresh_token = data["refresh_token"]

            # Recréer le client HTTP
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

            return self.config.access_token

    # =========================================================================
    # Merchant
    # =========================================================================
    async def get_merchant_profile(self) -> Merchant:
        """Récupérer le profil marchand."""
        result = await self._request("GET", "/me")

        return Merchant(
            merchant_code=result["merchant_code"],
            company_name=result.get("company_name", ""),
            country_code=result.get("country_code", ""),
            currency=result.get("currency", "EUR"),
            payout_type=result.get("payout_type", ""),
            iban=result.get("iban"),
            bic=result.get("bic")
        )

    # =========================================================================
    # Transactions
    # =========================================================================
    async def list_transactions(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[SumUpTransaction], int]:
        """
        Lister les transactions.

        Returns:
            Tuple (transactions, total_count)
        """
        params = {
            "limit": limit,
            "offset": offset
        }

        if from_date:
            params["oldest_time"] = from_date.isoformat()
        if to_date:
            params["newest_time"] = to_date.isoformat()
        if status:
            params["statuses[]"] = status

        result = await self._request("GET", "/me/transactions/history", params=params)

        transactions = []
        for tx in result.get("items", []):
            transactions.append(SumUpTransaction(
                id=tx["id"],
                transaction_code=tx["transaction_code"],
                amount=tx["amount"],
                currency=tx["currency"],
                status=TransactionStatus(tx["status"]),
                type=TransactionType(tx.get("type", "PAYMENT")),
                timestamp=datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00")),
                payment_type=tx.get("payment_type"),
                card_type=tx.get("card", {}).get("type"),
                card_last_4=tx.get("card", {}).get("last_4_digits"),
                product_summary=tx.get("product_summary"),
                internal_id=tx.get("internal_id"),
                payout_date=date.fromisoformat(tx["payout_date"]) if tx.get("payout_date") else None
            ))

        return transactions, result.get("total_count", len(transactions))

    async def get_transaction(self, transaction_id: str) -> Optional[SumUpTransaction]:
        """Récupérer une transaction."""
        try:
            result = await self._request("GET", f"/me/transactions/{transaction_id}")
            return SumUpTransaction(
                id=result["id"],
                transaction_code=result["transaction_code"],
                amount=result["amount"],
                currency=result["currency"],
                status=TransactionStatus(result["status"]),
                type=TransactionType(result.get("type", "PAYMENT")),
                timestamp=datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00")),
                payment_type=result.get("payment_type"),
                card_type=result.get("card", {}).get("type"),
                card_last_4=result.get("card", {}).get("last_4_digits"),
                product_summary=result.get("product_summary"),
                internal_id=result.get("internal_id"),
                payout_date=date.fromisoformat(result["payout_date"]) if result.get("payout_date") else None
            )
        except SumUpError:
            return None

    # =========================================================================
    # Checkouts (Liens de paiement)
    # =========================================================================
    async def create_checkout(
        self,
        amount: float,
        currency: str = "EUR",
        checkout_reference: Optional[str] = None,
        description: Optional[str] = None,
        pay_to_email: Optional[str] = None,
        redirect_url: Optional[str] = None,
        valid_for: int = 3600  # Secondes
    ) -> Checkout:
        """
        Créer un lien de paiement.

        Args:
            amount: Montant
            currency: Devise
            checkout_reference: Référence (ex: numéro facture)
            description: Description du paiement
            pay_to_email: Email du bénéficiaire
            redirect_url: URL de redirection après paiement
            valid_for: Durée de validité en secondes
        """
        # Récupérer le merchant code si pas défini
        if not self.config.merchant_code:
            profile = await self.get_merchant_profile()
            self.config.merchant_code = profile.merchant_code

        data = {
            "checkout_reference": checkout_reference or str(uuid4())[:8],
            "amount": amount,
            "currency": currency,
            "merchant_code": self.config.merchant_code
        }

        if description:
            data["description"] = description
        if pay_to_email:
            data["pay_to_email"] = pay_to_email
        if redirect_url:
            data["redirect_url"] = redirect_url

        result = await self._request("POST", "/checkouts", json_data=data)

        return Checkout(
            id=result["id"],
            checkout_reference=result["checkout_reference"],
            amount=result["amount"],
            currency=result["currency"],
            status=CheckoutStatus(result.get("status", "PENDING")),
            pay_to_email=result.get("pay_to_email", ""),
            description=result.get("description"),
            redirect_url=result.get("redirect_url"),
            checkout_url=f"https://checkout.sumup.com/{result['id']}",
            valid_until=datetime.fromisoformat(result["valid_until"].replace("Z", "+00:00")) if result.get("valid_until") else None,
            date=datetime.fromisoformat(result["date"].replace("Z", "+00:00")) if result.get("date") else None
        )

    async def get_checkout(self, checkout_id: str) -> Optional[Checkout]:
        """Récupérer un checkout."""
        try:
            result = await self._request("GET", f"/checkouts/{checkout_id}")
            return Checkout(
                id=result["id"],
                checkout_reference=result["checkout_reference"],
                amount=result["amount"],
                currency=result["currency"],
                status=CheckoutStatus(result.get("status", "PENDING")),
                pay_to_email=result.get("pay_to_email", ""),
                description=result.get("description"),
                redirect_url=result.get("redirect_url"),
                checkout_url=f"https://checkout.sumup.com/{result['id']}",
                valid_until=datetime.fromisoformat(result["valid_until"].replace("Z", "+00:00")) if result.get("valid_until") else None,
                date=datetime.fromisoformat(result["date"].replace("Z", "+00:00")) if result.get("date") else None
            )
        except SumUpError:
            return None

    async def delete_checkout(self, checkout_id: str) -> bool:
        """Annuler un checkout."""
        try:
            await self._request("DELETE", f"/checkouts/{checkout_id}")
            return True
        except SumUpError:
            return False

    # =========================================================================
    # Refunds
    # =========================================================================
    async def refund_transaction(
        self,
        transaction_id: str,
        amount: Optional[float] = None
    ) -> Dict:
        """
        Rembourser une transaction.

        Args:
            transaction_id: ID de la transaction
            amount: Montant partiel (None = remboursement total)
        """
        data = {}
        if amount:
            data["amount"] = amount

        return await self._request(
            "POST",
            f"/me/refund/{transaction_id}",
            json_data=data if data else None
        )

    # =========================================================================
    # Payouts
    # =========================================================================
    async def list_payouts(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[Payout], int]:
        """Lister les versements."""
        params = {
            "limit": limit,
            "offset": offset
        }

        if from_date:
            params["start_date"] = from_date.isoformat()
        if to_date:
            params["end_date"] = to_date.isoformat()

        result = await self._request("GET", "/me/financials/payouts", params=params)

        payouts = []
        for p in result.get("items", []):
            payouts.append(Payout(
                id=p["id"],
                amount=p["amount"],
                currency=p["currency"],
                status=PayoutStatus(p["status"]),
                payout_date=date.fromisoformat(p["payout_date"]),
                reference=p.get("reference"),
                transaction_count=p.get("transaction_count", 0)
            ))

        return payouts, result.get("total_count", len(payouts))

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class SumUpError(Exception):
    """Erreur API SumUp."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Service Métier AZALPLUS
# =============================================================================
class SumUpService:
    """
    Service SumUp intégré à AZALPLUS.

    Gère:
    - Synchronisation des transactions TPE
    - Liens de paiement pour factures
    - Rapprochement automatique
    """

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self._client: Optional[SumUpClient] = None

    async def _get_client(self) -> SumUpClient:
        """Récupérer le client SumUp configuré."""
        if self._client:
            return self._client

        import os
        config = SumUpConfig(
            client_id=os.getenv("SUMUP_CLIENT_ID", ""),
            client_secret=os.getenv("SUMUP_CLIENT_SECRET", ""),
            access_token=os.getenv("SUMUP_ACCESS_TOKEN", ""),
            refresh_token=os.getenv("SUMUP_REFRESH_TOKEN", ""),
            environment=SumUpEnvironment.SANDBOX
        )

        self._client = SumUpClient(config)
        return self._client

    async def sync_transactions(
        self,
        since: Optional[date] = None
    ) -> int:
        """
        Synchroniser les transactions SumUp.

        Returns:
            Nombre de nouvelles transactions
        """
        from moteur.db import Database
        from moteur.rapprochement_service import RapprochementService
        import hashlib

        client = await self._get_client()

        # Récupérer le compte SumUp
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SUMUP", "statut": "ACTIF"}
        )

        if not comptes:
            return 0

        compte = comptes[0]
        compte_id = str(compte["id"])

        total_new = 0
        offset = 0

        while True:
            transactions, total = await client.list_transactions(
                from_date=since,
                status=["SUCCESSFUL"],
                limit=100,
                offset=offset
            )

            if not transactions:
                break

            for tx in transactions:
                # Vérifier si déjà importée
                existing = Database.query(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    filters={"provider_id": tx.transaction_code}
                )

                if existing:
                    continue

                # Les transactions SumUp sont des encaissements (CREDIT)
                sens = "CREDIT" if tx.type == TransactionType.PAYMENT else "DEBIT"
                if tx.type == TransactionType.REFUND:
                    sens = "DEBIT"

                # Hash pour détection doublons
                date_op = tx.timestamp.date()
                hash_elements = f"{compte_id}|{date_op}|{tx.amount}|{sens}|{tx.transaction_code}"
                hash_doublon = hashlib.md5(hash_elements.encode()).hexdigest()

                # Créer le mouvement
                mouvement = Database.insert(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    {
                        "compte_id": compte_id,
                        "date_operation": date_op.isoformat(),
                        "date_valeur": tx.payout_date.isoformat() if tx.payout_date else None,
                        "libelle": tx.product_summary or f"SumUp {tx.card_type or 'Card'} ***{tx.card_last_4 or ''}",
                        "libelle_complementaire": tx.internal_id or "",
                        "sens": sens,
                        "montant": abs(tx.amount),
                        "devise": tx.currency,
                        "type_operation": "CARTE",
                        "source": "SUMUP",
                        "provider_id": tx.transaction_code,
                        "provider_data": {
                            "sumup_id": tx.id,
                            "type": tx.type.value,
                            "payment_type": tx.payment_type,
                            "card_type": tx.card_type,
                            "card_last_4": tx.card_last_4,
                            "payout_date": tx.payout_date.isoformat() if tx.payout_date else None
                        },
                        "statut": "A_TRAITER",
                        "hash_doublon": hash_doublon
                    }
                )

                total_new += 1

                # Tenter rapprochement automatique
                service = RapprochementService(self.tenant_id)
                await service.rapprocher_mouvement(UUID(str(mouvement["id"])))

            if offset + 100 >= total:
                break
            offset += 100

        # Mettre à jour la date de synchro
        Database.update(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id),
            {"derniere_synchro": datetime.utcnow().isoformat()}
        )

        logger.info(f"SumUp sync completed: {total_new} new transactions")
        return total_new

    async def create_payment_link(
        self,
        facture_id: UUID,
        redirect_url: Optional[str] = None
    ) -> Dict:
        """
        Créer un lien de paiement SumUp pour une facture.

        Returns:
            Dict avec checkout_id et checkout_url
        """
        from moteur.db import Database

        # Récupérer la facture
        facture = Database.get_by_id("Factures", self.tenant_id, facture_id)
        if not facture:
            raise ValueError("Facture non trouvée")

        client = await self._get_client()

        # Créer le checkout
        checkout = await client.create_checkout(
            amount=float(facture.get("total", 0)),
            currency="EUR",
            checkout_reference=facture.get("number", str(facture_id)[:8]),
            description=f"Facture {facture.get('number', '')}",
            redirect_url=redirect_url
        )

        # Sauvegarder le lien dans les métadonnées de la facture
        Database.update(
            "Factures",
            self.tenant_id,
            facture_id,
            {
                "sumup_checkout_id": checkout.id,
                "sumup_checkout_url": checkout.checkout_url
            }
        )

        return {
            "checkout_id": checkout.id,
            "checkout_url": checkout.checkout_url,
            "amount": checkout.amount,
            "currency": checkout.currency,
            "valid_until": checkout.valid_until.isoformat() if checkout.valid_until else None
        }

    async def handle_webhook(self, payload: Dict) -> Dict:
        """
        Gérer un webhook SumUp.

        Args:
            payload: Corps de la requête webhook

        Returns:
            Dict avec le résultat du traitement
        """
        from moteur.db import Database

        event_type = payload.get("event_type")

        if event_type == "CHECKOUT_COMPLETED":
            checkout_id = payload.get("checkout_id")

            # Rechercher la facture liée
            factures = Database.query(
                "Factures",
                self.tenant_id,
                filters={"sumup_checkout_id": checkout_id}
            )

            if factures:
                facture = factures[0]
                Database.update(
                    "Factures",
                    self.tenant_id,
                    UUID(str(facture["id"])),
                    {
                        "status": "PAID",
                        "paid_amount": payload.get("amount", facture.get("total")),
                        "payment_method": "CREDIT_CARD"
                    }
                )

                logger.info(f"SumUp checkout completed for facture {facture.get('number')}")
                return {"status": "success", "facture_id": str(facture["id"])}

        return {"status": "ignored", "event_type": event_type}

    async def sync_payouts(
        self,
        since: Optional[date] = None
    ) -> int:
        """
        Synchroniser les versements SumUp (virements vers compte bancaire).

        Returns:
            Nombre de nouveaux versements
        """
        from moteur.db import Database
        import hashlib

        client = await self._get_client()

        # Récupérer le compte SumUp
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SUMUP", "statut": "ACTIF"}
        )

        if not comptes:
            return 0

        compte = comptes[0]
        compte_id = str(compte["id"])

        # Récupérer le compte bancaire cible (où arrive le versement)
        # C'est généralement un compte différent de "SUMUP"
        # On crée un mouvement sur le compte bancaire principal

        payouts, _ = await client.list_payouts(from_date=since)
        total_new = 0

        for payout in payouts:
            if payout.status != PayoutStatus.SUCCESSFUL:
                continue

            # Vérifier si déjà importé
            existing = Database.query(
                "Mouvements_Bancaires",
                self.tenant_id,
                filters={"provider_id": f"PAYOUT-{payout.id}"}
            )

            if existing:
                continue

            # Ce versement apparaîtra comme un crédit sur le compte bancaire
            # où SumUp envoie les fonds
            hash_elements = f"{compte_id}|{payout.payout_date}|{payout.amount}|CREDIT|{payout.id}"
            hash_doublon = hashlib.md5(hash_elements.encode()).hexdigest()

            Database.insert(
                "Mouvements_Bancaires",
                self.tenant_id,
                {
                    "compte_id": compte_id,
                    "date_operation": payout.payout_date.isoformat(),
                    "date_valeur": payout.payout_date.isoformat(),
                    "libelle": f"Versement SumUp ({payout.transaction_count} transactions)",
                    "libelle_complementaire": payout.reference or "",
                    "sens": "CREDIT",
                    "montant": payout.amount,
                    "devise": payout.currency,
                    "type_operation": "VIREMENT_SEPA",
                    "tiers_libelle": "SumUp Payments Limited",
                    "source": "SUMUP",
                    "provider_id": f"PAYOUT-{payout.id}",
                    "provider_data": {
                        "payout_id": payout.id,
                        "transaction_count": payout.transaction_count
                    },
                    "statut": "A_TRAITER",
                    "hash_doublon": hash_doublon
                }
            )

            total_new += 1

        logger.info(f"SumUp payouts sync completed: {total_new} new payouts")
        return total_new
