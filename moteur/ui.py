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
from .tenant import get_current_tenant, SYSTEM_TENANT_ID
from .db import Database
from .config import settings
from .reports import ReportEngine
from .constants import get_tva_options, get_tva
from .icons import get_icon_html, get_icon_url, get_inline_svg, INLINE_ICONS
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
# TVA Helpers (chargés depuis config/constants.yml)
# =============================================================================
def _get_tva_select_options() -> str:
    """Génère les options HTML pour le select TVA."""
    tva_options = get_tva_options("france")
    # Trier par taux décroissant (normal en premier)
    sorted_tva = sorted(tva_options.items(), key=lambda x: x[1], reverse=True)
    options_html = ""
    for nom, taux in sorted_tva:
        options_html += f'<option value="{taux}">{taux}%</option>'
    # Ajouter 0% pour exonéré
    options_html += '<option value="0">0%</option>'
    return options_html

def _get_tva_default_rate() -> float:
    """Retourne le taux TVA par défaut (normal)."""
    return get_tva("france", "normal")

# Cache des valeurs TVA pour éviter les appels répétés
_TVA_OPTIONS_HTML = None
_TVA_DEFAULT_RATE = None

def get_tva_options_html() -> str:
    """Retourne les options HTML TVA (avec cache)."""
    global _TVA_OPTIONS_HTML
    if _TVA_OPTIONS_HTML is None:
        _TVA_OPTIONS_HTML = _get_tva_select_options()
    return _TVA_OPTIONS_HTML

def get_tva_default() -> float:
    """Retourne le taux TVA par défaut (avec cache)."""
    global _TVA_DEFAULT_RATE
    if _TVA_DEFAULT_RATE is None:
        _TVA_DEFAULT_RATE = _get_tva_default_rate()
    return _TVA_DEFAULT_RATE

