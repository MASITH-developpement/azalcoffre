# =============================================================================
# AZALPLUS - UI Generator
# =============================================================================
"""
Génère l'interface HTML depuis les définitions YAML.
Utilise Jinja2 pour le templating.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import UUID
import structlog
import os
import json
import html as html_module

# =============================================================================
# App Name (configurable via environment variable)
# =============================================================================
APP_NAME = os.environ.get("APP_NAME", "AZALPLUS")

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
    # Ajouter exonéré (0%)
    options_html += '<option value="0">Exonéré</option>'
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

    elif field.type in ("oui/non", "booleen", "boolean"):
        checked = "checked" if value else ""
        return f'''
        <div class="o-field-row">
            <label class="o-field-label" for="{field_id}">{label}</label>
            <div class="o-field-widget o-field-boolean">
                <input type="checkbox" id="{field_id}" name="{field.nom}" {checked} data-type="boolean">
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
            # Pour les interventions, utiliser les noms de champs spécifiques
            if module_name and module_name.lower() in ["interventions", "intervention"]:
                autofill_config = 'data-autofill="adresse_intervention:_compose_address:address_line1|address_line2|postal_code|city,contact_nom:contact_name,contact_telephone:phone,contact_email:email,ville:city,code_postal:postal_code"'
            else:
                autofill_config = 'data-autofill="adresse_ligne1:address_line1,adresse_ligne2:address_line2,ville:city,code_postal:postal_code,contact_sur_place:contact_name,telephone_contact:phone,email_contact:email"'
        elif field.nom == "customer_id":
            # Pour les factures : construire l'adresse complète dans billing_address (textarea)
            # Les champs clients sont: address_line1, address_line2, postal_code, city
            autofill_config = 'data-autofill="billing_address:_compose_address:address_line1|address_line2|postal_code|city"'
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

    elif field.type == "money":
        # Champ monétaire avec formatage
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <div class="input-with-suffix">
                    <input type="number" class="o-field-char" id="{field_id}" name="{field.nom}"
                           step="0.01" min="0" value="{escaped_value}" {required_attr}>
                    <span class="input-suffix">EUR</span>
                </div>
            </div>
        </div>
        '''

    elif field.type == "tags":
        # Champ tags - input avec séparation par virgule
        tags_value = ", ".join(value) if isinstance(value, list) else (escaped_value or "")
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <input type="text" class="o-field-char o-field-tags" id="{field_id}" name="{field.nom}"
                       value="{tags_value}" {required_attr} placeholder="Tag1, Tag2, Tag3...">
                <small class="form-help"> Séparer les tags par des virgules</small>
            </div>
        </div>
        '''

    elif field.type == "json":
        # Champ JSON - textarea avec validation
        json_value = value
        if isinstance(value, (dict, list)):
            import json as json_module
            json_value = json_module.dumps(value, indent=2, ensure_ascii=False)
        else:
            json_value = escaped_value or "{}"
        return f'''
        <div class="o-field-row" style="grid-template-columns: 150px 1fr;">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <textarea class="o-field-text o-field-json" id="{field_id}" name="{field.nom}" rows="4" {required_attr}>{json_value}</textarea>
                <small class="form-help">Format JSON</small>
            </div>
        </div>
        '''

    elif field.type == "tel":
        # Champ téléphone
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <input type="tel" class="o-field-char" id="{field_id}" name="{field.nom}"
                       value="{escaped_value}" {required_attr} placeholder="+33 1 23 45 67 89">
            </div>
        </div>
        '''

    elif field.type == "url":
        # Champ URL
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <input type="url" class="o-field-char" id="{field_id}" name="{field.nom}"
                       value="{escaped_value}" {required_attr} placeholder="https://...">
            </div>
        </div>
        '''

    elif field.type in ["file", "image"]:
        # Champ fichier/image
        file_accept = "image/*" if field.type == "image" else "*/*"
        current_file = f'<small class="form-help">Fichier actuel: {escaped_value}</small>' if escaped_value else ""
        return f'''
        <div class="o-field-row">
            <label class="o-field-label {required_class}" for="{field_id}">{label}</label>
            <div class="o-field-widget">
                <input type="file" class="o-field-char" id="{field_id}" name="{field.nom}"
                       accept="{file_accept}" {required_attr}>
                {current_file}
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


def generate_module_action_buttons(module_name: str, item: dict) -> str:
    """Génère les boutons d'action spécifiques à certains modules."""

    # Boutons pour le module import_odoo
    if module_name == "import_odoo":
        source_type = item.get('source_type', 'CSV')
        module_cible = item.get('module_cible', 'clients')
        odoo_model = item.get('odoo_model', 'res.partner')

        return f'''
        <div class="flex gap-2" style="margin-left: auto;">
            <button onclick="testOdooConnection()" class="btn btn-info btn-sm" title="Tester la connexion Odoo">
                🔌 Tester connexion
            </button>
            <button onclick="previewImport()" class="btn btn-warning btn-sm" title="Prévisualiser les données à importer">
                👁️ Prévisualiser
            </button>
            <button onclick="launchImport()" class="btn btn-success btn-sm" title="Lancer l'import">
                ▶️ Lancer l'import
            </button>
        </div>

        <!-- Modal pour upload CSV -->
        <div id="csv-upload-modal" class="modal" style="display: none;">
            <div class="modal-backdrop" onclick="closeCsvModal()"></div>
            <div class="modal-content" style="max-width: 500px;">
                <div class="modal-header">
                    <h3>Import CSV depuis Odoo</h3>
                    <button onclick="closeCsvModal()" class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Fichier CSV exporté d'Odoo</label>
                        <input type="file" id="csv-file-input" accept=".csv" class="form-control">
                    </div>
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="update-existing"> Mettre à jour les enregistrements existants
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button onclick="closeCsvModal()" class="btn btn-secondary">Annuler</button>
                    <button onclick="uploadCsvAndImport()" class="btn btn-primary">Importer</button>
                </div>
            </div>
        </div>

        <!-- Modal résultat import -->
        <div id="import-result-modal" class="modal" style="display: none;">
            <div class="modal-backdrop" onclick="closeResultModal()"></div>
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h3>Résultat de l'import</h3>
                    <button onclick="closeResultModal()" class="modal-close">&times;</button>
                </div>
                <div class="modal-body" id="import-result-content">
                </div>
                <div class="modal-footer">
                    <button onclick="closeResultModal()" class="btn btn-primary">Fermer</button>
                </div>
            </div>
        </div>

        <script>
        // Variables pour import Odoo
        const odooConfig = {{
            sourceType: '{source_type}',
            moduleCible: '{module_cible}',
            odooModel: '{odoo_model}',
            odooUrl: document.querySelector('[name="odoo_url"]')?.value || '',
            odooDb: document.querySelector('[name="odoo_db"]')?.value || '',
            odooLogin: document.querySelector('[name="odoo_login"]')?.value || '',
            odooApiKey: document.querySelector('[name="odoo_api_key"]')?.value || ''
        }};

        function getOdooConfig() {{
            return {{
                url: document.querySelector('[name="odoo_url"]')?.value || '',
                db: document.querySelector('[name="odoo_db"]')?.value || '',
                username: document.querySelector('[name="odoo_login"]')?.value || '',
                password: document.querySelector('[name="odoo_api_key"]')?.value || ''
            }};
        }}

        async function testOdooConnection() {{
            const config = getOdooConfig();
            if (!config.url || !config.db || !config.username || !config.password) {{
                alert('Veuillez remplir tous les champs de connexion Odoo (URL, Base, Login, Clé API)');
                return;
            }}

            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '⏳ Test en cours...';

            try {{
                const response = await fetch('/api/odoo/test-connection', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    credentials: 'include',
                    body: JSON.stringify(config)
                }});

                const result = await response.json();
                if (result.success) {{
                    alert('✅ Connexion réussie !\\n\\nVersion Odoo: ' + (result.version?.server_version || 'N/A'));
                }} else {{
                    alert('❌ Échec de connexion:\\n' + (result.error || 'Erreur inconnue'));
                }}
            }} catch (error) {{
                alert('❌ Erreur: ' + error.message);
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = originalText;
            }}
        }}

        async function previewImport() {{
            const sourceType = document.querySelector('[name="source_type"]')?.value || 'CSV';

            if (sourceType === 'CSV' || sourceType === 'EXCEL') {{
                alert('Pour prévisualiser un import CSV/Excel, utilisez le bouton "Lancer l\\'import" et sélectionnez votre fichier.');
                return;
            }}

            // Pour API, on pourrait faire un fetch limité
            const config = getOdooConfig();
            if (!config.url) {{
                alert('Veuillez configurer la connexion Odoo');
                return;
            }}

            const moduleCible = document.querySelector('[name="module_cible"]')?.value || 'clients';
            alert('Prévisualisation pour ' + moduleCible + ' via API...\\n\\nCette fonctionnalité affichera les 10 premiers enregistrements.');
        }}

        function launchImport() {{
            const sourceType = document.querySelector('[name="source_type"]')?.value || 'CSV';

            if (sourceType === 'CSV' || sourceType === 'EXCEL') {{
                // Ouvrir le modal d'upload CSV
                document.getElementById('csv-upload-modal').style.display = 'flex';
            }} else if (sourceType === 'API_XMLRPC') {{
                launchApiImport();
            }} else {{
                alert('Type de source non supporté: ' + sourceType);
            }}
        }}

        async function launchApiImport() {{
            const config = getOdooConfig();
            if (!config.url || !config.db || !config.username || !config.password) {{
                alert('Veuillez remplir tous les champs de connexion Odoo');
                return;
            }}

            const moduleCible = document.querySelector('[name="module_cible"]')?.value || 'clients';
            const odooModel = document.querySelector('[name="odoo_model"]')?.value || 'res.partner';

            if (!confirm('Lancer l\\'import ' + moduleCible + ' depuis Odoo (modèle: ' + odooModel + ') ?')) {{
                return;
            }}

            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '⏳ Import en cours...';

            try {{
                // Construire l'URL avec le paramètre odoo_model
                let apiUrl = '/api/odoo/' + moduleCible + '/api?odoo_model=' + encodeURIComponent(odooModel);
                console.log('Import API URL:', apiUrl, 'Model:', odooModel);

                const response = await fetch(apiUrl, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    credentials: 'include',
                    body: JSON.stringify({{
                        config: config,
                        options: {{
                            update_existing: false,
                            limit: parseInt(document.querySelector('[name="nb_lignes_total"]')?.value) || null
                        }}
                    }})
                }});

                const result = await response.json();
                showImportResult(result);
            }} catch (error) {{
                alert('❌ Erreur: ' + error.message);
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = originalText;
            }}
        }}

        function closeCsvModal() {{
            document.getElementById('csv-upload-modal').style.display = 'none';
        }}

        function closeResultModal() {{
            document.getElementById('import-result-modal').style.display = 'none';
        }}

        async function uploadCsvAndImport() {{
            const fileInput = document.getElementById('csv-file-input');
            const file = fileInput.files[0];

            if (!file) {{
                alert('Veuillez sélectionner un fichier CSV');
                return;
            }}

            const moduleCible = document.querySelector('[name="module_cible"]')?.value || 'clients';
            const updateExisting = document.getElementById('update-existing').checked;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('update_existing', updateExisting);

            closeCsvModal();

            try {{
                const response = await fetch('/api/odoo/' + moduleCible + '/csv', {{
                    method: 'POST',
                    credentials: 'include',
                    body: formData
                }});

                const result = await response.json();
                showImportResult(result);
            }} catch (error) {{
                alert('❌ Erreur: ' + error.message);
            }}
        }}

        function showImportResult(result) {{
            const content = document.getElementById('import-result-content');
            const stats = result.stats || {{}};

            let html = '<div class="import-result">';

            if (result.success) {{
                html += '<div class="alert alert-success">✅ Import terminé avec succès !</div>';
            }} else {{
                html += '<div class="alert alert-danger">❌ Import terminé avec des erreurs</div>';
            }}

            html += '<table class="table table-bordered" style="margin-top: 16px;">';
            html += '<tr><th>Module</th><td>' + (result.module || '-') + '</td></tr>';
            html += '<tr><th>Modèle Odoo</th><td>' + (result.odoo_model || '-') + '</td></tr>';
            html += '<tr><th>Total traités</th><td>' + (stats.total || 0) + '</td></tr>';
            html += '<tr><th>Importés</th><td style="color: green;">' + (stats.imported || 0) + '</td></tr>';
            html += '<tr><th>Mis à jour</th><td style="color: blue;">' + (stats.updated || 0) + '</td></tr>';
            html += '<tr><th>Ignorés</th><td style="color: orange;">' + (stats.skipped || 0) + '</td></tr>';
            html += '<tr><th>Erreurs</th><td style="color: red;">' + (stats.errors || 0) + '</td></tr>';
            html += '<tr><th>Durée</th><td>' + (result.duration_seconds?.toFixed(2) || '0') + 's</td></tr>';
            html += '</table>';

            if (result.errors && result.errors.length > 0) {{
                html += '<div style="margin-top: 16px;"><strong>Détails des erreurs:</strong></div>';
                html += '<ul class="error-list" style="max-height: 200px; overflow: auto; color: red;">';
                result.errors.slice(0, 10).forEach(err => {{
                    html += '<li>' + (err.message || err.error || JSON.stringify(err)) + '</li>';
                }});
                if (result.errors.length > 10) {{
                    html += '<li>... et ' + (result.errors.length - 10) + ' autres erreurs</li>';
                }}
                html += '</ul>';
            }}

            html += '</div>';
            content.innerHTML = html;

            document.getElementById('import-result-modal').style.display = 'flex';
        }}
        </script>

        <style>
        .modal {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .modal-backdrop {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
        }}
        .modal-content {{
            position: relative;
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            width: 90%;
            max-height: 90vh;
            overflow: auto;
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px;
            border-bottom: 1px solid #e5e5e5;
        }}
        .modal-header h3 {{
            margin: 0;
        }}
        .modal-close {{
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #666;
        }}
        .modal-body {{
            padding: 16px;
        }}
        .modal-footer {{
            padding: 16px;
            border-top: 1px solid #e5e5e5;
            display: flex;
            justify-content: flex-end;
            gap: 8px;
        }}
        .btn-info {{
            background: #17a2b8;
            color: white;
        }}
        .btn-info:hover {{
            background: #138496;
        }}
        .btn-success {{
            background: #28a745;
            color: white;
        }}
        .btn-success:hover {{
            background: #218838;
        }}
        .btn-warning {{
            background: #ffc107;
            color: #212529;
        }}
        .btn-warning:hover {{
            background: #e0a800;
        }}
        .alert {{
            padding: 12px 16px;
            border-radius: 4px;
            margin-bottom: 8px;
        }}
        .alert-success {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}
        .alert-danger {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}
        </style>
        '''

    # Autres modules peuvent avoir leurs propres boutons ici
    return ""


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
            <a href="/ui/technicien/installer" class="quick-link" style="border-left: 3px solid #1e3a5f;">
                {get_icon("smartphone")}
                <span>📱 App Technicien</span>
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
    import yaml

    # Charger les thèmes depuis config/themes.yml (AZAP-NC-001: zéro liste hardcodée)
    themes_config = Path(__file__).parent.parent / "config" / "themes.yml"
    themes = {}
    if themes_config.exists():
        with open(themes_config, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if data and 'themes' in data:
                themes = data['themes']

    # Générer les cartes de thème dynamiquement
    themes_cards_html = ""
    for key, theme in themes.items():
        nom = theme.get('nom', key.capitalize())
        inspiration = theme.get('inspiration', '')
        description = theme.get('description', '')
        couleurs = theme.get('couleurs', {})
        gradient = theme.get('gradient', couleurs.get('sidebar', '#1E3A8A'))
        has_border = theme.get('border', False)

        primary = couleurs.get('primary', '#1E3A8A')
        sidebar = couleurs.get('sidebar', '#1E3A8A')
        background = couleurs.get('background', '#FFFFFF')

        preview_style = f"background: {gradient};"
        if has_border:
            preview_style += " border: 2px solid #EBEAE6;"

        bg_border = "border: 1px solid #ddd;" if background in ['#FFFFFF', '#F7F6F3', '#FBFAF9', '#F6F9FC', '#F3F3F3', '#F0F0F0', '#F9FAFB'] else ""
        sidebar_border = "border: 1px solid #ddd;" if sidebar in ['#FFFFFF', '#F7F6F3', '#FBFAF9'] else ""

        themes_cards_html += f'''
                    <div class="style-card" data-style="{key}" onclick="selectStyle(\'{key}\', this)" style="border: 2px solid var(--gray-200); border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s;">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                            <div style="width: 48px; height: 48px; {preview_style} border-radius: 8px;"></div>
                            <div>
                                <h3 style="font-size: 16px; font-weight: 600; color: var(--gray-800);">{nom}</h3>
                                <span style="font-size: 12px; color: var(--gray-500);">{inspiration}</span>
                            </div>
                        </div>
                        <p style="font-size: 13px; color: var(--gray-600);">{description}</p>
                        <div style="margin-top: 12px; display: flex; gap: 6px;">
                            <span style="width: 20px; height: 20px; background: {primary}; border-radius: 4px;"></span>
                            <span style="width: 20px; height: 20px; background: {sidebar}; border-radius: 4px; {sidebar_border}"></span>
                            <span style="width: 20px; height: 20px; background: {background}; border-radius: 4px; {bg_border}"></span>
                        </div>
                    </div>'''

    html = generate_layout(
        title="Style des documents",
        content=f'''
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
                            <button class="color-btn active" style="background: #3454D1;" data-color="#3454D1"></button>
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
            .theme-option {{ margin-bottom: 24px; }}
            .color-options {{ display: flex; gap: 8px; margin-top: 8px; }}
            .color-btn {{
                width: 32px; height: 32px;
                border-radius: 50%;
                border: 2px solid transparent;
                cursor: pointer;
                transition: all 0.15s;
            }}
            .color-btn:hover {{ transform: scale(1.1); }}
            .color-btn.active {{ border-color: var(--gray-900); box-shadow: 0 0 0 2px white, 0 0 0 4px var(--gray-400); }}
            .style-options {{ display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }}
            .style-btn {{
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
            }}
            .style-btn:hover {{ border-color: var(--gray-400); }}
            .style-btn.active {{ border-color: var(--primary); background: var(--primary-light); color: var(--primary); }}
            .style-preview {{ width: 60px; height: 40px; background: var(--gray-100); border-radius: 4px; }}
        </style>

        <script>
            document.querySelectorAll('.color-btn').forEach(btn => {{
                btn.onclick = () => {{
                    document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                }};
            }});
            document.querySelectorAll('.style-btn').forEach(btn => {{
                btn.onclick = () => {{
                    const parent = btn.closest('.style-options');
                    parent.querySelectorAll('.style-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                }};
            }});
            function saveTheme() {{
                alert('Thème enregistré ! (à implémenter avec API)');
            }}
        </script>
        </div>
        </div>

        <!-- Tab Ambiance -->
        <div id="tab-ambiance" class="tab-content" style="display: none;">
        <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                <h2 class="card-title">Choisir l'ambiance de l'interface</h2>
                <button class="btn btn-secondary" onclick="toggleCustomTheme()" id="btn-create-theme">
                    <span>✨</span> Créer mon ambiance
                </button>
            </div>
            <div class="card-body">
                <!-- Section thèmes prédéfinis -->
                <div id="predefined-themes">
                    <p style="color: var(--gray-600); margin-bottom: 24px;">Sélectionnez l'ambiance visuelle qui correspond à votre style de travail</p>

                    <div class="style-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;">
                        {themes_cards_html}
                    </div>

                    <div class="flex justify-end gap-2" style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--gray-200);">
                        <button class="btn btn-primary" onclick="applyStyle()">Appliquer l'ambiance</button>
                    </div>
                </div>

                <!-- Section création ambiance personnalisée -->
                <div id="custom-theme-creator" style="display: none;">
                    <div style="display: flex; gap: 24px; flex-wrap: wrap;">
                        <!-- Formulaire de création -->
                        <div style="flex: 1; min-width: 300px;">
                            <h3 style="margin-bottom: 16px; color: var(--gray-800);">Personnaliser les couleurs</h3>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                                <div class="form-group">
                                    <label class="label">Couleur primaire</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-primary" value="#3454D1" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('primary')">
                                        <input type="text" id="custom-primary-hex" value="#3454D1" class="form-control" style="flex: 1;" oninput="syncColorFromHex('primary')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Primaire foncée</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-primary-dark" value="#2a44a8" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('primary-dark')">
                                        <input type="text" id="custom-primary-dark-hex" value="#2a44a8" class="form-control" style="flex: 1;" oninput="syncColorFromHex('primary-dark')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Sidebar</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-sidebar" value="#1E3A8A" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('sidebar')">
                                        <input type="text" id="custom-sidebar-hex" value="#1E3A8A" class="form-control" style="flex: 1;" oninput="syncColorFromHex('sidebar')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Sidebar hover</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-sidebar-hover" value="#1e40af" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('sidebar-hover')">
                                        <input type="text" id="custom-sidebar-hover-hex" value="#1e40af" class="form-control" style="flex: 1;" oninput="syncColorFromHex('sidebar-hover')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Accent</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-accent" value="#6B9FFF" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('accent')">
                                        <input type="text" id="custom-accent-hex" value="#6B9FFF" class="form-control" style="flex: 1;" oninput="syncColorFromHex('accent')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Fond de page</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-background" value="#F1F5F9" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('background')">
                                        <input type="text" id="custom-background-hex" value="#F1F5F9" class="form-control" style="flex: 1;" oninput="syncColorFromHex('background')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Succès</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-success" value="#10B981" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('success')">
                                        <input type="text" id="custom-success-hex" value="#10B981" class="form-control" style="flex: 1;" oninput="syncColorFromHex('success')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label class="label">Erreur</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="color" id="custom-error" value="#EF4444" style="width: 50px; height: 38px; border: none; border-radius: var(--radius); cursor: pointer;" onchange="syncColorFromPicker('error')">
                                        <input type="text" id="custom-error-hex" value="#EF4444" class="form-control" style="flex: 1;" oninput="syncColorFromHex('error')">
                                    </div>
                                </div>
                            </div>
                            <div class="form-group" style="margin-top: 16px;">
                                <label class="label">Rayon des bordures: <span id="radius-value">8</span>px</label>
                                <input type="range" id="custom-radius" min="0" max="20" value="8" style="width: 100%;" oninput="document.getElementById('radius-value').textContent = this.value; updatePreview();">
                            </div>
                        </div>
                        <!-- Aperçu en direct -->
                        <div style="flex: 1; min-width: 300px;">
                            <h3 style="margin-bottom: 16px; color: var(--gray-800);">Aperçu</h3>
                            <div id="theme-preview" style="border: 1px solid var(--gray-200); border-radius: var(--radius-lg); overflow: hidden; height: 320px;">
                                <div id="preview-sidebar" style="width: 60px; height: 100%; float: left; background: #1E3A8A; padding: 12px 8px;">
                                    <div style="width: 36px; height: 36px; background: rgba(255,255,255,0.1); border-radius: 8px; margin-bottom: 16px;"></div>
                                    <div id="preview-sidebar-active" style="width: 36px; height: 36px; background: rgba(255,255,255,0.2); border-radius: 8px; margin-bottom: 8px;"></div>
                                    <div style="width: 36px; height: 36px; background: rgba(255,255,255,0.1); border-radius: 8px; margin-bottom: 8px;"></div>
                                    <div style="width: 36px; height: 36px; background: rgba(255,255,255,0.1); border-radius: 8px;"></div>
                                </div>
                                <div id="preview-content" style="margin-left: 60px; height: 100%; background: #F1F5F9; padding: 16px;">
                                    <div style="background: white; padding: 12px; border-radius: 8px; margin-bottom: 12px; display: flex; gap: 8px;">
                                        <div id="preview-btn-primary" style="background: #3454D1; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px;">Bouton</div>
                                        <div style="background: var(--gray-200); padding: 6px 12px; border-radius: 6px; font-size: 12px;">Secondaire</div>
                                    </div>
                                    <div style="background: white; padding: 12px; border-radius: 8px; margin-bottom: 12px;">
                                        <div style="display: flex; gap: 8px; margin-bottom: 8px;">
                                            <span id="preview-badge-success" style="background: #D1FAE5; color: #059669; padding: 2px 8px; border-radius: 4px; font-size: 11px;">Payé</span>
                                            <span id="preview-badge-error" style="background: #FEE2E2; color: #DC2626; padding: 2px 8px; border-radius: 4px; font-size: 11px;">En retard</span>
                                        </div>
                                        <div style="height: 8px; background: var(--gray-200); border-radius: 4px; margin-bottom: 6px;"></div>
                                        <div style="height: 8px; background: var(--gray-200); border-radius: 4px; width: 70%;"></div>
                                    </div>
                                    <div style="background: white; padding: 12px; border-radius: 8px;">
                                        <div id="preview-accent-bar" style="height: 4px; background: #6B9FFF; border-radius: 2px; margin-bottom: 8px; width: 40%;"></div>
                                        <div style="height: 8px; background: var(--gray-200); border-radius: 4px;"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="flex justify-between gap-2" style="margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--gray-200);">
                        <button class="btn btn-secondary" onclick="toggleCustomTheme()">← Retour aux thèmes</button>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-secondary" onclick="resetCustomTheme()">Réinitialiser</button>
                            <button class="btn btn-primary" onclick="applyCustomTheme()">Appliquer mon ambiance</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        </div>

        <script>
            let selectedStyle = null;

            function showTab(tabName, element) {{
                event.preventDefault();
                document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById('tab-' + tabName).style.display = 'block';
                element.classList.add('active');
            }}

            function selectStyle(style, element) {{
                selectedStyle = style;
                document.querySelectorAll('.style-card').forEach(card => {{
                    card.style.borderColor = 'var(--gray-200)';
                    const badge = card.querySelector('div > div:last-of-type > span');
                    if (badge) badge.textContent = '';
                }});
                element.style.borderColor = 'var(--primary)';
                element.style.boxShadow = '0 0 0 3px rgba(113, 75, 103, 0.15)';
                const badge = element.querySelector('div > div:last-of-type > span');
                if (badge) badge.textContent = 'Sélectionné';
            }}

            async function applyStyle() {{
                if (!selectedStyle) {{
                    alert('Veuillez sélectionner une ambiance');
                    return;
                }}
                try {{
                    const response = await fetch('/api/admin/ambiance', {{
                        method: 'PUT',
                        headers: {{ 'Content-Type': 'application/json' }},
                        credentials: 'include',
                        body: JSON.stringify({{ ambiance: selectedStyle }})
                    }});

                    if (response.ok) {{
                        const data = await response.json();
                        alert('Ambiance "' + selectedStyle + '" appliquée ! La page va se recharger.');
                        window.location.reload();
                    }} else {{
                        const err = await response.json();
                        alert('Erreur: ' + (err.detail || 'Erreur inconnue'));
                    }}
                }} catch(e) {{
                    alert('Erreur: ' + e.message);
                }}
            }}

            // === CUSTOM THEME FUNCTIONS ===
            function toggleCustomTheme() {{
                const predefined = document.getElementById('predefined-themes');
                const custom = document.getElementById('custom-theme-creator');
                const btn = document.getElementById('btn-create-theme');
                if (custom.style.display === 'none') {{
                    predefined.style.display = 'none';
                    custom.style.display = 'block';
                    btn.innerHTML = '← Retour aux thèmes';
                }} else {{
                    predefined.style.display = 'block';
                    custom.style.display = 'none';
                    btn.innerHTML = '<span>✨</span> Créer mon ambiance';
                }}
            }}

            function syncColorFromPicker(field) {{
                const picker = document.getElementById('custom-' + field);
                const hex = document.getElementById('custom-' + field + '-hex');
                hex.value = picker.value.toUpperCase();
                updatePreview();
            }}

            function syncColorFromHex(field) {{
                const picker = document.getElementById('custom-' + field);
                const hex = document.getElementById('custom-' + field + '-hex');
                if (/^#[0-9A-Fa-f]{{6}}$/.test(hex.value)) {{
                    picker.value = hex.value;
                    updatePreview();
                }}
            }}

            function updatePreview() {{
                const primary = document.getElementById('custom-primary').value;
                const sidebar = document.getElementById('custom-sidebar').value;
                const accent = document.getElementById('custom-accent').value;
                const background = document.getElementById('custom-background').value;
                const success = document.getElementById('custom-success').value;
                const error = document.getElementById('custom-error').value;
                const radius = document.getElementById('custom-radius').value;

                document.getElementById('preview-sidebar').style.background = sidebar;
                document.getElementById('preview-content').style.background = background;
                document.getElementById('preview-btn-primary').style.background = primary;
                document.getElementById('preview-btn-primary').style.borderRadius = radius + 'px';
                document.getElementById('preview-accent-bar').style.background = accent;

                // Success/error badges
                const successLight = lightenColor(success, 0.85);
                const errorLight = lightenColor(error, 0.85);
                document.getElementById('preview-badge-success').style.background = successLight;
                document.getElementById('preview-badge-success').style.color = success;
                document.getElementById('preview-badge-error').style.background = errorLight;
                document.getElementById('preview-badge-error').style.color = error;
            }}

            function lightenColor(hex, percent) {{
                const num = parseInt(hex.replace('#', ''), 16);
                const r = Math.min(255, Math.floor((num >> 16) + (255 - (num >> 16)) * percent));
                const g = Math.min(255, Math.floor(((num >> 8) & 0x00FF) + (255 - ((num >> 8) & 0x00FF)) * percent));
                const b = Math.min(255, Math.floor((num & 0x0000FF) + (255 - (num & 0x0000FF)) * percent));
                return '#' + (0x1000000 + r * 0x10000 + g * 0x100 + b).toString(16).slice(1).toUpperCase();
            }}

            function resetCustomTheme() {{
                const defaults = {{
                    'primary': '#3454D1', 'primary-dark': '#2a44a8',
                    'sidebar': '#1E3A8A', 'sidebar-hover': '#1e40af',
                    'accent': '#6B9FFF', 'background': '#F1F5F9',
                    'success': '#10B981', 'error': '#EF4444'
                }};
                for (const [key, val] of Object.entries(defaults)) {{
                    document.getElementById('custom-' + key).value = val;
                    document.getElementById('custom-' + key + '-hex').value = val;
                }}
                document.getElementById('custom-radius').value = 8;
                document.getElementById('radius-value').textContent = '8';
                updatePreview();
            }}

            async function applyCustomTheme() {{
                const theme = {{
                    primary: document.getElementById('custom-primary').value,
                    primary_dark: document.getElementById('custom-primary-dark').value,
                    sidebar: document.getElementById('custom-sidebar').value,
                    sidebar_hover: document.getElementById('custom-sidebar-hover').value,
                    accent: document.getElementById('custom-accent').value,
                    background: document.getElementById('custom-background').value,
                    success: document.getElementById('custom-success').value,
                    error: document.getElementById('custom-error').value,
                    radius: parseInt(document.getElementById('custom-radius').value)
                }};

                try {{
                    const response = await fetch('/api/admin/ambiance/custom', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        credentials: 'include',
                        body: JSON.stringify(theme)
                    }});

                    if (response.ok) {{
                        alert('Votre ambiance personnalisée a été appliquée ! La page va se recharger.');
                        window.location.reload();
                    }} else {{
                        const err = await response.json();
                        alert('Erreur: ' + (err.detail || 'Erreur inconnue'));
                    }}
                }} catch(e) {{
                    alert('Erreur: ' + e.message);
                }}
            }}

            // Init preview on load
            document.addEventListener('DOMContentLoaded', updatePreview);
        </script>
        ''',
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/parametres/utilisateur", response_class=HTMLResponse)
async def user_settings(request: Request, user: dict = Depends(require_auth), tenant_id: UUID = Depends(get_current_tenant)):
    """Page de paramètres utilisateur avec configuration email SMTP."""
    from .db import Database

    # Charger la configuration email existante depuis la table administration_mail
    email_config = {}
    try:
        configs = Database.query("administration_mail", tenant_id, limit=1)
        if configs:
            email_config = configs[0]
    except Exception as e:
        logger.debug("email_config_not_found", error=str(e))

    # Valeurs actuelles
    smtp_host = email_config.get("smtp_host", "")
    smtp_port = email_config.get("smtp_port", 587)
    smtp_user = email_config.get("smtp_user", "")
    smtp_from = email_config.get("smtp_from", "")
    smtp_ssl = email_config.get("smtp_ssl", False)
    imap_host = email_config.get("imap_host", "")
    imap_port = email_config.get("imap_port", 993)
    imap_user = email_config.get("imap_user", "")

    # Échapper les valeurs utilisateur pour éviter les injections HTML
    user_nom = html_module.escape(str(user.get('nom', '') or ''))
    user_email = html_module.escape(str(user.get('email', '') or ''))
    user_telephone = html_module.escape(str(user.get('telephone', '') or ''))
    user_fonction = html_module.escape(str(user.get('fonction', '') or ''))
    smtp_host_escaped = html_module.escape(str(smtp_host or ''))
    smtp_user_escaped = html_module.escape(str(smtp_user or ''))
    smtp_from_escaped = html_module.escape(str(smtp_from or ''))
    imap_host_escaped = html_module.escape(str(imap_host or ''))
    imap_user_escaped = html_module.escape(str(imap_user or ''))

    html = generate_layout(
        title="Paramètres utilisateur",
        content=f'''
        <div class="settings-container" style="max-width: 900px;">
            <!-- Onglets -->
            <div class="tabs-container" style="background: var(--white); border-radius: var(--radius-lg) var(--radius-lg) 0 0; margin-bottom: 0;">
                <div class="tabs">
                    <a href="#" class="tab active" onclick="showSettingsTab('profil', this)">👤 Profil</a>
                    <a href="#" class="tab" onclick="showSettingsTab('email', this)">📧 Email (SMTP)</a>
                    <a href="#" class="tab" onclick="showSettingsTab('pdf', this)">📄 PDF</a>
                    <a href="#" class="tab" onclick="showSettingsTab('securite', this)">🔒 Sécurité</a>
                </div>
            </div>

            <!-- Tab Profil -->
            <div id="tab-profil" class="settings-tab-content">
                <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
                    <div class="card-header">
                        <h2 class="card-title">Informations personnelles</h2>
                    </div>
                    <div class="card-body">
                        <form id="profil-form" class="form-grid">
                            <div class="form-group">
                                <label class="label">Nom complet</label>
                                <input type="text" class="input" id="user_nom" value="{user_nom}" placeholder="Votre nom">
                            </div>
                            <div class="form-group">
                                <label class="label">Email</label>
                                <input type="email" class="input" id="user_email" value="{user_email}" readonly style="background: var(--gray-100);">
                                <small class="text-gray-500">L'email ne peut pas être modifié</small>
                            </div>
                            <div class="form-group">
                                <label class="label">Téléphone</label>
                                <input type="tel" class="input" id="user_telephone" value="{user_telephone}" placeholder="06 12 34 56 78">
                            </div>
                            <div class="form-group">
                                <label class="label">Fonction</label>
                                <input type="text" class="input" id="user_fonction" value="{user_fonction}" placeholder="Directeur, Technicien...">
                            </div>
                        </form>
                        <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
                            <button type="button" class="btn btn-primary" onclick="saveProfile()">
                                💾 Enregistrer le profil
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tab Email SMTP -->
            <div id="tab-email" class="settings-tab-content" style="display: none;">
                <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
                    <div class="card-header">
                        <h2 class="card-title">Configuration Email (SMTP)</h2>
                        <p class="text-gray-500" style="margin-top: 4px; font-size: 13px;">
                            Configurez les paramètres SMTP pour envoyer des emails (devis, factures, notifications)
                        </p>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-info" style="margin-bottom: 24px; padding: 16px; background: #EFF6FF; border-radius: 8px; border-left: 4px solid #3B82F6;">
                            <strong>💡 Astuce :</strong> Pour Gmail, utilisez smtp.gmail.com (port 587) avec un
                            <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color: #3454D1;">mot de passe d'application</a>.
                            Pour OVH, utilisez ssl0.ovh.net (port 465 SSL ou 587 TLS).
                        </div>

                        <form id="smtp-form">
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">📤 Serveur d'envoi (SMTP)</h3>
                            <div class="form-grid" style="grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Serveur SMTP</label>
                                    <input type="text" class="input" id="smtp_host" value="{smtp_host_escaped}" placeholder="smtp.gmail.com, ssl0.ovh.net...">
                                </div>
                                <div class="form-group">
                                    <label class="label">Port</label>
                                    <select class="input" id="smtp_port">
                                        <option value="587" {"selected" if smtp_port == 587 else ""}>587 (TLS/STARTTLS)</option>
                                        <option value="465" {"selected" if smtp_port == 465 else ""}>465 (SSL)</option>
                                        <option value="25" {"selected" if smtp_port == 25 else ""}>25 (Non sécurisé)</option>
                                    </select>
                                </div>
                            </div>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Identifiant (email)</label>
                                    <input type="email" class="input" id="smtp_user" value="{smtp_user_escaped}" placeholder="votre@email.com">
                                </div>
                                <div class="form-group">
                                    <label class="label">Mot de passe</label>
                                    <input type="password" class="input" id="smtp_password" placeholder="••••••••">
                                    <small class="text-gray-500">Laissez vide pour conserver le mot de passe actuel</small>
                                </div>
                            </div>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Email expéditeur (From)</label>
                                    <input type="email" class="input" id="smtp_from" value="{smtp_from_escaped}" placeholder="noreply@votreentreprise.com">
                                    <small class="text-gray-500">Adresse qui apparaît comme expéditeur</small>
                                </div>
                                <div class="form-group">
                                    <label class="label" style="margin-bottom: 12px;">Options</label>
                                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                        <input type="checkbox" id="smtp_ssl" {"checked" if smtp_ssl else ""}>
                                        <span>Utiliser SSL (port 465)</span>
                                    </label>
                                </div>
                            </div>

                            <div style="border-top: 1px solid var(--gray-200); padding-top: 24px; margin-top: 24px;">
                                <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">📥 Serveur de réception (IMAP) - Optionnel</h3>
                                <div class="form-grid" style="grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px;">
                                    <div class="form-group">
                                        <label class="label">Serveur IMAP</label>
                                        <input type="text" class="input" id="imap_host" value="{imap_host_escaped}" placeholder="imap.gmail.com, ssl0.ovh.net...">
                                    </div>
                                    <div class="form-group">
                                        <label class="label">Port</label>
                                        <select class="input" id="imap_port">
                                            <option value="993" {"selected" if imap_port == 993 else ""}>993 (SSL)</option>
                                            <option value="143" {"selected" if imap_port == 143 else ""}>143 (Non sécurisé)</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="form-grid" style="gap: 16px;">
                                    <div class="form-group">
                                        <label class="label">Identifiant IMAP</label>
                                        <input type="email" class="input" id="imap_user" value="{imap_user_escaped}" placeholder="votre@email.com">
                                    </div>
                                    <div class="form-group">
                                        <label class="label">Mot de passe IMAP</label>
                                        <input type="password" class="input" id="imap_password" placeholder="••••••••">
                                    </div>
                                </div>
                            </div>
                        </form>

                        <div style="margin-top: 24px; display: flex; justify-content: space-between; align-items: center;">
                            <button type="button" class="btn btn-secondary" onclick="testSmtpConnection()">
                                🔌 Tester la connexion
                            </button>
                            <button type="button" class="btn btn-primary" onclick="saveEmailConfig()">
                                💾 Enregistrer la configuration
                            </button>
                        </div>

                        <div id="smtp-test-result" style="margin-top: 16px; display: none;"></div>
                    </div>
                </div>
            </div>

            <!-- Tab PDF (Mise en page documents) -->
            <div id="tab-pdf" class="settings-tab-content" style="display: none;">
                <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
                    <div class="card-header">
                        <h2 class="card-title">Mise en page des documents PDF</h2>
                        <p class="text-gray-500" style="margin-top: 4px; font-size: 13px;">
                            Personnalisez l'apparence de vos devis et factures
                        </p>
                    </div>
                    <div class="card-body">
                        <form id="pdf-config-form">
                            <!-- Section En-tête -->
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">📋 En-tête du document</h3>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Afficher le logo</label>
                                    <select class="input" id="pdf_show_logo">
                                        <option value="true">Oui</option>
                                        <option value="false">Non</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="label">Position du logo</label>
                                    <select class="input" id="pdf_logo_position">
                                        <option value="left">Gauche</option>
                                        <option value="center">Centre</option>
                                        <option value="right">Droite</option>
                                    </select>
                                </div>
                            </div>

                            <!-- Section Style -->
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">🎨 Style visuel</h3>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Couleur principale</label>
                                    <input type="color" class="input" id="pdf_primary_color" value="#3454D1" style="height: 42px; padding: 4px;">
                                </div>
                                <div class="form-group">
                                    <label class="label">Couleur d'accent</label>
                                    <input type="color" class="input" id="pdf_accent_color" value="#6B9FFF" style="height: 42px; padding: 4px;">
                                </div>
                                <div class="form-group">
                                    <label class="label">Style du tableau</label>
                                    <select class="input" id="pdf_table_style">
                                        <option value="simple">Simple</option>
                                        <option value="striped">Lignes alternées</option>
                                        <option value="bordered">Bordures complètes</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="label">Coins</label>
                                    <select class="input" id="pdf_corners">
                                        <option value="rounded">Arrondis</option>
                                        <option value="square">Carrés</option>
                                    </select>
                                </div>
                            </div>

                            <!-- Section Typographie -->
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">🔤 Typographie</h3>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Police</label>
                                    <select class="input" id="pdf_font">
                                        <option value="Helvetica">Helvetica (défaut)</option>
                                        <option value="Times">Times New Roman</option>
                                        <option value="Courier">Courier</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="label">Taille de police</label>
                                    <select class="input" id="pdf_font_size">
                                        <option value="10">Petite (10pt)</option>
                                        <option value="11" selected>Normale (11pt)</option>
                                        <option value="12">Grande (12pt)</option>
                                    </select>
                                </div>
                            </div>

                            <!-- Section Marges -->
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">📐 Marges et mise en page</h3>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label class="label">Marges (mm)</label>
                                    <select class="input" id="pdf_margins">
                                        <option value="10">Étroites (10mm)</option>
                                        <option value="15" selected>Normales (15mm)</option>
                                        <option value="20">Larges (20mm)</option>
                                        <option value="25">Très larges (25mm)</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label class="label">Format papier</label>
                                    <select class="input" id="pdf_paper_size">
                                        <option value="A4" selected>A4</option>
                                        <option value="Letter">Letter (US)</option>
                                    </select>
                                </div>
                            </div>

                            <!-- Section Contenu -->
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">📝 Contenu affiché</h3>
                            <div class="form-grid" style="gap: 16px; margin-bottom: 24px;">
                                <div class="form-group">
                                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                        <input type="checkbox" id="pdf_show_siret" checked>
                                        <span>Afficher SIRET</span>
                                    </label>
                                </div>
                                <div class="form-group">
                                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                        <input type="checkbox" id="pdf_show_tva_intra" checked>
                                        <span>Afficher TVA intracommunautaire</span>
                                    </label>
                                </div>
                                <div class="form-group">
                                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                        <input type="checkbox" id="pdf_show_bank_details" checked>
                                        <span>Afficher coordonnées bancaires</span>
                                    </label>
                                </div>
                                <div class="form-group">
                                    <label style="display: flex; align-items; gap: 8px; cursor: pointer;">
                                        <input type="checkbox" id="pdf_show_signature_zone" checked>
                                        <span>Zone de signature client</span>
                                    </label>
                                </div>
                            </div>

                            <!-- Mentions légales -->
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--gray-700);">⚖️ Mentions légales</h3>
                            <div class="form-group" style="margin-bottom: 24px;">
                                <label class="label">Mention pied de page (devis)</label>
                                <textarea class="input" id="pdf_footer_devis" rows="2" placeholder="Ex: Devis valable 30 jours..."></textarea>
                            </div>
                            <div class="form-group" style="margin-bottom: 24px;">
                                <label class="label">Mention pied de page (factures)</label>
                                <textarea class="input" id="pdf_footer_facture" rows="2" placeholder="Ex: En cas de retard de paiement, des pénalités seront appliquées..."></textarea>
                            </div>
                        </form>

                        <div style="display: flex; gap: 12px; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--gray-200);">
                            <button type="button" class="btn btn-primary" onclick="savePdfConfig()">
                                💾 Enregistrer la configuration
                            </button>
                            <button type="button" class="btn btn-secondary" onclick="previewPdf()">
                                👁️ Aperçu
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tab Sécurité -->
            <div id="tab-securite" class="settings-tab-content" style="display: none;">
                <div class="card" style="border-radius: 0 0 var(--radius-lg) var(--radius-lg);">
                    <div class="card-header">
                        <h2 class="card-title">Sécurité du compte</h2>
                    </div>
                    <div class="card-body">
                        <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px;">Changer le mot de passe</h3>
                        <form id="password-form" class="form-grid" style="max-width: 400px;">
                            <div class="form-group">
                                <label class="label">Mot de passe actuel</label>
                                <input type="password" class="input" id="current_password" placeholder="••••••••">
                            </div>
                            <div class="form-group">
                                <label class="label">Nouveau mot de passe</label>
                                <input type="password" class="input" id="new_password" placeholder="••••••••">
                            </div>
                            <div class="form-group">
                                <label class="label">Confirmer le mot de passe</label>
                                <input type="password" class="input" id="confirm_password" placeholder="••••••••">
                            </div>
                        </form>
                        <div style="margin-top: 24px;">
                            <button type="button" class="btn btn-primary" onclick="changePassword()">
                                🔐 Changer le mot de passe
                            </button>
                        </div>

                        <div style="border-top: 1px solid var(--gray-200); padding-top: 24px; margin-top: 32px;">
                            <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 16px;">Sessions actives</h3>
                            <p class="text-gray-500" style="margin-bottom: 16px;">Déconnectez toutes les autres sessions pour sécuriser votre compte.</p>
                            <button type="button" class="btn btn-secondary" onclick="logoutAllSessions()">
                                🚪 Déconnecter toutes les autres sessions
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <style>
            .settings-container {{ max-width: 900px; }}
            .form-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }}
            .form-group {{ display: flex; flex-direction: column; gap: 6px; }}
            .label {{ font-size: 14px; font-weight: 500; color: var(--gray-700); }}
            .tabs {{ display: flex; gap: 0; border-bottom: 1px solid var(--gray-200); padding: 0 24px; }}
            .tab {{ padding: 16px 20px; color: var(--gray-600); text-decoration: none; border-bottom: 2px solid transparent; transition: all 0.2s; }}
            .tab:hover {{ color: var(--gray-900); }}
            .tab.active {{ color: var(--primary); border-bottom-color: var(--primary); font-weight: 500; }}
            @media (max-width: 640px) {{ .form-grid {{ grid-template-columns: 1fr; }} }}
        </style>

        <script>
        function showSettingsTab(tabId, el) {{
            event.preventDefault();
            document.querySelectorAll('.settings-tab-content').forEach(c => c.style.display = 'none');
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + tabId).style.display = 'block';
            el.classList.add('active');
        }}

        async function saveProfile() {{
            const data = {{
                nom: document.getElementById('user_nom').value,
                telephone: document.getElementById('user_telephone').value,
                fonction: document.getElementById('user_fonction').value
            }};

            try {{
                const response = await fetch('/api/auth/profile', {{
                    method: 'PUT',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});

                if (response.ok) {{
                    alert('Profil enregistré avec succès !');
                    location.reload();
                }} else {{
                    const err = await response.json();
                    alert(err.detail || 'Erreur lors de la sauvegarde');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        async function saveEmailConfig() {{
            const data = {{
                smtp_host: document.getElementById('smtp_host').value,
                smtp_port: parseInt(document.getElementById('smtp_port').value),
                smtp_user: document.getElementById('smtp_user').value,
                smtp_from: document.getElementById('smtp_from').value,
                smtp_ssl: document.getElementById('smtp_ssl').checked,
                imap_host: document.getElementById('imap_host').value,
                imap_port: parseInt(document.getElementById('imap_port').value),
                imap_user: document.getElementById('imap_user').value
            }};

            // Ajouter les mots de passe seulement s'ils sont remplis
            const smtpPwd = document.getElementById('smtp_password').value;
            const imapPwd = document.getElementById('imap_password').value;
            if (smtpPwd) data.smtp_password = smtpPwd;
            if (imapPwd) data.imap_password = imapPwd;

            try {{
                const response = await fetch('/api/administration_mail', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});

                if (response.ok) {{
                    alert('Configuration email enregistrée !');
                }} else {{
                    const err = await response.json();
                    alert(err.detail || 'Erreur lors de la sauvegarde');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        async function testSmtpConnection() {{
            const resultDiv = document.getElementById('smtp-test-result');
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<div style="padding: 12px; background: #FEF3C7; border-radius: 8px;">⏳ Test en cours...</div>';

            const data = {{
                smtp_host: document.getElementById('smtp_host').value,
                smtp_port: parseInt(document.getElementById('smtp_port').value),
                smtp_user: document.getElementById('smtp_user').value,
                smtp_password: document.getElementById('smtp_password').value,
                smtp_ssl: document.getElementById('smtp_ssl').checked
            }};

            try {{
                const response = await fetch('/api/email/test-connection', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});

                const result = await response.json();
                if (response.ok && result.success) {{
                    resultDiv.innerHTML = '<div style="padding: 12px; background: #D1FAE5; border-radius: 8px; color: #065F46;">✅ Connexion réussie ! Le serveur SMTP est fonctionnel.</div>';
                }} else {{
                    resultDiv.innerHTML = '<div style="padding: 12px; background: #FEE2E2; border-radius: 8px; color: #991B1B;">❌ Échec de connexion: ' + (result.detail || result.error || 'Erreur inconnue') + '</div>';
                }}
            }} catch (e) {{
                resultDiv.innerHTML = '<div style="padding: 12px; background: #FEE2E2; border-radius: 8px; color: #991B1B;">❌ Erreur: ' + e.message + '</div>';
            }}
        }}

        async function changePassword() {{
            const current = document.getElementById('current_password').value;
            const newPwd = document.getElementById('new_password').value;
            const confirm = document.getElementById('confirm_password').value;

            if (!current || !newPwd || !confirm) {{
                alert('Veuillez remplir tous les champs');
                return;
            }}

            if (newPwd !== confirm) {{
                alert('Les mots de passe ne correspondent pas');
                return;
            }}

            if (newPwd.length < 8) {{
                alert('Le mot de passe doit contenir au moins 8 caractères');
                return;
            }}

            try {{
                const response = await fetch('/api/auth/change-password', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        current_password: current,
                        new_password: newPwd
                    }})
                }});

                if (response.ok) {{
                    alert('Mot de passe modifié avec succès !');
                    document.getElementById('current_password').value = '';
                    document.getElementById('new_password').value = '';
                    document.getElementById('confirm_password').value = '';
                }} else {{
                    const err = await response.json();
                    alert(err.detail || 'Erreur lors du changement de mot de passe');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        async function logoutAllSessions() {{
            if (!confirm('Êtes-vous sûr de vouloir déconnecter toutes les autres sessions ?')) return;

            try {{
                const response = await fetch('/api/auth/logout-all', {{
                    method: 'POST',
                    credentials: 'include'
                }});

                if (response.ok) {{
                    alert('Toutes les autres sessions ont été déconnectées');
                }} else {{
                    alert('Erreur lors de la déconnexion');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        // ========== PDF Configuration ==========
        async function savePdfConfig() {{
            const config = {{
                show_logo: document.getElementById('pdf_show_logo').value === 'true',
                logo_position: document.getElementById('pdf_logo_position').value,
                primary_color: document.getElementById('pdf_primary_color').value,
                accent_color: document.getElementById('pdf_accent_color').value,
                table_style: document.getElementById('pdf_table_style').value,
                corners: document.getElementById('pdf_corners').value,
                font: document.getElementById('pdf_font').value,
                font_size: document.getElementById('pdf_font_size').value,
                margins: document.getElementById('pdf_margins').value,
                paper_size: document.getElementById('pdf_paper_size').value,
                show_siret: document.getElementById('pdf_show_siret').checked,
                show_tva_intra: document.getElementById('pdf_show_tva_intra').checked,
                show_bank_details: document.getElementById('pdf_show_bank_details').checked,
                show_signature_zone: document.getElementById('pdf_show_signature_zone').checked,
                footer_devis: document.getElementById('pdf_footer_devis').value,
                footer_facture: document.getElementById('pdf_footer_facture').value
            }};

            try {{
                const response = await fetch('/api/settings/pdf-config', {{
                    method: 'POST',
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(config)
                }});

                if (response.ok) {{
                    alert('Configuration PDF enregistrée avec succès !');
                }} else {{
                    const err = await response.json();
                    alert(err.detail || 'Erreur lors de la sauvegarde');
                }}
            }} catch (e) {{
                alert('Erreur: ' + e.message);
            }}
        }}

        function previewPdf() {{
            alert('Fonctionnalité aperçu PDF à venir. Vos modifications seront visibles lors du prochain téléchargement de devis/facture.');
        }}

        // Charger la configuration PDF au chargement
        document.addEventListener('DOMContentLoaded', async () => {{
            try {{
                const response = await fetch('/api/settings/pdf-config', {{ credentials: 'include' }});
                if (response.ok) {{
                    const config = await response.json();
                    if (config) {{
                        document.getElementById('pdf_show_logo').value = config.show_logo ? 'true' : 'false';
                        if (config.logo_position) document.getElementById('pdf_logo_position').value = config.logo_position;
                        if (config.primary_color) document.getElementById('pdf_primary_color').value = config.primary_color;
                        if (config.accent_color) document.getElementById('pdf_accent_color').value = config.accent_color;
                        if (config.table_style) document.getElementById('pdf_table_style').value = config.table_style;
                        if (config.corners) document.getElementById('pdf_corners').value = config.corners;
                        if (config.font) document.getElementById('pdf_font').value = config.font;
                        if (config.font_size) document.getElementById('pdf_font_size').value = config.font_size;
                        if (config.margins) document.getElementById('pdf_margins').value = config.margins;
                        if (config.paper_size) document.getElementById('pdf_paper_size').value = config.paper_size;
                        document.getElementById('pdf_show_siret').checked = config.show_siret !== false;
                        document.getElementById('pdf_show_tva_intra').checked = config.show_tva_intra !== false;
                        document.getElementById('pdf_show_bank_details').checked = config.show_bank_details !== false;
                        document.getElementById('pdf_show_signature_zone').checked = config.show_signature_zone !== false;
                        if (config.footer_devis) document.getElementById('pdf_footer_devis').value = config.footer_devis;
                        if (config.footer_facture) document.getElementById('pdf_footer_facture').value = config.footer_facture;
                    }}
                }}
            }} catch (e) {{
                console.log('Config PDF non chargée:', e);
            }}
        }});
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

@ui_router.get("/technicien/installer", response_class=HTMLResponse)
async def technicien_install_page(request: Request):
    """Page d'installation PWA pour l'application technicien."""
    try:
        # Lire le template d'installation
        template_path = Path(__file__).parent.parent / "templates" / "technicien_install.html"
        if template_path.exists():
            return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
        else:
            # Fallback: redirection vers le dashboard
            return RedirectResponse(url="/ui/technicien/dashboard")
    except Exception as e:
        logger.error("technicien_install_error", error=str(e))
        return RedirectResponse(url="/ui/technicien/dashboard")


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

    # Filtrer par technicien_id en Python (plus robuste)
    # Le champ s'appelle technicien_id dans interventions.yml
    my_interventions = [
        i for i in all_interventions_raw
        if str(i.get("technicien_id", "")) == str(user_id)
    ]

    # Si l'utilisateur n'a pas d'interventions assignees personnellement,
    # afficher toutes les interventions du tenant (mode manager/admin)
    if my_interventions:
        all_interventions = my_interventions
    else:
        all_interventions = all_interventions_raw

    interventions_today = []
    interventions_week = []
    interventions_en_cours = []

    for intv in all_interventions:
        if intv.get("statut") == "ANNULEE":
            continue

        # Le champ est date_prevue dans interventions.yml (pas date_prevue_debut)
        date_prevue = intv.get("date_prevue") or intv.get("date_demande")
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


# =============================================================================
# Administration Mail - Liste des configurations
# =============================================================================
@ui_router.get("/administration_mail", response_class=HTMLResponse)
async def administration_mail_list(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant)
):
    """Liste des configurations email."""

    items = Database.query("administration_mail", tenant_id, limit=50)

    rows_html = ""
    for item in items:
        status_class = "badge-success" if item.get("imap_actif") else "badge-pending"
        status_text = "Actif" if item.get("imap_actif") else "Inactif"
        rows_html += f'''
        <tr onclick="window.location='/ui/administration_mail/{item['id']}'" style="cursor:pointer">
            <td><strong>{item.get('imap_user', 'Non configuré')}</strong></td>
            <td>{item.get('imap_host', '-')}</td>
            <td>{item.get('smtp_host', '-')}</td>
            <td><span class="badge {status_class}">{status_text}</span></td>
            <td>{(item.get('dernier_statut') or 'Non testé')[:30]}</td>
        </tr>
        '''

    if not items:
        rows_html = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#6b7280;">Aucune configuration. Cliquez sur "Nouveau" pour en créer une.</td></tr>'

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Configuration Email - {APP_NAME}</title>
        <link rel="stylesheet" href="/assets/style.css">
        <style>
            .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
            .btn {{ padding: 10px 20px; border: none; border-radius: 8px; font-weight: 500; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }}
            .btn-primary {{ background: var(--primary); color: white; }}
            .btn-secondary {{ background: #f3f4f6; color: #374151; }}
            table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            th, td {{ padding: 14px 16px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
            th {{ background: #f9fafb; font-weight: 600; color: #374151; }}
            tr:hover {{ background: #f9fafb; }}
            .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }}
            .badge-success {{ background: #d1fae5; color: #065f46; }}
            .badge-pending {{ background: #fef3c7; color: #92400e; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h1 style="margin:0;font-size:24px;">Configuration Email</h1>
                    <p style="margin:4px 0 0;color:#6b7280;">Gérez vos comptes email pour la réception et l'envoi</p>
                </div>
                <div style="display:flex;gap:12px;">
                    <a href="/ui/" class="btn btn-secondary">Retour</a>
                    <a href="/ui/administration_mail/nouveau" class="btn btn-primary">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                        Nouveau
                    </a>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Serveur IMAP</th>
                        <th>Serveur SMTP</th>
                        <th>Statut</th>
                        <th>Dernier test</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''
    return HTMLResponse(content=html)


# =============================================================================
# Administration Mail - Formulaire (nouveau / édition)
# =============================================================================
@ui_router.get("/administration_mail/nouveau", response_class=HTMLResponse)
@ui_router.get("/administration_mail/{item_id}", response_class=HTMLResponse)
async def administration_mail_form(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id = Depends(get_current_tenant),
    item_id: str = None
):
    """Formulaire de configuration email avec layout en colonnes et boutons de test."""

    # Récupérer la config existante ou créer vide
    data = {}
    if item_id and item_id != "nouveau":
        items = Database.query("administration_mail", tenant_id, filters={"id": item_id}, limit=1)
        data = items[0] if items else {}

    # Valeurs par défaut
    defaults = {
        "imap_port": 993, "smtp_port": 587, "intervalle_polling": 300,
        "imap_dossier": "INBOX", "mots_cles": "INTERPARTNER ASSISTANCE France"
    }
    for k, v in defaults.items():
        if not data.get(k):
            data[k] = v

    def get_val(key):
        val = data.get(key, "")
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        # Convertir les nombres flottants en entiers pour l'affichage
        if isinstance(val, float) and val == int(val):
            return int(val)
        return val if val else ""

    def is_checked(key):
        return "checked" if data.get(key) else ""

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Configuration Email - {APP_NAME}</title>
        <link rel="stylesheet" href="/assets/style.css">
        <style>
            .config-container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
            .columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
            .column {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .column h3 {{ margin: 0 0 20px 0; padding-bottom: 12px; border-bottom: 2px solid var(--primary); display: flex; align-items: center; gap: 10px; }}
            .form-group {{ margin-bottom: 16px; }}
            .form-group label {{ display: block; font-weight: 500; margin-bottom: 6px; color: #374151; }}
            .form-group input, .form-group select {{ width: 100%; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; }}
            .form-group input:focus {{ outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }}
            .form-group small {{ color: #6b7280; font-size: 12px; margin-top: 4px; display: block; }}
            .form-row {{ display: grid; grid-template-columns: 1fr 120px; gap: 12px; }}
            .toggle-group {{ display: flex; align-items: center; gap: 12px; padding: 12px; background: #f9fafb; border-radius: 8px; margin-bottom: 16px; }}
            .toggle {{ width: 48px; height: 26px; background: #d1d5db; border-radius: 13px; position: relative; cursor: pointer; transition: 0.2s; }}
            .toggle.active {{ background: var(--primary); }}
            .toggle::after {{ content: ''; position: absolute; width: 22px; height: 22px; background: white; border-radius: 50%; top: 2px; left: 2px; transition: 0.2s; }}
            .toggle.active::after {{ left: 24px; }}
            .btn {{ padding: 12px 24px; border: none; border-radius: 8px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: 0.2s; }}
            .btn-primary {{ background: var(--primary); color: white; }}
            .btn-primary:hover {{ background: var(--primary-dark, #2563eb); }}
            .btn-secondary {{ background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }}
            .btn-test {{ background: #10b981; color: white; }}
            .btn-test:hover {{ background: #059669; }}
            .actions {{ display: flex; gap: 12px; justify-content: space-between; align-items: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid #e5e7eb; }}
            .test-result {{ padding: 12px 16px; border-radius: 8px; margin-top: 12px; display: none; }}
            .test-result.success {{ background: #d1fae5; color: #065f46; display: block; }}
            .test-result.error {{ background: #fee2e2; color: #991b1b; display: block; }}
            .status-box {{ background: #f9fafb; border-radius: 8px; padding: 16px; margin-top: 24px; }}
            .status-box h4 {{ margin: 0 0 12px 0; color: #374151; }}
            .status-item {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e5e7eb; }}
            .status-item:last-child {{ border-bottom: none; }}
            .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }}
            .badge-success {{ background: #d1fae5; color: #065f46; }}
            .badge-error {{ background: #fee2e2; color: #991b1b; }}
            .badge-pending {{ background: #fef3c7; color: #92400e; }}
            .spinner {{ width: 16px; height: 16px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; animation: spin 0.8s linear infinite; }}
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
            @media (max-width: 768px) {{ .columns {{ grid-template-columns: 1fr; }} }}
        </style>
    </head>
    <body>
        <div class="config-container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <div>
                    <h1 style="margin: 0; font-size: 24px;">Configuration Email</h1>
                    <p style="margin: 4px 0 0; color: #6b7280;">Paramètres IMAP/SMTP pour la réception et l'envoi d'emails</p>
                </div>
                <a href="/ui/administration_mail" class="btn btn-secondary">Retour à la liste</a>
            </div>

            <form id="mail-config-form" method="POST" action="javascript:void(0);" onsubmit="return handleSubmit(event);">
                <input type="hidden" name="id" value="{item_id or ''}">

                <div class="columns">
                    <!-- Colonne IMAP -->
                    <div class="column">
                        <h3><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg> Réception (IMAP)</h3>

                        <div class="toggle-group">
                            <div class="toggle {is_checked('imap_actif').replace('checked', 'active')}" onclick="toggleSwitch(this, 'imap_actif')"></div>
                            <input type="hidden" name="imap_actif" id="imap_actif" value="{str(data.get('imap_actif', False)).lower()}">
                            <span>Activer la réception des emails</span>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label>Serveur IMAP</label>
                                <input type="text" name="imap_host" value="{get_val('imap_host')}" list="imap-hosts" placeholder="ex: pro3.mail.ovh.net">
                                <datalist id="imap-hosts">
                                    <option value="ssl0.ovh.net">OVH Mutualisé</option>
                                    <option value="pro1.mail.ovh.net">OVH Pro 1</option>
                                    <option value="pro2.mail.ovh.net">OVH Pro 2</option>
                                    <option value="pro3.mail.ovh.net">OVH Pro 3</option>
                                    <option value="imap.gmail.com">Gmail</option>
                                    <option value="imap.ionos.fr">IONOS</option>
                                    <option value="mail.gandi.net">Gandi</option>
                                </datalist>
                                <small style="color: #9ca3af;">OVH Pro: pro1/pro2/pro3.mail.ovh.net</small>
                            </div>
                            <div class="form-group">
                                <label>Port</label>
                                <input type="number" name="imap_port" value="{get_val('imap_port')}" list="imap-ports" placeholder="993">
                                <datalist id="imap-ports">
                                    <option value="993">SSL (recommandé)</option>
                                    <option value="143">Non sécurisé</option>
                                </datalist>
                                <small style="color: #9ca3af;">993 = SSL (recommandé)</small>
                            </div>
                        </div>

                        <div class="form-group">
                            <label>Email</label>
                            <input type="email" name="imap_user" value="{get_val('imap_user')}" placeholder="ex: contact@votredomaine.com">
                            <small style="color: #9ca3af;">Adresse email complète</small>
                        </div>

                        <div class="form-group">
                            <label>Mot de passe</label>
                            <input type="password" name="imap_password" value="{get_val('imap_password')}" placeholder="Mot de passe de la boîte mail">
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label>Dossier source</label>
                                <input type="text" name="imap_dossier" value="{get_val('imap_dossier')}" list="imap-folders" placeholder="INBOX">
                                <datalist id="imap-folders">
                                    <option value="INBOX">Boîte de réception</option>
                                    <option value="INBOX/Interventions">Interventions</option>
                                    <option value="INBOX/SAV">SAV</option>
                                </datalist>
                                <small style="color: #9ca3af;">INBOX = boîte de réception</small>
                            </div>
                            <div class="form-group">
                                <label>Dossier traités</label>
                                <input type="text" name="imap_dossier_traite" value="{get_val('imap_dossier_traite')}" placeholder="INBOX/Traites">
                                <small style="color: #9ca3af;">Où déplacer les emails traités</small>
                            </div>
                        </div>

                        <button type="button" class="btn btn-test" onclick="testIMAP(event)" style="width: 100%; margin-top: 8px;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
                            Tester la réception
                        </button>
                        <div id="imap-result" class="test-result"></div>
                    </div>

                    <!-- Colonne SMTP -->
                    <div class="column">
                        <h3><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg> Envoi (SMTP)</h3>

                        <div class="toggle-group">
                            <div class="toggle {is_checked('smtp_actif').replace('checked', 'active')}" onclick="toggleSwitch(this, 'smtp_actif')"></div>
                            <input type="hidden" name="smtp_actif" id="smtp_actif" value="{str(data.get('smtp_actif', False)).lower()}">
                            <span>Activer l'envoi d'emails</span>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label>Serveur SMTP</label>
                                <input type="text" name="smtp_host" value="{get_val('smtp_host')}" list="smtp-hosts" placeholder="ex: pro3.mail.ovh.net">
                                <datalist id="smtp-hosts">
                                    <option value="ssl0.ovh.net">OVH Mutualisé</option>
                                    <option value="pro1.mail.ovh.net">OVH Pro 1</option>
                                    <option value="pro2.mail.ovh.net">OVH Pro 2</option>
                                    <option value="pro3.mail.ovh.net">OVH Pro 3</option>
                                    <option value="smtp.gmail.com">Gmail</option>
                                    <option value="smtp.ionos.fr">IONOS</option>
                                    <option value="mail.gandi.net">Gandi</option>
                                </datalist>
                                <small style="color: #9ca3af;">Souvent identique au serveur IMAP</small>
                            </div>
                            <div class="form-group">
                                <label>Port</label>
                                <input type="number" name="smtp_port" value="{get_val('smtp_port')}" list="smtp-ports" placeholder="587">
                                <datalist id="smtp-ports">
                                    <option value="587">STARTTLS (recommandé)</option>
                                    <option value="465">SSL</option>
                                    <option value="25">Non sécurisé</option>
                                </datalist>
                                <small style="color: #9ca3af;">587 = STARTTLS (recommandé)</small>
                            </div>
                        </div>

                        <div class="form-group">
                            <label>Identifiant SMTP</label>
                            <input type="email" name="smtp_user" value="{get_val('smtp_user')}" placeholder="ex: contact@votredomaine.com">
                            <small style="color: #9ca3af;">Souvent identique à l'email IMAP</small>
                        </div>

                        <div class="form-group">
                            <label>Mot de passe SMTP</label>
                            <input type="password" name="smtp_password" value="{get_val('smtp_password')}" placeholder="Mot de passe SMTP">
                            <small style="color: #9ca3af;">Souvent identique au mot de passe IMAP</small>
                        </div>

                        <div class="form-row">
                            <div class="form-group">
                                <label>Nom expéditeur</label>
                                <input type="text" name="smtp_from_name" value="{get_val('smtp_from_name')}" placeholder="ex: Service SAV">
                                <small style="color: #9ca3af;">Nom affiché dans les emails</small>
                            </div>
                            <div class="form-group">
                                <label>Email expéditeur</label>
                                <input type="email" name="smtp_from_email" value="{get_val('smtp_from_email')}" placeholder="ex: sav@votredomaine.com">
                                <small style="color: #9ca3af;">Adresse de réponse</small>
                            </div>
                        </div>

                        <button type="button" class="btn btn-test" onclick="testSMTP(event)" style="width: 100%; margin-top: 8px;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                            Tester l'envoi
                        </button>
                        <div id="smtp-result" class="test-result"></div>
                    </div>
                </div>

                <!-- Options intervention -->
                <div class="column" style="margin-bottom: 24px;">
                    <h3><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg> Options création intervention</h3>

                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;">
                        <div class="toggle-group" style="margin: 0;">
                            <div class="toggle {is_checked('intervention_auto').replace('checked', 'active')}" onclick="toggleSwitch(this, 'intervention_auto')"></div>
                            <input type="hidden" name="intervention_auto" id="intervention_auto" value="{str(data.get('intervention_auto', True)).lower()}">
                            <span style="font-size: 14px;">Création auto</span>
                        </div>
                        <div class="toggle-group" style="margin: 0;">
                            <div class="toggle {is_checked('reponse_auto').replace('checked', 'active')}" onclick="toggleSwitch(this, 'reponse_auto')"></div>
                            <input type="hidden" name="reponse_auto" id="reponse_auto" value="{str(data.get('reponse_auto', True)).lower()}">
                            <span style="font-size: 14px;">Réponse auto</span>
                        </div>
                        <div class="form-group" style="margin: 0;">
                            <label style="font-size: 13px;">Intervalle (sec)</label>
                            <input type="number" name="intervalle_polling" value="{get_val('intervalle_polling')}" style="padding: 8px;" placeholder="300">
                            <small style="color: #9ca3af;">300 = 5 min</small>
                        </div>
                    </div>

                    <div class="form-group" style="margin-top: 16px;">
                        <label>Mots-clés / Donneurs d'ordre déclencheurs</label>
                        <input type="text" name="mots_cles" class="o-field-tags" value="{get_val('mots_cles')}" placeholder="ex: INTERPARTNER, URGENT, DEPANNAGE">
                        <small style="color: #9ca3af;">Séparer par des virgules. Ces mots-clés dans l'objet du mail déclenchent la création d'intervention.</small>
                    </div>
                </div>

                <!-- Statut -->
                <div class="status-box">
                    <h4>Statut de la connexion</h4>
                    <div class="status-item">
                        <span>Dernière vérification</span>
                        <span>{data.get('derniere_verification') or 'Jamais'}</span>
                    </div>
                    <div class="status-item">
                        <span>Statut</span>
                        <span class="badge {'badge-success' if 'OK' in str(data.get('dernier_statut', '')) else 'badge-pending'}">{data.get('dernier_statut') or 'Non testé'}</span>
                    </div>
                    <div class="status-item">
                        <span>Emails non lus</span>
                        <span class="badge badge-pending">{data.get('emails_non_lus') or 0}</span>
                    </div>
                </div>

                <div class="actions">
                    <button type="button" class="btn btn-test" onclick="testAll()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
                        Tester IMAP + SMTP
                    </button>
                    <button type="submit" class="btn btn-primary">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg>
                        Enregistrer
                    </button>
                </div>
            </form>
        </div>

        <script>
            // Empêcher toute soumission GET du formulaire
            function handleSubmit(e) {{
                e.preventDefault();
                e.stopPropagation();
                submitForm();
                return false;
            }}

            async function submitForm() {{
                const btn = document.querySelector('#mail-config-form [type="submit"]');
                if (!btn || btn.disabled) return;

                btn.disabled = true;
                btn.innerHTML = '<span class="spinner"></span> Enregistrement...';

                try {{
                    const result = await saveConfig();
                    btn.innerHTML = '✓ Enregistré';
                    setTimeout(() => {{
                        btn.disabled = false;
                        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg> Enregistrer';
                    }}, 2000);
                }} catch (e) {{
                    alert('Erreur: ' + e.message);
                    btn.disabled = false;
                    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg> Enregistrer';
                }}
            }}

            function toggleSwitch(el, inputId) {{
                el.classList.toggle('active');
                document.getElementById(inputId).value = el.classList.contains('active') ? 'true' : 'false';
            }}

            async function testIMAP(e) {{
                const btn = e ? e.target.closest('button') : document.querySelector('[onclick*="testIMAP"]');
                const result = document.getElementById('imap-result');
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner"></span> Test en cours...';
                result.className = 'test-result';
                result.style.display = 'none';

                try {{
                    // Sauvegarder d'abord
                    await saveConfig();

                    const response = await fetch('/api/email-to-intervention/test-connexion', {{
                        method: 'POST',
                        credentials: 'include'
                    }});
                    const data = await response.json();

                    if (data.imap_ok) {{
                        result.className = 'test-result success';
                        result.innerHTML = '✓ ' + data.imap_message;
                    }} else {{
                        result.className = 'test-result error';
                        result.innerHTML = '✗ ' + data.imap_message;
                    }}
                }} catch (e) {{
                    result.className = 'test-result error';
                    result.innerHTML = '✗ Erreur: ' + e.message;
                }}

                btn.disabled = false;
                btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg> Tester la réception';
            }}

            async function testSMTP(e) {{
                const btn = e ? e.target.closest('button') : document.querySelector('[onclick*="testSMTP"]');
                const result = document.getElementById('smtp-result');
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner"></span> Test en cours...';
                result.className = 'test-result';
                result.style.display = 'none';

                try {{
                    await saveConfig();

                    const response = await fetch('/api/email-to-intervention/test-connexion', {{
                        method: 'POST',
                        credentials: 'include'
                    }});
                    const data = await response.json();

                    if (data.smtp_ok) {{
                        result.className = 'test-result success';
                        result.innerHTML = '✓ ' + data.smtp_message;
                    }} else {{
                        result.className = 'test-result error';
                        result.innerHTML = '✗ ' + data.smtp_message;
                    }}
                }} catch (e) {{
                    result.className = 'test-result error';
                    result.innerHTML = '✗ Erreur: ' + e.message;
                }}

                btn.disabled = false;
                btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg> Tester l\'envoi';
            }}

            async function testAll() {{
                await testIMAP();
                await testSMTP();
            }}

            async function saveConfig() {{
                const form = document.getElementById('mail-config-form');
                const formData = new FormData(form);
                const data = {{}};

                formData.forEach((value, key) => {{
                    if (value === 'true') data[key] = true;
                    else if (value === 'false') data[key] = false;
                    else if (key === 'mots_cles' && value) {{
                        data[key] = value.split(',').map(t => t.trim()).filter(t => t);
                    }} else {{
                        data[key] = value || null;
                    }}
                }});

                // Convertir les ports en nombres
                if (data.imap_port) data.imap_port = parseInt(data.imap_port);
                if (data.smtp_port) data.smtp_port = parseInt(data.smtp_port);
                if (data.intervalle_polling) data.intervalle_polling = parseInt(data.intervalle_polling);

                const itemId = data.id;
                delete data.id;

                const method = itemId ? 'PUT' : 'POST';
                const url = itemId ? '/api/administration_mail/' + itemId : '/api/administration_mail';

                const response = await fetch(url, {{
                    method: method,
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});

                if (!response.ok) {{
                    const err = await response.json();
                    throw new Error(err.detail || 'Erreur sauvegarde');
                }}

                return await response.json();
            }}

            // Event listener supprimé - géré par onsubmit="handleSubmit(event)"
        </script>
    </body>
    </html>
    '''

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

    # Pour les modules createur_only, utiliser SYSTEM_TENANT_ID
    query_tenant_id = SYSTEM_TENANT_ID if module.acces == "createur_only" else tenant_id

    # Paramètres de tri depuis la requête
    sort_field = request.query_params.get("sort", "")
    sort_order = request.query_params.get("order", "desc")

    # Tri par défaut si non spécifié: created_at DESC (le plus récent en haut)
    if not sort_field:
        sort_field = "created_at"
        sort_order = "desc"

    # Construire l'ordre de tri (sécurisé contre injection SQL)
    order_by = None
    # created_at est un champ système, toujours disponible
    if sort_field == "created_at":
        order_direction = "ASC" if sort_order.lower() == "asc" else "DESC"
        order_by = f"created_at {order_direction}"
    elif sort_field and sort_field in module.champs:
        # Valider que le champ existe dans le module
        order_direction = "ASC" if sort_order.lower() == "asc" else "DESC"
        order_by = f"{sort_field} {order_direction}"

    # Récupérer les données
    items = Database.query(module_name, query_tenant_id, limit=50, order_by=order_by)

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

    # Générer le tableau avec checkbox et tri
    def make_sortable_header(field_name: str, label: str) -> str:
        """Génère un header de colonne triable."""
        is_sorted = sort_field == field_name
        next_order = "desc" if is_sorted and sort_order == "asc" else "asc"
        sort_icon = ""
        if is_sorted:
            sort_icon = ' <span class="sort-icon">▲</span>' if sort_order == "asc" else ' <span class="sort-icon">▼</span>'
        return f'<th class="sortable" data-field="{field_name}" data-order="{next_order}" onclick="sortBy(\'{field_name}\', \'{next_order}\')">{label}{sort_icon}</th>'

    table_headers = "".join([
        make_sortable_header(f, module.champs[f].label or f.replace("_", " ").title())
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

    def format_cell_with_actions(field_name: str, field_config, value, item: dict) -> str:
        """Formate une cellule avec actions contextuelles (appel, SMS, GPS)."""
        if value is None or value == "":
            return "-"

        # Détection téléphone (par type ou nom de champ)
        is_phone = (
            (field_config and field_config.type == "tel") or
            any(x in field_name.lower() for x in ["telephone", "phone", "tel", "mobile", "portable"])
        )

        if is_phone and value and value != "-":
            # Nettoyer le numéro pour les liens
            clean_phone = str(value).replace(" ", "").replace(".", "").replace("-", "")
            return f'''<span class="cell-with-actions">
                {value}
                <a href="tel:{clean_phone}" class="action-btn" title="Appeler" onclick="event.stopPropagation()">📞</a>
                <a href="sms:{clean_phone}" class="action-btn" title="SMS" onclick="event.stopPropagation()">💬</a>
            </span>'''

        # Détection adresse (par nom de champ)
        is_address = any(x in field_name.lower() for x in ["adresse", "address", "rue", "street"])

        if is_address and value and value != "-":
            # Construire l'adresse complète pour GPS
            addr_parts = [str(value)]
            if item.get("code_postal"):
                addr_parts.append(str(item.get("code_postal")))
            if item.get("ville"):
                addr_parts.append(str(item.get("ville")))
            full_addr = " ".join(addr_parts)
            maps_url = f"https://www.google.com/maps/search/?api=1&query={full_addr.replace(' ', '+')}"
            return f'''<span class="cell-with-actions">
                {value}
                <a href="{maps_url}" target="_blank" class="action-btn" title="GPS" onclick="event.stopPropagation()">🗺️</a>
            </span>'''

        return str(value)

    # Pour interventions: générer les boutons d'actions rapides
    def get_quick_actions(item: dict) -> str:
        """Génère les boutons d'actions rapides (appel, SMS, GPS) pour une intervention."""
        actions = []

        # Téléphone du contact
        phone = item.get("contact_telephone") or item.get("telephone_contact")
        if phone:
            clean_phone = str(phone).replace(" ", "").replace(".", "").replace("-", "")
            actions.append(f'<a href="tel:{clean_phone}" class="quick-action-btn" title="Appeler {phone}" onclick="event.stopPropagation()">📞</a>')
            actions.append(f'<a href="sms:{clean_phone}" class="quick-action-btn" title="SMS" onclick="event.stopPropagation()">💬</a>')

        # Adresse pour GPS
        addr = item.get("adresse_intervention") or item.get("adresse_ligne1")
        if addr:
            addr_parts = [str(addr)]
            if item.get("code_postal"):
                addr_parts.append(str(item.get("code_postal")))
            if item.get("ville"):
                addr_parts.append(str(item.get("ville")))
            full_addr = " ".join(addr_parts)
            maps_url = f"https://www.google.com/maps/search/?api=1&query={full_addr.replace(' ', '+').replace(',', '')}"
            actions.append(f'<a href="{maps_url}" target="_blank" class="quick-action-btn" title="GPS: {full_addr[:30]}" onclick="event.stopPropagation()">🗺️</a>')

        if actions:
            return '<div class="quick-actions">' + ''.join(actions) + '</div>'
        return ''

    table_rows = ""
    is_intervention_module = module_name.lower() in ["interventions", "intervention"]

    for item in items:
        cells = ""
        for f in display_fields:
            value = item.get(f, "")
            field_config = module.champs.get(f)

            if f == "statut" and value:
                value = get_status_badge(value)
            elif field_config and field_config.type in ["relation", "lien"]:
                value = resolve_relation(f, field_config, value)
            else:
                value = format_cell_with_actions(f, field_config, value, item)

            # Pour interventions: ajouter les boutons sous le nom du contact
            if is_intervention_module and f in ["contact_nom", "contact_sur_place"]:
                quick_actions = get_quick_actions(item)
                if quick_actions:
                    value = f'{value}{quick_actions}'

            cells += f"<td>{value}</td>"

        # Cellule Actions avec boutons
        actions_cell = f'''
            <td class="actions-cell" onclick="event.stopPropagation()">
                <a href="/ui/{module_name}/{item['id']}" class="action-btn" title="Modifier">✏️</a>
                <button class="action-btn" onclick="confirmDelete('{item['id']}')" title="Supprimer">🗑️</button>
            </td>
        '''

        table_rows += f'''
        <tr data-id="{item['id']}" onclick="handleRowClick(event, '{item['id']}', '/ui/{module_name}/{item['id']}')" style="cursor:pointer">
            <td class="checkbox-cell" onclick="event.stopPropagation()">
                <input type="checkbox" class="row-checkbox" data-id="{item['id']}" onchange="updateBulkActions()">
            </td>
            {cells}
            {actions_cell}
        </tr>
        '''

    # Options de statut pour le dropdown
    status_options = ""
    if status_values:
        for status in status_values:
            status_options += f'<option value="{status}">{status}</option>'

    # Champs disponibles pour le tri (tous les champs du module + created_at)
    sort_fields = [("created_at", "Date création")]
    for field_name, field_config in module.champs.items():
        label = field_config.label or field_name.replace("_", " ").title()
        sort_fields.append((field_name, label))

    html = generate_layout(
        title=module.nom_affichage,
        content=generate_list_with_bulk_actions(
            module_name=module_name,
            module_display_name=module.nom_affichage,
            table_headers=table_headers,
            table_rows=table_rows,
            has_status=has_status,
            status_options=status_options,
            sort_fields=sort_fields,
            current_sort=sort_field,
            current_order=sort_order
        ),
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


@ui_router.get("/{module_name}/nouveau", response_class=HTMLResponse)
async def module_create_form(
    module_name: str,
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """Formulaire de création style Odoo."""
    import sys
    print(f"[DEBUG] module_create_form called for: {module_name}", file=sys.stderr, flush=True)

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
        content=generate_sectioned_form(module_name, sections, module, tenant_id=tenant_id),
        user=user,
        modules=get_all_modules()
    )
    return HTMLResponse(content=html)


def organize_intervention_fields(module) -> dict:
    """Organisation specifique des champs pour le module Interventions."""
    import sys
    print(f"[DEBUG] organize_intervention_fields called, fields: {list(module.champs.keys())[:15]}", file=sys.stderr, flush=True)
    print(f"[DEBUG] objet in champs: {'objet' in module.champs}, description in champs: {'description' in module.champs}", file=sys.stderr, flush=True)

    # Champs par section dans l'ordre souhaite
    general_fields = [
        "numero", "statut", "date_demande", "donneur_ordre_id", "type_intervention",
        "numero_os", "client_id", "type_fiche", "objet", "description",
        "adresse_intervention", "code_postal", "ville", "contact_telephone",
        "contact_nom", "date_prevue", "technicien_id"
    ]

    planning_fields = [
        "date_prevue_debut", "date_prevue_fin", "duree_prevue_minutes",
        "intervenant_id"
    ]

    # Adresse intervention supprimée - champs intégrés dans General
    adresse_fields = []

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
    # adresse_fields supprimé - intégré dans General
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
        for idx, f in enumerate(general_fields + planning_fields +
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
    """Organise les champs en sections basées sur l'attribut 'groupe' du champ."""
    module_name = getattr(module, 'nom', '').lower()

    # Debug log
    with open('/tmp/debug_sections.log', 'a') as f:
        f.write(f"organize_fields_into_sections called for: {module_name}\n")
        f.write(f"Fields in module: {list(module.champs.keys())[:20]}\n")

    # Organisation specifique pour les interventions
    if 'intervention' in module_name:
        with open('/tmp/debug_sections.log', 'a') as f:
            f.write(f"Calling organize_intervention_fields\n")
        return organize_intervention_fields(module)

    # Utiliser les groupes définis dans les YAML
    sections = {}

    for nom, field in module.champs.items():
        if field.type in ["auto", "calcul"]:
            continue

        # Utiliser l'attribut groupe du champ (prioritaire)
        groupe = getattr(field, 'groupe', None)

        if groupe:
            if groupe not in sections:
                sections[groupe] = []
            sections[groupe].append((nom, field))
        else:
            # Fallback pour les champs sans groupe
            if "Autres" not in sections:
                sections["Autres"] = []
            sections["Autres"].append((nom, field))

    # Ordre préférentiel des sections
    ordre_sections = [
        "Identification", "Informations", "Contact", "Relations",
        "Montants", "Quantites", "Dates", "Statut",
        "Fichiers", "Configuration", "Securite", "Metadata", "Notes", "Autres"
    ]

    # Trier les sections selon l'ordre préférentiel
    sections_ordonnees = {}
    for section in ordre_sections:
        if section in sections:
            sections_ordonnees[section] = sections[section]

    # Ajouter les sections non prévues à la fin
    for section, champs in sections.items():
        if section not in sections_ordonnees:
            sections_ordonnees[section] = champs

    return sections_ordonnees


def generate_sectioned_form(module_name: str, sections: dict, module, tenant_id: UUID = None) -> str:
    """Génère un formulaire professionnel AZAL avec sidebar et onglets."""
    from datetime import datetime

    section_names = list(sections.keys())
    module_title = module.nom_affichage if module else module_name.replace('_', ' ').title()

    # Pré-générer le numéro auto si configuré
    auto_number = None
    if tenant_id:
        try:
            from .api_v1 import generate_auto_number
            auto_number = generate_auto_number(module_name, tenant_id)
            import structlog
            structlog.get_logger().debug("auto_number_generated", module=module_name, number=auto_number)
        except Exception as e:
            import structlog
            structlog.get_logger().error("auto_number_error", module=module_name, error=str(e))

    # Générer les onglets dans la sidebar
    sidebar_tabs_html = ""
    for i, section_name in enumerate(section_names):
        active = "active" if i == 0 else ""
        sidebar_tabs_html += f'''
            <button class="azal-sidebar-item {active}" onclick="showSection({i}, event)">
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                {section_name}
            </button>'''

    # Générer le contenu des sections
    sections_html = ""
    for i, (section_name, fields) in enumerate(sections.items()):
        display = "block" if i == 0 else "none"

        # Générer les champs en grille
        fields_html = ""
        for nom, field in fields:
            # Appliquer les valeurs par défaut pour un nouveau formulaire
            default_value = None

            # Numéro auto-généré
            if nom == "numero" and auto_number:
                default_value = auto_number
            elif field.defaut is not None:
                if field.defaut == "now":
                    # Date/datetime actuelle
                    if field.type == "datetime":
                        default_value = datetime.now().strftime("%Y-%m-%d %H:%M")
                    elif field.type == "date":
                        default_value = datetime.now().strftime("%Y-%m-%d")
                else:
                    default_value = field.defaut
            fields_html += get_field_html(field, value=default_value, module_name=module_name)

        sections_html += f'''
        <div class="azal-section-content" id="section-{i}" style="display: {display};">
            <div class="azal-section-title">{section_name}</div>
            <div class="azal-form-grid">
                {fields_html}
            </div>
        </div>'''

    return f'''
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap">

    <style>
        .azal-section-content {{ padding: 20px 0; }}
        .azal-section-title {{
            font-size: 16px;
            font-weight: 600;
            color: var(--gray-800);
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--primary);
        }}
    </style>

    <div class="azal-container">
        <!-- Sidebar -->
        <div class="azal-sidebar">
            <div class="azal-sidebar-header">
                <div class="azal-sidebar-logo">
                    <div class="azal-sidebar-logo-icon">A</div>
                    <div class="azal-sidebar-logo-text">AZAL</div>
                </div>
            </div>
            <div class="azal-sidebar-nav">
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Navigation</div>
                    <a href="/ui/{module_name}" class="azal-sidebar-item">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                        </svg>
                        Liste {module_title}
                    </a>
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Sections</div>
                    {sidebar_tabs_html}
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Actions</div>
                    <button class="azal-sidebar-item" onclick="submitForm()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                        </svg>
                        Enregistrer
                    </button>
                </div>
            </div>
        </div>

        <!-- Main content -->
        <div class="azal-main">
            <div class="azal-header">
                <div class="azal-header-top">
                    <div class="azal-header-left">
                        <div class="azal-header-icon">
                            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <div class="azal-header-title">
                            <h1>Nouveau {module_title}</h1>
                            <span class="subtitle">En cours de création</span>
                        </div>
                    </div>
                    <div class="azal-header-meta">
                        <div class="azal-status">Nouveau</div>
                        <div class="azal-header-actions">
                            <a href="/ui/{module_name}" class="btn btn-cancel">Annuler</a>
                            <button id="submit-btn" class="btn btn-save" onclick="submitForm()">
                                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                                </svg>
                                Enregistrer
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="azal-content">
                <div class="azal-form-card">
                    <form id="create-form">
                        {sections_html}
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script>
    function showSection(index, event) {{
        if (event) event.preventDefault();
        // Cacher toutes les sections
        document.querySelectorAll('.azal-section-content').forEach(s => s.style.display = 'none');
        // Désactiver tous les onglets sidebar
        document.querySelectorAll('.azal-sidebar-section:nth-child(2) .azal-sidebar-item').forEach(t => t.classList.remove('active'));
        // Afficher la section sélectionnée
        document.getElementById('section-' + index).style.display = 'block';
        // Activer l'onglet sélectionné
        document.querySelectorAll('.azal-sidebar-section:nth-child(2) .azal-sidebar-item')[index].classList.add('active');
    }}
    </script>
    ''' + generate_form_scripts(module_name)


def generate_sectioned_form_edit(module_name: str, sections: dict, module, existing_data: dict) -> str:
    """Génère un formulaire professionnel AZAL avec sidebar et onglets pour l'édition."""

    section_names = list(sections.keys())
    module_title = module.nom_affichage if module else module_name.replace('_', ' ').title()
    item_id = existing_data.get('id', '')
    display_name = existing_data.get('numero', existing_data.get('nom', existing_data.get('name', 'Sans nom')))
    current_status = existing_data.get('statut', existing_data.get('status', ''))

    # Générer les onglets dans la sidebar
    sidebar_tabs_html = ""
    for i, section_name in enumerate(section_names):
        active = "active" if i == 0 else ""
        sidebar_tabs_html += f'''
            <button class="azal-sidebar-item {active}" onclick="showSection({i}, event)">
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                {section_name}
            </button>'''

    # Générer le contenu des sections
    sections_html = ""
    for i, (section_name, fields) in enumerate(sections.items()):
        display = "block" if i == 0 else "none"

        # Générer les champs en grille avec valeurs existantes
        fields_html = ""
        for nom, field in fields:
            value = existing_data.get(nom)
            fields_html += get_field_html(field, value, module_name=module_name)

        sections_html += f'''
        <div class="azal-section-content" id="section-{i}" style="display: {display};">
            <div class="azal-section-title">{section_name}</div>
            <div class="azal-form-grid">
                {fields_html}
            </div>
        </div>'''

    return f'''
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap">

    <style>
        .azal-section-content {{ padding: 20px 0; }}
        .azal-section-title {{
            font-size: 16px;
            font-weight: 600;
            color: var(--gray-800);
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--primary);
        }}
    </style>

    <div class="azal-container">
        <!-- Sidebar -->
        <div class="azal-sidebar">
            <div class="azal-sidebar-header">
                <div class="azal-sidebar-logo">
                    <div class="azal-sidebar-logo-icon">A</div>
                    <div class="azal-sidebar-logo-text">AZAL</div>
                </div>
            </div>
            <div class="azal-sidebar-nav">
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Navigation</div>
                    <a href="/ui/{module_name}" class="azal-sidebar-item">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                        </svg>
                        Liste {module_title}
                    </a>
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Sections</div>
                    {sidebar_tabs_html}
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Actions</div>
                    <button class="azal-sidebar-item" onclick="submitFormEdit()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                        </svg>
                        Enregistrer
                    </button>
                    <button class="azal-sidebar-item azal-sidebar-item-danger" onclick="deleteRecord()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                        Supprimer
                    </button>
                </div>
            </div>
        </div>

        <!-- Main content -->
        <div class="azal-main">
            <div class="azal-header">
                <div class="azal-header-top">
                    <div class="azal-header-left">
                        <div class="azal-header-icon">
                            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <div class="azal-header-title">
                            <h1>{display_name}</h1>
                            <span class="subtitle">{module_title}</span>
                        </div>
                    </div>
                    <div class="azal-header-meta">
                        <div class="azal-status">{current_status.replace('_', ' ').title() if current_status else 'Édition'}</div>
                        <div class="azal-header-actions">
                            <a href="/ui/{module_name}" class="btn btn-cancel">Annuler</a>
                            <button id="submit-btn" class="btn btn-save" onclick="submitFormEdit()">
                                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                                </svg>
                                Enregistrer
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="azal-content">
                <div class="azal-form-card">
                    <form id="create-form">
                        <input type="hidden" name="id" value="{item_id}">
                        {sections_html}
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script>
    const itemId = '{item_id}';
    const moduleName = '{module_name}';

    function showSection(index, event) {{
        if (event) event.preventDefault();
        document.querySelectorAll('.azal-section-content').forEach(s => s.style.display = 'none');
        document.querySelectorAll('.azal-sidebar-section:nth-child(2) .azal-sidebar-item').forEach(t => t.classList.remove('active'));
        document.getElementById('section-' + index).style.display = 'block';
        document.querySelectorAll('.azal-sidebar-section:nth-child(2) .azal-sidebar-item')[index].classList.add('active');
    }}

    async function submitFormEdit() {{
        const submitBtn = document.getElementById('submit-btn');
        const originalText = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {{
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span>Enregistrement...';
        }}
        try {{
            const data = collectFormData();
            const response = await fetch('/api/' + moduleName + '/' + itemId, {{
                method: 'PUT',
                credentials: 'include',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(data)
            }});
            if (response.ok) {{
                showNotification('Modifications enregistrées !', 'success');
                setTimeout(() => {{ window.location.href = '/ui/' + moduleName; }}, 1500);
            }} else {{
                const err = await response.json().catch(() => ({{}}));
                showNotification(err.detail || 'Erreur', 'error');
                if (submitBtn) {{
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }}
            }}
        }} catch (e) {{
            showNotification('Erreur de connexion', 'error');
            if (submitBtn) {{
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }}
        }}
    }}

    async function deleteRecord() {{
        if (!confirm('Êtes-vous sûr de vouloir supprimer cet enregistrement ?')) return;
        try {{
            const response = await fetch('/api/' + moduleName + '/' + itemId, {{
                method: 'DELETE',
                credentials: 'include'
            }});
            if (response.ok) {{
                showNotification('Enregistrement supprimé', 'success');
                setTimeout(() => {{ window.location.href = '/ui/' + moduleName; }}, 1500);
            }} else {{
                const err = await response.json().catch(() => ({{}}));
                showNotification(err.detail || 'Erreur lors de la suppression', 'error');
            }}
        }} catch (e) {{
            showNotification('Erreur de connexion', 'error');
        }}
    }}

    // =========================================================================
    // Chargement des options des selects relation (EDIT)
    // =========================================================================
    function getCookie(name) {{
        const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? match[2] : null;
    }}

    function getToken() {{
        const params = new URLSearchParams(window.location.search);
        return params.get('token')
            || localStorage.getItem('access_token')
            || localStorage.getItem('auth_token')
            || getCookie('access_token')
            || getCookie('token')
            || '';
    }}

    document.addEventListener('DOMContentLoaded', function() {{
        const authToken = getToken();

        document.querySelectorAll('select[data-link]').forEach(async select => {{
            const linkedModule = select.dataset.link;
            const currentValue = select.dataset.currentValue || '';

            try {{
                const url = `/api/select/${{linkedModule.toLowerCase()}}`;
                const headers = {{ 'Content-Type': 'application/json' }};
                if (authToken) {{
                    headers['Authorization'] = 'Bearer ' + authToken;
                }}

                const response = await fetch(url, {{
                    credentials: 'include',
                    headers: headers
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
                        opt.textContent = item.nom || item.name || item.raison_sociale || item.code || item.id;
                        // Comparaison robuste UUIDs (ignore casse et tirets)
                        const itemIdNorm = String(item.id).toLowerCase().replace(/-/g, '');
                        const currentNorm = String(currentValue).toLowerCase().replace(/-/g, '');
                        if (currentValue && itemIdNorm === currentNorm) {{
                            opt.selected = true;
                        }}
                        select.appendChild(opt);
                    }});
                }}
            }} catch (e) {{
                console.error('Erreur chargement ' + select.name + ':', e);
            }}
        }});
    }});
    </script>
    ''' + generate_form_scripts_edit(module_name)


def generate_form_scripts_edit(module_name: str) -> str:
    """Génère les scripts communs pour les formulaires en mode édition."""
    return f'''
    <div id="notification" class="notification hidden"></div>
    <style>
        .notification {{
            position: fixed; top: 20px; right: 20px; padding: 16px 24px;
            border-radius: 8px; font-weight: 500; z-index: 1000;
            transition: all 0.3s ease; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        .notification.hidden {{ opacity: 0; transform: translateY(-20px); pointer-events: none; }}
        .notification.success {{ background: #10B981; color: white; }}
        .notification.error {{ background: #EF4444; color: white; }}
        .spinner {{
            display: inline-block; width: 16px; height: 16px;
            border: 2px solid #ffffff; border-radius: 50%;
            border-top-color: transparent; animation: spin 0.8s linear infinite;
            margin-right: 8px;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
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
            if (key === 'id') continue;
            const input = form.querySelector(`[name="${{key}}"]`);
            if (input && input.type === 'checkbox') {{
                data[key] = input.checked;
            }} else if (input && input.type === 'number') {{
                data[key] = value ? parseFloat(value) : null;
            }} else {{
                data[key] = value || null;
            }}
        }}
        form.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
            if (!data.hasOwnProperty(cb.name)) data[cb.name] = cb.checked;
        }});
        return data;
    }}
    </script>
    '''


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
            }} else if (input && input.classList.contains('o-field-json')) {{
                // Champs JSON: parser ou utiliser objet/array vide
                if (value && value.trim()) {{
                    try {{
                        data[key] = JSON.parse(value);
                    }} catch (e) {{
                        data[key] = {{}};
                    }}
                }} else {{
                    data[key] = {{}};
                }}
            }} else if (input && input.classList.contains('o-field-tags')) {{
                // Champs tags: convertir en liste
                if (value && value.trim()) {{
                    data[key] = value.split(',').map(t => t.trim()).filter(t => t);
                }} else {{
                    data[key] = [];
                }}
            }} else {{
                data[key] = value || null;
            }}
        }}
        form.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
            if (!data.hasOwnProperty(cb.name)) data[cb.name] = cb.checked;
        }});
        return data;
    }}

    async function submitForm(event) {{
        // Trouver le bouton cliqué ou le bouton principal
        const submitBtn = document.getElementById('submit-btn') || (event && event.target) || document.querySelector('.btn-save');
        const originalText = submitBtn ? submitBtn.innerHTML : '';

        // Désactiver tous les boutons save pendant l'enregistrement
        document.querySelectorAll('.btn-save, .azal-sidebar-item').forEach(btn => {{
            if (btn.textContent.includes('Enregistrer')) btn.disabled = true;
        }});

        if (submitBtn) {{
            submitBtn.innerHTML = '<span class="spinner"></span>Enregistrement...';
        }}

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
                    const decodedUrl = decodeURIComponent(redirectUrl);
                    const selectField = params.get('select_field');
                    if (result.id && selectField) {{
                        sessionStorage.setItem('newlyCreatedId', result.id);
                        sessionStorage.setItem('newlyCreatedField', selectField);
                    }}
                    setTimeout(() => {{ window.location.href = decodedUrl; }}, 1500);
                }} else {{
                    setTimeout(() => {{ window.location.href = '/ui/{module_name}'; }}, 1500);
                }}
            }} else {{
                const err = await response.json().catch(() => ({{}}));
                showNotification(err.detail || 'Erreur lors de l\\'enregistrement', 'error');
                // Réactiver les boutons
                document.querySelectorAll('.btn-save, .azal-sidebar-item').forEach(btn => btn.disabled = false);
                if (submitBtn) submitBtn.innerHTML = originalText;
            }}
        }} catch (e) {{
            console.error('Erreur submitForm:', e);
            showNotification('Erreur de connexion au serveur', 'error');
            document.querySelectorAll('.btn-save, .azal-sidebar-item').forEach(btn => btn.disabled = false);
            if (submitBtn) submitBtn.innerHTML = originalText;
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

        // Auto-remplir Objet avec les 5 premiers mots de Description
        const descriptionField = document.getElementById('field_description');
        const objetField = document.getElementById('field_objet');
        let objetManuallyEdited = false;

        if (objetField) {{
            objetField.addEventListener('input', function() {{
                objetManuallyEdited = true;
            }});
        }}

        if (descriptionField && objetField) {{
            descriptionField.addEventListener('input', function() {{
                if (!objetManuallyEdited || !objetField.value.trim()) {{
                    const words = this.value.trim().split(/\s+/).slice(0, 5);
                    objetField.value = words.join(' ');
                    objetManuallyEdited = false;
                }}
            }});
        }}

        // Charger les options des champs relation
        document.querySelectorAll('select[data-link]').forEach(async select => {{
            const linkedModule = select.dataset.link;
            const currentValue = select.dataset.currentValue || '';

            try {{
                const url = `/api/select/${{linkedModule.toLowerCase()}}`;
                const headers = {{ 'Content-Type': 'application/json' }};
                if (authToken) {{
                    headers['Authorization'] = 'Bearer ' + authToken;
                }}

                const response = await fetch(url, {{
                    credentials: 'include',
                    headers: headers
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
                        // Comparaison robuste des UUIDs (ignore casse et tirets)
                        const itemIdNorm = String(item.id).toLowerCase().replace(/-/g, '');
                        const currentNorm = String(currentValue).toLowerCase().replace(/-/g, '');
                        if (currentValue && itemIdNorm === currentNorm) {{
                            opt.selected = true;
                        }}
                        select.appendChild(opt);
                    }});
                }}
            }} catch (e) {{ console.error('Erreur chargement ' + select.name + ':', e); }}
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
                    if (input) {{
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


def generate_form(module_name: str, fields_html: str, module=None, existing_data: dict = None) -> str:
    """Génère un formulaire professionnel style AZAL avec sidebar et actions."""

    is_edit_mode = existing_data is not None
    item_id = existing_data.get('id', '') if existing_data else ''
    module_title = module.nom_affichage if module else module_name.replace('_', ' ').title()
    current_status = existing_data.get('status', existing_data.get('statut', 'Nouveau')) if existing_data else 'Nouveau'

    return f'''
    <!-- AZAL PROFESSIONAL FORM - Styles in /assets/style.css -->
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap">

    <div class="azal-container">
        <!-- Sidebar -->
        <div class="azal-sidebar">
            <div class="azal-sidebar-header">
                <div class="azal-sidebar-logo">
                    <div class="azal-sidebar-logo-icon">A</div>
                    <div class="azal-sidebar-logo-text">AZAL</div>
                </div>
            </div>
            <div class="azal-sidebar-nav">
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Navigation</div>
                    <a href="/ui/{module_name}" class="azal-sidebar-item">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                        </svg>
                        Liste {module_title}
                    </a>
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Actions</div>
                    <button class="azal-sidebar-item" onclick="submitForm()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                        </svg>
                        Enregistrer
                    </button>
                    {'<button class="azal-sidebar-item azal-sidebar-item-danger" onclick="deleteRecord()">' +
                        '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">' +
                            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />' +
                        '</svg>' +
                        'Supprimer' +
                    '</button>' if is_edit_mode else ''}
                </div>
            </div>
        </div>

        <!-- Main content -->
        <div class="azal-main">
            <div class="azal-header">
                <div class="azal-header-top">
                    <div class="azal-header-left">
                        <div class="azal-header-icon">
                            <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <div class="azal-header-title">
                            <h1>{'Modifier' if is_edit_mode else 'Nouveau'} {module_title}</h1>
                            <span class="subtitle">{item_id if is_edit_mode else 'En cours de création'}</span>
                        </div>
                    </div>
                    <div class="azal-header-meta">
                        <div class="azal-status">{current_status.replace('_', ' ').title()}</div>
                        <div class="azal-header-actions">
                            <a href="/ui/{module_name}" class="btn btn-cancel">Annuler</a>
                            <button class="btn btn-save" onclick="submitForm()">
                                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                                </svg>
                                Enregistrer
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="azal-content">
                <div class="azal-form-card">
                    <form id="create-form">
                        <div class="azal-form-grid">
                            {fields_html}
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script>
        const isEditMode = {'true' if is_edit_mode else 'false'};
        const itemId = '{item_id}';
        const moduleName = '{module_name}';

        async function submitForm() {{
            const form = document.getElementById('create-form');
            const formData = new FormData(form);
            const data = {{}};

            formData.forEach((value, key) => {{
                if (value !== '' && value !== null) {{
                    const input = form.querySelector(`[name="${{key}}"]`);
                    if (input && input.type === 'checkbox') {{
                        data[key] = input.checked;
                    }} else if (input && input.type === 'number') {{
                        data[key] = parseFloat(value) || 0;
                    }} else {{
                        data[key] = value;
                    }}
                }}
            }});

            form.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
                if (!cb.checked) data[cb.name] = false;
            }});

            try {{
                const url = isEditMode ? `/api/${{moduleName}}/${{itemId}}` : `/api/${{moduleName}}`;
                const method = isEditMode ? 'PUT' : 'POST';

                const response = await fetch(url, {{
                    method: method,
                    credentials: 'include',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});

                if (response.ok) {{
                    window.location.href = `/ui/${{moduleName}}`;
                }} else {{
                    const error = await response.json().catch(() => ({{}}));
                    alert(error.detail || 'Erreur lors de l\\'enregistrement');
                }}
            }} catch (e) {{
                console.error(e);
                alert('Erreur de connexion');
            }}
        }}

        async function deleteRecord() {{
            if (!confirm('Êtes-vous sûr de vouloir supprimer cet élément ?')) return;

            try {{
                const response = await fetch(`/api/${{moduleName}}/${{itemId}}`, {{
                    method: 'DELETE',
                    credentials: 'include'
                }});

                if (response.ok) {{
                    window.location.href = `/ui/${{moduleName}}`;
                }} else {{
                    alert('Erreur lors de la suppression');
                }}
            }} catch (e) {{
                alert('Erreur de connexion');
            }}
        }}
    </script>
    '''


def generate_document_form(module, module_name: str, existing_data: dict = None) -> str:
    """Génère un formulaire style Odoo pour documents avec lignes.

    Args:
        module: Definition du module YAML
        module_name: Nom du module
        existing_data: Données existantes pour mode édition (optionnel)
    """
    is_edit_mode = existing_data is not None
    item_id = existing_data.get('id', '') if existing_data else ''

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
    <!-- AZAL BOLD IDENTITY -->
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');

        :root {{
            --azal-primary: #3454D1;
            --azal-primary-dark: #2a44a8;
            --azal-primary-light: #6B9FFF;
            --azal-electric: #6B9FFF;
            --azal-bg: #F1F5F9;
            --azal-card: #FFFFFF;
            --azal-text: #1E293B;
            --azal-text-muted: #64748B;
            --azal-border: #E2E8F0;
            --azal-input-bg: #FFFFFF;
            --azal-success: #10B981;
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --azal-primary: #6B9FFF;
                --azal-primary-dark: #3454D1;
                --azal-primary-light: #93C5FD;
                --azal-electric: #93C5FD;
                --azal-bg: #0F172A;
                --azal-card: #1E293B;
                --azal-text: #F1F5F9;
                --azal-text-muted: #94A3B8;
                --azal-border: #334155;
                --azal-input-bg: #1E293B;
            }}
        }}

        .azal-doc-container {{
            max-width: 1200px;
            margin: 0 auto;
            font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
            display: flex;
            min-height: calc(100vh - 80px);
        }}

        /* ========== BARRE LATERALE NAVIGATION ========== */
        .azal-sidebar {{
            width: 220px;
            background: linear-gradient(180deg, var(--azal-primary) 0%, var(--azal-primary-dark) 100%);
            display: flex;
            flex-direction: column;
            padding: 24px 0;
            position: relative;
        }}

        .azal-sidebar::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(180deg, rgba(255,255,255,0.1) 0%, transparent 30%);
            pointer-events: none;
        }}

        .azal-sidebar-header {{
            padding: 0 20px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 16px;
        }}

        .azal-sidebar-logo {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .azal-sidebar-logo-icon {{
            width: 40px;
            height: 40px;
            background: white;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 18px;
            color: var(--azal-primary);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}

        .azal-sidebar-logo-text {{
            font-weight: 700;
            font-size: 18px;
            color: white;
        }}

        .azal-sidebar-nav {{
            flex: 1;
            padding: 0 12px;
        }}

        .azal-sidebar-section {{
            margin-bottom: 24px;
        }}

        .azal-sidebar-section-title {{
            font-size: 11px;
            font-weight: 600;
            color: rgba(255,255,255,0.5);
            text-transform: uppercase;
            letter-spacing: 1px;
            padding: 0 8px;
            margin-bottom: 8px;
        }}

        .azal-sidebar-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 12px;
            border-radius: 10px;
            color: rgba(255,255,255,0.7);
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 14px;
            font-weight: 500;
            border: none;
            background: none;
            width: 100%;
            text-align: left;
        }}

        .azal-sidebar-item:hover {{
            background: rgba(255,255,255,0.1);
            color: white;
        }}

        .azal-sidebar-item.active {{
            background: white;
            color: var(--azal-primary);
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}

        .azal-sidebar-item svg {{
            width: 20px;
            height: 20px;
            flex-shrink: 0;
        }}

        .azal-sidebar-item-success {{
            background: rgba(16, 185, 129, 0.2);
            color: #10B981 !important;
            border: 1px solid rgba(16, 185, 129, 0.3);
            margin-top: 8px;
        }}

        .azal-sidebar-item-success:hover {{
            background: #10B981;
            color: white !important;
        }}

        .azal-sidebar-item .badge {{
            margin-left: auto;
            background: rgba(255,255,255,0.2);
            color: white;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 10px;
        }}

        .azal-sidebar-item.active .badge {{
            background: var(--azal-primary);
            color: white;
        }}

        .azal-doc-container * {{
            font-family: inherit;
        }}


        /* ========== CONTENU PRINCIPAL ========== */
        .azal-main {{
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--azal-bg);
        }}

        /* ========== HEADER AZAL ========== */
        .azal-doc-header {{
            background: var(--azal-card);
            border-bottom: 1px solid var(--azal-border);
            position: relative;
        }}

        .azal-doc-header::before {{
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            width: 30%;
            height: 3px;
            background: linear-gradient(90deg, var(--azal-primary) 0%, var(--azal-electric) 100%);
        }}

        .azal-doc-header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 32px;
        }}

        .azal-doc-header-left {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}

        .azal-doc-badge {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .azal-doc-icon {{
            width: 56px;
            height: 56px;
            background: linear-gradient(135deg, var(--azal-primary) 0%, var(--azal-primary-light) 100%);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 24px rgba(30, 58, 138, 0.25);
            position: relative;
        }}

        .azal-doc-icon::after {{
            content: '';
            position: absolute;
            inset: 0;
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, transparent 50%);
        }}

        .azal-doc-icon svg {{
            width: 28px;
            height: 28px;
            color: white;
            position: relative;
            z-index: 1;
        }}

        .azal-doc-title {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .azal-doc-title h1 {{
            font-size: 28px;
            font-weight: 700;
            margin: 0;
            color: var(--azal-text);
            letter-spacing: -0.5px;
        }}

        .azal-doc-title .subtitle {{
            font-size: 13px;
            color: var(--azal-text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .azal-doc-title .subtitle::before {{
            content: '';
            width: 8px;
            height: 8px;
            background: var(--azal-electric);
            border-radius: 50%;
            animation: pulse-dot 2s infinite;
        }}

        @keyframes pulse-dot {{
            0%, 100% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.2); opacity: 0.7; }}
        }}

        .azal-doc-meta {{
            display: flex;
            align-items: center;
            gap: 24px;
        }}

        .azal-doc-status {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
            border: 1px solid var(--azal-primary);
            padding: 10px 20px;
            border-radius: 100px;
            color: var(--azal-primary);
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .azal-doc-actions {{
            display: flex;
            gap: 12px;
        }}

        .azal-doc-actions .btn {{
            padding: 14px 28px;
            font-weight: 600;
            font-size: 14px;
            transition: all 0.2s ease;
            cursor: pointer;
            border: none;
            border-radius: 12px;
            font-family: inherit;
        }}

        .azal-doc-actions .btn-cancel {{
            background: transparent;
            color: var(--azal-text-muted);
            border: 1px solid var(--azal-border);
            text-decoration: none;
        }}

        .azal-doc-actions .btn-cancel:hover {{
            color: var(--azal-text);
            border-color: var(--azal-text-muted);
            background: var(--azal-bg);
        }}

        .azal-doc-actions .btn-save {{
            background: linear-gradient(135deg, var(--azal-primary) 0%, var(--azal-primary-light) 100%);
            color: white;
            box-shadow: 0 4px 16px rgba(30, 58, 138, 0.3);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .azal-doc-actions .btn-save:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(30, 58, 138, 0.4);
        }}

        .azal-doc-actions .btn-save svg {{
            width: 18px;
            height: 18px;
        }}

        /* ========== CORPS ========== */
        .azal-doc-body {{
            flex: 1;
            padding: 32px;
            overflow-y: auto;
        }}

        .azal-doc-content {{
            background: var(--azal-card);
            border-radius: 20px;
            border: 1px solid var(--azal-border);
            overflow: hidden;
            box-shadow: 0 4px 24px rgba(0,0,0,0.04);
        }}

        /* ========== SECTIONS ========== */
        .azal-section {{
            padding: 32px;
            border-bottom: 1px solid var(--azal-border);
        }}

        .azal-section:last-child {{
            border-bottom: none;
        }}

        .azal-section-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 28px;
        }}

        .azal-section-icon {{
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--azal-primary);
        }}

        .azal-section-icon svg {{
            width: 22px;
            height: 22px;
        }}

        .azal-section-title {{
            font-size: 18px;
            font-weight: 600;
            color: var(--azal-text);
        }}

        /* ========== CHAMPS ========== */
        .azal-fields-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
        }}

        @media (max-width: 768px) {{
            .azal-fields-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .azal-field {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .azal-field.full-width {{
            grid-column: 1 / -1;
        }}

        .azal-field label {{
            font-size: 13px;
            font-weight: 500;
            color: var(--azal-text-muted);
        }}

        .azal-field .input,
        .azal-field select,
        .azal-field textarea {{
            padding: 14px 16px;
            font-size: 15px;
            border: 2px solid var(--azal-border);
            border-radius: 12px;
            background: var(--azal-input-bg);
            color: var(--azal-text);
            transition: all 0.2s ease;
            font-family: inherit;
        }}

        .azal-field .input:focus,
        .azal-field select:focus,
        .azal-field textarea:focus {{
            outline: none;
            border-color: var(--azal-primary);
            box-shadow: 0 0 0 4px rgba(30, 58, 138, 0.1);
        }}

        .azal-field .select-with-create {{
            display: flex;
            gap: 8px;
        }}

        .azal-field .select-with-create select {{
            flex: 1;
        }}

        .azal-field .btn-create-inline {{
            width: 52px;
            height: 52px;
            background: linear-gradient(135deg, var(--azal-primary) 0%, var(--azal-primary-light) 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 24px;
            font-weight: 400;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 12px rgba(30, 58, 138, 0.25);
        }}

        .azal-field .btn-create-inline:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(30, 58, 138, 0.35);
        }}

        /* ========== ONGLETS ========== */
        .azal-tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            background: var(--azal-bg);
            padding: 6px;
            border-radius: 14px;
        }}

        .azal-tab {{
            padding: 12px 24px;
            font-size: 14px;
            font-weight: 500;
            color: var(--azal-text-muted);
            background: transparent;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
            flex: 1;
            text-align: center;
        }}

        .azal-tab:hover {{
            color: var(--azal-text);
            background: var(--azal-card);
        }}

        .azal-tab.active {{
            color: white;
            background: linear-gradient(135deg, var(--azal-primary) 0%, var(--azal-primary-light) 100%);
            box-shadow: 0 4px 12px rgba(30, 58, 138, 0.25);
        }}

        /* ========== TABLEAU ========== */
        .azal-lines-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .azal-lines-table thead {{
            background: var(--azal-bg);
        }}

        .azal-lines-table th {{
            padding: 16px 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--azal-text-muted);
            text-align: left;
            border-bottom: 1px solid var(--azal-border);
        }}

        .azal-lines-table tbody tr {{
            transition: background 0.15s ease;
        }}

        .azal-lines-table tbody tr:hover {{
            background: rgba(30, 58, 138, 0.03);
        }}

        .azal-lines-table td {{
            padding: 16px 20px;
            border-bottom: 1px solid var(--azal-border);
            vertical-align: middle;
            color: var(--azal-text);
        }}

        .azal-lines-table td:last-child {{
            text-align: center;
        }}

        .azal-lines-table .input,
        .azal-lines-table select {{
            padding: 12px 14px;
            font-size: 14px;
            border: 2px solid var(--azal-border);
            border-radius: 10px;
            background: var(--azal-input-bg);
            color: var(--azal-text);
            font-weight: 500;
            font-family: inherit;
            width: 100%;
        }}

        .azal-lines-table .input:focus,
        .azal-lines-table select:focus {{
            outline: none;
            border-color: var(--azal-primary);
        }}

        .azal-lines-table .btn-remove {{
            width: 36px;
            height: 36px;
            background: rgba(239, 68, 68, 0.1);
            color: #EF4444;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 18px;
            font-weight: 400;
            transition: all 0.15s ease;
        }}

        .azal-lines-table .btn-remove:hover {{
            background: #EF4444;
            color: white;
        }}

        .azal-lines-table .montant {{
            font-weight: 700;
            color: var(--azal-primary);
            font-size: 15px;
        }}

        .azal-empty-lines {{
            text-align: center;
            padding: 60px 24px !important;
            color: var(--azal-text-muted);
        }}

        .azal-empty-lines svg {{
            width: 64px;
            height: 64px;
            margin-bottom: 16px;
            opacity: 0.3;
            color: var(--azal-primary);
        }}

        .azal-empty-lines p {{
            font-size: 16px;
            font-weight: 500;
        }}

        /* ========== BOUTONS AJOUT ========== */
        .azal-add-buttons {{
            display: flex;
            gap: 12px;
            margin-top: 24px;
            flex-wrap: wrap;
        }}

        .azal-add-btn {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 14px 24px;
            font-size: 14px;
            font-weight: 600;
            color: var(--azal-primary);
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.08) 0%, rgba(59, 130, 246, 0.08) 100%);
            border: 2px dashed var(--azal-primary);
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: inherit;
        }}

        .azal-add-btn:hover {{
            background: linear-gradient(135deg, var(--azal-primary) 0%, var(--azal-primary-light) 100%);
            border-style: solid;
            color: white;
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(30, 58, 138, 0.25);
        }}

        .azal-add-btn:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
            transform: none;
        }}

        .azal-add-btn svg {{
            width: 18px;
            height: 18px;
        }}

        /* ========== TOTAUX ========== */
        .azal-totals {{
            background: linear-gradient(135deg, var(--azal-primary) 0%, var(--azal-primary-dark) 100%);
            padding: 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
            overflow: hidden;
            border-radius: 0 0 20px 20px;
        }}

        .azal-totals::before {{
            content: '';
            position: absolute;
            top: -100px;
            right: -100px;
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            pointer-events: none;
        }}

        .azal-totals-brand {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .azal-totals-brand .logo {{
            font-size: 32px;
            font-weight: 700;
            color: white;
            letter-spacing: -1px;
        }}

        .azal-totals-brand .tagline {{
            font-size: 12px;
            color: rgba(255,255,255,0.6);
            letter-spacing: 2px;
            text-transform: uppercase;
        }}

        .azal-totals-box {{
            min-width: 320px;
            z-index: 1;
        }}

        .azal-total-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        .azal-total-row:last-child {{
            border-bottom: none;
            padding-top: 16px;
            margin-top: 8px;
            border-top: 1px solid rgba(255,255,255,0.2);
        }}

        .azal-total-row .label {{
            color: rgba(255,255,255,0.7);
            font-size: 14px;
            font-weight: 500;
        }}

        .azal-total-row .value {{
            color: white;
            font-size: 18px;
            font-weight: 600;
        }}

        .azal-total-row.grand-total .label {{
            color: rgba(255,255,255,0.9);
            font-size: 16px;
            font-weight: 600;
        }}

        .azal-total-row.grand-total .value {{
            font-size: 36px;
            font-weight: 700;
            color: white;
            text-shadow: 0 2px 12px rgba(0,0,0,0.2);
        }}

        /* ========== TAB CONTENT ========== */
        .azal-tab-content {{
            display: none;
        }}

        .azal-tab-content.active {{
            display: block;
            animation: fadeIn 0.3s ease;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .azal-info-empty {{
            text-align: center;
            padding: 60px 24px;
            color: var(--azal-text-muted);
        }}

        .azal-info-empty svg {{
            width: 56px;
            height: 56px;
            margin-bottom: 16px;
            opacity: 0.25;
        }}

        /* ========== RESPONSIVE ========== */
        @media (max-width: 900px) {{
            .azal-doc-container {{
                flex-direction: column;
            }}

            .azal-doc-container {{
                flex-direction: column;
            }}

            .azal-sidebar {{
                width: 100%;
                flex-direction: row;
                padding: 12px 16px;
                overflow-x: auto;
            }}

            .azal-sidebar::before {{
                display: none;
            }}

            .azal-sidebar-header {{
                border-bottom: none;
                border-right: 1px solid rgba(255,255,255,0.1);
                padding: 0 16px 0 0;
                margin-bottom: 0;
                margin-right: 16px;
            }}

            .azal-sidebar-logo {{
                margin-bottom: 0;
            }}

            .azal-sidebar-nav {{
                display: flex;
                flex-direction: row;
                gap: 8px;
                padding: 0;
            }}

            .azal-sidebar-section {{
                display: flex;
                flex-direction: row;
                gap: 4px;
                margin-bottom: 0;
                align-items: center;
            }}

            .azal-sidebar-section-title {{
                display: none;
            }}

            .azal-sidebar-nav {{
                flex-direction: row;
            }}

            .azal-sidebar-item.active::before {{
                display: none;
            }}
        }}

        .azal-doc-header-bar {{
            display: none;
        }}

        /* ========== OPTIONS TAB STYLES ========== */
        .azal-option-section {{
            background: var(--azal-card);
            border: 1px solid var(--azal-border);
            border-radius: 16px;
            margin-bottom: 20px;
            overflow: hidden;
        }}

        .azal-option-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 18px 24px;
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.05) 0%, rgba(59, 130, 246, 0.05) 100%);
            border-bottom: 1px solid var(--azal-border);
            font-weight: 600;
            font-size: 15px;
            color: var(--azal-text);
        }}

        .azal-option-header svg {{
            color: var(--azal-primary);
        }}

        .azal-option-subtitle {{
            font-size: 12px;
            color: var(--azal-text-muted);
            font-weight: 400;
            margin-left: 8px;
        }}

        .azal-option-content {{
            padding: 24px;
        }}

        /* Radio Cards pour livraison */
        .azal-delivery-options {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
        }}

        .azal-radio-card {{
            display: block;
            cursor: pointer;
        }}

        .azal-radio-card input[type="radio"] {{
            display: none;
        }}

        .azal-radio-card-content {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 12px;
            padding: 24px 16px;
            background: var(--azal-bg);
            border: 2px solid var(--azal-border);
            border-radius: 16px;
            transition: all 0.2s ease;
            text-align: center;
        }}

        .azal-radio-card input[type="radio"]:checked + .azal-radio-card-content {{
            border-color: var(--azal-primary);
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.08) 0%, rgba(59, 130, 246, 0.08) 100%);
            box-shadow: 0 4px 16px rgba(30, 58, 138, 0.15);
        }}

        .azal-radio-card:hover .azal-radio-card-content {{
            border-color: var(--azal-primary-light);
            transform: translateY(-2px);
        }}

        .azal-radio-card-icon {{
            width: 56px;
            height: 56px;
            background: white;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--azal-primary);
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }}

        .azal-radio-card input[type="radio"]:checked + .azal-radio-card-content .azal-radio-card-icon {{
            background: var(--azal-primary);
            color: white;
        }}

        .azal-radio-card-info {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .azal-radio-card-info strong {{
            font-size: 15px;
            color: var(--azal-text);
        }}

        .azal-radio-card-info span {{
            font-size: 12px;
            color: var(--azal-text-muted);
        }}

        .azal-radio-card-price {{
            font-size: 14px;
            font-weight: 700;
            color: var(--azal-primary);
            background: rgba(30, 58, 138, 0.1);
            padding: 6px 16px;
            border-radius: 100px;
        }}

        /* Produits optionnels */
        .azal-optional-products {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .azal-optional-product {{
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 16px 20px;
            background: var(--azal-bg);
            border: 1px solid var(--azal-border);
            border-radius: 12px;
            transition: all 0.2s ease;
        }}

        .azal-optional-product:hover {{
            border-color: var(--azal-primary-light);
        }}

        .azal-optional-product input[type="checkbox"] {{
            width: 20px;
            height: 20px;
            accent-color: var(--azal-primary);
            cursor: pointer;
        }}

        .azal-optional-product-info {{
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .azal-optional-product-name {{
            font-weight: 600;
            color: var(--azal-text);
        }}

        .azal-optional-product-desc {{
            font-size: 13px;
            color: var(--azal-text-muted);
        }}

        .azal-optional-product-price {{
            font-weight: 700;
            color: var(--azal-primary);
            font-size: 15px;
        }}

        .azal-optional-product-remove {{
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: none;
            border: none;
            color: var(--azal-text-muted);
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.15s ease;
        }}

        .azal-optional-product-remove:hover {{
            background: rgba(239, 68, 68, 0.1);
            color: #EF4444;
        }}

        .azal-optional-empty {{
            text-align: center;
            padding: 32px;
            color: var(--azal-text-muted);
            font-size: 14px;
        }}

        /* Checkbox adresse */
        .azal-option-content label input[type="checkbox"] {{
            margin-right: 8px;
            accent-color: var(--azal-primary);
        }}
    </style>

    <div class="azal-doc-container">
        <!-- Barre latérale navigation -->
        <div class="azal-sidebar">
            <div class="azal-sidebar-header">
                <div class="azal-sidebar-logo">
                    <div class="azal-sidebar-logo-icon">A</div>
                    <span class="azal-sidebar-logo-text">AZAL</span>
                </div>
            </div>
            <div class="azal-sidebar-nav">
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Client</div>
                    <button class="azal-sidebar-item active" data-tab="client">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                        Informations
                    </button>
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Document</div>
                    <button class="azal-sidebar-item" data-tab="lignes">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                        </svg>
                        Lignes
                        <span class="badge" id="lignes-count">0</span>
                    </button>
                    <button class="azal-sidebar-item" data-tab="optionnels">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                        </svg>
                        Options
                    </button>
                    <button class="azal-sidebar-item" data-tab="autres">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Infos
                    </button>
                </div>
                <div class="azal-sidebar-section">
                    <div class="azal-sidebar-section-title">Actions</div>
                    <button class="azal-sidebar-item" onclick="envoyerParEmail()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Envoyer par email
                    </button>
                    <button class="azal-sidebar-item" onclick="telechargerPDF()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        Télécharger PDF
                    </button>
                    <button class="azal-sidebar-item" onclick="imprimerDocument()">
                        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                        </svg>
                        Imprimer
                    </button>
                    {'<button class="azal-sidebar-item azal-sidebar-item-success" onclick="convertirEnCommande()">' +
                        '<svg fill="none" viewBox="0 0 24 24" stroke="currentColor">' +
                            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />' +
                        '</svg>' +
                        'Convertir en Commande' +
                    '</button>' if module_name.lower() == 'devis' else ''}
                </div>
            </div>
        </div>

        <!-- Contenu principal -->
        <div class="azal-main">
            <!-- Header du document -->
            <div class="azal-doc-header">
                <div class="azal-doc-header-top">
                    <div class="azal-doc-header-left">
                        <div class="azal-doc-badge">
                            <div class="azal-doc-icon">
                                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                            </div>
                            <div class="azal-doc-title">
                                <h1>{'Modifier ' + doc_type if is_edit_mode else 'Nouveau ' + doc_type}</h1>
                                <span class="subtitle">{existing_data.get('numero', existing_data.get('number', 'Edition')) if is_edit_mode else 'En cours de création'}</span>
                            </div>
                        </div>
                    </div>
                    <div class="azal-doc-meta">
                        <div class="azal-doc-status">
                            {existing_data.get('statut', existing_data.get('status', 'Brouillon')).replace('_', ' ').title() if is_edit_mode else 'Brouillon'}
                        </div>
                        <div class="azal-doc-actions">
                            <a href="/ui/{module_name}" class="btn btn-cancel">Annuler</a>
                            <button class="btn btn-save" onclick="saveDocument()">
                                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                                </svg>
                                Enregistrer
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="azal-doc-body">
                <div class="azal-doc-content">
                    <!-- Tab: Client -->
                    <div id="tab-client" class="azal-tab-content active">
                        <!-- Section Client -->
            <div class="azal-section">
                <div class="azal-section-header">
                    <div class="azal-section-icon">
                        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                    </div>
                    <span class="azal-section-title">Informations client</span>
                </div>

                <div class="azal-fields-grid">
                    <div class="azal-field">
                        <label>Client</label>
                        <div class="select-with-create">
                            <select class="input" id="client_id" name="client_id" data-link="Clients" data-autofill="adresse_facturation:_compose_address:address_line1|address_line2|postal_code|city" onchange="handleRelationAutofill(this)">
                                <option value="">Selectionner un client...</option>
                            </select>
                            <button type="button" class="btn-create-inline" onclick="openFullCreatePage('clients', 'client_id')" title="Creer nouveau client">
                                +
                            </button>
                        </div>
                    </div>
                    <div class="azal-field">
                        <label>Date d'expiration</label>
                        <input type="date" class="input" id="date_validite" value="">
                    </div>
                    <div class="azal-field">
                        <label>Adresse de facturation</label>
                        <textarea class="input" id="adresse_facturation" name="adresse_facturation" rows="2" placeholder="Adresse complete..."></textarea>
                                </div>
                                <div class="azal-field">
                                    <label>Conditions de paiement</label>
                                    <select class="input" id="conditions" name="conditions">
                                        <option value="immediate">Paiement immediat</option>
                                        <option value="30j">30 jours</option>
                                        <option value="45j">45 jours</option>
                                        <option value="60j">60 jours</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Tab: Lignes de commande -->
                    <div id="tab-lignes" class="azal-tab-content">
                        <table class="azal-lines-table">
                        <thead>
                            <tr>
                                <th style="width: 35%;">Produit</th>
                                <th style="width: 80px;">Tarif</th>
                                <th style="width: 100px;">Prix unit.</th>
                                <th style="width: 80px;">Qte</th>
                                <th style="width: 100px;">TVA</th>
                                <th style="width: 110px;">Montant HT</th>
                                <th style="width: 50px;"></th>
                            </tr>
                        </thead>
                        <tbody id="lignes-table">
                            <tr class="ligne-vide">
                                <td colspan="7" class="azal-empty-lines">
                                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                                    </svg>
                                    <p>Aucune ligne. Ajoutez un produit ci-dessous.</p>
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    <div class="azal-add-buttons">
                        <button type="button" id="btn-ajouter-produit" class="azal-add-btn" onclick="ajouterLigne()" disabled title="Chargement des produits...">
                            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                            </svg>
                            Ajouter un produit
                        </button>
                        <button type="button" class="azal-add-btn" onclick="ajouterSection()">
                            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7" />
                            </svg>
                            Ajouter une section
                        </button>
                        <button type="button" class="azal-add-btn" onclick="ajouterNote()">
                            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                            </svg>
                            Ajouter une note
                        </button>
                    </div>
                    </div>

                    <!-- Tab: Options -->
                    <div id="tab-optionnels" class="azal-tab-content">
                        <!-- Section Remises -->
                        <div class="azal-option-section">
                            <div class="azal-option-header">
                                <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                                </svg>
                                <span>Remises</span>
                            </div>
                            <div class="azal-option-content">
                                <div class="azal-fields-grid">
                                    <div class="azal-field">
                                        <label>Type de remise</label>
                                        <select class="input" id="remise_type" onchange="updateRemise()">
                                            <option value="">Aucune remise</option>
                                            <option value="percent">Pourcentage (%)</option>
                                            <option value="amount">Montant fixe (€)</option>
                                        </select>
                                    </div>
                                    <div class="azal-field">
                                        <label>Valeur</label>
                                        <input type="number" class="input" id="remise_value" placeholder="0" min="0" step="0.01" onchange="updateRemise()">
                                    </div>
                                    <div class="azal-field">
                                        <label>Code promo</label>
                                        <div class="select-with-create">
                                            <input type="text" class="input" id="code_promo" placeholder="Entrer un code...">
                                            <button type="button" class="btn-create-inline" onclick="appliquerCodePromo()" title="Appliquer">
                                                ✓
                                            </button>
                                        </div>
                                    </div>
                                    <div class="azal-field">
                                        <label>Remise calculée</label>
                                        <input type="text" class="input" id="remise_calculee" value="0,00 €" readonly style="background: var(--azal-bg); font-weight: 600; color: var(--azal-primary);">
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Section Livraison -->
                        <div class="azal-option-section">
                            <div class="azal-option-header">
                                <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                                </svg>
                                <span>Options de livraison</span>
                            </div>
                            <div class="azal-option-content">
                                <div class="azal-delivery-options">
                                    <label class="azal-radio-card">
                                        <input type="radio" name="livraison" value="standard" onchange="updateLivraison()">
                                        <div class="azal-radio-card-content">
                                            <div class="azal-radio-card-icon">
                                                <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                                                </svg>
                                            </div>
                                            <div class="azal-radio-card-info">
                                                <strong>Standard</strong>
                                                <span>5-7 jours ouvrés</span>
                                            </div>
                                            <div class="azal-radio-card-price">Gratuit</div>
                                        </div>
                                    </label>
                                    <label class="azal-radio-card">
                                        <input type="radio" name="livraison" value="express" onchange="updateLivraison()">
                                        <div class="azal-radio-card-content">
                                            <div class="azal-radio-card-icon">
                                                <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                </svg>
                                            </div>
                                            <div class="azal-radio-card-info">
                                                <strong>Express</strong>
                                                <span>24-48h</span>
                                            </div>
                                            <div class="azal-radio-card-price">+15,00 €</div>
                                        </div>
                                    </label>
                                    <label class="azal-radio-card">
                                        <input type="radio" name="livraison" value="sursite" checked onchange="updateLivraison()">
                                        <div class="azal-radio-card-content">
                                            <div class="azal-radio-card-icon">
                                                <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                                </svg>
                                            </div>
                                            <div class="azal-radio-card-info">
                                                <strong>Sur site</strong>
                                                <span>Installation incluse</span>
                                            </div>
                                            <div class="azal-radio-card-price">Sur devis</div>
                                        </div>
                                    </label>
                                </div>
                                <div class="azal-fields-grid" style="margin-top: 20px;">
                                    <div class="azal-field">
                                        <label>
                                            <input type="checkbox" id="adresse_differente" onchange="toggleAdresseLivraison()">
                                            Adresse de livraison différente
                                        </label>
                                    </div>
                                </div>
                                <div id="adresse_livraison_section" class="azal-fields-grid" style="display: none; margin-top: 16px;">
                                    <div class="azal-field full-width">
                                        <label>Adresse de livraison</label>
                                        <textarea class="input" id="adresse_livraison" rows="3" placeholder="Adresse complète de livraison..."></textarea>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Section Produits optionnels -->
                        <div class="azal-option-section">
                            <div class="azal-option-header">
                                <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                                </svg>
                                <span>Produits optionnels</span>
                                <span class="azal-option-subtitle">(non inclus dans le total sauf si cochés)</span>
                            </div>
                            <div class="azal-option-content">
                                <div id="produits-optionnels-list" class="azal-optional-products">
                                    <!-- Les produits optionnels seront ajoutés ici -->
                                </div>
                                <button type="button" class="azal-add-btn" onclick="ajouterProduitOptionnel()" style="margin-top: 16px;">
                                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                                    </svg>
                                    Ajouter un produit optionnel
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Tab: Autres informations -->
                    <div id="tab-autres" class="azal-tab-content">
                        <div class="azal-fields-grid" style="margin-top: 16px;">
                            <div class="azal-field">
                                <label>Reference client</label>
                                <input type="text" class="input" id="reference_client" name="reference_client" placeholder="Numero donne par le client...">
                            </div>
                            <div class="azal-field">
                                <label>Date de livraison</label>
                                <input type="date" class="input" id="delivery_date" name="delivery_date">
                            </div>
                            <div class="azal-field">
                                <label>Vendeur</label>
                                <input type="text" class="input" id="vendeur" name="vendeur" value="">
                            </div>
                            <div class="azal-field">
                                <label>Commercial</label>
                                <select class="input" id="commercial_id" name="commercial_id">
                                    <option value="">-- Selectionner --</option>
                                </select>
                            </div>
                            <div class="azal-field">
                                <label>Banque destinataire</label>
                                <select class="input" id="banque_destinataire" name="banque_destinataire">
                                    <option value="">-- Selectionner --</option>
                                </select>
                            </div>
                            <div class="azal-field">
                                <label>Reference du paiement</label>
                                <input type="text" class="input" id="reference_paiement" name="reference_paiement" placeholder="Auto-genere" readonly>
                            </div>
                        </div>
                    </div>

                    <!-- Totaux -->
                <div class="azal-totals">
                    <div class="azal-totals-brand">
                        <span class="logo">AZAL</span>
                        <span class="tagline">Votre ERP intelligent</span>
                    </div>
                    <div class="azal-totals-box">
                        <div class="azal-total-row">
                            <span class="label">Sous-total HT</span>
                            <span class="value" id="sous-total-ht">0,00 EUR</span>
                        </div>
                        <div class="azal-total-row" id="row-remise" style="display: none;">
                            <span class="label">Remise</span>
                            <span class="value" id="total-remise" style="color: #10B981;">-0,00 EUR</span>
                        </div>
                        <div class="azal-total-row" id="row-livraison" style="display: none;">
                            <span class="label">Livraison</span>
                            <span class="value" id="total-livraison">0,00 EUR</span>
                        </div>
                        <div class="azal-total-row" id="row-optionnels" style="display: none;">
                            <span class="label">Options</span>
                            <span class="value" id="total-optionnels">0,00 EUR</span>
                        </div>
                        <div class="azal-total-row">
                            <span class="label">Total HT</span>
                            <span class="value" id="total-ht">0,00 EUR</span>
                        </div>
                        <div class="azal-total-row">
                            <span class="label" id="tva-label">TVA ({tva_default}%)</span>
                            <span class="value" id="total-tva">0,00 EUR</span>
                        </div>
                        <div class="azal-total-row grand-total">
                            <span class="label">Total TTC</span>
                            <span class="value" id="total-ttc">0,00 EUR</span>
                        </div>
                    </div>
                </div>
            </div>
            </div>
        </div>
    </div>

    <script>
    // Initialisation mode edition
    window.currentDocumentId = {'`' + str(item_id) + '`' if is_edit_mode else 'null'};
    window.isEditMode = {str(is_edit_mode).lower()};
    window.existingData = {json.dumps(existing_data, default=str) if existing_data else 'null'};

    let lignes = [];
    let ligneIndex = 0;

    // Afficher un message de succes discret
    function showSaveSuccess(message) {{
        const toast = document.createElement('div');
        toast.className = 'save-toast';
        toast.innerHTML = `
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <span>${{message}}</span>
        `;
        toast.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            background: linear-gradient(135deg, #10B981 0%, #059669 100%);
            color: white;
            padding: 12px 20px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 500;
            box-shadow: 0 4px 20px rgba(16, 185, 129, 0.3);
            z-index: 9999;
            animation: slideIn 0.3s ease-out;
        `;
        document.body.appendChild(toast);

        // Ajouter l'animation CSS si pas deja presente
        if (!document.getElementById('toast-animation')) {{
            const style = document.createElement('style');
            style.id = 'toast-animation';
            style.textContent = `
                @keyframes slideIn {{
                    from {{ transform: translateX(100%); opacity: 0; }}
                    to {{ transform: translateX(0); opacity: 1; }}
                }}
                @keyframes slideOut {{
                    from {{ transform: translateX(0); opacity: 1; }}
                    to {{ transform: translateX(100%); opacity: 0; }}
                }}
            `;
            document.head.appendChild(style);
        }}

        // Disparaitre apres 3 secondes
        setTimeout(() => {{
            toast.style.animation = 'slideOut 0.3s ease-in forwards';
            setTimeout(() => toast.remove(), 300);
        }}, 3000);
    }}

    function getProduitsOptions() {{
        const produits = window.produitsData || [];
        let options = '<option value="">-- Sélectionner un produit --</option>';
        produits.forEach(p => {{
            const code = p.code || '';
            const nom = p.name || p.nom || p.designation || p.libelle || '';
            const pu1 = p.sale_price || p.prix_vente || p.prix || p.price || p.unit_price || 0;
            const custom = p.custom_fields || {{}};
            const pu2 = custom.pu2 || pu1;
            const pu3 = custom.pu3 || pu1;
            const displayText = code ? `${{code}} - ${{nom}}` : nom;
            options += `<option value="${{p.id}}" data-pu1="${{pu1}}" data-pu2="${{pu2}}" data-pu3="${{pu3}}" data-nom="${{nom}}" data-code="${{code}}">${{displayText}}</option>`;
        }});
        return options;
    }}

    function onProduitChange(select) {{
        const selectedOption = select.options[select.selectedIndex];
        const tr = select.closest('tr');
        const prixInput = tr.querySelectorAll('input[type="number"]')[0];
        const niveauSelect = tr.querySelector('select.niveau-prix');
        if (selectedOption && selectedOption.value) {{
            const niveau = niveauSelect ? niveauSelect.value : 'pu1';
            const prix = parseFloat(selectedOption.dataset[niveau]) || 0;
            prixInput.value = prix;
        }}
        calculerTotaux();
    }}

    function onNiveauPrixChange(select) {{
        const tr = select.closest('tr');
        const produitSelect = tr.querySelector('select:first-child');
        onProduitChange(produitSelect);
    }}

    function updateLignesCount() {{
        const count = document.querySelectorAll('#lignes-table tr:not(.ligne-vide)').length;
        const badge = document.getElementById('lignes-count');
        if (badge) badge.textContent = count;
    }}

    function ajouterLigne() {{
        const tbody = document.getElementById('lignes-table');
        const videRow = tbody.querySelector('.ligne-vide');
        if (videRow) videRow.remove();

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><select class="input" onchange="onProduitChange(this)" style="width:100%">${{getProduitsOptions()}}</select></td>
            <td>
                <select class="input niveau-prix" style="width:100%" onchange="onNiveauPrixChange(this)">
                    <option value="pu1">PU1</option>
                    <option value="pu2">PU2</option>
                    <option value="pu3">PU3</option>
                </select>
            </td>
            <td><input type="number" class="input" value="0" step="0.01" style="width:100%" onchange="calculerTotaux()"></td>
            <td><input type="number" class="input" value="1" style="width:100%" onchange="calculerTotaux()"></td>
            <td><select class="input tva-select" style="width:100%" onchange="calculerTotaux()">{tva_options_html}</select></td>
            <td class="montant">0.00 EUR</td>
            <td>
                <button type="button" class="btn-delete" onclick="supprimerLigne(this)" title="Supprimer">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
        ligneIndex++;
        updateLignesCount();
    }}

    function calculerTotaux() {{
        // Calculer les montants par ligne (ignorer sections et notes)
        document.querySelectorAll('#lignes-table tr:not(.ligne-vide):not(.ligne-section):not(.ligne-note)').forEach(tr => {{
            const inputs = tr.querySelectorAll('input[type="number"]');
            if (inputs.length >= 2) {{
                const prix = parseFloat(inputs[0].value) || 0;
                const qte = parseFloat(inputs[1].value) || 0;
                const montantHT = prix * qte;
                // Chercher .montant ou .total-ligne (compatibilité)
                const montantEl = tr.querySelector('.montant, .total-ligne');
                if (montantEl) montantEl.textContent = montantHT.toFixed(2) + ' EUR';
            }}
        }});

        // Déléguer le calcul complet (avec options) à la fonction dédiée
        if (typeof recalculerTotauxAvecOptions === 'function') {{
            recalculerTotauxAvecOptions();
        }} else {{
            // Fallback si la fonction n'existe pas encore
            let totalHT = 0;
            let totalTVA = 0;
            document.querySelectorAll('#lignes-table tr:not(.ligne-vide):not(.ligne-section):not(.ligne-note)').forEach(tr => {{
                const inputs = tr.querySelectorAll('input[type="number"]');
                const selects = tr.querySelectorAll('select');
                if (inputs.length >= 2) {{
                    const prix = parseFloat(inputs[0].value) || 0;
                    const qte = parseFloat(inputs[1].value) || 0;
                    // TVA - chercher le select avec classe tva-select ou le dernier select avec valeur numérique
                    let tauxTVA = {tva_default};
                    const tvaSelect = tr.querySelector('.tva-select');
                    if (tvaSelect) {{
                        tauxTVA = parseFloat(tvaSelect.value) || {tva_default};
                    }} else {{
                        for (let i = selects.length - 1; i >= 0; i--) {{
                            const val = parseFloat(selects[i].value);
                            if (!isNaN(val) && val >= 0 && val <= 100) {{
                                tauxTVA = val;
                                break;
                            }}
                        }}
                    }}
                    const montantHT = prix * qte;
                    const montantTVA = montantHT * (tauxTVA / 100);
                    totalHT += montantHT;
                    totalTVA += montantTVA;
                }}
            }});
            const ttc = totalHT + totalTVA;
            const totalHTEl = document.getElementById('total-ht');
            const totalTVAEl = document.getElementById('total-tva');
            const totalTTCEl = document.getElementById('total-ttc');
            if (totalHTEl) totalHTEl.textContent = totalHT.toFixed(2) + ' EUR';
            if (totalTVAEl) totalTVAEl.textContent = totalTVA.toFixed(2) + ' EUR';
            if (totalTTCEl) totalTTCEl.textContent = ttc.toFixed(2) + ' EUR';
        }}

        // Mettre à jour le label TVA
        const tvaLabel = document.getElementById('tva-label');
        if (tvaLabel) tvaLabel.textContent = 'TVA';
    }}

    // Ajouter une section de titre dans le devis
    function ajouterSection() {{
        const tbody = document.getElementById('lignes-table');
        const videRow = tbody.querySelector('.ligne-vide');
        if (videRow) videRow.remove();

        const tr = document.createElement('tr');
        tr.className = 'ligne-section';
        tr.innerHTML = `
            <td colspan="7" style="background: var(--azal-primary-light, #3B82F6); background: linear-gradient(90deg, var(--azal-primary, #1E3A8A) 0%, var(--azal-primary-light, #3B82F6) 100%);">
                <input type="text" class="input section-title-input" placeholder="Titre de la section..."
                    style="background: transparent; border: none; color: white; font-weight: 600; font-size: 14px; width: 100%; padding: 8px 12px;">
            </td>
            <td style="background: var(--azal-primary-light, #3B82F6); text-align: center; white-space: nowrap;">
                <button type="button" class="btn-move" onclick="monterLigne(this)" title="Monter" style="color: white; background: transparent; border: none; cursor: pointer; padding: 4px;">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
                    </svg>
                </button>
                <button type="button" class="btn-move" onclick="descendreLigne(this)" title="Descendre" style="color: white; background: transparent; border: none; cursor: pointer; padding: 4px;">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                </button>
            </td>
            <td style="background: var(--azal-primary-light, #3B82F6);">
                <button type="button" class="btn-delete" onclick="supprimerLigne(this)" title="Supprimer" style="color: white;">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
        tr.querySelector('input').focus();
        ligneIndex++;
        updateLignesCount();
    }}

    // Ajouter une note/commentaire dans le devis
    function ajouterNote() {{
        const tbody = document.getElementById('lignes-table');
        const videRow = tbody.querySelector('.ligne-vide');
        if (videRow) videRow.remove();

        const tr = document.createElement('tr');
        tr.className = 'ligne-note';
        tr.innerHTML = `
            <td colspan="7" style="background: #FEF3C7; border-left: 4px solid #F59E0B;">
                <textarea class="input note-input" placeholder="Ajouter une note ou un commentaire..." rows="2"
                    style="background: transparent; border: none; width: 100%; resize: vertical; font-style: italic; color: #92400E;"></textarea>
            </td>
            <td style="background: #FEF3C7; text-align: center; white-space: nowrap;">
                <button type="button" class="btn-move" onclick="monterLigne(this)" title="Monter" style="color: #92400E; background: transparent; border: none; cursor: pointer; padding: 4px;">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
                    </svg>
                </button>
                <button type="button" class="btn-move" onclick="descendreLigne(this)" title="Descendre" style="color: #92400E; background: transparent; border: none; cursor: pointer; padding: 4px;">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                </button>
            </td>
            <td style="background: #FEF3C7;">
                <button type="button" class="btn-delete" onclick="supprimerLigne(this)" title="Supprimer">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
        tr.querySelector('textarea').focus();
        ligneIndex++;
        updateLignesCount();
    }}

    // Monter une ligne (section, note ou produit)
    function monterLigne(btn) {{
        const tr = btn.closest('tr');
        const tbody = tr.parentNode;
        const prev = tr.previousElementSibling;
        if (prev && !prev.classList.contains('ligne-vide')) {{
            tbody.insertBefore(tr, prev);
            calculerTotaux();
        }}
    }}

    // Descendre une ligne (section, note ou produit)
    function descendreLigne(btn) {{
        const tr = btn.closest('tr');
        const tbody = tr.parentNode;
        const next = tr.nextElementSibling;
        if (next) {{
            tbody.insertBefore(next, tr);
            calculerTotaux();
        }}
    }}

    // Supprimer une ligne (section, note ou produit)
    function supprimerLigne(btn) {{
        const tr = btn.closest('tr');
        if (tr) {{
            tr.remove();
            calculerTotaux();
            updateLignesCount();

            // Si plus aucune ligne, afficher la ligne vide
            const tbody = document.getElementById('lignes-table');
            const remainingRows = tbody.querySelectorAll('tr:not(.ligne-vide)');
            if (remainingRows.length === 0) {{
                const videRow = document.createElement('tr');
                videRow.className = 'ligne-vide';
                videRow.innerHTML = '<td colspan="9" style="text-align:center; padding: 40px; color: #9CA3AF;">Aucune ligne. Cliquez sur "Ajouter un produit" pour commencer.</td>';
                tbody.appendChild(videRow);
            }}
        }}
    }}

    function collectDocumentData() {{
        // Mapper les conditions de paiement vers le format API
        const conditionsMap = {{
            'immediate': 'IMMEDIATE',
            '30j': 'NET_30',
            '45j': 'NET_45',
            '60j': 'NET_60'
        }};
        const conditionsValue = document.getElementById('conditions').value || 'immediate';

        // Collecter d'abord les lignes (produits, sections, notes)
        const lignesData = [];
        let lineNumber = 1;
        let subtotalCalc = 0;
        let taxAmountCalc = 0;

        document.querySelectorAll('#lignes-table tr:not(.ligne-vide)').forEach(tr => {{
            // Ligne section (titre)
            if (tr.classList.contains('ligne-section')) {{
                const titleInput = tr.querySelector('.section-title-input');
                if (titleInput && titleInput.value.trim()) {{
                    lignesData.push({{
                        line_number: lineNumber++,
                        line_type: 'section',
                        description: titleInput.value.trim(),
                        quantity: 0,
                        unit_price: 0,
                        subtotal: 0,
                        tax_amount: 0,
                        total: 0
                    }});
                }}
                return;
            }}

            // Ligne note (commentaire)
            if (tr.classList.contains('ligne-note')) {{
                const noteInput = tr.querySelector('.note-input');
                if (noteInput && noteInput.value.trim()) {{
                    lignesData.push({{
                        line_number: lineNumber++,
                        line_type: 'note',
                        description: noteInput.value.trim(),
                        quantity: 0,
                        unit_price: 0,
                        subtotal: 0,
                        tax_amount: 0,
                        total: 0
                    }});
                }}
                return;
            }}

            // Ligne produit standard
            const selects = tr.querySelectorAll('select');
            const inputs = tr.querySelectorAll('input[type="number"]');
            if (inputs.length >= 2 && selects.length >= 3) {{
                const produitSelect = selects[0];
                const selectedOption = produitSelect.options[produitSelect.selectedIndex];
                const productId = produitSelect.value || null;
                const productCode = selectedOption?.dataset?.code || '';
                const productName = selectedOption?.dataset?.nom || '';
                const prix = parseFloat(inputs[0].value) || 0;
                const qte = parseFloat(inputs[1].value) || 0;
                const parsedTVALine = parseFloat(selects[2]?.value);
                const tauxTVA = isNaN(parsedTVALine) ? {tva_default} : parsedTVALine;

                if (productId || prix > 0) {{
                    const subtotal = prix * qte;
                    const taxAmount = subtotal * (tauxTVA / 100);
                    subtotalCalc += subtotal;
                    taxAmountCalc += taxAmount;
                    lignesData.push({{
                        line_number: lineNumber++,
                        line_type: 'product',
                        product_id: productId,
                        product_code: productCode,
                        description: productName,
                        quantity: qte,
                        unit_price: prix,
                        tax_rate: tauxTVA,
                        subtotal: subtotal,
                        tax_amount: taxAmount,
                        total: subtotal + taxAmount
                    }});
                }}
            }}
        }});

        // Collecter les données des options
        const remiseType = document.getElementById('remise_type')?.value || '';
        const remiseValue = parseFloat(document.getElementById('remise_value')?.value) || 0;
        const livraisonType = document.querySelector('input[name="livraison"]:checked')?.value || 'standard';
        const adresseDifferente = document.getElementById('adresse_differente')?.checked || false;
        const adresseLivraison = adresseDifferente ? document.getElementById('adresse_livraison')?.value : null;

        // Collecter les produits optionnels inclus
        const optionnelsInclus = Object.values(produitsOptionnels || {{}}).filter(opt => opt && opt.inclus).map(opt => ({{
            product_id: opt.productId,
            description: opt.productName,
            quantity: opt.quantite,
            unit_price: opt.prix,
            total: opt.total,
            optional: true
        }}));

        // Ajuster les totaux avec options
        const remiseAmount = remiseType === 'percent' ? subtotalCalc * (remiseValue / 100) : remiseValue;
        const optionnelsTotal = optionnelsInclus.reduce((sum, opt) => sum + opt.total, 0);
        const livraisonFraisVal = livraisonType === 'express' ? 15 : 0;
        const subtotalFinal = subtotalCalc - remiseAmount + optionnelsTotal + livraisonFraisVal;
        const taxAmountFinal = subtotalFinal * 0.20; // TVA simplifiée

        const data = {{
            // Inclure l'ID et le numéro si document existant
            id: window.existingData?.id || null,
            numero: window.existingData?.numero || null,
            customer_id: document.getElementById('client_id').value || null,
            date: window.existingData?.date || new Date().toISOString().split('T')[0],
            validity_date: document.getElementById('date_validite').value || null,
            billing_address: document.getElementById('adresse_facturation').value || null,
            delivery_address: adresseLivraison,
            payment_terms: conditionsMap[conditionsValue] || 'NET_30',
            reference: document.getElementById('reference_client')?.value || null,
            status: window.existingData?.status || 'BROUILLON',
            subtotal: subtotalFinal,
            tax_amount: taxAmountFinal,
            total: subtotalFinal + taxAmountFinal,
            discount_percent: remiseType === 'percent' ? remiseValue : 0,
            discount_amount: remiseAmount,
            lignes: lignesData,
            delivery_terms: livraisonType,
            assigned_to: document.getElementById('commercial_id')?.value || null,
            // Données supplémentaires pour les options
            custom_fields: {{
                livraison_type: livraisonType,
                livraison_frais: livraisonFraisVal,
                produits_optionnels: optionnelsInclus,
                code_promo: document.getElementById('code_promo')?.value || null
            }}
        }};

        return data;
    }}

    async function saveDocument() {{
        const saveBtn = document.querySelector('.btn-save[onclick="saveDocument()"]') || document.querySelector('.btn-primary[onclick="saveDocument()"]');
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

            // Determiner si c'est une creation ou une mise a jour
            const isUpdate = window.currentDocumentId && window.currentDocumentId !== 'null';
            const apiUrl = isUpdate ? `/api/{module_name}/${{window.currentDocumentId}}` : '/api/{module_name}';
            const method = isUpdate ? 'PUT' : 'POST';

            const response = await fetch(apiUrl, {{
                method: method,
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(data)
            }});

            if (response.ok) {{
                const result = await response.json();
                // Mettre a jour l'URL sans recharger (mode edition)
                const newId = result.id || window.currentDocumentId;
                if (newId && !window.location.pathname.includes(newId)) {{
                    // Premier enregistrement: mettre a jour l'URL pour mode edition
                    window.history.replaceState({{}}, '', '/ui/{module_name}/' + newId);
                    window.currentDocumentId = newId;
                    window.isEditMode = true;
                }}
                // Afficher un message de succes discret
                showSaveSuccess(isUpdate ? '{doc_type} mis a jour !' : '{doc_type} enregistre !');
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalText;
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

    // Envoyer par email au client
    async function envoyerParEmail() {{
        const clientSelect = document.getElementById('client_id');
        const clientId = clientSelect.value;

        if (!clientId) {{
            alert('Veuillez d\\'abord sélectionner un client');
            return;
        }}

        const lignes = document.querySelectorAll('#lignes-table tr:not(.ligne-vide)');
        if (lignes.length === 0) {{
            alert('Veuillez ajouter au moins une ligne avant d\\'envoyer');
            return;
        }}

        // Récupérer l'email du client
        try {{
            const urlParams = new URLSearchParams(window.location.search);
            const authToken = urlParams.get('token') || localStorage.getItem('access_token') || localStorage.getItem('auth_token') || '';

            // Vérifier si c'est un donneur d'ordre ou un client
            const selectedOption = clientSelect.options[clientSelect.selectedIndex];
            const isDonneurOrdre = selectedOption && selectedOption.dataset.type === 'donneur_ordre';
            const apiEndpoint = isDonneurOrdre ? 'donneur_ordre' : 'clients';

            const response = await fetch(`/api/${{apiEndpoint}}/${{clientId}}`, {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});

            if (!response.ok) {{
                console.error('Erreur API client:', response.status, response.statusText);
                alert('Impossible de récupérer les informations du client (erreur ' + response.status + ')');
                return;
            }}

            const client = await response.json();
            const email = client.email || client.custom_fields?.email || client.email_facturation;

            if (!email) {{
                alert('Ce client n\\'a pas d\\'adresse email enregistrée');
                return;
            }}

            const confirmed = confirm(`Envoyer ce {doc_type} à ${{email}} ?`);
            if (!confirmed) return;

            // Collecter les données du document
            const data = collectDocumentData();

            // Envoyer l'email via l'API
            const emailResponse = await fetch('/api/email/send-document', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    to: email,
                    document_type: '{doc_type}',
                    document_data: data,
                    client_id: clientId
                }})
            }});

            if (emailResponse.ok) {{
                alert('Email envoyé avec succès à ' + email);
            }} else {{
                const errorData = await emailResponse.json().catch(() => ({{}}));
                alert(errorData.detail || 'Erreur lors de l\\'envoi de l\\'email');
            }}
        }} catch (error) {{
            console.error('Erreur:', error);
            alert('Erreur lors de l\\'envoi de l\\'email');
        }}
    }}

    // Télécharger en PDF
    async function telechargerPDF() {{
        const clientId = document.getElementById('client_id').value;
        const lignes = document.querySelectorAll('#lignes-table tr:not(.ligne-vide)');

        if (!clientId) {{
            alert('Veuillez d\\'abord sélectionner un client');
            return;
        }}

        if (lignes.length === 0) {{
            alert('Veuillez ajouter au moins une ligne');
            return;
        }}

        try {{
            const data = collectDocumentData();

            const response = await fetch('/api/pdf/generate', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    document_type: '{doc_type}',
                    document_data: data
                }})
            }});

            if (response.ok) {{
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = '{doc_type.lower()}_' + new Date().toISOString().split('T')[0] + '.pdf';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }} else {{
                const errorData = await response.json().catch(() => ({{}}));
                alert(errorData.detail || 'Erreur lors de la génération du PDF');
            }}
        }} catch (error) {{
            console.error('Erreur:', error);
            alert('Erreur lors de la génération du PDF');
        }}
    }}

    // Imprimer le document
    // Imprimer = générer le PDF et l'ouvrir pour impression
    async function imprimerDocument() {{
        const clientId = document.getElementById('client_id').value;
        const lignes = document.querySelectorAll('#lignes-table tr:not(.ligne-vide)');

        if (!clientId) {{
            alert('Veuillez d\\'abord sélectionner un client');
            return;
        }}

        if (lignes.length === 0) {{
            alert('Veuillez ajouter au moins une ligne');
            return;
        }}

        try {{
            // Utiliser le même endpoint que télécharger PDF
            const data = collectDocumentData();

            const response = await fetch('/api/pdf/generate', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    document_type: '{doc_type}',
                    document_data: data
                }})
            }});

            if (response.ok) {{
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);

                // Ouvrir le PDF dans une nouvelle fenêtre pour impression
                const printWindow = window.open(url, '_blank');
                if (printWindow) {{
                    printWindow.onload = function() {{
                        printWindow.print();
                    }};
                }} else {{
                    // Si popup bloqué, télécharger le fichier
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = '{doc_type.lower()}_impression.pdf';
                    a.click();
                    alert('Popup bloqué. Le PDF a été téléchargé - ouvrez-le pour imprimer.');
                }}
            }} else {{
                const errorData = await response.json().catch(() => ({{}}));
                alert(errorData.detail || 'Erreur lors de la génération du PDF');
            }}
        }} catch (error) {{
            console.error('Erreur:', error);
            alert('Erreur lors de la génération du PDF pour impression');
        }}
    }}

    // Convertir un devis en commande
    async function convertirEnCommande() {{
        const devisId = window.location.pathname.split('/').pop();
        const clientId = document.getElementById('client_id')?.value;
        const lignes = document.querySelectorAll('#lignes-table tr:not(.ligne-vide)');

        if (!devisId || devisId === 'nouveau') {{
            alert('Veuillez d\\'abord enregistrer le devis avant de le convertir.');
            return;
        }}

        if (!clientId) {{
            alert('Veuillez sélectionner un client.');
            return;
        }}

        if (lignes.length === 0) {{
            alert('Veuillez ajouter au moins une ligne.');
            return;
        }}

        if (!confirm('Voulez-vous convertir ce devis en commande ?\\n\\nUne nouvelle commande sera créée avec les mêmes informations.')) {{
            return;
        }}

        try {{
            // Collecter les données du devis
            const devisData = collectDocumentData();

            // Préparer les données pour la commande
            const commandeData = {{
                customer_id: devisData.customer_id,
                devis_id: devisId,
                reference_client: devisData.reference || '',
                date_commande: new Date().toISOString().split('T')[0],
                status: 'CONFIRMEE',
                lignes: devisData.lines,
                total_ht: devisData.subtotal,
                total_tva: devisData.tax_amount,
                total_ttc: devisData.total,
                notes: devisData.notes || '',
                conditions: devisData.terms || ''
            }};

            // Créer la commande
            const response = await fetch('/api/commandes', {{
                method: 'POST',
                credentials: 'include',
                headers: {{
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify(commandeData)
            }});

            if (response.ok) {{
                const result = await response.json();
                const commandeId = result.id;
                const commandeNumber = result.number || 'Nouvelle commande';

                // Mettre à jour le statut du devis en CONVERTI
                await fetch(`/api/devis/${{devisId}}`, {{
                    method: 'PATCH',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        status: 'CONVERTI',
                        converted_to: 'commande',
                        converted_to_id: commandeId
                    }})
                }});

                alert(`✅ Commande ${{commandeNumber}} créée avec succès !`);

                // Rediriger vers la commande
                if (confirm('Voulez-vous ouvrir la commande ?')) {{
                    window.location.href = `/ui/commandes/${{commandeId}}`;
                }}
            }} else {{
                const errorData = await response.json().catch(() => ({{}}));
                alert('Erreur: ' + (errorData.detail || 'Impossible de créer la commande'));
            }}
        }} catch (error) {{
            console.error('Erreur:', error);
            alert('Erreur lors de la conversion en commande');
        }}
    }}

    function generatePrintContent() {{
        // Récupérer les infos du document
        const clientSelect = document.getElementById('client_id');
        const clientName = clientSelect.options[clientSelect.selectedIndex]?.text || 'Client';
        const clientAddress = clientSelect.options[clientSelect.selectedIndex]?.dataset?.adresse || '';
        const docNumber = document.getElementById('numero')?.value || 'NOUVEAU';
        const docDate = document.getElementById('date')?.value || new Date().toISOString().split('T')[0];
        const referenceClient = document.getElementById('reference_client')?.value || '';
        const validityDate = document.getElementById('validity_date')?.value || '';
        const notes = document.getElementById('notes')?.value || '';
        const conditions = document.getElementById('conditions')?.value || '';

        // Données entreprise (depuis window ou valeurs par défaut)
        const entreprise = window.entrepriseData || {{}};
        const entrepriseNom = entreprise.nom || entreprise.raison_sociale || 'Mon Entreprise';
        const entrepriseAdresse = entreprise.adresse || '';
        const entrepriseEmail = entreprise.email || '';
        const entrepriseTel = entreprise.telephone || '';
        const entrepriseSiret = entreprise.siret || '';
        const entrepriseTva = entreprise.tva_intra || '';

        const totalHT = document.getElementById('total-ht').textContent;
        const totalTVA = document.getElementById('total-tva').textContent;
        const totalTTC = document.getElementById('total-ttc').textContent;

        // Formater la date
        const formatDate = (dateStr) => {{
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return d.toLocaleDateString('fr-FR');
        }};

        // Construire les lignes avec sections et sous-totaux
        let lignesHTML = '';
        let currentSection = null;
        let sectionTotal = 0;

        document.querySelectorAll('#lignes-table tr:not(.ligne-vide)').forEach((tr) => {{
            // Ligne section
            if (tr.classList.contains('ligne-section')) {{
                // Afficher sous-total de la section précédente
                if (currentSection && sectionTotal > 0) {{
                    lignesHTML += `
                        <tr class="subtotal-row">
                            <td colspan="4" style="text-align: right; font-weight: bold; background: #f8f9fa;">Sous-total ${{currentSection}}</td>
                            <td style="text-align: right; font-weight: bold; background: #f8f9fa;">${{sectionTotal.toFixed(2).replace('.', ',')}} €</td>
                        </tr>
                    `;
                }}

                // Nouvelle section
                const titleInput = tr.querySelector('.section-title-input');
                currentSection = titleInput?.value || 'Section';
                sectionTotal = 0;

                lignesHTML += `
                    <tr class="section-row">
                        <td colspan="5" style="background: #1E3A8A; color: white; font-weight: bold; padding: 10px;">${{currentSection}}</td>
                    </tr>
                `;
                return;
            }}

            // Ligne note
            if (tr.classList.contains('ligne-note')) {{
                const noteInput = tr.querySelector('.note-input');
                const noteText = noteInput?.value || '';
                if (noteText) {{
                    lignesHTML += `
                        <tr class="note-row">
                            <td colspan="5" style="font-style: italic; color: #666; padding: 8px 12px;">${{noteText}}</td>
                        </tr>
                    `;
                }}
                return;
            }}

            // Ligne produit
            const inputs = tr.querySelectorAll('input[type="number"]');
            const selects = tr.querySelectorAll('select');
            const produitSelect = selects[0];
            const produitName = produitSelect?.options[produitSelect.selectedIndex]?.text || '';
            const prix = parseFloat(inputs[0]?.value) || 0;
            const qte = parseFloat(inputs[1]?.value) || 0;
            const unite = selects[1]?.value || 'Unité(s)';
            const tva = selects[2]?.value || '20';
            const montant = prix * qte;
            sectionTotal += montant;

            if (produitName || prix > 0) {{
                lignesHTML += `
                    <tr>
                        <td>${{produitName}}</td>
                        <td style="text-align: center;">${{qte.toFixed(2).replace('.', ',')}}<br/><small>${{unite}}</small></td>
                        <td style="text-align: right;">${{prix.toFixed(2).replace('.', ',')}}</td>
                        <td style="text-align: center;">TVA ${{tva}}%</td>
                        <td style="text-align: right; font-weight: bold;">${{montant.toFixed(2).replace('.', ',')}} €</td>
                    </tr>
                `;
            }}
        }});

        // Sous-total de la dernière section
        if (currentSection && sectionTotal > 0) {{
            lignesHTML += `
                <tr class="subtotal-row">
                    <td colspan="4" style="text-align: right; font-weight: bold; background: #f8f9fa;">Sous-total ${{currentSection}}</td>
                    <td style="text-align: right; font-weight: bold; background: #f8f9fa;">${{sectionTotal.toFixed(2).replace('.', ',')}} €</td>
                </tr>
            `;
        }}

        // Construire les infos document
        let docInfoHTML = `
            <tr><td><b>N° {doc_type}</b></td><td style="text-align: right;"><b>${{docNumber}}</b></td></tr>
        `;
        if (referenceClient) {{
            docInfoHTML += `<tr><td><b>Réf. client</b></td><td style="text-align: right;">${{referenceClient}}</td></tr>`;
        }}
        docInfoHTML += `<tr><td><b>Date</b></td><td style="text-align: right;">${{formatDate(docDate)}}</td></tr>`;
        if (validityDate) {{
            const dateLabel = '{doc_type}' === 'Devis' ? "Date d'expiration" : "Date d'échéance";
            docInfoHTML += `<tr><td><b>${{dateLabel}}</b></td><td style="text-align: right;">${{formatDate(validityDate)}}</td></tr>`;
        }}

        return `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{doc_type} ${{docNumber}}</title>
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; color: #333; font-size: 11px; }}

                    .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }}
                    .company-info {{ max-width: 50%; }}
                    .company-name {{ font-size: 18px; font-weight: bold; color: #1E3A8A; margin-bottom: 5px; }}
                    .company-details {{ color: #666; font-size: 10px; line-height: 1.4; }}
                    .doc-title {{ font-size: 24px; font-weight: bold; color: #1E3A8A; text-align: right; }}

                    .info-section {{ display: flex; justify-content: space-between; margin-bottom: 20px; gap: 20px; }}
                    .client-box {{ flex: 1; border: 1px solid #ddd; padding: 15px; background: white; }}
                    .client-box h4 {{ color: #1E3A8A; margin-bottom: 8px; font-size: 11px; }}
                    .client-name {{ font-weight: bold; margin-bottom: 5px; }}

                    .doc-info-box {{ width: 220px; background: #EFF6FF; border: 1px solid #ddd; }}
                    .doc-info-box table {{ width: 100%; border-collapse: collapse; }}
                    .doc-info-box td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 10px; }}
                    .doc-info-box tr:last-child td {{ border-bottom: none; }}

                    .lines-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                    .lines-table th {{ background: #1E3A8A; color: white; padding: 10px 8px; text-align: left; font-size: 10px; }}
                    .lines-table th:nth-child(2), .lines-table th:nth-child(4) {{ text-align: center; }}
                    .lines-table th:nth-child(3), .lines-table th:nth-child(5) {{ text-align: right; }}
                    .lines-table td {{ padding: 10px 8px; border-bottom: 1px solid #eee; vertical-align: middle; }}
                    .lines-table tbody tr:nth-child(even) {{ background: #F8FAFC; }}

                    .totals-section {{ display: flex; justify-content: flex-end; margin-bottom: 20px; }}
                    .totals-box {{ width: 250px; border: 1px solid #ddd; }}
                    .totals-box table {{ width: 100%; border-collapse: collapse; }}
                    .totals-box td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
                    .totals-box tr:last-child {{ background: #EFF6FF; }}
                    .totals-box tr:last-child td {{ border-bottom: none; font-weight: bold; font-size: 12px; }}

                    .notes-section {{ margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 4px; }}
                    .notes-section h4 {{ color: #1E3A8A; margin-bottom: 8px; }}
                    .notes-section p {{ white-space: pre-wrap; line-height: 1.5; }}

                    .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; text-align: center; color: #666; font-size: 9px; }}

                    @media print {{
                        body {{ padding: 15px; }}
                        .no-print {{ display: none; }}
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="company-info">
                        <div class="company-name">${{entrepriseNom}}</div>
                        <div class="company-details">
                            ${{entrepriseAdresse ? entrepriseAdresse + '<br/>' : ''}}
                            ${{entrepriseEmail}}${{entrepriseTel ? ' | ' + entrepriseTel : ''}}
                        </div>
                    </div>
                    <div class="doc-title">{doc_type}</div>
                </div>

                <div class="info-section">
                    <div class="client-box">
                        <h4>Client</h4>
                        <div class="client-name">${{clientName}}</div>
                        ${{clientAddress ? `<div>${{clientAddress}}</div>` : ''}}
                    </div>
                    <div class="doc-info-box">
                        <table>${{docInfoHTML}}</table>
                    </div>
                </div>

                <table class="lines-table">
                    <thead>
                        <tr>
                            <th style="width: 40%;">Description</th>
                            <th style="width: 15%;">Quantité</th>
                            <th style="width: 15%;">Prix unit.</th>
                            <th style="width: 15%;">Taxes</th>
                            <th style="width: 15%;">Montant</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${{lignesHTML}}
                    </tbody>
                </table>

                <div class="totals-section">
                    <div class="totals-box">
                        <table>
                            <tr>
                                <td>Sous-total HT</td>
                                <td style="text-align: right;">${{totalHT}}</td>
                            </tr>
                            <tr>
                                <td>TVA</td>
                                <td style="text-align: right;">${{totalTVA}}</td>
                            </tr>
                            <tr>
                                <td><b>Total TTC</b></td>
                                <td style="text-align: right;"><b>${{totalTTC}}</b></td>
                            </tr>
                        </table>
                    </div>
                </div>

                ${{notes ? `<div class="notes-section"><h4>Notes</h4><p>${{notes}}</p></div>` : ''}}
                ${{conditions ? `<div class="notes-section"><h4>Conditions</h4><p>${{conditions}}</p></div>` : ''}}

                <div class="footer">
                    <p>${{entrepriseNom}}${{entrepriseSiret ? ' - SIRET: ' + entrepriseSiret : ''}}${{entrepriseTva ? ' - TVA: ' + entrepriseTva : ''}}</p>
                </div>
            </body>
            </html>
        `;
    }}

    // ========== FONCTIONS OPTIONS ==========

    // Variables pour les options
    let remiseActuelle = 0;
    let livraisonFrais = 0;
    let produitsOptionnels = [];
    let optionnelIndex = 0;

    // Mettre à jour la remise
    function updateRemise() {{
        const type = document.getElementById('remise_type').value;
        const value = parseFloat(document.getElementById('remise_value').value) || 0;
        const totalHTElement = document.getElementById('total-ht');
        const totalHT = parseFloat(totalHTElement.textContent.replace(/[^0-9.,]/g, '').replace(',', '.')) || 0;

        let remise = 0;
        if (type === 'percent') {{
            remise = totalHT * (value / 100);
        }} else if (type === 'amount') {{
            remise = value;
        }}

        remiseActuelle = remise;
        document.getElementById('remise_calculee').value = remise.toFixed(2).replace('.', ',') + ' €';

        // Recalculer les totaux avec la remise
        recalculerTotauxAvecOptions();
    }}

    // Appliquer un code promo
    function appliquerCodePromo() {{
        const code = document.getElementById('code_promo').value.trim().toUpperCase();

        if (!code) {{
            alert('Veuillez entrer un code promo');
            return;
        }}

        // Codes promo prédéfinis (à remplacer par API)
        const codesPromo = {{
            'BIENVENUE10': {{ type: 'percent', value: 10 }},
            'ETE2024': {{ type: 'percent', value: 15 }},
            'FIDELE20': {{ type: 'percent', value: 20 }},
            'REDUCTION50': {{ type: 'amount', value: 50 }}
        }};

        const promo = codesPromo[code];
        if (promo) {{
            document.getElementById('remise_type').value = promo.type;
            document.getElementById('remise_value').value = promo.value;
            updateRemise();
            alert('Code promo "' + code + '" appliqué avec succès !');
        }} else {{
            alert('Code promo invalide ou expiré');
        }}
    }}

    // Mettre à jour les options de livraison
    function updateLivraison() {{
        const livraison = document.querySelector('input[name="livraison"]:checked')?.value || 'standard';

        // Frais de livraison
        const fraisLivraison = {{
            'standard': 0,
            'express': 15,
            'sursite': 0 // Sur devis = à définir manuellement
        }};

        livraisonFrais = fraisLivraison[livraison] || 0;
        recalculerTotauxAvecOptions();
    }}

    // Afficher/masquer l'adresse de livraison
    function toggleAdresseLivraison() {{
        const checkbox = document.getElementById('adresse_differente');
        const section = document.getElementById('adresse_livraison_section');
        section.style.display = checkbox.checked ? 'grid' : 'none';
    }}

    // Ajouter un produit optionnel
    function ajouterProduitOptionnel() {{
        const container = document.getElementById('produits-optionnels-list');

        const div = document.createElement('div');
        div.className = 'azal-optional-product';
        div.id = 'optionnel-' + optionnelIndex;
        div.innerHTML = `
            <input type="checkbox" onchange="toggleProduitOptionnel(this)" data-index="${{optionnelIndex}}">
            <select class="input" style="flex: 2;" onchange="updateProduitOptionnel(this, ${{optionnelIndex}})">
                ${{getProduitsOptions()}}
            </select>
            <input type="number" class="input" placeholder="Qté" value="1" min="1" style="width: 80px;" onchange="updateProduitOptionnel(this.previousElementSibling, ${{optionnelIndex}})">
            <span class="azal-optional-product-price" id="optionnel-prix-${{optionnelIndex}}">0,00 €</span>
            <button type="button" class="azal-optional-product-remove" onclick="supprimerProduitOptionnel(${{optionnelIndex}})">
                <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        `;
        container.appendChild(div);
        optionnelIndex++;
    }}

    // Mettre à jour un produit optionnel
    function updateProduitOptionnel(select, index) {{
        const container = document.getElementById('optionnel-' + index);
        if (!container) return;

        const selectedOption = select.options[select.selectedIndex];
        const prix = parseFloat(selectedOption?.dataset?.pu1) || 0;
        const qteInput = container.querySelector('input[type="number"]');
        const qte = parseFloat(qteInput?.value) || 1;
        const total = prix * qte;

        document.getElementById('optionnel-prix-' + index).textContent = total.toFixed(2).replace('.', ',') + ' €';

        // Mettre à jour le tableau des produits optionnels
        produitsOptionnels[index] = {{
            productId: select.value,
            productName: selectedOption?.dataset?.nom || '',
            prix: prix,
            quantite: qte,
            total: total,
            inclus: container.querySelector('input[type="checkbox"]').checked
        }};

        recalculerTotauxAvecOptions();
    }}

    // Activer/désactiver un produit optionnel
    function toggleProduitOptionnel(checkbox) {{
        const index = parseInt(checkbox.dataset.index);
        if (produitsOptionnels[index]) {{
            produitsOptionnels[index].inclus = checkbox.checked;
        }}
        recalculerTotauxAvecOptions();
    }}

    // Supprimer un produit optionnel
    function supprimerProduitOptionnel(index) {{
        const element = document.getElementById('optionnel-' + index);
        if (element) {{
            element.remove();
            delete produitsOptionnels[index];
            recalculerTotauxAvecOptions();
        }}
    }}

    // Recalculer les totaux avec options
    function recalculerTotauxAvecOptions() {{
        // D'abord calculer les totaux de base (lignes)
        let sousTotal = 0;
        let totalTVABase = 0;

        document.querySelectorAll('#lignes-table tr:not(.ligne-vide):not(.ligne-section):not(.ligne-note)').forEach(tr => {{
            const inputs = tr.querySelectorAll('input[type="number"]');
            const selects = tr.querySelectorAll('select');
            if (inputs.length >= 2) {{
                const prix = parseFloat(inputs[0].value) || 0;
                const qte = parseFloat(inputs[1].value) || 0;
                const tvaSelect = selects[2];
                const parsedTVA = parseFloat(tvaSelect?.value);
                const tauxTVA = isNaN(parsedTVA) ? {tva_default} : parsedTVA;
                const montantHT = prix * qte;
                const montantTVA = montantHT * (tauxTVA / 100);
                sousTotal += montantHT;
                totalTVABase += montantTVA;
                const montantEl = tr.querySelector('.montant');
                if (montantEl) montantEl.textContent = montantHT.toFixed(2) + ' EUR';
            }}
        }});

        // Ajouter les produits optionnels cochés
        let optionnelsTotal = 0;
        Object.values(produitsOptionnels).forEach(opt => {{
            if (opt && opt.inclus) {{
                optionnelsTotal += opt.total;
            }}
        }});

        // Afficher le sous-total
        const sousTotalEl = document.getElementById('sous-total-ht');
        if (sousTotalEl) sousTotalEl.textContent = sousTotal.toFixed(2) + ' EUR';

        // Afficher la remise si applicable
        const rowRemise = document.getElementById('row-remise');
        const totalRemiseEl = document.getElementById('total-remise');
        if (remiseActuelle > 0) {{
            rowRemise.style.display = 'flex';
            totalRemiseEl.textContent = '-' + remiseActuelle.toFixed(2) + ' EUR';
        }} else {{
            rowRemise.style.display = 'none';
        }}

        // Afficher les frais de livraison si applicable
        const rowLivraison = document.getElementById('row-livraison');
        const totalLivraisonEl = document.getElementById('total-livraison');
        if (livraisonFrais > 0) {{
            rowLivraison.style.display = 'flex';
            totalLivraisonEl.textContent = '+' + livraisonFrais.toFixed(2) + ' EUR';
        }} else {{
            rowLivraison.style.display = 'none';
        }}

        // Afficher les optionnels si applicable
        const rowOptionnels = document.getElementById('row-optionnels');
        const totalOptionnelsEl = document.getElementById('total-optionnels');
        if (optionnelsTotal > 0) {{
            rowOptionnels.style.display = 'flex';
            totalOptionnelsEl.textContent = '+' + optionnelsTotal.toFixed(2) + ' EUR';
        }} else {{
            rowOptionnels.style.display = 'none';
        }}

        // Calculer le total HT final
        let totalHT = sousTotal - remiseActuelle + livraisonFrais + optionnelsTotal;
        if (totalHT < 0) totalHT = 0;

        // Calculer la TVA (taux moyen basé sur les lignes)
        const tauxMoyen = sousTotal > 0 ? (totalTVABase / sousTotal) : 0.20;
        const totalTVA = totalHT * tauxMoyen;

        const ttc = totalHT + totalTVA;

        document.getElementById('total-ht').textContent = totalHT.toFixed(2) + ' EUR';
        document.getElementById('total-tva').textContent = totalTVA.toFixed(2) + ' EUR';
        document.getElementById('total-ttc').textContent = ttc.toFixed(2) + ' EUR';
    }}

    // ========== FIN FONCTIONS OPTIONS ==========

    // Charger les clients au chargement de la page
    document.addEventListener('DOMContentLoaded', async function() {{
        const urlParams = new URLSearchParams(window.location.search);
        const authToken = urlParams.get('token') || '';

        // Charger les données entreprise pour l'impression
        try {{
            const respEntreprise = await fetch('/api/entreprise', {{
                credentials: 'include',
                headers: {{ 'Authorization': 'Bearer ' + authToken }}
            }});
            if (respEntreprise.ok) {{
                const dataEntreprise = await respEntreprise.json();
                const entreprises = dataEntreprise.items || dataEntreprise || [];
                window.entrepriseData = entreprises[0] || {{}};
            }}
        }} catch (e) {{
            console.log('Info entreprise non chargée:', e);
            window.entrepriseData = {{}};
        }}

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

        // Charger les donneurs d'ordre et les ajouter au select client
        try {{
            const respDonneurs = await fetch('/api/donneur_ordre', {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});
            if (respDonneurs.ok) {{
                const dataDonneurs = await respDonneurs.json();
                const donneurs = dataDonneurs.items || dataDonneurs || [];
                const select = document.getElementById('client_id');
                if (donneurs.length > 0) {{
                    // Ajouter un séparateur
                    const separator = document.createElement('option');
                    separator.disabled = true;
                    separator.textContent = '── Donneurs d\\'ordre ──';
                    select.appendChild(separator);
                    // Ajouter les donneurs d'ordre
                    donneurs.forEach(donneur => {{
                        const option = document.createElement('option');
                        option.value = donneur.id;
                        option.textContent = donneur.nom || donneur.name || donneur.code || donneur.id;
                        option.dataset.type = 'donneur_ordre';
                        select.appendChild(option);
                    }});
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement donneurs d\\'ordre:', e);
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
                // Activer le bouton ajouter produit
                const btnAjouterProduit = document.getElementById('btn-ajouter-produit');
                if (btnAjouterProduit) {{
                    btnAjouterProduit.disabled = false;
                    btnAjouterProduit.title = '';
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement produits:', e);
            window.produitsData = [];
            // Activer quand même le bouton pour permettre saisie manuelle
            const btnAjouterProduit = document.getElementById('btn-ajouter-produit');
            if (btnAjouterProduit) {{
                btnAjouterProduit.disabled = false;
                btnAjouterProduit.title = 'Produits non chargés - saisie manuelle possible';
            }}
        }}

        // Charger les commerciaux (employés)
        try {{
            const respCommerciaux = await fetch('/api/employes', {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});
            if (respCommerciaux.ok) {{
                const dataCommerciaux = await respCommerciaux.json();
                const commerciaux = dataCommerciaux.items || dataCommerciaux || [];
                const selectCommercial = document.getElementById('commercial_id');
                if (selectCommercial && commerciaux.length > 0) {{
                    commerciaux.forEach(emp => {{
                        const option = document.createElement('option');
                        option.value = emp.id;
                        const nom = emp.prenom && emp.nom ? `${{emp.prenom}} ${{emp.nom}}` : (emp.nom || emp.name || emp.matricule);
                        option.textContent = nom;
                        selectCommercial.appendChild(option);
                    }});
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement commerciaux:', e);
        }}

        // Charger les comptes bancaires
        try {{
            const respBanques = await fetch('/api/comptes_bancaires', {{
                credentials: 'include',
                headers: {{
                    'Authorization': 'Bearer ' + authToken
                }}
            }});
            if (respBanques.ok) {{
                const dataBanques = await respBanques.json();
                const banques = dataBanques.items || dataBanques || [];
                const selectBanque = document.getElementById('banque_destinataire');
                if (selectBanque && banques.length > 0) {{
                    banques.forEach(bq => {{
                        const option = document.createElement('option');
                        option.value = bq.id;
                        const label = bq.iban ? `${{bq.iban}} - ${{bq.libelle || bq.code}}` : (bq.libelle || bq.code);
                        option.textContent = label;
                        selectBanque.appendChild(option);
                    }});
                }}
            }}
        }} catch (e) {{
            console.error('Erreur chargement comptes bancaires:', e);
        }}

        // Date par defaut : aujourd'hui + 30 jours (sauf en mode edition)
        const dateValidite = document.getElementById('date_validite');
        if (!window.existingData) {{
            const today = new Date();
            today.setDate(today.getDate() + 30);
            dateValidite.value = today.toISOString().split('T')[0];
        }}

        // Charger les donnees existantes en mode edition
        if (window.existingData && window.isEditMode) {{
            loadExistingData(window.existingData);
        }}
    }});

    // Fonction pour charger les donnees existantes dans le formulaire
    function loadExistingData(data) {{
        console.log('Chargement donnees existantes:', data);

        // Client
        if (data.customer_id || data.client_id) {{
            const clientSelect = document.getElementById('client_id');
            if (clientSelect) {{
                clientSelect.value = data.customer_id || data.client_id;
            }}
        }}

        // Date de validite
        if (data.validity_date || data.date_validite) {{
            const dateValidite = document.getElementById('date_validite');
            if (dateValidite) {{
                const dateVal = data.validity_date || data.date_validite;
                if (dateVal) {{
                    dateValidite.value = dateVal.split('T')[0];
                }}
            }}
        }}

        // Adresse facturation
        if (data.billing_address || data.adresse_facturation) {{
            const adresseInput = document.getElementById('adresse_facturation');
            if (adresseInput) {{
                adresseInput.value = data.billing_address || data.adresse_facturation || '';
            }}
        }}

        // Reference client
        if (data.reference || data.reference_client) {{
            const refInput = document.getElementById('reference_client');
            if (refInput) {{
                refInput.value = data.reference || data.reference_client || '';
            }}
        }}

        // Commercial
        if (data.assigned_to || data.commercial_id) {{
            const commercialSelect = document.getElementById('commercial_id');
            if (commercialSelect) {{
                commercialSelect.value = data.assigned_to || data.commercial_id;
            }}
        }}

        // Conditions de paiement
        if (data.payment_terms || data.conditions_paiement) {{
            const conditionsRadios = document.querySelectorAll('input[name="conditions_paiement"]');
            const value = data.payment_terms || data.conditions_paiement;
            conditionsRadios.forEach(radio => {{
                if (radio.value === value) {{
                    radio.checked = true;
                }}
            }});
        }}

        // Banque destinataire
        if (data.bank_account_id || data.banque_destinataire) {{
            const banqueSelect = document.getElementById('banque_destinataire');
            if (banqueSelect) {{
                banqueSelect.value = data.bank_account_id || data.banque_destinataire;
            }}
        }}

        // Notes
        if (data.notes) {{
            const notesInput = document.getElementById('notes');
            if (notesInput) {{
                notesInput.value = data.notes;
            }}
        }}

        // Conditions
        if (data.terms || data.conditions) {{
            const conditionsInput = document.getElementById('conditions');
            if (conditionsInput) {{
                conditionsInput.value = data.terms || data.conditions || '';
            }}
        }}

        // Options - Remise
        if (data.discount_percent || data.discount_amount) {{
            if (data.discount_percent) {{
                const remisePercent = document.getElementById('remise_percent');
                if (remisePercent) {{
                    const radio = document.querySelector('input[name="remise_type"][value="percent"]');
                    if (radio) radio.checked = true;
                    remisePercent.value = data.discount_percent;
                }}
            }} else if (data.discount_amount) {{
                const remiseFixe = document.getElementById('remise_fixe');
                if (remiseFixe) {{
                    const radio = document.querySelector('input[name="remise_type"][value="fixe"]');
                    if (radio) radio.checked = true;
                    remiseFixe.value = data.discount_amount;
                }}
            }}
        }}

        // Options - Livraison
        if (data.delivery_terms || data.custom_fields?.livraison_type) {{
            const livraisonType = data.delivery_terms || data.custom_fields?.livraison_type || 'sursite';
            const livraisonRadio = document.querySelector(`input[name="livraison"][value="${{livraisonType}}"]`);
            if (livraisonRadio) {{
                livraisonRadio.checked = true;
                updateLivraison();
            }}
        }}

        // Adresse de livraison differente
        if (data.delivery_address || data.adresse_livraison) {{
            const adresseDiff = document.getElementById('adresse_differente');
            const adresseLivraisonInput = document.getElementById('adresse_livraison');
            const adresseLivraisonSection = document.getElementById('adresse_livraison_section');
            if (adresseDiff && adresseLivraisonInput) {{
                adresseDiff.checked = true;
                adresseLivraisonInput.value = data.delivery_address || data.adresse_livraison || '';
                if (adresseLivraisonSection) {{
                    adresseLivraisonSection.style.display = 'block';
                }}
            }}
        }}

        // Charger les lignes
        if (data.lignes && Array.isArray(data.lignes)) {{
            data.lignes.forEach(ligne => {{
                ajouterLigneAvecDonnees(ligne);
            }});
            calculerTotaux();
        }}
    }}

    // Ajouter une ligne avec des donnees pre-remplies
    function ajouterLigneAvecDonnees(ligne) {{
        const tbody = document.getElementById('lignes-table');
        const videRow = tbody.querySelector('.ligne-vide');
        if (videRow) videRow.remove();

        const tr = document.createElement('tr');
        const lineType = ligne.line_type || 'product';

        // Ligne section (titre)
        if (lineType === 'section') {{
            tr.className = 'ligne-section';
            tr.innerHTML = `
                <td colspan="7" style="background: var(--azal-primary-light, #3B82F6); background: linear-gradient(90deg, var(--azal-primary, #1E3A8A) 0%, var(--azal-primary-light, #3B82F6) 100%);">
                    <input type="text" class="input section-title-input" value="${{ligne.description || ''}}" placeholder="Titre de la section..."
                        style="background: transparent; border: none; color: white; font-weight: 600; font-size: 14px; width: 100%; padding: 8px 12px;">
                </td>
                <td style="background: var(--azal-primary-light, #3B82F6); text-align: center; white-space: nowrap;">
                    <button type="button" class="btn-move" onclick="monterLigne(this)" title="Monter" style="color: white; background: transparent; border: none; cursor: pointer; padding: 4px;">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
                        </svg>
                    </button>
                    <button type="button" class="btn-move" onclick="descendreLigne(this)" title="Descendre" style="color: white; background: transparent; border: none; cursor: pointer; padding: 4px;">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>
                </td>
                <td style="background: var(--azal-primary-light, #3B82F6);">
                    <button type="button" class="btn-delete" onclick="supprimerLigne(this)" title="Supprimer" style="color: white;">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
            ligneIndex++;
            updateLignesCount();
            return;
        }}

        // Ligne note (commentaire)
        if (lineType === 'note') {{
            tr.className = 'ligne-note';
            tr.innerHTML = `
                <td colspan="7" style="background: #FEF3C7; border-left: 4px solid #F59E0B;">
                    <textarea class="input note-input" placeholder="Ajouter une note ou un commentaire..." rows="2"
                        style="background: transparent; border: none; width: 100%; resize: vertical; font-style: italic; color: #92400E;">${{ligne.description || ''}}</textarea>
                </td>
                <td style="background: #FEF3C7; text-align: center; white-space: nowrap;">
                    <button type="button" class="btn-move" onclick="monterLigne(this)" title="Monter" style="color: #92400E; background: transparent; border: none; cursor: pointer; padding: 4px;">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
                        </svg>
                    </button>
                    <button type="button" class="btn-move" onclick="descendreLigne(this)" title="Descendre" style="color: #92400E; background: transparent; border: none; cursor: pointer; padding: 4px;">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>
                </td>
                <td style="background: #FEF3C7;">
                    <button type="button" class="btn-delete" onclick="supprimerLigne(this)" title="Supprimer">
                        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
            ligneIndex++;
            updateLignesCount();
            return;
        }}

        // Ligne produit standard (7 colonnes: Produit, Tarif, Prix, Qte, TVA, Montant, Actions)
        tr.innerHTML = `
            <td><select class="input" onchange="onProduitChange(this)" style="width:100%">${{getProduitsOptions()}}</select></td>
            <td>
                <select class="input niveau-prix" style="width:100%" onchange="onNiveauPrixChange(this)">
                    <option value="pu1">PU1</option>
                    <option value="pu2">PU2</option>
                    <option value="pu3">PU3</option>
                </select>
            </td>
            <td><input type="number" class="input" style="width:100%" value="${{ligne.prix_unitaire || ligne.unit_price || 0}}" min="0" step="0.01" onchange="calculerTotaux()"></td>
            <td><input type="number" class="input" style="width:100%" value="${{ligne.quantite || ligne.quantity || 1}}" min="0" step="1" onchange="calculerTotaux()"></td>
            <td>
                <select class="input tva-select" style="width:100%" onchange="calculerTotaux()">
                    {tva_options_html}
                </select>
            </td>
            <td class="montant" style="text-align:right; font-weight:600;">0.00 EUR</td>
            <td>
                <button type="button" class="btn-delete" onclick="supprimerLigne(this)" title="Supprimer">
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
            </td>
        `;

        tbody.appendChild(tr);

        // Selectionner le produit si product_id existe
        if (ligne.product_id || ligne.produit_id) {{
            const produitSelect = tr.querySelector('select');
            if (produitSelect) {{
                produitSelect.value = ligne.product_id || ligne.produit_id;
            }}
        }}

        // Selectionner le taux TVA
        if (ligne.taux_tva || ligne.tax_rate) {{
            const tvaSelect = tr.querySelectorAll('select')[2];
            if (tvaSelect) {{
                tvaSelect.value = ligne.taux_tva || ligne.tax_rate;
            }}
        }}

        ligneIndex++;
        updateLignesCount();
    }}

    // Gestion des onglets AZAL
    // Navigation par sidebar
    function switchTab(tabId) {{
        // Desactiver tous les onglets sidebar
        document.querySelectorAll('.azal-sidebar-item[data-tab]').forEach(t => t.classList.remove('active'));
        // Activer l'onglet cliqué
        const sidebarItem = document.querySelector(`.azal-sidebar-item[data-tab="${{tabId}}"]`);
        if (sidebarItem) sidebarItem.classList.add('active');

        // Masquer tous les contenus
        document.querySelectorAll('.azal-tab-content').forEach(c => c.classList.remove('active'));

        // Afficher le contenu correspondant
        const content = document.getElementById('tab-' + tabId);
        if (content) content.classList.add('active');
    }}

    document.querySelectorAll('.azal-sidebar-item[data-tab]').forEach(item => {{
        item.addEventListener('click', function() {{
            const tabId = this.dataset.tab;
            switchTab(tabId);
        }});
    }});

    // Compatibilité anciens onglets (si présents)
    document.querySelectorAll('.azal-tab').forEach(tab => {{
        tab.addEventListener('click', function() {{
            const tabId = this.dataset.tab;
            switchTab(tabId);
        }});
    }});

    // Auto-remplir les champs quand une relation est sélectionnée
    async function handleRelationAutofill(select) {{
        const autofillConfig = select.dataset.autofill;
        if (!autofillConfig || !select.value) return;

        let linkedModule = select.dataset.link;
        const selectedId = select.value;

        // Vérifier si c'est un donneur d'ordre
        const selectedOption = select.options[select.selectedIndex];
        const isDonneurOrdre = selectedOption && selectedOption.dataset.type === 'donneur_ordre';

        // Utiliser le bon endpoint API
        const apiEndpoint = isDonneurOrdre ? 'donneur_ordre' : linkedModule.toLowerCase();

        try {{
            const urlParams = new URLSearchParams(window.location.search);
            const authToken = urlParams.get('token') || localStorage.getItem('access_token') || localStorage.getItem('auth_token') || '';

            const response = await fetch(`/api/${{apiEndpoint}}/${{selectedId}}`, {{
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
                        let addressFields = parts[2].split('|');

                        // Pour les donneurs d'ordre, utiliser les champs de facturation ou principaux
                        if (isDonneurOrdre) {{
                            // Utiliser l'adresse de facturation SEULEMENT si elle est complète (ligne1 ET ville)
                            const hasBillingAddr = data.facturation_adresse_ligne1 && data.facturation_ville;
                            console.log('Donneur ordre - hasBillingAddr:', hasBillingAddr);
                            if (hasBillingAddr) {{
                                addressFields = ['facturation_adresse_ligne1', 'facturation_adresse_ligne2', 'facturation_code_postal', 'facturation_ville'];
                            }} else {{
                                addressFields = ['adresse_ligne1', 'adresse_ligne2', 'code_postal', 'ville'];
                            }}
                            console.log('Donneur ordre - using fields:', addressFields);
                        }}

                        const addressParts = [];
                        addressFields.forEach(f => {{
                            console.log('Checking field:', f, '=', data[f]);
                            if (data[f]) addressParts.push(data[f]);
                        }});
                        value = addressParts.join('\\n');
                        console.log('Composed address value:', value);
                    }} else {{
                        value = data[remoteField] || '';
                    }}

                    // Trouver le champ local et le remplir (toujours mettre à jour)
                    const input = document.querySelector(`[name="${{localField}}"]`);
                    if (input) {{
                        input.value = value;
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }});

                // Pour les donneurs d'ordre, remplir aussi les conditions de paiement
                if (isDonneurOrdre) {{
                    const conditionsSelect = document.querySelector('[name="conditions"]');
                    if (conditionsSelect && data.delai_paiement !== undefined) {{
                        const delai = parseInt(data.delai_paiement) || 0;
                        if (delai === 0) {{
                            conditionsSelect.value = 'immediate';
                        }} else if (delai <= 30) {{
                            conditionsSelect.value = '30j';
                        }} else if (delai <= 45) {{
                            conditionsSelect.value = '45j';
                        }} else {{
                            conditionsSelect.value = '60j';
                        }}
                        console.log('Conditions de paiement:', delai, 'jours ->', conditionsSelect.value);
                    }}
                }}

                console.log('Auto-fill appliqué depuis', isDonneurOrdre ? 'donneur_ordre' : linkedModule);
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

    # Pour les modules documents commerciaux, utiliser le formulaire document
    document_modules = ["devis", "factures", "facture", "avoirs", "avoir", "bons_livraison", "bon_livraison", "contrats", "contrat", "notes_frais", "note_frais"]
    if module_name.lower() in document_modules:
        # Passer les donnees existantes pour pre-remplir le formulaire
        html = generate_layout(
            title=f"Modifier {module.nom_affichage}",
            content=generate_document_form(module, module_name, existing_data=item),
            user=user,
            modules=get_all_modules()
        )
        return HTMLResponse(content=html)

    # Pour les interventions, utiliser le formulaire sectionné
    if module_name.lower() in ["interventions", "intervention"]:
        sections = organize_fields_into_sections(module)
        html = generate_layout(
            title=f"{module.nom_affichage} - Détail",
            content=generate_sectioned_form_edit(module_name, sections, module, item),
            user=user,
            modules=get_all_modules()
        )
        return HTMLResponse(content=html)

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
            <a href="/ui/{module_name}?sort=created_at&order=desc" class="text-muted">← Retour à la liste</a>
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
                {generate_module_action_buttons(module_name, item)}
            </div>
        </div>

        <!-- Print Header (visible only when printing) -->
        <div class="print-only print-header">
            <div class="print-header-content">
                <div class="print-company">
                    <div class="print-company-name">{APP_NAME}</div>
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
                {APP_NAME} - Document genere automatiquement
            </div>
        </div>

        <!-- Documents Section -->
        {documents_html}

        <script>
        function getCookie(name) {{
            const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
            return match ? match[2] : null;
        }}

        function getToken() {{
            const params = new URLSearchParams(window.location.search);
            return params.get('token')
                || localStorage.getItem('access_token')
                || localStorage.getItem('auth_token')
                || getCookie('access_token')
                || getCookie('token')
                || '';
        }}

        function openPrintPreview() {{
            // Ajouter classe pour mode aperçu
            document.body.classList.add('print-preview-mode');
            // Afficher le contenu print-only
            document.querySelectorAll('.print-only').forEach(el => el.style.display = 'block');
            document.querySelectorAll('.no-print').forEach(el => el.style.opacity = '0.3');
            // Notification
            alert('Aperçu avant impression. Cliquez sur Imprimer pour lancer l\\'impression ou fermez ce message pour revenir.');
            // Restaurer
            document.body.classList.remove('print-preview-mode');
            document.querySelectorAll('.print-only').forEach(el => el.style.display = '');
            document.querySelectorAll('.no-print').forEach(el => el.style.opacity = '');
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

            // Charger les options des champs relation (select)
            const authToken = getToken();
            const selectsWithLink = document.querySelectorAll('select[data-link]');

            selectsWithLink.forEach(async select => {{
                const linkedModule = select.dataset.link;
                const currentValue = select.dataset.currentValue || '';

                try {{
                    const url = `/api/select/${{linkedModule.toLowerCase()}}`;
                    const headers = {{ 'Content-Type': 'application/json' }};
                    if (authToken) {{
                        headers['Authorization'] = 'Bearer ' + authToken;
                    }}

                    const response = await fetch(url, {{
                        credentials: 'include',
                        headers: headers
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
                            opt.textContent = item.nom || item.name || item.raison_sociale || item.code || item.id;
                            // Comparaison robuste des UUIDs (ignore casse et tirets)
                            const itemIdNorm = String(item.id).toLowerCase().replace(/-/g, '');
                            const currentNorm = String(currentValue).toLowerCase().replace(/-/g, '');
                            if (currentValue && itemIdNorm === currentNorm) {{
                                opt.selected = true;
                            }}
                            select.appendChild(opt);
                        }});
                    }}
                }} catch (e) {{
                    console.error('Erreur chargement ' + select.name + ':', e);
                }}
            }});
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
    status_options: str = "",
    sort_fields: list = None,
    current_sort: str = "",
    current_order: str = "desc"
) -> str:
    """Génère une liste avec actions en masse et sélecteur de tri."""

    # Générer le sélecteur de tri
    sort_selector_html = ""
    if sort_fields:
        sort_options = '<option value="">Trier par...</option>'
        for field_name, field_label in sort_fields:
            selected_asc = 'selected' if current_sort == field_name and current_order == 'asc' else ''
            selected_desc = 'selected' if current_sort == field_name and current_order == 'desc' else ''
            sort_options += f'<option value="{field_name}:asc" {selected_asc}>{field_label} ↑</option>'
            sort_options += f'<option value="{field_name}:desc" {selected_desc}>{field_label} ↓</option>'

        sort_selector_html = f'''
        <div class="sort-selector">
            <select id="sort-select" class="form-select" onchange="applySortSelection(this.value)" style="width: auto; min-width: 180px;">
                {sort_options}
            </select>
        </div>
        '''

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

    # Bouton création standard (fenêtre normale)
    nouveau_btn = f'<a href="/ui/{module_name}/nouveau" class="btn btn-primary">+ Nouveau</a>'
    wizard_html = ''

    return f'''
    <div class="list-container">
        <div class="list-toolbar">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Rechercher..." class="form-control">
            </div>
            {sort_selector_html}
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

    <style>
        .list-toolbar {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .sort-selector select {{
            padding: 8px 12px;
            border: 1px solid var(--gray-300, #ddd);
            border-radius: 6px;
            background: white;
            font-size: 14px;
            cursor: pointer;
        }}
        .sort-selector select:focus {{
            outline: none;
            border-color: var(--primary-color, #007bff);
            box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
        }}
        .sortable {{
            cursor: pointer;
            user-select: none;
        }}
        .sortable:hover {{
            background-color: var(--hover-bg, #f0f0f0);
        }}
        .sort-icon {{
            font-size: 0.8em;
            margin-left: 4px;
            color: var(--primary-color, #007bff);
        }}
        .cell-with-actions {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .action-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 4px;
            text-decoration: none;
            font-size: 14px;
            opacity: 0.7;
            transition: opacity 0.2s, background-color 0.2s;
        }}
        .action-btn:hover {{
            opacity: 1;
            background-color: var(--hover-bg, #f0f0f0);
        }}
        .quick-actions {{
            display: flex;
            gap: 4px;
            margin-top: 4px;
        }}
        .quick-action-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 16px;
            background-color: var(--primary-light, #e3f2fd);
            transition: all 0.2s;
        }}
        .quick-action-btn:hover {{
            background-color: var(--primary-color, #1976d2);
            transform: scale(1.1);
        }}
    </style>

    <script>
        function sortBy(field, order) {{
            const url = new URL(window.location.href);
            url.searchParams.set('sort', field);
            url.searchParams.set('order', order);
            window.location.href = url.toString();
        }}

        function applySortSelection(value) {{
            if (!value) return;
            const [field, order] = value.split(':');
            sortBy(field, order);
        }}

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

        // Récupérer le token depuis l'URL, localStorage ou cookies
        function getCookie(name) {{
            const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
            return match ? match[2] : null;
        }}

        function getToken() {{
            const params = new URLSearchParams(window.location.search);
            return params.get('token')
                || localStorage.getItem('access_token')
                || localStorage.getItem('auth_token')
                || getCookie('access_token')
                || getCookie('token')
                || '';
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
    <title>{title} - {APP_NAME}</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
    <link rel="apple-touch-icon" href="/static/logo.png">
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
    <link rel="stylesheet" href="/assets/style.css?v=9785f">
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
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="24" height="24" class="sidebar-logo-icon">
                    <circle cx="256" cy="256" r="256" fill="#3454D1"/>
                    <circle cx="380" cy="120" r="24" fill="#6B9FFF"/>
                    <text x="200" y="360" font-family="Inter, Montserrat, Arial, sans-serif" font-weight="800" font-size="280" fill="#FFFFFF">A</text>
                    <text x="340" y="280" font-family="Inter, Montserrat, Arial, sans-serif" font-weight="700" font-size="140" fill="#FFFFFF">+</text>
                </svg>
                <span>{APP_NAME}</span>
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
                    <a href="/ui/parametres/utilisateur" class="nav-item">
                        <span class="nav-icon">👤</span>
                        <span>Mon compte</span>
                    </a>
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
                <a href="/ui/parametres/utilisateur" class="user-box" style="text-decoration: none; cursor: pointer;" title="Paramètres utilisateur">
                    <div class="user-avatar">{initials}</div>
                    <div>
                        <div class="user-name">{user.get('nom', 'Utilisateur')}</div>
                        <div class="user-email">{user.get('email', '')}</div>
                    </div>
                    <span class="user-settings-icon">⚙️</span>
                </a>
                <a href="/login" onclick="localStorage.clear();" class="nav-item" style="margin-top: 8px; color: var(--gray-500);">
                    <span class="nav-icon">🚪</span>
                    <span>Déconnexion</span>
                </a>
            </div>
        </aside>

        <!-- Main content -->
        <div class="main-wrapper">
            <header class="main-header">
                <!-- Bouton hamburger mobile -->
                <div class="mobile-menu-btn show-mobile" onclick="toggleMobileSidebar()" style="display:none;">
                    <span style="font-size: 24px;">☰</span>
                </div>
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
            background: var(--primary, #1E3A8A);
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
            const response = await fetch(`/api/utilisateurs/${{dtPickerState.technicianId}}`, {{
                credentials: 'include'
            }});
            if (response.ok) {{
                const tech = await response.json();
                techInfo.textContent = `Technicien: ${{tech.nom || tech.name || tech.email}}`;

                // Charger les interventions planifiées
                const intResponse = await fetch(`/api/interventions?intervenant_id=${{dtPickerState.technicianId}}&statut=PLANIFIEE,EN_COURS,SUR_SITE`, {{
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
                const items = Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : []);

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
            <p>Scannez le QR code avec l'application {APP_NAME}</p>

            <div class="mobile-instructions">
                <strong>Comment se connecter :</strong>
                <ol>
                    <li>Téléchargez l'app {APP_NAME} sur votre mobile</li>
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
            var mobileBaseUrl = window.location.protocol + '//' + window.location.hostname + '/mobile';
            var mobileUrl = mobileBaseUrl + '/connect?token=' + encodeURIComponent(mobileToken) + '&api=' + encodeURIComponent(window.location.origin + '/api');

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
        var mobileBaseUrl = window.location.protocol + '//' + window.location.hostname + '/mobile';
        var mobileUrl = mobileBaseUrl + '/connect?token=' + encodeURIComponent(mobileToken || '') + '&api=' + encodeURIComponent(window.location.origin + '/api');

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

    // --- Mobile sidebar toggle ---
    function toggleMobileSidebar() {{
        var sidebar = document.querySelector('.sidebar');
        var overlay = document.getElementById('mobile-overlay');

        if (!overlay) {{
            overlay = document.createElement('div');
            overlay.id = 'mobile-overlay';
            overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:999;display:none;';
            overlay.onclick = toggleMobileSidebar;
            document.body.appendChild(overlay);
        }}

        var isOpen = sidebar.classList.toggle('open');
        overlay.style.display = isOpen ? 'block' : 'none';
        document.body.style.overflow = isOpen ? 'hidden' : '';
    }}

    // Afficher/masquer bouton hamburger selon largeur
    function updateMobileUI() {{
        var menuBtn = document.querySelector('.mobile-menu-btn');
        if (menuBtn) {{
            menuBtn.style.display = window.innerWidth <= 768 ? 'flex' : 'none';
        }}
    }}
    window.addEventListener('resize', updateMobileUI);
    document.addEventListener('DOMContentLoaded', updateMobileUI);

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
