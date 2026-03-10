# =============================================================================
# AZALPLUS - API v1 (Versioned API)
# =============================================================================
"""
API v1 avec versioning, documentation enrichie et schemas Pydantic dynamiques.

Endpoints:
    /api/v1/{module}        - CRUD operations
    /api/v1/{module}/search - Full-text search
    /api/v1/{module}/export - Export CSV/JSON
    /api/v1/{module}/bulk   - Bulk operations
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body, Path
from fastapi.responses import StreamingResponse, JSONResponse
from typing import List, Dict, Any, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field, create_model, validator
from pydantic.fields import FieldInfo
from enum import Enum
from datetime import datetime, date
import structlog
import io
import csv
import json

from .db import Database
from .parser import ModuleParser, ModuleDefinition, FieldDefinition
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth, require_role
from .icons import IconManager

logger = structlog.get_logger()


# =============================================================================
# Auto-numbering configuration
# =============================================================================
AUTO_NUMBER_CONFIG = {
    # Format: module_name -> (prefix, field_name, include_year)
    "interventions": ("INT", "reference", True),
    "clients": ("CLI", "code", False),
    "fournisseurs": ("FOU", "code", False),
    "donneur_ordre": ("DO", "code", False),
    "devis": ("DEV", "numero", True),
    "factures": ("FAC", "numero", True),
    "avoirs": ("AVO", "numero", True),
    "bons_livraison": ("BL", "numero", True),
    "commandes": ("CMD", "numero", True),
    "projets": ("PRJ", "code", False),
    "contrats": ("CTR", "numero", True),
    "produits": ("PRD", "code", False),
    "tickets": ("TKT", "numero", True),
}


def generate_auto_number(module_name: str, tenant_id: UUID) -> Optional[str]:
    """
    Génère automatiquement un numéro unique pour un module.
    Format: PREFIX-YYYY-XXXXX ou PREFIX-XXXXX selon la config.
    """
    config = AUTO_NUMBER_CONFIG.get(module_name.lower())
    if not config:
        return None

    prefix, field_name, include_year = config
    year = datetime.now().year

    # Récupérer le dernier numéro pour ce module/tenant
    with Database.get_session() as session:
        from sqlalchemy import text

        if include_year:
            # Chercher le dernier numéro de l'année en cours
            pattern = f"{prefix}-{year}-%"
            sql = text(f"""
                SELECT {field_name} FROM azalplus.{module_name}
                WHERE tenant_id = :tenant_id
                AND {field_name} LIKE :pattern
                AND deleted_at IS NULL
                ORDER BY {field_name} DESC
                LIMIT 1
            """)
            result = session.execute(sql, {"tenant_id": str(tenant_id), "pattern": pattern})
        else:
            # Chercher le dernier numéro global
            pattern = f"{prefix}-%"
            sql = text(f"""
                SELECT {field_name} FROM azalplus.{module_name}
                WHERE tenant_id = :tenant_id
                AND {field_name} LIKE :pattern
                AND deleted_at IS NULL
                ORDER BY {field_name} DESC
                LIMIT 1
            """)
            result = session.execute(sql, {"tenant_id": str(tenant_id), "pattern": pattern})

        row = result.fetchone()

        if row and row[0]:
            # Extraire le numéro séquentiel
            last_number = row[0]
            try:
                # Format: PREFIX-YYYY-XXXXX ou PREFIX-XXXXX
                parts = last_number.split("-")
                seq = int(parts[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1

        # Générer le nouveau numéro
        if include_year:
            return f"{prefix}-{year}-{seq:05d}"
        else:
            return f"{prefix}-{seq:05d}"

# =============================================================================
# API Router v1
# =============================================================================
router_v1 = APIRouter()  # Routes à /api/{module}


# =============================================================================
# Response Models
# =============================================================================

class PaginatedResponse(BaseModel):
    """Paginated list response."""
    items: List[Dict[str, Any]] = Field(..., description="Liste des elements")
    total: int = Field(..., description="Nombre total d'elements")
    skip: int = Field(0, description="Offset de pagination")
    limit: int = Field(25, description="Limite de pagination")
    has_more: bool = Field(False, description="Y a-t-il plus d'elements?")


class ItemResponse(BaseModel):
    """Single item response with metadata."""
    data: Dict[str, Any] = Field(..., description="Donnees de l'element")
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadonnees")


class BulkResult(BaseModel):
    """Result of a bulk operation."""
    success: int = Field(..., description="Nombre de succes")
    failed: int = Field(..., description="Nombre d'echecs")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Details des erreurs")


class ErrorDetail(BaseModel):
    """Detailed error response."""
    detail: str = Field(..., description="Message d'erreur")
    code: Optional[str] = Field(None, description="Code d'erreur")
    field: Optional[str] = Field(None, description="Champ concerne")


# =============================================================================
# Dynamic Schema Generation
# =============================================================================

def create_pydantic_model_v1(module: ModuleDefinition, mode: str = "create") -> type:
    """
    Create Pydantic model from module definition with enhanced validation.

    Args:
        module: Module definition from YAML
        mode: 'create', 'update', or 'response'

    Returns:
        Dynamically created Pydantic model class

    Note: Tous les champs sont optionnels côté Pydantic.
    La validation des champs requis se fait via Validator.validate_record()
    ce qui permet d'ajouter des valeurs par défaut avant la validation.
    """

    fields = {}
    validators = {}

    for nom, field_def in module.champs.items():
        python_type = _get_enhanced_python_type(field_def)
        field_info = _create_field_info(field_def, mode)

        if mode == "create":
            # Tous les champs optionnels - la validation se fait après
            fields[nom] = (Optional[python_type], field_info)

        elif mode == "update":
            # All fields optional for updates
            fields[nom] = (Optional[python_type], None)

        elif mode == "response":
            fields[nom] = (Optional[python_type], None)

        # Add enum validator if needed
        if field_def.enum_values:
            validators[f"validate_{nom}"] = _create_enum_validator(nom, field_def.enum_values)

    # Add system fields for response
    if mode == "response":
        fields["id"] = (UUID, Field(description="Identifiant unique"))
        fields["tenant_id"] = (UUID, Field(description="Identifiant du tenant"))
        fields["created_at"] = (Optional[datetime], Field(None, description="Date de creation"))
        fields["updated_at"] = (Optional[datetime], Field(None, description="Date de modification"))
        fields["created_by"] = (Optional[UUID], Field(None, description="Createur"))
        fields["updated_by"] = (Optional[UUID], Field(None, description="Modificateur"))

    model_name = f"{module.nom.title().replace('_', '')}{mode.title()}V1"

    # Create model with validators
    model = create_model(model_name, **fields)

    # Add validators dynamically
    for validator_name, validator_func in validators.items():
        setattr(model, validator_name, validator(validator_name.replace("validate_", ""), allow_reuse=True)(validator_func))

    return model


def _get_enhanced_python_type(field_def: FieldDefinition):
    """Get Python type with enhanced mapping."""

    type_mapping = {
        "text": str,
        "texte": str,
        "texte court": str,
        "texte long": str,
        "textarea": str,
        "email": str,
        "tel": str,
        "telephone": str,
        "url": str,
        "number": float,
        "nombre": float,
        "entier": int,
        "monnaie": float,
        "pourcentage": float,
        "date": str,  # ISO format
        "datetime": str,
        "heure": str,
        "boolean": bool,
        "booleen": bool,
        "oui/non": bool,
        "uuid": str,
        "relation": str,  # UUID as string
        "select": str,
        "enum": str,
        "tags": List[str],
        "json": Dict[str, Any],
        "fichier": str,
        "image": str,
    }

    return type_mapping.get(field_def.type.lower(), str)


def _create_field_info(field_def: FieldDefinition, mode: str) -> FieldInfo:
    """Create Pydantic FieldInfo with validation rules."""

    kwargs = {}

    # Description
    if field_def.aide:
        kwargs["description"] = field_def.aide
    elif field_def.label:
        kwargs["description"] = field_def.label

    # Default value
    if mode == "create" and field_def.defaut is not None:
        kwargs["default"] = field_def.defaut
    elif mode != "create":
        kwargs["default"] = None

    # Numeric constraints
    if field_def.min is not None:
        kwargs["ge"] = field_def.min
    if field_def.max is not None:
        kwargs["le"] = field_def.max

    # String constraints
    if field_def.type in ["text", "texte", "texte court"]:
        kwargs["max_length"] = 255
    elif field_def.type in ["texte long", "textarea"]:
        kwargs["max_length"] = 10000

    return Field(**kwargs) if kwargs else ...


def _create_enum_validator(field_name: str, enum_values: List[str]):
    """Create a validator for enum fields."""

    def validator_func(cls, v):
        if v is not None and v not in enum_values:
            raise ValueError(f"Valeur invalide pour {field_name}. Valeurs acceptees: {enum_values}")
        return v

    return validator_func


# =============================================================================
# Generic CRUD Router with Enhanced Features
# =============================================================================

class GenericCRUDRouterV1:
    """
    Enhanced CRUD router with:
    - Detailed OpenAPI documentation
    - Request/response examples
    - Pagination metadata
    - Search capabilities
    - Export functionality
    - Bulk operations
    """

    def __init__(self, module: ModuleDefinition):
        self.module = module
        self.table_name = module.nom
        self.display_name = module.nom_affichage

        # Generate models
        self.CreateModel = create_pydantic_model_v1(module, "create")
        self.UpdateModel = create_pydantic_model_v1(module, "update")
        self.ResponseModel = create_pydantic_model_v1(module, "response")

    def register(self, router: APIRouter):
        """Register all routes on the router."""

        module_name = self.module.nom
        tag = self.display_name or module_name.title()

        # =================================================================
        # LIST - GET /{module}
        # =================================================================
        @router.get(
            f"/{module_name}",
            tags=[tag],
            response_model=PaginatedResponse,
            summary=f"Lister les {self.display_name}",
            description=f"""
