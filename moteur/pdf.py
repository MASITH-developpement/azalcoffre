# =============================================================================
# AZALPLUS - PDF Generator (Style Professionnel)
# =============================================================================
"""
Generateur de PDF pour Devis et Factures.
Style inspiré des documents professionnels (AXA, etc.)
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Generator
from uuid import UUID as PyUUID
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO
import yaml
import structlog

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image, PageBreak, Frame, PageTemplate
)
from reportlab.platypus.doctemplate import BaseDocTemplate
import base64
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .db import Database
from .config import settings

logger = structlog.get_logger()


# =============================================================================
# Configuration du theme documents
# =============================================================================
class DocumentTheme:
    """Charge la configuration des documents depuis theme.yml."""

    _config: Dict = {}
    _theme_path = Path("config/theme.yml")
    _last_modified: float = 0

    @classmethod
    def load(cls) -> Dict:
        """Charge/recharge la configuration si modifiee."""
        if cls._theme_path.exists():
            current_mtime = cls._theme_path.stat().st_mtime
            if current_mtime > cls._last_modified or not cls._config:
                with open(cls._theme_path, 'r', encoding='utf-8') as f:
                    theme = yaml.safe_load(f)
                    cls._config = theme.get("documents", {})
                    cls._last_modified = current_mtime
                    logger.debug("document_theme_loaded")
        return cls._config

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Recupere une valeur de configuration."""
        config = cls.load()
        return config.get(key, default)


