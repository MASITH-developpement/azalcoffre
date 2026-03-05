# =============================================================================
# AZALPLUS - Mobile Configuration Service
# =============================================================================
"""
Service de configuration mobile par tenant.

Gere:
- Configuration des applications mobiles (internal, portal)
- Bootstrap data pour initialisation rapide
- Cache Redis avec TTL 5 minutes
- Audit trail des modifications

Usage:
    config = await MobileConfigService.get_config(tenant_id)
    bootstrap = await MobileConfigService.get_bootstrap_data(tenant_id, user_id)
    updated = await MobileConfigService.update_config(tenant_id, {"offline_enabled": True})
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field
import json
import structlog

from .db import Database
from .audit import AuditLogger, AuditContext, AuditAction
from .config import settings

logger = structlog.get_logger()

# =============================================================================
# Constants
# =============================================================================
MOBILE_CONFIG_CACHE_PREFIX = "mobile:config:"
MOBILE_CONFIG_CACHE_TTL = 300  # 5 minutes

# Table pour stocker les configurations mobiles
MOBILE_CONFIG_TABLE = "mobile_config"


# =============================================================================
# Pydantic Models
# =============================================================================
class QuickAction(BaseModel):
    """Action rapide affichee sur le dashboard mobile."""
    action: str = Field(..., description="Identifiant de l'action")
    module: str = Field(..., description="Module associe")
    icon: str = Field(default="plus", description="Icone Lucide")
    label: str = Field(..., description="Label affiche")
    color: str = Field(default="primary", description="Couleur du bouton")


class DashboardWidget(BaseModel):
    """Widget du dashboard mobile."""
    type: str = Field(..., description="Type de widget (stat, chart, list, calendar)")
    title: str = Field(..., description="Titre du widget")
    module: str = Field(..., description="Module source des donnees")
    metric: Optional[str] = Field(None, description="Metrique a afficher")
    size: str = Field(default="medium", description="Taille (small, medium, large)")
    order: int = Field(default=0, description="Ordre d'affichage")


class ModuleConfig(BaseModel):
    """Configuration d'un module pour l'app mobile."""
    name: str = Field(..., description="Nom technique du module")
    visible: bool = Field(default=True, description="Module visible dans l'app")
    order: int = Field(default=0, description="Ordre dans le menu")
    icon: str = Field(default="file", description="Icone Lucide")
    quick_actions: List[QuickAction] = Field(default_factory=list, description="Actions rapides")


class MobileConfig(BaseModel):
    """Configuration complete de l'application mobile pour un tenant."""

    # Application interne (employes)
    internal_enabled: bool = Field(default=True, description="App interne activee")
    internal_modules: List[str] = Field(
        default_factory=lambda: [
            "clients", "produits", "devis", "factures",
            "interventions", "temps", "contacts"
        ],
        description="Modules disponibles dans l'app interne"
    )

    # Dashboard
    dashboard_widgets: List[DashboardWidget] = Field(
        default_factory=list,
        description="Widgets du dashboard"
    )

    # Actions rapides
    quick_actions: List[QuickAction] = Field(
        default_factory=list,
        description="Actions rapides globales"
    )

    # Portail client
    portal_enabled: bool = Field(default=True, description="Portail client active")

    # Fonctionnalites
    offline_enabled: bool = Field(default=True, description="Mode offline active")
    push_enabled: bool = Field(default=True, description="Notifications push activees")

    # Theme
    theme: Dict[str, Any] = Field(
        default_factory=lambda: {
            "primary_color": "#2563eb",
            "accent_color": "#3b82f6",
            "dark_mode": "auto"
        },
        description="Configuration du theme"
    )

    # Metadata
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class UserInfo(BaseModel):
    """Informations utilisateur pour le bootstrap."""
    id: str
    email: str
    nom: str
    prenom: Optional[str] = None
    role: str
    avatar_url: Optional[str] = None


class TenantInfo(BaseModel):
    """Informations tenant pour le bootstrap."""
    id: str
    code: str
    nom: str
    logo_url: Optional[str] = None
    adresse: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None


