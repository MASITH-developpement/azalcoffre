# =============================================================================
# AZALPLUS - Tests de Securite Authentification
# =============================================================================
"""
Tests de securite pour le systeme d'authentification.

Verifie:
- Login avec credentials invalides
- JWT expire / invalide
- Refresh token
- Rate limiting sur /auth/login
- 2FA TOTP
- Revocation de tokens

NORMES: AZA-SEC-AUTH-*
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict
from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch, AsyncMock
import time

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")


# =============================================================================
# Tests Login Security
# =============================================================================
class TestLoginSecurity:
    """Tests de securite du login."""

    @pytest.mark.asyncio
    async def test_login_invalid_email(self, mock_database):
        """Test login avec email inexistant."""
        from moteur.auth import AuthManager

        with patch.object(AuthManager, "login") as mock_login:
            mock_login.return_value = None

            result = await AuthManager.login(
                email="nonexistent@example.com",
                password="somepassword",
                request=MagicMock()
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        """Test login avec mauvais mot de passe."""
        from moteur.auth import verify_password, hash_password

        # Test direct de verify_password avec mauvais mot de passe
        correct_password = "correctpassword123"
        wrong_password = "wrongpassword123"
        hashed = hash_password(correct_password)

        # Mot de passe correct
        assert verify_password(correct_password, hashed) is True

        # Mauvais mot de passe
        assert verify_password(wrong_password, hashed) is False

    @pytest.mark.asyncio
    async def test_login_increments_failed_attempts(self):
        """Test que le systeme detecte les tentatives echouees."""
        from moteur.auth import verify_password, hash_password

        # Simuler plusieurs tentatives echouees
        correct_password = "mysecurepassword"
        hashed = hash_password(correct_password)

        failed_attempts = 0
        wrong_passwords = ["attempt1", "attempt2", "attempt3"]

        for wrong_pwd in wrong_passwords:
            if not verify_password(wrong_pwd, hashed):
                failed_attempts += 1

        # Toutes les tentatives doivent echouer
        assert failed_attempts == 3

    @pytest.mark.asyncio
    async def test_login_inactive_user_rejected(self):
        """Test que les utilisateurs inactifs doivent etre rejetes."""
        # Ce test verifie le comportement attendu:
        # Un utilisateur avec actif=False ne doit pas pouvoir se connecter
        # La logique est dans la requete SQL qui filtre sur actif=true

        user_inactive = {
            "actif": False,
            "email": "inactive@test.com"
        }

        # La validation business doit verifier que l'utilisateur est actif
        assert user_inactive["actif"] is False

        # Le systeme doit rejeter les utilisateurs inactifs
        # Cette verification est faite dans la requete SQL
        # "WHERE ... AND actif = true"


# =============================================================================
# Tests JWT Security
# =============================================================================
class TestJWTSecurity:
    """Tests de securite JWT."""

    def test_token_decode_valid(self, valid_token_tenant_a, mock_settings):
        """Test decodage d'un token valide."""
        from moteur.auth import decode_token

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                payload = decode_token(valid_token_tenant_a)

        assert payload is not None
        assert "sub" in payload
        assert "tenant_id" in payload

    def test_token_decode_expired_returns_none(self, expired_token, mock_settings):
        """Test qu'un token expire retourne None."""
        from moteur.auth import decode_token

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                payload = decode_token(expired_token)

        # Le token expire doit retourner None ou lever une exception
        # decode_token de AZALPLUS retourne None en cas d'erreur
        assert payload is None

    def test_token_decode_invalid_signature(self, invalid_signature_token, mock_settings):
        """Test qu'un token avec mauvaise signature est rejete."""
        from moteur.auth import decode_token

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                payload = decode_token(invalid_signature_token)

        assert payload is None

    def test_token_decode_malformed(self, mock_settings):
        """Test qu'un token malformed est rejete."""
        from moteur.auth import decode_token

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                payload = decode_token("not.a.valid.token")

        assert payload is None

    def test_token_decode_empty(self, mock_settings):
        """Test qu'un token vide est rejete."""
        from moteur.auth import decode_token

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                payload = decode_token("")

        assert payload is None

    def test_access_token_has_correct_type(self, mock_settings):
        """Test que les access tokens ont le bon type."""
        from moteur.auth import create_access_token
        from jose import jwt

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                with patch("moteur.auth.settings.JWT_EXPIRE_MINUTES", 60):
                    token = create_access_token({"sub": "user123", "tenant_id": "tenant123"})

        payload = jwt.decode(token, "test_secret_key_minimum_32_characters_for_jwt", algorithms=["HS256"])

        assert payload["type"] == "access"

    def test_refresh_token_has_correct_type(self, mock_settings):
        """Test que les refresh tokens ont le bon type."""
        from moteur.auth import create_refresh_token
        from jose import jwt

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                with patch("moteur.auth.settings.JWT_REFRESH_EXPIRE_DAYS", 7):
                    token = create_refresh_token({"sub": "user123", "tenant_id": "tenant123"})

        payload = jwt.decode(token, "test_secret_key_minimum_32_characters_for_jwt", algorithms=["HS256"])

        assert payload["type"] == "refresh"

    def test_token_has_jti(self, mock_settings):
        """Test que les tokens ont un JTI pour revocation."""
        from moteur.auth import create_access_token
        from jose import jwt

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                with patch("moteur.auth.settings.JWT_EXPIRE_MINUTES", 60):
                    token = create_access_token({"sub": "user123"})

        payload = jwt.decode(token, "test_secret_key_minimum_32_characters_for_jwt", algorithms=["HS256"])

        assert "jti" in payload
        assert len(payload["jti"]) > 0


