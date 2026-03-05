# =============================================================================
# AZALPLUS - Core Engine
# =============================================================================
"""
Point d'entrée principal du moteur AZALPLUS.
Orchestre tous les composants : DB, API, UI, Guardian, etc.
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import structlog
import time
from typing import Callable

from .config import settings
from .db import Database
from .parser import ModuleParser
from .guardian import Guardian
from .tenant import TenantMiddleware
from .auth import AuthManager, AuthMiddleware, users_router
from .ratelimit import RateLimitMiddleware
from .csrf import CSRFMiddleware
from .waf import WAF
from .encryption import verify_encryption_setup
from .i18n import preload_translations, get_language_from_request, set_language
from .icons import IconManager

# =============================================================================
# Logging
# =============================================================================
logger = structlog.get_logger()

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

    # Vérifier la configuration de l'encryption
    verify_encryption_setup()

    # Log WAF stats
    logger.info("waf_ready", total_patterns=WAF.get_total_patterns())

    # Initialize workflow engine
    from .workflows import WorkflowEngine
    WorkflowEngine.initialize()

    # Initialize icons manager
    IconManager.initialize()

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

# Request timing middleware
@app.middleware("http")
async def timing_middleware(request: Request, call_next: Callable):
    """Mesure le temps de réponse."""
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    return response

# Guardian middleware (sécurité invisible)
@app.middleware("http")
async def guardian_middleware(request: Request, call_next: Callable):
    """Guardian surveille et protège silencieusement."""
    import traceback
    import sys

    try:
        # Vérification Guardian AVANT
        check_result = await Guardian.check_request(request)

        if check_result.blocked:
            # Message neutre - Guardian reste invisible
            return JSONResponse(
                status_code=400,
                content={"detail": check_result.neutral_message}
            )

        # Exécution normale
        response = await call_next(request)

        # Log Guardian APRÈS (silencieux)
        await Guardian.log_request(request, response)

        return response
    except Exception as e:
        print(f"MIDDLEWARE EXCEPTION on {request.url.path}: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
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
from .api_v1 import router_v1, register_v1_modules
from .icons import router as icons_router
from .stock_router import stock_router
from .workflows_api import workflows_router
from .mobile_api import router_mobile
from .sync_api import router_sync
from .planning_optimizer import router as planning_router

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

# Authentication
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])

# Admin - Users Management
app.include_router(users_router, prefix="/api/admin/users", tags=["Admin - Users"])

# Legacy API (backwards compatibility)
app.include_router(api_router, prefix="/api", tags=["API (Legacy)"])

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

# Planning Optimizer
app.include_router(planning_router, tags=["Planning"])

# Sync API (offline support)
app.include_router(router_sync, prefix="/api", tags=["Sync"])

# Notifications
if notification_router:
    app.include_router(notification_router, prefix="/api", tags=["Notifications"])

# Push Notifications
if push_router:
    app.include_router(push_router, prefix="/api", tags=["Push Notifications"])

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
# Exception handlers
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Gestion des erreurs HTTP."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Gestion des erreurs générales."""
    # Log l'erreur (Guardian voit tout)
    import traceback
    import sys
    print(f"EXCEPTION on {request.url.path}: {exc}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    logger.error("exception_traceback", path=request.url.path, error=str(exc), traceback=traceback.format_exc())
    await Guardian.log_error(request, exc)

    # Message neutre pour l'utilisateur
    return JSONResponse(
        status_code=500,
        content={"detail": "Une erreur est survenue"}
    )
