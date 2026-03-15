# =============================================================================
# AZALPLUS - API Import Bancaire
# =============================================================================
"""
Endpoints pour l'import de relevés bancaires.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from moteur.auth import require_auth
from moteur.tenant import TenantContext
from moteur.import_bancaire import (
    ImportBancaireService,
    FormatImport,
    PROFILS_CSV_BANQUES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/import-bancaire", tags=["Import Bancaire"])


# =============================================================================
# SCHEMAS
# =============================================================================

class FormatDetecteResponse(BaseModel):
    """Réponse de détection de format."""
    format: str
    profil_csv: Optional[str] = None
    banque_detectee: Optional[str] = None


class MouvementImporteSchema(BaseModel):
    """Mouvement importé."""
    reference_banque: str
    date_operation: str
    date_valeur: Optional[str] = None
    montant: float
    type_mouvement: str
    devise: str
    libelle: str
    nom_contrepartie: Optional[str] = None
    iban_contrepartie: Optional[str] = None


class ResultatImportResponse(BaseModel):
    """Résultat d'un import."""
    succes: bool
    format_detecte: str
    fichier_nom: str
    nb_mouvements_importes: int
    nb_mouvements_ignores: int
    nb_erreurs: int
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None
    solde_initial: Optional[float] = None
    solde_final: Optional[float] = None
    erreurs: list[str] = []
    avertissements: list[str] = []


class ProfilCSVSchema(BaseModel):
    """Profil CSV disponible."""
    code: str
    nom: str
    encodage: str
    separateur: str


class ProfilsDisponiblesResponse(BaseModel):
    """Liste des profils CSV disponibles."""
    profils: list[ProfilCSVSchema]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/profils-csv", response_model=ProfilsDisponiblesResponse)
async def lister_profils_csv(
    user: dict = Depends(require_auth),
) -> ProfilsDisponiblesResponse:
    """
    Liste les profils CSV disponibles par banque.

    Retourne la liste des banques françaises supportées avec leurs
    paramètres d'import (encodage, séparateur, format date).
    """
    profils = []

    for code, config in PROFILS_CSV_BANQUES.items():
        profils.append(ProfilCSVSchema(
            code=code,
            nom=config["nom"],
            encodage=config.get("encodage", "utf-8"),
            separateur=config.get("separateur", ";"),
        ))

    return ProfilsDisponiblesResponse(profils=profils)


@router.post("/detecter-format", response_model=FormatDetecteResponse)
async def detecter_format(
    fichier: UploadFile = File(...),
    user: dict = Depends(require_auth),
) -> FormatDetecteResponse:
    """
    Détecte automatiquement le format d'un fichier de relevé bancaire.

    Analyse le contenu et l'extension pour déterminer:
    - Le format (CSV, OFX, QIF, CAMT053, MT940)
    - Pour les CSV: la banque d'origine
    """
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant non identifié",
        )

    contenu = await fichier.read()
    nom_fichier = fichier.filename or "inconnu"

    service = ImportBancaireService(tenant_id)
    format_detecte = service.detecter_format(contenu, nom_fichier)

    profil_csv = None
    banque_detectee = None

    if format_detecte == FormatImport.CSV:
        profil_csv = service.detecter_banque_csv(contenu)
        banque_detectee = PROFILS_CSV_BANQUES.get(profil_csv, {}).get("nom")

    return FormatDetecteResponse(
        format=format_detecte.value,
        profil_csv=profil_csv,
        banque_detectee=banque_detectee,
    )


@router.post("/previsualiser", response_model=ResultatImportResponse)
async def previsualiser_import(
    fichier: UploadFile = File(...),
    compte_id: UUID = Form(...),
    format_force: Optional[str] = Form(None),
    profil_csv: Optional[str] = Form(None),
    user: dict = Depends(require_auth),
) -> ResultatImportResponse:
    """
    Prévisualise un import sans créer les mouvements.

    Parse le fichier et retourne les mouvements qui seraient importés,
    sans les enregistrer en base. Permet de vérifier avant import définitif.
    """
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant non identifié",
        )

    contenu = await fichier.read()
    nom_fichier = fichier.filename or "inconnu"

    # Convertir format si forcé
    format_enum = None
    if format_force:
        try:
            format_enum = FormatImport(format_force)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format invalide: {format_force}",
            )

    service = ImportBancaireService(tenant_id)
    resultat = service.importer(
        compte_id=compte_id,
        contenu=contenu,
        nom_fichier=nom_fichier,
        format_force=format_enum,
        profil_csv=profil_csv,
    )

    return ResultatImportResponse(
        succes=resultat.succes,
        format_detecte=resultat.format_detecte.value,
        fichier_nom=resultat.fichier_nom,
        nb_mouvements_importes=resultat.nb_mouvements_importes,
        nb_mouvements_ignores=resultat.nb_mouvements_ignores,
        nb_erreurs=resultat.nb_erreurs,
        date_debut=resultat.date_debut.isoformat() if resultat.date_debut else None,
        date_fin=resultat.date_fin.isoformat() if resultat.date_fin else None,
        solde_initial=float(resultat.solde_initial) if resultat.solde_initial else None,
        solde_final=float(resultat.solde_final) if resultat.solde_final else None,
        erreurs=resultat.erreurs,
        avertissements=resultat.avertissements,
    )


