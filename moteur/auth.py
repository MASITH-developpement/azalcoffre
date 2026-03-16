# =============================================================================
# AZALPLUS - Authentication
# =============================================================================
"""
Authentification JWT avec gestion des sessions.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID, uuid4
from jose import jwt, JWTError
from passlib.context import CryptContext
from argon2 import PasswordHasher
import structlog
import json

from .config import settings
from .db import Database
from .guardian import Guardian

logger = structlog.get_logger()

# =============================================================================
# Password Hashing (Argon2)
# =============================================================================
pwd_hasher = PasswordHasher()

def hash_password(password: str) -> str:
    """Hash un mot de passe avec Argon2."""
    return pwd_hasher.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """Vérifie un mot de passe."""
    try:
        pwd_hasher.verify(hashed, password)
        return True
    except:
        return False

# =============================================================================
# JWT
# =============================================================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crée un JWT access token avec JTI pour revocation."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES))
    # Ajouter JTI pour support revocation
    jti = str(uuid4())
    iat = datetime.utcnow()
    to_encode.update({
        "exp": expire,
        "type": "access",
        "jti": jti,
        "iat": int(iat.timestamp())
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """Crée un JWT refresh token avec JTI pour revocation."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    # Ajouter JTI pour support revocation
    jti = str(uuid4())
    iat = datetime.utcnow()
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": jti,
        "iat": int(iat.timestamp())
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    """Décode un JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def create_pending_2fa_token(data: dict) -> str:
    """Cree un token temporaire en attente de verification 2FA."""
    to_encode = data.copy()
    # Token valide 5 minutes seulement
    expire = datetime.utcnow() + timedelta(minutes=5)
    to_encode.update({"exp": expire, "type": "pending_2fa"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

# =============================================================================
# Security Scheme
# =============================================================================
security = HTTPBearer(auto_error=False)

# =============================================================================
# Auth Middleware (pour populer request.state.user AVANT TenantMiddleware)
# =============================================================================
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware qui décode le JWT et popule request.state.user."""

    async def dispatch(self, request: Request, call_next):
        """Décode le token JWT et ajoute l'utilisateur à request.state."""
        from .token_blacklist import TokenBlacklist

        # Laisser passer les requêtes OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Essayer de récupérer le token
        token = None

        # 1. Header Authorization
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # 2. Cookie access_token
        if not token:
            token = request.cookies.get("access_token")

        # 3. Query param token (pour iframe mobile)
        if not token:
            token = request.query_params.get("token")

        logger.debug("auth_middleware", path=request.url.path, has_token=bool(token))

        if token:
            payload = decode_token(token)
            logger.debug("auth_middleware_payload", payload_type=payload.get("type") if payload else None)

            if payload and payload.get("type") == "access":
                # Vérifier l'expiration
                exp = payload.get("exp")
                if exp and datetime.utcfromtimestamp(exp) >= datetime.utcnow():
                    # Vérifier si le token est révoqué (blacklist)
                    jti = payload.get("jti")
                    tenant_id = payload.get("tenant_id")
                    user_id = payload.get("sub")
                    iat = payload.get("iat")
                    issued_at = datetime.utcfromtimestamp(iat) if iat else None

                    if jti and tenant_id:
                        is_revoked = await TokenBlacklist.is_revoked(
                            jti=jti,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            issued_at=issued_at
                        )
                        if is_revoked:
                            logger.warning("auth_token_revoked", jti=jti[:8] + "...")
                            # Ne pas peupler request.state.user
                            return await call_next(request)

                    # Récupérer l'utilisateur en base
                    if user_id:
                        try:
                            with Database.get_session() as session:
                                from sqlalchemy import text
                                result = session.execute(
                                    text("SELECT * FROM azalplus.utilisateurs WHERE id = :id AND actif = true"),
                                    {"id": user_id}
                                )
                                user = result.fetchone()

                                if user:
                                    user_dict = dict(user._mapping)
                                    # Ajouter tenant_id depuis le token si pas en base
                                    if not user_dict.get("tenant_id") and payload.get("tenant_id"):
                                        user_dict["tenant_id"] = payload.get("tenant_id")
                                    # Stocker JTI pour revocation ultérieure
                                    user_dict["_jti"] = jti
                                    request.state.user = user_dict
                                    logger.debug("auth_middleware_user_set",
                                        email=user_dict.get("email"),
                                        tenant_id=str(user_dict.get("tenant_id")) if user_dict.get("tenant_id") else None
                                    )
                        except Exception as e:
                            logger.error("auth_middleware_error", error=str(e))

        return await call_next(request)

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """Récupère l'utilisateur courant depuis le token JWT."""

    # Essayer le header Authorization d'abord
    token = None
    if credentials:
        token = credentials.credentials

    # Sinon essayer le cookie
    if not token:
        token = request.cookies.get("access_token")

    # Sinon essayer le query param (pour iframe mobile)
    if not token:
        token = request.query_params.get("token")
        if token:
            logger.debug("auth_token_from_query_param", token_len=len(token))

    if not token:
        logger.debug("auth_no_token_found", path=request.url.path)
        return None

    payload = decode_token(token)
    logger.debug("auth_decode_result", has_payload=bool(payload))

    if not payload:
        return None

    # Vérifier le type
    if payload.get("type") != "access":
        return None

    # Vérifier l'expiration
    exp = payload.get("exp")
    if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
        return None

    # Récupérer l'utilisateur en base
    user_id = payload.get("sub")
    if not user_id:
        return None

    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("SELECT * FROM azalplus.utilisateurs WHERE id = :id AND actif = true"),
            {"id": user_id}
        )
        user = result.fetchone()

        if not user:
            return None

        user_dict = dict(user._mapping)
        # Stocker dans request.state pour le middleware tenant
        request.state.user = user_dict
        return user_dict

