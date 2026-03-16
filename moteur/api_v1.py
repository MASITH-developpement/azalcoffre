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
from .tenant import get_current_tenant, get_current_user_id, SYSTEM_TENANT_ID
from .auth import require_auth, require_role
from .icons import IconManager
# from .calendar_utils import calculate_calendar_workload  # Import commenté car non disponible

logger = structlog.get_logger()

# Routeur pour les endpoints non versionnés (compatibilité)
legacy_router = APIRouter(prefix="/api")

# Routeur pour les endpoints admin
admin_router = APIRouter(prefix="/api/admin")

# Cache pour les endpoints dynamiques
_dynamic_endpoints_cache = {}

class RecentTrackData(BaseModel):
    """Schéma pour les données de tracking d'accès récent"""
    module: Optional[str] = None
    record_id: Optional[str] = None
    action: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

@legacy_router.post("/recent/track")
async def track_recent_access(
    data: Optional[Dict[str, Any]] = Body(None)
):
    """Enregistre l'accès récent à un élément"""
    try:
        
        # Toujours retourner un succès, même avec des données invalides
        logger.debug("Tracking d'accès récent reçu", data=data)
        
        # Optionnel: valider les données si présentes
        if data and isinstance(data, dict):
            try:
                validated_data = RecentTrackData(**data)
                logger.debug("Tracking d'accès récent validé", 
                            module=validated_data.module, 
                            record_id=validated_data.record_id, 
                            action=validated_data.action)
            except Exception as validation_error:
                logger.debug("Données de tracking non valides, ignorées", error=str(validation_error))
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Access tracked successfully"}
        )
        
    except Exception as e:
        logger.error("Erreur lors du tracking d'accès récent", error=str(e))
        # Toujours retourner 200 même en cas d'erreur
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Access tracking skipped"}
        )

