# =============================================================================
# AZALPLUS - Business Plan PDF Generator
# =============================================================================
"""
Génération de PDF professionnels pour les business plans.
Export stylisé avec graphiques et mise en page soignée.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import structlog

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable, ListFlowable, ListItem
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart

# SVG support
try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    SVG_AVAILABLE = True
except ImportError:
    SVG_AVAILABLE = False

logger = structlog.get_logger()

# Chemin du logo (dynamique selon APP_NAME)
def _get_logo_path():
    """Retourne le chemin du logo selon APP_NAME."""
    import os
    app_name = os.environ.get("APP_NAME", "AZALPLUS")
    app_name_lower = app_name.lower()
    # Chercher dans plusieurs emplacements
    possible_paths = [
        Path(f"/home/ubuntu/{app_name_lower}/assets/logo-{app_name_lower}.svg"),
        Path(f"/home/ubuntu/{app_name_lower}/assets/logo.svg"),
        Path(f"/home/ubuntu/{app_name_lower}/static/logo.svg"),
        Path(__file__).parent.parent / "assets" / f"logo-{app_name_lower}-full.svg",
        Path(__file__).parent.parent / "assets" / "logo-azalplus-full.svg",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return Path(__file__).parent.parent / "assets" / "logo-azalplus-full.svg"

LOGO_PATH = _get_logo_path()


# =============================================================================
# Couleurs AZALPLUS
# =============================================================================
COLORS = {
    'primary': colors.HexColor('#3454D1'),
    'primary_dark': colors.HexColor('#2A45B0'),
    'accent': colors.HexColor('#6B9FFF'),
    'dark': colors.HexColor('#1a1a2e'),
    'gray': colors.HexColor('#666666'),
    'light_gray': colors.HexColor('#f5f5f5'),
    'white': colors.HexColor('#ffffff'),
    'success': colors.HexColor('#10b981'),
    'warning': colors.HexColor('#f59e0b'),
    'error': colors.HexColor('#ef4444'),
}


# =============================================================================
# Business Plan PDF Generator
# =============================================================================
class BusinessPlanPDFGenerator:
    """Générateur de PDF pour Business Plans."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Configure les styles personnalisés."""

        # Titre principal
        self.styles.add(ParagraphStyle(
            name='BPTitle',
            fontName='Helvetica-Bold',
            fontSize=28,
            textColor=COLORS['primary'],
            spaceAfter=20,
            alignment=TA_CENTER
        ))

        # Sous-titre
        self.styles.add(ParagraphStyle(
            name='BPSubtitle',
            fontName='Helvetica',
            fontSize=14,
            textColor=COLORS['gray'],
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        # Titre de section
        self.styles.add(ParagraphStyle(
            name='BPSection',
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=COLORS['dark'],
            spaceBefore=20,
            spaceAfter=12,
            borderPadding=(0, 0, 5, 0),
            borderColor=COLORS['primary'],
            borderWidth=0,
            leftIndent=0
        ))

        # Sous-section
        self.styles.add(ParagraphStyle(
            name='BPSubSection',
            fontName='Helvetica-Bold',
            fontSize=12,
            textColor=COLORS['primary'],
            spaceBefore=15,
            spaceAfter=8
        ))

        # Corps de texte
        self.styles.add(ParagraphStyle(
            name='BPBody',
            fontName='Helvetica',
            fontSize=10,
            textColor=COLORS['dark'],
            spaceAfter=8,
            alignment=TA_JUSTIFY,
            leading=14
        ))

        # Texte important
        self.styles.add(ParagraphStyle(
            name='BPHighlight',
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=COLORS['primary'],
            spaceAfter=8
        ))

        # Chiffres clés
        self.styles.add(ParagraphStyle(
            name='BPKeyFigure',
            fontName='Helvetica-Bold',
            fontSize=24,
            textColor=COLORS['primary'],
            alignment=TA_CENTER
        ))

        # Label chiffres
        self.styles.add(ParagraphStyle(
            name='BPKeyLabel',
            fontName='Helvetica',
            fontSize=9,
            textColor=COLORS['gray'],
            alignment=TA_CENTER
        ))

        # Citation / Pitch
        self.styles.add(ParagraphStyle(
            name='BPQuote',
            fontName='Helvetica-Oblique',
            fontSize=12,
            textColor=COLORS['dark'],
            spaceBefore=15,
            spaceAfter=15,
            leftIndent=20,
            rightIndent=20,
            borderPadding=10,
            backColor=COLORS['light_gray'],
            alignment=TA_CENTER
        ))

    def generate(self, bp_data: Dict[str, Any]) -> bytes:
        """
        Génère le PDF du business plan.

        Args:
            bp_data: Données du business plan

        Returns:
            bytes: Contenu du PDF
        """
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # Construire le contenu
        story = []

        # Page de garde
        story.extend(self._build_cover_page(bp_data))
        story.append(PageBreak())

        # Sommaire
        story.extend(self._build_toc())
        story.append(PageBreak())

        # Executive Summary
        story.extend(self._build_executive_summary(bp_data))
        story.append(PageBreak())

        # Le porteur de projet
        story.extend(self._build_porteur_section(bp_data))

        # Le projet
        story.extend(self._build_projet_section(bp_data))
        story.append(PageBreak())

        # Le marché
        story.extend(self._build_marche_section(bp_data))

        # Stratégie commerciale
        story.extend(self._build_strategie_section(bp_data))
        story.append(PageBreak())

        # Structure juridique
        story.extend(self._build_juridique_section(bp_data))

        # Prévisionnel financier
        story.extend(self._build_financier_section(bp_data))
        story.append(PageBreak())

        # Planning et risques
        story.extend(self._build_planning_section(bp_data))

        # Annexes
        story.extend(self._build_annexes(bp_data))

        # Générer le PDF
        doc.build(story, onFirstPage=self._add_header_footer, onLaterPages=self._add_header_footer)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info("business_plan_pdf_generated", nom=bp_data.get('nom_projet'))

        return pdf_bytes

    def _build_cover_page(self, bp: Dict) -> List:
        """Page de garde."""
        elements = []

        elements.append(Spacer(1, 2*cm))

        # Logo AZALPLUS (SVG)
        if SVG_AVAILABLE and LOGO_PATH.exists():
            try:
                drawing = svg2rlg(str(LOGO_PATH))
                if drawing:
                    # Redimensionner le logo (largeur 6cm)
                    scale = 6*cm / drawing.width
                    drawing.width = 6*cm
                    drawing.height = drawing.height * scale
                    drawing.scale(scale, scale)
                    # Centrer le logo
                    elements.append(drawing)
                    elements.append(Spacer(1, 1*cm))
            except Exception as e:
                logger.debug("logo_svg_error", error=str(e))

        elements.append(Spacer(1, 1*cm))

        # Titre
        elements.append(Paragraph("BUSINESS PLAN", self.styles['BPTitle']))
        elements.append(Spacer(1, 1*cm))

        # Nom du projet
        nom_projet = bp.get('nom_projet', 'Mon Projet')
        elements.append(Paragraph(nom_projet.upper(), self.styles['BPTitle']))

        elements.append(Spacer(1, 1*cm))

        # Pitch
        pitch = bp.get('pitch', '')
        if pitch:
            elements.append(Paragraph(f'"{pitch}"', self.styles['BPQuote']))

        elements.append(Spacer(1, 2*cm))

        # Infos porteur
        porteur = f"{bp.get('porteur_prenom', '')} {bp.get('porteur_nom', '')}".strip()
        if porteur:
            elements.append(Paragraph(porteur, self.styles['BPSubtitle']))

        email = bp.get('porteur_email', '')
        if email:
            elements.append(Paragraph(email, self.styles['BPSubtitle']))

        elements.append(Spacer(1, 3*cm))

        # Date
        date_str = datetime.now().strftime('%B %Y').capitalize()
        elements.append(Paragraph(date_str, self.styles['BPSubtitle']))

        # Mention confidentiel
        elements.append(Spacer(1, 1*cm))
        elements.append(Paragraph("DOCUMENT CONFIDENTIEL", ParagraphStyle(
            'Confidentiel',
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=COLORS['error'],
            alignment=TA_CENTER
        )))

        # Branding AZALPLUS (texte, pas d'image)
        elements.append(Spacer(1, 2*cm))
        elements.append(Paragraph("Généré avec AZALPLUS", ParagraphStyle(
            'Branding',
            fontName='Helvetica',
            fontSize=9,
            textColor=COLORS['gray'],
            alignment=TA_CENTER
        )))

        return elements

    def _build_toc(self) -> List:
        """Sommaire."""
        elements = []

        elements.append(Paragraph("SOMMAIRE", self.styles['BPSection']))
        elements.append(Spacer(1, 1*cm))

        toc_items = [
            ("1. Executive Summary", 3),
            ("2. Le porteur de projet", 4),
            ("3. Le projet", 5),
            ("4. Le marché", 6),
            ("5. Stratégie commerciale", 7),
            ("6. Structure juridique", 8),
            ("7. Prévisionnel financier", 9),
            ("8. Planning et risques", 11),
            ("Annexes", 12),
        ]

        for title, page in toc_items:
            row = Table(
                [[Paragraph(title, self.styles['BPBody']),
                  Paragraph(str(page), ParagraphStyle('TOCPage', alignment=TA_RIGHT))]],
                colWidths=[14*cm, 2*cm]
            )
            row.setStyle(TableStyle([
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, COLORS['light_gray']),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(row)

        return elements

    def _build_executive_summary(self, bp: Dict) -> List:
        """Executive Summary."""
        elements = []

        elements.append(Paragraph("1. EXECUTIVE SUMMARY", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Le projet en bref
        elements.append(Paragraph("Le projet", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('pitch', 'Non renseigné'), self.styles['BPBody']))

        # Chiffres clés
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph("Chiffres clés", self.styles['BPSubSection']))

        ca_1 = bp.get('ca_annee_1', 0) or 0
        ca_3 = bp.get('ca_annee_3', 0) or 0
        invest = bp.get('investissement_initial', 0) or 0
        financement = bp.get('financement_recherche', 0) or 0

        key_figures = Table([
            [
                self._key_figure_cell(f"{ca_1:,.0f} €".replace(',', ' '), "CA Année 1"),
                self._key_figure_cell(f"{ca_3:,.0f} €".replace(',', ' '), "CA Année 3"),
                self._key_figure_cell(f"{invest:,.0f} €".replace(',', ' '), "Investissement"),
                self._key_figure_cell(f"{financement:,.0f} €".replace(',', ' '), "Financement"),
            ]
        ], colWidths=[4*cm, 4*cm, 4*cm, 4*cm])

        key_figures.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 1, COLORS['light_gray']),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, COLORS['light_gray']),
            ('BACKGROUND', (0, 0), (-1, -1), COLORS['light_gray']),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        elements.append(key_figures)

        # Points forts
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph("Points forts", self.styles['BPSubSection']))

        avantages = bp.get('avantages_concurrentiels', '')
        if avantages:
            elements.append(Paragraph(avantages, self.styles['BPBody']))
        else:
            elements.append(Paragraph("À compléter", self.styles['BPBody']))

        return elements

    def _key_figure_cell(self, value: str, label: str) -> Table:
        """Cellule de chiffre clé."""
        return Table([
            [Paragraph(value, self.styles['BPKeyFigure'])],
            [Paragraph(label, self.styles['BPKeyLabel'])]
        ])

    def _build_porteur_section(self, bp: Dict) -> List:
        """Section porteur de projet."""
        elements = []

        elements.append(Paragraph("2. LE PORTEUR DE PROJET", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Identité
        porteur = f"{bp.get('porteur_prenom', '')} {bp.get('porteur_nom', '')}".strip()
        elements.append(Paragraph(f"<b>{porteur}</b>", self.styles['BPHighlight']))

        email = bp.get('porteur_email', '')
        tel = bp.get('porteur_telephone', '')
        if email:
            elements.append(Paragraph(f"Email : {email}", self.styles['BPBody']))
        if tel:
            elements.append(Paragraph(f"Téléphone : {tel}", self.styles['BPBody']))

        # Expérience
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph("Expérience et compétences", self.styles['BPSubSection']))
        experience = bp.get('porteur_experience', 'Non renseigné')
        elements.append(Paragraph(experience, self.styles['BPBody']))

        # Motivation
        elements.append(Paragraph("Motivation", self.styles['BPSubSection']))
        motivation = bp.get('porteur_motivation', 'Non renseigné')
        elements.append(Paragraph(motivation, self.styles['BPBody']))

        return elements

    def _build_projet_section(self, bp: Dict) -> List:
        """Section projet."""
        elements = []

        elements.append(Paragraph("3. LE PROJET", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Problème
        elements.append(Paragraph("Le problème identifié", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('probleme', 'Non renseigné'), self.styles['BPBody']))

        # Solution
        elements.append(Paragraph("Notre solution", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('solution', 'Non renseigné'), self.styles['BPBody']))

        # Proposition de valeur
        elements.append(Paragraph("Proposition de valeur", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('proposition_valeur', 'Non renseigné'), self.styles['BPBody']))

        # Secteur
        elements.append(Paragraph("Secteur d'activité", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('secteur_activite', 'Non renseigné'), self.styles['BPBody']))

        return elements

    def _build_marche_section(self, bp: Dict) -> List:
        """Section marché."""
        elements = []

        elements.append(Paragraph("4. LE MARCHÉ", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Marché cible
        elements.append(Paragraph("Marché cible", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('marche_cible', 'Non renseigné'), self.styles['BPBody']))

        # Zone géographique
        zone = bp.get('zone_geographique', '')
        details = bp.get('zone_details', '')
        if zone:
            elements.append(Paragraph("Zone géographique", self.styles['BPSubSection']))
            elements.append(Paragraph(f"{zone} - {details}" if details else zone, self.styles['BPBody']))

        # Taille du marché
        taille = bp.get('taille_marche', '')
        if taille:
            elements.append(Paragraph("Taille du marché", self.styles['BPSubSection']))
            elements.append(Paragraph(taille, self.styles['BPBody']))

        # Concurrents
        elements.append(Paragraph("Analyse concurrentielle", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('concurrents', 'Non renseigné'), self.styles['BPBody']))

        # Avantages concurrentiels
        elements.append(Paragraph("Nos avantages concurrentiels", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('avantages_concurrentiels', 'Non renseigné'), self.styles['BPBody']))

        return elements

    def _build_strategie_section(self, bp: Dict) -> List:
        """Section stratégie commerciale."""
        elements = []

        elements.append(Paragraph("5. STRATÉGIE COMMERCIALE", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Offre
        elements.append(Paragraph("Produits / Services", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('offre_produits', 'Non renseigné'), self.styles['BPBody']))

        # Prix
        elements.append(Paragraph("Politique de prix", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('politique_prix', 'Non renseigné'), self.styles['BPBody']))

        # Distribution
        elements.append(Paragraph("Canaux de distribution", self.styles['BPSubSection']))
        canaux = bp.get('canaux_distribution', [])
        if isinstance(canaux, list) and canaux:
            elements.append(Paragraph(", ".join(canaux), self.styles['BPBody']))
        else:
            elements.append(Paragraph('Non renseigné', self.styles['BPBody']))

        # Communication
        elements.append(Paragraph("Stratégie de communication", self.styles['BPSubSection']))
        elements.append(Paragraph(bp.get('strategie_communication', 'Non renseigné'), self.styles['BPBody']))

        return elements

    def _build_juridique_section(self, bp: Dict) -> List:
        """Section structure juridique."""
        elements = []

        elements.append(Paragraph("6. STRUCTURE JURIDIQUE", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Forme juridique
        forme = bp.get('forme_juridique', 'À définir')
        elements.append(Paragraph(f"<b>Forme juridique : {forme}</b>", self.styles['BPHighlight']))

        # Capital
        capital = bp.get('capital_prevu', 0)
        if capital:
            elements.append(Paragraph(f"Capital social prévu : {capital:,.0f} €".replace(',', ' '), self.styles['BPBody']))

        # Associés
        associes = bp.get('associes', '')
        if associes:
            elements.append(Paragraph("Associés", self.styles['BPSubSection']))
            elements.append(Paragraph(associes, self.styles['BPBody']))

        # Siège
        siege = bp.get('siege_social', '')
        if siege:
            elements.append(Paragraph(f"Siège social prévu : {siege}", self.styles['BPBody']))

        return elements

    def _build_financier_section(self, bp: Dict) -> List:
        """Section prévisionnel financier."""
        elements = []

        elements.append(Paragraph("7. PRÉVISIONNEL FINANCIER", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Plan de financement
        elements.append(Paragraph("Plan de financement", self.styles['BPSubSection']))

        invest = bp.get('investissement_initial', 0) or 0
        apport = bp.get('apport_personnel', 0) or 0
        financement = bp.get('financement_recherche', 0) or 0

        financement_data = [
            ['Besoins', 'Ressources'],
            [f"Investissement initial : {invest:,.0f} €".replace(',', ' '), f"Apport personnel : {apport:,.0f} €".replace(',', ' ')],
            ['', f"Financement recherché : {financement:,.0f} €".replace(',', ' ')],
            [f"<b>Total : {invest:,.0f} €</b>".replace(',', ' '), f"<b>Total : {apport + financement:,.0f} €</b>".replace(',', ' ')],
        ]

        fin_table = Table(financement_data, colWidths=[8*cm, 8*cm])
        fin_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS['white']),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, COLORS['gray']),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(fin_table)
        elements.append(Spacer(1, 0.5*cm))

        # Compte de résultat prévisionnel
        elements.append(Paragraph("Compte de résultat prévisionnel", self.styles['BPSubSection']))

        ca1 = bp.get('ca_annee_1', 0) or 0
        ca2 = bp.get('ca_annee_2', 0) or 0
        ca3 = bp.get('ca_annee_3', 0) or 0
        res1 = bp.get('resultat_annee_1', 0) or 0
        res2 = bp.get('resultat_annee_2', 0) or 0
        res3 = bp.get('resultat_annee_3', 0) or 0

        cr_data = [
            ['', 'Année 1', 'Année 2', 'Année 3'],
            ['Chiffre d\'affaires', f"{ca1:,.0f} €".replace(',', ' '), f"{ca2:,.0f} €".replace(',', ' '), f"{ca3:,.0f} €".replace(',', ' ')],
            ['Résultat net', f"{res1:,.0f} €".replace(',', ' '), f"{res2:,.0f} €".replace(',', ' '), f"{res3:,.0f} €".replace(',', ' ')],
        ]

        cr_table = Table(cr_data, colWidths=[6*cm, 3.5*cm, 3.5*cm, 3.5*cm])
        cr_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS['primary']),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS['white']),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, COLORS['gray']),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(cr_table)
        elements.append(Spacer(1, 0.5*cm))

        # Seuil de rentabilité
        seuil = bp.get('seuil_rentabilite', 0)
        if seuil:
            elements.append(Paragraph(f"<b>Seuil de rentabilité : {seuil:,.0f} €</b>".replace(',', ' '), self.styles['BPHighlight']))

        # BFR
        bfr = bp.get('bfr', 0)
        if bfr:
            elements.append(Paragraph(f"Besoin en Fonds de Roulement : {bfr:,.0f} €".replace(',', ' '), self.styles['BPBody']))

        return elements

    def _build_planning_section(self, bp: Dict) -> List:
        """Section planning et risques."""
        elements = []

        elements.append(Paragraph("8. PLANNING ET RISQUES", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Planning
        elements.append(Paragraph("Étapes clés", self.styles['BPSubSection']))
        etapes = bp.get('etapes_cles', [])
        if isinstance(etapes, list) and etapes:
            for etape in etapes:
                if isinstance(etape, dict):
                    label = etape.get('etape', '')
                    date = etape.get('date', '')
                    fait = "✓" if etape.get('fait', False) else "○"
                    elements.append(Paragraph(f"{fait} {label} - {date}", self.styles['BPBody']))
        else:
            elements.append(Paragraph("À définir", self.styles['BPBody']))

        # Risques
        elements.append(Paragraph("Risques identifiés", self.styles['BPSubSection']))
        risques = bp.get('risques_identifies', 'Aucun risque identifié')
        elements.append(Paragraph(risques, self.styles['BPBody']))

        # Ressources humaines
        elements.append(Paragraph("Ressources humaines", self.styles['BPSubSection']))
        eff_depart = bp.get('effectif_depart', 1) or 1
        eff_3 = bp.get('effectif_annee_3', eff_depart) or eff_depart
        elements.append(Paragraph(f"Effectif au démarrage : {eff_depart}", self.styles['BPBody']))
        elements.append(Paragraph(f"Effectif prévu Année 3 : {eff_3}", self.styles['BPBody']))

        postes = bp.get('postes_a_creer', '')
        if postes:
            elements.append(Paragraph(f"Postes à créer : {postes}", self.styles['BPBody']))

        return elements

    def _build_annexes(self, bp: Dict) -> List:
        """Section annexes."""
        elements = []

        elements.append(Paragraph("ANNEXES", self.styles['BPSection']))
        elements.append(HRFlowable(width="100%", thickness=2, color=COLORS['primary']))
        elements.append(Spacer(1, 0.5*cm))

        # Liste des annexes
        annexes = []
        if bp.get('cv_porteur'):
            annexes.append("CV du porteur de projet")
        if bp.get('etude_marche'):
            annexes.append("Étude de marché détaillée")
        if bp.get('previsionnel_detaille'):
            annexes.append("Prévisionnel financier détaillé")

        if annexes:
            for i, annexe in enumerate(annexes, 1):
                elements.append(Paragraph(f"Annexe {i} : {annexe}", self.styles['BPBody']))
        else:
            elements.append(Paragraph("Aucune annexe", self.styles['BPBody']))

        # Contact
        elements.append(Spacer(1, 2*cm))
        elements.append(Paragraph("Contact", self.styles['BPSubSection']))
        porteur = f"{bp.get('porteur_prenom', '')} {bp.get('porteur_nom', '')}".strip()
        elements.append(Paragraph(porteur, self.styles['BPBody']))
        elements.append(Paragraph(bp.get('porteur_email', ''), self.styles['BPBody']))
        elements.append(Paragraph(bp.get('porteur_telephone', ''), self.styles['BPBody']))

        return elements

    def _add_header_footer(self, canvas, doc):
        """Ajoute header et footer à chaque page."""
        canvas.saveState()

        # Footer
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(COLORS['gray'])

        # Numéro de page
        page_num = canvas.getPageNumber()
        canvas.drawRightString(A4[0] - 2*cm, 1.5*cm, f"Page {page_num}")

        # Mention AZALPLUS
        canvas.drawString(2*cm, 1.5*cm, "Généré avec AZALPLUS")

        # Ligne de séparation
        canvas.setStrokeColor(COLORS['light_gray'])
        canvas.line(2*cm, 1.8*cm, A4[0] - 2*cm, 1.8*cm)

        canvas.restoreState()


# =============================================================================
# Fonction raccourci
# =============================================================================
def generate_business_plan_pdf(bp_data: Dict[str, Any]) -> bytes:
    """
    Génère un PDF de business plan.

    Args:
        bp_data: Données du business plan

    Returns:
        bytes: Contenu du PDF
    """
    generator = BusinessPlanPDFGenerator()
    return generator.generate(bp_data)
