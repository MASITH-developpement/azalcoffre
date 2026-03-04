# =============================================================================
# AZALPLUS - Notes Client UI Components
# =============================================================================
"""
Generates the Notes/History section for client detail pages.
Includes timeline view, quick add form, and reminder system.
"""


def generate_client_notes_section(client_id: str) -> str:
    """Genere la section notes/historique pour un client."""
    return f'''
    <div class="card" style="margin-top: 24px;">
        <div class="card-header">
            <div class="flex justify-between items-center">
                <h3 class="font-bold">Notes et Historique</h3>
                <button class="btn btn-primary btn-sm" onclick="openNoteModal()">+ Ajouter une note</button>
            </div>
            <div class="notes-filters" style="margin-top: 12px;">
                <select id="filter-type" class="input" style="width: auto; padding: 6px 12px; font-size: 13px;" onchange="loadNotes()">
                    <option value="">Tous les types</option>
                    <option value="appel">Appels</option>
                    <option value="email">Emails</option>
                    <option value="reunion">Reunions</option>
                    <option value="note">Notes</option>
                    <option value="visite">Visites</option>
                    <option value="autre">Autres</option>
                </select>
                <input type="date" id="filter-date-from" class="input" style="width: auto; padding: 6px 12px; font-size: 13px;" placeholder="Du" onchange="loadNotes()">
                <input type="date" id="filter-date-to" class="input" style="width: auto; padding: 6px 12px; font-size: 13px;" placeholder="Au" onchange="loadNotes()">
            </div>
        </div>
        <div class="card-body">
            <div id="notes-timeline" class="notes-timeline">
                <p class="text-muted">Chargement...</p>
            </div>
        </div>
    </div>

    <!-- Modal Ajout Note -->
    <div id="note-modal" class="modal hidden">
        <div class="modal-backdrop" onclick="closeNoteModal()"></div>
        <div class="modal-content">
            <div class="modal-header">
                <h3>Nouvelle note</h3>
                <button class="modal-close" onclick="closeNoteModal()">&times;</button>
            </div>
            <form id="note-form" class="modal-body">
                <div class="note-form-grid">
                    <div class="form-group">
                        <label class="label">Type *</label>
                        <select class="input" name="type" required>
                            <option value="note">Note</option>
                            <option value="appel">Appel</option>
                            <option value="email">Email</option>
                            <option value="reunion">Reunion</option>
                            <option value="visite">Visite</option>
                            <option value="autre">Autre</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="label">Date *</label>
                        <input type="datetime-local" class="input" name="date" required>
                    </div>
                    <div class="form-group full-width">
                        <label class="label">Titre *</label>
                        <input type="text" class="input" name="titre" required placeholder="Objet de l'interaction">
                    </div>
                    <div class="form-group full-width">
                        <label class="label">Contenu</label>
                        <textarea class="input" name="contenu" rows="4" placeholder="Details de l'interaction..."></textarea>
                    </div>
                    <div class="form-group">
                        <label class="label">Duree (minutes)</label>
                        <input type="number" class="input" name="duree_minutes" min="0">
                    </div>
                    <div class="form-group">
                        <label class="label">Resultat</label>
                        <select class="input" name="resultat">
                            <option value="">-- Aucun --</option>
                            <option value="positif">Positif</option>
                            <option value="neutre">Neutre</option>
                            <option value="negatif">Negatif</option>
                            <option value="en_attente">En attente</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="label">Rappel</label>
                        <input type="datetime-local" class="input" name="rappel_date">
                    </div>
                    <div class="form-group">
                        <label class="label">Priorite</label>
                        <select class="input" name="priorite">
                            <option value="normale">Normale</option>
                            <option value="basse">Basse</option>
                            <option value="haute">Haute</option>
                            <option value="urgente">Urgente</option>
                        </select>
                    </div>
                    <div class="form-group full-width">
                        <label class="label">Contact</label>
                        <input type="text" class="input" name="contact_nom" placeholder="Nom du contact">
                    </div>
                </div>
            </form>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeNoteModal()">Annuler</button>
                <button class="btn btn-primary" onclick="saveNote()">Enregistrer</button>
            </div>
        </div>
    </div>

    <style>
        .notes-filters {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .notes-timeline {{
            position: relative;
            padding-left: 30px;
        }}
        .notes-timeline::before {{
            content: '';
            position: absolute;
            left: 8px;
            top: 0;
            bottom: 0;
            width: 2px;
            background: var(--gray-200);
        }}
        .note-item {{
            position: relative;
            padding: 16px;
            margin-bottom: 16px;
            background: var(--gray-50);
            border-radius: 8px;
            border: 1px solid var(--gray-200);
        }}
        .note-item::before {{
            content: '';
            position: absolute;
            left: -26px;
            top: 20px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: var(--primary);
            border: 2px solid white;
        }}
        .note-item.type-appel::before {{ background: #10B981; }}
        .note-item.type-email::before {{ background: #3B82F6; }}
        .note-item.type-reunion::before {{ background: #8B5CF6; }}
        .note-item.type-visite::before {{ background: #F59E0B; }}
        .note-item.type-note::before {{ background: #6B7280; }}
        .note-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
        }}
        .note-type {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 500;
            padding: 2px 8px;
            border-radius: 4px;
            background: var(--gray-200);
            color: var(--gray-700);
        }}
        .note-type.type-appel {{ background: #D1FAE5; color: #065F46; }}
        .note-type.type-email {{ background: #DBEAFE; color: #1E40AF; }}
        .note-type.type-reunion {{ background: #EDE9FE; color: #5B21B6; }}
        .note-type.type-visite {{ background: #FEF3C7; color: #92400E; }}
        .note-date {{
            font-size: 12px;
            color: var(--gray-500);
        }}
        .note-title {{
            font-weight: 600;
            color: var(--gray-800);
            margin-bottom: 4px;
        }}
        .note-content {{
            color: var(--gray-600);
            font-size: 14px;
            line-height: 1.5;
        }}
        .note-meta {{
            display: flex;
            gap: 16px;
            margin-top: 8px;
            font-size: 12px;
            color: var(--gray-500);
        }}
        .note-reminder {{
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-top: 8px;
        }}
        .note-reminder.pending {{
            background: #FEF3C7;
            color: #92400E;
        }}
        .note-reminder.done {{
            background: #D1FAE5;
            color: #065F46;
        }}
        .note-actions {{
            display: flex;
            gap: 8px;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--gray-200);
        }}
        .modal {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 1000;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .modal.hidden {{
            display: none;
        }}
        .modal-backdrop {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
        }}
        .modal-content {{
            position: relative;
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 600px;
            max-height: 90vh;
            overflow: auto;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid var(--gray-200);
        }}
        .modal-header h3 {{
            font-weight: 600;
            font-size: 18px;
        }}
        .modal-close {{
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--gray-400);
        }}
        .modal-close:hover {{
            color: var(--gray-600);
        }}
        .modal-body {{
            padding: 20px;
        }}
        .modal-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 12px;
            padding: 16px 20px;
            border-top: 1px solid var(--gray-200);
        }}
        .note-form-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
        }}
        .note-form-grid .full-width {{
            grid-column: 1 / -1;
        }}
        .empty-notes {{
            text-align: center;
            padding: 40px;
            color: var(--gray-500);
        }}
        .empty-notes-icon {{
            font-size: 48px;
            margin-bottom: 12px;
        }}
    </style>

    <script>
    const noteClientId = '{client_id}';

    function getNoteTypeIcon(type) {{
        const icons = {{
            'appel': '&#128222;',
            'email': '&#9993;',
            'reunion': '&#128197;',
            'note': '&#128221;',
            'visite': '&#127970;',
            'autre': '&#128172;'
        }};
        return icons[type] || '&#128172;';
    }}

    function formatNoteDate(dateStr) {{
        if (!dateStr) return '';
        const d = new Date(dateStr);
        return d.toLocaleDateString('fr-FR', {{
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        }});
    }}

    async function loadNotes() {{
        const timeline = document.getElementById('notes-timeline');
        const filterType = document.getElementById('filter-type').value;
        const filterFrom = document.getElementById('filter-date-from').value;
        const filterTo = document.getElementById('filter-date-to').value;

        try {{
            let url = `/api/NotesClient?order_by=date&order_dir=desc&limit=50`;

            const res = await fetch(url);
            if (!res.ok) throw new Error('Erreur chargement');

            const data = await res.json();
            let notes = (data.items || []).filter(n => n.client_id === noteClientId);

            if (filterType) {{
                notes = notes.filter(n => n.type === filterType);
            }}
            if (filterFrom) {{
                notes = notes.filter(n => n.date >= filterFrom);
            }}
            if (filterTo) {{
                notes = notes.filter(n => n.date <= filterTo + 'T23:59:59');
            }}

            if (notes.length === 0) {{
                timeline.innerHTML = `
                    <div class="empty-notes">
                        <div class="empty-notes-icon">&#128221;</div>
                        <div>Aucune note pour ce client</div>
                        <button class="btn btn-primary btn-sm" style="margin-top: 12px;" onclick="openNoteModal()">
                            Ajouter la premiere note
                        </button>
                    </div>
                `;
                return;
            }}

            timeline.innerHTML = notes.map(note => `
                <div class="note-item type-${{note.type}}">
                    <div class="note-header">
                        <span class="note-type type-${{note.type}}">
                            ${{getNoteTypeIcon(note.type)}} ${{note.type.charAt(0).toUpperCase() + note.type.slice(1)}}
                        </span>
                        <span class="note-date">${{formatNoteDate(note.date)}}</span>
                    </div>
                    <div class="note-title">${{note.titre}}</div>
                    ${{note.contenu ? `<div class="note-content">${{note.contenu}}</div>` : ''}}
                    <div class="note-meta">
                        ${{note.duree_minutes ? `<span>Duree: ${{note.duree_minutes}} min</span>` : ''}}
                        ${{note.contact_nom ? `<span>Contact: ${{note.contact_nom}}</span>` : ''}}
                        ${{note.resultat ? `<span>Resultat: ${{note.resultat}}</span>` : ''}}
                    </div>
                    ${{note.rappel_date ? `
                        <div class="note-reminder ${{note.rappel_fait ? 'done' : 'pending'}}">
                            ${{note.rappel_fait ? '&#10003; Rappel effectue' : '&#128276; Rappel: ' + formatNoteDate(note.rappel_date)}}
                            ${{!note.rappel_fait ? `<button class="btn btn-sm" onclick="markReminderDone('${{note.id}}')" style="margin-left:8px;">Marquer fait</button>` : ''}}
                        </div>
                    ` : ''}}
                    <div class="note-actions">
                        <button class="btn btn-sm btn-secondary" onclick="deleteNote('${{note.id}}')">Supprimer</button>
                    </div>
                </div>
            `).join('');
        }} catch (e) {{
            console.error('Erreur chargement notes:', e);
            timeline.innerHTML = '<p class="text-error">Erreur de chargement des notes</p>';
        }}
    }}

    function openNoteModal() {{
        document.getElementById('note-modal').classList.remove('hidden');
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        document.querySelector('#note-form input[name="date"]').value = now.toISOString().slice(0, 16);
    }}

    function closeNoteModal() {{
        document.getElementById('note-modal').classList.add('hidden');
        document.getElementById('note-form').reset();
    }}

    async function saveNote() {{
        const form = document.getElementById('note-form');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);

        data.client_id = noteClientId;
        data.source = 'manuel';

        Object.keys(data).forEach(key => {{
            if (data[key] === '' || data[key] === null) {{
                delete data[key];
            }}
        }});

        if (data.duree_minutes) {{
            data.duree_minutes = parseInt(data.duree_minutes);
        }}

        try {{
            const res = await fetch('/api/NotesClient', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(data)
            }});

            if (res.ok) {{
                closeNoteModal();
                loadNotes();
                showNotification('Note ajoutee avec succes', 'success');
            }} else {{
                const error = await res.json();
                showNotification(error.detail || 'Erreur lors de l\\'ajout', 'error');
            }}
        }} catch (e) {{
            showNotification('Erreur de connexion', 'error');
        }}
    }}

    async function markReminderDone(noteId) {{
        try {{
            const res = await fetch(`/api/NotesClient/${{noteId}}`, {{
                method: 'PUT',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ rappel_fait: true }})
            }});

            if (res.ok) {{
                loadNotes();
                showNotification('Rappel marque comme effectue', 'success');
            }}
        }} catch (e) {{
            showNotification('Erreur', 'error');
        }}
    }}

    async function deleteNote(noteId) {{
        if (!confirm('Supprimer cette note ?')) return;

        try {{
            const res = await fetch(`/api/NotesClient/${{noteId}}`, {{
                method: 'DELETE'
            }});

            if (res.ok) {{
                loadNotes();
                showNotification('Note supprimee', 'success');
            }}
        }} catch (e) {{
            showNotification('Erreur', 'error');
        }}
    }}

    document.addEventListener('DOMContentLoaded', loadNotes);
    </script>
    '''


