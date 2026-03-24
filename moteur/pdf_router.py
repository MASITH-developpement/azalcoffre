# =============================================================================
# AZALPLUS - PDF Router
# =============================================================================
"""
Routes API pour la generation de PDF (devis, factures, etc.).
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel
import structlog

from .tenant import get_current_tenant
from .auth import require_auth
from .pdf import PDFGenerator
from .db import Database

logger = structlog.get_logger()

# =============================================================================
# Router PDF
# =============================================================================
pdf_router = APIRouter(prefix="/api/pdf", tags=["PDF"])


# =============================================================================
# Schemas
# =============================================================================
class LigneDocument(BaseModel):
    """Schema pour une ligne de document."""
    line_number: Optional[int] = None
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = 1
    unit: Optional[str] = None
    unit_price: Optional[float] = 0
    discount_percent: Optional[float] = 0
    tax_rate: Optional[float] = 20
    subtotal: Optional[float] = 0
    tax_amount: Optional[float] = 0
    total: Optional[float] = 0


class GeneratePDFRequest(BaseModel):
    """Schema pour la generation de PDF."""
    document_type: str  # devis, facture
    document_data: Dict[str, Any]


# =============================================================================
# Routes
# =============================================================================

@pdf_router.post("/generate")
async def generate_pdf(
    request: GeneratePDFRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Genere un PDF pour un document (devis ou facture).

    Args:
        request: Type de document et donnees

    Returns:
        PDF en bytes
    """
    try:
        doc_type = request.document_type.lower()
        doc_data = request.document_data

        # Recuperer le document complet depuis la DB si on a l'ID
        doc_id = doc_data.get("id")
        if doc_id:
            table_name = "devis" if doc_type in ["devis", "quote"] else "factures"
            try:
                full_doc = Database.get_by_id(table_name, tenant_id, UUID(str(doc_id)))
                if full_doc:
                    # IMPORTANT: Si le frontend envoie 'lines', il a priorite sur 'lignes' de la DB
                    frontend_lines = doc_data.get("lines")

                    # Merger: donnees du frontend ecrasent celles de la DB
                    for key, value in doc_data.items():
                        if value is not None:
                            full_doc[key] = value

                    # Si le frontend a envoye 'lines', remplacer aussi 'lignes'
                    if frontend_lines:
                        full_doc["lignes"] = frontend_lines
                        logger.debug("pdf_using_frontend_lines", count=len(frontend_lines))

                    doc_data = full_doc
                    logger.debug("pdf_document_fetched_from_db", doc_id=doc_id)
            except Exception as e:
                logger.warning("pdf_document_fetch_failed", doc_id=doc_id, error=str(e))

        # Preparer les donnees pour le generateur
        prepared_data = _prepare_document_data(doc_data)

        # Generer le PDF
        generator = PDFGenerator(tenant_id)

        if doc_type in ["devis", "quote"]:
            pdf_bytes = generator.generate_devis_pdf(prepared_data)
            filename = f"devis_{prepared_data.get('numero', 'nouveau')}.pdf"
        elif doc_type in ["facture", "invoice"]:
            pdf_bytes = generator.generate_facture_pdf(prepared_data)
            filename = f"facture_{prepared_data.get('numero', 'nouveau')}.pdf"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Type de document non supporte: {doc_type}"
            )

        logger.info(
            "pdf_generated_via_api",
            tenant_id=str(tenant_id),
            doc_type=doc_type,
            user_email=user.get("email")
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("pdf_generation_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la generation du PDF: {str(e)}"
        )


@pdf_router.post("/preview")
async def preview_pdf(
    request: GeneratePDFRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Genere un apercu PDF (inline, pas en telechargement).
    """
    try:
        doc_type = request.document_type.lower()
        doc_data = request.document_data

        # Recuperer le document complet depuis la DB si on a l'ID
        doc_id = doc_data.get("id")
        if doc_id:
            table_name = "devis" if doc_type in ["devis", "quote"] else "factures"
            try:
                full_doc = Database.get_by_id(table_name, tenant_id, UUID(str(doc_id)))
                if full_doc:
                    # IMPORTANT: Si le frontend envoie 'lines', il a priorite sur 'lignes' de la DB
                    frontend_lines = doc_data.get("lines")

                    for key, value in doc_data.items():
                        if value is not None:
                            full_doc[key] = value

                    # Si le frontend a envoye 'lines', remplacer aussi 'lignes'
                    if frontend_lines:
                        full_doc["lignes"] = frontend_lines

                    doc_data = full_doc
            except Exception as e:
                logger.warning("pdf_preview_document_fetch_failed", doc_id=doc_id, error=str(e))

        prepared_data = _prepare_document_data(doc_data)
        generator = PDFGenerator(tenant_id)

        if doc_type in ["devis", "quote"]:
            pdf_bytes = generator.generate_devis_pdf(prepared_data)
        elif doc_type in ["facture", "invoice"]:
            pdf_bytes = generator.generate_facture_pdf(prepared_data)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Type de document non supporte: {doc_type}"
            )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("pdf_preview_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la generation de l'apercu: {str(e)}"
        )


def _prepare_document_data(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare les donnees du document pour le generateur PDF.
    Mappe les champs du frontend vers les champs attendus par PDFGenerator.
    Inclut tous les champs necessaires pour un PDF complet.
    """
    # Mapping des champs
    prepared = {
        "numero": doc_data.get("number") or doc_data.get("numero") or "NOUVEAU",
        "date": doc_data.get("date"),
        "validite": doc_data.get("validity_date") or doc_data.get("validite"),
        "validity_date": doc_data.get("validity_date") or doc_data.get("validite"),
        "echeance": doc_data.get("due_date") or doc_data.get("echeance"),
        "due_date": doc_data.get("due_date") or doc_data.get("echeance"),
        "client": doc_data.get("customer_id") or doc_data.get("client_id"),
        "customer_id": doc_data.get("customer_id") or doc_data.get("client_id"),
        "objet": doc_data.get("title") or doc_data.get("objet") or "",
        "reference_client": doc_data.get("reference") or doc_data.get("reference_client") or "",
        "total_ht": doc_data.get("subtotal") or doc_data.get("total_ht") or 0,
        "total_tva": doc_data.get("tax_amount") or doc_data.get("total_tva") or 0,
        "total_ttc": doc_data.get("total") or doc_data.get("total_ttc") or 0,
        "notes": doc_data.get("notes") or "",
        "conditions": doc_data.get("terms") or doc_data.get("conditions") or "",
        # Champs essentiels pour un PDF complet
        "billing_address": doc_data.get("billing_address") or doc_data.get("adresse_facturation") or "",
        "assigned_to": doc_data.get("assigned_to"),
        "created_by": doc_data.get("created_by"),
        # Signature
        "signature_client": doc_data.get("signature_client"),
        "signature_date": doc_data.get("signature_date"),
        "signature_ip": doc_data.get("signature_ip"),
        # Conditions de paiement
        "payment_terms": doc_data.get("payment_terms") or doc_data.get("conditions_paiement") or "",
        "payment_terms_text": doc_data.get("payment_terms_text") or "",
    }

    # Preparer les lignes avec tous les champs
    lignes_raw = doc_data.get("lignes") or doc_data.get("lines") or []
    lignes = []

    for ligne in lignes_raw:
        lignes.append({
            "line_type": ligne.get("line_type", "product"),  # section, note, ou product
            "description": ligne.get("description") or ligne.get("product_name") or "",
            "product_code": ligne.get("product_code") or ligne.get("code") or "",
            "quantite": ligne.get("quantity") or ligne.get("quantite") or 1,
            "unite": ligne.get("unit") or ligne.get("unite") or "Unité(s)",
            "prix_unitaire": ligne.get("unit_price") or ligne.get("prix_unitaire") or 0,
            "remise_percent": ligne.get("discount_percent") or ligne.get("remise_percent") or 0,
            "taux_tva": ligne.get("tax_rate") or ligne.get("taux_tva") or 20,
            "total_ht_ligne": ligne.get("subtotal") or ligne.get("total_ht_ligne") or 0,
            "section": ligne.get("section") or ligne.get("groupe") or "",
        })

    prepared["lignes"] = lignes

    return prepared