async def require_auth(
    user: Optional[dict] = Depends(get_current_user)
) -> dict:
    """Exige une authentification."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié"
        )
    return user

# =============================================================================
# Schemas
# =============================================================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nom: str
    prenom: Optional[str] = None
    tenant_code: str  # Code du tenant à rejoindre

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class RefreshRequest(BaseModel):
    refresh_token: str


# =============================================================================
# 2FA Schemas
# =============================================================================
class LoginWith2FARequest(BaseModel):
    """Request de connexion avec code 2FA."""
    email: EmailStr
    password: str
    totp_code: Optional[str] = None  # Code TOTP ou code de secours


class TwoFactorPendingResponse(BaseModel):
    """Reponse quand la 2FA est requise."""
    requires_2fa: bool = True
    pending_token: str  # Token temporaire pour completer la 2FA
    message: str = "Code d'authentification requis"


class Complete2FARequest(BaseModel):
    """Request pour completer la connexion avec 2FA."""
    pending_token: str
    code: str  # Code TOTP ou code de secours


class Setup2FAResponse(BaseModel):
    """Reponse de configuration 2FA."""
    secret: str
    qr_code: str  # QR code en base64


class Verify2FASetupRequest(BaseModel):
    """Verification du code pour activer 2FA."""
    code: str


class Verify2FASetupResponse(BaseModel):
    """Reponse apres activation 2FA."""
    enabled: bool
    backup_codes: List[str]


class Disable2FARequest(BaseModel):
    """Desactivation 2FA."""
    code: str  # Code TOTP ou code de secours


class Regenerate2FABackupCodesRequest(BaseModel):
    """Regeneration des codes de secours."""
    code: str  # Code TOTP actuel


class TwoFactorStatusResponse(BaseModel):
    """Statut 2FA."""
    enabled: bool
    backup_codes_remaining: int


# =============================================================================
# Auth Manager
# =============================================================================
class AuthManager:
    """Gestionnaire d'authentification."""

    @classmethod
    async def login(cls, email: str, password: str, request: Request) -> Optional[dict]:
        """Authentifie un utilisateur."""

        with Database.get_session() as session:
            from sqlalchemy import text

            result = session.execute(
                text("""
                    SELECT u.*, t.code as tenant_code, t.nom as tenant_nom
                    FROM azalplus.utilisateurs u
                    JOIN azalplus.tenants t ON u.tenant_id = t.id
                    WHERE u.email = :email AND u.actif = true AND t.actif = true
                """),
                {"email": email}
            )
            user = result.fetchone()

            if not user:
                return None

            user_dict = dict(user._mapping)

            # Vérifier le mot de passe
            if not verify_password(password, user_dict["password_hash"]):
                # Incrémenter les tentatives échouées
                session.execute(
                    text("""
                        UPDATE azalplus.utilisateurs
                        SET tentatives_echouees = tentatives_echouees + 1
                        WHERE id = :id
                    """),
                    {"id": str(user_dict["id"])}
                )
                session.commit()
                return None

            # Réinitialiser les tentatives et mettre à jour dernière connexion
            session.execute(
                text("""
                    UPDATE azalplus.utilisateurs
                    SET tentatives_echouees = 0, derniere_connexion = NOW()
                    WHERE id = :id
                """),
                {"id": str(user_dict["id"])}
            )
            session.commit()

            return user_dict

    @classmethod
    async def register(
        cls,
        email: str,
        password: str,
        nom: str,
        prenom: Optional[str],
        tenant_code: str
    ) -> Optional[dict]:
        """Inscrit un nouvel utilisateur."""

        with Database.get_session() as session:
            from sqlalchemy import text

            # Vérifier que le tenant existe
            tenant = session.execute(
                text("SELECT * FROM azalplus.tenants WHERE code = :code AND actif = true"),
                {"code": tenant_code}
            ).fetchone()

            if not tenant:
                return None

            tenant_dict = dict(tenant._mapping)

            # Vérifier que l'email n'existe pas déjà
            existing = session.execute(
                text("""
                    SELECT id FROM azalplus.utilisateurs
                    WHERE email = :email AND tenant_id = :tenant_id
                """),
                {"email": email, "tenant_id": str(tenant_dict["id"])}
            ).fetchone()

            if existing:
                return None

            # Créer l'utilisateur
            user_id = uuid4()
            session.execute(
                text("""
                    INSERT INTO azalplus.utilisateurs
                    (id, tenant_id, email, password_hash, nom, prenom, role, actif)
                    VALUES (:id, :tenant_id, :email, :password_hash, :nom, :prenom, :role, true)
                """),
                {
                    "id": str(user_id),
                    "tenant_id": str(tenant_dict["id"]),
                    "email": email,
                    "password_hash": hash_password(password),
                    "nom": nom,
                    "prenom": prenom,
                    "role": "utilisateur"
                }
            )
            session.commit()

            return {
                "id": str(user_id),
                "email": email,
                "nom": nom,
                "prenom": prenom,
                "tenant_id": str(tenant_dict["id"])
            }

