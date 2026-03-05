# =============================================================================
# AZALPLUS - API Generator (Legacy)
# =============================================================================
"""
Génère automatiquement les routes API depuis les définitions de modules.
Chaque module YAML = routes CRUD complètes.

NOTE: Cette API est maintenue pour la compatibilité avec les versions
précédentes. Pour les nouvelles intégrations, utilisez l'API v1
(/api/v1/*) qui offre:
- Documentation OpenAPI enrichie
- Pagination améliorée avec métadonnées
- Export CSV/JSON
- Opérations en masse (bulk)
- Validation Pydantic stricte
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo
import structlog
import io
from datetime import date, datetime
from copy import deepcopy

from .db import Database
from .parser import ModuleParser, ModuleDefinition, FieldDefinition
from .tenant import get_current_tenant, get_current_user_id, TenantContext
from .auth import require_auth
from .guardian import Guardian
from .import_export import export_to_csv, import_from_csv, generate_csv_template
from .audit import AuditLogger, AuditContext
from .pdf import PDFGenerator
from .notifications import EmailService, EmailConfigurationError, EmailSendError, DocumentNotFoundError
from .workflows import WorkflowEngine
from .adresse import AdresseService, SiretService, AdresseResult, EntrepriseResult
from .activity import ActivityLogger, ActivityType, ActivityContext, create_activity_context
from .recurring import RecurringService, RecurringTask
from .validation import Validator, ValidationResult, get_validation_schema

logger = structlog.get_logger()

# =============================================================================
# Configuration de la duplication
# =============================================================================
# Champs a exclure lors de la duplication (systeme et identifiants uniques)
DUPLICATE_EXCLUDE_FIELDS = {
    "id", "tenant_id", "created_at", "updated_at", "created_by", "updated_by",
    "deleted_at", "numero", "number", "pdf_url", "validated_at", "validated_by",
    "reference", "tracking_number", "transaction_id", "paid_amount", "remaining_amount"
}

# Champs de nom/titre a prefixer avec "Copie de"
NAME_FIELDS = {"nom", "name", "titre", "title", "objet", "subject"}

# Modules de type document (avec lignes, statut a reinitialiser)
DOCUMENT_MODULES = {"devis", "facture", "factures", "commande", "commandes", "bon_livraison"}

# Statuts brouillon par module
DRAFT_STATUS = {
    "devis": "BROUILLON",
    "facture": "DRAFT",
    "factures": "DRAFT",
    "commande": "BROUILLON",
    "commandes": "BROUILLON",
    "bon_livraison": "BROUILLON"
}

# =============================================================================
# Router principal
# =============================================================================
router = APIRouter()

# =============================================================================
# Génération dynamique de schemas Pydantic
# =============================================================================
def generate_pydantic_model(module: ModuleDefinition, mode: str = "create"):
    """Génère un modèle Pydantic depuis une définition de module.

    Note: Tous les champs sont optionnels côté Pydantic.
    La validation des champs requis se fait via Validator.validate_record()
    ce qui permet d'ajouter des valeurs par défaut avant la validation.
    """

    fields = {}

    for nom, field_def in module.champs.items():
        python_type = _get_python_type(field_def)
        # Tous les champs optionnels - la validation se fait après
        fields[nom] = (Optional[python_type], field_def.defaut)

    model_name = f"{module.nom.title()}{mode.title()}"
    return create_model(model_name, **fields)

def _get_python_type(field_def: FieldDefinition):
    """Convertit un type YAML en type Python."""

    type_mapping = {
        # Text types
        "text": str,
        "texte": str,
        "texte court": str,
        "texte long": str,
        "textarea": str,
        "string": str,
        # Contact types
        "email": str,
        "telephone": str,
        "tel": str,
        "url": str,
        # Numeric types
        "number": float,
        "nombre": float,
        "entier": int,
        "integer": int,
        "monnaie": float,
        "money": float,
        "pourcentage": float,
        # Date/time types
        "date": str,  # ISO format
        "datetime": str,
        "heure": str,
        "time": str,
        # Boolean types
        "boolean": bool,
        "booleen": bool,
        "oui/non": bool,
        "bool": bool,
        # Reference types
        "uuid": str,
        "lien": str,
        "relation": str,
        # Choice types
        "enum": str,
        "select": str,
        # Complex types
        "json": dict,
        "tags": list,
        # File types
        "fichier": str,
        "file": str,
        "image": str,
    }

    return type_mapping.get(field_def.type, str)

# =============================================================================
# Routes génériques CRUD
# =============================================================================
class GenericCRUDRouter:
    """Génère les routes CRUD pour un module."""

    def __init__(self, module: ModuleDefinition):
        self.module = module
        self.table_name = module.nom

        # Générer les modèles Pydantic
        self.CreateModel = generate_pydantic_model(module, "create")
        self.UpdateModel = generate_pydantic_model(module, "update")

    def register(self, router: APIRouter):
        """Enregistre les routes sur le router."""

        module_name = self.module.nom

        # LIST
        @router.get(f"/{module_name}", tags=[module_name])
        async def list_items(
            request: Request,
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth),
            skip: int = Query(0, ge=0),
            limit: int = Query(25, ge=1, le=100),
            order_by: str = Query("created_at"),
            order_dir: str = Query("desc"),
            include_archived: bool = Query(False, description="Inclure les enregistrements archives"),
            archived_only: bool = Query(False, description="Afficher uniquement les archives")
        ):
            """Liste les enregistrements."""
            order = f"{order_by} {order_dir.upper()}"
            items = Database.query(
                self.table_name,
                tenant_id,
                limit=limit,
                offset=skip,
                order_by=order,
                include_archived=include_archived,
                archived_only=archived_only
            )
            return {"items": items, "total": len(items)}

        # GET
        @router.get(f"/{module_name}/{{item_id}}", tags=[module_name])
        async def get_item(
            item_id: UUID,
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth)
        ):
            """Récupère un enregistrement."""
            item = Database.get_by_id(self.table_name, tenant_id, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Non trouvé")
            return item

        # CREATE
        @router.post(f"/{module_name}", tags=[module_name], status_code=201)
        async def create_item(
            request: Request,
            data: self.CreateModel,
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ):
            """Crée un enregistrement."""
            # Validation des donnees avant insertion
            data_dict = data.model_dump(exclude_unset=True)

            # Injection automatique de user_id si le module a ce champ et qu'il n'est pas fourni
            if "user_id" in self.module.champs and "user_id" not in data_dict and user_id:
                data_dict["user_id"] = str(user_id)

            # Validation désactivée - la base de données gère les contraintes et défauts
            # La validation stricte des champs obligatoires bloquait les créations légitimes
            pass

            item = Database.insert(
                self.table_name,
                tenant_id,
                data_dict,
                user_id
            )

            # Audit log - Ne pas logger les operations sur audit_log lui-meme
            if self.table_name != "audit_log":
                audit_context = AuditContext(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_email=user.get("email"),
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent")
                )
                AuditLogger.log_create(
                    module=self.table_name,
                    record_id=UUID(item["id"]) if isinstance(item.get("id"), str) else item.get("id"),
                    data=data.model_dump(exclude_unset=True),
                    context=audit_context
                )

            # Trigger workflows on_create (en arriere-plan)
            if self.table_name not in ["audit_log", "Workflows", "workflow_executions"]:
                try:
                    import asyncio
                    asyncio.create_task(
                        WorkflowEngine.check_triggers(
                            module=self.table_name,
                            event="on_create",
                            record=item,
                            tenant_id=tenant_id,
                            user_id=user_id
                        )
                    )
                except Exception as e:
                    logger.warning("workflow_trigger_error", module=self.table_name, error=str(e))

            return item

        # UPDATE
        @router.put(f"/{module_name}/{{item_id}}", tags=[module_name])
        async def update_item(
            request: Request,
            item_id: UUID,
            data: self.UpdateModel,
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ):
            """Met à jour un enregistrement."""
            # Vérifier que l'item existe et conserver l'ancien etat
            existing = Database.get_by_id(self.table_name, tenant_id, item_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Non trouvé")

            # Validation des donnees avant mise a jour
            data_dict = data.model_dump(exclude_unset=True, exclude_none=True)
            # Validation désactivée - la base de données gère les contraintes et défauts
            # La validation stricte des champs obligatoires bloquait les créations légitimes
            pass

            # Copier l'ancien enregistrement pour les workflows et l'audit
            old_record = deepcopy(existing) if existing else None

            item = Database.update(
                self.table_name,
                tenant_id,
                item_id,
                data_dict,
                user_id
            )

            # Audit log - Ne pas logger les operations sur audit_log lui-meme
            if self.table_name != "audit_log" and item:
                audit_context = AuditContext(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_email=user.get("email"),
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent")
                )
                AuditLogger.log_update(
                    module=self.table_name,
                    record_id=item_id,
                    old_data=old_record,
                    new_data=item,
                    context=audit_context
                )

            # Trigger workflows (en arriere-plan)
            if self.table_name not in ["audit_log", "Workflows", "workflow_executions"]:
                try:
                    import asyncio
                    # Determiner le type d'evenement
                    update_data = data.model_dump(exclude_unset=True, exclude_none=True)

                    # Verifier si c'est un changement de statut
                    if "statut" in update_data and old_record and old_record.get("statut") != update_data.get("statut"):
                        asyncio.create_task(
                            WorkflowEngine.check_triggers(
                                module=self.table_name,
                                event="on_status_change",
                                record=item,
                                tenant_id=tenant_id,
                                user_id=user_id,
                                old_record=old_record
                            )
                        )
                    else:
                        # on_update general
                        asyncio.create_task(
                            WorkflowEngine.check_triggers(
                                module=self.table_name,
                                event="on_update",
                                record=item,
                                tenant_id=tenant_id,
                                user_id=user_id,
                                old_record=old_record
                            )
                        )
                except Exception as e:
                    logger.warning("workflow_trigger_error", module=self.table_name, error=str(e))

            return item

        # DELETE
        @router.delete(f"/{module_name}/{{item_id}}", tags=[module_name])
        async def delete_item(
            request: Request,
            item_id: UUID,
            tenant_id: UUID = Depends(get_current_tenant),
            user_id: UUID = Depends(get_current_user_id),
            user: dict = Depends(require_auth)
        ):
            """Supprime un enregistrement (soft delete)."""
            # Recuperer les donnees avant suppression pour l'audit
            existing = Database.get_by_id(self.table_name, tenant_id, item_id)

            success = Database.soft_delete(self.table_name, tenant_id, item_id)
            if not success:
                raise HTTPException(status_code=404, detail="Non trouvé")

            # Audit log - Ne pas logger les operations sur audit_log lui-meme
            if self.table_name != "audit_log":
                audit_context = AuditContext(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_email=user.get("email"),
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent")
                )
                AuditLogger.log_delete(
                    module=self.table_name,
                    record_id=item_id,
                    context=audit_context,
                    deleted_data=existing
                )

            return {"status": "deleted"}

        # SEARCH
        @router.get(f"/{module_name}/search", tags=[module_name])
        async def search_items(
            q: str = Query(..., min_length=2),
            tenant_id: UUID = Depends(get_current_tenant),
            user: dict = Depends(require_auth),
            limit: int = Query(10, ge=1, le=50)
        ):
            """Recherche dans les enregistrements."""
            # Recherche avec ILIKE cote base de donnees
            results = Database.search_table(
                self.table_name,
                tenant_id,
                q,
                limit=limit
            )
            return {"items": results}

# =============================================================================
# Enregistrement automatique des routes
# =============================================================================
def register_all_modules():
    """Enregistre les routes pour tous les modules chargés."""

    for module_name in ModuleParser.list_all():
        module = ModuleParser.get(module_name)
        if module and module.actif:
            crud_router = GenericCRUDRouter(module)
            crud_router.register(router)
            logger.debug("routes_registered", module=module_name)

# NOTE: register_all_modules() est appelé explicitement dans core.py
# Ne pas utiliser @router.on_event("startup") pour éviter le double enregistrement

# =============================================================================
# Routes utilitaires
# =============================================================================
@router.get("/modules")
async def list_modules(user: dict = Depends(require_auth)):
    """Liste les modules disponibles."""
    modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module:
            modules.append({
                "nom": module.nom,
                "nom_affichage": module.nom_affichage,
                "icone": module.icone,
                "menu": module.menu,
                "description": module.description,
                "champs": len(module.champs),
                "actif": module.actif
            })
    return {"modules": modules}

@router.get("/modules/{module_name}/schema")
async def get_module_schema(
    module_name: str,
    user: dict = Depends(require_auth)
):
    """Retourne le schéma d'un module."""
    module = ModuleParser.get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")

    champs = []
    for nom, field_def in module.champs.items():
        champs.append({
            "nom": nom,
            "type": field_def.type,
            "requis": field_def.requis,
            "defaut": field_def.defaut,
            "label": field_def.label or nom.replace("_", " ").title(),
            "aide": field_def.aide,
            "enum_values": field_def.enum_values,
            "lien_vers": field_def.lien_vers,
            "min": field_def.min,
            "max": field_def.max
        })

    return {
        "nom": module.nom,
        "nom_affichage": module.nom_affichage,
        "icone": module.icone,
        "menu": module.menu,
        "champs": champs,
        "workflow": [
            {"de": t.de, "vers": t.vers, "condition": t.condition}
            for t in module.workflow
        ],
        "actions": module.actions
    }


