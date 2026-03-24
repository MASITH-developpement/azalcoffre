# =============================================================================
# AZALMED - Service Signature (CONSENT)
# =============================================================================
# Signature électronique eIDAS via Yousign
# Gestion des consentements médicaux

import os
import json
import structlog
import hashlib
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

import httpx

from moteur.db import Database

logger = structlog.get_logger()


class SignatureService:
    """
    Service de signature électronique pour les consentements médicaux.

    Provider : Yousign (eIDAS)
    Niveaux : SIMPLE (OTP), AVANCEE (certificat), QUALIFIEE
    """

    TABLE_CONSENTEMENTS = "med_consentements"
    TABLE_PATIENTS = "med_patients"

    def __init__(self, tenant_id: UUID):
        """
        Initialise le service de signature.

        Args:
            tenant_id: ID du tenant (OBLIGATOIRE pour isolation multi-tenant)
        """
        self.tenant_id = tenant_id
        self.api_key = os.getenv("YOUSIGN_API_KEY")
        self.api_url = os.getenv("YOUSIGN_API_URL", "https://api.yousign.com/v3")
        self.webhook_secret = os.getenv("YOUSIGN_WEBHOOK_SECRET")

    async def envoyer_demande(
        self,
        consentement_id: UUID,
        mode: str = "EMAIL",
    ) -> dict:
        """
        Crée et envoie une demande de signature.

        Args:
            consentement_id: ID du consentement à signer
            mode: EMAIL, SMS ou TABLETTE

        Returns:
            dict avec statut et URL de signature
        """
        # TODO: Récupérer les données du consentement depuis la base
        # Pour l'exemple, données fictives
        consentement = await self._get_consentement(consentement_id)

        # 1. Générer le PDF du consentement
        pdf_content = await self._generer_pdf(consentement)

        # 2. Créer la demande de signature chez Yousign
        signature_request = await self._creer_demande_yousign(
            pdf_content=pdf_content,
            signataire_email=consentement["patient_email"],
            signataire_nom=consentement["patient_nom"],
            signataire_tel=consentement.get("patient_tel"),
            mode=mode,
        )

        # 3. Mettre à jour le statut du consentement
        await self._update_statut(
            consentement_id=consentement_id,
            statut="ENVOYE",
            yousign_id=signature_request["id"],
        )

        return {
            "consentement_id": str(consentement_id),
            "statut": "ENVOYE",
            "yousign_id": signature_request["id"],
            "url_signature": signature_request.get("signing_url"),
            "date_envoi": datetime.utcnow().isoformat(),
            "date_expiration": (datetime.utcnow() + timedelta(hours=72)).isoformat(),
        }

    async def _creer_demande_yousign(
        self,
        pdf_content: bytes,
        signataire_email: str,
        signataire_nom: str,
        signataire_tel: Optional[str] = None,
        mode: str = "EMAIL",
    ) -> dict:
        """
        Crée une demande de signature via l'API Yousign.
        """
        if not self.api_key:
            raise ValueError("YOUSIGN_API_KEY non configurée")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Upload du document
            upload_response = await client.post(
                f"{self.api_url}/documents",
                headers={**headers, "Content-Type": "application/octet-stream"},
                content=pdf_content,
            )

            if upload_response.status_code != 201:
                raise Exception(f"Erreur upload Yousign: {upload_response.text}")

            document_id = upload_response.json()["id"]

            # 2. Créer la signature request
            signature_data = {
                "name": "Consentement médical",
                "delivery_mode": mode.lower(),
                "documents": [document_id],
                "signers": [
                    {
                        "info": {
                            "first_name": signataire_nom.split()[0] if " " in signataire_nom else signataire_nom,
                            "last_name": signataire_nom.split()[-1] if " " in signataire_nom else "",
                            "email": signataire_email,
                            "phone_number": signataire_tel,
                        },
                        "signature_level": "electronic_signature",
                        "signature_authentication_mode": "otp_sms" if signataire_tel else "otp_email",
                    }
                ],
            }

            sig_response = await client.post(
                f"{self.api_url}/signature_requests",
                headers=headers,
                json=signature_data,
            )

            if sig_response.status_code != 201:
                raise Exception(f"Erreur création signature: {sig_response.text}")

            return sig_response.json()

    async def traiter_webhook(self, payload: dict) -> dict:
        """
        Traite un webhook Yousign (signature effectuée, refusée, etc.).
        """
        event_type = payload.get("event_type")
        signature_request_id = payload.get("signature_request_id")

        if event_type == "signer.done":
            # Le patient a signé
            await self._traiter_signature_effectuee(signature_request_id, payload)
            return {"status": "ok", "action": "signature_enregistree"}

        elif event_type == "signer.declined":
            # Le patient a refusé
            await self._traiter_refus(signature_request_id, payload)
            return {"status": "ok", "action": "refus_enregistre"}

        elif event_type == "signature_request.expired":
            # La demande a expiré
            await self._traiter_expiration(signature_request_id)
            return {"status": "ok", "action": "expiration_enregistree"}

        return {"status": "ignored", "event": event_type}

    async def _traiter_signature_effectuee(
        self,
        signature_request_id: str,
        payload: dict,
    ):
        """
        Traite une signature effectuée :
        1. Télécharge le PDF signé
        2. Archive dans le coffre
        3. Génère le dossier de preuves
        4. Met à jour le statut
        """
        # TODO: Implémenter
        logger.info(f"Signature effectuée: {signature_request_id}")

    async def _traiter_refus(self, signature_request_id: str, payload: dict):
        """Traite un refus de signature."""
        logger.info(f"Signature refusée: {signature_request_id}")

    async def _traiter_expiration(self, signature_request_id: str):
        """Traite une expiration de demande."""
        logger.info(f"Demande expirée: {signature_request_id}")

    async def generer_dossier_preuves(self, consentement_id: UUID) -> dict:
        """
        Génère le dossier de preuves pour un consentement signé.

        Contenu :
        - PDF signé
        - Certificat de signature
        - Horodatage TSA
        - Logs de la transaction
        """
        # TODO: Implémenter
        return {
            "consentement_id": str(consentement_id),
            "fichiers": [
                "consentement_signe.pdf",
                "certificat.pem",
                "horodatage.tsr",
                "logs.json",
            ],
        }

    async def _get_consentement(self, consentement_id: UUID) -> dict:
        """Récupère les données d'un consentement depuis la base."""
        consentement = Database.get_by_id(
            self.TABLE_CONSENTEMENTS,
            self.tenant_id,
            consentement_id,
        )
        if not consentement:
            raise ValueError(f"Consentement non trouvé: {consentement_id}")

        # Enrichir avec les données patient si patient_id présent
        if consentement.get("patient_id"):
            patient = Database.get_by_id(
                self.TABLE_PATIENTS,
                self.tenant_id,
                UUID(consentement["patient_id"]),
            )
            if patient:
                consentement["patient_nom"] = f"{patient.get('prenom', '')} {patient.get('nom', '')}".strip()
                consentement["patient_email"] = patient.get("email")
                consentement["patient_tel"] = patient.get("telephone")

        return consentement

    async def _generer_pdf(self, consentement: dict) -> bytes:
        """Génère le PDF du consentement."""
        # TODO: Implémenter avec WeasyPrint ou autre
        return b"%PDF-1.4 ..."

    async def _update_statut(
        self,
        consentement_id: UUID,
        statut: str,
        yousign_id: Optional[str] = None,
    ):
        """Met à jour le statut du consentement en base."""
        data = {"statut": statut}
        if yousign_id:
            data["yousign_id"] = yousign_id

        Database.update(
            self.TABLE_CONSENTEMENTS,
            self.tenant_id,
            consentement_id,
            data,
        )
        logger.info("consentement_status_updated", consentement_id=str(consentement_id), statut=statut)