# =============================================================================
# Router
# =============================================================================
router = APIRouter()

@router.post("/login")
async def login(data: LoginWith2FARequest, request: Request):
    """
    Connexion utilisateur avec support 2FA.

    Flux:
    1. Si 2FA desactive: retourne directement les tokens
    2. Si 2FA active et code fourni: verifie le code et retourne les tokens
    3. Si 2FA active sans code: retourne un pending_token pour completer la 2FA
    """
    from fastapi.responses import JSONResponse
    from .totp import TwoFactorManager

    user = await AuthManager.login(data.email, data.password, request)

    if not user:
        # Message generique (securite)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects"
        )

    # Verifier si 2FA est active
    totp_enabled = user.get("totp_enabled", False)

    if totp_enabled:
        # 2FA active - verifier le code si fourni
        if data.totp_code:
            # Verifier le code TOTP ou code de secours
            is_valid, is_backup = TwoFactorManager.verify_2fa(
                tenant_id=user["tenant_id"],
                user_id=user["id"],
                code=data.totp_code
            )

            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Code d'authentification invalide"
                )

            # Log si code de secours utilise
            if is_backup:
                logger.info("backup_code_login", email=user["email"])
        else:
            # Pas de code fourni - retourner un token temporaire
            pending_token = create_pending_2fa_token({
                "sub": str(user["id"]),
                "email": user["email"],
                "tenant_id": str(user["tenant_id"]),
                "role": user["role"]
            })

            return JSONResponse(content={
                "requires_2fa": True,
                "pending_token": pending_token,
                "message": "Code d'authentification requis"
            })

    # Creer les tokens
    token_data = {
        "sub": str(user["id"]),
        "email": user["email"],
        "tenant_id": str(user["tenant_id"]),
        "role": user["role"]
    }

    access_token = create_access_token(token_data)
    refresh_token_value = create_refresh_token(token_data)

    # Reponse avec cookie
    response = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token_value,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60
    })

    # Set cookie pour les pages HTML
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.AZALPLUS_ENV == "production",
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60
    )

    return response


