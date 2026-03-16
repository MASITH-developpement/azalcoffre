"""
AZALPLUS - Service d'envoi email des factures
Envoi parallèle à la dématérialisation

Utilise la configuration centralisée de integrations/settings.py
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Optional
from uuid import UUID

from ..settings import get_settings, EmailSettings

logger = logging.getLogger(__name__)


class EmailStatus(str, Enum):
    """Statut d'envoi email"""
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    OPENED = "OPENED"
    CLICKED = "CLICKED"
    BOUNCED = "BOUNCED"
    ERROR = "ERROR"


@dataclass
class EmailResult:
    """Résultat d'envoi email"""
    success: bool
    status: EmailStatus
    message_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class InvoiceEmailData:
    """Données pour l'email de facture"""
    # Destinataire
    to_email: str
    to_name: str

    # Facture
    invoice_number: str
    invoice_date: str
    amount_ttc: str
    currency: str = "EUR"

    # Émetteur
    company_name: str = ""
    company_email: str = ""

    # Optionnel
    due_date: Optional[str] = None
    payment_link: Optional[str] = None  # Lien Fintecture/Stripe
    custom_message: Optional[str] = None

    # Répondre à
    reply_to: Optional[str] = None


class InvoiceEmailSender:
    """
    Service d'envoi d'emails pour les factures.

    Fonctionnalités :
    - Email avec PDF en pièce jointe
    - Template HTML professionnel
    - Lien de paiement intégré (Fintecture)
    - Tracking ouverture/clic (optionnel)

    Utilise la configuration centralisée depuis settings.py
    """

    def __init__(self, email_settings: Optional[EmailSettings] = None):
        if email_settings:
            self._settings = email_settings
        else:
            self._settings = get_settings().email

        if not self._settings.is_configured:
            logger.warning("Email non configuré - SMTP_HOST et SMTP_USER requis")

    def send_invoice(
        self,
        email_data: InvoiceEmailData,
        pdf_content: bytes,
        pdf_filename: str,
    ) -> EmailResult:
        """
        Envoie une facture par email.

        Args:
            email_data: Données de l'email
            pdf_content: Contenu du PDF Factur-X
            pdf_filename: Nom du fichier (ex: "FA-2026-001.pdf")

        Returns:
            EmailResult avec statut d'envoi
        """
        try:
            # Créer le message
            msg = self._create_message(email_data, pdf_content, pdf_filename)

            # Envoyer via SMTP
            message_id = self._send_smtp(msg, email_data.to_email)

            logger.info(
                f"Email facture envoyé: {email_data.invoice_number} -> {email_data.to_email}"
            )

            return EmailResult(
                success=True,
                status=EmailStatus.SENT,
                message_id=message_id,
            )

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Erreur authentification SMTP: {e}")
            return EmailResult(
                success=False,
                status=EmailStatus.ERROR,
                error_message="Erreur authentification email",
            )
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"Destinataire refusé: {e}")
            return EmailResult(
                success=False,
                status=EmailStatus.BOUNCED,
                error_message=f"Adresse email invalide: {email_data.to_email}",
            )
        except Exception as e:
            logger.exception(f"Erreur envoi email: {e}")
            return EmailResult(
                success=False,
                status=EmailStatus.ERROR,
                error_message=str(e),
            )

    def _create_message(
        self,
        data: InvoiceEmailData,
        pdf_content: bytes,
        pdf_filename: str,
    ) -> MIMEMultipart:
        """Crée le message email avec pièce jointe"""
        msg = MIMEMultipart("mixed")

        # Headers
        msg["Subject"] = f"Facture {data.invoice_number} - {data.company_name}"
        msg["From"] = f"{self._settings.from_name} <{self._settings.from_email}>"
        msg["To"] = f"{data.to_name} <{data.to_email}>"

        if data.reply_to:
            msg["Reply-To"] = data.reply_to

        # Corps du message (HTML + texte)
        body = MIMEMultipart("alternative")

        # Version texte
        text_content = self._generate_text_body(data)
        body.attach(MIMEText(text_content, "plain", "utf-8"))

        # Version HTML
        html_content = self._generate_html_body(data)
        body.attach(MIMEText(html_content, "html", "utf-8"))

        msg.attach(body)

        # Pièce jointe PDF
        pdf_attachment = MIMEApplication(pdf_content, _subtype="pdf")
        pdf_attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=pdf_filename,
        )
        msg.attach(pdf_attachment)

        return msg

    def _generate_text_body(self, data: InvoiceEmailData) -> str:
        """Génère le corps du message en texte brut"""
        lines = [
            f"Bonjour {data.to_name},",
            "",
            f"Veuillez trouver ci-joint la facture {data.invoice_number} "
            f"du {data.invoice_date}.",
            "",
            f"Montant : {data.amount_ttc} {data.currency}",
        ]

        if data.due_date:
            lines.append(f"Date d'échéance : {data.due_date}")

        if data.payment_link:
            lines.extend([
                "",
                "Pour régler cette facture en ligne, cliquez sur le lien suivant :",
                data.payment_link,
            ])

        if data.custom_message:
            lines.extend(["", data.custom_message])

        lines.extend([
            "",
            "Cordialement,",
            data.company_name,
        ])

        if data.company_email:
            lines.append(data.company_email)

        return "\n".join(lines)

    def _generate_html_body(self, data: InvoiceEmailData) -> str:
        """Génère le corps du message en HTML"""
        payment_button = ""
        if data.payment_link:
            payment_button = f"""
            <tr>
                <td style="padding: 30px 0; text-align: center;">
                    <a href="{data.payment_link}"
                       style="background-color: #4F46E5; color: white; padding: 14px 28px;
                              text-decoration: none; border-radius: 8px; font-weight: 600;
                              display: inline-block;">
                        Payer maintenant
                    </a>
                </td>
            </tr>
            """

        due_date_row = ""
        if data.due_date:
            due_date_row = f"""
            <tr>
                <td style="color: #6B7280; padding: 4px 0;">Échéance</td>
                <td style="text-align: right; font-weight: 500;">{data.due_date}</td>
            </tr>
            """

        custom_message_section = ""
        if data.custom_message:
            custom_message_section = f"""
            <tr>
                <td style="padding: 20px 0; color: #374151; font-style: italic;">
                    {data.custom_message}
                </td>
            </tr>
            """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #F3F4F6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F3F4F6; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); padding: 30px; border-radius: 12px 12px 0 0;">
                            <h1 style="margin: 0; color: white; font-size: 24px; font-weight: 600;">
                                {data.company_name}
                            </h1>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <p style="margin: 0 0 20px; color: #374151; font-size: 16px;">
                                Bonjour {data.to_name},
                            </p>

                            <p style="margin: 0 0 30px; color: #374151; font-size: 16px;">
                                Veuillez trouver ci-joint votre facture.
                            </p>

                            <!-- Invoice Card -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F9FAFB; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                                <tr>
                                    <td>
                                        <table width="100%" cellpadding="8" cellspacing="0">
                                            <tr>
                                                <td style="color: #6B7280; padding: 4px 0;">Numéro</td>
                                                <td style="text-align: right; font-weight: 600; color: #111827;">{data.invoice_number}</td>
                                            </tr>
                                            <tr>
                                                <td style="color: #6B7280; padding: 4px 0;">Date</td>
                                                <td style="text-align: right; font-weight: 500;">{data.invoice_date}</td>
                                            </tr>
                                            {due_date_row}
                                            <tr style="border-top: 1px solid #E5E7EB;">
                                                <td style="color: #111827; padding: 12px 0 4px; font-weight: 600;">Montant TTC</td>
                                                <td style="text-align: right; font-size: 20px; font-weight: 700; color: #4F46E5;">{data.amount_ttc} {data.currency}</td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            {custom_message_section}

                            {payment_button}

                            <p style="margin: 30px 0 0; color: #6B7280; font-size: 14px;">
                                La facture est également disponible en pièce jointe au format PDF.
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 30px; background-color: #F9FAFB; border-radius: 0 0 12px 12px; border-top: 1px solid #E5E7EB;">
                            <p style="margin: 0; color: #6B7280; font-size: 12px; text-align: center;">
                                {data.company_name}<br>
                                {data.company_email if data.company_email else ""}
                            </p>
                        </td>
                    </tr>
                </table>

                <!-- Legal footer -->
                <table width="600" cellpadding="0" cellspacing="0">
                    <tr>
                        <td style="padding: 20px; text-align: center; color: #9CA3AF; font-size: 11px;">
                            Cette facture a été générée au format Factur-X conforme à la norme EN16931.<br>
                            Archivage légal garanti 10 ans.
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    def _send_smtp(self, msg: MIMEMultipart, to_email: str) -> str:
        """Envoie via SMTP et retourne le message ID"""
        context = ssl.create_default_context()

        if self._settings.use_tls:
            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port) as server:
                server.starttls(context=context)
                server.login(self._settings.smtp_user, self._settings.smtp_password)
                server.sendmail(
                    self._settings.from_email,
                    to_email,
                    msg.as_string(),
                )
        else:
            with smtplib.SMTP_SSL(
                self._settings.smtp_host, self._settings.smtp_port, context=context
            ) as server:
                server.login(self._settings.smtp_user, self._settings.smtp_password)
                server.sendmail(
                    self._settings.from_email,
                    to_email,
                    msg.as_string(),
                )

        return msg.get("Message-ID", "")


# === SINGLETON ===

_email_sender: Optional[InvoiceEmailSender] = None


def get_email_sender() -> InvoiceEmailSender:
    """Retourne l'instance singleton"""
    global _email_sender
    if _email_sender is None:
        _email_sender = InvoiceEmailSender()
    return _email_sender
