# =============================================================================
# AZALPLUS - API Technicien Mobile
# =============================================================================
"""
API endpoints specialises pour les techniciens de terrain.

Endpoints:
    GET  /api/v1/technicien/dashboard           - Dashboard du jour
    GET  /api/v1/technicien/interventions       - Liste interventions assignees
    GET  /api/v1/technicien/intervention/{id}   - Detail intervention
    POST /api/v1/technicien/intervention/{id}/arrivee    - Marquer arrivee sur site
    POST /api/v1/technicien/intervention/{id}/demarrer   - Demarrer intervention
    POST /api/v1/technicien/intervention/{id}/photos     - Upload photos
    POST /api/v1/technicien/intervention/{id}/materiel   - Saisir materiel
    POST /api/v1/technicien/intervention/{id}/rapport    - Saisir rapport
    POST /api/v1/technicien/intervention/{id}/terminer   - Terminer travaux
    POST /api/v1/technicien/intervention/{id}/signer     - Signature client
    POST /api/v1/technicien/intervention/{id}/facturer   - Creer facture brouillon
    GET  /api/v1/technicien/produits/search     - Recherche produits pour materiel
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, date, timedelta
from decimal import Decimal
import structlog
import base64

from .db import Database
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth, require_role

logger = structlog.get_logger()

# =============================================================================
# Router Technicien
# =============================================================================
router_technicien = APIRouter(
    prefix="/technicien",
    tags=["Technicien Mobile"]
)


# =============================================================================
# Pydantic Models - Request
# =============================================================================

class GPSCoordinates(BaseModel):
    """Coordonnees GPS."""
    lat: Optional[float] = Field(None, description="Latitude")
    lng: Optional[float] = Field(None, description="Longitude")

    def is_valid(self) -> bool:
        """Vérifie si les coordonnées sont valides."""
        return self.lat is not None and self.lng is not None


class ArriveeRequest(BaseModel):
    """Requete pour marquer l'arrivee sur site."""
    gps: Optional[GPSCoordinates] = Field(None, description="Coordonnees GPS")


class DemarrerRequest(BaseModel):
    """Requete pour demarrer l'intervention."""
    gps: Optional[GPSCoordinates] = Field(None, description="Coordonnees GPS")
    constat_arrivee: Optional[str] = Field(None, description="Constat a l'arrivee")


class PhotoUpload(BaseModel):
    """Upload d'une photo."""
    type: str = Field(..., description="Type: avant ou apres")
    data: str = Field(..., description="Photo en base64")
    gps: Optional[GPSCoordinates] = Field(None, description="Coordonnees GPS")


class MaterielLigne(BaseModel):
    """Une ligne de materiel utilise."""
    produit_id: Optional[UUID] = Field(None, description="ID produit (si catalogue)")
    designation: str = Field(..., description="Designation")
    quantite: float = Field(1, description="Quantite")
    unite: str = Field("u", description="Unite")
    prix_unitaire: float = Field(0, description="Prix unitaire HT")
    notes: Optional[str] = Field(None, description="Notes")


class MaterielRequest(BaseModel):
    """Requete pour saisir le materiel."""
    lignes: List[MaterielLigne] = Field(default_factory=list, description="Lignes materiel")
    texte_libre: Optional[str] = Field(None, description="Materiel non catalogue")


class RapportRequest(BaseModel):
    """Requete pour saisir le rapport."""
    travaux_realises: str = Field(..., description="Description des travaux")
    anomalies: Optional[str] = Field(None, description="Anomalies constatees")
    recommandations: Optional[str] = Field(None, description="Recommandations")


class SignatureRequest(BaseModel):
    """Requete pour la signature client."""
    nom_signataire: str = Field(..., description="Nom du signataire")
    signature: str = Field(..., description="Signature en base64 PNG")
    avis_client: int = Field(..., ge=1, le=5, description="Note de 1 a 5")
    appreciation: Optional[str] = Field(None, description="Commentaire client")


# =============================================================================
# Pydantic Models - Response
# =============================================================================

class InterventionSummary(BaseModel):
    """Resume d'une intervention pour la liste."""
    id: UUID
    reference: str
    client_nom: str
    client_id: UUID
    statut: str
    priorite: str
    type_intervention: Optional[str]
    date_prevue_debut: Optional[datetime]
    adresse_ligne1: Optional[str]
    ville: Optional[str]
    code_postal: Optional[str]
    description: Optional[str]
    titre: Optional[str]


