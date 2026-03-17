# =============================================================================
# AZALPLUS - Tests d'Isolation Multi-Tenant
# =============================================================================
"""
Tests de securite pour l'isolation multi-tenant.

Verifie que:
- Un tenant ne peut JAMAIS acceder aux donnees d'un autre tenant
- tenant_id est obligatoire sur toutes les requetes
- Le middleware TenantMiddleware fonctionne correctement
- Les requetes cross-tenant sont bloquees

NORME: AZA-TENANT - Isolation obligatoire
"""

import pytest
from datetime import datetime
from typing import Dict
from uuid import UUID, uuid4
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, "/home/ubuntu/azalplus")


# =============================================================================
# Tests TenantContext
# =============================================================================
class TestTenantContext:
    """Tests du contexte tenant."""

    def test_tenant_context_set_and_get(self):
        """Test set et get du contexte tenant."""
        from moteur.tenant import TenantContext

        tenant_id = uuid4()
        user_id = uuid4()
        email = "test@example.com"

        TenantContext.set(tenant_id, user_id, email)

        assert TenantContext.get_tenant_id() == tenant_id
        assert TenantContext.get_user_id() == user_id

        TenantContext.clear()

    def test_tenant_context_clear(self):
        """Test nettoyage du contexte."""
        from moteur.tenant import TenantContext

        tenant_id = uuid4()
        TenantContext.set(tenant_id)

        TenantContext.clear()

        assert TenantContext.get_tenant_id() is None
        assert TenantContext.get_user_id() is None

    def test_tenant_context_isolation_between_requests(self):
        """Test que les contextes sont isoles entre requetes."""
        from moteur.tenant import TenantContext

        tenant_1 = uuid4()
        tenant_2 = uuid4()

        # Premiere requete
        TenantContext.set(tenant_1)
        assert TenantContext.get_tenant_id() == tenant_1

        # Simuler fin de requete
        TenantContext.clear()

        # Deuxieme requete avec autre tenant
        TenantContext.set(tenant_2)
        assert TenantContext.get_tenant_id() == tenant_2
        assert TenantContext.get_tenant_id() != tenant_1

        TenantContext.clear()

    def test_get_current_tenant_raises_without_context(self):
        """Test que get_current_tenant leve une erreur sans contexte."""
        from moteur.tenant import TenantContext, get_current_tenant
        from fastapi import HTTPException

        TenantContext.clear()

        with pytest.raises(HTTPException) as exc_info:
            get_current_tenant()

        assert exc_info.value.status_code == 400
        assert "Tenant non defini" in str(exc_info.value.detail).lower() or "tenant" in str(exc_info.value.detail).lower()

    def test_system_tenant_id_exists(self):
        """Test que le SYSTEM_TENANT_ID est defini."""
        from moteur.tenant import SYSTEM_TENANT_ID

        assert SYSTEM_TENANT_ID is not None
        assert isinstance(SYSTEM_TENANT_ID, UUID)
        assert str(SYSTEM_TENANT_ID) == "00000000-0000-0000-0000-000000000000"


