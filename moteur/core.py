# =============================================================================
# AZALPLUS - Core Engine
# =============================================================================
"""
Point d'entrée principal du moteur AZALPLUS.
Orchestre tous les composants : DB, API, UI, Guardian, etc.
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import structlog
import time
from typing import Callable, Optional

from .config import settings
from .db import Database
from .parser import ModuleParser
from .guardian import Guardian, GuardianAutoPilot
from .autopilot import AutoPilot, PostgresStorage
from .tenant import TenantMiddleware
from .auth import AuthManager, AuthMiddleware, users_router
from .ratelimit import RateLimitMiddleware
from .csrf import CSRFMiddleware
from .waf import WAF
from .encryption import verify_encryption_setup
from .i18n import preload_translations, get_language_from_request, set_language
from .icons import IconManager
from .prometheus import prometheus_router, record_request

# =============================================================================
# Logging
# =============================================================================
logger = structlog.get_logger()

# Instance globale AutoPilot (invisible)
_autopilot: AutoPilot = None

def get_autopilot() -> AutoPilot:
    """Retourne l'instance AutoPilot (créateur uniquement)."""
    return _autopilot

# =============================================================================
# Lifespan (startup/shutdown)
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation et fermeture de l'application."""
    logger.info("azalplus_starting", version="1.0.0")

    # Startup
    await Database.connect()
    # Recharger les modules pour créer les tables DB (modules déjà chargés pour les routes)
    ModuleParser.load_all_modules()
    Guardian.initialize()
    GuardianAutoPilot.initialize()

    # Initialiser AutoPilot modulaire (invisible, créateur uniquement)
    global _autopilot
    autopilot_storage = PostgresStorage()
    autopilot_storage.set_session_factory(Database.get_session)
    _autopilot = AutoPilot(storage=autopilot_storage)
    _autopilot.initialize()

    # Initialiser AutoFixer (corrections automatiques)
    from .autopilot import AutoFixer
    AutoFixer.initialize(Database.get_session)

    # Initialiser ClaudeFixer (corrections par IA)
    try:
        from .autopilot.claude_fixer import ClaudeFixer
        if ClaudeFixer.initialize():
            logger.info("claude_fixer_ready")
    except ImportError:
        logger.debug("claude_fixer_not_available")

    # Vérifier la configuration de l'encryption
    verify_encryption_setup()

    # Log WAF stats
    logger.info("waf_ready", total_patterns=WAF.get_total_patterns())

    # Initialize workflow engine
    from .workflows import WorkflowEngine
    WorkflowEngine.initialize()

    # Initialize icons manager
    IconManager.initialize()

    # Initialize debug tables (Simon QA)
    from .debug import DebugService
    await DebugService.init_tables()

    # Routes already registered at import time (before include_router)

    # Demarrer le planificateur de sauvegardes
    from .backup import BackupService
    await BackupService.start_scheduler()

    logger.info("azalplus_ready", modules_loaded=ModuleParser.count())

    yield

    # Shutdown
    await BackupService.stop_scheduler()
    await Database.disconnect()
    logger.info("azalplus_stopped")

# =============================================================================
# Application FastAPI
# =============================================================================
app = FastAPI(
    title="AZALPLUS API",
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

L'API utilise JWT (JSON Web Tokens). Obtenez un token via `/api/auth/login`.

### Versions de l'API

- **v1** (`/api/v1/*`): API stable avec documentation complete
- **Legacy** (`/api/*`): API compatible avec les versions precedentes

### Support

- Documentation: `/api/documentation`
- OpenAPI: `/api/docs` (Swagger UI)
- ReDoc: `/api/redoc`
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    license_info={
        "name": "Proprietary",
        "url": "https://azalplus.com/license"
    },
    contact={
        "name": "AZALPLUS Support",
        "email": "support@azalplus.com",
        "url": "https://azalplus.com"
    },
    lifespan=lifespan
)

# =============================================================================
# Middlewares
# =============================================================================

