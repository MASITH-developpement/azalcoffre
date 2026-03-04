# =============================================================================
# AZALPLUS - API Documentation
# =============================================================================
"""
Enhanced API documentation with:
- Detailed endpoint descriptions
- Request/response examples
- Error response documentation
- Custom documentation page
- Interactive API explorer
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.openapi.utils import get_openapi
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, create_model
from enum import Enum
import structlog

from .parser import ModuleParser, ModuleDefinition, FieldDefinition
from .auth import require_auth

logger = structlog.get_logger()

# =============================================================================
# Custom OpenAPI Documentation
# =============================================================================

def custom_openapi(app) -> Dict[str, Any]:
    """Generate custom OpenAPI schema with enhanced documentation."""

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="AZALPLUS API",
        version="1.0.0",
        description="""
## AZALPLUS - ERP No-Code Multi-Tenant

AZALPLUS est un ERP moderne, flexible et extensible construit sur une architecture No-Code.

### Fonctionnalites principales

- **Multi-tenant**: Isolation complete des donnees par organisation
- **No-Code**: Configuration via fichiers YAML
- **API REST**: Endpoints CRUD generes automatiquement
- **Temps reel**: Notifications et mises a jour en temps reel
- **IA integree**: Assistant Marceau pour l'aide contextuelle

### Authentification

L'API utilise JWT (JSON Web Tokens) pour l'authentification.

```bash
# Obtenir un token
curl -X POST /api/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email": "user@example.com", "password": "secret"}'

# Utiliser le token
curl -X GET /api/v1/clients \\
  -H "Authorization: Bearer <token>"
```

### Rate Limiting

- 60 requetes par minute pour l'API generale
- 5 tentatives par minute pour l'authentification

### Codes d'erreur

| Code | Description |
|------|-------------|
| 400 | Requete invalide |
| 401 | Non authentifie |
| 403 | Acces refuse |
| 404 | Ressource non trouvee |
| 422 | Erreur de validation |
| 429 | Trop de requetes |
| 500 | Erreur serveur |

### Multi-tenant

