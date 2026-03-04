# =============================================================================
# AZALPLUS - Token Blacklist (JWT Revocation)
# =============================================================================
"""
Systeme de revocation de tokens JWT via Redis.

Fonctionnalites:
- Revocation de tokens individuels (logout)
- Revocation de tous les tokens d'un utilisateur (changement mdp)
- Revocation de tous les tokens d'un tenant (urgence securite)
- TTL automatique base sur l'expiration du token
- Verification performante O(1) via Redis

Utilisation:
    # Revoquer un token (logout)
    await TokenBlacklist.revoke_token(jti, tenant_id)

    # Verifier si revoque
    is_revoked = await TokenBlacklist.is_revoked(jti, tenant_id)

    # Revoquer tous les tokens d'un utilisateur
    await TokenBlacklist.revoke_user_tokens(user_id, tenant_id)
"""

from datetime import datetime, timedelta
from typing import Optional, Union
from uuid import UUID
import structlog

from .db import Database
from .config import settings

logger = structlog.get_logger()

# =============================================================================
# CONFIGURATION
# =============================================================================
# Prefixes Redis pour les differents types de revocation
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
USER_REVOKE_PREFIX = "token:user_revoke:"
TENANT_REVOKE_PREFIX = "token:tenant_revoke:"

# TTL par defaut si non specifie (24h)
DEFAULT_TTL = 24 * 60 * 60


