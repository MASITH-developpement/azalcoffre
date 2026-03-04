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
import structlog

from .config import settings
from .guardian import Guardian, CREATEUR_EMAIL

logger = structlog.get_logger()

# =============================================================================
# Contexte Tenant (Thread-safe)
# =============================================================================
class TenantContext:
    """Contexte tenant pour la requête courante."""

    _current_tenant_id: Optional[UUID] = None
    _current_user_id: Optional[UUID] = None
    _current_user_email: Optional[str] = None

    @classmethod
    def set(cls, tenant_id: UUID, user_id: Optional[UUID] = None, email: Optional[str] = None):
        """Définit le contexte tenant."""
        cls._current_tenant_id = tenant_id
        cls._current_user_id = user_id
        cls._current_user_email = email

    @classmethod
    def get_tenant_id(cls) -> Optional[UUID]:
        """Retourne le tenant_id courant."""
        return cls._current_tenant_id

    @classmethod
    def get_user_id(cls) -> Optional[UUID]:
        """Retourne le user_id courant."""
        return cls._current_user_id

    @classmethod
    def is_createur(cls) -> bool:
        """Vérifie si l'utilisateur courant est le Créateur."""
        return cls._current_user_email == CREATEUR_EMAIL

    @classmethod
    def clear(cls):
        """Efface le contexte."""
        cls._current_tenant_id = None
        cls._current_user_id = None
        cls._current_user_email = None

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
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercepte chaque requête pour injecter le contexte tenant."""

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
                return Response(
                    content=f'{{"detail": "{check.neutral_message}"}}',
                    status_code=404,
                    media_type="application/json"
                )

        # Définir le contexte tenant
        # user_tenant_id peut être UUID ou string selon la source
        raw_tenant_id = request_tenant_id or user_tenant_id
        if isinstance(raw_tenant_id, UUID):
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