Toutes les requetes sont automatiquement filtrees par le tenant de l'utilisateur connecte.
Le `tenant_id` est extrait du token JWT.
        """,
        routes=app.routes,
        tags=[
            {
                "name": "Authentication",
                "description": "Endpoints d'authentification et gestion des sessions"
            },
            {
                "name": "API",
                "description": "Endpoints API generiques"
            },
            {
                "name": "Clients",
                "description": "Gestion des clients et contacts"
            },
            {
                "name": "Factures",
                "description": "Gestion des factures et paiements"
            },
            {
                "name": "Produits",
                "description": "Catalogue produits et tarification"
            },
            {
                "name": "Stock",
                "description": "Gestion des stocks et mouvements"
            },
            {
                "name": "Interventions",
                "description": "Planification et suivi des interventions"
            },
            {
                "name": "Employes",
                "description": "Ressources humaines et gestion des employes"
            },
            {
                "name": "Guardian",
                "description": "Monitoring et securite (acces restreint)"
            },
            {
                "name": "UI",
                "description": "Interface utilisateur HTML"
            },
            {
                "name": "Theme",
                "description": "Theming et personnalisation visuelle"
            }
        ]
    )

    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token obtenu via /api/auth/login"
        }
    }

    # Add common response schemas
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "description": "Message d'erreur"
            }
        },
        "required": ["detail"],
        "example": {
            "detail": "Non authentifie"
        }
    }

    openapi_schema["components"]["schemas"]["SuccessResponse"] = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Statut de l'operation"
            },
            "message": {
                "type": "string",
                "description": "Message optionnel"
            }
        },
        "example": {
            "status": "success",
            "message": "Operation reussie"
        }
    }

    openapi_schema["components"]["schemas"]["PaginatedResponse"] = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Liste des elements"
            },
            "total": {
                "type": "integer",
                "description": "Nombre total d'elements"
            }
        }
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


# =============================================================================
# Dynamic Schema Generation from YAML Modules
# =============================================================================

class SchemaGenerator:
    """Generate Pydantic schemas from module YAML definitions."""

    # Cache for generated schemas
    _schemas: Dict[str, type] = {}

    # Type mapping from YAML to OpenAPI/JSON Schema types
    TYPE_MAPPING = {
        "text": ("string", None),
        "texte": ("string", None),
        "textarea": ("string", None),
        "email": ("string", "email"),
        "tel": ("string", None),
        "url": ("string", "uri"),
        "number": ("number", None),
        "nombre": ("number", None),
        "entier": ("integer", None),
        "monnaie": ("number", None),
        "pourcentage": ("number", None),
        "date": ("string", "date"),
        "datetime": ("string", "date-time"),
        "boolean": ("boolean", None),
        "booleen": ("boolean", None),
        "oui/non": ("boolean", None),
        "uuid": ("string", "uuid"),
        "relation": ("string", "uuid"),
        "select": ("string", None),
        "enum": ("string", None),
        "tags": ("array", None),
        "json": ("object", None),
    }

    @classmethod
    def get_openapi_type(cls, yaml_type: str) -> tuple:
        """Convert YAML type to OpenAPI type and format."""
        return cls.TYPE_MAPPING.get(yaml_type.lower(), ("string", None))

    @classmethod
    def generate_schema_from_module(cls, module: ModuleDefinition) -> Dict[str, Any]:
        """Generate OpenAPI schema from module definition."""

        properties = {}
        required = []

        for field_name, field_def in module.champs.items():
            openapi_type, openapi_format = cls.get_openapi_type(field_def.type)

            prop = {
                "type": openapi_type,
                "description": field_def.aide or field_def.label or field_name.replace("_", " ").title()
            }

            if openapi_format:
                prop["format"] = openapi_format

            if field_def.defaut is not None:
                prop["default"] = field_def.defaut

            if field_def.enum_values:
                prop["enum"] = field_def.enum_values

            if field_def.min is not None:
                prop["minimum"] = field_def.min

            if field_def.max is not None:
                prop["maximum"] = field_def.max

            properties[field_name] = prop

            if field_def.requis:
                required.append(field_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required if required else None
        }

    @classmethod
    def generate_all_schemas(cls) -> Dict[str, Dict[str, Any]]:
        """Generate schemas for all loaded modules."""
        schemas = {}

        for module_name in ModuleParser.list_all():
            module = ModuleParser.get(module_name)
            if module and module.actif:
                # Create schema
                schema_name = module.nom.title().replace("_", "")
                schemas[f"{schema_name}Create"] = cls.generate_schema_from_module(module)

                # Update schema (all optional)
                update_schema = cls.generate_schema_from_module(module)
                update_schema["required"] = None
                schemas[f"{schema_name}Update"] = update_schema

                # Response schema (includes id, tenant_id, timestamps)
                response_schema = cls.generate_schema_from_module(module)
                response_schema["properties"]["id"] = {
                    "type": "string",
                    "format": "uuid",
                    "description": "Identifiant unique"
                }
                response_schema["properties"]["tenant_id"] = {
                    "type": "string",
                    "format": "uuid",
                    "description": "Identifiant du tenant"
                }
                response_schema["properties"]["created_at"] = {
                    "type": "string",
                    "format": "date-time",
                    "description": "Date de creation"
                }
                response_schema["properties"]["updated_at"] = {
                    "type": "string",
                    "format": "date-time",
                    "description": "Date de modification"
                }
                schemas[f"{schema_name}Response"] = response_schema

        return schemas


# =============================================================================
# API Examples
# =============================================================================

API_EXAMPLES = {
    "clients": {
        "create": {
            "summary": "Creer un client",
            "description": "Exemple de creation d'un nouveau client",
            "value": {
                "code": "CLI001",
                "name": "Entreprise ABC",
                "legal_name": "ABC SARL",
                "type": "CUSTOMER",
                "email": "contact@abc.fr",
                "phone": "+33 1 23 45 67 89",
                "address_line1": "123 Rue de Paris",
                "city": "Paris",
                "postal_code": "75001",
                "country_code": "FR",
                "tax_id": "FR12345678901",
                "payment_terms": "NET_30"
            }
        },
        "response": {
            "summary": "Reponse client",
            "value": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
                "code": "CLI001",
                "name": "Entreprise ABC",
                "legal_name": "ABC SARL",
                "type": "CUSTOMER",
                "email": "contact@abc.fr",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }
    },
    "factures": {
        "create": {
            "summary": "Creer une facture",
            "value": {
                "number": "FAC-2024-001",
                "status": "DRAFT",
                "customer_id": "550e8400-e29b-41d4-a716-446655440000",
                "date": "2024-01-15",
                "due_date": "2024-02-15",
                "subtotal": 1000.00,
                "tax_amount": 200.00,
                "total": 1200.00,
                "currency": "EUR",
                "payment_terms": "NET_30"
            }
        }
    },
    "auth": {
        "login": {
            "summary": "Connexion",
            "value": {
                "email": "user@example.com",
                "password": "mot_de_passe_secret"
            }
        },
        "token_response": {
            "summary": "Reponse token",
            "value": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 86400
            }
        }
    }
}


# =============================================================================
# Documentation Router
# =============================================================================

docs_router = APIRouter()

@docs_router.get("/documentation", response_class=HTMLResponse)
async def api_documentation():
    """
    Custom interactive API documentation page.
    Provides code examples in Python, JavaScript, and cURL.
    """

    html_content = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AZALPLUS API Documentation</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --secondary: #64748b;
            --success: #10b981;
            --warning: #f59e0b;
            --error: #ef4444;
            --bg: #f8fafc;
            --bg-card: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --code-bg: #1e293b;
            --code-text: #e2e8f0;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }

        /* Header */
        header {
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--primary);
        }

        .nav-links {
            display: flex;
            gap: 1.5rem;
        }

        .nav-links a {
            color: var(--text-muted);
            text-decoration: none;
            font-weight: 500;
            transition: color 0.2s;
        }

        .nav-links a:hover {
            color: var(--primary);
        }

        /* Layout */
        .container {
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 280px 1fr;
            min-height: calc(100vh - 60px);
        }

        /* Sidebar */
        .sidebar {
            background: var(--bg-card);
            border-right: 1px solid var(--border);
            padding: 1.5rem;
            position: sticky;
            top: 60px;
            height: calc(100vh - 60px);
            overflow-y: auto;
        }

        .sidebar h3 {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.75rem;
            letter-spacing: 0.05em;
        }

        .sidebar-section {
            margin-bottom: 1.5rem;
        }

        .sidebar-link {
            display: flex;
            align-items: center;
            padding: 0.5rem 0.75rem;
            border-radius: 0.5rem;
            color: var(--text);
            text-decoration: none;
            font-size: 0.875rem;
            margin-bottom: 0.25rem;
            transition: all 0.2s;
        }

        .sidebar-link:hover {
            background: var(--bg);
            color: var(--primary);
        }

        .sidebar-link.active {
            background: var(--primary);
            color: white;
        }

        .method-badge {
            display: inline-block;
            padding: 0.125rem 0.375rem;
            border-radius: 0.25rem;
            font-size: 0.625rem;
            font-weight: 600;
            margin-right: 0.5rem;
            text-transform: uppercase;
        }

        .method-get { background: #dbeafe; color: #1d4ed8; }
        .method-post { background: #d1fae5; color: #059669; }
        .method-put { background: #fef3c7; color: #d97706; }
        .method-delete { background: #fee2e2; color: #dc2626; }

        /* Main Content */
        main {
            padding: 2rem;
        }

        .section {
            background: var(--bg-card);
            border-radius: 1rem;
            border: 1px solid var(--border);
            padding: 2rem;
            margin-bottom: 2rem;
        }

        .section h1 {
            font-size: 2rem;
            margin-bottom: 1rem;
        }

        .section h2 {
            font-size: 1.5rem;
            margin-bottom: 1rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
        }

        .section h2:first-of-type {
            border-top: none;
            padding-top: 0;
        }

        .section p {
            color: var(--text-muted);
            margin-bottom: 1rem;
        }

        /* Code Block */
        .code-block {
            background: var(--code-bg);
            border-radius: 0.75rem;
            overflow: hidden;
            margin: 1rem 0;
        }

        .code-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: rgba(255,255,255,0.05);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }

        .code-tabs {
            display: flex;
            gap: 0.5rem;
        }

        .code-tab {
            padding: 0.375rem 0.75rem;
            border-radius: 0.375rem;
            background: transparent;
            color: var(--code-text);
            border: none;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 500;
            transition: all 0.2s;
        }

        .code-tab.active {
            background: var(--primary);
            color: white;
        }

        .copy-btn {
            padding: 0.375rem 0.75rem;
            border-radius: 0.375rem;
            background: rgba(255,255,255,0.1);
            color: var(--code-text);
            border: none;
            cursor: pointer;
            font-size: 0.75rem;
            transition: all 0.2s;
        }

        .copy-btn:hover {
            background: rgba(255,255,255,0.2);
        }

        .code-content {
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            color: var(--code-text);
            overflow-x: auto;
            line-height: 1.8;
        }

        .code-content pre {
            margin: 0;
            white-space: pre-wrap;
        }

        /* Syntax highlighting */
        .code-string { color: #a5d6ff; }
        .code-keyword { color: #ff7b72; }
        .code-comment { color: #8b949e; }
        .code-number { color: #79c0ff; }
        .code-function { color: #d2a8ff; }

        /* Endpoint Card */
        .endpoint-card {
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            margin-bottom: 1.5rem;
            overflow: hidden;
        }

        .endpoint-header {
            display: flex;
            align-items: center;
            padding: 1rem 1.25rem;
            background: var(--bg);
            border-bottom: 1px solid var(--border);
        }

        .endpoint-method {
            padding: 0.375rem 0.75rem;
            border-radius: 0.375rem;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            margin-right: 1rem;
        }

        .endpoint-path {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            color: var(--text);
        }

        .endpoint-body {
            padding: 1.25rem;
        }

        .endpoint-description {
            color: var(--text-muted);
            margin-bottom: 1rem;
        }

        /* Parameters Table */
        .params-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }

        .params-table th,
        .params-table td {
            text-align: left;
            padding: 0.75rem;
            border-bottom: 1px solid var(--border);
        }

        .params-table th {
            background: var(--bg);
            font-weight: 600;
            color: var(--text-muted);
            font-size: 0.75rem;
            text-transform: uppercase;
        }

        .param-name {
            font-family: 'JetBrains Mono', monospace;
            color: var(--primary);
        }

        .param-type {
            font-size: 0.75rem;
            color: var(--text-muted);
            background: var(--bg);
            padding: 0.125rem 0.375rem;
            border-radius: 0.25rem;
        }

        .param-required {
            color: var(--error);
            font-size: 0.75rem;
        }

        /* Try It Section */
        .try-it {
            background: var(--bg);
            border-radius: 0.75rem;
            padding: 1.25rem;
            margin-top: 1.5rem;
        }

        .try-it h4 {
            font-size: 0.875rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .try-it input,
        .try-it textarea {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            margin-bottom: 1rem;
            background: var(--bg-card);
        }

        .try-it button {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .try-it button:hover {
            background: var(--primary-dark);
        }

        /* Status Codes */
        .status-codes {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }

        .status-code {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .status-badge {
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .status-2xx { background: #d1fae5; color: #059669; }
        .status-4xx { background: #fef3c7; color: #d97706; }
        .status-5xx { background: #fee2e2; color: #dc2626; }

        /* Responsive */
        @media (max-width: 1024px) {
            .container {
                grid-template-columns: 1fr;
            }

            .sidebar {
                display: none;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="header-content">
            <div class="logo">AZALPLUS API</div>
            <nav class="nav-links">
                <a href="/api/docs">Swagger UI</a>
                <a href="/api/redoc">ReDoc</a>
                <a href="/api/openapi.json">OpenAPI JSON</a>
            </nav>
        </div>
    </header>

    <div class="container">
        <aside class="sidebar">
            <div class="sidebar-section">
                <h3>Introduction</h3>
                <a href="#overview" class="sidebar-link active">Vue d'ensemble</a>
                <a href="#authentication" class="sidebar-link">Authentification</a>
                <a href="#rate-limiting" class="sidebar-link">Rate Limiting</a>
                <a href="#errors" class="sidebar-link">Gestion des erreurs</a>
            </div>

            <div class="sidebar-section">
                <h3>Authentification</h3>
                <a href="#auth-login" class="sidebar-link">
                    <span class="method-badge method-post">POST</span>
                    /auth/login
                </a>
                <a href="#auth-register" class="sidebar-link">
                    <span class="method-badge method-post">POST</span>
                    /auth/register
                </a>
                <a href="#auth-me" class="sidebar-link">
                    <span class="method-badge method-get">GET</span>
                    /auth/me
                </a>
            </div>

            <div class="sidebar-section">
                <h3>Clients</h3>
                <a href="#clients-list" class="sidebar-link">
                    <span class="method-badge method-get">GET</span>
                    /v1/clients
                </a>
                <a href="#clients-create" class="sidebar-link">
                    <span class="method-badge method-post">POST</span>
                    /v1/clients
                </a>
                <a href="#clients-get" class="sidebar-link">
                    <span class="method-badge method-get">GET</span>
                    /v1/clients/{id}
                </a>
                <a href="#clients-update" class="sidebar-link">
                    <span class="method-badge method-put">PUT</span>
                    /v1/clients/{id}
                </a>
                <a href="#clients-delete" class="sidebar-link">
                    <span class="method-badge method-delete">DEL</span>
                    /v1/clients/{id}
                </a>
            </div>

            <div class="sidebar-section">
                <h3>Factures</h3>
                <a href="#factures-list" class="sidebar-link">
                    <span class="method-badge method-get">GET</span>
                    /v1/factures
                </a>
                <a href="#factures-create" class="sidebar-link">
                    <span class="method-badge method-post">POST</span>
                    /v1/factures
                </a>
            </div>
        </aside>

        <main>
            <!-- Overview Section -->
            <section class="section" id="overview">
                <h1>API AZALPLUS</h1>
                <p>
                    Bienvenue dans la documentation de l'API AZALPLUS.
                    Cette API REST vous permet d'interagir avec tous les modules de l'ERP.
                </p>

                <h2>Base URL</h2>
                <div class="code-block">
                    <div class="code-content">
                        <pre>https://api.azalplus.com/api/v1</pre>
                    </div>
                </div>

                <h2>Formats</h2>
                <p>
                    L'API accepte et retourne des donnees au format JSON.
                    Assurez-vous d'inclure le header <code>Content-Type: application/json</code> pour les requetes POST et PUT.
                </p>
            </section>

            <!-- Authentication Section -->
            <section class="section" id="authentication">
                <h1>Authentification</h1>
                <p>
                    L'API utilise des tokens JWT (JSON Web Tokens) pour l'authentification.
                    Obtenez un token via l'endpoint <code>/api/auth/login</code> et incluez-le dans le header Authorization.
                </p>

                <div class="code-block">
                    <div class="code-header">
                        <div class="code-tabs">
                            <button class="code-tab active" data-lang="curl">cURL</button>
                            <button class="code-tab" data-lang="python">Python</button>
                            <button class="code-tab" data-lang="javascript">JavaScript</button>
                        </div>
                        <button class="copy-btn">Copier</button>
                    </div>
                    <div class="code-content">
                        <pre class="code-curl"><span class="code-comment"># Obtenir un token</span>
curl -X POST https://api.azalplus.com/api/auth/login \\
  -H <span class="code-string">"Content-Type: application/json"</span> \\
  -d <span class="code-string">'{"email": "user@example.com", "password": "secret"}'</span>

<span class="code-comment"># Utiliser le token</span>
curl -X GET https://api.azalplus.com/api/v1/clients \\
  -H <span class="code-string">"Authorization: Bearer eyJhbGciOiJI..."</span></pre>
                        <pre class="code-python" style="display:none;"><span class="code-keyword">import</span> requests

<span class="code-comment"># Obtenir un token</span>
response = requests.<span class="code-function">post</span>(
    <span class="code-string">"https://api.azalplus.com/api/auth/login"</span>,
    json={
        <span class="code-string">"email"</span>: <span class="code-string">"user@example.com"</span>,
        <span class="code-string">"password"</span>: <span class="code-string">"secret"</span>
    }
)
token = response.<span class="code-function">json</span>()[<span class="code-string">"access_token"</span>]

<span class="code-comment"># Utiliser le token</span>
headers = {<span class="code-string">"Authorization"</span>: <span class="code-keyword">f</span><span class="code-string">"Bearer {token}"</span>}
clients = requests.<span class="code-function">get</span>(
    <span class="code-string">"https://api.azalplus.com/api/v1/clients"</span>,
    headers=headers
)</pre>
                        <pre class="code-javascript" style="display:none;"><span class="code-comment">// Obtenir un token</span>
<span class="code-keyword">const</span> loginResponse = <span class="code-keyword">await</span> <span class="code-function">fetch</span>(
  <span class="code-string">'https://api.azalplus.com/api/auth/login'</span>,
  {
    method: <span class="code-string">'POST'</span>,
    headers: { <span class="code-string">'Content-Type'</span>: <span class="code-string">'application/json'</span> },
    body: JSON.<span class="code-function">stringify</span>({
      email: <span class="code-string">'user@example.com'</span>,
      password: <span class="code-string">'secret'</span>
    })
  }
);
<span class="code-keyword">const</span> { access_token } = <span class="code-keyword">await</span> loginResponse.<span class="code-function">json</span>();

<span class="code-comment">// Utiliser le token</span>
<span class="code-keyword">const</span> clients = <span class="code-keyword">await</span> <span class="code-function">fetch</span>(
  <span class="code-string">'https://api.azalplus.com/api/v1/clients'</span>,
  {
    headers: {
      <span class="code-string">'Authorization'</span>: <span class="code-string">`Bearer ${access_token}`</span>
    }
  }
);</pre>
                    </div>
                </div>

                <!-- Login Endpoint -->
                <div class="endpoint-card" id="auth-login">
                    <div class="endpoint-header">
                        <span class="endpoint-method method-post">POST</span>
                        <span class="endpoint-path">/api/auth/login</span>
                    </div>
                    <div class="endpoint-body">
                        <p class="endpoint-description">
                            Authentifie un utilisateur et retourne un token JWT.
                        </p>

                        <h4>Parametres</h4>
                        <table class="params-table">
                            <thead>
                                <tr>
                                    <th>Nom</th>
                                    <th>Type</th>
                                    <th>Description</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><span class="param-name">email</span> <span class="param-required">*</span></td>
                                    <td><span class="param-type">string</span></td>
                                    <td>Email de l'utilisateur</td>
                                </tr>
                                <tr>
                                    <td><span class="param-name">password</span> <span class="param-required">*</span></td>
                                    <td><span class="param-type">string</span></td>
                                    <td>Mot de passe</td>
                                </tr>
                            </tbody>
                        </table>

                        <h4 style="margin-top: 1.5rem;">Reponses</h4>
                        <div class="status-codes">
                            <div class="status-code">
                                <span class="status-badge status-2xx">200</span>
                                <span>Token retourne</span>
                            </div>
                            <div class="status-code">
                                <span class="status-badge status-4xx">401</span>
                                <span>Identifiants invalides</span>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Clients Section -->
            <section class="section" id="clients">
                <h1>Clients</h1>
                <p>
                    Les endpoints clients permettent de gerer votre base clients :
                    creation, mise a jour, recherche et suppression.
                </p>

                <!-- List Clients -->
                <div class="endpoint-card" id="clients-list">
                    <div class="endpoint-header">
                        <span class="endpoint-method method-get">GET</span>
                        <span class="endpoint-path">/api/v1/clients</span>
                    </div>
                    <div class="endpoint-body">
                        <p class="endpoint-description">
                            Retourne la liste paginee des clients du tenant.
                        </p>

                        <h4>Parametres de requete</h4>
                        <table class="params-table">
                            <thead>
                                <tr>
                                    <th>Nom</th>
                                    <th>Type</th>
                                    <th>Defaut</th>
                                    <th>Description</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><span class="param-name">skip</span></td>
                                    <td><span class="param-type">integer</span></td>
                                    <td>0</td>
                                    <td>Nombre d'elements a ignorer</td>
                                </tr>
                                <tr>
                                    <td><span class="param-name">limit</span></td>
                                    <td><span class="param-type">integer</span></td>
                                    <td>25</td>
                                    <td>Nombre d'elements (max 100)</td>
                                </tr>
                                <tr>
                                    <td><span class="param-name">order_by</span></td>
                                    <td><span class="param-type">string</span></td>
                                    <td>created_at</td>
                                    <td>Champ de tri</td>
                                </tr>
                                <tr>
                                    <td><span class="param-name">order_dir</span></td>
                                    <td><span class="param-type">string</span></td>
                                    <td>desc</td>
                                    <td>Direction (asc/desc)</td>
                                </tr>
                            </tbody>
                        </table>

                        <div class="code-block">
                            <div class="code-header">
                                <div class="code-tabs">
                                    <button class="code-tab active" data-lang="curl">cURL</button>
                                    <button class="code-tab" data-lang="python">Python</button>
                                    <button class="code-tab" data-lang="javascript">JavaScript</button>
                                </div>
                                <button class="copy-btn">Copier</button>
                            </div>
                            <div class="code-content">
                                <pre class="code-curl">curl -X GET <span class="code-string">"https://api.azalplus.com/api/v1/clients?limit=10"</span> \\
  -H <span class="code-string">"Authorization: Bearer {token}"</span></pre>
                                <pre class="code-python" style="display:none;">response = requests.<span class="code-function">get</span>(
    <span class="code-string">"https://api.azalplus.com/api/v1/clients"</span>,
    headers={<span class="code-string">"Authorization"</span>: <span class="code-keyword">f</span><span class="code-string">"Bearer {token}"</span>},
    params={<span class="code-string">"limit"</span>: <span class="code-number">10</span>}
)
clients = response.<span class="code-function">json</span>()[<span class="code-string">"items"</span>]</pre>
                                <pre class="code-javascript" style="display:none;"><span class="code-keyword">const</span> response = <span class="code-keyword">await</span> <span class="code-function">fetch</span>(
  <span class="code-string">'https://api.azalplus.com/api/v1/clients?limit=10'</span>,
  {
    headers: {
      <span class="code-string">'Authorization'</span>: <span class="code-string">`Bearer ${token}`</span>
    }
  }
);
<span class="code-keyword">const</span> { items: clients } = <span class="code-keyword">await</span> response.<span class="code-function">json</span>();</pre>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Create Client -->
                <div class="endpoint-card" id="clients-create">
                    <div class="endpoint-header">
                        <span class="endpoint-method method-post">POST</span>
                        <span class="endpoint-path">/api/v1/clients</span>
                    </div>
                    <div class="endpoint-body">
                        <p class="endpoint-description">
                            Cree un nouveau client.
                        </p>

                        <div class="code-block">
                            <div class="code-header">
                                <span style="color: var(--code-text); font-size: 0.75rem;">Exemple de requete</span>
                                <button class="copy-btn">Copier</button>
                            </div>
                            <div class="code-content">
                                <pre>{
  <span class="code-string">"code"</span>: <span class="code-string">"CLI001"</span>,
  <span class="code-string">"name"</span>: <span class="code-string">"Entreprise ABC"</span>,
  <span class="code-string">"legal_name"</span>: <span class="code-string">"ABC SARL"</span>,
  <span class="code-string">"type"</span>: <span class="code-string">"CUSTOMER"</span>,
  <span class="code-string">"email"</span>: <span class="code-string">"contact@abc.fr"</span>,
  <span class="code-string">"phone"</span>: <span class="code-string">"+33 1 23 45 67 89"</span>,
  <span class="code-string">"address_line1"</span>: <span class="code-string">"123 Rue de Paris"</span>,
  <span class="code-string">"city"</span>: <span class="code-string">"Paris"</span>,
  <span class="code-string">"postal_code"</span>: <span class="code-string">"75001"</span>,
  <span class="code-string">"country_code"</span>: <span class="code-string">"FR"</span>,
  <span class="code-string">"payment_terms"</span>: <span class="code-string">"NET_30"</span>
}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Error Handling Section -->
            <section class="section" id="errors">
                <h1>Gestion des erreurs</h1>
                <p>
                    L'API retourne des codes HTTP standards.
                    En cas d'erreur, le corps de la reponse contient un objet avec le detail de l'erreur.
                </p>

                <div class="code-block">
                    <div class="code-header">
                        <span style="color: var(--code-text); font-size: 0.75rem;">Exemple d'erreur</span>
                    </div>
                    <div class="code-content">
                        <pre>{
  <span class="code-string">"detail"</span>: <span class="code-string">"Non authentifie"</span>
}</pre>
                    </div>
                </div>

                <h2>Codes HTTP</h2>
                <table class="params-table">
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><span class="status-badge status-2xx">200</span></td>
                            <td>Succes</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-2xx">201</span></td>
                            <td>Ressource creee</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-4xx">400</span></td>
                            <td>Requete invalide</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-4xx">401</span></td>
                            <td>Non authentifie</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-4xx">403</span></td>
                            <td>Acces refuse</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-4xx">404</span></td>
                            <td>Ressource non trouvee</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-4xx">422</span></td>
                            <td>Erreur de validation</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-4xx">429</span></td>
                            <td>Trop de requetes (rate limit)</td>
                        </tr>
                        <tr>
                            <td><span class="status-badge status-5xx">500</span></td>
                            <td>Erreur serveur</td>
                        </tr>
                    </tbody>
                </table>
            </section>
        </main>
    </div>

    <script>
        // Tab switching
        document.querySelectorAll('.code-tabs').forEach(tabs => {
            tabs.querySelectorAll('.code-tab').forEach(tab => {
                tab.addEventListener('click', () => {
                    const lang = tab.dataset.lang;
                    const codeBlock = tab.closest('.code-block');

                    // Update active tab
                    tabs.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');

                    // Show corresponding code
                    codeBlock.querySelectorAll('.code-content pre').forEach(pre => {
                        pre.style.display = pre.classList.contains('code-' + lang) ? 'block' : 'none';
                    });
                });
            });
        });

        // Copy button
        document.querySelectorAll('.copy-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const codeBlock = btn.closest('.code-block');
                const activePre = codeBlock.querySelector('.code-content pre:not([style*="display: none"]), .code-content pre:not([style])');

                if (activePre) {
                    navigator.clipboard.writeText(activePre.textContent);
                    btn.textContent = 'Copie !';
                    setTimeout(() => btn.textContent = 'Copier', 2000);
                }
            });
        });

        // Sidebar active state
        document.querySelectorAll('.sidebar-link').forEach(link => {
            link.addEventListener('click', () => {
                document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
                link.classList.add('active');
            });
        });
    </script>
</body>
</html>
    """

    return HTMLResponse(content=html_content)


