# =============================================================================
# AZALPLUS - API Création d'Entreprise
# =============================================================================
"""
Routes API pour l'accompagnement à la création d'entreprise :
- Business Plan
- Simulateur de statut juridique
- Annuaire des organismes d'accompagnement (CMA, CCI, BGE, etc.)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field
from io import BytesIO
import structlog
import httpx

from .tenant import get_current_tenant, TenantContext, SYSTEM_TENANT_ID
from .auth import require_auth
from .db import Database
from .simulateur_statut import simuler_statut
from .business_plan_pdf import generate_business_plan_pdf

logger = structlog.get_logger()

# =============================================================================
# Router
# =============================================================================
creation_router = APIRouter(prefix="/api/creation", tags=["Création d'entreprise"])


# =============================================================================
# Schemas
# =============================================================================
class SimulationStatutRequest(BaseModel):
    """Données pour la simulation de statut."""
    situation_actuelle: str
    maintien_activite_salariee: bool = False
    droits_chomage: bool = False
    acre_eligible: bool = True
    type_activite: str
    activite_reglementee: bool = False
    local_commercial: bool = False
    stock_important: bool = False
    nombre_associes: str = "1 (seul)"
    associes_actifs: bool = False
    investisseurs_exterieurs: bool = False
    ca_previsionnel: str
    benefice_previsionnel: str
    investissement_depart: str
    emprunt_bancaire: bool = False
    protection_patrimoine: str = "Pas importante"
    couverture_sociale: str = "Équilibrée"
    mode_remuneration: str = "Peu importe"
    cotisations_retraite: str = "Cotisations équilibrées"
    croissance_prevue: str = "Stable / Activité solo"
    embauche_prevue: str = "Non, jamais"
    cession_transmission: bool = False


class OrganismeAccompagnement(BaseModel):
    """Organisme d'accompagnement à la création."""
    nom: str
    type: str  # CMA, CCI, BGE, etc.
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    site_web: Optional[str] = None
    services: List[str] = []
    distance_km: Optional[float] = None