Retourne la liste paginee des {self.display_name}.

### Pagination
- `skip`: Nombre d'elements a ignorer (defaut: 0)
- `limit`: Nombre d'elements a retourner (defaut: 25, max: 100)

### Tri
- `order_by`: Champ de tri (defaut: created_at)
- `order_dir`: Direction du tri (asc/desc, defaut: desc)

### Exemple de reponse
```json
{{
    "items": [...],
    "total": 150,
    "skip": 0,
    "limit": 25,
    "has_more": true
}}
```
            """,
            responses={
                200: {
                    "description": "Liste des elements",
                    "content": {
                        "application/json": {
                            "example": {
                                "items": [{"id": "uuid", "name": "Example"}],
                                "total": 1,
                                "skip": 0,
                                "limit": 25,
                                "has_more": False
                            }
                        }
                    }
                },
                401: {"description": "Non authentifie", "model": ErrorDetail},
                403: {"description": "Acces refuse", "model": ErrorDetail}
            }
        )
        async def list_items(
            request: Request,
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth),
            skip: int = Query(0, ge=0, description="Offset de pagination"),
            limit: int = Query(25, ge=1, le=100, description="Limite de pagination"),
            order_by: str = Query("created_at", description="Champ de tri"),
            order_dir: str = Query("desc", regex="^(asc|desc)$", description="Direction du tri")
        ) -> PaginatedResponse:
            """Liste les enregistrements avec pagination."""

            order = f"{order_by} {order_dir.upper()}"
            items = Database.query(
                self.table_name,
                tenant_id,
                limit=limit + 1,  # +1 to check if has_more
                offset=skip,
                order_by=order
            )

            has_more = len(items) > limit
            if has_more:
                items = items[:limit]

            # Get total count
            total = Database.count(self.table_name, tenant_id)

            return PaginatedResponse(
                items=items,
                total=total,
                skip=skip,
                limit=limit,
                has_more=has_more
            )

        # =================================================================
        # BULK ROUTES - MUST BE BEFORE /{item_id} ROUTES
        # =================================================================

        # BULK CREATE - POST /{module}/bulk
        @router.post(
            f"/{module_name}/bulk",
            tags=[tag],
            summary=f"Creation en masse de {self.display_name}",
            responses={
                200: {"description": "Resultat de l'operation", "model": BulkResult},
                401: {"description": "Non authentifie", "model": ErrorDetail}
            }
        )
        async def bulk_create_early(
            items: List[Dict[str, Any]] = Body(..., max_items=100),
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ) -> BulkResult:
            success = 0
            failed = 0
            errors = []
            for idx, item_data in enumerate(items):
                try:
                    Database.insert(self.table_name, tenant_id, item_data, user_id)
                    success += 1
                except Exception as e:
                    failed += 1
                    errors.append({"index": idx, "error": str(e)})
            return BulkResult(success=success, failed=failed, errors=errors)

        # BULK UPDATE - PATCH /{module}/bulk
        @router.patch(
            f"/{module_name}/bulk",
            tags=[tag],
            summary=f"Mise a jour en masse de {self.display_name}",
            responses={
                200: {"description": "Resultat de l'operation", "model": BulkResult},
                401: {"description": "Non authentifie", "model": ErrorDetail}
            }
        )
        async def bulk_update_early(
            data: Dict[str, Any] = Body(...),
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ) -> BulkResult:
            ids = data.get("ids", [])
            updates = data.get("updates", {})
            if not ids:
                return BulkResult(success=0, failed=0, errors=[{"error": "Aucun ID fourni"}])
            if not updates:
                return BulkResult(success=0, failed=0, errors=[{"error": "Aucune mise a jour fournie"}])
            success = 0
            failed = 0
            errors = []
            for item_id in ids:
                try:
                    Database.update(self.table_name, tenant_id, UUID(item_id), updates, user_id)
                    success += 1
                except Exception as e:
                    failed += 1
                    errors.append({"id": item_id, "error": str(e)})
            return BulkResult(success=success, failed=failed, errors=errors)

        # BULK DELETE - DELETE /{module}/bulk
        @router.delete(
            f"/{module_name}/bulk",
            tags=[tag],
            summary=f"Suppression en masse de {self.display_name}",
            responses={
                200: {"description": "Resultat de l'operation", "model": BulkResult},
                401: {"description": "Non authentifie", "model": ErrorDetail}
            }
        )
        async def bulk_delete_early(
            data: Dict[str, Any] = Body(...),
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ) -> BulkResult:
            ids = data.get("ids", [])
            if not ids:
                return BulkResult(success=0, failed=0, errors=[{"error": "Aucun ID fourni"}])
            success = 0
            failed = 0
            errors = []
            for item_id in ids:
                try:
                    Database.soft_delete(self.table_name, tenant_id, UUID(item_id))
                    success += 1
                except Exception as e:
                    failed += 1
                    errors.append({"id": item_id, "error": str(e)})
            return BulkResult(success=success, failed=failed, errors=errors)

        # =================================================================
        # GET - GET /{module}/{id}
        # =================================================================
        @router.get(
            f"/{module_name}/{{item_id}}",
            tags=[tag],
            summary=f"Recuperer un(e) {self.display_name}",
            description=f"Retourne les details complets d'un(e) {self.display_name} par son ID.",
            responses={
                200: {"description": "Element trouve"},
                401: {"description": "Non authentifie", "model": ErrorDetail},
                404: {"description": "Element non trouve", "model": ErrorDetail}
            }
        )
        async def get_item(
            item_id: UUID = Path(..., description="ID de l'element"),
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth)
        ):
            """Recupere un enregistrement par ID."""

            item = Database.get_by_id(self.table_name, tenant_id, item_id)
            if not item:
                raise HTTPException(
                    status_code=404,
                    detail=f"{self.display_name} non trouve(e)"
                )
            return item

        # =================================================================
        # CREATE - POST /{module}
        # =================================================================
        @router.post(
            f"/{module_name}",
            tags=[tag],
            status_code=201,
            summary=f"Creer un(e) {self.display_name}",
            description=f"""
