# =============================================================================
# AZALPLUS - Workflow Engine
# =============================================================================
"""
Moteur d'execution des workflows automatiques.
Gere les declencheurs, conditions et actions.

PRINCIPES:
- tenant_id OBLIGATOIRE sur chaque execution
- Audit trail complet
- Execution asynchrone pour ne pas bloquer
- Gestion des erreurs robuste
"""

from typing import Dict, Any, List, Optional, Callable
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import re
import asyncio
import structlog

from .db import Database
from .parser import ModuleParser
from .tenant import TenantContext

logger = structlog.get_logger()


# =============================================================================
# Types et Enums
# =============================================================================
class TriggerType(str, Enum):
    ON_CREATE = "on_create"
    ON_UPDATE = "on_update"
    ON_STATUS_CHANGE = "on_status_change"
    SCHEDULED = "scheduled"


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    UPDATE_FIELD = "update_field"
    CREATE_RECORD = "create_record"
    NOTIFY_USER = "notify_user"
    WEBHOOK = "webhook"


@dataclass
class WorkflowExecution:
    """Resultat d'une execution de workflow."""
    workflow_id: UUID
    workflow_name: str
    tenant_id: UUID
    record_id: UUID
    module: str
    trigger: TriggerType
    success: bool
    actions_executed: int = 0
    actions_failed: int = 0
    error_message: Optional[str] = None
    duration_ms: float = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Workflow Engine