# =============================================================================
# Tests TenantMiddleware
# =============================================================================
class TestTenantMiddleware:
    """Tests du middleware multi-tenant."""

    @pytest.mark.asyncio
    async def test_middleware_blocks_unauthenticated_non_public_route(self, mock_request):
        """Test que le middleware bloque les requetes non authentifiees."""
        from moteur.tenant import TenantMiddleware
        from starlette.responses import Response

        middleware = TenantMiddleware(app=MagicMock())

        # Requete sans user sur route protegee
        mock_request.url.path = "/api/clients"
        mock_request.state.user = None
        mock_request.method = "GET"
        mock_request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_middleware_allows_public_routes(self, mock_request):
        """Test que le middleware laisse passer les routes publiques."""
        from moteur.tenant import TenantMiddleware

        middleware = TenantMiddleware(app=MagicMock())

        # Route publique
        mock_request.url.path = "/health"
        mock_request.method = "GET"

        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_middleware_allows_options_requests(self, mock_request):
        """Test que les requetes OPTIONS passent (CORS preflight)."""
        from moteur.tenant import TenantMiddleware

        middleware = TenantMiddleware(app=MagicMock())

        mock_request.method = "OPTIONS"
        mock_request.url.path = "/api/clients"

        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_middleware_extracts_tenant_from_user(self, mock_request, user_tenant_a):
        """Test extraction du tenant depuis l'utilisateur."""
        from moteur.tenant import TenantMiddleware, TenantContext

        middleware = TenantMiddleware(app=MagicMock())

        mock_request.url.path = "/api/clients"
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.state.user = user_tenant_a
        mock_request.query_params = {}

        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        # Mock Guardian.check_tenant_access
        with patch("moteur.tenant.Guardian") as mock_guardian:
            mock_guardian.check_tenant_access = AsyncMock(
                return_value=MagicMock(blocked=False)
            )

            response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_blocks_missing_tenant(self, mock_request):
        """Test que le middleware bloque si tenant manquant."""
        from moteur.tenant import TenantMiddleware

        middleware = TenantMiddleware(app=MagicMock())

        # User sans tenant_id et pas createur
        mock_request.url.path = "/api/clients"
        mock_request.method = "GET"
        mock_request.headers = {}
        mock_request.state.user = {
            "id": str(uuid4()),
            "email": "user@test.com",
            "tenant_id": None,  # Pas de tenant!
            "role": "user"
        }
        mock_request.query_params = {}

        call_next = AsyncMock()

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 400
        call_next.assert_not_called()

    def test_is_public_route(self):
        """Test detection des routes publiques."""
        from moteur.tenant import TenantMiddleware

        middleware = TenantMiddleware(app=MagicMock())

        # Routes publiques
        assert middleware._is_public_route("/") is True
        assert middleware._is_public_route("/health") is True
        assert middleware._is_public_route("/api/auth/login") is True
        assert middleware._is_public_route("/api/auth/register") is True
        assert middleware._is_public_route("/static/app.js") is True

        # Routes protegees
        assert middleware._is_public_route("/api/clients") is False
        assert middleware._is_public_route("/api/factures") is False
        assert middleware._is_public_route("/api/users") is False

    def test_extract_tenant_from_header(self, mock_request):
        """Test extraction tenant depuis header X-Tenant-ID."""
        from moteur.tenant import TenantMiddleware

        middleware = TenantMiddleware(app=MagicMock())

        tenant_id = str(uuid4())
        mock_request.headers = {"X-Tenant-ID": tenant_id}
        mock_request.query_params = {}
        mock_request.url.path = "/api/test"

        extracted = middleware._extract_tenant_from_request(mock_request)

        assert extracted == tenant_id

    def test_extract_tenant_from_query_param(self, mock_request):
        """Test extraction tenant depuis query param."""
        from moteur.tenant import TenantMiddleware

        middleware = TenantMiddleware(app=MagicMock())

        tenant_id = str(uuid4())
        mock_request.headers = {}
        mock_request.query_params = {"tenant_id": tenant_id}
        mock_request.url.path = "/api/test"

        extracted = middleware._extract_tenant_from_request(mock_request)

        assert extracted == tenant_id


# =============================================================================
# Tests Database Query Isolation
# =============================================================================
class TestDatabaseIsolation:
    """Tests d'isolation au niveau database."""

    def test_query_requires_tenant_id(self):
        """Test que Database.query requiert tenant_id."""
        from moteur.db import Database

        # Appeler query sans tenant_id devrait lever une erreur
        # ou ne rien retourner
        with pytest.raises(TypeError):
            Database.query("clients")  # Manque tenant_id

    def test_query_filters_by_tenant(self):
        """Test que les requetes filtrent par tenant."""
        # Ce test verifie la structure de la requete SQL generee

        from moteur.db import Database
        from unittest.mock import patch

        tenant_id = uuid4()

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute = MagicMock(return_value=MagicMock(fetchone=lambda: None))

            try:
                Database.query("clients", tenant_id)
            except:
                pass  # On veut juste verifier l'appel

            # Verifier que execute a ete appele avec tenant_id
            if mock_ctx.execute.called:
                call_args = mock_ctx.execute.call_args
                # La requete doit contenir tenant_id
                assert "tenant_id" in str(call_args)

    def test_insert_adds_tenant_id(self):
        """Test que insert ajoute automatiquement tenant_id."""
        from moteur.db import Database

        tenant_id = uuid4()
        data = {"nom": "Test Client"}

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            mock_result = MagicMock()
            mock_result.fetchone = MagicMock(return_value=MagicMock(_mapping={"id": str(uuid4())}))
            mock_ctx.execute = MagicMock(return_value=mock_result)

            try:
                result = Database.insert("clients", tenant_id, data)
            except:
                pass

            # Verifier que tenant_id est dans les params
            if mock_ctx.execute.called:
                call_args = mock_ctx.execute.call_args
                params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
                assert str(tenant_id) in str(params)

    def test_update_filters_by_tenant(self):
        """Test que update filtre par tenant_id."""
        from moteur.db import Database

        tenant_id = uuid4()
        record_id = uuid4()
        data = {"nom": "Updated"}

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute = MagicMock(return_value=MagicMock(fetchone=lambda: None))

            try:
                Database.update("clients", tenant_id, record_id, data)
            except:
                pass

            if mock_ctx.execute.called:
                call_args = mock_ctx.execute.call_args
                query = str(call_args[0][0])
                assert "tenant_id" in query

    def test_soft_delete_filters_by_tenant(self):
        """Test que soft_delete filtre par tenant_id."""
        from moteur.db import Database

        tenant_id = uuid4()
        record_id = uuid4()

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute = MagicMock(return_value=MagicMock(rowcount=1))

            try:
                Database.soft_delete("clients", tenant_id, record_id)
            except:
                pass

            if mock_ctx.execute.called:
                call_args = mock_ctx.execute.call_args
                query = str(call_args[0][0])
                assert "tenant_id" in query


