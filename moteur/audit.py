# =============================================================================
# AZALPLUS - Audit Logger
# =============================================================================
"""
Systeme de journalisation d'audit pour tracer toutes les modifications.
Conforme aux exigences de compliance et de debugging.

Fonctionnalites:
- Log automatique des operations CRUD
- Capture des anciennes/nouvelles valeurs
- Trace IP client et user agent
- Isolation multi-tenant stricte
"""

from datetime import datetime
from typing import Any, Dict, Optional, List
from uuid import UUID, uuid4
from dataclasses import dataclass
from enum import Enum
import structlog

from .db import Database

logger = structlog.get_logger()


class AuditAction(str, Enum):
    """Types d'actions auditables."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class AuditContext:
    """Contexte d'une operation d'audit."""
    tenant_id: UUID
    user_id: Optional[UUID]
    user_email: Optional[str]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogger:
    """
    Gestionnaire d'audit trail.

    Trace toutes les modifications avec isolation tenant stricte.
    Les logs ne peuvent jamais etre modifies ou supprimes.
    """

    TABLE_NAME = "audit_log"

    @classmethod
    def log_create(
        cls,
        module: str,
        record_id: UUID,
        data: Dict[str, Any],
        context: AuditContext
    ) -> Optional[Dict]:
        """
        Log une operation de creation.

        Args:
            module: Nom du module (ex: 'clients', 'factures')
            record_id: UUID de l'enregistrement cree
            data: Donnees de l'enregistrement cree
            context: Contexte d'audit (tenant, user, IP)

        Returns:
            L'entree d'audit creee
        """
        return cls._log(
            module=module,
            action=AuditAction.CREATE,
            record_id=record_id,
            changes={"new": cls._sanitize_data(data)},
            context=context
        )

    @classmethod
    def log_update(
        cls,
        module: str,
        record_id: UUID,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        context: AuditContext
    ) -> Optional[Dict]:
        """
        Log une operation de mise a jour.

        Args:
            module: Nom du module
            record_id: UUID de l'enregistrement modifie
            old_data: Anciennes valeurs avant modification
            new_data: Nouvelles valeurs apres modification
            context: Contexte d'audit

        Returns:
            L'entree d'audit creee
        """
        # Calculer uniquement les champs modifies
        diff = cls._compute_diff(old_data, new_data)

        if not diff:
            # Pas de modification reelle, pas de log
            return None

        return cls._log(
            module=module,
            action=AuditAction.UPDATE,
            record_id=record_id,
            changes=diff,
            context=context
        )

    @classmethod
    def log_delete(
        cls,
        module: str,
        record_id: UUID,
        context: AuditContext,
        deleted_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict]:
        """
        Log une operation de suppression.

        Args:
            module: Nom du module
            record_id: UUID de l'enregistrement supprime
            context: Contexte d'audit
            deleted_data: Donnees de l'enregistrement supprime (optionnel)

        Returns:
            L'entree d'audit creee
        """
        changes = {}
        if deleted_data:
            changes["deleted"] = cls._sanitize_data(deleted_data)

        return cls._log(
            module=module,
            action=AuditAction.DELETE,
            record_id=record_id,
            changes=changes,
            context=context
        )

    @classmethod
    def _log(
        cls,
        module: str,
        action: AuditAction,
        record_id: UUID,
        changes: Dict[str, Any],
        context: AuditContext
    ) -> Optional[Dict]:
        """
        Ecrit une entree d'audit en base.

        Cette methode ne doit JAMAIS echouer silencieusement.
        En cas d'erreur, on log et on continue (l'operation principale ne doit pas etre bloquee).
        """
        try:
            audit_entry = {
                "module": module,
                "action": action.value,
                "record_id": str(record_id),
                "user_id": str(context.user_id) if context.user_id else None,
                "user_email": context.user_email,
                "changes": changes,
                "ip_address": context.ip_address,
                "user_agent": context.user_agent,
                "timestamp": datetime.utcnow().isoformat()
            }

            result = Database.insert(
                cls.TABLE_NAME,
                context.tenant_id,
                audit_entry,
                context.user_id
            )

            logger.debug(
                "audit_logged",
                module=module,
                action=action.value,
                record_id=str(record_id),
                tenant_id=str(context.tenant_id)
            )

            return result

        except Exception as e:
            # Ne pas bloquer l'operation principale en cas d'erreur d'audit
            # Mais logger l'erreur pour investigation
            logger.error(
                "audit_log_failed",
                module=module,
                action=action.value,
                record_id=str(record_id),
                error=str(e)
            )
            return None

    @classmethod
    def _compute_diff(
        cls,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calcule les differences entre anciennes et nouvelles valeurs.

        Returns:
            Dict avec format {"field": {"old": value, "new": value}}
        """
        diff = {}

        # Champs a ignorer dans le diff (champs systeme)
        ignore_fields = {"id", "tenant_id", "created_at", "updated_at", "created_by", "updated_by", "deleted_at"}

        # Verifier les champs modifies
        all_keys = set(old_data.keys()) | set(new_data.keys())

        for key in all_keys:
            if key in ignore_fields:
                continue

            old_val = old_data.get(key)
            new_val = new_data.get(key)

            # Comparer les valeurs (gerer les None vs valeur vide)
            if cls._values_differ(old_val, new_val):
                diff[key] = {
                    "old": cls._serialize_value(old_val),
                    "new": cls._serialize_value(new_val)
                }

        return diff

    @classmethod
    def _values_differ(cls, old_val: Any, new_val: Any) -> bool:
        """Determine si deux valeurs sont differentes."""
        # Traiter None et chaine vide comme equivalents pour certains cas
        if old_val is None and new_val == "":
            return False
        if old_val == "" and new_val is None:
            return False
        return old_val != new_val

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """Serialise une valeur pour stockage JSON."""
        if value is None:
            return None
        if isinstance(value, (UUID,)):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @classmethod
    def _sanitize_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Nettoie les donnees avant stockage.
        Retire les champs sensibles et serialise les valeurs.
        """
        # Champs sensibles a masquer
        sensitive_fields = {"password", "mot_de_passe", "secret", "token", "api_key"}

        sanitized = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                sanitized[key] = "***MASKED***"
            else:
                sanitized[key] = cls._serialize_value(value)

        return sanitized

    # =========================================================================
    # Methodes de consultation
    # =========================================================================

    @classmethod
    def get_recent(
        cls,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """
        Recupere les logs d'audit recents pour un tenant.

        Args:
            tenant_id: ID du tenant
            limit: Nombre max de resultats
            offset: Decalage pour pagination

        Returns:
            Liste des entrees d'audit
        """
        return Database.query(
            cls.TABLE_NAME,
            tenant_id,
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
        """Recupere les logs d'audit pour un module specifique."""
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
        """Recupere l'historique d'audit d'un enregistrement specifique."""
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
        """Recupere les logs d'audit d'un utilisateur specifique."""
        return Database.query(
            cls.TABLE_NAME,
            tenant_id,
            filters={"user_id": str(user_id)},
            limit=limit,
            order_by="created_at DESC"
        )