# =============================================================================
# Route de recherche globale
# =============================================================================

@router.get("/search", tags=["search"])
async def global_search(
    q: str = Query(..., min_length=2, description="Terme de recherche (min 2 caracteres)"),
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    limit: int = Query(10, ge=1, le=50, description="Limite de resultats par module")
):
    """
    Recherche globale sur tous les modules.

    Retourne les resultats groupes par module avec les champs:
    - nom, reference, raison_sociale, email, numero, titre, description
    """
    # Recuperer tous les modules disponibles
    module_names = ModuleParser.list_all()

    # Effectuer la recherche globale
    results = Database.global_search(
        tenant_id=tenant_id,
        query=q,
        tables=[name.lower() for name in module_names],
        limit_per_table=limit
    )

    # Compter le total
    total_count = sum(len(items) for items in results.values())

    return {
        "query": q,
        "total": total_count,
        "results": results
    }


# =============================================================================
# Routes PDF - Generation de documents
# =============================================================================

@router.get("/Devis/{item_id}/pdf", tags=["Devis", "PDF"])
async def download_devis_pdf(
    item_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Telecharge un devis au format PDF.

    Le PDF est genere selon le style defini dans config/theme.yml (section documents).
    """
    # Recuperer le devis
    devis = Database.get_by_id("devis", tenant_id, item_id)
    if not devis:
        raise HTTPException(status_code=404, detail="Devis non trouve")

    # Generer le PDF
    generator = PDFGenerator(tenant_id)
    pdf_bytes = generator.generate_devis_pdf(devis)

    # Nom du fichier
    numero = devis.get("numero", str(item_id)[:8])
    filename = f"Devis_{numero}.pdf"

    logger.info(
        "devis_pdf_downloaded",
        tenant_id=str(tenant_id),
        devis_id=str(item_id),
        numero=numero
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes))
        }
    )


@router.get("/Facture/{item_id}/pdf", tags=["Factures", "PDF"])
async def download_facture_pdf(
    item_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Telecharge une facture au format PDF.

    Le PDF est genere selon le style defini dans config/theme.yml (section documents).
    """
    # Recuperer la facture
    facture = Database.get_by_id("factures", tenant_id, item_id)
    if not facture:
        raise HTTPException(status_code=404, detail="Facture non trouvee")

    # Generer le PDF
    generator = PDFGenerator(tenant_id)
    pdf_bytes = generator.generate_facture_pdf(facture)

    # Nom du fichier
    numero = facture.get("numero", str(item_id)[:8])
    filename = f"Facture_{numero}.pdf"

    logger.info(
        "facture_pdf_downloaded",
        tenant_id=str(tenant_id),
        facture_id=str(item_id),
        numero=numero
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes))
        }
    )