@legacy_router.api_route("/factures", methods=["GET", "POST", "PUT", "DELETE"])
@legacy_router.api_route("/factures/{item_id}", methods=["GET", "POST", "PUT", "DELETE"])
async def factures_handler(
    request: Request,
    item_id: Optional[str] = None,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Handler générique pour le module factures"""
    try:
        logger.info("Requête factures", method=request.method, item_id=item_id, tenant_id=str(tenant_id))
        
        db = Database()
        parser = ModuleParser()
        
        # Récupérer la définition du module
        module_def = parser.get_module_definition("factures", tenant_id)
        if not module_def:
            raise HTTPException(status_code=404, detail="Module factures non trouvé")
        
        # Traitement selon la méthode HTTP
        if request.method == "GET":
            if item_id:
                # Récupérer un élément spécifique
                result = db.get_record("factures", item_id, tenant_id)
                if not result:
                    raise HTTPException(status_code=404, detail="Facture non trouvée")
                return result
            else:
                # Récupérer la liste
                results = db.get_records("factures", tenant_id, limit=100)
                return {"data": results, "total": len(results)}
        
        elif request.method == "POST":
            # Créer un nouvel élément
            body = await request.json()
            result = db.create_record("factures", body, tenant_id, user_id)
            return resultltltltltltlt
        
        elif request.method == "PUT":
            if not item_id:
                raise HTTPException(status_code=400, detail="ID requis pour la mise à jour")
            body = await request.json()
            result = db.update_record("factures", item_id, body, tenant_id, user_id)
            return result
        
        elif request.method == "DELETE":
            if not item_id:
                raise HTTPException(status_code=400, detail="ID requis pour la suppression")
            result = db.delete_record("factures", item_id, tenant_id)
            return {"success": True, "deleted_id": item_id}
        
        else:
            raise HTTPException(status_code=405, detail="Méthode non autorisée")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erreur dans factures_handler", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@legacy_router.get("/calendar/workload")
async def get_calendar_workload(
    year: int = Query(..., description="Année", ge=1900, le=2100),
    month: int = Query(..., description="Mois", ge=1, le=12),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère la charge de travail du calendrier"""
    try:
        logger.info("Récupération de la charge de travail", year=year, month=month, tenant_id=str(tenant_id), user_id=str(user_id))
        
        # Validation explicite avec logs détaillés
        if not isinstance(year, int):
            logger.warning("Année invalide - pas un entier", year=year, type_year=type(year))
            raise HTTPException(status_code=400, detail=f"L'année doit être un entier, reçu: {type(year).__name__}")
            
        if not isinstance(month, int):
            logger.warning("Mois invalide - pas un entier", month=month, type_month=type(month))
            raise HTTPException(status_code=400, detail=f"Le mois doit être un entier, reçu: {type(month).__name__}")
            
        if not (1 <= month <= 12):
            logger.warning("Mois hors limites", month=month)
            raise HTTPException(status_code=400, detail=f"Le mois doit être entre 1 et 12, reçu: {month}")
            
        if not (1900 <= year <= 2100):
            logger.warning("Année hors limites", year=year)
            raise HTTPException(status_code=400, detail=f"L'année doit être entre 1900 et 2100, reçu: {year}")

        # Retourner des données vides pour le moment
        logger.debug("Retour de données temporaires pour la charge de travail")
        return {
            "year": year,
            "month": month,
            "workload": [],
            "total_hours": 0,
            "message": "Endpoint temporaire - fonctionnalité en cours de développement"
        }

    except HTTPException as he:
        logger.error("HTTPException dans get_calendar_workload", status_code=he.status_code, detail=he.detail)
        raise
    except Exception as e:
        logger.error("Erreur inattendue lors de la récupération de la charge de travail", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")

# Modules système à initialiser automatiquement
SYSTEM_MODULES = ['favoris', 'notifications', 'documents', 'utilisateurs', 'ged_dossiers', 'agenda', 'clients', 'interventions', 'marketplace_btob', 'business_plan', 'donneur_ordre', 'factures']

def create_module_endpoints(module_name: str):
    """Crée dynamiquement les endpoints CRUD pour un module"""
    if module_name in _dynamic_endpoints_cache:
        return
    
    @legacy_router.get(f"/{module_name}")
    async def get_module_records(
        limit: int = Query(50, le=1000),
        offset: int = Query(0, ge=0),
        role: Optional[str] = Query(None),
        tenant_id: UUID = Depends(get_current_tenant),
        user_id: UUID = Depends(get_current_user_id)
    ):
        """Récupère une liste d'enregistrements avec filtres optionnels"""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                
                # Vérifier si la table existe
                try:
                    table_check = f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'azalplus' 
                            AND table_name = '{module_name}'
                        )
                    """
                    
                    table_exists_result = session.execute(text(table_check))
                    table_exists = table_exists_result.scalar()
                    
                    if not table_exists:
                        logger.warning(f"Table {module_name} not found in schema")
                        raise HTTPException(status_code=404, detail=f"Module {module_name} not found")
                        
                except Exception as db_error:
                    logger.error(f"Database error checking table existence for {module_name}", error=str(db_error))
                    raise HTTPException(status_code=500, detail="Database connection error")
                
                # Vérifier les colonnes disponibles dans la table
                columns_check = f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = '{module_name}'
                """
                
                columns_result = session.execute(text(columns_check))
                available_columns = [row[0] for row in columns_result.fetchall()]
                
                # Construire la requête avec filtres en fonction des colonnes disponibles
                where_conditions = []
                params = {'limit': limit, 'offset': offset}
                
                # Ajouter le filtre tenant_id si la colonne existe
                if 'tenant_id' in available_columns:
                    where_conditions.append("tenant_id = :tenant_id")
                    params['tenant_id'] = str(tenant_id)
                
                # Construire la requête finale
                base_query = f"SELECT * FROM azalplus.{module_name}"
                if where_conditions:
                    base_query += " WHERE " + " AND ".join(where_conditions)
                base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                
                # Exécuter la requête
                result = session.execute(text(base_query), params)
                records = [dict(row._mapping) for row in result.fetchall()]
                
                # Compter le total pour la pagination
                count_query = f"SELECT COUNT(*) FROM azalplus.{module_name}"
                if where_conditions:
                    count_conditions = [cond for cond in where_conditions if 'tenant_id' in cond]
                    if count_conditions:
                        count_query += " WHERE " + " AND ".join(count_conditions)
                        count_result = session.execute(text(count_query), {'tenant_id': str(tenant_id)})
                    else:
                        count_result = session.execute(text(count_query))
                else:
                    count_result = session.execute(text(count_query))
                
                total = count_result.scalar()
                
                return {
                    'data': records,
                    'total': total,
                    'limit': limit,
                    'offset': offset
                }
                
                # Ajouter les filtres standard si les colonnes existent
                if 'tenant_id' in available_columns and tenant_id:
                    where_conditions.append('tenant_id = :tenant_id')
                    params['tenant_id'] = str(tenant_id)
                    
                if 'created_by' in available_columns and user_id:
                    # Ne filtrer par user que si un rôle spécifique est demandé
                    if role and role != 'admin':
                        where_conditions.append('created_by = :user_id')
                        params['user_id'] = str(user_id)
                
                # Construire la requête finale
                base_query = f"SELECT * FROM azalplus.{module_name}"
                if where_conditions:
                    base_query += " WHERE " + " AND ".join(where_conditions)
                base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                
                try:
                    result = session.execute(text(base_query), params)
                    records = [dict(row._mapping) for row in result.fetchall()]
                    
                    # Compter le total
                    count_query = f"SELECT COUNT(*) FROM azalplus.{module_name}"
                    if where_conditions:
                        count_conditions = [cond for cond in where_conditions if 'LIMIT' not in cond and 'OFFSET' not in cond]
                        if count_conditions:
                            count_query += " WHERE " + " AND ".join(count_conditions)
                    
                    count_params = {k: v for k, v in params.items() if k not in ['limit', 'offset']}
                    count_result = session.execute(text(count_query), count_params)
                    total = count_result.scalar() or 0
                    
                    return {
                        "data": records,
                        "total": total,
                        "limit": limit,
                        "offset": offset
                    }
                    
                except Exception as sql_error:
                    logger.error(f"Erreur SQL dans {module_name}", error=str(sql_error), query=base_query)
                    raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des données: {str(sql_error)}")
                
                # Ajouter le filtre tenant_id si la colonne existe
                if 'tenant_id' in available_columns:
                    where_conditions.append('tenant_id = :tenant_id')
                    params['tenant_id'] = str(tenant_id)
                
                # Ajouter le filtre role si spécifié et si la colonne existe
                if role and 'role' in available_columns:
                    where_conditions.append('role = :role')
                    params['role'] = role
                
                # Construire la requête finale
                base_query = f'SELECT * FROM azalplus.{module_name}'
                if where_conditions:
                    base_query += ' WHERE ' + ' AND '.join(where_conditions)
                base_query += ' ORDER BY id LIMIT :limit OFFSET :offset'
                
                result = session.execute(text(base_query), params)
                records = [dict(row._mapping) for row in result.fetchall()]
                
                return {
                    'data': records,
                    'total': len(records),
                    'limit': limit,
                    'offset': offset
                }
                
                # Filtrage par rôle si demandé et si la colonne existe
                if role and 'role' in available_columns:
                    where_conditions.append('role = :role')
                    params['role'] = role
                elif role and 'type_utilisateur' in available_columns:
                    where_conditions.append('type_utilisateur = :role')
                    params['role'] = role
                
                # Ajouter tenant_id seulement si la colonne existe
                if 'tenant_id' in available_columns:
                    where_conditions.append("tenant_id = :tenant_id")
                    params['tenant_id'] = str(tenant_id)
                
                # Ajouter deleted_at seulement si la colonne existe
                if 'deleted_at' in available_columns:
                    where_conditions.append("deleted_at IS NULL")
                
                # Ajouter le filtre role si spécifié et si la colonne existe
                if role and 'role' in available_columns:
                    where_conditions.append("role = :role")
                    params['role'] = role
                
                # Construire la clause WHERE
                where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
                
                # Utiliser created_at pour l'ordre seulement si la colonne existe
                order_clause = "ORDER BY created_at DESC" if 'created_at' in available_columns else "ORDER BY id DESC" if 'id' in available_columns else ""
                
                query = f"""
                    SELECT * FROM azalplus.{module_name}
                    WHERE {where_clause}
                    {order_clause}
                    LIMIT :limit OFFSET :offset
                """
                
                result = session.execute(text(query), params)
                records = [dict(row._mapping) for row in result.fetchall()]
                
                # Compter le total
                count_query = f"""
                    SELECT COUNT(*) FROM azalplus.{module_name}
                    WHERE {where_clause}
                """
                count_params = {k: v for k, v in params.items() if k not in ['limit', 'offset']}
                count_result = session.execute(text(count_query), count_params)
                total = count_result.scalar()
                
                return {
                    "data": records,
                    "total": total,
                    "limit": limit,
                    "offset": offset
                }
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des enregistrements {module_name}", error=str(e))
            raise HTTPException(status_code=500, detail="Erreur interne du serveur")
    
    @legacy_router.get(f"/{module_name}/{{record_id}}")
    async def get_module_record(
        record_id: UUID,
        tenant_id: UUID = Depends(get_current_tenant),
        user_id: UUID = Depends(get_current_user_id)
    ):
        """Récupère un enregistrement spécifique par ID"""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                
                # Vérifier si la table existe
                table_check = f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'azalplus' 
                        AND table_name = '{module_name}'
                    )
                """
                
                table_exists_result = session.execute(text(table_check))
                table_exists = table_exists_result.scalar()
                
                if not table_exists:
                    raise HTTPException(status_code=404, detail=f"Module {module_name} not found")
                
                # Récupérer l'enregistrement
                query = f"""
                    SELECT * FROM azalplus.{module_name}
                    WHERE id = :record_id
                    AND tenant_id = :tenant_id
                    AND deleted_at IS NULL
                """
                
                result = session.execute(text(query), {
                    'record_id': str(record_id),
                    'tenant_id': str(tenant_id)
                })
                
                record = result.fetchone()
                if not record:
                    raise HTTPException(status_code=404, detail=f"{module_name} record not found")
                
                # Convertir en dictionnaire
                record_dict = dict(record._mapping)
                
                # Traitement des champs JSON et dates
                for key, value in record_dict.items():
                    if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                        try:
                            record_dict[key] = json.loads(value)
                        except:
                            pass
                    elif isinstance(value, (datetime, date)):
                        record_dict[key] = value.isoformat()
                
                return record_dict
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'enregistrement {module_name}", error=str(e))
            raise HTTPException(status_code=500, detail="Erreur interne du serveur")
    
    @legacy_router.get(f"/{module_name}")
    async def get_module_records(
        request: Request,
        limit: int = Query(50, description="Nombre maximum de résultats"),
        offset: int = Query(0, description="Décalage pour la pagination"),
        search: Optional[str] = Query(None, description="Recherche textuelle"),
        order_by: Optional[str] = Query(None, description="Champ de tri"),
        order_dir: str = Query("asc", description="Direction du tri"),
        tenant_id: UUID = Depends(get_current_tenant),
        user_id: UUID = Depends(get_current_user_id)
    ):
        """Récupère les enregistrements d'un module"""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                
                # Vérifier si la table existe avant de faire la requête
                table_check = f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'azalplus' 
                        AND table_name = '{module_name}'
                    )
                """
                
                table_exists_result = session.execute(text(table_check))
                table_exists = table_exists_result.scalar()
                
                if not table_exists:
                    return {
                        "data": [],
                        "total": 0,
                        "limit": limit,
                        "offset": offset,
                        "warning": f"Table {module_name} does not exist"
                    }
                
                # Construction de la requête de base
                base_query = f"""
                    SELECT * FROM azalplus.{module_name}
                    WHERE tenant_id = :tenant_id
                    AND deleted_at IS NULL
                """""
                
                params = {"tenant_id": str(tenant_id)}
                
                # Ajout de la recherche si fournie
                if search:
                    # Recherche simple sur les champs texte courants
                    search_conditions = []
                    text_fields = ['nom', 'libelle', 'title', 'name', 'description']
                    
                    # Vérifier quels champs existent réellement dans la table
                    try:
                        field_check_query = f"""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_schema = 'azalplus' 
                            AND table_name = '{module_name}'
                            AND column_name IN ('nom', 'libelle', 'title', 'name', 'description')
                        """
                        existing_fields_result = session.execute(text(field_check_query))
                        existing_fields = [row[0] for row in existing_fields_result.fetchall()]
                        
                        for field in existing_fields:
                            search_conditions.append(f"{field} ILIKE :search")
                        
                        if search_conditions:
                            base_query += f" AND ({' OR '.join(search_conditions)})"
                            params['search'] = f"%{search}%"
                    except Exception as e:
                        logger.warning(f"Search field check failed for {module_name}: {e}")
                
                # Ajout de la pagination
                base_query += f" ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                params.update({"limit": limit, "offset": offset})
                
                result = session.execute(text(base_query), params)
                records = [dict(row._mapping) for row in result.fetchall()]
                
                # Compter le total pour la pagination
                count_query = f"""
                    SELECT COUNT(*) as total FROM azalplus.{module_name}
                    WHERE tenant_id = :tenant_id AND deleted_at IS NULL
                """
                if search and search_conditions:
                    count_query += f" AND ({' OR '.join(search_conditions)})"
                
                count_result = session.execute(text(count_query), params)
                total = count_result.scalar()
                
                return {
                    "data": records,
                    "total": total,
                    "limit": limit,
                    "offset": offset
                }
                
        except Exception as e:
            logger.error(f"{module_name}_get_error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    
    @legacy_router.post(f"/{module_name}")
    async def create_module_record(
        data: Dict[str, Any] = Body(...),
        tenant_id: UUID = Depends(get_current_tenant),
        user_id: UUID = Depends(get_current_user_id)
    ):
        """Crée un nouvel enregistrement"""
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                import uuid
                
                # Ajouter les métadonnées système
                record_data = data.copy()
                record_data.update({
                    'id': str(uuid.uuid4()),
                    'tenant_id': str(tenant_id),
                    'created_by': str(user_id),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
                
                # Construction de la requête d'insertion
                columns = list(record_data.keys())
                placeholders = [f":{col}" for col in columns]
                
                insert_query = f"""
                    INSERT INTO azalplus.{module_name} ({', '.join(columns)})
                    VALUES ({', '.join(placeholders)})
                    RETURNING *
                """
                
                result = session.execute(text(insert_query), record_data)
                session.commit()
                
                created_record = dict(result.fetchone()._mapping)
                return {"data": created_record}
                
        except Exception as e:
            logger.error(f"{module_name}_create_error", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    
    _dynamic_endpoints_cache[module_name] = True

# Créer automatiquement les endpoints pour les modules GED
create_module_endpoints("ged_dossiers")
create_module_endpoints("ged_documents")

# Initialiser les endpoints pour les modules système
for module in SYSTEM_MODULES:
    create_module_endpoints(module)

# Fonction pour obtenir les routeurs (utilisée dans main.py)
def get_routers():
    """Retourne les routeurs à inclure dans l'application"""
    return [legacy_router, admin_router]


