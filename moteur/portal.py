# =============================================================================
# AZALPLUS - Client Portal
# =============================================================================
"""
Portail client pour consultation de documents sans authentification.
Acces securise par tokens uniques.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime
from pathlib import Path
import structlog

from .db import Database
from .theme import ThemeManager

logger = structlog.get_logger()

# =============================================================================
# Router
# =============================================================================
portal_router = APIRouter()

# =============================================================================
# Schemas
# =============================================================================
class AcceptDevisRequest(BaseModel):
    accepte: bool
    commentaire: Optional[str] = None


class SignatureRequest(BaseModel):
    """Schema pour la soumission d'une signature electronique."""
    signature: str  # Base64 encoded image data


# =============================================================================
# Token Generation Helpers
# =============================================================================
def generate_portal_token() -> str:
    """Genere un token unique pour l'acces portail."""
    return str(uuid4())


def create_access_token_for_document(
    table_name: str,
    tenant_id: UUID,
    document_id: UUID
) -> str:
    """Cree ou retourne le token d'acces pour un document."""

    with Database.get_session() as session:
        from sqlalchemy import text

        # Verifier si le document a deja un token
        result = session.execute(
            text(f"""
                SELECT access_token FROM azalplus.{table_name}
                WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
            """),
            {"id": str(document_id), "tenant_id": str(tenant_id)}
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Document non trouve")

        existing_token = row[0] if row else None

        if existing_token:
            return existing_token

        # Generer un nouveau token
        new_token = generate_portal_token()

        session.execute(
            text(f"""
                UPDATE azalplus.{table_name}
                SET access_token = :token
                WHERE id = :id AND tenant_id = :tenant_id
            """),
            {"token": new_token, "id": str(document_id), "tenant_id": str(tenant_id)}
        )
        session.commit()

        return new_token


def get_document_by_token(table_name: str, token: str) -> Optional[dict]:
    """Recupere un document par son token d'acces."""

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text(f"""
                SELECT d.*, c.nom as client_nom, c.email as client_email,
                       c.adresse as client_adresse, c.telephone as client_telephone,
                       t.nom as tenant_nom, t.adresse as tenant_adresse,
                       t.email as tenant_email, t.telephone as tenant_telephone,
                       t.siret as tenant_siret
                FROM azalplus.{table_name} d
                LEFT JOIN azalplus.clients c ON d.client = c.id
                LEFT JOIN azalplus.tenants t ON d.tenant_id = t.id
                WHERE d.access_token = :token AND d.deleted_at IS NULL
            """),
            {"token": token}
        )
        row = result.fetchone()

        if not row:
            return None

        return dict(row._mapping)


