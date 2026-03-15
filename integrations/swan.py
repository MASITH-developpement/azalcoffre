# =============================================================================
# AZALPLUS - Intégration Swan (Banking as a Service)
# =============================================================================
"""
Swan BaaS - Compte bancaire intégré

Fonctionnalités:
- Ouverture de compte avec KYC intégré
- IBAN français
- Virements SEPA
- Cartes bancaires (virtuelles/physiques)
- Tap to Pay (encaissement NFC)

Tarification:
- Abonnement: 9-12€/mois
- Tap to Pay: 1.2-1.5%
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx

logger = logging.getLogger(__name__)


class SwanEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class AccountStatus(str, Enum):
    OPENING = "Opening"
    ENABLED = "Enabled"
    SUSPENDED = "Suspended"
    CLOSING = "Closing"
    CLOSED = "Closed"


class TransactionStatus(str, Enum):
    PENDING = "Pending"
    BOOKED = "Booked"
    REJECTED = "Rejected"
    CANCELED = "Canceled"


class TransactionType(str, Enum):
    SEPA_CREDIT_TRANSFER_IN = "SepaCreditTransferIn"
    SEPA_CREDIT_TRANSFER_OUT = "SepaCreditTransferOut"
    SEPA_DIRECT_DEBIT_IN = "SepaDirectDebitIn"
    SEPA_DIRECT_DEBIT_OUT = "SepaDirectDebitOut"
    CARD_TRANSACTION = "CardTransaction"
    INTERNAL_TRANSFER = "InternalTransfer"
    FEE = "Fee"


class CardStatus(str, Enum):
    PROCESSING = "Processing"
    ENABLED = "Enabled"
    SUSPENDED = "Suspended"
    CANCELED = "Canceled"


@dataclass
class SwanConfig:
    """Configuration Swan par tenant."""
    client_id: str
    client_secret: str
    project_id: str
    environment: SwanEnvironment = SwanEnvironment.SANDBOX
    webhook_secret: Optional[str] = None

    @property
    def base_url(self) -> str:
        if self.environment == SwanEnvironment.PRODUCTION:
            return "https://api.swan.io"
        return "https://api.sandbox.swan.io"

    @property
    def oauth_url(self) -> str:
        if self.environment == SwanEnvironment.PRODUCTION:
            return "https://oauth.swan.io"
        return "https://oauth.sandbox.swan.io"


@dataclass
class AccountHolder:
    """Titulaire de compte (personne ou entreprise)."""
    type: str  # "Individual" ou "Company"
    # Pour Individual
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    # Pour Company
    company_name: Optional[str] = None
    siren: Optional[str] = None
    # Commun
    email: str = ""
    phone: str = ""
    address_line1: str = ""
    city: str = ""
    postal_code: str = ""
    country: str = "FRA"


@dataclass
class Account:
    """Compte bancaire Swan."""
    id: str
    iban: str
    bic: str
    status: AccountStatus
    balance_available: float
    balance_pending: float
    balance_reserved: float
    currency: str = "EUR"
    name: str = ""
    created_at: Optional[datetime] = None


@dataclass
class Transaction:
    """Transaction bancaire."""
    id: str
    type: TransactionType
    status: TransactionStatus
    amount: float
    currency: str
    direction: str  # "Credit" ou "Debit"
    counterparty_name: str
    counterparty_iban: Optional[str]
    reference: str
    label: str
    booked_at: Optional[datetime]
    value_date: Optional[date]


@dataclass
class Card:
    """Carte bancaire."""
    id: str
    status: CardStatus
    type: str  # "Virtual" ou "Physical"
    last_four_digits: str
    expiry_date: str
    spending_limits: dict = field(default_factory=dict)
    holder_name: str = ""


class SwanClient:
    """
    Client API Swan pour Banking as a Service.

    Usage:
        config = SwanConfig(
            client_id="xxx",
            client_secret="xxx",
            project_id="xxx"
        )
        client = SwanClient(config)

        # Créer un compte
        onboarding = await client.create_onboarding(AccountHolder(...))

        # Récupérer le solde
        account = await client.get_account(account_id)
        print(f"Solde: {account.balance_available} EUR")

        # Effectuer un virement
        transfer = await client.create_transfer(
            account_id="xxx",
            amount=100.00,
            beneficiary_iban="FR76...",
            beneficiary_name="Fournisseur SAS",
            reference="FAC-001"
        )
    """

    def __init__(self, config: SwanConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0,
                headers={"Content-Type": "application/json"}
            )
        return self._http_client

    async def _get_access_token(self) -> str:
        """Obtenir un access token OAuth2."""
        if self._access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at:
                return self._access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.config.oauth_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "scope": "openid offline"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            data = response.json()
            self._access_token = data["access_token"]
            from datetime import timedelta
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)

            return self._access_token

    async def _graphql(self, query: str, variables: dict = None) -> dict:
        """Exécuter une requête GraphQL."""
        token = await self._get_access_token()
        client = await self._get_client()

        response = await client.post(
            "/graphql",
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {token}"}
        )

        if response.status_code >= 400:
            logger.error(f"Swan GraphQL error: {response.status_code} - {response.text}")
            raise SwanError(f"Erreur API Swan: {response.status_code}", response.json())

        data = response.json()

        if "errors" in data:
            logger.error(f"Swan GraphQL errors: {data['errors']}")
            raise SwanError("Erreur GraphQL", {"errors": data["errors"]})

        return data.get("data", {})

    # -------------------------------------------------------------------------
    # Onboarding & KYC
    # -------------------------------------------------------------------------

    async def create_onboarding(self, holder: AccountHolder, redirect_url: str) -> dict:
        """
        Créer un onboarding pour ouverture de compte.

        Args:
            holder: Informations du titulaire
            redirect_url: URL de redirection après KYC

        Returns:
            dict avec onboarding_id et onboarding_url
        """
        if holder.type == "Individual":
            mutation = """
            mutation CreateIndividualOnboarding($input: OnboardIndividualAccountHolderInput!) {
                onboardIndividualAccountHolder(input: $input) {
                    ... on OnboardIndividualAccountHolderSuccessPayload {
                        onboarding {
                            id
                            onboardingUrl
                            statusInfo {
                                status
                            }
                        }
                    }
                    ... on ValidationRejection {
                        message
                    }
                }
            }
            """
            variables = {
                "input": {
                    "accountName": f"{holder.first_name} {holder.last_name}",
                    "email": holder.email,
                    "redirectUrl": redirect_url,
                    "language": "fr",
                    "accountCountry": "FRA"
                }
            }
        else:
            mutation = """
            mutation CreateCompanyOnboarding($input: OnboardCompanyAccountHolderInput!) {
                onboardCompanyAccountHolder(input: $input) {
                    ... on OnboardCompanyAccountHolderSuccessPayload {
                        onboarding {
                            id
                            onboardingUrl
                            statusInfo {
                                status
                            }
                        }
                    }
                    ... on ValidationRejection {
                        message
                    }
                }
            }
            """
            variables = {
                "input": {
                    "accountName": holder.company_name,
                    "email": holder.email,
                    "redirectUrl": redirect_url,
                    "language": "fr",
                    "accountCountry": "FRA",
                    "registrationNumber": holder.siren
                }
            }

        result = await self._graphql(mutation, variables)

        key = "onboardIndividualAccountHolder" if holder.type == "Individual" else "onboardCompanyAccountHolder"
        payload = result.get(key, {})

        if "onboarding" in payload:
            onboarding = payload["onboarding"]
            return {
                "onboarding_id": onboarding["id"],
                "onboarding_url": onboarding["onboardingUrl"],
                "status": onboarding["statusInfo"]["status"]
            }
        else:
            raise SwanError("Échec création onboarding", payload)

    async def get_onboarding_status(self, onboarding_id: str) -> dict:
        """Récupérer le statut d'un onboarding."""
        query = """
        query GetOnboarding($id: ID!) {
            onboarding(id: $id) {
                id
                statusInfo {
                    status
                }
                account {
                    id
                    IBAN
                    BIC
                }
            }
        }
        """
        result = await self._graphql(query, {"id": onboarding_id})
        return result.get("onboarding", {})

    # -------------------------------------------------------------------------
    # Comptes
    # -------------------------------------------------------------------------

    async def get_account(self, account_id: str) -> Account:
        """Récupérer les détails d'un compte."""
        query = """
        query GetAccount($id: ID!) {
            account(id: $id) {
                id
                name
                IBAN
                BIC
                statusInfo {
                    status
                }
                balances {
                    available {
                        value
                        currency
                    }
                    pending {
                        value
                        currency
                    }
                    reserved {
                        value
                        currency
                    }
                }
                createdAt
            }
        }
        """
        result = await self._graphql(query, {"id": account_id})
        account_data = result.get("account", {})

        if not account_data:
            raise SwanError("Compte non trouvé", {"account_id": account_id})

        balances = account_data.get("balances", {})

        return Account(
            id=account_data["id"],
            iban=account_data.get("IBAN", ""),
            bic=account_data.get("BIC", ""),
            status=AccountStatus(account_data["statusInfo"]["status"]),
            balance_available=float(balances.get("available", {}).get("value", 0)),
            balance_pending=float(balances.get("pending", {}).get("value", 0)),
            balance_reserved=float(balances.get("reserved", {}).get("value", 0)),
            currency=balances.get("available", {}).get("currency", "EUR"),
            name=account_data.get("name", ""),
            created_at=datetime.fromisoformat(account_data["createdAt"].replace("Z", "+00:00"))
            if account_data.get("createdAt") else None
        )

    async def get_account_by_iban(self, iban: str) -> Optional[Account]:
        """Récupérer un compte par son IBAN."""
        query = """
        query GetAccountByIBAN($iban: IBAN!) {
            accountByIban(iban: $iban) {
                id
                name
                IBAN
                BIC
                statusInfo {
                    status
                }
                balances {
                    available {
                        value
                        currency
                    }
                }
            }
        }
        """
        result = await self._graphql(query, {"iban": iban})
        account_data = result.get("accountByIban")

        if not account_data:
            return None

        return Account(
            id=account_data["id"],
            iban=account_data["IBAN"],
            bic=account_data["BIC"],
            status=AccountStatus(account_data["statusInfo"]["status"]),
            balance_available=float(
                account_data.get("balances", {}).get("available", {}).get("value", 0)
            ),
            balance_pending=0,
            balance_reserved=0,
            name=account_data.get("name", "")
        )

    # -------------------------------------------------------------------------
    # Transactions
    # -------------------------------------------------------------------------

    async def get_transactions(
        self,
        account_id: str,
        first: int = 50,
        after: Optional[str] = None,
        status: Optional[TransactionStatus] = None
    ) -> tuple[list[Transaction], Optional[str]]:
        """
        Récupérer les transactions d'un compte.

        Returns:
            Tuple (transactions, next_cursor)
        """
        query = """
        query GetTransactions($accountId: ID!, $first: Int!, $after: String, $filters: TransactionFiltersInput) {
            account(id: $accountId) {
                transactions(first: $first, after: $after, filters: $filters) {
                    edges {
                        node {
                            id
                            type
                            statusInfo {
                                status
                            }
                            amount {
                                value
                                currency
                            }
                            side
                            counterparty
                            reference
                            label
                            bookedAt
                            valueDate
                        }
                        cursor
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        }
        """

        filters = {}
        if status:
            filters["status"] = status.value

        result = await self._graphql(query, {
            "accountId": account_id,
            "first": first,
            "after": after,
            "filters": filters if filters else None
        })

        transactions_data = result.get("account", {}).get("transactions", {})
        edges = transactions_data.get("edges", [])
        page_info = transactions_data.get("pageInfo", {})

        transactions = []
        for edge in edges:
            node = edge["node"]
            transactions.append(Transaction(
                id=node["id"],
                type=TransactionType(node["type"]),
                status=TransactionStatus(node["statusInfo"]["status"]),
                amount=float(node["amount"]["value"]),
                currency=node["amount"]["currency"],
                direction=node["side"],
                counterparty_name=node.get("counterparty", ""),
                counterparty_iban=None,
                reference=node.get("reference", ""),
                label=node.get("label", ""),
                booked_at=datetime.fromisoformat(node["bookedAt"].replace("Z", "+00:00"))
                if node.get("bookedAt") else None,
                value_date=date.fromisoformat(node["valueDate"])
                if node.get("valueDate") else None
            ))

        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None

        return transactions, next_cursor

    # -------------------------------------------------------------------------
    # Virements
    # -------------------------------------------------------------------------

    async def create_transfer(
        self,
        account_id: str,
        amount: float,
        beneficiary_iban: str,
        beneficiary_name: str,
        reference: str,
        label: str = "",
        scheduled_date: Optional[date] = None
    ) -> dict:
        """
        Créer un virement SEPA.

        Args:
            account_id: ID du compte débiteur
            amount: Montant en EUR
            beneficiary_iban: IBAN du bénéficiaire
            beneficiary_name: Nom du bénéficiaire
            reference: Référence du virement
            label: Libellé
            scheduled_date: Date programmée (optionnel)

        Returns:
            dict avec transfer_id et status
        """
        mutation = """
        mutation InitiateCreditTransfer($input: InitiateCreditTransfersInput!) {
            initiateCreditTransfers(input: $input) {
                ... on InitiateCreditTransfersSuccessPayload {
                    payment {
                        id
                        statusInfo {
                            status
                        }
                    }
                }
                ... on ValidationRejection {
                    message
                    fields {
                        path
                        message
                    }
                }
                ... on InsufficientFundsRejection {
                    message
                }
            }
        }
        """

        transfer_input = {
            "amount": {"value": str(amount), "currency": "EUR"},
            "targetIban": beneficiary_iban,
            "targetName": beneficiary_name,
            "reference": reference[:140],  # Max 140 chars
            "label": label[:140] if label else reference[:140]
        }

        if scheduled_date:
            transfer_input["requestedExecutionAt"] = scheduled_date.isoformat()

        variables = {
            "input": {
                "accountId": account_id,
                "creditTransfers": [transfer_input],
                "consentRedirectUrl": ""  # Pour SCA si nécessaire
            }
        }

        result = await self._graphql(mutation, variables)
        payload = result.get("initiateCreditTransfers", {})

        if "payment" in payload:
            return {
                "transfer_id": payload["payment"]["id"],
                "status": payload["payment"]["statusInfo"]["status"]
            }
        elif "message" in payload:
            raise SwanError(payload["message"], payload)
        else:
            raise SwanError("Erreur création virement", payload)

    # -------------------------------------------------------------------------
    # Cartes
    # -------------------------------------------------------------------------

    async def create_virtual_card(
        self,
        account_membership_id: str,
        spending_limit_amount: float = 1000,
        spending_limit_period: str = "Monthly"
    ) -> Card:
        """
        Créer une carte virtuelle.

        Args:
            account_membership_id: ID du membership
            spending_limit_amount: Plafond de dépense
            spending_limit_period: Période (Daily, Weekly, Monthly, Always)

        Returns:
            Card
        """
        mutation = """
        mutation AddVirtualCard($input: AddVirtualCardInput!) {
            addVirtualCard(input: $input) {
                ... on AddVirtualCardSuccessPayload {
                    card {
                        id
                        statusInfo {
                            status
                        }
                        type
                        lastFourDigits
                        expiryDate
                    }
                }
                ... on ValidationRejection {
                    message
                }
            }
        }
        """

        variables = {
            "input": {
                "accountMembershipId": account_membership_id,
                "spendingLimit": {
                    "amount": {"value": str(spending_limit_amount), "currency": "EUR"},
                    "period": spending_limit_period
                },
                "name": "Carte virtuelle AZALPLUS"
            }
        }

        result = await self._graphql(mutation, variables)
        payload = result.get("addVirtualCard", {})

        if "card" in payload:
            card_data = payload["card"]
            return Card(
                id=card_data["id"],
                status=CardStatus(card_data["statusInfo"]["status"]),
                type="Virtual",
                last_four_digits=card_data["lastFourDigits"],
                expiry_date=card_data["expiryDate"],
                spending_limits={
                    "amount": spending_limit_amount,
                    "period": spending_limit_period
                }
            )
        else:
            raise SwanError("Erreur création carte", payload)

    async def get_cards(self, account_id: str) -> list[Card]:
        """Récupérer les cartes d'un compte."""
        query = """
        query GetCards($accountId: ID!) {
            account(id: $accountId) {
                memberships {
                    edges {
                        node {
                            cards {
                                edges {
                                    node {
                                        id
                                        statusInfo {
                                            status
                                        }
                                        type
                                        lastFourDigits
                                        expiryDate
                                        name
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        result = await self._graphql(query, {"accountId": account_id})

        cards = []
        memberships = result.get("account", {}).get("memberships", {}).get("edges", [])

        for membership in memberships:
            card_edges = membership.get("node", {}).get("cards", {}).get("edges", [])
            for edge in card_edges:
                card_data = edge["node"]
                cards.append(Card(
                    id=card_data["id"],
                    status=CardStatus(card_data["statusInfo"]["status"]),
                    type=card_data["type"],
                    last_four_digits=card_data["lastFourDigits"],
                    expiry_date=card_data["expiryDate"],
                    holder_name=card_data.get("name", "")
                ))

        return cards

    async def suspend_card(self, card_id: str) -> bool:
        """Suspendre une carte."""
        mutation = """
        mutation SuspendCard($input: SuspendPhysicalCardInput!) {
            suspendPhysicalCard(input: $input) {
                ... on SuspendPhysicalCardSuccessPayload {
                    card {
                        id
                        statusInfo {
                            status
                        }
                    }
                }
            }
        }
        """

        result = await self._graphql(mutation, {"input": {"cardId": card_id}})
        return "card" in result.get("suspendPhysicalCard", {})

    # -------------------------------------------------------------------------
    # Webhooks
    # -------------------------------------------------------------------------

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Vérifier la signature d'un webhook Swan."""
        import hmac
        import hashlib

        if not self.config.webhook_secret:
            logger.warning("Webhook secret non configuré")
            return False

        expected = hmac.new(
            self.config.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class SwanError(Exception):
    """Erreur API Swan."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Service métier pour intégration AZALPLUS
# =============================================================================

class SwanBankingService:
    """
    Service bancaire Swan intégré à AZALPLUS.

    Gère:
    - Ouverture de compte pour les tenants
    - Synchronisation des transactions
    - Rapprochement automatique avec factures
    - Virements fournisseurs
    """

    ABONNEMENT_MENSUEL = 9.90  # EUR

    def __init__(self, db, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self._client: Optional[SwanClient] = None

    async def _get_client(self) -> SwanClient:
        """Récupérer le client Swan configuré."""
        if self._client:
            return self._client

        import os
        config = SwanConfig(
            client_id=os.getenv("SWAN_CLIENT_ID", ""),
            client_secret=os.getenv("SWAN_CLIENT_SECRET", ""),
            project_id=os.getenv("SWAN_PROJECT_ID", ""),
            environment=SwanEnvironment.SANDBOX,
            webhook_secret=os.getenv("SWAN_WEBHOOK_SECRET", "")
        )

        self._client = SwanClient(config)
        return self._client

    async def start_account_opening(self, holder: AccountHolder, redirect_url: str) -> dict:
        """
        Démarrer l'ouverture de compte pour un tenant.

        Returns:
            dict avec URL d'onboarding KYC
        """
        client = await self._get_client()
        result = await client.create_onboarding(holder, redirect_url)

        # Sauvegarder l'onboarding en base
        await self._save_onboarding(result["onboarding_id"], result["status"])

        return result

    async def get_balance(self) -> dict:
        """Récupérer le solde du compte du tenant."""
        account_id = await self._get_tenant_account_id()
        if not account_id:
            return {"status": "no_account"}

        client = await self._get_client()
        account = await client.get_account(account_id)

        return {
            "iban": account.iban,
            "balance_available": account.balance_available,
            "balance_pending": account.balance_pending,
            "currency": account.currency,
            "status": account.status.value
        }

    async def sync_transactions(self, since_cursor: Optional[str] = None) -> int:
        """
        Synchroniser les transactions depuis Swan.

        Returns:
            Nombre de nouvelles transactions
        """
        account_id = await self._get_tenant_account_id()
        if not account_id:
            return 0

        client = await self._get_client()
        cursor = since_cursor
        total_new = 0

        while True:
            transactions, next_cursor = await client.get_transactions(
                account_id, first=100, after=cursor
            )

            for tx in transactions:
                is_new = await self._save_transaction(tx)
                if is_new:
                    total_new += 1
                    # Tenter rapprochement automatique
                    await self._try_auto_reconcile(tx)

            if not next_cursor:
                break
            cursor = next_cursor

        return total_new

    async def pay_supplier(
        self,
        facture_achat_id: UUID,
        scheduled_date: Optional[date] = None
    ) -> dict:
        """
        Payer une facture fournisseur par virement.

        Args:
            facture_achat_id: ID de la facture d'achat
            scheduled_date: Date programmée (optionnel)

        Returns:
            dict avec statut du virement
        """
        account_id = await self._get_tenant_account_id()
        if not account_id:
            raise ValueError("Pas de compte bancaire configuré")

        # Récupérer la facture et le fournisseur
        facture = await self._get_facture_achat(facture_achat_id)
        fournisseur = await self._get_fournisseur(facture["fournisseur_id"])

        if not fournisseur.get("iban"):
            raise ValueError("IBAN fournisseur non renseigné")

        client = await self._get_client()
        result = await client.create_transfer(
            account_id=account_id,
            amount=float(facture["montant_ttc"]),
            beneficiary_iban=fournisseur["iban"],
            beneficiary_name=fournisseur["raison_sociale"],
            reference=facture["numero"],
            label=f"Paiement facture {facture['numero']}",
            scheduled_date=scheduled_date
        )

        # Enregistrer le paiement
        await self._record_supplier_payment(facture_achat_id, result)

        return result

    # =========================================================================
    # Méthodes DB (implémentées)
    # =========================================================================

    async def _get_tenant_account_id(self) -> Optional[str]:
        """Récupère l'ID du compte Swan du tenant."""
        from moteur.db import Database

        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SWAN", "statut": "ACTIF"}
        )

        if comptes:
            return comptes[0].get("provider_account_id")
        return None

    async def _save_onboarding(self, onboarding_id: str, status: str):
        """Sauvegarde les informations d'onboarding."""
        from moteur.db import Database

        # Créer ou mettre à jour le compte bancaire
        existing = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SWAN"}
        )

        if existing:
            Database.update(
                "Comptes_Bancaires",
                self.tenant_id,
                UUID(str(existing[0]["id"])),
                {
                    "provider_account_id": onboarding_id,
                    "provider_status": status
                }
            )
        else:
            Database.insert(
                "Comptes_Bancaires",
                self.tenant_id,
                {
                    "code": "SWAN-001",
                    "libelle": "Compte Swan",
                    "provider": "SWAN",
                    "provider_account_id": onboarding_id,
                    "provider_status": status,
                    "statut": "ACTIF" if status == "Finalized" else "INACTIF",
                    "banque": "Swan",
                    "devise": "EUR",
                    "iban": "",  # Sera rempli après finalisation
                    "rapprochement_auto": True,
                    "seuil_confiance": 95
                }
            )

    async def _save_transaction(self, tx: Transaction) -> bool:
        """
        Sauvegarde une transaction Swan en mouvement bancaire.

        Returns:
            True si nouvelle transaction, False si déjà existante
        """
        from moteur.db import Database
        import hashlib

        # Vérifier si déjà importée
        existing = Database.query(
            "Mouvements_Bancaires",
            self.tenant_id,
            filters={"provider_id": tx.id}
        )

        if existing:
            return False

        # Récupérer le compte
        compte = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SWAN", "statut": "ACTIF"}
        )

        if not compte:
            logger.warning("swan_no_account_for_transaction", tx_id=tx.id)
            return False

        compte_id = str(compte[0]["id"])

        # Mapper les données
        sens = "CREDIT" if tx.direction == "Credit" else "DEBIT"
        montant = abs(tx.amount)

        # Type d'opération
        type_map = {
            TransactionType.SEPA_CREDIT_TRANSFER_IN: "VIREMENT_SEPA",
            TransactionType.SEPA_CREDIT_TRANSFER_OUT: "VIREMENT_SEPA",
            TransactionType.SEPA_DIRECT_DEBIT_IN: "PRELEVEMENT",
            TransactionType.SEPA_DIRECT_DEBIT_OUT: "PRELEVEMENT",
            TransactionType.CARD_TRANSACTION: "CARTE",
            TransactionType.FEE: "FRAIS",
        }
        type_op = type_map.get(tx.type, "AUTRE")

        # Hash pour détection doublons
        hash_elements = f"{compte_id}|{tx.value_date}|{montant}|{sens}|{tx.label[:20]}"
        hash_doublon = hashlib.md5(hash_elements.encode()).hexdigest()

        # Créer le mouvement
        mouvement = Database.insert(
            "Mouvements_Bancaires",
            self.tenant_id,
            {
                "compte_id": compte_id,
                "date_operation": tx.value_date.isoformat() if tx.value_date else datetime.utcnow().date().isoformat(),
                "date_valeur": tx.value_date.isoformat() if tx.value_date else None,
                "libelle": tx.label or "",
                "libelle_complementaire": tx.reference or "",
                "sens": sens,
                "montant": montant,
                "devise": tx.currency,
                "type_operation": type_op,
                "tiers_libelle": tx.counterparty_name or "",
                "tiers_iban": tx.counterparty_iban or "",
                "tiers_reference": tx.reference or "",
                "source": "SWAN",
                "provider_id": tx.id,
                "provider_data": {
                    "swan_type": tx.type.value,
                    "swan_status": tx.status.value,
                    "booked_at": tx.booked_at.isoformat() if tx.booked_at else None
                },
                "statut": "A_TRAITER",
                "hash_doublon": hash_doublon
            }
        )

        logger.info(
            "swan_transaction_saved",
            tx_id=tx.id,
            mouvement_id=str(mouvement.get("id")),
            montant=montant,
            sens=sens
        )

        return True

    async def _try_auto_reconcile(self, tx: Transaction):
        """
        Tente le rapprochement automatique d'une transaction.

        Utilise le RapprochementService pour appliquer les 5 niveaux.
        """
        from moteur.rapprochement_service import RapprochementService
        from moteur.db import Database

        # Récupérer le mouvement créé
        mouvements = Database.query(
            "Mouvements_Bancaires",
            self.tenant_id,
            filters={"provider_id": tx.id}
        )

        if not mouvements:
            return

        mouvement_id = UUID(str(mouvements[0]["id"]))

        # Appeler le service de rapprochement
        service = RapprochementService(self.tenant_id)
        resultat = await service.rapprocher_mouvement(mouvement_id)

        if resultat.succes:
            logger.info(
                "swan_auto_reconcile_success",
                mouvement_id=str(mouvement_id),
                methode=resultat.methode.value if resultat.methode else None,
                confiance=resultat.confiance
            )
        else:
            logger.debug(
                "swan_auto_reconcile_no_match",
                mouvement_id=str(mouvement_id),
                message=resultat.message
            )

    async def _get_facture_achat(self, facture_id: UUID) -> dict:
        """Récupère une facture d'achat."""
        from moteur.db import Database

        facture = Database.get_by_id(
            "Factures_Achats",
            self.tenant_id,
            facture_id
        )

        if not facture:
            raise ValueError(f"Facture d'achat {facture_id} non trouvée")

        return facture

    async def _get_fournisseur(self, fournisseur_id: UUID) -> dict:
        """Récupère un fournisseur."""
        from moteur.db import Database

        fournisseur = Database.get_by_id(
            "Fournisseurs",
            self.tenant_id,
            fournisseur_id
        )

        if not fournisseur:
            raise ValueError(f"Fournisseur {fournisseur_id} non trouvé")

        return fournisseur

    async def _record_supplier_payment(self, facture_id: UUID, result: dict):
        """Enregistre un paiement fournisseur."""
        from moteur.db import Database

        # Créer un paiement
        Database.insert(
            "Paiements",
            self.tenant_id,
            {
                "facture_achat_id": str(facture_id),
                "montant": result.get("amount", 0),
                "date_paiement": datetime.utcnow().date().isoformat(),
                "mode_paiement": "VIREMENT_SEPA",
                "reference": result.get("transfer_id", ""),
                "statut": "VALIDE" if result.get("status") == "Booked" else "EN_ATTENTE",
                "provider": "SWAN",
                "provider_id": result.get("transfer_id", "")
            }
        )

        # Mettre à jour le statut de la facture si paiement confirmé
        if result.get("status") == "Booked":
            Database.update(
                "Factures_Achats",
                self.tenant_id,
                facture_id,
                {"statut": "PAYEE"}
            )
