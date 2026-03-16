# =============================================================================
# AZALPLUS - Module Factures - Router
# =============================================================================
"""
Endpoints REST pour les factures : preview, send, archive.

Routes :
- POST /api/v1/factures/preview - Prévisualiser avant envoi
- POST /api/v1/factures/send - Envoyer (email + démat en parallèle)
- GET /api/v1/factures/{id}/archive - Infos archivage AZALCOFFRE
- GET /api/v1/factures/{id}/archive/certificate - Certificat d'intégrité
- GET /api/v1/factures/health - État du module
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .schemas import (
    PreviewRequest,
    PreviewResponse,
    SendRequest,
    SendResponse,
    ArchiveInfoResponse,
    HealthResponse,
)
from .service import (
    FacturesService,
    SendOptions,
    cache_preview,
    get_cached_preview,
    clear_cached_preview,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/factures", tags=["Factures"])


# =============================================================================
# Dépendances
# =============================================================================

def get_tenant_id() -> UUID:
    """Obtenir le tenant_id depuis le contexte."""
    try:
        from moteur.tenant import TenantContext
        tenant_id = TenantContext.get_tenant_id()
        if tenant_id:
            return tenant_id
    except ImportError:
        pass
    # Fallback pour tests
    return UUID("00000000-0000-0000-0000-000000000001")


def get_tenant_config(tenant_id: UUID) -> dict:
    """Récupère la configuration du tenant."""
    try:
        from moteur.db import Database
        # Récupérer infos entreprise depuis paramètres tenant
        params = Database.query("parametres", tenant_id, limit=1)
        if params:
            p = params[0]
            return {
                "name": p.get("raison_sociale", ""),
                "siret": p.get("siret", ""),
                "tva_intra": p.get("tva_intra", ""),
                "address": p.get("adresse_ligne1", ""),
                "city": p.get("ville", ""),
                "postal_code": p.get("code_postal", ""),
                "email": p.get("email_facturation", ""),
            }
    except Exception as e:
        logger.warning(f"Erreur récupération config tenant: {e}")
    return {}


# =============================================================================
# Routes Preview & Send
# =============================================================================

@router.post("/preview", response_model=PreviewResponse)
async def generate_preview(request: PreviewRequest):
    """
    Génère une prévisualisation de facture.

    Retourne :
    - PDF en base64 pour affichage web
    - Totaux calculés
    - Options d'envoi disponibles
    - Erreurs de validation

    Stocke la prévisualisation en cache pour l'envoi ultérieur.
    """
    try:
        tenant_id = get_tenant_id()
        tenant_config = get_tenant_config(tenant_id)

        # Fusionner config tenant avec données requête
        seller_config = {
            "name": request.seller_name or tenant_config.get("name", ""),
            "siret": request.seller_siret or tenant_config.get("siret", ""),
            "tva_intra": request.seller_tva or tenant_config.get("tva_intra", ""),
            "address": request.seller_address or tenant_config.get("address", ""),
            "city": request.seller_city or tenant_config.get("city", ""),
            "postal_code": request.seller_postal_code or tenant_config.get("postal_code", ""),
            "email": request.seller_email or tenant_config.get("email", ""),
        }

        # Parser les dates
        from datetime import datetime as dt
        invoice_date = dt.strptime(request.invoice_date, "%Y-%m-%d").date()
        due_date = None
        if request.due_date:
            due_date = dt.strptime(request.due_date, "%Y-%m-%d").date()

        invoice_data = {
            "number": request.invoice_number,
            "date": invoice_date,
            "due_date": due_date,
            "payment_terms": request.payment_terms,
            "notes": request.notes,
        }

        buyer_data = {
            "name": request.buyer_name,
            "siret": request.buyer_siret,
            "tva_intra": request.buyer_tva,
            "address": request.buyer_address or "",
            "city": request.buyer_city or "",
            "postal_code": request.buyer_postal_code or "",
            "email": request.buyer_email,
        }

        lines = [
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "vat_rate": line.vat_rate,
            }
            for line in request.lines
        ]

        # Générer la prévisualisation
        service = FacturesService(tenant_id=tenant_id)
        preview = service.generate_preview(
            invoice_id=request.invoice_id,
            invoice_data=invoice_data,
            lines=lines,
            seller_config=seller_config,
            buyer_data=buyer_data,
        )

        # Stocker en cache
        cache_preview(request.invoice_id, preview)

        return PreviewResponse(
            success=True,
            invoice_number=preview.invoice_number,
            total_ht=float(preview.total_ht),
            total_tva=float(preview.total_tva),
            total_ttc=float(preview.total_ttc),
            pdf_base64=preview.pdf_base64,
            available_send_options=[opt.value for opt in preview.available_send_options],
            recommended_send_option=preview.recommended_send_option.value,
            is_valid=preview.is_valid,
            validation_errors=preview.validation_errors,
        )

    except Exception as e:
        logger.error(f"Erreur prévisualisation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send", response_model=SendResponse)
async def send_invoice(request: SendRequest):
    """
    Envoie une facture après prévisualisation.

    Exécute en parallèle :
    - Envoi email (si activé)
    - Envoi dématérialisé PDP/Chorus (si activé)
    - Archivage AZALCOFFRE (toujours)

    Requiert une prévisualisation préalable (POST /preview).
    """
    try:
        # Récupérer la prévisualisation du cache
        preview = get_cached_preview(request.invoice_id)

        if not preview:
            raise HTTPException(
                status_code=404,
                detail="Prévisualisation non trouvée. Appelez /preview d'abord."
            )

        # Options d'envoi
        options = SendOptions(
            send_email=request.send_email,
            send_demat=request.send_demat,
            email_to=request.email_to,
            email_cc=request.email_cc,
            email_message=request.email_message,
            include_payment_link=request.include_payment_link,
            demat_channel=request.demat_channel,
        )

        # Envoyer
        tenant_id = get_tenant_id()
        service = FacturesService(tenant_id=tenant_id)
        result = service.send_invoice(preview, options)

        # Nettoyer le cache
        clear_cached_preview(request.invoice_id)

        return SendResponse(
            success=result.success,
            email_sent=result.email_sent,
            email_error=result.email_error,
            demat_sent=result.demat_sent,
            demat_error=result.demat_error,
            demat_id=result.demat_id,
            archived=result.archived,
            archive_id=result.archive_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur envoi: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Routes Archive
# =============================================================================

@router.get("/{invoice_id}/archive", response_model=ArchiveInfoResponse)
async def get_archive_info(invoice_id: UUID):
    """
    Récupère les informations d'archivage depuis AZALCOFFRE.
    """
    try:
        from integrations.azalcoffre import AzalCoffreClient

        tenant_id = get_tenant_id()

        with AzalCoffreClient() as client:
            if not client.config.is_configured:
                return ArchiveInfoResponse(found=False, invoice_id=invoice_id)

            doc = client.get_document_by_source(
                tenant_id=tenant_id,
                source_id=invoice_id,
            )

            if not doc:
                return ArchiveInfoResponse(found=False, invoice_id=invoice_id)

            integrity = doc.integrity_proof
            if not integrity:
                try:
                    integrity = client.verify_integrity(
                        tenant_id=tenant_id,
                        archive_id=doc.id,
                    )
                except Exception:
                    pass

            return ArchiveInfoResponse(
                found=True,
                invoice_id=invoice_id,
                archive_id=doc.id,
                archived_at=doc.archived_at,
                hash_value=integrity.hash_value if integrity else None,
                hash_algorithm=integrity.hash_algorithm if integrity else "SHA-512",
                is_valid=integrity.is_valid if integrity else False,
                tsa_timestamp=integrity.tsa_timestamp if integrity else None,
                tsa_authority=integrity.tsa_authority if integrity else None,
                coffre_url=doc.coffre_url,
                retention_years=doc.retention_years,
                expires_at=doc.expires_at.isoformat() if doc.expires_at else None,
            )

    except Exception as e:
        logger.error(f"Erreur récupération archive: {e}")
        return ArchiveInfoResponse(found=False, invoice_id=invoice_id)


@router.get("/{invoice_id}/archive/certificate")
async def download_certificate(invoice_id: UUID):
    """
    Télécharge le certificat d'intégrité PDF depuis AZALCOFFRE.
    """
    try:
        from integrations.azalcoffre import AzalCoffreClient

        tenant_id = get_tenant_id()

        with AzalCoffreClient() as client:
            if not client.config.is_configured:
                raise HTTPException(status_code=503, detail="AZALCOFFRE non configuré")

            doc = client.get_document_by_source(
                tenant_id=tenant_id,
                source_id=invoice_id,
            )

            if not doc:
                raise HTTPException(status_code=404, detail="Document non archivé")

            certificate = client.get_integrity_certificate(
                tenant_id=tenant_id,
                archive_id=doc.id,
            )

            return Response(
                content=certificate,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="certificat_{doc.document_number}.pdf"'
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur certificat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Vérifie l'état du module."""
    # Vérifier AZALCOFFRE
    azalcoffre_ok = False
    try:
        from integrations.azalcoffre import AzalCoffreClient
        with AzalCoffreClient() as client:
            azalcoffre_ok = client.config.is_configured and client.health_check()
    except Exception:
        pass

    # Vérifier Email
    email_ok = False
    try:
        from integrations.settings import get_settings
        email_ok = get_settings().email.is_configured
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        module="factures",
        version="1.0.0",
        capabilities={
            "preview": True,
            "send": True,
            "email": email_ok,
            "archive": azalcoffre_ok,
            "demat_pdp": False,
            "demat_chorus": False,
        }
    )
