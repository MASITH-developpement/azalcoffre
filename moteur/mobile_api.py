# =============================================================================
# AZALPLUS - Mobile API
# =============================================================================
"""
API endpoints pour l'application mobile AZALPLUS.

Endpoints:
    /api/v1/mobile/config     - Configuration mobile du tenant
    /api/v1/mobile/bootstrap  - Initialisation complete de l'app
    /api/v1/mobile/modules    - Liste des modules disponibles
    /api/v1/mobile/config/reset - Reset de la configuration
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
import structlog

from .db import Database
from .parser import ModuleParser
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth, require_role

logger = structlog.get_logger()

# =============================================================================
# Router Mobile API
# =============================================================================
router_mobile = APIRouter(
    prefix="/mobile",
    tags=["Mobile"]
)


# =============================================================================
# Pydantic Models - Request
# =============================================================================

class MobileConfigUpdate(BaseModel):
    """Mise a jour partielle de la configuration mobile."""

    # Apparence
    theme: Optional[str] = Field(None, description="Theme de l'app (light/dark/system)")
    primary_color: Optional[str] = Field(None, description="Couleur primaire (hex)")
    logo_url: Optional[str] = Field(None, description="URL du logo tenant")

    # Fonctionnalites
    offline_enabled: Optional[bool] = Field(None, description="Mode hors-ligne active")
    sync_interval_minutes: Optional[int] = Field(None, ge=1, le=1440, description="Intervalle de synchronisation")
    max_offline_days: Optional[int] = Field(None, ge=1, le=30, description="Duree max hors-ligne")

    # Modules actifs sur mobile
    enabled_modules: Optional[List[str]] = Field(None, description="Modules actifs sur mobile")

    # Notifications
    push_notifications_enabled: Optional[bool] = Field(None, description="Notifications push actives")
    notification_types: Optional[List[str]] = Field(None, description="Types de notifications actives")

    # Securite
    biometric_auth_enabled: Optional[bool] = Field(None, description="Auth biometrique activee")
    session_timeout_minutes: Optional[int] = Field(None, ge=5, le=480, description="Timeout de session")
    pin_required: Optional[bool] = Field(None, description="PIN requis pour l'app")

    # Performance
    cache_ttl_minutes: Optional[int] = Field(None, ge=1, le=60, description="TTL du cache local")
    max_items_per_page: Optional[int] = Field(None, ge=10, le=100, description="Items par page")

    class Config:
        json_schema_extra = {
            "example": {
                "theme": "dark",
                "offline_enabled": True,
                "sync_interval_minutes": 15,
                "enabled_modules": ["clients", "factures", "temps"]
            }
        }


# =============================================================================
# Pydantic Models - Response
# =============================================================================

class MobileConfig(BaseModel):
    """Configuration mobile complete."""

    # Identifiants
    tenant_id: UUID = Field(..., description="ID du tenant")

    # Apparence
    theme: str = Field("system", description="Theme de l'app")
    primary_color: str = Field("#1976d2", description="Couleur primaire")
    logo_url: Optional[str] = Field(None, description="URL du logo")

    # Fonctionnalites
    offline_enabled: bool = Field(True, description="Mode hors-ligne")
    sync_interval_minutes: int = Field(15, description="Intervalle sync")
    max_offline_days: int = Field(7, description="Duree max hors-ligne")

    # Modules
    enabled_modules: List[str] = Field(default_factory=list, description="Modules actifs")

    # Notifications
    push_notifications_enabled: bool = Field(True, description="Notifications push")
    notification_types: List[str] = Field(
        default_factory=lambda: ["urgent", "mention", "assignment"],
        description="Types de notifications"
    )

    # Securite
    biometric_auth_enabled: bool = Field(False, description="Auth biometrique")
    session_timeout_minutes: int = Field(30, description="Timeout session")
    pin_required: bool = Field(False, description="PIN requis")

    # Performance
    cache_ttl_minutes: int = Field(5, description="TTL cache")
    max_items_per_page: int = Field(25, description="Items par page")

    # Metadata
    updated_at: Optional[datetime] = Field(None, description="Derniere modification")
    updated_by: Optional[UUID] = Field(None, description="Modifie par")

    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "theme": "dark",
                "primary_color": "#1976d2",
                "offline_enabled": True,
                "sync_interval_minutes": 15,
                "enabled_modules": ["clients", "factures", "temps"],
                "push_notifications_enabled": True
            }
        }


class UserInfo(BaseModel):
    """Informations utilisateur pour mobile."""

    id: UUID = Field(..., description="ID utilisateur")
    email: str = Field(..., description="Email")
    nom: str = Field(..., description="Nom")
    prenom: Optional[str] = Field(None, description="Prenom")
    role: str = Field(..., description="Role")
    avatar_url: Optional[str] = Field(None, description="URL avatar")


class TenantInfo(BaseModel):
    """Informations tenant pour mobile."""

    id: UUID = Field(..., description="ID tenant")
    code: str = Field(..., description="Code tenant")
    nom: str = Field(..., description="Nom du tenant")
    logo_url: Optional[str] = Field(None, description="URL logo")


class ModuleInfo(BaseModel):
    """Informations d'un module pour mobile."""

    name: str = Field(..., description="Nom technique du module")
    display_name: str = Field(..., description="Nom d'affichage")
    icon: Optional[str] = Field(None, description="Icone du module")
    menu: Optional[str] = Field(None, description="Menu parent")
    description: Optional[str] = Field(None, description="Description")
    fields_count: int = Field(0, description="Nombre de champs")
    fields: List[Dict[str, Any]] = Field(default_factory=list, description="Definition des champs")
    permissions: List[str] = Field(default_factory=list, description="Permissions requises")


