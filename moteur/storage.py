# =============================================================================
# AZALPLUS - Storage Service
# =============================================================================
"""
Service de stockage de fichiers avec isolation multi-tenant.
Gère l'upload, la récupération et la suppression de fichiers attachés.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
import structlog
import aiofiles
import os
import mimetypes

from .db import Database
from .tenant import get_current_tenant, get_current_user_id
from .auth import require_auth

logger = structlog.get_logger()

# =============================================================================
# Configuration
# =============================================================================
UPLOAD_DIR = Path("/home/ubuntu/azalplus/uploads")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".rtf", ".odt", ".ods", ".odp",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
    # Archives
    ".zip", ".rar", ".7z", ".tar", ".gz",
    # Autres
    ".xml", ".json", ".html", ".css", ".js"
}

# =============================================================================
# Storage Service
# =============================================================================
class StorageService:
    """Service de gestion des fichiers attachés."""

    @classmethod
    async def upload_file(
        cls,
        file: UploadFile,
        module: str,
        record_id: UUID,
        tenant_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Upload un fichier et crée l'enregistrement document.

        Args:
            file: Fichier uploadé
            module: Nom du module auquel le fichier est attaché
            record_id: ID de l'enregistrement auquel le fichier est attaché
            tenant_id: ID du tenant (isolation obligatoire)
            user_id: ID de l'utilisateur qui upload

        Returns:
            Dictionnaire avec les informations du document créé

        Raises:
            HTTPException: Si le fichier est invalide ou trop gros
        """
        # Vérifier que l'enregistrement cible existe et appartient au tenant
        target_record = Database.get_by_id(module, tenant_id, record_id)
        if not target_record:
            raise HTTPException(
                status_code=404,
                detail=f"Enregistrement {record_id} non trouvé dans {module}"
            )

        # Vérifier l'extension
        filename = file.filename or "fichier"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Extension {ext} non autorisée"
            )

        # Lire le contenu pour vérifier la taille
        content = await file.read()
        file_size = len(content)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Fichier trop gros ({file_size / 1024 / 1024:.1f} MB). Maximum: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
            )

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Le fichier est vide"
            )

        # Générer un nom de fichier unique
        document_id = uuid4()
        safe_filename = f"{document_id}{ext}"

        # Créer le répertoire tenant si nécessaire
        tenant_dir = UPLOAD_DIR / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)

        # Chemin complet du fichier
        file_path = tenant_dir / safe_filename

        # Écrire le fichier
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # Déterminer le type MIME
        mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Créer l'enregistrement en base
        document_data = {
            "id": str(document_id),
            "tenant_id": str(tenant_id),
            "nom": filename,
            "type_mime": mime_type,
            "taille": file_size,
            "chemin": str(file_path),
            "module": module,
            "record_id": str(record_id),
            "uploaded_by": str(user_id),
            "uploaded_at": datetime.utcnow().isoformat()
        }

        with Database.get_session() as session:
            from sqlalchemy import text

            columns = ", ".join(document_data.keys())
            placeholders = ", ".join(f":{k}" for k in document_data.keys())

            session.execute(
                text(f"""
                    INSERT INTO azalplus.document ({columns})
                    VALUES ({placeholders})
                """),
                document_data
            )
            session.commit()

        logger.info(
            "file_uploaded",
            document_id=str(document_id),
            filename=filename,
            module=module,
            record_id=str(record_id),
            size=file_size,
            tenant_id=str(tenant_id)
        )

        return {
            "id": str(document_id),
            "nom": filename,
            "type_mime": mime_type,
            "taille": file_size,
            "module": module,
            "record_id": str(record_id),
            "uploaded_at": document_data["uploaded_at"]
        }

    @classmethod
    def get_file(
        cls,
        document_id: UUID,
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """
        Récupère les informations d'un fichier.

        Args:
            document_id: ID du document
            tenant_id: ID du tenant (isolation obligatoire)

        Returns:
            Dictionnaire avec path et metadata du fichier

        Raises:
            HTTPException: Si le fichier n'existe pas
        """
        document = Database.get_by_id("document", tenant_id, document_id)

        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document non trouvé"
            )

        file_path = Path(document["chemin"])

        if not file_path.exists():
            logger.error(
                "file_not_found_on_disk",
                document_id=str(document_id),
                path=str(file_path)
            )
            raise HTTPException(
                status_code=404,
                detail="Fichier introuvable sur le disque"
            )

        return {
            "path": file_path,
            "filename": document["nom"],
            "mime_type": document["type_mime"],
            "size": document["taille"]
        }

    @classmethod
    async def delete_file(
        cls,
        document_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """
        Supprime un fichier (soft delete en base + suppression physique).

        Args:
            document_id: ID du document
            tenant_id: ID du tenant (isolation obligatoire)

        Returns:
            True si supprimé avec succès

        Raises:
            HTTPException: Si le fichier n'existe pas
        """
        document = Database.get_by_id("document", tenant_id, document_id)

        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document non trouvé"
            )

        # Supprimer le fichier physique
        file_path = Path(document["chemin"])
        if file_path.exists():
            try:
                os.remove(file_path)
                logger.info(
                    "file_deleted_from_disk",
                    document_id=str(document_id),
                    path=str(file_path)
                )
            except OSError as e:
                logger.error(
                    "file_delete_error",
                    document_id=str(document_id),
                    error=str(e)
                )

        # Soft delete en base
        success = Database.soft_delete("document", tenant_id, document_id)

        logger.info(
            "document_deleted",
            document_id=str(document_id),
            tenant_id=str(tenant_id)
        )

        return success

    @classmethod
    def list_documents(
        cls,
        module: str,
        record_id: UUID,
        tenant_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Liste les documents attachés à un enregistrement.

        Args:
            module: Nom du module
            record_id: ID de l'enregistrement
            tenant_id: ID du tenant (isolation obligatoire)

        Returns:
            Liste des documents
        """
        documents = Database.query(
            "document",
            tenant_id,
            filters={
                "module": module,
                "record_id": str(record_id)
            },
            order_by="uploaded_at DESC"
        )

        # Formater les résultats
        result = []
        for doc in documents:
            result.append({
                "id": str(doc["id"]),
                "nom": doc["nom"],
                "type_mime": doc["type_mime"],
                "taille": doc["taille"],
                "uploaded_at": doc.get("uploaded_at"),
                "uploaded_by": str(doc["uploaded_by"]) if doc.get("uploaded_by") else None
            })

        return result


# =============================================================================
# API Router pour les documents
# =============================================================================
storage_router = APIRouter()


@storage_router.post("/{module}/{record_id}/documents", tags=["Documents"])
async def upload_document(
    module: str,
    record_id: UUID,
    file: UploadFile = File(...),
    tenant_id: UUID = Depends(get_current_tenant),
    user_id: UUID = Depends(get_current_user_id),
    user: dict = Depends(require_auth)
):
    """
    Upload un fichier attaché à un enregistrement.

    - **module**: Nom du module (ex: Client, Devis, Facture)
    - **record_id**: ID de l'enregistrement
    - **file**: Fichier à uploader
    """
    return await StorageService.upload_file(
        file=file,
        module=module,
        record_id=record_id,
        tenant_id=tenant_id,
        user_id=user_id
    )


@storage_router.get("/{module}/{record_id}/documents", tags=["Documents"])
async def list_documents(
    module: str,
    record_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Liste les documents attachés à un enregistrement.

    - **module**: Nom du module
    - **record_id**: ID de l'enregistrement
    """
    documents = StorageService.list_documents(
        module=module,
        record_id=record_id,
        tenant_id=tenant_id
    )
    return {"documents": documents, "total": len(documents)}


@storage_router.get("/documents/{document_id}", tags=["Documents"])
async def get_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Récupère les métadonnées d'un document.
    """
    file_info = StorageService.get_file(document_id, tenant_id)
    return {
        "id": str(document_id),
        "nom": file_info["filename"],
        "type_mime": file_info["mime_type"],
        "taille": file_info["size"]
    }


@storage_router.get("/documents/{document_id}/download", tags=["Documents"])
async def download_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Télécharge un document.
    """
    file_info = StorageService.get_file(document_id, tenant_id)

    return FileResponse(
        path=file_info["path"],
        filename=file_info["filename"],
        media_type=file_info["mime_type"]
    )


@storage_router.delete("/documents/{document_id}", tags=["Documents"])
async def delete_document(
    document_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant),
    user: dict = Depends(require_auth)
):
    """
    Supprime un document.
    """
    success = await StorageService.delete_file(document_id, tenant_id)
    if success:
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Document non trouvé")