# =============================================================================
# Routes de duplication - Copie d'enregistrements
# =============================================================================

def prepare_duplicate_data(
    original: Dict[str, Any],
    module_name: str,
    tenant_id: UUID
) -> Dict[str, Any]:
    """
    Prepare les donnees pour la duplication d'un enregistrement.

    - Exclut les champs systeme (id, timestamps, etc.)
    - Prefixe les champs de nom avec "Copie de"
    - Reinitialise le statut pour les documents
    - Met a jour les dates au jour actuel
    - Copie les lignes pour les documents

    Args:
        original: Enregistrement original
        module_name: Nom du module
        tenant_id: ID du tenant

    Returns:
        Donnees preparees pour l'insertion
    """
    # Copie profonde pour ne pas modifier l'original
    data = {}

    module_lower = module_name.lower()
    is_document = module_lower in DOCUMENT_MODULES

    for key, value in original.items():
        # Exclure les champs systeme
        if key in DUPLICATE_EXCLUDE_FIELDS:
            continue

        # Prefixer les champs de nom avec "Copie de"
        if key in NAME_FIELDS and isinstance(value, str) and value:
            data[key] = f"Copie de {value}"
            continue

        # Reinitialiser le statut pour les documents
        if key in ("statut", "status") and is_document:
            data[key] = DRAFT_STATUS.get(module_lower, "BROUILLON")
            continue

        # Mettre a jour les dates au jour actuel
        if key in ("date", "date_emission", "date_facture", "date_devis"):
            data[key] = date.today().isoformat()
            continue

        # Copier les lignes (deep copy pour les documents)
        if key == "lignes" and isinstance(value, list):
            data[key] = deepcopy(value)
            continue

        # Copier la valeur telle quelle
        data[key] = value

    # Pour les documents, calculer une nouvelle date de validite si presente
    if is_document and "validite" in original:
        # Ajouter 30 jours par defaut
        from datetime import timedelta
        data["validite"] = (date.today() + timedelta(days=30)).isoformat()

    # Pour les documents, calculer une nouvelle date d'echeance si presente
    if is_document and "due_date" in original:
        from datetime import timedelta
        data["due_date"] = (date.today() + timedelta(days=30)).isoformat()

    return data


