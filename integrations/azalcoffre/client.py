"""
AZALPLUS - Client API AZALCOFFRE
Communication avec le coffre-fort numérique NF Z42-013

Utilise la configuration centralisée de integrations/settings.py
"""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from uuid import UUID

import httpx

from .models import (
    ArchivedDocument,
    ArchiveRequest,
    ArchiveSearchCriteria,
    ArchiveStatus,
    IntegrityProof,
)
from ..settings import get_settings, AzalCoffreSettings

logger = logging.getLogger(__name__)


# Alias pour compatibilité - utilise maintenant settings.py
AzalCoffreConfig = AzalCoffreSettings


class AzalCoffreError(Exception):
    """Erreur API AZALCOFFRE"""

    def __init__(self, status_code: int, message: str, details: Optional[dict] = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"AZALCOFFRE Error {status_code}: {message}")


class AzalCoffreClient:
    """
    Client API pour AZALCOFFRE.

    Gère l'archivage légal des documents avec :
    - Hachage SHA-512
    - Horodatage TSA RFC 3161
    - Conformité NF Z42-013

    Utilise la configuration centralisée depuis settings.py
    """

    def __init__(self, settings: Optional[AzalCoffreSettings] = None):
        if settings:
            self._settings = settings
        else:
            self._settings = get_settings().azalcoffre

        if not self._settings.is_configured:
            logger.warning("AZALCOFFRE non configuré - AZALCOFFRE_API_KEY requis")

        self._client = httpx.Client(
            base_url=self._settings.base_url,
            timeout=self._settings.timeout,
            verify=self._settings.verify_ssl,
        )

    # Alias pour compatibilité
    @property
    def config(self) -> AzalCoffreSettings:
        return self._settings

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.close()

    def _headers(self, tenant_id: UUID) -> dict:
        """Headers pour les requêtes API"""
        return {
            "Authorization": f"Bearer {self._settings.api_key}",
            "X-Tenant-ID": str(tenant_id),
            "Content-Type": "application/json",
            "X-Source": "AZALPLUS",
        }

    def _handle_response(self, response: httpx.Response) -> dict:
        """Gère la réponse API"""
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 201:
            return response.json()
        elif response.status_code == 404:
            raise AzalCoffreError(404, "Document non trouvé")
        elif response.status_code == 401:
            raise AzalCoffreError(401, "Non autorisé - Vérifier API key")
        elif response.status_code == 403:
            raise AzalCoffreError(403, "Accès interdit - Vérifier tenant_id")
        else:
            try:
                error_data = response.json()
                message = error_data.get("detail", response.text)
            except Exception:
                message = response.text
            raise AzalCoffreError(response.status_code, message)

    # === ARCHIVAGE ===

    def archive_document(self, request: ArchiveRequest) -> ArchivedDocument:
        """
        Archive un document dans AZALCOFFRE.

        Le document sera :
        - Haché en SHA-512
        - Horodaté via TSA RFC 3161 (si demandé)
        - Stocké avec métadonnées complètes
        - Conservé pendant la durée légale

        Args:
            request: Requête d'archivage avec fichier et métadonnées

        Returns:
            ArchivedDocument avec preuve d'intégrité
        """
        # Encoder le fichier en base64
        file_base64 = base64.b64encode(request.file_content).decode()

        payload = {
            "tenant_id": str(request.tenant_id),
            "source_id": str(request.source_id),
            "source_type": request.source_type.value,
            "source_system": "AZALPLUS",
            "document_number": request.document_number,
            "document_date": request.document_date.isoformat(),
            "file_content": file_base64,
            "file_name": request.file_name,
            "mime_type": request.mime_type,
            "emitter_name": request.emitter_name,
            "emitter_siret": request.emitter_siret,
            "recipient_name": request.recipient_name,
            "recipient_siret": request.recipient_siret,
            "amount_ht": str(request.amount_ht) if request.amount_ht else None,
            "amount_ttc": str(request.amount_ttc) if request.amount_ttc else None,
            "retention_years": request.retention_years,
            "request_tsa": request.request_tsa,
            "request_signature": request.request_signature,
        }

        response = self._client.post(
            "/api/v1/archive/documents",
            json=payload,
            headers=self._headers(request.tenant_id),
        )

        data = self._handle_response(response)
        logger.info(
            f"Document archivé: {request.document_number} -> {data.get('id')}"
        )

        return self._parse_archived_document(data)

    def get_document(self, tenant_id: UUID, archive_id: UUID) -> ArchivedDocument:
        """Récupère les métadonnées d'un document archivé"""
        response = self._client.get(
            f"/api/v1/archive/documents/{archive_id}",
            headers=self._headers(tenant_id),
        )
        data = self._handle_response(response)
        return self._parse_archived_document(data)

    def get_document_by_source(
        self, tenant_id: UUID, source_id: UUID
    ) -> Optional[ArchivedDocument]:
        """Récupère un document par son ID source (facture AZALPLUS)"""
        response = self._client.get(
            f"/api/v1/archive/documents/by-source/{source_id}",
            headers=self._headers(tenant_id),
        )
        if response.status_code == 404:
            return None
        data = self._handle_response(response)
        return self._parse_archived_document(data)

    def download_document(self, tenant_id: UUID, archive_id: UUID) -> bytes:
        """
        Télécharge le fichier original depuis AZALCOFFRE.

        Returns:
            Contenu binaire du fichier
        """
        response = self._client.get(
            f"/api/v1/archive/documents/{archive_id}/download",
            headers=self._headers(tenant_id),
        )
        if response.status_code != 200:
            raise AzalCoffreError(response.status_code, "Erreur téléchargement")

        logger.info(f"Document téléchargé: {archive_id}")
        return response.content

    def search_documents(
        self, criteria: ArchiveSearchCriteria
    ) -> tuple[List[ArchivedDocument], int]:
        """
        Recherche dans les documents archivés.

        Returns:
            Tuple (liste documents, total)
        """
        params = {
            "page": criteria.page,
            "page_size": criteria.page_size,
            "sort_by": criteria.sort_by,
            "sort_desc": criteria.sort_desc,
        }

        if criteria.source_type:
            params["source_type"] = criteria.source_type.value
        if criteria.status:
            params["status"] = criteria.status.value
        if criteria.date_from:
            params["date_from"] = criteria.date_from.isoformat()
        if criteria.date_to:
            params["date_to"] = criteria.date_to.isoformat()
        if criteria.document_number:
            params["document_number"] = criteria.document_number
        if criteria.emitter_siret:
            params["emitter_siret"] = criteria.emitter_siret
        if criteria.recipient_siret:
            params["recipient_siret"] = criteria.recipient_siret

        response = self._client.get(
            "/api/v1/archive/documents",
            params=params,
            headers=self._headers(criteria.tenant_id),
        )

        data = self._handle_response(response)
        documents = [
            self._parse_archived_document(doc) for doc in data.get("items", [])
        ]
        total = data.get("total", len(documents))

        return documents, total

    # === INTÉGRITÉ ===

    def verify_integrity(self, tenant_id: UUID, archive_id: UUID) -> IntegrityProof:
        """
        Vérifie l'intégrité d'un document archivé.

        Contrôle :
        - Hash SHA-512 correspond au fichier
        - Horodatage TSA valide
        - Chaînage audit intact

        Returns:
            IntegrityProof avec résultat vérification
        """
        response = self._client.post(
            f"/api/v1/archive/documents/{archive_id}/verify",
            headers=self._headers(tenant_id),
        )
        data = self._handle_response(response)

        proof = IntegrityProof(
            document_id=UUID(data.get("document_id")),
            archive_id=archive_id,
            hash_algorithm=data.get("hash_algorithm", "SHA-512"),
            hash_value=data.get("hash_value", ""),
            hash_computed_at=self._parse_datetime(data.get("hash_computed_at")),
            tsa_timestamp=self._parse_datetime(data.get("tsa_timestamp")),
            tsa_token=data.get("tsa_token"),
            tsa_authority=data.get("tsa_authority", ""),
            previous_hash=data.get("previous_hash"),
            entry_hash=data.get("entry_hash"),
            last_verified_at=datetime.now(),
            is_valid=data.get("is_valid", False),
            verification_message=data.get("verification_message"),
        )

        logger.info(
            f"Intégrité vérifiée: {archive_id} -> {'OK' if proof.is_valid else 'ERREUR'}"
        )
        return proof

    def get_integrity_certificate(
        self, tenant_id: UUID, archive_id: UUID
    ) -> bytes:
        """
        Génère un certificat d'intégrité PDF.

        Document attestant :
        - Authenticité de l'origine
        - Intégrité du contenu
        - Horodatage certifié

        Returns:
            PDF du certificat
        """
        response = self._client.get(
            f"/api/v1/archive/documents/{archive_id}/certificate",
            headers=self._headers(tenant_id),
        )
        if response.status_code != 200:
            raise AzalCoffreError(response.status_code, "Erreur génération certificat")

        return response.content

    # === STATISTIQUES ===

    def get_stats(self, tenant_id: UUID) -> dict:
        """Statistiques d'archivage pour un tenant"""
        response = self._client.get(
            "/api/v1/archive/stats",
            headers=self._headers(tenant_id),
        )
        return self._handle_response(response)

    # === HEALTH CHECK ===

    def health_check(self) -> bool:
        """Vérifie la connexion à AZALCOFFRE"""
        try:
            response = self._client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check AZALCOFFRE failed: {e}")
            return False

    # === HELPERS ===

    def _parse_archived_document(self, data: dict) -> ArchivedDocument:
        """Parse un document depuis la réponse API"""
        from decimal import Decimal
        from .models import DocumentType

        integrity_data = data.get("integrity_proof")
        integrity_proof = None
        if integrity_data:
            integrity_proof = IntegrityProof(
                document_id=UUID(integrity_data.get("document_id")),
                archive_id=UUID(data.get("id")),
                hash_algorithm=integrity_data.get("hash_algorithm", "SHA-512"),
                hash_value=integrity_data.get("hash_value", ""),
                hash_computed_at=self._parse_datetime(
                    integrity_data.get("hash_computed_at")
                ),
                tsa_timestamp=self._parse_datetime(integrity_data.get("tsa_timestamp")),
                tsa_token=integrity_data.get("tsa_token"),
                is_valid=integrity_data.get("is_valid", True),
            )

        return ArchivedDocument(
            id=UUID(data.get("id")),
            tenant_id=UUID(data.get("tenant_id")),
            source_id=UUID(data.get("source_id")),
            source_type=DocumentType(data.get("source_type")),
            document_number=data.get("document_number", ""),
            document_date=self._parse_date(data.get("document_date")),
            description=data.get("description", ""),
            emitter_name=data.get("emitter_name"),
            emitter_siret=data.get("emitter_siret"),
            recipient_name=data.get("recipient_name"),
            recipient_siret=data.get("recipient_siret"),
            amount_ht=Decimal(data["amount_ht"]) if data.get("amount_ht") else None,
            amount_ttc=Decimal(data["amount_ttc"]) if data.get("amount_ttc") else None,
            status=ArchiveStatus(data.get("status", "PENDING")),
            archived_at=self._parse_datetime(data.get("archived_at")),
            retention_years=data.get("retention_years", 10),
            expires_at=self._parse_date(data.get("expires_at")),
            integrity_proof=integrity_proof,
            file_name=data.get("file_name", ""),
            file_size=data.get("file_size", 0),
            mime_type=data.get("mime_type", "application/pdf"),
            coffre_url=data.get("coffre_url"),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse une datetime ISO"""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def _parse_date(self, value: Optional[str]):
        """Parse une date ISO"""
        from datetime import date

        if not value:
            return date.today()
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return date.today()
