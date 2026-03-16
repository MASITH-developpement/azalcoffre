# =============================================================================
# AZALPLUS - Router API intégration AZALCOFFRE
# =============================================================================
"""
Endpoints API pour l'intégration AZALCOFFRE.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

from .service import AzalCoffreService

router = APIRouter(prefix="/api/coffre", tags=["AZALCOFFRE Integration"])


# =============================================================================
# SCHEMAS
# =============================================================================

class ArchiveRequest(BaseModel):
    """Requête d'archivage."""
    document_type: str  # FACTURE, DEVIS, CONTRAT, etc.
    reference_id: str   # ID du document source dans AZALPLUS
    reference_number: str  # Numéro du document
    encrypt: bool = False
    metadata: Optional[dict] = None


class ArchiveResponse(BaseModel):
    """Réponse d'archivage."""
    document_id: str
    hash_sha256: str
    tsa_timestamp: Optional[str] = None
    status: str = "archived"


class SignatureRequest(BaseModel):
    """Demande de signature."""
    document_id: str  # ID du document dans AZALCOFFRE
    signer_email: EmailStr
    signer_name: str
    signature_level: str = "SIMPLE"  # SIMPLE, ADVANCED, QUALIFIED
    message: Optional[str] = None


class SignatureResponse(BaseModel):
    """Réponse demande de signature."""
    signature_request_id: str
    signing_url: str
    expires_at: str
    status: str = "pending"


class PDPSubmitRequest(BaseModel):
    """Soumission facture PDP."""
    invoice_id: str
    invoice_data: dict
    profile: str = "EN16931"


class PDPSubmitResponse(BaseModel):
    """Réponse soumission PDP."""
    id: str
    status: str
    ppf_status: Optional[str] = None


class InvoiceReceiveResponse(BaseModel):
    """Réponse réception facture."""
    id: str
    status: str
    invoice_data: Optional[dict] = None


class HealthResponse(BaseModel):
    """État du service."""
    available: bool
    version: Optional[str] = None


# =============================================================================
# DEPENDENCY
# =============================================================================

