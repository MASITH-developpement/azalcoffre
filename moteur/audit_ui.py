# =============================================================================
# AZALPLUS - Audit UI Routes
# =============================================================================
"""
Interface utilisateur pour le journal d'audit.
Accessible via /ui/parametres/audit
"""

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from uuid import UUID
from typing import Optional

from .auth import require_auth
from .tenant import get_current_tenant
from .audit import AuditLogger


# Router pour les pages d'audit
audit_ui_router = APIRouter()


def get_audit_modules():
    """Recupere la liste des modules pour les filtres."""
    from .parser import ModuleParser
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


def get_icon(icon_name: str) -> str:
    """Retourne un emoji pour l'icone."""
    icons = {
        "package": "package", "users": "users", "file-text": "file-text",
        "receipt": "receipt", "wrench": "wrench", "wallet": "wallet",
        "landmark": "landmark", "credit-card": "credit-card",
        "globe": "globe", "settings": "settings", "home": "home",
    }
    return icons.get(icon_name, "file")


@audit_ui_router.get("/parametres/audit", response_class=HTMLResponse)
async def audit_page(
    request: Request,
    user: dict = Depends(require_auth),
    tenant_id: UUID = Depends(get_current_tenant),
    module_filter: str = "",
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
):
    """Page du journal d'audit - affiche l'historique des modifications."""

    # Recuperer les logs d'audit
    if module_filter:
        audit_logs = AuditLogger.get_by_module(tenant_id, module_filter, limit=limit)
    else:
        audit_logs = AuditLogger.get_recent(tenant_id, limit=limit, offset=skip)

    # Recuperer la liste des modules pour le filtre
    modules = get_audit_modules()
    module_options = "".join([
        f'<option value="{m["nom"]}" {"selected" if m["nom"] == module_filter else ""}>{m["nom_affichage"]}</option>'
        for m in modules
    ])

    # Generer les lignes du tableau
    rows_html = ""
    for log in audit_logs:
        # Formater la date
        timestamp = log.get("timestamp") or log.get("created_at", "")
        if timestamp:
            timestamp = str(timestamp)[:16].replace("T", " ")

        # Determiner le style selon l'action
        action = log.get("action", "")
        if action == "create":
            action_icon, action_class, action_label = "+", "success", "Creation"
        elif action == "update":
            action_icon, action_class, action_label = "~", "primary", "Modification"
        elif action == "delete":
            action_icon, action_class, action_label = "-", "error", "Suppression"
        else:
            action_icon, action_class, action_label = "?", "gray", action

        # Formater les modifications
        changes = log.get("changes", {})
        changes_summary = ""
        if isinstance(changes, dict):
            if "new" in changes:
                changes_summary = f"{len(changes.get('new', {}))} champs"
            elif "deleted" in changes:
                changes_summary = "Enregistrement supprime"
            else:
                modified_fields = list(changes.keys())[:3]
                if modified_fields:
                    changes_summary = ", ".join(modified_fields)
                    if len(changes) > 3:
                        changes_summary += f" (+{len(changes) - 3})"

        user_email = log.get("user_email", "")
        user_display = user_email.split("@")[0] if user_email else "Systeme"
        module_name = log.get("module", "")
        record_id = str(log.get("record_id", ""))[:8]
        log_id = log.get('id', '')

        rows_html += f'''
        <tr class="audit-row" data-log-id="{log_id}">
            <td class="text-muted">{timestamp}</td>
            <td><span class="badge badge-{action_class}">{action_icon} {action_label}</span></td>
            <td>{module_name}</td>
            <td><code>{record_id}...</code></td>
            <td>{user_display}</td>
            <td class="text-muted">{changes_summary}</td>
            <td><button class="btn btn-sm btn-secondary" onclick="showDetails('{log_id}')">Details</button></td>
        </tr>
        '''

    if not rows_html:
        rows_html = '<tr><td colspan="7" class="text-center text-muted" style="padding: 48px;">Aucune activite enregistree</td></tr>'

    # Pagination
    prev_link = ""
    next_link = ""
    if skip > 0:
        prev_link = f'<a href="/ui/parametres/audit?skip={max(0, skip-limit)}&limit={limit}" class="btn btn-secondary btn-sm">Precedent</a>'
    if len(audit_logs) == limit:
        next_link = f'<a href="/ui/parametres/audit?skip={skip+limit}&limit={limit}" class="btn btn-secondary btn-sm">Suivant</a>'

    # Generer le layout (simplifie)
    user_name = user.get('nom', user.get('email', 'U'))
    initials = ''.join([n[0].upper() for n in user_name.split()[:2]]) if user_name else 'U'

    # Sidebar avec modules
    menus = {}
    for m in modules:
        menu = m.get("menu", "General")
        if menu not in menus:
            menus[menu] = []
        menus[menu].append(m)

    sidebar_html = ""
    for menu, items in menus.items():
        sidebar_html += f'<div class="nav-section"><div class="nav-title">{menu}</div>'
        for m in items:
            sidebar_html += f'<a href="/ui/{m["nom"]}" class="nav-item"><span>{m["nom_affichage"]}</span></a>'
        sidebar_html += '</div>'

    html = f'''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Journal d'audit - AZALPLUS</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
    <div class="app-layout">
        <aside class="sidebar">
            <div class="sidebar-logo">AZALPLUS</div>
            <nav class="sidebar-nav">
                <div class="nav-section">
                    <a href="/ui/" class="nav-item"><span>Dashboard</span></a>
                </div>
                {sidebar_html}
                <div class="nav-section">
                    <div class="nav-title">Parametres</div>
                    <a href="/ui/parametres/theme" class="nav-item"><span>Theme</span></a>
                    <a href="/ui/parametres/audit" class="nav-item active"><span>Journal d'audit</span></a>
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
            </div>
        </aside>

        <div class="main-wrapper">
            <header class="main-header">
                <div class="header-search">
                    <input type="text" placeholder="Rechercher...">
                </div>
            </header>

            <main class="main-content">
                <h1 class="page-title mb-4">Journal d'audit</h1>

                <div class="card">
                    <div class="card-header">
                        <h2 class="card-title">Historique des modifications</h2>
                        <form method="get" action="/ui/parametres/audit" class="flex gap-2">
                            <select name="module_filter" class="input" style="width: 200px;" onchange="this.form.submit()">
                                <option value="">Tous les modules</option>
                                {module_options}
                            </select>
                        </form>
                    </div>
                    <div class="card-body" style="padding: 0;">
                        <table class="table">
                            <thead><tr>
                                <th style="width: 140px;">Date/Heure</th>
                                <th style="width: 120px;">Action</th>
                                <th>Module</th>
                                <th style="width: 100px;">ID</th>
                                <th>Utilisateur</th>
                                <th>Modifications</th>
                                <th style="width: 80px;"></th>
                            </tr></thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                    </div>
                    <div class="card-footer flex justify-between items-center">
                        <span class="text-muted">{len(audit_logs)} enregistrements</span>
                        <div class="flex gap-2">{prev_link} {next_link}</div>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <!-- Modal pour les details -->
    <div id="details-modal" class="modal hidden">
        <div class="modal-backdrop" onclick="closeDetails()"></div>
        <div class="modal-content">
            <div class="modal-header">
                <h3>Details de la modification</h3>
                <button onclick="closeDetails()" class="btn btn-sm">&times;</button>
            </div>
            <div class="modal-body" id="details-content">Chargement...</div>
        </div>
    </div>

    <style>
        .audit-row:hover {{ background: var(--gray-50); }}
        .badge-success {{ background: #10B981; color: white; }}
        .badge-primary {{ background: var(--primary); color: white; }}
        .badge-error {{ background: #EF4444; color: white; }}
        code {{ background: var(--gray-100); padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
        .modal {{ position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; }}
        .modal.hidden {{ display: none; }}
        .modal-backdrop {{ position: absolute; inset: 0; background: rgba(0,0,0,0.5); }}
        .modal-content {{ position: relative; background: white; border-radius: 12px; max-width: 700px; width: 90%; max-height: 80vh; overflow: hidden; }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--gray-200); }}
        .modal-header h3 {{ margin: 0; font-size: 18px; }}
        .modal-body {{ padding: 24px; overflow-y: auto; max-height: 60vh; }}
        .change-item {{ margin-bottom: 12px; padding: 12px; background: var(--gray-50); border-radius: 6px; }}
        .change-field {{ font-weight: 600; color: var(--gray-700); margin-bottom: 4px; }}
        .change-old {{ color: #EF4444; }}
        .change-new {{ color: #10B981; }}
    </style>

    <script>
        async function showDetails(logId) {{
            document.getElementById('details-modal').classList.remove('hidden');
            const content = document.getElementById('details-content');
            content.innerHTML = 'Chargement...';

            try {{
                const res = await fetch('/api/audit_log/' + logId);
                if (res.ok) {{
                    const log = await res.json();
                    content.innerHTML = formatChanges(log);
                }} else {{
                    content.innerHTML = '<p class="text-muted">Erreur de chargement</p>';
                }}
            }} catch (e) {{
                content.innerHTML = '<p class="text-muted">Erreur de connexion</p>';
            }}
        }}

        function formatChanges(log) {{
            const changes = log.changes || {{}};
            let html = '<div style="margin-bottom: 16px;">';
            html += '<strong>Module:</strong> ' + log.module + '<br>';
            html += '<strong>Enregistrement:</strong> ' + log.record_id + '<br>';
            html += '<strong>Utilisateur:</strong> ' + (log.user_email || 'N/A') + '<br>';
            html += '<strong>IP:</strong> ' + (log.ip_address || 'N/A') + '<br>';
            html += '<strong>Date:</strong> ' + (log.timestamp || log.created_at);
            html += '</div>';

            if (changes.new) {{
                html += '<h4>Donnees creees</h4>';
                html += '<pre style="background: var(--gray-100); padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 12px;">' + JSON.stringify(changes.new, null, 2) + '</pre>';
            }} else if (changes.deleted) {{
                html += '<h4>Donnees supprimees</h4>';
                html += '<pre style="background: var(--gray-100); padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 12px;">' + JSON.stringify(changes.deleted, null, 2) + '</pre>';
            }} else {{
                html += '<h4>Modifications</h4>';
                for (const [field, values] of Object.entries(changes)) {{
                    html += '<div class="change-item">';
                    html += '<div class="change-field">' + field + '</div>';
                    html += '<div><span class="change-old">Ancien: ' + JSON.stringify(values.old) + '</span>';
                    html += ' &rarr; <span class="change-new">Nouveau: ' + JSON.stringify(values.new) + '</span></div>';
                    html += '</div>';
                }}
            }}
            return html;
        }}

        function closeDetails() {{
            document.getElementById('details-modal').classList.add('hidden');
        }}

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeDetails();
        }});
    </script>
</body>
</html>
'''
    return HTMLResponse(content=html)