class DashboardResponse(BaseModel):
    """Reponse du dashboard technicien."""
    interventions_aujourdhui: int
    interventions_semaine: int
    interventions_en_cours: int
    heures_saisies_semaine: float
    interventions: List[InterventionSummary]
    date_serveur: datetime


class InterventionDetail(BaseModel):
    """Detail complet d'une intervention."""
    id: UUID
    reference: str
    statut: str
    priorite: str
    type_intervention: Optional[str]

    # Client
    client_id: UUID
    client_nom: str
    client_telephone: Optional[str]
    client_email: Optional[str]

    # Contact sur place
    contact_sur_place: Optional[str]
    telephone_contact: Optional[str]

    # Adresse
    adresse_ligne1: Optional[str]
    adresse_ligne2: Optional[str]
    ville: Optional[str]
    code_postal: Optional[str]
    pays: Optional[str]

    # Planification
    date_prevue_debut: Optional[datetime]
    date_prevue_fin: Optional[datetime]
    duree_prevue_minutes: Optional[int]

    # Description
    titre: Optional[str]
    description: Optional[str]
    notes_internes: Optional[str]

    # Donnees saisies
    date_arrivee_site: Optional[datetime]
    date_demarrage: Optional[datetime]
    date_fin: Optional[datetime]
    duree_reelle_minutes: Optional[int]
    constat_arrivee: Optional[str]
    travaux_realises: Optional[str]
    photos_avant: Optional[List[Dict]]
    photos_apres: Optional[List[Dict]]
    materiel_utilise_lignes: Optional[List[Dict]]
    materiel_utilise: Optional[str]
    is_signed: bool

    # Facturation
    facturable: bool
    montant_ht: Optional[float]


class ProduitSearch(BaseModel):
    """Resultat recherche produit."""
    id: UUID
    code: str
    nom: str
    prix_vente: float
    unite: str
    stock_disponible: Optional[float]


# =============================================================================
# Endpoints Dashboard
# =============================================================================

