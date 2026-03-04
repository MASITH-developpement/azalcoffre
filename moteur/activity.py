# =============================================================================
# AZALPLUS - Activity Feed Service
# =============================================================================
"""
Service de journal d'activites en temps reel.
Trace les actions utilisateurs pour le fil d'actualite du dashboard.

Fonctionnalites:
- Log automatique des operations CRUD
- Log des connexions/deconnexions
- Log des actions sur documents (envoi, signature, etc.)
- Isolation multi-tenant stricte
- Support SSE pour temps reel (optionnel)
"""

from datetime import datetime
from typing import Any, Dict, Optional, List, AsyncGenerator
from uuid import UUID, uuid4
from dataclasses import dataclass
from enum import Enum
import structlog
import asyncio
import json

from .db import Database

logger = structlog.get_logger()


class ActivityType(str, Enum):
    """Types d'activites tracables."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    VIEW = "view"
    EXPORT = "export"
    IMPORT = "import"
    SEND = "send"
    SIGN = "sign"
    VALIDATE = "validate"
    REJECT = "reject"
    CANCEL = "cancel"
    OTHER = "other"


@dataclass
class ActivityContext:
    """Contexte d'une activite."""
    tenant_id: UUID
    user_id: Optional[UUID]
    user_email: Optional[str] = None
    user_nom: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# =============================================================================
# Activity descriptions templates
# =============================================================================
ACTIVITY_DESCRIPTIONS = {
    ActivityType.CREATE: "a cree {article} {module_label} \"{record_label}\"",
    ActivityType.UPDATE: "a modifie {article} {module_label} \"{record_label}\"",
    ActivityType.DELETE: "a supprime {article} {module_label} \"{record_label}\"",
    ActivityType.LOGIN: "s'est connecte",
    ActivityType.LOGOUT: "s'est deconnecte",
    ActivityType.VIEW: "a consulte {article} {module_label} \"{record_label}\"",
    ActivityType.EXPORT: "a exporte les {module_label}",
    ActivityType.IMPORT: "a importe des {module_label}",
    ActivityType.SEND: "a envoye {article} {module_label} \"{record_label}\"",
    ActivityType.SIGN: "a signe {article} {module_label} \"{record_label}\"",
    ActivityType.VALIDATE: "a valide {article} {module_label} \"{record_label}\"",
    ActivityType.REJECT: "a refuse {article} {module_label} \"{record_label}\"",
    ActivityType.CANCEL: "a annule {article} {module_label} \"{record_label}\"",
    ActivityType.OTHER: "{description}",
}

# Articles par module (pour description)
MODULE_ARTICLES = {
    "clients": ("le client", "un client"),
    "Clients": ("le client", "un client"),
    "factures": ("la facture", "une facture"),
    "Factures": ("la facture", "une facture"),
    "devis": ("le devis", "un devis"),
    "Devis": ("le devis", "un devis"),
    "produits": ("le produit", "un produit"),
    "Produits": ("le produit", "un produit"),
    "interventions": ("l'intervention", "une intervention"),
    "Interventions": ("l'intervention", "une intervention"),
    "employes": ("l'employe", "un employe"),
    "Employes": ("l'employe", "un employe"),
    "fournisseurs": ("le fournisseur", "un fournisseur"),
    "Fournisseurs": ("le fournisseur", "un fournisseur"),
    "paiements": ("le paiement", "un paiement"),
    "Paiements": ("le paiement", "un paiement"),
    "stock": ("le stock", "un stock"),
    "Stock": ("le stock", "un stock"),
    "conges": ("la demande de conge", "une demande de conge"),
    "Conges": ("la demande de conge", "une demande de conge"),
    "documents": ("le document", "un document"),
    "Documents": ("le document", "un document"),
}


def get_article(module: str, definite: bool = True) -> str:
    """Retourne l'article approprie pour un module."""
    articles = MODULE_ARTICLES.get(module, ("l'enregistrement", "un enregistrement"))
    return articles[0] if definite else articles[1]


def get_module_label(module: str) -> str:
    """Retourne le label lisible d'un module."""
    labels = {
        "clients": "client",
        "Clients": "client",
        "factures": "facture",
        "Factures": "facture",
        "devis": "devis",
        "Devis": "devis",
        "produits": "produit",
        "Produits": "produit",
        "interventions": "intervention",
        "Interventions": "intervention",
        "employes": "employe",
        "Employes": "employe",
        "fournisseurs": "fournisseur",
        "Fournisseurs": "fournisseur",
        "paiements": "paiement",
        "Paiements": "paiement",
        "stock": "article",
        "Stock": "article",
        "conges": "demande",
        "Conges": "demande",
        "documents": "document",
        "Documents": "document",
    }
    return labels.get(module, module)