class PermissionInfo(BaseModel):
    """Permissions utilisateur pour mobile."""

    role: str = Field(..., description="Role de l'utilisateur")
    modules: List[str] = Field(default_factory=list, description="Modules accessibles")
    actions: List[str] = Field(default_factory=list, description="Actions autorisees")
    special_permissions: List[str] = Field(default_factory=list, description="Permissions speciales")


class BootstrapResponse(BaseModel):
    """Reponse complete d'initialisation mobile."""

    user: UserInfo = Field(..., description="Informations utilisateur")
    tenant: TenantInfo = Field(..., description="Informations tenant")
    config: MobileConfig = Field(..., description="Configuration mobile")
    permissions: PermissionInfo = Field(..., description="Permissions utilisateur")
    modules: List[ModuleInfo] = Field(..., description="Modules disponibles")
    server_time: datetime = Field(..., description="Heure serveur pour sync")
    api_version: str = Field("1.0.0", description="Version de l'API")


class ModulesListResponse(BaseModel):
    """Liste des modules disponibles pour mobile."""

    modules: List[ModuleInfo] = Field(..., description="Modules disponibles")
    count: int = Field(..., description="Nombre de modules")


class ErrorDetail(BaseModel):
    """Detail d'erreur."""
    detail: str = Field(..., description="Message d'erreur")
    code: Optional[str] = Field(None, description="Code d'erreur")


# =============================================================================
# Configuration par defaut
# =============================================================================
DEFAULT_MOBILE_CONFIG = {
    "theme": "system",
    "primary_color": "#1976d2",
    "logo_url": None,
    "offline_enabled": True,
    "sync_interval_minutes": 15,
    "max_offline_days": 7,
    "enabled_modules": [],
    "push_notifications_enabled": True,
    "notification_types": ["urgent", "mention", "assignment"],
    "biometric_auth_enabled": False,
    "session_timeout_minutes": 30,
    "pin_required": False,
    "cache_ttl_minutes": 5,
    "max_items_per_page": 25
}


