# =============================================================================
# AZALPLUS - Transcription Service (Whisper)
# =============================================================================
"""
Service de transcription audio via Whisper (local ou API).
Supporte la transcription en temps reel et par batch.
"""

import os
import json
import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================
class TranscriptionStatus(str, Enum):
    """Statuts de transcription."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionProvider(str, Enum):
    """Providers de transcription."""
    WHISPER_LOCAL = "whisper_local"
    WHISPER_API = "whisper_api"
    GOOGLE = "google"


# =============================================================================
# Transcription Service
# =============================================================================
class TranscriptionService:
    """
    Service de transcription audio pour les reunions.

    Fonctionnalites:
    - Transcription temps reel (streaming)
    - Transcription batch (fichiers audio)
    - Detection des locuteurs (speaker diarization)
    - Timestamps precis
    - Multi-langue

    Providers:
    - whisper_local: Modele Whisper local (medium par defaut)
    - whisper_api: API OpenAI Whisper
    - google: Google Cloud Speech-to-Text
    """

    def __init__(self, db: Session, tenant_id: UUID):
        """
        Initialise le service de transcription.

        Args:
            db: Session SQLAlchemy
            tenant_id: ID du tenant pour l'isolation
        """
        self.db = db
        self.tenant_id = tenant_id
        self._config: Optional[dict] = None
        self._whisper_model = None

    def _get_config(self) -> dict:
        """Charge la configuration de transcription."""
        if self._config is None:
            self._config = {
                "provider": os.environ.get("TRANSCRIPTION_PROVIDER", "whisper_local"),
                "whisper_model": os.environ.get("WHISPER_MODEL", "medium"),
                "whisper_device": os.environ.get("WHISPER_DEVICE", "cpu"),
                "default_language": "fr",
                "threads": 4,
                "model_path": "/home/ubuntu/azalplus/models/whisper",
                "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
                "timestamps": True,
                "speaker_detection": True,
                "filter_silence": True,
                "auto_punctuation": True,
            }
        return self._config

    def _get_whisper_model(self):
        """Charge le modele Whisper (lazy loading)."""
        if self._whisper_model is None:
            config = self._get_config()
            try:
                import whisper

                model_name = config["whisper_model"]
                device = config["whisper_device"]

                logger.info(
                    "loading_whisper_model",
                    model=model_name,
                    device=device
                )

                self._whisper_model = whisper.load_model(
                    model_name,
                    device=device
                )

                logger.info("whisper_model_loaded", model=model_name)

            except ImportError:
                logger.warning("whisper_not_installed")
                self._whisper_model = "mock"
            except Exception as e:
                logger.error("whisper_load_error", error=str(e))
                self._whisper_model = "mock"

        return self._whisper_model

    # =========================================================================
    # Helpers
    # =========================================================================
    def _verify_meeting_access(self, meeting_id: UUID) -> Optional[dict]:
        """Verifie que la reunion appartient au tenant."""
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

    # =========================================================================
    # Start/Stop Transcription
    # =========================================================================
    async def start_transcription(
        self,
        meeting_id: UUID,
        language: Optional[str] = None,
        started_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Demarre la transcription pour une reunion.

        Args:
            meeting_id: ID de la reunion
            language: Code langue (fr, en, etc.)
            started_by: ID de l'utilisateur

        Returns:
            Informations sur la transcription demarree
        """
        meeting = self._verify_meeting_access(meeting_id)
        if not meeting:
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        if meeting.get("statut") not in ["en_cours", "active"]:
            raise ValueError("La reunion doit etre en cours")

        config = self._get_config()
        lang = language or config["default_language"]
        transcription_id = uuid4()
        now = datetime.utcnow()

        # Inserer en base
        insert_query = text("""
            INSERT INTO azalplus.reunion_transcriptions
            (id, tenant_id, reunion_id, status, language, provider,
             started_at, started_by, created_at)
            VALUES (:id, :tenant_id, :reunion_id, :status, :language, :provider,
                    :started_at, :started_by, :created_at)
            RETURNING *
        """)

        result = self.db.execute(insert_query, {
            "id": str(transcription_id),
            "tenant_id": str(self.tenant_id),
            "reunion_id": str(meeting_id),
            "status": TranscriptionStatus.PROCESSING.value,
            "language": lang,
            "provider": config["provider"],
            "started_at": now,
            "started_by": str(started_by) if started_by else None,
            "created_at": now
        })
        self.db.commit()

        row = result.fetchone()
        transcription = dict(row._mapping) if row else None

        logger.info(
            "transcription_started",
            transcription_id=str(transcription_id),
            meeting_id=str(meeting_id),
            language=lang,
            provider=config["provider"]
        )

        return transcription

    async def stop_transcription(
        self,
        meeting_id: UUID,
        stopped_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Arrete la transcription en cours.

        Args:
            meeting_id: ID de la reunion
            stopped_by: ID de l'utilisateur

        Returns:
            Transcription arretee
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Trouver la transcription active
        query = text("""
            SELECT * FROM azalplus.reunion_transcriptions
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            AND status = :status
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "status": TranscriptionStatus.PROCESSING.value
        })
        row = result.fetchone()

        if not row:
            raise ValueError("Aucune transcription en cours")

        transcription = dict(row._mapping)
        now = datetime.utcnow()

        # Mettre a jour
        update_query = text("""
            UPDATE azalplus.reunion_transcriptions
            SET status = :status, stopped_at = :stopped_at, stopped_by = :stopped_by
            WHERE id = :id AND tenant_id = :tenant_id
            RETURNING *
        """)

        update_result = self.db.execute(update_query, {
            "id": str(transcription["id"]),
            "tenant_id": str(self.tenant_id),
            "status": TranscriptionStatus.COMPLETED.value,
            "stopped_at": now,
            "stopped_by": str(stopped_by) if stopped_by else None
        })
        self.db.commit()

        updated = dict(update_result.fetchone()._mapping)

        logger.info(
            "transcription_stopped",
            transcription_id=str(transcription["id"]),
            meeting_id=str(meeting_id)
        )

        return updated

    # =========================================================================
    # Transcribe Audio
    # =========================================================================
    async def transcribe_audio(
        self,
        audio_path: str,
        meeting_id: UUID,
        language: Optional[str] = None,
        speaker_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcrit un fichier audio.

        Args:
            audio_path: Chemin vers le fichier audio
            meeting_id: ID de la reunion
            language: Code langue
            speaker_id: ID du locuteur (pour speaker diarization)

        Returns:
            Resultat de transcription avec segments
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        config = self._get_config()
        lang = language or config["default_language"]

        # Verifier le fichier
        if not os.path.exists(audio_path):
            raise ValueError(f"Fichier audio non trouve: {audio_path}")

        provider = config["provider"]

        if provider == TranscriptionProvider.WHISPER_LOCAL.value:
            result = await self._transcribe_whisper_local(audio_path, lang)
        elif provider == TranscriptionProvider.WHISPER_API.value:
            result = await self._transcribe_whisper_api(audio_path, lang)
        else:
            raise ValueError(f"Provider non supporte: {provider}")

        # Enregistrer les segments
        transcription_id = result.get("transcription_id")
        if transcription_id:
            await self._save_segments(
                transcription_id=transcription_id,
                segments=result.get("segments", []),
                speaker_id=speaker_id
            )

        logger.info(
            "audio_transcribed",
            meeting_id=str(meeting_id),
            duration=result.get("duration"),
            segment_count=len(result.get("segments", []))
        )

        return result

    async def _transcribe_whisper_local(
        self,
        audio_path: str,
        language: str
    ) -> Dict[str, Any]:
        """Transcrit avec Whisper local."""
        model = self._get_whisper_model()

        if model == "mock":
            # Mode mock sans Whisper
            return {
                "text": "[Transcription non disponible - Whisper non installe]",
                "language": language,
                "duration": 0,
                "segments": []
            }

        # Executer dans un thread pour ne pas bloquer
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: model.transcribe(
                audio_path,
                language=language,
                task="transcribe",
                verbose=False
            )
        )

        # Formater les segments
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "id": str(uuid4()),
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
                "confidence": seg.get("avg_logprob", 0)
            })

        return {
            "text": result.get("text", "").strip(),
            "language": result.get("language", language),
            "duration": segments[-1]["end"] if segments else 0,
            "segments": segments
        }

    async def _transcribe_whisper_api(
        self,
        audio_path: str,
        language: str
    ) -> Dict[str, Any]:
        """Transcrit avec l'API OpenAI Whisper."""
        config = self._get_config()
        api_key = config["openai_api_key"]

        if not api_key:
            raise ValueError("OPENAI_API_KEY non configure")

        try:
            import openai

            client = openai.OpenAI(api_key=api_key)

            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            segments = []
            for seg in response.segments:
                segments.append({
                    "id": str(uuid4()),
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "confidence": 1.0  # API ne retourne pas de confiance
                })

            return {
                "text": response.text,
                "language": language,
                "duration": response.duration if hasattr(response, "duration") else 0,
                "segments": segments
            }

        except ImportError:
            raise ValueError("openai package non installe")

    async def _save_segments(
        self,
        transcription_id: UUID,
        segments: List[dict],
        speaker_id: Optional[str] = None
    ) -> None:
        """Sauvegarde les segments en base."""
        for seg in segments:
            insert_query = text("""
                INSERT INTO azalplus.reunion_transcription_segments
                (id, tenant_id, transcription_id, start_time, end_time,
                 text, speaker_id, confidence, created_at)
                VALUES (:id, :tenant_id, :transcription_id, :start_time, :end_time,
                        :text, :speaker_id, :confidence, :created_at)
            """)

            self.db.execute(insert_query, {
                "id": seg.get("id", str(uuid4())),
                "tenant_id": str(self.tenant_id),
                "transcription_id": str(transcription_id),
                "start_time": seg["start"],
                "end_time": seg["end"],
                "text": seg["text"],
                "speaker_id": speaker_id,
                "confidence": seg.get("confidence"),
                "created_at": datetime.utcnow()
            })

        self.db.commit()

    # =========================================================================
    # Add Segment (Streaming)
    # =========================================================================
    async def add_segment(
        self,
        meeting_id: UUID,
        start_time: float,
        end_time: float,
        text: str,
        speaker_id: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ajoute un segment de transcription (mode streaming).

        Args:
            meeting_id: ID de la reunion
            start_time: Timestamp debut (secondes)
            end_time: Timestamp fin (secondes)
            text: Texte transcrit
            speaker_id: ID du locuteur
            confidence: Score de confiance

        Returns:
            Segment cree
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Trouver la transcription active
        query = text("""
            SELECT id FROM azalplus.reunion_transcriptions
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            AND status = :status
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id),
            "status": TranscriptionStatus.PROCESSING.value
        })
        row = result.fetchone()

        if not row:
            raise ValueError("Aucune transcription active")

        transcription_id = row.id
        segment_id = uuid4()
        now = datetime.utcnow()

        insert_query = text("""
            INSERT INTO azalplus.reunion_transcription_segments
            (id, tenant_id, transcription_id, start_time, end_time,
             text, speaker_id, confidence, created_at)
            VALUES (:id, :tenant_id, :transcription_id, :start_time, :end_time,
                    :text, :speaker_id, :confidence, :created_at)
            RETURNING *
        """)

        insert_result = self.db.execute(insert_query, {
            "id": str(segment_id),
            "tenant_id": str(self.tenant_id),
            "transcription_id": str(transcription_id),
            "start_time": start_time,
            "end_time": end_time,
            "text": text.strip(),
            "speaker_id": speaker_id,
            "confidence": confidence,
            "created_at": now
        })
        self.db.commit()

        segment = dict(insert_result.fetchone()._mapping)

        logger.debug(
            "transcription_segment_added",
            segment_id=str(segment_id),
            meeting_id=str(meeting_id),
            text_length=len(text)
        )

        return segment

    # =========================================================================
    # Get Transcription
    # =========================================================================
    async def get_transcription(
        self,
        meeting_id: UUID,
        include_segments: bool = True,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        Recupere la transcription complete d'une reunion.

        Args:
            meeting_id: ID de la reunion
            include_segments: Inclure les segments individuels
            format: Format de sortie (json, text, srt, vtt)

        Returns:
            Transcription formatee
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        # Recuperer la transcription
        query = text("""
            SELECT * FROM azalplus.reunion_transcriptions
            WHERE reunion_id = :meeting_id
            AND tenant_id = :tenant_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })
        row = result.fetchone()

        if not row:
            return {"text": "", "segments": [], "status": "not_started"}

        transcription = dict(row._mapping)

        # Recuperer les segments si demande
        segments = []
        if include_segments:
            seg_query = text("""
                SELECT * FROM azalplus.reunion_transcription_segments
                WHERE transcription_id = :transcription_id
                AND tenant_id = :tenant_id
                ORDER BY start_time ASC
            """)
            seg_result = self.db.execute(seg_query, {
                "transcription_id": str(transcription["id"]),
                "tenant_id": str(self.tenant_id)
            })
            segments = [dict(r._mapping) for r in seg_result]

        # Construire le texte complet
        full_text = " ".join(s["text"] for s in segments)

        # Formater selon le format demande
        if format == "text":
            return {
                "text": full_text,
                "status": transcription["status"]
            }
        elif format == "srt":
            return {
                "content": self._to_srt(segments),
                "format": "srt",
                "status": transcription["status"]
            }
        elif format == "vtt":
            return {
                "content": self._to_vtt(segments),
                "format": "vtt",
                "status": transcription["status"]
            }
        else:  # json
            transcription["segments"] = segments
            transcription["full_text"] = full_text
            return transcription

    def _to_srt(self, segments: List[dict]) -> str:
        """Convertit en format SRT."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = self._format_timestamp_srt(seg["start_time"])
            end = self._format_timestamp_srt(seg["end_time"])
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)

    def _to_vtt(self, segments: List[dict]) -> str:
        """Convertit en format WebVTT."""
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = self._format_timestamp_vtt(seg["start_time"])
            end = self._format_timestamp_vtt(seg["end_time"])
            lines.append(f"{start} --> {end}")
            lines.append(seg["text"])
            lines.append("")
        return "\n".join(lines)

    def _format_timestamp_srt(self, seconds: float) -> str:
        """Formate un timestamp pour SRT (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_timestamp_vtt(self, seconds: float) -> str:
        """Formate un timestamp pour VTT (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    # =========================================================================
    # List Transcriptions
    # =========================================================================
    async def list_transcriptions(
        self,
        meeting_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Liste toutes les transcriptions d'une reunion.

        Args:
            meeting_id: ID de la reunion

        Returns:
            Liste des transcriptions
        """
        if not self._verify_meeting_access(meeting_id):
            raise ValueError(f"Reunion {meeting_id} non trouvee")

        query = text("""
            SELECT t.*,
                   COUNT(s.id) as segment_count,
                   SUM(CASE WHEN s.id IS NOT NULL THEN LENGTH(s.text) ELSE 0 END) as total_chars
            FROM azalplus.reunion_transcriptions t
            LEFT JOIN azalplus.reunion_transcription_segments s
                ON t.id = s.transcription_id
            WHERE t.reunion_id = :meeting_id
            AND t.tenant_id = :tenant_id
            GROUP BY t.id
            ORDER BY t.created_at DESC
        """)

        result = self.db.execute(query, {
            "meeting_id": str(meeting_id),
            "tenant_id": str(self.tenant_id)
        })

        return [dict(r._mapping) for r in result]