# GZip compression (minimum 500 bytes)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant Middleware
app.add_middleware(TenantMiddleware)

# Auth Middleware (APRES TenantMiddleware = s'execute AVANT)
app.add_middleware(AuthMiddleware)

# Rate Limit Middleware (APRES AuthMiddleware = s'execute AVANT)
# Ordre d'execution: RateLimit -> CSRF -> Auth -> Tenant -> Guardian -> Route
app.add_middleware(RateLimitMiddleware)

# CSRF Middleware (protection formulaires HTML)
# Exempte automatiquement les API REST avec JWT
app.add_middleware(CSRFMiddleware)

# Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: Callable):
    """Ajoute les headers de sécurité sur toutes les réponses."""
    response = await call_next(request)

    # Protection contre le clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Protection contre le MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Protection XSS (navigateurs anciens)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy (ex-Feature-Policy)
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Content Security Policy (mode rapport pour ne pas casser l'existant)
    if not request.url.path.startswith("/api/"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.anthropic.com https://api.openai.com; "
            "frame-ancestors 'none';"
        )

    return response

# Request timing middleware + Prometheus
@app.middleware("http")
async def timing_middleware(request: Request, call_next: Callable):
    """Mesure le temps de réponse et enregistre les métriques."""
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Response-Time"] = f"{duration:.4f}s"

    # Prometheus metrics (sauf /metrics et /health)
    if not request.url.path.startswith("/metrics") and request.url.path != "/health":
        try:
            record_request(response.status_code, duration)
        except:
            pass

    return response

# Guardian middleware (sécurité invisible)
# Paths exemptés du WAF (reçoivent des données qui ressemblent à des attaques)
GUARDIAN_EXEMPT_PATHS = [
    "/guardian/frontend-error",  # Reçoit des stack traces, code JS, etc.
    "/api/v1/technicien/intervention/",  # Upload photos base64, signatures
]

@app.middleware("http")
async def guardian_middleware(request: Request, call_next: Callable):
    """Guardian surveille et protège silencieusement."""
    import traceback
    import sys

    try:
        # Exempter certains paths du WAF
        if any(request.url.path.startswith(p) for p in GUARDIAN_EXEMPT_PATHS):
            return await call_next(request)

        # Vérification Guardian AVANT
        check_result = await Guardian.check_request(request)

        if check_result.blocked:
            # Message neutre - Guardian reste invisible
            return JSONResponse(
                status_code=400,
                content={"detail": check_result.neutral_message}
            )

        # Si données nettoyées (XSS), on bloque aussi car on ne peut pas
        # modifier le body en vol facilement - mieux vaut bloquer
        if check_result.cleaned:
            return JSONResponse(
                status_code=400,
                content={"detail": "Requête invalide"}
            )

        # Exécution normale
        response = await call_next(request)

        # Log Guardian APRÈS (silencieux)
        await Guardian.log_request(request, response)

        # === GUARDIAN: Capturer TOUTES les erreurs 4xx/5xx ===
        if response.status_code >= 400:
            import asyncio
            async def fix_response_error():
                try:
                    from .autopilot import AutoFixer
                    error_log = f"HTTP {response.status_code} on {request.method} {request.url.path}"
                    logger.info("response_error_to_autofixer", path=request.url.path, status=response.status_code)
                    success, message = AutoFixer.try_fix(error_log)
                    if success:
                        logger.info("response_error_fixed", path=request.url.path, message=message)
                except Exception as e:
                    logger.debug("response_fix_failed", error=str(e))
            asyncio.create_task(fix_response_error())

        return response
    except Exception as e:
        logger.error("middleware_exception", path=request.url.path, error=str(e), traceback=traceback.format_exc())
        raise

# =============================================================================
# Routes de base
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check pour monitoring."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "database": await Database.is_healthy(),
        "cache": await Database.cache_healthy()
    }

@app.get("/")
async def root():
    """Page d'accueil."""
    return {
        "name": "AZALPLUS",
        "version": "1.0.0",
        "status": "running"
    }