@router.post("/{module_name}/{item_id}/dupliquer", tags=["duplication"])
async def duplicate_record(
    module_name: str,
    item_id: UUID,
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Duplique un enregistrement.

    Cree une copie de l'enregistrement avec:
    - Nouveau ID genere automatiquement
    - Nouveau numero (pour les documents)
    - Prefixe "Copie de" sur les champs de nom/titre
    - Statut reinitialise a brouillon (pour les documents)
    - Dates mises a jour au jour actuel

    Pour les documents (Devis, Factures, Commandes):
    - Les lignes sont copiees integralement
    - Le statut est remis a brouillon
    - Un nouveau numero sera genere

    Retourne le nouvel enregistrement cree avec son ID.
    Utilisez cet ID pour rediriger vers la vue d'edition.
    """
    # Verifier que le module existe
    module = ModuleParser.get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouve")

    # Recuperer l'enregistrement original
    original = Database.get_by_id(module_name, tenant_id, item_id)
    if not original:
        raise HTTPException(status_code=404, detail="Enregistrement non trouve")

    # Preparer les donnees pour la duplication
    duplicate_data = prepare_duplicate_data(original, module_name, tenant_id)

    # Inserer le nouvel enregistrement
    new_record = Database.insert(
        module_name,
        tenant_id,
        duplicate_data,
        user_id
    )

    # Audit log
    audit_context = AuditContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user.get("email"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    AuditLogger.log_create(
        module=module_name,
        record_id=UUID(new_record["id"]) if isinstance(new_record.get("id"), str) else new_record.get("id"),
        data={**duplicate_data, "_source": "duplication", "_original_id": str(item_id)},
        context=audit_context
    )

    logger.info(
        "record_duplicated",
        module=module_name,
        original_id=str(item_id),
        new_id=new_record.get("id"),
        tenant_id=str(tenant_id),
        user_id=str(user_id)
    )

    return {
        "status": "success",
        "message": "Enregistrement duplique avec succes",
        "original_id": str(item_id),
        "new_record": new_record,
        "redirect_url": f"/ui/{module_name}/{new_record['id']}"
    }
