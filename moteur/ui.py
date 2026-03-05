# =============================================================================
# AZALPLUS - UI Generator
# =============================================================================
"""
Génère l'interface HTML depuis les définitions YAML.
Utilise Jinja2 pour le templating.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

from .parser import ModuleParser, ModuleDefinition, FieldDefinition
from .auth import get_current_user, require_auth
from .tenant import get_current_tenant
from .db import Database
from .config import settings
from .reports import ReportEngine
from datetime import date, timedelta

logger = structlog.get_logger()

# =============================================================================
# Jinja2 Environment
# =============================================================================
templates_dir = Path(__file__).parent.parent / "templates" / "ui"
templates_dir.mkdir(parents=True, exist_ok=True)

jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True
)

# =============================================================================
# UI Router
# =============================================================================
ui_router = APIRouter()

# =============================================================================
# Helpers
# =============================================================================
def get_field_html(field: FieldDefinition, value: Any = None, is_custom: bool = False, module_name: str = "") -> str:
    """Génère le HTML d'un champ de formulaire."""

    field_id = f"field_{field.nom}"
    required = "required" if field.requis else ""
    label = field.label or field.nom.replace("_", " ").title()
    placeholder = getattr(field, 'placeholder', None) or ""
    help_text = f'<small class="form-help">{field.aide}</small>' if field.aide else ""
    custom_class = "custom-field" if is_custom or getattr(field, 'is_custom', False) else ""
    groupe = getattr(field, 'groupe', None) or ""

    # Type de champ
    if field.type == "texte long" or field.type == "textarea":
        return f'''
        <div class="form-group {custom_class}" data-groupe="{groupe}">
            <label class="label" for="{field_id}">{label}</label>
            <textarea class="input" id="{field_id}" name="{field.nom}" rows="4" {required} placeholder="{placeholder}">{value or ''}</textarea>
            {help_text}
        </div>
        '''

    elif field.type == "enum" and field.enum_values:
        options = "".join([
            f'<option value="{v}" {"selected" if v == value else ""}>{v}</option>'
            for v in field.enum_values
        ])
        return f'''
        <div class="form-group">
            <label class="label" for="{field_id}">{label}</label>
            <select class="input" id="{field_id}" name="{field.nom}" {required}>
                <option value="">-- Sélectionner --</option>
                {options}
            </select>
        </div>
        '''

    elif field.type == "oui/non" or field.type == "booleen":
        checked = "checked" if value else ""
        return f'''
        <div class="form-group">
            <label class="flex items-center gap-2">
                <input type="checkbox" id="{field_id}" name="{field.nom}" {checked}>
                <span>{label}</span>
            </label>
        </div>
        '''

    elif field.type == "date":
        return f'''
        <div class="form-group">
            <label class="label" for="{field_id}">{label}</label>
            <input type="date" class="input" id="{field_id}" name="{field.nom}" value="{value or ''}" {required}>
        </div>
        '''

    elif field.type == "datetime":
        return f'''
        <div class="form-group">
            <label class="label" for="{field_id}">{label}</label>
            <input type="datetime-local" class="input" id="{field_id}" name="{field.nom}" value="{value or ''}" {required}>
        </div>
        '''

    elif field.type in ["nombre", "entier", "monnaie", "pourcentage"]:
        step = "0.01" if field.type in ["nombre", "monnaie", "pourcentage"] else "1"
        min_attr = f'min="{field.min}"' if field.min is not None else ""
        max_attr = f'max="{field.max}"' if field.max is not None else ""
        return f'''
        <div class="form-group">
            <label class="label" for="{field_id}">{label}</label>
            <input type="number" class="input" id="{field_id}" name="{field.nom}"
                   step="{step}" {min_attr} {max_attr} value="{value or ''}" {required}>
        </div>
        '''

    elif field.type == "email":
        return f'''
        <div class="form-group">
            <label class="label" for="{field_id}">{label}</label>
            <input type="email" class="input" id="{field_id}" name="{field.nom}" value="{value or ''}" {required}>
        </div>
        '''

    elif field.type in ["lien", "relation"]:
        # Pour les liens/relations, on génère un select avec option de création
        linked_module = field.lien_vers or getattr(field, 'relation', '') or ""
        return f'''
        <div class="form-group">
            <label class="label" for="{field_id}">{label}</label>
            <div class="select-with-create">
                <select class="input" id="{field_id}" name="{field.nom}" data-link="{linked_module}" {required}>
                    <option value="">-- Sélectionner --</option>
                </select>
                <button type="button" class="btn-create-inline" onclick="openCreateModal('{linked_module}', '{field_id}')" title="Créer nouveau">
                    +
                </button>
            </div>
        </div>
        '''

    else:  # texte par défaut
        # Vérifier si autocomplétion IA est activée pour ce champ
        has_autocompletion = getattr(field, 'autocompletion', False)

        if has_autocompletion:
            # Input avec autocomplétion IA
            return f'''
            <div class="form-group autocomplete-container">
                <label class="label" for="{field_id}">{label}</label>
                <div class="autocomplete-wrapper">
                    <input type="text" class="input autocomplete-input" id="{field_id}" name="{field.nom}"
                           value="{value or ''}" {required}
                           data-autocomplete="true" data-module="{module_name}" data-champ="{field.nom}"
                           autocomplete="off">
                    <div class="autocomplete-suggestions" id="{field_id}_suggestions"></div>
                    <span class="autocomplete-indicator" title="Autocomplétion IA">✨</span>
                </div>
            </div>
            '''
        else:
            return f'''
            <div class="form-group">
                <label class="label" for="{field_id}">{label}</label>
                <input type="text" class="input" id="{field_id}" name="{field.nom}" value="{value or ''}" {required}>
            </div>
            '''


def get_status_badge(statut: str) -> str:
    """Génère le badge de statut."""
    colors = {
        "BROUILLON": "gray",
        "ENVOYE": "primary",
        "ENVOYEE": "primary",
        "VALIDEE": "primary",
        "ACCEPTE": "success",
        "PAYEE": "success",
        "TERMINEE": "success",
        "REFUSE": "error",
        "ANNULEE": "error",
        "ANNULE": "error",
        "BLOQUEE": "warning",
        "EN_COURS": "primary",
        "PLANIFIEE": "primary",
        "A_PLANIFIER": "warning",
    }
    color = colors.get(statut, "gray")
    return f'<span class="badge badge-{color}">{statut}</span>'


def generate_documents_section(module_name: str, item_id: str) -> str:
    """Génère la section de gestion des documents attachés."""
    return f'''
    <div class="card" style="margin-top: 24px;">
        <div class="card-header">
            <h3 class="font-bold">Documents attaches</h3>
        </div>
        <div class="card-body">
            <!-- Upload Zone -->
            <div class="upload-zone" id="upload-zone">
                <div class="upload-content">
                    <div class="upload-icon">📎</div>
                    <p class="upload-text">Glissez un fichier ici ou</p>
                    <label class="btn btn-secondary btn-sm" for="file-input">
                        Parcourir
                    </label>
                    <input type="file" id="file-input" style="display: none;" onchange="uploadDocument()">
                </div>
            </div>

            <!-- Documents List -->
            <div id="documents-list" style="margin-top: 16px;">
                <p class="text-muted">Chargement...</p>
            </div>
        </div>
    </div>

    <!-- Notification -->
    <div id="doc-notification" class="notification hidden"></div>

    <style>
        .upload-zone {{
            border: 2px dashed var(--gray-300);
            border-radius: 8px;
            padding: 24px;
            text-align: center;
            background: var(--gray-50);
            transition: all 0.2s;
        }}
        .upload-zone:hover, .upload-zone.dragover {{
            border-color: var(--primary);
            background: var(--primary-light);
        }}
        .upload-icon {{
            font-size: 32px;
            margin-bottom: 8px;
        }}
        .upload-text {{
            color: var(--gray-500);
            margin-bottom: 8px;
        }}
        .documents-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .document-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            border: 1px solid var(--gray-200);
            border-radius: 6px;
            margin-bottom: 8px;
            background: white;
        }}
        .document-item:hover {{
            background: var(--gray-50);
        }}
        .doc-icon {{
            font-size: 24px;
        }}
        .doc-info {{
            flex: 1;
        }}
        .doc-name {{
            font-weight: 500;
            color: var(--gray-800);
        }}
        .doc-meta {{
            font-size: 12px;
            color: var(--gray-500);
            display: block;
            margin-top: 2px;
        }}
        .doc-actions {{
            display: flex;
            gap: 8px;
        }}
    </style>

    <script>
    // Drag and drop support
    const uploadZone = document.getElementById('upload-zone');

    uploadZone.addEventListener('dragover', (e) => {{
        e.preventDefault();
        uploadZone.classList.add('dragover');
    }});

    uploadZone.addEventListener('dragleave', () => {{
        uploadZone.classList.remove('dragover');
    }});

    uploadZone.addEventListener('drop', async (e) => {{
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {{
            await uploadFileObject(files[0]);
        }}
    }});

    async function uploadFileObject(file) {{
        const formData = new FormData();
        formData.append('file', file);

        try {{
            const res = await fetch('/api/{module_name}/{item_id}/documents', {{
                method: 'POST',
                credentials: 'include',
                body: formData
            }});

            if (res.ok) {{
                loadDocuments();
                showNotification('Document uploade avec succes', 'success');
            }} else {{
                const data = await res.json();
                showNotification(data.detail || 'Erreur upload', 'error');
            }}
        }} catch (e) {{
            showNotification('Erreur de connexion', 'error');
        }}
    }}
    </script>
    '''


# =============================================================================
# Routes UI
# =============================================================================

@ui_router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(require_auth)):
    """Page d'accueil / Dashboard avec indicateurs financiers."""
    from .db import Database
    from .tenant import TenantContext
    from datetime import datetime, timedelta
    import json

    tenant_id = TenantContext.get_tenant_id()

    # Récupérer les modules pour le menu
    modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module:
            modules.append({
                "nom": module.nom,
                "nom_affichage": module.nom_affichage,
                "icone": module.icone,
                "menu": module.menu
            })

    # ===== CALCUL DES INDICATEURS FINANCIERS =====
    today = datetime.now().date()
    debut_mois = today.replace(day=1)
    debut_annee = today.replace(month=1, day=1)

    # Initialiser les valeurs
    ca_mois = 0
    ca_annee = 0
    factures_a_payer = 0
    nb_factures_impayees = 0
    impayes_clients = 0
    nb_impayes_clients = 0
    impayes_fournisseurs = 0
    tresorerie = 0
    tva_a_payer = 0
    nb_factures_payees = 0
    nb_factures_en_attente = 0
    nb_factures_en_retard = 0

    # CA par mois (12 derniers mois)
    ca_par_mois = {i: 0 for i in range(1, 13)}
    mois_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]

    try:
        # CA du mois (factures validées/payées ce mois)
        factures = Database.query("factures", tenant_id, filters={}, limit=1000)
        for f in factures:
            f_date = f.get("date")
            if f_date:
                if isinstance(f_date, str):
                    f_date = datetime.strptime(f_date[:10], "%Y-%m-%d").date()
                elif hasattr(f_date, 'date'):
                    f_date = f_date.date()

                total = float(f.get("total") or f.get("subtotal") or 0)
                status = f.get("status", "").upper()

                # CA = factures validées ou payées
                if status in ["VALIDATED", "PAID", "PAYEE", "VALIDEE", "SENT"]:
                    if f_date >= debut_mois:
                        ca_mois += total
                    if f_date >= debut_annee:
                        ca_annee += total
                        # Ajouter au mois correspondant
                        ca_par_mois[f_date.month] += total

                # Comptage par statut
                if status in ["PAID", "PAYEE"]:
                    nb_factures_payees += 1
                elif status in ["OVERDUE", "EN_RETARD"]:
                    nb_factures_en_retard += 1
                    impayes_clients += total
                    nb_impayes_clients += 1
                elif status in ["VALIDATED", "SENT", "VALIDEE", "ENVOYEE"]:
                    nb_factures_en_attente += 1
                    impayes_clients += total
                    nb_impayes_clients += 1

                # Factures à payer (échéance proche)
                due_date = f.get("due_date")
                if due_date and status not in ["PAID", "PAYEE"]:
                    if isinstance(due_date, str):
                        due_date = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
                    elif hasattr(due_date, 'date'):
                        due_date = due_date.date()
                    if due_date <= today + timedelta(days=30):
                        factures_a_payer += total
                        nb_factures_impayees += 1

                # TVA collectée
                tva = float(f.get("tax_amount") or 0)
                if status in ["VALIDATED", "PAID", "PAYEE", "VALIDEE", "SENT"] and f_date >= debut_mois:
                    tva_a_payer += tva

    except Exception as e:
        logger.warning("dashboard_factures_error", error=str(e))

    try:
        # Trésorerie (solde comptes bancaires)
        comptes = Database.query("comptes_bancaires", tenant_id, filters={}, limit=100)
        for c in comptes:
            tresorerie += float(c.get("solde") or c.get("solde_actuel") or 0)
    except Exception as e:
        logger.warning("dashboard_tresorerie_error", error=str(e))

    try:
        # Impayés fournisseurs (commandes d'achat non payées)
        commandes = Database.query("commandes_achat", tenant_id, filters={}, limit=500)
        for c in commandes:
            status = c.get("statut", "").upper()
            if status in ["RECUE", "VALIDEE", "EN_ATTENTE"]:
                impayes_fournisseurs += float(c.get("total") or c.get("montant_total") or 0)
    except Exception as e:
        logger.warning("dashboard_fournisseurs_error", error=str(e))

    # Données pour les graphiques
    ca_data = json.dumps([ca_par_mois[i] for i in range(1, 13)])
    total_factures = nb_factures_payees + nb_factures_en_attente + nb_factures_en_retard
    if total_factures == 0:
        total_factures = 1  # Éviter division par zéro

    # Formater les montants
    def fmt(val):
        return f"{val:,.2f}".replace(",", " ").replace(".", ",") + " €"

    html = generate_layout(
        title="Tableau de bord",
        content=f'''
        <style>
            .dashboard-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .kpi-card {{
                background: white;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                border-left: 4px solid var(--primary);
            }}
            .kpi-card.success {{ border-left-color: #10B981; }}
            .kpi-card.warning {{ border-left-color: #F59E0B; }}
            .kpi-card.danger {{ border-left-color: #EF4444; }}
            .kpi-card.info {{ border-left-color: #3B82F6; }}
            .kpi-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
            }}
            .kpi-title {{
                font-size: 14px;
                color: #64748B;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .kpi-icon {{
                width: 40px;
                height: 40px;
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #F1F5F9;
            }}
            .kpi-icon svg {{ width: 20px; height: 20px; }}
            .kpi-value {{
                font-size: 28px;
                font-weight: 700;
                color: #1E293B;
                margin-bottom: 4px;
            }}
            .kpi-subtitle {{
                font-size: 13px;
                color: #94A3B8;
            }}
            .kpi-badge {{
                display: inline-block;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
                margin-left: 8px;
            }}
            .kpi-badge.up {{ background: #D1FAE5; color: #059669; }}
            .kpi-badge.down {{ background: #FEE2E2; color: #DC2626; }}
            .section-title {{
                font-size: 18px;
                font-weight: 600;
                color: #1E293B;
                margin: 30px 0 15px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid #E2E8F0;
            }}
            .quick-links {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 12px;
            }}
            .quick-link {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 16px;
                background: white;
                border-radius: 8px;
                text-decoration: none;
                color: #1E293B;
                box-shadow: 0 1px 3px rgba(0,0,0,0.06);
                transition: all 0.2s;
            }}
            .quick-link:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }}
            .quick-link svg {{ width: 24px; height: 24px; color: var(--primary); }}
            .charts-row {{
                display: grid;
                grid-template-columns: 2fr 1fr 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }}
            @media (max-width: 1200px) {{
                .charts-row {{
                    grid-template-columns: 1fr;
                }}
            }}
            .chart-card {{
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                position: relative;
            }}
            .chart-card.large {{
                grid-column: span 1;
            }}
            .chart-card h3 {{
                font-size: 16px;
                font-weight: 600;
                color: #1E293B;
                margin: 0 0 15px 0;
            }}
            .chart-container {{
                position: relative;
                height: 250px;
                width: 100%;
            }}
            .chart-container.large {{
                height: 300px;
            }}
            .chart-legend {{
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-top: 15px;
                justify-content: center;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 12px;
                color: #64748B;
            }}
            .dot {{
                width: 10px;
                height: 10px;
                border-radius: 50%;
            }}
            .dot.green {{ background: #10B981; }}
            .dot.orange {{ background: #F59E0B; }}
            .dot.red {{ background: #EF4444; }}
            .dot.blue {{ background: #3B82F6; }}
        </style>

        <h2 class="section-title">💰 Indicateurs financiers</h2>
        <div class="dashboard-grid">
            <div class="kpi-card success">
                <div class="kpi-header">
                    <span class="kpi-title">CA du mois</span>
                    <div class="kpi-icon">{get_icon("trending-up")}</div>
                </div>
                <div class="kpi-value">{fmt(ca_mois)}</div>
                <div class="kpi-subtitle">Année: {fmt(ca_annee)}</div>
            </div>

            <div class="kpi-card info">
                <div class="kpi-header">
                    <span class="kpi-title">Trésorerie</span>
                    <div class="kpi-icon">{get_icon("credit-card")}</div>
                </div>
                <div class="kpi-value">{fmt(tresorerie)}</div>
                <div class="kpi-subtitle">Solde comptes bancaires</div>
            </div>

            <div class="kpi-card warning">
                <div class="kpi-header">
                    <span class="kpi-title">Factures à encaisser</span>
                    <div class="kpi-icon">{get_icon("clock")}</div>
                </div>
                <div class="kpi-value">{fmt(factures_a_payer)}</div>
                <div class="kpi-subtitle">{nb_factures_impayees} facture(s) en attente</div>
            </div>

            <div class="kpi-card {"danger" if impayes_clients > 0 else "success"}">
                <div class="kpi-header">
                    <span class="kpi-title">Impayés clients</span>
                    <div class="kpi-icon">{get_icon("alert-triangle")}</div>
                </div>
                <div class="kpi-value">{fmt(impayes_clients)}</div>
                <div class="kpi-subtitle">{nb_impayes_clients} facture(s) impayée(s)</div>
            </div>

            <div class="kpi-card {"danger" if impayes_fournisseurs > 0 else "success"}">
                <div class="kpi-header">
                    <span class="kpi-title">À payer fournisseurs</span>
                    <div class="kpi-icon">{get_icon("shopping-cart")}</div>
                </div>
                <div class="kpi-value">{fmt(impayes_fournisseurs)}</div>
                <div class="kpi-subtitle">Commandes à régler</div>
            </div>

            <div class="kpi-card info">
                <div class="kpi-header">
                    <span class="kpi-title">TVA à reverser</span>
                    <div class="kpi-icon">{get_icon("percent")}</div>
                </div>
                <div class="kpi-value">{fmt(tva_a_payer)}</div>
                <div class="kpi-subtitle">TVA collectée ce mois</div>
            </div>
        </div>

        <h2 class="section-title">📊 Évolution annuelle</h2>
        <div class="charts-row">
            <div class="chart-card large">
                <h3>Chiffre d'affaires {today.year}</h3>
                <div class="chart-container large">
                    <canvas id="caChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>Statut des factures</h3>
                <div class="chart-container">
                    <canvas id="facturesChart"></canvas>
                </div>
                <div class="chart-legend">
                    <span class="legend-item"><span class="dot green"></span> Payées ({nb_factures_payees})</span>
                    <span class="legend-item"><span class="dot orange"></span> En attente ({nb_factures_en_attente})</span>
                    <span class="legend-item"><span class="dot red"></span> En retard ({nb_factures_en_retard})</span>
                </div>
            </div>
            <div class="chart-card">
                <h3>Trésorerie vs Dettes</h3>
                <div class="chart-container">
                    <canvas id="tresoChart"></canvas>
                </div>
                <div class="chart-legend">
                    <span class="legend-item"><span class="dot blue"></span> Trésorerie</span>
                    <span class="legend-item"><span class="dot orange"></span> À encaisser</span>
                    <span class="legend-item"><span class="dot red"></span> À payer</span>
                </div>
            </div>
        </div>

        <h2 class="section-title">🚀 Accès rapides</h2>
        <div class="quick-links">
            <a href="/ui/factures/nouveau" class="quick-link">
                {get_icon("file-plus")}
                <span>Nouvelle facture</span>
            </a>
            <a href="/ui/devis/nouveau" class="quick-link">
                {get_icon("file-text")}
                <span>Nouveau devis</span>
            </a>
            <a href="/ui/interventions/nouveau" class="quick-link">
                {get_icon("wrench")}
                <span>Nouvelle intervention</span>
            </a>
            <a href="/ui/clients/nouveau" class="quick-link">
                {get_icon("user-plus")}
                <span>Nouveau client</span>
            </a>
            <a href="/ui/factures" class="quick-link">
                {get_icon("list")}
                <span>Voir les factures</span>
            </a>
            <a href="/ui/paiements" class="quick-link">
                {get_icon("dollar-sign")}
                <span>Enregistrer un paiement</span>
            </a>
            <a href="/ui/clients" class="quick-link">
                {get_icon("users")}
                <span>Gérer les clients</span>
            </a>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                // Graphique CA annuel
                const caCtx = document.getElementById('caChart').getContext('2d');
                new Chart(caCtx, {{
                    type: 'bar',
                    data: {{
                        labels: {json.dumps(mois_labels)},
                        datasets: [{{
                            label: 'CA (€)',
                            data: {ca_data},
                            backgroundColor: 'rgba(37, 99, 235, 0.8)',
                            borderColor: 'rgba(37, 99, 235, 1)',
                            borderWidth: 1,
                            borderRadius: 6
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        scales: {{
                            y: {{
                                beginAtZero: true,
                                ticks: {{
                                    callback: function(value) {{
                                        return value.toLocaleString('fr-FR') + ' €';
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});

                // Camembert factures
                const factCtx = document.getElementById('facturesChart').getContext('2d');
                new Chart(factCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['Payées', 'En attente', 'En retard'],
                        datasets: [{{
                            data: [{nb_factures_payees}, {nb_factures_en_attente}, {nb_factures_en_retard}],
                            backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
                            borderWidth: 0
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ display: false }},
                        }},
                        cutout: '60%'
                    }}
                }});

                // Camembert trésorerie
                const tresoCtx = document.getElementById('tresoChart').getContext('2d');
                new Chart(tresoCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['Trésorerie', 'À encaisser', 'À payer'],
                        datasets: [{{
                            data: [{tresorerie}, {impayes_clients}, {impayes_fournisseurs}],
                            backgroundColor: ['#3B82F6', '#F59E0B', '#EF4444'],
                            borderWidth: 0
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ display: false }}
                        }},
                        cutout: '60%'
                    }}
                }});
            }});
        </script>
        ''',
        user=user,
        modules=modules
    )
    return HTMLResponse(content=html)