# =============================================================================
# Import des routers dynamiques
# =============================================================================
from .api import router as api_router, register_all_modules
from .auth import router as auth_router
from .storage import storage_router
from .backup import backup_router, BackupService
from .email_router import email_router
from .docs import docs_router, custom_openapi
from .api_v1 import router_v1, register_v1_modules, legacy_router
from .icons import router as icons_router
from .stock_router import stock_router
from .workflows_api import workflows_router
from .mobile_api import router_mobile
from .sync_api import router_sync
from .technicien_api import router_technicien
from .planning_optimizer import router as planning_router
from .creation_entreprise_router import creation_router

# IMPORTANT: Charger les modules YAML AVANT d'enregistrer les routes
# Le parsing YAML ne nécessite pas la connexion DB
from .parser import ModuleParser
ModuleParser.load_all_modules(validate_first=True)
logger.info("yaml_modules_preloaded", count=ModuleParser.count())

# IMPORTANT: Enregistrer les routes AVANT include_router()
register_all_modules()
register_v1_modules()

# =============================================================================
# Auto-discovery des modules Python custom (app/modules/*)
# =============================================================================
from .module_loader import discover_and_register, get_loaded_modules

# Notification router (moteur component)
try:
    from .notification_api import notification_router
except ImportError:
    notification_router = None

# Push notification router
try:
    from .push_api import push_router
except ImportError:
    push_router = None

# Integration routes (Fintecture, Swan, Twilio, Transporteurs)
try:
    from integrations.routes import setup_integration_routes
    _integrations_available = True
except ImportError:
    _integrations_available = False
    logger.debug("integrations_routes_not_available")

# Authentication
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])

# Admin - Users Management
app.include_router(users_router, prefix="/api/admin/users", tags=["Admin - Users"])

# Legacy API (backwards compatibility)
app.include_router(api_router, prefix="/api", tags=["API (Legacy)"])

# Legacy interventions router (avec filtrage date_prevue_debut)
app.include_router(legacy_router, tags=["API Legacy Interventions"])

# API v1 (versioned, fully documented)
app.include_router(router_v1, prefix="/api", tags=["API v1"])

# Icons API (public, no auth required)
app.include_router(icons_router, prefix="/api/icons", tags=["Icons"])

# Documentation
app.include_router(docs_router, prefix="/api", tags=["Documentation"])

# Other routers
app.include_router(storage_router, prefix="/api", tags=["Documents"])
app.include_router(backup_router, prefix="/api/admin/backup", tags=["Backup"])
app.include_router(email_router, tags=["Email"])
app.include_router(stock_router, prefix="/api", tags=["Stock"])
app.include_router(workflows_router, prefix="/api", tags=["Workflows"])

# Mobile API
app.include_router(router_mobile, prefix="/api", tags=["Mobile"])

# Technicien Mobile API
app.include_router(router_technicien, prefix="/api/v1", tags=["Technicien Mobile"])

# Planning Optimizer
app.include_router(planning_router, tags=["Planning"])

# Creation Entreprise (Business Plan, Simulateur Statut)
app.include_router(creation_router, tags=["Création Entreprise"])

# Sync API (offline support)
app.include_router(router_sync, prefix="/api", tags=["Sync"])

# Notifications
if notification_router:
    app.include_router(notification_router, prefix="/api", tags=["Notifications"])

# Push Notifications
if push_router:
    app.include_router(push_router, prefix="/api", tags=["Push Notifications"])

# Integration Routes (Fintecture, Swan, Twilio, Transporteurs)
if _integrations_available:
    try:
        integrations_count = setup_integration_routes(app)
        logger.info("integrations_routes_loaded", count=integrations_count)
    except Exception as e:
        logger.warning("integrations_routes_failed", error=str(e))

# Factur-X Routes (Facturation Électronique)
try:
    from integrations.facturx.routes import router as facturx_router
    app.include_router(facturx_router, tags=["Factur-X"])
    logger.info("facturx_routes_loaded")