# =============================================================================
# TOKEN BLACKLIST
# =============================================================================
class TokenBlacklist:
    """
    Gestionnaire de revocation de tokens JWT.

    Utilise Redis pour une verification performante.
    """

    @classmethod
    async def revoke_token(
        cls,
        jti: str,
        tenant_id: Union[str, UUID],
        ttl: Optional[int] = None,
        reason: str = "logout"
    ) -> bool:
        """
        Revoque un token specifique.

        Args:
            jti: JWT ID (identifiant unique du token)
            tenant_id: ID du tenant
            ttl: Duree de vie de l'entree (par defaut: expiration du token)
            reason: Raison de la revocation

        Returns:
            True si la revocation a reussi
        """
        try:
            redis = Database.get_redis()
            key = f"{TOKEN_BLACKLIST_PREFIX}{tenant_id}:{jti}"

            # Stocker avec TTL
            await redis.setex(
                key,
                ttl or DEFAULT_TTL,
                f"{reason}:{datetime.utcnow().isoformat()}"
            )

            logger.info(
                "token_revoked",
                jti=jti[:8] + "...",
                tenant_id=str(tenant_id),
                reason=reason
            )

            return True

        except Exception as e:
            logger.error(
                "token_revoke_failed",
                jti=jti[:8] + "...",
                error=str(e)
            )
            return False

    @classmethod
    async def is_revoked(
        cls,
        jti: str,
        tenant_id: Union[str, UUID],
        user_id: Optional[Union[str, UUID]] = None,
        issued_at: Optional[datetime] = None
    ) -> bool:
        """
        Verifie si un token est revoque.

        Verifie:
        1. Token individuel revoque
        2. Tous les tokens de l'utilisateur revoques
        3. Tous les tokens du tenant revoques

        Args:
            jti: JWT ID
            tenant_id: ID du tenant
            user_id: ID de l'utilisateur (optionnel, pour check user revoke)
            issued_at: Date d'emission du token (pour check revoke_all)

        Returns:
            True si le token est revoque
        """
        try:
            redis = Database.get_redis()

            # 1. Token individuel
            token_key = f"{TOKEN_BLACKLIST_PREFIX}{tenant_id}:{jti}"
            if await redis.exists(token_key):
                logger.debug("token_blacklisted", jti=jti[:8] + "...")
                return True

            # 2. Revocation utilisateur (tous les tokens avant une date)
            if user_id and issued_at:
                user_key = f"{USER_REVOKE_PREFIX}{tenant_id}:{user_id}"
                revoke_time = await redis.get(user_key)

                if revoke_time:
                    revoke_dt = datetime.fromisoformat(revoke_time.decode())
                    if issued_at < revoke_dt:
                        logger.debug(
                            "token_user_revoked",
                            user_id=str(user_id),
                            issued_at=issued_at.isoformat()
                        )
                        return True

            # 3. Revocation tenant (tous les tokens avant une date)
            if issued_at:
                tenant_key = f"{TENANT_REVOKE_PREFIX}{tenant_id}"
                revoke_time = await redis.get(tenant_key)

                if revoke_time:
                    revoke_dt = datetime.fromisoformat(revoke_time.decode())
                    if issued_at < revoke_dt:
                        logger.debug(
                            "token_tenant_revoked",
                            tenant_id=str(tenant_id),
                            issued_at=issued_at.isoformat()
                        )
                        return True

            return False

        except Exception as e:
            logger.error("token_check_failed", error=str(e))
            # En cas d'erreur Redis, on laisse passer (fail open)
            # En production, on pourrait choisir fail close
            return False

    @classmethod
    async def revoke_user_tokens(
        cls,
        user_id: Union[str, UUID],
        tenant_id: Union[str, UUID],
        reason: str = "password_change"
    ) -> bool:
        """
        Revoque tous les tokens d'un utilisateur.

        Utile pour:
        - Changement de mot de passe
        - Deconnexion de tous les appareils
        - Compromission de compte

        Args:
            user_id: ID de l'utilisateur
            tenant_id: ID du tenant
            reason: Raison de la revocation

        Returns:
            True si la revocation a reussi
        """
        try:
            redis = Database.get_redis()
            key = f"{USER_REVOKE_PREFIX}{tenant_id}:{user_id}"

            # Stocker la date de revocation
            # Tous les tokens emis AVANT cette date seront invalides
            await redis.setex(
                key,
                DEFAULT_TTL * 7,  # Garder 7 jours
                datetime.utcnow().isoformat()
            )

            logger.info(
                "user_tokens_revoked",
                user_id=str(user_id),
                tenant_id=str(tenant_id),
                reason=reason
            )

            return True

        except Exception as e:
            logger.error(
                "user_tokens_revoke_failed",
                user_id=str(user_id),
                error=str(e)
            )
            return False

    @classmethod
    async def revoke_tenant_tokens(
        cls,
        tenant_id: Union[str, UUID],
        reason: str = "security_incident"
    ) -> bool:
        """
        Revoque tous les tokens d'un tenant.

        Utile pour:
        - Incident de securite
        - Maintenance urgente
        - Changement de politique

        Args:
            tenant_id: ID du tenant
            reason: Raison de la revocation

        Returns:
            True si la revocation a reussi
        """
        try:
            redis = Database.get_redis()
            key = f"{TENANT_REVOKE_PREFIX}{tenant_id}"

            # Stocker la date de revocation
            await redis.setex(
                key,
                DEFAULT_TTL * 7,  # Garder 7 jours
                datetime.utcnow().isoformat()
            )

            logger.warning(
                "tenant_tokens_revoked",
                tenant_id=str(tenant_id),
                reason=reason
            )

            return True

        except Exception as e:
            logger.error(
                "tenant_tokens_revoke_failed",
                tenant_id=str(tenant_id),
                error=str(e)
            )
            return False

    @classmethod
    async def get_stats(cls, tenant_id: Union[str, UUID]) -> dict:
        """
        Retourne des statistiques sur les tokens revoques.

        Args:
            tenant_id: ID du tenant

        Returns:
            Dictionnaire de statistiques
        """
        try:
            redis = Database.get_redis()

            # Compter les tokens revoques pour ce tenant
            pattern = f"{TOKEN_BLACKLIST_PREFIX}{tenant_id}:*"
            keys = []

            async for key in redis.scan_iter(pattern):
                keys.append(key)

            # Verifier les revocations globales
            user_revoke_key = f"{USER_REVOKE_PREFIX}{tenant_id}:*"
            tenant_revoke_key = f"{TENANT_REVOKE_PREFIX}{tenant_id}"

            has_tenant_revoke = await redis.exists(tenant_revoke_key)

            return {
                "revoked_tokens_count": len(keys),
                "tenant_wide_revoke_active": bool(has_tenant_revoke),
                "tenant_id": str(tenant_id)
            }

        except Exception as e:
            logger.error("token_stats_failed", error=str(e))
            return {
                "error": str(e),
                "revoked_tokens_count": -1
            }

    @classmethod
    async def cleanup_expired(cls) -> int:
        """
        Nettoie les entrees expirees (normalement gere par TTL Redis).

        Returns:
            Nombre d'entrees nettoyees
        """
        # Redis gere automatiquement les TTL
        # Cette methode est pour le monitoring/debug
        logger.info("token_blacklist_cleanup_triggered")
        return 0


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def extract_jti_from_token(token_payload: dict) -> Optional[str]:
    """
    Extrait le JTI d'un payload de token.

    Args:
        token_payload: Payload decode du JWT

    Returns:
        JTI ou None
    """
    return token_payload.get("jti")


def extract_issued_at(token_payload: dict) -> Optional[datetime]:
    """
    Extrait la date d'emission d'un payload de token.

    Args:
        token_payload: Payload decode du JWT

    Returns:
        Datetime d'emission ou None
    """
    iat = token_payload.get("iat")
    if iat:
        return datetime.utcfromtimestamp(iat)
    return None
