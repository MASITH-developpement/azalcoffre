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
# Email Service
# =============================================================================
class EmailService:
    """Service d'envoi d'emails."""

    @classmethod
    def is_configured(cls) -> bool:
        """Vérifie si le service SMTP est configuré."""
        return bool(settings.SMTP_HOST and settings.SMTP_USER)

    @classmethod
    def _validate_config(cls) -> None:
        """Valide la configuration SMTP."""
        if not settings.SMTP_HOST:
            raise EmailConfigurationError("SMTP_HOST non configuré")
        if not settings.SMTP_USER:
            raise EmailConfigurationError("SMTP_USER non configuré")
        if not settings.SMTP_PASSWORD:
            raise EmailConfigurationError("SMTP_PASSWORD non configuré")

    @classmethod
    def _create_connection(cls):
        """Crée une connexion SMTP."""
        cls._validate_config()

        context = ssl.create_default_context()

        if settings.SMTP_PORT == 465:
            # SSL direct
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                context=context
            )
        else:
            # STARTTLS
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls(context=context)

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
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
        attachments: Optional[List[Dict[str, Any]]] = None
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

        Returns:
            True si envoyé avec succès
        """
        try:
            cls._validate_config()

            # Créer le message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM
            msg["To"] = to

            if cc:
                msg["Cc"] = ", ".join(cc)

            # Corps texte
            if text_body:
                part1 = MIMEText(text_body, "plain", "utf-8")
                msg.attach(part1)

            # Corps HTML
            part2 = MIMEText(html_body, "html", "utf-8")
            msg.attach(part2)

            # Pièces jointes
            if attachments:
                for attachment in attachments:
                    part = MIMEApplication(
                        attachment["content"],
                        Name=attachment["filename"]
                    )
                    part["Content-Disposition"] = f'attachment; filename="{attachment["filename"]}"'
                    msg.attach(part)

            # Destinataires
            all_recipients = [to]
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)

            # Envoyer
            with cls._create_connection() as server:
                server.sendmail(settings.SMTP_FROM, all_recipients, msg.as_string())

            logger.info("email_sent", to=to, subject=subject)
            return True

        except EmailConfigurationError:
            raise
        except Exception as e:
            logger.error("email_send_failed", to=to, error=str(e))
            raise EmailSendError(f"Erreur lors de l'envoi: {str(e)}")

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

        # Envoyer l'email
        await cls.send_email(
            to=recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body
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
        facture = Database.get_by_id("facture", tenant_id, facture_id)

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

        # Envoyer l'email
        await cls.send_email(
            to=recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

        # Mettre à jour le statut de la facture
        Database.update(
            "facture",
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