except ImportError as e:
    logger.warning("facturx_routes_not_available", error=str(e))

# Import Bancaire Routes (CSV, OFX, QIF, CAMT.053, MT940)
try:
    from .api_import_bancaire import router as import_bancaire_router
    app.include_router(import_bancaire_router, tags=["Import Bancaire"])
    logger.info("import_bancaire_routes_loaded")
except ImportError as e:
    logger.warning("import_bancaire_routes_not_available", error=str(e))

# Generated Endpoints (Auto-created by Guardian)
try:
    from .generated_endpoints import generated_router
    app.include_router(generated_router, prefix="/api", tags=["Generated"])
except ImportError:
    pass

# Recent Items Tracker
from .activity import recent_router
app.include_router(recent_router, prefix="/api", tags=["Recent"])

# Debug Module (Simon QA Assistant)
from .debug import debug_api_router, debug_ui_router
app.include_router(debug_api_router, tags=["Debug API"])
app.include_router(debug_ui_router, tags=["Debug UI"])

# =============================================================================
# Route /api/utilisateurs (alias pour les selects UI)
# =============================================================================
from .auth import require_auth
from .db import Database

@app.get("/api/utilisateurs", tags=["Users"])
async def api_utilisateurs(user: dict = Depends(require_auth)):
    """Liste les utilisateurs du tenant (pour les selects)."""
    tenant_id = user.get("tenant_id")
    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("""
                SELECT id, email, nom, prenom, role
                FROM azalplus.utilisateurs
                WHERE tenant_id = :tenant_id AND actif = true
                ORDER BY nom, prenom
            """),
            {"tenant_id": str(tenant_id)}
        )
        users = []
        for row in result:
            r = dict(row._mapping)
            users.append({
                "id": str(r["id"]),
                "nom": f"{r.get('prenom', '')} {r.get('nom', '')}".strip() or r["email"],
                "email": r["email"],
                "role": r["role"]
            })
    return {"items": users, "total": len(users)}


@app.get("/api/select/{module}", tags=["Selects"])
async def api_select_options(module: str, user: dict = Depends(require_auth)):
    """Retourne les options pour les selects de relations (id + libellé)."""
    tenant_id = user.get("tenant_id")
    module_lower = module.lower().replace("-", "_")

    # Mapping des colonnes d'affichage par module
    display_columns = {
        "clients": "COALESCE(name, '') as display_name",
        "donneur_ordre": "COALESCE(nom, '') as display_name",
        "employes": "COALESCE(prenom || ' ' || nom, nom, '') as display_name",
        "fournisseurs": "COALESCE(nom, raison_sociale, '') as display_name",
        "produits": "COALESCE(nom, designation, '') as display_name",
        "projets": "COALESCE(nom, titre, '') as display_name",
        "contrats": "COALESCE(numero, reference, '') as display_name",
    }

    display_col = display_columns.get(module_lower, "COALESCE(nom, name, code, numero, id::text) as display_name")

    with Database.get_session() as session:
        from sqlalchemy import text
        try:
            query = text(f"""
                SELECT id, {display_col}
                FROM azalplus.{module_lower}
                WHERE tenant_id = :tenant_id
                AND (deleted_at IS NULL OR deleted_at > NOW())
                ORDER BY display_name
                LIMIT 500
            """)
            result = session.execute(query, {"tenant_id": str(tenant_id)})
            items = []
            for row in result:
                items.append({
                    "id": str(row[0]),
                    "nom": row[1] or str(row[0])
                })
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.warning("select_options_error", module=module, error=str(e))
            return {"items": [], "total": 0}

# =============================================================================
# Auto-discovery des modules Python custom (app/modules/*)
# =============================================================================
# Charge automatiquement tous les routers des modules dans app/modules/
# Chaque module peut avoir un meta.py pour configurer prefix, tags, etc.
custom_modules_count = discover_and_register(app)
logger.info("custom_modules_loaded", count=custom_modules_count, modules=list(get_loaded_modules().keys()))

