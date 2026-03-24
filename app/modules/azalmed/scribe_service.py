# =============================================================================
# AZALMED - Service SCRIBE (Transcription IA)
# =============================================================================
# Transcription audio → texte structuré
# Technologies : Whisper (OpenAI) + LLM (GPT/Claude)

import os
import json
import structlog
from typing import Optional
from uuid import UUID
from datetime import datetime

import httpx
from fastapi import UploadFile

from moteur.db import Database

logger = structlog.get_logger()


class ScribeService:
    """
    Service de transcription médicale par IA.

    Flux :
    1. Audio → Whisper → Transcription brute
    2. Transcription brute → LLM → Texte structuré
    """

    TABLE_CONSULTATIONS = "med_consultations"
    TABLE_PRATICIENS = "med_praticiens"

    def __init__(self, tenant_id: UUID):
        """
        Initialise le service de transcription.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE pour isolation multi-tenant)
        """
        self.tenant_id = tenant_id
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.whisper_model = "whisper-1"
        self.llm_model = "gpt-4o-mini"  # ou claude-3-haiku

    async def transcrire(
        self,
        audio_file: UploadFile,
        langue: str = "fr",
        consultation_id: Optional[UUID] = None,
    ) -> dict:
        """
        Transcrit un fichier audio et structure le résultat.

        Args:
            audio_file: Fichier audio (mp3, wav, m4a, webm)
            langue: Langue de la transcription (fr, en)
            consultation_id: ID de la consultation liée

        Returns:
            dict avec transcription_brute et transcription_structuree
        """
        # 1. Transcription avec Whisper
        transcription_brute = await self._appeler_whisper(audio_file, langue)

        # 2. Structuration avec LLM
        transcription_structuree = await self.structurer(
            texte=transcription_brute,
            specialite=None,  # TODO: récupérer depuis praticien
        )

        result = {
            "consultation_id": str(consultation_id) if consultation_id else None,
            "langue": langue,
            "transcription_brute": transcription_brute,
            "transcription_structuree": transcription_structuree,
            "duree_audio_secondes": None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Mettre à jour la consultation avec la transcription
        if consultation_id:
            Database.update(
                self.TABLE_CONSULTATIONS,
                self.tenant_id,
                consultation_id,
                {
                    "transcription_brute": transcription_brute,
                    "transcription_structuree": json.dumps(transcription_structuree),
                    "langue_transcription": langue,
                },
            )
            logger.info("transcription_saved", consultation_id=str(consultation_id))

        return result

    async def _appeler_whisper(self, audio_file: UploadFile, langue: str) -> str:
        """
        Appelle l'API Whisper d'OpenAI pour la transcription.
        """
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY non configurée")

        # Lire le fichier audio
        audio_content = await audio_file.read()

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                },
                files={
                    "file": (audio_file.filename, audio_content, audio_file.content_type),
                },
                data={
                    "model": self.whisper_model,
                    "language": langue,
                    "response_format": "text",
                },
            )

            if response.status_code != 200:
                logger.error(f"Erreur Whisper: {response.status_code} - {response.text}")
                raise Exception(f"Erreur Whisper: {response.status_code}")

            return response.text

    async def structurer(
        self,
        texte: str,
        specialite: Optional[str] = None,
    ) -> dict:
        """
        Structure une transcription brute en sections médicales.

        Sections générées :
        - motif : Motif de consultation
        - anamnese : Histoire de la maladie
        - examen_clinique : Examen physique
        - diagnostic : Diagnostic ou hypothèses
        - traitement : Traitement prescrit
        - conclusion : Conclusion et suivi
        """
        prompt = self._construire_prompt_structuration(texte, specialite)

        # Appel LLM (OpenAI par défaut)
        resultat = await self._appeler_llm(prompt)

        return resultat

    def _construire_prompt_structuration(
        self,
        texte: str,
        specialite: Optional[str] = None,
    ) -> str:
        """
        Construit le prompt pour structurer la transcription.
        """
        contexte_specialite = ""
        if specialite:
            contexte_specialite = f"Le praticien est spécialisé en {specialite}. "

        return f"""Tu es un assistant médical expert. {contexte_specialite}

Voici la transcription d'une consultation médicale :

---
{texte}
---

Structure cette transcription en sections médicales. Retourne un JSON avec les clés suivantes :
- motif : Le motif de consultation (1-2 phrases)
- anamnese : L'histoire de la maladie, les symptômes décrits par le patient
- examen_clinique : Les éléments de l'examen physique mentionnés
- diagnostic : Le diagnostic ou les hypothèses diagnostiques
- traitement : Le traitement prescrit ou recommandé
- conclusion : La conclusion, les recommandations, le suivi prévu

Si une section n'est pas mentionnée dans la transcription, mets null.
Réponds UNIQUEMENT avec le JSON, sans commentaire."""

    async def _appeler_llm(self, prompt: str) -> dict:
        """
        Appelle le LLM pour structurer le texte.
        """
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY non configurée")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )

            if response.status_code != 200:
                logger.error(f"Erreur LLM: {response.status_code} - {response.text}")
                raise Exception(f"Erreur LLM: {response.status_code}")

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            return json.loads(content)
