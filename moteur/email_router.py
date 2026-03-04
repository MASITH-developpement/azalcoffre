# =============================================================================
# AZALPLUS - Email Router
# =============================================================================
"""
Routes API pour l'envoi d'emails (devis et factures).
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
import structlog

from .tenant import get_current_tenant
from .auth import require_auth
from .notifications import EmailService, EmailConfigurationError, EmailSendError, DocumentNotFoundError

logger = structlog.get_logger()

# =============================================================================
# Router Email
# =============================================================================
email_router = APIRouter(prefix="/api", tags=["Email"])


# =============================================================================
# Schemas
# =============================================================================
class SendEmailRequest(BaseModel):
    """Schema pour l'envoi d'email."""
    recipient: str
    custom_message: Optional[str] = None


# =============================================================================
# Routes
# =============================================================================

@email_router.get("/email/status")
async def get_email_status(user: dict = Depends(require_auth)):
    """
    Verifie si le service email est configure.

    Returns:
        Status de configuration du service email
    """
    return {
        "configured": EmailService.is_configured(),
        "smtp_host": bool(EmailService.is_configured())
    }


@email_router.post("/Devis/{item_id}/envoyer")
async def send_devis_email(
    item_id: UUID,
    data: SendEmailRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Envoie un devis par email au client.

    Args:
        item_id: ID du devis
        data: Email du destinataire et message optionnel

    Returns:
        Confirmation d'envoi avec details

    Raises:
        404: Devis non trouve
        400: Email non configure ou erreur d'envoi
    """
    try:
        result = await EmailService.send_devis_email(
            devis_id=item_id,
            recipient=data.recipient,
            tenant_id=tenant_id,
            custom_message=data.custom_message
        )

        logger.info(
            "devis_email_sent_via_api",
            tenant_id=str(tenant_id),
            devis_id=str(item_id),
            recipient=data.recipient,
            user_email=user.get("email")
        )

        return result

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EmailConfigurationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Service email non configure: {str(e)}"
        )
    except EmailSendError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erreur d'envoi: {str(e)}"
        )


@email_router.post("/Facture/{item_id}/envoyer")
async def send_facture_email(
    item_id: UUID,
    data: SendEmailRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Envoie une facture par email au client.

    Args:
        item_id: ID de la facture
        data: Email du destinataire et message optionnel

    Returns:
        Confirmation d'envoi avec details

    Raises:
        404: Facture non trouvee
        400: Email non configure ou erreur d'envoi
    """
    try:
        result = await EmailService.send_facture_email(
            facture_id=item_id,
            recipient=data.recipient,
            tenant_id=tenant_id,
            custom_message=data.custom_message
        )

        logger.info(
            "facture_email_sent_via_api",
            tenant_id=str(tenant_id),
            facture_id=str(item_id),
            recipient=data.recipient,
            user_email=user.get("email")
        )

        return result

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EmailConfigurationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Service email non configure: {str(e)}"
        )
    except EmailSendError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erreur d'envoi: {str(e)}"
        )