# Apply custom OpenAPI schema
app.openapi = lambda: custom_openapi(app)

# =============================================================================
# Router Prometheus (métriques monitoring)
# =============================================================================
app.include_router(prometheus_router, tags=["Monitoring"])

# =============================================================================
# Router Guardian (visible Créateur uniquement)
# =============================================================================
from .guardian import guardian_router
app.include_router(guardian_router, prefix="/guardian", tags=["Guardian"])

# =============================================================================
# Router UI (interface HTML)
# =============================================================================
from .ui import ui_router
app.include_router(ui_router, prefix="/ui", tags=["UI"])

# =============================================================================
# Router Theme (CSS généré depuis theme.yml)
# =============================================================================
from .theme import theme_router, ThemeManager
app.include_router(theme_router, prefix="/static", tags=["Theme"])

# =============================================================================
# Router Portal (accès client sans auth)
# =============================================================================
from .portal import portal_router
app.include_router(portal_router, prefix="/portail", tags=["Portal"])

# =============================================================================
# Router Portal API (mobile client portal with auth)
# =============================================================================
from .portal_api import portal_api_router
app.include_router(portal_api_router, tags=["Portal Client API"])

# Charger le thème au démarrage
ThemeManager.load()

# =============================================================================
# Static files (images, fonts - pas le CSS qui est généré)
# =============================================================================
static_path = Path(__file__).parent.parent / "assets"
if static_path.exists():
    app.mount("/assets", StaticFiles(directory=str(static_path)), name="assets")

# Static files (manifest.json, icons, etc.)
static_public_path = Path(__file__).parent.parent / "static"
if static_public_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_public_path)), name="static")

# =============================================================================
# Login page (public)
# =============================================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Page de connexion."""
    template_path = Path(__file__).parent.parent / "templates" / "ui" / "login.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>Login</h1>")

# =============================================================================
# Waitlist page (public)
# =============================================================================
@app.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page():
    """Page d'inscription à la liste d'attente."""
    template_path = Path(__file__).parent.parent / "templates" / "waitlist.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>Waitlist</h1>")

@app.get("/inscription", response_class=HTMLResponse)
async def inscription_page():
    """Alias pour la page waitlist."""
    return await waitlist_page()

@app.get("/partenaires", response_class=HTMLResponse)
async def partenaires_page():
    """Page partenaires AZALPLUS."""
    template_path = Path(__file__).parent.parent / "templates" / "partenaires.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>Partenaires</h1>")

# =============================================================================
# Landing Page (public)
# =============================================================================
@app.get("/LANDING_PAGE_AZALPLUS.html", response_class=HTMLResponse)
async def landing_page():
    """Page d'accueil AZALPLUS."""
    landing_path = Path(__file__).parent.parent / "docs" / "LANDING_PAGE_AZALPLUS.html"
    if landing_path.exists():
        return HTMLResponse(content=landing_path.read_text())
    return HTMLResponse(content="<h1>AZALPLUS</h1>", status_code=404)

# =============================================================================
# Style API (change interface theme)
# =============================================================================
@app.put("/api/admin/style")
async def change_style(request: Request):
    """Changer le style de l'interface."""
    import shutil
    import random

    try:
        data = await request.json()
        style = data.get("style", "odoo")

        # Valider le style
        valid_styles = ["odoo", "axo", "penny", "sage"]
        if style not in valid_styles:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Style invalide. Choisir parmi: {', '.join(valid_styles)}"}
            )

        # Chemins des fichiers
        assets_dir = Path(__file__).parent.parent / "assets"
        source_file = assets_dir / f"style_{style}.css"
        target_file = assets_dir / "style.css"

        if not source_file.exists():
            return JSONResponse(
                status_code=404,
                content={"detail": f"Fichier de style non trouvé: style_{style}.css"}
            )

        # Copier le fichier de style
        shutil.copy(source_file, target_file)

        # Mettre à jour le cache-busting dans ui.py
        ui_path = Path(__file__).parent / "ui.py"
        if ui_path.exists():
            content = ui_path.read_text()
            import re
            # Incrémenter la version du cache
            new_version = random.randint(100, 9999)
            content = re.sub(r'style\.css\?v=\d+', f'style.css?v={new_version}', content)
            ui_path.write_text(content)

        logger.info("style_changed", style=style)

        return JSONResponse(
            status_code=200,
            content={"message": f"Style '{style}' appliqué avec succès", "style": style}
        )

    except Exception as e:
        logger.error("style_change_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"detail": f"Erreur: {str(e)}"}
        )

