# =============================================================================
# AZALPLUS - Email Router
# =============================================================================
"""
Routes API pour l'envoi d'emails (devis et factures).
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel
import structlog

from .tenant import get_current_tenant
from .auth import require_auth
from .notifications import EmailService, EmailConfigurationError, EmailSendError, DocumentNotFoundError
from .db import Database
from .pdf import PDFGenerator

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


class SendDocumentRequest(BaseModel):
    """Schema pour l'envoi de document par email."""
    to: str
    document_type: str  # Devis, Facture
    document_data: Dict[str, Any]
    client_id: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None


class TestSmtpRequest(BaseModel):
    """Schema pour tester la connexion SMTP."""
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_ssl: bool = False


# =============================================================================
# Routes
# =============================================================================

@email_router.post("/email/test-connection")
async def test_smtp_connection(
    data: TestSmtpRequest,
    user: dict = Depends(require_auth)
):
    """
    Teste la connexion au serveur SMTP.

    Returns:
        Resultat du test de connexion
    """
    import smtplib
    import ssl

    try:
        context = ssl.create_default_context()

        if data.smtp_ssl or data.smtp_port == 465:
            # SSL direct
            server = smtplib.SMTP_SSL(
                data.smtp_host,
                data.smtp_port,
                context=context,
                timeout=10
            )
        else:
            # STARTTLS
            server = smtplib.SMTP(data.smtp_host, data.smtp_port, timeout=10)
            server.starttls(context=context)

        # Tenter l'authentification
        server.login(data.smtp_user, data.smtp_password)
        server.quit()

        logger.info("smtp_test_success", host=data.smtp_host, user=data.smtp_user)
        return {
            "success": True,
            "message": "Connexion SMTP réussie"
        }

    except smtplib.SMTPAuthenticationError as e:
        logger.warning("smtp_test_auth_failed", error=str(e))
        return {
            "success": False,
            "error": "Échec d'authentification. Vérifiez vos identifiants."
        }
    except smtplib.SMTPConnectError as e:
        logger.warning("smtp_test_connect_failed", error=str(e))
        return {
            "success": False,
            "error": f"Impossible de se connecter au serveur {data.smtp_host}:{data.smtp_port}"
        }
    except Exception as e:
        logger.error("smtp_test_error", error=str(e))
        return {
            "success": False,
            "error": str(e)
        }


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