@router.post("/login/2fa")
async def complete_2fa_login(data: Complete2FARequest, request: Request):
    """
    Complete la connexion avec le code 2FA.

    Utilise le pending_token obtenu lors du login initial.
    """
    from fastapi.responses import JSONResponse
    from .totp import TwoFactorManager

    # Decoder le pending token
    payload = decode_token(data.pending_token)

    if not payload or payload.get("type") != "pending_2fa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée. Veuillez vous reconnecter."
        )

    # Verifier l'expiration
    exp = payload.get("exp")
    if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée. Veuillez vous reconnecter."
        )

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")

    # Verifier le code 2FA
    is_valid, is_backup = TwoFactorManager.verify_2fa(
        tenant_id=tenant_id,
        user_id=user_id,
        code=data.code
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code d'authentification invalide"
        )

    # Log si code de secours utilise
    if is_backup:
        logger.info("backup_code_login", user_id=user_id)

    # Creer les tokens finaux
    token_data = {
        "sub": user_id,
        "email": payload.get("email"),
        "tenant_id": tenant_id,
        "role": payload.get("role", "user")
    }

    access_token = create_access_token(token_data)
    refresh_token_value = create_refresh_token(token_data)

    # Reponse avec cookie
    response = JSONResponse(content={
        "access_token": access_token,
        "refresh_token": refresh_token_value,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60
    })

    # Set cookie pour les pages HTML
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.AZALPLUS_ENV == "production",
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60
    )

    return response

@router.post("/register")
async def register(data: RegisterRequest):
    """Inscription utilisateur."""

    user = await AuthManager.register(
        email=data.email,
        password=data.password,
        nom=data.nom,
        prenom=data.prenom,
        tenant_code=data.tenant_code
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inscription impossible"
        )

    return {"status": "success", "message": "Compte créé"}

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest):
    """Rafraîchit un access token."""

    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide"
        )

    # Créer un nouveau access token
    token_data = {
        "sub": payload["sub"],
        "email": payload["email"],
        "tenant_id": payload["tenant_id"],
        "role": payload.get("role", "utilisateur")
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60
    )

@router.get("/me")
async def get_me(user: dict = Depends(require_auth)):
    """Retourne l'utilisateur courant."""
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "nom": user["nom"],
        "prenom": user.get("prenom"),
        "role": user["role"],
        "tenant_id": str(user["tenant_id"])
    }