class ModulePermission(BaseModel):
    """Permission sur un module."""
    module: str
    can_read: bool = True
    can_create: bool = False
    can_update: bool = False
    can_delete: bool = False


class BootstrapData(BaseModel):
    """Donnees de bootstrap pour l'application mobile."""
    user: UserInfo
    tenant: TenantInfo
    config: MobileConfig
    permissions: List[ModulePermission]
    modules: List[ModuleConfig]
    server_time: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Mobile Config Service
# =============================================================================
class MobileConfigService:
    """
    Service de configuration mobile.

    Gere les configurations par tenant avec cache Redis.
    """

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Retourne la configuration mobile par defaut.

        Returns:
            Dict de configuration par defaut
        """
        return MobileConfig().model_dump()

    @classmethod
    def _get_default_widgets(cls) -> List[Dict[str, Any]]:
        """Retourne les widgets par defaut."""
        return [
            {
                "type": "stat",
                "title": "Chiffre d'affaires",
                "module": "factures",
                "metric": "total_ttc_mois",
                "size": "medium",
                "order": 1
            },
            {
                "type": "stat",
                "title": "Devis en cours",
                "module": "devis",
                "metric": "count_envoye",
                "size": "small",
                "order": 2
            },
            {
                "type": "stat",
                "title": "Factures impayees",
                "module": "factures",
                "metric": "count_impaye",
                "size": "small",
                "order": 3
            },
            {
                "type": "list",
                "title": "Interventions du jour",
                "module": "interventions",
                "metric": "today",
                "size": "large",
                "order": 4
            },
            {
                "type": "calendar",
                "title": "Planning",
                "module": "interventions",
                "metric": "week",
                "size": "large",
                "order": 5
            }
        ]

    @classmethod
    def _get_default_quick_actions(cls) -> List[Dict[str, Any]]:
        """Retourne les actions rapides par defaut."""
        return [
            {
                "action": "create",
                "module": "clients",
                "icon": "user-plus",
                "label": "Nouveau client",
                "color": "primary"
            },
            {
                "action": "create",
                "module": "devis",
                "icon": "file-plus",
                "label": "Nouveau devis",
                "color": "success"
            },
            {
                "action": "create",
                "module": "interventions",
                "icon": "wrench",
                "label": "Intervention",
                "color": "warning"
            },
            {
                "action": "scan",
                "module": "produits",
                "icon": "scan",
                "label": "Scanner",
                "color": "secondary"
            }
        ]

    @classmethod
    async def get_config(cls, tenant_id: UUID) -> MobileConfig:
        """
        Recupere la configuration mobile pour un tenant.

        Utilise le cache Redis avec TTL 5 minutes.
        Si aucune config n'existe, retourne la config par defaut.

        Args:
            tenant_id: ID du tenant

        Returns:
            MobileConfig
        """
        # 1. Verifier le cache Redis
        cache_key = f"{MOBILE_CONFIG_CACHE_PREFIX}{tenant_id}"

        try:
            redis = Database.get_redis()
            cached = await redis.get(cache_key)

            if cached:
                logger.debug("mobile_config_cache_hit", tenant_id=str(tenant_id))
                data = json.loads(cached)
                return MobileConfig(**data)
        except Exception as e:
            logger.warning("mobile_config_cache_error", error=str(e))

        # 2. Charger depuis la base
        config_data = None

        try:
            with Database.get_session() as session:
                from sqlalchemy import text

                result = session.execute(
                    text("""
                        SELECT config_data, updated_at, updated_by
                        FROM azalplus.mobile_config
                        WHERE tenant_id = :tenant_id
                        LIMIT 1
                    """),
                    {"tenant_id": str(tenant_id)}
                )
                row = result.fetchone()

                if row:
                    config_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    config_data["updated_at"] = row[1]
                    config_data["updated_by"] = row[2]
        except Exception as e:
            # Table n'existe peut-etre pas encore
            logger.debug("mobile_config_db_read_error", error=str(e))

        # 3. Utiliser les defaults si pas de config
        if not config_data:
            config_data = cls.get_default_config()
            # Ajouter widgets et actions par defaut
            config_data["dashboard_widgets"] = cls._get_default_widgets()
            config_data["quick_actions"] = cls._get_default_quick_actions()

        config = MobileConfig(**config_data)

        # 4. Mettre en cache
        try:
            redis = Database.get_redis()
            await redis.setex(
                cache_key,
                MOBILE_CONFIG_CACHE_TTL,
                json.dumps(config.model_dump(), default=str)
            )
        except Exception as e:
            logger.warning("mobile_config_cache_set_error", error=str(e))

        logger.debug("mobile_config_loaded", tenant_id=str(tenant_id))
        return config

    @classmethod
    async def update_config(
        cls,
        tenant_id: UUID,
        updates: Dict[str, Any],
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None
    ) -> MobileConfig:
        """
        Met a jour la configuration mobile.

        Fusionne les updates avec la config existante.
        Invalide le cache.
        Log dans l'audit trail.

        Args:
            tenant_id: ID du tenant
            updates: Dictionnaire des mises a jour
            user_id: ID de l'utilisateur effectuant la modification
            user_email: Email de l'utilisateur

        Returns:
            MobileConfig mise a jour
        """
        # 1. Charger la config actuelle
        current_config = await cls.get_config(tenant_id)
        old_data = current_config.model_dump()

        # 2. Fusionner les updates
        new_data = current_config.model_dump()
        for key, value in updates.items():
            if key in new_data:
                new_data[key] = value

        new_data["updated_at"] = datetime.utcnow()
        new_data["updated_by"] = user_email or str(user_id) if user_id else None

        # 3. Sauvegarder en base
        with Database.get_session() as session:
            from sqlalchemy import text

            # Upsert
            session.execute(
                text("""
                    INSERT INTO azalplus.mobile_config (id, tenant_id, config_data, updated_at, updated_by)
                    VALUES (gen_random_uuid(), :tenant_id, :config_data::jsonb, NOW(), :updated_by)
                    ON CONFLICT (tenant_id)
                    DO UPDATE SET
                        config_data = :config_data::jsonb,
                        updated_at = NOW(),
                        updated_by = :updated_by
                """),
                {
                    "tenant_id": str(tenant_id),
                    "config_data": json.dumps(new_data, default=str),
                    "updated_by": new_data["updated_by"]
                }
            )
            session.commit()

        # 4. Invalider le cache
        try:
            redis = Database.get_redis()
            cache_key = f"{MOBILE_CONFIG_CACHE_PREFIX}{tenant_id}"
            await redis.delete(cache_key)
        except Exception as e:
            logger.warning("mobile_config_cache_invalidate_error", error=str(e))

        # 5. Log audit
        try:
            context = AuditContext(
                tenant_id=tenant_id,
                user_id=user_id,
                user_email=user_email
            )
            AuditLogger.log_update(
                module="mobile_config",
                record_id=tenant_id,  # Utilise tenant_id comme record_id car 1 config par tenant
                old_data=old_data,
                new_data=new_data,
                context=context
            )
        except Exception as e:
            logger.warning("mobile_config_audit_error", error=str(e))

        logger.info(
            "mobile_config_updated",
            tenant_id=str(tenant_id),
            updated_fields=list(updates.keys())
        )

        return MobileConfig(**new_data)

    @classmethod
    async def get_bootstrap_data(
        cls,
        tenant_id: UUID,
        user_id: UUID
    ) -> BootstrapData:
        """
        Retourne les donnees de bootstrap pour l'app mobile.

        Inclut tout ce dont l'app a besoin pour s'initialiser:
        - Infos utilisateur
        - Infos tenant
        - Configuration mobile
        - Permissions utilisateur
        - Modules disponibles

        Args:
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur

        Returns:
            BootstrapData
        """
        # 1. Charger la config mobile
        config = await cls.get_config(tenant_id)

        # 2. Charger les infos utilisateur et tenant
        user_info = None
        tenant_info = None
        user_role = "user"

        with Database.get_session() as session:
            from sqlalchemy import text

            # Utilisateur
            result = session.execute(
                text("""
                    SELECT id, email, nom, prenom, role, avatar_url
                    FROM azalplus.utilisateurs
                    WHERE id = :user_id AND tenant_id = :tenant_id AND actif = true
                """),
                {"user_id": str(user_id), "tenant_id": str(tenant_id)}
            )
            user_row = result.fetchone()

            if user_row:
                user_info = UserInfo(
                    id=str(user_row[0]),
                    email=user_row[1],
                    nom=user_row[2],
                    prenom=user_row[3],
                    role=user_row[4],
                    avatar_url=user_row[5]
                )
                user_role = user_row[4]
            else:
                raise ValueError(f"Utilisateur {user_id} non trouve pour tenant {tenant_id}")

            # Tenant
            result = session.execute(
                text("""
                    SELECT id, code, nom, logo_url, adresse, telephone, email
                    FROM azalplus.tenants
                    WHERE id = :tenant_id AND actif = true
                """),
                {"tenant_id": str(tenant_id)}
            )
            tenant_row = result.fetchone()

            if tenant_row:
                tenant_info = TenantInfo(
                    id=str(tenant_row[0]),
                    code=tenant_row[1],
                    nom=tenant_row[2],
                    logo_url=tenant_row[3],
                    adresse=tenant_row[4],
                    telephone=tenant_row[5],
                    email=tenant_row[6]
                )
            else:
                raise ValueError(f"Tenant {tenant_id} non trouve")

        # 3. Calculer les permissions selon le role
        permissions = cls._compute_permissions(user_role, config.internal_modules)

        # 4. Construire la liste des modules disponibles
        modules = cls._build_module_list(config.internal_modules, permissions, user_role)

        logger.debug(
            "mobile_bootstrap_loaded",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            modules_count=len(modules)
        )

        return BootstrapData(
            user=user_info,
            tenant=tenant_info,
            config=config,
            permissions=permissions,
            modules=modules
        )

    @classmethod
    def _compute_permissions(
        cls,
        role: str,
        enabled_modules: List[str]
    ) -> List[ModulePermission]:
        """
        Calcule les permissions basees sur le role.

        Roles supportes: admin, manager, commercial, technicien, comptable, lecture_seule
        """
        permissions = []

        # Definitions des permissions par role
        role_permissions = {
            "admin": {
                "can_read": True,
                "can_create": True,
                "can_update": True,
                "can_delete": True
            },
            "manager": {
                "can_read": True,
                "can_create": True,
                "can_update": True,
                "can_delete": True
            },
            "commercial": {
                "can_read": True,
                "can_create": True,
                "can_update": True,
                "can_delete": False
            },
            "technicien": {
                "can_read": True,
                "can_create": False,
                "can_update": True,
                "can_delete": False
            },
            "comptable": {
                "can_read": True,
                "can_create": True,
                "can_update": True,
                "can_delete": False
            },
            "lecture_seule": {
                "can_read": True,
                "can_create": False,
                "can_update": False,
                "can_delete": False
            }
        }

        # Permissions par defaut
        default_perms = role_permissions.get(role, role_permissions["lecture_seule"])

        for module in enabled_modules:
            perms = default_perms.copy()

            # Restrictions specifiques par role/module
            if role == "technicien":
                if module not in ["interventions", "temps"]:
                    perms["can_update"] = False
            elif role == "commercial":
                if module == "factures":
                    perms["can_create"] = False
                    perms["can_update"] = False
            elif role == "comptable":
                if module not in ["factures", "paiements", "clients"]:
                    perms["can_create"] = False
                    perms["can_update"] = False

            permissions.append(ModulePermission(
                module=module,
                **perms
            ))

        return permissions

    @classmethod
    def _build_module_list(
        cls,
        enabled_modules: List[str],
        permissions: List[ModulePermission],
        role: str
    ) -> List[ModuleConfig]:
        """
        Construit la liste des modules avec leur configuration.
        """
        # Icons par defaut pour les modules
        module_icons = {
            "clients": "users",
            "produits": "package",
            "devis": "file-text",
            "factures": "receipt",
            "interventions": "wrench",
            "temps": "clock",
            "contacts": "contact",
            "paiements": "credit-card",
            "projets": "folder",
            "stocks": "warehouse",
            "fournisseurs": "truck"
        }

        # Actions rapides par module
        module_quick_actions = {
            "clients": [
                QuickAction(action="call", module="clients", icon="phone", label="Appeler", color="primary"),
                QuickAction(action="email", module="clients", icon="mail", label="Email", color="secondary"),
            ],
            "devis": [
                QuickAction(action="send", module="devis", icon="send", label="Envoyer", color="primary"),
                QuickAction(action="duplicate", module="devis", icon="copy", label="Dupliquer", color="secondary"),
            ],
            "factures": [
                QuickAction(action="send", module="factures", icon="send", label="Envoyer", color="primary"),
                QuickAction(action="payment", module="factures", icon="credit-card", label="Paiement", color="success"),
            ],
            "interventions": [
                QuickAction(action="start", module="interventions", icon="play", label="Demarrer", color="success"),
                QuickAction(action="complete", module="interventions", icon="check", label="Terminer", color="primary"),
            ],
            "temps": [
                QuickAction(action="start", module="temps", icon="play", label="Demarrer", color="success"),
                QuickAction(action="stop", module="temps", icon="square", label="Arreter", color="danger"),
            ]
        }

        modules = []

        # Creer un dict des permissions pour lookup rapide
        perms_by_module = {p.module: p for p in permissions}

        for order, module_name in enumerate(enabled_modules):
            perm = perms_by_module.get(module_name)

            # Si pas de permission de lecture, ne pas inclure le module
            if perm and not perm.can_read:
                continue

            # Quick actions filtrees selon permissions
            quick_actions = []
            if module_name in module_quick_actions:
                for qa in module_quick_actions[module_name]:
                    # Filtrer les actions de modification si pas de permission
                    if qa.action in ["create", "start"] and perm and not perm.can_create:
                        continue
                    if qa.action in ["edit", "complete", "send"] and perm and not perm.can_update:
                        continue
                    quick_actions.append(qa)

            modules.append(ModuleConfig(
                name=module_name,
                visible=True,
                order=order,
                icon=module_icons.get(module_name, "file"),
                quick_actions=quick_actions
            ))

        return modules

    @classmethod
    async def invalidate_cache(cls, tenant_id: UUID) -> bool:
        """
        Invalide le cache de configuration pour un tenant.

        Args:
            tenant_id: ID du tenant

        Returns:
            True si le cache a ete invalide
        """
        try:
            redis = Database.get_redis()
            cache_key = f"{MOBILE_CONFIG_CACHE_PREFIX}{tenant_id}"
            await redis.delete(cache_key)
            logger.debug("mobile_config_cache_invalidated", tenant_id=str(tenant_id))
            return True
        except Exception as e:
            logger.warning("mobile_config_cache_invalidate_error", error=str(e))
            return False


# =============================================================================
# Database Setup Helper
# =============================================================================
async def ensure_mobile_config_table():
    """
    Cree la table mobile_config si elle n'existe pas.

    Appelee au demarrage de l'application.
    """
    try:
        with Database.get_session() as session:
            from sqlalchemy import text

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS azalplus.mobile_config (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL UNIQUE REFERENCES azalplus.tenants(id),
                    config_data JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    updated_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_mobile_config_tenant
                ON azalplus.mobile_config(tenant_id);
            """))
            session.commit()

        logger.info("mobile_config_table_ensured")
        return True
    except Exception as e:
        logger.error("mobile_config_table_error", error=str(e))
        return False
