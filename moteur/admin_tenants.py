# =============================================================================
# AZALPLUS - Tenant Administration API
# =============================================================================
"""
API d'administration des tenants.
ACCES EXCLUSIF au Createur (contact@stephane-moreau.fr).

Endpoints retournent 404 pour les non-createurs (invisibilite).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID, uuid4
import structlog
import json
import re
from sqlalchemy import text

from .db import Database
from .tenant import require_createur
from .auth import require_auth
from .config import settings

logger = structlog.get_logger()


# =============================================================================
# Schemas
# =============================================================================

class TenantCreateRequest(BaseModel):
    """Schema pour creation d'un tenant."""
    code: str = Field(..., min_length=2, max_length=50, description="Code unique du tenant")
    nom: str = Field(..., min_length=2, max_length=255, description="Nom de l'entreprise")
    email: EmailStr = Field(..., description="Email principal du tenant")

    # Informations legales (optionnelles)
    siret: Optional[str] = Field(None, max_length=14)
    tva_intra: Optional[str] = Field(None, max_length=20)
    adresse: Optional[str] = None
    code_postal: Optional[str] = Field(None, max_length=10)
    ville: Optional[str] = Field(None, max_length=100)
    pays: str = Field("FR", max_length=2)
    telephone: Optional[str] = Field(None, max_length=20)

    # Configuration
    modules_actifs: List[str] = Field(
        default=["produits", "clients", "devis", "factures", "interventions"]
    )
    country_pack: str = Field("france", max_length=20)
    devise: str = Field("EUR", max_length=3)
    langue: str = Field("fr", max_length=5)
    timezone: str = Field("Europe/Paris", max_length=50)

    # Limites
    max_utilisateurs: int = Field(5, ge=1, le=1000)
    max_stockage_mo: int = Field(1024, ge=100, le=1000000)

    # Statut
    date_expiration: Optional[datetime] = None

    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        """Code en majuscules, alphanumerique + underscore."""
        if not re.match(r'^[A-Za-z0-9_]+$', v):
            raise ValueError("Code doit etre alphanumerique (lettres, chiffres, underscore)")
        return v.upper()

    @field_validator('siret')
    @classmethod
    def validate_siret(cls, v):
        """SIRET doit etre 14 chiffres si fourni."""
        if v is not None:
            cleaned = re.sub(r'\s', '', v)
            if not re.match(r'^[0-9]{14}$', cleaned):
                raise ValueError("SIRET doit contenir 14 chiffres")
            return cleaned
        return v


class TenantUpdateRequest(BaseModel):
    """Schema pour mise a jour d'un tenant."""
    nom: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    siret: Optional[str] = Field(None, max_length=14)
    tva_intra: Optional[str] = Field(None, max_length=20)
    adresse: Optional[str] = None
    code_postal: Optional[str] = Field(None, max_length=10)
    ville: Optional[str] = Field(None, max_length=100)
    pays: Optional[str] = Field(None, max_length=2)
    telephone: Optional[str] = Field(None, max_length=20)
    config: Optional[Dict[str, Any]] = None
    modules_actifs: Optional[List[str]] = None
    country_pack: Optional[str] = Field(None, max_length=20)
    devise: Optional[str] = Field(None, max_length=3)
    langue: Optional[str] = Field(None, max_length=5)
    timezone: Optional[str] = Field(None, max_length=50)
    max_utilisateurs: Optional[int] = Field(None, ge=1, le=1000)
    max_stockage_mo: Optional[int] = Field(None, ge=100, le=1000000)
    date_expiration: Optional[datetime] = None

    @field_validator('siret')
    @classmethod
    def validate_siret(cls, v):
        """SIRET doit etre 14 chiffres si fourni."""
        if v is not None:
            cleaned = re.sub(r'\s', '', v)
            if not re.match(r'^[0-9]{14}$', cleaned):
                raise ValueError("SIRET doit contenir 14 chiffres")
            return cleaned
        return v


class TenantResponse(BaseModel):
    """Schema de reponse pour un tenant."""
    id: UUID
    code: str
    nom: str
    email: str
    siret: Optional[str] = None
    tva_intra: Optional[str] = None
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    pays: str
    telephone: Optional[str] = None
    config: Dict[str, Any]
    modules_actifs: List[str]
    country_pack: str
    devise: str
    langue: str
    timezone: str
    max_utilisateurs: int
    max_stockage_mo: int
    actif: bool
    date_creation: datetime
    date_expiration: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # Stats supplementaires
    nb_utilisateurs: Optional[int] = None