def generate_reminders_dashboard_widget() -> str:
    """Genere le widget des rappels pour le dashboard."""
    return '''
    <div class="card">
        <div class="card-header">
            <h3 class="font-bold">Rappels a venir</h3>
            <a href="/ui/NotesClient" class="btn btn-sm btn-secondary">Voir tout</a>
        </div>
        <div class="card-body">
            <div id="reminders-list">
                <p class="text-muted">Chargement...</p>
            </div>
        </div>
    </div>

    <style>
        .reminder-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 8px;
            background: var(--gray-50);
            border: 1px solid var(--gray-200);
        }
        .reminder-item:hover {
            background: var(--gray-100);
        }
        .reminder-item.urgent {
            border-left: 3px solid #EF4444;
        }
        .reminder-item.today {
            border-left: 3px solid #F59E0B;
        }
        .reminder-item.upcoming {
            border-left: 3px solid #10B981;
        }
        .reminder-icon {
            font-size: 20px;
        }
        .reminder-info {
            flex: 1;
        }
        .reminder-title {
            font-weight: 500;
            color: var(--gray-800);
        }
        .reminder-client {
            font-size: 12px;
            color: var(--gray-500);
        }
        .reminder-date {
            font-size: 12px;
            color: var(--gray-500);
            text-align: right;
        }
        .reminder-date.overdue {
            color: #EF4444;
            font-weight: 500;
        }
    </style>

    <script>
    async function loadReminders() {
        const container = document.getElementById('reminders-list');

        try {
            const res = await fetch('/api/NotesClient?rappel_fait=false&order_by=rappel_date&order_dir=asc&limit=10');
            if (!res.ok) throw new Error('Erreur');

            const data = await res.json();
            const notes = (data.items || []).filter(n => n.rappel_date && !n.rappel_fait);

            if (notes.length === 0) {
                container.innerHTML = '<p class="text-muted text-center" style="padding: 20px;">Aucun rappel en attente</p>';
                return;
            }

            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

            container.innerHTML = notes.map(note => {
                const rappelDate = new Date(note.rappel_date);
                const isOverdue = rappelDate < now;
                const isToday = rappelDate >= today && rappelDate < new Date(today.getTime() + 86400000);

                let urgencyClass = 'upcoming';
                if (isOverdue) urgencyClass = 'urgent';
                else if (isToday) urgencyClass = 'today';

                return `
                    <div class="reminder-item ${urgencyClass}" onclick="window.location='/ui/Clients/${note.client_id}'">
                        <span class="reminder-icon">&#128276;</span>
                        <div class="reminder-info">
                            <div class="reminder-title">${note.titre}</div>
                            <div class="reminder-client">${note.type}</div>
                        </div>
                        <div class="reminder-date ${isOverdue ? 'overdue' : ''}">
                            ${isOverdue ? 'En retard' : formatReminderDate(note.rappel_date)}
                        </div>
                    </div>
                `;
            }).join('');
        } catch (e) {
            console.error('Erreur chargement rappels:', e);
            container.innerHTML = '<p class="text-error">Erreur de chargement</p>';
        }
    }

    function formatReminderDate(dateStr) {
        const d = new Date(dateStr);
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const tomorrow = new Date(today.getTime() + 86400000);

        if (d >= today && d < tomorrow) {
            return "Aujourd'hui " + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
        } else if (d >= tomorrow && d < new Date(tomorrow.getTime() + 86400000)) {
            return "Demain " + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
        } else {
            return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
        }
    }

    document.addEventListener('DOMContentLoaded', loadReminders);
    </script>
    '''