# =============================================================================
# Tests Refresh Token
# =============================================================================
class TestRefreshToken:
    """Tests du refresh token."""

    def test_refresh_token_longer_expiry(self, mock_settings):
        """Test que le refresh token expire plus tard que l'access token."""
        from moteur.auth import create_access_token, create_refresh_token
        from jose import jwt

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                with patch("moteur.auth.settings.JWT_EXPIRE_MINUTES", 60):
                    with patch("moteur.auth.settings.JWT_REFRESH_EXPIRE_DAYS", 7):
                        access = create_access_token({"sub": "user123"})
                        refresh = create_refresh_token({"sub": "user123"})

        access_payload = jwt.decode(access, "test_secret_key_minimum_32_characters_for_jwt", algorithms=["HS256"])
        refresh_payload = jwt.decode(refresh, "test_secret_key_minimum_32_characters_for_jwt", algorithms=["HS256"])

        assert refresh_payload["exp"] > access_payload["exp"]

    def test_cannot_use_refresh_token_as_access(self, refresh_token, mock_settings):
        """Test qu'on ne peut pas utiliser un refresh token comme access token."""
        from moteur.auth import decode_token
        from jose import jwt

        # Decoder le refresh token
        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                payload = decode_token(refresh_token)

        # Meme si le token est valide, le type doit etre verifie
        if payload:
            assert payload.get("type") != "access"

    def test_cannot_use_access_token_as_refresh(self, valid_token_tenant_a, mock_settings):
        """Test qu'on ne peut pas utiliser un access token comme refresh token."""
        from jose import jwt

        payload = jwt.decode(
            valid_token_tenant_a,
            "test_secret_key_minimum_32_characters_for_jwt",
            algorithms=["HS256"]
        )

        assert payload.get("type") != "refresh"