@router_technicien.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard technicien du jour"
)
async def get_dashboard(
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Retourne le dashboard technicien avec:
    - Compteurs (interventions jour/semaine, en cours, heures)
    - Liste des interventions du jour triees par heure
    """
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())

    # Interventions assignees au technicien
    interventions = Database.query(
        "interventions",
        tenant_id,
        filters={
            "intervenant_id": user_id,
            "statut": {"$nin": ["ANNULEE"]}
        },
        sort=[("date_prevue_debut", "ASC")]
    )

    # Filtrer pour aujourd'hui
    interventions_today = []
    interventions_week = []
    interventions_en_cours = []

    for intv in interventions:
        date_prevue = intv.get("date_prevue_debut")
        statut = intv.get("statut")

        if date_prevue:
            date_intv = date_prevue.date() if isinstance(date_prevue, datetime) else date_prevue

            if date_intv == today:
                interventions_today.append(intv)

            if date_intv >= start_of_week:
                interventions_week.append(intv)

        if statut in ["SUR_SITE", "EN_COURS"]:
            interventions_en_cours.append(intv)
            if intv not in interventions_today:
                interventions_today.append(intv)

    # Heures saisies cette semaine
    temps_entries = Database.query(
        "temps",
        tenant_id,
        filters={
            "user_id": user_id,
            "date": {"$gte": start_of_week}
        }
    )
    heures_semaine = sum(
        (e.get("duree_minutes", 0) or 0) / 60
        for e in temps_entries
    )

    # Enrichir avec noms clients
    client_ids = list(set(i.get("client_id") for i in interventions_today if i.get("client_id")))
    clients = {}
    if client_ids:
        clients_data = Database.query(
            "clients",
            tenant_id,
            filters={"id": {"$in": client_ids}}
        )
        clients = {c["id"]: c.get("nom", c.get("raison_sociale", "")) for c in clients_data}

    # Formatter les interventions
    interventions_list = [
        InterventionSummary(
            id=i["id"],
            reference=i.get("reference", ""),
            client_nom=clients.get(i.get("client_id"), "Client inconnu"),
            client_id=i.get("client_id"),
            statut=i.get("statut", "DRAFT"),
            priorite=i.get("priorite", "NORMAL"),
            type_intervention=i.get("type_intervention"),
            date_prevue_debut=i.get("date_prevue_debut"),
            adresse_ligne1=i.get("adresse_ligne1"),
            ville=i.get("ville"),
            code_postal=i.get("code_postal"),
            description=i.get("description"),
            titre=i.get("titre")
        )
        for i in interventions_today
    ]

    return DashboardResponse(
        interventions_aujourdhui=len(interventions_today),
        interventions_semaine=len(interventions_week),
        interventions_en_cours=len(interventions_en_cours),
        heures_saisies_semaine=round(heures_semaine, 1),
        interventions=interventions_list,
        date_serveur=datetime.now()
    )


@router_technicien.get(
    "/interventions",
    response_model=List[InterventionSummary],
    summary="Liste des interventions assignees"
)
async def get_interventions(
    statut: Optional[str] = None,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Liste toutes les interventions assignees au technicien."""
    filters = {
        "intervenant_id": user_id,
        "statut": {"$nin": ["ANNULEE"]}
    }

    if statut:
        filters["statut"] = statut

    if date_debut:
        filters["date_prevue_debut"] = {"$gte": datetime.combine(date_debut, datetime.min.time())}

    if date_fin:
        if "date_prevue_debut" in filters:
            filters["date_prevue_debut"]["$lte"] = datetime.combine(date_fin, datetime.max.time())
        else:
            filters["date_prevue_debut"] = {"$lte": datetime.combine(date_fin, datetime.max.time())}

    interventions = Database.query(
        "interventions",
        tenant_id,
        filters=filters,
        sort=[("date_prevue_debut", "ASC")]
    )

    # Enrichir avec noms clients
    client_ids = list(set(i.get("client_id") for i in interventions if i.get("client_id")))
    clients = {}
    if client_ids:
        clients_data = Database.query(
            "clients",
            tenant_id,
            filters={"id": {"$in": client_ids}}
        )
        clients = {c["id"]: c.get("nom", c.get("raison_sociale", "")) for c in clients_data}

    return [
        InterventionSummary(
            id=i["id"],
            reference=i.get("reference", ""),
            client_nom=clients.get(i.get("client_id"), "Client inconnu"),
            client_id=i.get("client_id"),
            statut=i.get("statut", "DRAFT"),
            priorite=i.get("priorite", "NORMAL"),
            type_intervention=i.get("type_intervention"),
            date_prevue_debut=i.get("date_prevue_debut"),
            adresse_ligne1=i.get("adresse_ligne1"),
            ville=i.get("ville"),
            code_postal=i.get("code_postal"),
            description=i.get("description"),
            titre=i.get("titre")
        )
        for i in interventions
    ]


# =============================================================================
# Endpoints Detail Intervention
# =============================================================================

@router_technicien.get(
    "/intervention/{intervention_id}",
    response_model=InterventionDetail,
    summary="Detail d'une intervention"
)
async def get_intervention_detail(
    intervention_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """Retourne le detail complet d'une intervention."""
    intervention = Database.get(
        "interventions",
        tenant_id,
        intervention_id
    )

    if not intervention:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intervention non trouvee"
        )

    # Verifier que l'intervention est assignee au technicien
    if intervention.get("intervenant_id") != user_id:
        # Verifier si l'utilisateur est admin/manager
        user_role = user.get("role", "")
        if user_role not in ["admin", "manager"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Intervention non assignee a ce technicien"
            )

    # Recuperer le client
    client = Database.get(
        "clients",
        tenant_id,
        intervention.get("client_id")
    )
    client_nom = client.get("nom", client.get("raison_sociale", "")) if client else "Client inconnu"
    client_tel = client.get("telephone") if client else None
    client_email = client.get("email") if client else None

    return InterventionDetail(
        id=intervention["id"],
        reference=intervention.get("reference", ""),
        statut=intervention.get("statut", "DRAFT"),
        priorite=intervention.get("priorite", "NORMAL"),
        type_intervention=intervention.get("type_intervention"),
        client_id=intervention.get("client_id"),
        client_nom=client_nom,
        client_telephone=client_tel,
        client_email=client_email,
        contact_sur_place=intervention.get("contact_sur_place"),
        telephone_contact=intervention.get("telephone_contact"),
        adresse_ligne1=intervention.get("adresse_ligne1"),
        adresse_ligne2=intervention.get("adresse_ligne2"),
        ville=intervention.get("ville"),
        code_postal=intervention.get("code_postal"),
        pays=intervention.get("pays"),
        date_prevue_debut=intervention.get("date_prevue_debut"),
        date_prevue_fin=intervention.get("date_prevue_fin"),
        duree_prevue_minutes=intervention.get("duree_prevue_minutes"),
        titre=intervention.get("titre"),
        description=intervention.get("description"),
        notes_internes=intervention.get("notes_internes"),
        date_arrivee_site=intervention.get("date_arrivee_site"),
        date_demarrage=intervention.get("date_demarrage"),
        date_fin=intervention.get("date_fin"),
        duree_reelle_minutes=intervention.get("duree_reelle_minutes"),
        constat_arrivee=intervention.get("constat_arrivee"),
        travaux_realises=intervention.get("travaux_realises"),
        photos_avant=intervention.get("photos_avant"),
        photos_apres=intervention.get("photos_apres"),
        materiel_utilise_lignes=intervention.get("materiel_utilise_lignes"),
        materiel_utilise=intervention.get("materiel_utilise"),
        is_signed=intervention.get("is_signed", False),
        facturable=intervention.get("facturable", True),
        montant_ht=intervention.get("montant_ht")
    )


# =============================================================================
# Endpoints Actions Workflow
# =============================================================================

@router_technicien.post(
    "/intervention/{intervention_id}/arrivee",
    summary="Marquer l'arrivee sur site"
)
async def marquer_arrivee(
    intervention_id: UUID,
    request: ArriveeRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Marque l'arrivee du technicien sur site.
    Enregistre la date/heure et les coordonnees GPS.
    Passe le statut a SUR_SITE.
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    if intervention.get("statut") not in ["DRAFT", "A_PLANIFIER", "PLANIFIEE", None]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de marquer l'arrivee depuis le statut {intervention.get('statut')}"
        )

    update_data = {
        "statut": "SUR_SITE",
        "date_arrivee_site": datetime.now()
    }

    if request.gps:
        update_data["geoloc_arrivee_lat"] = request.gps.lat
        update_data["geoloc_arrivee_lng"] = request.gps.lng

    Database.update("interventions", tenant_id, intervention_id, update_data)

    logger.info(
        "technicien_arrivee",
        intervention_id=str(intervention_id),
        technicien_id=str(user_id),
        tenant_id=str(tenant_id)
    )

    return {"success": True, "statut": "SUR_SITE", "message": "Arrivee enregistree"}


@router_technicien.post(
    "/intervention/{intervention_id}/demarrer",
    summary="Demarrer l'intervention"
)
async def demarrer_intervention(
    intervention_id: UUID,
    request: DemarrerRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Demarre l'intervention.
    Enregistre la date/heure de debut.
    Passe le statut a EN_COURS.
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    if intervention.get("statut") not in ["SUR_SITE", "PLANIFIEE"]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de demarrer depuis le statut {intervention.get('statut')}"
        )

    update_data = {
        "statut": "EN_COURS",
        "date_demarrage": datetime.now()
    }

    if request.constat_arrivee:
        update_data["constat_arrivee"] = request.constat_arrivee

    if request.gps:
        update_data["geoloc_arrivee_lat"] = request.gps.lat
        update_data["geoloc_arrivee_lng"] = request.gps.lng

    Database.update("interventions", tenant_id, intervention_id, update_data)

    logger.info(
        "technicien_demarrage",
        intervention_id=str(intervention_id),
        technicien_id=str(user_id)
    )

    return {"success": True, "statut": "EN_COURS", "message": "Intervention demarree"}


@router_technicien.post(
    "/intervention/{intervention_id}/photos",
    summary="Ajouter des photos"
)
async def ajouter_photos(
    intervention_id: UUID,
    photo: PhotoUpload,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Ajoute une photo a l'intervention (avant ou apres).
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    # Determiner le champ cible
    if photo.type == "avant":
        field = "photos_avant"
    elif photo.type == "apres":
        field = "photos_apres"
    else:
        raise HTTPException(status_code=400, detail="Type de photo invalide (avant/apres)")

    # Recuperer les photos existantes
    photos_existantes = intervention.get(field) or []

    # Ajouter la nouvelle photo
    nouvelle_photo = {
        "data": photo.data,  # En production: stocker sur S3/GCS et garder l'URL
        "timestamp": datetime.now().isoformat(),
        "uploaded_by": str(user_id)
    }

    if photo.gps:
        nouvelle_photo["gps"] = {"lat": photo.gps.lat, "lng": photo.gps.lng}

    photos_existantes.append(nouvelle_photo)

    Database.update(
        "interventions",
        tenant_id,
        intervention_id,
        {field: photos_existantes}
    )

    return {
        "success": True,
        "type": photo.type,
        "count": len(photos_existantes),
        "message": f"Photo {photo.type} ajoutee ({len(photos_existantes)} total)"
    }


@router_technicien.post(
    "/intervention/{intervention_id}/materiel",
    summary="Saisir le materiel utilise"
)
async def saisir_materiel(
    intervention_id: UUID,
    request: MaterielRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Enregistre le materiel utilise (articles + texte libre).
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    # Calculer les prix totaux
    lignes_avec_totaux = []
    montant_total = 0

    for ligne in request.lignes:
        prix_total = ligne.quantite * ligne.prix_unitaire
        lignes_avec_totaux.append({
            "produit_id": str(ligne.produit_id) if ligne.produit_id else None,
            "designation": ligne.designation,
            "quantite": ligne.quantite,
            "unite": ligne.unite,
            "prix_unitaire": ligne.prix_unitaire,
            "prix_total": round(prix_total, 2),
            "notes": ligne.notes
        })
        montant_total += prix_total

    update_data = {
        "materiel_utilise_lignes": lignes_avec_totaux
    }

    if request.texte_libre:
        update_data["materiel_utilise"] = request.texte_libre

    Database.update("interventions", tenant_id, intervention_id, update_data)

    return {
        "success": True,
        "lignes_count": len(lignes_avec_totaux),
        "montant_total": round(montant_total, 2),
        "message": "Materiel enregistre"
    }


@router_technicien.post(
    "/intervention/{intervention_id}/rapport",
    summary="Saisir le rapport des travaux"
)
async def saisir_rapport(
    intervention_id: UUID,
    request: RapportRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Enregistre le rapport des travaux realises.
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    update_data = {
        "travaux_realises": request.travaux_realises
    }

    if request.anomalies:
        update_data["anomalies"] = request.anomalies

    if request.recommandations:
        update_data["recommandations"] = request.recommandations

    Database.update("interventions", tenant_id, intervention_id, update_data)

    return {"success": True, "message": "Rapport enregistre"}


@router_technicien.post(
    "/intervention/{intervention_id}/terminer",
    summary="Terminer les travaux"
)
async def terminer_travaux(
    intervention_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Termine les travaux (avant signature client).
    Calcule la duree reelle.
    Passe le statut a TRAVAUX_TERMINES.
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    if intervention.get("statut") not in ["EN_COURS"]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de terminer depuis le statut {intervention.get('statut')}"
        )

    # Calculer la duree reelle
    date_fin = datetime.now()
    date_demarrage = intervention.get("date_demarrage")
    duree_minutes = None

    if date_demarrage:
        delta = date_fin - date_demarrage
        duree_minutes = int(delta.total_seconds() / 60)

    update_data = {
        "statut": "TRAVAUX_TERMINES",
        "date_fin": date_fin
    }

    if duree_minutes:
        update_data["duree_reelle_minutes"] = duree_minutes

    Database.update("interventions", tenant_id, intervention_id, update_data)

    return {
        "success": True,
        "statut": "TRAVAUX_TERMINES",
        "duree_minutes": duree_minutes,
        "message": "Travaux termines"
    }


@router_technicien.post(
    "/intervention/{intervention_id}/signer",
    summary="Signature client et cloture"
)
async def signer_intervention(
    intervention_id: UUID,
    request: SignatureRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Enregistre la signature client et cloture l'intervention.
    Declenche la creation de la facture brouillon si facturable.
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Autoriser: intervenant assigne, createur, ou admin
    is_intervenant = str(intervention.get("intervenant_id")) == str(user_id)
    is_creator = str(intervention.get("created_by")) == str(user_id)
    is_admin = user.get("role") in ["ADMIN", "SUPER_ADMIN", "admin", "super_admin"]

    if not (is_intervenant or is_creator or is_admin):
        raise HTTPException(status_code=403, detail="Non autorise")

    if intervention.get("statut") not in ["TRAVAUX_TERMINES", "EN_COURS"]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de signer depuis le statut {intervention.get('statut')}"
        )

    update_data = {
        "statut": "TERMINEE",
        "nom_signataire": request.nom_signataire,
        "signature_client": request.signature,
        "avis_client": request.avis_client,
        "date_signature": datetime.now(),
        "is_signed": True
    }

    if request.appreciation:
        update_data["appreciation_client"] = request.appreciation

    # Si pas de date_fin, la definir maintenant
    if not intervention.get("date_fin"):
        update_data["date_fin"] = datetime.now()

    Database.update("interventions", tenant_id, intervention_id, update_data)

    # Creer la facture brouillon si facturable
    facture_id = None
    if intervention.get("facturable", True):
        facture_id = await _creer_facture_brouillon(
            tenant_id,
            intervention_id,
            intervention,
            user_id
        )

        if facture_id:
            Database.update(
                "interventions",
                tenant_id,
                intervention_id,
                {"facture_generee_id": facture_id}
            )

    logger.info(
        "technicien_signature",
        intervention_id=str(intervention_id),
        technicien_id=str(user_id),
        facture_id=str(facture_id) if facture_id else None
    )

    return {
        "success": True,
        "statut": "TERMINEE",
        "facture_id": str(facture_id) if facture_id else None,
        "message": "Intervention terminee et signee"
    }


# =============================================================================
# Endpoint Creation Facture
# =============================================================================

async def _creer_facture_brouillon(
    tenant_id: UUID,
    intervention_id: UUID,
    intervention: dict,
    user_id: UUID
) -> Optional[UUID]:
    """
    Cree une facture brouillon a partir de l'intervention.
    Inclut la main d'oeuvre et le materiel utilise.
    """
    try:
        # Generer le numero de facture
        # TODO: Utiliser le generateur de sequence du tenant
        facture_number = f"FAC-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Recuperer le tarif horaire (depuis config tenant ou defaut)
        tarif_horaire = 50.0  # TODO: Recuperer depuis config tenant

        # Calculer la duree en heures
        duree_minutes = intervention.get("duree_reelle_minutes", 0) or 0
        duree_heures = duree_minutes / 60

        # Construire les lignes de facture
        lignes = []

        # Ligne main d'oeuvre
        if duree_heures > 0:
            lignes.append({
                "description": f"Main d'oeuvre - Intervention {intervention.get('reference', '')}",
                "quantity": round(duree_heures, 2),
                "unit_price": tarif_horaire,
                "subtotal": round(duree_heures * tarif_horaire, 2),
                "taxe_id": None,  # TODO: TVA par defaut
                "tax_amount": round(duree_heures * tarif_horaire * 0.2, 2)  # TVA 20%
            })

        # Lignes materiel
        materiel_lignes = intervention.get("materiel_utilise_lignes") or []
        for mat in materiel_lignes:
            lignes.append({
                "product_id": mat.get("produit_id"),
                "description": mat.get("designation", "Materiel"),
                "quantity": mat.get("quantite", 1),
                "unit_price": mat.get("prix_unitaire", 0),
                "subtotal": mat.get("prix_total", 0),
                "taxe_id": None,
                "tax_amount": round(mat.get("prix_total", 0) * 0.2, 2)
            })

        # Calculer les totaux
        subtotal = sum(l.get("subtotal", 0) for l in lignes)
        tax_amount = sum(l.get("tax_amount", 0) for l in lignes)
        total = subtotal + tax_amount

        # Creer la facture
        facture_data = {
            "number": facture_number,
            "status": "DRAFT",
            "customer_id": intervention.get("client_id"),
            "date": datetime.now(),
            "due_date": datetime.now() + timedelta(days=30),
            "lignes": lignes,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total": total,
            "notes": f"Facture generee automatiquement depuis l'intervention {intervention.get('reference', '')}",
            "intervention_id": str(intervention_id),
            "created_by": str(user_id)
        }

        facture_id = Database.create("factures", tenant_id, facture_data)

        logger.info(
            "facture_brouillon_creee",
            facture_id=str(facture_id),
            intervention_id=str(intervention_id),
            total=total
        )

        return facture_id

    except Exception as e:
        logger.error(
            "erreur_creation_facture",
            intervention_id=str(intervention_id),
            error=str(e)
        )
        return None


# =============================================================================
# Endpoint Recherche Produits
# =============================================================================

@router_technicien.get(
    "/produits/search",
    response_model=List[ProduitSearch],
    summary="Rechercher des produits pour le materiel"
)
async def rechercher_produits(
    q: str,
    limit: int = 20,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Recherche des produits par code ou nom.
    Utilise pour la saisie du materiel utilise.
    """
    if len(q) < 2:
        return []

    # Recherche dans le nom et le code
    produits = Database.search(
        "produits",
        tenant_id,
        query=q,
        fields=["code", "name", "nom", "sku"],
        limit=limit
    )

    return [
        ProduitSearch(
            id=p["id"],
            code=p.get("code", p.get("sku", "")),
            nom=p.get("name", p.get("nom", "")),
            prix_vente=p.get("sale_price", p.get("prix_vente", 0)) or 0,
            unite=p.get("unit", p.get("unite", "u")) or "u",
            stock_disponible=p.get("stock_disponible")
        )
        for p in produits
    ]


# =============================================================================
# Endpoint Guidage
# =============================================================================

@router_technicien.get(
    "/intervention/{intervention_id}/navigation",
    summary="Obtenir les infos de navigation"
)
async def get_navigation_info(
    intervention_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Retourne les informations pour la navigation GPS.
    """
    intervention = Database.get("interventions", tenant_id, intervention_id)

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Construire l'adresse complete
    adresse_parts = []
    if intervention.get("adresse_ligne1"):
        adresse_parts.append(intervention["adresse_ligne1"])
    if intervention.get("adresse_ligne2"):
        adresse_parts.append(intervention["adresse_ligne2"])
    if intervention.get("code_postal"):
        adresse_parts.append(intervention["code_postal"])
    if intervention.get("ville"):
        adresse_parts.append(intervention["ville"])
    if intervention.get("pays"):
        adresse_parts.append(intervention["pays"])

    adresse_complete = ", ".join(adresse_parts)

    # Encoder pour les URLs
    import urllib.parse
    adresse_encoded = urllib.parse.quote(adresse_complete)

    return {
        "adresse": adresse_complete,
        "urls": {
            "google_maps": f"https://www.google.com/maps/dir/?api=1&destination={adresse_encoded}",
            "apple_maps": f"http://maps.apple.com/?daddr={adresse_encoded}",
            "waze": f"https://waze.com/ul?q={adresse_encoded}&navigate=yes"
        },
        "contact": {
            "nom": intervention.get("contact_sur_place"),
            "telephone": intervention.get("telephone_contact")
        }
    }


# =============================================================================
# Endpoint Saisie Temps
# =============================================================================

class TempsCreate(BaseModel):
    date: str
    duree_minutes: int
    intervention_id: Optional[UUID] = None
    description: Optional[str] = None


@router_technicien.post(
    "/temps",
    summary="Enregistrer du temps"
)
async def create_temps(
    data: TempsCreate,
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Enregistre une saisie de temps pour le technicien.
    """
    from datetime import datetime

    # Parser la date
    try:
        entry_date = datetime.strptime(data.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date invalide (YYYY-MM-DD)")

    # Verifier que la duree est positive
    if data.duree_minutes <= 0:
        raise HTTPException(status_code=400, detail="La duree doit etre positive")

    # Creer l'entree temps
    temps_data = {
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "date": str(entry_date),
        "duree_minutes": data.duree_minutes,
        "description": data.description,
        "intervention_id": str(data.intervention_id) if data.intervention_id else None,
        "created_at": datetime.now().isoformat(),
        "created_by": str(user_id)
    }

    try:
        result = Database.create("temps", tenant_id, temps_data)
        return {
            "success": True,
            "message": "Temps enregistre",
            "id": result.get("id") if result else None
        }
    except Exception as e:
        logger.error("temps_create_error", error=str(e))
        raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement")
