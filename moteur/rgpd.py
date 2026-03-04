# =============================================================================
# AZALPLUS - RGPD/GDPR Compliance Engine
# =============================================================================
"""
Moteur de conformite RGPD/GDPR.
- Export des donnees (droit a la portabilite)
- Anonymisation (droit a l'effacement)
- Gestion des consentements
- Politiques de retention
- Rapports de conformite
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, date, timedelta
from pydantic import BaseModel, EmailStr
import structlog
import json
import zipfile
import io
import hashlib
import yaml
from pathlib import Path

from .db import Database
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth
from .audit import AuditLogger, AuditContext

logger = structlog.get_logger()

# =============================================================================
# Configuration RGPD
# =============================================================================
def load_rgpd_config() -> Dict:
    """Charge la configuration RGPD."""
    config_path = Path(__file__).parent.parent / "config" / "rgpd.yml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

RGPD_CONFIG = load_rgpd_config()

# =============================================================================
# Schemas Pydantic
# =============================================================================
class ConsentementCreate(BaseModel):
    """Creation d'un consentement."""
    client_id: UUID
    contact_id: Optional[UUID] = None
    type_consentement: str
    statut: str = "ACCORDE"
    source: str = "FORMULAIRE_WEB"
    version_politique: Optional[str] = None
    texte_accepte: Optional[str] = None
    notes: Optional[str] = None


class ConsentementUpdate(BaseModel):
    """Mise a jour d'un consentement."""
    statut: str
    notes: Optional[str] = None


class DemandeRGPDCreate(BaseModel):
    """Creation d'une demande RGPD."""
    client_id: Optional[UUID] = None
    nom_demandeur: str
    prenom_demandeur: str
    email_demandeur: EmailStr
    telephone_demandeur: Optional[str] = None
    type_demande: str  # ACCES, PORTABILITE, EFFACEMENT, RECTIFICATION, LIMITATION, OPPOSITION
    description: Optional[str] = None


class PolitiqueRetentionCreate(BaseModel):
    """Creation d'une politique de retention."""
    nom: str
    description: Optional[str] = None
    module: str
    duree_retention_jours: int
    action_expiration: str  # ANONYMISER, SUPPRIMER, ARCHIVER, NOTIFIER
    champs_a_anonymiser: Optional[List[str]] = None
    condition: Optional[str] = None
    base_legale: str
    reference_legale: Optional[str] = None


# =============================================================================
# RGPD Router
# =============================================================================
rgpd_router = APIRouter(prefix="/rgpd", tags=["RGPD"])


