# =============================================================================
# AZALPLUS - Email UI Components
# =============================================================================
"""
Composants UI pour l'envoi d'emails.
Integre dans les pages de detail Devis et Facture.
"""


def generate_email_section(module_name: str, item_id: str) -> str:
    """Genere la section d'envoi par email pour Devis et Factures."""
    if module_name.lower() not in ["devis", "facture"]:
        return ""

    doc_type = "devis" if module_name.lower() == "devis" else "facture"

    return f'''
    <div class="card" style="margin-top: 24px;">
        <div class="card-header flex justify-between items-center">
            <h3 class="font-bold">Envoyer par email</h3>
        </div>
        <div class="card-body">
            <div class="email-send-form">
                <div class="form-group">
                    <label class="label" for="email-recipient">Email du destinataire</label>
                    <input type="email" class="input" id="email-recipient" placeholder="client@exemple.com" required>
                </div>
                <div class="form-group">
                    <label class="label" for="email-message">Message personnalise (optionnel)</label>
                    <textarea class="input" id="email-message" rows="3" placeholder="Votre message..."></textarea>
                </div>
                <div class="flex gap-3" style="margin-top: 16px;">
                    <button type="button" class="btn btn-primary" onclick="sendDocumentEmail()">
                        Envoyer le {doc_type}
                    </button>
                    <a href="/api/{module_name}/{item_id}/pdf" class="btn btn-secondary" target="_blank">
                        Telecharger le PDF
                    </a>
                </div>
            </div>
        </div>
    </div>

    <!-- Email notification -->
    <div id="email-notification" class="notification hidden"></div>

    <script>
    async function sendDocumentEmail() {{
        const recipient = document.getElementById('email-recipient').value;
        const customMessage = document.getElementById('email-message').value;

        if (!recipient) {{
            showEmailNotification('Veuillez saisir un email', 'error');
            return;
        }}

        // Validation email basique
        const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
        if (!emailRegex.test(recipient)) {{
            showEmailNotification('Format email invalide', 'error');
            return;
        }}

        // Desactiver le bouton
        const btn = event.target;
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>Envoi en cours...';

        try {{
            const res = await fetch('/api/{module_name}/{item_id}/envoyer', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    recipient: recipient,
                    custom_message: customMessage || null
                }})
            }});

            if (res.ok) {{
                const data = await res.json();
                showEmailNotification(data.message || 'Email envoye avec succes', 'success');
                // Actualiser la page apres 2 secondes pour voir le nouveau statut
                setTimeout(() => window.location.reload(), 2000);
            }} else {{
                const error = await res.json();
                showEmailNotification(error.detail || "Erreur lors de l'envoi", 'error');
            }}
        }} catch (e) {{
            console.error('Erreur:', e);
            showEmailNotification('Erreur de connexion au serveur', 'error');
        }} finally {{
            btn.disabled = false;
            btn.textContent = originalText;
        }}
    }}

    function showEmailNotification(message, type) {{
        const notif = document.getElementById('email-notification');
        notif.textContent = message;
        notif.className = 'notification ' + type;
        setTimeout(() => {{
            notif.classList.add('hidden');
        }}, 5000);
    }}
    </script>

    <style>
        .email-send-form {{
            max-width: 500px;
        }}
        #email-notification.notification {{
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
        #email-notification.hidden {{
            opacity: 0;
            transform: translateY(-20px);
            pointer-events: none;
        }}
        #email-notification.success {{
            background: #10B981;
            color: white;
        }}
        #email-notification.error {{
            background: #EF4444;
            color: white;
        }}
    </style>
    '''
