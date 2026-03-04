# =============================================================================
# AZALPLUS - PDF Generator
# =============================================================================
"""
Generateur de PDF pour Devis et Factures.
Utilise ReportLab pour generer des PDF.
Le style est configure dans config/theme.yml (section 'documents').
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import UUID as PyUUID
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO
import yaml
import structlog

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image
)
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
# PDFGenerator Class
# =============================================================================
class PDFGenerator:
    """Generateur de PDF pour documents commerciaux."""

    def __init__(self, tenant_id: PyUUID):
        """
        Initialise le generateur.

        Args:
            tenant_id: UUID du tenant (isolation multi-tenant)
        """
        self.tenant_id = tenant_id
        self.theme = DocumentTheme.load()

        # Couleurs depuis le theme
        self.primary_color = hex_to_color(self.theme.get("couleur", "#2563EB"))
        self.text_color = hex_to_color("#1e293b")
        self.gray_color = hex_to_color("#64748b")
        self.light_gray = hex_to_color("#f8fafc")
        self.border_color = hex_to_color("#e2e8f0")

        # Styles
        self._setup_styles()

    def _setup_styles(self):
        """Configure les styles de paragraphe."""
        self.styles = getSampleStyleSheet()

        # Style titre entreprise
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=self.primary_color,
            spaceAfter=6
        ))

        # Style details entreprise
        self.styles.add(ParagraphStyle(
            name='CompanyDetails',
            fontName='Helvetica',
            fontSize=9,
            textColor=self.gray_color,
            leading=13
        ))

        # Style type document (DEVIS / FACTURE)
        self.styles.add(ParagraphStyle(
            name='DocType',
            fontName='Helvetica-Bold',
            fontSize=20,
            textColor=self.primary_color,
            alignment=TA_RIGHT
        ))

        # Style numero document
        self.styles.add(ParagraphStyle(
            name='DocNumber',
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=self.text_color,
            alignment=TA_RIGHT
        ))

        # Style date
        self.styles.add(ParagraphStyle(
            name='DocDate',
            fontName='Helvetica',
            fontSize=10,
            textColor=self.gray_color,
            alignment=TA_RIGHT
        ))

        # Style titre section
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=self.gray_color,
            spaceAfter=6,
            spaceBefore=12
        ))

        # Style nom client
        self.styles.add(ParagraphStyle(
            name='ClientName',
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=self.text_color,
            spaceAfter=4
        ))

        # Style details client
        self.styles.add(ParagraphStyle(
            name='ClientDetails',
            fontName='Helvetica',
            fontSize=9,
            textColor=self.gray_color,
            leading=13
        ))

        # Style objet
        self.styles.add(ParagraphStyle(
            name='Object',
            fontName='Helvetica',
            fontSize=11,
            textColor=self.text_color
        ))

        # Style notes
        self.styles.add(ParagraphStyle(
            name='Notes',
            fontName='Helvetica',
            fontSize=9,
            textColor=self.gray_color,
            leading=12
        ))

    def _format_date(self, d: Any) -> str:
        """Formate une date pour l'affichage."""
        if d is None:
            return ""
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d.replace('Z', '+00:00'))
            except ValueError:
                return d
        if isinstance(d, datetime):
            return d.strftime("%d/%m/%Y")
        if isinstance(d, date):
            return d.strftime("%d/%m/%Y")
        return str(d)

    def _format_money(self, amount: Any) -> str:
        """Formate un montant monetaire."""
        if amount is None:
            return "0,00"
        try:
            value = Decimal(str(amount))
            # Format francais: espace pour milliers, virgule pour decimales
            formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
            return formatted
        except (ValueError, TypeError):
            return "0,00"

    def _get_client_info(self, client_id: Optional[str]) -> Dict:
        """Recupere les informations du client."""
        if not client_id:
            return {}

        client = Database.get_by_id("clients", self.tenant_id, PyUUID(client_id))
        return client or {}

    def _get_tenant_info(self) -> Dict:
        """Recupere les informations de l'entreprise (tenant) depuis la base."""
        # Recuperer les parametres entreprise du tenant
        try:
            entreprises = Database.query(
                "entreprise",
                self.tenant_id,
                limit=1
            )

            if entreprises and len(entreprises) > 0:
                ent = entreprises[0]
                return {
                    "raison_sociale": ent.get("raison_sociale") or ent.get("nom", ""),
                    "nom": ent.get("nom", ""),
                    "adresse": ent.get("adresse", ""),
                    "code_postal": ent.get("code_postal", ""),
                    "ville": ent.get("ville", ""),
                    "pays": ent.get("pays", ""),
                    "telephone": ent.get("telephone", ""),
                    "email": ent.get("email", ""),
                    "siret": ent.get("siret", ""),
                    "siren": ent.get("siren", ""),
                    "tva_intra": ent.get("tva_intracommunautaire", ""),
                    "rcs": ent.get("rcs", ""),
                    "capital_social": ent.get("capital_social", ""),
                    "forme_juridique": ent.get("forme_juridique", ""),
                    "site_web": ent.get("site_web", ""),
                    "logo_url": ent.get("logo_url", ""),
                    "logo_filename": ent.get("logo_filename", ""),
                    "iban": ent.get("iban", ""),
                    "bic": ent.get("bic", ""),
                    "banque": ent.get("banque", ""),
                    "titulaire_compte": ent.get("titulaire_compte", ""),
                    "mentions_legales": ent.get("mentions_legales", ""),
                    "mention_facture": ent.get("mention_facture", ""),
                    "mention_devis": ent.get("mention_devis", ""),
                    "texte_pied_facture": ent.get("texte_pied_facture", ""),
                    "conditions_generales_vente": ent.get("conditions_generales_vente", ""),
                }
        except Exception as e:
            logger.warning("entreprise_not_found", error=str(e))

        # Valeurs par defaut si aucune configuration
        return {
            "raison_sociale": "Mon Entreprise",
            "nom": "Mon Entreprise",
            "adresse": "",
            "code_postal": "",
            "ville": "",
            "pays": "France",
            "telephone": "",
            "email": "",
            "siret": "",
            "siren": "",
            "tva_intra": "",
            "rcs": "",
            "capital_social": "",
            "forme_juridique": "",
            "site_web": "",
            "logo_url": "",
            "logo_filename": "",
            "iban": "",
            "bic": "",
            "banque": "",
            "titulaire_compte": "",
            "mentions_legales": "",
            "mention_facture": "",
            "mention_devis": "",
            "texte_pied_facture": "",
            "conditions_generales_vente": "",
        }

    def _build_header(self, doc_type: str, doc_data: Dict, tenant_data: Dict) -> List:
        """Construit l'en-tete du document."""
        elements = []

        # Informations entreprise (gauche)
        company_name = tenant_data.get("raison_sociale", "")
        company_address = tenant_data.get("adresse", "")
        company_cp = tenant_data.get("code_postal", "")
        company_ville = tenant_data.get("ville", "")
        company_tel = tenant_data.get("telephone", "")
        company_email = tenant_data.get("email", "")
        company_siret = tenant_data.get("siret", "")
        company_tva = tenant_data.get("tva_intra", "")

        company_details = f"{company_address}<br/>{company_cp} {company_ville}<br/>Tel: {company_tel}<br/>Email: {company_email}<br/>SIRET: {company_siret}<br/>TVA: {company_tva}"

        # Informations document (droite)
        titles = {"devis": "DEVIS", "facture": "FACTURE"}
        title = titles.get(doc_type, "DOCUMENT")
        numero = doc_data.get("numero", "")
        date_doc = self._format_date(doc_data.get("date"))

        # Dates specifiques
        date_info = f"Date: {date_doc}"
        if doc_type == "devis":
            validite = self._format_date(doc_data.get("validite"))
            if validite:
                date_info += f"<br/>Validite: {validite}"
        elif doc_type == "facture":
            echeance = self._format_date(doc_data.get("echeance"))
            if echeance:
                date_info += f"<br/>Echeance: {echeance}"

        # Creer le tableau d'en-tete
        left_content = [
            Paragraph(company_name, self.styles['CompanyName']),
            Paragraph(company_details, self.styles['CompanyDetails'])
        ]

        right_content = [
            Paragraph(title, self.styles['DocType']),
            Paragraph(f"N. {numero}", self.styles['DocNumber']),
            Paragraph(date_info, self.styles['DocDate'])
        ]

        header_data = [[left_content, right_content]]
        header_table = Table(header_data, colWidths=[90*mm, 90*mm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))

        elements.append(header_table)
        elements.append(Spacer(1, 8*mm))
        elements.append(HRFlowable(width="100%", thickness=1, color=self.border_color))
        elements.append(Spacer(1, 8*mm))

        return elements

    def _build_client_section(self, client_data: Dict) -> List:
        """Construit la section client."""
        elements = []

        elements.append(Paragraph("CLIENT", self.styles['SectionTitle']))

        client_name = client_data.get("raison_sociale") or f"{client_data.get('nom', '')} {client_data.get('prenom', '')}".strip()
        client_address = client_data.get("adresse", "")
        client_cp = client_data.get("code_postal", "")
        client_ville = client_data.get("ville", "")
        client_pays = client_data.get("pays", "")

        # Box client avec bordure gauche coloree
        client_details = f"{client_address}<br/>{client_cp} {client_ville}<br/>{client_pays}"

        client_table_data = [[
            Paragraph(client_name, self.styles['ClientName']),
        ], [
            Paragraph(client_details, self.styles['ClientDetails'])
        ]]

        client_table = Table(client_table_data, colWidths=[100*mm])
        client_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.light_gray),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (0, 0), 10),
            ('BOTTOMPADDING', (-1, -1), (-1, -1), 10),
            ('LINEBEFORESTARTPADDING', (0, 0), (0, -1), 3),
            ('LINEBEFORECOLOR', (0, 0), (0, -1), self.primary_color),
        ]))

        elements.append(client_table)
        elements.append(Spacer(1, 6*mm))

        return elements

    def _build_object_section(self, doc_data: Dict) -> List:
        """Construit la section objet."""
        elements = []

        objet = doc_data.get("objet", "")
        if objet:
            elements.append(Paragraph("OBJET", self.styles['SectionTitle']))
            elements.append(Paragraph(objet, self.styles['Object']))
            elements.append(Spacer(1, 6*mm))

        return elements

    def _build_lines_table(self, doc_data: Dict) -> List:
        """Construit le tableau des lignes avec colonne TVA."""
        elements = []

        lignes = doc_data.get("lignes", [])
        if isinstance(lignes, str):
            import json
            try:
                lignes = json.loads(lignes)
            except json.JSONDecodeError:
                lignes = []

        # En-tetes du tableau - avec colonne TVA
        header = ['Description', 'Qte', 'P.U. HT', 'Remise', 'TVA', 'Total HT']

        # Donnees
        table_data = [header]

        for ligne in lignes:
            description = ligne.get("description", "")
            quantite = ligne.get("quantite") or ligne.get("quantity", 1)
            unite = ligne.get("unite") or ligne.get("unit", "")
            qte_str = f"{quantite} {unite}".strip() if unite else str(quantite)

            prix_unitaire = ligne.get("prix_unitaire") or ligne.get("unit_price", 0)
            prix_unitaire_str = f"{self._format_money(prix_unitaire)} EUR"

            remise = ligne.get("remise_percent") or ligne.get("remise") or ligne.get("discount_percent", 0)
            remise_str = f"-{remise}%" if remise else ""

            # Taux TVA de la ligne
            taux_tva = ligne.get("taux_tva") or ligne.get("tax_rate", 20)
            tva_str = f"{taux_tva}%"

            # Total HT de la ligne
            total_ht_ligne = ligne.get("total_ht_ligne") or ligne.get("subtotal", 0)
            if not total_ht_ligne:
                # Calculer si non fourni
                prix = float(prix_unitaire)
                qte = float(quantite)
                rem = float(remise) / 100 if remise else 0
                total_ht_ligne = prix * qte * (1 - rem)

            total_ligne_str = f"{self._format_money(total_ht_ligne)} EUR"

            table_data.append([description, qte_str, prix_unitaire_str, remise_str, tva_str, total_ligne_str])

        # Si pas de lignes, ajouter une ligne vide
        if len(table_data) == 1:
            table_data.append(["Aucune ligne", "", "", "", "", ""])

        # Creer le tableau avec colonnes ajustees
        col_widths = [68*mm, 15*mm, 25*mm, 15*mm, 15*mm, 25*mm]
        table = Table(table_data, colWidths=col_widths)

        # Style du tableau
        style_commands = [
            # En-tete
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

            # Corps
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # Qte
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),   # P.U.
            ('ALIGN', (3, 1), (3, -1), 'CENTER'),  # Remise
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # TVA
            ('ALIGN', (5, 1), (5, -1), 'RIGHT'),   # Total

            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),

            # Lignes
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, self.border_color),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Style zebra si configure
        tableaux_style = self.theme.get("tableaux", "simple")
        if tableaux_style == "zebra":
            for i in range(2, len(table_data), 2):
                style_commands.append(('BACKGROUND', (0, i), (-1, i), self.light_gray))

        table.setStyle(TableStyle(style_commands))

        elements.append(table)
        elements.append(Spacer(1, 6*mm))

        return elements

    def _build_tax_summary(self, doc_data: Dict) -> List[Dict]:
        """
        Construit le resume de TVA par taux a partir des lignes.

        Args:
            doc_data: Donnees du document

        Returns:
            Liste de dicts avec code, nom, taux, base_ht, montant_tva
        """
        # Si ventilation_tva est deja fournie, l'utiliser
        ventilation = doc_data.get("ventilation_tva")
        if ventilation:
            if isinstance(ventilation, str):
                import json
                try:
                    ventilation = json.loads(ventilation)
                except json.JSONDecodeError:
                    ventilation = []
            return ventilation

        # Sinon, calculer depuis les lignes
        lignes = doc_data.get("lignes", [])
        if isinstance(lignes, str):
            import json
            try:
                lignes = json.loads(lignes)
            except json.JSONDecodeError:
                lignes = []

        # Grouper par taux de TVA
        tva_groups: Dict[str, Dict] = {}
        for ligne in lignes:
            taux = ligne.get("taux_tva") or ligne.get("tax_rate") or 20
            code_taxe = ligne.get("code_taxe") or ligne.get("tax_code") or f"TVA{int(taux)}"

            key = str(taux)
            if key not in tva_groups:
                tva_groups[key] = {
                    "taxe_code": code_taxe,
                    "taxe_nom": f"TVA {taux}%",
                    "taux": float(taux),
                    "base_ht": Decimal("0"),
                    "montant_tva": Decimal("0")
                }

            # Calculer la base HT de la ligne
            prix = Decimal(str(ligne.get("prix_unitaire") or ligne.get("unit_price") or 0))
            qte = Decimal(str(ligne.get("quantite") or ligne.get("quantity") or 1))
            remise_pct = Decimal(str(ligne.get("remise_percent") or ligne.get("remise") or ligne.get("discount_percent") or 0))

            base_ligne = prix * qte * (1 - remise_pct / 100)
            tva_ligne = base_ligne * Decimal(str(taux)) / 100

            tva_groups[key]["base_ht"] += base_ligne
            tva_groups[key]["montant_tva"] += tva_ligne

        # Convertir en liste triee par taux decroissant
        result = []
        for key in sorted(tva_groups.keys(), key=lambda x: float(x), reverse=True):
            group = tva_groups[key]
            result.append({
                "taxe_code": group["taxe_code"],
                "taxe_nom": group["taxe_nom"],
                "taux": group["taux"],
                "base_ht": float(group["base_ht"]),
                "montant_tva": float(group["montant_tva"])
            })

        return result

    def _build_totals_section(self, doc_type: str, doc_data: Dict) -> List:
        """Construit la section des totaux avec ventilation TVA par taux."""
        elements = []

        # Construire le resume TVA par taux
        tax_summary = self._build_tax_summary(doc_data)

        # Calculer les totaux depuis le resume TVA
        total_ht = Decimal("0")
        total_tva = Decimal("0")
        for tax_group in tax_summary:
            total_ht += Decimal(str(tax_group["base_ht"]))
            total_tva += Decimal(str(tax_group["montant_tva"]))

        # Utiliser les valeurs du document si disponibles (priorite)
        if doc_data.get("total_ht") or doc_data.get("subtotal"):
            total_ht = Decimal(str(doc_data.get("total_ht") or doc_data.get("subtotal", 0) or 0))
        if doc_data.get("total_tva") or doc_data.get("tax_amount"):
            total_tva = Decimal(str(doc_data.get("total_tva") or doc_data.get("tax_amount", 0) or 0))

        total_ttc = total_ht + total_tva
        if doc_data.get("total_ttc") or doc_data.get("total"):
            total_ttc = Decimal(str(doc_data.get("total_ttc") or doc_data.get("total", 0) or 0))

        # Construction du tableau des totaux
        totals_data = [
            ['Total HT', f'{self._format_money(total_ht)} EUR'],
        ]

        # Ajouter la ventilation TVA si plusieurs taux
        if len(tax_summary) > 1:
            # Plusieurs taux: afficher le detail
            for tax_group in tax_summary:
                taux = tax_group["taux"]
                base_ht = tax_group["base_ht"]
                montant_tva = tax_group["montant_tva"]
                # Format: "TVA 20% (sur 1000,00)" => "200,00"
                totals_data.append([
                    f'TVA {taux}% (base {self._format_money(base_ht)})',
                    f'{self._format_money(montant_tva)} EUR'
                ])
        elif len(tax_summary) == 1:
            # Un seul taux: format simple
            tax_group = tax_summary[0]
            taux = tax_group["taux"]
            montant_tva = tax_group["montant_tva"]
            totals_data.append([f'TVA ({taux}%)', f'{self._format_money(montant_tva)} EUR'])
        else:
            # Pas de detail: utiliser le taux par defaut
            tva_pct = doc_data.get("tva", 20) or 20
            totals_data.append([f'TVA ({tva_pct}%)', f'{self._format_money(total_tva)} EUR'])

        # Ajuster la largeur des colonnes selon le contenu
        col_width_label = 45*mm
        col_width_value = 30*mm

        totals_table = Table(totals_data, colWidths=[col_width_label, col_width_value])
        totals_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), self.gray_color),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, self.border_color),
        ]))

        # Total TTC (avec fond couleur)
        ttc_data = [['Total TTC', f'{self._format_money(total_ttc)} EUR']]
        ttc_table = Table(ttc_data, colWidths=[col_width_label, col_width_value])
        ttc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))

        # Conteneur aligne a droite
        wrapper_data = [[totals_table], [Spacer(1, 2*mm)], [ttc_table]]

        # Montant paye pour factures
        if doc_type == "facture":
            montant_paye = doc_data.get("montant_paye") or doc_data.get("paid_amount", 0)
            reste = doc_data.get("reste_a_payer") or doc_data.get("remaining_amount")
            if reste is None:
                reste = float(total_ttc) - float(montant_paye or 0)

            paiement_data = [
                ['Deja paye', f'{self._format_money(montant_paye)} EUR'],
                ['Reste a payer', f'{self._format_money(reste)} EUR'],
            ]
            paiement_table = Table(paiement_data, colWidths=[col_width_label, col_width_value])
            paiement_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TEXTCOLOR', (0, 0), (0, -1), self.gray_color),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, self.border_color),
            ]))
            wrapper_data.append([Spacer(1, 2*mm)])
            wrapper_data.append([paiement_table])

        wrapper_width = col_width_label + col_width_value
        wrapper_table = Table(wrapper_data, colWidths=[wrapper_width])
        wrapper_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ]))

        # Aligner a droite avec un tableau externe
        left_width = 180*mm - wrapper_width - 5*mm
        outer_data = [['', wrapper_table]]
        outer_table = Table(outer_data, colWidths=[left_width, wrapper_width])
        outer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        elements.append(outer_table)
        elements.append(Spacer(1, 8*mm))

        return elements

    def _build_notes_section(self, doc_data: Dict) -> List:
        """Construit la section notes/conditions."""
        elements = []

        notes = doc_data.get("notes", "")
        conditions = doc_data.get("conditions", "")

        if notes or conditions:
            elements.append(HRFlowable(width="100%", thickness=0.5, color=self.border_color))
            elements.append(Spacer(1, 4*mm))

            if notes:
                elements.append(Paragraph("NOTES", self.styles['SectionTitle']))
                elements.append(Paragraph(notes.replace('\n', '<br/>'), self.styles['Notes']))
                elements.append(Spacer(1, 4*mm))

            if conditions:
                elements.append(Paragraph("CONDITIONS", self.styles['SectionTitle']))
                elements.append(Paragraph(conditions.replace('\n', '<br/>'), self.styles['Notes']))

        return elements

    def _build_footer_section(self, doc_type: str, tenant_data: Dict) -> List:
        """Construit le pied de page avec informations bancaires et mentions legales."""
        elements = []

        # Informations bancaires
        iban = tenant_data.get("iban", "")
        bic = tenant_data.get("bic", "")
        banque = tenant_data.get("banque", "")
        titulaire = tenant_data.get("titulaire_compte", "")

        if iban or bic:
            elements.append(Spacer(1, 6*mm))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=self.border_color))
            elements.append(Spacer(1, 4*mm))
            elements.append(Paragraph("COORDONNEES BANCAIRES", self.styles['SectionTitle']))

            bank_info = []
            if titulaire:
                bank_info.append(f"<b>Titulaire:</b> {titulaire}")
            if banque:
                bank_info.append(f"<b>Banque:</b> {banque}")
            if iban:
                # Formater IBAN avec espaces
                iban_formatted = " ".join([iban[i:i+4] for i in range(0, len(iban), 4)])
                bank_info.append(f"<b>IBAN:</b> {iban_formatted}")
            if bic:
                bank_info.append(f"<b>BIC:</b> {bic}")

            bank_text = "<br/>".join(bank_info)
            elements.append(Paragraph(bank_text, self.styles['Notes']))

        # Mentions legales specifiques au type de document
        mention = ""
        if doc_type == "facture":
            mention = tenant_data.get("mention_facture", "")
        elif doc_type == "devis":
            mention = tenant_data.get("mention_devis", "")

        mentions_legales = tenant_data.get("mentions_legales", "")

        if mention or mentions_legales:
            elements.append(Spacer(1, 4*mm))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=self.border_color))
            elements.append(Spacer(1, 4*mm))
            elements.append(Paragraph("MENTIONS LEGALES", self.styles['SectionTitle']))

            all_mentions = []
            if mention:
                all_mentions.append(mention)
            if mentions_legales:
                all_mentions.append(mentions_legales)

            mentions_text = "<br/><br/>".join(all_mentions).replace('\n', '<br/>')
            elements.append(Paragraph(mentions_text, self.styles['Notes']))

        return elements

    def _build_signature_section(self, doc_data: Dict) -> List:
        """Construit la section signature electronique si presente."""
        elements = []

        signature = doc_data.get("signature_client")
        signature_date = doc_data.get("signature_date")
        signature_ip = doc_data.get("signature_ip")

        if not signature:
            return elements

        # Ligne de separation
        elements.append(Spacer(1, 6*mm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=self.border_color))
        elements.append(Spacer(1, 4*mm))

        # Titre de la section
        elements.append(Paragraph("SIGNATURE ELECTRONIQUE", self.styles['SectionTitle']))
        elements.append(Spacer(1, 2*mm))

        # Formater la date
        date_str = ""
        if signature_date:
            if hasattr(signature_date, "strftime"):
                date_str = signature_date.strftime("%d/%m/%Y a %H:%M")
            else:
                date_str = str(signature_date)

        # Texte d'information
        info_text = f"<font color='#065F46'><b>Document signe electroniquement</b></font><br/>"
        if date_str:
            info_text += f"Date: {date_str}<br/>"
        if signature_ip:
            info_text += f"IP: {signature_ip}"

        # Creer l'image de la signature depuis le base64
        signature_image = None
        try:
            # Retirer le prefixe data:image/png;base64, si present
            if signature.startswith("data:image/"):
                signature_data = signature.split(",", 1)[1]
            else:
                signature_data = signature

            # Decoder le base64
            image_bytes = base64.b64decode(signature_data)
            image_buffer = BytesIO(image_bytes)

            # Creer l'image ReportLab
            signature_image = Image(image_buffer, width=50*mm, height=20*mm)
        except Exception as e:
            logger.warning("signature_image_error", error=str(e))

        # Construction du tableau avec l'image de signature
        if signature_image:
            # Style pour le texte d'info
            info_style = ParagraphStyle(
                'SignatureInfo',
                parent=self.styles['Notes'],
                fontSize=9,
                leading=12
            )

            # Creer un conteneur pour le texte et l'image
            sig_data = [
                [Paragraph(info_text, info_style), signature_image]
            ]

            sig_table = Table(sig_data, colWidths=[100*mm, 60*mm])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('BACKGROUND', (0, 0), (-1, -1), hex_to_color("#dcfce7")),
                ('BOX', (0, 0), (-1, -1), 1, hex_to_color("#a7f3d0")),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))

            elements.append(sig_table)
        else:
            # Juste le texte si l'image n'a pas pu etre chargee
            elements.append(Paragraph(info_text, self.styles['Notes']))

        return elements

    def _generate_pdf(self, doc_type: str, doc_data: Dict) -> bytes:
        """Genere le PDF complet."""
        # Recuperer les informations
        client_data = self._get_client_info(doc_data.get("client"))
        tenant_data = self._get_tenant_info()

        # Creer le buffer
        buffer = BytesIO()

        # Marges depuis le theme
        margin_str = self.theme.get("marges", "15mm")
        try:
            margin = float(margin_str.replace("mm", "")) * mm
        except (ValueError, AttributeError):
            margin = 15 * mm

        # Creer le document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin
        )

        # Construire les elements
        elements = []
        elements.extend(self._build_header(doc_type, doc_data, tenant_data))
        elements.extend(self._build_client_section(client_data))
        elements.extend(self._build_object_section(doc_data))
        elements.extend(self._build_lines_table(doc_data))
        elements.extend(self._build_totals_section(doc_type, doc_data))
        elements.extend(self._build_notes_section(doc_data))
        elements.extend(self._build_footer_section(doc_type, tenant_data))
        elements.extend(self._build_signature_section(doc_data))

        # Generer le PDF
        doc.build(elements)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

    def generate_devis_pdf(self, devis_data: Dict) -> bytes:
        """
        Genere le PDF d'un devis.

        Args:
            devis_data: Donnees du devis (depuis la base)

        Returns:
            bytes: Contenu du PDF
        """
        pdf_bytes = self._generate_pdf("devis", devis_data)

        logger.info(
            "devis_pdf_generated",
            tenant_id=str(self.tenant_id),
            numero=devis_data.get("numero")
        )

        return pdf_bytes

    def generate_facture_pdf(self, facture_data: Dict) -> bytes:
        """
        Genere le PDF d'une facture.

        Args:
            facture_data: Donnees de la facture (depuis la base)

        Returns:
            bytes: Contenu du PDF
        """
        pdf_bytes = self._generate_pdf("facture", facture_data)

        logger.info(
            "facture_pdf_generated",
            tenant_id=str(self.tenant_id),
            numero=facture_data.get("numero")
        )

        return pdf_bytes


# =============================================================================
# Fonctions utilitaires (raccourcis)
# =============================================================================
def generate_devis_pdf(tenant_id: PyUUID, devis_data: Dict) -> bytes:
    """
    Raccourci pour generer un PDF de devis.

    Args:
        tenant_id: UUID du tenant
        devis_data: Donnees du devis

    Returns:
        bytes: Contenu du PDF
    """
    generator = PDFGenerator(tenant_id)
    return generator.generate_devis_pdf(devis_data)


def generate_facture_pdf(tenant_id: PyUUID, facture_data: Dict) -> bytes:
    """
    Raccourci pour generer un PDF de facture.

    Args:
        tenant_id: UUID du tenant
        facture_data: Donnees de la facture

    Returns:
        bytes: Contenu du PDF
    """
    generator = PDFGenerator(tenant_id)
    return generator.generate_facture_pdf(facture_data)
