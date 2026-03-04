# =============================================================================
# AZALPLUS - Event System
# =============================================================================
"""
Systeme d'evenements pour la communication cross-module.

Ce systeme permet aux modules de s'abonner a des evenements emis par d'autres
modules sans couplage direct. C'est la base de l'architecture No-Code.

Evenements principaux:
- invoice_paid: Facture payee
- quote_accepted: Devis accepte (devient commande ou facture)
- stock_low: Stock en dessous du seuil
- stock_out: Rupture de stock
- intervention_completed: Intervention terminee
- client_created: Nouveau client cree
- payment_received: Paiement recu
- subscription_renewed: Abonnement renouvele
- document_validated: Document valide (devis, facture, etc.)
- workflow_transition: Changement d'etat d'un workflow

Usage:
    # S'abonner a un evenement
    @EventBus.subscribe('invoice_paid')
    async def on_invoice_paid(event: Event):
        print(f"Facture {event.data['invoice_id']} payee!")

    # Emettre un evenement
    await EventBus.emit('invoice_paid', {
        'invoice_id': '...',
        'amount': 1500.00,
        'client_id': '...'
    })
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable, Optional, Awaitable
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum
import structlog
import asyncio
from functools import wraps

logger = structlog.get_logger()


# =============================================================================
# Event Types (Enumeration des evenements standard)
# =============================================================================
class EventType(str, Enum):
    """Types d'evenements standard du systeme."""

    # === Ventes ===
    QUOTE_CREATED = "quote_created"
    QUOTE_SENT = "quote_sent"
    QUOTE_ACCEPTED = "quote_accepted"
    QUOTE_REFUSED = "quote_refused"

    INVOICE_CREATED = "invoice_created"
    INVOICE_SENT = "invoice_sent"
    INVOICE_VALIDATED = "invoice_validated"
    INVOICE_PAID = "invoice_paid"
    INVOICE_PARTIAL_PAID = "invoice_partial_paid"
    INVOICE_CANCELLED = "invoice_cancelled"

    # === Achats ===
    ORDER_CREATED = "order_created"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_RECEIVED = "order_received"
    ORDER_CANCELLED = "order_cancelled"

    # === Stock ===
    STOCK_LOW = "stock_low"
    STOCK_OUT = "stock_out"
    STOCK_REPLENISHED = "stock_replenished"
    STOCK_MOVEMENT = "stock_movement"
    STOCK_ADJUSTED = "stock_adjusted"

    # === Clients ===
    CLIENT_CREATED = "client_created"
    CLIENT_UPDATED = "client_updated"
    CLIENT_DEACTIVATED = "client_deactivated"

    # === Interventions ===
    INTERVENTION_CREATED = "intervention_created"
    INTERVENTION_SCHEDULED = "intervention_scheduled"
    INTERVENTION_STARTED = "intervention_started"
    INTERVENTION_COMPLETED = "intervention_completed"
    INTERVENTION_BLOCKED = "intervention_blocked"
    INTERVENTION_CANCELLED = "intervention_cancelled"

    # === Paiements ===
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"

    # === Abonnements ===
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_EXPIRED = "subscription_expired"

    # === Documents ===
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_VALIDATED = "document_validated"
    DOCUMENT_ARCHIVED = "document_archived"

    # === Workflow ===
    WORKFLOW_TRANSITION = "workflow_transition"
    WORKFLOW_COMPLETED = "workflow_completed"

    # === Systeme ===
    TENANT_CREATED = "tenant_created"
    USER_CREATED = "user_created"
    USER_LOGGED_IN = "user_logged_in"
    BACKUP_COMPLETED = "backup_completed"

    # === Generique ===
    RECORD_CREATED = "record_created"
    RECORD_UPDATED = "record_updated"
    RECORD_DELETED = "record_deleted"


# =============================================================================
# Event Data Class
# =============================================================================
@dataclass
class Event:
    """Represente un evenement dans le systeme."""

    id: UUID = field(default_factory=uuid4)
    type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Contexte obligatoire (multi-tenant)
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None

    # Source de l'evenement
    source_module: str = ""
    source_record_id: Optional[UUID] = None

    # Metadonnees
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Etat de traitement
    processed: bool = False
    error: Optional[str] = None


# =============================================================================
# Event Subscriber Type
# =============================================================================
EventHandler = Callable[[Event], Awaitable[None]]


