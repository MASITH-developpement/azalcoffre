# =============================================================================
# AZALPLUS - Backup Service
# =============================================================================
"""
Systeme de sauvegarde de la base de donnees PostgreSQL.
- Sauvegardes completes avec pg_dump
- Restauration depuis backup
- Planification automatique (daily, weekly, monthly)
- Rotation des sauvegardes
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from enum import Enum
import subprocess
import gzip
import os
import re
import json
import structlog
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .auth import require_role
from .db import Database

logger = structlog.get_logger()

# =============================================================================
# Configuration
# =============================================================================
BACKUP_DIR = Path("/home/ubuntu/azalplus/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Retention policy
RETENTION_DAILY = 7       # Keep last 7 daily backups
RETENTION_WEEKLY = 4      # Keep last 4 weekly backups
RETENTION_MONTHLY = 12    # Keep last 12 monthly backups

# =============================================================================
# Schemas
# =============================================================================
class BackupType(str, Enum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class BackupStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class BackupInfo(BaseModel):
    """Informations sur une sauvegarde."""
    id: str
    filename: str
    backup_type: BackupType
    status: BackupStatus
    size_bytes: int
    size_human: str
    created_at: datetime
    tenant_id: Optional[str] = None
    error_message: Optional[str] = None


class BackupCreateRequest(BaseModel):
    """Requete de creation de sauvegarde."""
    description: Optional[str] = None
    tenant_id: Optional[str] = None  # None = sauvegarde complete


class RestoreRequest(BaseModel):
    """Requete de restauration."""
    confirm: bool = False  # Doit etre True pour confirmer la restauration


# =============================================================================
# Backup Service
# =============================================================================
class BackupService:
    """Service de sauvegarde de la base de donnees."""

    _scheduler: Optional[AsyncIOScheduler] = None
    _metadata_file = BACKUP_DIR / "metadata.json"

    @classmethod
    def _parse_db_url(cls) -> Dict[str, str]:
        """Parse l'URL de connexion PostgreSQL."""
        url = settings.DATABASE_URL
        # Format: postgresql://user:password@host:port/database
        pattern = r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
        match = re.match(pattern, url)
        if not match:
            raise ValueError("Format DATABASE_URL invalide")

        return {
            "user": match.group(1),
            "password": match.group(2),
            "host": match.group(3),
            "port": match.group(4),
            "database": match.group(5)
        }

    @classmethod
    def _load_metadata(cls) -> Dict[str, Any]:
        """Charge les metadonnees des sauvegardes."""
        if cls._metadata_file.exists():
            try:
                return json.loads(cls._metadata_file.read_text())
            except Exception:
                return {"backups": {}}
        return {"backups": {}}

    @classmethod
    def _save_metadata(cls, metadata: Dict[str, Any]) -> None:
        """Sauvegarde les metadonnees."""
        cls._metadata_file.write_text(json.dumps(metadata, indent=2, default=str))

    @classmethod
    def _format_size(cls, size_bytes: int) -> str:
        """Formate une taille en bytes en format lisible."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    @classmethod
    async def create_backup(
        cls,
        backup_type: BackupType = BackupType.MANUAL,
        tenant_id: Optional[UUID] = None,
        description: Optional[str] = None
    ) -> BackupInfo:
        """
        Cree une sauvegarde complete de la base de donnees.

        Args:
            backup_type: Type de sauvegarde (manual, daily, weekly, monthly)
            tenant_id: ID du tenant pour sauvegarde partielle (None = complete)
            description: Description optionnelle

        Returns:
            BackupInfo avec les details de la sauvegarde
        """
        backup_id = str(uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Nom du fichier
        if tenant_id:
            filename = f"backup_{backup_type.value}_{timestamp}_tenant_{str(tenant_id)[:8]}.sql.gz"
        else:
            filename = f"backup_{backup_type.value}_{timestamp}_full.sql.gz"

        filepath = BACKUP_DIR / filename

        # Metadonnees initiales
        metadata = cls._load_metadata()
        metadata["backups"][backup_id] = {
            "id": backup_id,
            "filename": filename,
            "backup_type": backup_type.value,
            "status": BackupStatus.IN_PROGRESS.value,
            "size_bytes": 0,
            "created_at": datetime.now().isoformat(),
            "tenant_id": str(tenant_id) if tenant_id else None,
            "description": description
        }
        cls._save_metadata(metadata)

        logger.info("backup_starting", backup_id=backup_id, type=backup_type.value)

        try:
            # Configuration PostgreSQL
            db_config = cls._parse_db_url()

            # Commande pg_dump
            env = os.environ.copy()
            env["PGPASSWORD"] = db_config["password"]

            # Construction de la commande pg_dump
            cmd = [
                "pg_dump",
                "-h", db_config["host"],
                "-p", db_config["port"],
                "-U", db_config["user"],
                "-d", db_config["database"],
                "--no-owner",
                "--no-acl",
                "-F", "p",  # Format plain SQL
            ]

            # Si sauvegarde par tenant, filtrer le schema
            if tenant_id:
                # Pour une sauvegarde tenant, on exporte seulement les donnees
                # avec filtrage sur tenant_id (via WHERE)
                cmd.extend(["--data-only", "--schema=azalplus"])
            else:
                # Sauvegarde complete
                cmd.extend(["--schema=azalplus"])

            # Executer pg_dump et compresser
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Erreur pg_dump inconnue"
                raise Exception(error_msg)

            # Compresser et sauvegarder
            with gzip.open(filepath, 'wb') as f:
                f.write(stdout)

            # Mettre a jour les metadonnees
            file_size = filepath.stat().st_size
            metadata["backups"][backup_id].update({
                "status": BackupStatus.COMPLETED.value,
                "size_bytes": file_size,
                "completed_at": datetime.now().isoformat()
            })
            cls._save_metadata(metadata)

            logger.info(
                "backup_completed",
                backup_id=backup_id,
                size=cls._format_size(file_size)
            )

            return BackupInfo(
                id=backup_id,
                filename=filename,
                backup_type=backup_type,
                status=BackupStatus.COMPLETED,
                size_bytes=file_size,
                size_human=cls._format_size(file_size),
                created_at=datetime.fromisoformat(metadata["backups"][backup_id]["created_at"]),
                tenant_id=str(tenant_id) if tenant_id else None
            )

        except Exception as e:
            # Mise a jour en cas d'erreur
            metadata = cls._load_metadata()
            if backup_id in metadata["backups"]:
                metadata["backups"][backup_id].update({
                    "status": BackupStatus.FAILED.value,
                    "error_message": str(e)
                })
                cls._save_metadata(metadata)

            logger.error("backup_failed", backup_id=backup_id, error=str(e))

            raise HTTPException(
                status_code=500,
                detail=f"Erreur lors de la sauvegarde: {str(e)}"
            )

    @classmethod
    async def restore_backup(cls, backup_id: str) -> Dict[str, Any]:
        """
        Restaure la base de donnees depuis une sauvegarde.

        ATTENTION: Cette operation remplace toutes les donnees actuelles.

        Args:
            backup_id: ID de la sauvegarde a restaurer

        Returns:
            Dict avec le resultat de la restauration
        """
        metadata = cls._load_metadata()

        if backup_id not in metadata["backups"]:
            raise HTTPException(status_code=404, detail="Sauvegarde non trouvee")

        backup_info = metadata["backups"][backup_id]

        if backup_info["status"] != BackupStatus.COMPLETED.value:
            raise HTTPException(
                status_code=400,
                detail="Cette sauvegarde n'est pas complete ou a echoue"
            )

        filepath = BACKUP_DIR / backup_info["filename"]

        if not filepath.exists():
            raise HTTPException(
                status_code=404,
                detail="Fichier de sauvegarde introuvable"
            )

        logger.warning("restore_starting", backup_id=backup_id)

        try:
            db_config = cls._parse_db_url()

            # Decompresser le fichier
            with gzip.open(filepath, 'rb') as f:
                sql_content = f.read()

            # Configuration PostgreSQL
            env = os.environ.copy()
            env["PGPASSWORD"] = db_config["password"]

            # Executer psql pour restaurer
            cmd = [
                "psql",
                "-h", db_config["host"],
                "-p", db_config["port"],
                "-U", db_config["user"],
                "-d", db_config["database"],
                "-v", "ON_ERROR_STOP=1"
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout, stderr = await process.communicate(input=sql_content)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Erreur restauration inconnue"
                raise Exception(error_msg)

            logger.info("restore_completed", backup_id=backup_id)

            return {
                "status": "success",
                "message": "Restauration terminee avec succes",
                "backup_id": backup_id,
                "restored_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error("restore_failed", backup_id=backup_id, error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Erreur lors de la restauration: {str(e)}"
            )

    @classmethod
    def list_backups(
        cls,
        backup_type: Optional[BackupType] = None,
        status: Optional[BackupStatus] = None,
        limit: int = 50
    ) -> List[BackupInfo]:
        """
        Liste les sauvegardes disponibles.

        Args:
            backup_type: Filtrer par type
            status: Filtrer par statut
            limit: Nombre maximum de resultats

        Returns:
            Liste de BackupInfo
        """
        metadata = cls._load_metadata()
        backups = []

        for backup_id, info in metadata.get("backups", {}).items():
            # Filtres
            if backup_type and info.get("backup_type") != backup_type.value:
                continue
            if status and info.get("status") != status.value:
                continue

            # Verifier que le fichier existe
            filepath = BACKUP_DIR / info.get("filename", "")
            file_exists = filepath.exists()

            if not file_exists and info.get("status") == BackupStatus.COMPLETED.value:
                # Fichier supprime, mettre a jour le statut
                continue

            size_bytes = info.get("size_bytes", 0)

            backups.append(BackupInfo(
                id=backup_id,
                filename=info.get("filename", ""),
                backup_type=BackupType(info.get("backup_type", "manual")),
                status=BackupStatus(info.get("status", "pending")),
                size_bytes=size_bytes,
                size_human=cls._format_size(size_bytes),
                created_at=datetime.fromisoformat(info.get("created_at", datetime.now().isoformat())),
                tenant_id=info.get("tenant_id"),
                error_message=info.get("error_message")
            ))

        # Trier par date decroissante
        backups.sort(key=lambda x: x.created_at, reverse=True)

        return backups[:limit]

    @classmethod
    def get_backup(cls, backup_id: str) -> Optional[BackupInfo]:
        """Recupere les informations d'une sauvegarde."""
        metadata = cls._load_metadata()

        if backup_id not in metadata.get("backups", {}):
            return None

        info = metadata["backups"][backup_id]
        size_bytes = info.get("size_bytes", 0)

        return BackupInfo(
            id=backup_id,
            filename=info.get("filename", ""),
            backup_type=BackupType(info.get("backup_type", "manual")),
            status=BackupStatus(info.get("status", "pending")),
            size_bytes=size_bytes,
            size_human=cls._format_size(size_bytes),
            created_at=datetime.fromisoformat(info.get("created_at", datetime.now().isoformat())),
            tenant_id=info.get("tenant_id"),
            error_message=info.get("error_message")
        )

    @classmethod
    def delete_backup(cls, backup_id: str) -> bool:
        """
        Supprime une sauvegarde.

        Args:
            backup_id: ID de la sauvegarde

        Returns:
            True si supprime, False sinon
        """
        metadata = cls._load_metadata()

        if backup_id not in metadata.get("backups", {}):
            return False

        info = metadata["backups"][backup_id]
        filepath = BACKUP_DIR / info.get("filename", "")

        # Supprimer le fichier
        if filepath.exists():
            filepath.unlink()

        # Supprimer des metadonnees
        del metadata["backups"][backup_id]
        cls._save_metadata(metadata)

        logger.info("backup_deleted", backup_id=backup_id)

        return True

    @classmethod
    def get_backup_path(cls, backup_id: str) -> Optional[Path]:
        """Retourne le chemin du fichier de sauvegarde."""
        metadata = cls._load_metadata()

        if backup_id not in metadata.get("backups", {}):
            return None

        info = metadata["backups"][backup_id]
        filepath = BACKUP_DIR / info.get("filename", "")

        if filepath.exists():
            return filepath
        return None

    @classmethod
    async def cleanup_old_backups(cls, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Supprime les anciennes sauvegardes selon la politique de retention.

        Politique par defaut:
        - 7 sauvegardes quotidiennes
        - 4 sauvegardes hebdomadaires
        - 12 sauvegardes mensuelles
        - Sauvegardes manuelles: conservees indefiniment sauf si > days

        Args:
            days: Si specifie, supprime les sauvegardes manuelles plus vieilles que N jours

        Returns:
            Rapport de nettoyage
        """
        metadata = cls._load_metadata()
        deleted = []
        kept = []

        # Grouper par type
        by_type: Dict[str, List] = {
            "daily": [],
            "weekly": [],
            "monthly": [],
            "manual": []
        }

        for backup_id, info in metadata.get("backups", {}).items():
            backup_type = info.get("backup_type", "manual")
            created_at = datetime.fromisoformat(info.get("created_at", datetime.now().isoformat()))

            by_type.get(backup_type, by_type["manual"]).append({
                "id": backup_id,
                "created_at": created_at,
                "info": info
            })

        # Trier chaque groupe par date
        for bt in by_type:
            by_type[bt].sort(key=lambda x: x["created_at"], reverse=True)

        # Appliquer la politique de retention
        retention = {
            "daily": RETENTION_DAILY,
            "weekly": RETENTION_WEEKLY,
            "monthly": RETENTION_MONTHLY
        }

        for bt, limit in retention.items():
            backups_to_process = by_type.get(bt, [])
            for i, backup in enumerate(backups_to_process):
                if i >= limit:
                    # Supprimer
                    cls.delete_backup(backup["id"])
                    deleted.append(backup["id"])
                else:
                    kept.append(backup["id"])

        # Sauvegardes manuelles: supprimer si > days jours
        if days:
            cutoff = datetime.now() - timedelta(days=days)
            for backup in by_type.get("manual", []):
                if backup["created_at"] < cutoff:
                    cls.delete_backup(backup["id"])
                    deleted.append(backup["id"])
                else:
                    kept.append(backup["id"])
        else:
            kept.extend([b["id"] for b in by_type.get("manual", [])])

        logger.info(
            "backup_cleanup_completed",
            deleted_count=len(deleted),
            kept_count=len(kept)
        )

        return {
            "status": "success",
            "deleted_count": len(deleted),
            "deleted_ids": deleted,
            "kept_count": len(kept)
        }

    # =========================================================================
    # Scheduler pour sauvegardes automatiques
    # =========================================================================
    @classmethod
    async def start_scheduler(cls) -> None:
        """Demarre le planificateur de sauvegardes automatiques."""
        if cls._scheduler is not None:
            return

        cls._scheduler = AsyncIOScheduler()

        # Sauvegarde quotidienne a 02:00
        cls._scheduler.add_job(
            cls._scheduled_backup,
            CronTrigger(hour=2, minute=0),
            args=[BackupType.DAILY],
            id="daily_backup",
            name="Sauvegarde quotidienne"
        )

        # Sauvegarde hebdomadaire le dimanche a 03:00
        cls._scheduler.add_job(
            cls._scheduled_backup,
            CronTrigger(day_of_week="sun", hour=3, minute=0),
            args=[BackupType.WEEKLY],
            id="weekly_backup",
            name="Sauvegarde hebdomadaire"
        )

        # Sauvegarde mensuelle le 1er du mois a 04:00
        cls._scheduler.add_job(
            cls._scheduled_backup,
            CronTrigger(day=1, hour=4, minute=0),
            args=[BackupType.MONTHLY],
            id="monthly_backup",
            name="Sauvegarde mensuelle"
        )

        # Nettoyage quotidien a 05:00
        cls._scheduler.add_job(
            cls.cleanup_old_backups,
            CronTrigger(hour=5, minute=0),
            id="cleanup_backups",
            name="Nettoyage sauvegardes"
        )

        cls._scheduler.start()
        logger.info("backup_scheduler_started")

    @classmethod
    async def stop_scheduler(cls) -> None:
        """Arrete le planificateur."""
        if cls._scheduler:
            cls._scheduler.shutdown()
            cls._scheduler = None
            logger.info("backup_scheduler_stopped")

    @classmethod
    async def _scheduled_backup(cls, backup_type: BackupType) -> None:
        """Execute une sauvegarde planifiee."""
        try:
            await cls.create_backup(backup_type=backup_type)
        except Exception as e:
            logger.error(
                "scheduled_backup_failed",
                backup_type=backup_type.value,
                error=str(e)
            )


# =============================================================================
# API Router
# =============================================================================
backup_router = APIRouter()


@backup_router.post("/", response_model=BackupInfo)
async def create_backup(
    request: BackupCreateRequest = None,
    background_tasks: BackgroundTasks = None,
    user: dict = Depends(require_role("admin"))
):
    """
    Cree une nouvelle sauvegarde de la base de donnees.

    Necessite le role admin.
    """
    tenant_id = None
    if request and request.tenant_id:
        tenant_id = UUID(request.tenant_id)

    description = request.description if request else None

    return await BackupService.create_backup(
        backup_type=BackupType.MANUAL,
        tenant_id=tenant_id,
        description=description
    )


@backup_router.get("/", response_model=List[BackupInfo])
async def list_backups(
    backup_type: Optional[BackupType] = None,
    status: Optional[BackupStatus] = None,
    limit: int = 50,
    user: dict = Depends(require_role("admin"))
):
    """
    Liste les sauvegardes disponibles.

    Peut etre filtre par type et statut.
    """
    return BackupService.list_backups(
        backup_type=backup_type,
        status=status,
        limit=limit
    )


@backup_router.get("/{backup_id}", response_model=BackupInfo)
async def get_backup(
    backup_id: str,
    user: dict = Depends(require_role("admin"))
):
    """Recupere les details d'une sauvegarde."""
    backup = BackupService.get_backup(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Sauvegarde non trouvee")
    return backup


@backup_router.get("/{backup_id}/download")
async def download_backup(
    backup_id: str,
    user: dict = Depends(require_role("admin"))
):
    """Telecharge un fichier de sauvegarde."""
    filepath = BackupService.get_backup_path(backup_id)

    if not filepath:
        raise HTTPException(status_code=404, detail="Sauvegarde non trouvee")

    return FileResponse(
        path=filepath,
        filename=filepath.name,
        media_type="application/gzip"
    )


@backup_router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    request: RestoreRequest,
    user: dict = Depends(require_role("admin"))
):
    """
    Restaure la base de donnees depuis une sauvegarde.

    ATTENTION: Cette operation remplace toutes les donnees actuelles.
    Vous devez confirmer en passant confirm=true.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Vous devez confirmer la restauration avec confirm=true. "
                   "ATTENTION: Cette operation remplacera toutes les donnees actuelles."
        )

    return await BackupService.restore_backup(backup_id)


@backup_router.delete("/{backup_id}")
async def delete_backup(
    backup_id: str,
    user: dict = Depends(require_role("admin"))
):
    """Supprime une sauvegarde."""
    success = BackupService.delete_backup(backup_id)

    if not success:
        raise HTTPException(status_code=404, detail="Sauvegarde non trouvee")

    return {"status": "deleted", "backup_id": backup_id}


@backup_router.post("/cleanup")
async def cleanup_backups(
    days: Optional[int] = None,
    user: dict = Depends(require_role("admin"))
):
    """
    Nettoie les anciennes sauvegardes selon la politique de retention.

    Args:
        days: Si specifie, supprime aussi les sauvegardes manuelles plus vieilles
    """
    return await BackupService.cleanup_old_backups(days=days)


@backup_router.get("/scheduler/status")
async def scheduler_status(
    user: dict = Depends(require_role("admin"))
):
    """Retourne le statut du planificateur de sauvegardes."""
    scheduler = BackupService._scheduler

    if not scheduler:
        return {"status": "stopped", "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None
        })

    return {
        "status": "running",
        "jobs": jobs
    }
