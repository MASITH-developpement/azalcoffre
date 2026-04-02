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

import os

# =============================================================================
# App Name (configurable via environment variable)
# =============================================================================
APP_NAME = os.environ.get("APP_NAME", "AZALPLUS")

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

    # Run pending schema migrations (safe to run multiple times)
    try:
        with Database.get_session() as session:
            from sqlalchemy import text
            # Add fonction column if missing (migration 005)
            session.execute(text("""
                ALTER TABLE azalplus.utilisateurs
                ADD COLUMN IF NOT EXISTS fonction VARCHAR(100) DEFAULT NULL
            """))
            # Add modules_mobile column if missing (migration 006)
            session.execute(text("""
                ALTER TABLE azalplus.utilisateurs
                ADD COLUMN IF NOT EXISTS modules_mobile TEXT DEFAULT NULL
            """))
            session.commit()
            logger.debug("schema_migrations_applied")
    except Exception as e:
        logger.warning("schema_migration_error", error=str(e))

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

    # Initialiser Guardian Learner (auto-apprentissage)
    try:
        from .autopilot.guardian_learner import get_guardian_learner
        guardian_learner = get_guardian_learner()
        logger.info("guardian_learner_ready",
                   learnings=guardian_learner.get_stats()["total_learnings"])
    except Exception as e:
        logger.warning("guardian_learner_init_failed", error=str(e))

    # Démarrer le collecteur d'erreurs (déclenche Guardian automatiquement)
    try:
        from .autopilot.error_collector import start_error_collector
        start_error_collector()
        logger.info("error_collector_started")
    except Exception as e:
        logger.warning("error_collector_start_failed", error=str(e))

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

    # Demarrer le scheduler de traitement des emails
    from .email_to_intervention import EmailToInterventionScheduler
    EmailToInterventionScheduler.start()

    logger.info("azalplus_ready", modules_loaded=ModuleParser.count())

    yield

    # Shutdown
    EmailToInterventionScheduler.stop()

    # Arrêter le collecteur d'erreurs Guardian
    try:
        from .autopilot.error_collector import stop_error_collector
        stop_error_collector()
        logger.info("error_collector_stopped")
    except Exception:
        pass

    await BackupService.stop_scheduler()
    await Database.disconnect()
    logger.info("azalplus_stopped")

