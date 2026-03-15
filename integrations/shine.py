# =============================================================================
# AZALPLUS - Intégration Shine
# =============================================================================
"""
Shine - Compte pro pour indépendants et TPE.

Fonctionnalités:
- Compte courant professionnel avec IBAN français
- Cartes bancaires Mastercard
- Virements SEPA
- Facturation intégrée
- Comptabilité simplifiée
- Multi-comptes

Tarification:
- Basic: 7.90€/mois
- Plus: 14.90€/mois
- Pro: 29€/mois

Documentation: https://developers.shine.fr/
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
class ShineEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class TransactionType(str, Enum):
    CARD = "card"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    DIRECT_DEBIT = "direct_debit"
    FEE = "fee"
    INTEREST = "interest"
    CHECK = "check"
    OTHER = "other"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class TransferStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class ShineConfig:
    """Configuration Shine par tenant."""
    client_id: str
    client_secret: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    environment: ShineEnvironment = ShineEnvironment.SANDBOX

    @property
    def base_url(self) -> str:
        if self.environment == ShineEnvironment.PRODUCTION:
            return "https://api.shine.fr/v1"
        return "https://api.sandbox.shine.fr/v1"

    @property
    def oauth_url(self) -> str:
        if self.environment == ShineEnvironment.PRODUCTION:
            return "https://auth.shine.fr"
        return "https://auth.sandbox.shine.fr"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class ShineAccount:
    """Compte Shine."""
    id: str
    iban: str
    bic: str
    balance: float
    available_balance: float
    currency: str = "EUR"
    name: str = ""
    status: str = "active"


@dataclass
class ShineTransaction:
    """Transaction Shine."""
    id: str
    amount: float
    currency: str
    type: TransactionType
    status: TransactionStatus
    label: str
    executed_at: Optional[datetime] = None
    value_date: Optional[date] = None
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    reference: Optional[str] = None
    category: Optional[str] = None
    receipt_url: Optional[str] = None


@dataclass
class ShineTransfer:
    """Virement Shine."""
    id: str
    amount: float
    currency: str
    status: TransferStatus
    beneficiary_name: str
    beneficiary_iban: str
    reference: str
    label: Optional[str] = None
    scheduled_date: Optional[date] = None
    executed_at: Optional[datetime] = None


@dataclass
class ShineBeneficiary:
    """Bénéficiaire Shine."""
    id: str
    name: str
    iban: str
    bic: Optional[str] = None


# =============================================================================
# Client API Shine
# =============================================================================
class ShineClient:
    """
    Client API Shine.

    Usage:
        config = ShineConfig(
            client_id="xxx",
            client_secret="xxx",
            access_token="xxx"
        )
        client = ShineClient(config)

        # Récupérer les transactions
        transactions = await client.list_transactions()
    """

    def __init__(self, config: ShineConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            headers = {"Content-Type": "application/json"}
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
            logger.error(f"Shine API error: {response.status_code} - {error_msg}")
            raise ShineError(error_msg, error_data)

        return response.json()

    async def refresh_access_token(self) -> str:
        """Rafraîchir le token d'accès."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.config.oauth_url}/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "refresh_token": self.config.refresh_token
                }
            )

            if response.status_code != 200:
                raise ShineError("Failed to refresh token")

            data = response.json()
            self.config.access_token = data["access_token"]
            if "refresh_token" in data:
                self.config.refresh_token = data["refresh_token"]

            # Recréer le client HTTP avec le nouveau token
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None

            return self.config.access_token

    # =========================================================================
    # Accounts
    # =========================================================================
    async def get_accounts(self) -> List[ShineAccount]:
        """Récupérer les comptes."""
        result = await self._request("GET", "/accounts")

        accounts = []
        for acc in result.get("accounts", [result] if "id" in result else []):
            accounts.append(ShineAccount(
                id=acc["id"],
                iban=acc["iban"],
                bic=acc.get("bic", ""),
                balance=acc.get("balance", 0),
                available_balance=acc.get("available_balance", 0),
                currency=acc.get("currency", "EUR"),
                name=acc.get("name", ""),
                status=acc.get("status", "active")
            ))

        return accounts

    async def get_account(self, account_id: str) -> Optional[ShineAccount]:
        """Récupérer un compte spécifique."""
        try:
            result = await self._request("GET", f"/accounts/{account_id}")
            return ShineAccount(
                id=result["id"],
                iban=result["iban"],
                bic=result.get("bic", ""),
                balance=result.get("balance", 0),
                available_balance=result.get("available_balance", 0),
                currency=result.get("currency", "EUR"),
                name=result.get("name", ""),
                status=result.get("status", "active")
            )
        except ShineError:
            return None

    # =========================================================================
    # Transactions
    # =========================================================================
    async def list_transactions(
        self,
        account_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        page: int = 1,
        per_page: int = 100
    ) -> tuple[List[ShineTransaction], Dict]:
        """
        Lister les transactions.

        Returns:
            Tuple (transactions, pagination_meta)
        """
        params = {
            "page": page,
            "per_page": per_page
        }

        if from_date:
            params["from"] = from_date.isoformat()
        if to_date:
            params["to"] = to_date.isoformat()

        endpoint = f"/accounts/{account_id}/transactions" if account_id else "/transactions"
        result = await self._request("GET", endpoint, params=params)

        transactions = []
        for tx in result.get("transactions", []):
            # Déterminer le type
            tx_type = TransactionType.OTHER
            raw_type = tx.get("type", "").lower()
            if "card" in raw_type:
                tx_type = TransactionType.CARD
            elif "transfer" in raw_type and tx.get("amount", 0) > 0:
                tx_type = TransactionType.TRANSFER_IN
            elif "transfer" in raw_type:
                tx_type = TransactionType.TRANSFER_OUT
            elif "debit" in raw_type:
                tx_type = TransactionType.DIRECT_DEBIT
            elif "fee" in raw_type:
                tx_type = TransactionType.FEE

            transactions.append(ShineTransaction(
                id=tx["id"],
                amount=tx["amount"],
                currency=tx.get("currency", "EUR"),
                type=tx_type,
                status=TransactionStatus(tx.get("status", "completed")),
                label=tx.get("label", ""),
                executed_at=datetime.fromisoformat(tx["executed_at"].replace("Z", "+00:00")) if tx.get("executed_at") else None,
                value_date=date.fromisoformat(tx["value_date"]) if tx.get("value_date") else None,
                counterparty_name=tx.get("counterparty_name"),
                counterparty_iban=tx.get("counterparty_iban"),
                reference=tx.get("reference"),
                category=tx.get("category"),
                receipt_url=tx.get("receipt_url")
            ))

        meta = result.get("meta", {"page": page, "per_page": per_page})

        return transactions, meta

    # =========================================================================
    # Transfers
    # =========================================================================
    async def create_transfer(
        self,
        account_id: str,
        beneficiary_iban: str,
        beneficiary_name: str,
        amount: float,
        reference: str,
        label: Optional[str] = None,
        scheduled_date: Optional[date] = None
    ) -> ShineTransfer:
        """Créer un virement."""
        data = {
            "beneficiary_iban": beneficiary_iban,
            "beneficiary_name": beneficiary_name,
            "amount": amount,
            "currency": "EUR",
            "reference": reference
        }

        if label:
            data["label"] = label
        if scheduled_date:
            data["scheduled_date"] = scheduled_date.isoformat()

        result = await self._request(
            "POST",
            f"/accounts/{account_id}/transfers",
            json_data=data
        )

        return ShineTransfer(
            id=result["id"],
            amount=result["amount"],
            currency=result.get("currency", "EUR"),
            status=TransferStatus(result.get("status", "pending")),
            beneficiary_name=result["beneficiary_name"],
            beneficiary_iban=result["beneficiary_iban"],
            reference=result.get("reference", ""),
            label=result.get("label"),
            scheduled_date=date.fromisoformat(result["scheduled_date"]) if result.get("scheduled_date") else None,
            executed_at=datetime.fromisoformat(result["executed_at"].replace("Z", "+00:00")) if result.get("executed_at") else None
        )

    async def get_transfer(self, transfer_id: str) -> Optional[ShineTransfer]:
        """Récupérer un virement."""
        try:
            result = await self._request("GET", f"/transfers/{transfer_id}")
            return ShineTransfer(
                id=result["id"],
                amount=result["amount"],
                currency=result.get("currency", "EUR"),
                status=TransferStatus(result.get("status", "pending")),
                beneficiary_name=result["beneficiary_name"],
                beneficiary_iban=result["beneficiary_iban"],
                reference=result.get("reference", ""),
                label=result.get("label"),
                scheduled_date=date.fromisoformat(result["scheduled_date"]) if result.get("scheduled_date") else None,
                executed_at=datetime.fromisoformat(result["executed_at"].replace("Z", "+00:00")) if result.get("executed_at") else None
            )
        except ShineError:
            return None

    # =========================================================================
    # Beneficiaries
    # =========================================================================
    async def list_beneficiaries(self) -> List[ShineBeneficiary]:
        """Lister les bénéficiaires."""
        result = await self._request("GET", "/beneficiaries")

        beneficiaries = []
        for b in result.get("beneficiaries", []):
            beneficiaries.append(ShineBeneficiary(
                id=b["id"],
                name=b["name"],
                iban=b["iban"],
                bic=b.get("bic")
            ))

        return beneficiaries

    async def create_beneficiary(
        self,
        name: str,
        iban: str,
        bic: Optional[str] = None
    ) -> ShineBeneficiary:
        """Créer un bénéficiaire."""
        data = {"name": name, "iban": iban}
        if bic:
            data["bic"] = bic

        result = await self._request("POST", "/beneficiaries", json_data=data)

        return ShineBeneficiary(
            id=result["id"],
            name=result["name"],
            iban=result["iban"],
            bic=result.get("bic")
        )

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class ShineError(Exception):
    """Erreur API Shine."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Service Métier AZALPLUS
# =============================================================================
class ShineService:
    """
    Service Shine intégré à AZALPLUS.

    Gère:
    - Synchronisation des transactions
    - Rapprochement automatique
    - Virements fournisseurs
    """

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self._client: Optional[ShineClient] = None

    async def _get_client(self) -> ShineClient:
        """Récupérer le client Shine configuré."""
        if self._client:
            return self._client

        import os
        config = ShineConfig(
            client_id=os.getenv("SHINE_CLIENT_ID", ""),
            client_secret=os.getenv("SHINE_CLIENT_SECRET", ""),
            access_token=os.getenv("SHINE_ACCESS_TOKEN", ""),
            refresh_token=os.getenv("SHINE_REFRESH_TOKEN", ""),
            environment=ShineEnvironment.SANDBOX
        )

        self._client = ShineClient(config)
        return self._client

    async def sync_transactions(
        self,
        since: Optional[date] = None
    ) -> int:
        """
        Synchroniser les transactions Shine.

        Returns:
            Nombre de nouvelles transactions
        """
        from moteur.db import Database
        from moteur.rapprochement_service import RapprochementService
        import hashlib

        client = await self._get_client()

        # Récupérer le compte Shine
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SHINE", "statut": "ACTIF"}
        )

        if not comptes:
            return 0

        compte = comptes[0]
        compte_id = str(compte["id"])
        shine_account_id = compte.get("provider_account_id")

        if not shine_account_id:
            # Récupérer le premier compte Shine
            accounts = await client.get_accounts()
            if accounts:
                shine_account_id = accounts[0].id
                Database.update(
                    "Comptes_Bancaires",
                    self.tenant_id,
                    UUID(compte_id),
                    {
                        "provider_account_id": shine_account_id,
                        "iban": accounts[0].iban,
                        "solde_actuel": accounts[0].balance
                    }
                )

        total_new = 0
        page = 1

        while True:
            transactions, meta = await client.list_transactions(
                account_id=shine_account_id,
                from_date=since,
                page=page,
                per_page=100
            )

            if not transactions:
                break

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

                # Type d'opération
                type_map = {
                    TransactionType.TRANSFER_IN: "VIREMENT_SEPA",
                    TransactionType.TRANSFER_OUT: "VIREMENT_SEPA",
                    TransactionType.CARD: "CARTE",
                    TransactionType.DIRECT_DEBIT: "PRELEVEMENT",
                    TransactionType.FEE: "FRAIS",
                    TransactionType.CHECK: "CHEQUE",
                }
                type_op = type_map.get(tx.type, "AUTRE")

                # Hash pour détection doublons
                date_op = tx.value_date or (tx.executed_at.date() if tx.executed_at else date.today())
                hash_elements = f"{compte_id}|{date_op}|{abs(tx.amount)}|{sens}|{tx.label[:20]}"
                hash_doublon = hashlib.md5(hash_elements.encode()).hexdigest()

                # Créer le mouvement
                mouvement = Database.insert(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    {
                        "compte_id": compte_id,
                        "date_operation": date_op.isoformat(),
                        "date_valeur": tx.value_date.isoformat() if tx.value_date else None,
                        "libelle": tx.label or "Opération Shine",
                        "libelle_complementaire": tx.reference or "",
                        "sens": sens,
                        "montant": abs(tx.amount),
                        "devise": tx.currency,
                        "type_operation": type_op,
                        "tiers_libelle": tx.counterparty_name or "",
                        "tiers_iban": tx.counterparty_iban or "",
                        "tiers_reference": tx.reference or "",
                        "source": "SHINE",
                        "provider_id": tx.id,
                        "provider_data": {
                            "type": tx.type.value,
                            "category": tx.category,
                            "receipt_url": tx.receipt_url
                        },
                        "statut": "A_TRAITER",
                        "hash_doublon": hash_doublon
                    }
                )

                total_new += 1

                # Tenter rapprochement automatique
                service = RapprochementService(self.tenant_id)
                await service.rapprocher_mouvement(UUID(str(mouvement["id"])))

            # Pagination
            total_pages = meta.get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1

        # Mettre à jour la date de synchro
        Database.update(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id),
            {"derniere_synchro": datetime.utcnow().isoformat()}
        )

        logger.info(f"Shine sync completed: {total_new} new transactions")
        return total_new

    async def pay_supplier(
        self,
        facture_achat_id: UUID,
        scheduled_date: Optional[date] = None
    ) -> Dict:
        """Payer une facture fournisseur par virement Shine."""
        from moteur.db import Database

        client = await self._get_client()

        # Récupérer la facture et le fournisseur
        facture = Database.get_by_id("Factures_Achats", self.tenant_id, facture_achat_id)
        if not facture:
            raise ValueError("Facture non trouvée")

        fournisseur = Database.get_by_id(
            "Fournisseurs",
            self.tenant_id,
            UUID(facture["fournisseur_id"])
        )

        if not fournisseur or not fournisseur.get("iban"):
            raise ValueError("Fournisseur ou IBAN non trouvé")

        # Récupérer le compte Shine
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "SHINE", "statut": "ACTIF"}
        )

        if not comptes:
            raise ValueError("Aucun compte Shine configuré")

        compte = comptes[0]
        shine_account_id = compte.get("provider_account_id")

        if not shine_account_id:
            raise ValueError("Compte Shine non synchronisé")

        # Créer le virement
        transfer = await client.create_transfer(
            account_id=shine_account_id,
            beneficiary_iban=fournisseur["iban"],
            beneficiary_name=fournisseur.get("raison_sociale") or fournisseur.get("nom"),
            amount=float(facture.get("montant_ttc", 0)),
            reference=facture.get("numero", str(facture_achat_id)[:20]),
            label=f"Paiement facture {facture.get('numero')}",
            scheduled_date=scheduled_date
        )

        # Enregistrer le paiement
        Database.insert(
            "Paiements",
            self.tenant_id,
            {
                "facture_achat_id": str(facture_achat_id),
                "montant": transfer.amount,
                "date_paiement": datetime.utcnow().date().isoformat(),
                "mode_paiement": "VIREMENT_SEPA",
                "reference": transfer.id,
                "statut": "EN_ATTENTE" if transfer.status == TransferStatus.PENDING else "VALIDE",
                "provider": "SHINE",
                "provider_id": transfer.id
            }
        )

        logger.info(f"Shine transfer created: {transfer.id}")

        return {
            "transfer_id": transfer.id,
            "status": transfer.status.value,
            "amount": transfer.amount
        }