@router.get("/utilisateurs")
async def list_utilisateurs(
    request: Request,
    user: dict = Depends(require_auth)
):
    """Liste les utilisateurs du tenant courant (pour les selects)."""
    tenant_id = user.get("tenant_id")

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text("""
                SELECT id, email, nom, prenom, role, actif
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
                "nom": f"{r.get('prenom', '')} {r.get('nom', '')}".strip(),
                "email": r["email"],
                "role": r["role"]
            })

    return {"items": users, "total": len(users)}


@router.post("/logout")
async def logout(request: Request, user: dict = Depends(require_auth)):
    """Déconnexion avec revocation du token."""
    from .token_blacklist import TokenBlacklist

    # Récupérer le JTI depuis le user dict (ajouté par AuthMiddleware)
    jti = user.get("_jti")
    tenant_id = user.get("tenant_id")

    if jti and tenant_id:
        # Révoquer le token
        await TokenBlacklist.revoke_token(
            jti=jti,
            tenant_id=tenant_id,
            reason="logout"
        )
        logger.info("user_logout", email=user.get("email"))

    # Supprimer le cookie
    from fastapi.responses import JSONResponse
    response = JSONResponse(content={"status": "success"})
    response.delete_cookie("access_token")

    return response


@router.post("/mobile-token")
async def create_mobile_token(request: Request, user: dict = Depends(require_auth)):
    """
    Génère un token temporaire pour la connexion mobile via QR code.
    Le token est valide 5 minutes.
    """
    import secrets
    from datetime import datetime, timedelta

    tenant_id = user.get("tenant_id")
    user_id = user.get("id")

    # Générer un token unique
    mobile_token = secrets.token_urlsafe(32)

    # Stocker dans Redis avec expiration 5 minutes
    from .db import Database
    redis = Database.get_redis()
    if redis:
        token_data = {
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "email": user.get("email", ""),
            "nom": user.get("nom", ""),
            "created_at": datetime.utcnow().isoformat()
        }
        import json
        redis.setex(
            f"mobile_token:{mobile_token}",
            300,  # 5 minutes
            json.dumps(token_data)
        )

    logger.info("mobile_token_created", email=user.get("email"))

    return {
        "token": mobile_token,
        "expires_in": 300,
        "url": f"/mobile/connect?token={mobile_token}"
    }


@router.post("/mobile-verify")
async def verify_mobile_token(request: Request):
    """
    Vérifie un token mobile et retourne les credentials de connexion.
    Utilisé par l'application mobile après scan du QR code.
    """
    from pydantic import BaseModel

    class MobileVerifyRequest(BaseModel):
        token: str

    data = await request.json()
    mobile_token = data.get("token")

    if not mobile_token:
        raise HTTPException(status_code=400, detail="Token requis")

    # Récupérer depuis Redis
    from .db import Database
    redis = Database.get_redis()
    if not redis:
        raise HTTPException(status_code=500, detail="Service indisponible")

    import json
    token_data = redis.get(f"mobile_token:{mobile_token}")

    if not token_data:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

    token_info = json.loads(token_data)

    # Supprimer le token (usage unique)
    redis.delete(f"mobile_token:{mobile_token}")

    # Générer un vrai JWT pour le mobile
    from uuid import UUID
    access_token = create_access_token({
        "sub": token_info["user_id"],
        "tenant_id": token_info["tenant_id"],
        "email": token_info["email"],
        "nom": token_info.get("nom", ""),
        "mobile": True
    })

    logger.info("mobile_login_success", email=token_info["email"])

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": token_info["user_id"],
            "email": token_info["email"],
            "nom": token_info.get("nom", "")
        }
    }


# =============================================================================
# Role-Based Access Control (RBAC)
# =============================================================================
ROLES = {
    "admin": {
        "level": 100,
        "description": "Accès complet - gestion système et paramètres"
    },
    "manager": {
        "level": 50,
        "description": "Gestion des modules métier sans paramètres système"
    },
    "user": {
        "level": 10,
        "description": "Accès basique - consultation et saisie"
    }
}

def require_role(min_role: str):
    """Dépendance pour vérifier le rôle minimum."""
    min_level = ROLES.get(min_role, {}).get("level", 0)

    async def role_checker(user: dict = Depends(require_auth)):
        user_role = user.get("role", "user")
        user_level = ROLES.get(user_role, {}).get("level", 0)

        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle {min_role} requis"
            )
        return user

    return role_checker


# =============================================================================
# User Management Schemas
# =============================================================================
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nom: str
    prenom: Optional[str] = None
    role: str = "user"

class UserUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    role: Optional[str] = None
    actif: Optional[bool] = None
    modules_mobile: Optional[List[str]] = None  # Custom mobile modules for this user
    reset_modules_mobile: Optional[bool] = None  # Set to true to reset to role-based defaults

class UserPasswordReset(BaseModel):
    new_password: str


# =============================================================================
# User Management Router (Créateur cross-tenant OU Admin/tenant)
# =============================================================================
from .tenant import TenantContext, CREATEUR_EMAIL

users_router = APIRouter()

def get_user_management_context(user: dict) -> tuple:
    """Retourne (is_createur, tenant_id_filter)."""
    user_email = user.get("email", "")
    is_createur = user_email == CREATEUR_EMAIL
    tenant_id = None if is_createur else user.get("tenant_id")
    return is_createur, tenant_id

@users_router.get("/")
async def list_users(
    request: Request,
    tenant_filter: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """Liste les utilisateurs (créateur: tous, admin: son tenant)."""
    is_createur, user_tenant_id = get_user_management_context(user)

    # Admin doit avoir le role admin
    if not is_createur and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    with Database.get_session() as session:
        from sqlalchemy import text

        # Créateur peut filtrer par tenant ou voir tous
        # Admin voit uniquement son tenant
        if is_createur and tenant_filter:
            filter_tenant = tenant_filter
        elif is_createur:
            filter_tenant = None  # Tous les tenants
        else:
            filter_tenant = str(user_tenant_id)  # Son tenant uniquement

        if filter_tenant:
            result = session.execute(
                text("""
                    SELECT u.id, u.email, u.nom, u.prenom, u.role, u.actif,
                           u.derniere_connexion, u.tentatives_echouees, u.created_at,
                           u.modules_mobile, u.tenant_id, t.nom as tenant_nom
                    FROM azalplus.utilisateurs u
                    LEFT JOIN azalplus.tenants t ON u.tenant_id = t.id
                    WHERE u.tenant_id = :tenant_id
                    ORDER BY u.created_at DESC
                """),
                {"tenant_id": filter_tenant}
            )
        else:
            result = session.execute(
                text("""
                    SELECT u.id, u.email, u.nom, u.prenom, u.role, u.actif,
                           u.derniere_connexion, u.tentatives_echouees, u.created_at,
                           u.modules_mobile, u.tenant_id, t.nom as tenant_nom
                    FROM azalplus.utilisateurs u
                    LEFT JOIN azalplus.tenants t ON u.tenant_id = t.id
                    ORDER BY t.nom, u.created_at DESC
                """)
            )

        users = [dict(row._mapping) for row in result]

    return {"users": users}


# ============================================================================
# Routes /me/* (AVANT les routes /{user_id} pour éviter les conflits)
# ============================================================================
class UpdateUserModules(BaseModel):
    """Schema pour mise à jour des modules actifs."""
    modules: List[str] = Field(..., description="Liste des modules activés")


@users_router.put("/me/modules")
async def update_my_modules(
    data: UpdateUserModules,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Met à jour les modules actifs pour l'utilisateur courant."""
    user_id = user.get("id")
    tenant_id = user.get("tenant_id")

    if not user_id or not tenant_id:
        raise HTTPException(status_code=400, detail="Utilisateur invalide")

    with Database.get_session() as session:
        from sqlalchemy import text

        session.execute(
            text("""
                UPDATE azalplus.utilisateurs
                SET modules_mobile = :modules_mobile, updated_at = NOW()
                WHERE id = :user_id AND tenant_id = :tenant_id
            """),
            {
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "modules_mobile": json.dumps(data.modules)
            }
        )
        session.commit()

    return {"status": "success", "modules": data.modules}


# ============================================================================
# Routes /{user_id}
# ============================================================================
@users_router.get("/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Récupère un utilisateur (créateur: tous, admin: son tenant)."""
    is_createur, user_tenant_id = get_user_management_context(user)

    if not is_createur and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    with Database.get_session() as session:
        from sqlalchemy import text

        if is_createur:
            # Créateur peut voir n'importe quel utilisateur
            result = session.execute(
                text("""
                    SELECT u.id, u.email, u.nom, u.prenom, u.role, u.actif,
                           u.derniere_connexion, u.tentatives_echouees, u.created_at,
                           u.modules_mobile, u.tenant_id, t.nom as tenant_nom
                    FROM azalplus.utilisateurs u
                    LEFT JOIN azalplus.tenants t ON u.tenant_id = t.id
                    WHERE u.id = :user_id
                """),
                {"user_id": user_id}
            )
        else:
            # Admin voit uniquement les utilisateurs de son tenant
            result = session.execute(
                text("""
                    SELECT u.id, u.email, u.nom, u.prenom, u.role, u.actif,
                           u.derniere_connexion, u.tentatives_echouees, u.created_at,
                           u.modules_mobile, u.tenant_id, t.nom as tenant_nom
                    FROM azalplus.utilisateurs u
                    LEFT JOIN azalplus.tenants t ON u.tenant_id = t.id
                    WHERE u.id = :user_id AND u.tenant_id = :tenant_id
                """),
                {"user_id": user_id, "tenant_id": str(user_tenant_id)}
            )

        user_data = result.fetchone()

    if not user_data:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    return dict(user_data._mapping)


class UserCreateWithTenant(UserCreate):
    """Schema création utilisateur avec tenant (pour créateur)."""
    tenant_id: Optional[str] = None  # Requis si créateur

@users_router.post("/", status_code=201)
async def create_user(
    data: UserCreateWithTenant,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Crée un utilisateur (créateur: tout tenant, admin: son tenant)."""
    is_createur, user_tenant_id = get_user_management_context(user)

    if not is_createur and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    # Déterminer le tenant cible
    if is_createur:
        if not data.tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id requis pour le créateur")
        target_tenant_id = data.tenant_id
    else:
        target_tenant_id = str(user_tenant_id)

    # Valider le rôle
    if data.role not in ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Rôle invalide. Rôles valides: {list(ROLES.keys())}"
        )

    with Database.get_session() as session:
        from sqlalchemy import text

        # Vérifier que l'email n'existe pas déjà dans ce tenant
        existing = session.execute(
            text("""
                SELECT id FROM azalplus.utilisateurs
                WHERE email = :email AND tenant_id = :tenant_id
            """),
            {"email": data.email, "tenant_id": target_tenant_id}
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Un utilisateur avec cet email existe déjà"
            )

        # Créer l'utilisateur
        new_user_id = uuid4()
        session.execute(
            text("""
                INSERT INTO azalplus.utilisateurs
                (id, tenant_id, email, password_hash, nom, prenom, role, actif)
                VALUES (:id, :tenant_id, :email, :password_hash, :nom, :prenom, :role, true)
            """),
            {
                "id": str(new_user_id),
                "tenant_id": target_tenant_id,
                "email": data.email,
                "password_hash": hash_password(data.password),
                "nom": data.nom,
                "prenom": data.prenom,
                "role": data.role
            }
        )
        session.commit()

    return {
        "id": str(new_user_id),
        "tenant_id": target_tenant_id,
        "email": data.email,
        "nom": data.nom,
        "prenom": data.prenom,
        "role": data.role,
        "actif": True
    }


@users_router.put("/{user_id}")
async def update_user(
    user_id: str,
    data: UserUpdate,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Met à jour un utilisateur (créateur: tous, admin: son tenant)."""
    is_createur, user_tenant_id = get_user_management_context(user)

    if not is_createur and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    # Valider le rôle si fourni
    if data.role and data.role not in ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Rôle invalide. Rôles valides: {list(ROLES.keys())}"
        )

    # Empêcher de se désactiver soi-même
    if str(user.get("id")) == user_id and data.actif is False:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas désactiver votre propre compte"
        )

    with Database.get_session() as session:
        from sqlalchemy import text

        # Vérifier que l'utilisateur existe (avec filtre tenant si admin)
        if is_createur:
            existing = session.execute(
                text("SELECT id, tenant_id FROM azalplus.utilisateurs WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
        else:
            existing = session.execute(
                text("SELECT id, tenant_id FROM azalplus.utilisateurs WHERE id = :user_id AND tenant_id = :tenant_id"),
                {"user_id": user_id, "tenant_id": str(user_tenant_id)}
            ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        # Construire la requête de mise à jour
        updates = []
        params = {"user_id": user_id}

        if data.nom is not None:
            updates.append("nom = :nom")
            params["nom"] = data.nom
        if data.prenom is not None:
            updates.append("prenom = :prenom")
            params["prenom"] = data.prenom
        if data.role is not None:
            updates.append("role = :role")
            params["role"] = data.role
        if data.actif is not None:
            updates.append("actif = :actif")
            params["actif"] = data.actif
        if data.reset_modules_mobile:
            # Reset to NULL (role-based defaults)
            updates.append("modules_mobile = NULL")
        elif data.modules_mobile is not None:
            import json
            updates.append("modules_mobile = :modules_mobile")
            params["modules_mobile"] = json.dumps(data.modules_mobile)

        if updates:
            query = f"""
                UPDATE azalplus.utilisateurs
                SET {", ".join(updates)}, updated_at = NOW()
                WHERE id = :user_id
                RETURNING id, email, nom, prenom, role, actif, modules_mobile, tenant_id
            """
            result = session.execute(text(query), params)
            session.commit()
            updated_user = result.fetchone()

            return dict(updated_user._mapping)

    raise HTTPException(status_code=400, detail="Aucune modification fournie")


@users_router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    data: UserPasswordReset,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Réinitialise le mot de passe (créateur: tous, admin: son tenant)."""
    is_createur, user_tenant_id = get_user_management_context(user)

    if not is_createur and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Le mot de passe doit contenir au moins 8 caractères"
        )

    with Database.get_session() as session:
        from sqlalchemy import text

        # Vérifier que l'utilisateur existe
        if is_createur:
            existing = session.execute(
                text("SELECT id FROM azalplus.utilisateurs WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
        else:
            existing = session.execute(
                text("SELECT id FROM azalplus.utilisateurs WHERE id = :user_id AND tenant_id = :tenant_id"),
                {"user_id": user_id, "tenant_id": str(user_tenant_id)}
            ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        # Mettre à jour le mot de passe
        session.execute(
            text("""
                UPDATE azalplus.utilisateurs
                SET password_hash = :password_hash,
                    tentatives_echouees = 0,
                    updated_at = NOW()
                WHERE id = :user_id
            """),
            {
                "user_id": user_id,
                "password_hash": hash_password(data.new_password)
            }
        )
        session.commit()

    return {"status": "success", "message": "Mot de passe réinitialisé"}


@users_router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Supprime un utilisateur (créateur: tous, admin: son tenant)."""
    is_createur, user_tenant_id = get_user_management_context(user)

    if not is_createur and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    # Empêcher de se supprimer soi-même
    if str(user.get("id")) == user_id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas supprimer votre propre compte"
        )

    with Database.get_session() as session:
        from sqlalchemy import text

        # Vérifier que l'utilisateur existe
        if is_createur:
            existing = session.execute(
                text("SELECT id FROM azalplus.utilisateurs WHERE id = :user_id"),
                {"user_id": user_id}
            ).fetchone()
        else:
            existing = session.execute(
                text("SELECT id FROM azalplus.utilisateurs WHERE id = :user_id AND tenant_id = :tenant_id"),
                {"user_id": user_id, "tenant_id": str(user_tenant_id)}
            ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        # Soft delete (désactivation)
        session.execute(
            text("""
                UPDATE azalplus.utilisateurs
                SET actif = false, updated_at = NOW()
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        )
        session.commit()

    return {"status": "deleted"}
