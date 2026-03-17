"""
AZALPLUS - Pages d'erreur personnalisées
========================================

Gère l'affichage de pages d'erreur stylisées pour les codes HTTP courants.
"""

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
import os

# Configuration Jinja2 pour les templates d'erreur
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "errors")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# Configuration des erreurs
ERROR_CONFIGS = {
    400: {
        "title": "Requête invalide",
        "message": "La requête envoyée au serveur est incorrecte ou mal formée. Veuillez vérifier les données envoyées.",
        "icon": "⚠️",
        "color": "#f59e0b",
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    401: {
        "title": "Authentification requise",
        "message": "Vous devez vous connecter pour accéder à cette page. Veuillez vous identifier avec vos identifiants.",
        "icon": "🔐",
        "color": "#f59e0b",
        "actions": [
            {"label": "Se connecter", "url": "/login", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    403: {
        "title": "Accès refusé",
        "message": "Vous n'avez pas les permissions nécessaires pour accéder à cette ressource. Contactez votre administrateur si vous pensez qu'il s'agit d'une erreur.",
        "icon": "🚫",
        "color": "#ef4444",
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    404: {
        "title": "Page introuvable",
        "message": "La page que vous recherchez n'existe pas ou a été déplacée. Vérifiez l'URL ou retournez à l'accueil.",
        "icon": "🔍",
        "color": "#6b7280",
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    405: {
        "title": "Méthode non autorisée",
        "message": "La méthode HTTP utilisée n'est pas autorisée pour cette ressource.",
        "icon": "🚧",
        "color": "#f59e0b",
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    408: {
        "title": "Délai d'attente dépassé",
        "message": "La requête a pris trop de temps. Veuillez réessayer.",
        "icon": "⏱️",
        "color": "#f59e0b",
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    422: {
        "title": "Données invalides",
        "message": "Les données envoyées ne sont pas valides. Veuillez vérifier le formulaire et réessayer.",
        "icon": "📝",
        "color": "#f59e0b",
        "actions": [
            {"label": "Retour", "url": "javascript:history.back()", "style": "secondary"},
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    },
    429: {
        "title": "Trop de requêtes",
        "message": "Vous avez envoyé trop de requêtes en peu de temps. Veuillez patienter quelques instants avant de réessayer.",
        "icon": "🛑",
        "color": "#ef4444",
        "actions": [
            {"label": "Réessayer dans 30s", "url": "javascript:setTimeout(()=>location.reload(),30000)", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    500: {
        "title": "Erreur serveur",
        "message": "Une erreur inattendue s'est produite sur le serveur. Notre équipe technique a été notifiée. Veuillez réessayer plus tard.",
        "icon": "💥",
        "color": "#ef4444",
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    502: {
        "title": "Erreur de passerelle",
        "message": "Le serveur a reçu une réponse invalide d'un serveur en amont. Le service est peut-être en cours de redémarrage.",
        "icon": "🔌",
        "color": "#ef4444",
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    503: {
        "title": "Service indisponible",
        "message": "Le service est temporairement indisponible pour maintenance. Veuillez réessayer dans quelques minutes.",
        "icon": "🔧",
        "color": "#6b7280",
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
    504: {
        "title": "Délai de passerelle dépassé",
        "message": "Le serveur n'a pas répondu à temps. Veuillez réessayer.",
        "icon": "⏳",
        "color": "#ef4444",
        "actions": [
            {"label": "Réessayer", "url": "javascript:location.reload()", "style": "primary"},
            {"label": "Accueil", "url": "/", "style": "secondary"},
        ]
    },
}


def render_error_page(
    status_code: int,
    request: Request = None,
    custom_message: str = None,
    show_details: bool = True
) -> HTMLResponse:
    """
    Génère une page d'erreur HTML stylisée.

    Args:
        status_code: Code HTTP de l'erreur
        request: Objet Request FastAPI (optionnel)
        custom_message: Message personnalisé (optionnel)
        show_details: Afficher le chemin de la requête

    Returns:
        HTMLResponse avec la page d'erreur
    """
    config = ERROR_CONFIGS.get(status_code, {
        "title": "Erreur",
        "message": "Une erreur s'est produite.",
        "icon": "❌",
        "color": "#ef4444",
        "actions": [
            {"label": "Accueil", "url": "/", "style": "primary"},
        ]
    })

    # Générer les boutons d'action
    actions_html = ""
    for action in config["actions"]:
        btn_class = "btn-primary" if action["style"] == "primary" else "btn-secondary"
        actions_html += f'<a href="{action["url"]}" class="btn {btn_class}">{action["label"]}</a>\n'

    # Charger et rendre le template
    try:
        template = env.get_template("base_error.html")
        html = template.render(
            error_code=status_code,
            error_title=config["title"],
            error_message=custom_message or config["message"],
            error_icon=config["icon"],
            header_color=config["color"],
            error_actions=actions_html,
            request_path=request.url.path if request else None,
            show_details=show_details
        )
    except Exception:
        # Fallback si le template n'existe pas
        html = generate_fallback_error_page(status_code, config, custom_message)

    return HTMLResponse(content=html, status_code=status_code)


def generate_fallback_error_page(status_code: int, config: dict, custom_message: str = None) -> str:
    """Génère une page d'erreur de secours sans template."""
    return f'''
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{status_code} - {config["title"]} | AZALPLUS</title>
        <style>
            body {{
                font-family: -apple-system, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                color: white;
                text-align: center;
            }}
            .error {{ max-width: 400px; padding: 20px; }}
            .code {{ font-size: 96px; font-weight: 800; opacity: 0.9; }}
            .title {{ font-size: 24px; margin: 20px 0; }}
            .message {{ opacity: 0.8; line-height: 1.6; }}
            .btn {{
                display: inline-block;
                margin-top: 30px;
                padding: 12px 24px;
                background: white;
                color: #667eea;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
            }}
            .btn:hover {{ transform: translateY(-2px); }}
        </style>
    </head>
    <body>
        <div class="error">
            <div class="code">{status_code}</div>
            <h1 class="title">{config["title"]}</h1>
            <p class="message">{custom_message or config["message"]}</p>
            <a href="/" class="btn">Retour à l'accueil</a>
        </div>
    </body>
    </html>
    '''


# Fonctions utilitaires pour les handlers FastAPI
def error_400(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(400, request, message)

def error_401(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(401, request, message)

def error_403(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(403, request, message)

def error_404(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(404, request, message)

def error_500(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(500, request, message)

def error_502(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(502, request, message)

def error_503(request: Request, message: str = None) -> HTMLResponse:
    return render_error_page(503, request, message)