# =============================================================================
# SSE Connections Manager (pour temps reel)
# =============================================================================
class SSEManager:
    """Gestionnaire de connexions Server-Sent Events."""

    def __init__(self):
        self._connections: Dict[UUID, List[asyncio.Queue]] = {}

    async def subscribe(self, tenant_id: UUID) -> asyncio.Queue:
        """Ajoute un abonne pour un tenant."""
        if tenant_id not in self._connections:
            self._connections[tenant_id] = []

        queue = asyncio.Queue()
        self._connections[tenant_id].append(queue)
        return queue

    async def unsubscribe(self, tenant_id: UUID, queue: asyncio.Queue):
        """Retire un abonne."""
        if tenant_id in self._connections:
            try:
                self._connections[tenant_id].remove(queue)
            except ValueError:
                pass

    async def broadcast(self, tenant_id: UUID, activity: Dict):
        """Diffuse une activite a tous les abonnes d'un tenant."""
        if tenant_id not in self._connections:
            return

        for queue in self._connections[tenant_id]:
            try:
                await queue.put(activity)
            except Exception as e:
                logger.warning("sse_broadcast_error", error=str(e))


# Singleton SSE Manager
sse_manager = SSEManager()


# =============================================================================
# Activity Logger
# =============================================================================
class ActivityLogger:
    """
    Gestionnaire du journal d'activites.

    Trace toutes les actions utilisateurs avec isolation tenant stricte.
    """

    TABLE_NAME = "activites"

    @classmethod
    def log(
        cls,
        activity_type: ActivityType,
        context: ActivityContext,
        module: Optional[str] = None,
        record_id: Optional[UUID] = None,
        record_label: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict]:
        """
        Log une activite.

        Args:
            activity_type: Type d'action (create, update, delete, login, etc.)
            context: Contexte (tenant, user, IP)
            module: Nom du module concerne (optionnel)
            record_id: UUID de l'enregistrement concerne (optionnel)
            record_label: Label lisible de l'enregistrement (optionnel)
            description: Description personnalisee (optionnel)
            metadata: Donnees supplementaires (optionnel)

        Returns:
            L'entree d'activite creee
        """
        try:
            # Generer la description si non fournie
            if not description:
                description = cls._generate_description(
                    activity_type, module, record_label
                )

            activity_entry = {
                "user_id": str(context.user_id) if context.user_id else None,
                "user_email": context.user_email,
                "user_nom": context.user_nom,
                "type": activity_type.value,
                "module": module,
                "record_id": str(record_id) if record_id else None,
                "record_label": record_label,
                "description": description,
                "metadata": metadata or {},
                "ip_address": context.ip_address,
                "user_agent": context.user_agent
            }

            result = Database.insert(
                cls.TABLE_NAME,
                context.tenant_id,
                activity_entry,
                context.user_id
            )

            logger.debug(
                "activity_logged",
                type=activity_type.value,
                module=module,
                tenant_id=str(context.tenant_id)
            )

            # Diffuser en temps reel (async)
            if result:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            sse_manager.broadcast(context.tenant_id, result)
                        )
                except Exception:
                    pass  # SSE optionnel

            return result

        except Exception as e:
            logger.error(
                "activity_log_failed",
                type=activity_type.value,
                module=module,
                error=str(e)
            )
            return None

    @classmethod
    def _generate_description(
        cls,
        activity_type: ActivityType,
        module: Optional[str],
        record_label: Optional[str]
    ) -> str:
        """Genere une description lisible de l'activite."""
        template = ACTIVITY_DESCRIPTIONS.get(activity_type, "{description}")

        # Pour login/logout, description simple
        if activity_type in [ActivityType.LOGIN, ActivityType.LOGOUT]:
            return template

        # Pour les autres, utiliser le template
        return template.format(
            article=get_article(module or "", definite=True),
            module_label=get_module_label(module or ""),
            record_label=record_label or "sans nom",
            description=""
        )

    # =========================================================================
    # Methodes de log specifiques
    # =========================================================================

    @classmethod
    def log_create(
        cls,
        module: str,
        record_id: UUID,
        record_label: str,
        context: ActivityContext,
        metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Log une creation."""
        return cls.log(
            activity_type=ActivityType.CREATE,
            context=context,
            module=module,
            record_id=record_id,
            record_label=record_label,
            metadata=metadata
        )

    @classmethod
    def log_update(
        cls,
        module: str,
        record_id: UUID,
        record_label: str,
        context: ActivityContext,
        changes: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Log une mise a jour."""
        return cls.log(
            activity_type=ActivityType.UPDATE,
            context=context,
            module=module,
            record_id=record_id,
            record_label=record_label,
            metadata={"changes": changes} if changes else None
        )

    @classmethod
    def log_delete(
        cls,
        module: str,
        record_id: UUID,
        record_label: str,
        context: ActivityContext
    ) -> Optional[Dict]:
        """Log une suppression."""
        return cls.log(
            activity_type=ActivityType.DELETE,
            context=context,
            module=module,
            record_id=record_id,
            record_label=record_label
        )

    @classmethod
    def log_login(
        cls,
        context: ActivityContext,
        success: bool = True
    ) -> Optional[Dict]:
        """Log une connexion."""
        return cls.log(
            activity_type=ActivityType.LOGIN,
            context=context,
            metadata={"success": success, "failed": not success}
        )

    @classmethod
    def log_logout(cls, context: ActivityContext) -> Optional[Dict]:
        """Log une deconnexion."""
        return cls.log(
            activity_type=ActivityType.LOGOUT,
            context=context
        )

    @classmethod
    def log_send(
        cls,
        module: str,
        record_id: UUID,
        record_label: str,
        context: ActivityContext,
        recipient: Optional[str] = None
    ) -> Optional[Dict]:
        """Log un envoi de document."""
        return cls.log(
            activity_type=ActivityType.SEND,
            context=context,
            module=module,
            record_id=record_id,
            record_label=record_label,
            metadata={"recipient": recipient} if recipient else None
        )

    @classmethod
    def log_validate(
        cls,
        module: str,
        record_id: UUID,
        record_label: str,
        context: ActivityContext
    ) -> Optional[Dict]:
        """Log une validation."""
        return cls.log(
            activity_type=ActivityType.VALIDATE,
            context=context,
            module=module,
            record_id=record_id,
            record_label=record_label
        )

    # =========================================================================
    # Methodes de consultation
    # =========================================================================

    @classmethod
    def get_recent(
        cls,
        tenant_id: UUID,
        limit: int = 10,
        offset: int = 0,
        user_id: Optional[UUID] = None,
        module: Optional[str] = None,
        activity_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Recupere les activites recentes pour un tenant.

        Args:
            tenant_id: ID du tenant
            limit: Nombre max de resultats
            offset: Decalage pour pagination
            user_id: Filtrer par utilisateur (optionnel)
            module: Filtrer par module (optionnel)
            activity_type: Filtrer par type (optionnel)

        Returns:
            Liste des activites
        """
        filters = {}
        if user_id:
            filters["user_id"] = str(user_id)
        if module:
            filters["module"] = module
        if activity_type:
            filters["type"] = activity_type

        return Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters=filters if filters else None,
            limit=limit,
            offset=offset,
            order_by="created_at DESC"
        )

    @classmethod
    def get_by_module(
        cls,
        tenant_id: UUID,
        module: str,
        limit: int = 50
    ) -> List[Dict]:
        """Recupere les activites pour un module specifique."""
        return Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"module": module},
            limit=limit,
            order_by="created_at DESC"
        )

    @classmethod
    def get_by_record(
        cls,
        tenant_id: UUID,
        record_id: UUID
    ) -> List[Dict]:
        """Recupere l'historique d'activites d'un enregistrement specifique."""
        return Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"record_id": str(record_id)},
            order_by="created_at DESC"
        )

    @classmethod
    def get_by_user(
        cls,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 50
    ) -> List[Dict]:
        """Recupere les activites d'un utilisateur specifique."""
        return Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"user_id": str(user_id)},
            limit=limit,
            order_by="created_at DESC"
        )

    @classmethod
    def count(
        cls,
        tenant_id: UUID,
        module: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> int:
        """Compte les activites."""
        filters = {}
        if module:
            filters["module"] = module
        if user_id:
            filters["user_id"] = str(user_id)

        # Utiliser une requete count
        items = Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters=filters if filters else None,
            limit=10000
        )
        return len(items)


# =============================================================================
# Helper pour creer un contexte depuis une Request FastAPI
# =============================================================================
def create_activity_context(
    request,
    user: Optional[Dict] = None
) -> ActivityContext:
    """
    Cree un contexte d'activite depuis une requete FastAPI.

    Args:
        request: Requete FastAPI
        user: Utilisateur courant (optionnel)

    Returns:
        ActivityContext
    """
    tenant_id = getattr(request.state, 'tenant_id', None)

    # Si pas de tenant_id dans state, essayer depuis l'utilisateur
    if not tenant_id and user:
        tenant_id = user.get('tenant_id')

    # Convertir en UUID si string
    if isinstance(tenant_id, str):
        tenant_id = UUID(tenant_id)

    user_id = None
    user_email = None
    user_nom = None

    if user:
        user_id = user.get('id')
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        user_email = user.get('email')
        user_nom = user.get('nom', '')
        if user.get('prenom'):
            user_nom = f"{user.get('prenom')} {user_nom}".strip()

    return ActivityContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user_email,
        user_nom=user_nom,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