def hex_to_color(hex_color: str) -> colors.Color:
    """Convertit une couleur hex en couleur ReportLab."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return colors.Color(r, g, b)


# =============================================================================
# PDFGenerator Class - Style Professionnel
# =============================================================================
class PDFGenerator:
    """Generateur de PDF style professionnel."""

    def __init__(self, tenant_id: PyUUID):
        self.tenant_id = tenant_id
        self.theme = DocumentTheme.load()

        # Couleurs
        self.primary_color = hex_to_color(self.theme.get("couleur", "#3454D1"))
        self.text_color = hex_to_color("#1e293b")
        self.gray_color = hex_to_color("#64748b")
        self.light_gray = hex_to_color("#f1f5f9")
        self.border_color = hex_to_color("#e2e8f0")
        self.header_bg = hex_to_color("#f8fafc")

        # Données entreprise (chargées une fois)
        self.tenant_data = None

        self._setup_styles()

    def _setup_styles(self):
        """Configure les styles de paragraphe."""
        self.styles = getSampleStyleSheet()

        # Nom entreprise (header)
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            fontName='Helvetica-Bold',
            fontSize=14,
            textColor=self.primary_color,
            spaceAfter=2
        ))

        # Slogan/description entreprise
        self.styles.add(ParagraphStyle(
            name='CompanySlogan',
            fontName='Helvetica',
            fontSize=9,
            textColor=self.gray_color,
            leading=12
        ))

        # Titre document (DEVIS / FACTURE)
        self.styles.add(ParagraphStyle(
            name='DocTitle',
            fontName='Helvetica-Bold',
            fontSize=18,
            textColor=self.text_color,
            alignment=TA_LEFT
        ))

        # Labels (Référence, Date, etc.)
        self.styles.add(ParagraphStyle(
            name='Label',
            fontName='Helvetica',
            fontSize=9,
            textColor=self.gray_color,
        ))

        # Valeurs
        self.styles.add(ParagraphStyle(
            name='Value',
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=self.text_color,
        ))

        # Adresse client
        self.styles.add(ParagraphStyle(
            name='ClientAddress',
            fontName='Helvetica',
            fontSize=10,
            textColor=self.text_color,
            leading=14
        ))

        # Titre de section (1ere intervention, etc.)
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=self.primary_color,
            spaceBefore=8,
            spaceAfter=4
        ))

        # Notes
        self.styles.add(ParagraphStyle(
            name='Notes',
            fontName='Helvetica',
            fontSize=8,
            textColor=self.gray_color,
            leading=11
        ))

        # Footer
        self.styles.add(ParagraphStyle(
            name='Footer',
            fontName='Helvetica',
            fontSize=8,
            textColor=self.gray_color,
            alignment=TA_CENTER,
            leading=11
        ))

    def _format_date(self, d) -> str:
        """Formate une date."""
        if not d:
            return ""
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d.replace('Z', '+00:00'))
            except ValueError:
                return d
        if isinstance(d, (datetime, date)):
            return d.strftime("%d/%m/%Y")
        return str(d)

    def _format_money(self, amount, with_symbol: bool = False) -> str:
        """Formate un montant en euros."""
        try:
            value = Decimal(str(amount or 0))
            formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
            if with_symbol:
                return f"{formatted} €"
            return formatted
        except (ValueError, TypeError):
            return "0,00"

    def _get_tenant_info(self) -> Dict:
        """Recupere les informations de l'entreprise."""
        if self.tenant_data:
            return self.tenant_data

        try:
            from sqlalchemy import text
            with Database.get_session() as session:
                result = session.execute(
                    text("SELECT * FROM azalplus.entreprise WHERE tenant_id = :tenant_id LIMIT 1"),
                    {"tenant_id": str(self.tenant_id)}
                )
                row = result.fetchone()
                if row:
                    ent = dict(row._mapping)
                    self.tenant_data = {
                        "raison_sociale": ent.get("raison_sociale") or ent.get("nom", ""),
                        "nom": ent.get("nom", ""),
                        "slogan": ent.get("texte_pied_facture") or ent.get("slogan") or "",
                        "adresse": ent.get("adresse", ""),
                        "complement_adresse": ent.get("adresse_complement", ""),
                        "code_postal": ent.get("code_postal", ""),
                        "ville": ent.get("ville", ""),
                        "pays": ent.get("pays", "France"),
                        "telephone": ent.get("telephone", ""),
                        "email": ent.get("email", ""),
                        "site_web": ent.get("site_web", ""),
                        "siret": ent.get("siret", ""),
                        "tva_intra": ent.get("tva_intracommunautaire", ""),
                        "iban": ent.get("iban", ""),
                        "bic": ent.get("bic", ""),
                        "logo_filename": ent.get("logo_filename", ""),
                        "logo_url": ent.get("logo_url", ""),
                        "regime_tva": ent.get("regime_tva", ""),
                        "mentions_legales": ent.get("mentions_legales", ""),
                    }
                    return self.tenant_data
        except Exception as e:
            logger.warning("entreprise_not_found", error=str(e))

        # Valeurs par défaut
        self.tenant_data = {
            "raison_sociale": "Mon Entreprise",
            "nom": "Mon Entreprise",
            "slogan": "",
            "adresse": "",
            "code_postal": "",
            "ville": "",
            "pays": "France",
            "telephone": "",
            "email": "",
            "site_web": "",
            "siret": "",
            "tva_intra": "",
            "iban": "",
            "bic": "",
        }
        return self.tenant_data

    def _get_client_info(self, client_id) -> Dict:
        """Recupere les informations du client et normalise les colonnes."""
        if not client_id:
            return {}

        try:
            from sqlalchemy import text
            uuid_str = str(client_id)

            with Database.get_session() as session:
                # Essayer clients (schema moderne avec colonnes anglaises)
                result = session.execute(
                    text("SELECT * FROM azalplus.clients WHERE id = :id AND tenant_id = :tenant_id"),
                    {"id": uuid_str, "tenant_id": str(self.tenant_id)}
                )
                row = result.fetchone()
                if row:
                    d = dict(row._mapping)
                    # Normaliser vers le format attendu (FR)
                    return {
                        "raison_sociale": d.get("legal_name") or d.get("name") or "",
                        "nom": d.get("name") or d.get("contact_name") or "",
                        "prenom": "",
                        "code_client": d.get("code") or "",  # Référence client
                        "adresse": d.get("address_line1") or d.get("adresse1") or "",
                        "adresse2": d.get("address_line2") or d.get("adresse2") or "",
                        "code_postal": d.get("postal_code") or d.get("cp") or "",
                        "ville": d.get("city") or d.get("ville") or "",
                        "pays": d.get("country_code") or d.get("pays") or "France",
                        "email": d.get("email") or "",
                        "telephone": d.get("phone") or d.get("mobile") or "",
                    }

                # Essayer donneur_ordre (schema FR)
                result = session.execute(
                    text("SELECT * FROM azalplus.donneur_ordre WHERE id = :id AND tenant_id = :tenant_id"),
                    {"id": uuid_str, "tenant_id": str(self.tenant_id)}
                )
                row = result.fetchone()
                if row:
                    d = dict(row._mapping)
                    return {
                        "raison_sociale": d.get("raison_sociale") or d.get("nom", ""),
                        "nom": d.get("nom", ""),
                        "prenom": d.get("prenom", ""),
                        "adresse": d.get("adresse", ""),
                        "code_postal": d.get("code_postal", ""),
                        "ville": d.get("ville", ""),
                        "pays": d.get("pays", "France"),
                    }
        except Exception as e:
            logger.debug("client_lookup_failed", error=str(e), client_id=client_id)

        return {}

    def _get_user_name(self, user_id) -> str:
        """Recupere le nom d'un utilisateur."""
        if not user_id:
            return ""
        try:
            from sqlalchemy import text
            with Database.get_session() as session:
                result = session.execute(
                    text("SELECT prenom, nom FROM azalplus.utilisateurs WHERE id = :id"),
                    {"id": str(user_id)}
                )
                row = result.fetchone()
                if row:
                    return f"{row[0] or ''} {row[1] or ''}".strip()
        except:
            pass
        return ""

    def _build_header(self, doc_type: str, doc_data: Dict, tenant_data: Dict, client_data: Dict) -> List:
        """Construit l'en-tete style Odoo."""
        elements = []

        # === LIGNE 1: ENTREPRISE (gauche) + DOCUMENT TITLE (droite) ===
        company_name = tenant_data.get("nom") or tenant_data.get("raison_sociale", "Mon Entreprise")
        company_addr = []
        if tenant_data.get("adresse"):
            company_addr.append(tenant_data.get("adresse"))
        cp_ville = f"{tenant_data.get('code_postal', '')} {tenant_data.get('ville', '')}".strip()
        if cp_ville:
            company_addr.append(cp_ville)
        if tenant_data.get("telephone"):
            company_addr.append(f"Tél: {tenant_data.get('telephone')}")
        if tenant_data.get("email"):
            company_addr.append(tenant_data.get("email"))

        company_text = f"<b><font size='14' color='#{self.primary_color.hexval()[2:]}'>{company_name}</font></b>"
        if company_addr:
            company_text += "<br/>" + "<br/>".join(company_addr)

        # Titre document
        doc_titles = {"devis": "Devis", "facture": "Facture"}
        doc_title = doc_titles.get(doc_type, "Document")
        numero = doc_data.get("numero") or doc_data.get("number", "")

        header_data = [[
            Paragraph(company_text, self.styles['ClientAddress']),
            Paragraph(f"<font size='22' color='#{self.primary_color.hexval()[2:]}'><b>{doc_title}</b></font>",
                     ParagraphStyle('BigTitle', parent=self.styles['DocTitle'], alignment=TA_RIGHT, fontSize=22))
        ]]

        header_table = Table(header_data, colWidths=[100*mm, 80*mm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 8*mm))

        # === LIGNE 2: CLIENT (gauche, encadré) + INFOS DOC (droite, encadré) ===
        # Client
        client_name = client_data.get("raison_sociale") or \
                     f"{client_data.get('prenom', '')} {client_data.get('nom', '')}".strip() or \
                     "Client"

        billing_addr = doc_data.get("billing_address") or doc_data.get("adresse_facturation") or ""
        if billing_addr and isinstance(billing_addr, str):
            client_address = billing_addr.replace("\n", "<br/>")
        else:
            client_address_lines = []
            if client_data.get("adresse"):
                client_address_lines.append(client_data.get("adresse"))
            cp_ville = f"{client_data.get('code_postal', '')} {client_data.get('ville', '')}".strip()
            if cp_ville:
                client_address_lines.append(cp_ville)
            client_address = "<br/>".join(client_address_lines)

        client_box_content = f"<b>{client_name}</b>"
        if client_address:
            client_box_content += f"<br/>{client_address}"

        # Box client avec bordure
        client_box = Table([[Paragraph(client_box_content, self.styles['ClientAddress'])]], colWidths=[85*mm])
        client_box.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, self.border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ]))

        # Infos document dans un box coloré
        date_doc = self._format_date(doc_data.get("date"))
        if doc_type == "devis":
            date_fin = self._format_date(doc_data.get("validite") or doc_data.get("validity_date"))
            date_fin_label = "Date d'expiration"
        else:
            date_fin = self._format_date(doc_data.get("echeance") or doc_data.get("due_date"))
            date_fin_label = "Date d'échéance"

        vendeur = self._get_user_name(doc_data.get("assigned_to") or doc_data.get("created_by"))
        # Référence client: priorité à la référence du document, sinon code client
        ref_client = doc_data.get("reference_client") or doc_data.get("reference") or client_data.get("code_client") or ""

        info_data = [
            [Paragraph(f"<b>N° {doc_title}</b>", self.styles['Label']),
             Paragraph(f"<b>{numero}</b>", self.styles['Value'])],
        ]
        # Référence client (si présente)
        if ref_client:
            info_data.append([
                Paragraph("<b>Réf. client</b>", self.styles['Label']),
                Paragraph(ref_client, self.styles['Value'])
            ])
        info_data.append([
            Paragraph(f"<b>Date</b>", self.styles['Label']),
            Paragraph(date_doc, self.styles['Value'])
        ])
        if date_fin:
            info_data.append([
                Paragraph(f"<b>{date_fin_label}</b>", self.styles['Label']),
                Paragraph(date_fin, self.styles['Value'])
            ])
        if vendeur:
            info_data.append([
                Paragraph("<b>Commercial</b>", self.styles['Label']),
                Paragraph(vendeur, self.styles['Value'])
            ])

        info_table = Table(info_data, colWidths=[40*mm, 45*mm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.header_bg),
            ('BOX', (0, 0), (-1, -1), 1, self.border_color),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, self.border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))

        # Assemblage
        row2_data = [[client_box, info_table]]
        row2_table = Table(row2_data, colWidths=[95*mm, 85*mm])
        row2_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(row2_table)
        elements.append(Spacer(1, 10*mm))

        return elements

    def _build_lines_table(self, doc_data: Dict) -> List:
        """Construit le tableau des lignes avec groupes/sections."""
        elements = []

        lignes = doc_data.get("lignes") or doc_data.get("lines") or []
        if isinstance(lignes, str):
            import json
            try:
                lignes = json.loads(lignes)
            except:
                lignes = []

        if not lignes:
            return elements

        # En-têtes du tableau
        header = ['Description', 'Quantité', 'Prix\nunitaire', 'Taxes', 'Montant']
        col_widths = [85*mm, 20*mm, 25*mm, 20*mm, 25*mm]

        table_data = [header]

        # Parcourir les lignes dans l'ordre et grouper par section pour les sous-totaux
        current_section = None
        section_total = Decimal("0")
        section_rows_start = len(table_data)  # Pour savoir où commence la section courante

        for i, ligne in enumerate(lignes):
            line_type = ligne.get("line_type", "product")

            # Ligne de type section (titre)
            if line_type == "section":
                # Afficher le sous-total de la section précédente si elle existe
                if current_section and section_total > 0:
                    table_data.append([
                        Paragraph(f"<b>Sous-total {current_section}</b>", self.styles['SectionTitle']),
                        '', '', '',
                        Paragraph(f"<b>{self._format_money(section_total)} €</b>", self.styles['Value'])
                    ])

                # Nouvelle section
                current_section = ligne.get("description", "Section")
                section_total = Decimal("0")

                # Afficher le titre de section (ligne colorée)
                table_data.append([
                    Paragraph(f"<b>{current_section}</b>", self.styles['SectionTitle']),
                    '', '', '', ''
                ])
                continue

            # Ligne de type note (commentaire)
            elif line_type == "note":
                note_text = ligne.get("description", "")
                if note_text:
                    table_data.append([
                        Paragraph(f"<i>{note_text}</i>", self.styles['Notes']),
                        '', '', '', ''
                    ])
                continue

            # Ligne produit standard
            description = ligne.get("description") or ligne.get("product_name", "")
            code = ligne.get("product_code") or ligne.get("code", "")
            if code:
                description = f"[{code}] {description}"

            quantite = ligne.get("quantite") or ligne.get("quantity", 1)
            unite = ligne.get("unite") or ligne.get("unit", "Unité(s)")
            qte_str = f"{self._format_money(quantite)}\n{unite}"

            prix_unitaire = Decimal(str(ligne.get("prix_unitaire") or ligne.get("unit_price", 0)))
            prix_str = f"{self._format_money(prix_unitaire)}"

            taux_tva = ligne.get("taux_tva") or ligne.get("tax_rate", 0)
            tva_str = f"TVA {int(taux_tva)}%"

            # Calcul du montant
            remise_pct = Decimal(str(ligne.get("remise_percent") or ligne.get("discount_percent", 0)))
            montant = prix_unitaire * Decimal(str(quantite)) * (1 - remise_pct / 100)
            section_total += montant
            montant_str = f"{self._format_money(montant)} €"

            table_data.append([
                Paragraph(description, self.styles['Notes']),
                Paragraph(qte_str, self.styles['Notes']),
                Paragraph(prix_str, self.styles['Notes']),
                Paragraph(tva_str, self.styles['Notes']),
                Paragraph(f"<b>{montant_str}</b>", self.styles['Value'])
            ])

        # Afficher le sous-total de la dernière section si elle existe
        if current_section and section_total > 0:
            table_data.append([
                Paragraph(f"<b>Sous-total {current_section}</b>", self.styles['SectionTitle']),
                '', '', '',
                Paragraph(f"<b>{self._format_money(section_total)} €</b>", self.styles['Value'])
            ])

        # Créer le tableau
        table = Table(table_data, colWidths=col_widths)

        # Style du tableau - Style Odoo avec header coloré
        style_commands = [
            # En-tête avec couleur primaire (style Odoo)
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),     # Description alignée à gauche
            ('ALIGN', (1, 0), (-1, 0), 'CENTER'),  # Reste centré
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

            # Corps
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),    # Description
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Quantité
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),   # Prix unitaire
            ('ALIGN', (3, 1), (3, -1), 'CENTER'),  # Taxes
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),   # Montant
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),

            # Padding
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),

            # Bordures style Odoo
            ('BOX', (0, 0), (-1, -1), 1, self.border_color),
            ('LINEBELOW', (0, 0), (-1, 0), 2, self.primary_color),
            ('LINEBELOW', (0, 1), (-1, -2), 0.5, self.border_color),
        ]

        # Lignes alternées (style Odoo)
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_commands.append(('BACKGROUND', (0, i), (-1, i), self.header_bg))

        table.setStyle(TableStyle(style_commands))
        elements.append(table)
        elements.append(Spacer(1, 8*mm))

        return elements

    def _build_totals(self, doc_data: Dict) -> List:
        """Construit la section des totaux style Odoo (encadré)."""
        elements = []

        total_ht = Decimal(str(doc_data.get("total_ht") or doc_data.get("subtotal", 0) or 0))
        total_tva = Decimal(str(doc_data.get("total_tva") or doc_data.get("tax_amount", 0) or 0))
        total_ttc = Decimal(str(doc_data.get("total_ttc") or doc_data.get("total", 0) or 0))

        # Déterminer le taux TVA principal
        taux_tva = 20
        lignes = doc_data.get("lignes") or doc_data.get("lines") or []
        if lignes and isinstance(lignes, list) and len(lignes) > 0:
            if isinstance(lignes[0], dict):
                taux_tva = lignes[0].get("taux_tva") or lignes[0].get("tax_rate", 20)

        # Tableau des totaux style Odoo (encadré, aligné à droite)
        totals_data = [
            [Paragraph("Sous-total HT", self.styles['Value']),
             Paragraph(f"{self._format_money(total_ht)} €", self.styles['Value'])],
            [Paragraph(f"TVA ({taux_tva}%)", self.styles['Label']),
             Paragraph(f"{self._format_money(total_tva)} €", self.styles['Value'])],
            [Paragraph("<b>Total TTC</b>", self.styles['Value']),
             Paragraph(f"<b><font size='12'>{self._format_money(total_ttc)} €</font></b>", self.styles['Value'])],
        ]

        totals_table = Table(totals_data, colWidths=[45*mm, 40*mm])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            # Ligne de séparation avant Total
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, self.primary_color),
            # Fond coloré pour la ligne Total
            ('BACKGROUND', (0, -1), (-1, -1), self.header_bg),
            # Bordure du box
            ('BOX', (0, 0), (-1, -1), 1, self.border_color),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, self.border_color),
        ]))

        # Aligner à droite
        outer_data = [['', totals_table]]
        outer_table = Table(outer_data, colWidths=[90*mm, 85*mm])
        elements.append(outer_table)

        # === MENTIONS LEGALES TVA ===
        elements.append(Spacer(1, 4*mm))

        # Mention TVA selon le taux ou le régime de l'entreprise
        regime_tva = ""
        if self.tenant_data:
            regime_tva = self.tenant_data.get("regime_tva", "")

        if taux_tva == 0 or regime_tva in ["EXONERE", "FRANCHISE"]:
            # TVA non applicable
            tva_mention = doc_data.get("mention_tva") or ""
            if not tva_mention:
                if regime_tva == "EXONERE":
                    tva_mention = "TVA non applicable, art. 293 B du CGI"
                elif regime_tva == "FRANCHISE":
                    tva_mention = "TVA non applicable, art. 293 B du CGI - Franchise en base"
                else:
                    tva_mention = "TVA non applicable, art. 293 B du CGI"
            elements.append(Paragraph(
                f"<i>{tva_mention}</i>",
                self.styles['Notes']
            ))

        # === CONDITIONS DE PAIEMENT ===
        payment_terms = doc_data.get("payment_terms") or doc_data.get("conditions_paiement") or ""
        payment_text = doc_data.get("payment_terms_text") or ""

        # Mapper les codes vers texte lisible
        terms_mapping = {
            "IMMEDIATE": "Paiement comptant",
            "COMPTANT": "Paiement comptant",
            "15_DAYS": "Paiement à 15 jours",
            "30_DAYS": "Paiement à 30 jours",
            "30JOURS": "Paiement à 30 jours",
            "45_DAYS": "Paiement à 45 jours",
            "60_DAYS": "Paiement à 60 jours",
            "END_OF_MONTH": "Paiement fin de mois",
        }

        if payment_terms or payment_text:
            terms_display = payment_text or terms_mapping.get(str(payment_terms).upper(), str(payment_terms))
            if terms_display:
                elements.append(Paragraph(
                    f"<b>Conditions de paiement :</b> {terms_display}",
                    self.styles['Notes']
                ))

        # === NOTES / CONDITIONS GENERALES ===
        notes = doc_data.get("notes") or ""
        conditions = doc_data.get("conditions") or doc_data.get("terms") or ""

        if notes:
            elements.append(Spacer(1, 2*mm))
            elements.append(Paragraph(notes, self.styles['Notes']))

        if conditions:
            elements.append(Spacer(1, 2*mm))
            elements.append(Paragraph(conditions, self.styles['Notes']))

        return elements

    def _build_options_section(self, doc_data: Dict) -> List:
        """Construit la section Options (produits optionnels)."""
        elements = []

        # Récupérer les options depuis custom_fields ou lignes optionnelles
        custom = doc_data.get("custom_fields") or {}
        options = custom.get("produits_optionnels") or []

        if not options:
            # Chercher les lignes marquées comme optionnelles
            lignes = doc_data.get("lignes") or doc_data.get("lines") or []
            for ligne in lignes:
                if isinstance(ligne, dict) and ligne.get("optional"):
                    options.append(ligne)

        if not options:
            return elements

        elements.append(Spacer(1, 6*mm))
        elements.append(Paragraph("<b>Options</b>", self.styles['SectionTitle']))

        # En-têtes
        header = ['Description', 'Prix unitaire']
        table_data = [header]

        for opt in options:
            if isinstance(opt, dict):
                desc = opt.get("description") or opt.get("product_name", "")
                prix = opt.get("prix_unitaire") or opt.get("unit_price", 0)
            else:
                continue

            table_data.append([
                Paragraph(desc, self.styles['Notes']),
                Paragraph(f"{self._format_money(prix)} €", self.styles['Value'])
            ])

        table = Table(table_data, colWidths=[130*mm, 45*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.light_gray),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, self.border_color),
        ]))

        elements.append(table)
        return elements

    def _get_footer_text(self, tenant_data: Dict) -> str:
        """Prépare le texte du pied de page."""
        nom = tenant_data.get("nom") or tenant_data.get("raison_sociale", "")
        tel = tenant_data.get("telephone", "")
        email = tenant_data.get("email", "")
        site = tenant_data.get("site_web", "")
        siret = tenant_data.get("siret", "")
        iban = tenant_data.get("iban", "")
        tva_intra = tenant_data.get("tva_intra", "")

        # Adresse sur une ligne
        addr_parts = []
        if tenant_data.get("adresse"):
            addr_parts.append(tenant_data.get("adresse"))
        cp_ville = f"{tenant_data.get('code_postal', '')} {tenant_data.get('ville', '')}".strip()
        if cp_ville:
            addr_parts.append(cp_ville)
        adresse_line = " | ".join(addr_parts) if addr_parts else ""

        # Contact sur une ligne
        contact_parts = []
        if tel:
            contact_parts.append(f"Tél: {tel}")
        if email:
            contact_parts.append(email)
        if site:
            contact_parts.append(site)
        contact_line = " | ".join(contact_parts) if contact_parts else ""

        # Legal sur une ligne
        legal_parts = []
        if siret:
            siret_fmt = " ".join([siret[i:i+3] for i in range(0, len(siret), 3)])
            legal_parts.append(f"SIRET: {siret_fmt}")
        if tva_intra:
            legal_parts.append(f"TVA: {tva_intra}")
        if iban:
            iban_fmt = " ".join([iban[i:i+4] for i in range(0, len(iban), 4)])
            legal_parts.append(f"IBAN: {iban_fmt}")
        legal_line = " | ".join(legal_parts) if legal_parts else ""

        # Assemblage
        lines = []
        if nom:
            lines.append(nom)
        if adresse_line:
            lines.append(adresse_line)
        if contact_line:
            lines.append(contact_line)
        if legal_line:
            lines.append(legal_line)

        return lines

    def _generate_pdf(self, doc_type: str, doc_data: Dict) -> bytes:
        """Génère le PDF complet avec footer en bas de page."""
        tenant_data = self._get_tenant_info()
        client_data = self._get_client_info(doc_data.get("client") or doc_data.get("customer_id"))

        # Fallback pour adresse client depuis billing_address
        if not client_data.get("adresse") and doc_data.get("billing_address"):
            lines = str(doc_data.get("billing_address", "")).split("\n")
            client_data["adresse"] = lines[0] if len(lines) > 0 else ""
            if len(lines) > 1:
                parts = lines[1].split()
                client_data["code_postal"] = parts[0] if parts else ""
                client_data["ville"] = " ".join(parts[1:]) if len(parts) > 1 else ""

        buffer = BytesIO()

        # Marges - plus d'espace en bas pour le footer
        margin = 15 * mm
        footer_height = 30 * mm  # Espace réservé pour le footer

        # Préparer les données du footer
        footer_lines = self._get_footer_text(tenant_data)
        primary_hex = self.primary_color.hexval()[2:] if hasattr(self.primary_color, 'hexval') else '3454D1'

        # Fonction pour dessiner le footer en bas de chaque page
        def draw_footer(canvas, doc):
            canvas.saveState()
            page_width, page_height = A4

            # Position du footer (en bas)
            footer_y = 12 * mm

            # Ligne de séparation colorée
            canvas.setStrokeColor(self.primary_color)
            canvas.setLineWidth(2)
            canvas.line(margin, footer_y + 22*mm, page_width - margin, footer_y + 22*mm)

            # Texte du footer centré
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(self.gray_color)

            y_pos = footer_y + 18*mm
            for line in footer_lines:
                # Première ligne en gras
                if line == footer_lines[0]:
                    canvas.setFont("Helvetica-Bold", 8)
                else:
                    canvas.setFont("Helvetica", 7)

                text_width = canvas.stringWidth(line, canvas._fontname, canvas._fontsize)
                x_pos = (page_width - text_width) / 2
                canvas.drawString(x_pos, y_pos, line)
                y_pos -= 10

            canvas.restoreState()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=footer_height  # Espace pour le footer
        )

        # Construire les éléments (sans footer, il est dessiné séparément)
        elements = []
        elements.extend(self._build_header(doc_type, doc_data, tenant_data, client_data))
        elements.extend(self._build_lines_table(doc_data))
        elements.extend(self._build_totals(doc_data))
        elements.extend(self._build_options_section(doc_data))

        logger.debug("pdf_elements_count",
                     total_elements=len(elements),
                     doc_type=doc_type,
                     numero=doc_data.get("numero"),
                     lignes_count=len(doc_data.get("lignes") or []))

        # Build avec callback pour le footer
        doc.build(elements, onFirstPage=draw_footer, onLaterPages=draw_footer)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.debug("pdf_generated_size", size=len(pdf_bytes))

        return pdf_bytes

    def generate_devis_pdf(self, devis_data: Dict) -> bytes:
        """Génère le PDF d'un devis."""
        lignes = devis_data.get("lignes") or [] if devis_data else []
        logger.debug("generate_devis_pdf_input",
                     keys=list(devis_data.keys()) if devis_data else [],
                     numero=devis_data.get("numero"),
                     client=devis_data.get("client") or devis_data.get("customer_id"),
                     lignes_count=len(lignes))

        pdf_bytes = self._generate_pdf("devis", devis_data)

        logger.info("devis_pdf_generated",
                    numero=devis_data.get("numero"),
                    tenant_id=str(self.tenant_id))

        return pdf_bytes

    def generate_facture_pdf(self, facture_data: Dict) -> bytes:
        """Génère le PDF d'une facture."""
        lignes = facture_data.get("lignes") or [] if facture_data else []
        logger.debug("generate_facture_pdf_input",
                     keys=list(facture_data.keys()) if facture_data else [],
                     numero=facture_data.get("numero"),
                     client=facture_data.get("client") or facture_data.get("customer_id"),
                     lignes_count=len(lignes))

        pdf_bytes = self._generate_pdf("facture", facture_data)

        logger.info("facture_pdf_generated",
                    numero=facture_data.get("numero"),
                    tenant_id=str(self.tenant_id))

        return pdf_bytes