# =============================================================================
# Helpers
# =============================================================================
def get_field_html(field: FieldDefinition, value: Any = None, is_custom: bool = False, module_name: str = "", odoo_style: bool = True) -> str:
    """Génère le HTML d'un champ de formulaire style Odoo (label à gauche, input à droite)."""
    import html as html_module

    field_id = f"field_{field.nom}"
    required_attr = "required" if field.requis else ""
    required_class = "required" if field.requis else ""
    label = field.label or field.nom.replace("_", " ").title()
    placeholder = getattr(field, 'placeholder', None) or ""
    help_text = f'<small class="form-help">{field.aide}</small>' if field.aide else ""

    # Échapper la valeur pour HTML
    escaped_value = html_module.escape(str(value)) if value is not None else ""

    # Type de champ
    if field.type == "texte long" or field.type == "textarea":
        return f'''
        <div class="o-field-row" style="grid-template-columns: 150px 1fr;">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <textarea class="o-field-text" id="{field_id}" name="{field.nom}" rows="6" {required_attr} placeholder="{placeholder}">{escaped_value}</textarea>
                {help_text}
            </div>
        </div>
        '''

    elif field.type in ["enum", "select"] and field.enum_values:
        options = "".join([
            f'<option value="{v}" {"selected" if v == value else ""}>{v}</option>'
            for v in field.enum_values
        ])
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <select class="o-field-char" id="{field_id}" name="{field.nom}" {required_attr}>
                    <option value="">-- Sélectionner --</option>
                    {options}
                </select>
            </div>
        </div>
        '''

    elif field.type == "oui/non" or field.type == "booleen":
        checked = "checked" if value else ""
        return f'''
        <div class="o-field-row">
            <label class="o-field-label" for="{field_id}">{label}</label>
            <div class="o-field-widget o-field-boolean">
                <input type="checkbox" id="{field_id}" name="{field.nom}" {checked}>
            </div>
        </div>
        '''

    elif field.type == "date":
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <div class="datetime-picker-wrapper">
                    <input type="text" class="o-field-char datetime-picker" id="{field_id}" name="{field.nom}"
                           value="{escaped_value}" {required_attr} readonly
                           onclick="openDateTimePicker(this, 'date')" placeholder="Sélectionner...">
                    <span class="datetime-picker-icon" onclick="openDateTimePicker(document.getElementById('{field_id}'), 'date')">📅</span>
                </div>
            </div>
        </div>
        '''

    elif field.type == "datetime":
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <div class="datetime-picker-wrapper">
                    <input type="text" class="o-field-char datetime-picker" id="{field_id}" name="{field.nom}"
                           value="{escaped_value}" {required_attr} readonly
                           onclick="openDateTimePicker(this, 'datetime')" placeholder="Sélectionner...">
                    <span class="datetime-picker-icon" onclick="openDateTimePicker(document.getElementById('{field_id}'), 'datetime')">📅</span>
                </div>
            </div>
        </div>
        '''

    elif field.type in ["nombre", "entier", "monnaie", "pourcentage"]:
        step = "0.01" if field.type in ["nombre", "monnaie", "pourcentage"] else "1"
        min_attr = f'min="{field.min}"' if field.min is not None else ""
        max_attr = f'max="{field.max}"' if field.max is not None else ""
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <input type="number" class="o-field-char" id="{field_id}" name="{field.nom}"
                       step="{step}" {min_attr} {max_attr} value="{escaped_value}" {required_attr}>
            </div>
        </div>
        '''

    elif field.type == "email":
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <input type="email" class="o-field-char" id="{field_id}" name="{field.nom}" value="{escaped_value}" {required_attr}>
            </div>
        </div>
        '''

    elif field.type in ["lien", "relation"]:
        # Pour les liens/relations, on génère un select avec option de création
        linked_module = field.lien_vers or getattr(field, 'relation', '') or ""
        linked_module_lower = linked_module.lower()

        # Configuration auto-fill pour certains champs de relation
        autofill_config = ""
        if field.nom == "client_id":
            autofill_config = 'data-autofill="adresse_ligne1:address_line1,adresse_ligne2:address_line2,ville:city,code_postal:postal_code,contact_sur_place:contact_name,telephone_contact:phone,email_contact:email"'
        elif field.nom == "customer_id":
            # Pour les factures : construire l'adresse complète dans billing_address (textarea)
            # Note: l'API /clients/{id} retourne adresse1, adresse2, cp, ville (noms français)
            autofill_config = 'data-autofill="billing_address:_compose_address:adresse1|adresse2|cp|ville"'
        elif field.nom == "donneur_ordre_id":
            autofill_config = 'data-autofill="adresse_ligne1:adresse_ligne1,adresse_ligne2:adresse_ligne2,ville:ville,code_postal:code_postal,contact_sur_place:contact_principal,telephone_contact:telephone,email_contact:email"'

        # Valeur actuelle pour pré-sélection
        current_value = value or ""

        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <div class="select-with-create">
                    <select class="o-field-char" id="{field_id}" name="{field.nom}" data-link="{linked_module}" data-current-value="{current_value}" {autofill_config} {required_attr} onchange="handleRelationAutofill(this)">
                        <option value="">-- Sélectionner --</option>
                    </select>
                    <button type="button" class="btn-create-inline" onclick="openFullCreatePage('{linked_module_lower}', '{field_id}')" title="Créer nouveau">
                        +
                    </button>
                </div>
            </div>
        </div>
        '''

    else:  # texte par défaut
        # Vérifier si autocomplétion IA est activée pour ce champ
        has_autocompletion = getattr(field, 'autocompletion', False)

        if has_autocompletion:
            # Input avec autocomplétion IA
            return f'''
            <div class="o-field-row">
                <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
                <div class="o-field-widget autocomplete-container">
                    <div class="autocomplete-wrapper">
                        <input type="text" class="o-field-char autocomplete-input" id="{field_id}" name="{field.nom}"
                               value="{escaped_value}" {required_attr}
                               data-autocomplete="true" data-module="{module_name}" data-champ="{field.nom}"
                               autocomplete="off">
                        <div class="autocomplete-suggestions" id="{field_id}_suggestions"></div>
                        <span class="autocomplete-indicator" title="Autocomplétion IA">✨</span>
                    </div>
                </div>
            </div>
            '''
        else:
            return f'''
            <div class="o-field-row">
                <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
                <div class="o-field-widget">
                    <input type="text" class="o-field-char" id="{field_id}" name="{field.nom}" value="{escaped_value}" {required_attr}>
                </div>
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
                background: var(--gray-100);
                border-radius: 12px;
                padding: 24px;
                box-shadow: var(--shadow-sm);
                border-left: 4px solid var(--primary);
                transition: all 0.2s;
            }}
            .kpi-card:hover {{
                box-shadow: var(--shadow);
                border-left-color: var(--primary-light);
            }}
            .kpi-card.success {{ border-left-color: var(--success); }}
            .kpi-card.warning {{ border-left-color: var(--warning); }}
            .kpi-card.danger {{ border-left-color: var(--error); }}
            .kpi-card.info {{ border-left-color: var(--info); }}
            .kpi-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
            }}
            .kpi-title {{
                font-size: 14px;
                color: var(--gray-500);
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
                background: var(--gray-200);
            }}
            .kpi-icon svg {{ width: 20px; height: 20px; color: var(--primary-light); }}
            .kpi-value {{
                font-size: 28px;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: 4px;
            }}
            .kpi-subtitle {{
                font-size: 13px;
                color: var(--gray-500);
            }}
            .kpi-badge {{
                display: inline-block;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
                margin-left: 8px;
            }}
            .kpi-badge.up {{ background: var(--success-light); color: var(--success); }}
            .kpi-badge.down {{ background: var(--error-light); color: var(--error); }}
            .section-title {{
                font-size: 18px;
                font-weight: 600;
                color: var(--gray-800);
                margin: 30px 0 15px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid var(--gray-200);
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
        <!-- Onglets -->
        <div class="tabs-container" style="background: var(--white); border-radius: var(--radius-lg) var(--radius-lg) 0 0; margin-bottom: 0;">
            <div class="tabs">
                <a href="#" class="tab active" onclick="showTab('documents', this)">Style Documents</a>
                <a href="#" class="tab" onclick="showTab('ambiance', this)">Ambiance</a>
            </div>
        </div>

        <!-- Tab Documents -->
        <div id="tab-documents" class="tab-content">
        <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
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
        </div>
        </div>

        <!-- Tab Ambiance -->
        <div id="tab-ambiance" class="tab-content" style="display: none;">
        <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
            <div class="card-header">
                <h2 class="card-title">Choisir l'ambiance de l'interface</h2>
            </div>
            <div class="card-body">
                <p style="color: var(--gray-600); margin-bottom: 24px;">Sélectionnez l'ambiance visuelle qui correspond à votre style de travail</p>

                <div class="style-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;">

                    <!-- Ambiance Énergique -->
                    <div class="style-card" data-style="energique" onclick="selectStyle('energique', this)" style="border: 2px solid var(--gray-200); border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s;">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                            <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #8B5CF6 0%, #06B6D4 100%); border-radius: 8px;"></div>
                            <div>
                                <h3 style="font-size: 16px; font-weight: 600; color: var(--gray-800);">Énergique</h3>
                                <span style="font-size: 12px; color: var(--gray-500);">Linear, Vercel</span>
                            </div>
                        </div>
                        <p style="font-size: 13px; color: var(--gray-600);">Contrastes forts, accents vifs, sidebar sombre. Pour les équipes dynamiques.</p>
                        <div style="margin-top: 12px; display: flex; gap: 6px;">
                            <span style="width: 20px; height: 20px; background: #8B5CF6; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #0F0F0F; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #FAFAFA; border-radius: 4px; border: 1px solid #ddd;"></span>
                        </div>
                    </div>

                    <!-- Ambiance Calme -->
                    <div class="style-card" data-style="calme" onclick="selectStyle('calme', this)" style="border: 2px solid var(--gray-200); border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s;">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                            <div style="width: 48px; height: 48px; background: #F7F6F3; border: 2px solid #EBEAE6; border-radius: 8px;"></div>
                            <div>
                                <h3 style="font-size: 16px; font-weight: 600; color: var(--gray-800);">Calme</h3>
                                <span style="font-size: 12px; color: var(--gray-500);">Notion, Basecamp</span>
                            </div>
                        </div>
                        <p style="font-size: 13px; color: var(--gray-600);">Tons neutres, beaucoup de blanc, minimaliste. Pour la concentration.</p>
                        <div style="margin-top: 12px; display: flex; gap: 6px;">
                            <span style="width: 20px; height: 20px; background: #37352F; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #F7F6F3; border-radius: 4px; border: 1px solid #ddd;"></span>
                            <span style="width: 20px; height: 20px; background: #FFFFFF; border-radius: 4px; border: 1px solid #ddd;"></span>
                        </div>
                    </div>

                    <!-- Ambiance Premium -->
                    <div class="style-card" data-style="premium" onclick="selectStyle('premium', this)" style="border: 2px solid var(--gray-200); border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s;">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                            <div style="width: 48px; height: 48px; background: linear-gradient(180deg, #0A2540 0%, #635BFF 100%); border-radius: 8px;"></div>
                            <div>
                                <h3 style="font-size: 16px; font-weight: 600; color: var(--gray-800);">Premium</h3>
                                <span style="font-size: 12px; color: var(--gray-500);">Stripe, Mercury</span>
                            </div>
                        </div>
                        <p style="font-size: 13px; color: var(--gray-600);">Dégradés subtils, ombres douces, sophistiqué. Pour une image haut de gamme.</p>
                        <div style="margin-top: 12px; display: flex; gap: 6px;">
                            <span style="width: 20px; height: 20px; background: #635BFF; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #0A2540; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #F6F9FC; border-radius: 4px; border: 1px solid #ddd;"></span>
                        </div>
                    </div>

                    <!-- Ambiance Corporate -->
                    <div class="style-card" data-style="corporate" onclick="selectStyle('corporate', this)" style="border: 2px solid var(--gray-200); border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s;">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                            <div style="width: 48px; height: 48px; background: #032D60; border-radius: 8px;"></div>
                            <div>
                                <h3 style="font-size: 16px; font-weight: 600; color: var(--gray-800);">Corporate</h3>
                                <span style="font-size: 12px; color: var(--gray-500);">Salesforce</span>
                            </div>
                        </div>
                        <p style="font-size: 13px; color: var(--gray-600);">Bleu dominant, structuré, professionnel. Pour les entreprises établies.</p>
                        <div style="margin-top: 12px; display: flex; gap: 6px;">
                            <span style="width: 20px; height: 20px; background: #0176D3; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #032D60; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: #F3F3F3; border-radius: 4px; border: 1px solid #ddd;"></span>
                        </div>
                    </div>

                </div>

                <div class="flex justify-end gap-2" style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--gray-200);">
                    <button class="btn btn-primary" onclick="applyStyle()">Appliquer l'ambiance</button>
                </div>
            </div>
        </div>
        </div>

        <script>
            let selectedStyle = null;

            function showTab(tabName, element) {
                event.preventDefault();
                document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById('tab-' + tabName).style.display = 'block';
                element.classList.add('active');
            }

            function selectStyle(style, element) {
                selectedStyle = style;
                document.querySelectorAll('.style-card').forEach(card => {
                    card.style.borderColor = 'var(--gray-200)';
                    const badge = card.querySelector('div > div:last-of-type > span');
                    if (badge) badge.textContent = '';
                });
                element.style.borderColor = 'var(--primary)';
                element.style.boxShadow = '0 0 0 3px rgba(113, 75, 103, 0.15)';
                const badge = element.querySelector('div > div:last-of-type > span');
                if (badge) badge.textContent = 'Sélectionné';
            }

            async function applyStyle() {
                if (!selectedStyle) {
                    alert('Veuillez sélectionner une ambiance');
                    return;
                }
                try {
                    const response = await fetch('/api/admin/ambiance', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ ambiance: selectedStyle })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        alert('Ambiance "' + selectedStyle + '" appliquée ! La page va se recharger.');
                        window.location.reload();
                    } else {
                        const err = await response.json();
                        alert('Erreur: ' + (err.detail || 'Erreur inconnue'));
                    }
                } catch(e) {
                    alert('Erreur: ' + e.message);
                }
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
    from .guardian import CREATEUR_EMAIL

    # Vérifier si l'utilisateur est le créateur
    user_email = user.get("email", "")
    is_createur = user_email == CREATEUR_EMAIL

    all_modules = []
    for name in ModuleParser.list_all():
        module = ModuleParser.get(name)
        if module and module.actif:
            # Filtrer les modules createur_only
            module_acces = getattr(module, 'acces', None)
            if module_acces == 'createur_only' and not is_createur:
                continue  # Ne pas afficher ce module aux non-créateurs

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
            background: white;
            color: #1e3a5f;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            text-decoration: none;
            transition: transform 0.2s, box-shadow 0.2s;
            z-index: 100;
        }
        .fab-create:hover {
            transform: scale(1.1);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
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
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
            border-radius: 6px;
            padding: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            color: white;
        }
        .calendar-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
            flex-wrap: wrap;
            gap: 4px;
            color: white;
        }
        .calendar-header h2 {
            color: white;
        }
        .calendar-nav {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .calendar-nav .btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        .calendar-nav .btn:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        .calendar-views {
            display: flex;
            gap: 8px;
        }
        .calendar-views .btn {
            background: rgba(255, 255, 255, 0.15);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        .calendar-views .btn:hover {
            background: rgba(255, 255, 255, 0.25);
        }
        .calendar-views .btn.active {
            background: white;
            color: #1e3a5f;
        }
        .calendar-actions .btn-secondary {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        .calendar-actions .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        .calendar-actions .btn-primary {
            background: white;
            color: #1e3a5f;
        }
        .calendar-actions .btn-primary:hover {
            background: rgba(255, 255, 255, 0.9);
        }
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 1px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            padding: 2px;
        }
        .calendar-weekdays {
            display: contents;
        }
        .calendar-weekdays > div {
            text-align: center;
            font-weight: 600;
            font-size: 0.75rem;
            color: white;
            padding: 3px 1px;
            text-transform: uppercase;
            letter-spacing: 0.25px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.3);
            background: rgba(255, 255, 255, 0.05);
        }
        .calendar-days {
            display: contents;
        }
        .calendar-day {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding: 2px;
            border-radius: 2px;
            cursor: pointer;
            transition: all 0.15s;
            min-height: 18px;
            color: white;
            background: rgba(255, 255, 255, 0.05);
        }
        .calendar-day:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        .calendar-day.today {
            background: rgba(255, 255, 255, 0.3);
            color: white;
            font-weight: bold;
        }
        .calendar-day.other-month {
            color: rgba(255, 255, 255, 0.4);
        }
        .calendar-day.selected {
            border: 1px solid white;
            background: rgba(255, 255, 255, 0.2);
        }
        .calendar-day .day-number {
            font-weight: 600;
            font-size: 20px;
        }
        .calendar-day .day-events {
            font-size: 9px;
            margin-top: 2px;
        }
        .event-dot {
            min-width: 10px;
            height: 10px;
            border-radius: 5px;
            background: #f97316;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 8px;
            font-weight: 600;
            color: white;
        }
        /* Couleurs de charge de travail */
        .calendar-day.workload-light {
            background: rgba(34, 197, 94, 0.3) !important; /* vert */
        }
        .calendar-day.workload-moderate {
            background: rgba(234, 179, 8, 0.4) !important; /* jaune */
        }
        .calendar-day.workload-busy {
            background: rgba(249, 115, 22, 0.5) !important; /* orange */
        }
        .calendar-day.workload-heavy {
            background: rgba(239, 68, 68, 0.5) !important; /* rouge */
        }
        .calendar-day.workload-overload {
            background: rgba(185, 28, 28, 0.7) !important; /* rouge foncé */
        }
        .calendar-day .workload-hours {
            font-size: 8px;
            color: rgba(255,255,255,0.9);
            margin-top: 1px;
            font-weight: 500;
        }
        .calendar-day .workload-travel {
            font-size: 7px;
            color: rgba(255,255,255,0.7);
            margin-top: 1px;
        }
        .calendar-events {
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid rgba(255, 255, 255, 0.3);
            color: white;
        }
        .calendar-events h3 {
            color: white;
        }
        .events-list .event-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            margin-bottom: 8px;
            color: white;
        }
        .event-time {
            font-weight: 600;
            color: rgba(255, 255, 255, 0.8);
            min-width: 60px;
        }
        .event-title {
            flex: 1;
            color: white;
        }
        .calendar-container .text-muted {
            color: rgba(255, 255, 255, 0.7) !important;
        }
    </style>

    <script>
        let currentDate = new Date();
        let selectedDate = new Date();

        const months = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                       'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

        function renderMainCalendar() {
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
                day.addEventListener('click', () => selectMainDate(year, month, i));
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

        function selectMainDate(year, month, day) {
            selectedDate = new Date(year, month, day);
            renderMainCalendar();
            loadEvents(selectedDate);
        }

        async function loadEvents(date) {
            const eventsList = document.getElementById('events-list');
            const dateStr = date.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
            eventsList.innerHTML = `
                <p class="text-muted">Événements du ${dateStr}</p>
                <div class="event-item">
                    <span class="event-time">⏳</span>
                    <span class="event-title">Chargement...</span>
                </div>
            `;

            // Formater les dates pour l'API (début et fin de journée)
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const startOfDay = `${year}-${month}-${day}T00:00:00`;
            const nextDay = new Date(date);
            nextDay.setDate(nextDay.getDate() + 1);
            const endOfDay = `${nextDay.getFullYear()}-${String(nextDay.getMonth() + 1).padStart(2, '0')}-${String(nextDay.getDate()).padStart(2, '0')}T00:00:00`;

            try {
                // Charger agenda ET interventions
                const [agendaRes, interventionsRes] = await Promise.all([
                    fetch(`/api/agenda?date_debut_gte=${encodeURIComponent(startOfDay)}&date_debut_lt=${encodeURIComponent(endOfDay)}&order_by=date_debut&order_dir=asc&limit=50`, { credentials: 'include' }),
                    fetch(`/api/interventions?date_prevue_debut_gte=${encodeURIComponent(startOfDay)}&date_prevue_debut_lt=${encodeURIComponent(endOfDay)}&order_by=date_prevue_debut&order_dir=asc&limit=50`, { credentials: 'include' })
                ]);

                const response = agendaRes; // Pour compatibilité

                // Combiner les résultats agenda + interventions
                const agendaData = agendaRes.ok ? await agendaRes.json() : { items: [] };
                const interventionsData = interventionsRes.ok ? await interventionsRes.json() : { items: [] };

                const agendaEvents = (agendaData.items || []).map(e => ({ ...e, _type: 'agenda' }));
                const interventionEvents = (interventionsData.items || []).map(e => ({ ...e, _type: 'intervention', titre: e.reference || e.objet || 'Intervention', date_debut: e.date_prevue_debut }));

                const events = [...agendaEvents, ...interventionEvents].sort((a, b) =>
                    new Date(a.date_debut || 0) - new Date(b.date_debut || 0)
                );

                if (events.length === 0) {
                    eventsList.innerHTML = `
                        <p class="text-muted">Événements du ${dateStr}</p>
                        <p style="color: var(--gray-500); text-align: center; padding: 20px;">
                            Aucun événement ce jour
                        </p>
                    `;
                    return;
                }

                let html = `<p class="text-muted">Événements du ${dateStr}</p>`;
                events.forEach(event => {
                    const startTime = event.date_debut ? new Date(event.date_debut).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '--:--';
                    const statusClass = event.statut === 'TERMINE' ? 'done' : event.statut === 'ANNULE' ? 'cancelled' : '';
                    const moduleUrl = event._type === 'intervention' ? 'interventions' : 'agenda';
                    const typeLabel = event._type === 'intervention' ? '🔧' : '📅';
                    html += `
                        <a href="/ui/${moduleUrl}/${event.id}" class="event-item ${statusClass}" style="text-decoration: none; color: inherit;">
                            <span class="event-time">${typeLabel} ${startTime}</span>
                            <span class="event-title">${event.titre || 'Sans titre'}</span>
                            <span class="event-status" style="font-size: 11px; color: var(--gray-500);">${event.statut || ''}</span>
                        </a>
                    `;
                });
                eventsList.innerHTML = html;
            } catch (err) {
                console.error('Erreur chargement événements:', err);
                eventsList.innerHTML = `
                    <p class="text-muted">Événements du ${dateStr}</p>
                    <p style="color: var(--red-500); text-align: center;">Erreur de chargement</p>
                `;
            }
        }

        // Charger les événements du mois pour afficher les indicateurs et couleurs de charge
        async function loadMonthEvents() {
            const year = currentDate.getFullYear();
            const month = currentDate.getMonth() + 1; // API attend 1-12

            try {
                // Appeler l'API de calcul de charge avec temps de trajet dynamique
                const response = await fetch(`/api/calendar/workload?year=${year}&month=${month}`, {
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                const workload = data.workload || {};

                // Appliquer les couleurs et indicateurs sur les jours
                const days = document.querySelectorAll('.calendar-day:not(.other-month)');
                days.forEach(dayEl => {
                    const dayNum = parseInt(dayEl.querySelector('.day-number')?.textContent);
                    if (!dayNum) return;

                    // Supprimer les anciennes classes de charge
                    dayEl.classList.remove('workload-light', 'workload-moderate', 'workload-busy', 'workload-heavy', 'workload-overload');

                    const dayData = workload[dayNum];
                    if (!dayData) return;

                    const totalMinutes = dayData.total_minutes || 0;
                    const travelMinutes = dayData.travel_minutes || 0;
                    const workMinutes = dayData.work_minutes || 0;
                    const eventCount = dayData.events_count || 0;
                    const totalHours = totalMinutes / 60;

                    if (totalMinutes > 0) {
                        // Appliquer la classe de couleur selon la charge
                        if (totalHours <= 2) {
                            dayEl.classList.add('workload-light');
                        } else if (totalHours <= 4) {
                            dayEl.classList.add('workload-moderate');
                        } else if (totalHours <= 6) {
                            dayEl.classList.add('workload-busy');
                        } else if (totalHours <= 8) {
                            dayEl.classList.add('workload-heavy');
                        } else {
                            dayEl.classList.add('workload-overload');
                        }

                        // Afficher les heures et le détail trajet/travail
                        let indicator = dayEl.querySelector('.day-events');
                        if (!indicator) {
                            indicator = document.createElement('div');
                            indicator.className = 'day-events';
                            dayEl.appendChild(indicator);
                        }

                        const hoursDisplay = totalHours >= 1 ? `${totalHours.toFixed(1)}h` : `${Math.round(totalMinutes)}m`;
                        const travelDisplay = travelMinutes > 0 ? `🚗${Math.round(travelMinutes)}m` : '';

                        indicator.innerHTML = `
                            <span class="event-dot">${eventCount}</span>
                            <div class="workload-hours">${hoursDisplay}</div>
                            ${travelDisplay ? `<div class="workload-travel">${travelDisplay}</div>` : ''}
                        `;
                    }
                });
            } catch (err) {
                console.error('Erreur chargement charge du mois:', err);
                // Fallback: charger les événements sans calcul de trajet
                await loadMonthEventsSimple();
            }
        }

        // Fallback simple sans calcul de trajet
        async function loadMonthEventsSimple() {
            const year = currentDate.getFullYear();
            const month = currentDate.getMonth();
            const startDate = `${year}-${String(month + 1).padStart(2, '0')}-01T00:00:00`;
            const nextMonth = new Date(year, month + 1, 1);
            const endDate = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, '0')}-01T00:00:00`;

            try {
                const [agendaRes, interventionsRes] = await Promise.all([
                    fetch(`/api/agenda?date_debut_gte=${encodeURIComponent(startDate)}&date_debut_lt=${encodeURIComponent(endDate)}&limit=100`, { credentials: 'include' }),
                    fetch(`/api/interventions?date_prevue_debut_gte=${encodeURIComponent(startDate)}&date_prevue_debut_lt=${encodeURIComponent(endDate)}&limit=100`, { credentials: 'include' })
                ]);

                const agendaData = agendaRes.ok ? await agendaRes.json() : { items: [] };
                const interventionsData = interventionsRes.ok ? await interventionsRes.json() : { items: [] };
                const events = [...(agendaData.items || []), ...(interventionsData.items || [])];

                const eventsByDay = {};
                events.forEach(event => {
                    const eventDate = event.date_debut || event.date_prevue_debut;
                    if (eventDate) {
                        const eventDay = new Date(eventDate).getDate();
                        eventsByDay[eventDay] = (eventsByDay[eventDay] || 0) + 1;
                    }
                });

                const days = document.querySelectorAll('.calendar-day:not(.other-month)');
                days.forEach(dayEl => {
                    const dayNum = parseInt(dayEl.querySelector('.day-number')?.textContent);
                    if (dayNum && eventsByDay[dayNum]) {
                        let indicator = dayEl.querySelector('.day-events');
                        if (!indicator) {
                            indicator = document.createElement('div');
                            indicator.className = 'day-events';
                            dayEl.appendChild(indicator);
                        }
                        indicator.innerHTML = `<span class="event-dot">${eventsByDay[dayNum]}</span>`;
                    }
                });
            } catch (err) {
                console.error('Erreur chargement événements du mois:', err);
            }
        }

        document.getElementById('prev-month').addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            renderMainCalendar();
            loadMonthEvents();
        });

        document.getElementById('next-month').addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            renderMainCalendar();
            loadMonthEvents();
        });

        // Initialisation
        renderMainCalendar();
        loadMonthEvents();
        loadEvents(selectedDate);

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


# =============================================================================
# Interface Technicien Mobile
# =============================================================================

@ui_router.get("/technicien/dashboard", response_class=HTMLResponse)
async def technicien_dashboard(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Dashboard technicien mobile."""
    from datetime import datetime, timedelta
    from uuid import UUID as UUIDType

    user_id = user.get("id") or user.get("sub")
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())

    # Interventions du jour assignees au technicien
    # Note: On recupere toutes les interventions et on filtre en Python
    # car le filtre UUID pose probleme avec certains formats
    all_interventions_raw = Database.query(
        "interventions",
        tenant_id,
        limit=200
    )

    # Filtrer par intervenant_id en Python (plus robuste)
    all_interventions = [
        i for i in all_interventions_raw
        if str(i.get("intervenant_id", "")) == str(user_id)
    ]

    interventions_today = []
    interventions_week = []
    interventions_en_cours = []

    for intv in all_interventions:
        if intv.get("statut") == "ANNULEE":
            continue

        date_prevue = intv.get("date_prevue_debut")
        statut = intv.get("statut")

        if date_prevue:
            date_intv = date_prevue.date() if hasattr(date_prevue, 'date') else date_prevue

            if date_intv == today:
                interventions_today.append(intv)

            if date_intv >= start_of_week:
                interventions_week.append(intv)

        if statut in ["SUR_SITE", "EN_COURS"]:
            interventions_en_cours.append(intv)
            if intv not in interventions_today:
                interventions_today.append(intv)

    # Enrichir avec noms clients
    client_ids = list(set(i.get("client_id") for i in interventions_today if i.get("client_id")))
    clients = {}
    if client_ids:
        for cid in client_ids:
            client = Database.get("clients", tenant_id, cid)
            if client:
                nom = client.get("nom") or client.get("name") or client.get("raison_sociale") or ""
                prenom = client.get("prenom", "")
                clients[cid] = f"{nom} {prenom}".strip() if prenom else nom

    for intv in interventions_today:
        intv["client_nom"] = clients.get(intv.get("client_id"), "Client inconnu")

    # Heures saisies cette semaine
    # Recuperer tous les temps et filtrer en Python (evite probleme cast UUID)
    try:
        temps_entries_raw = Database.query(
            "temps",
            tenant_id,
            limit=500
        )
        temps_entries = [
            e for e in temps_entries_raw
            if str(e.get("user_id", "")) == str(user_id)
        ]
        heures_semaine = sum(
            (e.get("duree_minutes", 0) or 0) / 60
            for e in temps_entries
            if e.get("date") and e.get("date") >= start_of_week
        )
    except Exception:
        heures_semaine = 0

    # Trier par heure prevue
    interventions_today.sort(key=lambda x: x.get("date_prevue_debut") or datetime.max)

    # Charger le template
    try:
        template = jinja_env.get_template("technicien/dashboard.html")

        # Ajouter filtre format_time
        def format_time(dt):
            if dt and hasattr(dt, 'strftime'):
                return dt.strftime("%H:%M")
            return ""

        jinja_env.filters['format_time'] = format_time

        # Formater la date en francais
        jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        mois_fr = ["", "janvier", "février", "mars", "avril", "mai", "juin",
                   "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        date_jour_fr = f"{jours_fr[today.weekday()]} {today.day} {mois_fr[today.month]} {today.year}"

        html = template.render(
            user=user,
            date_jour=date_jour_fr,
            interventions_aujourdhui=len(interventions_today),
            interventions_semaine=len(interventions_week),
            interventions_en_cours=len(interventions_en_cours),
            heures_saisies_semaine=round(heures_semaine, 1),
            interventions=interventions_today
        )
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error("technicien_dashboard_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@ui_router.get("/technicien/intervention/{intervention_id}", response_class=HTMLResponse)
async def technicien_intervention_detail(
    intervention_id: str,
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Detail intervention pour technicien avec workflow."""
    from uuid import UUID

    try:
        intv_uuid = UUID(intervention_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID intervention invalide")

    intervention = Database.get("interventions", tenant_id, intv_uuid)
    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Enrichir avec client
    client = Database.get("clients", tenant_id, intervention.get("client_id"))
    if client:
        nom = client.get("nom") or client.get("name") or client.get("raison_sociale") or ""
        prenom = client.get("prenom", "")
        intervention["client_nom"] = f"{nom} {prenom}".strip() if prenom else nom
        intervention["client_telephone"] = client.get("telephone") or client.get("phone")
        intervention["client_email"] = client.get("email")
    else:
        intervention["client_nom"] = "Client inconnu"
        intervention["client_telephone"] = None
        intervention["client_email"] = None

    # Determiner l'etape courante
    statut = intervention.get("statut", "DRAFT")
    current_step = {
        "DRAFT": 1,
        "A_PLANIFIER": 1,
        "PLANIFIEE": 1,
        "SUR_SITE": 2,
        "EN_COURS": 3,
        "TRAVAUX_TERMINES": 7,
        "TERMINEE": 8
    }.get(statut, 1)

    # Ajuster selon les donnees saisies
    if statut == "EN_COURS":
        photos_avant = intervention.get("photos_avant") or []
        photos_apres = intervention.get("photos_apres") or []
        materiel = intervention.get("materiel_utilise_lignes") or []
        travaux = intervention.get("travaux_realises")

        if len(photos_avant) < 2:
            current_step = 3
        elif len(photos_apres) < 2:
            current_step = 4
        elif not materiel and not intervention.get("materiel_utilise"):
            current_step = 5
        elif not travaux:
            current_step = 6
        else:
            current_step = 6

    try:
        template = jinja_env.get_template("technicien/intervention.html")

        def format_time(dt):
            if dt and hasattr(dt, 'strftime'):
                return dt.strftime("%H:%M")
            return ""

        jinja_env.filters['format_time'] = format_time

        html = template.render(
            user=user,
            intervention=intervention,
            current_step=current_step
        )
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error("technicien_intervention_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@ui_router.get("/technicien/intervention/{intervention_id}/navigation", response_class=HTMLResponse)
async def technicien_navigation(
    intervention_id: str,
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Page de navigation GPS vers l'intervention."""
    from uuid import UUID
    import urllib.parse

    try:
        intv_uuid = UUID(intervention_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID intervention invalide")

    intervention = Database.get("interventions", tenant_id, intv_uuid)
    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    # Construire l'adresse
    adresse_parts = []
    if intervention.get("adresse_ligne1"):
        adresse_parts.append(intervention["adresse_ligne1"])
    if intervention.get("code_postal"):
        adresse_parts.append(intervention["code_postal"])
    if intervention.get("ville"):
        adresse_parts.append(intervention["ville"])

    adresse_complete = ", ".join(adresse_parts)
    adresse_encoded = urllib.parse.quote(adresse_complete)

    # Section contact conditionnelle
    contact_html = ""
    if intervention.get("telephone_contact"):
        tel = intervention.get("telephone_contact")
        contact_name = intervention.get("contact_sur_place", "")
        contact_html = f'''
        <div class="card">
            <div class="title">&#x1F4DE; Contact sur place</div>
            <div class="address">{contact_name}</div>
            <a href="tel:{tel}"
               style="display: block; margin-top: 12px; padding: 14px; background: #22c55e;
                      color: white; text-align: center; border-radius: 10px; text-decoration: none;
                      font-weight: 600;">
                Appeler {tel}
            </a>
        </div>
        '''

    html = f'''
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Navigation - {intervention.get("reference", "")}</title>
        <script>
        (function(){{
            'use strict';
            var REPORT_ENDPOINT='/guardian/frontend-error';
            var errorCount=0;
            function reportError(d){{
                if(errorCount>=10)return;
                errorCount++;
                fetch(REPORT_ENDPOINT,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}})
                .then(function(r){{return r.json();}})
                .then(function(data){{
                    if(data&&data.action==='reload'){{location.reload(true);}}
                }}).catch(function(){{}});
            }}
            window.onerror=function(message,source,line,column,error){{
                reportError({{error_type:'js_error',message:String(message),url:window.location.href,source:source,line:line,column:column,stack:error?error.stack:null,user_agent:navigator.userAgent}});
                return false;
            }};
        }})();
        </script>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f3f4f6;
                min-height: 100vh;
                padding: 16px;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            }}
            .title {{ font-size: 18px; font-weight: 700; margin-bottom: 16px; }}
            .address {{ font-size: 15px; color: #374151; line-height: 1.5; }}
            .nav-buttons {{ display: flex; flex-direction: column; gap: 12px; }}
            .nav-btn {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                padding: 16px;
                border-radius: 12px;
                text-decoration: none;
                font-size: 16px;
                font-weight: 600;
                color: white;
            }}
            .nav-btn.google {{ background: #4285f4; }}
            .nav-btn.apple {{ background: #333; }}
            .nav-btn.waze {{ background: #33ccff; }}
            .back-btn {{
                display: block;
                text-align: center;
                padding: 14px;
                color: #6b7280;
                text-decoration: none;
                margin-top: 16px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="title">&#x1F4CD; Destination</div>
            <div class="address">{adresse_complete}</div>
        </div>

        <div class="card">
            <div class="title">Choisir l'application</div>
            <div class="nav-buttons">
                <a href="https://www.google.com/maps/dir/?api=1&destination={adresse_encoded}"
                   class="nav-btn google">
                    &#x1F5FA; Google Maps
                </a>
                <a href="http://maps.apple.com/?daddr={adresse_encoded}"
                   class="nav-btn apple">
                    &#x1F34E; Apple Plans
                </a>
                <a href="https://waze.com/ul?q={adresse_encoded}&navigate=yes"
                   class="nav-btn waze">
                    &#x1F697; Waze
                </a>
            </div>
        </div>

        {contact_html}

        <a href="/ui/technicien/intervention/{intervention_id}" class="back-btn">
            &#x2190; Retour a l'intervention
        </a>
    </body>
    </html>
    '''

    return HTMLResponse(content=html)


@ui_router.get("/technicien/profil", response_class=HTMLResponse)
async def technicien_profil(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Page profil technicien."""
    from datetime import datetime, timedelta

    user_id = user.get("id") or user.get("sub")
    today = date.today()
    start_of_month = today.replace(day=1)

    # Stats du technicien
    try:
        all_interventions = Database.query("interventions", tenant_id, limit=500)
        my_interventions = [
            i for i in all_interventions
            if str(i.get("intervenant_id", "")) == str(user_id)
        ]

        # Interventions du mois
        interventions_mois = len([
            i for i in my_interventions
            if i.get("date_cloture") and i.get("date_cloture").date() >= start_of_month
        ])

        # Note moyenne
        notes = [i.get("avis_client") for i in my_interventions if i.get("avis_client")]
        note_moyenne = round(sum(notes) / len(notes), 1) if notes else "-"

    except Exception:
        interventions_mois = 0
        note_moyenne = "-"

    # Heures du mois
    try:
        temps_entries = Database.query("temps", tenant_id, limit=500)
        my_temps = [
            e for e in temps_entries
            if str(e.get("user_id", "")) == str(user_id)
        ]
        heures_mois = sum(
            (e.get("duree_minutes", 0) or 0) / 60
            for e in my_temps
            if e.get("date") and e.get("date") >= start_of_month
        )
    except Exception:
        heures_mois = 0

    # Nom tenant
    try:
        tenant = Database.get("tenants", tenant_id, tenant_id)
        tenant_name = tenant.get("nom", "Entreprise") if tenant else "Entreprise"
    except Exception:
        tenant_name = "Entreprise"

    try:
        template = jinja_env.get_template("technicien/profil.html")
        html = template.render(
            user=user,
            tenant_name=tenant_name,
            stats={
                "interventions_mois": interventions_mois,
                "heures_mois": round(heures_mois, 1),
                "note_moyenne": note_moyenne
            }
        )
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error("technicien_profil_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@ui_router.get("/technicien/interventions", response_class=HTMLResponse)
async def technicien_interventions_list(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Liste complete des interventions du technicien."""
    from datetime import datetime
    from collections import OrderedDict

    user_id = user.get("id") or user.get("sub")
    today = date.today()

    # Jours et mois en francais
    jours_fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    mois_fr = ["", "janvier", "fevrier", "mars", "avril", "mai", "juin",
               "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]

    # Toutes les interventions du technicien
    all_interventions = Database.query("interventions", tenant_id, limit=500)
    my_interventions = [
        i for i in all_interventions
        if str(i.get("intervenant_id", "")) == str(user_id)
    ]

    # Enrichir avec noms clients
    client_ids = list(set(i.get("client_id") for i in my_interventions if i.get("client_id")))
    clients = {}
    for cid in client_ids:
        try:
            client = Database.get("clients", tenant_id, cid)
            if client:
                # Essayer plusieurs champs possibles pour le nom
                nom = client.get("nom") or client.get("name") or client.get("raison_sociale") or client.get("legal_name") or ""
                prenom = client.get("prenom", "")
                if prenom:
                    clients[cid] = f"{nom} {prenom}".strip()
                else:
                    clients[cid] = nom
        except Exception:
            pass

    for intv in my_interventions:
        intv["client_nom"] = clients.get(intv.get("client_id"), "Client")

    # Trier par date prevue (plus recentes d'abord)
    my_interventions.sort(
        key=lambda x: x.get("date_prevue_debut") or datetime.min,
        reverse=True
    )

    # Grouper par date
    interventions_grouped = OrderedDict()
    for intv in my_interventions:
        date_prevue = intv.get("date_prevue_debut")
        if date_prevue:
            date_obj = date_prevue.date() if hasattr(date_prevue, 'date') else date_prevue
            date_label = f"{jours_fr[date_obj.weekday()]} {date_obj.day} {mois_fr[date_obj.month]}"
        else:
            date_label = "Non planifiee"

        if date_label not in interventions_grouped:
            interventions_grouped[date_label] = []
        interventions_grouped[date_label].append(intv)

    # Compteurs
    counts = {
        "all": len(my_interventions),
        "today": len([i for i in my_interventions if i.get("date_prevue_debut") and
                      (i["date_prevue_debut"].date() if hasattr(i["date_prevue_debut"], 'date') else i["date_prevue_debut"]) == today]),
        "en_cours": len([i for i in my_interventions if i.get("statut") in ["SUR_SITE", "EN_COURS"]]),
        "planifiee": len([i for i in my_interventions if i.get("statut") == "PLANIFIEE"]),
        "terminee": len([i for i in my_interventions if i.get("statut") == "TERMINEE"])
    }

    # Date d'aujourd'hui formatee
    date_aujourdhui = f"{jours_fr[today.weekday()]} {today.day} {mois_fr[today.month]}"

    try:
        template = jinja_env.get_template("technicien/interventions.html")

        def format_datetime(dt):
            if dt and hasattr(dt, 'strftime'):
                return dt.strftime("%d/%m %H:%M")
            return ""

        jinja_env.filters['format_datetime'] = format_datetime

        html = template.render(
            user=user,
            interventions_grouped=interventions_grouped,
            counts=counts,
            date_aujourdhui=date_aujourdhui
        )
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error("technicien_interventions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@ui_router.get("/technicien/temps", response_class=HTMLResponse)
async def technicien_temps(
    request: Request,
    week_offset: int = 0,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Page saisie temps technicien."""
    from datetime import datetime, timedelta

    user_id = user.get("id") or user.get("sub")
    today = date.today()

    # Mois en francais
    mois_fr = ["", "jan", "fev", "mar", "avr", "mai", "juin",
               "juil", "aout", "sep", "oct", "nov", "dec"]
    mois_fr_long = ["", "janvier", "fevrier", "mars", "avril", "mai", "juin",
                    "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]

    # Calculer la semaine
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    start_of_month = today.replace(day=1)

    # Label semaine
    if start_of_week.month == end_of_week.month:
        semaine_label = f"{start_of_week.day} - {end_of_week.day} {mois_fr_long[start_of_week.month]}"
    else:
        semaine_label = f"{start_of_week.day} {mois_fr[start_of_week.month]} - {end_of_week.day} {mois_fr[end_of_week.month]}"

    # Recuperer les temps
    try:
        all_temps = Database.query("temps", tenant_id, limit=500)
        my_temps = [
            e for e in all_temps
            if str(e.get("user_id", "")) == str(user_id)
        ]
    except Exception:
        my_temps = []

    # Filtrer par semaine
    temps_semaine = []
    heures_semaine = 0
    heures_mois = 0

    for entry in my_temps:
        entry_date = entry.get("date")
        if not entry_date:
            continue

        if isinstance(entry_date, datetime):
            entry_date = entry_date.date()

        duree = entry.get("duree_minutes", 0) or 0

        # Cette semaine
        if start_of_week <= entry_date <= end_of_week:
            heures_semaine += duree / 60
            entry["jour"] = entry_date.day
            entry["mois_abbr"] = mois_fr[entry_date.month].upper()
            entry["heures"] = int(duree // 60)
            entry["minutes"] = int(duree % 60)
            temps_semaine.append(entry)

        # Ce mois
        if entry_date >= start_of_month:
            heures_mois += duree / 60

    # Trier par date (plus recentes d'abord)
    temps_semaine.sort(key=lambda x: x.get("date"), reverse=True)

    # Enrichir avec interventions
    for entry in temps_semaine:
        if entry.get("intervention_id"):
            try:
                intv = Database.get("interventions", tenant_id, entry["intervention_id"])
                if intv:
                    entry["intervention_ref"] = intv.get("reference")
            except Exception:
                pass

    # Interventions actives pour le formulaire
    try:
        all_interventions = Database.query("interventions", tenant_id, limit=200)
        interventions_actives = [
            i for i in all_interventions
            if str(i.get("intervenant_id", "")) == str(user_id)
            and i.get("statut") in ["PLANIFIEE", "SUR_SITE", "EN_COURS", "TRAVAUX_TERMINES"]
        ]
        # Enrichir avec client
        for intv in interventions_actives:
            try:
                client = Database.get("clients", tenant_id, intv.get("client_id"))
                intv["client_nom"] = client.get("name", "") if client else ""
            except Exception:
                intv["client_nom"] = ""
    except Exception:
        interventions_actives = []

    try:
        template = jinja_env.get_template("technicien/temps.html")
        html = template.render(
            user=user,
            semaine_label=semaine_label,
            heures_semaine=round(heures_semaine, 1),
            heures_mois=round(heures_mois, 1),
            temps_entries=temps_semaine,
            interventions_actives=interventions_actives
        )
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error("technicien_temps_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


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

    # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
    query_tenant_id = SYSTEM_TENANT_ID if module.acces == "createur_only" else tenant_id

    # Récupérer les données
    items = Database.query(module_name, query_tenant_id, limit=50)

    # Colonnes à afficher (max 5)
    # Utiliser liste_colonnes si défini dans le YAML, sinon les 5 premiers champs
    if hasattr(module, 'liste_colonnes') and module.liste_colonnes:
        display_fields = [f for f in module.liste_colonnes if f in module.champs]
    else:
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

    # Cache pour les relations (éviter de requêter plusieurs fois la même entité)
    relation_cache = {}

    def resolve_relation(field_name: str, field_config, value):
        """Résout une relation UUID vers le nom de l'entité liée."""
        if not value:
            return "-"

        # Récupérer le module lié
        related_module = getattr(field_config, 'relation', None) or getattr(field_config, 'lien_vers', None)
        if not related_module:
            return str(value)

        # Clé de cache
        cache_key = f"{related_module}:{value}"
        if cache_key in relation_cache:
            return relation_cache[cache_key]

        # Requêter l'entité liée
        try:
            related_item = Database.get_by_id(related_module.lower(), tenant_id, value)
            if related_item:
                # Chercher un champ de nom dans l'ordre de préférence
                nom = related_item.get('nom') or related_item.get('name') or related_item.get('raison_sociale') or ""
                prenom = related_item.get('prenom', "")
                if nom and prenom:
                    display_name = f"{nom} {prenom}"
                elif nom:
                    display_name = nom
                else:
                    display_name = (
                        related_item.get('code') or
                        related_item.get('reference') or
                        str(value)[:8] + "..."
                    )
                relation_cache[cache_key] = display_name
                return display_name
        except Exception:
            pass

        return str(value)[:8] + "..."

    table_rows = ""
    for item in items:
        cells = ""
        for f in display_fields:
            value = item.get(f, "")
            field_config = module.champs.get(f)

            if f == "statut" and value:
                value = get_status_badge(value)
            elif field_config and field_config.type in ["relation", "lien"]:
                value = resolve_relation(f, field_config, value)
            elif value is None:
                value = "-"

            cells += f"<td>{value}</td>"
        table_rows += f'''
        <tr data-id="{item['id']}" onclick="handleRowClick(event, '{item['id']}', '/ui/{module_name}/{item['id']}')" style="cursor:pointer">
            <td class="checkbox-cell" onclick="event.stopPropagation()">
                <input type="checkbox" class="row-checkbox" data-id="{item['id']}" onchange="updateBulkActions()">
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

    # Formulaire spécial pour modules avec lignes (documents commerciaux)
    document_modules = ["devis", "factures", "facture", "avoirs", "avoir", "bons_livraison", "bon_livraison", "contrats", "contrat", "notes_frais", "note_frais"]
    if module_name.lower() in document_modules:
        html = generate_layout(
            title=f"Nouveau {module.nom_affichage}",
            content=generate_document_form(module, module_name),
            user=user,
            modules=get_all_modules()
        )
        return HTMLResponse(content=html)

    # Formulaire standard pour autres modules - organisé en sections
    # Grouper les champs par catégorie logique
    sections = organize_fields_into_sections(module)

    html = generate_layout(
        title=f"Nouveau {module.nom_affichage}",
        content=generate_sectioned_form(module_name, sections, module),
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


def organize_intervention_fields(module) -> dict:
    """Organisation specifique des champs pour le module Interventions."""

    # Champs par section dans l'ordre souhaite
    general_fields = [
        "reference", "donneur_ordre_id", "reference_externe", "client_id",
        "type_intervention", "priorite", "corps_etat", "titre", "description"
    ]

    planning_fields = [
        "date_prevue_debut", "date_prevue_fin", "duree_prevue_minutes",
        "intervenant_id"
    ]

    adresse_fields = [
        "adresse_ligne1", "adresse_ligne2", "code_postal", "ville", "pays"
    ]

    contact_fields = [
        "contact_civilite", "contact_sur_place", "telephone_contact", "email_contact"
    ]

    execution_fields = [
        "statut", "date_arrivee_site", "date_demarrage", "date_fin",
        "duree_reelle_minutes", "constat_arrivee", "travaux_realises",
        "anomalies", "recommandations"
    ]

    materiel_fields = [
        "materiel_necessaire", "materiel_utilise", "materiel_utilise_lignes"
    ]

    facturation_fields = [
        "facturable", "montant_ht", "montant_ttc", "facture_generee_id"
    ]

    signature_fields = [
        "signature_client", "nom_signataire", "date_signature", "is_signed",
        "avis_client", "appreciation_client"
    ]

    liens_fields = [
        "projet_id", "affaire_id", "devis_id", "facture_client_id"
    ]

    sections = {
        "General": [],
        "Planning": [],
        "Adresse intervention": [],
        "Contact sur place": [],
        "Execution": [],
        "Materiel": [],
        "Facturation": [],
        "Signature client": [],
        "Liens": [],
        "Autres": []
    }

    # Map des champs vers sections
    field_to_section = {}
    for f in general_fields:
        field_to_section[f] = "General"
    for f in planning_fields:
        field_to_section[f] = "Planning"
    for f in adresse_fields:
        field_to_section[f] = "Adresse intervention"
    for f in contact_fields:
        field_to_section[f] = "Contact sur place"
    for f in execution_fields:
        field_to_section[f] = "Execution"
    for f in materiel_fields:
        field_to_section[f] = "Materiel"
    for f in facturation_fields:
        field_to_section[f] = "Facturation"
    for f in signature_fields:
        field_to_section[f] = "Signature client"
    for f in liens_fields:
        field_to_section[f] = "Liens"

    # Organiser les champs
    for nom, field in module.champs.items():
        if field.type in ["auto", "calcul"]:
            continue

        section_name = field_to_section.get(nom, "Autres")
        sections[section_name].append((nom, field))

    # Trier les champs dans chaque section selon l'ordre defini
    def sort_key(item):
        nom = item[0]
        for idx, f in enumerate(general_fields + planning_fields + adresse_fields +
                                contact_fields + execution_fields + materiel_fields +
                                facturation_fields + signature_fields + liens_fields):
            if f == nom:
                return idx
        return 999

    for section_name in sections:
        sections[section_name].sort(key=sort_key)

    # Supprimer les sections vides
    return {k: v for k, v in sections.items() if v}


def organize_fields_into_sections(module) -> dict:
    """Organise les champs en sections logiques basées sur leur nom/type."""

    # Organisation specifique pour les interventions
    module_name = getattr(module, 'nom', '').lower()
    if 'intervention' in module_name:
        return organize_intervention_fields(module)

    # Sections universelles ordonnées
    sections = {
        "Identification": [],    # Code, nom, type, statut
        "Contact": [],           # Email, téléphone, civilité, contact
        "Adresse": [],           # Adresse, ville, code postal, pays
        "Informations légales": [],  # SIRET, TVA, forme juridique
        "Commercial": [],        # Commercial assigné, conditions paiement
        "Dates & Planning": [],  # Dates prévues, exécution
        "Montants": [],          # Prix, totaux, TVA
        "Notes": [],             # Notes, commentaires, description
        "Liens": [],             # Relations vers autres modules
        "Autres": []
    }

    for nom, field in module.champs.items():
        if field.type in ["auto", "calcul"]:
            continue

        nom_lower = nom.lower()

        # === IDENTIFICATION ===
        if any(x in nom_lower for x in ["code", "name", "nom", "type", "statut", "status", "titre", "title", "reference", "numero"]):
            sections["Identification"].append((nom, field))

        # === CONTACT ===
        elif any(x in nom_lower for x in ["email", "phone", "tel", "mobile", "fax", "contact", "civilite", "website", "linkedin"]):
            sections["Contact"].append((nom, field))

        # === ADRESSE ===
        elif any(x in nom_lower for x in ["address", "adresse", "city", "ville", "postal", "zip", "country", "pays", "state", "region", "departement"]):
            sections["Adresse"].append((nom, field))

        # === INFORMATIONS LÉGALES ===
        elif any(x in nom_lower for x in ["tax_id", "tva_intra", "siret", "siren", "registration", "legal", "raison_sociale", "forme_juridique"]):
            sections["Informations légales"].append((nom, field))

        # === COMMERCIAL ===
        elif any(x in nom_lower for x in ["assigned", "commercial", "payment", "paiement", "credit", "discount", "remise", "currency", "devise", "industry", "secteur", "segment", "source", "score", "revenue", "order_count", "size", "employee"]):
            sections["Commercial"].append((nom, field))

        # === DATES & PLANNING ===
        elif any(x in nom_lower for x in ["date", "debut", "fin", "validite", "expir", "duree", "arrivee", "demarrage", "prevue"]):
            sections["Dates & Planning"].append((nom, field))

        # === MONTANTS ===
        elif any(x in nom_lower for x in ["montant", "prix", "total", "tva", "ht", "ttc", "facturable", "solde"]):
            sections["Montants"].append((nom, field))

        # === NOTES ===
        elif any(x in nom_lower for x in ["note", "comment", "description", "observation", "materiel"]):
            sections["Notes"].append((nom, field))
        elif field.type in ["textarea", "texte long"]:
            sections["Notes"].append((nom, field))

        # === LIENS (relations) ===
        elif field.type in ["lien", "relation"]:
            sections["Liens"].append((nom, field))

        # === AUTRES ===
        else:
            sections["Autres"].append((nom, field))

    # Supprimer les sections vides et retourner dans l'ordre
    return {k: v for k, v in sections.items() if v}


def generate_sectioned_form(module_name: str, sections: dict, module) -> str:
    """Génère un formulaire style Odoo avec 2 colonnes et onglets."""

    section_names = list(sections.keys())

    # Générer les onglets Odoo
    tabs_html = ""
    for i, section_name in enumerate(section_names):
        active = "active" if i == 0 else ""
        tabs_html += f'<a href="#" class="o-notebook-header {active}" onclick="showSection(\'{i}\', event)">{section_name}</a>'

    # Générer le contenu des sections en 2 colonnes
    sections_html = ""
    for i, (section_name, fields) in enumerate(sections.items()):
        display = "block" if i == 0 else "none"

        # Séparer les champs en 2 colonnes
        col1_fields = []
        col2_fields = []
        full_width_fields = []

        for idx, (nom, field) in enumerate(fields):
            # Les textareas prennent toute la largeur
            if field.type in ["textarea", "texte long"]:
                full_width_fields.append((nom, field))
            elif idx % 2 == 0:
                col1_fields.append((nom, field))
            else:
                col2_fields.append((nom, field))

        # Générer colonne 1
        col1_html = ""
        for nom, field in col1_fields:
            col1_html += get_field_html(field, module_name=module_name)

        # Générer colonne 2
        col2_html = ""
        for nom, field in col2_fields:
            col2_html += get_field_html(field, module_name=module_name)

        # Champs pleine largeur (textareas)
        full_width_html = ""
        for nom, field in full_width_fields:
            full_width_html += f'''
            <div style="grid-column: 1 / -1;">
                {get_field_html(field, module_name=module_name)}
            </div>'''

        sections_html += f'''
        <div class="o-notebook-content" id="section-{i}" style="display: {display};">
            <div class="o-group">
                <div class="o-group-col">
                    {col1_html}
                </div>
                <div class="o-group-col">
                    {col2_html}
                </div>
            </div>
            {full_width_html}
        </div>'''

    return f'''
    <!-- Control Panel Odoo -->
    <div class="control-panel">
        <div class="control-panel-left">
            <div class="breadcrumb">
                <a href="/ui/{module_name}">{module.nom_affichage}</a>
                <span class="breadcrumb-separator">/</span>
                <span class="breadcrumb-current">Nouveau</span>
            </div>
        </div>
        <div class="control-panel-right">
            <a href="/ui/{module_name}" class="btn btn-secondary">Annuler</a>
            <button type="button" id="submit-btn" onclick="submitForm()" class="btn btn-primary">Enregistrer</button>
        </div>
    </div>

    <!-- Form Sheet Odoo -->
    <div class="o-form-sheet">
        <form id="create-form">
            <!-- Notebook (onglets) -->
            <div class="o-notebook">
                <div class="o-notebook-headers">
                    {tabs_html}
                </div>
                {sections_html}
            </div>
        </form>
    </div>

    <script>
    function showSection(index, event) {{
        if (event) event.preventDefault();
        // Cacher toutes les sections
        document.querySelectorAll('.o-notebook-content').forEach(s => s.style.display = 'none');
        // Désactiver tous les onglets
        document.querySelectorAll('.o-notebook-header').forEach(t => t.classList.remove('active'));
        // Afficher la section sélectionnée
        document.getElementById('section-' + index).style.display = 'block';
        // Activer l'onglet sélectionné
        document.querySelectorAll('.o-notebook-header')[index].classList.add('active');
    }}
    </script>
    ''' + generate_form_scripts(module_name)


def generate_form_scripts(module_name: str) -> str:
    """Génère les scripts communs pour les formulaires."""
    return f'''
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
            border-bottom: 1px solid var(--gray-200);
        }}
        .modal-header h3 {{ margin: 0; font-size: 18px; }}
        .modal-close {{
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--gray-500);
        }}
        .modal-body {{ padding: 20px; }}
        .modal-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            padding: 16px 20px;
            border-top: 1px solid var(--gray-200);
        }}
    </style>

    <script>
    function showNotification(message, type) {{
        const notif = document.getElementById('notification');
        notif.textContent = message;
        notif.className = 'notification ' + type;
        setTimeout(() => {{ notif.classList.add('hidden'); }}, 4000);
    }}

    function collectFormData() {{
        const form = document.getElementById('create-form');
        const formData = new FormData(form);
        const data = {{}};
        for (const [key, value] of formData.entries()) {{
            const input = form.querySelector(`[name="${{key}}"]`);
            if (input && input.type === 'checkbox') {{
                data[key] = input.checked;
            }} else if (input && input.type === 'number') {{
                data[key] = value ? parseFloat(value) : null;
            }} else if (input && input.classList.contains('datetime-picker')) {{
                // Utiliser la valeur ISO stockée dans data-iso-value
                data[key] = input.dataset.isoValue || value || null;
            }} else {{
                data[key] = value || null;
            }}
        }}
        form.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
            if (!data.hasOwnProperty(cb.name)) data[cb.name] = cb.checked;
        }});
        return data;
    }}

    async function submitForm() {{
        const submitBtn = document.getElementById('submit-btn');
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span>Enregistrement...';
        try {{
            const data = collectFormData();
            const response = await fetch('/api/{module_name}', {{
                method: 'POST',
                credentials: 'include',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(data)
            }});
            if (response.ok) {{
                const result = await response.json();
                showNotification('Enregistrement créé avec succès !', 'success');
                // Vérifier s'il y a une URL de redirection
                const params = new URLSearchParams(window.location.search);
                const redirectUrl = params.get('redirect');
                if (redirectUrl) {{
                    // Retourner à la page précédente avec l'ID du nouveau record
                    const decodedUrl = decodeURIComponent(redirectUrl);
                    const selectField = params.get('select_field');
                    // Stocker l'ID créé pour pré-sélection
                    if (result.id && selectField) {{
                        sessionStorage.setItem('newlyCreatedId', result.id);
                        sessionStorage.setItem('newlyCreatedField', selectField);
                    }}
                    setTimeout(() => {{ window.location.href = decodedUrl; }}, 800);
                }} else {{
                    setTimeout(() => {{ window.location.href = '/ui/{module_name}'; }}, 1500);
                }}
            }} else {{
                const err = await response.json().catch(() => ({{}}));
                showNotification(err.detail || 'Erreur', 'error');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }}
        }} catch (e) {{
            showNotification('Erreur de connexion', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }}
    }}

    document.addEventListener('DOMContentLoaded', function() {{
        // Récupérer le token depuis URL, localStorage ou cookies
        const urlParams = new URLSearchParams(window.location.search);
        const getCookie = (name) => {{
            const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
            return match ? match[2] : null;
        }};
        const authToken = urlParams.get('token') || localStorage.getItem('access_token') || localStorage.getItem('auth_token') || getCookie('access_token') || getCookie('token') || '';

        document.querySelectorAll('select[data-link]').forEach(async select => {{
            const linkedModule = select.dataset.link;
            const currentValue = select.dataset.currentValue || '';
            try {{
                const response = await fetch(`/api/select/${{linkedModule.toLowerCase()}}`, {{
                    credentials: 'include',
                    headers: {{
                        'Authorization': 'Bearer ' + authToken,
                        'Content-Type': 'application/json'
                    }}
                }});
                if (response.ok) {{
                    const data = await response.json();
                    const items = Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : []);
                    const firstOption = select.options[0];
                    select.innerHTML = '';
                    select.appendChild(firstOption);
                    items.forEach(item => {{
                        const opt = document.createElement('option');
                        opt.value = item.id;
                        opt.textContent = item.nom || item.name || item.id;
                        if (currentValue && item.id === currentValue) {{
                            opt.selected = true;
                        }}
                        select.appendChild(opt);
                    }});
                }} else {{
                    console.warn('Erreur chargement ' + linkedModule + ':', response.status);
                }}
            }} catch (e) {{ console.error('Erreur chargement ' + linkedModule + ':', e); }}
        }});
    }});

    function openCreateModal(moduleName, selectId) {{
        document.getElementById('createModalTitle').textContent = 'Créer ' + moduleName;
        document.getElementById('createModalModule').value = moduleName;
        document.getElementById('createModal').style.display = 'flex';
        window.currentSelectId = selectId;
        window.currentModule = moduleName;
    }}
    function closeCreateModal() {{
        document.getElementById('createModal').style.display = 'none';
    }}

    // Auto-remplir les champs quand une relation est sélectionnée
    async function handleRelationAutofill(select) {{
        const autofillConfig = select.dataset.autofill;
        if (!autofillConfig || !select.value) return;

        const linkedModule = select.dataset.link;
        const selectedId = select.value;

        try {{
            const urlParams = new URLSearchParams(window.location.search);
            const authToken = urlParams.get('token') || localStorage.getItem('access_token') || localStorage.getItem('auth_token') || '';

            const response = await fetch(`/api/${{linkedModule.toLowerCase()}}/${{selectedId}}`, {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});

            if (response.ok) {{
                const data = await response.json();

                // Parser la config: "champ_local:champ_distant,..."
                const mappings = autofillConfig.split(',');
                mappings.forEach(mapping => {{
                    const parts = mapping.split(':');
                    const localField = parts[0];
                    const remoteField = parts[1];
                    let value = '';

                    // Cas spécial: _compose_address construit une adresse complète
                    if (remoteField === '_compose_address' && parts.length > 2) {{
                        const addressFields = parts[2].split('|');
                        const addressParts = [];
                        addressFields.forEach(f => {{
                            if (data[f]) addressParts.push(data[f]);
                        }});
                        value = addressParts.join('\\n');
                    }} else {{
                        value = data[remoteField] || '';
                    }}

                    // Trouver le champ local et le remplir
                    const input = document.querySelector(`[name="${{localField}}"]`);
                    if (input && !input.value) {{
                        input.value = value;
                        // Trigger change event pour d'autres listeners
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }});

                console.log('Auto-fill appliqué depuis', linkedModule);
            }}
        }} catch (e) {{
            console.error('Erreur auto-fill:', e);
        }}
    }}

    // Ouvrir la page complete de creation dans une nouvelle fenetre
    function openFullCreatePage(moduleName, selectId) {{
        // Sauvegarder l'URL actuelle pour retour après création
        const returnUrl = encodeURIComponent(window.location.href);
        const url = '/ui/' + moduleName + '/nouveau?redirect=' + returnUrl + '&select_field=' + selectId;
        // Naviguer dans la même page
        window.location.href = url;
    }}

    function openFullCreatePage_OLD(moduleName, selectId) {{
        const params = new URLSearchParams(window.location.search);
        const token = params.get('token') || '';
        const url = '/ui/' + moduleName + '/nouveau?token=' + token;

        // Stocker l'ID du select pour rafraichir apres creation
        window.pendingSelectRefresh = selectId;
        window.pendingModule = moduleName;

        // Ouvrir dans une nouvelle fenetre
        const popup = window.open(url, '_blank', 'width=1200,height=800,scrollbars=yes,resizable=yes');

        // Rafraichir le select quand l'utilisateur revient sur cette page
        window.addEventListener('focus', function onFocus() {{
            if (window.pendingSelectRefresh) {{
                refreshSelectOptions(window.pendingModule, window.pendingSelectRefresh);
                window.pendingSelectRefresh = null;
                window.pendingModule = null;
            }}
            window.removeEventListener('focus', onFocus);
        }});
    }}

    // Rafraichir les options d'un select apres creation
    async function refreshSelectOptions(moduleName, selectId) {{
        const params = new URLSearchParams(window.location.search);
        const token = params.get('token') || '';
        const select = document.getElementById(selectId);
        if (!select) return;

        try {{
            const response = await fetch('/api/' + moduleName.toLowerCase(), {{
                credentials: 'include',
                headers: {{ 'Authorization': 'Bearer ' + token }}
            }});
            if (response.ok) {{
                const data = await response.json();
                const items = Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : []);
                const currentValue = select.value;
                const firstOption = select.options[0];
                select.innerHTML = '';
                select.appendChild(firstOption);
                items.forEach(item => {{
                    const opt = document.createElement('option');
                    opt.value = item.id;
                    opt.textContent = item.nom || item.name || item.code || item.titre || item.numero || item.id;
                    select.appendChild(opt);
                }});
                // Selectionner le dernier element cree (le plus recent)
                if (items.length > 0) {{
                    select.value = items[0].id;
                }}
            }}
        }} catch (e) {{
            console.error('Erreur rafraichissement:', e);
        }}
    }}

    async function saveQuickCreate() {{
        const moduleName = window.currentModule;
        const selectId = window.currentSelectId;
        const nom = document.getElementById('quick_nom').value.trim();

        if (!nom) {{
            alert('Veuillez saisir un nom');
            return;
        }}

        // Récupérer le token
        const params = new URLSearchParams(window.location.search);
        const token = params.get('token') || '';

        // Convertir le nom du module en minuscules pour l'API
        const apiModule = moduleName.toLowerCase();

        try {{
            const response = await fetch('/api/' + apiModule, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                }},
                body: JSON.stringify({{ nom: nom, name: nom }})
            }});

            if (response.ok) {{
                const data = await response.json();
                // Ajouter l'option au select
                const select = document.getElementById(selectId);
                if (select) {{
                    const opt = document.createElement('option');
                    opt.value = data.id;
                    opt.textContent = nom;
                    opt.selected = true;
                    select.appendChild(opt);
                }}
                // Fermer la modal et vider le champ
                document.getElementById('quick_nom').value = '';
                closeCreateModal();
            }} else {{
                const err = await response.json();
                alert('Erreur: ' + (err.detail || 'Création échouée'));
            }}
        }} catch (e) {{
            alert('Erreur: ' + e.message);
        }}
    }}
    </script>

    <div id="createModal" class="modal-overlay" style="display:none;">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="createModalTitle">Créer</h3>
                <button onclick="closeCreateModal()" class="modal-close">&times;</button>
            </div>
            <div class="modal-body" id="createModalBody">
                <div class="form-group"><label class="label">Nom</label><input type="text" class="input" id="quick_nom"></div>
            </div>
            <input type="hidden" id="createModalModule">
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeCreateModal()">Annuler</button>
                <button class="btn btn-primary" onclick="saveQuickCreate()">Créer</button>
            </div>
        </div>
    </div>
    '''


def generate_form(module_name: str, fields_html: str) -> str:
    """Génère un formulaire standard style Odoo avec soumission API."""

    return f'''
    <div class="card">
        <div class="card-header">
            <div class="flex items-center gap-2">
                <span class="badge badge-gray">Nouveau</span>
            </div>
            <div class="flex gap-2">
                <a href="/ui/{module_name}" class="btn btn-secondary">Annuler</a>
                <button type="button" id="submit-btn" onclick="submitForm()" class="btn btn-primary">Enregistrer</button>
            </div>
        </div>

        <form id="create-form" class="card-body">
            <div class="doc-section">
                <div class="form-fields-container">
                    {fields_html}
                </div>
            </div>
        </form>
    </div>
    ''' + generate_form_scripts(module_name)


def generate_document_form(module, module_name: str) -> str:
    """Génère un formulaire style Odoo pour documents avec lignes."""

    # Déterminer le type de document
    doc_types = {
        "devis": "Devis",
        "factures": "Facture",
        "facture": "Facture",
        "avoirs": "Avoir",
        "avoir": "Avoir",
        "bons_livraison": "Bon de livraison",
        "bon_livraison": "Bon de livraison",
        "contrats": "Contrat",
        "contrat": "Contrat",
        "notes_frais": "Note de frais",
        "note_frais": "Note de frais",
    }
    doc_type = doc_types.get(module_name.lower(), module.nom_affichage)

    # Charger les taux TVA depuis constants.yml
    tva_options_html = get_tva_options_html()
    tva_default = get_tva_default()
    tva_default_decimal = tva_default / 100  # 0.20 pour 20%

    return f'''
    <div class="card">
        <div class="card-header">
            <div class="flex items-center gap-2">
                <span class="badge badge-gray">Nouveau</span>
            </div>
            <div class="flex gap-2">
                <a href="/ui/{module_name}" class="btn btn-secondary">Annuler</a>
                <button class="btn btn-primary" onclick="saveDocument()">Enregistrer</button>
            </div>
        </div>

        <div class="card-body">
            <!-- Section Client -->
            <div class="doc-section">
                <div class="doc-row">
                    <div class="doc-field">
                        <label class="label">Client</label>
                        <div class="select-with-create">
                            <select class="input" id="client_id" name="client_id" data-link="Clients" data-autofill="adresse_facturation:_compose_address:adresse1|adresse2|cp|ville" onchange="handleRelationAutofill(this)">
                                <option value="">Sélectionner un client...</option>
                            </select>
                            <button type="button" class="btn-create-inline" onclick="openFullCreatePage('clients', 'client_id')" title="Créer nouveau client">
                                +
                            </button>
                        </div>
                    </div>
                    <div class="doc-field">
                        <label class="label">Date d'expiration</label>
                        <input type="date" class="input" id="date_validite" value="">
                    </div>
                </div>

                <div class="doc-row">
                    <div class="doc-field">
                        <label class="label">Adresse de facturation</label>
                        <textarea class="input" id="adresse_facturation" name="adresse_facturation" rows="2" placeholder="Adresse..."></textarea>
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
                    <span id="tva-label">TVA {tva_default}%</span>
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

    function getProduitsOptions() {{
        const produits = window.produitsData || [];
        let options = '<option value="">-- Sélectionner un produit --</option>';
        produits.forEach(p => {{
            const nom = p.name || p.nom || p.designation || p.libelle || '';
            const prix = p.sale_price || p.prix_vente || p.prix || p.price || p.unit_price || 0;
            options += `<option value="${{p.id}}" data-prix="${{prix}}" data-nom="${{nom}}">${{nom}}</option>`;
        }});
        return options;
    }}

    function onProduitChange(select) {{
        const selectedOption = select.options[select.selectedIndex];
        const tr = select.closest('tr');
        const prixInput = tr.querySelectorAll('input[type="number"]')[0];
        if (selectedOption && selectedOption.dataset.prix) {{
            prixInput.value = parseFloat(selectedOption.dataset.prix) || 0;
        }}
        calculerTotaux();
    }}

    function ajouterLigne() {{
        const tbody = document.getElementById('lignes-table');
        const videRow = tbody.querySelector('.ligne-vide');
        if (videRow) videRow.remove();

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><select class="input" onchange="onProduitChange(this)">${{getProduitsOptions()}}</select></td>
            <td><input type="number" class="input" value="0" step="0.01" style="width:80px" onchange="calculerTotaux()"></td>
            <td><input type="number" class="input" value="1" style="width:60px" onchange="calculerTotaux()"></td>
            <td><select class="input" style="width:100px" onchange="calculerTotaux()">{tva_options_html}</select></td>
            <td class="montant">0,00 €</td>
            <td><button class="btn btn-sm" onclick="this.closest('tr').remove(); calculerTotaux();">✕</button></td>
        `;
        tbody.appendChild(tr);
        ligneIndex++;
    }}

    function calculerTotaux() {{
        let totalHT = 0;
        let totalTVA = 0;
        document.querySelectorAll('#lignes-table tr').forEach(tr => {{
            const inputs = tr.querySelectorAll('input');
            const tvaSelect = tr.querySelector('select');
            if (inputs.length >= 3) {{
                const prix = parseFloat(inputs[1].value) || 0;
                const qte = parseFloat(inputs[2].value) || 0;
                const tauxTVA = parseFloat(tvaSelect?.value) || {tva_default};
                const montantHT = prix * qte;
                const montantTVA = montantHT * (tauxTVA / 100);
                totalHT += montantHT;
                totalTVA += montantTVA;
                tr.querySelector('.montant').textContent = montantHT.toFixed(2) + ' €';
            }}
        }});

        const ttc = totalHT + totalTVA;

        document.getElementById('total-ht').textContent = totalHT.toFixed(2) + ' €';
        document.getElementById('total-tva').textContent = totalTVA.toFixed(2) + ' €';
        document.getElementById('total-ttc').textContent = ttc.toFixed(2) + ' €';

        // Mettre à jour le label TVA si taux mixtes
        const tvaLabel = document.getElementById('tva-label');
        if (tvaLabel) tvaLabel.textContent = 'TVA';
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
                const tauxTVA = parseFloat(tvaSelect?.value) || {tva_default};

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
        const urlParams = new URLSearchParams(window.location.search);
        const authToken = urlParams.get('token') || '';

        try {{
            const response = await fetch('/api/clients', {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});
            if (response.ok) {{
                const data = await response.json();
                const clients = data.items || data || [];
                const select = document.getElementById('client_id');
                clients.forEach(client => {{
                    const option = document.createElement('option');
                    option.value = client.id;
                    option.textContent = client.name || client.nom || client.raison_sociale || client.code || client.id;
                    select.appendChild(option);
                }});

                // Vérifier s'il y a un client nouvellement créé à pré-sélectionner
                const newlyCreatedId = sessionStorage.getItem('newlyCreatedId');
                const newlyCreatedField = sessionStorage.getItem('newlyCreatedField');
                if (newlyCreatedId && newlyCreatedField === 'client_id') {{
                    select.value = newlyCreatedId;
                    sessionStorage.removeItem('newlyCreatedId');
                    sessionStorage.removeItem('newlyCreatedField');
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement clients:', e);
        }}

        // Charger les produits
        try {{
            const respProduits = await fetch('/api/produits', {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});
            if (respProduits.ok) {{
                const dataProduits = await respProduits.json();
                window.produitsData = dataProduits.items || dataProduits || [];
                console.log('Produits chargés:', window.produitsData.length);
            }}
        }} catch (e) {{
            console.error('Erreur chargement produits:', e);
            window.produitsData = [];
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

    // Auto-remplir les champs quand une relation est sélectionnée
    async function handleRelationAutofill(select) {{
        const autofillConfig = select.dataset.autofill;
        if (!autofillConfig || !select.value) return;

        const linkedModule = select.dataset.link;
        const selectedId = select.value;

        try {{
            const urlParams = new URLSearchParams(window.location.search);
            const authToken = urlParams.get('token') || localStorage.getItem('access_token') || localStorage.getItem('auth_token') || '';

            const response = await fetch(`/api/${{linkedModule.toLowerCase()}}/${{selectedId}}`, {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});

            if (response.ok) {{
                const data = await response.json();

                // Parser la config: "champ_local:champ_distant,..."
                const mappings = autofillConfig.split(',');
                mappings.forEach(mapping => {{
                    const parts = mapping.split(':');
                    const localField = parts[0];
                    const remoteField = parts[1];
                    let value = '';

                    // Cas spécial: _compose_address construit une adresse complète
                    if (remoteField === '_compose_address' && parts.length > 2) {{
                        const addressFields = parts[2].split('|');
                        const addressParts = [];
                        addressFields.forEach(f => {{
                            if (data[f]) addressParts.push(data[f]);
                        }});
                        value = addressParts.join('\\n');
                    }} else {{
                        value = data[remoteField] || '';
                    }}

                    // Trouver le champ local et le remplir
                    const input = document.querySelector(`[name="${{localField}}"]`);
                    if (input && !input.value) {{
                        input.value = value;
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }});

                console.log('Auto-fill appliqué depuis', linkedModule);
            }}
        }} catch (e) {{
            console.error('Erreur auto-fill:', e);
        }}
    }}

    // Ouvrir la page de creation dans une nouvelle fenetre
    function openFullCreatePage(moduleName, selectId) {{
        // Sauvegarder l'URL actuelle pour retour après création
        const returnUrl = encodeURIComponent(window.location.href);
        const url = '/ui/' + moduleName + '/nouveau?redirect=' + returnUrl + '&select_field=' + selectId;
        // Naviguer dans la même page
        window.location.href = url;
    }}

    // Rafraichir les options d'un select apres creation
    async function refreshSelectOptions(moduleName, selectId) {{
        const select = document.getElementById(selectId);
        if (!select) return;
        try {{
            const response = await fetch('/api/' + moduleName, {{ credentials: 'include' }});
            if (response.ok) {{
                const data = await response.json();
                const items = Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : []);
                const currentValue = select.value;
                select.innerHTML = '<option value="">Sélectionner un client...</option>';
                items.forEach(item => {{
                    const option = document.createElement('option');
                    option.value = item.id;
                    option.textContent = item.name || item.nom || item.raison_sociale || item.code || item.id;
                    select.appendChild(option);
                }});
                if (currentValue) select.value = currentValue;
            }}
        }} catch (e) {{
            console.error('Erreur rafraichissement:', e);
        }}
    }}
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

    # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
    query_tenant_id = SYSTEM_TENANT_ID if module.acces == "createur_only" else tenant_id

    from uuid import UUID
    item = Database.get_by_id(module_name, query_tenant_id, UUID(item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Enregistrement non trouvé")

    # Générer les champs avec valeurs - layout 2 colonnes style Odoo
    fields_list = []
    full_width_fields = []  # Textareas, JSON fields - pleine largeur

    for nom, field in module.champs.items():
        if field.type not in ["auto", "calcul"]:
            field_html = get_field_html(field, item.get(nom), module_name=module_name)
            # Textareas et JSON en pleine largeur
            if field.type in ["textarea", "json", "texte long", "text"] and field.nom in ["description", "notes", "commentaire", "contenu", "details"]:
                full_width_fields.append(field_html)
            elif field.type in ["textarea", "json"]:
                full_width_fields.append(field_html)
            else:
                fields_list.append(field_html)

    # Diviser en 2 colonnes
    mid = (len(fields_list) + 1) // 2
    col1_html = "".join(fields_list[:mid])
    col2_html = "".join(fields_list[mid:])
    full_width_html = "".join(full_width_fields)

    fields_html = f'''
    <div class="o-group">
        <div class="o-group-col">
            {col1_html}
        </div>
        <div class="o-group-col">
            {col2_html}
        </div>
    </div>
    {f'<div class="o-group-full">{full_width_html}</div>' if full_width_html else ''}
    '''

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

    # Échapper les valeurs pour JavaScript (template literals et attributs HTML)
    def escape_js_string(s):
        if not s:
            return ''
        return str(s).replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$').replace("'", "\\'").replace('"', '\\"')

    # Échapper pour HTML
    import html
    display_name_html = html.escape(str(display_name) if display_name else 'Sans nom')

    display_name_js = escape_js_string(display_name)
    sous_titre_js = escape_js_string(sous_titre)
    item_statut_js = escape_js_string(item_statut)
    module_icone_js = escape_js_string(module_icone)

    html = generate_layout(
        title=f"{module.nom_affichage} - Détail",
        content=f'''
        <div class="mb-4">
            <a href="/ui/{module_name}" class="text-muted">← Retour à la liste</a>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="flex items-center gap-3">
                    {get_status_badge(item.get('statut', 'ACTIF')) if 'statut' in item else '<span class="badge badge-gray">Édition</span>'}
                    <h2 class="font-bold" style="margin: 0;">{display_name_html}</h2>
                    <button class="star-btn" id="fav-btn-{item_id}"
                        onclick="toggleFavori('{module_name}', '{item_id}', `{display_name_js}`, `{sous_titre_js}`, '{item_statut_js}', `{module_icone_js}`, this)"
                        title="Ajouter aux favoris">
                        ☆
                    </button>
                </div>
                <div class="flex gap-2">
                    <button onclick="openPrintPreview()" class="btn btn-secondary btn-sm" title="Apercu avant impression">
                        👁️ <span class="hide-mobile">Aperçu</span>
                    </button>
                    <button onclick="window.print()" class="btn btn-secondary btn-sm" title="Imprimer">
                        🖨️ <span class="hide-mobile">Imprimer</span>
                    </button>
                    <a href="/ui/{module_name}" class="btn btn-secondary">Annuler</a>
                    <button onclick="saveItem()" class="btn btn-primary">Enregistrer</button>
                </div>
            </div>

            <form id="edit-form" class="card-body o-form-sheet">
                {fields_html}
            </form>

            <div class="card-footer flex justify-between no-print">
                <div class="flex gap-2">
                    <button onclick="deleteItem()" class="btn btn-danger btn-sm">Supprimer</button>
                    <button onclick="duplicateItem()" class="btn btn-secondary btn-sm" title="Creer une copie">Dupliquer</button>
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
                    <div class="print-doc-number">{display_name_html}</div>
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
        function getToken() {{
            const params = new URLSearchParams(window.location.search);
            return params.get('token') || localStorage.getItem('auth_token') || '';
        }}

        async function saveItem() {{
            const form = document.getElementById('edit-form');
            const formData = new FormData(form);
            const data = {{}};

            // Champs qui attendent des types spécifiques
            const numberFields = ['duree_reelle_minutes', 'geoloc_arrivee_lat', 'geoloc_arrivee_lng', 'avis_client', 'montant_ht', 'montant_ttc', 'quantite', 'prix_unitaire', 'taux_tva', 'remise', 'total_ht', 'total_ttc', 'latitude', 'longitude', 'note'];
            const jsonFields = ['photos_avant', 'photos_apres', 'materiel_utilise_lignes', 'metadata', 'config', 'options', 'donnees'];
            const listFields = ['tags', 'etiquettes', 'categories'];
            const boolFields = ['is_signed', 'facturable', 'is_active', 'archived', 'urgent', 'prioritaire'];

            // Convertir FormData en objet, gérer les checkboxes
            formData.forEach((value, key) => {{
                // Nettoyer les chaînes vides selon le type de champ
                if (value === '' || value === null || value === undefined) {{
                    if (numberFields.includes(key)) {{
                        data[key] = null;
                    }} else if (jsonFields.includes(key)) {{
                        data[key] = {{}};
                    }} else if (listFields.includes(key)) {{
                        data[key] = [];
                    }} else if (boolFields.includes(key)) {{
                        data[key] = false;
                    }} else {{
                        data[key] = null;
                    }}
                }} else {{
                    // Convertir les nombres
                    if (numberFields.includes(key)) {{
                        const num = parseFloat(value);
                        data[key] = isNaN(num) ? null : num;
                    }} else {{
                        data[key] = value;
                    }}
                }}
            }});

            // Gérer les checkboxes non cochées
            form.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
                if (!formData.has(cb.name)) {{
                    data[cb.name] = false;
                }} else {{
                    data[cb.name] = true;
                }}
            }});

            const token = getToken();
            try {{
                const res = await fetch('/api/{module_name}/{item_id}', {{
                    method: 'PUT',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    }},
                    body: JSON.stringify(data)
                }});

                if (res.ok) {{
                    window.location.reload();
                }} else {{
                    const err = await res.json().catch(() => ({{}}));
                    alert('Erreur: ' + (err.detail || err.message || 'Enregistrement échoué'));
                    console.error('Save error:', err);
                }}
            }} catch (e) {{
                alert('Erreur réseau: ' + e.message);
                console.error('Network error:', e);
            }}
        }}

        async function deleteItem() {{
            if (!confirm('Supprimer cet élément ?')) return;
            const token = getToken();
            const res = await fetch('/api/{module_name}/{item_id}', {{
                method: 'DELETE',
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + token
                }}
            }});
            if (res.ok) window.location = '/ui/{module_name}';
            else alert('Erreur de suppression');
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
            trackRecent('{module_name}', '{item_id}', `{display_name_js}`, `{sous_titre_js}`, '{item_statut_js}', `{module_icone_js}`);
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


# Alias pour compatibilité avec le code existant
get_icon = get_icon_html


def generate_intervention_wizard() -> str:
    """Génère le wizard Typeform pour création d'interventions."""
    return '''
    <!-- Wizard Typeform Interventions -->
    <style>
    .wizard-overlay {
        position: fixed;
        inset: 0;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        z-index: 2000;
        display: none;
        flex-direction: column;
    }
    .wizard-overlay.open { display: flex; }

    .wizard-progress {
        height: 4px;
        background: rgba(255,255,255,0.2);
    }
    .wizard-progress-bar {
        height: 100%;
        background: white;
        transition: width 0.3s ease;
        width: 12.5%;
    }

    .wizard-close {
        position: absolute;
        top: 16px;
        right: 16px;
        background: rgba(255,255,255,0.2);
        border: none;
        color: white;
        width: 44px;
        height: 44px;
        border-radius: 50%;
        font-size: 24px;
        cursor: pointer;
        z-index: 10;
    }
    .wizard-close:hover { background: rgba(255,255,255,0.3); }

    .wizard-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 24px;
        max-width: 500px;
        margin: 0 auto;
        width: 100%;
        overflow-y: auto;
    }

    .wizard-question {
        font-size: 24px;
        font-weight: 700;
        color: white;
        margin-bottom: 24px;
        line-height: 1.3;
    }

    .wizard-subtitle {
        font-size: 14px;
        color: rgba(255,255,255,0.7);
        margin-top: -16px;
        margin-bottom: 24px;
    }

    .wizard-input {
        background: white;
        border: none;
        border-radius: 12px;
        padding: 16px 20px;
        font-size: 18px;
        width: 100%;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        margin-bottom: 12px;
    }
    .wizard-input:focus {
        outline: none;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
    }

    .wizard-textarea {
        background: white;
        border: none;
        border-radius: 12px;
        padding: 16px 20px;
        font-size: 16px;
        width: 100%;
        min-height: 120px;
        resize: vertical;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    }

    .wizard-cards {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
    }
    .wizard-card {
        background: white;
        border-radius: 12px;
        padding: 20px 16px;
        text-align: center;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
        border: 3px solid transparent;
    }
    .wizard-card:hover { transform: translateY(-2px); }
    .wizard-card:active { transform: scale(0.95); }
    .wizard-card.selected {
        border-color: #4ade80;
        box-shadow: 0 0 20px rgba(74, 222, 128, 0.3);
    }
    .wizard-card-icon {
        font-size: 28px;
        margin-bottom: 8px;
    }
    .wizard-card-label {
        font-size: 14px;
        font-weight: 600;
        color: #333;
    }

    .wizard-option-btn {
        background: rgba(255,255,255,0.95);
        border: none;
        border-radius: 12px;
        padding: 16px 20px;
        font-size: 16px;
        width: 100%;
        text-align: left;
        cursor: pointer;
        margin-bottom: 8px;
        transition: transform 0.2s;
    }
    .wizard-option-btn:hover { transform: translateX(4px); }
    .wizard-option-btn.selected {
        background: white;
        box-shadow: 0 0 0 3px #4ade80;
    }

    .wizard-client-result {
        background: white;
        border-radius: 12px;
        padding: 16px;
        margin-top: 8px;
        cursor: pointer;
        transition: transform 0.2s;
    }
    .wizard-client-result:hover { transform: translateX(4px); }
    .wizard-client-result.selected { box-shadow: 0 0 0 3px #4ade80; }
    .wizard-client-name { font-weight: 600; color: #333; }
    .wizard-client-info { font-size: 13px; color: #666; margin-top: 4px; }

    .wizard-quick-btns {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
        flex-wrap: wrap;
    }
    .wizard-quick-btn {
        background: rgba(255,255,255,0.2);
        border: none;
        border-radius: 20px;
        padding: 8px 16px;
        color: white;
        font-size: 14px;
        cursor: pointer;
        transition: background 0.2s;
    }
    .wizard-quick-btn:hover { background: rgba(255,255,255,0.3); }
    .wizard-quick-btn.selected { background: white; color: #764ba2; }

    .wizard-time-btns {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin-bottom: 8px;
    }
    .wizard-time-btn {
        background: rgba(255,255,255,0.15);
        border: none;
        border-radius: 8px;
        padding: 10px 8px;
        color: white;
        font-size: 14px;
        cursor: pointer;
        transition: background 0.2s;
    }
    .wizard-time-btn:hover { background: rgba(255,255,255,0.25); }
    .wizard-time-btn.selected { background: white; color: #764ba2; font-weight: 600; }

    .wizard-selected-item {
        background: rgba(74, 222, 128, 0.2);
        border: 2px solid #4ade80;
        border-radius: 8px;
        padding: 12px 16px;
        color: white;
        margin-top: 12px;
        font-weight: 500;
    }

    .wizard-summary {
        background: rgba(255,255,255,0.95);
        border-radius: 16px;
        padding: 20px;
        color: #333;
    }
    .wizard-summary-row {
        display: flex;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid #eee;
    }
    .wizard-summary-row:last-child { border-bottom: none; }
    .wizard-summary-label { color: #666; font-size: 14px; }
    .wizard-summary-value { font-weight: 600; }

    .wizard-nav {
        padding: 16px 24px;
        padding-bottom: calc(16px + env(safe-area-inset-bottom));
        display: flex;
        gap: 12px;
    }
    .wizard-btn {
        flex: 1;
        padding: 16px;
        border-radius: 12px;
        font-size: 16px;
        font-weight: 600;
        border: none;
        cursor: pointer;
        transition: transform 0.2s, opacity 0.2s;
    }
    .wizard-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .wizard-btn-next { background: white; color: #764ba2; }
    .wizard-btn-next:hover:not(:disabled) { transform: translateY(-2px); }
    .wizard-btn-back { background: rgba(255,255,255,0.2); color: white; }

    .wizard-loading {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 2px solid rgba(118,75,162,0.3);
        border-top-color: #764ba2;
        border-radius: 50%;
        animation: wizard-spin 0.8s linear infinite;
    }
    @keyframes wizard-spin {
        to { transform: rotate(360deg); }
    }
    </style>

    <div id="interventionWizard" class="wizard-overlay">
        <div class="wizard-progress">
            <div class="wizard-progress-bar" id="wizardProgress"></div>
        </div>

        <button class="wizard-close" onclick="closeWizard()">&times;</button>

        <div class="wizard-content" id="wizardContent">
            <!-- Contenu dynamique -->
        </div>

        <div class="wizard-nav">
            <button class="wizard-btn wizard-btn-back" id="wizardBack" onclick="wizardBack()">Retour</button>
            <button class="wizard-btn wizard-btn-next" id="wizardNext" onclick="wizardNext()">Suivant</button>
        </div>
    </div>

    <script>
    // État du wizard
    var wizardState = {
        currentStep: 0,
        data: {},
        clientData: null,
        clientResults: []
    };

    var WIZARD_STEPS = [
        { id: 'client', question: 'Pour quel client ?', type: 'client' },
        { id: 'donneur', question: 'Qui demande l\\'intervention ?', type: 'donneur' },
        { id: 'facture', question: 'Qui sera facturé ?', type: 'facture' },
        { id: 'refext', question: 'Référence externe ?', type: 'refext' },
        { id: 'type', question: "Quel type d'intervention ?", type: 'cards', field: 'type_intervention',
          options: [
            { value: 'INSTALLATION', label: 'Installation', icon: '🔧' },
            { value: 'MAINTENANCE', label: 'Maintenance', icon: '🛠️' },
            { value: 'REPARATION', label: 'Réparation', icon: '🔩' },
            { value: 'INSPECTION', label: 'Inspection', icon: '🔍' },
            { value: 'AUTRE', label: 'Autre', icon: '📋' }
          ]},
        { id: 'priority', question: 'Quelle priorité ?', type: 'cards', field: 'priorite',
          options: [
            { value: 'LOW', label: 'Basse', icon: '🟢' },
            { value: 'NORMAL', label: 'Normale', icon: '🔵' },
            { value: 'HIGH', label: 'Haute', icon: '🟠' },
            { value: 'URGENT', label: 'Urgente', icon: '🔴' }
          ]},
        { id: 'description', question: 'Décrivez le problème', type: 'description' },
        { id: 'address', question: "Lieu de l'intervention ?", type: 'address' },
        { id: 'contact', question: 'Contact sur place différent du client ?', type: 'contact' },
        { id: 'technicien', question: 'Quel technicien assigner ?', type: 'technicien' },
        { id: 'schedule', question: 'Quand planifier ?', type: 'schedule' },
        { id: 'confirm', question: 'Confirmer la création', type: 'summary' }
    ];

    function openInterventionWizard() {
        wizardState = {
            currentStep: 0,
            data: {
                donneurSameAsClient: true,  // Par défaut, le client est le demandeur
                factureSameAsClient: true,  // Par défaut, on facture le client
                contactDifferent: false,    // Par défaut, le contact est le client
                heure_intervention: '09:00' // Heure par défaut
            },
            clientData: null,
            clientResults: []
        };
        document.getElementById('interventionWizard').classList.add('open');
        document.body.style.overflow = 'hidden';
        renderWizardStep();
    }

    function closeWizard() {
        document.getElementById('interventionWizard').classList.remove('open');
        document.body.style.overflow = '';
    }

    function renderWizardStep() {
        var step = WIZARD_STEPS[wizardState.currentStep];
        var container = document.getElementById('wizardContent');
        var progress = ((wizardState.currentStep + 1) / WIZARD_STEPS.length) * 100;
        document.getElementById('wizardProgress').style.width = progress + '%';

        var html = '<div class="wizard-question">' + step.question + '</div>';

        switch(step.type) {
            case 'client': html += renderClientStep(); break;
            case 'donneur': html += renderDonneurStep(); break;
            case 'facture': html += renderFactureStep(); break;
            case 'refext': html += renderRefExtStep(); break;
            case 'cards': html += renderCardsStep(step); break;
            case 'description': html += renderDescriptionStep(); break;
            case 'address': html += renderAddressStep(); break;
            case 'contact': html += renderContactStep(); break;
            case 'technicien': html += renderTechnicienStep(); break;
            case 'schedule': html += renderScheduleStep(); break;
            case 'summary': html += renderSummaryStep(); break;
        }

        container.innerHTML = html;
        updateWizardNav();

        // Focus premier input
        var firstInput = container.querySelector('input, textarea');
        if (firstInput) setTimeout(function() { firstInput.focus(); }, 100);
    }

    function renderClientStep() {
        var html = '<input type="text" class="wizard-input" id="wizardClientSearch" placeholder="Rechercher un client..." oninput="searchClients(this.value)">';
        html += '<button type="button" class="wizard-option-btn" onclick="showQuickClientModal()" style="margin-top:12px;text-align:center;">➕ Créer un nouveau client</button>';
        html += '<div id="wizardClientResults">';
        if (wizardState.clientResults.length > 0) {
            wizardState.clientResults.forEach(function(c) {
                var selected = wizardState.data.client_id === c.id ? 'selected' : '';
                html += '<div class="wizard-client-result ' + selected + '" onclick="selectClient(\\'' + c.id + '\\')">';
                html += '<div class="wizard-client-name">' + (c.nom || c.raison_sociale || 'Client') + '</div>';
                html += '<div class="wizard-client-info">' + (c.ville || '') + (c.telephone ? ' • ' + c.telephone : '') + '</div>';
                html += '</div>';
            });
        }
        html += '</div>';
        // Modal création client rapide
        html += '<div id="quickClientModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:3000;align-items:center;justify-content:center;overflow-y:auto;">';
        html += '<div style="background:white;border-radius:16px;padding:24px;width:90%;max-width:450px;margin:40px auto;max-height:90vh;overflow-y:auto;">';
        html += '<h3 style="margin:0 0 16px;color:#333;">Nouveau client</h3>';

        // Infos client
        html += '<input type="text" class="wizard-input" id="quickClientNom" placeholder="Nom du client *" style="margin-bottom:12px;">';
        html += '<input type="tel" class="wizard-input" id="quickClientTel" placeholder="Téléphone" style="margin-bottom:12px;">';
        html += '<input type="email" class="wizard-input" id="quickClientEmail" placeholder="Email" style="margin-bottom:16px;">';

        // Adresse client
        html += '<div style="color:#666;font-size:13px;margin-bottom:8px;font-weight:600;">Adresse du client</div>';
        html += '<input type="text" class="wizard-input" id="quickClientAdresse1" placeholder="Adresse" style="margin-bottom:8px;">';
        html += '<input type="text" class="wizard-input" id="quickClientAdresse2" placeholder="Adresse ligne 2 (optionnel)" style="margin-bottom:8px;">';
        html += '<div style="display:flex;gap:8px;margin-bottom:16px;">';
        html += '<input type="text" class="wizard-input" id="quickClientCp" placeholder="Code postal" style="width:120px;">';
        html += '<input type="text" class="wizard-input" id="quickClientVille" placeholder="Ville" style="flex:1;">';
        html += '</div>';

        // Question : adresse d\\'intervention ?
        html += '<div style="background:#f5f3ff;border-radius:12px;padding:16px;margin-bottom:16px;">';
        html += '<div style="color:#333;font-weight:600;margin-bottom:12px;">📍 Lieu d\\'intervention</div>';
        html += '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:8px;">';
        html += '<input type="radio" name="interventionLieu" id="lieuMeme" checked onchange="toggleInterventionFields()">';
        html += '<span>Même adresse que le client</span>';
        html += '</label>';
        html += '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">';
        html += '<input type="radio" name="interventionLieu" id="lieuAutre" onchange="toggleInterventionFields()">';
        html += '<span>Adresse différente</span>';
        html += '</label>';
        html += '</div>';

        // Champs adresse intervention (masqués par défaut)
        html += '<div id="interventionFieldsContainer" style="display:none;margin-bottom:16px;">';
        html += '<div style="color:#666;font-size:13px;margin-bottom:8px;font-weight:600;">Adresse d\\'intervention</div>';
        html += '<input type="text" class="wizard-input" id="quickIntervAdresse" placeholder="Adresse intervention" style="margin-bottom:8px;">';
        html += '<div style="display:flex;gap:8px;margin-bottom:8px;">';
        html += '<input type="text" class="wizard-input" id="quickIntervCp" placeholder="Code postal" style="width:120px;">';
        html += '<input type="text" class="wizard-input" id="quickIntervVille" placeholder="Ville" style="flex:1;">';
        html += '</div>';
        html += '<input type="text" class="wizard-input" id="quickIntervContact" placeholder="Nom du contact sur place" style="margin-bottom:8px;">';
        html += '<input type="tel" class="wizard-input" id="quickIntervTel" placeholder="Téléphone contact" style="margin-bottom:8px;">';
        html += '</div>';

        html += '<div style="display:flex;gap:12px;">';
        html += '<button onclick="hideQuickClientModal()" style="flex:1;padding:12px;border-radius:8px;border:1px solid #ddd;background:white;cursor:pointer;">Annuler</button>';
        html += '<button onclick="createQuickClient()" style="flex:1;padding:12px;border-radius:8px;border:none;background:#764ba2;color:white;cursor:pointer;font-weight:600;">Créer</button>';
        html += '</div></div></div>';
        return html;
    }

    function toggleInterventionFields() {
        var container = document.getElementById('interventionFieldsContainer');
        var lieuAutre = document.getElementById('lieuAutre');
        if (container && lieuAutre) {
            container.style.display = lieuAutre.checked ? 'block' : 'none';
        }
    }

    function showQuickClientModal() {
        var modal = document.getElementById('quickClientModal');
        if (modal) {
            modal.style.display = 'flex';
            document.getElementById('quickClientNom').focus();
        }
    }

    function hideQuickClientModal() {
        var modal = document.getElementById('quickClientModal');
        if (modal) modal.style.display = 'none';
    }

    async function createQuickClient() {
        var nom = document.getElementById('quickClientNom').value.trim();
        var tel = document.getElementById('quickClientTel').value.trim();
        var email = document.getElementById('quickClientEmail').value.trim();
        var adresse1 = document.getElementById('quickClientAdresse1').value.trim();
        var adresse2 = document.getElementById('quickClientAdresse2').value.trim();
        var cp = document.getElementById('quickClientCp').value.trim();
        var ville = document.getElementById('quickClientVille').value.trim();

        if (!nom) {
            alert('Le nom est requis');
            return;
        }

        try {
            var res = await fetch('/api/clients', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    nom: nom,
                    telephone: tel,
                    email: email,
                    adresse1: adresse1,
                    adresse2: adresse2,
                    cp: cp,
                    ville: ville
                })
            });

            if (res.ok) {
                var client = await res.json();
                // Enrichir avec les données saisies (au cas où l'API ne les retourne pas)
                client.adresse1 = adresse1;
                client.adresse2 = adresse2;
                client.cp = cp;
                client.ville = ville;
                client.telephone = tel;
                client.contact_name = nom;

                hideQuickClientModal();

                // Sélectionner automatiquement le nouveau client
                wizardState.data.client_id = client.id;
                wizardState.data.client_nom = client.nom;
                wizardState.clientData = client;
                wizardState.clientResults = [client];

                // Gérer l'adresse d'intervention
                var lieuAutre = document.getElementById('lieuAutre');
                if (lieuAutre && lieuAutre.checked) {
                    // Adresse intervention différente
                    wizardState.data.useClientAddress = false;
                    wizardState.data.adresse_ligne1 = document.getElementById('quickIntervAdresse').value.trim();
                    wizardState.data.code_postal = document.getElementById('quickIntervCp').value.trim();
                    wizardState.data.ville = document.getElementById('quickIntervVille').value.trim();
                    // Contact sur place
                    wizardState.data.contactDifferent = true;
                    wizardState.data.contact_sur_place = document.getElementById('quickIntervContact').value.trim();
                    wizardState.data.telephone_contact = document.getElementById('quickIntervTel').value.trim();
                } else {
                    // Même adresse que le client
                    wizardState.data.useClientAddress = true;
                    wizardState.data.adresse_ligne1 = adresse1;
                    wizardState.data.code_postal = cp;
                    wizardState.data.ville = ville;
                    // Contact = client
                    wizardState.data.contactDifferent = false;
                    wizardState.data.contact_sur_place = nom;
                    wizardState.data.telephone_contact = tel;
                }

                renderWizardStep();
            } else {
                var err = await res.json();
                alert('Erreur: ' + (err.detail || 'Création échouée'));
            }
        } catch(e) {
            alert('Erreur: ' + e.message);
        }
    }

    // === DONNEUR D'ORDRE ===
    function renderDonneurStep() {
        var html = '<div class="wizard-subtitle">Qui a demandé cette intervention ?</div>';
        html += '<button class="wizard-option-btn ' + (wizardState.data.donneurSameAsClient ? 'selected' : '') + '" onclick="setDonneurSameAsClient(true)">';
        html += '👤 Le client lui-même (' + (wizardState.data.client_nom || 'Client') + ')';
        html += '</button>';
        html += '<button class="wizard-option-btn ' + (wizardState.data.donneurSameAsClient === false ? 'selected' : '') + '" onclick="setDonneurSameAsClient(false)">';
        html += '🏢 Autre donneur d\\'ordre';
        html += '</button>';

        if (wizardState.data.donneurSameAsClient === false) {
            html += '<div style="margin-top:16px;">';
            html += '<input type="text" class="wizard-input" id="wizardDonneurSearch" placeholder="Rechercher un donneur d\\'ordre..." oninput="searchDonneurs(this.value)">';
            html += '<div id="wizardDonneurResults"></div>';
            if (wizardState.data.donneur_ordre_nom) {
                html += '<div class="wizard-selected-item">✓ ' + wizardState.data.donneur_ordre_nom + '</div>';
            }
            html += '</div>';
        }
        return html;
    }

    function setDonneurSameAsClient(same) {
        wizardState.data.donneurSameAsClient = same;
        if (same) {
            wizardState.data.donneur_ordre_id = null;
            wizardState.data.donneur_ordre_nom = null;
        }
        renderWizardStep();
        updateWizardNav();
    }

    var donneurSearchTimeout;
    function searchDonneurs(query) {
        clearTimeout(donneurSearchTimeout);
        if (query.length < 2) {
            document.getElementById('wizardDonneurResults').innerHTML = '';
            return;
        }
        donneurSearchTimeout = setTimeout(async function() {
            try {
                var res = await fetch('/api/donneur_ordre?search=' + encodeURIComponent(query) + '&limit=5', { credentials: 'include' });
                if (!res.ok) return;
                var data = await res.json();
                var items = data.donneur_ordre || data.items || (Array.isArray(data) ? data : []);
                var html = '';
                items.forEach(function(d) {
                    html += '<div class="wizard-client-result" onclick="selectDonneur(\\'' + d.id + '\\', \\'' + (d.nom || d.raison_sociale || '').replace(/'/g, "\\\\'") + '\\')">';
                    html += '<div class="wizard-client-name">' + (d.nom || d.raison_sociale || 'Donneur') + '</div>';
                    html += '</div>';
                });
                document.getElementById('wizardDonneurResults').innerHTML = html;
            } catch(e) { console.error(e); }
        }, 300);
    }

    function selectDonneur(id, nom) {
        wizardState.data.donneur_ordre_id = id;
        wizardState.data.donneur_ordre_nom = nom;
        renderWizardStep();
        updateWizardNav();
    }

    // === QUI SERA FACTURE ===
    function renderFactureStep() {
        var html = '<div class="wizard-subtitle">Qui recevra la facture ?</div>';
        html += '<button class="wizard-option-btn ' + (wizardState.data.factureSameAsClient ? 'selected' : '') + '" onclick="setFactureSameAsClient(true)">';
        html += '👤 Le client (' + (wizardState.data.client_nom || 'Client') + ')';
        html += '</button>';
        html += '<button class="wizard-option-btn ' + (wizardState.data.factureSameAsClient === false ? 'selected' : '') + '" onclick="setFactureSameAsClient(false)">';
        html += '🏢 Un autre client/tiers';
        html += '</button>';

        if (wizardState.data.factureSameAsClient === false) {
            html += '<div style="margin-top:16px;">';
            html += '<input type="text" class="wizard-input" id="wizardFactureSearch" placeholder="Rechercher le client à facturer..." oninput="searchFactureClient(this.value)">';
            html += '<div id="wizardFactureResults"></div>';
            if (wizardState.data.facture_client_nom) {
                html += '<div class="wizard-selected-item">✓ ' + wizardState.data.facture_client_nom + '</div>';
            }
            html += '</div>';
        }
        return html;
    }

    function setFactureSameAsClient(same) {
        wizardState.data.factureSameAsClient = same;
        if (same) {
            wizardState.data.facture_autre_client_id = null;
            wizardState.data.facture_client_nom = null;
        }
        renderWizardStep();
        updateWizardNav();
    }

    var factureSearchTimeout;
    function searchFactureClient(query) {
        clearTimeout(factureSearchTimeout);
        if (query.length < 2) {
            document.getElementById('wizardFactureResults').innerHTML = '';
            return;
        }
        factureSearchTimeout = setTimeout(async function() {
            try {
                var res = await fetch('/api/clients?search=' + encodeURIComponent(query) + '&limit=5', { credentials: 'include' });
                if (!res.ok) return;
                var data = await res.json();
                var items = data.clients || data.items || (Array.isArray(data) ? data : []);
                var html = '';
                items.forEach(function(c) {
                    html += '<div class="wizard-client-result" onclick="selectFactureClient(\\'' + c.id + '\\', \\'' + (c.nom || c.raison_sociale || '').replace(/'/g, "\\\\'") + '\\')">';
                    html += '<div class="wizard-client-name">' + (c.nom || c.raison_sociale || 'Client') + '</div>';
                    html += '<div class="wizard-client-info">' + (c.ville || '') + '</div>';
                    html += '</div>';
                });
                document.getElementById('wizardFactureResults').innerHTML = html;
            } catch(e) { console.error(e); }
        }, 300);
    }

    function selectFactureClient(id, nom) {
        wizardState.data.facture_autre_client_id = id;
        wizardState.data.facture_client_nom = nom;
        renderWizardStep();
        updateWizardNav();
    }

    // === REFERENCE EXTERNE ===
    function renderRefExtStep() {
        var html = '<div class="wizard-subtitle">Numéro de référence externe (bon de commande, etc.)</div>';
        var refVal = wizardState.data.reference_externe || '';
        html += '<input type="text" class="wizard-input" id="wizardRefExt" placeholder="Ex: BC-2026-001, REF12345..." value="' + refVal + '">';
        html += '<div style="color:rgba(255,255,255,0.7);font-size:13px;margin-top:12px;">Optionnel - Laissez vide si non applicable</div>';
        return html;
    }

    // === TECHNICIEN ===
    function renderTechnicienStep() {
        var html = '<div class="wizard-subtitle">Sélectionnez le technicien qui interviendra</div>';

        // Option: pas de technicien assigné
        html += '<button class="wizard-option-btn ' + (!wizardState.data.intervenant_id ? 'selected' : '') + '" onclick="selectTechnicien(null, null)">';
        html += '📋 Pas encore assigné';
        html += '</button>';

        // Liste des techniciens
        html += '<div id="wizardTechnicienList" style="margin-top:12px;">';
        if (wizardState.techniciens && wizardState.techniciens.length > 0) {
            wizardState.techniciens.forEach(function(t) {
                var selected = wizardState.data.intervenant_id === t.id ? 'selected' : '';
                html += '<button class="wizard-option-btn ' + selected + '" onclick="selectTechnicien(\\'' + t.id + '\\', \\'' + (t.nom || '').replace(/'/g, "\\\\'") + '\\')">';
                html += '👷 ' + (t.prenom ? t.prenom + ' ' : '') + (t.nom || t.email || 'Technicien');
                html += '</button>';
            });
        } else {
            html += '<div style="color:rgba(255,255,255,0.7);font-size:14px;">Chargement des techniciens...</div>';
            // Charger les techniciens
            loadTechniciens();
        }
        html += '</div>';

        // Afficher temps de trajet estimé si technicien et adresse
        if (wizardState.data.intervenant_id && wizardState.data.ville) {
            html += '<div class="wizard-trajet-info" style="margin-top:16px;background:rgba(255,255,255,0.15);padding:12px;border-radius:8px;">';
            html += '<span style="opacity:0.8;">🚗 Temps de trajet estimé :</span> ';
            html += '<strong>' + (wizardState.data.temps_trajet_estime || '~30') + ' min</strong>';
            html += '</div>';
        }

        return html;
    }

    async function loadTechniciens() {
        try {
            var res = await fetch('/api/utilisateurs?role=technicien&limit=50', { credentials: 'include' });
            if (!res.ok) {
                // Essayer avec tous les utilisateurs
                res = await fetch('/api/utilisateurs?limit=50', { credentials: 'include' });
            }
            if (res.ok) {
                var data = await res.json();
                wizardState.techniciens = data.items || data.utilisateurs || (Array.isArray(data) ? data : []);
                renderWizardStep();
            }
        } catch(e) {
            console.error('Erreur chargement techniciens:', e);
        }
    }

    function selectTechnicien(id, nom) {
        wizardState.data.intervenant_id = id;
        wizardState.data.intervenant_nom = nom;

        // Calculer temps de trajet estimé (simulation basique)
        if (id && wizardState.data.ville) {
            // En production, appeler une API de calcul de distance
            wizardState.data.temps_trajet_estime = Math.floor(Math.random() * 45) + 15; // 15-60 min
        } else {
            wizardState.data.temps_trajet_estime = null;
        }

        renderWizardStep();
        updateWizardNav();
    }

    var searchTimeout;
    function searchClients(query) {
        clearTimeout(searchTimeout);
        if (query.length < 2) {
            wizardState.clientResults = [];
            document.getElementById('wizardClientResults').innerHTML = '';
            return;
        }
        searchTimeout = setTimeout(async function() {
            try {
                var res = await fetch('/api/clients?search=' + encodeURIComponent(query) + '&limit=5', { credentials: 'include' });
                if (!res.ok) {
                    console.error('Search clients error:', res.status);
                    wizardState.clientResults = [];
                    renderClientResults();
                    return;
                }
                var data = await res.json();
                // Handle different API response formats
                wizardState.clientResults = data.clients || data.items || (Array.isArray(data) ? data : []);
                renderClientResults();
            } catch(e) {
                console.error('Search clients exception:', e);
                wizardState.clientResults = [];
                renderClientResults();
            }
        }, 300);
    }

    function renderClientResults() {
        var container = document.getElementById('wizardClientResults');
        if (!container) return;
        var html = '';
        wizardState.clientResults.forEach(function(c) {
            var selected = wizardState.data.client_id === c.id ? 'selected' : '';
            html += '<div class="wizard-client-result ' + selected + '" onclick="selectClient(\\'' + c.id + '\\')">';
            html += '<div class="wizard-client-name">' + (c.nom || c.raison_sociale || 'Client') + '</div>';
            html += '<div class="wizard-client-info">' + (c.ville || '') + (c.telephone ? ' • ' + c.telephone : '') + '</div>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    async function selectClient(id) {
        wizardState.data.client_id = id;
        var client = wizardState.clientResults.find(function(c) { return c.id === id; });
        if (client) {
            wizardState.data.client_nom = client.nom || client.raison_sociale;
            // Charger données complètes
            try {
                var res = await fetch('/api/clients/' + id, { credentials: 'include' });
                wizardState.clientData = await res.json();
            } catch(e) { console.error(e); }
        }
        renderClientResults();
        updateWizardNav();
    }

    function renderCardsStep(step) {
        var html = '<div class="wizard-cards">';
        step.options.forEach(function(opt) {
            var selected = wizardState.data[step.field] === opt.value ? 'selected' : '';
            html += '<div class="wizard-card ' + selected + '" onclick="selectCard(\\'' + step.field + '\\', \\'' + opt.value + '\\')">';
            html += '<div class="wizard-card-icon">' + opt.icon + '</div>';
            html += '<div class="wizard-card-label">' + opt.label + '</div>';
            html += '</div>';
        });
        html += '</div>';
        return html;
    }

    function selectCard(field, value) {
        wizardState.data[field] = value;
        renderWizardStep();
    }

    function renderDescriptionStep() {
        var titre = wizardState.data.titre || '';
        var desc = wizardState.data.description || '';
        return '<input type="text" class="wizard-input" id="wizardTitre" placeholder="Titre court (ex: Panne chauffage)" value="' + titre + '">' +
               '<textarea class="wizard-textarea" id="wizardDescription" placeholder="Description détaillée du problème...">' + desc + '</textarea>';
    }

    function renderAddressStep() {
        var html = '';
        if (wizardState.clientData && wizardState.clientData.adresse1) {
            html += '<div class="wizard-subtitle">Adresse du client disponible</div>';
            html += '<button class="wizard-option-btn ' + (wizardState.data.useClientAddress ? 'selected' : '') + '" onclick="useClientAddress(true)">';
            html += '📍 ' + wizardState.clientData.adresse1 + ', ' + (wizardState.clientData.cp || '') + ' ' + (wizardState.clientData.ville || '');
            html += '</button>';
            html += '<button class="wizard-option-btn ' + (wizardState.data.useClientAddress === false ? 'selected' : '') + '" onclick="useClientAddress(false)">✏️ Autre adresse</button>';

            if (wizardState.data.useClientAddress === false) {
                html += renderAddressFields();
            }
        } else {
            html += renderAddressFields();
        }
        return html;
    }

    function renderAddressFields() {
        var a1 = wizardState.data.adresse_ligne1 || '';
        var cp = wizardState.data.code_postal || '';
        var ville = wizardState.data.ville || '';
        return '<input type="text" class="wizard-input" id="wizardAdresse" placeholder="Adresse" value="' + a1 + '">' +
               '<div style="display:flex;gap:12px;">' +
               '<input type="text" class="wizard-input" id="wizardCp" placeholder="Code postal" value="' + cp + '" style="width:120px;">' +
               '<input type="text" class="wizard-input" id="wizardVille" placeholder="Ville" value="' + ville + '" style="flex:1;">' +
               '</div>';
    }

    function useClientAddress(use) {
        wizardState.data.useClientAddress = use;
        if (use && wizardState.clientData) {
            wizardState.data.adresse_ligne1 = wizardState.clientData.adresse1;
            wizardState.data.code_postal = wizardState.clientData.cp;
            wizardState.data.ville = wizardState.clientData.ville;
        }
        renderWizardStep();
    }

    function renderContactStep() {
        var html = '<div class="wizard-subtitle">Le contact sur place est-il différent du client ?</div>';

        // Par défaut, le contact est le client
        if (wizardState.data.contactDifferent === undefined) {
            wizardState.data.contactDifferent = false;
            // Pré-remplir avec les infos du client
            if (wizardState.clientData) {
                wizardState.data.contact_sur_place = wizardState.clientData.contact_name || wizardState.clientData.nom;
                wizardState.data.telephone_contact = wizardState.clientData.telephone;
            }
        }

        html += '<button class="wizard-option-btn ' + (!wizardState.data.contactDifferent ? 'selected' : '') + '" onclick="setContactDifferent(false)">';
        html += '👤 Non, c\\'est le client';
        if (wizardState.clientData) {
            html += '<br><small style="opacity:0.7;">' + (wizardState.clientData.contact_name || wizardState.clientData.nom || '') + '</small>';
        }
        html += '</button>';

        html += '<button class="wizard-option-btn ' + (wizardState.data.contactDifferent ? 'selected' : '') + '" onclick="setContactDifferent(true)">';
        html += '✏️ Oui, autre personne';
        html += '</button>';

        if (wizardState.data.contactDifferent) {
            html += '<div style="margin-top:16px;">';
            var nom = wizardState.data.contact_sur_place || '';
            var tel = wizardState.data.telephone_contact || '';
            html += '<input type="text" class="wizard-input" id="wizardContactNom" placeholder="Nom du contact sur place" value="' + nom + '">';
            html += '<input type="tel" class="wizard-input" id="wizardContactTel" placeholder="Téléphone" value="' + tel + '">';
            html += '</div>';
        }
        return html;
    }

    function setContactDifferent(different) {
        wizardState.data.contactDifferent = different;
        if (!different && wizardState.clientData) {
            // Utiliser le contact du client
            wizardState.data.contact_sur_place = wizardState.clientData.contact_name || wizardState.clientData.nom;
            wizardState.data.telephone_contact = wizardState.clientData.telephone;
        } else if (different) {
            // Vider pour saisie manuelle
            wizardState.data.contact_sur_place = '';
            wizardState.data.telephone_contact = '';
        }
        renderWizardStep();
    }

    function renderScheduleStep() {
        var html = '<div class="wizard-quick-btns">';
        var today = new Date().toISOString().split('T')[0];
        var tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];
        html += '<button class="wizard-quick-btn ' + (wizardState.data.date_intervention === today ? 'selected' : '') + '" onclick="setQuickDate(\\'' + today + '\\')">Aujourd\\'hui</button>';
        html += '<button class="wizard-quick-btn ' + (wizardState.data.date_intervention === tomorrow ? 'selected' : '') + '" onclick="setQuickDate(\\'' + tomorrow + '\\')">Demain</button>';
        html += '<button class="wizard-quick-btn ' + (wizardState.data.date_intervention === 'later' ? 'selected' : '') + '" onclick="setQuickDate(\\'later\\')">À planifier</button>';
        html += '</div>';

        var dateVal = wizardState.data.date_intervention || '';
        var heureVal = wizardState.data.heure_intervention || '09:00';
        var dureeVal = wizardState.data.duree_prevue_minutes || 60;

        html += '<div style="color:white;margin:16px 0 8px;font-size:14px;">Date</div>';
        html += '<input type="date" class="wizard-input" id="wizardDate" value="' + (dateVal === 'later' ? '' : dateVal) + '">';

        html += '<div style="color:white;margin:16px 0 8px;font-size:14px;">Heure de début</div>';
        html += '<div class="wizard-time-btns">';
        ['08:00', '09:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00'].forEach(function(h) {
            var sel = heureVal === h ? 'selected' : '';
            html += '<button class="wizard-time-btn ' + sel + '" onclick="setQuickTime(\\'' + h + '\\')">' + h + '</button>';
        });
        html += '</div>';
        html += '<input type="time" class="wizard-input" id="wizardTime" value="' + heureVal + '" style="margin-top:8px;">';

        html += '<div style="color:white;margin:16px 0 8px;font-size:14px;">Durée estimée</div>';
        html += '<select class="wizard-input" id="wizardDuree" style="background:white;">';
        [30, 60, 90, 120, 180, 240, 480].forEach(function(d) {
            var selected = dureeVal == d ? 'selected' : '';
            var label = d < 60 ? d + ' min' : (d/60) + 'h';
            html += '<option value="' + d + '" ' + selected + '>' + label + '</option>';
        });
        html += '</select>';
        return html;
    }

    function setQuickDate(date) {
        wizardState.data.date_intervention = date;
        if (date === 'later') {
            wizardState.data.date_prevue_debut = null;
        }
        renderWizardStep();
    }

    function setQuickTime(time) {
        wizardState.data.heure_intervention = time;
        var timeInput = document.getElementById('wizardTime');
        if (timeInput) timeInput.value = time;
        renderWizardStep();
    }

    function renderSummaryStep() {
        var d = wizardState.data;
        var html = '<div class="wizard-summary">';
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Client</span><span class="wizard-summary-value">' + (d.client_nom || '-') + '</span></div>';

        // Donneur d'ordre
        var donneurLabel = d.donneurSameAsClient ? 'Le client' : (d.donneur_ordre_nom || '-');
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Demandeur</span><span class="wizard-summary-value">' + donneurLabel + '</span></div>';

        // Qui sera facturé
        var factureLabel = d.factureSameAsClient ? 'Le client' : (d.facture_client_nom || '-');
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Facturé à</span><span class="wizard-summary-value">' + factureLabel + '</span></div>';

        // Référence externe
        if (d.reference_externe) {
            html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Réf. externe</span><span class="wizard-summary-value">' + d.reference_externe + '</span></div>';
        }

        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Type</span><span class="wizard-summary-value">' + (d.type_intervention || 'AUTRE') + '</span></div>';
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Priorité</span><span class="wizard-summary-value">' + (d.priorite || 'NORMAL') + '</span></div>';
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Titre</span><span class="wizard-summary-value">' + (d.titre || '-') + '</span></div>';
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Adresse</span><span class="wizard-summary-value">' + (d.adresse_ligne1 || '-') + ', ' + (d.ville || '') + '</span></div>';
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Contact</span><span class="wizard-summary-value">' + (d.contact_sur_place || '-') + (d.telephone_contact ? ' • ' + d.telephone_contact : '') + '</span></div>';

        // Technicien
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Technicien</span><span class="wizard-summary-value">' + (d.intervenant_nom || 'Non assigné') + '</span></div>';

        // Date et heure
        var dateLabel = 'Non planifiée';
        if (d.date_prevue_debut) {
            var dt = new Date(d.date_prevue_debut);
            dateLabel = dt.toLocaleDateString('fr-FR') + ' à ' + (d.heure_intervention || '09:00');
        }
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Date/Heure</span><span class="wizard-summary-value">' + dateLabel + '</span></div>';

        // Temps de trajet si assigné
        if (d.intervenant_id && d.temps_trajet_estime) {
            html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Trajet</span><span class="wizard-summary-value">~' + d.temps_trajet_estime + ' min</span></div>';
        }

        // Durée
        var dureeLabel = (d.duree_prevue_minutes || 60) < 60 ? (d.duree_prevue_minutes || 60) + ' min' : ((d.duree_prevue_minutes || 60)/60) + 'h';
        html += '<div class="wizard-summary-row"><span class="wizard-summary-label">Durée</span><span class="wizard-summary-value">' + dureeLabel + '</span></div>';

        html += '</div>';
        return html;
    }

    function updateWizardNav() {
        var backBtn = document.getElementById('wizardBack');
        var nextBtn = document.getElementById('wizardNext');
        var step = WIZARD_STEPS[wizardState.currentStep];

        backBtn.style.display = wizardState.currentStep === 0 ? 'none' : 'block';

        if (step.id === 'confirm') {
            nextBtn.textContent = 'Créer l\\'intervention';
        } else {
            nextBtn.textContent = 'Suivant';
        }

        // Validation
        var isValid = validateWizardStep();
        nextBtn.disabled = !isValid;
    }

    function validateWizardStep() {
        var step = WIZARD_STEPS[wizardState.currentStep];
        switch(step.id) {
            case 'client': return !!wizardState.data.client_id;
            case 'donneur':
                // Valide si "même que client" ou si un donneur est sélectionné
                return wizardState.data.donneurSameAsClient === true ||
                       (wizardState.data.donneurSameAsClient === false && wizardState.data.donneur_ordre_id);
            case 'facture':
                // Valide si "même que client" ou si un client facture est sélectionné
                return wizardState.data.factureSameAsClient === true ||
                       (wizardState.data.factureSameAsClient === false && wizardState.data.facture_autre_client_id);
            case 'type': return !!wizardState.data.type_intervention;
            case 'priority': return !!wizardState.data.priorite;
            default: return true;
        }
    }

    function saveWizardStepData() {
        var step = WIZARD_STEPS[wizardState.currentStep];
        switch(step.id) {
            case 'refext':
                var refEl = document.getElementById('wizardRefExt');
                if (refEl) wizardState.data.reference_externe = refEl.value.trim();
                break;
            case 'description':
                var titreEl = document.getElementById('wizardTitre');
                var descEl = document.getElementById('wizardDescription');
                if (titreEl) wizardState.data.titre = titreEl.value;
                if (descEl) wizardState.data.description = descEl.value;
                break;
            case 'address':
                if (!wizardState.data.useClientAddress) {
                    var a = document.getElementById('wizardAdresse');
                    var cp = document.getElementById('wizardCp');
                    var v = document.getElementById('wizardVille');
                    if (a) wizardState.data.adresse_ligne1 = a.value;
                    if (cp) wizardState.data.code_postal = cp.value;
                    if (v) wizardState.data.ville = v.value;
                }
                break;
            case 'contact':
                if (wizardState.data.contactDifferent) {
                    var nom = document.getElementById('wizardContactNom');
                    var tel = document.getElementById('wizardContactTel');
                    if (nom) wizardState.data.contact_sur_place = nom.value;
                    if (tel) wizardState.data.telephone_contact = tel.value;
                }
                break;
            case 'schedule':
                var dateEl = document.getElementById('wizardDate');
                var timeEl = document.getElementById('wizardTime');
                var dureeEl = document.getElementById('wizardDuree');
                if (dateEl && dateEl.value) {
                    var time = timeEl ? timeEl.value : '09:00';
                    wizardState.data.date_prevue_debut = dateEl.value + 'T' + time + ':00';
                    wizardState.data.heure_intervention = time;
                } else {
                    wizardState.data.date_prevue_debut = null;
                }
                if (dureeEl) wizardState.data.duree_prevue_minutes = parseInt(dureeEl.value);
                break;
        }
    }

    async function wizardNext() {
        saveWizardStepData();

        if (wizardState.currentStep === WIZARD_STEPS.length - 1) {
            await submitWizard();
            return;
        }

        wizardState.currentStep++;
        renderWizardStep();
    }

    function wizardBack() {
        if (wizardState.currentStep > 0) {
            saveWizardStepData();
            wizardState.currentStep--;
            renderWizardStep();
        }
    }

    async function submitWizard() {
        var btn = document.getElementById('wizardNext');
        btn.disabled = true;
        btn.innerHTML = '<span class="wizard-loading"></span>';

        var d = wizardState.data;
        var payload = {
            client_id: d.client_id,
            // Donneur d'ordre : si même que client, on ne met pas de donneur_ordre_id
            donneur_ordre_id: d.donneurSameAsClient ? null : (d.donneur_ordre_id || null),
            // Référence externe
            reference_externe: d.reference_externe || null,
            // Technicien assigné
            intervenant_id: d.intervenant_id || null,
            // Temps de trajet estimé
            temps_trajet_estime: d.temps_trajet_estime || null,
            type_intervention: d.type_intervention || 'AUTRE',
            priorite: d.priorite || 'NORMAL',
            titre: d.titre || '',
            description: d.description || '',
            adresse_ligne1: d.adresse_ligne1 || '',
            code_postal: d.code_postal || '',
            ville: d.ville || '',
            contact_sur_place: d.contact_sur_place || '',
            telephone_contact: d.telephone_contact || '',
            date_prevue_debut: d.date_prevue_debut || null,
            duree_prevue_minutes: d.duree_prevue_minutes || null,
            statut: d.intervenant_id ? 'PLANIFIEE' : 'DRAFT'  // Si technicien assigné, passer en PLANIFIEE
        };

        // Ajouter note si client facturé différent
        if (!d.factureSameAsClient && d.facture_client_nom) {
            payload.notes_internes = (payload.notes_internes || '') + '\\n[Facturer à: ' + d.facture_client_nom + ']';
        }

        try {
            var res = await fetch('/api/interventions', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                var result = await res.json();
                closeWizard();
                window.location.href = '/ui/interventions/' + result.id;
            } else {
                var err = await res.json();
                alert('Erreur: ' + (err.detail || 'Création échouée'));
                btn.disabled = false;
                btn.textContent = 'Créer l\\'intervention';
            }
        } catch(e) {
            alert('Erreur: ' + e.message);
            btn.disabled = false;
            btn.textContent = 'Créer l\\'intervention';
        }
    }

    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
        var wizard = document.getElementById('interventionWizard');
        if (!wizard || !wizard.classList.contains('open')) return;

        if (e.key === 'Escape') {
            closeWizard();
        } else if (e.key === 'Enter' && !e.shiftKey && e.target.tagName !== 'TEXTAREA') {
            e.preventDefault();
            var nextBtn = document.getElementById('wizardNext');
            if (nextBtn && !nextBtn.disabled) wizardNext();
        }
    });
    </script>
    '''


def generate_list_with_bulk_actions(
    module_name: str,
    module_display_name: str,
    table_headers: str,
    table_rows: str,
    has_status: bool = False,
    status_options: str = ""
) -> str:
    """Génère une liste avec actions en masse."""

    # Toujours afficher les actions bulk (au moins le bouton supprimer)
    if has_status:
        # Avec statut : sélecteur de statut + bouton appliquer + bouton supprimer
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
    else:
        # Sans statut : juste le bouton supprimer
        bulk_actions_html = f'''
        <div class="bulk-actions" id="bulk-actions" style="display: none;">
            <span class="bulk-count">0 sélectionné(s)</span>
            <button class="btn btn-danger" onclick="deleteBulkItems()">Supprimer</button>
        </div>
        '''

    # Bouton spécial wizard pour interventions
    is_interventions = module_name.lower() == 'interventions'
    if is_interventions:
        nouveau_btn = '<button class="btn btn-primary" onclick="openInterventionWizard()">+ Nouveau</button>'
        wizard_html = generate_intervention_wizard()
    else:
        nouveau_btn = f'<a href="/ui/{module_name}/nouveau" class="btn btn-primary">+ Nouveau</a>'
        wizard_html = ''

    return f'''
    <div class="list-container">
        <div class="list-toolbar">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Rechercher..." class="form-control">
            </div>
            {nouveau_btn}
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
        function handleRowClick(event, id, url) {{
            // Ne pas naviguer si on clique sur une checkbox ou un bouton
            if (event.target.type === 'checkbox' || event.target.tagName === 'BUTTON' || event.target.closest('button')) {{
                return;
            }}
            window.location.href = url;
        }}

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

        // Récupérer le token depuis l'URL
        function getToken() {{
            const params = new URLSearchParams(window.location.search);
            return params.get('token') || '';
        }}

        async function applyBulkStatus() {{
            const status = document.getElementById('bulk-status').value;
            if (!status) return alert('Veuillez sélectionner un statut');

            const ids = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => cb.dataset.id);
            if (ids.length === 0) return alert('Aucun élément sélectionné');

            try {{
                const response = await fetch('/api/{module_name}/bulk', {{
                    method: 'PATCH',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + getToken()
                    }},
                    body: JSON.stringify({{ ids, updates: {{ statut: status }} }})
                }});
                if (response.ok) {{
                    location.reload();
                }} else {{
                    const err = await response.json();
                    alert('Erreur: ' + (err.detail || 'Mise à jour échouée'));
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        async function deleteBulkItems() {{
            const ids = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => cb.dataset.id);
            if (ids.length === 0) return alert('Aucun élément sélectionné');

            if (!confirm('Supprimer ' + ids.length + ' élément(s) ?')) return;

            try {{
                const response = await fetch('/api/{module_name}/bulk', {{
                    method: 'DELETE',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + getToken()
                    }},
                    body: JSON.stringify({{ ids }})
                }});
                if (response.ok) {{
                    location.reload();
                }} else {{
                    const err = await response.json();
                    alert('Erreur: ' + (err.detail || 'Suppression échouée'));
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}
    </script>
    {wizard_html}
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

    # Modules JSON for Command Palette
    import json as json_module
    modules_for_palette = [
        {"nom": m.get("nom", ""), "icone": get_icon(m.get("icone", "file")), "menu": m.get("menu", "Général")}
        for m in modules
    ]
    modules_json = json_module.dumps(modules_for_palette, ensure_ascii=False)

    return f'''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - AZALPLUS</title>
    <!-- Error Reporter INLINE - capture immédiate avant tout autre script -->
    <script>
    (function(){{
        'use strict';
        var REPORT_ENDPOINT='/guardian/frontend-error';
        var errorCount=0;
        setInterval(function(){{errorCount=0;}},60000);
        function reportError(d){{
            if(errorCount>=10)return;
            errorCount++;
            fetch(REPORT_ENDPOINT,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}})
            .then(function(r){{return r.json();}})
            .then(function(data){{
                if(data&&data.action==='reload'){{
                    console.log('[Guardian] Correction appliquée, rechargement...');
                    setTimeout(function(){{location.reload(true);}},500);
                }}
            }}).catch(function(){{}});
        }}
        window.onerror=function(message,source,line,column,error){{
            reportError({{
                error_type:'js_error',
                message:String(message),
                url:window.location.href,
                source:source,
                line:line,
                column:column,
                stack:error?error.stack:null,
                user_agent:navigator.userAgent
            }});
            return false;
        }};
        window.onunhandledrejection=function(event){{
            reportError({{
                error_type:'promise_rejection',
                message:String(event.reason),
                url:window.location.href,
                source:null,
                line:null,
                column:null,
                stack:event.reason&&event.reason.stack?event.reason.stack:null,
                user_agent:navigator.userAgent
            }});
        }};
        console.debug('[ErrorReporter] Inline error reporting initialized');
    }})();
    </script>
    <script src="/assets/js/error-reporter.js"></script>
    <!-- Google Fonts - Plus Jakarta Sans -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- CSS genere depuis theme.yml -->
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
        if (notifPanelOpen && typeof loadNotifications === 'function') {{
            loadNotifications();
        }}
    }}
    // Fermer le panel si on clique ailleurs
    document.addEventListener('click', function(e) {{
        if (!notifPanelOpen) return;
        var panel = document.getElementById('notif-panel');
        var bell = document.getElementById('notif-bell');
        if (panel && bell && !panel.contains(e.target) && !bell.contains(e.target)) {{
            panel.style.display = 'none';
            notifPanelOpen = false;
        }}
    }});
    </script>
</head>
<body>
    <div class="app-layout">
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="sidebar-logo">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="sidebar-logo-icon">
                    <circle cx="256" cy="256" r="256" fill="#3454D1"/>
                    <circle cx="380" cy="120" r="24" fill="#6B9FFF"/>
                    <text x="200" y="360" font-family="Inter, Montserrat, Arial, sans-serif" font-weight="800" font-size="280" fill="#FFFFFF">A</text>
                    <text x="340" y="280" font-family="Inter, Montserrat, Arial, sans-serif" font-weight="700" font-size="140" fill="#FFFFFF">+</text>
                </svg>
                <span>AZALPLUS</span>
            </div>

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

            <!-- Toggle sidebar -->
            <div class="sidebar-toggle" onclick="toggleSidebar()" title="Réduire/Agrandir le menu">
                <span id="sidebar-toggle-icon">◀</span>
            </div>

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
                    <div class="add-dropdown">
                        <button class="btn btn-primary" onclick="toggleAddDropdown(event)">
                            + Ajouter <span style="margin-left:4px;font-size:10px;">▼</span>
                        </button>
                        <div class="add-dropdown-content" id="add-dropdown">
                            <div class="add-dropdown-section" id="add-current-section" style="display:none">
                                <div class="add-dropdown-title">Page actuelle</div>
                                <a href="#" class="add-dropdown-item" id="add-current-link">
                                    <span id="add-current-icon">📄</span>
                                    <span>Nouveau <span id="add-current-name"></span></span>
                                </a>
                            </div>
                            <div class="add-dropdown-section">
                                <div class="add-dropdown-title">Création rapide</div>
                                <a href="/ui/Clients/nouveau" class="add-dropdown-item">👤 Nouveau Client</a>
                                <a href="/ui/Factures/nouveau" class="add-dropdown-item">🧾 Nouvelle Facture</a>
                                <a href="/ui/Devis/nouveau" class="add-dropdown-item">📝 Nouveau Devis</a>
                                <a href="/ui/Produits/nouveau" class="add-dropdown-item">📦 Nouveau Produit</a>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            <main class="main-content">
                <h1 class="page-title mb-4">{title}</h1>
                {content}
            </main>
        </div>
    </div>

    <style>
        /* === NAVIGATION AMÉLIORÉE === */

        /* Indicateur page active */
        .nav-item.active {{
            background: rgba(255,255,255,0.15);
            border-left: 3px solid white;
            padding-left: 13px;
        }}

        /* Sidebar collapsible */
        .sidebar.collapsed {{
            width: 60px;
        }}
        .sidebar.collapsed .nav-item span:last-child,
        .sidebar.collapsed .nav-title,
        .sidebar.collapsed .user-name,
        .sidebar.collapsed .user-email,
        .sidebar.collapsed .sidebar-logo span {{
            display: none;
        }}
        .sidebar.collapsed .nav-item {{
            justify-content: center;
            padding: 10px;
        }}
        .sidebar.collapsed .nav-icon {{
            margin: 0;
        }}
        .app-layout.sidebar-collapsed .main-wrapper {{
            margin-left: 60px;
        }}
        .sidebar-toggle {{
            position: absolute;
            bottom: 80px;
            right: -12px;
            width: 24px;
            height: 24px;
            background: var(--primary, #714B67);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: white;
            font-size: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            z-index: 1001;
            transition: transform 0.15s;
        }}
        .sidebar-toggle:hover {{
            transform: scale(1.1);
        }}

        /* Dropdown + Ajouter */
        .add-dropdown {{
            position: relative;
            display: inline-block;
        }}
        .add-dropdown-content {{
            display: none;
            position: absolute;
            top: 100%;
            right: 0;
            background: white;
            border-radius: 8px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            min-width: 220px;
            z-index: 1000;
            margin-top: 8px;
            overflow: hidden;
        }}
        .add-dropdown-content.open {{
            display: block;
        }}
        .add-dropdown-section {{
            padding: 8px 0;
            border-bottom: 1px solid var(--gray-100, #f3f4f6);
        }}
        .add-dropdown-section:last-child {{
            border-bottom: none;
        }}
        .add-dropdown-title {{
            padding: 4px 16px;
            font-size: 11px;
            color: var(--gray-500, #6b7280);
            text-transform: uppercase;
            font-weight: 600;
        }}
        .add-dropdown-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 16px;
            color: var(--gray-700, #374151);
            text-decoration: none;
            font-size: 14px;
        }}
        .add-dropdown-item:hover {{
            background: var(--gray-50, #f9fafb);
        }}

        /* Command Palette */
        .command-palette-overlay {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.5);
            z-index: 10000;
            align-items: flex-start;
            justify-content: center;
            padding-top: 15vh;
        }}
        .command-palette-overlay.open {{
            display: flex;
        }}
        .command-palette {{
            background: white;
            border-radius: 12px;
            width: 560px;
            max-width: 90vw;
            max-height: 400px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .command-input {{
            width: 100%;
            padding: 16px 20px;
            border: none;
            border-bottom: 1px solid var(--gray-200, #e5e7eb);
            font-size: 16px;
            outline: none;
        }}
        .command-input::placeholder {{
            color: var(--gray-400, #9ca3af);
        }}
        .command-results {{
            max-height: 320px;
            overflow-y: auto;
        }}
        .command-section-title {{
            padding: 8px 20px 4px;
            font-size: 11px;
            color: var(--gray-500, #6b7280);
            text-transform: uppercase;
            font-weight: 600;
        }}
        .command-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 20px;
            cursor: pointer;
        }}
        .command-item:hover, .command-item.selected {{
            background: var(--gray-100, #f3f4f6);
        }}
        .command-item-icon {{
            font-size: 18px;
            width: 24px;
            text-align: center;
        }}
        .command-item-text {{
            flex: 1;
        }}
        .command-item-name {{
            font-weight: 500;
            color: var(--gray-800, #1f2937);
        }}
        .command-item-hint {{
            font-size: 12px;
            color: var(--gray-500, #6b7280);
        }}
        .command-shortcut {{
            margin-left: auto;
            font-size: 11px;
            color: var(--gray-400, #9ca3af);
            background: var(--gray-100, #f3f4f6);
            padding: 2px 6px;
            border-radius: 4px;
        }}
        .command-empty {{
            padding: 24px 20px;
            text-align: center;
            color: var(--gray-500, #6b7280);
        }}
        .command-hint {{
            padding: 8px 20px;
            font-size: 12px;
            color: var(--gray-400, #9ca3af);
            border-top: 1px solid var(--gray-100, #f3f4f6);
            display: flex;
            gap: 16px;
        }}
        .command-hint kbd {{
            background: var(--gray-100, #f3f4f6);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: inherit;
        }}

        /* === STYLES GLOBAUX BOUTON CREATION INLINE === */
        .select-with-create {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .select-with-create select {{
            flex: 1;
        }}
        .btn-create-inline {{
            width: 36px;
            height: 36px;
            min-width: 36px;
            border-radius: 6px;
            border: 2px solid #3454D1;
            background: #3454D1;
            color: #ffffff;
            font-size: 20px;
            font-weight: bold;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
            padding: 0;
            box-sizing: border-box;
        }}
        .btn-create-inline:hover {{
            background: #2a45b0;
            border-color: #2a45b0;
        }}

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

        /* ============================================
           DATETIME PICKER GLOBAL
           ============================================ */
        .datetime-picker-wrapper {{
            position: relative;
            display: flex;
            align-items: center;
        }}
        .datetime-picker-wrapper .datetime-picker {{
            padding-right: 40px;
            cursor: pointer;
        }}
        .datetime-picker-icon {{
            position: absolute;
            right: 10px;
            cursor: pointer;
            font-size: 18px;
        }}
        .datetime-modal {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        }}
        .datetime-modal-content {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 380px;
            max-height: 90vh;
            overflow: hidden;
        }}
        .datetime-modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid #e5e7eb;
            background: #dbeafe;
        }}
        .datetime-modal-header h3 {{
            margin: 0;
            font-size: 16px;
            font-weight: 600;
            color: #1e40af;
        }}
        .datetime-modal-close {{
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #1e40af;
        }}
        .datetime-calendar {{
            padding: 16px;
            background: #ffffff;
        }}
        .calendar-nav {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .calendar-nav button {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 6px 12px;
            cursor: pointer;
            font-size: 14px;
            color: #374151;
        }}
        .calendar-nav button:hover {{
            background: #f3f4f6;
            color: #1f2937;
        }}
        .calendar-nav span {{
            font-weight: 600;
            font-size: 15px;
            color: #1f2937;
        }}
        .calendar-grid {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 4px;
        }}
        .calendar-day-header {{
            text-align: center;
            font-size: 12px;
            font-weight: 600;
            color: #6b7280;
            padding: 8px 0;
        }}
        .calendar-day {{
            aspect-ratio: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.15s;
            color: #1f2937;
            background: #ffffff;
        }}
        .calendar-day:hover {{
            background: #e5e7eb;
            color: #1f2937;
        }}
        .calendar-day.today {{
            border: 2px solid #3454D1;
            color: #3454D1;
            font-weight: 600;
        }}
        .calendar-day.selected {{
            background: #3454D1;
            color: #ffffff !important;
        }}
        .calendar-day.other-month {{
            color: #9ca3af;
            background: #f9fafb;
        }}
        .calendar-day.disabled {{
            color: #d1d5db;
            background: #f3f4f6;
            cursor: not-allowed;
        }}
        .time-slots {{
            padding: 16px;
            border-top: 1px solid #e5e7eb;
            max-height: 200px;
            overflow-y: auto;
            background: #ffffff;
        }}
        .time-slots-title {{
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 12px;
            color: #1e40af;
        }}
        .time-slots-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }}
        .time-slot {{
            padding: 8px;
            text-align: center;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.15s;
            background: #f0f9ff;
            color: #1e40af;
        }}
        .time-slot:hover {{
            background: #dbeafe;
            border-color: #3454D1;
            color: #1e40af;
        }}
        .time-slot.selected {{
            background: #3454D1;
            color: #ffffff !important;
            border-color: #3454D1;
        }}
        .time-slot.unavailable {{
            background: #fee2e2;
            color: #991b1b;
            cursor: not-allowed;
            border-color: #fecaca;
        }}
        .time-slot.unavailable:hover {{
            background: #fee2e2;
            border-color: #fecaca;
            color: #991b1b;
        }}
        .datetime-modal-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            padding: 16px;
            border-top: 1px solid #e5e7eb;
            background: #f0f9ff;
        }}
        .technician-info {{
            padding: 12px 16px;
            background: #dbeafe;
            border-bottom: 1px solid #bfdbfe;
            font-size: 13px;
            color: #1e40af;
        }}
        .loading-slots {{
            text-align: center;
            padding: 20px;
            color: #374151;
        }}
    </style>

    <script>
    // ==========================================================================
    // Token d'authentification global
    // ==========================================================================
    function getAuthToken() {{
        const params = new URLSearchParams(window.location.search);
        return params.get('token') || '';
    }}
    const AUTH_TOKEN = getAuthToken();

    // ==========================================================================
    // DATETIME PICKER GLOBAL
    // ==========================================================================
    let dtPickerState = {{
        inputElement: null,
        mode: 'datetime',
        selectedDate: null,
        selectedTime: null,
        currentMonth: new Date(),
        technicianId: null,
        unavailableSlots: []
    }};

    function openDateTimePicker(inputElement, mode) {{
        dtPickerState.inputElement = inputElement;
        dtPickerState.mode = mode;
        dtPickerState.selectedDate = null;
        dtPickerState.selectedTime = null;
        dtPickerState.currentMonth = new Date();
        dtPickerState.unavailableSlots = [];

        // Chercher le technicien sélectionné (si existe)
        const techSelect = document.getElementById('intervenant_id');
        dtPickerState.technicianId = techSelect ? techSelect.value : null;

        renderDateTimePicker();
    }}

    function renderDateTimePicker() {{
        // Supprimer modal existant
        const existing = document.getElementById('datetime-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'datetime-modal';
        modal.className = 'datetime-modal';
        modal.onclick = (e) => {{ if (e.target === modal) closeDateTimePicker(); }};

        const title = dtPickerState.mode === 'date' ? 'Sélectionner une date' : 'Sélectionner date et heure';

        modal.innerHTML = `
            <div class="datetime-modal-content">
                <div class="datetime-modal-header">
                    <h3>${{title}}</h3>
                    <button class="datetime-modal-close" onclick="closeDateTimePicker()">&times;</button>
                </div>
                ${{dtPickerState.technicianId ? '<div class="technician-info" id="tech-info">Chargement disponibilités...</div>' : ''}}
                <div class="datetime-calendar">
                    <div class="calendar-nav">
                        <button onclick="navigateMonth(-1)">&lt; Préc.</button>
                        <span id="calendar-month-label"></span>
                        <button onclick="navigateMonth(1)">Suiv. &gt;</button>
                    </div>
                    <div class="calendar-grid" id="calendar-grid"></div>
                </div>
                ${{dtPickerState.mode === 'datetime' ? `
                <div class="time-slots" id="time-slots-container" style="display:none;">
                    <div class="time-slots-title">Créneaux disponibles (1h)</div>
                    <div class="time-slots-grid" id="time-slots-grid"></div>
                </div>
                ` : ''}}
                <div class="datetime-modal-footer">
                    <button class="btn btn-secondary" onclick="closeDateTimePicker()">Annuler</button>
                    <button class="btn btn-primary" onclick="confirmDateTime()">Valider</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        renderCalendar();

        // Charger les disponibilités si technicien sélectionné
        if (dtPickerState.technicianId) {{
            loadTechnicianAvailability();
        }}
    }}

    function renderCalendar() {{
        const grid = document.getElementById('calendar-grid');
        const label = document.getElementById('calendar-month-label');
        const date = dtPickerState.currentMonth;
        const today = new Date();
        today.setHours(0,0,0,0);

        const months = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
        label.textContent = `${{months[date.getMonth()]}} ${{date.getFullYear()}}`;

        const days = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
        let html = days.map(d => `<div class="calendar-day-header">${{d}}</div>`).join('');

        const firstDay = new Date(date.getFullYear(), date.getMonth(), 1);
        let startDay = firstDay.getDay() - 1;
        if (startDay < 0) startDay = 6;

        const lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
        const prevLastDay = new Date(date.getFullYear(), date.getMonth(), 0).getDate();

        // Jours du mois précédent
        for (let i = startDay - 1; i >= 0; i--) {{
            html += `<div class="calendar-day other-month disabled">${{prevLastDay - i}}</div>`;
        }}

        // Jours du mois actuel
        for (let d = 1; d <= lastDay; d++) {{
            const thisDate = new Date(date.getFullYear(), date.getMonth(), d);
            const isToday = thisDate.getTime() === today.getTime();
            const isPast = thisDate < today;
            const isSelected = dtPickerState.selectedDate &&
                               dtPickerState.selectedDate.getTime() === thisDate.getTime();

            let classes = 'calendar-day';
            if (isToday) classes += ' today';
            if (isPast) classes += ' disabled';
            if (isSelected) classes += ' selected';

            const onclick = isPast ? '' : `onclick="selectDate(${{date.getFullYear()}}, ${{date.getMonth()}}, ${{d}})"`;
            html += `<div class="${{classes}}" ${{onclick}}>${{d}}</div>`;
        }}

        // Jours du mois suivant
        const remaining = 42 - (startDay + lastDay);
        for (let i = 1; i <= remaining; i++) {{
            html += `<div class="calendar-day other-month disabled">${{i}}</div>`;
        }}

        grid.innerHTML = html;
    }}

    function navigateMonth(delta) {{
        dtPickerState.currentMonth.setMonth(dtPickerState.currentMonth.getMonth() + delta);
        renderCalendar();
    }}

    function selectDate(year, month, day) {{
        dtPickerState.selectedDate = new Date(year, month, day);
        renderCalendar();

        if (dtPickerState.mode === 'datetime') {{
            document.getElementById('time-slots-container').style.display = 'block';
            renderTimeSlots();
        }}
    }}

    async function loadTechnicianAvailability() {{
        const techInfo = document.getElementById('tech-info');
        if (!dtPickerState.technicianId) return;

        try {{
            const response = await fetch(`/api/v1/utilisateurs/${{dtPickerState.technicianId}}`, {{
                credentials: 'include'
            }});
            if (response.ok) {{
                const tech = await response.json();
                techInfo.textContent = `Technicien: ${{tech.nom || tech.name || tech.email}}`;

                // Charger les interventions planifiées
                const intResponse = await fetch(`/api/v1/interventions?intervenant_id=${{dtPickerState.technicianId}}&statut=PLANIFIEE,EN_COURS,SUR_SITE`, {{
                    credentials: 'include'
                }});
                if (intResponse.ok) {{
                    const interventions = await intResponse.json();
                    dtPickerState.unavailableSlots = (interventions.items || interventions || []).map(i => ({{
                        start: new Date(i.date_prevue_debut),
                        end: new Date(i.date_prevue_fin || new Date(new Date(i.date_prevue_debut).getTime() + 60*60*1000))
                    }}));
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement technicien:', e);
            techInfo.textContent = 'Technicien sélectionné';
        }}
    }}

    function renderTimeSlots() {{
        const grid = document.getElementById('time-slots-grid');
        if (!dtPickerState.selectedDate) {{
            grid.innerHTML = '<p>Sélectionnez une date</p>';
            return;
        }}

        // Créneaux de 8h à 18h par tranche de 1h
        const slots = [];
        for (let h = 8; h <= 17; h++) {{
            slots.push(`${{h.toString().padStart(2, '0')}}:00`);
        }}

        let html = '';
        for (const slot of slots) {{
            const [hours, minutes] = slot.split(':').map(Number);
            const slotDate = new Date(dtPickerState.selectedDate);
            slotDate.setHours(hours, minutes, 0, 0);
            const slotEnd = new Date(slotDate.getTime() + 60*60*1000); // +1h

            // Vérifier si le créneau est disponible
            const isUnavailable = dtPickerState.unavailableSlots.some(u => {{
                return (slotDate >= u.start && slotDate < u.end) ||
                       (slotEnd > u.start && slotEnd <= u.end) ||
                       (slotDate <= u.start && slotEnd >= u.end);
            }});

            const isSelected = dtPickerState.selectedTime === slot;
            const isPast = slotDate < new Date();

            let classes = 'time-slot';
            if (isUnavailable || isPast) classes += ' unavailable';
            if (isSelected) classes += ' selected';

            const onclick = (isUnavailable || isPast) ? '' : `onclick="selectTime('${{slot}}')"`;
            const label = isUnavailable ? `${{slot}} (occupé)` : slot;
            html += `<div class="${{classes}}" ${{onclick}}>${{label}}</div>`;
        }}

        grid.innerHTML = html;
    }}

    function selectTime(time) {{
        dtPickerState.selectedTime = time;
        renderTimeSlots();
    }}

    function confirmDateTime() {{
        if (!dtPickerState.selectedDate) {{
            alert('Veuillez sélectionner une date');
            return;
        }}

        if (dtPickerState.mode === 'datetime' && !dtPickerState.selectedTime) {{
            alert('Veuillez sélectionner un créneau horaire');
            return;
        }}

        let value;
        const d = dtPickerState.selectedDate;
        const dateStr = `${{d.getFullYear()}}-${{(d.getMonth()+1).toString().padStart(2,'0')}}-${{d.getDate().toString().padStart(2,'0')}}`;

        if (dtPickerState.mode === 'datetime') {{
            value = `${{dateStr}}T${{dtPickerState.selectedTime}}`;
            dtPickerState.inputElement.value = `${{d.getDate().toString().padStart(2,'0')}}/${{(d.getMonth()+1).toString().padStart(2,'0')}}/${{d.getFullYear()}} ${{dtPickerState.selectedTime}}`;
        }} else {{
            value = dateStr;
            dtPickerState.inputElement.value = `${{d.getDate().toString().padStart(2,'0')}}/${{(d.getMonth()+1).toString().padStart(2,'0')}}/${{d.getFullYear()}}`;
        }}

        // Stocker la valeur ISO dans un attribut data
        dtPickerState.inputElement.dataset.isoValue = value;

        closeDateTimePicker();
    }}

    function closeDateTimePicker() {{
        const modal = document.getElementById('datetime-modal');
        if (modal) modal.remove();
    }}

    // ==========================================================================
    // Notifications - Chargement des données
    // ==========================================================================

    async function loadNotifications() {{
        const list = document.getElementById('notif-list');
        const countBadge = document.getElementById('notif-count');

        try {{
            const response = await fetch('/api/notifications?limit=10&order_by=created_at&order_dir=desc', {{
                credentials: 'include',
                headers: {{ 'Authorization': 'Bearer ' + AUTH_TOKEN }}
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
                headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + AUTH_TOKEN }},
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
                credentials: 'include',
                headers: {{ 'Authorization': 'Bearer ' + AUTH_TOKEN }}
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
                    credentials: 'include',
                    headers: {{ 'Authorization': 'Bearer ' + AUTH_TOKEN }}
                }});
                if (searchRes.ok) {{
                    const searchData = await searchRes.json();
                    const favori = searchData.items && searchData.items.find(f =>
                        f.module === module && f.record_id === recordId
                    );
                    if (favori) {{
                        await fetch(`/api/favoris/${{favori.id}}`, {{
                            method: 'DELETE',
                            credentials: 'include',
                            headers: {{ 'Authorization': 'Bearer ' + AUTH_TOKEN }}
                        }});
                    }}
                }}
            }} else {{
                // Ajouter le favori
                await fetch('/api/favoris', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + AUTH_TOKEN }},
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
                credentials: 'include',
                headers: {{ 'Authorization': 'Bearer ' + AUTH_TOKEN }}
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
            const token = localStorage.getItem('access_token');
            if (!token) return; // Pas de tracking si pas connecté

            // Envoyer la visite au backend
            await fetch('/api/recent/track', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                }},
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

    <!-- Command Palette (Ctrl+K) -->
    <div id="command-palette" class="command-palette-overlay" onclick="closeCommandPalette(event)">
        <div class="command-palette" onclick="event.stopPropagation()">
            <input type="text" class="command-input" placeholder="Rechercher un module ou une action..." id="command-input" autocomplete="off">
            <div class="command-results" id="command-results"></div>
            <div class="command-hint">
                <span><kbd>↑↓</kbd> naviguer</span>
                <span><kbd>Enter</kbd> ouvrir</span>
                <span><kbd>Esc</kbd> fermer</span>
            </div>
        </div>
    </div>

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

        // Fallback pour HTTP (clipboard API ne marche qu'en HTTPS)
        function fallbackCopy(text) {{
            var textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            textarea.style.top = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {{
                var success = document.execCommand('copy');
                document.body.removeChild(textarea);
                return success;
            }} catch (e) {{
                document.body.removeChild(textarea);
                return false;
            }}
        }}

        // Essayer clipboard API d'abord, sinon fallback
        if (navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(mobileUrl).then(function() {{
                showToast('Lien copié dans le presse-papier !', 'success');
            }}).catch(function() {{
                if (fallbackCopy(mobileUrl)) {{
                    showToast('Lien copié !', 'success');
                }} else {{
                    prompt('Copiez ce lien manuellement:', mobileUrl);
                }}
            }});
        }} else {{
            if (fallbackCopy(mobileUrl)) {{
                showToast('Lien copié !', 'success');
            }} else {{
                prompt('Copiez ce lien manuellement:', mobileUrl);
            }}
        }}
    }}

    // === NAVIGATION AMÉLIORÉE ===

    // Liste des modules pour la Command Palette
    var ALL_MODULES = {modules_json};

    // --- 1. Indicateur page active ---
    function highlightActiveNavItem() {{
        var path = window.location.pathname;
        var parts = path.split('/');
        var moduleName = parts[2] || '';

        document.querySelectorAll('.nav-item').forEach(function(item) {{
            var href = item.getAttribute('href') || '';
            var hrefParts = href.split('/');
            var itemModule = hrefParts[2] || '';

            // Dashboard
            if (path === '/ui/' && href === '/ui/') {{
                item.classList.add('active');
            }}
            // Module match
            else if (moduleName && itemModule && moduleName.toLowerCase() === itemModule.toLowerCase()) {{
                item.classList.add('active');
            }}
        }});
    }}

    // --- 2. Sidebar collapsible ---
    function toggleSidebar() {{
        var layout = document.querySelector('.app-layout');
        var sidebar = document.querySelector('.sidebar');
        var icon = document.getElementById('sidebar-toggle-icon');

        var isCollapsed = sidebar.classList.toggle('collapsed');
        layout.classList.toggle('sidebar-collapsed', isCollapsed);
        icon.textContent = isCollapsed ? '▶' : '◀';

        localStorage.setItem('sidebar_collapsed', isCollapsed ? '1' : '0');
    }}

    function restoreSidebarState() {{
        if (localStorage.getItem('sidebar_collapsed') === '1') {{
            var sidebar = document.querySelector('.sidebar');
            var layout = document.querySelector('.app-layout');
            var icon = document.getElementById('sidebar-toggle-icon');
            if (sidebar) sidebar.classList.add('collapsed');
            if (layout) layout.classList.add('sidebar-collapsed');
            if (icon) icon.textContent = '▶';
        }}
    }}

    // --- 3. Dropdown + Ajouter ---
    var addDropdownOpen = false;

    function toggleAddDropdown(event) {{
        event.stopPropagation();
        addDropdownOpen = !addDropdownOpen;
        document.getElementById('add-dropdown').classList.toggle('open', addDropdownOpen);

        // Détecter module actuel
        var path = window.location.pathname;
        var parts = path.split('/');
        if (parts[1] === 'ui' && parts[2] && parts[2] !== 'search' && parts[2] !== 'parametres') {{
            var moduleName = parts[2];
            var currentSection = document.getElementById('add-current-section');
            var currentLink = document.getElementById('add-current-link');
            var currentName = document.getElementById('add-current-name');
            if (currentSection && currentLink && currentName) {{
                currentSection.style.display = 'block';
                currentLink.href = '/ui/' + moduleName + '/nouveau';
                currentName.textContent = moduleName;
            }}
        }}
    }}

    // --- 4. Command Palette (Ctrl+K) ---
    var commandPaletteOpen = false;
    var commandSelectedIndex = 0;
    var commandItems = [];

    function openCommandPalette() {{
        commandPaletteOpen = true;
        document.getElementById('command-palette').classList.add('open');
        var input = document.getElementById('command-input');
        input.value = '';
        input.focus();
        renderCommandResults('');
    }}

    function closeCommandPalette(event) {{
        if (event) event.stopPropagation();
        commandPaletteOpen = false;
        document.getElementById('command-palette').classList.remove('open');
    }}

    function renderCommandResults(query) {{
        var results = document.getElementById('command-results');
        var q = query.toLowerCase().trim();

        var filtered = ALL_MODULES.filter(function(m) {{
            return m.nom.toLowerCase().includes(q) || m.menu.toLowerCase().includes(q);
        }}).slice(0, 10);

        commandItems = filtered;
        commandSelectedIndex = 0;

        if (filtered.length === 0) {{
            results.innerHTML = '<div class="command-empty">Aucun résultat pour "' + query + '"</div>';
            return;
        }}

        // Grouper par menu
        var byMenu = {{}};
        filtered.forEach(function(m) {{
            if (!byMenu[m.menu]) byMenu[m.menu] = [];
            byMenu[m.menu].push(m);
        }});

        var html = '';
        var idx = 0;
        for (var menu in byMenu) {{
            html += '<div class="command-section-title">' + menu + '</div>';
            byMenu[menu].forEach(function(m) {{
                html += '<div class="command-item ' + (idx === 0 ? 'selected' : '') + '" data-index="' + idx + '" data-module="' + m.nom + '">' +
                    '<span class="command-item-icon">' + m.icone + '</span>' +
                    '<div class="command-item-text">' +
                        '<div class="command-item-name">' + m.nom + '</div>' +
                    '</div>' +
                    '<span class="command-shortcut">Ouvrir</span>' +
                '</div>';
                idx++;
            }});
        }}

        results.innerHTML = html;

        // Event listeners pour les items
        results.querySelectorAll('.command-item').forEach(function(item) {{
            item.addEventListener('click', function() {{
                var mod = this.dataset.module;
                if (mod) window.location.href = '/ui/' + mod;
            }});
        }});
    }}

    function updateCommandSelection() {{
        document.querySelectorAll('.command-item').forEach(function(el, i) {{
            el.classList.toggle('selected', i === commandSelectedIndex);
        }});
        // Scroll into view
        var selected = document.querySelector('.command-item.selected');
        if (selected) selected.scrollIntoView({{ block: 'nearest' }});
    }}

    // --- Event Listeners ---
    document.addEventListener('DOMContentLoaded', function() {{
        highlightActiveNavItem();
        restoreSidebarState();

        // Input listener pour Command Palette
        var cmdInput = document.getElementById('command-input');
        if (cmdInput) {{
            cmdInput.addEventListener('input', function(e) {{
                renderCommandResults(e.target.value);
            }});
        }}
    }});

    // Fermer dropdowns si clic ailleurs
    document.addEventListener('click', function(e) {{
        // Add dropdown
        if (addDropdownOpen) {{
            var dropdown = document.getElementById('add-dropdown');
            if (dropdown && !dropdown.contains(e.target)) {{
                dropdown.classList.remove('open');
                addDropdownOpen = false;
            }}
        }}
    }});

    // Raccourcis clavier globaux
    document.addEventListener('keydown', function(e) {{
        // Ctrl+K ou Cmd+K pour Command Palette
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {{
            e.preventDefault();
            if (commandPaletteOpen) closeCommandPalette();
            else openCommandPalette();
        }}

        // Escape pour fermer Command Palette
        if (e.key === 'Escape' && commandPaletteOpen) {{
            closeCommandPalette();
        }}

        // Navigation dans Command Palette
        if (commandPaletteOpen) {{
            if (e.key === 'ArrowDown') {{
                e.preventDefault();
                commandSelectedIndex = Math.min(commandSelectedIndex + 1, commandItems.length - 1);
                updateCommandSelection();
            }}
            if (e.key === 'ArrowUp') {{
                e.preventDefault();
                commandSelectedIndex = Math.max(commandSelectedIndex - 1, 0);
                updateCommandSelection();
            }}
            if (e.key === 'Enter' && commandItems[commandSelectedIndex]) {{
                window.location.href = '/ui/' + commandItems[commandSelectedIndex].nom;
            }}
        }}
    }});

    </script>
</body>
</html>
'''