# =============================================================================
# DROIT D'ACCES (Article 15) - Rapport des donnees detenues
# =============================================================================
@rgpd_router.get("/client/{client_id}/rapport-acces")
async def generer_rapport_acces(
    client_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Genere un rapport de toutes les donnees detenues sur un client.
    Article 15 RGPD - Droit d'acces.
    """
    rapport = RGPDEngine.generer_rapport_acces(tenant_id, client_id)

    if not rapport:
        raise HTTPException(status_code=404, detail="Client non trouve")

    # Log de l'acces
    logger.info(
        "rgpd_rapport_acces",
        tenant_id=str(tenant_id),
        client_id=str(client_id),
        user_id=user.get("id")
    )

    return rapport


# =============================================================================
# DROIT A LA PORTABILITE (Article 20) - Export JSON/ZIP
# =============================================================================
@rgpd_router.get("/client/{client_id}/export")
async def exporter_donnees_client(
    client_id: UUID,
    format: str = Query("json", enum=["json", "zip"]),
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Exporte toutes les donnees d'un client dans un format portable.
    Article 20 RGPD - Droit a la portabilite.
    """
    donnees = RGPDEngine.exporter_donnees_client(tenant_id, client_id)

    if not donnees:
        raise HTTPException(status_code=404, detail="Client non trouve")

    # Log
    logger.info(
        "rgpd_export_donnees",
        tenant_id=str(tenant_id),
        client_id=str(client_id),
        format=format
    )

    if format == "zip":
        # Creer un ZIP avec les donnees
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Fichier principal
            zip_file.writestr(
                "donnees_client.json",
                json.dumps(donnees, indent=2, default=str, ensure_ascii=False)
            )

            # Fichiers separees par module
            for module, data in donnees.get("modules", {}).items():
                if data:
                    zip_file.writestr(
                        f"{module}.json",
                        json.dumps(data, indent=2, default=str, ensure_ascii=False)
                    )

        zip_buffer.seek(0)
        filename = f"export_rgpd_{client_id}_{date.today().isoformat()}.zip"

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    else:
        # Export JSON simple
        return JSONResponse(content=donnees)


# =============================================================================
# DROIT A L'EFFACEMENT (Article 17) - Anonymisation
# =============================================================================
@rgpd_router.post("/client/{client_id}/anonymiser")
async def anonymiser_client(
    client_id: UUID,
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Anonymise les donnees personnelles d'un client.
    Article 17 RGPD - Droit a l'effacement.

    ATTENTION: Cette action est irreversible.
    Les documents legaux (factures) sont conserves mais anonymises.
    """
    resultat = RGPDEngine.anonymiser_client(tenant_id, client_id, user_id)

    if not resultat["success"]:
        raise HTTPException(status_code=400, detail=resultat.get("error"))

    # Audit
    audit_context = AuditContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user.get("email"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    AuditLogger.log_create(
        module="rgpd_anonymisation",
        record_id=client_id,
        data={"action": "anonymisation", "client_id": str(client_id)},
        context=audit_context
    )

    logger.info(
        "rgpd_anonymisation",
        tenant_id=str(tenant_id),
        client_id=str(client_id),
        user_id=str(user_id)
    )

    return resultat


@rgpd_router.delete("/client/{client_id}/supprimer")
async def supprimer_donnees_client(
    client_id: UUID,
    request: Request,
    conserver_factures: bool = Query(True, description="Conserver les factures (obligation legale)"),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Supprime les donnees personnelles d'un client.
    Article 17 RGPD - Droit a l'effacement.

    ATTENTION: Cette action est irreversible.
    Les factures sont anonymisees mais conservees (obligation legale 10 ans).
    """
    resultat = RGPDEngine.supprimer_donnees_client(
        tenant_id, client_id, user_id, conserver_factures
    )

    if not resultat["success"]:
        raise HTTPException(status_code=400, detail=resultat.get("error"))

    # Audit
    audit_context = AuditContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user.get("email"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    AuditLogger.log_delete(
        module="rgpd_suppression",
        record_id=client_id,
        context=audit_context,
        deleted_data={"action": "suppression_rgpd", "client_id": str(client_id)}
    )

    logger.info(
        "rgpd_suppression",
        tenant_id=str(tenant_id),
        client_id=str(client_id),
        user_id=str(user_id),
        factures_conservees=conserver_factures
    )

    return resultat


# =============================================================================
# GESTION DES CONSENTEMENTS
# =============================================================================
@rgpd_router.get("/client/{client_id}/consentements")
async def lister_consentements_client(
    client_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Liste tous les consentements d'un client."""
    consentements = Database.query(
        "consentements",
        tenant_id,
        filters={"client_id": str(client_id)},
        order_by="date_consentement DESC"
    )
    return {"items": consentements, "total": len(consentements)}


@rgpd_router.post("/consentements")
async def creer_consentement(
    data: ConsentementCreate,
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Enregistre un nouveau consentement."""
    # Preparer les donnees
    consentement_data = data.model_dump()
    consentement_data["date_consentement"] = datetime.utcnow().isoformat()

    # Definir la date d'expiration
    config = RGPD_CONFIG.get("consentements", {})
    duree = config.get("duree_validite_jours", 730)
    consentement_data["date_expiration"] = (
        datetime.utcnow() + timedelta(days=duree)
    ).isoformat()

    # IP et User Agent
    if request.client:
        consentement_data["ip_address"] = request.client.host
    consentement_data["user_agent"] = request.headers.get("user-agent", "")

    # Version de la politique
    if not consentement_data.get("version_politique"):
        consentement_data["version_politique"] = RGPD_CONFIG.get(
            "rgpd", {}
        ).get("version_politique", "1.0")

    # Inserer
    consentement = Database.insert("consentements", tenant_id, consentement_data, user_id)

    # Historique
    RGPDEngine.enregistrer_historique_consentement(
        tenant_id=tenant_id,
        consentement_id=UUID(consentement["id"]),
        client_id=data.client_id,
        type_consentement=data.type_consentement,
        action="ACCORDE" if data.statut == "ACCORDE" else data.statut,
        ancien_statut=None,
        nouveau_statut=data.statut,
        source=data.source,
        ip_address=consentement_data.get("ip_address"),
        user_id=user_id
    )

    logger.info(
        "consentement_cree",
        tenant_id=str(tenant_id),
        client_id=str(data.client_id),
        type=data.type_consentement,
        statut=data.statut
    )

    return consentement


@rgpd_router.put("/consentements/{consentement_id}")
async def modifier_consentement(
    consentement_id: UUID,
    data: ConsentementUpdate,
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Modifie le statut d'un consentement (retrait, etc.)."""
    # Recuperer l'ancien consentement
    ancien = Database.get_by_id("consentements", tenant_id, consentement_id)
    if not ancien:
        raise HTTPException(status_code=404, detail="Consentement non trouve")

    # Mettre a jour
    update_data = data.model_dump(exclude_unset=True)
    consentement = Database.update(
        "consentements", tenant_id, consentement_id, update_data, user_id
    )

    # Historique
    RGPDEngine.enregistrer_historique_consentement(
        tenant_id=tenant_id,
        consentement_id=consentement_id,
        client_id=UUID(ancien["client_id"]),
        type_consentement=ancien["type_consentement"],
        action="RETIRE" if data.statut == "RETIRE" else "MODIFIE",
        ancien_statut=ancien["statut"],
        nouveau_statut=data.statut,
        source="API",
        ip_address=request.client.host if request.client else None,
        user_id=user_id
    )

    logger.info(
        "consentement_modifie",
        tenant_id=str(tenant_id),
        consentement_id=str(consentement_id),
        ancien_statut=ancien["statut"],
        nouveau_statut=data.statut
    )

    return consentement


@rgpd_router.post("/consentements/{consentement_id}/retirer")
async def retirer_consentement(
    consentement_id: UUID,
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Retire un consentement (droit de retrait)."""
    return await modifier_consentement(
        consentement_id,
        ConsentementUpdate(statut="RETIRE"),
        request,
        tenant_id,
        user_id,
        user
    )


# =============================================================================
# DEMANDES RGPD
# =============================================================================
@rgpd_router.get("/demandes")
async def lister_demandes_rgpd(
    statut: Optional[str] = None,
    type_demande: Optional[str] = None,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100)
):
    """Liste les demandes RGPD."""
    filters = {}
    if statut:
        filters["statut"] = statut
    if type_demande:
        filters["type_demande"] = type_demande

    demandes = Database.query(
        "demandes_rgpd",
        tenant_id,
        filters=filters,
        order_by="date_reception DESC",
        limit=limit,
        offset=skip
    )
    return {"items": demandes, "total": len(demandes)}


@rgpd_router.post("/demandes")
async def creer_demande_rgpd(
    data: DemandeRGPDCreate,
    request: Request,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Enregistre une nouvelle demande RGPD."""
    # Generer le numero
    numero = Database.next_sequence(tenant_id, "demande_rgpd")

    demande_data = data.model_dump()
    demande_data["numero"] = numero
    demande_data["date_reception"] = datetime.utcnow().isoformat()

    # Calculer la date limite (30 jours)
    delai = RGPD_CONFIG.get("delais", {}).get("reponse_standard", 30)
    demande_data["date_limite"] = (
        datetime.utcnow() + timedelta(days=delai)
    ).isoformat()

    demande_data["statut"] = "RECUE"

    demande = Database.insert("demandes_rgpd", tenant_id, demande_data, user_id)

    logger.info(
        "demande_rgpd_creee",
        tenant_id=str(tenant_id),
        numero=numero,
        type=data.type_demande,
        email=data.email_demandeur
    )

    return demande


@rgpd_router.get("/demandes/{demande_id}")
async def obtenir_demande_rgpd(
    demande_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Recupere une demande RGPD."""
    demande = Database.get_by_id("demandes_rgpd", tenant_id, demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande non trouvee")
    return demande


@rgpd_router.post("/demandes/{demande_id}/traiter")
async def traiter_demande_rgpd(
    demande_id: UUID,
    background_tasks: BackgroundTasks,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Traite automatiquement une demande RGPD.
    Lance le traitement en arriere-plan.
    """
    demande = Database.get_by_id("demandes_rgpd", tenant_id, demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande non trouvee")

    if demande["statut"] not in ["RECUE", "VERIFICATION_IDENTITE", "EN_COURS"]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de traiter une demande avec le statut {demande['statut']}"
        )

    # Mettre a jour le statut
    Database.update(
        "demandes_rgpd", tenant_id, demande_id,
        {"statut": "EN_COURS", "traite_par": str(user_id)},
        user_id
    )

    # Lancer le traitement en arriere-plan
    background_tasks.add_task(
        RGPDEngine.traiter_demande_async,
        tenant_id, demande_id, user_id
    )

    return {"message": "Traitement lance", "demande_id": str(demande_id)}


# =============================================================================
# POLITIQUES DE RETENTION
# =============================================================================
@rgpd_router.get("/retention/politiques")
async def lister_politiques_retention(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Liste les politiques de retention configurees."""
    politiques = Database.query(
        "politiques_retention",
        tenant_id,
        order_by="module ASC"
    )
    return {"items": politiques, "total": len(politiques)}


@rgpd_router.post("/retention/politiques")
async def creer_politique_retention(
    data: PolitiqueRetentionCreate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Cree une nouvelle politique de retention."""
    politique_data = data.model_dump()
    politique_data["actif"] = True

    politique = Database.insert(
        "politiques_retention", tenant_id, politique_data, user_id
    )

    logger.info(
        "politique_retention_creee",
        tenant_id=str(tenant_id),
        module=data.module,
        duree=data.duree_retention_jours
    )

    return politique


@rgpd_router.post("/retention/executer")
async def executer_politiques_retention(
    background_tasks: BackgroundTasks,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Execute toutes les politiques de retention actives."""
    # Lancer en arriere-plan
    background_tasks.add_task(
        RGPDEngine.executer_politiques_retention,
        tenant_id, user_id
    )

    return {"message": "Execution des politiques de retention lancee"}


# =============================================================================
# RAPPORTS DE CONFORMITE
# =============================================================================
@rgpd_router.get("/rapports/statistiques")
async def statistiques_rgpd(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Statistiques de conformite RGPD."""
    stats = RGPDEngine.generer_statistiques(tenant_id)
    return stats


@rgpd_router.get("/rapports/registre-traitements")
async def registre_traitements(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Genere le registre des activites de traitement.
    Obligatoire selon Article 30 RGPD.
    """
    registre = RGPDEngine.generer_registre_traitements(tenant_id)
    return registre


# =============================================================================
# POLITIQUE DE CONFIDENTIALITE
# =============================================================================
@rgpd_router.get("/politique-confidentialite")
async def obtenir_politique_confidentialite(
    tenant_id: UUID = Depends(get_current_tenant)
):
    """Retourne la politique de confidentialite."""
    politique = RGPD_CONFIG.get("politique_confidentialite", {})
    return politique


# =============================================================================
# RGPD Engine - Logique metier
# =============================================================================
class RGPDEngine:
    """Moteur de traitement RGPD."""

    # Modules a inclure dans les exports
    MODULES_EXPORT = [
        "clients", "devis", "factures", "paiements",
        "interventions", "documents", "consentements", "notes_client"
    ]

    # Champs a anonymiser par defaut
    CHAMPS_ANONYMISATION = {
        "clients": ["name", "legal_name", "email", "phone", "mobile",
                    "address_line1", "address_line2", "notes", "internal_notes"],
        "devis": ["notes", "conditions"],
        "factures": ["notes"],
        "interventions": ["description", "notes"],
    }

    @classmethod
    def generer_rapport_acces(
        cls,
        tenant_id: UUID,
        client_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Genere un rapport complet des donnees detenues sur un client.
        Article 15 RGPD.
        """
        # Verifier que le client existe
        client = Database.get_by_id("clients", tenant_id, client_id)
        if not client:
            return None

        rapport = {
            "date_generation": datetime.utcnow().isoformat(),
            "client_id": str(client_id),
            "tenant_id": str(tenant_id),
            "donnees_detenues": {},
            "finalites_traitement": [],
            "destinataires": [],
            "durees_conservation": {},
            "droits": []
        }

        # Donnees client directes
        rapport["donnees_detenues"]["informations_client"] = {
            k: v for k, v in client.items()
            if k not in ["tenant_id", "deleted_at", "created_by", "updated_by"]
        }

        # Donnees liees
        for module in cls.MODULES_EXPORT:
            if module == "clients":
                continue

            try:
                donnees = Database.query(
                    module, tenant_id,
                    filters={"client_id": str(client_id)},
                    limit=1000
                )
                if donnees:
                    rapport["donnees_detenues"][module] = [
                        {k: v for k, v in item.items()
                         if k not in ["tenant_id", "deleted_at"]}
                        for item in donnees
                    ]
            except Exception:
                pass

        # Consentements
        consentements = Database.query(
            "consentements", tenant_id,
            filters={"client_id": str(client_id)}
        )
        rapport["donnees_detenues"]["consentements"] = consentements

        # Finalites
        rapport["finalites_traitement"] = [
            "Gestion de la relation client",
            "Execution des contrats",
            "Facturation et comptabilite",
            "Communication commerciale (si consentement)"
        ]

        # Durees de conservation
        retention_config = RGPD_CONFIG.get("retention", {})
        for module, config in retention_config.items():
            if isinstance(config, dict):
                rapport["durees_conservation"][module] = {
                    "duree_jours": config.get("duree_jours"),
                    "action": config.get("action"),
                    "base_legale": config.get("base_legale")
                }

        # Droits
        rapport["droits"] = [
            {"droit": "Acces", "article": "Article 15", "description": "Obtenir une copie de vos donnees"},
            {"droit": "Rectification", "article": "Article 16", "description": "Corriger vos donnees"},
            {"droit": "Effacement", "article": "Article 17", "description": "Supprimer vos donnees"},
            {"droit": "Limitation", "article": "Article 18", "description": "Limiter le traitement"},
            {"droit": "Portabilite", "article": "Article 20", "description": "Recuperer vos donnees"},
            {"droit": "Opposition", "article": "Article 21", "description": "Vous opposer au traitement"}
        ]

        return rapport

    @classmethod
    def exporter_donnees_client(
        cls,
        tenant_id: UUID,
        client_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Exporte toutes les donnees d'un client.
        Article 20 RGPD - Droit a la portabilite.
        """
        client = Database.get_by_id("clients", tenant_id, client_id)
        if not client:
            return None

        export = {
            "export_info": {
                "date_export": datetime.utcnow().isoformat(),
                "format": "JSON",
                "version": "1.0",
                "rgpd_article": "Article 20 - Droit a la portabilite"
            },
            "client": {k: v for k, v in client.items()
                       if k not in ["tenant_id", "deleted_at", "created_by", "updated_by"]},
            "modules": {}
        }

        # Exporter les donnees liees
        for module in cls.MODULES_EXPORT:
            if module == "clients":
                continue

            try:
                donnees = Database.query(
                    module, tenant_id,
                    filters={"client_id": str(client_id)},
                    limit=10000
                )
                if donnees:
                    export["modules"][module] = [
                        {k: v for k, v in item.items()
                         if k not in ["tenant_id", "deleted_at", "created_by", "updated_by"]}
                        for item in donnees
                    ]
            except Exception:
                pass

        return export

    @classmethod
    def anonymiser_client(
        cls,
        tenant_id: UUID,
        client_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Anonymise les donnees personnelles d'un client.
        Conserve les factures (obligation legale) mais anonymisees.
        """
        client = Database.get_by_id("clients", tenant_id, client_id)
        if not client:
            return {"success": False, "error": "Client non trouve"}

        config = RGPD_CONFIG.get("anonymisation", {})
        valeurs = config.get("valeurs_remplacement", {})

        resultats = {"success": True, "anonymisations": []}

        try:
            # Anonymiser le client
            client_update = {
                "name": valeurs.get("nom", "ANONYMISE"),
                "legal_name": valeurs.get("nom", "ANONYMISE"),
                "email": valeurs.get("email", "anonymise@anonymise.local"),
                "phone": valeurs.get("telephone", "0000000000"),
                "mobile": valeurs.get("telephone", "0000000000"),
                "address_line1": valeurs.get("adresse", "Adresse anonymisee"),
                "address_line2": "",
                "notes": "",
                "internal_notes": "[DONNEES ANONYMISEES RGPD]",
                "is_active": False
            }
            Database.update("clients", tenant_id, client_id, client_update, user_id)
            resultats["anonymisations"].append({"module": "clients", "count": 1})

            # Anonymiser les modules lies
            for module, champs in cls.CHAMPS_ANONYMISATION.items():
                if module == "clients":
                    continue

                try:
                    items = Database.query(
                        module, tenant_id,
                        filters={"client_id": str(client_id)}
                    )

                    for item in items:
                        update_data = {}
                        for champ in champs:
                            if champ in item:
                                update_data[champ] = "[ANONYMISE]"

                        if update_data:
                            Database.update(
                                module, tenant_id,
                                UUID(item["id"]), update_data, user_id
                            )

                    if items:
                        resultats["anonymisations"].append({
                            "module": module,
                            "count": len(items)
                        })
                except Exception as e:
                    logger.warning(f"Erreur anonymisation {module}: {e}")

            # Mettre a jour les consentements
            consentements = Database.query(
                "consentements", tenant_id,
                filters={"client_id": str(client_id)}
            )
            for consent in consentements:
                Database.update(
                    "consentements", tenant_id,
                    UUID(consent["id"]),
                    {"statut": "RETIRE", "notes": "[ANONYMISATION RGPD]"},
                    user_id
                )

            return resultats

        except Exception as e:
            logger.error(f"Erreur anonymisation: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def supprimer_donnees_client(
        cls,
        tenant_id: UUID,
        client_id: UUID,
        user_id: UUID,
        conserver_factures: bool = True
    ) -> Dict[str, Any]:
        """
        Supprime les donnees d'un client.
        Les factures sont anonymisees si conserver_factures=True.
        """
        client = Database.get_by_id("clients", tenant_id, client_id)
        if not client:
            return {"success": False, "error": "Client non trouve"}

        resultats = {"success": True, "suppressions": [], "anonymisations": []}

        try:
            # Si on conserve les factures, les anonymiser d'abord
            if conserver_factures:
                factures = Database.query(
                    "factures", tenant_id,
                    filters={"client_id": str(client_id)}
                )
                for facture in factures:
                    Database.update(
                        "factures", tenant_id,
                        UUID(facture["id"]),
                        {
                            "notes": "[CLIENT SUPPRIME - DONNEES ANONYMISEES]",
                            "client_id": None  # Detacher du client
                        },
                        user_id
                    )
                if factures:
                    resultats["anonymisations"].append({
                        "module": "factures",
                        "count": len(factures),
                        "raison": "Obligation legale 10 ans"
                    })

            # Supprimer les autres modules
            modules_a_supprimer = ["devis", "interventions", "documents",
                                   "notes_client", "consentements", "paiements"]

            for module in modules_a_supprimer:
                try:
                    items = Database.query(
                        module, tenant_id,
                        filters={"client_id": str(client_id)}
                    )
                    for item in items:
                        Database.soft_delete(module, tenant_id, UUID(item["id"]))

                    if items:
                        resultats["suppressions"].append({
                            "module": module,
                            "count": len(items)
                        })
                except Exception:
                    pass

            # Supprimer le client
            Database.soft_delete("clients", tenant_id, client_id)
            resultats["suppressions"].append({"module": "clients", "count": 1})

            return resultats

        except Exception as e:
            logger.error(f"Erreur suppression: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def enregistrer_historique_consentement(
        cls,
        tenant_id: UUID,
        consentement_id: UUID,
        client_id: UUID,
        type_consentement: str,
        action: str,
        ancien_statut: Optional[str],
        nouveau_statut: str,
        source: str,
        ip_address: Optional[str],
        user_id: UUID
    ):
        """Enregistre une entree dans l'historique des consentements."""
        historique = {
            "consentement_id": str(consentement_id),
            "client_id": str(client_id),
            "type_consentement": type_consentement,
            "action": action,
            "ancien_statut": ancien_statut,
            "nouveau_statut": nouveau_statut,
            "date_action": datetime.utcnow().isoformat(),
            "effectue_par": str(user_id),
            "source": source,
            "ip_address": ip_address
        }

        try:
            Database.insert("historique_consentements", tenant_id, historique, user_id)
        except Exception as e:
            logger.warning(f"Erreur enregistrement historique consentement: {e}")

    @classmethod
    async def traiter_demande_async(
        cls,
        tenant_id: UUID,
        demande_id: UUID,
        user_id: UUID
    ):
        """Traite une demande RGPD de maniere asynchrone."""
        demande = Database.get_by_id("demandes_rgpd", tenant_id, demande_id)
        if not demande:
            return

        try:
            type_demande = demande["type_demande"]
            client_id = demande.get("client_id")
            actions = []

            if type_demande == "ACCES" and client_id:
                # Generer le rapport d'acces
                rapport = cls.generer_rapport_acces(tenant_id, UUID(client_id))
                actions.append({"action": "rapport_acces_genere", "resultat": "OK"})

            elif type_demande == "PORTABILITE" and client_id:
                # Generer l'export
                export = cls.exporter_donnees_client(tenant_id, UUID(client_id))
                actions.append({"action": "export_genere", "resultat": "OK"})

            elif type_demande == "EFFACEMENT" and client_id:
                # Anonymiser
                resultat = cls.anonymiser_client(tenant_id, UUID(client_id), user_id)
                actions.append({"action": "anonymisation", "resultat": resultat})

            # Mettre a jour la demande
            Database.update(
                "demandes_rgpd", tenant_id, demande_id,
                {
                    "statut": "COMPLETEE",
                    "date_reponse": datetime.utcnow().isoformat(),
                    "actions_effectuees": json.dumps(actions)
                },
                user_id
            )

            logger.info(
                "demande_rgpd_traitee",
                demande_id=str(demande_id),
                type=type_demande
            )

        except Exception as e:
            logger.error(f"Erreur traitement demande RGPD: {e}")
            Database.update(
                "demandes_rgpd", tenant_id, demande_id,
                {"statut": "REFUSEE", "motif_refus": str(e)},
                user_id
            )

    @classmethod
    async def executer_politiques_retention(
        cls,
        tenant_id: UUID,
        user_id: UUID
    ):
        """Execute les politiques de retention actives."""
        politiques = Database.query(
            "politiques_retention", tenant_id,
            filters={"actif": True}
        )

        for politique in politiques:
            try:
                module = politique["module"]
                duree = politique["duree_retention_jours"]
                action = politique["action_expiration"]
                date_limite = (datetime.utcnow() - timedelta(days=duree)).isoformat()

                # Trouver les enregistrements expires
                # Note: Simplification - en production, utiliser une requete SQL directe
                items = Database.query(module, tenant_id, limit=1000)
                expired = [
                    item for item in items
                    if item.get("created_at") and item["created_at"] < date_limite
                ]

                for item in expired:
                    if action == "ANONYMISER":
                        champs = politique.get("champs_a_anonymiser", [])
                        update = {c: "[RETENTION_EXPIRE]" for c in champs}
                        Database.update(module, tenant_id, UUID(item["id"]), update, user_id)

                    elif action == "SUPPRIMER":
                        Database.soft_delete(module, tenant_id, UUID(item["id"]))

                # Mettre a jour la politique
                Database.update(
                    "politiques_retention", tenant_id,
                    UUID(politique["id"]),
                    {"derniere_execution": datetime.utcnow().isoformat()},
                    user_id
                )

                logger.info(
                    "politique_retention_executee",
                    module=module,
                    action=action,
                    count=len(expired)
                )

            except Exception as e:
                logger.error(f"Erreur execution politique retention: {e}")

    @classmethod
    def generer_statistiques(cls, tenant_id: UUID) -> Dict[str, Any]:
        """Genere les statistiques RGPD."""
        stats = {
            "date_generation": datetime.utcnow().isoformat(),
            "consentements": {},
            "demandes": {},
            "retention": {}
        }

        # Statistiques consentements
        try:
            consentements = Database.query("consentements", tenant_id, limit=10000)
            stats["consentements"]["total"] = len(consentements)
            stats["consentements"]["par_statut"] = {}
            stats["consentements"]["par_type"] = {}

            for c in consentements:
                statut = c.get("statut", "INCONNU")
                stats["consentements"]["par_statut"][statut] = \
                    stats["consentements"]["par_statut"].get(statut, 0) + 1

                type_c = c.get("type_consentement", "INCONNU")
                stats["consentements"]["par_type"][type_c] = \
                    stats["consentements"]["par_type"].get(type_c, 0) + 1
        except Exception:
            pass

        # Statistiques demandes
        try:
            demandes = Database.query("demandes_rgpd", tenant_id, limit=10000)
            stats["demandes"]["total"] = len(demandes)
            stats["demandes"]["par_statut"] = {}
            stats["demandes"]["par_type"] = {}

            for d in demandes:
                statut = d.get("statut", "INCONNU")
                stats["demandes"]["par_statut"][statut] = \
                    stats["demandes"]["par_statut"].get(statut, 0) + 1

                type_d = d.get("type_demande", "INCONNU")
                stats["demandes"]["par_type"][type_d] = \
                    stats["demandes"]["par_type"].get(type_d, 0) + 1
        except Exception:
            pass

        return stats

    @classmethod
    def generer_registre_traitements(cls, tenant_id: UUID) -> Dict[str, Any]:
        """
        Genere le registre des activites de traitement.
        Obligatoire selon Article 30 RGPD.
        """
        registre = {
            "date_generation": datetime.utcnow().isoformat(),
            "responsable_traitement": {
                "nom": "[A COMPLETER]",
                "adresse": "[A COMPLETER]",
                "contact_dpo": "[A COMPLETER]"
            },
            "traitements": []
        }

        # Liste des traitements par module
        traitements = [
            {
                "nom": "Gestion des clients",
                "finalite": "Gestion de la relation client et prospection commerciale",
                "categories_personnes": ["Clients", "Prospects", "Contacts professionnels"],
                "categories_donnees": ["Identification", "Contact", "Professionnel"],
                "destinataires": ["Personnel interne", "Sous-traitants techniques"],
                "transferts": "Non",
                "duree_conservation": "3 ans apres fin de relation",
                "base_legale": "Execution du contrat / Interet legitime"
            },
            {
                "nom": "Facturation",
                "finalite": "Emission et suivi des factures",
                "categories_personnes": ["Clients"],
                "categories_donnees": ["Identification", "Facturation", "Bancaire"],
                "destinataires": ["Personnel comptable", "Expert-comptable"],
                "transferts": "Non",
                "duree_conservation": "10 ans (obligation legale)",
                "base_legale": "Obligation legale"
            },
            {
                "nom": "Gestion des interventions",
                "finalite": "Planification et suivi des interventions",
                "categories_personnes": ["Clients", "Techniciens"],
                "categories_donnees": ["Identification", "Localisation", "Technique"],
                "destinataires": ["Personnel technique"],
                "transferts": "Non",
                "duree_conservation": "5 ans",
                "base_legale": "Execution du contrat"
            },
            {
                "nom": "Marketing et communication",
                "finalite": "Envoi de communications commerciales",
                "categories_personnes": ["Clients avec consentement", "Prospects"],
                "categories_donnees": ["Identification", "Contact", "Preferences"],
                "destinataires": ["Personnel marketing"],
                "transferts": "Non",
                "duree_conservation": "3 ans sans interaction",
                "base_legale": "Consentement"
            }
        ]

        registre["traitements"] = traitements

        # Ajouter les politiques de retention configurees
        try:
            politiques = Database.query("politiques_retention", tenant_id)
            registre["politiques_retention"] = [
                {
                    "module": p["module"],
                    "duree_jours": p["duree_retention_jours"],
                    "action": p["action_expiration"],
                    "base_legale": p["base_legale"]
                }
                for p in politiques
            ]
        except Exception:
            registre["politiques_retention"] = []

        return registre