Cree un(e) nouveau/nouvelle {self.display_name}.

### Champs requis
{self._get_required_fields_doc()}

### Exemple
```json
{self._get_create_example()}
```
            """,
            responses={
                201: {"description": "Element cree"},
                400: {"description": "Donnees invalides", "model": ErrorDetail},
                401: {"description": "Non authentifie", "model": ErrorDetail},
                422: {"description": "Erreur de validation", "model": ErrorDetail}
            }
        )
        async def create_item(
            data: Dict[str, Any] = Body(..., description="Donnees de l'element"),
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ):
            """Cree un nouvel enregistrement."""

            # Auto-generate reference/code/numero if configured
            config = AUTO_NUMBER_CONFIG.get(self.table_name.lower())
            if config:
                prefix, field_name, include_year = config
                # Ne générer que si le champ n'est pas fourni ou est vide
                if not data.get(field_name):
                    auto_number = generate_auto_number(self.table_name, tenant_id)
                    if auto_number:
                        data[field_name] = auto_number

            # Validate required fields (skip auto-generated fields)
            for field_name, field_def in self.module.champs.items():
                if field_def.requis and field_name not in data:
                    # Skip if it's an auto-generated field
                    if config and field_name == config[1]:
                        continue
                    raise HTTPException(
                        status_code=422,
                        detail=f"Champ requis manquant: {field_name}"
                    )

            item = Database.insert(
                self.table_name,
                tenant_id,
                data,
                user_id
            )
            return item

        # =================================================================
        # UPDATE - PUT /{module}/{id}
        # =================================================================
        @router.put(
            f"/{module_name}/{{item_id}}",
            tags=[tag],
            summary=f"Mettre a jour un(e) {self.display_name}",
            description=f"Met a jour un(e) {self.display_name} existant(e). Seuls les champs fournis sont mis a jour.",
            responses={
                200: {"description": "Element mis a jour"},
                400: {"description": "Donnees invalides", "model": ErrorDetail},
                401: {"description": "Non authentifie", "model": ErrorDetail},
                404: {"description": "Element non trouve", "model": ErrorDetail},
                422: {"description": "Erreur de validation", "model": ErrorDetail}
            }
        )
        async def update_item(
            item_id: UUID = Path(..., description="ID de l'element"),
            data: Dict[str, Any] = Body(..., description="Donnees a mettre a jour"),
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ):
            """Met a jour un enregistrement existant."""

            # Check exists
            existing = Database.get_by_id(self.table_name, tenant_id, item_id)
            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail=f"{self.display_name} non trouve(e)"
                )

            # Remove None values
            update_data = {k: v for k, v in data.items() if v is not None}

            if not update_data:
                raise HTTPException(
                    status_code=400,
                    detail="Aucune donnee a mettre a jour"
                )

            item = Database.update(
                self.table_name,
                tenant_id,
                item_id,
                update_data,
                user_id
            )
            return item

        # =================================================================
        # DELETE - DELETE /{module}/{id}
        # =================================================================
        @router.delete(
            f"/{module_name}/{{item_id}}",
            tags=[tag],
            summary=f"Supprimer un(e) {self.display_name}",
            description=f"""