# =============================================================================
# Service Mobile
# =============================================================================
class MobileService:
    """Service pour la gestion de la configuration mobile."""

    @staticmethod
    def get_config(tenant_id: UUID) -> MobileConfig:
        """Recupere la configuration mobile du tenant."""

        try:
            with Database.get_session() as session:
                from sqlalchemy import text

                # Essayer de recuperer la config existante
                result = session.execute(
                    text("""
                        SELECT config_data, updated_at, updated_by
                        FROM azalplus.mobile_configurations
                        WHERE tenant_id = :tenant_id
                    """),
                    {"tenant_id": str(tenant_id)}
                )
                row = result.fetchone()

                if row:
                    config_data = row._mapping["config_data"] or {}
                    return MobileConfig(
                        tenant_id=tenant_id,
                        **{**DEFAULT_MOBILE_CONFIG, **config_data},
                        updated_at=row._mapping["updated_at"],
                        updated_by=row._mapping["updated_by"]
                    )

        except Exception as e:
            # Table n'existe pas ou autre erreur - retourner config par defaut
            logger.warning("mobile_config_db_error", error=str(e), tenant_id=str(tenant_id))

        # Retourner la config par defaut
        return MobileConfig(
            tenant_id=tenant_id,
            **DEFAULT_MOBILE_CONFIG
        )

    @staticmethod
    def update_config(tenant_id: UUID, user_id: UUID, updates: MobileConfigUpdate) -> MobileConfig:
        """Met a jour la configuration mobile du tenant."""

        # Filtrer les champs None
        update_data = updates.model_dump(exclude_none=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucune donnee a mettre a jour"
            )

        with Database.get_session() as session:
            from sqlalchemy import text
            import json

            # Recuperer la config existante
            result = session.execute(
                text("""
                    SELECT config_data FROM azalplus.mobile_configurations
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if row:
                # Merge avec la config existante
                existing_data = row._mapping["config_data"] or {}
                merged_data = {**existing_data, **update_data}

                session.execute(
                    text("""
                        UPDATE azalplus.mobile_configurations
                        SET config_data = :config_data,
                            updated_at = NOW(),
                            updated_by = :user_id
                        WHERE tenant_id = :tenant_id
                    """),
                    {
                        "tenant_id": str(tenant_id),
                        "config_data": json.dumps(merged_data),
                        "user_id": str(user_id)
                    }
                )
            else:
                # Creer une nouvelle config
                merged_data = {**DEFAULT_MOBILE_CONFIG, **update_data}

                session.execute(
                    text("""
                        INSERT INTO azalplus.mobile_configurations
                        (tenant_id, config_data, updated_at, updated_by)
                        VALUES (:tenant_id, :config_data, NOW(), :user_id)
                    """),
                    {
                        "tenant_id": str(tenant_id),
                        "config_data": json.dumps(merged_data),
                        "user_id": str(user_id)
                    }
                )

            session.commit()

        # Retourner la config mise a jour
        return MobileService.get_config(tenant_id)

    @staticmethod
    def reset_config(tenant_id: UUID, user_id: UUID) -> MobileConfig:
        """Remet la configuration aux valeurs par defaut."""

        with Database.get_session() as session:
            from sqlalchemy import text
            import json

            # Supprimer ou reinitialiser la config
            session.execute(
                text("""
                    DELETE FROM azalplus.mobile_configurations
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )
            session.commit()

        logger.info("mobile_config_reset", tenant_id=str(tenant_id), user_id=str(user_id))

        return MobileConfig(
            tenant_id=tenant_id,
            **DEFAULT_MOBILE_CONFIG
        )

    @staticmethod
    def get_user_info(user: dict) -> UserInfo:
        """Construit les informations utilisateur."""
        return UserInfo(
            id=UUID(str(user["id"])),
            email=user["email"],
            nom=user["nom"],
            prenom=user.get("prenom"),
            role=user["role"],
            avatar_url=user.get("avatar_url")
        )

    @staticmethod
    def get_tenant_info(tenant_id: UUID) -> TenantInfo:
        """Recupere les informations du tenant."""

        with Database.get_session() as session:
            from sqlalchemy import text

            result = session.execute(
                text("""
                    SELECT id, code, nom
                    FROM azalplus.tenants
                    WHERE id = :tenant_id AND actif = true
                """),
                {"tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tenant non trouve"
                )

            return TenantInfo(
                id=row._mapping["id"],
                code=row._mapping["code"],
                nom=row._mapping["nom"],
                logo_url=None  # Colonne pas encore dans la table
            )

    @staticmethod
    def get_user_permissions(user: dict) -> PermissionInfo:
        """Construit les permissions de l'utilisateur."""

        role = user.get("role", "user")

        # Permissions basees sur le role
        role_permissions = {
            "admin": {
                "modules": ["*"],  # Tous les modules
                "actions": ["read", "create", "update", "delete", "export", "import"],
                "special": ["admin_tenant", "admin_facturation"]
            },
            "manager": {
                "modules": ["clients", "produits", "devis", "factures", "interventions", "temps"],
                "actions": ["read", "create", "update", "delete", "export", "import"],
                "special": ["temps_approuver", "temps_facturer"]
            },
            "commercial": {
                "modules": ["clients", "produits", "devis"],
                "actions": ["read", "create", "update", "export"],
                "special": []
            },
            "technicien": {
                "modules": ["interventions", "clients", "temps"],
                "actions": ["read", "update"],
                "special": []
            },
            "comptable": {
                "modules": ["factures", "clients", "paiements"],
                "actions": ["read", "create", "update", "export"],
                "special": []
            },
            "user": {
                "modules": [],
                "actions": ["read"],
                "special": []
            }
        }

        perms = role_permissions.get(role, role_permissions["user"])

        # Check for per-user custom mobile modules configuration
        # If user has modules_mobile set, use it instead of role-based defaults
        user_modules_mobile = user.get("modules_mobile")
        if user_modules_mobile is not None:
            # User has custom mobile modules configured
            # Parse JSON if it's a string (from database)
            if isinstance(user_modules_mobile, str):
                import json
                try:
                    user_modules_mobile = json.loads(user_modules_mobile)
                except (json.JSONDecodeError, TypeError):
                    user_modules_mobile = None

            if user_modules_mobile is not None and isinstance(user_modules_mobile, list):
                # Use custom modules for this user
                return PermissionInfo(
                    role=role,
                    modules=user_modules_mobile,
                    actions=perms["actions"],
                    special_permissions=perms["special"]
                )

        # Fall back to role-based permissions
        return PermissionInfo(
            role=role,
            modules=perms["modules"],
            actions=perms["actions"],
            special_permissions=perms["special"]
        )

    @staticmethod
    def get_available_modules(user: dict, config: MobileConfig) -> List[ModuleInfo]:
        """Recupere les modules disponibles pour l'utilisateur sur mobile."""

        permissions = MobileService.get_user_permissions(user)
        modules = []

        # Parcourir tous les modules du systeme
        for module_name in ModuleParser.list_all():
            module = ModuleParser.get(module_name)

            if not module or not module.actif:
                continue

            # Verifier si le module est active pour mobile
            if config.enabled_modules and module_name not in config.enabled_modules:
                # Si une liste est definie, ne montrer que ceux-la
                # Sauf si la liste est vide (montrer tous)
                if config.enabled_modules:
                    continue

            # Verifier les permissions utilisateur
            if permissions.modules != ["*"] and module_name not in permissions.modules:
                continue

            # Construire la liste des champs
            fields = []
            for field_name, field_def in module.champs.items():
                fields.append({
                    "name": field_name,
                    "type": field_def.type,
                    "label": field_def.label or field_name,
                    "required": field_def.requis,
                    "options": field_def.enum_values if field_def.enum_values else None
                })

            modules.append(ModuleInfo(
                name=module.nom,
                display_name=module.nom_affichage or module.nom.title(),
                icon=module.icone,
                menu=module.menu,
                description=module.description,
                fields_count=len(module.champs),
                fields=fields,
                permissions=permissions.actions
            ))

        return modules


# =============================================================================
# Endpoints
# =============================================================================

@router_mobile.get(
    "/config",
    response_model=MobileConfig,
    summary="Recuperer la configuration mobile",
    description="""
Retourne la configuration mobile pour le tenant de l'utilisateur connecte.

La configuration inclut:
- Parametres d'apparence (theme, couleurs)
- Parametres de synchronisation (mode hors-ligne, intervalles)
- Modules actifs sur mobile
- Parametres de notifications
- Parametres de securite (biometrie, timeout)
- Parametres de performance (cache, pagination)
    """,
    responses={
        200: {"description": "Configuration mobile"},
        401: {"description": "Non authentifie", "model": ErrorDetail},
        403: {"description": "Acces refuse", "model": ErrorDetail}
    }
)
async def get_mobile_config(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> MobileConfig:
    """Recupere la configuration mobile du tenant."""

    logger.debug("mobile_config_get", tenant_id=str(tenant_id), user_email=user.get("email"))
    return MobileService.get_config(tenant_id)


@router_mobile.put(
    "/config",
    response_model=MobileConfig,
    summary="Mettre a jour la configuration mobile",
    description="""
Met a jour la configuration mobile du tenant.

**Requiert le role admin.**

Seuls les champs fournis sont mis a jour (mise a jour partielle).
Les champs non fournis conservent leur valeur actuelle.
    """,
    responses={
        200: {"description": "Configuration mise a jour"},
        400: {"description": "Donnees invalides", "model": ErrorDetail},
        401: {"description": "Non authentifie", "model": ErrorDetail},
        403: {"description": "Role admin requis", "model": ErrorDetail}
    }
)
async def update_mobile_config(
    updates: MobileConfigUpdate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_role("admin"))
) -> MobileConfig:
    """Met a jour la configuration mobile du tenant."""

    logger.info(
        "mobile_config_update",
        tenant_id=str(tenant_id),
        user_email=user.get("email"),
        updates=updates.model_dump(exclude_none=True)
    )

    return MobileService.update_config(tenant_id, user_id, updates)


@router_mobile.get(
    "/bootstrap",
    response_model=BootstrapResponse,
    summary="Initialisation de l'application mobile",
    description="""
Endpoint d'initialisation pour l'application mobile.

Retourne en une seule requete toutes les donnees necessaires au demarrage:
- Informations utilisateur
- Informations tenant
- Configuration mobile
- Permissions de l'utilisateur
- Liste des modules disponibles
- Heure serveur pour synchronisation

Utiliser cet endpoint au lancement de l'app pour minimiser les appels reseau.
    """,
    responses={
        200: {"description": "Donnees d'initialisation"},
        401: {"description": "Non authentifie", "model": ErrorDetail}
    }
)
async def bootstrap_mobile(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> BootstrapResponse:
    """Initialise l'application mobile avec toutes les donnees necessaires."""

    logger.info("mobile_bootstrap", tenant_id=str(tenant_id), user_email=user.get("email"))

    try:
        # Recuperer toutes les informations en parallele
        config = MobileService.get_config(tenant_id)
        user_info = MobileService.get_user_info(user)
        tenant_info = MobileService.get_tenant_info(tenant_id)
        permissions = MobileService.get_user_permissions(user)
        modules = MobileService.get_available_modules(user, config)

        return BootstrapResponse(
            user=user_info,
            tenant=tenant_info,
            config=config,
            permissions=permissions,
            modules=modules,
            server_time=datetime.utcnow(),
            api_version="1.0.0"
        )
    except Exception as e:
        logger.error("mobile_bootstrap_error", error=str(e), tenant_id=str(tenant_id))
        import traceback
        logger.error("mobile_bootstrap_traceback", traceback=traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur bootstrap: {str(e)}"
        )


@router_mobile.get(
    "/modules",
    response_model=ModulesListResponse,
    summary="Liste des modules disponibles sur mobile",
    description="""
Retourne la liste des modules accessibles a l'utilisateur sur mobile.

Les modules sont filtres par:
- Permissions de l'utilisateur (role)
- Configuration mobile du tenant (modules actifs)
- Statut actif du module

Chaque module inclut ses metadonnees et la definition de ses champs.
    """,
    responses={
        200: {"description": "Liste des modules"},
        401: {"description": "Non authentifie", "model": ErrorDetail}
    }
)
async def list_mobile_modules(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> ModulesListResponse:
    """Liste les modules disponibles pour mobile."""

    config = MobileService.get_config(tenant_id)
    modules = MobileService.get_available_modules(user, config)

    return ModulesListResponse(
        modules=modules,
        count=len(modules)
    )


@router_mobile.post(
    "/config/reset",
    response_model=MobileConfig,
    summary="Reinitialiser la configuration mobile",
    description="""
Remet la configuration mobile aux valeurs par defaut.

**Requiert le role admin.**

Cette action supprime toutes les personnalisations et restaure
les parametres par defaut du systeme.
    """,
    responses={
        200: {"description": "Configuration reinitialisee"},
        401: {"description": "Non authentifie", "model": ErrorDetail},
        403: {"description": "Role admin requis", "model": ErrorDetail}
    }
)
async def reset_mobile_config(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_role("admin"))
) -> MobileConfig:
    """Reinitialise la configuration mobile aux valeurs par defaut."""

    logger.warning(
        "mobile_config_reset",
        tenant_id=str(tenant_id),
        user_email=user.get("email")
    )

    return MobileService.reset_config(tenant_id, user_id)
