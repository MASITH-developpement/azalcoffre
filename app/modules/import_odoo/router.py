# =============================================================================
# AZALPLUS - Router Import/Export Odoo
# =============================================================================
"""
API REST pour import/export Odoo avec endpoints séparés par module:
- /api/odoo/clients - Import clients (res.partner)
- /api/odoo/fournisseurs - Import fournisseurs
- /api/odoo/produits - Import produits
- /api/odoo/factures - Import factures
- /api/odoo/commandes - Import commandes
- etc.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
import structlog


def ensure_uuid(value: Union[str, UUID]) -> UUID:
    """Convertit une valeur en UUID si nécessaire."""
    if isinstance(value, UUID):
        return value
    return UUID(str(value))

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from pydantic import BaseModel, Field

from moteur.auth import get_current_user
from moteur.tenant import TenantContext
from moteur.db import Database

from .service import (
    OdooAPIClient,
    OdooImportService,
    OdooExportService,
    get_supported_odoo_models,
    get_field_mapping,
    test_odoo_connection,
    ODOO_MODEL_MAPPING,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/odoo", tags=["Import/Export Odoo"])


# =============================================================================
# SCHEMAS
# =============================================================================

class OdooConnectionConfig(BaseModel):
    """Configuration de connexion Odoo."""
    url: str = Field(..., description="URL Odoo (ex: https://monodoo.com)")
    db: str = Field(..., description="Nom de la base Odoo")
    username: str = Field(..., description="Login Odoo")
    password: str = Field(..., description="Mot de passe ou clé API")


class OdooImportOptions(BaseModel):
    """Options d'import."""
    update_existing: bool = Field(False, description="Mettre à jour si existant")
    ignore_errors: bool = Field(True, description="Continuer en cas d'erreur")
    limit: Optional[int] = Field(None, description="Limite d'enregistrements")
    domain: Optional[str] = Field(None, description="Filtre domaine Odoo")
    date_from: Optional[str] = Field(None, description="Date début (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Date fin (YYYY-MM-DD)")


class ImportResult(BaseModel):
    """Résultat d'import."""
    success: bool
    module: str
    odoo_model: str
    stats: Dict[str, int]
    errors: List[Dict] = []
    imported_ids: List[str] = []
    duration_seconds: float = 0


class OdooTestResult(BaseModel):
    """Résultat de test connexion."""
    success: bool
    version: Optional[Dict] = None
    error: Optional[str] = None


class OdooImportRequest(BaseModel):
    """Request body pour import API Odoo."""
    config: OdooConnectionConfig
    options: Optional[OdooImportOptions] = None


# =============================================================================
# ENDPOINTS GÉNÉRAUX
# =============================================================================

@router.get("/models")
async def list_supported_models(
    user: dict = Depends(get_current_user)
) -> List[Dict]:
    """Liste les modèles Odoo supportés."""
    return get_supported_odoo_models()


@router.get("/mapping/{odoo_model}")
async def get_model_mapping(
    odoo_model: str,
    user: dict = Depends(get_current_user)
) -> Dict:
    """Retourne le mapping des champs pour un modèle Odoo."""
    mapping = get_field_mapping(odoo_model)
    if not mapping:
        raise HTTPException(404, f"Modèle non supporté: {odoo_model}")
    return {
        "odoo_model": odoo_model,
        "azalplus_module": ODOO_MODEL_MAPPING.get(odoo_model, {}).get("module"),
        "fields": mapping
    }


@router.post("/test-connection")
async def test_connection(
    config: OdooConnectionConfig,
    user: dict = Depends(get_current_user)
) -> OdooTestResult:
    """Teste la connexion à une instance Odoo."""
    result = test_odoo_connection(
        config.url,
        config.db,
        config.username,
        config.password
    )
    return OdooTestResult(**result)


