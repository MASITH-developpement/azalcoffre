# =============================================================================
# AZALPLUS - Multi-Tenant Middleware
# =============================================================================
"""
Gestion du multi-tenant.
Chaque requête est isolée par tenant_id.
AUCUNE donnée ne peut fuiter entre tenants.
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from typing import Optional, Callable
from uuid import UUID
from contextvars import ContextVar
import structlog

from .config import settings
from .guardian import Guardian, CREATEUR_EMAIL
from .error_pages import render_error_page

logger = structlog.get_logger()


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

# =============================================================================
# Contexte Tenant (Async-safe avec contextvars)
# =============================================================================
# Tenant systeme pour le createur (UUID fixe)
SYSTEM_TENANT_ID = UUID("00000000-0000-0000-0000-000000000000")

# Utilisation de contextvars pour l'isolation correcte entre requêtes async
_tenant_id_var: ContextVar[Optional[UUID]] = ContextVar('tenant_id', default=None)
_user_id_var: ContextVar[Optional[UUID]] = ContextVar('user_id', default=None)
_user_email_var: ContextVar[Optional[str]] = ContextVar('user_email', default=None)


class TenantContext:
    """Contexte tenant pour la requête courante (async-safe)."""

    @classmethod
    def set(cls, tenant_id: UUID, user_id: Optional[UUID] = None, email: Optional[str] = None):
        """Définit le contexte tenant."""
        _tenant_id_var.set(tenant_id)
        _user_id_var.set(user_id)
        _user_email_var.set(email)

    @classmethod
    def get_tenant_id(cls) -> Optional[UUID]:
        """Retourne le tenant_id courant."""
        return _tenant_id_var.get()

    @classmethod
    def get_user_id(cls) -> Optional[UUID]:
        """Retourne le user_id courant."""
        return _user_id_var.get()

    @classmethod
    def is_createur(cls) -> bool:
        """Vérifie si l'utilisateur courant est le Créateur."""
        return _user_email_var.get() == CREATEUR_EMAIL

    @classmethod
    def clear(cls):
        """Efface le contexte."""
        _tenant_id_var.set(None)
        _user_id_var.set(None)
        _user_email_var.set(None)

