# =============================================================================
# Tests AZALMED - Module médical
# =============================================================================

import pytest
from uuid import uuid4, UUID
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO

from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tenant_id():
    """Tenant ID de test."""
    return uuid4()


@pytest.fixture
def praticien_id():
    """Praticien ID de test."""
    return uuid4()


@pytest.fixture
def patient_id():
    """Patient ID de test."""
    return uuid4()


@pytest.fixture
def mock_database():
    """Mock de la classe Database."""
    with patch("moteur.db.Database") as mock:
        mock.insert.return_value = {"id": str(uuid4())}
        mock.get_by_id.return_value = {
            "id": str(uuid4()),
            "nom": "Test",
        }
        mock.update.return_value = {"id": str(uuid4())}
        mock.query.return_value = []
        yield mock


# =============================================================================
# Tests CoffreService
# =============================================================================

class TestCoffreService:
    """Tests du service coffre-fort HDS."""

    def test_calculer_hash_sha256(self, tenant_id):
        """Test calcul hash SHA-256."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)
        contenu = b"Test content"

        hash_result = service._calculer_hash(contenu, "sha256")

        assert hash_result is not None
        assert len(hash_result) == 64  # SHA-256 = 64 caractères hex

    def test_calculer_hash_sha512(self, tenant_id):
        """Test calcul hash SHA-512."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)
        contenu = b"Test content"

        hash_result = service._calculer_hash(contenu, "sha512")

        assert hash_result is not None
        assert len(hash_result) == 128  # SHA-512 = 128 caractères hex

    def test_hash_deterministe(self, tenant_id):
        """Test que le hash est déterministe."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)
        contenu = b"Test content"

        hash1 = service._calculer_hash(contenu, "sha256")
        hash2 = service._calculer_hash(contenu, "sha256")

        assert hash1 == hash2

    def test_hash_different_pour_contenu_different(self, tenant_id):
        """Test que des contenus différents donnent des hash différents."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)

        hash1 = service._calculer_hash(b"Content A", "sha256")
        hash2 = service._calculer_hash(b"Content B", "sha256")

        assert hash1 != hash2

    def test_chiffrement_sans_cle(self, tenant_id):
        """Test chiffrement en mode développement (sans clé)."""
        from app.modules.azalmed.coffre_service import CoffreService

        with patch.dict("os.environ", {"AZALMED_ENCRYPTION_KEY": ""}):
            service = CoffreService(tenant_id)
            contenu = b"Test content"

            # Sans clé, le contenu est retourné tel quel
            result = service._chiffrer(contenu)

            assert result == contenu

    def test_generer_reference(self, tenant_id):
        """Test génération référence document."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)

        ref = service._generer_reference()

        assert ref.startswith("DOC-")
        assert len(ref) > 10

    def test_get_extension(self, tenant_id):
        """Test extraction extension fichier."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)

        assert service._get_extension("document.pdf") == ".pdf"
        assert service._get_extension("image.PNG") == ".png"
        assert service._get_extension("fichier") == ""
        assert service._get_extension("archive.tar.gz") == ".gz"


# =============================================================================
# Tests ScribeService
# =============================================================================

class TestScribeService:
    """Tests du service de transcription."""

    def test_construire_prompt_structuration(self, tenant_id):
        """Test construction du prompt de structuration."""
        from app.modules.azalmed.scribe_service import ScribeService

        service = ScribeService(tenant_id)

        prompt = service._construire_prompt_structuration(
            texte="Patient présente des douleurs abdominales.",
            specialite="Gastro-entérologie",
        )

        assert "Gastro-entérologie" in prompt
        assert "douleurs abdominales" in prompt
        assert "motif" in prompt
        assert "diagnostic" in prompt
        assert "traitement" in prompt

    def test_construire_prompt_sans_specialite(self, tenant_id):
        """Test prompt sans spécialité."""
        from app.modules.azalmed.scribe_service import ScribeService

        service = ScribeService(tenant_id)

        prompt = service._construire_prompt_structuration(
            texte="Consultation standard.",
            specialite=None,
        )

        assert "Consultation standard" in prompt
        assert "spécialisé en" not in prompt


# =============================================================================
# Tests VeilleService
# =============================================================================

