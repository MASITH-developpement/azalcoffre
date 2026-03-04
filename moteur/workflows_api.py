# =============================================================================
# AZALPLUS - Workflow API Routes
# =============================================================================
"""
Routes API pour la gestion des workflows automatiques.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel
import structlog

from .db import Database
from .parser import ModuleParser
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth
from .workflows import WorkflowEngine

logger = structlog.get_logger()

# =============================================================================
# Router Workflows
# =============================================================================
workflows_router = APIRouter(prefix="/workflows", tags=["Workflows"])


# =============================================================================
# Schemas Pydantic
# =============================================================================
class WorkflowCreate(BaseModel):
    """Schema pour creer un workflow."""
    nom: str
    description: Optional[str] = None
    module: str
    declencheur: str  # on_create, on_update, on_status_change, scheduled
    cron_expression: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = {}
    actions: List[Dict[str, Any]]
    actif: bool = True


class WorkflowUpdate(BaseModel):
    """Schema pour mettre a jour un workflow."""
    nom: Optional[str] = None
    description: Optional[str] = None
    module: Optional[str] = None
    declencheur: Optional[str] = None
    cron_expression: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    actif: Optional[bool] = None


class WorkflowTestRequest(BaseModel):
    """Schema pour tester un workflow."""
    test_data: Dict[str, Any]


# =============================================================================
# Routes de reference
# =============================================================================
@workflows_router.get("/triggers")
async def list_workflow_triggers(user: dict = Depends(require_auth)):
    """Liste les declencheurs disponibles pour les workflows."""
    return {"triggers": WorkflowEngine.get_available_triggers()}


@workflows_router.get("/actions")
async def list_workflow_actions(user: dict = Depends(require_auth)):
    """Liste les actions disponibles pour les workflows."""
    return {"actions": WorkflowEngine.get_available_actions()}


@workflows_router.get("/modules")
async def list_workflow_modules(user: dict = Depends(require_auth)):
    """Liste les modules disponibles pour les workflows."""
    modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module and name not in ["Workflows", "workflow_executions", "audit_log"]:
            modules.append({
                "nom": module.nom,
                "nom_affichage": module.nom_affichage,
                "champs": [
                    {
                        "nom": f.nom,
                        "type": f.type,
                        "label": f.label or f.nom.replace("_", " ").title()
                    }
                    for f in module.champs.values()
                ]
            })
    return {"modules": modules}


# =============================================================================
# Routes CRUD
# =============================================================================
@workflows_router.get("")
async def list_workflows(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    module: Optional[str] = None,
    actif: Optional[bool] = None,
    limit: int = Query(25, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """Liste les workflows du tenant."""
    filters = {}
    if module:
        filters["module"] = module
    if actif is not None:
        filters["actif"] = actif

    try:
        workflows = Database.query(
            table_name="Workflows",
            tenant_id=tenant_id,
            filters=filters if filters else None,
            limit=limit,
            offset=skip,
            order_by="created_at DESC"
        )
        return {"items": workflows, "total": len(workflows)}
    except Exception:
        return {"items": [], "total": 0}


@workflows_router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Recupere un workflow par son ID."""
    workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow non trouve")
    return workflow


