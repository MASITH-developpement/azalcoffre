# =============================================================================
# AZALPLUS - Client API AZALCOFFRE
# =============================================================================
"""
Client HTTP pour communiquer avec AZALCOFFRE.
Gère l'authentification, les retries et la mise en cache.

API AZALCOFFRE réelle (120+ endpoints) :
- /api/v1/documents/* : Coffre-fort (upload, verify, proof)
- /api/v1/signatures/* : Signatures eIDAS
- /api/v1/invoices/* : Factur-X / PDP
- /api/v1/clients/* : Gestion clients
- /api/v1/employees/* : Gestion employés
"""

import httpx
import hashlib
import json
from typing import Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AzalCoffreConfig:
    """Configuration de connexion à AZALCOFFRE."""
    base_url: str = "https://api.azalcoffre.com"  # Production
    api_key: str = ""  # Format: sk_live_xxx ou sk_sandbox_xxx
    tenant_id: str = ""  # UUID du tenant
    timeout: int = 30
    retry_count: int = 3
    verify_ssl: bool = True


class AzalCoffreClient:
    """
    Client HTTP pour l'API AZALCOFFRE.

    URLs:
        Production: https://api.azalcoffre.com
        Sandbox:    https://sandbox.azalcoffre.com

    Usage:
        config = AzalCoffreConfig(
            base_url="https://api.azalcoffre.com",
            api_key="sk_live_xxxxx",
            tenant_id="uuid-tenant"
        )
        client = AzalCoffreClient(config)

        # Archiver un document
        result = await client.upload_document(
            file_content=pdf_bytes,
            filename="facture.pdf",
            document_type="FACTURE",
            metadata={"numero": "FAC-2026-001"}
        )
    """

    def __init__(self, config: AzalCoffreConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Retourne un client HTTP configuré."""
        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": "AZALPLUS/1.0",
                "Accept": "application/json",
            }
            # Auth par API Key ou JWT
            if self.config.api_key:
                headers["X-API-Key"] = self.config.api_key
            if self.config.tenant_id:
                headers["X-Tenant-ID"] = self.config.tenant_id

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                headers=headers
            )
        return self._client

    async def close(self):
        """Ferme le client HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # DOCUMENTS - Coffre-fort (/api/v1/documents)
    # =========================================================================

    async def upload_document(
        self,
        file_content: bytes,
        filename: str,
        document_type: str,
        metadata: Optional[dict] = None,
        encrypt: bool = False
    ) -> dict:
        """
        Upload un document dans le coffre-fort AZALCOFFRE.

        Endpoint: POST /api/v1/documents/upload

        Args:
            file_content: Contenu binaire du fichier
            filename: Nom du fichier
            document_type: Type (FACTURE, DEVIS, CONTRAT, BULLETIN_PAIE, etc.)
            metadata: Métadonnées additionnelles
            encrypt: Chiffrer le document (AES-128)

        Returns:
            dict avec id, hash_sha256, tsa_timestamp, etc.
        """
        client = await self._get_client()

        files = {
            "file": (filename, file_content, "application/octet-stream")
        }
        data = {
            "document_type": document_type,
            "encrypt": str(encrypt).lower(),
        }
        if metadata:
            data["metadata"] = json.dumps(metadata)

        response = await client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data
        )
        response.raise_for_status()

        result = response.json()
        logger.info(f"Document uploadé: {result.get('id')}")
        return result

    async def upload_documents_batch(
        self,
        documents: list[dict]
    ) -> dict:
        """
        Upload multiple documents en batch.

        Endpoint: POST /api/v1/documents/upload/batch

        Args:
            documents: Liste de {file_content, filename, document_type, metadata}

        Returns:
            dict avec results (liste des documents créés)
        """
        client = await self._get_client()

        files = []
        for i, doc in enumerate(documents):
            files.append(
                ("files", (doc["filename"], doc["file_content"], "application/octet-stream"))
            )

        data = {
            "document_types": json.dumps([d.get("document_type", "AUTRE") for d in documents])
        }

        response = await client.post(
            "/api/v1/documents/upload/batch",
            files=files,
            data=data
        )
        response.raise_for_status()
        return response.json()

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        document_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> dict:
        """
        Liste les documents avec pagination.

        Endpoint: GET /api/v1/documents
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if document_type:
            params["document_type"] = document_type
        if search:
            params["search"] = search

        response = await client.get("/api/v1/documents", params=params)
        response.raise_for_status()
        return response.json()

    async def get_document(self, document_id: str) -> dict:
        """
        Récupère les métadonnées d'un document.

        Endpoint: GET /api/v1/documents/{document_id}
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/documents/{document_id}")
        response.raise_for_status()
        return response.json()

    async def download_document(self, document_id: str) -> bytes:
        """
        Télécharge le contenu d'un document.

        Endpoint: GET /api/v1/documents/{document_id}/download
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/documents/{document_id}/download")
        response.raise_for_status()
        return response.content

    async def verify_document(self, document_id: str) -> dict:
        """
        Vérifie l'intégrité d'un document (hash + TSA).

        Endpoint: GET /api/v1/documents/{document_id}/verify
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/documents/{document_id}/verify")
        response.raise_for_status()
        return response.json()

    async def get_document_proof(self, document_id: str) -> dict:
        """
        Récupère le package de preuve complet (hash + TSA + audit).

        Endpoint: GET /api/v1/documents/{document_id}/proof
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/documents/{document_id}/proof")
        response.raise_for_status()
        return response.json()

    async def get_document_audit_trail(self, document_id: str) -> dict:
        """
        Récupère la chaîne d'audit du document.

        Endpoint: GET /api/v1/documents/{document_id}/audit-trail
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/documents/{document_id}/audit-trail")
        response.raise_for_status()
        return response.json()

    async def get_document_types(self) -> list:
        """
        Liste les types de documents supportés.

        Endpoint: GET /api/v1/documents/types/list
        """
        client = await self._get_client()
        response = await client.get("/api/v1/documents/types/list")
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # SIGNATURES - eIDAS (/api/v1/signatures)
    # =========================================================================

    async def request_signature(
        self,
        document_id: str,
        signers: list[dict],
        signature_level: str = "SIMPLE",
        expiration_hours: int = 72,
        message: Optional[str] = None
    ) -> dict:
        """
        Demande une signature électronique sur un document.

        Endpoint: POST /api/v1/signatures/request

        Args:
            document_id: ID du document dans AZALCOFFRE
            signers: Liste des signataires [{"email": "...", "name": "...", "order": 1}]
            signature_level: SIMPLE (code), ADVANCED (certificat), QUALIFIED (HSM)
            expiration_hours: Délai d'expiration
            message: Message pour les signataires

        Returns:
            dict avec signature_id, status, signers
        """
        client = await self._get_client()

        payload = {
            "document_id": document_id,
            "signers": signers,
            "signature_level": signature_level,
            "expires_at": (datetime.utcnow() + timedelta(hours=expiration_hours)).isoformat(),
            "message": message
        }

        response = await client.post("/api/v1/signatures/request", json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Demande signature créée: {result.get('id')}")
        return result

    async def get_signature(self, signature_id: str) -> dict:
        """
        Récupère le statut d'une demande de signature.

        Endpoint: GET /api/v1/signatures/{signature_id}
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/signatures/{signature_id}")
        response.raise_for_status()
        return response.json()

    async def list_signatures(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> dict:
        """
        Liste les demandes de signature.

        Endpoint: GET /api/v1/signatures
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status

        response = await client.get("/api/v1/signatures", params=params)
        response.raise_for_status()
        return response.json()

    async def sign_document(self, signature_id: str, code: str) -> dict:
        """
        Signe un document avec le code reçu (niveau SIMPLE).

        Endpoint: POST /api/v1/signatures/{signature_id}/sign
        """
        client = await self._get_client()
        response = await client.post(
            f"/api/v1/signatures/{signature_id}/sign",
            json={"code": code}
        )
        response.raise_for_status()
        return response.json()

    async def download_signed_document(self, signature_id: str) -> bytes:
        """
        Télécharge le document signé.

        Endpoint: GET /api/v1/signatures/{signature_id}/download
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/signatures/{signature_id}/download")
        response.raise_for_status()
        return response.content

    async def verify_signatures(self, file_content: bytes) -> dict:
        """
        Vérifie les signatures d'un PDF.

        Endpoint: POST /api/v1/signatures/verify
        """
        client = await self._get_client()
        files = {"file": ("document.pdf", file_content, "application/pdf")}
        response = await client.post("/api/v1/signatures/verify", files=files)
        response.raise_for_status()
        return response.json()

    async def resend_signature_code(self, signature_id: str) -> dict:
        """
        Renvoie le code de signature au signataire.

        Endpoint: POST /api/v1/signatures/{signature_id}/resend-code
        """
        client = await self._get_client()
        response = await client.post(f"/api/v1/signatures/{signature_id}/resend-code")
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # FACTURES - Factur-X / PDP (/api/v1/invoices)
    # =========================================================================

    async def create_invoice(
        self,
        invoice_data: dict,
        profile: str = "EN16931"
    ) -> dict:
        """
        Crée une facture Factur-X.

        Endpoint: POST /api/v1/invoices/create

        Args:
            invoice_data: Données structurées de la facture
            profile: Profil Factur-X (MINIMUM, BASIC_WL, BASIC, EN16931, EXTENDED)

        Returns:
            dict avec id, status, facturx_xml
        """
        client = await self._get_client()

        payload = {
            "invoice": invoice_data,
            "profile": profile
        }

        response = await client.post("/api/v1/invoices/create", json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Facture créée: {result.get('id')}")
        return result

    async def create_invoice_with_pdf(
        self,
        invoice_data: dict,
        pdf_content: bytes,
        profile: str = "EN16931"
    ) -> dict:
        """
        Crée une facture Factur-X à partir d'un PDF existant.

        Endpoint: POST /api/v1/invoices/create-with-pdf
        """
        client = await self._get_client()

        files = {"pdf": ("facture.pdf", pdf_content, "application/pdf")}
        data = {
            "invoice": json.dumps(invoice_data),
            "profile": profile
        }

        response = await client.post(
            "/api/v1/invoices/create-with-pdf",
            files=files,
            data=data
        )
        response.raise_for_status()
        return response.json()

    async def send_invoice_to_ppf(self, invoice_id: str) -> dict:
        """
        Envoie une facture au PPF (Portail Public de Facturation).

        Endpoint: POST /api/v1/invoices/{invoice_id}/send
        """
        client = await self._get_client()
        response = await client.post(f"/api/v1/invoices/{invoice_id}/send")
        response.raise_for_status()

        result = response.json()
        logger.info(f"Facture envoyée au PPF: {invoice_id}")
        return result

    async def receive_invoice(self, file_content: bytes) -> dict:
        """
        Reçoit et parse une facture Factur-X entrante.

        Endpoint: POST /api/v1/invoices/receive
        """
        client = await self._get_client()
        files = {"file": ("facture.pdf", file_content, "application/pdf")}
        response = await client.post("/api/v1/invoices/receive", files=files)
        response.raise_for_status()
        return response.json()

    async def list_invoices(
        self,
        page: int = 1,
        page_size: int = 20,
        direction: Optional[str] = None,  # "inbound" ou "outbound"
        status: Optional[str] = None
    ) -> dict:
        """
        Liste les factures avec pagination.

        Endpoint: GET /api/v1/invoices
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if direction:
            params["direction"] = direction
        if status:
            params["status"] = status

        response = await client.get("/api/v1/invoices", params=params)
        response.raise_for_status()
        return response.json()

    async def get_invoice(self, invoice_id: str) -> dict:
        """
        Récupère le statut d'une facture.

        Endpoint: GET /api/v1/invoices/{invoice_id}
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/invoices/{invoice_id}")
        response.raise_for_status()
        return response.json()

    async def download_invoice_pdf(self, invoice_id: str) -> bytes:
        """
        Télécharge le PDF d'une facture.

        Endpoint: GET /api/v1/invoices/{invoice_id}/pdf
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/invoices/{invoice_id}/pdf")
        response.raise_for_status()
        return response.content

    async def download_invoice_xml(self, invoice_id: str) -> str:
        """
        Télécharge le XML Factur-X d'une facture.

        Endpoint: GET /api/v1/invoices/{invoice_id}/xml
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/invoices/{invoice_id}/xml")
        response.raise_for_status()
        return response.text

    # =========================================================================
    # CLIENTS (/api/v1/clients)
    # =========================================================================

    async def list_clients(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None
    ) -> dict:
        """
        Liste les clients.

        Endpoint: GET /api/v1/clients
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if search:
            params["search"] = search

        response = await client.get("/api/v1/clients", params=params)
        response.raise_for_status()
        return response.json()

    async def get_client(self, client_id: str) -> dict:
        """
        Récupère un client.

        Endpoint: GET /api/v1/clients/{client_id}
        """
        http_client = await self._get_client()
        response = await http_client.get(f"/api/v1/clients/{client_id}")
        response.raise_for_status()
        return response.json()

    async def get_client_documents(self, client_id: str) -> dict:
        """
        Récupère les documents d'un client.

        Endpoint: GET /api/v1/clients/{client_id}/documents
        """
        http_client = await self._get_client()
        response = await http_client.get(f"/api/v1/clients/{client_id}/documents")
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # EMPLOYEES (/api/v1/employees)
    # =========================================================================

    async def list_employees(
        self,
        page: int = 1,
        page_size: int = 20,
        department: Optional[str] = None
    ) -> dict:
        """
        Liste les employés.

        Endpoint: GET /api/v1/employees
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if department:
            params["department"] = department

        response = await client.get("/api/v1/employees", params=params)
        response.raise_for_status()
        return response.json()

    async def get_employee_payslips(self, employee_id: str, year: Optional[int] = None) -> dict:
        """
        Récupère les bulletins de paie d'un employé.

        Endpoint: GET /api/v1/employees/{employee_id}/payslips
        """
        client = await self._get_client()

        params = {}
        if year:
            params["year"] = year

        response = await client.get(
            f"/api/v1/employees/{employee_id}/payslips",
            params=params
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # AUDIT (/api/v1/audit)
    # =========================================================================

    async def list_audit_entries(
        self,
        page: int = 1,
        page_size: int = 50,
        action: Optional[str] = None,
        document_id: Optional[str] = None
    ) -> dict:
        """
        Liste les entrées d'audit.

        Endpoint: GET /api/v1/audit
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if action:
            params["action"] = action
        if document_id:
            params["document_id"] = document_id

        response = await client.get("/api/v1/audit", params=params)
        response.raise_for_status()
        return response.json()

    async def verify_audit_chain(self) -> dict:
        """
        Vérifie l'intégrité de la chaîne d'audit.

        Endpoint: POST /api/v1/audit/verify-chain
        """
        client = await self._get_client()
        response = await client.post("/api/v1/audit/verify-chain")
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # BACKUPS (/api/v1/backups)
    # =========================================================================

    async def create_backup(
        self,
        backup_type: str = "postgresql",
        description: Optional[str] = None
    ) -> dict:
        """
        Crée une sauvegarde manuelle.

        Endpoint: POST /api/v1/backups

        Args:
            backup_type: Type de backup (postgresql, files, mysql, erp, config)
            description: Description optionnelle

        Returns:
            dict avec id, status, size, created_at
        """
        client = await self._get_client()

        payload = {
            "type": backup_type,
            "description": description
        }

        response = await client.post("/api/v1/backups", json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Backup créé: {result.get('id')}")
        return result

    async def list_backups(
        self,
        page: int = 1,
        page_size: int = 20,
        backup_type: Optional[str] = None
    ) -> dict:
        """
        Liste les sauvegardes.

        Endpoint: GET /api/v1/backups
        """
        client = await self._get_client()

        params = {"page": page, "page_size": page_size}
        if backup_type:
            params["type"] = backup_type

        response = await client.get("/api/v1/backups", params=params)
        response.raise_for_status()
        return response.json()

    async def get_backup(self, backup_id: str) -> dict:
        """
        Récupère les détails d'une sauvegarde.

        Endpoint: GET /api/v1/backups/{backup_id}
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/backups/{backup_id}")
        response.raise_for_status()
        return response.json()

    async def download_backup(self, backup_id: str) -> bytes:
        """
        Télécharge une sauvegarde.

        Endpoint: GET /api/v1/backups/{backup_id}/download
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/backups/{backup_id}/download")
        response.raise_for_status()
        return response.content

    async def verify_backup(self, backup_id: str) -> dict:
        """
        Vérifie l'intégrité d'une sauvegarde.

        Endpoint: GET /api/v1/backups/{backup_id}/verify
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/backups/{backup_id}/verify")
        response.raise_for_status()
        return response.json()

    async def restore_backup(
        self,
        backup_id: str,
        target: Optional[str] = None
    ) -> dict:
        """
        Restaure une sauvegarde.

        Endpoint: POST /api/v1/backups/{backup_id}/restore

        Args:
            backup_id: ID de la sauvegarde
            target: Cible de restauration (optionnel)

        Returns:
            dict avec restore_id, status
        """
        client = await self._get_client()

        payload = {}
        if target:
            payload["target"] = target

        response = await client.post(
            f"/api/v1/backups/{backup_id}/restore",
            json=payload
        )
        response.raise_for_status()

        result = response.json()
        logger.info(f"Restauration lancée: {result.get('restore_id')}")
        return result

    async def get_backup_stats(self) -> dict:
        """
        Récupère les statistiques de backup.

        Endpoint: GET /api/v1/backups/stats
        """
        client = await self._get_client()
        response = await client.get("/api/v1/backups/stats")
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # HEALTH
    # =========================================================================

    async def health_check(self) -> dict:
        """
        Vérifie la disponibilité d'AZALCOFFRE.

        Endpoint: GET /health
        """
        client = await self._get_client()
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()