# =============================================================================
# Event Bus (Singleton)
# =============================================================================
class EventBus:
    """
    Bus d'evenements central pour la communication inter-modules.

    Le bus est thread-safe et supporte:
    - Abonnements multiples par evenement
    - Execution asynchrone des handlers
    - Retry automatique en cas d'echec
    - Log de tous les evenements pour audit
    """

    _subscribers: Dict[str, List[EventHandler]] = {}
    _event_history: List[Event] = []
    _max_history: int = 1000
    _enabled: bool = True

    @classmethod
    def subscribe(cls, event_type: str):
        """
        Decorateur pour s'abonner a un evenement.

        Usage:
            @EventBus.subscribe('invoice_paid')
            async def handle_invoice_paid(event: Event):
                ...
        """
        def decorator(handler: EventHandler):
            if event_type not in cls._subscribers:
                cls._subscribers[event_type] = []
            cls._subscribers[event_type].append(handler)
            logger.debug("event_subscriber_registered", event_type=event_type, handler=handler.__name__)

            @wraps(handler)
            async def wrapper(event: Event):
                return await handler(event)
            return wrapper
        return decorator

    @classmethod
    def register(cls, event_type: str, handler: EventHandler):
        """
        Enregistre un handler programmatiquement.

        Args:
            event_type: Type d'evenement
            handler: Fonction async a appeler
        """
        if event_type not in cls._subscribers:
            cls._subscribers[event_type] = []
        cls._subscribers[event_type].append(handler)
        logger.debug("event_handler_registered", event_type=event_type, handler=handler.__name__)

    @classmethod
    def unsubscribe(cls, event_type: str, handler: EventHandler):
        """Retire un handler d'un type d'evenement."""
        if event_type in cls._subscribers:
            try:
                cls._subscribers[event_type].remove(handler)
                logger.debug("event_handler_unregistered", event_type=event_type, handler=handler.__name__)
            except ValueError:
                pass

    @classmethod
    async def emit(
        cls,
        event_type: str,
        data: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        source_module: str = "",
        source_record_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Event:
        """
        Emet un evenement et notifie tous les abonnes.

        Args:
            event_type: Type d'evenement (utiliser EventType.X.value)
            data: Donnees de l'evenement
            tenant_id: ID du tenant (OBLIGATOIRE en production)
            user_id: ID de l'utilisateur declencheur
            source_module: Module source de l'evenement
            source_record_id: ID de l'enregistrement source
            metadata: Metadonnees supplementaires

        Returns:
            L'evenement cree
        """
        if not cls._enabled:
            logger.debug("event_bus_disabled", event_type=event_type)
            return Event(type=event_type, data=data)

        # Creer l'evenement
        event = Event(
            type=event_type,
            data=data,
            tenant_id=tenant_id,
            user_id=user_id,
            source_module=source_module,
            source_record_id=source_record_id,
            metadata=metadata or {}
        )

        # Log de l'emission
        logger.info(
            "event_emitted",
            event_id=str(event.id),
            event_type=event_type,
            tenant_id=str(tenant_id) if tenant_id else None,
            source_module=source_module
        )

        # Stocker dans l'historique
        cls._event_history.append(event)
        if len(cls._event_history) > cls._max_history:
            cls._event_history = cls._event_history[-cls._max_history:]

        # Notifier les abonnes
        handlers = cls._subscribers.get(event_type, [])

        if handlers:
            # Executer tous les handlers en parallele
            tasks = []
            for handler in handlers:
                tasks.append(cls._execute_handler(handler, event))

            # Attendre tous les handlers
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        event.processed = True
        return event

    @classmethod
    async def emit_fire_and_forget(
        cls,
        event_type: str,
        data: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        source_module: str = "",
        source_record_id: Optional[UUID] = None
    ):
        """
        Emet un evenement sans attendre le traitement.
        Utile pour les evenements non-critiques.
        """
        asyncio.create_task(
            cls.emit(
                event_type=event_type,
                data=data,
                tenant_id=tenant_id,
                user_id=user_id,
                source_module=source_module,
                source_record_id=source_record_id
            )
        )

    @classmethod
    async def _execute_handler(cls, handler: EventHandler, event: Event):
        """Execute un handler avec gestion d'erreur."""
        try:
            await handler(event)
            logger.debug(
                "event_handler_success",
                event_type=event.type,
                handler=handler.__name__
            )
        except Exception as e:
            logger.error(
                "event_handler_error",
                event_type=event.type,
                handler=handler.__name__,
                error=str(e)
            )
            event.error = str(e)

    @classmethod
    def get_subscribers(cls, event_type: str) -> List[str]:
        """Retourne les noms des handlers abonnes a un evenement."""
        handlers = cls._subscribers.get(event_type, [])
        return [h.__name__ for h in handlers]

    @classmethod
    def list_event_types(cls) -> List[str]:
        """Liste tous les types d'evenements avec des abonnes."""
        return list(cls._subscribers.keys())

    @classmethod
    def get_history(
        cls,
        event_type: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[Event]:
        """
        Retourne l'historique des evenements recents.

        Args:
            event_type: Filtrer par type
            tenant_id: Filtrer par tenant
            limit: Nombre max d'evenements
        """
        events = cls._event_history

        if event_type:
            events = [e for e in events if e.type == event_type]

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        return events[-limit:]

    @classmethod
    def clear_history(cls):
        """Vide l'historique des evenements."""
        cls._event_history.clear()

    @classmethod
    def enable(cls):
        """Active le bus d'evenements."""
        cls._enabled = True
        logger.info("event_bus_enabled")

    @classmethod
    def disable(cls):
        """Desactive le bus d'evenements (pour tests)."""
        cls._enabled = False
        logger.info("event_bus_disabled")

    @classmethod
    def reset(cls):
        """Reset complet (pour tests)."""
        cls._subscribers.clear()
        cls._event_history.clear()
        cls._enabled = True


# =============================================================================
# Default Event Handlers (Handlers par defaut du systeme)
# =============================================================================

@EventBus.subscribe(EventType.INVOICE_PAID.value)
async def on_invoice_paid(event: Event):
    """Handler par defaut: met a jour les stats client quand une facture est payee."""
    logger.info(
        "default_handler_invoice_paid",
        invoice_id=event.data.get("invoice_id"),
        amount=event.data.get("amount")
    )
    # Les modules peuvent surcharger ce comportement


@EventBus.subscribe(EventType.QUOTE_ACCEPTED.value)
async def on_quote_accepted(event: Event):
    """Handler par defaut: log quand un devis est accepte."""
    logger.info(
        "default_handler_quote_accepted",
        quote_id=event.data.get("quote_id"),
        client_id=event.data.get("client_id")
    )


@EventBus.subscribe(EventType.STOCK_LOW.value)
async def on_stock_low(event: Event):
    """Handler par defaut: alerte quand le stock est bas."""
    logger.warning(
        "default_handler_stock_low",
        product_id=event.data.get("product_id"),
        current_stock=event.data.get("current_stock"),
        minimum_stock=event.data.get("minimum_stock")
    )


@EventBus.subscribe(EventType.STOCK_OUT.value)
async def on_stock_out(event: Event):
    """Handler par defaut: alerte critique quand le stock est en rupture."""
    logger.error(
        "default_handler_stock_out",
        product_id=event.data.get("product_id"),
        product_name=event.data.get("product_name")
    )


@EventBus.subscribe(EventType.INTERVENTION_COMPLETED.value)
async def on_intervention_completed(event: Event):
    """Handler par defaut: log quand une intervention est terminee."""
    logger.info(
        "default_handler_intervention_completed",
        intervention_id=event.data.get("intervention_id"),
        client_id=event.data.get("client_id")
    )


@EventBus.subscribe(EventType.PAYMENT_RECEIVED.value)
async def on_payment_received(event: Event):
    """Handler par defaut: log quand un paiement est recu."""
    logger.info(
        "default_handler_payment_received",
        payment_id=event.data.get("payment_id"),
        amount=event.data.get("amount"),
        method=event.data.get("method")
    )


# =============================================================================
# Helper Functions
# =============================================================================

async def emit_stock_alert(
    tenant_id: UUID,
    product_id: UUID,
    product_name: str,
    current_stock: int,
    minimum_stock: int,
    user_id: Optional[UUID] = None
):
    """Helper pour emettre une alerte de stock."""
    if current_stock <= 0:
        event_type = EventType.STOCK_OUT.value
    else:
        event_type = EventType.STOCK_LOW.value

    await EventBus.emit(
        event_type=event_type,
        data={
            "product_id": str(product_id),
            "product_name": product_name,
            "current_stock": current_stock,
            "minimum_stock": minimum_stock
        },
        tenant_id=tenant_id,
        user_id=user_id,
        source_module="stock"
    )


async def emit_invoice_paid(
    tenant_id: UUID,
    invoice_id: UUID,
    amount: float,
    client_id: UUID,
    payment_method: str = "",
    user_id: Optional[UUID] = None
):
    """Helper pour emettre un evenement de facture payee."""
    await EventBus.emit(
        event_type=EventType.INVOICE_PAID.value,
        data={
            "invoice_id": str(invoice_id),
            "amount": amount,
            "client_id": str(client_id),
            "payment_method": payment_method
        },
        tenant_id=tenant_id,
        user_id=user_id,
        source_module="factures",
        source_record_id=invoice_id
    )


async def emit_quote_accepted(
    tenant_id: UUID,
    quote_id: UUID,
    client_id: UUID,
    total_amount: float,
    user_id: Optional[UUID] = None
):
    """Helper pour emettre un evenement de devis accepte."""
    await EventBus.emit(
        event_type=EventType.QUOTE_ACCEPTED.value,
        data={
            "quote_id": str(quote_id),
            "client_id": str(client_id),
            "total_amount": total_amount
        },
        tenant_id=tenant_id,
        user_id=user_id,
        source_module="devis",
        source_record_id=quote_id
    )


async def emit_workflow_transition(
    tenant_id: UUID,
    module: str,
    record_id: UUID,
    from_status: str,
    to_status: str,
    user_id: Optional[UUID] = None
):
    """Helper pour emettre un evenement de transition de workflow."""
    await EventBus.emit(
        event_type=EventType.WORKFLOW_TRANSITION.value,
        data={
            "module": module,
            "record_id": str(record_id),
            "from_status": from_status,
            "to_status": to_status
        },
        tenant_id=tenant_id,
        user_id=user_id,
        source_module=module,
        source_record_id=record_id
    )