@docs_router.get("/schemas")
async def get_schemas(user: dict = Depends(require_auth)):
    """
    Returns all dynamically generated schemas from YAML modules.
    Useful for frontend form generation and validation.
    """
    return SchemaGenerator.generate_all_schemas()


@docs_router.get("/schemas/{module_name}")
async def get_module_schema(module_name: str, user: dict = Depends(require_auth)):
    """
    Returns the schema for a specific module.

    Args:
        module_name: Name of the module (e.g., 'clients', 'factures')

    Returns:
        OpenAPI-compatible schema for the module
    """
    module = ModuleParser.get(module_name)
    if not module:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Module '{module_name}' non trouve"}
        )

    return SchemaGenerator.generate_schema_from_module(module)


@docs_router.get("/examples/{module_name}")
async def get_module_examples(module_name: str):
    """
    Returns request/response examples for a module.
    """
    if module_name in API_EXAMPLES:
        return API_EXAMPLES[module_name]

    # Generate basic examples from module definition
    module = ModuleParser.get(module_name)
    if not module:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Module '{module_name}' non trouve"}
        )

    # Generate example from schema
    example = {}
    for field_name, field_def in module.champs.items():
        if field_def.defaut is not None:
            example[field_name] = field_def.defaut
        elif field_def.requis:
            # Generate placeholder based on type
            if field_def.type in ["text", "texte"]:
                example[field_name] = f"exemple_{field_name}"
            elif field_def.type in ["number", "nombre"]:
                example[field_name] = 0
            elif field_def.type == "email":
                example[field_name] = "exemple@email.com"
            elif field_def.type in ["boolean", "booleen"]:
                example[field_name] = True
            elif field_def.enum_values:
                example[field_name] = field_def.enum_values[0]

    return {
        "create": {"summary": f"Creer un {module.nom_affichage}", "value": example}
    }


@docs_router.get("/openapi.json")
async def get_openapi_json(request: Request):
    """
    Returns the OpenAPI JSON specification.
    """
    from .core import app
    return JSONResponse(content=custom_openapi(app))