@app.put("/api/admin/ambiance")
async def change_ambiance(request: Request):
    """Changer l'ambiance visuelle de l'interface."""
    import shutil
    import random

    try:
        data = await request.json()
        ambiance = data.get("ambiance", "calme")

        # Valider l'ambiance
        valid_ambiances = ["energique", "calme", "premium", "corporate"]
        if ambiance not in valid_ambiances:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Ambiance invalide. Choisir parmi: {', '.join(valid_ambiances)}"}
            )

        # Chemins des fichiers
        assets_dir = Path(__file__).parent.parent / "assets"
        source_file = assets_dir / f"ambiance_{ambiance}.css"
        target_file = assets_dir / "style.css"

        if not source_file.exists():
            return JSONResponse(
                status_code=404,
                content={"detail": f"Fichier d'ambiance non trouvé: ambiance_{ambiance}.css"}
            )

        # Copier le fichier d'ambiance vers style.css
        shutil.copy(source_file, target_file)

        # Mettre à jour le cache-busting dans ui.py
        ui_path = Path(__file__).parent / "ui.py"
        if ui_path.exists():
            content = ui_path.read_text()
            import re
            # Incrémenter la version du cache
            new_version = random.randint(100, 9999)
            content = re.sub(r'style\.css\?v=\d+', f'style.css?v={new_version}', content)
            ui_path.write_text(content)

        logger.info("ambiance_changed", ambiance=ambiance)

        return JSONResponse(
            status_code=200,
            content={"message": f"Ambiance '{ambiance}' appliquée avec succès", "ambiance": ambiance}
        )

    except Exception as e:
        logger.error("ambiance_change_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"detail": f"Erreur: {str(e)}"}
        )


@app.post("/api/public/waitlist")
async def waitlist_register(request: Request):
    """Enregistrer une inscription à la waitlist."""
    from moteur.db import Database
    from moteur.notifications import EmailService
    from uuid import UUID
    from datetime import datetime
    import asyncio

    # Tenant système pour les inscriptions publiques
    SYSTEM_TENANT = UUID("00000000-0000-0000-0000-000000000000")

    try:
        data = await request.json()

        # Validation basique
        email = data.get("email", "").strip().lower()
        prenom = data.get("prenom", "").strip()
        ami_email = data.get("ami_email", "").strip().lower() if data.get("ami_email") else None

        if not email or "@" not in email:
            return JSONResponse(
                status_code=400,
                content={"detail": "Email invalide"}
            )

        if not prenom:
            return JSONResponse(
                status_code=400,
                content={"detail": "Prénom requis"}
            )

        # Valider l'email de l'ami si fourni
        if ami_email and "@" not in ami_email:
            ami_email = None  # Ignorer si invalide

        # Vérifier si l'email existe déjà
        existing = Database.query(
            "waitlist",
            SYSTEM_TENANT,
            filters={"email": email},
            limit=1
        )
        if existing:
            return JSONResponse(
                status_code=400,
                content={"detail": "Tu es déjà inscrit ! On te préviendra bientôt."}
            )

        # Préparer les données
        waitlist_data = {
            "email": email,
            "prenom": prenom,
            "activite": data.get("activite", ""),
            "source": data.get("source", ""),
            "ami_email": ami_email,
            "utm_source": data.get("utm_source", ""),
            "utm_campaign": data.get("utm_campaign", ""),
            "utm_content": data.get("utm_content", ""),
            "inscrit_le": datetime.now().isoformat(),
            "converti": False
        }

        # Insérer dans la base
        result = Database.insert("waitlist", SYSTEM_TENANT, waitlist_data)

        logger.info("waitlist_inscription", email=email, source=data.get("source", "direct"), ami_email=ami_email)

        # Envoyer l'email de remerciement à l'ami (en arrière-plan)
        if ami_email:
            asyncio.create_task(
                EmailService.send_referral_thank_you(
                    ami_email=ami_email,
                    prenom_inscrit=prenom,
                    email_inscrit=email
                )
            )
            logger.info("referral_thank_you_queued", ami_email=ami_email, prenom_inscrit=prenom)

        return JSONResponse(
            status_code=201,
            content={"message": "Inscription réussie", "id": str(result.get("id"))}
        )

    except Exception as e:
        logger.error("waitlist_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"detail": "Erreur serveur. Réessaie plus tard."}
        )