# =============================================================================
# Application FastAPI
# =============================================================================
app = FastAPI(
    title=f"{APP_NAME} API",
    description=f"""
## {APP_NAME} - ERP No-Code Multi-Tenant

{APP_NAME} est un ERP moderne, flexible et extensible construit sur une architecture No-Code.

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
        "name": f"{APP_NAME} Support",
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

    # Protection contre le clickjacking (SAMEORIGIN pour permettre l'app mobile)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    # Protection contre le MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Protection XSS (navigateurs anciens)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy (ex-Feature-Policy)
    # Autoriser caméra/micro pour les pages Marceau (analyse expressions faciales, voix)
    if request.url.path.startswith("/ui/marceau") or request.url.path.startswith("/api/marceau"):
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=(self)"
    else:
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Content Security Policy (mode rapport pour ne pas casser l'existant)
    if not request.url.path.startswith("/api/"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.anthropic.com https://api.openai.com https://cdn.jsdelivr.net;"
            "frame-ancestors 'self';"
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
    "/api/admin/ambiance/custom",  # Codes couleurs hex (#XXXXXX)
    "/api/admin/tenants",  # Admin tenants - protégé par require_createur
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

@app.get("/", response_class=HTMLResponse)
async def root():
    """Page d'accueil - Landing page (avec branding dynamique)."""
    landing_path = Path(__file__).parent.parent / "docs" / "LANDING_PAGE_AZALPLUS.html"
    if landing_path.exists():
        # Appliquer le branding dynamique (APP_NAME)
        content = landing_path.read_text()
        content = content.replace("AZALPLUS", APP_NAME)
        return HTMLResponse(content=content)
    # Fallback si le fichier n'existe pas - utilise .replace() car CSS contient des accolades
    html = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__APP_NAME__ - Moteur ERP No-Code</title>
    <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bleu-roi: #3454D1;
            --bleu-accent: #6B9FFF;
            --bleu-marine: #1E3A8A;
        }

        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            padding: 20px;
        }

        .bg-shapes {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: -1;
            overflow: hidden;
        }

        .shape {
            position: absolute;
            border-radius: 50%;
            opacity: 0.1;
        }

        .shape-1 { width: 400px; height: 400px; background: var(--bleu-roi); top: -100px; right: -100px; }
        .shape-2 { width: 300px; height: 300px; background: var(--bleu-accent); bottom: -50px; left: -50px; }
        .shape-3 { width: 200px; height: 200px; background: var(--bleu-marine); top: 50%; left: 10%; }

        .container {
            background: white;
            border-radius: 24px;
            box-shadow: 0 25px 80px -12px rgba(52, 84, 209, 0.15);
            max-width: 500px;
            width: 100%;
            text-align: center;
            overflow: hidden;
            animation: fadeIn 0.6s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .header {
            background: linear-gradient(135deg, var(--bleu-roi) 0%, var(--bleu-marine) 100%);
            padding: 50px 30px;
            position: relative;
            overflow: hidden;
        }

        .header::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
            animation: shimmer 4s infinite;
        }

        @keyframes shimmer {
            0%, 100% { transform: translate(0, 0); }
            50% { transform: translate(20%, 20%); }
        }

        .logo {
            width: 120px;
            height: 120px;
            margin: 0 auto 20px;
            position: relative;
            z-index: 1;
        }

        .logo svg {
            width: 100%;
            height: 100%;
            filter: drop-shadow(0 10px 25px rgba(0,0,0,0.2));
        }

        .brand-name {
            font-size: 36px;
            font-weight: 800;
            color: white;
            letter-spacing: 2px;
            position: relative;
            z-index: 1;
            text-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }

        .brand-tagline {
            font-size: 14px;
            color: rgba(255,255,255,0.8);
            margin-top: 8px;
            position: relative;
            z-index: 1;
        }

        .body {
            padding: 40px 30px;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #ecfdf5;
            color: #059669;
            padding: 10px 20px;
            border-radius: 50px;
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 25px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.6; transform: scale(1.2); }
        }

        .version {
            font-size: 13px;
            color: #9ca3af;
            margin-bottom: 30px;
        }

        .actions {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 16px 24px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.3s ease;
            cursor: pointer;
            border: none;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--bleu-roi) 0%, var(--bleu-marine) 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(52, 84, 209, 0.4);
        }

        .btn-primary:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(52, 84, 209, 0.5);
        }

        .btn-secondary {
            background: #f3f4f6;
            color: #374151;
        }

        .btn-secondary:hover {
            background: #e5e7eb;
            transform: translateY(-2px);
        }

        .footer {
            padding: 20px;
            border-top: 1px solid #f3f4f6;
            font-size: 12px;
            color: #9ca3af;
        }

        .footer a {
            color: var(--bleu-roi);
            text-decoration: none;
        }

        .footer a:hover {
            text-decoration: underline;
        }

        @media (max-width: 480px) {
            .brand-name { font-size: 28px; }
            .header { padding: 40px 20px; }
            .body { padding: 30px 20px; }
            .logo { width: 100px; height: 100px; }
        }
    </style>