@workflows_router.post("", status_code=201)
async def create_workflow(
    data: WorkflowCreate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Cree un nouveau workflow."""
    # Valider le module
    module = ModuleParser.get(data.module)
    if not module:
        raise HTTPException(status_code=400, detail=f"Module {data.module} non trouve")

    # Valider le declencheur
    valid_triggers = ["on_create", "on_update", "on_status_change", "scheduled"]
    if data.declencheur not in valid_triggers:
        raise HTTPException(status_code=400, detail=f"Declencheur invalide: {data.declencheur}")

    # Creer le workflow
    workflow_data = data.model_dump()
    workflow = Database.insert("Workflows", tenant_id, workflow_data, user_id)

    # Invalider le cache
    WorkflowEngine.invalidate_cache(tenant_id, data.module)

    logger.info(
        "workflow_created",
        workflow_id=str(workflow.get("id")),
        nom=data.nom,
        module=data.module,
        tenant_id=str(tenant_id)
    )

    return workflow


@workflows_router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: UUID,
    data: WorkflowUpdate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Met a jour un workflow."""
    existing = Database.get_by_id("Workflows", tenant_id, workflow_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Workflow non trouve")

    # Mettre a jour
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    workflow = Database.update("Workflows", tenant_id, workflow_id, update_data, user_id)

    # Invalider le cache pour l'ancien et le nouveau module
    WorkflowEngine.invalidate_cache(tenant_id, existing.get("module"))
    if data.module and data.module != existing.get("module"):
        WorkflowEngine.invalidate_cache(tenant_id, data.module)

    return workflow


@workflows_router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Supprime un workflow."""
    workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow non trouve")

    success = Database.soft_delete("Workflows", tenant_id, workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow non trouve")

    # Invalider le cache
    WorkflowEngine.invalidate_cache(tenant_id, workflow.get("module"))

    return {"status": "deleted"}


# =============================================================================
# Routes d'actions
# =============================================================================
@workflows_router.post("/{workflow_id}/test")
async def test_workflow(
    workflow_id: UUID,
    request: WorkflowTestRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Teste un workflow avec des donnees de test.
    Simule l'execution sans effectuer les actions reelles.
    """
    try:
        result = await WorkflowEngine.test_workflow(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            test_data=request.test_data
        )
        return {
            "success": result.success,
            "workflow_name": result.workflow_name,
            "conditions_match": result.details.get("conditions_match"),
            "message": result.details.get("message"),
            "actions_count": result.actions_executed
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@workflows_router.post("/{workflow_id}/activate")
async def activate_workflow(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Active un workflow."""
    workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow non trouve")

    Database.update("Workflows", tenant_id, workflow_id, {"actif": True}, user_id)
    WorkflowEngine.invalidate_cache(tenant_id, workflow.get("module"))

    return {"status": "activated", "workflow_id": str(workflow_id)}


@workflows_router.post("/{workflow_id}/deactivate")
async def deactivate_workflow(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Desactive un workflow."""
    workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow non trouve")

    Database.update("Workflows", tenant_id, workflow_id, {"actif": False}, user_id)
    WorkflowEngine.invalidate_cache(tenant_id, workflow.get("module"))

    return {"status": "deactivated", "workflow_id": str(workflow_id)}


@workflows_router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Duplique un workflow existant."""
    workflow = Database.get_by_id("Workflows", tenant_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow non trouve")

    new_workflow_data = {
        "nom": f"{workflow.get('nom', 'Workflow')} (copie)",
        "description": workflow.get("description"),
        "module": workflow.get("module"),
        "declencheur": workflow.get("declencheur"),
        "cron_expression": workflow.get("cron_expression"),
        "conditions": workflow.get("conditions"),
        "actions": workflow.get("actions"),
        "actif": False  # Desactive par defaut
    }

    new_workflow = Database.insert("Workflows", tenant_id, new_workflow_data, user_id)

    return {"status": "duplicated", "new_workflow_id": str(new_workflow.get("id"))}


# =============================================================================
# Routes d'historique
# =============================================================================
@workflows_router.get("/executions/history")
async def list_workflow_executions(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    workflow_id: Optional[UUID] = None,
    success: Optional[bool] = None,
    limit: int = Query(25, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """Liste l'historique des executions de workflows."""
    filters = {}
    if workflow_id:
        filters["workflow_id"] = str(workflow_id)
    if success is not None:
        filters["success"] = success

    try:
        executions = Database.query(
            table_name="workflow_executions",
            tenant_id=tenant_id,
            filters=filters if filters else None,
            limit=limit,
            offset=skip,
            order_by="created_at DESC"
        )
        return {"items": executions, "total": len(executions)}
    except Exception:
        return {"items": [], "total": 0}


@workflows_router.get("/{workflow_id}/executions")
async def get_workflow_executions(
    workflow_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    limit: int = Query(25, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """Liste l'historique des executions d'un workflow specifique."""
    try:
        executions = Database.query(
            table_name="workflow_executions",
            tenant_id=tenant_id,
            filters={"workflow_id": str(workflow_id)},
            limit=limit,
            offset=skip,
            order_by="created_at DESC"
        )
        return {"items": executions, "total": len(executions)}
    except Exception:
        return {"items": [], "total": 0}