@router.post("/importer", response_model=ResultatImportResponse)
async def importer_releve(
    fichier: UploadFile = File(...),
    compte_id: UUID = Form(...),
    format_force: Optional[str] = Form(None),
    profil_csv: Optional[str] = Form(None),
    rapprocher_auto: bool = Form(True),
    user: dict = Depends(require_auth),
) -> ResultatImportResponse:
    """
    Importe un relevé bancaire et crée les mouvements.

    Workflow:
    1. Parse le fichier selon le format détecté/forcé
    2. Détecte les doublons (par référence banque)
    3. Crée les nouveaux mouvements en base
    4. Lance le rapprochement automatique si activé

    Args:
        fichier: Fichier de relevé bancaire
        compte_id: ID du compte bancaire cible
        format_force: Forcer un format (CSV, OFX, QIF, CAMT053, MT940)
        profil_csv: Profil CSV à utiliser (credit_agricole, bnp, etc.)
        rapprocher_auto: Lancer le rapprochement après import (défaut: True)

    Returns:
        Résultat avec statistiques d'import
    """
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant non identifié",
        )

    contenu = await fichier.read()
    nom_fichier = fichier.filename or "inconnu"

    # Vérifier que le compte existe et appartient au tenant
    from moteur.db import Database

    compte = Database.get_by_id("comptes_bancaires", tenant_id, compte_id)
    if not compte:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte bancaire non trouvé",
        )

    # Convertir format si forcé
    format_enum = None
    if format_force:
        try:
            format_enum = FormatImport(format_force)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format invalide: {format_force}",
            )

    service = ImportBancaireService(tenant_id)

    try:
        resultat = await service.importer_et_creer(
            compte_id=compte_id,
            contenu=contenu,
            nom_fichier=nom_fichier,
            format_force=format_enum,
            profil_csv=profil_csv,
            rapprocher_auto=rapprocher_auto,
        )
    except Exception as e:
        logger.exception("Erreur import bancaire")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import: {str(e)}",
        )

    return ResultatImportResponse(
        succes=resultat.succes,
        format_detecte=resultat.format_detecte.value,
        fichier_nom=resultat.fichier_nom,
        nb_mouvements_importes=resultat.nb_mouvements_importes,
        nb_mouvements_ignores=resultat.nb_mouvements_ignores,
        nb_erreurs=resultat.nb_erreurs,
        date_debut=resultat.date_debut.isoformat() if resultat.date_debut else None,
        date_fin=resultat.date_fin.isoformat() if resultat.date_fin else None,
        solde_initial=float(resultat.solde_initial) if resultat.solde_initial else None,
        solde_final=float(resultat.solde_final) if resultat.solde_final else None,
        erreurs=resultat.erreurs,
        avertissements=resultat.avertissements,
    )


@router.get("/formats-supportes")
async def lister_formats_supportes(
    user: dict = Depends(require_auth),
) -> dict:
    """
    Liste les formats de fichiers supportés pour l'import.
    """
    return {
        "formats": [
            {
                "code": "CSV",
                "nom": "CSV (Comma-Separated Values)",
                "extensions": [".csv", ".txt"],
                "description": "Format texte avec colonnes séparées. Support des banques françaises majeures.",
            },
            {
                "code": "OFX",
                "nom": "OFX (Open Financial Exchange)",
                "extensions": [".ofx"],
                "description": "Format standard international pour l'échange de données financières.",
            },
            {
                "code": "QIF",
                "nom": "QIF (Quicken Interchange Format)",
                "extensions": [".qif"],
                "description": "Format legacy Quicken, encore utilisé par certaines banques.",
            },
            {
                "code": "CAMT053",
                "nom": "CAMT.053 (ISO 20022)",
                "extensions": [".xml"],
                "description": "Format XML SEPA pour les relevés de compte. Standard européen.",
            },
            {
                "code": "MT940",
                "nom": "MT940 (SWIFT)",
                "extensions": [".sta", ".mt940", ".940"],
                "description": "Format SWIFT pour les relevés bancaires. Standard international.",
            },
        ],
        "banques_csv_supportees": [
            config["nom"] for config in PROFILS_CSV_BANQUES.values()
        ],
    }