</head>
<body>
    <div class="bg-shapes">
        <div class="shape shape-1"></div>
        <div class="shape shape-2"></div>
        <div class="shape shape-3"></div>
    </div>

    <div class="container">
        <div class="header">
            <div class="logo">
                <svg viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="256" cy="256" r="256" fill="white"/>
                    <circle cx="380" cy="120" r="24" fill="#6B9FFF"/>
                    <text x="256" y="340" font-family="Arial Black, sans-serif" font-size="280" font-weight="900" fill="#3454D1" text-anchor="middle">A</text>
                    <text x="380" y="280" font-family="Arial Black, sans-serif" font-size="140" font-weight="900" fill="#3454D1" text-anchor="middle">+</text>
                </svg>
            </div>
            <div class="brand-name">__APP_NAME__</div>
            <div class="brand-tagline">Moteur ERP No-Code Multi-Tenant</div>
        </div>

        <div class="body">
            <div class="status-badge">
                <span class="status-dot"></span>
                Systeme operationnel
            </div>

            <div class="version">Version 1.0.0</div>

            <div class="actions">
                <a href="/ui/login" class="btn btn-primary">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
                        <polyline points="10,17 15,12 10,7"/>
                        <line x1="15" y1="12" x2="3" y2="12"/>
                    </svg>
                    Connexion
                </a>
                <a href="/docs" class="btn btn-secondary">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14,2 14,8 20,8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                        <polyline points="10,9 9,9 8,9"/>
                    </svg>
                    Documentation API
                </a>
                <a href="/health" class="btn btn-secondary">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                    </svg>
                    Health Check
                </a>
            </div>
        </div>

        <div class="footer">
            __APP_NAME__ &copy; 2024 &mdash; <a href="/docs">API</a> &bull; <a href="/health">Status</a>
        </div>
    </div>