@router.post("/available-models")
async def list_available_models(
    config: OdooConnectionConfig,
    search: str = Query("", description="Filtrer par nom (ex: 'maintenance', 'helpdesk', 'project')"),
    user: dict = Depends(get_current_user)
) -> Dict:
    """
    Liste les modèles disponibles dans l'instance Odoo.

    Utile pour trouver le bon modèle pour les interventions:
    - maintenance.request (Odoo Maintenance)
    - helpdesk.ticket (Odoo Helpdesk)
    - project.task (Odoo Project)
    - repair.order (Odoo Repair)
    - field.service.task (Odoo Field Service)
    """
    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    try:
        # Rechercher les modèles dans ir.model
        domain = [('transient', '=', False)]  # Exclure les modèles temporaires
        if search:
            domain.append(('model', 'ilike', search))

        models = client.search_read(
            'ir.model',
            domain=domain,
            fields=['model', 'name', 'info'],
            limit=100,
            order='model'
        )

        # Filtrer les modèles intéressants pour l'import
        intervention_keywords = ['maintenance', 'helpdesk', 'ticket', 'repair', 'field', 'service', 'task', 'project', 'intervention']

        relevant_models = []
        other_models = []

        for m in models:
            model_info = {
                'model': m.get('model'),
                'name': m.get('name'),
                'description': m.get('info') or ''
            }

            # Vérifier si c'est un modèle pertinent pour les interventions
            model_lower = m.get('model', '').lower()
            if any(kw in model_lower for kw in intervention_keywords):
                relevant_models.append(model_info)
            else:
                other_models.append(model_info)

        return {
            "success": True,
            "total": len(models),
            "intervention_models": relevant_models,
            "other_models": other_models[:50] if not search else other_models
        }

    except Exception as e:
        raise HTTPException(500, f"Erreur lors de la récupération des modèles: {str(e)}")


# =============================================================================
# IMPORT CLIENTS (res.partner)
# =============================================================================