Supprime un(e) {self.display_name} (soft delete).

L'element n'est pas physiquement supprime mais marque comme supprime.
Il peut etre restaure par un administrateur.
            """,
            responses={
                200: {"description": "Element supprime"},
                401: {"description": "Non authentifie", "model": ErrorDetail},
                404: {"description": "Element non trouve", "model": ErrorDetail}
            }
        )
        async def delete_item(
            item_id: UUID = Path(..., description="ID de l'element"),
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth)
        ):
            """Supprime un enregistrement (soft delete)."""

            success = Database.soft_delete(self.table_name, tenant_id, item_id)
            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"{self.display_name} non trouve(e)"
                )
            return {"status": "deleted", "id": str(item_id)}

        # =================================================================
        # SEARCH - GET /{module}/search
        # =================================================================
        @router.get(
            f"/{module_name}/search",
            tags=[tag],
            summary=f"Rechercher dans les {self.display_name}",
            description=f"""
Recherche full-text dans les {self.display_name}.

La recherche est effectuee sur tous les champs texte du module.
            """,
            responses={
                200: {"description": "Resultats de recherche"},
                401: {"description": "Non authentifie", "model": ErrorDetail}
            }
        )
        async def search_items(
            q: str = Query(..., min_length=2, description="Terme de recherche"),
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth),
            limit: int = Query(10, ge=1, le=50, description="Nombre max de resultats")
        ):
            """Recherche dans les enregistrements."""

            items = Database.query(
                self.table_name,
                tenant_id,
                limit=100  # Get more to filter
            )

            # Filter in Python (simplified - should use PostgreSQL full-text search in production)
            q_lower = q.lower()
            results = []
            for item in items:
                for key, value in item.items():
                    if isinstance(value, str) and q_lower in value.lower():
                        results.append(item)
                        break

            return {
                "items": results[:limit],
                "total": len(results),
                "query": q
            }

        # =================================================================
        # EXPORT - GET /{module}/export
        # =================================================================
        @router.get(
            f"/{module_name}/export",
            tags=[tag],
            summary=f"Exporter les {self.display_name}",
            description=f"""
