# =============================================================================
# AZALPLUS - Routes API Factur-X (format technique)
# =============================================================================
"""
Endpoints REST pour le format Factur-X (PDF/A-3 + XML).

NOTE: Les routes preview/send/archive sont dans app/modules/factures/
      → /api/v1/factures/preview, /send, /{id}/archive

Routes génération:
- POST /api/facturx/generate - Générer PDF Factur-X
- POST /api/facturx/generate/download - Générer et télécharger
- POST /api/facturx/validate - Valider un PDF Factur-X
- POST /api/facturx/extract - Extraire XML d'un PDF

Routes PDP:
- POST /api/facturx/pdp/submit - Soumettre à une PDP
- GET /api/facturx/pdp/status/{id} - Statut PDP

Routes Chorus Pro:
- POST /api/facturx/chorus/submit - Soumettre à Chorus Pro
- GET /api/facturx/chorus/status/{id} - Statut Chorus

Routes réception:
- POST /api/facturx/reception/parse - Parser facture entrante

Routes annuaire:
- GET /api/facturx/annuaire/lookup - Recherche annuaire PPF
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Body
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/facturx", tags=["Factur-X"])


# =============================================================================
# Schémas Pydantic
# =============================================================================

class AddressSchema(BaseModel):
    """Adresse."""
    line1: Optional[str] = None
    line2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "FR"


class PartySchema(BaseModel):
    """Partie (vendeur/acheteur)."""
    name: str
    siret: Optional[str] = None
    siren: Optional[str] = None
    vat_number: Optional[str] = None
    address: Optional[AddressSchema] = None
    email: Optional[str] = None


class InvoiceLineSchema(BaseModel):
    """Ligne de facture."""
    description: str
    quantity: float
    unit_price: float
    vat_rate: float = 20.0
    unit: str = "C62"


class GenerateRequest(BaseModel):
    """Requête de génération Factur-X."""
    invoice_number: str = Field(..., description="Numéro de facture")
    issue_date: str = Field(..., description="Date d'émission (YYYY-MM-DD)")
    due_date: Optional[str] = Field(None, description="Date d'échéance")

    seller: PartySchema = Field(..., description="Vendeur")
    buyer: PartySchema = Field(..., description="Acheteur")

    lines: List[InvoiceLineSchema] = Field(..., description="Lignes de facture")

    currency: str = "EUR"
    payment_terms: Optional[str] = None
    note: Optional[str] = None

    profile: str = Field("EN16931", description="Profil Factur-X")


class GenerateResponse(BaseModel):
    """Réponse génération."""
    success: bool
    invoice_number: str
    profile: str
    is_valid: bool
    validation_errors: List[str] = []
    xml_size: int
    pdf_size: int


class ValidateRequest(BaseModel):
    """Requête de validation."""
    # PDF en base64 ou via upload


class ValidateResponse(BaseModel):
    """Réponse validation."""
    is_valid: bool
    is_pdfa: bool
    has_xml: bool
    profile: Optional[str] = None
    errors: List[str] = []


class ExtractResponse(BaseModel):
    """Réponse extraction XML."""
    success: bool
    xml_content: Optional[str] = None
    invoice_number: Optional[str] = None
    error: Optional[str] = None


class PDPSubmitRequest(BaseModel):
    """Requête soumission PDP."""
    invoice_id: UUID
    provider: str = "generic"  # cegid, sage, pennylane, etc.


class PDPStatusResponse(BaseModel):
    """Réponse statut PDP."""
    pdp_id: str
    status: str
    status_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class ChorusSubmitRequest(BaseModel):
    """Requête soumission Chorus Pro."""
    invoice_id: UUID
    service_code: Optional[str] = None
    engagement_number: Optional[str] = None


class ChorusStatusResponse(BaseModel):
    """Réponse statut Chorus."""
    chorus_id: str
    status: str
    status_date: Optional[datetime] = None
    payment_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class AnnuaireLookupResponse(BaseModel):
    """Réponse recherche annuaire."""
    siret: str
    is_registered: bool
    company_name: Optional[str] = None
    routing: str  # ppf, pdp, not_registered
    pdp_name: Optional[str] = None
    can_receive: bool = False
    can_send: bool = False
    supported_formats: List[str] = []


class ParsedInvoiceResponse(BaseModel):
    """Réponse parsing facture."""
    success: bool
    format: str
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_siret: Optional[str] = None
    total_with_tax: Optional[float] = None
    currency: str = "EUR"
    confidence: float = 0.0
    errors: List[str] = []


# =============================================================================
# Dépendances
# =============================================================================


def get_facturx_generator():
    """Obtenir le générateur Factur-X."""
    from .generator import FacturXGenerator, FacturXProfile
    return FacturXGenerator(profile=FacturXProfile.EN16931)


def get_pdp_config():
    """Obtenir la config PDP depuis les settings."""
    # À implémenter selon la config AZALPLUS
    return None


def get_chorus_config():
    """Obtenir la config Chorus depuis les settings."""
    return None


def get_ppf_config():
    """Obtenir la config PPF depuis les settings."""
    return None


# =============================================================================
# Routes Génération
# =============================================================================

@router.post("/generate", response_model=GenerateResponse)
async def generate_facturx_route(
    request: GenerateRequest,
    pdf_file: UploadFile = File(..., description="PDF source")
):
    """
    Générer un PDF Factur-X (PDF/A-3 avec XML embarqué).

    Le PDF source est converti en PDF/A-3 avec le XML Factur-X embarqué.
    """
    try:
        from .generator import FacturXGenerator, FacturXProfile
        from .xml_builder import InvoiceData, Party, Address, InvoiceLine
        from decimal import Decimal

        # Lire le PDF
        pdf_content = await pdf_file.read()

        # Construire les données (using correct field names from xml_builder.py)
        seller_address = None
        if request.seller.address:
            seller_address = Address(
                line1=request.seller.address.line1 or "",
                postal_code=request.seller.address.postal_code or "",
                city=request.seller.address.city or "",
                country_code=request.seller.address.country
            )

        buyer_address = None
        if request.buyer.address:
            buyer_address = Address(
                line1=request.buyer.address.line1 or "",
                postal_code=request.buyer.address.postal_code or "",
                city=request.buyer.address.city or "",
                country_code=request.buyer.address.country
            )

        seller = Party(
            name=request.seller.name,
            siret=request.seller.siret or "",
            tva_intra=request.seller.vat_number or "",
            address=seller_address,
            email=request.seller.email or ""
        )

        buyer = Party(
            name=request.buyer.name,
            siret=request.buyer.siret or "",
            tva_intra=request.buyer.vat_number or "",
            address=buyer_address,
            email=request.buyer.email or ""
        )

        # Build lines with correct field names from xml_builder.py
        lines = []
        for i, line in enumerate(request.lines, 1):
            lines.append(InvoiceLine(
                line_id=str(i),
                description=line.description,
                quantity=Decimal(str(line.quantity)),
                unit_code=line.unit,
                unit_price=Decimal(str(line.unit_price)),
                vat_rate=Decimal(str(line.vat_rate)),
                line_total=Decimal(str(line.quantity * line.unit_price))
            ))

        # Calculer les totaux
        total_ht = Decimal(str(sum(l.quantity * l.unit_price for l in request.lines)))
        total_tva = Decimal(str(sum(l.quantity * l.unit_price * l.vat_rate / 100 for l in request.lines)))
        total_ttc = total_ht + total_tva

        # Parser les dates
        from datetime import datetime
        invoice_date = datetime.strptime(request.issue_date, "%Y-%m-%d").date()

        # Create payment terms if due_date is provided
        from .xml_builder import PaymentTerms
        payment_terms = None
        if request.due_date:
            due_date = datetime.strptime(request.due_date, "%Y-%m-%d").date()
            payment_terms = PaymentTerms(due_date=due_date)

        invoice_data = InvoiceData(
            invoice_number=request.invoice_number,
            invoice_date=invoice_date,
            seller=seller,
            buyer=buyer,
            lines=lines,
            total_ht=total_ht,
            total_tva=total_tva,
            total_ttc=total_ttc,
            currency_code=request.currency,
            payment_terms=payment_terms,
            notes=[request.note] if request.note else []
        )

        # Générer
        profile = FacturXProfile(request.profile) if request.profile in [p.value for p in FacturXProfile] else FacturXProfile.EN16931
        generator = FacturXGenerator(profile=profile)
        result = generator.generate(pdf_content, invoice_data)

        return GenerateResponse(
            success=result.is_valid,
            invoice_number=result.invoice_number,
            profile=result.profile.value,
            is_valid=result.is_valid,
            validation_errors=result.validation_errors,
            xml_size=result.metadata.get("xml_size", 0),
            pdf_size=result.metadata.get("pdf_size", 0)
        )

    except Exception as e:
        logger.error(f"Erreur génération Factur-X: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/download")
async def generate_and_download(
    request: GenerateRequest,
    pdf_file: UploadFile = File(...)
):
    """
    Générer et télécharger le PDF Factur-X.
    """
    try:
        from .generator import FacturXGenerator, FacturXProfile
        from .xml_builder import InvoiceData, Party, Address, InvoiceLine, PaymentTerms
        from datetime import datetime
        from decimal import Decimal

        pdf_content = await pdf_file.read()

        # Construire les données avec les bons noms de champs
        seller = Party(
            name=request.seller.name,
            siret=request.seller.siret or "",
            tva_intra=request.seller.vat_number or ""
        )

        buyer = Party(
            name=request.buyer.name,
            siret=request.buyer.siret or "",
            tva_intra=request.buyer.vat_number or ""
        )

        lines = []
        for i, line in enumerate(request.lines, 1):
            lines.append(InvoiceLine(
                line_id=str(i),
                description=line.description,
                quantity=Decimal(str(line.quantity)),
                unit_code=line.unit,
                unit_price=Decimal(str(line.unit_price)),
                vat_rate=Decimal(str(line.vat_rate)),
                line_total=Decimal(str(line.quantity * line.unit_price))
            ))

        total_ht = Decimal(str(sum(l.quantity * l.unit_price for l in request.lines)))
        total_tva = Decimal(str(sum(l.quantity * l.unit_price * l.vat_rate / 100 for l in request.lines)))

        invoice_date = datetime.strptime(request.issue_date, "%Y-%m-%d").date()

        invoice_data = InvoiceData(
            invoice_number=request.invoice_number,
            invoice_date=invoice_date,
            seller=seller,
            buyer=buyer,
            lines=lines,
            total_ht=total_ht,
            total_tva=total_tva,
            total_ttc=total_ht + total_tva,
            currency_code=request.currency
        )

        generator = FacturXGenerator()
        result = generator.generate(pdf_content, invoice_data)

        if not result.is_valid:
            raise HTTPException(status_code=400, detail=result.validation_errors)

        return Response(
            content=result.pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="facturx_{request.invoice_number}.pdf"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur téléchargement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate", response_model=ValidateResponse)
async def validate_facturx(
    pdf_file: UploadFile = File(...)
):
    """
    Valider qu'un PDF est conforme Factur-X.
    """
    try:
        from .generator import FacturXGenerator

        pdf_content = await pdf_file.read()
        generator = FacturXGenerator()

        is_valid, issues = generator.validate_pdf(pdf_content)
        xml_content = generator.extract_xml(pdf_content)

        return ValidateResponse(
            is_valid=is_valid,
            is_pdfa="PDF/A" not in str(issues),
            has_xml=xml_content is not None,
            profile="EN16931" if xml_content and "EN16931" in xml_content else None,
            errors=issues
        )

    except Exception as e:
        logger.error(f"Erreur validation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract", response_model=ExtractResponse)
async def extract_xml(
    pdf_file: UploadFile = File(...)
):
    """
    Extraire le XML Factur-X d'un PDF.
    """
    try:
        from .generator import FacturXGenerator

        pdf_content = await pdf_file.read()
        generator = FacturXGenerator()

        xml_content = generator.extract_xml(pdf_content)

        if xml_content:
            # Extraire le numéro de facture du XML
            import re
            match = re.search(r"<ram:ID>([^<]+)</ram:ID>", xml_content)
            invoice_number = match.group(1) if match else None

            return ExtractResponse(
                success=True,
                xml_content=xml_content,
                invoice_number=invoice_number
            )

        return ExtractResponse(
            success=False,
            error="Aucun XML Factur-X trouvé dans ce PDF"
        )

    except Exception as e:
        logger.error(f"Erreur extraction: {e}")
        return ExtractResponse(success=False, error=str(e))


# =============================================================================
# Routes PDP
# =============================================================================

@router.post("/pdp/submit", response_model=PDPStatusResponse)
async def submit_to_pdp(request: PDPSubmitRequest):
    """
    Soumettre une facture à une PDP.
    """
    # À implémenter avec les vraies données AZALPLUS
    raise HTTPException(
        status_code=501,
        detail="Configuration PDP requise. Configurez votre PDP dans les paramètres."
    )


@router.get("/pdp/status/{pdp_id}", response_model=PDPStatusResponse)
async def get_pdp_status(pdp_id: str):
    """
    Obtenir le statut d'une facture sur la PDP.
    """
    raise HTTPException(status_code=501, detail="Configuration PDP requise")


@router.get("/pdp/list")
async def list_pdp_invoices(
    direction: str = Query("outgoing", enum=["outgoing", "incoming"]),
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """
    Lister les factures sur la PDP.
    """
    raise HTTPException(status_code=501, detail="Configuration PDP requise")


# =============================================================================
# Routes Chorus Pro
# =============================================================================

@router.post("/chorus/submit", response_model=ChorusStatusResponse)
async def submit_to_chorus(request: ChorusSubmitRequest):
    """
    Soumettre une facture à Chorus Pro (B2G).
    """
    raise HTTPException(
        status_code=501,
        detail="Configuration Chorus Pro requise. Configurez vos credentials PISTE."
    )


@router.get("/chorus/status/{chorus_id}", response_model=ChorusStatusResponse)
async def get_chorus_status(chorus_id: str):
    """
    Obtenir le statut d'une facture Chorus Pro.
    """
    raise HTTPException(status_code=501, detail="Configuration Chorus Pro requise")


@router.get("/chorus/structures")
async def search_chorus_structures(
    siret: Optional[str] = None,
    designation: Optional[str] = None,
    code_postal: Optional[str] = None
):
    """
    Rechercher des structures publiques (destinataires B2G).
    """
    raise HTTPException(status_code=501, detail="Configuration Chorus Pro requise")


# =============================================================================
# Routes Réception
# =============================================================================

@router.post("/reception/parse", response_model=ParsedInvoiceResponse)
async def parse_received_invoice(
    invoice_file: UploadFile = File(...)
):
    """
    Parser une facture reçue (PDF Factur-X, UBL, CII ou PDF simple).
    """
    try:
        from .reception import InvoiceReceptionService

        content = await invoice_file.read()
        service = InvoiceReceptionService()

        invoice = await service.receive(
            content=content,
            filename=invoice_file.filename,
            source="api"
        )

        return ParsedInvoiceResponse(
            success=invoice.status.value not in ["error"],
            format=invoice.format.value,
            invoice_number=invoice.invoice_number,
            issue_date=invoice.issue_date.isoformat() if invoice.issue_date else None,
            supplier_name=invoice.supplier_name,
            supplier_siret=invoice.supplier_siret,
            total_with_tax=float(invoice.total_with_tax) if invoice.total_with_tax else None,
            currency=invoice.currency,
            confidence=invoice.confidence_score,
            errors=[e.get("message", str(e)) for e in invoice.validation_errors]
        )

    except Exception as e:
        logger.error(f"Erreur parsing: {e}")
        return ParsedInvoiceResponse(
            success=False,
            format="unknown",
            errors=[str(e)]
        )


# =============================================================================
# Routes Annuaire PPF
# =============================================================================

@router.get("/annuaire/lookup", response_model=AnnuaireLookupResponse)
async def lookup_annuaire(
    siret: Optional[str] = Query(None, min_length=14, max_length=14),
    siren: Optional[str] = Query(None, min_length=9, max_length=9)
):
    """
    Rechercher une entreprise dans l'annuaire PPF.

    Permet de vérifier si un destinataire est inscrit à la facturation électronique
    et d'obtenir ses informations de routage (PPF ou PDP).
    """
    if not siret and not siren:
        raise HTTPException(
            status_code=400,
            detail="SIRET ou SIREN requis"
        )

    # En mode sandbox/demo, retourner des données simulées
    # En production, utiliser le vrai client PPF

    # Données de test
    return AnnuaireLookupResponse(
        siret=siret or (siren + "00001" if siren else ""),
        is_registered=True,
        company_name="Entreprise Test",
        routing="ppf",
        can_receive=True,
        can_send=True,
        supported_formats=["facturx", "ubl"]
    )


@router.get("/annuaire/routing")
async def get_routing_info(
    siret: str = Query(..., min_length=14, max_length=14)
):
    """
    Obtenir les informations de routage pour envoyer une facture.
    """
    # Données de test
    return {
        "siret": siret,
        "can_receive": True,
        "routing_type": "ppf",
        "preferred_format": "facturx",
        "supported_formats": ["facturx", "ubl", "cii"]
    }


@router.get("/annuaire/check-eligibility")
async def check_eligibility(
    siret: str = Query(..., min_length=14, max_length=14)
):
    """
    Vérifier l'éligibilité d'une entreprise à la facturation électronique.

    Retourne les dates d'obligation selon la réforme 2024-2026.
    """
    return {
        "siret": siret,
        "must_register": True,
        "obligation_date": "2026-01-01",
        "is_registered": False,
        "message": "Cette entreprise devra être inscrite à la facturation électronique au plus tard le 01/01/2026"
    }


# =============================================================================
# Routes Utilitaires
# =============================================================================

@router.get("/health")
async def health_check():
    """
    Vérifier l'état du module Factur-X (format technique).

    NOTE: Preview/Send/Archive sont dans /api/v1/factures/
    """
    return {
        "status": "ok",
        "module": "facturx",
        "version": "1.0.0",
        "note": "Preview/Send/Archive déplacés vers /api/v1/factures/",
        "capabilities": {
            "generate": True,
            "validate": True,
            "extract": True,
            "pdp": False,  # Nécessite configuration
            "chorus": False,  # Nécessite configuration
            "reception": True,
            "annuaire": True  # Mode démo
        }
    }


@router.get("/profiles")
async def list_profiles():
    """Lister les profils Factur-X supportés."""
    return {
        "profiles": [
            {
                "id": "MINIMUM",
                "name": "Minimum",
                "description": "Données essentielles uniquement"
            },
            {
                "id": "BASICWL",
                "name": "Basic WL",
                "description": "Sans lignes de détail"
            },
            {
                "id": "BASIC",
                "name": "Basic",
                "description": "Lignes de détail basiques"
            },
            {
                "id": "EN16931",
                "name": "EN16931 (Comfort)",
                "description": "Profil complet recommandé",
                "recommended": True
            },
            {
                "id": "EXTENDED",
                "name": "Extended",
                "description": "Extensions propriétaires"
            }
        ]
    }