# =============================================================================
class WorkflowEngine:
    """
    Moteur d'execution des workflows.

    Usage:
        # Apres une operation CRUD
        await WorkflowEngine.check_triggers(
            module="Devis",
            event="on_status_change",
            record={"id": "...", "statut": "ACCEPTE", ...},
            old_record={"statut": "ENVOYE", ...},
            tenant_id=tenant_id,
            user_id=user_id
        )
    """

    # Cache des workflows actifs par tenant
    _cache: Dict[str, List[Dict]] = {}
    _cache_ttl: int = 300  # 5 minutes
    _cache_timestamps: Dict[str, datetime] = {}

    # Handlers d'actions personnalises
    _action_handlers: Dict[str, Callable] = {}

    # =============================================================================
    # Initialisation
    # =============================================================================
    @classmethod
    def initialize(cls):
        """Initialise le moteur de workflows."""
        # Enregistrer les handlers d'actions par defaut
        cls.register_action_handler("send_email", cls._action_send_email)
        cls.register_action_handler("update_field", cls._action_update_field)
        cls.register_action_handler("create_record", cls._action_create_record)
        cls.register_action_handler("notify_user", cls._action_notify_user)
        cls.register_action_handler("webhook", cls._action_webhook)

        logger.info("workflow_engine_initialized")

    @classmethod
    def register_action_handler(cls, action_type: str, handler: Callable):
        """Enregistre un handler pour un type d'action."""
        cls._action_handlers[action_type] = handler
        logger.debug("action_handler_registered", action_type=action_type)

    # =============================================================================
    # Verification des declencheurs
    # =============================================================================
    @classmethod
    async def check_triggers(
        cls,
        module: str,
        event: str,
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        old_record: Optional[Dict[str, Any]] = None
    ) -> List[WorkflowExecution]:
        """
        Verifie si des workflows doivent etre declenches.

        Args:
            module: Nom du module (ex: "Devis")
            event: Type d'evenement ("on_create", "on_update", "on_status_change")
            record: Donnees de l'enregistrement
            tenant_id: ID du tenant (OBLIGATOIRE)
            user_id: ID de l'utilisateur executant
            old_record: Anciennes donnees (pour on_update)

        Returns:
            Liste des executions de workflow
        """
        if not tenant_id:
            logger.error("workflow_check_no_tenant")
            return []

        executions = []

        # Recuperer les workflows actifs pour ce tenant et module
        workflows = await cls._get_active_workflows(tenant_id, module)

        for workflow in workflows:
            # Verifier si le declencheur correspond
            if workflow.get("declencheur") != event:
                continue

            # Pour on_status_change, verifier que le statut a change
            if event == "on_status_change":
                if old_record is None:
                    continue
                old_status = old_record.get("statut")
                new_status = record.get("statut")
                if old_status == new_status:
                    continue

            # Evaluer les conditions
            conditions = workflow.get("conditions", {})
            if not cls._evaluate_conditions(conditions, record, old_record):
                continue

            # Executer le workflow
            execution = await cls.execute_workflow(
                workflow=workflow,
                record=record,
                tenant_id=tenant_id,
                user_id=user_id,
                old_record=old_record
            )
            executions.append(execution)

        return executions

    # =============================================================================
    # Execution des workflows
    # =============================================================================
    @classmethod
    async def execute_workflow(
        cls,
        workflow: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        old_record: Optional[Dict[str, Any]] = None
    ) -> WorkflowExecution:
        """
        Execute un workflow complet.

        Args:
            workflow: Definition du workflow
            record: Donnees de l'enregistrement declencheur
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur
            old_record: Anciennes donnees

        Returns:
            Resultat de l'execution
        """
        start_time = datetime.utcnow()

        workflow_id = UUID(str(workflow.get("id"))) if workflow.get("id") else uuid4()
        workflow_name = workflow.get("nom", "Sans nom")
        module = workflow.get("module", "inconnu")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            tenant_id=tenant_id,
            record_id=UUID(str(record.get("id"))) if record.get("id") else uuid4(),
            module=module,
            trigger=TriggerType(workflow.get("declencheur", "on_update")),
            success=True
        )

        logger.info(
            "workflow_executing",
            workflow_name=workflow_name,
            module=module,
            tenant_id=str(tenant_id),
            record_id=str(record.get("id"))
        )

        try:
            # Executer les actions
            actions = workflow.get("actions", [])

            for action in actions:
                action_success = await cls._execute_action(
                    action=action,
                    record=record,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    workflow_name=workflow_name
                )

                if action_success:
                    execution.actions_executed += 1
                else:
                    execution.actions_failed += 1

            # Determiner le succes global
            if execution.actions_failed > 0:
                execution.success = False

        except Exception as e:
            execution.success = False
            execution.error_message = str(e)
            logger.error(
                "workflow_execution_error",
                workflow_name=workflow_name,
                error=str(e)
            )

        # Calculer la duree
        end_time = datetime.utcnow()
        execution.duration_ms = (end_time - start_time).total_seconds() * 1000

        # Sauvegarder l'execution dans l'historique
        await cls._save_execution(execution, tenant_id)

        # Mettre a jour les statistiques du workflow
        await cls._update_workflow_stats(workflow_id, tenant_id, execution.success)

        logger.info(
            "workflow_executed",
            workflow_name=workflow_name,
            success=execution.success,
            actions_executed=execution.actions_executed,
            actions_failed=execution.actions_failed,
            duration_ms=execution.duration_ms
        )

        return execution

    # =============================================================================
    # Execution des actions
    # =============================================================================
    @classmethod
    async def _execute_action(
        cls,
        action: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID],
        workflow_name: str
    ) -> bool:
        """Execute une action de workflow."""

        action_type = action.get("type")
        if not action_type:
            logger.warning("workflow_action_no_type", workflow=workflow_name)
            return False

        handler = cls._action_handlers.get(action_type)
        if not handler:
            logger.warning(
                "workflow_action_unknown",
                action_type=action_type,
                workflow=workflow_name
            )
            return False

        try:
            # Resoudre les templates dans l'action
            resolved_action = cls._resolve_templates(action, record)

            # Executer le handler
            result = await handler(
                action=resolved_action,
                record=record,
                tenant_id=tenant_id,
                user_id=user_id
            )

            logger.debug(
                "workflow_action_executed",
                action_type=action_type,
                workflow=workflow_name,
                success=result
            )

            return result

        except Exception as e:
            logger.error(
                "workflow_action_error",
                action_type=action_type,
                workflow=workflow_name,
                error=str(e)
            )
            return False

    # =============================================================================
    # Handlers d'actions
    # =============================================================================
    @classmethod
    async def _action_send_email(
        cls,
        action: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID]
    ) -> bool:
        """Envoie un email."""

        to = action.get("to")
        subject = action.get("subject")
        template = action.get("template")
        delay_hours = action.get("delay_hours", 0)

        if not to or not subject:
            logger.warning("send_email_missing_params", to=to, subject=subject)
            return False

        # TODO: Implementer l'envoi d'email reel
        # Pour l'instant, on simule
        logger.info(
            "email_sent",
            to=to,
            subject=subject,
            template=template,
            delay_hours=delay_hours,
            tenant_id=str(tenant_id)
        )

        # Enregistrer dans l'historique des emails
        # Database.insert("workflow_emails", tenant_id, {...})

        return True

    @classmethod
    async def _action_update_field(
        cls,
        action: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID]
    ) -> bool:
        """Met a jour un champ de l'enregistrement."""

        field_name = action.get("field")
        value = action.get("value")
        operation = action.get("operation")

        if not field_name:
            return False

        # Construire les donnees de mise a jour
        update_data = {}

        if operation == "increment":
            current_value = record.get(field_name, 0)
            update_data[field_name] = current_value + 1
        elif operation == "set":
            update_data[field_name] = value
        else:
            update_data[field_name] = value

        # Determiner le module
        module = record.get("_module") or action.get("module")
        if not module:
            logger.warning("update_field_no_module")
            return False

        record_id = record.get("id")
        if not record_id:
            return False

        try:
            Database.update(
                table_name=module,
                tenant_id=tenant_id,
                record_id=UUID(str(record_id)),
                data=update_data,
                user_id=user_id
            )
            return True
        except Exception as e:
            logger.error("update_field_error", error=str(e))
            return False

    @classmethod
    async def _action_create_record(
        cls,
        action: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID]
    ) -> bool:
        """Cree un nouvel enregistrement."""

        target_module = action.get("module")
        if not target_module:
            logger.warning("create_record_no_module")
            return False

        # Construire les donnees depuis le mapping
        mapping = action.get("mapping", {})
        data = action.get("data", {})

        # Fusionner mapping et data
        new_record_data = {}

        for key, value in mapping.items():
            resolved = cls._resolve_template_value(value, record)
            new_record_data[key] = resolved

        for key, value in data.items():
            resolved = cls._resolve_template_value(value, record)
            new_record_data[key] = resolved

        try:
            new_record = Database.insert(
                table_name=target_module,
                tenant_id=tenant_id,
                data=new_record_data,
                user_id=user_id
            )

            logger.info(
                "record_created_by_workflow",
                module=target_module,
                record_id=str(new_record.get("id")),
                tenant_id=str(tenant_id)
            )

            return True

        except Exception as e:
            logger.error("create_record_error", module=target_module, error=str(e))
            return False

    @classmethod
    async def _action_notify_user(
        cls,
        action: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID]
    ) -> bool:
        """Envoie une notification a l'utilisateur."""

        message = action.get("message")
        if not message:
            return False

        # TODO: Implementer le systeme de notifications
        logger.info(
            "notification_sent",
            message=message,
            user_id=str(user_id) if user_id else None,
            tenant_id=str(tenant_id)
        )

        return True

    @classmethod
    async def _action_webhook(
        cls,
        action: Dict[str, Any],
        record: Dict[str, Any],
        tenant_id: UUID,
        user_id: Optional[UUID]
    ) -> bool:
        """Appelle un webhook externe."""

        url = action.get("url")
        method = action.get("method", "POST")
        headers = action.get("headers", {})
        payload = action.get("payload", record)

        if not url:
            return False

        # TODO: Implementer l'appel HTTP
        logger.info(
            "webhook_called",
            url=url,
            method=method,
            tenant_id=str(tenant_id)
        )

        return True

    # =============================================================================
    # Evaluation des conditions
    # =============================================================================
    @classmethod
    def _evaluate_conditions(
        cls,
        conditions: Dict[str, Any],
        record: Dict[str, Any],
        old_record: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Evalue les conditions du workflow.

        Supporte:
        - Egalite simple: {"statut": "ACCEPTE"}
        - Operateurs: {"montant": {"$gte": 1000}}
        - Variables: {"statut": "{{new_status}}"}
        """
        if not conditions:
            return True

        for field, expected in conditions.items():
            actual = record.get(field)

            # Condition avec operateur
            if isinstance(expected, dict):
                if not cls._evaluate_operator(actual, expected):
                    return False
            # Egalite simple
            else:
                # Resoudre les templates
                expected_resolved = cls._resolve_template_value(expected, record)
                if actual != expected_resolved:
                    return False

        return True

    @classmethod
    def _evaluate_operator(cls, actual: Any, condition: Dict[str, Any]) -> bool:
        """Evalue une condition avec operateur."""

        for op, expected in condition.items():
            if op == "$eq":
                if actual != expected:
                    return False
            elif op == "$ne":
                if actual == expected:
                    return False
            elif op == "$gt":
                if actual is None or actual <= expected:
                    return False
            elif op == "$gte":
                if actual is None or actual < expected:
                    return False
            elif op == "$lt":
                if actual is None or actual >= expected:
                    return False
            elif op == "$lte":
                if actual is None or actual > expected:
                    return False
            elif op == "$in":
                if actual not in expected:
                    return False
            elif op == "$nin":
                if actual in expected:
                    return False
            elif op == "$exists":
                if (actual is not None) != expected:
                    return False

        return True

    # =============================================================================
    # Resolution de templates
    # =============================================================================
    @classmethod
    def _resolve_templates(cls, obj: Any, record: Dict[str, Any]) -> Any:
        """Resout tous les templates dans un objet."""

        if isinstance(obj, str):
            return cls._resolve_template_value(obj, record)
        elif isinstance(obj, dict):
            return {k: cls._resolve_templates(v, record) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._resolve_templates(item, record) for item in obj]
        else:
            return obj

    @classmethod
    def _resolve_template_value(cls, value: Any, record: Dict[str, Any]) -> Any:
        """Resout une valeur template {{field}}."""

        if not isinstance(value, str):
            return value

        # Pattern: {{field}} ou {{field.subfield}}
        pattern = r'\{\{([^}]+)\}\}'

        def replacer(match):
            field_path = match.group(1).strip()

            # Gerer les chemins imbriques (ex: client.email)
            parts = field_path.split(".")
            current = record

            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return match.group(0)  # Garder le template si non resolu

            if current is None:
                return ""
            return str(current)

        result = re.sub(pattern, replacer, value)
        return result

    # =============================================================================
    # Cache et persistance
    # =============================================================================
    @classmethod
    async def _get_active_workflows(
        cls,
        tenant_id: UUID,
        module: str
    ) -> List[Dict[str, Any]]:
        """Recupere les workflows actifs pour un tenant et module."""

        cache_key = f"{tenant_id}:{module}"

        # Verifier le cache
        if cache_key in cls._cache:
            timestamp = cls._cache_timestamps.get(cache_key)
            if timestamp and (datetime.utcnow() - timestamp).seconds < cls._cache_ttl:
                return cls._cache[cache_key]

        # Charger depuis la base
        try:
            workflows = Database.query(
                table_name="Workflows",
                tenant_id=tenant_id,
                filters={"module": module, "actif": True}
            )
        except Exception:
            workflows = []

        # Mettre en cache
        cls._cache[cache_key] = workflows
        cls._cache_timestamps[cache_key] = datetime.utcnow()

        return workflows

    @classmethod
    def invalidate_cache(cls, tenant_id: UUID, module: Optional[str] = None):
        """Invalide le cache des workflows."""

        if module:
            cache_key = f"{tenant_id}:{module}"
            cls._cache.pop(cache_key, None)
            cls._cache_timestamps.pop(cache_key, None)
        else:
            # Invalider tous les caches du tenant
            keys_to_remove = [k for k in cls._cache.keys() if k.startswith(str(tenant_id))]
            for key in keys_to_remove:
                cls._cache.pop(key, None)
                cls._cache_timestamps.pop(key, None)

    @classmethod
    async def _save_execution(cls, execution: WorkflowExecution, tenant_id: UUID):
        """Sauvegarde l'execution dans l'historique."""

        try:
            Database.insert(
                table_name="workflow_executions",
                tenant_id=tenant_id,
                data={
                    "workflow_id": str(execution.workflow_id),
                    "workflow_name": execution.workflow_name,
                    "record_id": str(execution.record_id),
                    "module": execution.module,
                    "trigger": execution.trigger.value,
                    "success": execution.success,
                    "actions_executed": execution.actions_executed,
                    "actions_failed": execution.actions_failed,
                    "error_message": execution.error_message,
                    "duration_ms": execution.duration_ms,
                    "details": json.dumps(execution.details)
                }
            )
        except Exception as e:
            # Log mais ne pas bloquer
            logger.warning("workflow_execution_save_error", error=str(e))

    @classmethod
    async def _update_workflow_stats(
        cls,
        workflow_id: UUID,
        tenant_id: UUID,
        success: bool
    ):
        """Met a jour les statistiques du workflow."""

        try:
            workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
            if workflow:
                update_data = {
                    "executions_total": (workflow.get("executions_total") or 0) + 1,
                    "derniere_execution": datetime.utcnow().isoformat()
                }

                if success:
                    update_data["executions_succes"] = (workflow.get("executions_succes") or 0) + 1
                else:
                    update_data["executions_echec"] = (workflow.get("executions_echec") or 0) + 1

                Database.update("Workflows", tenant_id, workflow_id, update_data)
        except Exception as e:
            logger.warning("workflow_stats_update_error", error=str(e))

    # =============================================================================
    # Execution planifiee (scheduled)
    # =============================================================================
    @classmethod
    async def run_scheduled_workflows(cls, tenant_id: UUID):
        """
        Execute les workflows planifies pour un tenant.
        A appeler periodiquement (ex: toutes les minutes).
        """

        try:
            # Recuperer tous les workflows scheduled actifs
            workflows = Database.query(
                table_name="Workflows",
                tenant_id=tenant_id,
                filters={"declencheur": "scheduled", "actif": True}
            )

            for workflow in workflows:
                # TODO: Verifier si le cron_expression correspond au moment actuel
                # Pour l'instant, on execute tous les scheduled a chaque appel

                # Recuperer les enregistrements correspondant aux conditions
                target_module = workflow.get("module")
                conditions = workflow.get("conditions", {})

                # Convertir les conditions pour la requete
                filters = {}
                for field, value in conditions.items():
                    if not isinstance(value, dict):
                        filters[field] = value

                records = Database.query(
                    table_name=target_module,
                    tenant_id=tenant_id,
                    filters=filters if filters else None,
                    limit=100  # Limiter pour eviter les surcharges
                )

                for record in records:
                    await cls.execute_workflow(
                        workflow=workflow,
                        record=record,
                        tenant_id=tenant_id
                    )

        except Exception as e:
            logger.error("scheduled_workflows_error", tenant_id=str(tenant_id), error=str(e))

    # =============================================================================
    # Helpers publics
    # =============================================================================
    @classmethod
    async def test_workflow(
        cls,
        workflow_id: UUID,
        tenant_id: UUID,
        test_data: Dict[str, Any]
    ) -> WorkflowExecution:
        """
        Teste un workflow avec des donnees de test.
        N'execute pas vraiment les actions, simule seulement.
        """

        workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
        if not workflow:
            raise ValueError("Workflow non trouve")

        # Mode test: on log mais on n'execute pas vraiment
        logger.info("workflow_test_mode", workflow_name=workflow.get("nom"))

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_name=workflow.get("nom", "Test"),
            tenant_id=tenant_id,
            record_id=uuid4(),
            module=workflow.get("module", "test"),
            trigger=TriggerType(workflow.get("declencheur", "on_update")),
            success=True
        )

        # Evaluer les conditions
        conditions = workflow.get("conditions", {})
        conditions_match = cls._evaluate_conditions(conditions, test_data)

        execution.details["conditions_match"] = conditions_match
        execution.details["conditions"] = conditions
        execution.details["test_data"] = test_data

        if conditions_match:
            execution.details["message"] = "Les conditions sont satisfaites, le workflow serait execute"
            execution.actions_executed = len(workflow.get("actions", []))
        else:
            execution.details["message"] = "Les conditions ne sont pas satisfaites"
            execution.success = False

        return execution

    @classmethod
    def get_available_triggers(cls) -> List[Dict[str, str]]:
        """Retourne la liste des declencheurs disponibles."""
        return [
            {"value": "on_create", "label": "A la creation"},
            {"value": "on_update", "label": "A la modification"},
            {"value": "on_status_change", "label": "Au changement de statut"},
            {"value": "scheduled", "label": "Planifie (cron)"}
        ]

    @classmethod
    def get_available_actions(cls) -> List[Dict[str, str]]:
        """Retourne la liste des actions disponibles."""
        return [
            {"value": "send_email", "label": "Envoyer un email"},
            {"value": "create_record", "label": "Creer un enregistrement"},
            {"value": "update_field", "label": "Modifier un champ"},
            {"value": "notify_user", "label": "Notifier l'utilisateur"},
            {"value": "webhook", "label": "Appeler un webhook"}
        ]