@app.get("/favicon.ico")
async def favicon():
    """Favicon."""
    favicon_path = Path(__file__).parent.parent / "assets" / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    # Fallback: favicon SVG
    svg_path = Path(__file__).parent.parent / "assets" / "favicon.svg"
    if svg_path.exists():
        return FileResponse(svg_path, media_type="image/svg+xml")
    # Retourner 204 No Content si pas de favicon
    return JSONResponse(status_code=204, content=None)


# =============================================================================
# SEO & Referencing Files
# =============================================================================
STATIC_SEO_DIR = Path(__file__).parent.parent / "static"

@app.get("/robots.txt")
async def robots_txt():
    """Robots.txt pour les moteurs de recherche."""
    file_path = STATIC_SEO_DIR / "robots.txt"
    if file_path.exists():
        return FileResponse(file_path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/sitemap.xml")
async def sitemap_xml():
    """Sitemap XML pour les moteurs de recherche."""
    file_path = STATIC_SEO_DIR / "sitemap.xml"
    if file_path.exists():
        return FileResponse(file_path, media_type="application/xml")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/llms.txt")
async def llms_txt():
    """LLMs.txt pour les assistants IA."""
    file_path = STATIC_SEO_DIR / "llms.txt"
    if file_path.exists():
        return FileResponse(file_path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/llms-full.txt")
async def llms_full_txt():
    """Documentation complete pour les IA."""
    file_path = STATIC_SEO_DIR / "llms-full.txt"
    if file_path.exists():
        return FileResponse(file_path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/manifest.json")
async def manifest_json():
    """Web App Manifest pour PWA."""
    file_path = STATIC_SEO_DIR / "manifest.json"
    if file_path.exists():
        return FileResponse(file_path, media_type="application/json")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/humans.txt")
async def humans_txt():
    """Humans.txt - credits."""
    file_path = STATIC_SEO_DIR / "humans.txt"
    if file_path.exists():
        return FileResponse(file_path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/.well-known/security.txt")
async def security_txt():
    """Security.txt pour les rapports de vulnerabilites."""
    file_path = STATIC_SEO_DIR / ".well-known" / "security.txt"
    if file_path.exists():
        return FileResponse(file_path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "Not found"})

@app.get("/ai-plugin.json")
async def ai_plugin_json():
    """AI Plugin manifest pour ChatGPT et autres."""
    file_path = STATIC_SEO_DIR / "ai-plugin.json"
    if file_path.exists():
        return FileResponse(file_path, media_type="application/json")
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# =============================================================================
# Exception handlers
# =============================================================================
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Gestion des erreurs de validation avec logging pour Guardian."""
    import asyncio
    errors = exc.errors()
    path = request.url.path

    # Log détaillé pour Guardian
    logger.warning("validation_error",
                  path=path,
                  method=request.method,
                  errors=errors)

    # Construire un message utile
    error_messages = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "")
        error_messages.append(f"{loc}: {msg}")

    error_log = f"ValidationError on {path}\n" + "\n".join(error_messages)

    # === GUARDIAN: Envoyer à AutoFixer/ClaudeFixer ===
    async def fix_validation_error():
        try:
            from .autopilot import AutoFixer
            logger.info("validation_error_to_autofixer", path=path, error_count=len(errors))
            success, message = AutoFixer.try_fix(error_log)
            if success:
                logger.info("validation_error_fixed", path=path, message=message)
        except Exception as e:
            logger.warning("validation_fix_failed", error=str(e))

    asyncio.create_task(fix_validation_error())

    # Envoyer aussi à AutoPilot pour apprentissage
    autopilot = get_autopilot()
    if autopilot:
        autopilot.analyze(error_log)

    return JSONResponse(
        status_code=422,
        content={
            "detail": error_messages,
            "validation_errors": errors
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Gestion des erreurs HTTP avec Guardian."""
    import asyncio
    path = request.url.path
    status_code = exc.status_code

    # Log pour Guardian
    if status_code >= 400:
        logger.warning("http_error", path=path, status=status_code, detail=exc.detail)

    # === GUARDIAN: Envoyer les erreurs 4xx à AutoFixer ===
    if status_code in [400, 404, 422]:
        async def fix_http_error():
            try:
                from .autopilot import AutoFixer
                error_log = f"HTTP {status_code} on {path}: {exc.detail}"
                logger.info("http_error_to_autofixer", path=path, status=status_code)
                success, message = AutoFixer.try_fix(error_log)
                if success:
                    logger.info("http_error_fixed", path=path, message=message)
            except Exception as e:
                logger.warning("http_fix_failed", error=str(e))

        asyncio.create_task(fix_http_error())

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Gestion des erreurs générales avec auto-correction Guardian."""
    import traceback
    import sys
    import asyncio

    # Capturer le traceback complet
    tb = traceback.format_exc()
    error_log = f"{type(exc).__name__}: {exc}\n{tb}"

    # Log l'erreur (Guardian voit tout)
    logger.error("exception_traceback", path=request.url.path, error=str(exc), traceback=tb)

    # === AUTOFIXER + CLAUDEFIXER: Correction ASYNCHRONE ===
    async def analyze_in_background():
        """Analyse et corrige l'erreur en arrière-plan - invisible pour le client."""
        try:
            await Guardian.log_error(request, exc)

            # 1. Essayer AutoFixer d'abord (corrections automatiques)
            from .autopilot import AutoFixer
            logger.info("backend_error_to_autofixer", path=request.url.path, error_type=type(exc).__name__)

            success, message = AutoFixer.try_fix(error_log)
            if success:
                logger.info("backend_error_fixed", path=request.url.path, message=message)
                return  # Corrigé!

            # 2. Si AutoFixer échoue, AutoPilot analyse
            if _autopilot:
                proposal = _autopilot.analyze(error_log)

                if proposal:
                    if proposal.confidence >= 0.95:
                        result = _autopilot.validate(
                            proposal.id,
                            approved=True,
                            explanation="Auto-validated (high confidence pattern)"
                        )
                        if result.success:
                            logger.info("autopilot_auto_fix_applied",
                                       error_type=proposal.error_type,
                                       file=proposal.file_path,
                                       confidence=proposal.confidence)
                    else:
                        logger.info("autopilot_fix_pending",
                                   id=proposal.id,
                                   error_type=proposal.error_type,
                                   confidence=proposal.confidence)
        except Exception as autopilot_error:
            logger.warning("autopilot_analysis_failed", error=str(autopilot_error))

    # Lancer l'analyse en arrière-plan (fire-and-forget)
    asyncio.create_task(analyze_in_background())

    # Message neutre IMMÉDIAT pour l'utilisateur (Guardian invisible)
    return JSONResponse(
        status_code=500,
        content={"detail": "Une erreur est survenue"}
    )