# =============================================================================
# Routes Business Plan
# =============================================================================
@creation_router.get("/business-plans")
async def list_business_plans(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> List[Dict]:
    """Liste les business plans du tenant."""
    plans = Database.query("business_plan", tenant_id)
    return plans


@creation_router.get("/business-plans/{plan_id}")
async def get_business_plan(
    plan_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> Dict:
    """Récupère un business plan."""
    plan = Database.get_by_id("business_plan", tenant_id, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Business plan non trouvé")
    return plan


@creation_router.post("/business-plans/{plan_id}/pdf")
async def generate_bp_pdf(
    plan_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Génère le PDF d'un business plan."""
    # Récupérer le business plan
    plan = Database.get_by_id("business_plan", tenant_id, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Business plan non trouvé")

    try:
        # Générer le PDF
        pdf_bytes = generate_business_plan_pdf(plan)

        # Nom du fichier
        nom_projet = plan.get('nom_projet', 'business_plan').replace(' ', '_')
        filename = f"BusinessPlan_{nom_projet}.pdf"

        # Retourner le PDF
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error("business_plan_pdf_error", error=str(e), plan_id=str(plan_id))
        raise HTTPException(status_code=500, detail=f"Erreur génération PDF: {str(e)}")


@creation_router.post("/business-plans/{plan_id}/analyser")
async def analyser_business_plan(
    plan_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> Dict:
    """Analyse un business plan avec l'IA et retourne des suggestions."""
    plan = Database.get_by_id("business_plan", tenant_id, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Business plan non trouvé")

    # Calculer le score de complétude
    champs_importants = [
        'nom_projet', 'pitch', 'probleme', 'solution', 'marche_cible',
        'ca_annee_1', 'investissement_initial', 'forme_juridique'
    ]
    remplis = sum(1 for c in champs_importants if plan.get(c))
    score_completude = round(remplis / len(champs_importants) * 100)

    # Points de vigilance
    vigilance = []
    if not plan.get('concurrents'):
        vigilance.append("Analyse concurrentielle manquante")
    if not plan.get('ca_annee_1'):
        vigilance.append("Prévisionnel CA non renseigné")
    if plan.get('financement_recherche', 0) > plan.get('apport_personnel', 0) * 3:
        vigilance.append("Ratio apport/financement faible - risque refus bancaire")
    if not plan.get('forme_juridique') or plan.get('forme_juridique') == 'A définir':
        vigilance.append("Statut juridique non défini - utilisez le simulateur")

    # Suggestions
    suggestions = []
    if score_completude < 50:
        suggestions.append("Compléter les informations de base (pitch, problème, solution)")
    if not plan.get('etude_marche'):
        suggestions.append("Joindre une étude de marché")
    if not plan.get('accompagnement'):
        suggestions.append("Contacter un organisme d'accompagnement (CMA, CCI, BGE)")

    # Mettre à jour le business plan
    Database.update("business_plan", tenant_id, plan_id, {
        "ia_score_completude": score_completude,
        "ia_points_vigilance": "\n".join(vigilance),
        "ia_suggestions": suggestions
    })

    return {
        "score_completude": score_completude,
        "points_vigilance": vigilance,
        "suggestions": suggestions,
        "statut": "complet" if score_completude >= 80 else "en_cours" if score_completude >= 50 else "a_completer"
    }


# =============================================================================
# Routes Simulateur Statut
# =============================================================================
@creation_router.post("/simulateur-statut")
async def simuler_statut_juridique(
    data: SimulationStatutRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
) -> Dict:
    """
    Simule le meilleur statut juridique selon les critères fournis.

    Retourne le statut recommandé avec score, alternatives, avantages/inconvénients,
    estimation des charges, et prochaines étapes.
    """
    try:
        # Lancer la simulation
        resultat = simuler_statut(data.model_dump())

        # Sauvegarder la simulation
        simulation_data = {
            **data.model_dump(),
            **resultat
        }
        saved = Database.insert("simulateur_statut", tenant_id, simulation_data)

        # Ajouter l'ID de la simulation au résultat
        resultat["simulation_id"] = str(saved.get("id"))

        logger.info("simulation_statut_effectuee",
                    tenant_id=str(tenant_id),
                    statut_recommande=resultat["statut_recommande"])

        return resultat

    except Exception as e:
        logger.error("simulation_statut_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur simulation: {str(e)}")


@creation_router.post("/simulateur-statut/public")
async def simuler_statut_public(data: SimulationStatutRequest) -> Dict:
    """
    Version publique du simulateur (sans authentification).
    Pour les visiteurs de la landing page.
    """
    try:
        resultat = simuler_statut(data.model_dump())

        # Log anonymisé
        logger.info("simulation_statut_public",
                    statut_recommande=resultat["statut_recommande"])

        return resultat

    except Exception as e:
        logger.error("simulation_statut_public_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur simulation: {str(e)}")


# =============================================================================
# Routes Organismes d'Accompagnement
# =============================================================================
@creation_router.get("/organismes")
async def rechercher_organismes(
    code_postal: Optional[str] = Query(None, description="Code postal pour recherche géographique"),
    type_organisme: Optional[str] = Query(None, description="Type: CMA, CCI, BGE, INITIATIVE, RESEAU_ENTREPRENDRE, POLE_EMPLOI"),
    activite: Optional[str] = Query(None, description="Type d'activité: artisanat, commerce, services"),
) -> List[OrganismeAccompagnement]:
    """
    Recherche les organismes d'accompagnement à la création.

    Retourne les CMA, CCI, BGE, Initiative France, Réseau Entreprendre, etc.
    à proximité du code postal fourni.
    """
    organismes = []

    # Base de données des organismes nationaux
    organismes_nationaux = [
        {
            "nom": "Chambre de Métiers et de l'Artisanat",
            "type": "CMA",
            "site_web": "https://www.artisanat.fr/",
            "services": ["Immatriculation artisans", "Formation", "Accompagnement création", "Stage préalable installation"]
        },
        {
            "nom": "Chambre de Commerce et d'Industrie",
            "type": "CCI",
            "site_web": "https://www.cci.fr/",
            "services": ["Formalités entreprise", "Accompagnement", "Formation", "Réseautage"]
        },
        {
            "nom": "BGE - Réseau national d'accompagnement",
            "type": "BGE",
            "site_web": "https://www.bge.asso.fr/",
            "services": ["Accompagnement création", "Formation", "Financement", "Couveuse d'entreprise"]
        },
        {
            "nom": "Initiative France",
            "type": "INITIATIVE",
            "site_web": "https://www.initiative-france.fr/",
            "services": ["Prêt d'honneur", "Accompagnement", "Parrainage", "Financement"]
        },
        {
            "nom": "Réseau Entreprendre",
            "type": "RESEAU_ENTREPRENDRE",
            "site_web": "https://www.reseau-entreprendre.org/",
            "services": ["Accompagnement par des chefs d'entreprise", "Prêt d'honneur", "Réseau"]
        },
        {
            "nom": "France Travail (ex-Pôle Emploi)",
            "type": "POLE_EMPLOI",
            "site_web": "https://www.francetravail.fr/",
            "services": ["ACRE", "ARCE", "ARE maintenue", "Ateliers création"]
        },
        {
            "nom": "ADIE - Association pour le Droit à l'Initiative Économique",
            "type": "ADIE",
            "site_web": "https://www.adie.org/",
            "services": ["Microcrédit", "Accompagnement", "Formation", "Assurance"]
        },
        {
            "nom": "BPI France",
            "type": "BPI",
            "site_web": "https://www.bpifrance.fr/",
            "services": ["Financement", "Garantie", "Accompagnement croissance"]
        }
    ]

    # Filtrer par type si demandé
    if type_organisme:
        organismes_nationaux = [o for o in organismes_nationaux if o["type"] == type_organisme.upper()]

    # Filtrer par activité
    if activite:
        activite_lower = activite.lower()
        if "artisan" in activite_lower:
            # Prioriser CMA pour les artisans
            organismes_nationaux = sorted(organismes_nationaux, key=lambda x: 0 if x["type"] == "CMA" else 1)
        elif "commerce" in activite_lower:
            # Prioriser CCI pour le commerce
            organismes_nationaux = sorted(organismes_nationaux, key=lambda x: 0 if x["type"] == "CCI" else 1)

    # Convertir en modèle
    for org in organismes_nationaux:
        organismes.append(OrganismeAccompagnement(**org))

    # Si code postal fourni, tenter de trouver les coordonnées locales
    if code_postal:
        # Enrichir avec les données locales (API externe possible)
        for org in organismes:
            if org.type == "CMA":
                org.site_web = f"https://www.artisanat.fr/cma/{code_postal[:2]}"
            elif org.type == "CCI":
                org.site_web = f"https://www.cci.fr/annuaire-cci?cp={code_postal}"

    return organismes


@creation_router.get("/organismes/recherche-locale")
async def rechercher_organismes_locaux(
    code_postal: str = Query(..., description="Code postal"),
    rayon_km: int = Query(30, description="Rayon de recherche en km")
) -> List[Dict]:
    """
    Recherche les organismes locaux via l'API Annuaire Entreprises.
    """
    try:
        # Utiliser l'API Adresse pour géolocaliser le code postal
        async with httpx.AsyncClient() as client:
            # Géocodage du code postal
            geo_response = await client.get(
                f"https://api-adresse.data.gouv.fr/search/",
                params={"q": code_postal, "type": "municipality", "limit": 1}
            )
            geo_data = geo_response.json()

            if not geo_data.get("features"):
                return []

            coords = geo_data["features"][0]["geometry"]["coordinates"]
            lon, lat = coords[0], coords[1]

            # Rechercher les CCI/CMA à proximité (exemple avec API entreprise)
            # Note: En production, utiliser une vraie API ou base de données

            return [
                {
                    "nom": f"CMA {geo_data['features'][0]['properties'].get('context', '')}",
                    "type": "CMA",
                    "adresse": "À rechercher sur artisanat.fr",
                    "code_postal": code_postal,
                    "latitude": lat,
                    "longitude": lon
                },
                {
                    "nom": f"CCI {geo_data['features'][0]['properties'].get('context', '')}",
                    "type": "CCI",
                    "adresse": "À rechercher sur cci.fr",
                    "code_postal": code_postal,
                    "latitude": lat,
                    "longitude": lon
                }
            ]

    except Exception as e:
        logger.error("recherche_organismes_error", error=str(e))
        return []


@creation_router.get("/aides-financements")
async def lister_aides_financements(
    situation: Optional[str] = Query(None, description="demandeur_emploi, salarie, etudiant, etc."),
    type_projet: Optional[str] = Query(None, description="creation, reprise, innovation"),
) -> List[Dict]:
    """
    Liste les aides et financements disponibles pour la création d'entreprise.
    """
    aides = [
        {
            "nom": "ACRE",
            "description": "Exonération partielle de charges sociales la 1ère année",
            "type": "exoneration",
            "conditions": "Créateurs et repreneurs d'entreprise",
            "montant": "Jusqu'à 50% d'exonération",
            "organisme": "URSSAF",
            "url": "https://www.urssaf.fr/acre"
        },
        {
            "nom": "ARCE",
            "description": "Versement en capital de 60% des droits ARE restants",
            "type": "capital",
            "conditions": "Demandeurs d'emploi indemnisés",
            "montant": "60% des ARE restantes",
            "organisme": "France Travail",
            "url": "https://www.francetravail.fr/"
        },
        {
            "nom": "Maintien ARE",
            "description": "Cumul allocations chômage et revenus d'activité",
            "type": "allocation",
            "conditions": "Demandeurs d'emploi créant leur entreprise",
            "montant": "Variable selon revenus",
            "organisme": "France Travail",
            "url": "https://www.francetravail.fr/"
        },
        {
            "nom": "Prêt d'honneur Initiative France",
            "description": "Prêt à taux zéro sans garantie personnelle",
            "type": "pret",
            "conditions": "Projet viable, accompagnement obligatoire",
            "montant": "3 000 € à 50 000 €",
            "organisme": "Initiative France",
            "url": "https://www.initiative-france.fr/"
        },
        {
            "nom": "Prêt NACRE",
            "description": "Nouveau parcours d'accompagnement à la création",
            "type": "pret",
            "conditions": "Demandeurs d'emploi, minima sociaux",
            "montant": "1 000 € à 10 000 €",
            "organisme": "Région",
            "url": "https://travail-emploi.gouv.fr/"
        },
        {
            "nom": "Microcrédit ADIE",
            "description": "Financement pour les exclus du crédit bancaire",
            "type": "pret",
            "conditions": "Refus bancaire, projet viable",
            "montant": "Jusqu'à 12 000 €",
            "organisme": "ADIE",
            "url": "https://www.adie.org/"
        },
        {
            "nom": "Garantie France Active",
            "description": "Garantie bancaire pour faciliter l'accès au crédit",
            "type": "garantie",
            "conditions": "Créateurs demandeurs d'emploi",
            "montant": "Jusqu'à 65% du prêt garanti",
            "organisme": "France Active",
            "url": "https://www.franceactive.org/"
        },
        {
            "nom": "Aide AGEFIPH",
            "description": "Aide à la création pour travailleurs handicapés",
            "type": "subvention",
            "conditions": "Reconnaissance RQTH",
            "montant": "Jusqu'à 6 300 €",
            "organisme": "AGEFIPH",
            "url": "https://www.agefiph.fr/"
        }
    ]

    # Filtrer par situation
    if situation:
        if situation == "demandeur_emploi":
            aides = [a for a in aides if "demandeur" in a.get("conditions", "").lower() or
                     a["nom"] in ["ACRE", "ARCE", "Maintien ARE"]]
        elif situation == "salarie":
            aides = [a for a in aides if a["nom"] == "ACRE"]

    return aides


# =============================================================================
# Route publique pour la landing page
# =============================================================================
@creation_router.get("/checklist-creation")
async def get_checklist_creation(
    forme_juridique: str = Query("micro-entreprise", description="Forme juridique choisie")
) -> List[Dict]:
    """
    Retourne la checklist des étapes de création selon la forme juridique.
    """
    etapes_communes = [
        {"ordre": 1, "etape": "Valider son idée et étudier le marché", "obligatoire": True},
        {"ordre": 2, "etape": "Réaliser un business plan", "obligatoire": True},
        {"ordre": 3, "etape": "Choisir son statut juridique", "obligatoire": True},
        {"ordre": 4, "etape": "Domicilier son entreprise", "obligatoire": True},
    ]

    etapes_micro = [
        {"ordre": 5, "etape": "Déclarer son activité sur le guichet unique (INPI)", "obligatoire": True},
        {"ordre": 6, "etape": "Recevoir son numéro SIRET", "obligatoire": True},
        {"ordre": 7, "etape": "Ouvrir un compte bancaire dédié", "obligatoire": True},
        {"ordre": 8, "etape": "Souscrire une assurance RC Pro", "obligatoire": False},
    ]

    etapes_societe = [
        {"ordre": 5, "etape": "Rédiger les statuts", "obligatoire": True},
        {"ordre": 6, "etape": "Déposer le capital social", "obligatoire": True},
        {"ordre": 7, "etape": "Publier l'annonce légale", "obligatoire": True},
        {"ordre": 8, "etape": "Déposer le dossier sur le guichet unique (INPI)", "obligatoire": True},
        {"ordre": 9, "etape": "Recevoir l'extrait Kbis", "obligatoire": True},
        {"ordre": 10, "etape": "Ouvrir un compte bancaire professionnel", "obligatoire": True},
        {"ordre": 11, "etape": "Souscrire les assurances obligatoires", "obligatoire": True},
    ]

    if forme_juridique.lower() in ["micro-entreprise", "micro", "auto-entrepreneur"]:
        return etapes_communes + etapes_micro
    else:
        return etapes_communes + etapes_societe