# =============================================================================
# HTML Templates
# =============================================================================
def render_portal_base(title: str, content: str) -> str:
    """Template de base pour le portail."""

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - AZALPLUS</title>
    <link rel="stylesheet" href="/static/style.css">
    <style>
        .portal-container {{
            max-width: 900px;
            margin: 40px auto;
            padding: 0 20px;
        }}
        .portal-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 32px;
            padding-bottom: 24px;
            border-bottom: 2px solid var(--gray-200);
        }}
        .portal-logo {{
            font-size: 24px;
            font-weight: 700;
            color: var(--primary);
        }}
        .portal-company {{
            text-align: right;
        }}
        .portal-company-name {{
            font-size: 18px;
            font-weight: 600;
            color: var(--gray-800);
        }}
        .portal-company-details {{
            font-size: 13px;
            color: var(--gray-500);
            margin-top: 4px;
        }}
        .document-card {{
            background: var(--white);
            border-radius: 12px;
            border: 1px solid var(--gray-200);
            overflow: hidden;
        }}
        .document-header {{
            background: var(--gray-50);
            padding: 24px;
            border-bottom: 1px solid var(--gray-200);
        }}
        .document-type {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--gray-500);
            margin-bottom: 4px;
        }}
        .document-number {{
            font-size: 24px;
            font-weight: 700;
            color: var(--gray-900);
        }}
        .document-meta {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            padding: 24px;
            background: var(--white);
            border-bottom: 1px solid var(--gray-200);
        }}
        .meta-block {{

        }}
        .meta-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--gray-500);
            margin-bottom: 4px;
        }}
        .meta-value {{
            font-size: 14px;
            color: var(--gray-800);
        }}
        .document-lines {{
            padding: 24px;
        }}
        .lines-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .lines-table th {{
            text-align: left;
            padding: 12px 8px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            color: var(--gray-500);
            background: var(--gray-50);
            border-bottom: 1px solid var(--gray-200);
        }}
        .lines-table td {{
            padding: 14px 8px;
            font-size: 14px;
            color: var(--gray-700);
            border-bottom: 1px solid var(--gray-100);
        }}
        .lines-table .col-qty,
        .lines-table .col-price,
        .lines-table .col-total {{
            text-align: right;
        }}
        .document-totals {{
            padding: 24px;
            background: var(--gray-50);
            border-top: 1px solid var(--gray-200);
        }}
        .total-row {{
            display: flex;
            justify-content: flex-end;
            gap: 48px;
            padding: 8px 0;
            font-size: 14px;
        }}
        .total-row .label {{
            color: var(--gray-600);
            min-width: 120px;
            text-align: right;
        }}
        .total-row .value {{
            min-width: 100px;
            text-align: right;
            font-weight: 500;
            color: var(--gray-800);
        }}
        .total-row.grand-total {{
            padding-top: 12px;
            margin-top: 8px;
            border-top: 2px solid var(--gray-300);
            font-size: 18px;
            font-weight: 700;
        }}
        .total-row.grand-total .value {{
            color: var(--primary);
        }}
        .document-notes {{
            padding: 24px;
            border-top: 1px solid var(--gray-200);
        }}
        .notes-title {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--gray-500);
            margin-bottom: 8px;
        }}
        .notes-content {{
            font-size: 14px;
            color: var(--gray-600);
            line-height: 1.6;
        }}
        .document-actions {{
            display: flex;
            gap: 12px;
            justify-content: center;
            padding: 32px;
            background: var(--gray-50);
            border-top: 1px solid var(--gray-200);
        }}
        .btn-lg {{
            padding: 12px 24px;
            font-size: 15px;
        }}
        .portal-footer {{
            text-align: center;
            padding: 32px;
            color: var(--gray-400);
            font-size: 12px;
        }}
        .status-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
        }}
        .status-brouillon {{ background: var(--gray-100); color: var(--gray-600); }}
        .status-envoye {{ background: var(--info-light); color: var(--info); }}
        .status-accepte, .status-validee, .status-payee {{ background: var(--success-light); color: var(--success); }}
        .status-refuse, .status-annulee {{ background: var(--error-light); color: var(--error); }}
        .alert {{
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 24px;
            font-size: 14px;
        }}
        .alert-success {{
            background: var(--success-light);
            color: #065F46;
            border: 1px solid #A7F3D0;
        }}
        .alert-error {{
            background: var(--error-light);
            color: #991B1B;
            border: 1px solid #FECACA;
        }}
        .alert-info {{
            background: var(--info-light);
            color: #1E40AF;
            border: 1px solid #BFDBFE;
        }}
        @media print {{
            .document-actions, .portal-footer {{
                display: none;
            }}
            .portal-container {{
                margin: 0;
                padding: 0;
            }}
        }}
    </style>
</head>
<body style="background: var(--gray-100);">
    {content}
