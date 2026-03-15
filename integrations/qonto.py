# =============================================================================
# AZALPLUS - Intégration Qonto
# =============================================================================
"""
Qonto - Banque en ligne pour entreprises.

Fonctionnalités:
- Compte courant professionnel avec IBAN français
- Cartes bancaires (virtuelles et physiques)
- Virements SEPA (instant et standard)
- Prélèvements
- Multi-utilisateurs avec droits
- API complète

Tarification:
- Basic: 9€/mois
- Smart: 19€/mois
- Premium: 39€/mois

Documentation: https://api-doc.qonto.com/
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
class QontoEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    REVERSED = "reversed"
    DECLINED = "declined"
    COMPLETED = "completed"


class TransactionSide(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionOperationType(str, Enum):
    TRANSFER = "transfer"
    CARD = "card"
    DIRECT_DEBIT = "direct_debit"
    INCOME = "income"
    QONTO_FEE = "qonto_fee"
    CHECK = "check"
    RECALL = "recall"
    OTHER = "other"


class TransferStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SETTLED = "settled"
    DECLINED = "declined"
    CANCELED = "canceled"


# =============================================================================
# Configuration
# =============================================================================
@dataclass
class QontoConfig:
    """Configuration Qonto par tenant."""
    login: str  # Identifiant de connexion (slug organisation)
    secret_key: str  # Clé secrète API
    environment: QontoEnvironment = QontoEnvironment.SANDBOX

    @property
    def base_url(self) -> str:
        if self.environment == QontoEnvironment.PRODUCTION:
            return "https://thirdparty.qonto.com/v2"
        return "https://thirdparty.sandbox.qonto.com/v2"


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class Organization:
    """Organisation Qonto."""
    slug: str
    legal_name: str
    bank_accounts: List["BankAccount"] = field(default_factory=list)


@dataclass
class BankAccount:
    """Compte bancaire Qonto."""
    slug: str
    iban: str
    bic: str
    currency: str
    balance: float
    balance_cents: int
    authorized_balance: float
    authorized_balance_cents: int
    name: str = ""
    status: str = "active"


@dataclass
class Transaction:
    """Transaction Qonto."""
    id: str
    transaction_id: str
    amount: float
    amount_cents: int
    currency: str
    side: TransactionSide
    operation_type: TransactionOperationType
    status: TransactionStatus
    label: str
    settled_at: Optional[datetime] = None
    emitted_at: Optional[datetime] = None
    reference: Optional[str] = None
    note: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_iban: Optional[str] = None
    category: Optional[str] = None
    attachment_ids: List[str] = field(default_factory=list)


@dataclass
class ExternalTransfer:
    """Virement externe."""
    id: str
    status: TransferStatus
    amount: float
    amount_cents: int
    currency: str
    beneficiary_name: str
    beneficiary_iban: str
    reference: str
    scheduled_date: Optional[date] = None
    note: Optional[str] = None


@dataclass
class Beneficiary:
    """Bénéficiaire de virement."""
    id: str
    name: str
    iban: str
    bic: Optional[str] = None
    email: Optional[str] = None


# =============================================================================
# Client API Qonto
# =============================================================================
class QontoClient:
    """
    Client API Qonto.

    Usage:
        config = QontoConfig(
            login="my-company",
            secret_key="xxx"
        )
        client = QontoClient(config)

        # Récupérer les transactions
        transactions = await client.list_transactions(iban="FR76xxx")
    """

    def __init__(self, config: QontoConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0,
                headers={
                    "Authorization": f"{self.config.login}:{self.config.secret_key}",
                    "Content-Type": "application/json"
                }
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
            logger.error(f"Qonto API error: {response.status_code} - {error_msg}")
            raise QontoError(error_msg, error_data)

        return response.json()

    # =========================================================================
    # Organization
    # =========================================================================
    async def get_organization(self) -> Organization:
        """Récupérer les informations de l'organisation."""
        result = await self._request("GET", "/organization")
        org_data = result.get("organization", {})

        bank_accounts = []
        for ba in org_data.get("bank_accounts", []):
            bank_accounts.append(BankAccount(
                slug=ba["slug"],
                iban=ba["iban"],
                bic=ba["bic"],
                currency=ba["currency"],
                balance=ba["balance"],
                balance_cents=ba["balance_cents"],
                authorized_balance=ba["authorized_balance"],
                authorized_balance_cents=ba["authorized_balance_cents"],
                name=ba.get("name", ""),
                status=ba.get("status", "active")
            ))

        return Organization(
            slug=org_data["slug"],
            legal_name=org_data.get("legal_name", ""),
            bank_accounts=bank_accounts
        )

    # =========================================================================
    # Transactions
    # =========================================================================
    async def list_transactions(
        self,
        iban: str,
        status: Optional[List[str]] = None,
        settled_at_from: Optional[datetime] = None,
        settled_at_to: Optional[datetime] = None,
        side: Optional[str] = None,
        current_page: int = 1,
        per_page: int = 100
    ) -> tuple[List[Transaction], Dict]:
        """
        Lister les transactions d'un compte.

        Args:
            iban: IBAN du compte
            status: Filtrer par statut(s)
            settled_at_from: Date de début
            settled_at_to: Date de fin
            side: "debit" ou "credit"
            current_page: Page courante
            per_page: Nombre par page

        Returns:
            Tuple (transactions, pagination_meta)
        """
        params = {
            "iban": iban,
            "current_page": current_page,
            "per_page": per_page
        }

        if status:
            params["status[]"] = status
        if settled_at_from:
            params["settled_at_from"] = settled_at_from.isoformat()
        if settled_at_to:
            params["settled_at_to"] = settled_at_to.isoformat()
        if side:
            params["side"] = side

        result = await self._request("GET", "/transactions", params=params)

        transactions = []
        for tx in result.get("transactions", []):
            transactions.append(Transaction(
                id=tx["id"],
                transaction_id=tx["transaction_id"],
                amount=tx["amount"],
                amount_cents=tx["amount_cents"],
                currency=tx["currency"],
                side=TransactionSide(tx["side"]),
                operation_type=TransactionOperationType(tx.get("operation_type", "other")),
                status=TransactionStatus(tx["status"]),
                label=tx.get("label", ""),
                settled_at=datetime.fromisoformat(tx["settled_at"].replace("Z", "+00:00")) if tx.get("settled_at") else None,
                emitted_at=datetime.fromisoformat(tx["emitted_at"].replace("Z", "+00:00")) if tx.get("emitted_at") else None,
                reference=tx.get("reference"),
                note=tx.get("note"),
                counterparty_name=tx.get("label"),
                counterparty_iban=None,
                category=tx.get("category"),
                attachment_ids=tx.get("attachment_ids", [])
            ))

        meta = result.get("meta", {})

        return transactions, meta

    # =========================================================================
    # Transfers
    # =========================================================================
    async def create_external_transfer(
        self,
        debit_iban: str,
        beneficiary_id: str,
        amount: float,
        reference: str,
        note: Optional[str] = None,
        scheduled_date: Optional[date] = None
    ) -> ExternalTransfer:
        """
        Créer un virement externe.

        Args:
            debit_iban: IBAN du compte à débiter
            beneficiary_id: ID du bénéficiaire
            amount: Montant en euros
            reference: Référence du virement
            note: Note interne
            scheduled_date: Date programmée
        """
        data = {
            "external_transfer": {
                "debit_iban": debit_iban,
                "beneficiary_id": beneficiary_id,
                "amount": amount,
                "currency": "EUR",
                "reference": reference
            }
        }

        if note:
            data["external_transfer"]["note"] = note
        if scheduled_date:
            data["external_transfer"]["scheduled_date"] = scheduled_date.isoformat()

        result = await self._request("POST", "/external_transfers", json_data=data)
        transfer_data = result.get("external_transfer", {})

        return ExternalTransfer(
            id=transfer_data["id"],
            status=TransferStatus(transfer_data["status"]),
            amount=transfer_data["amount"],
            amount_cents=transfer_data["amount_cents"],
            currency=transfer_data["currency"],
            beneficiary_name=transfer_data.get("beneficiary_name", ""),
            beneficiary_iban=transfer_data.get("beneficiary_iban", ""),
            reference=transfer_data.get("reference", ""),
            scheduled_date=date.fromisoformat(transfer_data["scheduled_date"]) if transfer_data.get("scheduled_date") else None,
            note=transfer_data.get("note")
        )

    # =========================================================================
    # Beneficiaries
    # =========================================================================
    async def list_beneficiaries(
        self,
        current_page: int = 1,
        per_page: int = 100
    ) -> tuple[List[Beneficiary], Dict]:
        """Lister les bénéficiaires."""
        params = {
            "current_page": current_page,
            "per_page": per_page
        }

        result = await self._request("GET", "/beneficiaries", params=params)

        beneficiaries = []
        for b in result.get("beneficiaries", []):
            beneficiaries.append(Beneficiary(
                id=b["id"],
                name=b["name"],
                iban=b["iban"],
                bic=b.get("bic"),
                email=b.get("email")
            ))

        return beneficiaries, result.get("meta", {})

    async def create_beneficiary(
        self,
        name: str,
        iban: str,
        bic: Optional[str] = None,
        email: Optional[str] = None
    ) -> Beneficiary:
        """Créer un bénéficiaire."""
        data = {
            "beneficiary": {
                "name": name,
                "iban": iban
            }
        }

        if bic:
            data["beneficiary"]["bic"] = bic
        if email:
            data["beneficiary"]["email"] = email

        result = await self._request("POST", "/beneficiaries", json_data=data)
        b = result.get("beneficiary", {})

        return Beneficiary(
            id=b["id"],
            name=b["name"],
            iban=b["iban"],
            bic=b.get("bic"),
            email=b.get("email")
        )

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class QontoError(Exception):
    """Erreur API Qonto."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Service Métier AZALPLUS
# =============================================================================
class QontoService:
    """
    Service Qonto intégré à AZALPLUS.

    Gère:
    - Synchronisation des transactions
    - Rapprochement automatique
    - Virements fournisseurs
    """

    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
        self._client: Optional[QontoClient] = None

    async def _get_client(self) -> QontoClient:
        """Récupérer le client Qonto configuré."""
        if self._client:
            return self._client

        import os
        config = QontoConfig(
            login=os.getenv("QONTO_LOGIN", ""),
            secret_key=os.getenv("QONTO_SECRET_KEY", ""),
            environment=QontoEnvironment.SANDBOX
        )

        self._client = QontoClient(config)
        return self._client

    async def sync_transactions(
        self,
        since: Optional[datetime] = None
    ) -> int:
        """
        Synchroniser les transactions Qonto.

        Returns:
            Nombre de nouvelles transactions
        """
        from moteur.db import Database
        from moteur.rapprochement_service import RapprochementService
        import hashlib

        client = await self._get_client()

        # Récupérer le compte Qonto
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "QONTO", "statut": "ACTIF"}
        )

        if not comptes:
            return 0

        compte = comptes[0]
        compte_id = str(compte["id"])
        iban = compte.get("iban")

        if not iban:
            logger.warning("Qonto account has no IBAN")
            return 0

        total_new = 0
        current_page = 1

        while True:
            transactions, meta = await client.list_transactions(
                iban=iban,
                status=["completed"],
                settled_at_from=since,
                current_page=current_page,
                per_page=100
            )

            for tx in transactions:
                # Vérifier si déjà importée
                existing = Database.query(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    filters={"provider_id": tx.transaction_id}
                )

                if existing:
                    continue

                # Mapper les données
                sens = "CREDIT" if tx.side == TransactionSide.CREDIT else "DEBIT"

                # Type d'opération
                type_map = {
                    TransactionOperationType.TRANSFER: "VIREMENT_SEPA",
                    TransactionOperationType.CARD: "CARTE",
                    TransactionOperationType.DIRECT_DEBIT: "PRELEVEMENT",
                    TransactionOperationType.INCOME: "VIREMENT_SEPA",
                    TransactionOperationType.QONTO_FEE: "FRAIS",
                    TransactionOperationType.CHECK: "CHEQUE",
                }
                type_op = type_map.get(tx.operation_type, "AUTRE")

                # Hash pour détection doublons
                date_op = tx.settled_at.date() if tx.settled_at else date.today()
                hash_elements = f"{compte_id}|{date_op}|{tx.amount}|{sens}|{tx.label[:20]}"
                hash_doublon = hashlib.md5(hash_elements.encode()).hexdigest()

                # Créer le mouvement
                mouvement = Database.insert(
                    "Mouvements_Bancaires",
                    self.tenant_id,
                    {
                        "compte_id": compte_id,
                        "date_operation": date_op.isoformat(),
                        "date_valeur": date_op.isoformat(),
                        "libelle": tx.label or "Opération Qonto",
                        "libelle_complementaire": tx.reference or "",
                        "sens": sens,
                        "montant": abs(tx.amount),
                        "devise": tx.currency.upper(),
                        "type_operation": type_op,
                        "tiers_libelle": tx.counterparty_name or "",
                        "tiers_reference": tx.reference or "",
                        "source": "QONTO",
                        "provider_id": tx.transaction_id,
                        "provider_data": {
                            "qonto_id": tx.id,
                            "operation_type": tx.operation_type.value,
                            "category": tx.category,
                            "attachments": tx.attachment_ids
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
            if current_page >= total_pages:
                break
            current_page += 1

        # Mettre à jour la date de synchro
        Database.update(
            "Comptes_Bancaires",
            self.tenant_id,
            UUID(compte_id),
            {"derniere_synchro": datetime.utcnow().isoformat()}
        )

        logger.info(f"Qonto sync completed: {total_new} new transactions")
        return total_new

    async def pay_supplier(
        self,
        facture_achat_id: UUID,
        scheduled_date: Optional[date] = None
    ) -> Dict:
        """
        Payer une facture fournisseur par virement Qonto.

        Args:
            facture_achat_id: ID de la facture d'achat
            scheduled_date: Date programmée (optionnel)
        """
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

        # Récupérer le compte Qonto
        comptes = Database.query(
            "Comptes_Bancaires",
            self.tenant_id,
            filters={"provider": "QONTO", "statut": "ACTIF"}
        )

        if not comptes:
            raise ValueError("Aucun compte Qonto configuré")

        compte = comptes[0]

        # Créer ou récupérer le bénéficiaire
        beneficiaries, _ = await client.list_beneficiaries()
        beneficiary_id = None

        for b in beneficiaries:
            if b.iban == fournisseur["iban"]:
                beneficiary_id = b.id
                break

        if not beneficiary_id:
            new_beneficiary = await client.create_beneficiary(
                name=fournisseur.get("raison_sociale") or fournisseur.get("nom"),
                iban=fournisseur["iban"],
                bic=fournisseur.get("bic")
            )
            beneficiary_id = new_beneficiary.id

        # Créer le virement
        transfer = await client.create_external_transfer(
            debit_iban=compte["iban"],
            beneficiary_id=beneficiary_id,
            amount=float(facture.get("montant_ttc", 0)),
            reference=facture.get("numero", str(facture_achat_id)[:20]),
            note=f"Paiement facture {facture.get('numero')}",
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
                "provider": "QONTO",
                "provider_id": transfer.id
            }
        )

        logger.info(f"Qonto transfer created: {transfer.id}")

        return {
            "transfer_id": transfer.id,
            "status": transfer.status.value,
            "amount": transfer.amount
        }