</body>
</html>'''.replace('__APP_NAME__', APP_NAME)
    return HTMLResponse(content=html)

# =============================================================================
# Import des routers dynamiques
# =============================================================================
from .api import router as api_router, register_all_modules
from .auth import router as auth_router
from .storage import storage_router
from .backup import backup_router, BackupService
from .email_router import email_router
from .pdf_router import pdf_router
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

# Admin - Tenants Management (Createur uniquement)
from .admin_tenants import router as admin_tenants_router
app.include_router(admin_tenants_router, prefix="/api/admin/tenants", tags=["Admin - Tenants"])

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
app.include_router(pdf_router, tags=["PDF"])

# Email to Intervention (création auto depuis emails)
from .email_to_intervention import router as email_to_intervention_router
app.include_router(email_to_intervention_router, prefix="/api", tags=["Email to Intervention"])

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

# Import/Export Odoo Routes (API XML-RPC + CSV)
try:
    from app.modules.import_odoo import router as import_odoo_router
    app.include_router(import_odoo_router, tags=["Import/Export Odoo"])
    logger.info("import_odoo_routes_loaded")
except ImportError as e:
    logger.warning("import_odoo_routes_not_available", error=str(e))

# POS Router (Point de Vente - Sessions, Tickets, Produits)
try:
    from .pos_router import router as pos_router
    app.include_router(pos_router, prefix="/api/v1", tags=["POS"])
    logger.info("pos_routes_loaded")
except ImportError as e:
    logger.warning("pos_routes_not_available", error=str(e))

# POS Payments Routes (SumUp, Stripe Terminal, Tap to Pay)
try:
    from .pos_payments import pos_payments_router
    app.include_router(pos_payments_router, tags=["POS Payments"])
    logger.info("pos_payments_routes_loaded")
except ImportError as e:
    logger.warning("pos_payments_routes_not_available", error=str(e))

# Generated Endpoints (Auto-created by Guardian)
try:
    from .generated_endpoints import generated_router
    app.include_router(generated_router, prefix="/api", tags=["Generated"])
except ImportError:
    pass

# Recent Items Tracker
from .activity import recent_router
app.include_router(recent_router, prefix="/api", tags=["Recent"])

# =============================================================================
# MARCEAU - Assistant IA
# =============================================================================
try:
    from app.modules.marceau.router import router as marceau_router
    from app.modules.marceau.router_v2 import router as marceau_router_v2
    from app.modules.marceau.router_v3 import router as marceau_router_v3
    from app.modules.marceau.setup import init_marceau_tables
    app.include_router(marceau_router, tags=["Marceau IA"])
    app.include_router(marceau_router_v2, tags=["Marceau IA v2 - Agents & Scoring"])
    app.include_router(marceau_router_v3, tags=["Marceau IA v3 - Vision & Voice"])
    # Initialiser les tables au démarrage
    init_marceau_tables()
    logger.info("marceau_module_loaded", routers=["v1", "v2", "v3"])
except ImportError as e:
    logger.debug(f"marceau_module_not_available: {e}")
except Exception as e:
    logger.warning(f"marceau_module_error: {e}")

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
# Support pour chemins dynamiques selon APP_NAME
_app_assets_path = os.environ.get("AZALPLUS_ASSETS_PATH")
_app_static_path = os.environ.get("AZALPLUS_STATIC_PATH")

# Priorité : variable d'environnement > dossier app spécifique > azalplus par défaut
if _app_assets_path:
    static_path = Path(_app_assets_path)
else:
    static_path = Path(__file__).parent.parent / "assets"

if static_path.exists():
    app.mount("/assets", StaticFiles(directory=str(static_path), follow_symlink=True), name="assets")

# Static files (manifest.json, icons, etc.)
if _app_static_path:
    static_public_path = Path(_app_static_path)
else:
    static_public_path = Path(__file__).parent.parent / "static"

# =============================================================================
# Routes dynamiques pour fichiers statiques critiques (priorité sur StaticFiles)
# Ces routes sont définies AVANT le mount pour avoir la priorité dans FastAPI
# =============================================================================

def _get_static_file_path(filename: str, subdirs: list = None) -> Path | None:
    """Cherche un fichier statique avec fallback selon APP_NAME."""
    app_name_lower = APP_NAME.lower()
    subdirs = subdirs or ["static", "assets"]

    possible_paths = []
    for subdir in subdirs:
        possible_paths.append(Path(f"/home/ubuntu/{app_name_lower}/{subdir}/{filename}"))
    possible_paths.extend([
        static_public_path / filename,
        static_path / filename,
    ])

    # Debug logging
    import structlog
    logger = structlog.get_logger()
    logger.debug("static_file_search", filename=filename, app_name=APP_NAME, paths=[str(p) for p in possible_paths])

    for path in possible_paths:
        if path.exists():
            logger.debug("static_file_found", path=str(path))
            return path
    return None

@app.get("/static/logo.png", response_class=FileResponse)
async def serve_logo_png():
    """Sert le logo PNG avec fallback selon APP_NAME."""
    path = _get_static_file_path("logo.png")
    if path:
        return FileResponse(str(path))
    # Fallback : retourner le favicon comme logo
    favicon_path = _get_static_file_path("favicon.ico")
    if favicon_path:
        return FileResponse(str(favicon_path))
    raise HTTPException(status_code=404, detail="Logo not found")

@app.get("/static/logo.svg", response_class=FileResponse)
async def serve_logo_svg():
    """Sert le logo SVG avec fallback selon APP_NAME."""
    app_name_lower = APP_NAME.lower()
    # Essayer d'abord logo-{appname}.svg, puis logo.svg
    path = _get_static_file_path(f"logo-{app_name_lower}.svg")
    if not path:
        path = _get_static_file_path("logo.svg")
    if path:
        return FileResponse(str(path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Logo SVG not found")

@app.get("/static/__debug__")
async def debug_static_config():
    """Debug: affiche la configuration des fichiers statiques (route publique sous /static)."""
    return {
        "APP_NAME": APP_NAME,
        "static_public_path": str(static_public_path),
        "static_path": str(static_path),
        "_app_static_path": _app_static_path,
        "_app_assets_path": _app_assets_path,
        "manifest_search": str(_get_static_file_path("manifest.json")),
    }

@app.get("/static/manifest.json", response_class=FileResponse)
async def serve_manifest():
    """Sert le manifest.json avec fallback selon APP_NAME."""
    path = _get_static_file_path("manifest.json")
    if path:
        return FileResponse(str(path), media_type="application/json")
    raise HTTPException(status_code=404, detail="Manifest not found")

@app.get("/static/favicon.ico", response_class=FileResponse)
async def serve_favicon_ico():
    """Sert le favicon.ico avec fallback selon APP_NAME."""
    path = _get_static_file_path("favicon.ico")
    if path:
        return FileResponse(str(path), media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/static/favicon.svg", response_class=FileResponse)
async def serve_favicon_svg():
    """Sert le favicon.svg avec fallback selon APP_NAME."""
    path = _get_static_file_path("favicon.svg")
    if path:
        return FileResponse(str(path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Favicon SVG not found")

# Route générique pour servir les autres fichiers statiques avec fallback APP_NAME
@app.get("/static/{filepath:path}", response_class=FileResponse)
async def serve_static_file(filepath: str):
    """Sert un fichier statique avec fallback selon APP_NAME."""
    # Déterminer le type MIME
    import mimetypes
    mime_type, _ = mimetypes.guess_type(filepath)
    if not mime_type:
        mime_type = "application/octet-stream"

    path = _get_static_file_path(filepath)
    if path:
        return FileResponse(str(path), media_type=mime_type)
    raise HTTPException(status_code=404, detail=f"Static file not found: {filepath}")

# =============================================================================
# Login page (public)
# =============================================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Page de connexion (avec branding dynamique)."""
    template_path = Path(__file__).parent.parent / "templates" / "ui" / "login.html"
    if template_path.exists():
        content = template_path.read_text()
        content = content.replace("AZALPLUS", APP_NAME)
        return HTMLResponse(content=content)
    return HTMLResponse(content=f"<h1>{APP_NAME} Login</h1>")

# =============================================================================
# Waitlist page (public)
# =============================================================================
@app.get("/waitlist", response_class=HTMLResponse)
async def waitlist_page():
    """Page d'inscription à la liste d'attente (avec branding dynamique)."""
    template_path = Path(__file__).parent.parent / "templates" / "waitlist.html"
    if template_path.exists():
        content = template_path.read_text()
        content = content.replace("AZALPLUS", APP_NAME)
        return HTMLResponse(content=content)
    return HTMLResponse(content=f"<h1>{APP_NAME} Waitlist</h1>")

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
# Test Error Pages (TEMPORAIRE - à supprimer après validation)
# =============================================================================
@app.get("/test-erreurs", response_class=HTMLResponse)
async def test_erreurs_index():
    """Page index pour tester les pages d'erreur."""
    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Pages d'Erreur | {APP_NAME}</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f5f5f5; padding: 40px; }
        .container { max-width: 800px; margin: 0 auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
        h1 { color: #1f2937; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }
        a { display: block; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 8px; text-align: center; font-weight: 500; transition: transform 0.2s; }
        a:hover { transform: translateY(-3px); }
        .code { font-size: 32px; font-weight: 800; }
        .label { font-size: 12px; opacity: 0.9; margin-top: 8px; }
        .warning { background: #fef3c7; border: 1px solid #f59e0b; padding: 16px; border-radius: 8px; margin-top: 30px; color: #92400e; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 Test des Pages d'Erreur</h1>
        <p style="color: #6b7280; margin-bottom: 30px;">Cliquez sur un code pour voir la page d'erreur correspondante.</p>
        <div class="grid">
            <a href="/test-erreurs/400"><div class="code">400</div><div class="label">Requête invalide</div></a>
            <a href="/test-erreurs/401"><div class="code">401</div><div class="label">Non authentifié</div></a>
            <a href="/test-erreurs/403"><div class="code">403</div><div class="label">Accès refusé</div></a>
            <a href="/test-erreurs/404"><div class="code">404</div><div class="label">Page introuvable</div></a>
            <a href="/test-erreurs/405"><div class="code">405</div><div class="label">Méthode non autorisée</div></a>
            <a href="/test-erreurs/408"><div class="code">408</div><div class="label">Timeout</div></a>
            <a href="/test-erreurs/422"><div class="code">422</div><div class="label">Données invalides</div></a>
            <a href="/test-erreurs/429"><div class="code">429</div><div class="label">Trop de requêtes</div></a>
            <a href="/test-erreurs/500"><div class="code">500</div><div class="label">Erreur serveur</div></a>
            <a href="/test-erreurs/502"><div class="code">502</div><div class="label">Bad Gateway</div></a>
            <a href="/test-erreurs/503"><div class="code">503</div><div class="label">Service indisponible</div></a>
            <a href="/test-erreurs/504"><div class="code">504</div><div class="label">Gateway Timeout</div></a>
        </div>
        <div class="warning">
            ⚠️ <strong>Page temporaire</strong> - Cette page sera supprimée après validation.
        </div>
    </div>
</body>
</html>
""")

@app.get("/test-erreurs/{code}", response_class=HTMLResponse)
async def test_erreur_page(request: Request, code: int):
    """Affiche une page d'erreur pour test."""
    if code not in [400, 401, 403, 404, 405, 408, 422, 429, 500, 502, 503, 504]:
        code = 404
    return render_error_page(code, request)

# =============================================================================
# Landing Page (public)
# =============================================================================
@app.get("/LANDING_PAGE_AZALPLUS.html", response_class=HTMLResponse)
async def landing_page():
    """Page d'accueil."""
    landing_path = Path(__file__).parent.parent / "docs" / "LANDING_PAGE_AZALPLUS.html"
    if landing_path.exists():
        return HTMLResponse(content=landing_path.read_text())
    return HTMLResponse(content=f"<h1>{APP_NAME}</h1>", status_code=404)

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
    import yaml

    try:
        data = await request.json()
        ambiance = data.get("ambiance", "calme")

        # Chemins des fichiers
        base_dir = Path(__file__).parent.parent
        assets_dir = base_dir / "assets"
        target_file = assets_dir / "style.css"
        themes_config = base_dir / "config" / "themes.yml"

        # Lire les thèmes depuis config/themes.yml (AZAP-NC-001)
        available_styles = {}
        if themes_config.exists():
            with open(themes_config, 'r', encoding='utf-8') as f:
                themes_data = yaml.safe_load(f)
                if themes_data and 'themes' in themes_data:
                    for key, theme in themes_data['themes'].items():
                        available_styles[key] = theme.get('fichier', f"ambiance_{key}.css")

        # Fallback: scanner les fichiers CSS si themes.yml n'existe pas
        if not available_styles:
            for css_file in assets_dir.glob("*.css"):
                if css_file.name == "style.css":
                    continue
                name = css_file.stem
                if name.startswith("ambiance_"):
                    style_key = name.replace("ambiance_", "")
                elif name.startswith("style_"):
                    style_key = name.replace("style_", "")
                else:
                    style_key = name
                available_styles[style_key] = css_file.name

        # Valider l'ambiance
        if ambiance not in available_styles:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Ambiance invalide. Choisir parmi: {', '.join(sorted(available_styles.keys()))}"}
            )

        source_file = assets_dir / available_styles[ambiance]

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


@app.post("/api/admin/ambiance/custom")
async def apply_custom_ambiance(request: Request):
    """Appliquer une ambiance personnalisée en modifiant les variables CSS du template premium."""
    import re

    try:
        data = await request.json()

        # Extraire les couleurs
        primary = data.get("primary", "#635BFF")
        primary_dark = data.get("primary_dark", "#5851EA")
        sidebar = data.get("sidebar", "#0A2540")
        sidebar_hover = data.get("sidebar_hover", "#0F3358")
        accent = data.get("accent", "#00D4FF")
        background = data.get("background", "#F6F9FC")
        success = data.get("success", "#30D158")
        error = data.get("error", "#FF453A")
        radius = data.get("radius", 6)

        # Lire le CSS premium comme base
        base_dir = Path(__file__).parent.parent
        assets_dir = base_dir / "assets"
        premium_css = (assets_dir / "ambiance_premium.css").read_text(encoding="utf-8")

        # Remplacer les couleurs dans :root
        replacements = [
            (r'--primary: #[0-9A-Fa-f]{6};', f'--primary: {primary};'),
            (r'--primary-dark: #[0-9A-Fa-f]{6};', f'--primary-dark: {primary_dark};'),
            (r'--primary-light: #[0-9A-Fa-f]{6};', f'--primary-light: {lighten_color(primary, 0.9)};'),
            (r'--primary-50: #[0-9A-Fa-f]{6};', f'--primary-50: {lighten_color(primary, 0.95)};'),
            (r'--accent: #[0-9A-Fa-f]{6};', f'--accent: {accent};'),
            (r'--sidebar-bg: #[0-9A-Fa-f]{6};', f'--sidebar-bg: {sidebar};'),
            (r'--sidebar-hover: #[0-9A-Fa-f]{6};', f'--sidebar-hover: {sidebar_hover};'),
            (r'--success: #[0-9A-Fa-f]{6};', f'--success: {success};'),
            (r'--success-light: #[0-9A-Fa-f]{6};', f'--success-light: {lighten_color(success, 0.85)};'),
            (r'--error: #[0-9A-Fa-f]{6};', f'--error: {error};'),
            (r'--error-light: #[0-9A-Fa-f]{6};', f'--error-light: {lighten_color(error, 0.85)};'),
            (r'--info: #[0-9A-Fa-f]{6};', f'--info: {accent};'),
            (r'--info-light: #[0-9A-Fa-f]{6};', f'--info-light: {lighten_color(accent, 0.85)};'),
            (r'--radius: \d+px;', f'--radius: {radius}px;'),
            (r'--radius-lg: \d+px;', f'--radius-lg: {radius + 4}px;'),
        ]

        custom_css = premium_css
        for pattern, replacement in replacements:
            custom_css = re.sub(pattern, replacement, custom_css)

        # Remplacer le commentaire d'en-tête
        custom_css = re.sub(
            r'/\* =+\s+AZALPLUS - Ambiance Premium.*?=+ \*/',
            '''/* =============================================================================
   AZALPLUS - Ambiance Personnalisée
   Générée depuis le template Premium avec vos couleurs
   ============================================================================= */''',
            custom_css,
            flags=re.DOTALL
        )

        # Remplacer le fond de page
        custom_css = re.sub(
            r'background: linear-gradient\(180deg, var\(--gray-50\) 0%, var\(--white\) 100%\);',
            f'background: {background};',
            custom_css
        )

        # Écrire le fichier CSS
        target_file = assets_dir / "style.css"
        target_file.write_text(custom_css, encoding="utf-8")

        logger.info("custom_ambiance_applied", primary=primary, sidebar=sidebar)

        return JSONResponse(
            status_code=200,
            content={"message": "Ambiance personnalisée appliquée avec succès"}
        )

    except Exception as e:
        logger.error("custom_ambiance_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"detail": f"Erreur: {str(e)}"}
        )


def lighten_color(hex_color: str, factor: float) -> str:
    """Éclaircir une couleur hex."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))

    return f"#{r:02X}{g:02X}{b:02X}"


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
from starlette.exceptions import HTTPException as StarletteHTTPException
from .error_pages import render_error_page

def _is_html_request(request: Request) -> bool:
    """Détermine si la requête attend une réponse HTML."""
    path = request.url.path
    # Routes UI qui attendent du HTML
    if path.startswith("/ui/") or path in ["/login", "/inscription", "/waitlist", "/partenaires"]:
        return True
    # Vérifier le header Accept
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return True
    return False

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

    # Retourner une page HTML stylisée pour les requêtes UI
    if _is_html_request(request):
        return render_error_page(422, request, "Les données envoyées ne sont pas valides.")

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

    # Retourner une page HTML stylisée pour les requêtes UI
    if _is_html_request(request):
        return render_error_page(status_code, request, str(exc.detail) if exc.detail else None)

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

    # Retourner une page HTML stylisée pour les requêtes UI
    if _is_html_request(request):
        return render_error_page(500, request)

    # Message neutre IMMÉDIAT pour l'utilisateur (Guardian invisible)
    return JSONResponse(
        status_code=500,
        content={"detail": "Une erreur est survenue"}
    )


@app.exception_handler(StarletteHTTPException)
async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    """Gestion des erreurs HTTP Starlette (404 sur routes inexistantes, etc.)."""
    status_code = exc.status_code

    # Log pour les erreurs significatives
    if status_code >= 400:
        logger.warning("starlette_http_error", path=request.url.path, status=status_code, detail=exc.detail)

    # Retourner une page HTML stylisée pour les requêtes UI
    if _is_html_request(request):
        return render_error_page(status_code, request, str(exc.detail) if exc.detail else None)

    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.detail or "Une erreur est survenue"}
    )


# =============================================================================
# POS UI Routes (Point de Vente - Interface tactile)
# =============================================================================
from jinja2 import Environment, FileSystemLoader

pos_templates_path = Path(__file__).parent.parent / "templates" / "pos"
pos_env = Environment(loader=FileSystemLoader(str(pos_templates_path)))


@app.get("/ui/pos/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/ui/pos", response_class=HTMLResponse, include_in_schema=False)
async def pos_index(request: Request):
    """Interface POS principale."""
    try:
        template = pos_env.get_template("index.html")
        return HTMLResponse(content=template.render(request=request))
    except Exception as e:
        logger.error("pos_index_error", error=str(e))
        return render_error_page(500, request, "Erreur POS")


@app.get("/ui/pos/session/open", response_class=HTMLResponse, include_in_schema=False)
async def pos_session_open(request: Request):
    """Page d'ouverture de session POS."""
    try:
        template = pos_env.get_template("session_open.html")
        return HTMLResponse(content=template.render(request=request))
    except Exception as e:
        logger.error("pos_session_open_error", error=str(e))
        return render_error_page(500, request, "Erreur POS")


@app.get("/ui/pos/session/close", response_class=HTMLResponse, include_in_schema=False)
async def pos_session_close(request: Request):
    """Page de clôture de session POS."""
    try:
        template = pos_env.get_template("session_close.html")
        return HTMLResponse(content=template.render(request=request))
    except Exception as e:
        logger.error("pos_session_close_error", error=str(e))
        return render_error_page(500, request, "Erreur POS")


@app.get("/ui/pos/payment", response_class=HTMLResponse, include_in_schema=False)
async def pos_payment(request: Request):
    """Page de paiement POS."""
    try:
        template = pos_env.get_template("payment.html")
        return HTMLResponse(content=template.render(request=request))
    except Exception as e:
        logger.error("pos_payment_error", error=str(e))
        return render_error_page(500, request, "Erreur POS")


# =============================================================================
# Catch-all route pour 404 sur les chemins UI
# IMPORTANT: Cette route doit être définie EN DERNIER
# =============================================================================
@app.get("/ui/{path:path}", response_class=HTMLResponse, include_in_schema=False)
async def ui_catch_all(request: Request, path: str):
    """Catch-all pour les routes UI inexistantes."""
    return render_error_page(404, request, f"La page '/ui/{path}' n'existe pas.")