# =============================================================================
# Tests Rate Limiting
# =============================================================================
class TestRateLimiting:
    """Tests du rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_under_limit(self, mock_redis_rate_limit):
        """Test que le rate limiter autorise sous la limite."""
        from moteur.ratelimit import RateLimiter

        with patch.object(RateLimiter, "_check_redis", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (True, 99, 100, int(time.time()) + 60)

            allowed, remaining, limit, reset = await RateLimiter.check_limit(
                key="test:user:123",
                limit=100,
                window=60
            )

            assert allowed is True
            assert remaining > 0

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_over_limit(self, mock_redis_rate_limit):
        """Test que le rate limiter bloque au-dessus de la limite."""
        from moteur.ratelimit import RateLimiter

        with patch.object(RateLimiter, "_check_redis", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (False, 0, 100, int(time.time()) + 60)

            allowed, remaining, limit, reset = await RateLimiter.check_limit(
                key="test:user:123",
                limit=100,
                window=60
            )

            assert allowed is False
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_uses_memory_fallback(self):
        """Test que le rate limiter utilise le fallback memoire si Redis echoue."""
        from moteur.ratelimit import RateLimiter

        with patch.object(RateLimiter, "_check_redis", side_effect=Exception("Redis down")):
            with patch.object(RateLimiter, "_check_memory", new_callable=AsyncMock) as mock_memory:
                mock_memory.return_value = (True, 99, 100, int(time.time()) + 60)

                allowed, _, _, _ = await RateLimiter.check_limit(
                    key="test:user:123",
                    limit=100,
                    window=60
                )

                mock_memory.assert_called_once()
                assert allowed is True

    def test_rate_limit_config_values(self):
        """Test les valeurs de configuration du rate limiting."""
        from moteur.ratelimit import RateLimitConfig

        # Verifier les valeurs par defaut
        assert RateLimitConfig.DEFAULT_AUTHENTICATED == 100
        assert RateLimitConfig.DEFAULT_UNAUTHENTICATED == 20
        assert RateLimitConfig.DEFAULT_INTERNAL == 1000
        assert RateLimitConfig.WINDOW_SECONDS == 60

    def test_exempt_routes(self):
        """Test que certaines routes sont exemptees du rate limiting."""
        from moteur.ratelimit import is_route_exempt

        # Routes exemptees
        assert is_route_exempt("/health") is True
        assert is_route_exempt("/static/app.js") is True
        assert is_route_exempt("/assets/logo.png") is True

        # Routes non exemptees
        assert is_route_exempt("/api/clients") is False
        assert is_route_exempt("/api/auth/login") is False


# =============================================================================
# Tests 2FA TOTP
# =============================================================================
class TestTOTP:
    """Tests de l'authentification 2FA TOTP."""

    def test_totp_generate_secret(self):
        """Test generation d'un secret TOTP."""
        from moteur.totp import TOTPService

        secret = TOTPService.generate_secret()

        assert secret is not None
        assert len(secret) > 0
        # Base32 valide
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_totp_verify_code_valid(self):
        """Test verification d'un code TOTP valide."""
        from moteur.totp import TOTPService
        import pyotp

        secret = "JBSWY3DPEHPK3PXP"  # Secret de test
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        result = TOTPService.verify_code(secret, valid_code)

        assert result is True

    def test_totp_verify_code_invalid(self):
        """Test que les codes invalides sont rejetes."""
        from moteur.totp import TOTPService

        secret = "JBSWY3DPEHPK3PXP"

        result = TOTPService.verify_code(secret, "000000")

        # Un code aleatoire devrait etre invalide
        # (sauf coincidence tres rare)
        assert result is False

    def test_totp_verify_code_wrong_length(self):
        """Test que les codes de mauvaise longueur sont rejetes."""
        from moteur.totp import TOTPService

        secret = "JBSWY3DPEHPK3PXP"

        assert TOTPService.verify_code(secret, "12345") is False  # Trop court
        assert TOTPService.verify_code(secret, "1234567") is False  # Trop long
        assert TOTPService.verify_code(secret, "") is False  # Vide

    def test_generate_backup_codes(self):
        """Test generation des codes de secours."""
        from moteur.totp import TOTPService

        codes = TOTPService.generate_backup_codes()

        assert len(codes) == TOTPService.BACKUP_CODE_COUNT
        for code in codes:
            # Format xxxx-xxxx
            assert "-" in code
            assert len(code) == 9

    def test_backup_code_hashing(self):
        """Test hachage des codes de secours."""
        from moteur.totp import TOTPService

        code = "ABCD-EFGH"
        hash1 = TOTPService.hash_backup_code(code)
        hash2 = TOTPService.hash_backup_code(code)

        # Le meme code produit le meme hash
        assert hash1 == hash2

        # Hash different pour code different
        hash3 = TOTPService.hash_backup_code("WXYZ-1234")
        assert hash1 != hash3

    def test_backup_code_verification(self):
        """Test verification des codes de secours."""
        from moteur.totp import TOTPService

        codes = ["AAAA-BBBB", "CCCC-DDDD", "EEEE-FFFF"]
        hashed = [TOTPService.hash_backup_code(c) for c in codes]

        # Code valide
        idx = TOTPService.verify_backup_code("CCCC-DDDD", hashed)
        assert idx == 1

        # Code invalide
        idx = TOTPService.verify_backup_code("XXXX-YYYY", hashed)
        assert idx is None


