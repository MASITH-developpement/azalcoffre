# =============================================================================
# AZALPLUS - Intégration Fintecture (Open Banking)
# =============================================================================
"""
Fintecture Connect API - Paiements instantanés via Open Banking

Commission: 0.99% (Fintecture) + 0.30% (AZALPLUS) = 1.29% total

Workflow:
1. Créer un lien de paiement pour une facture
2. Client clique et choisit sa banque
3. Authentification bancaire (SCA)
4. Virement pré-rempli confirmé
5. Webhook notification -> rapprochement automatique
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx

logger = logging.getLogger(__name__)


class FintectureEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class PaymentStatus(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FintectureConfig:
    """Configuration Fintecture par tenant."""
    app_id: str
    app_secret: str
    private_key: str  # PEM format
    environment: FintectureEnvironment = FintectureEnvironment.SANDBOX
    webhook_secret: Optional[str] = None

    @property
    def base_url(self) -> str:
        if self.environment == FintectureEnvironment.PRODUCTION:
            return "https://api.fintecture.com"
        return "https://api-sandbox.fintecture.com"

    @property
    def connect_url(self) -> str:
        if self.environment == FintectureEnvironment.PRODUCTION:
            return "https://connect.fintecture.com"
        return "https://connect-sandbox.fintecture.com"


@dataclass
class PaymentRequest:
    """Demande de paiement."""
    amount: float
    currency: str = "EUR"
    reference: str = ""
    description: str = ""
    beneficiary_name: str = ""
    beneficiary_iban: str = ""
    beneficiary_swift: str = ""
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    redirect_uri: str = ""
    webhook_uri: str = ""
    metadata: Optional[dict] = None


@dataclass
class PaymentResponse:
    """Réponse création paiement."""
    payment_id: str
    connect_url: str
    status: PaymentStatus
    created_at: datetime
    expires_at: Optional[datetime] = None


@dataclass
class PaymentStatusResponse:
    """Statut d'un paiement."""
    payment_id: str
    status: PaymentStatus
    amount: float
    currency: str
    reference: str
    execution_date: Optional[datetime] = None
    bank_name: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class FintectureClient:
    """
    Client API Fintecture pour Open Banking.

    Usage:
        config = FintectureConfig(
            app_id="xxx",
            app_secret="xxx",
            private_key="-----BEGIN RSA PRIVATE KEY-----..."
        )
        client = FintectureClient(config)

        # Créer un paiement
        payment = await client.create_payment(PaymentRequest(
            amount=150.00,
            reference="FAC-2024-001",
            description="Facture plomberie",
            beneficiary_name="SARL Dupont",
            beneficiary_iban="FR7630001007941234567890185",
            redirect_uri="https://app.azalplus.fr/paiement/success",
            webhook_uri="https://app.azalplus.fr/api/webhooks/fintecture"
        ))

        # URL à envoyer au client
        print(payment.connect_url)
    """

    COMMISSION_FINTECTURE = 0.0099  # 0.99%
    COMMISSION_AZALPLUS = 0.0030   # 0.30%
    COMMISSION_TOTALE = 0.0129    # 1.29%

    def __init__(self, config: FintectureConfig):
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

        client = await self._get_client()

        response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "app_id": self.config.app_id,
                "scope": "PIS"  # Payment Initiation Service
            },
            headers={
                "Authorization": f"Basic {self._encode_credentials()}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        response.raise_for_status()

        data = response.json()
        self._access_token = data["access_token"]
        # Token valide 1 heure, on rafraîchit à 50 min
        from datetime import timedelta
        self._token_expires_at = datetime.utcnow() + timedelta(minutes=50)

        return self._access_token

    def _encode_credentials(self) -> str:
        """Encode app_id:app_secret en Base64."""
        import base64
        credentials = f"{self.config.app_id}:{self.config.app_secret}"
        return base64.b64encode(credentials.encode()).decode()

    async def create_payment(self, request: PaymentRequest) -> PaymentResponse:
        """
        Créer un lien de paiement.

        Args:
            request: Détails du paiement

        Returns:
            PaymentResponse avec l'URL de paiement
        """
        token = await self._get_access_token()
        client = await self._get_client()

        # Payload Fintecture PIS
        payload = {
            "data": {
                "type": "PIS",
                "attributes": {
                    "amount": str(request.amount),
                    "currency": request.currency,
                    "communication": request.reference,
                    "beneficiary": {
                        "name": request.beneficiary_name,
                        "iban": request.beneficiary_iban,
                        "swift_bic": request.beneficiary_swift or "",
                        "street": "",
                        "city": "",
                        "zip": "",
                        "country": "FR"
                    },
                    "end_to_end_id": request.reference[:35],  # Max 35 chars
                }
            },
            "meta": {
                "psu_name": request.customer_name or "",
                "psu_email": request.customer_email or "",
                "redirect_uri": request.redirect_uri,
                "webhook_uri": request.webhook_uri,
            }
        }

        if request.metadata:
            payload["meta"]["metadata"] = request.metadata

        response = await client.post(
            "/pis/v2/connect",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Id": str(uuid4())
            }
        )

        if response.status_code >= 400:
            logger.error(f"Fintecture error: {response.status_code} - {response.text}")
            raise FintectureError(
                f"Erreur création paiement: {response.status_code}",
                response.json() if response.text else {}
            )

        data = response.json()

        return PaymentResponse(
            payment_id=data["meta"]["session_id"],
            connect_url=data["meta"]["url"],
            status=PaymentStatus.CREATED,
            created_at=datetime.utcnow(),
            expires_at=None
        )

    async def get_payment_status(self, payment_id: str) -> PaymentStatusResponse:
        """
        Récupérer le statut d'un paiement.

        Args:
            payment_id: ID du paiement (session_id)

        Returns:
            PaymentStatusResponse
        """
        token = await self._get_access_token()
        client = await self._get_client()

        response = await client.get(
            f"/pis/v2/payments/{payment_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Id": str(uuid4())
            }
        )

        if response.status_code == 404:
            raise FintectureError("Paiement non trouvé", {"payment_id": payment_id})

        response.raise_for_status()
        data = response.json()

        attrs = data["data"]["attributes"]
        status_map = {
            "payment_created": PaymentStatus.CREATED,
            "payment_pending": PaymentStatus.PENDING,
            "payment_processing": PaymentStatus.PROCESSING,
            "payment_successful": PaymentStatus.COMPLETED,
            "payment_unsuccessful": PaymentStatus.FAILED,
            "payment_cancelled": PaymentStatus.CANCELLED,
        }

        return PaymentStatusResponse(
            payment_id=payment_id,
            status=status_map.get(attrs.get("status"), PaymentStatus.PENDING),
            amount=float(attrs.get("amount", 0)),
            currency=attrs.get("currency", "EUR"),
            reference=attrs.get("communication", ""),
            execution_date=None,
            bank_name=attrs.get("bank_name"),
            error_code=attrs.get("error_code"),
            error_message=attrs.get("error_message")
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Vérifier la signature d'un webhook Fintecture.

        Args:
            payload: Corps de la requête (bytes)
            signature: Header X-Fintecture-Signature

        Returns:
            True si signature valide
        """
        if not self.config.webhook_secret:
            logger.warning("Webhook secret non configuré")
            return False

        expected = hmac.new(
            self.config.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def calculate_commission(self, amount: float) -> dict:
        """
        Calculer les commissions sur un paiement.

        Args:
            amount: Montant du paiement

        Returns:
            dict avec détail des commissions
        """
        commission_fintecture = round(amount * self.COMMISSION_FINTECTURE, 2)
        commission_azalplus = round(amount * self.COMMISSION_AZALPLUS, 2)
        commission_totale = commission_fintecture + commission_azalplus
        montant_net = round(amount - commission_totale, 2)

        return {
            "montant_brut": amount,
            "commission_fintecture": commission_fintecture,
            "commission_fintecture_pct": self.COMMISSION_FINTECTURE * 100,
            "commission_azalplus": commission_azalplus,
            "commission_azalplus_pct": self.COMMISSION_AZALPLUS * 100,
            "commission_totale": commission_totale,
            "commission_totale_pct": self.COMMISSION_TOTALE * 100,
            "montant_net": montant_net
        }

    async def get_banks(self, country: str = "FR") -> list[dict]:
        """
        Liste des banques disponibles.

        Args:
            country: Code pays ISO (défaut FR)

        Returns:
            Liste des banques avec nom, logo, etc.
        """
        token = await self._get_access_token()
        client = await self._get_client()

        response = await client.get(
            f"/ais/v2/providers?filter[country]={country}",
            headers={
                "Authorization": f"Bearer {token}"
            }
        )
        response.raise_for_status()

        data = response.json()
        banks = []

        for provider in data.get("data", []):
            attrs = provider.get("attributes", {})
            banks.append({
                "id": provider["id"],
                "name": attrs.get("name"),
                "logo": attrs.get("logo"),
                "country": attrs.get("country"),
                "pis_enabled": attrs.get("pis", False)
            })

        return banks

    async def close(self):
        """Fermer le client HTTP."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class FintectureError(Exception):
    """Erreur API Fintecture."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


# =============================================================================
# Service métier pour intégration avec les factures
# =============================================================================

class FintecturePaymentService:
    """
    Service de paiement Fintecture intégré aux factures AZALPLUS.

    Usage:
        service = FintecturePaymentService(db, tenant_id)

        # Créer lien de paiement pour une facture
        result = await service.create_invoice_payment_link(
            facture_id="uuid-facture",
            redirect_url="https://..."
        )

        # Traiter webhook de paiement reçu
        await service.handle_payment_webhook(webhook_data)
    """

    def __init__(self, db, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self._client: Optional[FintectureClient] = None

    async def _get_client(self) -> FintectureClient:
        """Récupérer le client Fintecture configuré pour le tenant."""
        if self._client:
            return self._client

        # Récupérer config depuis la base
        # En prod: SELECT * FROM tenant_settings WHERE tenant_id = ? AND key = 'fintecture'
        config = await self._load_tenant_config()

        self._client = FintectureClient(config)
        return self._client

    async def _load_tenant_config(self) -> FintectureConfig:
        """Charger la configuration Fintecture du tenant."""
        # TODO: Implémenter lecture depuis DB
        # Pour l'instant, config par défaut (sandbox)
        import os
        return FintectureConfig(
            app_id=os.getenv("FINTECTURE_APP_ID", ""),
            app_secret=os.getenv("FINTECTURE_APP_SECRET", ""),
            private_key=os.getenv("FINTECTURE_PRIVATE_KEY", ""),
            environment=FintectureEnvironment.SANDBOX,
            webhook_secret=os.getenv("FINTECTURE_WEBHOOK_SECRET", "")
        )

    async def create_invoice_payment_link(
        self,
        facture_id: UUID,
        redirect_url: str,
        webhook_url: str
    ) -> dict:
        """
        Créer un lien de paiement pour une facture.

        Args:
            facture_id: ID de la facture
            redirect_url: URL de redirection après paiement
            webhook_url: URL webhook pour notifications

        Returns:
            dict avec payment_url et payment_id
        """
        # Récupérer la facture
        facture = await self._get_facture(facture_id)
        if not facture:
            raise ValueError(f"Facture {facture_id} non trouvée")

        if facture["status"] == "PAYEE":
            raise ValueError("Facture déjà payée")

        # Récupérer infos entreprise (bénéficiaire)
        entreprise = await self._get_entreprise()

        # Récupérer client
        client_data = await self._get_client_data(facture["client_id"])

        client = await self._get_client()

        request = PaymentRequest(
            amount=float(facture["montant_ttc"]),
            currency="EUR",
            reference=facture["numero"],
            description=f"Facture {facture['numero']}",
            beneficiary_name=entreprise["raison_sociale"],
            beneficiary_iban=entreprise["iban"],
            beneficiary_swift=entreprise.get("bic", ""),
            customer_email=client_data.get("email"),
            customer_name=client_data.get("nom"),
            redirect_uri=redirect_url,
            webhook_uri=webhook_url,
            metadata={
                "facture_id": str(facture_id),
                "tenant_id": str(self.tenant_id),
                "facture_numero": facture["numero"]
            }
        )

        response = await client.create_payment(request)

        # Sauvegarder le paiement en base
        await self._save_payment_record(
            facture_id=facture_id,
            payment_id=response.payment_id,
            amount=facture["montant_ttc"],
            status=response.status.value,
            connect_url=response.connect_url
        )

        # Calculer commissions
        commissions = client.calculate_commission(float(facture["montant_ttc"]))

        return {
            "payment_id": response.payment_id,
            "payment_url": response.connect_url,
            "status": response.status.value,
            "created_at": response.created_at.isoformat(),
            "commissions": commissions
        }

    async def handle_payment_webhook(self, payload: dict, signature: str) -> dict:
        """
        Traiter un webhook de paiement Fintecture.

        Args:
            payload: Données du webhook
            signature: Signature du webhook

        Returns:
            Résultat du traitement
        """
        client = await self._get_client()

        # Vérifier signature
        payload_bytes = json.dumps(payload).encode()
        if not client.verify_webhook_signature(payload_bytes, signature):
            logger.warning("Signature webhook invalide")
            raise ValueError("Signature invalide")

        event_type = payload.get("type")
        data = payload.get("data", {})

        if event_type == "payment.successful":
            return await self._handle_payment_success(data)
        elif event_type == "payment.unsuccessful":
            return await self._handle_payment_failure(data)
        elif event_type == "payment.cancelled":
            return await self._handle_payment_cancelled(data)
        else:
            logger.info(f"Webhook ignoré: {event_type}")
            return {"status": "ignored", "type": event_type}

    async def _handle_payment_success(self, data: dict) -> dict:
        """Traiter un paiement réussi."""
        payment_id = data.get("session_id")
        metadata = data.get("metadata", {})
        facture_id = metadata.get("facture_id")

        if not facture_id:
            logger.error(f"Paiement {payment_id} sans facture_id")
            return {"status": "error", "message": "facture_id manquant"}

        # Mettre à jour le paiement
        await self._update_payment_status(payment_id, PaymentStatus.COMPLETED)

        # Marquer la facture comme payée
        await self._mark_facture_paid(
            facture_id=UUID(facture_id),
            payment_id=payment_id,
            payment_date=datetime.utcnow()
        )

        # Créer le mouvement de paiement
        amount = float(data.get("amount", 0))
        commissions = FintectureClient.calculate_commission(
            FintectureClient, amount
        )

        await self._create_payment_record(
            facture_id=UUID(facture_id),
            amount=amount,
            commission=commissions["commission_totale"],
            net_amount=commissions["montant_net"],
            payment_method="OPEN_BANKING",
            reference=payment_id
        )

        logger.info(f"Facture {facture_id} payée via Fintecture ({payment_id})")

        return {
            "status": "success",
            "facture_id": facture_id,
            "payment_id": payment_id,
            "amount": amount,
            "commission": commissions["commission_totale"]
        }

    async def _handle_payment_failure(self, data: dict) -> dict:
        """Traiter un paiement échoué."""
        payment_id = data.get("session_id")
        error_code = data.get("error_code")
        error_message = data.get("error_message")

        await self._update_payment_status(
            payment_id,
            PaymentStatus.FAILED,
            error_code=error_code,
            error_message=error_message
        )

        logger.warning(f"Paiement {payment_id} échoué: {error_code} - {error_message}")

        return {
            "status": "failed",
            "payment_id": payment_id,
            "error_code": error_code,
            "error_message": error_message
        }

    async def _handle_payment_cancelled(self, data: dict) -> dict:
        """Traiter un paiement annulé."""
        payment_id = data.get("session_id")

        await self._update_payment_status(payment_id, PaymentStatus.CANCELLED)

        logger.info(f"Paiement {payment_id} annulé par l'utilisateur")

        return {
            "status": "cancelled",
            "payment_id": payment_id
        }

    # -------------------------------------------------------------------------
    # Méthodes DB (à implémenter selon le schéma)
    # -------------------------------------------------------------------------

    async def _get_facture(self, facture_id: UUID) -> Optional[dict]:
        """Récupérer une facture."""
        # TODO: Implémenter avec Database.query
        pass

    async def _get_entreprise(self) -> dict:
        """Récupérer les infos de l'entreprise du tenant."""
        # TODO: Implémenter
        pass

    async def _get_client_data(self, client_id: UUID) -> dict:
        """Récupérer les infos client."""
        # TODO: Implémenter
        pass

    async def _save_payment_record(self, **kwargs):
        """Sauvegarder un enregistrement de paiement."""
        # TODO: Implémenter
        pass

    async def _update_payment_status(self, payment_id: str, status: PaymentStatus, **kwargs):
        """Mettre à jour le statut d'un paiement."""
        # TODO: Implémenter
        pass

    async def _mark_facture_paid(self, facture_id: UUID, payment_id: str, payment_date: datetime):
        """Marquer une facture comme payée."""
        # TODO: Implémenter
        pass

    async def _create_payment_record(self, **kwargs):
        """Créer un mouvement de paiement."""
        # TODO: Implémenter
        pass