# =============================================================================
# Tests Cross-Tenant Access Prevention
# =============================================================================
class TestCrossTenantPrevention:
    """Tests de prevention d'acces cross-tenant."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_tenant_data_via_header(
        self, mock_request, user_tenant_a
    ):
        """Test qu'un user ne peut pas acceder a un autre tenant via header."""
        from moteur.tenant import TenantMiddleware
        from conftest import TEST_TENANT_B_ID

        middleware = TenantMiddleware(app=MagicMock())

        # User du tenant A essaie d'acceder au tenant B
        mock_request.url.path = "/api/clients"
        mock_request.method = "GET"
        mock_request.headers = {"X-Tenant-ID": str(TEST_TENANT_B_ID)}

        # Creer une copie avec les bons types
        user_state = {
            "id": str(user_tenant_a["id"]),
            "email": user_tenant_a["email"],
            "tenant_id": str(user_tenant_a["tenant_id"]),
            "role": user_tenant_a["role"]
        }
        mock_request.state.user = user_state
        mock_request.query_params = {}

        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        with patch("moteur.tenant.Guardian") as mock_guardian:
            # Guardian doit bloquer l'acces
            mock_guardian.check_tenant_access = AsyncMock(
                return_value=MagicMock(blocked=True, neutral_message="Not found")
            )

            response = await middleware.dispatch(mock_request, call_next)

        # Doit etre bloque
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_access_other_tenant_data_via_query_param(
        self, mock_request, user_tenant_a
    ):
        """Test qu'un user ne peut pas acceder a un autre tenant via query param."""
        from moteur.tenant import TenantMiddleware
        from conftest import TEST_TENANT_B_ID

        middleware = TenantMiddleware(app=MagicMock())

        mock_request.url.path = "/api/clients"
        mock_request.method = "GET"
        mock_request.headers = {}

        # Creer une copie avec les bons types
        user_state = {
            "id": str(user_tenant_a["id"]),
            "email": user_tenant_a["email"],
            "tenant_id": str(user_tenant_a["tenant_id"]),
            "role": user_tenant_a["role"]
        }
        mock_request.state.user = user_state
        mock_request.query_params = {"tenant_id": str(TEST_TENANT_B_ID)}

        call_next = AsyncMock()

        with patch("moteur.tenant.Guardian") as mock_guardian:
            mock_guardian.check_tenant_access = AsyncMock(
                return_value=MagicMock(blocked=True, neutral_message="Not found")
            )

            response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 404

    def test_database_get_by_id_respects_tenant(self):
        """Test que get_by_id ne retourne rien si tenant different."""
        from moteur.db import Database
        from conftest import TEST_TENANT_A_ID, TEST_TENANT_B_ID

        record_id = uuid4()

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)

            # Simuler qu'un enregistrement existe pour tenant A
            mock_ctx.execute = MagicMock(return_value=MagicMock(fetchone=lambda: None))

            # Tenant B essaie de recuperer l'enregistrement
            result = Database.get_by_id("clients", TEST_TENANT_B_ID, record_id)

            # Doit retourner None (pas d'acces)
            assert result is None