@admin_router.get("/users/me/modules")
async def get_user_modules(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère les modules accessibles à l'utilisateur connecté"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Récupérer les modules actifs pour le tenant
            sql = text("""
                SELECT m.name, m.label, m.icon, m.is_active
                FROM azalplus.modules m
                WHERE m.tenant_id = :tenant_id 
                AND m.is_active = true
                AND m.deleted_at IS NULL
                ORDER BY m.label
            """)
            
            result = session.execute(sql, {"tenant_id": str(tenant_id)})
            modules = result.fetchall()
            
            # Convertir en liste de dictionnaires
            modules_list = []
            for module in modules:
                modules_list.append({
                    "name": module.name,
                    "label": module.label,
                    "icon": module.icon,
                    "is_active": module.is_active
                })
            
            return {"modules": modules_list}
            
    except Exception as e:
        logger.error("get_user_modules_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/calendar/workload")
async def get_calendar_workload(
    year: int = Query(..., description="Année"),
    month: int = Query(..., description="Mois"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Calcule la charge de travail par jour pour un mois donné.

    Inclut:
    - Temps de trajet (calculé dynamiquement depuis le lieu précédent ou l'entreprise)
    - Durée des interventions
    - Durée des RDV agenda

    Retourne un dict avec pour chaque jour:
    - total_minutes: temps total (trajet + travail)
    - travel_minutes: temps de trajet
    - work_minutes: temps de travail
    - events_count: nombre d'événements
    """
    try:
        # Implémentation temporaire - retourner une charge de travail vide
        # TODO: Implémenter calculate_calendar_workload quand le module sera disponible
        workload = {}
        return {"workload": workload, "year": year, "month": month}
    except Exception as e:
        logger.error("calendar_workload_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/favoris")
async def get_favoris(
    limit: int = Query(10, description="Nombre maximum de résultats"),
    order_by: str = Query("created_at", description="Champ de tri"),
    order_dir: str = Query("desc", description="Direction du tri"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère les favoris de l'utilisateur"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Récupérer les favoris de l'utilisateur
            direction = "DESC" if order_dir.lower() == "desc" else "ASC"
            sql = text(f"""
                SELECT f.id, f.module_name, f.record_id, f.title, f.created_at
                FROM azalplus.favoris f
                WHERE f.tenant_id = :tenant_id 
                AND f.user_id = :user_id
                AND f.deleted_at IS NULL
                ORDER BY f.{order_by} {direction}
                LIMIT :limit
            """)
            
            result = session.execute(sql, {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "limit": limit
            })
            favoris = result.fetchall()
            
            # Convertir en liste de dictionnaires
            favoris_list = []
            for fav in favoris:
                favoris_list.append({
                    "id": str(fav.id),
                    "module_name": fav.module_name,
                    "record_id": str(fav.record_id),
                    "title": fav.title,
                    "created_at": fav.created_at.isoformat() if fav.created_at else None
                })
            
            return {"favoris": favoris_list, "total": len(favoris_list)}
            
    except Exception as e:
        logger.error("get_favoris_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/agenda")
async def get_agenda(
    date_debut_gte: Optional[datetime] = Query(None, description="Date de début minimum"),
    date_debut_lt: Optional[datetime] = Query(None, description="Date de début maximum"),
    order_by: str = Query("date_debut", description="Champ de tri"),
    order_dir: str = Query("asc", description="Direction du tri"),
    limit: int = Query(50, description="Nombre maximum de résultats"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère les événements d'agenda pour une période donnée"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Construction de la requête avec filtres optionnels
            where_conditions = ["tenant_id = :tenant_id", "deleted_at IS NULL"]
            params = {"tenant_id": str(tenant_id)}
            
            if date_debut_gte:
                where_conditions.append("date_debut >= :date_debut_gte")
                params["date_debut_gte"] = date_debut_gte
                
            if date_debut_lt:
                where_conditions.append("date_debut < :date_debut_lt")
                params["date_debut_lt"] = date_debut_lt
            
            where_clause = " AND ".join(where_conditions)
            order_clause = f"ORDER BY {order_by} {order_dir.upper()}"
            
            sql = text(f"""
                SELECT id, titre, description, date_debut, date_fin, 
                       lieu, type_evenement, statut, created_at, updated_at
                FROM azalplus.agenda
                WHERE {where_clause}
                {order_clause}
                LIMIT :limit
            """)
            
            params["limit"] = limit
            result = session.execute(sql, params)
            events = result.fetchall()
            
            # Convertir en liste de dictionnaires
            events_list = []
            for event in events:
                events_list.append({
                    "id": str(event.id),
                    "titre": event.titre,
                    "description": event.description,
                    "date_debut": event.date_debut.isoformat() if event.date_debut else None,
                    "date_fin": event.date_fin.isoformat() if event.date_fin else None,
                    "lieu": event.lieu,
                    "type_evenement": event.type_evenement,
                    "statut": event.statut,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                    "updated_at": event.updated_at.isoformat() if event.updated_at else None
                })
            
            return {"events": events_list, "total": len(events_list)}
            
    except Exception as e:
        logger.error("get_agenda_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/favoris")
async def get_favoris(
    limit: int = Query(10, description="Nombre maximum de résultats"),
    order_by: str = Query("created_at", description="Champ de tri"),
    order_dir: str = Query("desc", description="Direction du tri"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère la liste des favoris de l'utilisateur"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Récupérer les favoris pour l'utilisateur
            sql = text(f"""
                SELECT id, module_name, record_id, title, created_at
                FROM azalplus.favoris
                WHERE tenant_id = :tenant_id 
                AND user_id = :user_id
                AND deleted_at IS NULL
                ORDER BY {order_by} {order_dir}
                LIMIT :limit
            """)
            
            result = session.execute(sql, {
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "limit": limit
            })
            favoris = result.fetchall()
            
            # Convertir en liste de dictionnaires
            favoris_list = []
            for fav in favoris:
                favoris_list.append({
                    "id": str(fav.id),
                    "module_name": fav.module_name,
                    "record_id": str(fav.record_id),
                    "title": fav.title,
                    "created_at": fav.created_at.isoformat() if fav.created_at else None
                })
            
            return {"favoris": favoris_list}
            
    except Exception as e:
        logger.error("get_favoris_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/donneur_ordre")
async def search_donneur_ordre(
    search: str = Query("", description="Terme de recherche"),
    limit: int = Query(10, description="Nombre maximum de résultats"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Recherche des donneurs d'ordre par nom"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Nettoyer le terme de recherche
            search_term = search.strip()
            
            if not search_term:
                return {"donneur_ordre": []}
            
            sql = text("""
                SELECT id, nom, email, telephone
                FROM azalplus.donneur_ordre
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (LOWER(nom) LIKE LOWER(:search) OR LOWER(email) LIKE LOWER(:search))
                ORDER BY nom
                LIMIT :limit
            """)
            
            result = session.execute(sql, {
                "tenant_id": str(tenant_id),
                "search": f"%{search_term}%",
                "limit": limit
            })
            
            donneurs = []
            for row in result.fetchall():
                donneurs.append({
                    "id": str(row.id),
                    "nom": row.nom,
                    "email": row.email,
                    "telephone": row.telephone
                })
            
            return {"donneur_ordre": donneurs}
            
    except Exception as e:
        logger.error("search_donneur_ordre_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/clients")
async def search_clients(
    search: str = Query("", description="Terme de recherche"),
    limit: int = Query(10, description="Nombre maximum de résultats"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Recherche des clients par nom/prénom"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Nettoyer le terme de recherche
            search_term = search.strip()
            
            if not search_term:
                return {"clients": []}
            
            sql = text("""
                SELECT id, name, contact_name, email, phone, adresse1, cp, ville
                FROM azalplus.clients
                WHERE tenant_id = :tenant_id
                AND deleted_at IS NULL
                AND (LOWER(name || ' ' || COALESCE(contact_name, '')) LIKE LOWER(:search)
                     OR LOWER(contact_name || ' ' || name) LIKE LOWER(:search)
                     OR LOWER(name) LIKE LOWER(:search)
                     OR LOWER(contact_name) LIKE LOWER(:search))
                ORDER BY name, contact_name
                LIMIT :limit
            """)
            
            result = session.execute(sql, {
                "tenant_id": str(tenant_id),
                "search": f"%{search_term}%",
                "limit": limit
            })
            
            clients = []
            for row in result.fetchall():
                clients.append({
                    "id": str(row.id),
                    "nom": row.name,
                    "prenom": row.contact_name,
                    "email": row.email,
                    "telephone": row.phone,
                    "adresse1": row.adresse1,
                    "cp": row.cp,
                    "ville": row.ville,
                    "display_name": f"{row.name} {row.contact_name or ''}".strip()
                })
            
            return {"clients": clients}

    except Exception as e:
        logger.error("search_clients_error", error=str(e), search=search)
        raise HTTPException(status_code=500, detail=str(e))


class ClientCreate(BaseModel):
    """Schéma pour créer un client rapidement."""
    nom: str
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    adresse1: Optional[str] = None
    adresse2: Optional[str] = None
    cp: Optional[str] = None
    ville: Optional[str] = None

    class Config:
        extra = "allow"


@legacy_router.post("/clients", status_code=201)
async def create_client(
    data: ClientCreate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Crée un nouveau client rapidement."""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            from uuid import uuid4

            client_id = uuid4()

            sql = text("""
                INSERT INTO azalplus.clients (
                    id, tenant_id, name, contact_name, phone, email,
                    adresse1, adresse2, cp, ville,
                    created_at, updated_at, created_by
                ) VALUES (
                    :id, :tenant_id, :name, :contact_name, :phone, :email,
                    :adresse1, :adresse2, :cp, :ville,
                    NOW(), NOW(), :created_by
                )
                RETURNING id, name, contact_name, phone, email, adresse1, cp, ville
            """)

            result = session.execute(sql, {
                "id": str(client_id),
                "tenant_id": str(tenant_id),
                "name": data.nom,
                "contact_name": data.prenom,
                "phone": data.telephone,
                "email": data.email,
                "adresse1": data.adresse1,
                "adresse2": data.adresse2,
                "cp": data.cp,
                "ville": data.ville,
                "created_by": str(user_id)
            })
            session.commit()

            row = result.fetchone()
            return {
                "id": str(row.id),
                "nom": row.name,
                "prenom": row.contact_name,
                "telephone": row.phone,
                "email": row.email,
                "adresse1": row.adresse1,
                "cp": row.cp,
                "ville": row.ville,
                "contact_name": f"{row.name} {row.contact_name or ''}".strip()
            }

    except Exception as e:
        logger.error("create_client_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/clients/{client_id}")
async def get_client_by_id(
    client_id: UUID = Path(..., description="ID du client"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère un client par son ID"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text

            sql = text("""
                SELECT id, name, contact_name, email, phone, adresse1, adresse2, cp, ville
                FROM azalplus.clients
                WHERE id = :client_id
                AND tenant_id = :tenant_id
                AND deleted_at IS NULL
            """)

            result = session.execute(sql, {
                "client_id": str(client_id),
                "tenant_id": str(tenant_id)
            })
            client = result.fetchone()

            if not client:
                raise HTTPException(status_code=404, detail="Client non trouvé")

            return {
                "id": str(client.id),
                "nom": client.name,
                "prenom": client.contact_name,
                "email": client.email,
                "telephone": client.phone,
                "adresse1": client.adresse1,
                "adresse2": client.adresse2,
                "cp": client.cp,
                "ville": client.ville,
                "contact_name": f"{client.name} {client.contact_name or ''}".strip()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_client_error", error=str(e), client_id=str(client_id))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/utilisateurs")
async def get_utilisateurs(
    search: Optional[str] = Query(None, description="Recherche"),
    role: Optional[str] = Query(None, description="Filtrer par rôle"),
    limit: int = Query(50, description="Limite"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Récupère la liste des utilisateurs"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text

            conditions = ["tenant_id = :tenant_id", "actif = true"]
            params = {"tenant_id": str(tenant_id), "limit": limit}

            if role:
                conditions.append("LOWER(role) = LOWER(:role)")
                params["role"] = role

            if search:
                conditions.append("(LOWER(nom || ' ' || COALESCE(prenom, '')) LIKE LOWER(:search) OR LOWER(email) LIKE LOWER(:search))")
                params["search"] = f"%{search}%"

            where_clause = " AND ".join(conditions)

            sql = text(f"""
                SELECT id, nom, prenom, email, telephone, role, avatar_url
                FROM azalplus.utilisateurs
                WHERE {where_clause}
                ORDER BY nom, prenom
                LIMIT :limit
            """)

            result = session.execute(sql, params)

            utilisateurs = []
            for row in result.fetchall():
                utilisateurs.append({
                    "id": str(row.id),
                    "nom": row.nom,
                    "prenom": row.prenom,
                    "email": row.email,
                    "telephone": row.telephone,
                    "role": row.role,
                    "avatar_url": row.avatar_url,
                    "display_name": f"{row.prenom or ''} {row.nom or ''}".strip()
                })

            return {"utilisateurs": utilisateurs, "items": utilisateurs, "total": len(utilisateurs)}

    except Exception as e:
        logger.error("get_utilisateurs_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/comptescomptables")
async def get_comptes_comptables(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Endpoint de compatibilité pour récupérer les comptes comptables"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            sql = text("""
                SELECT id, numero, libelle, type_compte, actif
                FROM azalplus.comptescomptables
                WHERE tenant_id = :tenant_id 
                AND deleted_at IS NULL
                ORDER BY numero
            """)
            
            result = session.execute(sql, {"tenant_id": str(tenant_id)})
            comptes = result.fetchall()
            
            # Convertir en liste de dictionnaires
            comptes_list = []
            for compte in comptes:
                comptes_list.append({
                    "id": str(compte.id),
                    "numero": compte.numero,
                    "libelle": compte.libelle,
                    "type_compte": compte.type_compte,
                    "actif": compte.actif
                })
            
            return {"data": comptes_list}
            
    except Exception as e:
        logger.error("get_comptes_comptables_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/interventions/{intervention_id}")
async def get_intervention_by_id(
    intervention_id: str = Path(...),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Endpoint de compatibilité pour récupérer une intervention par ID"""
    try:
        # Valider manuellement l'UUID
        try:
            uuid_obj = UUID(intervention_id)
        except ValueError:
            logger.error("invalid_uuid", intervention_id=intervention_id)
            raise HTTPException(status_code=400, detail=f"UUID invalide: {intervention_id}")
            
        with Database.get_session() as session:
            from sqlalchemy import text
            
            sql = text("""
                SELECT * FROM azalplus.interventions
                WHERE id = :intervention_id 
                AND tenant_id = :tenant_id 
                AND deleted_at IS NULL
            """)
            
            result = session.execute(sql, {
                "intervention_id": str(intervention_id),
                "tenant_id": str(tenant_id)
            })
            intervention = result.fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            # Convertir les données en dict et nettoyer les valeurs
            data = dict(intervention._mapping)
            
            # Nettoyer les valeurs None et convertir les types
            cleaned_data = {}
            for key, value in data.items():
                if value is not None:
                    # Convertir les dates en string ISO
                    if isinstance(value, (datetime, date)):
                        cleaned_data[key] = value.isoformat()
                    # Convertir les UUID en string
                    elif hasattr(value, '__str__') and 'uuid' in str(type(value)).lower():
                        cleaned_data[key] = str(value)
                    else:
                        cleaned_data[key] = value
                else:
                    cleaned_data[key] = None
            
            return cleaned_data
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur dans get_intervention_by_id: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.put("/interventions/{intervention_id}")
async def update_intervention(
    intervention_id: str = Path(...),
    data: Dict[str, Any] = Body(...),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Met à jour une intervention"""
    try:
        # Valider l'UUID
        try:
            uuid_obj = UUID(intervention_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"UUID invalide: {intervention_id}")

        # Vérifier que l'intervention existe
        existing = Database.get_by_id("interventions", tenant_id, uuid_obj)
        if not existing:
            raise HTTPException(status_code=404, detail="Intervention non trouvée")

        # Nettoyer les données (supprimer les valeurs None et champs système)
        fields_to_skip = ['id', 'tenant_id', 'created_at', 'created_by', 'deleted_at']
        update_data = {k: v for k, v in data.items() if k not in fields_to_skip}

        if not update_data:
            raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")

        # Mettre à jour
        updated = Database.update("interventions", tenant_id, uuid_obj, update_data, user_id)
        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur update_intervention: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/entreprise")
async def get_entreprises(
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Endpoint pour récupérer les entreprises"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            
            sql = text("""
                SELECT * FROM azalplus.entreprises
                WHERE tenant_id = :tenant_id 
                AND deleted_at IS NULL
                ORDER BY nom
            """)
            
            result = session.execute(sql, {"tenant_id": str(tenant_id)})
            entreprises = result.fetchall()
            
            # Convertir en liste de dictionnaires
            data = []
            for entreprise in entreprises:
                item = dict(entreprise._mapping)
                # Nettoyer les valeurs
                cleaned_item = {}
                for key, value in item.items():
                    if value is not None:
                        if isinstance(value, (datetime, date)):
                            cleaned_item[key] = value.isoformat()
                        elif hasattr(value, '__str__') and 'uuid' in str(type(value)).lower():
                            cleaned_item[key] = str(value)
                        else:
                            cleaned_item[key] = value
                    else:
                        cleaned_item[key] = None
                data.append(cleaned_item)
            
            return data
            
    except Exception as e:
        logger.error(f"Erreur dans get_entreprises: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.post("/entreprise")
async def create_entreprise(
    request: Request,
    data: Dict[str, Any] = Body(...),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Endpoint pour créer une nouvelle entreprise"""
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            import uuid
            
            # Générer un nouvel ID
            new_id = str(uuid.uuid4())
            
            # Préparer les données de base
            base_data = {
                "id": new_id,
                "tenant_id": str(tenant_id),
                "created_by": str(user_id),
                "updated_by": str(user_id),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Ajouter les données du formulaire
            for key, value in data.items():
                if key not in base_data and value is not None:
                    base_data[key] = value
            
            # Construire la requête d'insertion
            columns = ", ".join(base_data.keys())
            placeholders = ", ".join([f":{k}" for k in base_data.keys()])
            
            sql = text(f"""
                INSERT INTO azalplus.entreprises ({columns})
                VALUES ({placeholders})
                RETURNING *
            """)
            
            result = session.execute(sql, base_data)
            session.commit()
            
            created = result.fetchone()
            if created:
                return {"id": new_id, "success": True}
            else:
                raise HTTPException(status_code=500, detail="Erreur lors de la création")
                
    except Exception as e:
        logger.error(f"Erreur dans create_entreprise: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@legacy_router.get("/interventions")
async def get_interventions(
    request: Request,
    date_debut_gte: Optional[str] = Query(None),
    date_debut_lt: Optional[str] = Query(None),
    date_prevue_debut_gte: Optional[str] = Query(None),
    date_prevue_debut_lt: Optional[str] = Query(None),
    order_by: str = Query("date_prevue_debut"),
    order_dir: str = Query("asc"),
    limit: int = Query(50),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id)
):
    """Endpoint de compatibilité pour les interventions"""
    try:
        # Parser les paramètres de date (supporte les deux noms)
        filters = {}
        # Support date_prevue_debut (nouveau) et date_debut (ancien)
        gte_value = date_prevue_debut_gte or date_debut_gte
        lt_value = date_prevue_debut_lt or date_debut_lt

        if gte_value:
            date_str = gte_value.replace('%3A', ':')
            filters['date_prevue_debut_gte'] = datetime.fromisoformat(date_str.replace('Z', ''))
        if lt_value:
            date_str = lt_value.replace('%3A', ':')
            filters['date_prevue_debut_lt'] = datetime.fromisoformat(date_str.replace('Z', ''))
        
        # Utiliser la base de données pour récupérer les interventions
        with Database.get_session() as session:
            from sqlalchemy import text
            
            # Construire la requête SQL
            where_conditions = ["tenant_id = :tenant_id", "deleted_at IS NULL"]
            params = {"tenant_id": str(tenant_id)}
            
            if 'date_prevue_debut_gte' in filters:
                where_conditions.append("date_prevue_debut >= :date_prevue_debut_gte")
                params['date_prevue_debut_gte'] = filters['date_prevue_debut_gte']

            if 'date_prevue_debut_lt' in filters:
                where_conditions.append("date_prevue_debut < :date_prevue_debut_lt")
                params['date_prevue_debut_lt'] = filters['date_prevue_debut_lt']
            
            where_clause = " AND ".join(where_conditions)
            order_clause = f"ORDER BY {order_by} {order_dir.upper()}"

            sql_str = f"""
                SELECT * FROM azalplus.interventions
                WHERE {where_clause}
                {order_clause}
                LIMIT :limit
            """
            sql = text(sql_str)
            params['limit'] = limit

            # Debug log
            logger.debug("legacy_interventions_query", filters=filters, where=where_clause, sql=sql_str.strip()[:200], params=params)

            result = session.execute(sql, params)
            interventions = [dict(row._mapping) for row in result.fetchall()]

            logger.debug("legacy_interventions_result", count=len(interventions))

            return {"items": interventions, "total": len(interventions)}
            
    except Exception as e:
        logger.error(f"Erreur dans get_interventions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Auto-numbering configuration
# =============================================================================
AUTO_NUMBER_CONFIG = {
    # Format: module_name -> (prefix, field_name, include_year)
    "interventions": ("INT", "numero", True, True),  # include_year=True, include_month=True
    "clients": ("CLI", "code", False),
    "fournisseurs": ("FOU", "code", False),
    "donneur_ordre": ("DO", "code", False),
    "devis": ("DEV", "numero", True),
    "factures": ("FAC", "number", True),
    "avoirs": ("AVO", "numero", True),
    "bons_livraison": ("BL", "numero", True),
    "commandes": ("CMD", "numero", True),
    "projets": ("PRJ", "code", False),
    "contrats": ("CTR", "numero", True),
    "produits": ("PRD", "code", False),
    "tickets": ("TKT", "numero", True),
    "modeles_email": ("TPL", "code", False),
}


def generate_auto_number(module_name: str, tenant_id: UUID) -> Optional[str]:
    """
    Génère automatiquement un numéro unique pour un module.
    Format: PREFIX-YYYY-XXXXX ou PREFIX-XXXXX selon la config.
    """
    try:
        config = AUTO_NUMBER_CONFIG.get(module_name.lower())
        if not config:
            return None

        # Config: (prefix, field_name, include_year, include_month=False)
        if len(config) == 4:
            prefix, field_name, include_year, include_month = config
        else:
            prefix, field_name, include_year = config
            include_month = False
        year = datetime.now().year
        month = datetime.now().month

        # Récupérer le dernier numéro pour ce module/tenant
        with Database.get_session() as session:
            from sqlalchemy import text

            # Vérifier que la table existe avant d'exécuter la requête
            check_table_sql = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'azalplus'
                    AND table_name = :table_name
                )
            """)
            table_exists = session.execute(check_table_sql, {"table_name": module_name}).scalar()

            if not table_exists:
                logger.warning(f"Table azalplus.{module_name} n'existe pas, auto-numbering ignoré")
                return None

            # Vérifier que le champ existe dans la table
            check_column_sql = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'azalplus'
                    AND table_name = :table_name
                    AND column_name = :column_name
                )
            """)
            column_exists = session.execute(check_column_sql, {
                "table_name": module_name,
                "column_name": field_name
            }).scalar()

            if not column_exists:
                logger.warning(f"Colonne {field_name} n'existe pas dans azalplus.{module_name}, auto-numbering ignoré")
                return None

            if include_year and include_month:
                # Chercher le dernier numéro du mois en cours (format: INT-YYYYMM-XXXX)
                pattern = f"{prefix}-{year}{month:02d}-%"
            elif include_year:
                # Chercher le dernier numéro de l'année en cours
                pattern = f"{prefix}-{year}-%"
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
            if include_year and include_month:
                return f"{prefix}-{year}{month:02d}-{seq:04d}"
            elif include_year:
                return f"{prefix}-{year}-{seq:05d}"
            else:
                return f"{prefix}-{seq:05d}"

    except Exception as e:
        logger.error(f"Erreur lors de la génération du numéro automatique pour {module_name}: {str(e)}")
        return None

# =============================================================================
# API Router v1
# =============================================================================
router_v1 = APIRouter()  # Routes à /api/{module}


# =============================================================================
# Response Models
# =============================================================================

class BulkOperationResponse(BaseModel):
    """Response for bulk operations."""
    success: int = Field(..., description="Nombre d'operations reussies")
    errors: int = Field(0, description="Nombre d'erreurs")
    messages: List[str] = Field(default_factory=list, description="Messages d'erreur")


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
        module_acces = self.module.acces  # Capturer localement pour les closures
        is_createur_only = (module_acces == "createur_only")

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
            """Liste les enregistrements avec pagination et filtres dynamiques.

            Filtres supportes via query params:
            - ?champ=valeur : filtre exact
            - ?champ_gte=valeur : >= (greater than or equal)
            - ?champ_lte=valeur : <= (less than or equal)
            - ?champ_lt=valeur : < (less than)
            - ?champ_gt=valeur : > (greater than)
            - ?champ_like=valeur : LIKE %valeur%
            """

            # Extraire les filtres dynamiques des query params
            filters = {}
            reserved_params = {'skip', 'limit', 'order_by', 'order_dir'}

            for key, value in request.query_params.items():
                if key in reserved_params:
                    continue

                # Operateurs de comparaison
                if key.endswith('_gte'):
                    field = key[:-4]
                    filters[f"{field}__gte"] = value
                elif key.endswith('_lte'):
                    field = key[:-4]
                    filters[f"{field}__lte"] = value
                elif key.endswith('_gt'):
                    field = key[:-3]
                    filters[f"{field}__gt"] = value
                elif key.endswith('_lt'):
                    field = key[:-3]
                    filters[f"{field}__lt"] = value
                elif key.endswith('_like'):
                    field = key[:-5]
                    filters[f"{field}__like"] = value
                else:
                    # Filtre exact
                    filters[key] = value

            order = f"{order_by} {order_dir.upper()}"

            # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
            query_tenant_id = SYSTEM_TENANT_ID if is_createur_only else tenant_id

            items = Database.query(
                self.table_name,
                query_tenant_id,
                filters=filters if filters else None,
                limit=limit + 1,  # +1 to check if has_more
                offset=skip,
                order_by=order
            )

            has_more = len(items) > limit
            if has_more:
                items = items[:limit]

            # Get total count
            total = Database.count(self.table_name, query_tenant_id)

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

            # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
            query_tenant_id = SYSTEM_TENANT_ID if is_createur_only else tenant_id
            item = Database.get_by_id(self.table_name, query_tenant_id, item_id)
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

            # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
            query_tenant_id = SYSTEM_TENANT_ID if is_createur_only else tenant_id
            items = Database.query(
                self.table_name,
                query_tenant_id,
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

            # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
            query_tenant_id = SYSTEM_TENANT_ID if is_createur_only else tenant_id
            items = Database.query(
                self.table_name,
                query_tenant_id,
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