async def get_coffre_service() -> AzalCoffreService:
    """Dependency injection pour le service AZALCOFFRE."""
    # TODO: Récupérer tenant_id du contexte JWT
    service = AzalCoffreService.from_env()
    try:
        yield service
    finally:
        await service.close()


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/health", response_model=HealthResponse)
async def check_coffre_health(
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """Vérifie la disponibilité d'AZALCOFFRE."""
    available = await service.is_available()
    return HealthResponse(available=available)


@router.post("/archive", response_model=ArchiveResponse)
async def archive_document(
    request: ArchiveRequest,
    file: UploadFile = File(...),
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Archive un document dans le coffre-fort AZALCOFFRE.

    Endpoint AZALCOFFRE: POST /api/v1/documents/upload

    Le document reçoit:
    - Hash SHA-256 pour intégrité
    - Horodatage TSA RFC 3161
    - Chiffrement optionnel (AES-128)
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    content = await file.read()

    result = await service.client.upload_document(
        file_content=content,
        filename=file.filename or f"{request.reference_number}.pdf",
        document_type=request.document_type,
        metadata={
            "source": "AZALPLUS",
            "reference_id": request.reference_id,
            "reference_number": request.reference_number,
            **(request.metadata or {})
        },
        encrypt=request.encrypt
    )

    return ArchiveResponse(
        document_id=result["id"],
        hash_sha256=result.get("hash_sha256", ""),
        tsa_timestamp=result.get("tsa_timestamp"),
        status="archived"
    )


@router.post("/sign", response_model=SignatureResponse)
async def request_signature(
    request: SignatureRequest,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Demande une signature électronique sur un document archivé.

    Endpoint AZALCOFFRE: POST /api/v1/signatures/request

    Niveaux de signature eIDAS:
    - SIMPLE: Code SMS/email
    - ADVANCED: Certificat logiciel
    - QUALIFIED: HSM qualifié
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    result = await service.client.request_signature(
        document_id=request.document_id,
        signers=[{
            "email": request.signer_email,
            "name": request.signer_name,
            "order": 1
        }],
        signature_level=request.signature_level,
        message=request.message
    )

    # Extraire l'URL de signature du premier signataire
    signers = result.get("signers", [])
    signing_url = signers[0].get("signing_url", "") if signers else ""

    return SignatureResponse(
        signature_request_id=result["id"],
        signing_url=signing_url,
        expires_at=result.get("expires_at", ""),
        status=result.get("status", "pending")
    )


@router.get("/sign/{signature_request_id}")
async def get_signature_status(
    signature_request_id: str,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """Récupère le statut d'une demande de signature."""
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    return await service.client.get_signature_status(signature_request_id)


@router.post("/pdp/submit", response_model=PDPSubmitResponse)
async def submit_to_pdp(
    request: PDPSubmitRequest,
    file: Optional[UploadFile] = File(None),
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Soumet une facture au Portail Public de Facturation (PPF).

    Endpoints AZALCOFFRE:
    - POST /api/v1/invoices/create ou /create-with-pdf
    - POST /api/v1/invoices/{id}/send

    Génère automatiquement le XML Factur-X au profil demandé.
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    pdf_content = None
    if file:
        pdf_content = await file.read()

    result = await service.submit_invoice_to_pdp(
        invoice_id=request.invoice_id,
        invoice_data=request.invoice_data,
        pdf_content=pdf_content
    )

    return PDPSubmitResponse(
        id=result["id"],
        status=result["status"],
        ppf_status=result.get("ppf_status")
    )


@router.get("/pdp/{invoice_id}")
async def get_pdp_status(
    invoice_id: str,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Récupère le statut d'une facture PDP.

    Endpoint AZALCOFFRE: GET /api/v1/invoices/{invoice_id}
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    return await service.check_pdp_status(invoice_id)


@router.post("/invoices/receive", response_model=InvoiceReceiveResponse)
async def receive_invoice(
    file: UploadFile = File(...),
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Reçoit et parse une facture Factur-X entrante.

    Endpoint AZALCOFFRE: POST /api/v1/invoices/receive

    AZALCOFFRE extrait automatiquement:
    - XML Factur-X embarqué
    - Données structurées de la facture
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    content = await file.read()

    result = await service.receive_incoming_invoice(
        file_content=content,
        filename=file.filename or "facture.pdf"
    )

    return InvoiceReceiveResponse(
        id=result.get("id", ""),
        status=result.get("status", "received"),
        invoice_data=result.get("invoice_data")
    )


@router.get("/document/{document_id}")
async def get_document_info(
    document_id: str,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Récupère les informations d'un document archivé.

    Endpoint AZALCOFFRE: GET /api/v1/documents/{document_id}
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    return await service.client.get_document(document_id)


@router.get("/document/{document_id}/verify")
async def verify_document(
    document_id: str,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Vérifie l'intégrité d'un document archivé.

    Endpoint AZALCOFFRE: GET /api/v1/documents/{document_id}/verify

    Contrôle:
    - Hash SHA-256/512
    - Horodatage TSA
    - Chaîne d'audit
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    return await service.client.verify_document(document_id)


@router.get("/document/{document_id}/proof")
async def get_document_proof(
    document_id: str,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Récupère le package de preuve complet d'un document.

    Endpoint AZALCOFFRE: GET /api/v1/documents/{document_id}/proof

    Inclut:
    - Hash SHA-256/512
    - Token TSA RFC 3161
    - Chaîne d'audit complète
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    return await service.client.get_document_proof(document_id)


@router.get("/document/{document_id}/audit")
async def get_document_audit(
    document_id: str,
    service: AzalCoffreService = Depends(get_coffre_service)
):
    """
    Récupère la chaîne d'audit d'un document.

    Endpoint AZALCOFFRE: GET /api/v1/documents/{document_id}/audit-trail
    """
    if not await service.is_available():
        raise HTTPException(503, "AZALCOFFRE indisponible")

    return await service.client.get_document_audit_trail(document_id)