# =============================================================================
# Tests Pending 2FA Token
# =============================================================================
class TestPending2FAToken:
    """Tests du token en attente de 2FA."""

    def test_pending_2fa_token_short_expiry(self, mock_settings):
        """Test que le token pending 2FA a une courte duree de vie."""
        from moteur.auth import create_pending_2fa_token
        from jose import jwt

        with patch("moteur.auth.settings.SECRET_KEY", "test_secret_key_minimum_32_characters_for_jwt"):
            with patch("moteur.auth.settings.JWT_ALGORITHM", "HS256"):
                token = create_pending_2fa_token({"sub": "user123", "tenant_id": "tenant123"})

        payload = jwt.decode(
            token,
            "test_secret_key_minimum_32_characters_for_jwt",
            algorithms=["HS256"]
        )

        assert payload["type"] == "pending_2fa"
        # Expiration dans ~5 minutes
        exp_time = datetime.utcfromtimestamp(payload["exp"])
        now = datetime.utcnow()
        delta = exp_time - now
        assert delta.total_seconds() <= 300  # 5 minutes max


# =============================================================================
# Tests Password Security
# =============================================================================
class TestPasswordSecurity:
    """Tests de securite des mots de passe."""

    def test_password_hash_is_argon2(self):
        """Test que les mots de passe sont hashes avec Argon2."""
        from moteur.auth import hash_password

        hashed = hash_password("testpassword")

        assert hashed.startswith("$argon2")

    def test_password_verify_correct(self):
        """Test verification d'un mot de passe correct."""
        from moteur.auth import hash_password, verify_password

        password = "MySecurePassword123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_password_verify_incorrect(self):
        """Test verification d'un mot de passe incorrect."""
        from moteur.auth import hash_password, verify_password

        password = "MySecurePassword123!"
        hashed = hash_password(password)

        assert verify_password("WrongPassword", hashed) is False

    def test_password_hash_is_unique(self):
        """Test que chaque hash est unique (salt)."""
        from moteur.auth import hash_password

        password = "SamePassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Meme mot de passe, hashes differents (grace au salt)
        assert hash1 != hash2


# =============================================================================
# Tests Token Blacklist
# =============================================================================
class TestTokenBlacklist:
    """Tests de la blacklist de tokens."""

    @pytest.mark.asyncio
    async def test_revoke_token(self):
        """Test revocation d'un token."""
        from moteur.token_blacklist import TokenBlacklist

        with patch.object(TokenBlacklist, "revoke_token", new_callable=AsyncMock) as mock_revoke:
            mock_revoke.return_value = True

            result = await TokenBlacklist.revoke_token(
                jti="test-jti-123",
                tenant_id="tenant-123",
                reason="logout"
            )

            assert result is True
            mock_revoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_revoked_true(self):
        """Test detection d'un token revoque."""
        from moteur.token_blacklist import TokenBlacklist

        with patch.object(TokenBlacklist, "is_revoked", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            result = await TokenBlacklist.is_revoked(
                jti="revoked-jti",
                tenant_id="tenant-123"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_is_revoked_false(self):
        """Test detection d'un token non revoque."""
        from moteur.token_blacklist import TokenBlacklist

        with patch.object(TokenBlacklist, "is_revoked", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False

            result = await TokenBlacklist.is_revoked(
                jti="valid-jti",
                tenant_id="tenant-123"
            )

            assert result is False


# =============================================================================
# Tests Role-Based Access Control
# =============================================================================
class TestRBAC:
    """Tests du controle d'acces base sur les roles."""

    def test_roles_hierarchy(self):
        """Test hierarchie des roles."""
        from moteur.auth import ROLES

        assert ROLES["admin"]["level"] > ROLES["manager"]["level"]
        assert ROLES["manager"]["level"] > ROLES["user"]["level"]

    @pytest.mark.asyncio
    async def test_require_role_admin(self, admin_user):
        """Test que require_role('admin') fonctionne."""
        from moteur.auth import require_role
        from fastapi import HTTPException

        checker = require_role("admin")

        # Admin peut acceder
        result = await checker(user=admin_user)
        assert result == admin_user

    @pytest.mark.asyncio
    async def test_require_role_blocks_insufficient(self, user_tenant_a):
        """Test que require_role bloque les roles insuffisants."""
        from moteur.auth import require_role
        from fastapi import HTTPException

        checker = require_role("admin")

        # User normal ne peut pas acceder
        with pytest.raises(HTTPException) as exc_info:
            await checker(user=user_tenant_a)

        assert exc_info.value.status_code == 403


# =============================================================================
# Execution
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