class TestVeilleService:
    """Tests du service de veille médicale."""

    def test_parser_pubmed_xml(self, tenant_id):
        """Test parsing XML PubMed."""
        from app.modules.azalmed.veille_service import VeilleService

        service = VeilleService(tenant_id)

        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Article Title</ArticleTitle>
                        <Abstract>
                            <AbstractText>This is the abstract text.</AbstractText>
                        </Abstract>
                        <AuthorList>
                            <Author>
                                <LastName>Dupont</LastName>
                                <ForeName>Jean</ForeName>
                            </Author>
                        </AuthorList>
                    </Article>
                </MedlineCitation>
                <PubmedData>
                    <History>
                        <PubMedPubDate PubStatus="pubmed">
                            <Year>2024</Year>
                            <Month>01</Month>
                            <Day>15</Day>
                        </PubMedPubDate>
                    </History>
                </PubmedData>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        articles = service._parser_pubmed_xml(xml_content)

        assert len(articles) == 1
        assert articles[0]["pmid"] == "12345678"
        assert articles[0]["titre"] == "Test Article Title"
        assert "Dupont" in articles[0]["auteurs"]
        assert articles[0]["source"] == "PUBMED"

    def test_parser_pubmed_xml_vide(self, tenant_id):
        """Test parsing XML vide."""
        from app.modules.azalmed.veille_service import VeilleService

        service = VeilleService(tenant_id)

        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet></PubmedArticleSet>
        """

        articles = service._parser_pubmed_xml(xml_content)

        assert len(articles) == 0

    def test_parser_pubmed_xml_invalide(self, tenant_id):
        """Test parsing XML invalide."""
        from app.modules.azalmed.veille_service import VeilleService

        service = VeilleService(tenant_id)

        articles = service._parser_pubmed_xml("invalid xml content")

        assert len(articles) == 0


# =============================================================================
# Tests SignatureService
# =============================================================================

class TestSignatureService:
    """Tests du service de signature électronique."""

    @pytest.mark.asyncio
    async def test_traiter_webhook_signature_done(self, tenant_id, mock_database):
        """Test traitement webhook signature effectuée."""
        from app.modules.azalmed.signature_service import SignatureService

        service = SignatureService(tenant_id)

        payload = {
            "event_type": "signer.done",
            "signature_request_id": "sig_123",
        }

        result = await service.traiter_webhook(payload)

        assert result["status"] == "ok"
        assert result["action"] == "signature_enregistree"

    @pytest.mark.asyncio
    async def test_traiter_webhook_signature_declined(self, tenant_id, mock_database):
        """Test traitement webhook signature refusée."""
        from app.modules.azalmed.signature_service import SignatureService

        service = SignatureService(tenant_id)

        payload = {
            "event_type": "signer.declined",
            "signature_request_id": "sig_123",
        }

        result = await service.traiter_webhook(payload)

        assert result["status"] == "ok"
        assert result["action"] == "refus_enregistre"

    @pytest.mark.asyncio
    async def test_traiter_webhook_signature_expired(self, tenant_id, mock_database):
        """Test traitement webhook signature expirée."""
        from app.modules.azalmed.signature_service import SignatureService

        service = SignatureService(tenant_id)

        payload = {
            "event_type": "signature_request.expired",
            "signature_request_id": "sig_123",
        }

        result = await service.traiter_webhook(payload)

        assert result["status"] == "ok"
        assert result["action"] == "expiration_enregistree"

    @pytest.mark.asyncio
    async def test_traiter_webhook_event_inconnu(self, tenant_id):
        """Test traitement webhook événement inconnu."""
        from app.modules.azalmed.signature_service import SignatureService

        service = SignatureService(tenant_id)

        payload = {
            "event_type": "unknown_event",
            "signature_request_id": "sig_123",
        }

        result = await service.traiter_webhook(payload)

        assert result["status"] == "ignored"
        assert result["event"] == "unknown_event"


# =============================================================================
# Tests Isolation Tenant
# =============================================================================

class TestTenantIsolation:
    """Tests d'isolation multi-tenant."""

    def test_coffre_service_requires_tenant_id(self):
        """Test que CoffreService nécessite tenant_id."""
        from app.modules.azalmed.coffre_service import CoffreService

        with pytest.raises(TypeError):
            CoffreService()  # Sans tenant_id

    def test_scribe_service_requires_tenant_id(self):
        """Test que ScribeService nécessite tenant_id."""
        from app.modules.azalmed.scribe_service import ScribeService

        with pytest.raises(TypeError):
            ScribeService()  # Sans tenant_id

    def test_veille_service_requires_tenant_id(self):
        """Test que VeilleService nécessite tenant_id."""
        from app.modules.azalmed.veille_service import VeilleService

        with pytest.raises(TypeError):
            VeilleService()  # Sans tenant_id

    def test_signature_service_requires_tenant_id(self):
        """Test que SignatureService nécessite tenant_id."""
        from app.modules.azalmed.signature_service import SignatureService

        with pytest.raises(TypeError):
            SignatureService()  # Sans tenant_id

    def test_service_stores_tenant_id(self, tenant_id):
        """Test que les services stockent le tenant_id."""
        from app.modules.azalmed.coffre_service import CoffreService
        from app.modules.azalmed.scribe_service import ScribeService
        from app.modules.azalmed.veille_service import VeilleService
        from app.modules.azalmed.signature_service import SignatureService

        assert CoffreService(tenant_id).tenant_id == tenant_id
        assert ScribeService(tenant_id).tenant_id == tenant_id
        assert VeilleService(tenant_id).tenant_id == tenant_id
        assert SignatureService(tenant_id).tenant_id == tenant_id


# =============================================================================
# Tests Markers
# =============================================================================

@pytest.mark.critical
class TestCritical:
    """Tests critiques qui doivent passer."""

    def test_hash_sha256_not_empty(self, tenant_id):
        """Hash SHA-256 ne doit jamais être vide."""
        from app.modules.azalmed.coffre_service import CoffreService

        service = CoffreService(tenant_id)
        result = service._calculer_hash(b"x", "sha256")

        assert result
        assert len(result) == 64

    def test_tenant_id_required(self, tenant_id):
        """Tenant ID est obligatoire pour tous les services."""
        from app.modules.azalmed.coffre_service import CoffreService

        # Ne doit pas lever d'exception avec tenant_id
        service = CoffreService(tenant_id)
        assert service.tenant_id == tenant_id


@pytest.mark.tenant_isolation
class TestTenantIsolationMarker:
    """Tests marqués pour isolation tenant."""

    def test_all_services_have_tenant_id(self, tenant_id):
        """Tous les services ont un attribut tenant_id."""
        from app.modules.azalmed.coffre_service import CoffreService
        from app.modules.azalmed.scribe_service import ScribeService
        from app.modules.azalmed.veille_service import VeilleService
        from app.modules.azalmed.signature_service import SignatureService

        services = [
            CoffreService(tenant_id),
            ScribeService(tenant_id),
            VeilleService(tenant_id),
            SignatureService(tenant_id),
        ]

        for service in services:
            assert hasattr(service, "tenant_id")
            assert service.tenant_id == tenant_id
