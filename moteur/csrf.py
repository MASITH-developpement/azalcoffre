# =============================================================================
# AZALPLUS - CSRF Protection Middleware
# =============================================================================
"""
Protection CSRF (Cross-Site Request Forgery).

Fonctionnalites:
- Generation de tokens CSRF securises
- Validation sur POST/PUT/DELETE/PATCH
- Injection automatique dans les formulaires HTML
- Rotation des tokens (24h)
- Double Submit Cookie pattern
- Support SameSite cookie
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
import hmac
import structlog

from .config import settings

logger = structlog.get_logger()

# =============================================================================
# CONFIGURATION
# =============================================================================
CSRF_TOKEN_LENGTH = 32  # bytes
CSRF_TOKEN_TTL = 24 * 60 * 60  # 24 heures en secondes
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "_csrf"
CSRF_COOKIE_NAME = "csrf_token"

# Methodes HTTP qui necessitent une validation CSRF
CSRF_PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# Routes exemptees de CSRF (API avec JWT, webhooks, etc.)
CSRF_EXEMPT_PATHS = [
    "/api/",  # Toutes les API REST utilisent JWT, pas besoin de CSRF
    "/auth/login",  # Login utilise credentials, pas de CSRF
    "/health",
    "/guardian/frontend-error",  # Endpoint public pour reporting erreurs frontend
]


# =============================================================================
# CSRF TOKEN MANAGER
# =============================================================================
class CSRFTokenManager:
    """Gestionnaire de tokens CSRF."""

    @staticmethod
    def generate_token() -> str:
        """
        Genere un token CSRF securise.

        Returns:
            Token CSRF en hexadecimal
        """
        return secrets.token_hex(CSRF_TOKEN_LENGTH)

    @staticmethod
    def create_signed_token(secret_key: str, session_id: Optional[str] = None) -> str:
        """
        Cree un token CSRF signe avec timestamp.

        Args:
            secret_key: Cle secrete pour la signature
            session_id: ID de session optionnel pour lier le token

        Returns:
            Token signe format: token:timestamp:signature
        """
        token = secrets.token_hex(CSRF_TOKEN_LENGTH)
        timestamp = str(int(datetime.utcnow().timestamp()))

        # Donnees a signer
        data = f"{token}:{timestamp}"
        if session_id:
            data = f"{data}:{session_id}"

        # Signature HMAC-SHA256
        signature = hmac.new(
            secret_key.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()[:16]  # Tronquer pour raccourcir

        return f"{token}:{timestamp}:{signature}"

    @staticmethod
    def verify_signed_token(
        token_string: str,
        secret_key: str,
        session_id: Optional[str] = None,
        max_age: int = CSRF_TOKEN_TTL
    ) -> bool:
        """
        Verifie un token CSRF signe.

        Args:
            token_string: Token a verifier (format token:timestamp:signature)
            secret_key: Cle secrete pour la verification
            session_id: ID de session si utilise a la creation
            max_age: Age maximum du token en secondes

        Returns:
            True si le token est valide
        """
        try:
            parts = token_string.split(":")
            if len(parts) != 3:
                return False

            token, timestamp, signature = parts

            # Verifier l'age
            token_time = int(timestamp)
            current_time = int(datetime.utcnow().timestamp())

            if current_time - token_time > max_age:
                logger.debug("csrf_token_expired", age=current_time - token_time)
                return False

            # Recreer la signature
            data = f"{token}:{timestamp}"
            if session_id:
                data = f"{data}:{session_id}"

            expected_signature = hmac.new(
                secret_key.encode(),
                data.encode(),
                hashlib.sha256
            ).hexdigest()[:16]

            # Comparaison securisee
            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error("csrf_verify_error", error=str(e))
            return False


# =============================================================================
# CSRF MIDDLEWARE
# =============================================================================
class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware de protection CSRF.

    Utilise le pattern Double Submit Cookie:
    1. Un cookie CSRF est defini (httponly=false pour JS)
    2. Le client doit renvoyer le token dans un header ou champ de formulaire
    3. Le middleware verifie que les deux correspondent
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Traite la requete avec protection CSRF."""

        # Verifier si la route est exemptee
        if self._is_exempt(request.url.path):
            return await call_next(request)

        # Recuperer ou generer le token CSRF
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)

        if not csrf_cookie:
            # Generer un nouveau token
            csrf_cookie = CSRFTokenManager.create_signed_token(settings.SECRET_KEY)

        # Valider CSRF pour les methodes protegees
        if request.method in CSRF_PROTECTED_METHODS:
            # Recuperer le token depuis header ou formulaire
            csrf_token = await self._get_csrf_token(request)

            if not csrf_token:
                logger.warning(
                    "csrf_missing",
                    path=request.url.path,
                    method=request.method
                )
                raise HTTPException(
                    status_code=403,
                    detail="Token CSRF manquant"
                )

            # Verifier que le token correspond au cookie
            if not self._verify_tokens(csrf_cookie, csrf_token):
                logger.warning(
                    "csrf_invalid",
                    path=request.url.path,
                    method=request.method
                )
                raise HTTPException(
                    status_code=403,
                    detail="Token CSRF invalide"
                )

        # Executer la requete
        response = await call_next(request)

        # Definir/renouveler le cookie CSRF
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=csrf_cookie,
            httponly=False,  # JS doit pouvoir le lire
            secure=settings.AZALPLUS_ENV == "production",
            samesite="lax",  # Protection CSRF supplementaire
            max_age=CSRF_TOKEN_TTL
        )

        return response

    def _is_exempt(self, path: str) -> bool:
        """Verifie si le chemin est exempte de CSRF."""
        for exempt_path in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt_path):
                return True
        return False

    async def _get_csrf_token(self, request: Request) -> Optional[str]:
        """
        Recupere le token CSRF depuis la requete.

        Cherche dans:
        1. Header X-CSRF-Token
        2. Champ de formulaire _csrf
        """
        # 1. Header
        token = request.headers.get(CSRF_HEADER_NAME)
        if token:
            return token

        # 2. Formulaire (pour les soumissions HTML)
        if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            try:
                form = await request.form()
                token = form.get(CSRF_FORM_FIELD)
                if token:
                    return str(token)
            except Exception:
                pass

        # 3. JSON body (pour certaines API)
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                # Ne pas consommer le body ici, juste verifier le header
                pass
            except Exception:
                pass

        return None

    def _verify_tokens(self, cookie_token: str, request_token: str) -> bool:
        """
        Verifie que les tokens correspondent.

        Args:
            cookie_token: Token du cookie
            request_token: Token de la requete

        Returns:
            True si les tokens sont valides et correspondent
        """
        # Verifier que le token du cookie est valide (signe)
        if not CSRFTokenManager.verify_signed_token(cookie_token, settings.SECRET_KEY):
            return False

        # Verifier que le token de la requete correspond
        # (comparaison securisee contre timing attacks)
        return hmac.compare_digest(cookie_token, request_token)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_csrf_token(request: Request) -> str:
    """
    Recupere le token CSRF courant pour l'injecter dans les templates.

    Args:
        request: Requete FastAPI

    Returns:
        Token CSRF a inclure dans les formulaires
    """
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = CSRFTokenManager.create_signed_token(settings.SECRET_KEY)
    return token


def csrf_input_field(request: Request) -> str:
    """
    Genere un champ input HTML pour le token CSRF.

    Args:
        request: Requete FastAPI

    Returns:
        HTML du champ input cache
    """
    token = get_csrf_token(request)
    return f'<input type="hidden" name="{CSRF_FORM_FIELD}" value="{token}">'


def csrf_meta_tag(request: Request) -> str:
    """
    Genere une balise meta pour le token CSRF (pour JS).

    Args:
        request: Requete FastAPI

    Returns:
        HTML de la balise meta
    """
    token = get_csrf_token(request)
    return f'<meta name="csrf-token" content="{token}">'