@email_router.post("/email/send-document")
async def send_document_email(
    data: SendDocumentRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Envoie un document (devis ou facture) par email avec PDF attache.

    Args:
        data: Donnees du document et destinataire

    Returns:
        Confirmation d'envoi
    """
    try:
        # Verifier la configuration email (tenant-specific)
        if not EmailService.is_configured(tenant_id):
            raise HTTPException(
                status_code=400,
                detail="Service email non configure. Configurez SMTP dans Parametres > Email."
            )

        # Generer le PDF
        doc_type = data.document_type.lower()
        generator = PDFGenerator(tenant_id)

        # Preparer les donnees pour le PDF
        # Recuperer le document complet depuis la DB si on a l'ID
        doc_data = data.document_data
        doc_id = doc_data.get("id")

        if doc_id:
            # Fetch le document complet depuis la DB pour avoir tous les champs
            table_name = "devis" if doc_type in ["devis", "quote"] else "factures"
            try:
                full_doc = Database.get_by_id(table_name, tenant_id, UUID(str(doc_id)))
                if full_doc:
                    # IMPORTANT: Si le frontend envoie 'lines', il a priorite sur 'lignes' de la DB
                    frontend_lines = doc_data.get("lines")

                    # Merger: les donnees du frontend ecrasent celles de la DB
                    for key, value in doc_data.items():
                        if value is not None:
                            full_doc[key] = value

                    # Si le frontend a envoye 'lines', remplacer aussi 'lignes'
                    if frontend_lines:
                        full_doc["lignes"] = frontend_lines
                        logger.debug("email_pdf_using_frontend_lines", count=len(frontend_lines))

                    doc_data = full_doc
                    logger.debug("document_fetched_from_db", doc_id=doc_id, keys=list(doc_data.keys()))
            except Exception as e:
                logger.warning("document_fetch_failed", doc_id=doc_id, error=str(e))

        prepared_data = _prepare_pdf_data(doc_data)

        # Debug: log les données préparées
        logger.info("email_pdf_data_prepared",
                    numero=prepared_data.get("numero"),
                    lignes_count=len(prepared_data.get("lignes", [])),
                    total_ttc=prepared_data.get("total_ttc"),
                    customer_id=prepared_data.get("customer_id"),
                    payment_terms=prepared_data.get("payment_terms"))

        if doc_type in ["devis", "quote"]:
            pdf_bytes = generator.generate_devis_pdf(prepared_data)
            doc_name = "Devis"
            filename = f"devis_{prepared_data.get('numero', 'nouveau')}.pdf"
        elif doc_type in ["facture", "invoice"]:
            pdf_bytes = generator.generate_facture_pdf(prepared_data)
            doc_name = "Facture"
            filename = f"facture_{prepared_data.get('numero', 'nouveau')}.pdf"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Type de document non supporte: {doc_type}"
            )

        # Debug: log la taille du PDF généré
        logger.info("email_pdf_generated",
                    doc_type=doc_type,
                    filename=filename,
                    pdf_size=len(pdf_bytes) if pdf_bytes else 0)

        # Recuperer les infos client si client_id fourni
        client_name = ""
        if data.client_id:
            try:
                client = Database.get_by_id("clients", tenant_id, UUID(data.client_id))
                if client:
                    client_name = client.get("raison_sociale") or client.get("name") or client.get("nom", "")
            except Exception:
                pass

        # Preparer l'email
        subject = data.subject or f"{doc_name} - {prepared_data.get('numero', '')}"
        if client_name:
            subject = f"{doc_name} pour {client_name}"

        # Corps du message
        body = data.message or f"""Bonjour,

Veuillez trouver ci-joint votre {doc_name.lower()}.

Cordialement,
L'equipe AZAL"""

        # Envoyer l'email via EmailService (avec config tenant)
        result = await EmailService.send_email(
            to=data.to,
            subject=subject,
            html_body=f"<html><body><p>{body.replace(chr(10), '<br/>')}</p></body></html>",
            text_body=body,
            attachments=[{
                "filename": filename,
                "content": pdf_bytes,
                "mime_type": "application/pdf"
            }],
            tenant_id=tenant_id
        )

        logger.info(
            "document_email_sent",
            tenant_id=str(tenant_id),
            doc_type=doc_type,
            recipient=data.to,
            user_email=user.get("email")
        )

        return {
            "success": True,
            "message": f"Email envoye a {data.to}",
            "document_type": doc_type,
            "filename": filename
        }

    except HTTPException:
        raise
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
    except Exception as e:
        logger.error("document_email_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'envoi: {str(e)}"
        )


def _prepare_pdf_data(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare les donnees du document pour le generateur PDF.
    Inclut tous les champs necessaires pour un PDF complet.
    """
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
        # Champs essentiels pour le PDF
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


# =============================================================================
# PDF Configuration Endpoints
# =============================================================================
class PDFConfigRequest(BaseModel):
    """Schema pour la configuration PDF."""
    show_logo: Optional[bool] = True
    logo_position: Optional[str] = "left"
    primary_color: Optional[str] = "#3454D1"
    accent_color: Optional[str] = "#6B9FFF"
    table_style: Optional[str] = "simple"
    corners: Optional[str] = "rounded"
    font: Optional[str] = "Helvetica"
    font_size: Optional[str] = "11"
    margins: Optional[str] = "15"
    paper_size: Optional[str] = "A4"
    show_siret: Optional[bool] = True
    show_tva_intra: Optional[bool] = True
    show_bank_details: Optional[bool] = True
    show_signature_zone: Optional[bool] = True
    footer_devis: Optional[str] = ""
    footer_facture: Optional[str] = ""


@email_router.get("/settings/pdf-config")
async def get_pdf_config(
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Récupère la configuration PDF du tenant."""
    try:
        configs = Database.query("pdf_config", tenant_id, limit=1)
        if configs and len(configs) > 0:
            return configs[0]
        return {}
    except Exception as e:
        logger.debug("pdf_config_not_found", error=str(e))
        return {}


@email_router.post("/settings/pdf-config")
async def save_pdf_config(
    config: PDFConfigRequest,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """Enregistre la configuration PDF du tenant."""
    try:
        config_data = config.model_dump()

        # Vérifier si une config existe déjà
        existing = Database.query("pdf_config", tenant_id, limit=1)

        if existing and len(existing) > 0:
            # Mettre à jour
            Database.update("pdf_config", tenant_id, existing[0]["id"], config_data)
        else:
            # Créer
            Database.create("pdf_config", tenant_id, config_data)

        logger.info("pdf_config_saved", tenant_id=str(tenant_id), user_email=user.get("email"))
        return {"success": True, "message": "Configuration PDF enregistrée"}
    except Exception as e:
        logger.error("pdf_config_save_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