@router.post("/clients/csv", response_model=ImportResult)
async def import_clients_csv(
    file: UploadFile = File(..., description="Fichier CSV exporté d'Odoo"),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """
    Import clients depuis CSV Odoo (res.partner).

    Le fichier doit être exporté depuis Odoo avec les colonnes:
    id, name, street, city, zip, country_id, phone, email, vat, etc.
    """
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="res.partner",
        module_cible="clients",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    logger.info(
        "odoo_import_clients_csv",
        tenant_id=str(tenant_id),
        imported=result["stats"]["imported"],
        errors=result["stats"]["errors"]
    )

    return ImportResult(
        success=result["success"],
        module="clients",
        odoo_model="res.partner",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/clients/api", response_model=ImportResult)
async def import_clients_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """
    Import clients depuis API Odoo (res.partner).

    Récupère directement les contacts depuis l'API XML-RPC.
    """
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    # Connexion Odoo
    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    # Construire le domaine
    domain = []
    if options.domain:
        try:
            domain = eval(options.domain)  # Attention: sécuriser en prod
        except:
            pass

    # Ajouter filtres date
    if options.date_from:
        domain.append(('create_date', '>=', options.date_from))
    if options.date_to:
        domain.append(('create_date', '<=', options.date_to))

    # Filtrer les clients (pas fournisseurs uniquement)
    domain.append(('customer_rank', '>', 0))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="res.partner",
        module_cible="clients",
        domain=domain,
        limit=options.limit,
        options={"update_existing": options.update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="clients",
        odoo_model="res.partner",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT FOURNISSEURS (res.partner)
# =============================================================================

@router.post("/fournisseurs/csv", response_model=ImportResult)
async def import_fournisseurs_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import fournisseurs depuis CSV Odoo (res.partner avec supplier_rank)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="res.partner",
        module_cible="fournisseurs",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="fournisseurs",
        odoo_model="res.partner",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/fournisseurs/api", response_model=ImportResult)
async def import_fournisseurs_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import fournisseurs depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    domain = [('supplier_rank', '>', 0)]
    if options.date_from:
        domain.append(('create_date', '>=', options.date_from))
    if options.date_to:
        domain.append(('create_date', '<=', options.date_to))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="res.partner",
        module_cible="fournisseurs",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="fournisseurs",
        odoo_model="res.partner",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT PRODUITS (product.product / product.template)
# =============================================================================

@router.post("/produits/csv", response_model=ImportResult)
async def import_produits_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import produits depuis CSV Odoo (product.product)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="product.product",
        module_cible="produits",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="produits",
        odoo_model="product.product",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/produits/api", response_model=ImportResult)
async def import_produits_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import produits depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    domain = [('active', '=', True)]
    if options.date_from:
        domain.append(('create_date', '>=', options.date_from))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="product.product",
        module_cible="produits",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="produits",
        odoo_model="product.product",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT FACTURES (account.move)
# =============================================================================

@router.post("/factures/csv", response_model=ImportResult)
async def import_factures_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import factures depuis CSV Odoo (account.move)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="account.move",
        module_cible="factures",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="factures",
        odoo_model="account.move",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/factures/api", response_model=ImportResult)
async def import_factures_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import factures depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    # Filtrer les factures clients
    domain = [('move_type', 'in', ['out_invoice', 'out_refund'])]
    if options.date_from:
        domain.append(('invoice_date', '>=', options.date_from))
    if options.date_to:
        domain.append(('invoice_date', '<=', options.date_to))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="account.move",
        module_cible="factures",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="factures",
        odoo_model="account.move",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT COMMANDES VENTE (sale.order)
# =============================================================================

@router.post("/commandes/csv", response_model=ImportResult)
async def import_commandes_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import commandes vente depuis CSV Odoo (sale.order)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="sale.order",
        module_cible="commandes",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="commandes",
        odoo_model="sale.order",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/commandes/api", response_model=ImportResult)
async def import_commandes_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import commandes vente depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    domain = []
    if options.date_from:
        domain.append(('date_order', '>=', options.date_from))
    if options.date_to:
        domain.append(('date_order', '<=', options.date_to))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="sale.order",
        module_cible="commandes",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="commandes",
        odoo_model="sale.order",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT COMMANDES ACHAT (purchase.order)
# =============================================================================

@router.post("/commandes-achat/csv", response_model=ImportResult)
async def import_commandes_achat_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import commandes achat depuis CSV Odoo (purchase.order)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="purchase.order",
        module_cible="commandes_achat",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="commandes_achat",
        odoo_model="purchase.order",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/commandes-achat/api", response_model=ImportResult)
async def import_commandes_achat_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import commandes achat depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    domain = []
    if options.date_from:
        domain.append(('date_order', '>=', options.date_from))
    if options.date_to:
        domain.append(('date_order', '<=', options.date_to))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="purchase.order",
        module_cible="commandes_achat",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="commandes_achat",
        odoo_model="purchase.order",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT EMPLOYES (hr.employee)
# =============================================================================

@router.post("/employes/csv", response_model=ImportResult)
async def import_employes_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import employés depuis CSV Odoo (hr.employee)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="hr.employee",
        module_cible="employes",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="employes",
        odoo_model="hr.employee",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/employes/api", response_model=ImportResult)
async def import_employes_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import employés depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    domain = [('active', '=', True)]

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="hr.employee",
        module_cible="employes",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="employes",
        odoo_model="hr.employee",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT PROJETS (project.project)
# =============================================================================

@router.post("/projets/csv", response_model=ImportResult)
async def import_projets_csv(
    file: UploadFile = File(...),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """Import projets depuis CSV Odoo (project.project)."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model="project.project",
        module_cible="projets",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="projets",
        odoo_model="project.project",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/projets/api", response_model=ImportResult)
async def import_projets_api(
    request: OdooImportRequest,
    user: dict = Depends(get_current_user)
):
    """Import projets depuis API Odoo."""
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    domain = [('active', '=', True)]

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model="project.project",
        module_cible="projets",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    return ImportResult(
        success=result["success"],
        module="projets",
        odoo_model="project.project",
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT INTERVENTIONS (maintenance.request, helpdesk.ticket, field.service, repair.order)
# =============================================================================

@router.post("/interventions/csv", response_model=ImportResult)
async def import_interventions_csv(
    file: UploadFile = File(...),
    odoo_model: str = Form("maintenance.request", description="Modèle Odoo: maintenance.request, helpdesk.ticket, field.service, repair.order"),
    update_existing: bool = Form(False),
    user: dict = Depends(get_current_user)
):
    """
    Import interventions depuis CSV Odoo.

    Modèles supportés:
    - maintenance.request: Demandes de maintenance
    - helpdesk.ticket: Tickets SAV/support
    - field.service: Interventions terrain (Odoo 16+)
    - repair.order: Ordres de réparation
    """
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()

    # Valider le modèle
    valid_models = ["maintenance.request", "helpdesk.ticket", "field.service", "repair.order", "intervention.intervention"]
    if odoo_model not in valid_models:
        raise HTTPException(400, f"Modèle non supporté. Utilisez: {', '.join(valid_models)}")

    content = await file.read()
    csv_content = content.decode('utf-8-sig')

    service = OdooImportService(tenant_id)
    result = service.import_from_csv(
        csv_content,
        odoo_model=odoo_model,
        module_cible="interventions",
        options={"update_existing": update_existing}
    )

    duration = (datetime.now() - start_time).total_seconds()

    logger.info(
        "odoo_import_interventions_csv",
        tenant_id=str(tenant_id),
        odoo_model=odoo_model,
        imported=result["stats"]["imported"],
        errors=result["stats"]["errors"]
    )

    return ImportResult(
        success=result["success"],
        module="interventions",
        odoo_model=odoo_model,
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


@router.post("/interventions/api", response_model=ImportResult)
async def import_interventions_api(
    request: OdooImportRequest,
    odoo_model: str = Query("maintenance.request", description="Modèle Odoo source"),
    user: dict = Depends(get_current_user)
):
    """
    Import interventions depuis API Odoo.

    Modèles supportés:
    - maintenance.request: Demandes de maintenance Odoo
    - helpdesk.ticket: Tickets helpdesk/SAV
    - field.service: Interventions terrain (Field Service)
    - repair.order: Ordres de réparation
    """
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    valid_models = ["maintenance.request", "helpdesk.ticket", "field.service", "repair.order", "intervention.intervention"]
    if odoo_model not in valid_models:
        raise HTTPException(400, f"Modèle non supporté. Utilisez: {', '.join(valid_models)}")

    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    # Construire le domaine selon le modèle
    domain = []
    if odoo_model == "maintenance.request":
        if options.date_from:
            domain.append(('request_date', '>=', options.date_from))
        if options.date_to:
            domain.append(('request_date', '<=', options.date_to))
    elif odoo_model == "helpdesk.ticket":
        if options.date_from:
            domain.append(('create_date', '>=', options.date_from))
        if options.date_to:
            domain.append(('create_date', '<=', options.date_to))
    elif odoo_model == "repair.order":
        if options.date_from:
            domain.append(('create_date', '>=', options.date_from))
        if options.date_to:
            domain.append(('create_date', '<=', options.date_to))
    else:  # field.service
        if options.date_from:
            domain.append(('planned_date_begin', '>=', options.date_from))
        if options.date_to:
            domain.append(('planned_date_begin', '<=', options.date_to))

    service = OdooImportService(tenant_id)
    result = service.import_from_api(
        client,
        odoo_model=odoo_model,
        module_cible="interventions",
        domain=domain,
        limit=options.limit
    )

    duration = (datetime.now() - start_time).total_seconds()

    logger.info(
        "odoo_import_interventions_api",
        tenant_id=str(tenant_id),
        odoo_model=odoo_model,
        imported=result["stats"]["imported"],
        errors=result["stats"]["errors"]
    )

    return ImportResult(
        success=result["success"],
        module="interventions",
        odoo_model=odoo_model,
        stats=result["stats"],
        errors=result.get("errors", []),
        imported_ids=result.get("imported_ids", []),
        duration_seconds=duration
    )


# =============================================================================
# IMPORT COMPLET (Tous les modules)
# =============================================================================

@router.post("/import-complet/api")
async def import_complet_api(
    request: OdooImportRequest,
    modules: List[str] = Query(
        default=["clients", "fournisseurs", "produits", "factures", "commandes"],
        description="Modules à importer"
    ),
    user: dict = Depends(get_current_user)
):
    """
    Import complet depuis Odoo - plusieurs modules à la fois.

    Modules disponibles: clients, fournisseurs, produits, factures,
    commandes, commandes_achat, employes, projets
    """
    tenant_id = ensure_uuid(user["tenant_id"])
    start_time = datetime.now()
    config = request.config
    options = request.options or OdooImportOptions()

    # Connexion Odoo
    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    results = {}
    service = OdooImportService(tenant_id)

    # Mapping module -> (odoo_model, domain_extra)
    module_config = {
        "clients": ("res.partner", [('customer_rank', '>', 0)]),
        "fournisseurs": ("res.partner", [('supplier_rank', '>', 0)]),
        "produits": ("product.product", [('active', '=', True)]),
        "factures": ("account.move", [('move_type', 'in', ['out_invoice', 'out_refund'])]),
        "commandes": ("sale.order", []),
        "commandes_achat": ("purchase.order", []),
        "employes": ("hr.employee", [('active', '=', True)]),
        "projets": ("project.project", [('active', '=', True)]),
        "interventions": ("maintenance.request", []),  # ou helpdesk.ticket, repair.order
    }

    for module in modules:
        if module not in module_config:
            results[module] = {"success": False, "error": "Module non supporté"}
            continue

        odoo_model, domain = module_config[module]

        # Ajouter filtres dates
        if options.date_from:
            domain.append(('create_date', '>=', options.date_from))
        if options.date_to:
            domain.append(('create_date', '<=', options.date_to))

        try:
            result = service.import_from_api(
                client,
                odoo_model=odoo_model,
                module_cible=module,
                domain=domain,
                limit=options.limit
            )
            results[module] = result
        except Exception as e:
            results[module] = {"success": False, "error": str(e)}
            logger.error("odoo_import_module_error", module=module, error=str(e))

    duration = (datetime.now() - start_time).total_seconds()

    return {
        "success": True,
        "modules": results,
        "duration_seconds": duration
    }


# =============================================================================
# EXPORT VERS ODOO
# =============================================================================

@router.post("/export/{module}/csv")
async def export_module_csv(
    module: str,
    limit: int = Query(None, description="Limite d'enregistrements"),
    user: dict = Depends(get_current_user)
):
    """
    Exporte un module AZALPLUS vers CSV format Odoo.

    Le fichier généré peut être importé directement dans Odoo.
    """
    tenant_id = ensure_uuid(user["tenant_id"])

    # Mapping module AZALPLUS -> modèle Odoo
    module_to_odoo = {
        "clients": "res.partner",
        "fournisseurs": "res.partner",
        "produits": "product.product",
        "factures": "account.move",
        "commandes": "sale.order",
        "commandes_achat": "purchase.order",
        "employes": "hr.employee",
        "projets": "project.project",
    }

    odoo_model = module_to_odoo.get(module)
    if not odoo_model:
        raise HTTPException(400, f"Module non supporté pour export: {module}")

    # Récupérer les données
    records = Database.query(module, tenant_id, limit=limit)

    if not records:
        raise HTTPException(404, "Aucun enregistrement à exporter")

    # Exporter
    service = OdooExportService(tenant_id)
    csv_content = service.export_to_csv(module, odoo_model, records)

    from fastapi.responses import Response

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={module}_odoo_export.csv"
        }
    )


@router.post("/export/{module}/api")
async def export_module_api(
    module: str,
    config: OdooConnectionConfig,
    limit: int = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    Exporte un module AZALPLUS vers Odoo via API XML-RPC.

    Crée les enregistrements directement dans l'instance Odoo.
    """
    tenant_id = ensure_uuid(user["tenant_id"])

    module_to_odoo = {
        "clients": "res.partner",
        "fournisseurs": "res.partner",
        "produits": "product.product",
    }

    odoo_model = module_to_odoo.get(module)
    if not odoo_model:
        raise HTTPException(400, f"Module non supporté pour export API: {module}")

    # Connexion
    client = OdooAPIClient(config.url, config.db, config.username, config.password)
    if not client.connect():
        raise HTTPException(401, "Échec connexion Odoo")

    # Récupérer les données
    records = Database.query(module, tenant_id, limit=limit)

    if not records:
        raise HTTPException(404, "Aucun enregistrement à exporter")

    # Exporter
    service = OdooExportService(tenant_id)
    result = service.export_to_api(client, module, odoo_model, records)

    return result
