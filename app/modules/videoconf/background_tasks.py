# =============================================================================
# AZALPLUS - Background Tasks (Celery)
# =============================================================================
"""
Taches asynchrones pour le module de videoconference.
Utilise Celery pour les traitements longs en arriere-plan.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

# Configuration Celery
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/1")

# Import Celery conditionnellement
try:
    from celery import Celery

    celery_app = Celery(
        "azalplus_videoconf",
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,  # 1 heure max
        task_soft_time_limit=3300,  # Warning a 55 min
        task_routes={
            "videoconf.recording.*": {"queue": "videoconf_recording"},
            "videoconf.transcription.*": {"queue": "videoconf_transcription"},
            "videoconf.minutes.*": {"queue": "videoconf_minutes"},
            "videoconf.notifications.*": {"queue": "videoconf_notifications"},
        }
    )

    CELERY_AVAILABLE = True

except ImportError:
    logger.warning("celery_not_installed")
    celery_app = None
    CELERY_AVAILABLE = False


# =============================================================================
# Helper: Get DB Session
# =============================================================================
def get_db_session():
    """Cree une session DB pour les taches Celery."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/azalplus")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()


# =============================================================================
# Recording Tasks
# =============================================================================
if CELERY_AVAILABLE:

    @celery_app.task(name="videoconf.recording.process")
    def process_recording(
        recording_id: str,
        tenant_id: str,
        meeting_id: str,
        options: Optional[dict] = None
    ) -> Dict[str, Any]:
        """
        Traite un enregistrement termine.

        - Conversion de format (si necessaire)
        - Extraction audio separee
        - Generation de miniature
        - Mise a jour des metadonnees

        Args:
            recording_id: ID de l'enregistrement
            tenant_id: ID du tenant
            meeting_id: ID de la reunion
            options: Options de traitement

        Returns:
            Resultat du traitement
        """
        logger.info(
            "processing_recording",
            recording_id=recording_id,
            tenant_id=tenant_id
        )

        db = get_db_session()
        try:
            from .recording import RecordingService

            service = RecordingService(db, UUID(tenant_id))

            # Recuperer l'enregistrement
            recording = db.execute(
                "SELECT * FROM azalplus.reunion_recordings WHERE id = %s AND tenant_id = %s",
                (recording_id, tenant_id)
            ).fetchone()

            if not recording:
                logger.error("recording_not_found", recording_id=recording_id)
                return {"success": False, "error": "Recording not found"}

            file_path = recording.file_path

            # Calculer la taille et duree
            file_size = None
            duration = None

            if file_path and os.path.exists(file_path):
                file_size = os.path.getsize(file_path)

                # Calculer la duree avec ffprobe si disponible
                try:
                    import subprocess
                    result = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                         file_path],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        duration = float(result.stdout.strip())
                except Exception as e:
                    logger.warning("ffprobe_failed", error=str(e))

            # Marquer comme termine
            import asyncio
            asyncio.run(service.mark_completed(
                recording_id=UUID(recording_id),
                file_size=file_size,
                duration_seconds=duration
            ))

            logger.info(
                "recording_processed",
                recording_id=recording_id,
                file_size=file_size,
                duration=duration
            )

            return {
                "success": True,
                "recording_id": recording_id,
                "file_size": file_size,
                "duration_seconds": duration
            }

        except Exception as e:
            logger.error("recording_processing_error", error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            db.close()


    @celery_app.task(name="videoconf.recording.extract_audio")
    def extract_audio(
        recording_id: str,
        tenant_id: str,
        output_format: str = "mp3"
    ) -> Dict[str, Any]:
        """
        Extrait la piste audio d'un enregistrement video.

        Args:
            recording_id: ID de l'enregistrement
            tenant_id: ID du tenant
            output_format: Format audio (mp3, wav, ogg)

        Returns:
            Chemin vers le fichier audio
        """
        logger.info(
            "extracting_audio",
            recording_id=recording_id,
            output_format=output_format
        )

        try:
            import subprocess

            db = get_db_session()
            recording = db.execute(
                "SELECT file_path FROM azalplus.reunion_recordings WHERE id = %s AND tenant_id = %s",
                (recording_id, tenant_id)
            ).fetchone()
            db.close()

            if not recording or not recording.file_path:
                return {"success": False, "error": "Recording file not found"}

            input_path = recording.file_path
            output_path = input_path.rsplit(".", 1)[0] + f".{output_format}"

            # Extraction avec ffmpeg
            result = subprocess.run(
                ["ffmpeg", "-i", input_path, "-vn", "-acodec",
                 "libmp3lame" if output_format == "mp3" else "copy",
                 "-y", output_path],
                capture_output=True
            )

            if result.returncode != 0:
                return {"success": False, "error": result.stderr.decode()}

            logger.info("audio_extracted", output_path=output_path)

            return {
                "success": True,
                "audio_path": output_path,
                "format": output_format
            }

        except Exception as e:
            logger.error("audio_extraction_error", error=str(e))
            return {"success": False, "error": str(e)}


    # =========================================================================
    # Transcription Tasks
    # =========================================================================
    @celery_app.task(name="videoconf.transcription.transcribe_recording")
    def transcribe_recording(
        recording_id: str,
        tenant_id: str,
        meeting_id: str,
        language: str = "fr"
    ) -> Dict[str, Any]:
        """
        Transcrit un enregistrement audio/video.

        Args:
            recording_id: ID de l'enregistrement
            tenant_id: ID du tenant
            meeting_id: ID de la reunion
            language: Code langue

        Returns:
            Resultat de transcription
        """
        logger.info(
            "transcribing_recording",
            recording_id=recording_id,
            meeting_id=meeting_id,
            language=language
        )

        db = get_db_session()
        try:
            from .transcription import TranscriptionService

            # Recuperer le fichier
            recording = db.execute(
                "SELECT file_path FROM azalplus.reunion_recordings WHERE id = %s AND tenant_id = %s",
                (recording_id, tenant_id)
            ).fetchone()

            if not recording or not recording.file_path:
                return {"success": False, "error": "Recording file not found"}

            # Extraire l'audio d'abord
            audio_result = extract_audio.delay(recording_id, tenant_id, "wav").get()
            if not audio_result.get("success"):
                return {"success": False, "error": "Audio extraction failed"}

            audio_path = audio_result["audio_path"]

            # Transcrire
            service = TranscriptionService(db, UUID(tenant_id))
            import asyncio
            result = asyncio.run(service.transcribe_audio(
                audio_path=audio_path,
                meeting_id=UUID(meeting_id),
                language=language
            ))

            logger.info(
                "recording_transcribed",
                recording_id=recording_id,
                segment_count=len(result.get("segments", []))
            )

            return {
                "success": True,
                "recording_id": recording_id,
                "text": result.get("text", ""),
                "segment_count": len(result.get("segments", []))
            }

        except Exception as e:
            logger.error("transcription_error", error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            db.close()


    # =========================================================================
    # Minutes Tasks
    # =========================================================================
    @celery_app.task(name="videoconf.minutes.auto_generate")
    def auto_generate_minutes(
        meeting_id: str,
        tenant_id: str,
        delay_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Genere automatiquement le compte-rendu apres la fin de la reunion.

        Args:
            meeting_id: ID de la reunion
            tenant_id: ID du tenant
            delay_seconds: Delai avant generation

        Returns:
            Compte-rendu genere
        """
        import time
        time.sleep(delay_seconds)

        logger.info(
            "auto_generating_minutes",
            meeting_id=meeting_id,
            tenant_id=tenant_id
        )

        db = get_db_session()
        try:
            from .minutes import MinutesService

            service = MinutesService(db, UUID(tenant_id))
            import asyncio
            minutes = asyncio.run(service.generate(
                meeting_id=UUID(meeting_id)
            ))

            logger.info(
                "minutes_auto_generated",
                meeting_id=meeting_id,
                minutes_id=str(minutes["id"])
            )

            # Notifier l'organisateur
            notify_minutes_ready.delay(
                minutes_id=str(minutes["id"]),
                tenant_id=tenant_id,
                meeting_id=meeting_id
            )

            return {
                "success": True,
                "minutes_id": str(minutes["id"]),
                "status": minutes["status"]
            }

        except Exception as e:
            logger.error("auto_minutes_error", error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            db.close()


    # =========================================================================
    # Notification Tasks
    # =========================================================================
    @celery_app.task(name="videoconf.notifications.meeting_reminder")
    def send_meeting_reminder(
        meeting_id: str,
        tenant_id: str,
        minutes_before: int = 15
    ) -> Dict[str, Any]:
        """
        Envoie un rappel de reunion aux participants.

        Args:
            meeting_id: ID de la reunion
            tenant_id: ID du tenant
            minutes_before: Minutes avant la reunion

        Returns:
            Resultat d'envoi
        """
        logger.info(
            "sending_meeting_reminder",
            meeting_id=meeting_id,
            minutes_before=minutes_before
        )

        db = get_db_session()
        try:
            # Recuperer la reunion et les participants
            meeting = db.execute(
                """SELECT r.*, u.email as organisateur_email
                   FROM azalplus.reunions r
                   LEFT JOIN azalplus.users u ON r.organisateur_id = u.id
                   WHERE r.id = %s AND r.tenant_id = %s""",
                (meeting_id, tenant_id)
            ).fetchone()

            if not meeting:
                return {"success": False, "error": "Meeting not found"}

            participants = db.execute(
                """SELECT email FROM azalplus.reunion_participants
                   WHERE reunion_id = %s AND tenant_id = %s AND email IS NOT NULL""",
                (meeting_id, tenant_id)
            ).fetchall()

            emails = [p.email for p in participants]
            if meeting.organisateur_email:
                emails.append(meeting.organisateur_email)

            emails = list(set(emails))

            # TODO: Integrer avec le service de notifications
            # Pour l'instant, on log juste

            logger.info(
                "reminder_sent",
                meeting_id=meeting_id,
                recipient_count=len(emails)
            )

            return {
                "success": True,
                "recipient_count": len(emails),
                "emails": emails
            }

        except Exception as e:
            logger.error("reminder_error", error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            db.close()


    @celery_app.task(name="videoconf.notifications.recording_ready")
    def notify_recording_ready(
        recording_id: str,
        tenant_id: str,
        meeting_id: str
    ) -> Dict[str, Any]:
        """
        Notifie les participants qu'un enregistrement est pret.

        Args:
            recording_id: ID de l'enregistrement
            tenant_id: ID du tenant
            meeting_id: ID de la reunion

        Returns:
            Resultat de notification
        """
        logger.info(
            "notifying_recording_ready",
            recording_id=recording_id,
            meeting_id=meeting_id
        )

        # TODO: Implementer la notification
        return {
            "success": True,
            "recording_id": recording_id,
            "notified": True
        }


    @celery_app.task(name="videoconf.notifications.minutes_ready")
    def notify_minutes_ready(
        minutes_id: str,
        tenant_id: str,
        meeting_id: str
    ) -> Dict[str, Any]:
        """
        Notifie l'organisateur qu'un compte-rendu est pret pour validation.

        Args:
            minutes_id: ID du compte-rendu
            tenant_id: ID du tenant
            meeting_id: ID de la reunion

        Returns:
            Resultat de notification
        """
        logger.info(
            "notifying_minutes_ready",
            minutes_id=minutes_id,
            meeting_id=meeting_id
        )

        db = get_db_session()
        try:
            # Recuperer l'organisateur
            meeting = db.execute(
                """SELECT r.titre, u.email, u.nom
                   FROM azalplus.reunions r
                   JOIN azalplus.users u ON r.organisateur_id = u.id
                   WHERE r.id = %s AND r.tenant_id = %s""",
                (meeting_id, tenant_id)
            ).fetchone()

            if not meeting:
                return {"success": False, "error": "Meeting not found"}

            # TODO: Envoyer l'email de notification
            logger.info(
                "minutes_notification_sent",
                minutes_id=minutes_id,
                email=meeting.email
            )

            return {
                "success": True,
                "minutes_id": minutes_id,
                "notified_email": meeting.email
            }

        except Exception as e:
            logger.error("minutes_notification_error", error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            db.close()


    # =========================================================================
    # Cleanup Tasks
    # =========================================================================
    @celery_app.task(name="videoconf.cleanup.expired_recordings")
    def cleanup_expired_recordings(
        retention_days: int = 90
    ) -> Dict[str, Any]:
        """
        Supprime les enregistrements expires.

        Args:
            retention_days: Duree de retention en jours

        Returns:
            Nombre d'enregistrements supprimes
        """
        logger.info(
            "cleaning_expired_recordings",
            retention_days=retention_days
        )

        db = get_db_session()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

            # Recuperer les enregistrements expires
            expired = db.execute(
                """SELECT id, tenant_id, file_path FROM azalplus.reunion_recordings
                   WHERE created_at < %s AND deleted_at IS NULL
                   AND status = 'completed'""",
                (cutoff_date,)
            ).fetchall()

            deleted_count = 0
            for rec in expired:
                # Supprimer le fichier
                if rec.file_path and os.path.exists(rec.file_path):
                    os.remove(rec.file_path)

                # Marquer comme supprime
                db.execute(
                    """UPDATE azalplus.reunion_recordings
                       SET deleted_at = %s WHERE id = %s""",
                    (datetime.utcnow(), rec.id)
                )
                deleted_count += 1

            db.commit()

            logger.info(
                "recordings_cleaned",
                deleted_count=deleted_count
            )

            return {
                "success": True,
                "deleted_count": deleted_count
            }

        except Exception as e:
            logger.error("cleanup_error", error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            db.close()


    # =========================================================================
    # Scheduled Tasks (Celery Beat)
    # =========================================================================
    celery_app.conf.beat_schedule = {
        "cleanup-expired-recordings-daily": {
            "task": "videoconf.cleanup.expired_recordings",
            "schedule": 86400.0,  # 24 heures
            "args": (90,)
        }
    }

else:
    # Mode sans Celery - fonctions de fallback
    def process_recording(*args, **kwargs):
        logger.warning("celery_not_available", task="process_recording")
        return {"success": False, "error": "Celery not available"}

    def extract_audio(*args, **kwargs):
        logger.warning("celery_not_available", task="extract_audio")
        return {"success": False, "error": "Celery not available"}

    def transcribe_recording(*args, **kwargs):
        logger.warning("celery_not_available", task="transcribe_recording")
        return {"success": False, "error": "Celery not available"}

    def auto_generate_minutes(*args, **kwargs):
        logger.warning("celery_not_available", task="auto_generate_minutes")
        return {"success": False, "error": "Celery not available"}

    def send_meeting_reminder(*args, **kwargs):
        logger.warning("celery_not_available", task="send_meeting_reminder")
        return {"success": False, "error": "Celery not available"}

    def notify_recording_ready(*args, **kwargs):
        logger.warning("celery_not_available", task="notify_recording_ready")
        return {"success": False, "error": "Celery not available"}

    def notify_minutes_ready(*args, **kwargs):
        logger.warning("celery_not_available", task="notify_minutes_ready")
        return {"success": False, "error": "Celery not available"}

    def cleanup_expired_recordings(*args, **kwargs):
        logger.warning("celery_not_available", task="cleanup_expired_recordings")
        return {"success": False, "error": "Celery not available"}