# =============================================================================
# Middleware Multi-Tenant
# =============================================================================
class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware d'isolation multi-tenant."""

    # Routes sans authentification requise
    PUBLIC_ROUTES = [
        "/",
        "/health",
        "/login",
        "/favicon.ico",
        "/assets",
        "/static",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/api/auth/forgot-password",
        # === APIs publiques - données gov.fr et externes ===
        # Entreprise (SIRET/SIREN)
        "/api/autocompletion-ia/entreprise",
        # Adresses (API Adresse gouv.fr)
        "/api/autocompletion-ia/adresse",
        # Produits (Open Food Facts)
        "/api/autocompletion-ia/produit",
        # TVA (VIES)
        "/api/autocompletion-ia/tva",
        # IBAN / BIC (validation)
        "/api/autocompletion-ia/iban",
        "/api/autocompletion-ia/bic",
        # Smart lookup (unifié)
        "/api/autocompletion-ia/smart-lookup",
        # Icons (public)
        "/api/icons",
        # Mobile connect (QR code auth)
        "/api/mobile/connect",
        # Guardian - Error reporting (public, rate-limited)
        "/guardian/frontend-error",
        # Waitlist - Pré-inscription (public)
        "/waitlist",
        "/inscription",
        "/api/public/waitlist",
        # Landing page (public)
        "/LANDING_PAGE_AZALPLUS.html",
        # Partenaires (public)
        "/partenaires",
        # Test pages d'erreur (TEMPORAIRE)
        "/test-erreurs",
        # Création Entreprise - Outils publics
        "/api/creation/simulateur-statut/public",
        "/api/creation/checklist-creation",
        "/api/creation/organismes",
        "/api/creation/aides-financements",
        # Prometheus metrics (filtré par IP dans le handler)
        "/metrics",
        # Ambiance personnalisée (utilisateur connecté via cookie)
        "/api/admin/ambiance/custom",
        "/api/admin/ambiance",
        # === SEO & Referencing (public) ===
        "/robots.txt",
        "/sitemap.xml",
        "/llms.txt",
        "/llms-full.txt",
        "/manifest.json",
        "/humans.txt",
        "/.well-known/security.txt",
        "/ai-plugin.json",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercepte chaque requête pour injecter le contexte tenant."""

        # Laisser passer les requêtes OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Routes publiques - pas de vérification tenant
        if self._is_public_route(request.url.path):
            return await call_next(request)

        # Récupérer l'utilisateur depuis le state (ajouté par AuthMiddleware)
        user = getattr(request.state, "user", None)

        logger.debug("tenant_middleware", path=request.url.path, has_user=bool(user),
                     user_email=user.get("email") if user else None,
                     user_tenant=str(user.get("tenant_id")) if user and user.get("tenant_id") else None)

        if not user:
            # Pas d'utilisateur = pas d'accès
            if _is_html_request(request):
                return render_error_page(401, request)
            return Response(
                content='{"detail": "Non authentifié"}',
                status_code=401,
                media_type="application/json"
            )

        # Extraire tenant_id de l'utilisateur
        user_tenant_id = user.get("tenant_id")
        user_email = user.get("email")
        user_id = user.get("id")

        if not user_tenant_id and user_email != CREATEUR_EMAIL:
            if _is_html_request(request):
                return render_error_page(400, request, "Tenant non défini")
            return Response(
                content='{"detail": "Tenant non défini"}',
                status_code=400,
                media_type="application/json"
            )

        # Vérifier si la requête cible un tenant spécifique
        request_tenant_id = self._extract_tenant_from_request(request)

        if request_tenant_id:
            # Guardian vérifie l'accès
            check = await Guardian.check_tenant_access(
                request_tenant_id=request_tenant_id,
                user_tenant_id=UUID(user_tenant_id) if user_tenant_id else None,
                user_email=user_email
            )

            if check.blocked:
                # Message neutre - Guardian invisible
                if _is_html_request(request):
                    return render_error_page(404, request)
                return Response(
                    content=f'{{"detail": "{check.neutral_message}"}}',
                    status_code=404,
                    media_type="application/json"
                )

        # Définir le contexte tenant
        # user_tenant_id peut être UUID ou string selon la source
        raw_tenant_id = request_tenant_id or user_tenant_id

        # Createur sans tenant => utiliser le tenant systeme
        if not raw_tenant_id and user_email == CREATEUR_EMAIL:
            tenant_id = SYSTEM_TENANT_ID
        elif isinstance(raw_tenant_id, UUID):
            tenant_id = raw_tenant_id
        else:
            tenant_id = UUID(str(raw_tenant_id))

        # user_id peut être UUID ou string
        if user_id:
            if isinstance(user_id, UUID):
                parsed_user_id = user_id
            else:
                parsed_user_id = UUID(str(user_id))
        else:
            parsed_user_id = None

        TenantContext.set(
            tenant_id=tenant_id,
            user_id=parsed_user_id,
            email=user_email
        )

        # Stocker dans request.state pour accès facile
        request.state.tenant_id = tenant_id

        try:
            response = await call_next(request)
            return response
        finally:
            # Toujours nettoyer le contexte
            TenantContext.clear()

    def _is_public_route(self, path: str) -> bool:
        """Vérifie si la route est publique."""
        for route in self.PUBLIC_ROUTES:
            # "/" doit être une correspondance exacte
            if route == "/":
                if path == "/":
                    return True
            elif path.startswith(route):
                return True
        return False

    def _extract_tenant_from_request(self, request: Request) -> Optional[str]:
        """Extrait le tenant_id de la requête si présent."""

        # 1. Header X-Tenant-ID
        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant:
            return header_tenant

        # 2. Query param tenant_id
        query_tenant = request.query_params.get("tenant_id")
        if query_tenant:
            return query_tenant

        # 3. Dans l'URL (pour certains endpoints)
        # Ex: /api/tenants/{tenant_id}/...
        path_parts = request.url.path.split("/")
        if "tenants" in path_parts:
            idx = path_parts.index("tenants")
            if idx + 1 < len(path_parts):
                return path_parts[idx + 1]

        return None

# =============================================================================
# Dependency pour les routes
# =============================================================================
def get_current_tenant() -> UUID:
    """Dependency pour récupérer le tenant_id courant."""
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant non défini")
    return tenant_id

def get_current_user_id() -> Optional[UUID]:
    """Dependency pour récupérer le user_id courant."""
    return TenantContext.get_user_id()

def require_createur():
    """Dependency qui exige d'être le Créateur."""
    if not TenantContext.is_createur():
        raise HTTPException(status_code=404, detail="Not found")
    return True