Exporte les {self.display_name} au format CSV ou JSON.

### Formats supportes
- `csv`: Export CSV avec headers
- `json`: Export JSON array
            """,
            responses={
                200: {
                    "description": "Fichier d'export",
                    "content": {
                        "text/csv": {},
                        "application/json": {}
                    }
                },
                401: {"description": "Non authentifie", "model": ErrorDetail}
            }
        )
        async def export_items(
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth),
            format: str = Query("csv", regex="^(csv|json)$", description="Format d'export"),
            limit: int = Query(1000, ge=1, le=10000, description="Nombre max d'elements")
        ):
            """Exporte les enregistrements."""

            items = Database.query(
                self.table_name,
                tenant_id,
                limit=limit,
                order_by="created_at DESC"
            )

            if format == "csv":
                output = io.StringIO()
                if items:
                    writer = csv.DictWriter(output, fieldnames=items[0].keys())
                    writer.writeheader()
                    writer.writerows(items)

                return StreamingResponse(
                    iter([output.getvalue()]),
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename={module_name}_export.csv"
                    }
                )

            else:  # JSON
                return StreamingResponse(
                    iter([json.dumps(items, default=str, indent=2)]),
                    media_type="application/json",
                    headers={
                        "Content-Disposition": f"attachment; filename={module_name}_export.json"
                    }
                )

    def _get_required_fields_doc(self) -> str:
        """Generate documentation for required fields."""
        required = []
        for nom, field_def in self.module.champs.items():
            if field_def.requis:
                desc = field_def.aide or field_def.label or nom
                required.append(f"- `{nom}`: {desc}")
        return "\n".join(required) if required else "Aucun champ requis"

    def _get_create_example(self) -> str:
        """Generate create example JSON."""
        example = {}
        for nom, field_def in self.module.champs.items():
            if field_def.requis or field_def.defaut is not None:
                if field_def.defaut is not None:
                    example[nom] = field_def.defaut
                elif field_def.type in ["text", "texte"]:
                    example[nom] = f"exemple_{nom}"
                elif field_def.type in ["number", "nombre"]:
                    example[nom] = 0
                elif field_def.type == "email":
                    example[nom] = "exemple@email.com"
                elif field_def.type in ["boolean", "booleen"]:
                    example[nom] = True
                elif field_def.enum_values:
                    example[nom] = field_def.enum_values[0]
        return json.dumps(example, indent=2)


# =============================================================================
# Register all modules on v1 router
# =============================================================================

def register_v1_modules():
    """Register all active modules on the v1 router."""

    for module_name in ModuleParser.list_all():
        module = ModuleParser.get(module_name)
        if module and module.actif:
            crud_router = GenericCRUDRouterV1(module)
            crud_router.register(router_v1)
            logger.debug("v1_routes_registered", module=module_name)


# =============================================================================
# Utility endpoints
# =============================================================================

@router_v1.get(
    "/",
    tags=["API"],
    summary="API v1 Information",
    description="Retourne les informations sur l'API v1."
)
async def api_info():
    """Information sur l'API v1."""
    return {
        "version": "1.0.0",
        "status": "stable",
        "documentation": "/api/documentation",
        "modules": ModuleParser.count(),
        "endpoints": {
            "list": "GET /api/v1/{module}",
            "get": "GET /api/v1/{module}/{id}",
            "create": "POST /api/v1/{module}",
            "update": "PUT /api/v1/{module}/{id}",
            "delete": "DELETE /api/v1/{module}/{id}",
            "search": "GET /api/v1/{module}/search",
            "export": "GET /api/v1/{module}/export",
            "bulk": "POST /api/v1/{module}/bulk"
        }
    }


@router_v1.get(
    "/modules",
    tags=["API"],
    summary="Liste des modules disponibles",
    description="Retourne la liste des modules accessibles via l'API v1."
)
async def list_v1_modules(user: dict = Depends(require_auth)):
    """Liste les modules disponibles en v1."""

    modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module and module.actif:
            modules.append({
                "name": module.nom,
                "display_name": module.nom_affichage,
                "icon": module.icone,
                "icon_url": IconManager.get_icon_url(module.icone),
                "menu": module.menu,
                "description": module.description,
                "fields_count": len(module.champs),
                "endpoints": {
                    "list": f"/api/v1/{module.nom}",
                    "get": f"/api/v1/{module.nom}/{{id}}",
                    "create": f"/api/v1/{module.nom}",
                    "update": f"/api/v1/{module.nom}/{{id}}",
                    "delete": f"/api/v1/{module.nom}/{{id}}",
                    "search": f"/api/v1/{module.nom}/search",
                    "export": f"/api/v1/{module.nom}/export"
                }
            })

    return {"modules": modules, "count": len(modules)}