</body>
</html>'''


def render_devis_view(doc: dict, message: Optional[str] = None, message_type: str = "info") -> str:
    """Render le template de visualisation d'un devis."""

    # Formater les lignes
    lignes = doc.get("lignes") or []
    lignes_html = ""

    if isinstance(lignes, list):
        for ligne in lignes:
            description = ligne.get("description", "")
            quantite = ligne.get("quantite", 1)
            prix_unitaire = ligne.get("prix_unitaire", 0)
            remise = ligne.get("remise", 0)
            total_ligne = quantite * prix_unitaire * (1 - remise / 100)

            lignes_html += f'''
            <tr>
                <td>{description}</td>
                <td class="col-qty">{quantite}</td>
                <td class="col-price">{prix_unitaire:.2f} EUR</td>
                <td class="col-price">{remise}%</td>
                <td class="col-total">{total_ligne:.2f} EUR</td>
            </tr>
            '''

    if not lignes_html:
        lignes_html = '<tr><td colspan="5" style="text-align: center; color: var(--gray-400);">Aucune ligne</td></tr>'

    # Calculer les totaux
    total_ht = doc.get("total_ht") or 0
    tva = doc.get("tva") or 20
    total_ttc = doc.get("total_ttc") or (total_ht * (1 + tva / 100))

    # Statut
    statut = (doc.get("statut") or "BROUILLON").upper()
    statut_class = f"status-{statut.lower().replace('_', '-')}"

    # Dates
    date = doc.get("date") or ""
    if hasattr(date, "strftime"):
        date = date.strftime("%d/%m/%Y")
    validite = doc.get("validite") or ""
    if hasattr(validite, "strftime"):
        validite = validite.strftime("%d/%m/%Y")

    # Message alert
    alert_html = ""
    if message:
        alert_html = f'<div class="alert alert-{message_type}">{message}</div>'

    # Actions (seulement si le devis est en attente)
    actions_html = ""
    if statut == "ENVOYE":
        actions_html = f'''
        <div class="document-actions">
            <button onclick="accepterDevis(true)" class="btn btn-success btn-lg">Accepter le devis</button>
            <button onclick="accepterDevis(false)" class="btn btn-danger btn-lg">Refuser le devis</button>
            <button onclick="window.print()" class="btn btn-secondary btn-lg">Imprimer / PDF</button>
        </div>
        <script>
            async function accepterDevis(accepte) {{
                const commentaire = accepte ? "" : prompt("Motif du refus (optionnel):");
                if (!accepte && commentaire === null) return;

                try {{
                    const res = await fetch(window.location.pathname + '/accepter', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ accepte: accepte, commentaire: commentaire || "" }})
                    }});

                    if (res.ok) {{
                        window.location.reload();
                    }} else {{
                        const data = await res.json();
                        alert(data.detail || 'Erreur lors de la mise a jour');
                    }}
                }} catch (e) {{
                    alert('Erreur de connexion');
                }}
            }}
        </script>
        '''
    elif statut == "ACCEPTE":
        actions_html = '''
        <div class="document-actions">
            <div class="alert alert-success" style="margin: 0;">Vous avez accepte ce devis</div>
            <button onclick="window.print()" class="btn btn-secondary btn-lg">Imprimer / PDF</button>
        </div>
        '''
    elif statut == "REFUSE":
        actions_html = '''
        <div class="document-actions">
            <div class="alert alert-error" style="margin: 0;">Ce devis a ete refuse</div>
            <button onclick="window.print()" class="btn btn-secondary btn-lg">Imprimer / PDF</button>
        </div>
        '''
    else:
        actions_html = '''
        <div class="document-actions">
            <button onclick="window.print()" class="btn btn-secondary btn-lg">Imprimer / PDF</button>
        </div>
        '''

    content = f'''
    <div class="portal-container">
        <div class="portal-header">
            <div>
                <div class="portal-logo">AZALPLUS</div>
                <div style="font-size: 13px; color: var(--gray-500); margin-top: 4px;">Portail Client</div>
            </div>
            <div class="portal-company">
                <div class="portal-company-name">{doc.get("tenant_nom", "")}</div>
                <div class="portal-company-details">
                    {doc.get("tenant_adresse", "") or ""}<br>
                    {doc.get("tenant_email", "") or ""} - {doc.get("tenant_telephone", "") or ""}<br>
                    {f'SIRET: {doc.get("tenant_siret")}' if doc.get("tenant_siret") else ""}
                </div>
            </div>
        </div>

        {alert_html}

        <div class="document-card">
            <div class="document-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div class="document-type">Devis</div>
                        <div class="document-number">{doc.get("numero", "N/A")}</div>
                    </div>
                    <div class="status-indicator {statut_class}">{statut}</div>
                </div>
            </div>

            <div class="document-meta">
                <div class="meta-block">
                    <div class="meta-label">Client</div>
                    <div class="meta-value">
                        <strong>{doc.get("client_nom", "N/A")}</strong><br>
                        {doc.get("client_adresse", "") or ""}<br>
                        {doc.get("client_email", "") or ""}
                    </div>
                </div>
                <div class="meta-block" style="text-align: right;">
                    <div class="meta-label">Date du devis</div>
                    <div class="meta-value">{date}</div>
                    <div class="meta-label" style="margin-top: 12px;">Valide jusqu'au</div>
                    <div class="meta-value">{validite}</div>
                </div>
            </div>

            <div class="document-lines">
                <table class="lines-table">
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th class="col-qty">Quantite</th>
                            <th class="col-price">Prix unitaire</th>
                            <th class="col-price">Remise</th>
                            <th class="col-total">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lignes_html}
                    </tbody>
                </table>
            </div>

            <div class="document-totals">
                <div class="total-row">
                    <span class="label">Total HT</span>
                    <span class="value">{total_ht:.2f} EUR</span>
                </div>
                <div class="total-row">
                    <span class="label">TVA ({tva}%)</span>
                    <span class="value">{(total_ttc - total_ht):.2f} EUR</span>
                </div>
                <div class="total-row grand-total">
                    <span class="label">Total TTC</span>
                    <span class="value">{total_ttc:.2f} EUR</span>
                </div>
            </div>

            {f'<div class="document-notes"><div class="notes-title">Objet</div><div class="notes-content">{doc.get("objet", "")}</div></div>' if doc.get("objet") else ""}

            {f'<div class="document-notes"><div class="notes-title">Notes</div><div class="notes-content">{doc.get("notes", "")}</div></div>' if doc.get("notes") else ""}

            {f'<div class="document-notes"><div class="notes-title">Conditions</div><div class="notes-content">{doc.get("conditions", "")}</div></div>' if doc.get("conditions") else ""}

            {_render_signature_section(doc, "devis")}

            {actions_html}
        </div>

        <div class="portal-footer">
            Document genere par AZALPLUS - Ce lien est confidentiel et personnel.
        </div>
    </div>
    '''

    return render_portal_base(f"Devis {doc.get('numero', '')}", content)


def _render_signature_section(doc: dict, doc_type: str = "devis") -> str:
    """Render la section signature pour un document."""

    signature = doc.get("signature_client")
    signature_date = doc.get("signature_date")
    signature_ip = doc.get("signature_ip")
    access_token = doc.get("access_token", "")

    if signature:
        # Document signe - afficher la signature
        date_str = format_signature_date(signature_date) if signature_date else "Date inconnue"

        return f'''
        <div class="document-notes" style="background: var(--success-light); border-left: 3px solid var(--success);">
            <div class="notes-title" style="color: var(--success);">Signature electronique</div>
            <div style="display: flex; gap: 24px; align-items: flex-start;">
                <div style="flex: 1;">
                    <div style="font-size: 14px; color: #065F46; margin-bottom: 8px;">
                        Document signe electroniquement
                    </div>
                    <div style="font-size: 12px; color: var(--gray-600);">
                        Date: {date_str}<br>
                        IP: {signature_ip or "Non enregistree"}
                    </div>
                </div>
                <div style="flex-shrink: 0;">
                    <img src="{signature}" alt="Signature" style="max-width: 200px; max-height: 80px; border: 1px solid var(--gray-200); border-radius: 4px; background: white;"/>
                </div>
            </div>
        </div>
        '''
    else:
        # Document non signe - afficher badge et bouton
        statut = (doc.get("statut") or "").upper()
        can_sign = statut in ["ENVOYE", "ACCEPTE"] if doc_type == "devis" else True

        if can_sign:
            return f'''
            <div class="document-notes" style="background: var(--gray-50);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 500; background: var(--gray-200); color: var(--gray-600);">
                            Non signe
                        </span>
                        <span style="font-size: 13px; color: var(--gray-500); margin-left: 12px;">
                            Ce document n'a pas encore ete signe
                        </span>
                    </div>
                    <a href="/{doc_type}/{access_token}/signer" class="btn btn-primary">
                        Signer ce document
                    </a>
                </div>
            </div>
            '''
        else:
            return '''
            <div class="document-notes" style="background: var(--gray-50);">
                <span style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 500; background: var(--gray-200); color: var(--gray-600);">
                    Non signe
                </span>
            </div>
            '''


def render_facture_view(doc: dict) -> str:
    """Render le template de visualisation d'une facture."""

    # Formater les lignes
    lignes = doc.get("lignes") or []
    lignes_html = ""

    if isinstance(lignes, list):
        for ligne in lignes:
            description = ligne.get("description", "")
            quantite = ligne.get("quantite", 1)
            prix_unitaire = ligne.get("prix_unitaire", 0)
            remise = ligne.get("remise", 0)
            total_ligne = quantite * prix_unitaire * (1 - remise / 100)

            lignes_html += f'''
            <tr>
                <td>{description}</td>
                <td class="col-qty">{quantite}</td>
                <td class="col-price">{prix_unitaire:.2f} EUR</td>
                <td class="col-price">{remise}%</td>
                <td class="col-total">{total_ligne:.2f} EUR</td>
            </tr>
            '''

    if not lignes_html:
        lignes_html = '<tr><td colspan="5" style="text-align: center; color: var(--gray-400);">Aucune ligne</td></tr>'

    # Calculer les totaux
    total_ht = doc.get("total_ht") or 0
    tva = doc.get("tva") or 20
    total_ttc = doc.get("total_ttc") or (total_ht * (1 + tva / 100))
    montant_paye = doc.get("montant_paye") or 0
    reste_a_payer = total_ttc - montant_paye

    # Statut
    statut = (doc.get("statut") or "BROUILLON").upper()
    statut_class = f"status-{statut.lower().replace('_', '-')}"

    # Dates
    date = doc.get("date") or ""
    if hasattr(date, "strftime"):
        date = date.strftime("%d/%m/%Y")
    echeance = doc.get("echeance") or ""
    if hasattr(echeance, "strftime"):
        echeance = echeance.strftime("%d/%m/%Y")

    # Paiement info
    paiement_html = ""
    if montant_paye > 0:
        paiement_html = f'''
        <div class="total-row">
            <span class="label">Deja paye</span>
            <span class="value" style="color: var(--success);">-{montant_paye:.2f} EUR</span>
        </div>
        <div class="total-row grand-total">
            <span class="label">Reste a payer</span>
            <span class="value">{reste_a_payer:.2f} EUR</span>
        </div>
        '''
    else:
        paiement_html = f'''
        <div class="total-row grand-total">
            <span class="label">A payer</span>
            <span class="value">{total_ttc:.2f} EUR</span>
        </div>
        '''

    content = f'''
    <div class="portal-container">
        <div class="portal-header">
            <div>
                <div class="portal-logo">AZALPLUS</div>
                <div style="font-size: 13px; color: var(--gray-500); margin-top: 4px;">Portail Client</div>
            </div>
            <div class="portal-company">
                <div class="portal-company-name">{doc.get("tenant_nom", "")}</div>
                <div class="portal-company-details">
                    {doc.get("tenant_adresse", "") or ""}<br>
                    {doc.get("tenant_email", "") or ""} - {doc.get("tenant_telephone", "") or ""}<br>
                    {f'SIRET: {doc.get("tenant_siret")}' if doc.get("tenant_siret") else ""}
                </div>
            </div>
        </div>

        <div class="document-card">
            <div class="document-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div class="document-type">Facture</div>
                        <div class="document-number">{doc.get("numero", "N/A")}</div>
                    </div>
                    <div class="status-indicator {statut_class}">{statut}</div>
                </div>
            </div>

            <div class="document-meta">
                <div class="meta-block">
                    <div class="meta-label">Client</div>
                    <div class="meta-value">
                        <strong>{doc.get("client_nom", "N/A")}</strong><br>
                        {doc.get("client_adresse", "") or ""}<br>
                        {doc.get("client_email", "") or ""}
                    </div>
                </div>
                <div class="meta-block" style="text-align: right;">
                    <div class="meta-label">Date de facturation</div>
                    <div class="meta-value">{date}</div>
                    <div class="meta-label" style="margin-top: 12px;">Date d'echeance</div>
                    <div class="meta-value">{echeance}</div>
                </div>
            </div>

            <div class="document-lines">
                <table class="lines-table">
                    <thead>
                        <tr>
                            <th>Description</th>
                            <th class="col-qty">Quantite</th>
                            <th class="col-price">Prix unitaire</th>
                            <th class="col-price">Remise</th>
                            <th class="col-total">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lignes_html}
                    </tbody>
                </table>
            </div>

            <div class="document-totals">
                <div class="total-row">
                    <span class="label">Total HT</span>
                    <span class="value">{total_ht:.2f} EUR</span>
                </div>
                <div class="total-row">
                    <span class="label">TVA ({tva}%)</span>
                    <span class="value">{(total_ttc - total_ht):.2f} EUR</span>
                </div>
                <div class="total-row">
                    <span class="label">Total TTC</span>
                    <span class="value">{total_ttc:.2f} EUR</span>
                </div>
                {paiement_html}
            </div>

            {f'<div class="document-notes"><div class="notes-title">Objet</div><div class="notes-content">{doc.get("objet", "")}</div></div>' if doc.get("objet") else ""}

            {f'<div class="document-notes"><div class="notes-title">Notes</div><div class="notes-content">{doc.get("notes", "")}</div></div>' if doc.get("notes") else ""}

            {_render_signature_section(doc, "facture")}

            <div class="document-actions">
                <button onclick="window.print()" class="btn btn-secondary btn-lg">Imprimer / PDF</button>
            </div>
        </div>

        <div class="portal-footer">
            Document genere par AZALPLUS - Ce lien est confidentiel et personnel.
        </div>
    </div>
    '''

    return render_portal_base(f"Facture {doc.get('numero', '')}", content)


def render_error_page(title: str, message: str) -> str:
    """Render une page d'erreur."""

    content = f'''
    <div class="portal-container">
        <div class="portal-header" style="justify-content: center;">
            <div style="text-align: center;">
                <div class="portal-logo">AZALPLUS</div>
                <div style="font-size: 13px; color: var(--gray-500); margin-top: 4px;">Portail Client</div>
            </div>
        </div>

        <div class="document-card" style="text-align: center; padding: 48px;">
            <div style="font-size: 48px; opacity: 0.3; margin-bottom: 16px;">:(</div>
            <div style="font-size: 20px; font-weight: 600; color: var(--gray-800); margin-bottom: 8px;">{title}</div>
            <div style="font-size: 14px; color: var(--gray-500);">{message}</div>
        </div>

        <div class="portal-footer">
            AZALPLUS - Portail Client
        </div>
    </div>
    '''

    return render_portal_base(title, content)


def render_signature_page(doc: dict, doc_type: str = "devis") -> str:
    """Render la page de signature electronique."""

    numero = doc.get("numero", "N/A")
    total_ttc = doc.get("total_ttc") or 0
    client_nom = doc.get("client_nom", "")

    # Determine doc label
    doc_label = "Devis" if doc_type == "devis" else "Facture"

    content = f'''
    <div class="portal-container">
        <div class="portal-header">
            <div>
                <div class="portal-logo">AZALPLUS</div>
                <div style="font-size: 13px; color: var(--gray-500); margin-top: 4px;">Signature Electronique</div>
            </div>
            <div class="portal-company">
                <div class="portal-company-name">{doc.get("tenant_nom", "")}</div>
            </div>
        </div>

        <div class="document-card">
            <div class="document-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div class="document-type">{doc_label}</div>
                        <div class="document-number">{numero}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 18px; font-weight: 700; color: var(--primary);">{total_ttc:.2f} EUR</div>
                    </div>
                </div>
            </div>

            <div style="padding: 24px;">
                <div class="alert alert-info">
                    En signant ce document, vous acceptez les termes et conditions decrits dans le {doc_label.lower()} {numero}.
                    Votre signature sera enregistree avec votre adresse IP et l'horodatage.
                </div>

                <div style="margin-bottom: 24px;">
                    <div class="meta-label">Client</div>
                    <div class="meta-value"><strong>{client_nom}</strong></div>
                </div>

                <div style="margin-bottom: 16px;">
                    <div class="meta-label">Votre signature</div>
                    <div style="margin-top: 8px; border: 2px solid var(--gray-300); border-radius: 8px; background: white; position: relative;">
                        <canvas id="signature-pad" style="width: 100%; height: 200px; touch-action: none;"></canvas>
                        <button type="button" id="clear-btn" style="position: absolute; top: 8px; right: 8px; background: var(--gray-100); border: none; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer;">
                            Effacer
                        </button>
                    </div>
                    <div style="font-size: 11px; color: var(--gray-400); margin-top: 8px;">
                        Utilisez votre souris ou votre doigt pour signer dans le cadre ci-dessus
                    </div>
                </div>
            </div>

            <div class="document-actions">
                <button onclick="submitSignature()" id="submit-btn" class="btn btn-success btn-lg">Valider ma signature</button>
                <a href="/{doc_type}/{doc.get('access_token', '')}" class="btn btn-secondary btn-lg">Annuler</a>
            </div>
        </div>

        <div class="portal-footer">
            Document genere par AZALPLUS - Signature electronique securisee
        </div>
    </div>

    <!-- Signature Pad Library -->
    <script src="https://cdn.jsdelivr.net/npm/signature_pad@4.1.5/dist/signature_pad.umd.min.js"></script>
    <script>
        // Initialize signature pad
        const canvas = document.getElementById('signature-pad');
        const signaturePad = new SignaturePad(canvas, {{
            backgroundColor: 'rgb(255, 255, 255)',
            penColor: 'rgb(0, 0, 0)',
            minWidth: 0.5,
            maxWidth: 2.5
        }});

        // Resize canvas to fit container
        function resizeCanvas() {{
            const ratio = Math.max(window.devicePixelRatio || 1, 1);
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width * ratio;
            canvas.height = rect.height * ratio;
            canvas.getContext("2d").scale(ratio, ratio);
            signaturePad.clear();
        }}

        window.addEventListener("resize", resizeCanvas);
        resizeCanvas();

        // Clear button
        document.getElementById('clear-btn').addEventListener('click', function() {{
            signaturePad.clear();
        }});

        // Submit signature
        async function submitSignature() {{
            if (signaturePad.isEmpty()) {{
                alert('Veuillez signer avant de valider');
                return;
            }}

            const submitBtn = document.getElementById('submit-btn');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Envoi en cours...';

            try {{
                const signatureData = signaturePad.toDataURL('image/png');

                const response = await fetch(window.location.pathname, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        signature: signatureData
                    }})
                }});

                const result = await response.json();

                if (response.ok) {{
                    alert('Signature enregistree avec succes !');
                    window.location.href = '/{doc_type}/' + '{doc.get("access_token", "")}';
                }} else {{
                    alert(result.detail || 'Erreur lors de l\\'enregistrement de la signature');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Valider ma signature';
                }}
            }} catch (error) {{
                alert('Erreur de connexion');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Valider ma signature';
            }}
        }}
    </script>
    '''

    return render_portal_base(f"Signer {doc_label} {numero}", content)


def format_signature_date(dt: datetime) -> str:
    """Formate une date de signature pour l'affichage."""
    if dt is None:
        return ""
    if hasattr(dt, "strftime"):
        return dt.strftime("%d/%m/%Y a %H:%M")
    return str(dt)


# =============================================================================
# Routes - Devis
# =============================================================================
@portal_router.get("/devis/{token}", response_class=HTMLResponse)
async def view_devis(token: str, request: Request):
    """Affiche un devis via son token d'acces public."""

    logger.info("portal_devis_view", token=token[:8] + "...")

    doc = get_document_by_token("devis", token)

    if not doc:
        return HTMLResponse(
            content=render_error_page(
                "Document introuvable",
                "Ce lien n'est plus valide ou le document n'existe pas."
            ),
            status_code=404
        )

    return HTMLResponse(content=render_devis_view(doc))


@portal_router.post("/devis/{token}/accepter")
async def accept_devis(token: str, data: AcceptDevisRequest):
    """Accepte ou refuse un devis via son token."""

    logger.info("portal_devis_action", token=token[:8] + "...", accepte=data.accepte)

    doc = get_document_by_token("devis", token)

    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    # Verifier que le devis est en attente
    if doc.get("statut") != "ENVOYE":
        raise HTTPException(
            status_code=400,
            detail="Ce devis ne peut plus etre modifie"
        )

    # Mettre a jour le statut
    new_status = "ACCEPTE" if data.accepte else "REFUSE"

    with Database.get_session() as session:
        from sqlalchemy import text

        session.execute(
            text("""
                UPDATE azalplus.devis
                SET statut = :statut, updated_at = NOW()
                WHERE access_token = :token
            """),
            {"statut": new_status, "token": token}
        )
        session.commit()

    message = "Devis accepte avec succes" if data.accepte else "Devis refuse"

    return JSONResponse(content={
        "status": "success",
        "message": message,
        "new_status": new_status
    })


# =============================================================================
# Routes - Signature Devis
# =============================================================================
@portal_router.get("/devis/{token}/signer", response_class=HTMLResponse)
async def sign_devis_page(token: str, request: Request):
    """Affiche la page de signature electronique pour un devis."""

    logger.info("portal_devis_sign_page", token=token[:8] + "...")

    doc = get_document_by_token("devis", token)

    if not doc:
        return HTMLResponse(
            content=render_error_page(
                "Document introuvable",
                "Ce lien n'est plus valide ou le document n'existe pas."
            ),
            status_code=404
        )

    # Verifier si deja signe
    if doc.get("signature_client"):
        return HTMLResponse(
            content=render_error_page(
                "Document deja signe",
                f"Ce devis a deja ete signe le {format_signature_date(doc.get('signature_date'))}."
            ),
            status_code=400
        )

    # Verifier que le devis peut etre signe (statut ENVOYE ou ACCEPTE)
    statut = (doc.get("statut") or "").upper()
    if statut not in ["ENVOYE", "ACCEPTE"]:
        return HTMLResponse(
            content=render_error_page(
                "Signature non disponible",
                "Ce devis ne peut pas etre signe dans son etat actuel."
            ),
            status_code=400
        )

    return HTMLResponse(content=render_signature_page(doc, "devis"))


@portal_router.post("/devis/{token}/signer")
async def sign_devis(token: str, data: SignatureRequest, request: Request):
    """Enregistre la signature electronique d'un devis."""

    logger.info("portal_devis_sign", token=token[:8] + "...")

    doc = get_document_by_token("devis", token)

    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    # Verifier si deja signe
    if doc.get("signature_client"):
        raise HTTPException(status_code=400, detail="Ce document a deja ete signe")

    # Verifier le statut
    statut = (doc.get("statut") or "").upper()
    if statut not in ["ENVOYE", "ACCEPTE"]:
        raise HTTPException(
            status_code=400,
            detail="Ce devis ne peut pas etre signe dans son etat actuel"
        )

    # Valider la signature (doit etre une image base64)
    if not data.signature or not data.signature.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Signature invalide")

    # Recuperer l'adresse IP du client
    client_ip = request.client.host if request.client else "unknown"
    # Support pour X-Forwarded-For si derriere un proxy
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    # Enregistrer la signature
    with Database.get_session() as session:
        from sqlalchemy import text

        session.execute(
            text("""
                UPDATE azalplus.devis
                SET signature_client = :signature,
                    signature_date = NOW(),
                    signature_ip = :ip,
                    statut = CASE WHEN statut = 'ENVOYE' THEN 'ACCEPTE' ELSE statut END,
                    updated_at = NOW()
                WHERE access_token = :token
            """),
            {
                "signature": data.signature,
                "ip": client_ip,
                "token": token
            }
        )
        session.commit()

    logger.info(
        "portal_devis_signed",
        token=token[:8] + "...",
        client_ip=client_ip
    )

    return JSONResponse(content={
        "status": "success",
        "message": "Signature enregistree avec succes"
    })


# =============================================================================
# Routes - Signature Factures
# =============================================================================
@portal_router.get("/facture/{token}/signer", response_class=HTMLResponse)
async def sign_facture_page(token: str, request: Request):
    """Affiche la page de signature electronique pour une facture."""

    logger.info("portal_facture_sign_page", token=token[:8] + "...")

    doc = get_document_by_token("factures", token)

    if not doc:
        return HTMLResponse(
            content=render_error_page(
                "Document introuvable",
                "Ce lien n'est plus valide ou le document n'existe pas."
            ),
            status_code=404
        )

    # Verifier si deja signe
    if doc.get("signature_client"):
        return HTMLResponse(
            content=render_error_page(
                "Document deja signe",
                f"Cette facture a deja ete signee le {format_signature_date(doc.get('signature_date'))}."
            ),
            status_code=400
        )

    return HTMLResponse(content=render_signature_page(doc, "facture"))


@portal_router.post("/facture/{token}/signer")
async def sign_facture(token: str, data: SignatureRequest, request: Request):
    """Enregistre la signature electronique d'une facture."""

    logger.info("portal_facture_sign", token=token[:8] + "...")

    doc = get_document_by_token("factures", token)

    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    # Verifier si deja signe
    if doc.get("signature_client"):
        raise HTTPException(status_code=400, detail="Ce document a deja ete signe")

    # Valider la signature (doit etre une image base64)
    if not data.signature or not data.signature.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Signature invalide")

    # Recuperer l'adresse IP du client
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    # Enregistrer la signature
    with Database.get_session() as session:
        from sqlalchemy import text

        session.execute(
            text("""
                UPDATE azalplus.factures
                SET signature_client = :signature,
                    signature_date = NOW(),
                    signature_ip = :ip,
                    updated_at = NOW()
                WHERE access_token = :token
            """),
            {
                "signature": data.signature,
                "ip": client_ip,
                "token": token
            }
        )
        session.commit()

    logger.info(
        "portal_facture_signed",
        token=token[:8] + "...",
        client_ip=client_ip
    )

    return JSONResponse(content={
        "status": "success",
        "message": "Signature enregistree avec succes"
    })


# =============================================================================
# Routes - Factures
# =============================================================================
@portal_router.get("/facture/{token}", response_class=HTMLResponse)
async def view_facture(token: str, request: Request):
    """Affiche une facture via son token d'acces public."""

    logger.info("portal_facture_view", token=token[:8] + "...")

    doc = get_document_by_token("factures", token)

    if not doc:
        return HTMLResponse(
            content=render_error_page(
                "Document introuvable",
                "Ce lien n'est plus valide ou le document n'existe pas."
            ),
            status_code=404
        )

    return HTMLResponse(content=render_facture_view(doc))


# =============================================================================
# API Routes - Token Generation (pour usage interne avec auth)
# =============================================================================
@portal_router.get("/api/devis/{document_id}/token")
async def get_devis_portal_token(
    document_id: UUID,
    request: Request
):
    """Genere ou recupere le token d'acces portail pour un devis.

    Note: Cette route devrait normalement etre protegee par authentification.
    Elle est utilisee par l'application pour generer des liens de partage.
    """
    from .tenant import get_current_tenant
    from .auth import require_auth

    # En production, ajouter: user = Depends(require_auth), tenant_id = Depends(get_current_tenant)
    # Pour simplifier l'exemple, on recupere le tenant_id depuis le document

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text("SELECT tenant_id FROM azalplus.devis WHERE id = :id AND deleted_at IS NULL"),
            {"id": str(document_id)}
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Document non trouve")

        tenant_id = row[0]

    token = create_access_token_for_document("devis", tenant_id, document_id)

    base_url = str(request.base_url).rstrip("/")
    portal_url = f"{base_url}/portail/devis/{token}"

    return {
        "token": token,
        "url": portal_url
    }


@portal_router.get("/api/facture/{document_id}/token")
async def get_facture_portal_token(
    document_id: UUID,
    request: Request
):
    """Genere ou recupere le token d'acces portail pour une facture."""

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text("SELECT tenant_id FROM azalplus.factures WHERE id = :id AND deleted_at IS NULL"),
            {"id": str(document_id)}
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Document non trouve")

        tenant_id = row[0]

    token = create_access_token_for_document("factures", tenant_id, document_id)

    base_url = str(request.base_url).rstrip("/")
    portal_url = f"{base_url}/portail/facture/{token}"

    return {
        "token": token,
        "url": portal_url
    }