class TenantListResponse(BaseModel):
    """Schema de reponse pour la liste des tenants."""
    tenants: List[TenantResponse]
    total: int


# =============================================================================
# Service
# =============================================================================

class TenantAdminService:
    """Service d'administration des tenants (Createur uniquement)."""

    # Sequences par defaut pour un nouveau tenant
    DEFAULT_SEQUENCES = [
        {"entite": "devis", "prefixe": "DEV", "separateur": "-", "padding": 4},
        {"entite": "facture", "prefixe": "FAC", "separateur": "-", "padding": 4},
        {"entite": "client", "prefixe": "CLI", "separateur": "-", "padding": 4},
        {"entite": "intervention", "prefixe": "INT", "separateur": "-", "padding": 4},
    ]

    @classmethod
    async def list_tenants(
        cls,
        include_inactive: bool = False,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Liste tous les tenants."""
        with Database.get_session() as session:
            query = """
                SELECT t.*,
                       (SELECT COUNT(*) FROM azalplus.utilisateurs u
                        WHERE u.tenant_id = t.id AND u.actif = true) as nb_utilisateurs
                FROM azalplus.tenants t
                WHERE 1=1
            """
            params = {}

            if not include_inactive:
                query += " AND t.actif = true"

            if search:
                query += """ AND (
                    t.code ILIKE :search OR
                    t.nom ILIKE :search OR
                    t.email ILIKE :search
                )"""
                params["search"] = f"%{search}%"

            query += " ORDER BY t.created_at DESC"

            result = session.execute(text(query), params)
            tenants = []
            for row in result:
                tenant_dict = dict(row._mapping)
                # Convertir les JSONB en types Python
                if isinstance(tenant_dict.get("config"), str):
                    tenant_dict["config"] = json.loads(tenant_dict["config"])
                if isinstance(tenant_dict.get("modules_actifs"), str):
                    tenant_dict["modules_actifs"] = json.loads(tenant_dict["modules_actifs"])
                tenants.append(tenant_dict)

        return tenants

    @classmethod
    async def get_tenant(cls, tenant_id: UUID) -> Optional[Dict[str, Any]]:
        """Recupere un tenant par son ID."""
        with Database.get_session() as session:
            result = session.execute(
                text("""
                    SELECT t.*,
                           (SELECT COUNT(*) FROM azalplus.utilisateurs u
                            WHERE u.tenant_id = t.id AND u.actif = true) as nb_utilisateurs
                    FROM azalplus.tenants t
                    WHERE t.id = :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )
            row = result.fetchone()

            if row:
                tenant_dict = dict(row._mapping)
                # Convertir les JSONB en types Python
                if isinstance(tenant_dict.get("config"), str):
                    tenant_dict["config"] = json.loads(tenant_dict["config"])
                if isinstance(tenant_dict.get("modules_actifs"), str):
                    tenant_dict["modules_actifs"] = json.loads(tenant_dict["modules_actifs"])
                return tenant_dict
        return None

    @classmethod
    async def create_tenant(cls, data: TenantCreateRequest) -> Dict[str, Any]:
        """Cree un nouveau tenant avec ses sequences par defaut."""
        tenant_id = uuid4()

        with Database.get_session() as session:
            # Verifier que le code n'existe pas deja
            existing = session.execute(
                text("SELECT id FROM azalplus.tenants WHERE code = :code"),
                {"code": data.code}
            ).fetchone()

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Un tenant avec le code '{data.code}' existe deja"
                )

            # Creer le tenant
            session.execute(
                text("""
                    INSERT INTO azalplus.tenants (
                        id, code, nom, email, siret, tva_intra, adresse,
                        code_postal, ville, pays, telephone, config,
                        modules_actifs, country_pack, devise, langue,
                        timezone, max_utilisateurs, max_stockage_mo,
                        actif, date_creation, date_expiration
                    ) VALUES (
                        :id, :code, :nom, :email, :siret, :tva_intra, :adresse,
                        :code_postal, :ville, :pays, :telephone, :config,
                        :modules_actifs, :country_pack, :devise, :langue,
                        :timezone, :max_utilisateurs, :max_stockage_mo,
                        true, NOW(), :date_expiration
                    )
                """),
                {
                    "id": str(tenant_id),
                    "code": data.code,
                    "nom": data.nom,
                    "email": data.email,
                    "siret": data.siret,
                    "tva_intra": data.tva_intra,
                    "adresse": data.adresse,
                    "code_postal": data.code_postal,
                    "ville": data.ville,
                    "pays": data.pays,
                    "telephone": data.telephone,
                    "config": json.dumps({}),
                    "modules_actifs": json.dumps(data.modules_actifs),
                    "country_pack": data.country_pack,
                    "devise": data.devise,
                    "langue": data.langue,
                    "timezone": data.timezone,
                    "max_utilisateurs": data.max_utilisateurs,
                    "max_stockage_mo": data.max_stockage_mo,
                    "date_expiration": data.date_expiration,
                }
            )

            # Creer les sequences par defaut
            for seq in cls.DEFAULT_SEQUENCES:
                session.execute(
                    text("""
                        INSERT INTO azalplus.sequences (
                            tenant_id, entite, prefixe, separateur, padding
                        ) VALUES (
                            :tenant_id, :entite, :prefixe, :separateur, :padding
                        )
                    """),
                    {
                        "tenant_id": str(tenant_id),
                        **seq
                    }
                )

            # Logger dans audit_log
            session.execute(
                text("""
                    INSERT INTO azalplus.audit_log (
                        tenant_id, action, entite, entite_id,
                        utilisateur_email, donnees_apres, metadata
                    ) VALUES (
                        :tenant_id, 'CREATE', 'tenant', :tenant_id,
                        :createur_email, :donnees, :metadata
                    )
                """),
                {
                    "tenant_id": str(tenant_id),
                    "createur_email": settings.CREATEUR_EMAIL,
                    "donnees": json.dumps(data.model_dump(mode="json")),
                    "metadata": json.dumps({"source": "admin_api"})
                }
            )

            session.commit()

        logger.info(
            "tenant_created",
            tenant_id=str(tenant_id),
            code=data.code,
            nom=data.nom
        )

        return await cls.get_tenant(tenant_id)

    @classmethod
    async def update_tenant(
        cls,
        tenant_id: UUID,
        data: TenantUpdateRequest
    ) -> Dict[str, Any]:
        """Met a jour un tenant."""
        # Verifier que le tenant existe
        existing = await cls.get_tenant(tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Tenant non trouve")

        # Construire la requete de mise a jour
        updates = []
        params = {"tenant_id": str(tenant_id)}

        update_fields = data.model_dump(exclude_unset=True)

        for field, value in update_fields.items():
            if value is not None:
                if field in ("config", "modules_actifs"):
                    updates.append(f"{field} = :{field}::jsonb")
                    params[field] = json.dumps(value)
                else:
                    updates.append(f"{field} = :{field}")
                    params[field] = value

        if not updates:
            raise HTTPException(status_code=400, detail="Aucune modification fournie")

        with Database.get_session() as session:
            session.execute(
                text(f"""
                    UPDATE azalplus.tenants
                    SET {", ".join(updates)}, updated_at = NOW()
                    WHERE id = :tenant_id
                """),
                params
            )

            # Logger dans audit_log
            session.execute(
                text("""
                    INSERT INTO azalplus.audit_log (
                        tenant_id, action, entite, entite_id,
                        utilisateur_email, donnees_avant, donnees_apres, metadata
                    ) VALUES (
                        :tenant_id, 'UPDATE', 'tenant', :tenant_id,
                        :createur_email, :avant, :apres, :metadata
                    )
                """),
                {
                    "tenant_id": str(tenant_id),
                    "createur_email": settings.CREATEUR_EMAIL,
                    "avant": json.dumps(existing, default=str),
                    "apres": json.dumps(update_fields, default=str),
                    "metadata": json.dumps({"source": "admin_api"})
                }
            )

            session.commit()

        logger.info("tenant_updated", tenant_id=str(tenant_id))
        return await cls.get_tenant(tenant_id)

    @classmethod
    async def soft_delete_tenant(cls, tenant_id: UUID) -> Dict[str, Any]:
        """Desactive un tenant (soft delete)."""
        existing = await cls.get_tenant(tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Tenant non trouve")

        if not existing.get("actif"):
            raise HTTPException(status_code=400, detail="Tenant deja inactif")

        with Database.get_session() as session:
            session.execute(
                text("""
                    UPDATE azalplus.tenants
                    SET actif = false, updated_at = NOW()
                    WHERE id = :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )

            # Logger dans audit_log
            session.execute(
                text("""
                    INSERT INTO azalplus.audit_log (
                        tenant_id, action, entite, entite_id,
                        utilisateur_email, metadata
                    ) VALUES (
                        :tenant_id, 'DELETE', 'tenant', :tenant_id,
                        :createur_email, :metadata
                    )
                """),
                {
                    "tenant_id": str(tenant_id),
                    "createur_email": settings.CREATEUR_EMAIL,
                    "metadata": json.dumps({"source": "admin_api", "type": "soft_delete"})
                }
            )

            session.commit()

        logger.info("tenant_soft_deleted", tenant_id=str(tenant_id))
        return await cls.get_tenant(tenant_id)

    @classmethod
    async def activate_tenant(cls, tenant_id: UUID) -> Dict[str, Any]:
        """Reactive un tenant desactive."""
        existing = await cls.get_tenant(tenant_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Tenant non trouve")

        if existing.get("actif"):
            raise HTTPException(status_code=400, detail="Tenant deja actif")

        with Database.get_session() as session:
            session.execute(
                text("""
                    UPDATE azalplus.tenants
                    SET actif = true, updated_at = NOW()
                    WHERE id = :tenant_id
                """),
                {"tenant_id": str(tenant_id)}
            )

            # Logger dans audit_log
            session.execute(
                text("""
                    INSERT INTO azalplus.audit_log (
                        tenant_id, action, entite, entite_id,
                        utilisateur_email, metadata
                    ) VALUES (
                        :tenant_id, 'UPDATE', 'tenant', :tenant_id,
                        :createur_email, :metadata
                    )
                """),
                {
                    "tenant_id": str(tenant_id),
                    "createur_email": settings.CREATEUR_EMAIL,
                    "metadata": json.dumps({"source": "admin_api", "action": "activate"})
                }
            )

            session.commit()

        logger.info("tenant_activated", tenant_id=str(tenant_id))
        return await cls.get_tenant(tenant_id)


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/")
async def list_tenants(
    include_inactive: bool = False,
    search: Optional[str] = None,
    _: bool = Depends(require_createur),
    user: dict = Depends(require_auth)
):
    """
    Liste tous les tenants.

    - **include_inactive**: Inclure les tenants desactives
    - **search**: Recherche par code, nom ou email

    *Acces reserve au Createur.*
    """
    tenants = await TenantAdminService.list_tenants(
        include_inactive=include_inactive,
        search=search
    )
    return {"tenants": tenants, "total": len(tenants)}


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: UUID,
    _: bool = Depends(require_createur),
    user: dict = Depends(require_auth)
):
    """
    Recupere les details d'un tenant.

    *Acces reserve au Createur.*
    """
    tenant = await TenantAdminService.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant non trouve")
    return tenant


@router.post("/", status_code=201)
async def create_tenant(
    data: TenantCreateRequest,
    _: bool = Depends(require_createur),
    user: dict = Depends(require_auth)
):
    """
    Cree un nouveau tenant.

    Cree automatiquement les sequences par defaut:
    - devis (DEV-YYYY-0001)
    - facture (FAC-YYYY-0001)
    - client (CLI-YYYY-0001)
    - intervention (INT-YYYY-0001)

    *Acces reserve au Createur.*
    """
    tenant = await TenantAdminService.create_tenant(data)
    return tenant


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: UUID,
    data: TenantUpdateRequest,
    _: bool = Depends(require_createur),
    user: dict = Depends(require_auth)
):
    """
    Met a jour un tenant.

    *Acces reserve au Createur.*
    """
    tenant = await TenantAdminService.update_tenant(tenant_id, data)
    return tenant


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: UUID,
    _: bool = Depends(require_createur),
    user: dict = Depends(require_auth)
):
    """
    Desactive un tenant (soft delete).

    Le tenant et ses donnees sont conserves mais inaccessibles.
    Utilisez POST /{tenant_id}/activate pour le reactiver.

    *Acces reserve au Createur.*
    """
    tenant = await TenantAdminService.soft_delete_tenant(tenant_id)
    return {"status": "deleted", "tenant": tenant}


@router.post("/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: UUID,
    _: bool = Depends(require_createur),
    user: dict = Depends(require_auth)
):
    """
    Reactive un tenant desactive.

    *Acces reserve au Createur.*
    """
    tenant = await TenantAdminService.activate_tenant(tenant_id)
    return {"status": "activated", "tenant": tenant}