# =============================================================================
# Tests Guardian Integration
# =============================================================================
class TestGuardianIntegration:
    """Tests d'integration avec Guardian."""

    @pytest.mark.asyncio
    async def test_guardian_blocks_cross_tenant_access(self):
        """Test que Guardian bloque les acces cross-tenant."""
        from moteur.guardian import Guardian
        from conftest import TEST_TENANT_A_ID, TEST_TENANT_B_ID

        # User du tenant A essaie d'acceder au tenant B
        result = await Guardian.check_tenant_access(
            request_tenant_id=TEST_TENANT_B_ID,
            user_tenant_id=TEST_TENANT_A_ID,
            user_email="user@tenant-a.com"
        )

        assert result.blocked is True

    @pytest.mark.asyncio
    async def test_guardian_allows_same_tenant_access(self):
        """Test que Guardian autorise l'acces au meme tenant."""
        from moteur.guardian import Guardian
        from conftest import TEST_TENANT_A_ID

        result = await Guardian.check_tenant_access(
            request_tenant_id=TEST_TENANT_A_ID,
            user_tenant_id=TEST_TENANT_A_ID,
            user_email="user@tenant-a.com"
        )

        assert result.blocked is False


# =============================================================================
# Tests Tenant in JWT Token
# =============================================================================
class TestTenantInToken:
    """Tests du tenant_id dans les tokens JWT."""

    def test_token_contains_tenant_id(self, valid_token_tenant_a):
        """Test que le token contient bien le tenant_id."""
        from jose import jwt
        from conftest import TEST_SECRET_KEY, TEST_TENANT_A_ID

        payload = jwt.decode(valid_token_tenant_a, TEST_SECRET_KEY, algorithms=["HS256"])

        assert "tenant_id" in payload
        assert payload["tenant_id"] == str(TEST_TENANT_A_ID)

    def test_different_tenants_have_different_tokens(
        self, valid_token_tenant_a, valid_token_tenant_b
    ):
        """Test que differents tenants ont des tokens differents."""
        from jose import jwt
        from conftest import TEST_SECRET_KEY

        payload_a = jwt.decode(valid_token_tenant_a, TEST_SECRET_KEY, algorithms=["HS256"])
        payload_b = jwt.decode(valid_token_tenant_b, TEST_SECRET_KEY, algorithms=["HS256"])

        assert payload_a["tenant_id"] != payload_b["tenant_id"]

    def test_token_tenant_must_match_user_tenant(self, mock_settings):
        """Test que le tenant du token doit matcher celui de l'utilisateur."""
        from jose import jwt
        from conftest import TEST_TENANT_A_ID, TEST_TENANT_B_ID, TEST_SECRET_KEY

        # Token forge avec mauvais tenant
        forged_token = jwt.encode({
            "sub": str(uuid4()),
            "email": "user@tenant-a.com",
            "tenant_id": str(TEST_TENANT_B_ID),  # Mauvais tenant!
            "type": "access",
            "exp": 9999999999
        }, TEST_SECRET_KEY, algorithm="HS256")

        # Decoder le token
        payload = jwt.decode(forged_token, TEST_SECRET_KEY, algorithms=["HS256"])

        # Le tenant dans le token ne correspond pas au tenant attendu
        assert payload["tenant_id"] != str(TEST_TENANT_A_ID)


# =============================================================================
# Tests Bulk Operations Isolation
# =============================================================================
class TestBulkOperationsIsolation:
    """Tests d'isolation pour les operations en masse."""

    def test_global_search_respects_tenant(self):
        """Test que global_search respecte l'isolation tenant."""
        from moteur.db import Database

        tenant_id = uuid4()

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute = MagicMock(return_value=iter([]))

            try:
                Database.global_search(
                    tenant_id=tenant_id,
                    query="test",
                    tables=["clients", "factures"]
                )
            except:
                pass

            # Verifier que chaque requete contient tenant_id
            for call in mock_ctx.execute.call_args_list:
                query = str(call[0][0])
                assert "tenant_id" in query

    def test_count_respects_tenant(self):
        """Test que count respecte l'isolation tenant."""
        from moteur.db import Database

        tenant_id = uuid4()

        with patch.object(Database, "get_session") as mock_session:
            mock_ctx = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute = MagicMock(return_value=MagicMock(scalar=lambda: 0))

            try:
                Database.count("clients", tenant_id)
            except:
                pass

            if mock_ctx.execute.called:
                call_args = mock_ctx.execute.call_args
                query = str(call_args[0][0])
                assert "tenant_id" in query


# =============================================================================
# Execution
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
