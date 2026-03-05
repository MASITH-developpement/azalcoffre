# =============================================================================
# AZALPLUS - VideoConf Recording Service
# =============================================================================
"""
Service de gestion des enregistrements de reunions.

Fonctionnalites:
- Demarrer/arreter l'enregistrement
- Gestion du stockage (local, S3, MinIO)
- Generation d'URLs signees
- Integration LiveKit Egress API
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from enum import Enum
import os

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger()


class RecordingStatus(str, Enum):
    """Statuts d'enregistrement."""
    STARTING = "starting"
    RECORDING = "recording"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    PROCESSING = "processing"


class RecordingType(str, Enum):
    """Types d'enregistrement."""
    COMPOSITE = "composite"      # Vue composite (tous les participants)
    TRACK = "track"              # Pistes individuelles
    AUDIO_ONLY = "audio_only"    # Audio seul


class RecordingService:
    """Service de gestion des enregistrements."""

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service d'enregistrement.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant (isolation obligatoire)
        """
        self.db = db
        self.tenant_id = tenant_id
        self._config: Optional[dict] = None

    # =========================================================================
    # Configuration
    # =========================================================================
    def _get_config(self) -> dict:
        """Charge la configuration d'enregistrement."""
        if self._config is None:
            # Configuration par defaut (depuis videoconf.yml)
            self._config = {
                "storage_backend": os.environ.get("RECORDING_STORAGE", "local"),
                "local_path": "/home/ubuntu/azalplus/uploads/recordings",
                "s3_endpoint": os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
                "s3_access_key": os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
                "s3_secret_key": os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
                "s3_bucket": os.environ.get("RECORDINGS_BUCKET", "azalplus-recordings"),
                "s3_region": os.environ.get("MINIO_REGION", "us-east-1"),
                "s3_use_ssl": False,
                "retention_days": 90,
                "max_recording_size_gb": 5,
                "video_codec": "vp8",
                "video_width": 1920,
                "video_height": 1080,
                "video_framerate": 30,
                "video_bitrate": 3000000,
                "audio_sample_rate": 48000,
                "audio_channels": 2,
                "audio_bitrate": 128000,
                "livekit_api_key": os.environ.get("LIVEKIT_API_KEY", "devkey"),
                "livekit_api_secret": os.environ.get("LIVEKIT_API_SECRET", "secret"),
                "livekit_api_url": os.environ.get("LIVEKIT_API_URL", "http://localhost:7880"),
            }
        return self._config

    # =========================================================================
    # Helpers
    # =========================================================================
    def _verify_meeting_access(self, meeting_id: UUID) -> Optional[dict]:
        """Verifie que la reunion appartient au tenant et retourne ses infos."""
        query = text("""
            SELECT id, titre, livekit_room_name, statut
            FROM azalplus.reunions
            WHERE id = :meeting_id
            AND tenant_id = :tenant_id
            AND deleted_at IS NULL
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _generate_file_path(
        self,
        meeting_id: UUID,
        recording_type: RecordingType
    ) -> str:
        """Genere le chemin du fichier d'enregistrement."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        extension = "webm" if recording_type != RecordingType.AUDIO_ONLY else "ogg"
        return f"{self.tenant_id}/{meeting_id}/{timestamp}_{recording_type.value}.{extension}"

    async def _start_livekit_egress(
        self,
        room_name: str,
        recording_id: UUID,
        recording_type: RecordingType,
        file_path: str
    ) -> Optional[str]:
        """
        Demarre l'enregistrement via LiveKit Egress API.

        Returns:
            Egress ID si reussi, None sinon
        """
        config = self._get_config()

        try:
            # Import LiveKit SDK
            from livekit.api import LiveKitAPI
            from livekit.api.egress_service import (
                RoomCompositeEgressRequest,
                TrackEgressRequest,
                EncodedFileOutput,
                S3Upload,
                DirectFileOutput,
            )

            api = LiveKitAPI(
                url=config["livekit_api_url"],
                api_key=config["livekit_api_key"],
                api_secret=config["livekit_api_secret"]
            )

            # Configuration de sortie
            if config["storage_backend"] in ["s3", "minio"]:
                output = EncodedFileOutput(
                    file_type="webm" if recording_type != RecordingType.AUDIO_ONLY else "ogg",
                    filepath=file_path,
                    s3=S3Upload(
                        access_key=config["s3_access_key"],
                        secret=config["s3_secret_key"],
                        region=config["s3_region"],
                        endpoint=config["s3_endpoint"],
                        bucket=config["s3_bucket"],
                        force_path_style=True
                    )
                )
            else:
                output = DirectFileOutput(
                    filepath=os.path.join(config["local_path"], file_path)
                )

            # Demarrer l'egress selon le type
            if recording_type == RecordingType.COMPOSITE:
                request = RoomCompositeEgressRequest(
                    room_name=room_name,
                    file=output,
                    video_only=False,
                    audio_only=False
                )
                egress_info = await api.egress.start_room_composite_egress(request)

            elif recording_type == RecordingType.AUDIO_ONLY:
                request = RoomCompositeEgressRequest(
                    room_name=room_name,
                    file=output,
                    audio_only=True
                )
                egress_info = await api.egress.start_room_composite_egress(request)

            else:
                # Track egress - pour chaque participant
                # Simplifie: utiliser composite
                request = RoomCompositeEgressRequest(
                    room_name=room_name,
                    file=output
                )
                egress_info = await api.egress.start_room_composite_egress(request)

            return egress_info.egress_id

        except ImportError:
            logger.warning("livekit_sdk_not_available")
            return None
        except Exception as e:
            logger.error("livekit_egress_start_error", error=str(e))
            return None

    async def _stop_livekit_egress(self, egress_id: str) -> bool:
        """Arrete l'enregistrement LiveKit."""
        config = self._get_config()

        try:
            from livekit.api import LiveKitAPI

            api = LiveKitAPI(
                url=config["livekit_api_url"],
                api_key=config["livekit_api_key"],
                api_secret=config["livekit_api_secret"]
            )

            await api.egress.stop_egress(egress_id)
            return True

        except ImportError:
            logger.warning("livekit_sdk_not_available")
            return True
        except Exception as e:
            logger.error("livekit_egress_stop_error", error=str(e))
            return False

    # =========================================================================
    # Start / Stop Recording
    # =========================================================================
    async def start_recording(
        self,
        meeting_id: UUID,
        recording_type: RecordingType = RecordingType.COMPOSITE,
        started_by: Optional[UUID] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Demarre l'enregistrement d'une reunion.

        Args:
            meeting_id: ID de la reunion
            recording_type: Type d'enregistrement
            started_by: ID de l'utilisateur qui demarre
            options: Options additionnelles (qualite, etc.)

        Returns:
            Informations sur l'enregistrement demarre

        Raises:
            ValueError: Si reunion non trouvee ou deja en enregistrement
        """
        # Verification tenant et reunion
        meeting = self._verify_meeting_access(meeting_id)
        if not meeting:
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        if meeting.get("statut") not in ["en_cours", "active"]:
            raise ValueError("La reunion doit etre en cours pour enregistrer")

        # Verifier si un enregistrement est deja en cours
        active_query = text("""
            SELECT id FROM azalplus.reunion_recordings
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            AND status IN ('starting', 'recording')
        """)
        active_result = self.db.execute(active_query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        if active_result.fetchone():
            raise ValueError("Un enregistrement est deja en cours")

        # Generer les identifiants
        recording_id = uuid4()
        file_path = self._generate_file_path(meeting_id, recording_type)
        now = datetime.utcnow()

        # Inserer l'enregistrement en base
        import json
        insert_query = text("""
            INSERT INTO azalplus.reunion_recordings
            (id, tenant_id, reunion_id, recording_type, status, file_path,
             started_at, started_by, options, created_at)
            VALUES (:id, :tenant_id, :reunion_id, :recording_type, :status, :file_path,
                    :started_at, :started_by, :options, :created_at)
            RETURNING *
        """)

        result = self.db.execute(insert_query, {
            "id": str(recording_id),
            "tenant_id": str(self.tenant_id),
            "reunion_id": str(meeting_id),
            "recording_type": recording_type.value,
            "status": RecordingStatus.STARTING.value,
            "file_path": file_path,
            "started_at": now,
            "started_by": str(started_by) if started_by else None,
            "options": json.dumps(options) if options else None,
            "created_at": now
        })
        self.db.commit()

        row = result.fetchone()
        recording = dict(row._mapping) if row else None

        # Demarrer l'egress LiveKit
        room_name = meeting.get("livekit_room_name")
        egress_id = None

        if room_name:
            egress_id = await self._start_livekit_egress(
                room_name=room_name,
                recording_id=recording_id,
                recording_type=recording_type,
                file_path=file_path
            )

        # Mettre a jour le statut
        if egress_id:
            update_query = text("""
                UPDATE azalplus.reunion_recordings
                SET status = :status, egress_id = :egress_id
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            self.db.execute(update_query, {
                "id": str(recording_id),
                "tenant_id": str(self.tenant_id),
                "status": RecordingStatus.RECORDING.value,
                "egress_id": egress_id
            })
            self.db.commit()
            recording["status"] = RecordingStatus.RECORDING.value
            recording["egress_id"] = egress_id
        else:
            # Mode simulation sans LiveKit
            update_query = text("""
                UPDATE azalplus.reunion_recordings
                SET status = :status
                WHERE id = :id AND tenant_id = :tenant_id
            """)
            self.db.execute(update_query, {
                "id": str(recording_id),
                "tenant_id": str(self.tenant_id),
                "status": RecordingStatus.RECORDING.value
            })
            self.db.commit()
            recording["status"] = RecordingStatus.RECORDING.value

        logger.info(
            "recording_started",
            recording_id=str(recording_id),
            meeting_id=str(meeting_id),
            recording_type=recording_type.value,
            egress_id=egress_id
        )

        return recording

    async def stop_recording(
        self,
        meeting_id: UUID,
        recording_id: UUID,
        stopped_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Arrete l'enregistrement en cours.

        Args:
            meeting_id: ID de la reunion
            recording_id: ID de l'enregistrement
            stopped_by: ID de l'utilisateur qui arrete

        Returns:
            Enregistrement arrete

        Raises:
            ValueError: Si enregistrement non trouve ou deja arrete
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Recuperer l'enregistrement
        query = text("""
            SELECT * FROM azalplus.reunion_recordings
            WHERE id = :recording_id
            AND reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "recording_id": str(recording_id),
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            raise ValueError(f"Enregistrement {recording_id} non trouve")

        recording = dict(row._mapping)

        if recording["status"] not in [
            RecordingStatus.STARTING.value,
            RecordingStatus.RECORDING.value
        ]:
            raise ValueError("L'enregistrement n'est pas en cours")

        # Mettre a jour le statut
        now = datetime.utcnow()
        update_query = text("""
            UPDATE azalplus.reunion_recordings
            SET status = :status, stopped_at = :stopped_at, stopped_by = :stopped_by
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)
        update_result = self.db.execute(update_query, {
            "id": str(recording_id),
            "tenant_id": str(self.tenant_id),
            "status": RecordingStatus.STOPPING.value,
            "stopped_at": now,
            "stopped_by": str(stopped_by) if stopped_by else None
        })
        self.db.commit()

        # Arreter l'egress LiveKit
        egress_id = recording.get("egress_id")
        if egress_id:
            success = await self._stop_livekit_egress(egress_id)
            if not success:
                logger.warning(
                    "livekit_egress_stop_failed",
                    egress_id=egress_id,
                    recording_id=str(recording_id)
                )

        # Mettre a jour le statut final
        final_update = text("""
            UPDATE azalplus.reunion_recordings
            SET status = :status
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)
        final_result = self.db.execute(final_update, {
            "id": str(recording_id),
            "tenant_id": str(self.tenant_id),
            "status": RecordingStatus.PROCESSING.value
        })
        self.db.commit()

        updated_row = final_result.fetchone()
        updated_recording = dict(updated_row._mapping) if updated_row else recording

        logger.info(
            "recording_stopped",
            recording_id=str(recording_id),
            meeting_id=str(meeting_id),
            duration_seconds=(now - recording["started_at"]).total_seconds() if recording.get("started_at") else None
        )

        return updated_recording

    # =========================================================================
    # Status and List
    # =========================================================================
    async def get_recording_status(
        self,
        recording_id: UUID
    ) -> Dict[str, Any]:
        """
        Recupere le statut d'un enregistrement.

        Args:
            recording_id: ID de l'enregistrement

        Returns:
            Statut et informations de l'enregistrement
        """
        query = text("""
            SELECT r.*, m.titre as reunion_titre
            FROM azalplus.reunion_recordings r
            JOIN azalplus.reunions m ON r.reunion_id = m.id
            WHERE r.id = :recording_id
            AND r.tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "recording_id": str(recording_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            raise ValueError(f"Enregistrement {recording_id} non trouve")

        recording = dict(row._mapping)

        # Calculer la duree si en cours ou termine
        if recording["started_at"]:
            if recording["stopped_at"]:
                duration = (recording["stopped_at"] - recording["started_at"]).total_seconds()
            elif recording["status"] == RecordingStatus.RECORDING.value:
                duration = (datetime.utcnow() - recording["started_at"]).total_seconds()
            else:
                duration = None
            recording["duration_seconds"] = duration

        return recording

    async def list_recordings(
        self,
        meeting_id: UUID,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Liste les enregistrements d'une reunion.

        Args:
            meeting_id: ID de la reunion
            include_deleted: Inclure les enregistrements supprimes

        Returns:
            Liste des enregistrements
        """
        # Verification tenant
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        sql = """
            SELECT * FROM azalplus.reunion_recordings
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
        """
        params = {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        }

        if not include_deleted:
            sql += " AND deleted_at IS NULL"

        sql += " ORDER BY created_at DESC"

        result = self.db.execute(text(sql), params)
        recordings = [dict(row._mapping) for row in result]

        # Calculer les durees
        for rec in recordings:
            if rec["started_at"] and rec["stopped_at"]:
                rec["duration_seconds"] = (rec["stopped_at"] - rec["started_at"]).total_seconds()

        return recordings

    # =========================================================================
    # Download URL
    # =========================================================================
    async def get_download_url(
        self,
        recording_id: UUID,
        expires_in_hours: int = 24
    ) -> str:
        """
        Genere une URL signee pour telecharger l'enregistrement.

        Args:
            recording_id: ID de l'enregistrement
            expires_in_hours: Duree de validite de l'URL

        Returns:
            URL signee

        Raises:
            ValueError: Si enregistrement non trouve ou pas pret
        """
        # Recuperer l'enregistrement
        query = text("""
            SELECT * FROM azalplus.reunion_recordings
            WHERE id = :recording_id
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "recording_id": str(recording_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            raise ValueError(f"Enregistrement {recording_id} non trouve")

        recording = dict(row._mapping)

        if recording["status"] != RecordingStatus.COMPLETED.value:
            raise ValueError("L'enregistrement n'est pas encore disponible")

        if not recording.get("file_path"):
            raise ValueError("Fichier d'enregistrement non disponible")

        config = self._get_config()
        file_path = recording["file_path"]

        if config["storage_backend"] in ["s3", "minio"]:
            # Generer URL signee S3/MinIO
            try:
                import boto3
                from botocore.config import Config as BotoConfig

                s3_client = boto3.client(
                    "s3",
                    endpoint_url=f"http://{config['s3_endpoint']}",
                    aws_access_key_id=config["s3_access_key"],
                    aws_secret_access_key=config["s3_secret_key"],
                    region_name=config["s3_region"],
                    config=BotoConfig(signature_version="s3v4")
                )

                url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": config["s3_bucket"],
                        "Key": file_path
                    },
                    ExpiresIn=expires_in_hours * 3600
                )

                return url

            except ImportError:
                logger.warning("boto3_not_available")
                raise ValueError("Service de stockage non configure")

        else:
            # Stockage local - generer token d'acces
            import hashlib
            import time

            expiry = int(time.time()) + (expires_in_hours * 3600)
            token_data = f"{recording_id}:{self.tenant_id}:{expiry}:{config.get('secret', 'default')}"
            token = hashlib.sha256(token_data.encode()).hexdigest()[:32]

            return f"/api/videoconf/recordings/{recording_id}/download?token={token}&expires={expiry}"

    # =========================================================================
    # Delete Recording
    # =========================================================================
    async def delete_recording(
        self,
        recording_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """
        Supprime un enregistrement.

        Args:
            recording_id: ID de l'enregistrement
            deleted_by: ID de l'utilisateur qui supprime
            hard_delete: Supprimer aussi le fichier physique

        Returns:
            True si suppression reussie
        """
        # Recuperer l'enregistrement
        query = text("""
            SELECT * FROM azalplus.reunion_recordings
            WHERE id = :recording_id
            AND tenant_id = :tenant_id
        """)
        result = self.db.execute(query, {
            "recording_id": str(recording_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            raise ValueError(f"Enregistrement {recording_id} non trouve")

        recording = dict(row._mapping)

        # Verifier que l'enregistrement n'est pas en cours
        if recording["status"] in [
            RecordingStatus.STARTING.value,
            RecordingStatus.RECORDING.value
        ]:
            raise ValueError("Impossible de supprimer un enregistrement en cours")

        # Soft delete en base
        delete_query = text("""
            UPDATE azalplus.reunion_recordings
            SET deleted_at = :now, deleted_by = :deleted_by
            WHERE id = :id AND tenant_id = :tenant_id
        """)
        self.db.execute(delete_query, {
            "id": str(recording_id),
            "tenant_id": str(self.tenant_id),
            "now": datetime.utcnow(),
            "deleted_by": str(deleted_by) if deleted_by else None
        })
        self.db.commit()

        # Supprimer le fichier physique si demande
        if hard_delete and recording.get("file_path"):
            config = self._get_config()
            file_path = recording["file_path"]

            try:
                if config["storage_backend"] in ["s3", "minio"]:
                    import boto3
                    s3_client = boto3.client(
                        "s3",
                        endpoint_url=f"http://{config['s3_endpoint']}",
                        aws_access_key_id=config["s3_access_key"],
                        aws_secret_access_key=config["s3_secret_key"],
                        region_name=config["s3_region"]
                    )
                    s3_client.delete_object(
                        Bucket=config["s3_bucket"],
                        Key=file_path
                    )
                else:
                    full_path = os.path.join(config["local_path"], file_path)
                    if os.path.exists(full_path):
                        os.remove(full_path)

                logger.info(
                    "recording_file_deleted",
                    recording_id=str(recording_id),
                    file_path=file_path
                )

            except Exception as e:
                logger.error(
                    "recording_file_delete_error",
                    recording_id=str(recording_id),
                    error=str(e)
                )

        logger.info(
            "recording_deleted",
            recording_id=str(recording_id),
            hard_delete=hard_delete
        )

        return True

    # =========================================================================
    # Mark as completed (webhook callback)
    # =========================================================================
    async def mark_completed(
        self,
        recording_id: UUID,
        file_size: Optional[int] = None,
        duration_seconds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Marque un enregistrement comme termine (appele par webhook LiveKit).

        Args:
            recording_id: ID de l'enregistrement
            file_size: Taille du fichier en bytes
            duration_seconds: Duree en secondes

        Returns:
            Enregistrement mis a jour
        """
        query = text("""
            UPDATE azalplus.reunion_recordings
            SET status = :status,
                file_size = COALESCE(:file_size, file_size),
                duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                completed_at = :completed_at
            WHERE id = :id
            AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(query, {
            "id": str(recording_id),
            "tenant_id": str(self.tenant_id),
            "status": RecordingStatus.COMPLETED.value,
            "file_size": file_size,
            "duration_seconds": duration_seconds,
            "completed_at": datetime.utcnow()
        })
        self.db.commit()

        row = result.fetchone()
        recording = dict(row._mapping) if row else None

        if recording:
            logger.info(
                "recording_completed",
                recording_id=str(recording_id),
                file_size=file_size,
                duration_seconds=duration_seconds
            )

        return recording

    async def mark_failed(
        self,
        recording_id: UUID,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Marque un enregistrement comme echoue.

        Args:
            recording_id: ID de l'enregistrement
            error_message: Message d'erreur

        Returns:
            Enregistrement mis a jour
        """
        query = text("""
            UPDATE azalplus.reunion_recordings
            SET status = :status, error_message = :error_message
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        result = self.db.execute(query, {
            "id": str(recording_id),
            "tenant_id": str(self.tenant_id),
            "status": RecordingStatus.FAILED.value,
            "error_message": error_message
        })
        self.db.commit()

        row = result.fetchone()
        recording = dict(row._mapping) if row else None

        if recording:
            logger.error(
                "recording_failed",
                recording_id=str(recording_id),
                error_message=error_message
            )

        return recording