@ui_router.get("/parametres/theme", response_class=HTMLResponse)
async def theme_settings(request: Request, user: dict = Depends(require_auth)):
    """Page de personnalisation du thème des documents."""

    html = generate_layout(
        title="Style des documents",
        content='''
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">Personnaliser le style des devis et factures</h2>
            </div>
            <div class="card-body">
                <div class="theme-editor">
                    <!-- Couleur -->
                    <div class="theme-option">
                        <label class="label">Couleur principale</label>
                        <div class="color-options">
                            <button class="color-btn active" style="background: #2563EB;" data-color="#2563EB"></button>
                            <button class="color-btn" style="background: #10B981;" data-color="#10B981"></button>
                            <button class="color-btn" style="background: #F59E0B;" data-color="#F59E0B"></button>
                            <button class="color-btn" style="background: #EF4444;" data-color="#EF4444"></button>
                            <button class="color-btn" style="background: #8B5CF6;" data-color="#8B5CF6"></button>
                            <button class="color-btn" style="background: #1E293B;" data-color="#1E293B"></button>
                        </div>
                    </div>

                    <!-- Structure -->
                    <div class="theme-option">
                        <label class="label">Structure</label>
                        <div class="style-options">
                            <button class="style-btn active" data-value="moderne">
                                <div class="style-preview moderne"></div>
                                <span>Moderne</span>
                            </button>
                            <button class="style-btn" data-value="classique">
                                <div class="style-preview classique"></div>
                                <span>Classique</span>
                            </button>
                            <button class="style-btn" data-value="minimal">
                                <div class="style-preview minimal"></div>
                                <span>Minimal</span>
                            </button>
                        </div>
                    </div>

                    <!-- Style tableaux -->
                    <div class="theme-option">
                        <label class="label">Style des tableaux</label>
                        <div class="style-options">
                            <button class="style-btn active" data-value="simple">Simple</button>
                            <button class="style-btn" data-value="zebra">Zebra</button>
                            <button class="style-btn" data-value="bordure">Bordures</button>
                            <button class="style-btn" data-value="sans">Sans bordure</button>
                        </div>
                    </div>

                    <!-- Angles -->
                    <div class="theme-option">
                        <label class="label">Angles</label>
                        <div class="style-options">
                            <button class="style-btn active" data-value="arrondis">
                                <div style="width:30px;height:20px;background:var(--gray-300);border-radius:4px;"></div>
                            </button>
                            <button class="style-btn" data-value="carres">
                                <div style="width:30px;height:20px;background:var(--gray-300);border-radius:0;"></div>
                            </button>
                        </div>
                    </div>

                    <!-- Lignes -->
                    <div class="theme-option">
                        <label class="label">Lignes</label>
                        <div class="style-options">
                            <button class="style-btn" data-value="aucune">Aucune</button>
                            <button class="style-btn active" data-value="fines">Fines</button>
                            <button class="style-btn" data-value="epaisses">Épaisses</button>
                        </div>
                    </div>

                    <!-- Images produits -->
                    <div class="theme-option">
                        <label class="label">Images des produits</label>
                        <div class="style-options">
                            <button class="style-btn" data-value="aucune">Aucune</button>
                            <button class="style-btn active" data-value="petites">Petites</button>
                            <button class="style-btn" data-value="moyennes">Moyennes</button>
                            <button class="style-btn" data-value="grandes">Grandes</button>
                        </div>
                    </div>
                </div>

                <div class="flex justify-end gap-2" style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--gray-200);">
                    <button class="btn btn-primary" onclick="saveTheme()">Enregistrer</button>
                </div>
            </div>
        </div>

        <style>
            .theme-option { margin-bottom: 24px; }
            .color-options { display: flex; gap: 8px; margin-top: 8px; }
            .color-btn {
                width: 32px; height: 32px;
                border-radius: 50%;
                border: 2px solid transparent;
                cursor: pointer;
                transition: all 0.15s;
            }
            .color-btn:hover { transform: scale(1.1); }
            .color-btn.active { border-color: var(--gray-900); box-shadow: 0 0 0 2px white, 0 0 0 4px var(--gray-400); }
            .style-options { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
            .style-btn {
                padding: 8px 16px;
                border: 1px solid var(--gray-300);
                background: white;
                border-radius: 6px;
                cursor: pointer;
                font-size: 13px;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 6px;
                transition: all 0.15s;
            }
            .style-btn:hover { border-color: var(--gray-400); }
            .style-btn.active { border-color: var(--primary); background: var(--primary-light); color: var(--primary); }
            .style-preview { width: 60px; height: 40px; background: var(--gray-100); border-radius: 4px; }
        </style>

        <script>
            document.querySelectorAll('.color-btn').forEach(btn => {
                btn.onclick = () => {
                    document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                };
            });
            document.querySelectorAll('.style-btn').forEach(btn => {
                btn.onclick = () => {
                    const parent = btn.closest('.style-options');
                    parent.querySelectorAll('.style-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                };
            });
            function saveTheme() {
                alert('Thème enregistré ! (à implémenter avec API)');
            }
        </script>
        ''',
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/parametres/modules", response_class=HTMLResponse)
async def modules_settings(request: Request, user: dict = Depends(require_auth)):
    """Page de configuration des modules actifs pour l'utilisateur."""

    # Get all available modules
    all_modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module and module.actif:
            all_modules.append({
                "name": name,
                "label": module.nom or name.capitalize(),
                "icon": module.icone or "file",
                "menu": module.menu or "Général",
                "description": module.description or ""
            })

    # Sort by menu then by name
    all_modules.sort(key=lambda m: (m["menu"], m["label"]))

    # Get user's enabled modules (from modules_mobile field)
    user_id = user.get("id")
    tenant_id = user.get("tenant_id")
    enabled_modules = None

    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("""
                SELECT modules_mobile
                FROM azalplus.utilisateurs
                WHERE id = :user_id AND tenant_id = :tenant_id
            """),
            {"user_id": str(user_id), "tenant_id": str(tenant_id)}
        )
        row = result.fetchone()
        if row and row[0]:
            try:
                import json
                enabled_modules = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except:
                enabled_modules = None

    # Group modules by menu
    modules_by_menu = {}
    for m in all_modules:
        menu = m["menu"]
        if menu not in modules_by_menu:
            modules_by_menu[menu] = []
        modules_by_menu[menu].append(m)

    # Generate module toggles HTML
    modules_html = ""
    for menu, modules in modules_by_menu.items():
        modules_html += f'''
        <div class="module-group" style="margin-bottom: 24px;">
            <h3 class="font-medium mb-3" style="color: var(--gray-600); font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">{menu}</h3>
            <div class="module-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;">
        '''
        for mod in modules:
            is_enabled = enabled_modules is None or mod["name"] in enabled_modules
            checked = "checked" if is_enabled else ""
            modules_html += f'''
                <label class="module-card" style="display: flex; align-items: center; padding: 12px 16px; background: white; border: 1px solid var(--gray-200); border-radius: 8px; cursor: pointer; transition: all 0.2s;">
                    <input type="checkbox" name="module" value="{mod['name']}" {checked} class="module-checkbox" style="margin-right: 12px;">
                    <span style="font-size: 20px; margin-right: 12px;">{get_icon(mod['icon'])}</span>
                    <div style="flex: 1;">
                        <div style="font-weight: 500; color: var(--gray-800);">{mod['label']}</div>
                        <div style="font-size: 12px; color: var(--gray-500);">{mod['description'][:50] + '...' if len(mod['description']) > 50 else mod['description']}</div>
                    </div>
                </label>
            '''
        modules_html += '''
            </div>
        </div>
        '''

    html = generate_layout(
        title="Modules actifs",
        content=f'''
        <div class="card">
            <div class="card-header flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <span style="font-size: 24px;">📦</span>
                    <div>
                        <h2 class="card-title">Modules actifs</h2>
                        <p class="text-gray-500 text-sm">Personnalisez les modules visibles dans votre interface</p>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button class="btn btn-secondary" onclick="selectAll(true)">
                        <span>✓</span> Tout activer
                    </button>
                    <button class="btn btn-secondary" onclick="selectAll(false)">
                        <span>✗</span> Tout désactiver
                    </button>
                    <button class="btn btn-primary" onclick="saveModules()">
                        <span>💾</span> Sauvegarder
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="alert alert-info" style="margin-bottom: 24px;">
                    <span>ℹ️</span> Les modules désactivés ne seront plus visibles dans le menu. Cette configuration est personnelle.
                </div>

                <form id="modules-form">
                    {modules_html}
                </form>
            </div>
        </div>

        <style>
            .module-card:hover {{
                border-color: var(--primary);
                background: var(--primary-50);
            }}
            .module-card:has(input:checked) {{
                border-color: var(--primary);
                background: var(--primary-50);
            }}
            .module-checkbox {{
                width: 18px;
                height: 18px;
                accent-color: var(--primary);
            }}
        </style>

        <script>
            function selectAll(checked) {{
                document.querySelectorAll('.module-checkbox').forEach(cb => cb.checked = checked);
            }}

            function showToast(message, type) {{
                const toast = document.createElement('div');
                toast.style.cssText = 'position: fixed; top: 20px; right: 20px; padding: 12px 24px; border-radius: 8px; color: white; z-index: 9999; font-weight: 500;';
                toast.style.background = type === 'success' ? '#22c55e' : '#ef4444';
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            }}

            async function saveModules() {{
                const checkboxes = document.querySelectorAll('.module-checkbox:checked');
                const enabledModules = Array.from(checkboxes).map(cb => cb.value);

                console.log('Saving modules:', enabledModules);

                try {{
                    const response = await fetch('/api/admin/users/me/modules', {{
                        method: 'PUT',
                        headers: {{
                            'Content-Type': 'application/json'
                        }},
                        credentials: 'include',
                        body: JSON.stringify({{ modules: enabledModules }})
                    }});

                    console.log('Response status:', response.status);

                    if (response.ok) {{
                        showToast('Modules mis à jour', 'success');
                        setTimeout(() => window.location.reload(), 1000);
                    }} else {{
                        const data = await response.json();
                        console.log('Error:', data);
                        showToast(data.detail || 'Erreur lors de la sauvegarde', 'error');
                    }}
                }} catch(e) {{
                    console.error('Network error:', e);
                    showToast('Erreur réseau: ' + e.message, 'error');
                }}
            }}
        </script>
        ''',
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/parametres/autocompletion-ia", response_class=HTMLResponse)
async def autocompletion_ia_settings(request: Request, user: dict = Depends(require_auth)):
    """Page de configuration de l'autocomplétion IA."""

    html = generate_layout(
        title="Autocomplétion IA",
        content='''
        <div class="card">
            <div class="card-header flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <span style="font-size: 24px;">✨</span>
                    <div>
                        <h2 class="card-title">Autocomplétion IA</h2>
                        <p class="text-gray-500 text-sm">Suggestions intelligentes avec ChatGPT et Claude</p>
                    </div>
                </div>
                <button class="btn btn-primary" onclick="saveConfig()">
                    <span>💾</span> Sauvegarder
                </button>
            </div>
            <div class="card-body">
                <!-- Activation -->
                <div class="form-group" style="margin-bottom: 24px; padding-bottom: 24px; border-bottom: 1px solid var(--gray-200);">
                    <label class="flex items-center gap-3 cursor-pointer">
                        <input type="checkbox" id="ia_actif" checked class="toggle-checkbox">
                        <span class="font-medium">Activer l'autocomplétion IA</span>
                    </label>
                    <p class="text-gray-500 text-sm mt-1">Active les suggestions IA dans tous les champs configurés</p>
                </div>

                <!-- État des providers -->
                <div style="margin-bottom: 24px;">
                    <h3 class="font-medium mb-3">État des fournisseurs</h3>
                    <div class="grid grid-cols-3 gap-4" id="providers-status">
                        <div class="provider-card" data-provider="anthropic">
                            <div class="flex items-center justify-between mb-2">
                                <span class="font-medium">Claude (Anthropic)</span>
                                <span class="status-badge status-unknown">⏳</span>
                            </div>
                            <p class="text-sm text-gray-500">Vérification...</p>
                        </div>
                        <div class="provider-card" data-provider="openai">
                            <div class="flex items-center justify-between mb-2">
                                <span class="font-medium">ChatGPT (OpenAI)</span>
                                <span class="status-badge status-unknown">⏳</span>
                            </div>
                            <p class="text-sm text-gray-500">Vérification...</p>
                        </div>
                        <div class="provider-card" data-provider="local">
                            <div class="flex items-center justify-between mb-2">
                                <span class="font-medium">Local (Fallback)</span>
                                <span class="status-badge status-ok">✓</span>
                            </div>
                            <p class="text-sm text-gray-500">Toujours disponible</p>
                        </div>
                    </div>
                </div>

                <!-- Clés API -->
                <div style="margin-bottom: 24px; padding: 16px; background: var(--gray-50); border-radius: 8px;">
                    <h3 class="font-medium mb-3">🔑 Clés API</h3>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="form-group">
                            <label class="label">Clé API Anthropic</label>
                            <div class="input-group">
                                <input type="password" id="anthropic_key" class="input" placeholder="sk-ant-...">
                                <button class="btn btn-sm" onclick="toggleKey('anthropic_key')">👁</button>
                            </div>
                            <p class="text-xs text-gray-500 mt-1">
                                <a href="https://console.anthropic.com/settings/keys" target="_blank" class="text-blue-600">Obtenir une clé →</a>
                            </p>
                        </div>
                        <div class="form-group">
                            <label class="label">Clé API OpenAI</label>
                            <div class="input-group">
                                <input type="password" id="openai_key" class="input" placeholder="sk-...">
                                <button class="btn btn-sm" onclick="toggleKey('openai_key')">👁</button>
                            </div>
                            <p class="text-xs text-gray-500 mt-1">
                                <a href="https://platform.openai.com/api-keys" target="_blank" class="text-blue-600">Obtenir une clé →</a>
                            </p>
                        </div>
                    </div>
                </div>

                <!-- Fournisseur par défaut -->
                <div class="grid grid-cols-2 gap-4" style="margin-bottom: 24px;">
                    <div class="form-group">
                        <label class="label">Fournisseur par défaut</label>
                        <select id="default_provider" class="select">
                            <option value="anthropic">Claude (Anthropic) - Recommandé</option>
                            <option value="openai">ChatGPT (OpenAI)</option>
                            <option value="local">Local (sans IA)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="label">Modèle</label>
                        <select id="default_model" class="select">
                            <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                            <option value="claude-3-5-haiku-20241022">Claude 3.5 Haiku (rapide)</option>
                            <option value="gpt-4o">GPT-4o</option>
                            <option value="gpt-4o-mini">GPT-4o Mini (économique)</option>
                        </select>
                    </div>
                </div>

                <!-- Paramètres -->
                <div style="margin-bottom: 24px;">
                    <h3 class="font-medium mb-3">Paramètres</h3>
                    <div class="grid grid-cols-3 gap-4">
                        <div class="form-group">
                            <label class="label">Mode</label>
                            <select id="mode" class="select">
                                <option value="suggestions">Suggestions (dropdown)</option>
                                <option value="completion">Complétion (inline)</option>
                                <option value="hybrid">Hybride</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="label">Nombre de suggestions</label>
                            <input type="number" id="max_suggestions" class="input" value="5" min="1" max="10">
                        </div>
                        <div class="form-group">
                            <label class="label">Délai (ms)</label>
                            <input type="number" id="debounce_ms" class="input" value="300" min="100" max="2000" step="50">
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 mt-4">
                        <div class="form-group">
                            <label class="label">Température (créativité): <span id="temp_value">0.3</span></label>
                            <input type="range" id="temperature" class="slider" value="0.3" min="0" max="1" step="0.1"
                                   oninput="document.getElementById('temp_value').textContent = this.value">
                            <div class="flex justify-between text-xs text-gray-500">
                                <span>Précis</span>
                                <span>Créatif</span>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="label">Caractères minimum</label>
                            <input type="number" id="min_chars" class="input" value="2" min="1" max="10">
                        </div>
                    </div>
                </div>

                <!-- Limites -->
                <div style="margin-bottom: 24px; padding: 16px; background: var(--gray-50); border-radius: 8px;">
                    <h3 class="font-medium mb-3">Limites d'utilisation</h3>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="form-group">
                            <label class="label">Requêtes par jour</label>
                            <input type="number" id="daily_limit" class="input" value="1000" min="100" max="100000" step="100">
                            <div class="progress-bar mt-2">
                                <div class="progress-fill" style="width: 12%"></div>
                            </div>
                            <p class="text-xs text-gray-500 mt-1">Utilisé: 120 / 1000</p>
                        </div>
                        <div class="form-group">
                            <label class="label">Tokens par jour</label>
                            <input type="number" id="token_limit" class="input" value="100000" min="1000" max="1000000" step="1000">
                            <div class="progress-bar mt-2">
                                <div class="progress-fill" style="width: 8%; background: var(--purple-500);"></div>
                            </div>
                            <p class="text-xs text-gray-500 mt-1">Utilisé: 8,000 / 100,000</p>
                        </div>
                    </div>
                </div>

                <!-- Test -->
                <div style="padding: 16px; background: linear-gradient(135deg, var(--purple-50), var(--blue-50)); border-radius: 8px; border: 1px solid var(--purple-200);">
                    <h3 class="font-medium mb-3">Tester l'autocomplétion</h3>
                    <div class="flex gap-3 mb-4">
                        <button class="btn btn-purple" onclick="testProvider('anthropic')">Tester Claude</button>
                        <button class="btn btn-success" onclick="testProvider('openai')">Tester OpenAI</button>
                        <button class="btn btn-secondary" onclick="testProvider('local')">Tester Local</button>
                    </div>
                    <div id="test-result" class="hidden">
                        <div class="bg-white rounded-lg p-4">
                            <p class="text-sm text-gray-600 mb-2">
                                <strong>Provider:</strong> <span id="result-provider">-</span> |
                                <strong>Modèle:</strong> <span id="result-model">-</span> |
                                <strong>Latence:</strong> <span id="result-latency">-</span>ms
                            </p>
                            <p class="font-medium mb-2">Suggestions pour "Dup" :</p>
                            <ul id="result-suggestions" class="list-disc list-inside space-y-1"></ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <style>
            .toggle-checkbox {
                width: 44px; height: 24px;
                appearance: none; background: var(--gray-300);
                border-radius: 12px; position: relative;
                cursor: pointer; transition: background 0.2s;
            }
            .toggle-checkbox:checked { background: var(--primary); }
            .toggle-checkbox::after {
                content: ''; position: absolute;
                top: 2px; left: 2px;
                width: 20px; height: 20px;
                background: white; border-radius: 50%;
                transition: transform 0.2s;
            }
            .toggle-checkbox:checked::after { transform: translateX(20px); }

            .provider-card {
                padding: 16px;
                border: 1px solid var(--gray-200);
                border-radius: 8px;
                background: white;
            }
            .status-badge {
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 12px;
            }
            .status-ok { background: var(--green-100); color: var(--green-700); }
            .status-error { background: var(--red-100); color: var(--red-700); }
            .status-unknown { background: var(--gray-100); color: var(--gray-600); }

            .input-group {
                display: flex;
                gap: 8px;
            }
            .input-group .input { flex: 1; }

            .slider {
                width: 100%;
                height: 6px;
                border-radius: 3px;
                background: var(--gray-200);
                appearance: none;
            }
            .slider::-webkit-slider-thumb {
                appearance: none;
                width: 18px; height: 18px;
                border-radius: 50%;
                background: var(--primary);
                cursor: pointer;
            }

            .progress-bar {
                height: 6px;
                background: var(--gray-200);
                border-radius: 3px;
                overflow: hidden;
            }
            .progress-fill {
                height: 100%;
                background: var(--primary);
                border-radius: 3px;
                transition: width 0.3s;
            }

            .btn-purple {
                background: var(--purple-600);
                color: white;
            }
            .btn-purple:hover { background: var(--purple-700); }

            .hidden { display: none; }
            .grid-cols-2 { display: grid; grid-template-columns: repeat(2, 1fr); }
            .grid-cols-3 { display: grid; grid-template-columns: repeat(3, 1fr); }
        </style>

        <script>
            // Toggle API key visibility
            function toggleKey(inputId) {
                const input = document.getElementById(inputId);
                input.type = input.type === 'password' ? 'text' : 'password';
            }

            // Check providers health
            async function checkHealth() {
                try {
                    const response = await fetch('/api/autocompletion-ia/health');
                    if (response.ok) {
                        const data = await response.json();
                        updateProviderStatus(data);
                    }
                } catch (e) {
                    console.log('Health check failed:', e);
                }
            }

            function updateProviderStatus(health) {
                ['anthropic', 'openai'].forEach(provider => {
                    const card = document.querySelector(`[data-provider="${provider}"]`);
                    if (!card) return;

                    const badge = card.querySelector('.status-badge');
                    const text = card.querySelector('p');

                    const status = health[provider];
                    if (status && status.status === 'ok') {
                        badge.className = 'status-badge status-ok';
                        badge.textContent = '✓';
                        text.textContent = status.latency_ms + 'ms';
                    } else {
                        badge.className = 'status-badge status-error';
                        badge.textContent = '✗';
                        text.textContent = status?.error || 'Non configuré';
                    }
                });
            }

            // Test provider
            async function testProvider(provider) {
                const resultDiv = document.getElementById('test-result');
                resultDiv.classList.remove('hidden');
                document.getElementById('result-suggestions').innerHTML = '<li>Chargement...</li>';

                try {
                    const response = await fetch('/api/autocompletion-ia/suggest', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            module: 'Clients',
                            champ: 'nom',
                            valeur: 'Dup',
                            limite: 5,
                            provider: provider
                        })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        document.getElementById('result-provider').textContent = data.meta?.provider || provider;
                        document.getElementById('result-model').textContent = data.meta?.model || '-';
                        document.getElementById('result-latency').textContent = data.meta?.latency_ms || '-';

                        const ul = document.getElementById('result-suggestions');
                        ul.innerHTML = data.suggestions.map(s =>
                            `<li>${s.texte} <span class="text-gray-400">(${s.source})</span></li>`
                        ).join('');
                    } else {
                        const error = await response.json();
                        document.getElementById('result-suggestions').innerHTML =
                            `<li class="text-red-600">Erreur: ${error.detail || 'Échec du test'}</li>`;
                    }
                } catch (e) {
                    document.getElementById('result-suggestions').innerHTML =
                        `<li class="text-red-600">Erreur: ${e.message}</li>`;
                }
            }

            // Save config
            async function saveConfig() {
                const config = {
                    actif: document.getElementById('ia_actif').checked,
                    fournisseur_defaut: document.getElementById('default_provider').value,
                    modele_defaut: document.getElementById('default_model').value,
                    mode: document.getElementById('mode').value,
                    nombre_suggestions: parseInt(document.getElementById('max_suggestions').value),
                    temperature: parseFloat(document.getElementById('temperature').value),
                    delai_declenchement: parseInt(document.getElementById('debounce_ms').value),
                    longueur_min: parseInt(document.getElementById('min_chars').value),
                    limite_requetes_jour: parseInt(document.getElementById('daily_limit').value),
                    limite_tokens_jour: parseInt(document.getElementById('token_limit').value),
                    anthropic_api_key: document.getElementById('anthropic_key').value || undefined,
                    openai_api_key: document.getElementById('openai_key').value || undefined
                };

                try {
                    const response = await fetch('/api/autocompletion-ia/config', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(config)
                    });

                    if (response.ok) {
                        alert('Configuration sauvegardée !');
                        checkHealth();
                    } else {
                        const error = await response.json();
                        alert('Erreur: ' + (error.detail || 'Échec de la sauvegarde'));
                    }
                } catch (e) {
                    alert('Erreur: ' + e.message);
                }
            }

            // Load config on page load
            async function loadConfig() {
                try {
                    const response = await fetch('/api/autocompletion-ia/config');
                    if (response.ok) {
                        const data = await response.json();
                        if (data.actif !== undefined) document.getElementById('ia_actif').checked = data.actif;
                        if (data.fournisseur_defaut) document.getElementById('default_provider').value = data.fournisseur_defaut;
                        if (data.modele_defaut) document.getElementById('default_model').value = data.modele_defaut;
                        if (data.mode) document.getElementById('mode').value = data.mode;
                        if (data.nombre_suggestions) document.getElementById('max_suggestions').value = data.nombre_suggestions;
                        if (data.temperature) {
                            document.getElementById('temperature').value = data.temperature;
                            document.getElementById('temp_value').textContent = data.temperature;
                        }
                        if (data.delai_declenchement) document.getElementById('debounce_ms').value = data.delai_declenchement;
                        if (data.longueur_min) document.getElementById('min_chars').value = data.longueur_min;
                        if (data.limite_requetes_jour) document.getElementById('daily_limit').value = data.limite_requetes_jour;
                        if (data.limite_tokens_jour) document.getElementById('token_limit').value = data.limite_tokens_jour;
                    }
                } catch (e) {
                    console.log('Config load failed:', e);
                }
            }

            // Init
            loadConfig();
            checkHealth();
        </script>
        ''',
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Page de recherche globale."""

    results_html = ""
    total_count = 0

    if q and len(q) >= 2:
        # Recuperer tous les modules disponibles
        module_names = ModuleParser.list_all()

        # Effectuer la recherche globale
        search_results = Database.global_search(
            tenant_id=tenant_id,
            query=q,
            tables=[name.lower() for name in module_names],
            limit_per_table=10
        )

        # Generer le HTML des resultats groupes par module
        for module_name_lower, items in search_results.items():
            # Trouver le module correspondant
            module = None
            for name in module_names:
                if name.lower() == module_name_lower:
                    module = ModuleParser.get(name)
                    break

            if not module:
                continue

            module_display_name = module.nom_affichage if module else module_name_lower.title()
            module_icon = get_icon(module.icone) if module else "📁"

            # Compter les resultats
            total_count += len(items)

            # Generer les lignes de resultats
            rows_html = ""
            for item in items:
                # Determiner le nom a afficher
                display_name = item.get('nom') or item.get('raison_sociale') or item.get('titre') or item.get('numero') or item.get('reference') or str(item.get('id', ''))[:8]
                secondary_info = item.get('email') or item.get('description', '')[:50] if item.get('description') else ''

                # Badge de statut si present
                status_badge = ""
                if 'statut' in item and item['statut']:
                    status_badge = get_status_badge(item['statut'])

                rows_html += f'''
                <tr onclick="window.location='/ui/{module.nom}/{item['id']}'" style="cursor: pointer;">
                    <td>
                        <div class="search-result-name">{display_name}</div>
                        <div class="search-result-secondary">{secondary_info}</div>
                    </td>
                    <td class="text-right">{status_badge}</td>
                </tr>
                '''

            results_html += f'''
            <div class="search-results-group">
                <div class="search-results-header">
                    <span class="search-results-icon">{module_icon}</span>
                    <span class="search-results-title">{module_display_name}</span>
                    <span class="search-results-count">{len(items)} resultat(s)</span>
                </div>
                <table class="table">
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
            '''

    # Message si pas de resultats
    if not results_html and q:
        results_html = f'''
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">Aucun resultat</div>
            <div class="empty-text">Aucun resultat trouve pour "{q}"</div>
        </div>
        '''
    elif not q:
        results_html = '''
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">Rechercher</div>
            <div class="empty-text">Entrez au moins 2 caracteres pour rechercher</div>
        </div>
        '''

    # Message de resultats
    results_summary = ""
    if q and total_count > 0:
        results_summary = f'<div class="search-summary">{total_count} resultat(s) pour "{q}"</div>'

    html = generate_layout(
        title="Recherche",
        content=f'''
        <div class="search-page">
            <div class="search-header mb-6">
                <form action="/ui/search" method="GET" class="search-form-large">
                    <input type="text" name="q" value="{q}" placeholder="Rechercher clients, factures, devis, interventions..."
                           class="input search-input-large" autofocus>
                    <button type="submit" class="btn btn-primary">Rechercher</button>
                </form>
            </div>

            {results_summary}

            <div class="search-results">
                {results_html}
            </div>
        </div>

        <style>
            .search-form-large {{
                display: flex;
                gap: 12px;
                max-width: 600px;
            }}
            .search-input-large {{
                flex: 1;
                font-size: 16px;
                padding: 12px 16px;
            }}
            .search-summary {{
                color: var(--gray-600);
                margin-bottom: 20px;
                font-size: 14px;
            }}
            .search-results-group {{
                background: var(--white);
                border-radius: var(--radius-lg);
                border: 1px solid var(--gray-200);
                margin-bottom: 16px;
                overflow: hidden;
            }}
            .search-results-header {{
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 14px 16px;
                background: var(--gray-50);
                border-bottom: 1px solid var(--gray-200);
            }}
            .search-results-icon {{
                font-size: 18px;
            }}
            .search-results-title {{
                font-weight: 600;
                color: var(--gray-800);
                flex: 1;
            }}
            .search-results-count {{
                font-size: 12px;
                color: var(--gray-500);
                background: var(--gray-200);
                padding: 2px 8px;
                border-radius: 10px;
            }}
            .search-result-name {{
                font-weight: 500;
                color: var(--gray-800);
            }}
            .search-result-secondary {{
                font-size: 12px;
                color: var(--gray-500);
                margin-top: 2px;
            }}
            .search-results .table td {{
                padding: 12px 16px;
            }}
            .search-results .table tr:hover {{
                background: var(--primary-light);
            }}
        </style>
        ''',
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/calendrier", response_class=HTMLResponse)
async def calendar_view(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Vue calendrier des interventions."""

    # Contenu du calendrier
    calendar_content = '''
    <div class="calendar-container">
        <div class="calendar-header">
            <div class="calendar-nav">
                <button class="btn btn-secondary" id="prev-month">◀ Précédent</button>
                <h2 id="current-month" style="margin: 0 20px;"></h2>
                <button class="btn btn-secondary" id="next-month">Suivant ▶</button>
            </div>
            <div class="calendar-actions" style="display: flex; gap: 8px;">
                <button onclick="openOptimizer()" class="btn btn-secondary" style="display: flex; align-items: center; gap: 6px;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                        <path d="M2 17l10 5 10-5"></path>
                        <path d="M2 12l10 5 10-5"></path>
                    </svg>
                    Optimiser
                </button>
                <a href="/ui/agenda/nouveau" class="btn btn-primary" style="display: flex; align-items: center; gap: 6px;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Nouveau RDV
                </a>
            </div>
            <div class="calendar-views">
                <button class="btn btn-secondary active" data-view="month">Mois</button>
                <button class="btn btn-secondary" data-view="week">Semaine</button>
                <button class="btn btn-secondary" data-view="day">Jour</button>
            </div>
        </div>

        <div class="calendar-grid" id="calendar-grid">
            <!-- Jours de la semaine -->
            <div class="calendar-weekdays">
                <div>Lun</div>
                <div>Mar</div>
                <div>Mer</div>
                <div>Jeu</div>
                <div>Ven</div>
                <div>Sam</div>
                <div>Dim</div>
            </div>
            <div class="calendar-days" id="calendar-days">
                <!-- Les jours seront générés par JavaScript -->
            </div>
        </div>

        <!-- Liste des événements du jour sélectionné -->
        <div class="calendar-events" id="calendar-events">
            <h3>Événements</h3>
            <div class="events-list" id="events-list">
                <p class="text-muted">Sélectionnez une date pour voir les événements</p>
            </div>
        </div>

        <!-- Bouton flottant pour créer un RDV (mobile) -->
        <a href="/ui/agenda/nouveau" class="fab-create" title="Nouveau RDV">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
        </a>
    </div>

    <style>
        /* FAB - Floating Action Button */
        .fab-create {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: var(--primary-color, #2563EB);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
            text-decoration: none;
            transition: transform 0.2s, box-shadow 0.2s;
            z-index: 100;
        }
        .fab-create:hover {
            transform: scale(1.1);
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
        }
        .fab-create:active {
            transform: scale(0.95);
        }
        @media (min-width: 768px) {
            .fab-create {
                display: none; /* Caché sur desktop, le bouton header suffit */
            }
        }
        .calendar-container {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .calendar-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }
        .calendar-nav {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .calendar-views {
            display: flex;
            gap: 8px;
        }
        .calendar-views .btn.active {
            background: var(--primary-color, #2563EB);
            color: white;
        }
        .calendar-weekdays {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 4px;
            margin-bottom: 8px;
        }
        .calendar-weekdays > div {
            text-align: center;
            font-weight: 600;
            color: var(--gray-600, #666);
            padding: 8px;
        }
        .calendar-days {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 4px;
        }
        .calendar-day {
            aspect-ratio: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.15s;
            min-height: 80px;
        }
        .calendar-day:hover {
            background: var(--gray-100, #f3f4f6);
        }
        .calendar-day.today {
            background: var(--primary-color, #2563EB);
            color: white;
        }
        .calendar-day.other-month {
            color: var(--gray-400, #9ca3af);
        }
        .calendar-day.selected {
            border: 2px solid var(--primary-color, #2563EB);
        }
        .calendar-day .day-number {
            font-weight: 600;
            font-size: 14px;
        }
        .calendar-day .day-events {
            font-size: 10px;
            margin-top: 4px;
        }
        .event-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--success-color, #10B981);
            display: inline-block;
            margin: 1px;
        }
        .calendar-events {
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--gray-200, #e5e7eb);
        }
        .events-list .event-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: var(--gray-50, #f9fafb);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        .event-time {
            font-weight: 600;
            color: var(--gray-600, #666);
            min-width: 60px;
        }
        .event-title {
            flex: 1;
        }
    </style>

    <script>
        let currentDate = new Date();
        let selectedDate = new Date();

        const months = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                       'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

        function renderCalendar() {
            const year = currentDate.getFullYear();
            const month = currentDate.getMonth();

            document.getElementById('current-month').textContent = `${months[month]} ${year}`;

            const firstDay = new Date(year, month, 1);
            const lastDay = new Date(year, month + 1, 0);
            const startDay = firstDay.getDay() || 7; // Convert Sunday (0) to 7

            const daysContainer = document.getElementById('calendar-days');
            daysContainer.innerHTML = '';

            // Previous month days
            const prevMonthLastDay = new Date(year, month, 0).getDate();
            for (let i = startDay - 1; i > 0; i--) {
                const day = document.createElement('div');
                day.className = 'calendar-day other-month';
                day.innerHTML = `<span class="day-number">${prevMonthLastDay - i + 1}</span>`;
                daysContainer.appendChild(day);
            }

            // Current month days
            const today = new Date();
            for (let i = 1; i <= lastDay.getDate(); i++) {
                const day = document.createElement('div');
                day.className = 'calendar-day';

                if (year === today.getFullYear() && month === today.getMonth() && i === today.getDate()) {
                    day.classList.add('today');
                }

                if (year === selectedDate.getFullYear() && month === selectedDate.getMonth() && i === selectedDate.getDate()) {
                    day.classList.add('selected');
                }

                day.innerHTML = `<span class="day-number">${i}</span>`;
                day.addEventListener('click', () => selectDate(year, month, i));
                daysContainer.appendChild(day);
            }

            // Next month days
            const totalCells = 42; // 6 rows x 7 days
            const currentCells = startDay - 1 + lastDay.getDate();
            const nextDays = totalCells - currentCells;
            for (let i = 1; i <= nextDays; i++) {
                const day = document.createElement('div');
                day.className = 'calendar-day other-month';
                day.innerHTML = `<span class="day-number">${i}</span>`;
                daysContainer.appendChild(day);
            }
        }

        function selectDate(year, month, day) {
            selectedDate = new Date(year, month, day);
            renderCalendar();
            loadEvents(selectedDate);
        }

        function loadEvents(date) {
            const eventsList = document.getElementById('events-list');
            const dateStr = date.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
            eventsList.innerHTML = `
                <p class="text-muted">Événements du ${dateStr}</p>
                <div class="event-item">
                    <span class="event-time">09:00</span>
                    <span class="event-title">Chargement...</span>
                </div>
            `;

            // TODO: Fetch real events from API
        }

        document.getElementById('prev-month').addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            renderCalendar();
        });

        document.getElementById('next-month').addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            renderCalendar();
        });

        renderCalendar();

        // ===========================================
        // Optimisation Planning
        // ===========================================
        function openOptimizer() {
            document.getElementById('optimizerModal').style.display = 'flex';
        }

        function closeOptimizer() {
            document.getElementById('optimizerModal').style.display = 'none';
            document.getElementById('optimizerResults').innerHTML = '';
        }

        async function runOptimization() {
            const duree = document.getElementById('opt-duree').value || 60;
            const adresse = document.getElementById('opt-adresse').value || '';
            const date = document.getElementById('opt-date').value || '';

            document.getElementById('optimizerResults').innerHTML = '<p style="text-align:center;"><span class="loading"></span> Recherche des créneaux optimaux...</p>';

            try {
                const response = await fetch('/api/planning/optimize', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        duree_minutes: parseInt(duree),
                        adresse_rdv: adresse,
                        date_souhaitee: date,
                        type_event: 'RDV'
                    })
                });

                const data = await response.json();

                if (data.slots && data.slots.length > 0) {
                    let html = '<div class="optimizer-slots">';
                    html += '<h4 style="margin-bottom:12px;">Créneaux recommandés :</h4>';

                    data.slots.forEach((slot, i) => {
                        const startDate = new Date(slot.start);
                        const endDate = new Date(slot.end);
                        const dateStr = startDate.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
                        const startTime = startDate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
                        const endTime = endDate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });

                        const scoreClass = slot.score >= 80 ? 'score-high' : slot.score >= 50 ? 'score-medium' : 'score-low';

                        html += `
                            <div class="optimizer-slot" onclick="selectSlot('${slot.start}', '${slot.end}')">
                                <div class="slot-header">
                                    <span class="slot-date">${dateStr}</span>
                                    <span class="slot-score ${scoreClass}">${Math.round(slot.score)}%</span>
                                </div>
                                <div class="slot-time">${startTime} - ${endTime}</div>
                                ${slot.travel_time_before > 0 ? '<div class="slot-travel">🚗 ' + slot.travel_time_before + ' min de trajet</div>' : ''}
                                <div class="slot-reason">${slot.reason}</div>
                            </div>
                        `;
                    });

                    html += '</div>';
                    document.getElementById('optimizerResults').innerHTML = html;
                } else {
                    document.getElementById('optimizerResults').innerHTML = '<p style="color:var(--orange-500);">Aucun créneau disponible trouvé. Essayez une autre date.</p>';
                }
            } catch (err) {
                console.error(err);
                document.getElementById('optimizerResults').innerHTML = '<p style="color:var(--red-500);">Erreur lors de l\\'optimisation</p>';
            }
        }

        function selectSlot(start, end) {
            // Rediriger vers le formulaire de création avec les dates pré-remplies
            const startDate = new Date(start);
            const formattedStart = startDate.toISOString().slice(0, 16);
            window.location.href = '/ui/agenda/nouveau?date_debut=' + encodeURIComponent(formattedStart);
        }
    </script>

    <!-- Modal Optimisation -->
    <div id="optimizerModal" class="modal" style="display:none;">
        <div class="modal-content" style="max-width:500px;">
            <div class="modal-header">
                <h3>🎯 Optimiser mon planning</h3>
                <button onclick="closeOptimizer()" class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label class="label">Date souhaitée</label>
                    <input type="date" class="input" id="opt-date" value="">
                </div>
                <div class="form-group">
                    <label class="label">Durée (minutes)</label>
                    <select class="input" id="opt-duree">
                        <option value="30">30 min</option>
                        <option value="60" selected>1 heure</option>
                        <option value="90">1h30</option>
                        <option value="120">2 heures</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="label">Adresse du RDV (optionnel)</label>
                    <input type="text" class="input" id="opt-adresse" placeholder="Pour calculer les temps de trajet">
                </div>
                <button onclick="runOptimization()" class="btn btn-primary" style="width:100%;margin-top:12px;">
                    Trouver les meilleurs créneaux
                </button>
                <div id="optimizerResults" style="margin-top:16px;"></div>
            </div>
        </div>
    </div>

    <style>
        .optimizer-slots { display: flex; flex-direction: column; gap: 10px; }
        .optimizer-slot {
            border: 1px solid var(--gray-200);
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .optimizer-slot:hover {
            border-color: var(--primary-color);
            background: var(--primary-50, #EFF6FF);
        }
        .slot-header { display: flex; justify-content: space-between; align-items: center; }
        .slot-date { font-weight: 600; text-transform: capitalize; }
        .slot-score {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        .score-high { background: var(--green-100); color: var(--green-700); }
        .score-medium { background: var(--orange-100); color: var(--orange-700); }
        .score-low { background: var(--red-100); color: var(--red-700); }
        .slot-time { font-size: 18px; font-weight: 500; margin: 4px 0; }
        .slot-travel { font-size: 12px; color: var(--gray-500); }
        .slot-reason { font-size: 11px; color: var(--gray-400); margin-top: 4px; }
    </style>
    '''

    html = generate_layout(
        title="Calendrier des interventions",
        content=calendar_content,
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/{module_name}", response_class=HTMLResponse)
async def module_list(
    module_name: str,
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Liste des enregistrements d'un module avec actions groupees."""

    module = ModuleParser.get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")

    # Récupérer les données
    items = Database.query(module_name, tenant_id, limit=50)

    # Colonnes à afficher (max 5)
    display_fields = list(module.champs.keys())[:5]

    # Vérifier si le module a un champ statut
    has_status = "statut" in module.champs

    # Récupérer les valeurs de statut possibles pour le module
    status_values = []
    if has_status and module.champs.get("statut"):
        statut_field = module.champs.get("statut")
        if statut_field.enum_values:
            status_values = statut_field.enum_values

    # Générer le tableau avec checkbox
    table_headers = "".join([
        f'<th>{module.champs[f].label or f.replace("_", " ").title()}</th>'
        for f in display_fields
    ])

    table_rows = ""
    for item in items:
        cells = ""
        for f in display_fields:
            value = item.get(f, "")
            if f == "statut" and value:
                value = get_status_badge(value)
            cells += f"<td>{value}</td>"
        table_rows += f'''
        <tr data-id="{item['id']}" onclick="handleRowClick(event, '{item['id']}', '/ui/{module_name}/{item['id']}')" style="cursor:pointer">
            <td class="checkbox-cell" onclick="event.stopPropagation()">
                <input type="checkbox" class="row-checkbox" data-id="{item['id']}" onchange="updateBulkSelection()">
            </td>
            {cells}
        </tr>
        '''

    # Options de statut pour le dropdown
    status_options = ""
    if status_values:
        for status in status_values:
            status_options += f'<option value="{status}">{status}</option>'

    html = generate_layout(
        title=module.nom_affichage,
        content=generate_list_with_bulk_actions(
            module_name=module_name,
            module_display_name=module.nom_affichage,
            table_headers=table_headers,
            table_rows=table_rows,
            has_status=has_status,
            status_options=status_options
        ),
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/{module_name}/nouveau", response_class=HTMLResponse)
async def module_create_form(
    module_name: str,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Formulaire de création style Odoo."""

    module = ModuleParser.get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")

    # Formulaire spécial pour Devis/Factures
    if module_name.lower() in ["devis", "facture"]:
        html = generate_layout(
            title=f"Nouveau {module.nom_affichage}",
            content=generate_document_form(module, module_name),
            user=user,
            modules=get_all_modules()
        )
        return HTMLResponse(content=html)

    # Formulaire standard pour autres modules
    fields_html = ""
    for nom, field in module.champs.items():
        if field.type not in ["auto", "calcul"]:
            fields_html += get_field_html(field, module_name=module_name)

    html = generate_layout(
        title=f"Nouveau {module.nom_affichage}",
        content=generate_form(module_name, fields_html),
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


def generate_form(module_name: str, fields_html: str) -> str:
    """Génère un formulaire standard avec soumission API."""

    return f'''
    <div class="card">
        <div class="card-header">
            <span class="badge badge-gray">Nouveau</span>
        </div>
        <form id="create-form" class="card-body">
            <div class="form-grid">
                {fields_html}
            </div>
        </form>
        <div class="card-body flex justify-end gap-2" style="border-top: 1px solid var(--gray-200); padding-top: 16px;">
            <a href="/ui/{module_name}" class="btn btn-secondary">Annuler</a>
            <button type="button" id="submit-btn" onclick="submitForm()" class="btn btn-primary">Enregistrer</button>
        </div>
    </div>

    <!-- Messages de notification -->
    <div id="notification" class="notification hidden"></div>

    <style>
        .notification {{
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 24px;
            border-radius: 8px;
            font-weight: 500;
            z-index: 1000;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .notification.hidden {{
            opacity: 0;
            transform: translateY(-20px);
            pointer-events: none;
        }}
        .notification.success {{
            background: #10B981;
            color: white;
        }}
        .notification.error {{
            background: #EF4444;
            color: white;
        }}
        .btn:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}
        .spinner {{
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #ffffff;
            border-radius: 50%;
            border-top-color: transparent;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>

    <script>
    function showNotification(message, type) {{
        const notif = document.getElementById('notification');
        notif.textContent = message;
        notif.className = 'notification ' + type;
        setTimeout(() => {{
            notif.classList.add('hidden');
        }}, 4000);
    }}

    function collectFormData() {{
        const form = document.getElementById('create-form');
        const formData = new FormData(form);
        const data = {{}};

        for (const [key, value] of formData.entries()) {{
            // Gestion des checkbox
            const input = form.querySelector(`[name="${{key}}"]`);
            if (input && input.type === 'checkbox') {{
                data[key] = input.checked;
            }} else if (input && input.type === 'number') {{
                data[key] = value ? parseFloat(value) : null;
            }} else {{
                data[key] = value || null;
            }}
        }}

        // Ajouter les checkbox non cochées
        form.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
            if (!data.hasOwnProperty(cb.name)) {{
                data[cb.name] = cb.checked;
            }}
        }});

        return data;
    }}

    async function submitForm() {{
        const submitBtn = document.getElementById('submit-btn');
        const originalText = submitBtn.innerHTML;

        // État de chargement
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span>Enregistrement...';

        try {{
            const data = collectFormData();

            const response = await fetch('/api/{module_name}', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }});

            if (response.ok) {{
                const result = await response.json();
                showNotification('Enregistrement créé avec succès !', 'success');

                // Redirection vers la liste après 1.5 secondes
                setTimeout(() => {{
                    window.location.href = '/ui/{module_name}';
                }}, 1500);
            }} else {{
                const errorData = await response.json().catch(() => ({{}}));
                const errorMessage = errorData.detail || errorData.message || 'Erreur lors de l\\'enregistrement';
                showNotification(errorMessage, 'error');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }}
        }} catch (error) {{
            console.error('Erreur:', error);
            showNotification('Erreur de connexion au serveur', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }}
    }}

    // Charger les données de lien (select avec data-link)
    document.addEventListener('DOMContentLoaded', function() {{
        document.querySelectorAll('select[data-link]').forEach(async select => {{
            const linkedModule = select.dataset.link;
            await loadSelectOptions(select, linkedModule);
        }});
    }});

    async function loadSelectOptions(select, linkedModule) {{
        try {{
            // Convertir en minuscules pour l'API
            const apiModule = linkedModule.toLowerCase();
            const response = await fetch(`/api/${{apiModule}}`, {{ credentials: 'include' }});
            if (response.ok) {{
                const data = await response.json();
                const items = data.items || data || [];
                // Garder la première option (-- Sélectionner --)
                const firstOption = select.options[0];
                select.innerHTML = '';
                select.appendChild(firstOption);
                items.forEach(item => {{
                    const option = document.createElement('option');
                    option.value = item.id;
                    option.textContent = item.nom || item.raison_sociale || item.titre || item.numero || item.email || item.id;
                    select.appendChild(option);
                }});
            }}
        }} catch (e) {{
            console.error('Erreur chargement des liens:', e);
        }}
    }}

    // Modal de création inline
    let currentSelectId = null;
    let currentModule = null;

    function openCreateModal(moduleName, selectId) {{
        currentSelectId = selectId;
        currentModule = moduleName;
        document.getElementById('createModalTitle').textContent = 'Créer ' + moduleName;
        document.getElementById('createModalModule').value = moduleName;
        document.getElementById('createModalBody').innerHTML = '<p>Chargement...</p>';
        document.getElementById('createModal').style.display = 'flex';

        // Charger le formulaire simplifié
        loadQuickCreateForm(moduleName);
    }}

    async function loadQuickCreateForm(moduleName) {{
        // Formulaire simplifié avec les champs essentiels
        const commonFields = {{
            'Clients': ['code', 'name', 'legal_name', 'email', 'phone'],
            'clients': ['code', 'name', 'legal_name', 'email', 'phone'],
            'Fournisseurs': ['reference', 'nom', 'raison_sociale', 'email', 'telephone'],
            'fournisseurs': ['reference', 'nom', 'raison_sociale', 'email', 'telephone'],
            'Produits': ['nom', 'reference', 'prix_vente'],
            'produits': ['nom', 'reference', 'prix_vente'],
            'Utilisateurs': ['nom', 'email'],
            'utilisateurs': ['nom', 'email'],
            'Employes': ['nom', 'prenom', 'email', 'poste'],
            'employes': ['nom', 'prenom', 'email', 'poste'],
            'Projets': ['nom', 'description'],
            'projets': ['nom', 'description'],
            'Agenda': ['titre', 'date_debut'],
            'agenda': ['titre', 'date_debut'],
        }};

        const fields = commonFields[moduleName] || ['nom'];
        let formHtml = '<form id="quickCreateForm">';
        fields.forEach(field => {{
            const label = field.replace('_', ' ').replace(/^./, c => c.toUpperCase());
            formHtml += `
                <div class="form-group" style="margin-bottom: 12px;">
                    <label class="label">${{label}}</label>
                    <input type="text" class="input" name="${{field}}" id="quick_${{field}}">
                </div>
            `;
        }});
        formHtml += '</form>';
        document.getElementById('createModalBody').innerHTML = formHtml;
    }}

    function closeCreateModal() {{
        document.getElementById('createModal').style.display = 'none';
        currentSelectId = null;
        currentModule = null;
    }}

    async function saveQuickCreate() {{
        console.log('saveQuickCreate called, currentModule:', currentModule);

        const form = document.getElementById('quickCreateForm');
        if (!form) {{
            console.error('Form not found');
            showNotification('Erreur: formulaire non trouvé', 'error');
            return;
        }}
        const formData = new FormData(form);
        const data = {{}};
        formData.forEach((value, key) => {{
            if (value) data[key] = value;
        }});
        console.log('Form data collected:', data);

        // Auto-génération des champs obligatoires pour certains modules
        const moduleDefaults = {{
            'employes': {{
                matricule: 'EMP-' + Date.now().toString(36).toUpperCase(),
                type_contrat: 'CDI',
                date_embauche: new Date().toISOString().split('T')[0],
                statut: 'ACTIF',
                is_active: true
            }},
            'produits': {{
                is_active: true
            }},
            'clients': {{
                code: 'CLI-' + Date.now().toString(36).toUpperCase(),
                is_active: true
            }},
            'fournisseurs': {{
                reference: 'FRN-' + Date.now().toString(36).toUpperCase(),
                is_active: true
            }},
            'agenda': {{
                type: 'RDV',
                statut: 'PLANIFIE',
                is_active: true
            }}
        }};

        const moduleLower = currentModule.toLowerCase();
        console.log('moduleLower:', moduleLower, 'defaults:', moduleDefaults[moduleLower]);
        if (moduleDefaults[moduleLower]) {{
            Object.entries(moduleDefaults[moduleLower]).forEach(([key, value]) => {{
                if (!(key in data)) {{
                    data[key] = value;
                }}
            }});
        }}
        console.log('Final data to send:', data);

        try {{
            const apiModule = currentModule.toLowerCase();
            const response = await fetch(`/api/${{apiModule}}`, {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify(data)
            }});

            if (response.ok) {{
                const newItem = await response.json();
                console.log('Created item:', newItem);
                // Ajouter au select et sélectionner
                const select = document.getElementById(currentSelectId);
                if (select) {{
                    const option = document.createElement('option');
                    option.value = newItem.id;
                    option.textContent = newItem.nom || newItem.raison_sociale || newItem.titre || newItem.id;
                    option.selected = true;
                    select.appendChild(option);
                }}
                closeCreateModal();
                showNotification('Créé avec succès', 'success');
            }} else {{
                const err = await response.json();
                console.error('Server error:', err);
                // Afficher les erreurs de validation de manière explicite
                let errorMsg = 'Erreur';
                if (err.detail) {{
                    if (typeof err.detail === 'string') {{
                        errorMsg = err.detail;
                    }} else if (err.detail.errors && Array.isArray(err.detail.errors)) {{
                        // Erreurs de validation avec champs
                        const fieldErrors = err.detail.errors.map(e => {{
                            const fieldName = e.field.replace('_', ' ');
                            return `${{fieldName}}: ${{e.message}}`;
                        }});
                        errorMsg = fieldErrors.join(', ');
                    }} else if (Array.isArray(err.detail)) {{
                        // Erreurs Pydantic
                        const fieldErrors = err.detail.map(e => {{
                            const field = e.loc ? e.loc[e.loc.length - 1] : 'champ';
                            return `${{field}}: ${{e.msg}}`;
                        }});
                        errorMsg = fieldErrors.join(', ');
                    }} else {{
                        errorMsg = JSON.stringify(err.detail);
                    }}
                }}
                // Afficher l'erreur dans le modal lui-même
                const modalBody = document.getElementById('createModalBody');
                const existingError = modalBody.querySelector('.modal-error');
                if (existingError) existingError.remove();
                const errorDiv = document.createElement('div');
                errorDiv.className = 'modal-error';
                errorDiv.style.cssText = 'background:#fee;border:1px solid #c00;color:#c00;padding:10px;margin-bottom:10px;border-radius:4px;';
                errorDiv.textContent = errorMsg;
                modalBody.insertBefore(errorDiv, modalBody.firstChild);
                showNotification(errorMsg, 'error');
            }}
        }} catch (e) {{
            console.error('saveQuickCreate error:', e);
            showNotification('Erreur: ' + e.message, 'error');
        }}
    }}
    </script>

    <!-- Modal de création rapide -->
    <div id="createModal" class="modal-overlay" style="display:none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="createModalTitle">Créer</h3>
                <button onclick="closeCreateModal()" class="modal-close">&times;</button>
            </div>
            <div class="modal-body" id="createModalBody">
            </div>
            <input type="hidden" id="createModalModule">
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeCreateModal()">Annuler</button>
                <button class="btn btn-primary" onclick="saveQuickCreate()">Créer</button>
            </div>
        </div>
    </div>

    <style>
        .select-with-create {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .select-with-create select {{
            flex: 1;
        }}
        .btn-create-inline {{
            width: 32px;
            height: 32px;
            border-radius: 6px;
            border: 1px solid var(--primary-color, #2563EB);
            background: var(--primary-color, #2563EB);
            color: white;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s;
        }}
        .btn-create-inline:hover {{
            background: var(--primary-dark, #1d4ed8);
            transform: scale(1.05);
        }}
        .modal-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }}
        .modal-content {{
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid var(--gray-200, #e5e7eb);
        }}
        .modal-header h3 {{
            margin: 0;
            font-size: 18px;
        }}
        .modal-close {{
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--gray-500);
        }}
        .modal-body {{
            padding: 20px;
        }}
        .modal-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            padding: 16px 20px;
            border-top: 1px solid var(--gray-200, #e5e7eb);
        }}
    </style>
    '''


def generate_document_form(module, module_name: str) -> str:
    """Génère un formulaire style Odoo pour devis/factures."""

    doc_type = "Devis" if module_name.lower() == "devis" else "Facture"

    return f'''
    <div class="card">
        <div class="card-header">
            <div class="flex items-center gap-2">
                <span class="badge badge-gray">Nouveau</span>
            </div>
            <div class="flex gap-2">
                <button class="btn btn-secondary">Annuler</button>
                <button class="btn btn-primary" onclick="saveDocument()">Enregistrer</button>
            </div>
        </div>

        <div class="card-body">
            <!-- Section Client -->
            <div class="doc-section">
                <div class="doc-row">
                    <div class="doc-field">
                        <label class="label">Client</label>
                        <select class="input" id="client_id">
                            <option value="">Sélectionner un client...</option>
                        </select>
                    </div>
                    <div class="doc-field">
                        <label class="label">Date d'expiration</label>
                        <input type="date" class="input" id="date_validite" value="">
                    </div>
                </div>

                <div class="doc-row">
                    <div class="doc-field">
                        <label class="label">Adresse de facturation</label>
                        <textarea class="input" id="adresse_facturation" rows="2" placeholder="Adresse..."></textarea>
                    </div>
                    <div class="doc-field">
                        <label class="label">Conditions de paiement</label>
                        <select class="input" id="conditions">
                            <option value="immediate">Paiement immédiat</option>
                            <option value="30j">30 jours</option>
                            <option value="60j">60 jours</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- Section Lignes -->
            <div class="doc-section" style="margin-top: 24px;">
                <div class="doc-tabs">
                    <button class="doc-tab active">Lignes de commande</button>
                    <button class="doc-tab">Produits optionnels</button>
                    <button class="doc-tab">Autres informations</button>
                </div>

                <table class="table" style="margin-top: 16px;">
                    <thead>
                        <tr>
                            <th style="width: 50%;">Produit</th>
                            <th>Prix unit.</th>
                            <th>Quantité</th>
                            <th>Taxes</th>
                            <th>Montant</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="lignes-table">
                        <tr class="ligne-vide">
                            <td colspan="6" style="text-align: center; padding: 32px; color: var(--gray-400);">
                                Aucune ligne. Ajoutez un produit ci-dessous.
                            </td>
                        </tr>
                    </tbody>
                </table>

                <div class="doc-actions" style="margin-top: 12px;">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="ajouterLigne()">+ Ajouter un produit</button>
                    <button type="button" class="btn btn-secondary btn-sm">+ Ajouter une section</button>
                    <button type="button" class="btn btn-secondary btn-sm">+ Ajouter une note</button>
                </div>
            </div>

            <!-- Totaux -->
            <div class="doc-totals" style="margin-top: 24px; text-align: right;">
                <div class="doc-total-row">
                    <span>Total HT</span>
                    <span id="total-ht">0,00 €</span>
                </div>
                <div class="doc-total-row">
                    <span>TVA 20%</span>
                    <span id="total-tva">0,00 €</span>
                </div>
                <div class="doc-total-row" style="font-weight: 700; font-size: 18px;">
                    <span>Total TTC</span>
                    <span id="total-ttc">0,00 €</span>
                </div>
            </div>
        </div>
    </div>

    <script>
    let lignes = [];
    let ligneIndex = 0;

    function ajouterLigne() {{
        const tbody = document.getElementById('lignes-table');
        const videRow = tbody.querySelector('.ligne-vide');
        if (videRow) videRow.remove();

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><input type="text" class="input" placeholder="Nom du produit" onchange="calculerTotaux()"></td>
            <td><input type="number" class="input" value="0" step="0.01" style="width:80px" onchange="calculerTotaux()"></td>
            <td><input type="number" class="input" value="1" style="width:60px" onchange="calculerTotaux()"></td>
            <td><select class="input" style="width:100px"><option value="20">20%</option><option value="10">10%</option><option value="0">0%</option></select></td>
            <td class="montant">0,00 €</td>
            <td><button class="btn btn-sm" onclick="this.closest('tr').remove(); calculerTotaux();">✕</button></td>
        `;
        tbody.appendChild(tr);
        ligneIndex++;
    }}

    function calculerTotaux() {{
        let totalHT = 0;
        document.querySelectorAll('#lignes-table tr').forEach(tr => {{
            const inputs = tr.querySelectorAll('input');
            if (inputs.length >= 3) {{
                const prix = parseFloat(inputs[1].value) || 0;
                const qte = parseFloat(inputs[2].value) || 0;
                const montant = prix * qte;
                totalHT += montant;
                tr.querySelector('.montant').textContent = montant.toFixed(2) + ' €';
            }}
        }});

        const tva = totalHT * 0.20;
        const ttc = totalHT + tva;

        document.getElementById('total-ht').textContent = totalHT.toFixed(2) + ' €';
        document.getElementById('total-tva').textContent = tva.toFixed(2) + ' €';
        document.getElementById('total-ttc').textContent = ttc.toFixed(2) + ' €';
    }}

    function collectDocumentData() {{
        const data = {{
            client_id: document.getElementById('client_id').value || null,
            date_validite: document.getElementById('date_validite').value || null,
            adresse_facturation: document.getElementById('adresse_facturation').value || null,
            conditions: document.getElementById('conditions').value || 'immediate',
            lignes: [],
            total_ht: 0,
            total_tva: 0,
            total_ttc: 0
        }};

        // Collecter les lignes
        document.querySelectorAll('#lignes-table tr:not(.ligne-vide)').forEach(tr => {{
            const inputs = tr.querySelectorAll('input');
            const tvaSelect = tr.querySelector('select');
            if (inputs.length >= 3) {{
                const produit = inputs[0].value;
                const prix = parseFloat(inputs[1].value) || 0;
                const qte = parseFloat(inputs[2].value) || 0;
                const tauxTVA = parseFloat(tvaSelect?.value) || 20;

                if (produit || prix > 0) {{
                    data.lignes.push({{
                        produit: produit,
                        prix_unitaire: prix,
                        quantite: qte,
                        taux_tva: tauxTVA,
                        montant_ht: prix * qte,
                        montant_tva: (prix * qte) * (tauxTVA / 100)
                    }});
                }}
            }}
        }});

        // Calculer les totaux
        data.lignes.forEach(ligne => {{
            data.total_ht += ligne.montant_ht;
            data.total_tva += ligne.montant_tva;
        }});
        data.total_ttc = data.total_ht + data.total_tva;

        return data;
    }}

    async function saveDocument() {{
        const saveBtn = document.querySelector('.btn-primary[onclick="saveDocument()"]');
        if (!saveBtn || saveBtn.disabled) return;

        const originalText = saveBtn.innerHTML;

        // Validation basique
        const clientId = document.getElementById('client_id').value;
        const lignes = document.querySelectorAll('#lignes-table tr:not(.ligne-vide)');

        if (!clientId) {{
            alert('Veuillez selectionner un client');
            return;
        }}

        if (lignes.length === 0) {{
            alert('Veuillez ajouter au moins une ligne');
            return;
        }}

        // Etat de chargement
        saveBtn.disabled = true;
        saveBtn.innerHTML = 'Enregistrement...';

        try {{
            const data = collectDocumentData();

            const response = await fetch('/api/{module_name}', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }});

            if (response.ok) {{
                const result = await response.json();
                alert('{doc_type} cree avec succes !');
                window.location.href = '/ui/{module_name}';
            }} else {{
                const errorData = await response.json().catch(() => ({{}}));
                const errorMessage = errorData.detail || errorData.message || 'Erreur lors de l\\'enregistrement';
                alert(errorMessage);
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalText;
            }}
        }} catch (error) {{
            console.error('Erreur:', error);
            alert('Erreur de connexion au serveur');
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalText;
        }}
    }}

    // Charger les clients au chargement de la page
    document.addEventListener('DOMContentLoaded', async function() {{
        try {{
            const response = await fetch('/api/Client', {{ credentials: 'include' }});
            if (response.ok) {{
                const clients = await response.json();
                const select = document.getElementById('client_id');
                clients.forEach(client => {{
                    const option = document.createElement('option');
                    option.value = client.id;
                    option.textContent = client.nom || client.raison_sociale || client.id;
                    select.appendChild(option);
                }});
            }}
        }} catch (e) {{
            console.error('Erreur chargement clients:', e);
        }}

        // Date par defaut : aujourd'hui + 30 jours
        const dateValidite = document.getElementById('date_validite');
        const today = new Date();
        today.setDate(today.getDate() + 30);
        dateValidite.value = today.toISOString().split('T')[0];
    }});

    // Gestion des onglets
    document.querySelectorAll('.doc-tab').forEach(tab => {{
        tab.addEventListener('click', function() {{
            document.querySelectorAll('.doc-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');
        }});
    }});
    </script>
    '''


@ui_router.get("/{module_name}/{item_id}", response_class=HTMLResponse)
async def module_detail(
    module_name: str,
    item_id: str,
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Détail d'un enregistrement."""

    module = ModuleParser.get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")

    from uuid import UUID
    item = Database.get_by_id(module_name, tenant_id, UUID(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Enregistrement non trouvé")

    # Générer les champs avec valeurs
    fields_html = ""
    for nom, field in module.champs.items():
        if field.type not in ["auto", "calcul"]:
            fields_html += get_field_html(field, item.get(nom), module_name=module_name)

    # Statut et workflow
    statut_html = ""
    if "statut" in item and module.workflow:
        statut_html = f'''
        <div class="mb-4">
            <span class="text-muted">Statut:</span> {get_status_badge(item['statut'])}
        </div>
        '''

    # Generate documents section HTML
    documents_html = generate_documents_section(module_name, item_id)

    # Nom d'affichage pour le favori
    display_name = item.get('nom', item.get('name', item.get('titre', item.get('numero', item.get('reference', 'Sans nom')))))
    sous_titre = item.get('email', item.get('code', item.get('description', '')[:50] if item.get('description') else ''))
    item_statut = item.get('statut', '')
    module_icone = get_icon(module.icone) if module.icone else '📁'

    html = generate_layout(
        title=f"{module.nom_affichage} - Détail",
        content=f'''
        <div class="mb-6 flex justify-between items-center">
            <a href="/ui/{module_name}" class="text-muted">← Retour</a>
            <div class="flex items-center gap-3">
                <button class="star-btn" id="fav-btn-{item_id}"
                    onclick="toggleFavori('{module_name}', '{item_id}', `{display_name}`, `{sous_titre}`, '{item_statut}', '{module_icone}', this)"
                    title="Ajouter aux favoris">
                    ☆
                </button>
                {statut_html}
            </div>
        </div>

        <div class="card">
            <div class="card-header flex justify-between items-center">
                <h2 class="font-bold">{display_name}</h2>
                <div class="print-actions no-print">
                    <button onclick="openPrintPreview()" class="btn-print" title="Apercu avant impression">
                        <span class="print-icon">👁️</span>
                        <span class="hide-mobile">Apercu</span>
                    </button>
                    <button onclick="window.print()" class="btn-print btn-print-primary" title="Imprimer">
                        <span class="print-icon">🖨️</span>
                        <span class="hide-mobile">Imprimer</span>
                    </button>
                </div>
            </div>
            <form id="edit-form" class="card-body">
                {fields_html}
            </form>
            <div class="card-footer flex justify-between no-print">
                <div class="flex gap-2">
                    <button onclick="deleteItem()" class="btn btn-danger">Supprimer</button>
                    <button onclick="duplicateItem()" class="btn btn-secondary" title="Creer une copie de cet enregistrement">Dupliquer</button>
                </div>
                <div class="flex gap-3">
                    <a href="/ui/{module_name}" class="btn btn-secondary">Annuler</a>
                    <button onclick="saveItem()" class="btn btn-primary">Enregistrer</button>
                </div>
            </div>
        </div>

        <!-- Print Header (visible only when printing) -->
        <div class="print-only print-header">
            <div class="print-header-content">
                <div class="print-company">
                    <div class="print-company-name">AZALPLUS</div>
                    <div class="print-company-details">
                        Entreprise Demo<br>
                        123 Rue de l'Exemple<br>
                        75001 Paris, France<br>
                        Tel: 01 23 45 67 89
                    </div>
                </div>
                <div class="print-doc-info">
                    <div class="print-doc-type">{module.nom_affichage}</div>
                    <div class="print-doc-number">{display_name}</div>
                    <div class="print-doc-date">Imprime le: Date du jour</div>
                </div>
            </div>
        </div>

        <!-- Print Footer (visible only when printing) -->
        <div class="print-only print-footer">
            <div class="print-footer-legal">
                AZALPLUS - Document genere automatiquement
            </div>
        </div>

        <!-- Documents Section -->
        {documents_html}

        <script>
        async function saveItem() {{
            const form = document.getElementById('edit-form');
            const data = Object.fromEntries(new FormData(form));
            const res = await fetch('/api/{module_name}/{item_id}', {{
                method: 'PUT',
                credentials: 'include',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify(data)
            }});
            if (res.ok) window.location.reload();
            else alert('Erreur');
        }}

        async function deleteItem() {{
            if (!confirm('Supprimer ?')) return;
            const res = await fetch('/api/{module_name}/{item_id}', {{method: 'DELETE', credentials: 'include'}});
            if (res.ok) window.location = '/ui/{module_name}';
        }}

        // Document management functions
        async function loadDocuments() {{
            try {{
                const res = await fetch('/api/{module_name}/{item_id}/documents', {{credentials: 'include'}});
                if (res.ok) {{
                    const data = await res.json();
                    renderDocuments(data.documents);
                }}
            }} catch (e) {{
                console.error('Erreur chargement documents:', e);
            }}
        }}

        function renderDocuments(documents) {{
            const container = document.getElementById('documents-list');
            if (documents.length === 0) {{
                container.innerHTML = '<p class="text-muted">Aucun document attache</p>';
                return;
            }}

            let html = '<ul class="documents-list">';
            documents.forEach(doc => {{
                const sizeKB = (doc.taille / 1024).toFixed(1);
                const icon = getFileIcon(doc.type_mime);
                html += `
                    <li class="document-item">
                        <span class="doc-icon">${{icon}}</span>
                        <div class="doc-info">
                            <span class="doc-name">${{doc.nom}}</span>
                            <span class="doc-meta">${{sizeKB}} KB</span>
                        </div>
                        <div class="doc-actions">
                            <a href="/api/documents/${{doc.id}}/download" class="btn btn-sm btn-secondary" download>Telecharger</a>
                            <button onclick="deleteDocument('${{doc.id}}')" class="btn btn-sm btn-danger">Supprimer</button>
                        </div>
                    </li>
                `;
            }});
            html += '</ul>';
            container.innerHTML = html;
        }}

        function getFileIcon(mimeType) {{
            if (mimeType.startsWith('image/')) return '🖼️';
            if (mimeType.includes('pdf')) return '📄';
            if (mimeType.includes('word') || mimeType.includes('document')) return '📝';
            if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return '📊';
            if (mimeType.includes('zip') || mimeType.includes('archive')) return '📦';
            return '📎';
        }}

        async function uploadDocument() {{
            const input = document.getElementById('file-input');
            const file = input.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            try {{
                const res = await fetch('/api/{module_name}/{item_id}/documents', {{
                    method: 'POST',
                    credentials: 'include',
                    body: formData
                }});

                if (res.ok) {{
                    input.value = '';
                    loadDocuments();
                    showNotification('Document uploade avec succes', 'success');
                }} else {{
                    const data = await res.json();
                    showNotification(data.detail || 'Erreur upload', 'error');
                }}
            }} catch (e) {{
                showNotification('Erreur de connexion', 'error');
            }}
        }}

        async function deleteDocument(docId) {{
            if (!confirm('Supprimer ce document ?')) return;

            try {{
                const res = await fetch(`/api/documents/${{docId}}`, {{ method: 'DELETE', credentials: 'include' }});
                if (res.ok) {{
                    loadDocuments();
                    showNotification('Document supprime', 'success');
                }} else {{
                    showNotification('Erreur suppression', 'error');
                }}
            }} catch (e) {{
                showNotification('Erreur de connexion', 'error');
            }}
        }}

        function showNotification(message, type) {{
            const notif = document.getElementById('doc-notification');
            if (notif) {{
                notif.textContent = message;
                notif.className = 'notification ' + type;
                setTimeout(() => notif.classList.add('hidden'), 3000);
            }}
        }}

        // Load documents on page load
        document.addEventListener('DOMContentLoaded', loadDocuments);

        // Check if favorite and track recent view
        document.addEventListener('DOMContentLoaded', async function() {{
            // Check if this item is a favorite
            const isFav = await checkIsFavori('{module_name}', '{item_id}');
            const favBtn = document.getElementById('fav-btn-{item_id}');
            if (favBtn && isFav) {{
                favBtn.classList.add('active');
                favBtn.innerHTML = '★';
            }}

            // Track recent view
            trackRecent('{module_name}', '{item_id}', `{display_name}`, `{sous_titre}`, '{item_statut}', '{module_icone}');
        }});
        </script>
        ''',
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


# =============================================================================
# Layout Generator
# =============================================================================
def get_all_modules() -> List[Dict]:
    """Retourne tous les modules."""
    modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module:
            modules.append({
                "nom": module.nom,
                "nom_affichage": module.nom_affichage,
                "icone": module.icone,
                "menu": module.menu
            })
    return modules


def get_icon(icon_name: str, size: int = 20, css_class: str = "icon") -> str:
    """
    Retourne une balise img SVG pour l'icône.

    Args:
        icon_name: Nom de l'icône (sans extension)
        size: Taille en pixels (défaut: 20)
        css_class: Classe CSS à appliquer (défaut: "icon")

    Returns:
        Balise HTML img pointant vers le SVG
    """
    return f'<img src="/assets/icons/{icon_name}.svg" alt="{icon_name}" width="{size}" height="{size}" class="{css_class}" onerror="this.src=\'/assets/icons/default.svg\'" />'


def get_icon_url(icon_name: str) -> str:
    """Retourne l'URL de l'icône SVG."""
    return f"/assets/icons/{icon_name}.svg"


def generate_list_with_bulk_actions(
    module_name: str,
    module_display_name: str,
    table_headers: str,
    table_rows: str,
    has_status: bool = False,
    status_options: str = ""
) -> str:
    """Génère une liste avec actions en masse."""

    bulk_actions_html = ""
    if has_status:
        bulk_actions_html = f'''
        <div class="bulk-actions" id="bulk-actions" style="display: none;">
            <span class="bulk-count">0 sélectionné(s)</span>
            <select id="bulk-status" class="form-select" style="width: auto; display: inline-block;">
                <option value="">Changer le statut...</option>
                {status_options}
            </select>
            <button class="btn btn-secondary" onclick="applyBulkStatus()">Appliquer</button>
            <button class="btn btn-danger" onclick="deleteBulkItems()">Supprimer</button>
        </div>
        '''

    return f'''
    <div class="list-container">
        <div class="list-toolbar">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Rechercher..." class="form-control">
            </div>
            <a href="/ui/{module_name}/nouveau" class="btn btn-primary">+ Nouveau</a>
        </div>

        {bulk_actions_html}

        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th style="width: 40px;">
                            <input type="checkbox" id="select-all" onchange="toggleSelectAll()">
                        </th>
                        {table_headers}
                        <th style="width: 100px;">Actions</th>
                    </tr>
                </thead>
                <tbody id="list-body">
                    {table_rows}
                </tbody>
            </table>
        </div>

        <div class="pagination-container" id="pagination">
            <!-- Pagination générée par JS -->
        </div>
    </div>

    <script>
        function toggleSelectAll() {{
            const selectAll = document.getElementById('select-all');
            const checkboxes = document.querySelectorAll('.row-checkbox');
            checkboxes.forEach(cb => cb.checked = selectAll.checked);
            updateBulkActions();
        }}

        function updateBulkActions() {{
            const checkboxes = document.querySelectorAll('.row-checkbox:checked');
            const bulkActions = document.getElementById('bulk-actions');
            if (bulkActions) {{
                bulkActions.style.display = checkboxes.length > 0 ? 'flex' : 'none';
                bulkActions.querySelector('.bulk-count').textContent = checkboxes.length + ' sélectionné(s)';
            }}
        }}

        document.querySelectorAll('.row-checkbox').forEach(cb => {{
            cb.addEventListener('change', updateBulkActions);
        }});

        async function applyBulkStatus() {{
            const status = document.getElementById('bulk-status').value;
            if (!status) return alert('Veuillez sélectionner un statut');

            const ids = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => cb.value);
            if (ids.length === 0) return;

            try {{
                const response = await fetch('/api/v1/{module_name}/bulk', {{
                    method: 'PATCH',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{ ids, updates: {{ statut: status }} }})
                }});
                if (response.ok) {{
                    location.reload();
                }} else {{
                    alert('Erreur lors de la mise à jour');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        async function deleteBulkItems() {{
            const ids = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => cb.value);
            if (ids.length === 0) return;

            if (!confirm('Supprimer ' + ids.length + ' élément(s) ?')) return;

            try {{
                const response = await fetch('/api/v1/{module_name}/bulk', {{
                    method: 'DELETE',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{ ids }})
                }});
                if (response.ok) {{
                    location.reload();
                }} else {{
                    alert('Erreur lors de la suppression');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}
    </script>
    '''


def generate_layout(title: str, content: str, user: dict, modules: List[Dict]) -> str:
    """Génère le layout HTML complet style Axonaut."""

    # Get user's enabled modules from database (modules_mobile field)
    user_id = user.get("id")
    tenant_id = user.get("tenant_id")
    enabled_modules = None

    if user_id and tenant_id:
        try:
            with Database.get_session() as session:
                from sqlalchemy import text
                import json as json_lib
                result = session.execute(
                    text("""
                        SELECT modules_mobile
                        FROM azalplus.utilisateurs
                        WHERE id = :user_id AND tenant_id = :tenant_id
                    """),
                    {"user_id": str(user_id), "tenant_id": str(tenant_id)}
                )
                row = result.fetchone()
                if row and row[0]:
                    enabled_modules = json_lib.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            pass  # If error, show all modules

    # Filter modules if user has custom enabled modules
    if enabled_modules is not None and len(enabled_modules) > 0:
        modules = [m for m in modules if m.get("nom") in enabled_modules]

    # Grouper les modules par menu
    menus = {}
    for m in modules:
        menu = m.get("menu", "Général")
        if menu not in menus:
            menus[menu] = []
        menus[menu].append(m)

    # Sidebar navigation
    sidebar_html = ""
    for menu, items in menus.items():
        sidebar_html += f'<div class="nav-section"><div class="nav-title">{menu}</div>'
        for m in items:
            sidebar_html += f'''
            <a href="/ui/{m['nom']}" class="nav-item">
                <span class="nav-icon">{get_icon(m['icone'])}</span>
                <span>{m['nom_affichage']}</span>
            </a>
            '''
        sidebar_html += '</div>'

    # User initials
    user_name = user.get('nom', user.get('email', 'U'))
    initials = ''.join([n[0].upper() for n in user_name.split()[:2]]) if user_name else 'U'

    return f'''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - AZALPLUS</title>
    <link rel="stylesheet" href="/static/style.css">
    <script>
    // Notification bell - defined early so onclick works
    var notifPanelOpen = false;
    function toggleNotifPanel(event) {{
        if (event) {{ event.preventDefault(); event.stopPropagation(); }}
        var panel = document.getElementById('notif-panel');
        if (!panel) {{ console.error('Panel not found'); return; }}
        notifPanelOpen = !notifPanelOpen;
        panel.style.display = notifPanelOpen ? 'block' : 'none';
        console.log('Bell clicked, panel open:', notifPanelOpen);
        if (notifPanelOpen) {{
            loadNotifications();
        }}
    }}
    </script>
</head>
<body>
    <div class="app-layout">
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="sidebar-logo">AZALPLUS</div>

            <nav class="sidebar-nav">
                <div class="nav-section">
                    <a href="/ui/" class="nav-item">
                        <span class="nav-icon">🏠</span>
                        <span>Dashboard</span>
                    </a>
                    <a href="/ui/calendrier" class="nav-item">
                        <span class="nav-icon">📅</span>
                        <span>Calendrier</span>
                    </a>
                    <a href="/ui/favoris" class="nav-item">
                        <span class="nav-icon">⭐</span>
                        <span>Favoris</span>
                    </a>
                </div>

                <!-- Favoris epingles -->
                <div class="nav-section" id="sidebar-favoris">
                    <div class="nav-title">Acces rapide</div>
                    <div id="favoris-list" class="favoris-sidebar-list">
                        <!-- Charge dynamiquement -->
                    </div>
                </div>

                {sidebar_html}

                <!-- Paramètres -->
                <div class="nav-section">
                    <div class="nav-title">Paramètres</div>
                    <a href="/ui/parametres/modules" class="nav-item">
                        <span class="nav-icon">📦</span>
                        <span>Modules actifs</span>
                    </a>
                    <a href="/ui/parametres/theme" class="nav-item">
                        <span class="nav-icon">🎨</span>
                        <span>Style documents</span>
                    </a>
                    <a href="/ui/parametres/autocompletion-ia" class="nav-item">
                        <span class="nav-icon">✨</span>
                        <span>Autocomplétion IA</span>
                        <span style="margin-left: auto; font-size: 10px; background: var(--purple-100); color: var(--purple-700); padding: 2px 6px; border-radius: 10px;">Nouveau</span>
                    </a>
                </div>
            </nav>

            <div class="sidebar-user">
                <div class="user-box">
                    <div class="user-avatar">{initials}</div>
                    <div>
                        <div class="user-name">{user.get('nom', 'Utilisateur')}</div>
                        <div class="user-email">{user.get('email', '')}</div>
                    </div>
                </div>
                <a href="/login" onclick="localStorage.clear();" class="nav-item" style="margin-top: 8px; color: var(--gray-500);">
                    <span class="nav-icon">🚪</span>
                    <span>Déconnexion</span>
                </a>
            </div>
        </aside>

        <!-- Main content -->
        <div class="main-wrapper">
            <header class="main-header">
                <form class="header-search" action="/ui/search" method="GET">
                    <span style="margin-right: 8px; color: var(--gray-400);">🔍</span>
                    <input type="text" name="q" placeholder="Rechercher clients, factures, devis..." autocomplete="off">
                </form>

                <div class="header-actions">
                    <a href="javascript:void(0)" class="header-mobile" id="mobile-btn" onclick="openMobileModal(event); return false;" title="Application mobile">
                        <span class="mobile-icon">📱</span>
                    </a>
                    <a href="javascript:void(0)" class="header-notif" id="notif-bell" onclick="toggleNotifPanel(event); return false;">
                        <span class="notif-icon-bell">🔔</span>
                        <span class="notif-badge" id="notif-count">0</span>
                    </a>
                    <div id="notif-panel" class="notif-panel" style="display: none;">
                        <div class="notif-panel-header">
                            <strong>Notifications</strong>
                            <a href="/ui/notifications">Tout voir</a>
                        </div>
                        <div id="notif-list" class="notif-list">
                            <p class="notif-empty">Chargement...</p>
                        </div>
                    </div>
                    <a href="/ui/Devis/nouveau" class="btn btn-primary">+ Ajouter</a>
                </div>
            </header>

            <main class="main-content">
                <h1 class="page-title mb-4">{title}</h1>
                {content}
            </main>
        </div>
    </div>

    <style>
        /* Favoris Sidebar */
        .favoris-sidebar-list {{
            max-height: 200px;
            overflow-y: auto;
        }}
        .favoris-sidebar-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 6px;
            color: var(--gray-600);
            font-size: 12px;
            text-decoration: none;
            transition: all 0.15s;
        }}
        .favoris-sidebar-item:hover {{
            background: var(--gray-100);
            color: var(--gray-900);
        }}
        .favoris-sidebar-item .fav-icon {{
            font-size: 14px;
        }}
        .favoris-sidebar-item .fav-name {{
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        /* Star Button */
        .star-btn {{
            background: none;
            border: none;
            cursor: pointer;
            font-size: 18px;
            padding: 4px;
            transition: transform 0.2s;
            line-height: 1;
        }}
        .star-btn:hover {{
            transform: scale(1.2);
        }}
        .star-btn.active {{
            color: #F59E0B;
        }}
        .star-btn:not(.active) {{
            color: var(--gray-300);
        }}
        .star-btn.loading {{
            opacity: 0.5;
            pointer-events: none;
        }}

        /* Table star column */
        .table .col-star {{
            width: 40px;
            text-align: center;
        }}

        /* Notification Panel */
        .header-notif {{
            position: relative;
            cursor: pointer;
            padding: 8px;
            border-radius: 8px;
            transition: background 0.15s;
            user-select: none;
            text-decoration: none;
            display: inline-block;
            color: inherit;
        }}
        .header-notif:hover {{
            background: var(--gray-100);
        }}
        .notif-badge {{
            position: absolute;
            top: 2px;
            right: 2px;
            min-width: 18px;
            height: 18px;
            background: #EF4444;
            color: white;
            font-size: 11px;
            font-weight: 600;
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: none;
        }}
        .notif-icon-bell {{
            font-size: 20px;
            display: block;
        }}
        .notif-panel {{
            position: absolute;
            top: 100%;
            right: 0;
            width: 320px;
            max-height: 400px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            z-index: 1000;
            overflow: hidden;
            margin-top: 8px;
        }}
        .notif-panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid var(--gray-200);
            background: var(--gray-50);
        }}
        .notif-panel-header a {{
            font-size: 12px;
            color: var(--primary);
            text-decoration: none;
        }}
        .notif-list {{
            max-height: 320px;
            overflow-y: auto;
        }}
        .notif-item {{
            display: flex;
            gap: 12px;
            padding: 12px 16px;
            border-bottom: 1px solid var(--gray-100);
            cursor: pointer;
            transition: background 0.15s;
        }}
        .notif-item:hover {{
            background: var(--gray-50);
        }}
        .notif-item.unread {{
            background: #EFF6FF;
        }}
        .notif-icon {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: var(--gray-100);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .notif-content {{
            flex: 1;
            min-width: 0;
        }}
        .notif-title {{
            font-size: 13px;
            font-weight: 500;
            color: var(--gray-900);
            margin-bottom: 2px;
        }}
        .notif-desc {{
            font-size: 12px;
            color: var(--gray-500);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .notif-time {{
            font-size: 11px;
            color: var(--gray-400);
            margin-top: 4px;
        }}
        .notif-empty {{
            padding: 24px;
            text-align: center;
            color: var(--gray-400);
            font-size: 13px;
        }}
    </style>

    <script>
    // ==========================================================================
    // Notifications - JavaScript
    // ==========================================================================

    let notifPanelOpen = false;

    function toggleNotifPanel(event) {{
        if (event) event.stopPropagation();
        const panel = document.getElementById('notif-panel');
        notifPanelOpen = !notifPanelOpen;
        panel.style.display = notifPanelOpen ? 'block' : 'none';
        if (notifPanelOpen) {{
            loadNotifications();
        }}
    }}

    // Attacher l'événement au clic sur la cloche
    document.addEventListener('DOMContentLoaded', function() {{
        const bell = document.getElementById('notif-bell');
        if (bell) {{
            bell.addEventListener('click', toggleNotifPanel);
            console.log('Notification bell listener attached');
        }}
    }});

    // Fermer le panel si on clique ailleurs
    document.addEventListener('click', function(e) {{
        const panel = document.getElementById('notif-panel');
        const notifBtn = document.getElementById('notif-bell');
        if (notifPanelOpen && panel && notifBtn && !panel.contains(e.target) && !notifBtn.contains(e.target)) {{
            panel.style.display = 'none';
            notifPanelOpen = false;
        }}
    }});

    async function loadNotifications() {{
        const list = document.getElementById('notif-list');
        const countBadge = document.getElementById('notif-count');

        try {{
            const response = await fetch('/api/notifications?limit=10&order_by=created_at&order_dir=desc', {{
                credentials: 'include'
            }});

            if (response.ok) {{
                const data = await response.json();
                const items = data.items || data || [];

                if (items.length === 0) {{
                    list.innerHTML = '<p class="notif-empty">Aucune notification</p>';
                    countBadge.textContent = '0';
                    countBadge.style.display = 'none';
                    return;
                }}

                // Compter les non lues
                const unreadCount = items.filter(n => !n.read && !n.lu).length;
                countBadge.textContent = unreadCount;
                countBadge.style.display = unreadCount > 0 ? 'flex' : 'none';

                list.innerHTML = items.map(n => {{
                    const isUnread = !n.read && !n.lu;
                    const icon = n.type === 'success' ? '✅' : n.type === 'warning' ? '⚠️' : n.type === 'error' ? '❌' : '📣';
                    const time = n.created_at ? new Date(n.created_at).toLocaleString('fr-FR', {{day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'}}) : '';
                    return `
                        <div class="notif-item ${{isUnread ? 'unread' : ''}}" onclick="markNotifRead('${{n.id}}')">
                            <div class="notif-icon">${{icon}}</div>
                            <div class="notif-content">
                                <div class="notif-title">${{n.titre || n.title || 'Notification'}}</div>
                                <div class="notif-desc">${{n.message || n.contenu || ''}}</div>
                                <div class="notif-time">${{time}}</div>
                            </div>
                        </div>
                    `;
                }}).join('');

            }} else {{
                list.innerHTML = '<p class="notif-empty">Erreur de chargement</p>';
            }}
        }} catch (e) {{
            console.error('Erreur notifications:', e);
            list.innerHTML = '<p class="notif-empty">Aucune notification</p>';
            countBadge.textContent = '0';
            countBadge.style.display = 'none';
        }}
    }}

    async function markNotifRead(id) {{
        try {{
            await fetch(`/api/notifications/${{id}}`, {{
                method: 'PUT',
                credentials: 'include',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ read: true, lu: true }})
            }});
            loadNotifications();
        }} catch (e) {{
            console.error('Erreur marquage notification:', e);
        }}
    }}

    // Charger le compteur au démarrage
    document.addEventListener('DOMContentLoaded', function() {{
        loadNotifications();
    }});

    // ==========================================================================
    // Favoris & Recent - JavaScript
    // ==========================================================================

    // Charger les favoris dans la sidebar
    async function loadSidebarFavoris() {{
        try {{
            const res = await fetch('/api/favoris?limit=10&order_by=created_at&order_dir=desc', {{
                credentials: 'include'
            }});
            if (res.ok) {{
                const data = await res.json();
                const container = document.getElementById('favoris-list');
                if (data.items && data.items.length > 0) {{
                    container.innerHTML = data.items.map(fav => `
                        <a href="/ui/${{fav.module}}/${{fav.record_id}}" class="favoris-sidebar-item">
                            <span class="fav-icon">${{fav.module_icone || '📁'}}</span>
                            <span class="fav-name">${{fav.nom}}</span>
                            ${{fav.epingle ? '<span style="color: #F59E0B;">📌</span>' : ''}}
                        </a>
                    `).join('');
                }} else {{
                    container.innerHTML = '<div style="padding: 8px 12px; color: var(--gray-400); font-size: 12px;">Aucun favori</div>';
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement favoris:', e);
        }}
    }}

    // Toggle favori avec mise a jour optimiste
    async function toggleFavori(module, recordId, nom, sousTitre, statut, moduleIcone, button) {{
        const isActive = button.classList.contains('active');
        const originalState = isActive;

        // Mise a jour optimiste
        button.classList.add('loading');
        button.classList.toggle('active');
        button.innerHTML = isActive ? '☆' : '★';

        try {{
            if (isActive) {{
                // Retirer le favori - d'abord trouver l'ID du favori
                const searchRes = await fetch(`/api/favoris?module=${{encodeURIComponent(module)}}&record_id=${{recordId}}`, {{
                    credentials: 'include'
                }});
                if (searchRes.ok) {{
                    const searchData = await searchRes.json();
                    const favori = searchData.items && searchData.items.find(f =>
                        f.module === module && f.record_id === recordId
                    );
                    if (favori) {{
                        await fetch(`/api/favoris/${{favori.id}}`, {{
                            method: 'DELETE',
                            credentials: 'include'
                        }});
                    }}
                }}
            }} else {{
                // Ajouter le favori
                await fetch('/api/favoris', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        module: module,
                        record_id: recordId,
                        nom: nom || 'Sans nom',
                        sous_titre: sousTitre || '',
                        statut: statut || '',
                        module_icone: moduleIcone || '📁',
                        epingle: false
                    }})
                }});
            }}

            // Recharger la sidebar
            loadSidebarFavoris();

        }} catch (e) {{
            // Rollback en cas d'erreur
            console.error('Erreur toggle favori:', e);
            button.classList.toggle('active');
            button.innerHTML = originalState ? '★' : '☆';
        }} finally {{
            button.classList.remove('loading');
        }}
    }}

    // Verifier si un enregistrement est en favori
    async function checkIsFavori(module, recordId) {{
        try {{
            const res = await fetch(`/api/favoris?limit=100`, {{
                credentials: 'include'
            }});
            if (res.ok) {{
                const data = await res.json();
                return data.items && data.items.some(f =>
                    f.module === module && f.record_id === recordId
                );
            }}
        }} catch (e) {{
            console.error('Erreur verification favori:', e);
        }}
        return false;
    }}

    // Tracker une visite (recent)
    async function trackRecent(module, recordId, nom, sousTitre, statut, moduleIcone) {{
        try {{
            // Envoyer la visite au backend
            await fetch('/api/recent/track', {{
                method: 'POST',
                credentials: 'include',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    module: module,
                    record_id: recordId,
                    nom: nom || 'Sans nom',
                    sous_titre: sousTitre || '',
                    statut: statut || '',
                    module_icone: moduleIcone || '📁'
                }})
            }});
        }} catch (e) {{
            // Ignorer les erreurs de tracking silencieusement
            console.debug('Erreur tracking recent:', e);
        }}
    }}

    // Charger les favoris au demarrage
    document.addEventListener('DOMContentLoaded', function() {{
        loadSidebarFavoris();
        initAutocompletion();
    }});

    // ==========================================================================
    // Autocompletion IA - JavaScript
    // ==========================================================================
    let autocompleteDebounceTimer = null;
    let currentAutocompleteInput = null;

    function initAutocompletion() {{
        document.querySelectorAll('input[data-autocomplete="true"]').forEach(input => {{
            const suggestionsDiv = document.getElementById(input.id + '_suggestions');
            if (!suggestionsDiv) return;

            // Input handler avec debounce
            input.addEventListener('input', function(e) {{
                const value = e.target.value;
                const module = input.dataset.module || 'default';
                const champ = input.dataset.champ || input.name;

                if (autocompleteDebounceTimer) clearTimeout(autocompleteDebounceTimer);

                if (value.length < 2) {{
                    suggestionsDiv.innerHTML = '';
                    suggestionsDiv.style.display = 'none';
                    return;
                }}

                autocompleteDebounceTimer = setTimeout(() => {{
                    fetchAutocompleteSuggestions(input, suggestionsDiv, module, champ, value);
                }}, 300);
            }});

            // Navigation clavier
            input.addEventListener('keydown', function(e) {{
                const items = suggestionsDiv.querySelectorAll('.autocomplete-item');
                const activeItem = suggestionsDiv.querySelector('.autocomplete-item.active');
                let activeIndex = Array.from(items).indexOf(activeItem);

                if (e.key === 'ArrowDown') {{
                    e.preventDefault();
                    if (activeIndex < items.length - 1) {{
                        if (activeItem) activeItem.classList.remove('active');
                        items[activeIndex + 1].classList.add('active');
                    }} else if (!activeItem && items.length > 0) {{
                        items[0].classList.add('active');
                    }}
                }} else if (e.key === 'ArrowUp') {{
                    e.preventDefault();
                    if (activeIndex > 0) {{
                        activeItem.classList.remove('active');
                        items[activeIndex - 1].classList.add('active');
                    }}
                }} else if (e.key === 'Enter' && activeItem) {{
                    e.preventDefault();
                    selectSuggestion(input, activeItem.dataset.value, suggestionsDiv);
                }} else if (e.key === 'Tab' && items.length > 0) {{
                    e.preventDefault();
                    const firstItem = items[0];
                    selectSuggestion(input, firstItem.dataset.value, suggestionsDiv);
                }} else if (e.key === 'Escape') {{
                    suggestionsDiv.innerHTML = '';
                    suggestionsDiv.style.display = 'none';
                }}
            }});

            // Fermer quand on clique ailleurs
            document.addEventListener('click', function(e) {{
                if (!input.contains(e.target) && !suggestionsDiv.contains(e.target)) {{
                    suggestionsDiv.innerHTML = '';
                    suggestionsDiv.style.display = 'none';
                }}
            }});
        }});
    }}

    async function fetchAutocompleteSuggestions(input, suggestionsDiv, module, champ, value) {{
        try {{
            const response = await fetch('/api/autocompletion-ia/suggest', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    module: module,
                    champ: champ,
                    valeur: value,
                    limite: 5
                }})
            }});

            if (response.ok) {{
                const data = await response.json();
                if (data.suggestions && data.suggestions.length > 0) {{
                    renderSuggestions(input, suggestionsDiv, data.suggestions);
                }} else {{
                    suggestionsDiv.innerHTML = '';
                    suggestionsDiv.style.display = 'none';
                }}
            }}
        }} catch (e) {{
            console.debug('Autocompletion error:', e);
        }}
    }}

    function renderSuggestions(input, suggestionsDiv, suggestions) {{
        suggestionsDiv.innerHTML = suggestions.map((s, i) => `
            <div class="autocomplete-item ${{i === 0 ? 'active' : ''}}" data-value="${{s.texte}}" data-id="${{s.id}}">
                <span class="suggestion-text">${{s.texte}}</span>
                <span class="suggestion-source">${{s.source === 'ia' ? '✨' : s.source === 'historique' ? '📖' : ''}}</span>
            </div>
        `).join('');
        suggestionsDiv.style.display = 'block';

        // Click handlers
        suggestionsDiv.querySelectorAll('.autocomplete-item').forEach(item => {{
            item.addEventListener('click', () => {{
                selectSuggestion(input, item.dataset.value, suggestionsDiv);
            }});
        }});
    }}

    function selectSuggestion(input, value, suggestionsDiv) {{
        input.value = value;
        suggestionsDiv.innerHTML = '';
        suggestionsDiv.style.display = 'none';
        input.focus();
        // Trigger change event
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }}

    // ==========================================================================
    // Auto-remplissage multi-sources (SIRET, Code Postal, Code-barres, IBAN, TVA)
    // ==========================================================================
    function initAutoFill() {{
        // ---- SIRET / SIREN ----
        const siretFields = document.querySelectorAll('input[name*="siret" i], input[id*="siret" i]');
        const sirenFields = document.querySelectorAll('input[name*="siren" i], input[id*="siren" i]');

        siretFields.forEach(input => {{
            input.addEventListener('blur', handleSIRETChange);
            input.addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') handleSIRETChange.call(this, e);
            }});
            addSearchIcon(input, 'SIRET');
        }});

        sirenFields.forEach(input => {{
            if (!input.name.toLowerCase().includes('siret')) {{
                input.addEventListener('blur', handleSIRENChange);
                input.addEventListener('keypress', function(e) {{
                    if (e.key === 'Enter') handleSIRENChange.call(this, e);
                }});
                addSearchIcon(input, 'SIREN');
            }}
        }});

        // ---- CODE POSTAL → VILLE ----
        const cpFields = document.querySelectorAll('input[name*="code_postal" i], input[name*="cp" i], input[name="postal_code" i], input[id*="code_postal" i]');
        cpFields.forEach(input => {{
            input.addEventListener('blur', handleCodePostalChange);
            input.addEventListener('input', debounce(handleCodePostalChange, 500));
        }});

        // ---- CODE-BARRES → PRODUIT ----
        const barcodeFields = document.querySelectorAll('input[name*="code_barre" i], input[name*="ean" i], input[name*="barcode" i], input[name*="upc" i], input[id*="code_barre" i]');
        barcodeFields.forEach(input => {{
            input.addEventListener('blur', handleBarcodeChange);
            input.addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') handleBarcodeChange.call(this, e);
            }});
            addSearchIcon(input, 'Code-barres');
        }});

        // ---- IBAN → VALIDATION ----
        const ibanFields = document.querySelectorAll('input[name*="iban" i], input[id*="iban" i]');
        ibanFields.forEach(input => {{
            input.addEventListener('blur', handleIBANChange);
        }});

        // ---- TVA → VALIDATION ----
        const tvaFields = document.querySelectorAll('input[name*="tva" i], input[name*="vat" i], input[id*="tva" i]');
        tvaFields.forEach(input => {{
            if (!input.name.toLowerCase().includes('taux')) {{  // Exclure taux_tva
                input.addEventListener('blur', handleTVAChange);
            }}
        }});

        // ---- ADRESSE → AUTOCOMPLETION ----
        const adresseFields = document.querySelectorAll('input[name="adresse" i], input[name="adresse_ligne1" i], input[name="address" i], input[id*="adresse" i]');
        adresseFields.forEach(input => {{
            initAdresseAutocomplete(input);
        }});
    }}

    // Alias pour compatibilité
    function initAutoFillSIRET() {{
        initAutoFill();
    }}

    // Debounce utility
    function debounce(func, wait) {{
        let timeout;
        return function executedFunction(...args) {{
            const later = () => {{
                clearTimeout(timeout);
                func.apply(this, args);
            }};
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        }};
    }}

    function addSearchIcon(input, type) {{
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        wrapper.style.display = 'inline-block';
        wrapper.style.width = '100%';

        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const icon = document.createElement('span');
        icon.innerHTML = '🔍';
        icon.style.cssText = 'position: absolute; right: 10px; top: 50%; transform: translateY(-50%); cursor: pointer; opacity: 0.5; font-size: 14px;';
        icon.title = `Rechercher par ${{type}}`;
        icon.onclick = () => {{
            if (type === 'SIRET') handleSIRETChange.call(input);
            else handleSIRENChange.call(input);
        }};
        wrapper.appendChild(icon);
    }}

    async function handleSIRETChange(e) {{
        const siret = this.value.replace(/[\\s.]/g, '');
        if (siret.length !== 14 || !/^\\d+$/.test(siret)) return;

        await autoFillFromSIRET(siret);
    }}

    async function handleSIRENChange(e) {{
        const siren = this.value.replace(/[\\s.]/g, '');
        if (siren.length !== 9 || !/^\\d+$/.test(siren)) return;

        await autoFillFromSIREN(siren);
    }}

    async function autoFillFromSIRET(siret) {{
        showAutoFillLoading(true);
        try {{
            const response = await fetch(`/api/autocompletion-ia/entreprise/siret/${{siret}}`);
            if (response.ok) {{
                const data = await response.json();
                fillFormWithEntrepriseData(data);
                showAutoFillNotification('✅ Informations entreprise récupérées', 'success');
            }} else {{
                showAutoFillNotification('❌ Entreprise non trouvée pour ce SIRET', 'error');
            }}
        }} catch (e) {{
            console.error('Erreur auto-fill SIRET:', e);
            showAutoFillNotification('❌ Erreur lors de la recherche', 'error');
        }}
        showAutoFillLoading(false);
    }}

    async function autoFillFromSIREN(siren) {{
        showAutoFillLoading(true);
        try {{
            const response = await fetch(`/api/autocompletion-ia/entreprise/siren/${{siren}}`);
            if (response.ok) {{
                const data = await response.json();
                fillFormWithEntrepriseData(data);
                showAutoFillNotification('✅ Informations entreprise récupérées', 'success');
            }} else {{
                showAutoFillNotification('❌ Entreprise non trouvée pour ce SIREN', 'error');
            }}
        }} catch (e) {{
            console.error('Erreur auto-fill SIREN:', e);
            showAutoFillNotification('❌ Erreur lors de la recherche', 'error');
        }}
        showAutoFillLoading(false);
    }}

    // ==========================================================================
    // CODE POSTAL → VILLE
    // ==========================================================================
    async function handleCodePostalChange() {{
        const cp = this.value.replace(/\\s/g, '');
        if (cp.length !== 5 || !/^\\d+$/.test(cp)) return;

        try {{
            const response = await fetch(`/api/autocompletion-ia/adresse/cp/${{cp}}`);
            if (response.ok) {{
                const data = await response.json();
                fillFormWithAdresseData(data);
                showAutoFillNotification('📍 Ville identifiée', 'success');
            }}
        }} catch (e) {{
            console.error('Erreur lookup code postal:', e);
        }}
    }}

    function fillFormWithAdresseData(data) {{
        const mappings = {{
            'ville': ['ville', 'city', 'commune', 'localite'],
            'departement': ['departement', 'dept'],
            'region': ['region'],
            'code_postal': ['code_postal', 'cp', 'postal_code']
        }};

        for (const [apiField, formFields] of Object.entries(mappings)) {{
            const value = data[apiField];
            if (!value) continue;

            for (const fieldName of formFields) {{
                try {{
                    const field = document.querySelector(`input[name="${{fieldName}}" i], input[id*="${{fieldName}}" i]`);
                    if (field && !field.value) {{
                        field.value = value;
                        field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        highlightField(field);
                        break;
                    }}
                }} catch (e) {{}}
            }}
        }}
    }}

    // ==========================================================================
    // CODE-BARRES → PRODUIT
    // ==========================================================================
    async function handleBarcodeChange() {{
        const barcode = this.value.replace(/[\\s-]/g, '');
        if (!/^\\d{{8,14}}$/.test(barcode)) return;

        showAutoFillLoading(true);
        try {{
            const response = await fetch(`/api/autocompletion-ia/produit/barcode/${{barcode}}`);
            if (response.ok) {{
                const data = await response.json();
                fillFormWithProduitData(data);
                showAutoFillNotification('📦 Produit identifié: ' + (data.nom || barcode), 'success');
            }} else {{
                showAutoFillNotification('❌ Produit non trouvé', 'error');
            }}
        }} catch (e) {{
            console.error('Erreur lookup produit:', e);
            showAutoFillNotification('❌ Erreur lors de la recherche', 'error');
        }}
        showAutoFillLoading(false);
    }}

    function fillFormWithProduitData(data) {{
        const mappings = {{
            'nom': ['nom', 'nom_produit', 'designation', 'libelle', 'name', 'product_name'],
            'marque': ['marque', 'brand', 'fabricant'],
            'categorie': ['categorie', 'category', 'famille'],
            'code_barres': ['code_barres', 'ean', 'upc', 'barcode', 'gtin'],
            'quantite': ['quantite', 'quantity', 'contenance'],
            'origine': ['origine', 'origin', 'provenance'],
            'nutriscore': ['nutriscore', 'score_nutritionnel'],
            'ingredients': ['ingredients', 'composition']
        }};

        let filledCount = 0;
        for (const [apiField, formFields] of Object.entries(mappings)) {{
            const value = data[apiField];
            if (!value) continue;

            for (const fieldName of formFields) {{
                try {{
                    const field = document.querySelector(`input[name="${{fieldName}}" i], textarea[name="${{fieldName}}" i]`);
                    if (field && !field.value) {{
                        field.value = value;
                        field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        highlightField(field);
                        filledCount++;
                        break;
                    }}
                }} catch (e) {{}}
            }}
        }}
        console.log(`Auto-fill produit: ${{filledCount}} champs remplis`);
    }}

    // ==========================================================================
    // IBAN → VALIDATION
    // ==========================================================================
    async function handleIBANChange() {{
        const iban = this.value.replace(/[\\s-]/g, '').toUpperCase();
        if (iban.length < 15) return;

        try {{
            const response = await fetch(`/api/autocompletion-ia/iban/validate/${{iban}}`);
            if (response.ok) {{
                const data = await response.json();
                if (data.valid) {{
                    this.value = data.iban_formate || iban;
                    highlightField(this);
                    showAutoFillNotification('✅ IBAN valide', 'success');
                    // Remplir les infos bancaires si disponibles
                    fillFormWithBankData(data);
                }} else {{
                    this.style.borderColor = '#dc3545';
                    showAutoFillNotification('❌ IBAN invalide: ' + (data.error || ''), 'error');
                }}
            }}
        }} catch (e) {{
            console.error('Erreur validation IBAN:', e);
        }}
    }}

    function fillFormWithBankData(data) {{
        const mappings = {{
            'code_banque': ['code_banque', 'bank_code'],
            'code_guichet': ['code_guichet', 'branch_code'],
            'cle_rib': ['cle_rib', 'rib_key']
        }};

        for (const [apiField, formFields] of Object.entries(mappings)) {{
            const value = data[apiField];
            if (!value) continue;

            for (const fieldName of formFields) {{
                try {{
                    const field = document.querySelector(`input[name="${{fieldName}}" i]`);
                    if (field && !field.value) {{
                        field.value = value;
                        highlightField(field);
                        break;
                    }}
                }} catch (e) {{}}
            }}
        }}
    }}

    // ==========================================================================
    // TVA → VALIDATION
    // ==========================================================================
    async function handleTVAChange() {{
        const tva = this.value.replace(/[\\s.-]/g, '').toUpperCase();
        if (tva.length < 4 || !/^[A-Z]{{2}}/.test(tva)) return;

        showAutoFillLoading(true);
        try {{
            const response = await fetch(`/api/autocompletion-ia/tva/validate/${{tva}}`);
            if (response.ok) {{
                const data = await response.json();
                if (data.valid) {{
                    highlightField(this);
                    showAutoFillNotification('✅ TVA valide: ' + (data.nom || tva), 'success');
                    // Remplir le nom si trouvé via VIES
                    if (data.nom) {{
                        fillFormField(['nom', 'nom_entreprise', 'raison_sociale'], data.nom);
                    }}
                    if (data.adresse) {{
                        fillFormField(['adresse', 'adresse_ligne1'], data.adresse);
                    }}
                }} else {{
                    this.style.borderColor = '#dc3545';
                    showAutoFillNotification('❌ TVA invalide', 'error');
                }}
            }}
        }} catch (e) {{
            console.error('Erreur validation TVA:', e);
        }}
        showAutoFillLoading(false);
    }}

    function fillFormField(fieldNames, value) {{
        for (const fieldName of fieldNames) {{
            try {{
                const field = document.querySelector(`input[name="${{fieldName}}" i], textarea[name="${{fieldName}}" i]`);
                if (field && !field.value) {{
                    field.value = value;
                    field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    highlightField(field);
                    return true;
                }}
            }} catch (e) {{}}
        }}
        return false;
    }}

    // ==========================================================================
    // ADRESSE → AUTOCOMPLETION
    // ==========================================================================
    function initAdresseAutocomplete(input) {{
        const wrapper = document.createElement('div');
        wrapper.className = 'adresse-autocomplete-wrapper';
        wrapper.style.position = 'relative';

        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const suggestionsDiv = document.createElement('div');
        suggestionsDiv.className = 'adresse-suggestions';
        suggestionsDiv.style.cssText = `
            position: absolute; top: 100%; left: 0; right: 0;
            background: white; border: 1px solid #ddd; border-top: none;
            max-height: 200px; overflow-y: auto; z-index: 1000;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: none;
        `;
        wrapper.appendChild(suggestionsDiv);

        let debounceTimer;
        input.addEventListener('input', function() {{
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => fetchAdresseSuggestions(this, suggestionsDiv), 300);
        }});

        input.addEventListener('blur', () => {{
            setTimeout(() => suggestionsDiv.style.display = 'none', 200);
        }});
    }}

    async function fetchAdresseSuggestions(input, suggestionsDiv) {{
        const query = input.value.trim();
        if (query.length < 3) {{
            suggestionsDiv.style.display = 'none';
            return;
        }}

        try {{
            const response = await fetch(`/api/autocompletion-ia/adresse/search?q=${{encodeURIComponent(query)}}&limit=5`);
            if (response.ok) {{
                const data = await response.json();
                if (data.resultats && data.resultats.length > 0) {{
                    suggestionsDiv.innerHTML = data.resultats.map(addr => `
                        <div class="adresse-item" style="padding: 10px; cursor: pointer; border-bottom: 1px solid #eee;"
                             data-adresse='${{JSON.stringify(addr).replace(/'/g, "&#39;")}}'>
                            <div style="font-weight: 500;">${{addr.adresse_complete}}</div>
                            <div style="font-size: 12px; color: #666;">${{addr.code_postal}} ${{addr.ville}}</div>
                        </div>
                    `).join('');
                    suggestionsDiv.style.display = 'block';

                    suggestionsDiv.querySelectorAll('.adresse-item').forEach(item => {{
                        item.addEventListener('mouseenter', () => item.style.backgroundColor = '#f5f5f5');
                        item.addEventListener('mouseleave', () => item.style.backgroundColor = 'white');
                        item.addEventListener('click', () => {{
                            const addr = JSON.parse(item.dataset.adresse);
                            input.value = addr.rue || addr.adresse_complete;
                            fillFormWithAdresseData(addr);
                            suggestionsDiv.style.display = 'none';
                        }});
                    }});
                }} else {{
                    suggestionsDiv.style.display = 'none';
                }}
            }}
        }} catch (e) {{
            console.error('Erreur recherche adresse:', e);
        }}
    }}

    function fillFormWithEntrepriseData(data) {{
        // Mapping des champs API vers les champs de formulaire possibles
        const mappings = {{
            'nom': ['nom', 'nom_entreprise', 'raison_sociale', 'name', 'company_name', 'societe'],
            'raison_sociale': ['raison_sociale', 'nom_entreprise', 'nom', 'name'],
            'siret': ['siret', 'numero_siret'],
            'siren': ['siren', 'numero_siren'],
            'tva_intracommunautaire': ['tva_intracommunautaire', 'tva_intra', 'numero_tva', 'tva', 'vat', 'vat_number'],
            'code_naf': ['code_naf', 'naf', 'ape', 'code_ape'],
            'forme_juridique': ['forme_juridique', 'type_societe', 'legal_form'],
            'adresse': ['adresse', 'adresse_ligne1', 'address', 'rue', 'street'],
            'complement_adresse': ['complement_adresse', 'adresse_ligne2', 'address2'],
            'code_postal': ['code_postal', 'cp', 'postal_code', 'zip', 'zipcode'],
            'ville': ['ville', 'city', 'commune'],
            'pays': ['pays', 'country']
        }};

        let filledCount = 0;

        for (const [apiField, formFields] of Object.entries(mappings)) {{
            const value = data[apiField];
            if (!value) continue;

            for (const fieldName of formFields) {{
                // Chercher par name ou id (case insensitive)
                const selectors = [
                    `input[name="${{fieldName}}" i]`,
                    `input[name="${{fieldName.toLowerCase()}}"]`,
                    `input[name="${{fieldName.toUpperCase()}}"]`,
                    `input[id*="${{fieldName}}" i]`,
                    `textarea[name="${{fieldName}}" i]`,
                    `select[name="${{fieldName}}" i]`
                ];

                for (const selector of selectors) {{
                    try {{
                        const field = document.querySelector(selector);
                        if (field && !field.value) {{
                            field.value = value;
                            field.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            highlightField(field);
                            filledCount++;
                            break;
                        }}
                    }} catch (e) {{}}
                }}
            }}
        }}

        console.log(`Auto-fill: ${{filledCount}} champs remplis`);
        return filledCount;
    }}

    function highlightField(field) {{
        field.style.transition = 'background-color 0.3s, border-color 0.3s';
        field.style.backgroundColor = '#d4edda';
        field.style.borderColor = '#28a745';
        setTimeout(() => {{
            field.style.backgroundColor = '';
            field.style.borderColor = '';
        }}, 2000);
    }}

    function showAutoFillLoading(show) {{
        let loader = document.getElementById('autofill-loader');
        if (!loader && show) {{
            loader = document.createElement('div');
            loader.id = 'autofill-loader';
            loader.innerHTML = `
                <div style="position: fixed; top: 20px; right: 20px; background: white; padding: 16px 24px;
                            border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 10000;
                            display: flex; align-items: center; gap: 12px;">
                    <div class="spinner" style="width: 20px; height: 20px; border: 2px solid #f3f3f3;
                                                border-top: 2px solid var(--primary, #4F46E5);
                                                border-radius: 50%; animation: spin 1s linear infinite;"></div>
                    <span>Recherche en cours...</span>
                </div>
                <style>@keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}</style>
            `;
            document.body.appendChild(loader);
        }}
        if (loader) {{
            loader.style.display = show ? 'block' : 'none';
        }}
    }}

    function showAutoFillNotification(message, type) {{
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed; top: 20px; right: 20px; padding: 16px 24px;
            background: ${{type === 'success' ? '#d4edda' : '#f8d7da'}};
            color: ${{type === 'success' ? '#155724' : '#721c24'}};
            border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 10000;
            animation: slideIn 0.3s ease;
        `;
        notification.innerHTML = message;
        document.body.appendChild(notification);

        setTimeout(() => {{
            notification.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }}, 3000);
    }}

    // Initialiser au chargement
    document.addEventListener('DOMContentLoaded', function() {{
        initAutoFillSIRET();
    }});
    </script>

    <style>
    /* Autocompletion IA Styles */
    .autocomplete-container {{
        position: relative;
    }}
    .autocomplete-wrapper {{
        position: relative;
    }}
    .autocomplete-input {{
        padding-right: 32px !important;
    }}
    .autocomplete-indicator {{
        position: absolute;
        right: 10px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 14px;
        opacity: 0.5;
        pointer-events: none;
    }}
    .autocomplete-suggestions {{
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        border: 1px solid var(--gray-200);
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 1000;
        max-height: 200px;
        overflow-y: auto;
        display: none;
    }}
    .autocomplete-item {{
        padding: 10px 12px;
        cursor: pointer;
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: background 0.1s;
    }}
    .autocomplete-item:hover,
    .autocomplete-item.active {{
        background: var(--primary-light, #EEF2FF);
    }}
    .autocomplete-item .suggestion-text {{
        flex: 1;
    }}
    .autocomplete-item .suggestion-source {{
        font-size: 12px;
        opacity: 0.6;
        margin-left: 8px;
    }}

    /* Auto-fill animations */
    @keyframes slideIn {{
        from {{ transform: translateX(100%); opacity: 0; }}
        to {{ transform: translateX(0); opacity: 1; }}
    }}
    @keyframes fadeOut {{
        from {{ opacity: 1; }}
        to {{ opacity: 0; }}
    }}

    /* Mobile Modal */
    .mobile-modal-overlay {{
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.5);
        z-index: 9999;
        align-items: center;
        justify-content: center;
    }}
    .mobile-modal-overlay.open {{
        display: flex;
    }}
    .mobile-modal {{
        background: white;
        border-radius: 16px;
        padding: 32px;
        max-width: 400px;
        width: 90%;
        text-align: center;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }}
    .mobile-modal h2 {{
        margin: 0 0 8px 0;
        font-size: 24px;
        color: var(--gray-900);
    }}
    .mobile-modal p {{
        color: var(--gray-500);
        margin: 0 0 24px 0;
        font-size: 14px;
    }}
    .qr-container {{
        background: white;
        padding: 20px;
        border-radius: 12px;
        display: inline-block;
        margin-bottom: 24px;
        border: 2px solid var(--gray-200);
    }}
    #qrcode {{
        width: 200px;
        height: 200px;
    }}
    #qrcode canvas {{
        width: 200px !important;
        height: 200px !important;
    }}
    .mobile-token {{
        background: var(--gray-100);
        padding: 12px 16px;
        border-radius: 8px;
        font-family: monospace;
        font-size: 14px;
        margin-bottom: 24px;
        word-break: break-all;
        color: var(--gray-700);
    }}
    .mobile-buttons {{
        display: flex;
        gap: 12px;
        justify-content: center;
    }}
    .mobile-buttons .btn {{
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 500;
        cursor: pointer;
        border: none;
        font-size: 14px;
    }}
    .mobile-buttons .btn-primary {{
        background: var(--primary);
        color: white;
    }}
    .mobile-buttons .btn-secondary {{
        background: var(--gray-200);
        color: var(--gray-700);
    }}
    .header-mobile {{
        position: relative;
        cursor: pointer;
        padding: 8px;
        border-radius: 8px;
        transition: background 0.15s;
        text-decoration: none;
        display: inline-block;
        color: inherit;
    }}
    .header-mobile:hover {{
        background: var(--gray-100);
    }}
    .mobile-icon {{
        font-size: 20px;
    }}
    .mobile-instructions {{
        text-align: left;
        background: var(--blue-50);
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 20px;
        font-size: 13px;
        color: var(--gray-700);
    }}
    .mobile-instructions ol {{
        margin: 8px 0 0 0;
        padding-left: 20px;
    }}
    .mobile-instructions li {{
        margin: 4px 0;
    }}
    </style>

    <!-- Mobile Connection Modal -->
    <div id="mobile-modal" class="mobile-modal-overlay" onclick="closeMobileModal(event)">
        <div class="mobile-modal" onclick="event.stopPropagation()">
            <h2>📱 Application Mobile</h2>
            <p>Scannez le QR code avec l'application AZALPLUS</p>

            <div class="mobile-instructions">
                <strong>Comment se connecter :</strong>
                <ol>
                    <li>Téléchargez l'app AZALPLUS sur votre mobile</li>
                    <li>Ouvrez l'app et appuyez sur "Scanner QR"</li>
                    <li>Scannez le code ci-dessous</li>
                </ol>
            </div>

            <div class="qr-container">
                <div id="qrcode"></div>
            </div>

            <p style="font-size: 12px; color: var(--gray-400); margin-bottom: 16px;">
                Code valide 5 minutes • <a href="javascript:void(0)" onclick="refreshQRCode()" style="color: var(--primary);">Actualiser</a>
            </p>

            <div class="mobile-buttons">
                <button class="btn btn-secondary" onclick="closeMobileModal(event)">Fermer</button>
                <button class="btn btn-primary" onclick="copyMobileLink()">📋 Copier le lien</button>
            </div>
        </div>
    </div>

    <script>
    var mobileToken = null;
    var qrGenerated = false;

    function openMobileModal(event) {{
        if (event) {{ event.preventDefault(); event.stopPropagation(); }}
        document.getElementById('mobile-modal').classList.add('open');
        if (!qrGenerated) {{
            generateQRCode();
        }}
    }}

    function closeMobileModal(event) {{
        if (event) {{ event.preventDefault(); }}
        document.getElementById('mobile-modal').classList.remove('open');
    }}

    async function generateQRCode() {{
        var qrContainer = document.getElementById('qrcode');
        qrContainer.innerHTML = '<div style="padding:40px;color:var(--gray-400);">Génération...</div>';

        try {{
            // Generate a mobile connection token
            const response = await fetch('/api/auth/mobile-token', {{
                method: 'POST',
                credentials: 'include',
                headers: {{ 'Content-Type': 'application/json' }}
            }});

            if (response.ok) {{
                const tokenData = await response.json();
                mobileToken = tokenData.token;
            }} else {{
                // Fallback: use session-based token
                mobileToken = 'session_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 9);
            }}

            // Mobile app is on port 5174
            var mobileBaseUrl = window.location.protocol + '//' + window.location.hostname + ':5174';
            var mobileUrl = mobileBaseUrl + '/connect?token=' + encodeURIComponent(mobileToken) + '&api=' + encodeURIComponent(window.location.origin);

            // Use external QR API (more reliable)
            var qrApiUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&format=svg&data=' + encodeURIComponent(mobileUrl);

            qrContainer.innerHTML = '<img src="' + qrApiUrl + '" alt="QR Code" width="200" height="200" style="border-radius: 8px;" onerror="this.parentElement.innerHTML=\\'<div style=padding:40px;color:#EF4444;>Erreur QR</div>\\';">';

            qrGenerated = true;
            console.log('QR Code generated for:', mobileUrl);
        }} catch (e) {{
            console.error('Error generating QR:', e);
            qrContainer.innerHTML = '<div style="padding:40px;color:#EF4444;">Erreur: ' + e.message + '</div>';
        }}
    }}

    function refreshQRCode() {{
        qrGenerated = false;
        generateQRCode();
    }}

    function copyMobileLink() {{
        var mobileBaseUrl = window.location.protocol + '//' + window.location.hostname + ':5174';
        var mobileUrl = mobileBaseUrl + '/connect?token=' + encodeURIComponent(mobileToken || '') + '&api=' + encodeURIComponent(window.location.origin);
        navigator.clipboard.writeText(mobileUrl).then(function() {{
            alert('Lien copié !');
        }}).catch(function() {{
            prompt('Copiez ce lien:', mobileUrl);
        }});
    }}
    </script>
</body>
</html>
'''
