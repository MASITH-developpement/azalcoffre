# =============================================================================
# AZALMED - Router principal
# =============================================================================

from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from typing import Optional
from uuid import UUID

from moteur.tenant import TenantContext

from .scribe_service import ScribeService
from .signature_service import SignatureService
from .veille_service import VeilleService
from .coffre_service import CoffreService

router = APIRouter()

# Router public (sans auth)
public_router = APIRouter()


# =============================================================================
# LANDING PAGE (Public)
# =============================================================================

@public_router.get("/", response_class=HTMLResponse)
async def landing_page():
    """Page d'accueil AZALMED."""
    template_path = Path(__file__).parent.parent.parent.parent / "templates" / "landing" / "azalmed.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AZALMED</h1><p>Coming soon...</p>")


@public_router.get("/login", response_class=HTMLResponse)
async def login_page():
    """Page de connexion AZALMED."""
    template_path = Path(__file__).parent.parent.parent.parent / "templates" / "landing" / "azalmed_login.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Login</h1>")


@public_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """Dashboard AZALMED."""
    template_path = Path(__file__).parent.parent.parent.parent / "templates" / "landing" / "azalmed_dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard</h1>")


def get_tenant_id() -> UUID:
    """Récupère le tenant_id du contexte de requête."""
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant non identifié")
    return tenant_id

# =============================================================================
# SCRIBE - Transcription IA
# =============================================================================

@router.post("/scribe/transcribe")
async def transcrire_audio(
    consultation_id: UUID,
    audio: UploadFile = File(...),
    langue: str = "fr",
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Transcrit un fichier audio en texte structuré.

    1. Envoie l'audio à Whisper (OpenAI)
    2. Reçoit la transcription brute
    3. Envoie au LLM pour structuration
    4. Retourne le texte structuré (motif, examen, diagnostic, etc.)
    """
    service = ScribeService(tenant_id)
    result = await service.transcrire(
        audio_file=audio,
        langue=langue,
        consultation_id=consultation_id,
    )
    return result


@router.post("/scribe/structurer")
async def structurer_texte(
    texte: str,
    specialite: Optional[str] = None,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Structure un texte brut en sections médicales.
    Utile si la transcription est déjà faite ailleurs.
    """
    service = ScribeService(tenant_id)
    result = await service.structurer(texte=texte, specialite=specialite)
    return result


# =============================================================================
# CONSENT - Signature électronique
# =============================================================================

@router.post("/consent/envoyer")
async def envoyer_consentement(
    consentement_id: UUID,
    mode: str = "EMAIL",  # EMAIL, SMS, TABLETTE
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Envoie une demande de signature au patient.

    1. Génère le PDF du consentement
    2. Crée la demande chez Yousign
    3. Envoie le lien au patient (email ou SMS)
    4. Met à jour le statut
    """
    service = SignatureService(tenant_id)
    result = await service.envoyer_demande(
        consentement_id=consentement_id,
        mode=mode,
    )
    return result


@router.post("/consent/webhook")
async def webhook_signature(
    payload: dict,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Webhook appelé par Yousign quand le patient signe.

    1. Vérifie la signature du webhook
    2. Met à jour le statut du consentement
    3. Archive le document signé dans le coffre
    4. Génère le dossier de preuves
    """
    service = SignatureService(tenant_id)
    result = await service.traiter_webhook(payload=payload)
    return result


@router.get("/consent/{consentement_id}/preuves")
async def telecharger_preuves(
    consentement_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Télécharge le dossier de preuves d'un consentement signé.
    Contient : PDF signé, certificat, horodatage TSA, logs.
    """
    service = SignatureService(tenant_id)
    result = await service.generer_dossier_preuves(consentement_id=consentement_id)
    return result


# =============================================================================
# VEILLE - Agrégation et résumé
# =============================================================================

@router.post("/veille/synchroniser")
async def synchroniser_veille(
    praticien_id: UUID,
    sources: Optional[list[str]] = None,  # PUBMED, HAS, ANSM
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Synchronise les articles de veille pour un praticien.

    1. Récupère le profil du praticien (spécialité, thèmes)
    2. Interroge les sources (PubMed, HAS, ANSM)
    3. Filtre par pertinence
    4. Génère les résumés IA
    5. Stocke les articles
    """
    service = VeilleService(tenant_id)
    result = await service.synchroniser(
        praticien_id=praticien_id,
        sources=sources,
    )
    return result


@router.post("/veille/resumer/{article_id}")
async def resumer_article(
    article_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Génère ou régénère le résumé IA d'un article.
    """
    service = VeilleService(tenant_id)
    result = await service.generer_resume(article_id=article_id)
    return result


@router.post("/veille/digest")
async def envoyer_digest(
    praticien_id: UUID,
    frequence: str = "QUOTIDIEN",
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Envoie le digest de veille par email.
    """
    service = VeilleService(tenant_id)
    result = await service.envoyer_digest(
        praticien_id=praticien_id,
        frequence=frequence,
    )
    return result


# =============================================================================
# ARCHIVE - Coffre-fort HDS
# =============================================================================

@router.post("/archive/deposer")
async def deposer_document(
    patient_id: UUID,
    praticien_id: UUID,
    type_document: str,
    titre: str,
    fichier: UploadFile = File(...),
    confidentiel: bool = False,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Dépose un document dans le coffre-fort HDS.

    1. Calcule le hash SHA-256
    2. Chiffre le fichier (AES-256)
    3. Stocke sur OVH Healthcare
    4. Demande l'horodatage TSA
    5. Crée l'entrée en base
    """
    service = CoffreService(tenant_id)
    result = await service.deposer(
        patient_id=patient_id,
        praticien_id=praticien_id,
        type_document=type_document,
        titre=titre,
        fichier=fichier,
        confidentiel=confidentiel,
    )
    return result


@router.get("/archive/{document_id}/telecharger")
async def telecharger_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Télécharge un document du coffre-fort.

    1. Vérifie les droits d'accès
    2. Récupère le fichier chiffré
    3. Déchiffre
    4. Log l'accès
    5. Retourne le fichier
    """
    service = CoffreService(tenant_id)
    result = await service.telecharger(document_id=document_id)
    return result


@router.get("/archive/{document_id}/verifier")
async def verifier_integrite(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Vérifie l'intégrité d'un document archivé.

    1. Recalcule le hash
    2. Compare avec le hash stocké
    3. Vérifie l'horodatage TSA
    4. Retourne le statut
    """
    service = CoffreService(tenant_id)
    result = await service.verifier_integrite(document_id=document_id)
    return result


@router.post("/archive/{document_id}/attestation")
async def generer_attestation(
    document_id: UUID,
    tenant_id: UUID = Depends(get_tenant_id),
):
    """
    Génère une attestation d'archivage (PDF).
    Prouve que le document est authentique et non modifié.
    """
    service = CoffreService(tenant_id)
    result = await service.generer_attestation(document_id=document_id)
    return result
