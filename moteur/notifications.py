# =============================================================================
# AZALPLUS - Email Notifications
# =============================================================================
"""
Service d'envoi d'emails pour les devis et factures.
Utilise SMTP configuré via variables d'environnement.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import structlog

from .config import settings
from .db import Database
from .pdf import PDFGenerator

logger = structlog.get_logger()


# =============================================================================
# Exceptions
# =============================================================================
class EmailConfigurationError(Exception):
    """Configuration SMTP manquante ou invalide."""
    pass


class EmailSendError(Exception):
    """Erreur lors de l'envoi d'email."""
    pass


class DocumentNotFoundError(Exception):
    """Document non trouvé."""
    pass


# =============================================================================
# Email Templates Path
# =============================================================================
from pathlib import Path
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# =============================================================================
# Email Service
# =============================================================================
class EmailService:
    """Service d'envoi d'emails (tenant-aware)."""

    _tenant_config_cache: Dict[str, Dict] = {}

    @classmethod
    def get_tenant_config(cls, tenant_id: UUID) -> Dict:
        """Récupère la configuration SMTP du tenant depuis la base de données."""
        cache_key = str(tenant_id)

        # Essayer de charger depuis la base de données
        try:
            configs = Database.query("administration_mail", tenant_id, limit=1)
            if configs and len(configs) > 0:
                config = configs[0]
                return {
                    "smtp_host": config.get("smtp_host", ""),
                    "smtp_port": int(config.get("smtp_port", 587)),
                    "smtp_user": config.get("smtp_user", ""),
                    "smtp_password": config.get("smtp_password", ""),
                    "smtp_from": config.get("smtp_from", "") or config.get("smtp_user", ""),
                    "smtp_ssl": config.get("smtp_ssl", False),
                }
        except Exception as e:
            logger.debug("tenant_smtp_config_not_found", tenant_id=str(tenant_id), error=str(e))

        # Fallback sur les variables d'environnement
        return {
            "smtp_host": settings.SMTP_HOST or "",
            "smtp_port": settings.SMTP_PORT or 587,
            "smtp_user": settings.SMTP_USER or "",
            "smtp_password": settings.SMTP_PASSWORD or "",
            "smtp_from": settings.SMTP_FROM or settings.SMTP_USER or "",
            "smtp_ssl": settings.SMTP_PORT == 465,
        }

    @classmethod
    def is_configured(cls, tenant_id: UUID = None) -> bool:
        """Vérifie si le service SMTP est configuré."""
        if tenant_id:
            config = cls.get_tenant_config(tenant_id)
            return bool(config.get("smtp_host") and config.get("smtp_user"))
        return bool(settings.SMTP_HOST and settings.SMTP_USER)

    @classmethod
    def _validate_config(cls, config: Dict) -> None:
        """Valide la configuration SMTP."""
        if not config.get("smtp_host"):
            raise EmailConfigurationError("SMTP_HOST non configuré")
        if not config.get("smtp_user"):
            raise EmailConfigurationError("SMTP_USER non configuré")
        if not config.get("smtp_password"):
            raise EmailConfigurationError("SMTP_PASSWORD non configuré")

    @classmethod
    def _prepare_devis_for_pdf(cls, devis: Dict) -> Dict:
        """Mappe les champs du devis (base) vers le format attendu par le PDF."""
        import json

        # Debug: log les champs disponibles dans le devis
        logger.debug("prepare_devis_for_pdf",
                     keys=list(devis.keys()) if devis else [],
                     has_lignes="lignes" in devis if devis else False,
                     has_lines="lines" in devis if devis else False,
                     lignes_type=type(devis.get("lignes")).__name__ if devis else None,
                     lignes_count=len(devis.get("lignes", [])) if devis and devis.get("lignes") else 0)

        prepared = {
            "numero": devis.get("number") or devis.get("numero") or "NOUVEAU",
            "date": devis.get("date"),
            "validite": devis.get("validity_date") or devis.get("validite"),
            "validity_date": devis.get("validity_date") or devis.get("validite"),
            "client": devis.get("customer_id") or devis.get("client_id") or devis.get("client"),
            "customer_id": devis.get("customer_id") or devis.get("client_id"),
            "objet": devis.get("title") or devis.get("objet") or "",
            "total_ht": devis.get("subtotal") or devis.get("total_ht") or 0,
            "total_tva": devis.get("tax_amount") or devis.get("total_tva") or 0,
            "total_ttc": devis.get("total") or devis.get("total_ttc") or 0,
            "notes": devis.get("notes") or "",
            "conditions": devis.get("terms") or devis.get("conditions") or "",
            "billing_address": devis.get("billing_address") or "",
            # Pour le vendeur
            "assigned_to": devis.get("assigned_to"),
            "created_by": devis.get("created_by"),
            # Conditions de paiement
            "payment_terms": devis.get("payment_terms") or devis.get("conditions_paiement") or "",
            "payment_terms_text": devis.get("payment_terms_text") or "",
        }

        # Préparer les lignes
        lignes_raw = devis.get("lignes") or devis.get("lines") or []
        if isinstance(lignes_raw, str):
            try:
                lignes_raw = json.loads(lignes_raw)
            except json.JSONDecodeError:
                lignes_raw = []

        lignes = []
        for ligne in lignes_raw:
            if isinstance(ligne, str):
                try:
                    ligne = json.loads(ligne)
                except json.JSONDecodeError:
                    continue

            lignes.append({
                "line_type": ligne.get("line_type", "product"),  # section, note, ou product
                "description": ligne.get("description") or ligne.get("product_name") or "",
                "product_code": ligne.get("product_code") or ligne.get("code") or "",
                "quantite": ligne.get("quantity") or ligne.get("quantite") or 1,
                "unite": ligne.get("unit") or ligne.get("unite") or "Unité(s)",
                "prix_unitaire": ligne.get("unit_price") or ligne.get("prix_unitaire") or 0,
                "remise_percent": ligne.get("discount_percent") or ligne.get("remise_percent") or ligne.get("remise") or 0,
                "taux_tva": ligne.get("tax_rate") or ligne.get("taux_tva") or 20,
                "total_ht_ligne": ligne.get("subtotal") or ligne.get("total_ht_ligne") or 0,
                "section": ligne.get("section") or ligne.get("groupe") or "",
            })

        prepared["lignes"] = lignes

        # Debug: log le résultat
        logger.debug("devis_pdf_data_prepared",
                     numero=prepared.get("numero"),
                     client=prepared.get("client"),
                     lignes_count=len(lignes),
                     total_ttc=prepared.get("total_ttc"))

        return prepared

    @classmethod
    def _prepare_facture_for_pdf(cls, facture: Dict) -> Dict:
        """Mappe les champs de la facture (base) vers le format attendu par le PDF."""
        import json

        prepared = {
            "numero": facture.get("number") or facture.get("numero") or "NOUVEAU",
            "date": facture.get("date") or facture.get("invoice_date"),
            "echeance": facture.get("due_date") or facture.get("echeance"),
            "due_date": facture.get("due_date") or facture.get("echeance"),
            "client": facture.get("customer_id") or facture.get("client_id") or facture.get("client"),
            "customer_id": facture.get("customer_id") or facture.get("client_id"),
            "objet": facture.get("title") or facture.get("objet") or "",
            "total_ht": facture.get("subtotal") or facture.get("total_ht") or 0,
            "total_tva": facture.get("tax_amount") or facture.get("total_tva") or 0,
            "total_ttc": facture.get("total") or facture.get("total_ttc") or 0,
            "notes": facture.get("notes") or "",
            "conditions": facture.get("terms") or facture.get("conditions") or "",
            "billing_address": facture.get("billing_address") or "",
            # Pour le vendeur
            "assigned_to": facture.get("assigned_to"),
            "created_by": facture.get("created_by"),
            # Conditions de paiement
            "payment_terms": facture.get("payment_terms") or facture.get("conditions_paiement") or "",
            "payment_terms_text": facture.get("payment_terms_text") or "",
        }

        # Préparer les lignes
        lignes_raw = facture.get("lignes") or facture.get("lines") or []
        if isinstance(lignes_raw, str):
            try:
                lignes_raw = json.loads(lignes_raw)
            except json.JSONDecodeError:
                lignes_raw = []

        lignes = []
        for ligne in lignes_raw:
            if isinstance(ligne, str):
                try:
                    ligne = json.loads(ligne)
                except json.JSONDecodeError:
                    continue

            lignes.append({
                "line_type": ligne.get("line_type", "product"),  # section, note, ou product
                "description": ligne.get("description") or ligne.get("product_name") or "",
                "product_code": ligne.get("product_code") or ligne.get("code") or "",
                "quantite": ligne.get("quantity") or ligne.get("quantite") or 1,
                "unite": ligne.get("unit") or ligne.get("unite") or "Unité(s)",
                "prix_unitaire": ligne.get("unit_price") or ligne.get("prix_unitaire") or 0,
                "remise_percent": ligne.get("discount_percent") or ligne.get("remise_percent") or ligne.get("remise") or 0,
                "taux_tva": ligne.get("tax_rate") or ligne.get("taux_tva") or 20,
                "total_ht_ligne": ligne.get("subtotal") or ligne.get("total_ht_ligne") or 0,
                "section": ligne.get("section") or ligne.get("groupe") or "",
            })

        prepared["lignes"] = lignes
        return prepared

    @classmethod
    def _create_connection(cls, config: Dict):
        """Crée une connexion SMTP avec la configuration fournie."""
        cls._validate_config(config)

        context = ssl.create_default_context()
        smtp_host = config["smtp_host"]
        smtp_port = config["smtp_port"]
        smtp_user = config["smtp_user"]
        smtp_password = config["smtp_password"]

        if smtp_port == 465 or config.get("smtp_ssl"):
            # SSL direct
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context)
        else:
            # STARTTLS
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls(context=context)

        server.login(smtp_user, smtp_password)
        return server

    @classmethod
    async def send_email(
        cls,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        tenant_id: UUID = None
    ) -> bool:
        """
        Envoie un email.

        Args:
            to: Adresse email du destinataire
            subject: Sujet de l'email
            html_body: Corps de l'email en HTML
            text_body: Corps de l'email en texte brut (fallback)
            cc: Liste des adresses en copie
            bcc: Liste des adresses en copie cachée
            attachments: Liste des pièces jointes [{"filename": str, "content": bytes, "mime_type": str}]
            tenant_id: UUID du tenant pour récupérer la config SMTP

        Returns:
            True si envoyé avec succès
        """
        try:
            # Récupérer la configuration SMTP (tenant-specific ou fallback)
            if tenant_id:
                config = cls.get_tenant_config(tenant_id)
            else:
                config = {
                    "smtp_host": settings.SMTP_HOST,
                    "smtp_port": settings.SMTP_PORT or 587,
                    "smtp_user": settings.SMTP_USER,
                    "smtp_password": settings.SMTP_PASSWORD,
                    "smtp_from": settings.SMTP_FROM or settings.SMTP_USER,
                    "smtp_ssl": settings.SMTP_PORT == 465,
                }

            cls._validate_config(config)

            smtp_from = config.get("smtp_from") or config.get("smtp_user")

            # Créer le message avec la bonne structure MIME
            # Avec pièces jointes: multipart/mixed contenant multipart/alternative + attachments
            # Sans pièces jointes: multipart/alternative
            if attachments:
                msg = MIMEMultipart("mixed")
                msg["Subject"] = subject
                msg["From"] = smtp_from
                msg["To"] = to

                if cc:
                    msg["Cc"] = ", ".join(cc)

                # Sous-partie alternative pour le corps (texte + HTML)
                body_part = MIMEMultipart("alternative")

                if text_body:
                    body_part.attach(MIMEText(text_body, "plain", "utf-8"))
                body_part.attach(MIMEText(html_body, "html", "utf-8"))

                msg.attach(body_part)

                # Ajouter les pièces jointes au niveau racine (mixed)
                for attachment in attachments:
                    mime_type = attachment.get("mime_type", "application/octet-stream")
                    # Extraire le sous-type (ex: "pdf" de "application/pdf")
                    if "/" in mime_type:
                        main_type, sub_type = mime_type.split("/", 1)
                    else:
                        main_type, sub_type = "application", "octet-stream"

                    # Créer l'attachement avec le bon type MIME
                    if main_type == "application":
                        part = MIMEApplication(
                            attachment["content"],
                            _subtype=sub_type,
                            Name=attachment["filename"]
                        )
                    else:
                        # Fallback pour les autres types
                        from email.mime.base import MIMEBase
                        from email import encoders
                        part = MIMEBase(main_type, sub_type)
                        part.set_payload(attachment["content"])
                        encoders.encode_base64(part)

                    part["Content-Disposition"] = f'attachment; filename="{attachment["filename"]}"'
                    msg.attach(part)
                    logger.debug("attachment_added",
                                filename=attachment["filename"],
                                mime_type=mime_type,
                                size=len(attachment["content"]))
            else:
                # Sans pièces jointes: structure simple alternative
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = smtp_from
                msg["To"] = to

                if cc:
                    msg["Cc"] = ", ".join(cc)

                if text_body:
                    msg.attach(MIMEText(text_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Destinataires
            all_recipients = [to]
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)

            # Envoyer
            with cls._create_connection(config) as server:
                server.sendmail(smtp_from, all_recipients, msg.as_string())

            logger.info("email_sent", to=to, subject=subject, tenant_id=str(tenant_id) if tenant_id else None)
            return True

        except EmailConfigurationError:
            raise
        except Exception as e:
            logger.error("email_send_failed", to=to, error=str(e))
            raise EmailSendError(f"Erreur lors de l'envoi: {str(e)}")

    @classmethod
    async def send_referral_thank_you(
        cls,
        ami_email: str,
        prenom_inscrit: str,
        email_inscrit: str
    ) -> bool:
        """
        Envoie un email de remerciement à l'ami qui a recommandé AZALPLUS.

        Args:
            ami_email: Email de l'ami à remercier
            prenom_inscrit: Prénom de la personne qui s'est inscrite
            email_inscrit: Email de la personne inscrite (pour UTM tracking)

        Returns:
            True si envoyé avec succès
        """
        try:
            # Charger les templates
            html_template_path = TEMPLATES_DIR / "email-merci-ami.html"
            text_template_path = TEMPLATES_DIR / "email-merci-ami.txt"

            if not html_template_path.exists():
                logger.error("referral_email_template_missing", path=str(html_template_path))
                return False

            # Encoder l'email pour l'URL
            import urllib.parse
            email_inscrit_encoded = urllib.parse.quote(email_inscrit)

            # Lire et personnaliser le template HTML
            html_body = html_template_path.read_text(encoding="utf-8")
            html_body = html_body.replace("{{ prenom_inscrit }}", prenom_inscrit)
            html_body = html_body.replace("{{ email_inscrit_encoded }}", email_inscrit_encoded)

            # Lire et personnaliser le template texte
            text_body = None
            if text_template_path.exists():
                text_body = text_template_path.read_text(encoding="utf-8")
                text_body = text_body.replace("{{ prenom_inscrit }}", prenom_inscrit)

            # Envoyer l'email
            await cls.send_email(
                to=ami_email,
                subject=f"Merci d'avoir parlé d'AZALPLUS à {prenom_inscrit} !",
                html_body=html_body,
                text_body=text_body
            )

            logger.info(
                "referral_thank_you_sent",
                ami_email=ami_email,
                prenom_inscrit=prenom_inscrit
            )
            return True

        except EmailConfigurationError:
            # SMTP non configuré - on log mais on ne plante pas l'inscription
            logger.warning("referral_email_skipped_no_smtp", ami_email=ami_email)
            return False
        except Exception as e:
            # Erreur d'envoi - on log mais on ne plante pas l'inscription
            logger.error("referral_email_failed", ami_email=ami_email, error=str(e))
            return False

    @classmethod
    async def send_devis_email(
        cls,
        devis_id: UUID,
        recipient: str,
        tenant_id: UUID,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envoie un devis par email.

        Args:
            devis_id: ID du devis
            recipient: Email du destinataire
            tenant_id: ID du tenant (isolation obligatoire)
            custom_message: Message personnalisé optionnel

        Returns:
            Dict avec le statut de l'envoi
        """
        # Récupérer le devis avec isolation tenant
        devis = Database.get_by_id("devis", tenant_id, devis_id)

        if not devis:
            raise DocumentNotFoundError(f"Devis {devis_id} non trouvé")

        # Debug: log les données du devis
        logger.info("send_devis_email_data",
                    devis_id=str(devis_id),
                    has_lignes="lignes" in devis,
                    lignes_count=len(devis.get("lignes", [])) if devis.get("lignes") else 0,
                    numero=devis.get("numero"),
                    number=devis.get("number"),
                    total=devis.get("total"),
                    keys=list(devis.keys())[:15])

        # Récupérer les infos du tenant pour l'email
        with Database.get_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text("SELECT * FROM azalplus.tenants WHERE id = :tenant_id"),
                {"tenant_id": str(tenant_id)}
            )
            tenant = result.fetchone()
            tenant_info = dict(tenant._mapping) if tenant else {}

        # Générer le contenu de l'email
        numero = devis.get("numero", "N/A")
        client_nom = devis.get("client_nom", "")
        montant_ttc = devis.get("montant_ttc", 0)
        date_validite = devis.get("date_validite", "")

        subject = f"Votre devis {numero}"

        html_body = cls._generate_devis_html(
            devis=devis,
            tenant_info=tenant_info,
            custom_message=custom_message
        )

        text_body = f"""
Bonjour,

Veuillez trouver ci-joint votre devis {numero}.

Montant TTC : {montant_ttc:.2f} EUR
{f"Valide jusqu'au : {date_validite}" if date_validite else ""}

{custom_message or "N'hésitez pas à nous contacter pour toute question."}

Cordialement,
{tenant_info.get('nom', "L'équipe")}
        """

        # Générer le PDF
        try:
            generator = PDFGenerator(tenant_id)
            # Mapper les champs de la base vers le format PDF
            pdf_data = cls._prepare_devis_for_pdf(devis)
            pdf_bytes = generator.generate_devis_pdf(pdf_data)
            pdf_filename = f"devis_{numero}.pdf"
            attachments = [{
                "filename": pdf_filename,
                "content": pdf_bytes,
                "mime_type": "application/pdf"
            }]
            logger.info("devis_pdf_generated",
                        numero=numero,
                        size=len(pdf_bytes),
                        pdf_data_lignes=len(pdf_data.get("lignes", [])),
                        pdf_data_numero=pdf_data.get("numero"))
        except Exception as e:
            logger.error("devis_pdf_generation_failed", error=str(e), devis_id=str(devis_id))
            import traceback
            logger.error("devis_pdf_traceback", traceback=traceback.format_exc())
            attachments = None  # Envoyer sans PDF si échec

        # Envoyer l'email avec le PDF
        logger.info("send_devis_email_calling_send",
                    recipient=recipient,
                    has_attachments=attachments is not None,
                    attachment_count=len(attachments) if attachments else 0,
                    attachment_size=len(attachments[0]["content"]) if attachments else 0)
        await cls.send_email(
            to=recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
            tenant_id=tenant_id
        )

        # Mettre à jour le statut du devis
        Database.update(
            "devis",
            tenant_id,
            devis_id,
            {
                "statut": "ENVOYE",
                "date_envoi": datetime.utcnow().isoformat(),
                "email_destinataire": recipient
            }
        )

        logger.info("devis_email_sent", devis_id=str(devis_id), recipient=recipient)

        return {
            "success": True,
            "message": f"Devis {numero} envoyé à {recipient}",
            "devis_id": str(devis_id),
            "recipient": recipient,
            "sent_at": datetime.utcnow().isoformat()
        }

    @classmethod
    async def send_facture_email(
        cls,
        facture_id: UUID,
        recipient: str,
        tenant_id: UUID,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envoie une facture par email.

        Args:
            facture_id: ID de la facture
            recipient: Email du destinataire
            tenant_id: ID du tenant (isolation obligatoire)
            custom_message: Message personnalisé optionnel

        Returns:
            Dict avec le statut de l'envoi
        """
        # Récupérer la facture avec isolation tenant
        facture = Database.get_by_id("factures", tenant_id, facture_id)

        if not facture:
            raise DocumentNotFoundError(f"Facture {facture_id} non trouvée")

        # Récupérer les infos du tenant pour l'email
        with Database.get_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text("SELECT * FROM azalplus.tenants WHERE id = :tenant_id"),
                {"tenant_id": str(tenant_id)}
            )
            tenant = result.fetchone()
            tenant_info = dict(tenant._mapping) if tenant else {}

        # Générer le contenu de l'email
        numero = facture.get("numero", "N/A")
        montant_ttc = facture.get("montant_ttc", 0)
        date_echeance = facture.get("date_echeance", "")

        subject = f"Votre facture {numero}"

        html_body = cls._generate_facture_html(
            facture=facture,
            tenant_info=tenant_info,
            custom_message=custom_message
        )

        text_body = f"""
Bonjour,

Veuillez trouver ci-joint votre facture {numero}.

Montant TTC : {montant_ttc:.2f} EUR
{f"Date d'échéance : {date_echeance}" if date_echeance else ""}

{custom_message or "Nous vous remercions de votre confiance."}

Cordialement,
{tenant_info.get('nom', "L'équipe")}
        """

        # Générer le PDF
        try:
            generator = PDFGenerator(tenant_id)
            # Mapper les champs de la base vers le format PDF
            pdf_data = cls._prepare_facture_for_pdf(facture)
            pdf_bytes = generator.generate_facture_pdf(pdf_data)
            pdf_filename = f"facture_{numero}.pdf"
            attachments = [{
                "filename": pdf_filename,
                "content": pdf_bytes,
                "mime_type": "application/pdf"
            }]
            logger.debug("facture_pdf_generated", numero=numero, size=len(pdf_bytes))
        except Exception as e:
            logger.error("facture_pdf_generation_failed", error=str(e), facture_id=str(facture_id))
            attachments = None  # Envoyer sans PDF si échec

        # Envoyer l'email
        await cls.send_email(
            to=recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
            tenant_id=tenant_id
        )

        # Mettre à jour le statut de la facture
        Database.update(
            "factures",
            tenant_id,
            facture_id,
            {
                "statut": "ENVOYEE",
                "date_envoi": datetime.utcnow().isoformat(),
                "email_destinataire": recipient
            }
        )

        logger.info("facture_email_sent", facture_id=str(facture_id), recipient=recipient)

        return {
            "success": True,
            "message": f"Facture {numero} envoyée à {recipient}",
            "facture_id": str(facture_id),
            "recipient": recipient,
            "sent_at": datetime.utcnow().isoformat()
        }

    @classmethod
    def _generate_devis_html(
        cls,
        devis: Dict[str, Any],
        tenant_info: Dict[str, Any],
        custom_message: Optional[str] = None
    ) -> str:
        """Génère le contenu HTML de l'email pour un devis."""

        numero = devis.get("numero", "N/A")
        client_nom = devis.get("client_nom", "")
        montant_ht = devis.get("montant_ht", 0)
        montant_tva = devis.get("montant_tva", 0)
        montant_ttc = devis.get("montant_ttc", 0)
        date_validite = devis.get("date_validite", "")
        lignes = devis.get("lignes", [])

        tenant_nom = tenant_info.get("nom", "")
        tenant_email = tenant_info.get("email", "")
        tenant_telephone = tenant_info.get("telephone", "")

        # Générer le tableau des lignes
        lignes_html = ""
        if lignes and isinstance(lignes, list):
            for ligne in lignes:
                designation = ligne.get("designation", ligne.get("produit", ""))
                quantite = ligne.get("quantite", 1)
                prix_unitaire = ligne.get("prix_unitaire", 0)
                montant = ligne.get("montant", quantite * prix_unitaire)
                lignes_html += f"""
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;">{designation}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">{quantite}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{prix_unitaire:.2f} EUR</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{montant:.2f} EUR</td>
                </tr>
                """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #2563EB 0%, #1d4ed8 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0;">
        <h1 style="margin: 0; font-size: 24px;">{tenant_nom}</h1>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">Devis N° {numero}</p>
    </div>

    <div style="background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
        <p style="margin: 0 0 20px 0;">Bonjour{f" {client_nom}" if client_nom else ""},</p>

        <p style="margin: 0 0 20px 0;">
            Veuillez trouver ci-dessous votre devis.
            {f"Ce devis est valable jusqu'au {date_validite}." if date_validite else ""}
        </p>

        {f'<p style="margin: 0 0 20px 0; padding: 15px; background: #fff; border-left: 4px solid #2563EB;">{custom_message}</p>' if custom_message else ''}

        <!-- Tableau des lignes -->
        <table style="width: 100%; border-collapse: collapse; background: white; margin: 20px 0;">
            <thead>
                <tr style="background: #f1f5f9;">
                    <th style="padding: 12px; text-align: left;">Désignation</th>
                    <th style="padding: 12px; text-align: center;">Qté</th>
                    <th style="padding: 12px; text-align: right;">Prix unit.</th>
                    <th style="padding: 12px; text-align: right;">Montant</th>
                </tr>
            </thead>
            <tbody>
                {lignes_html if lignes_html else '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #666;">Détail disponible en pièce jointe</td></tr>'}
            </tbody>
        </table>

        <!-- Totaux -->
        <div style="background: white; padding: 20px; border-radius: 8px; margin-top: 20px;">
            <table style="width: 100%; max-width: 300px; margin-left: auto;">
                <tr>
                    <td style="padding: 8px 0; color: #666;">Total HT</td>
                    <td style="padding: 8px 0; text-align: right; font-weight: 500;">{montant_ht:.2f} EUR</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666;">TVA</td>
                    <td style="padding: 8px 0; text-align: right; font-weight: 500;">{montant_tva:.2f} EUR</td>
                </tr>
                <tr style="border-top: 2px solid #2563EB;">
                    <td style="padding: 12px 0; font-weight: 700; font-size: 18px;">Total TTC</td>
                    <td style="padding: 12px 0; text-align: right; font-weight: 700; font-size: 18px; color: #2563EB;">{montant_ttc:.2f} EUR</td>
                </tr>
            </table>
        </div>

        <p style="margin: 30px 0 0 0; color: #666; font-size: 14px;">
            Pour toute question, n'hésitez pas à nous contacter.
        </p>
    </div>

    <div style="background: #1e293b; color: white; padding: 20px; border-radius: 0 0 8px 8px; text-align: center; font-size: 14px;">
        <p style="margin: 0;">{tenant_nom}</p>
        {f'<p style="margin: 5px 0 0 0; opacity: 0.8;">{tenant_email}</p>' if tenant_email else ''}
        {f'<p style="margin: 5px 0 0 0; opacity: 0.8;">{tenant_telephone}</p>' if tenant_telephone else ''}
    </div>
</body>
</html>
        """

    @classmethod
    def _generate_facture_html(
        cls,
        facture: Dict[str, Any],
        tenant_info: Dict[str, Any],
        custom_message: Optional[str] = None
    ) -> str:
        """Génère le contenu HTML de l'email pour une facture."""

        numero = facture.get("numero", "N/A")
        client_nom = facture.get("client_nom", "")
        montant_ht = facture.get("montant_ht", 0)
        montant_tva = facture.get("montant_tva", 0)
        montant_ttc = facture.get("montant_ttc", 0)
        date_echeance = facture.get("date_echeance", "")
        lignes = facture.get("lignes", [])

        tenant_nom = tenant_info.get("nom", "")
        tenant_email = tenant_info.get("email", "")
        tenant_telephone = tenant_info.get("telephone", "")

        # Générer le tableau des lignes
        lignes_html = ""
        if lignes and isinstance(lignes, list):
            for ligne in lignes:
                designation = ligne.get("designation", ligne.get("produit", ""))
                quantite = ligne.get("quantite", 1)
                prix_unitaire = ligne.get("prix_unitaire", 0)
                montant = ligne.get("montant", quantite * prix_unitaire)
                lignes_html += f"""
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;">{designation}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">{quantite}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{prix_unitaire:.2f} EUR</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{montant:.2f} EUR</td>
                </tr>
                """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #10B981 0%, #059669 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0;">
        <h1 style="margin: 0; font-size: 24px;">{tenant_nom}</h1>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">Facture N° {numero}</p>
    </div>

    <div style="background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
        <p style="margin: 0 0 20px 0;">Bonjour{f" {client_nom}" if client_nom else ""},</p>

        <p style="margin: 0 0 20px 0;">
            Veuillez trouver ci-dessous votre facture.
            {f"<strong>Date d'échéance : {date_echeance}</strong>" if date_echeance else ""}
        </p>

        {f'<p style="margin: 0 0 20px 0; padding: 15px; background: #fff; border-left: 4px solid #10B981;">{custom_message}</p>' if custom_message else ''}

        <!-- Tableau des lignes -->
        <table style="width: 100%; border-collapse: collapse; background: white; margin: 20px 0;">
            <thead>
                <tr style="background: #f1f5f9;">
                    <th style="padding: 12px; text-align: left;">Désignation</th>
                    <th style="padding: 12px; text-align: center;">Qté</th>
                    <th style="padding: 12px; text-align: right;">Prix unit.</th>
                    <th style="padding: 12px; text-align: right;">Montant</th>
                </tr>
            </thead>
            <tbody>
                {lignes_html if lignes_html else '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #666;">Détail disponible en pièce jointe</td></tr>'}
            </tbody>
        </table>

        <!-- Totaux -->
        <div style="background: white; padding: 20px; border-radius: 8px; margin-top: 20px;">
            <table style="width: 100%; max-width: 300px; margin-left: auto;">
                <tr>
                    <td style="padding: 8px 0; color: #666;">Total HT</td>
                    <td style="padding: 8px 0; text-align: right; font-weight: 500;">{montant_ht:.2f} EUR</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #666;">TVA</td>
                    <td style="padding: 8px 0; text-align: right; font-weight: 500;">{montant_tva:.2f} EUR</td>
                </tr>
                <tr style="border-top: 2px solid #10B981;">
                    <td style="padding: 12px 0; font-weight: 700; font-size: 18px;">Total TTC</td>
                    <td style="padding: 12px 0; text-align: right; font-weight: 700; font-size: 18px; color: #10B981;">{montant_ttc:.2f} EUR</td>
                </tr>
            </table>
        </div>

        <p style="margin: 30px 0 0 0; color: #666; font-size: 14px;">
            Nous vous remercions de votre confiance.
        </p>
    </div>

    <div style="background: #1e293b; color: white; padding: 20px; border-radius: 0 0 8px 8px; text-align: center; font-size: 14px;">
        <p style="margin: 0;">{tenant_nom}</p>
        {f'<p style="margin: 5px 0 0 0; opacity: 0.8;">{tenant_email}</p>' if tenant_email else ''}
        {f'<p style="margin: 5px 0 0 0; opacity: 0.8;">{tenant_telephone}</p>' if tenant_telephone else ''}
    </div>
</body>
</html>
        """
