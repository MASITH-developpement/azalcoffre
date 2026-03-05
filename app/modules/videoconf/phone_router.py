# =============================================================================
# AZALPLUS - Phone Call Router
# =============================================================================
"""
Endpoints REST pour la gestion des appels telephoniques.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/phone", tags=["Phone Calls"])


# =============================================================================
# Pydantic Schemas
# =============================================================================
class InitiateCallRequest(BaseModel):
    """Requete pour initier un appel."""
    callee: str = Field(..., description="Email, telephone ou ID du destinataire")
    subject: Optional[str] = Field(None, description="Sujet de l'appel")
    provider: Optional[str] = Field("app", description="Provider: 'app' (gratuit) ou 'twilio' (payant)")
    auto_record: Optional[bool] = Field(True, description="Enregistrer l'appel")
    auto_transcribe: Optional[bool] = Field(True, description="Transcrire automatiquement")
    auto_minutes: Optional[bool] = Field(True, description="Generer compte-rendu")


class LinkPhoneRequest(BaseModel):
    """Requete pour lier un telephone."""
    phone_number: str = Field(..., description="Numero de telephone")
    verify: bool = Field(True, description="Envoyer SMS de verification")


class VerifyPhoneRequest(BaseModel):
    """Requete pour verifier un telephone."""
    phone_number: str = Field(..., description="Numero de telephone")
    code: str = Field(..., description="Code de verification")


class ResendMinutesRequest(BaseModel):
    """Requete pour renvoyer le compte-rendu."""
    email: Optional[str] = Field(None, description="Email alternatif")


class CallResponse(BaseModel):
    """Reponse d'appel."""
    id: str
    status: str
    to_number: str
    from_number: Optional[str] = None
    subject: Optional[str] = None
    direction: str
    duration_seconds: Optional[int] = None
    minutes_status: Optional[str] = None


# =============================================================================
# Dependencies
# =============================================================================
async def get_phone_service(request: Request):
    """Recupere le service d'appels avec contexte tenant."""
    from .phone_call import PhoneCallService

    # Extraire tenant_id du contexte (middleware)
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant non identifie")

    db = request.state.db
    return PhoneCallService(db, tenant_id)


async def get_current_user(request: Request) -> dict:
    """Recupere l'utilisateur courant."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifie")
    return user


# =============================================================================
# Endpoints
# =============================================================================
@router.post("/calls")
async def initiate_call(
    request: InitiateCallRequest,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """
    Initie un appel telephonique.

    **Deux modes disponibles:**

    - `provider: "app"` (defaut, gratuit)
      Appel via l'application AZALPLUS (WebRTC).
      Le destinataire doit etre un utilisateur AZALPLUS.

    - `provider: "twilio"` (option payante)
      Appel PSTN vers n'importe quel numero.
      Necessite une configuration Twilio.

    L'appel sera automatiquement:
    - Enregistre (si auto_record=true)
    - Transcrit apres la fin (si auto_transcribe=true)
    - Synthetise en compte-rendu (si auto_minutes=true)
    - Envoye par email (config utilisateur AZALPLUS)
    """
    from .phone_call import CallProvider

    try:
        # Determiner le provider
        provider = CallProvider.APP
        if request.provider and request.provider.lower() == "twilio":
            provider = CallProvider.TWILIO

        call = await service.initiate_call(
            caller_id=UUID(user["id"]),
            callee_identifier=request.callee,
            subject=request.subject,
            provider=provider,
            auto_record=request.auto_record,
            auto_transcribe=request.auto_transcribe,
            auto_minutes=request.auto_minutes
        )
        return call
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("initiate_call_error", error=str(e))
        raise HTTPException(status_code=500, detail="Erreur lors de l'initiation de l'appel")


@router.get("/calls")
async def list_calls(
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    direction: Optional[str] = Query(None, description="Filtrer par direction"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Liste les appels de l'utilisateur."""
    from .phone_call import CallStatus, CallDirection

    status_enum = CallStatus(status) if status else None
    direction_enum = CallDirection(direction) if direction else None

    calls = await service.list_calls(
        user_id=UUID(user["id"]),
        status=status_enum,
        direction=direction_enum,
        limit=limit,
        offset=offset
    )
    return {"data": calls, "total": len(calls)}


@router.get("/calls/{call_id}")
async def get_call(
    call_id: UUID,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Recupere les details d'un appel."""
    try:
        call = await service.get_call(call_id)

        # Verifier que l'appel appartient a l'utilisateur
        if str(call["user_id"]) != user["id"]:
            raise HTTPException(status_code=403, detail="Acces refuse")

        return call
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/calls/incoming")
async def get_incoming_calls(
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """
    Recupere les appels entrants en attente pour l'utilisateur.
    Utilise par l'app mobile pour afficher les appels a repondre.
    """
    calls = await service.get_incoming_calls(UUID(user["id"]))
    return {"data": calls}


@router.post("/calls/{call_id}/answer")
async def answer_call(
    call_id: UUID,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """
    Repond a un appel entrant.
    Retourne le token LiveKit pour rejoindre la conversation.
    """
    try:
        result = await service.answer_call(call_id, UUID(user["id"]))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calls/{call_id}/decline")
async def decline_call(
    call_id: UUID,
    reason: Optional[str] = None,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Decline un appel entrant."""
    try:
        result = await service.decline_call(call_id, UUID(user["id"]), reason)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calls/{call_id}/end")
async def end_call(
    call_id: UUID,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """
    Termine un appel en cours.
    Declenche automatiquement la transcription et le compte-rendu.
    """
    try:
        # Verifier l'acces (appelant ou destinataire)
        call = await service.get_call(call_id)
        if str(call["user_id"]) != user["id"] and str(call.get("callee_id")) != user["id"]:
            raise HTTPException(status_code=403, detail="Acces refuse")

        result = await service.end_call(call_id, ended_by=UUID(user["id"]))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/calls/{call_id}/transcription")
async def get_transcription(
    call_id: UUID,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Recupere la transcription d'un appel."""
    call = await service.get_call(call_id)

    if str(call["user_id"]) != user["id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")

    if not call.get("transcription"):
        raise HTTPException(status_code=404, detail="Transcription non disponible")

    return {
        "call_id": str(call_id),
        "transcription": call["transcription"]
    }


@router.get("/calls/{call_id}/minutes")
async def get_minutes(
    call_id: UUID,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Recupere le compte-rendu d'un appel."""
    call = await service.get_call(call_id)

    if str(call["user_id"]) != user["id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")

    if not call.get("minutes_content"):
        raise HTTPException(status_code=404, detail="Compte-rendu non disponible")

    return {
        "call_id": str(call_id),
        "minutes": call["minutes_content"],
        "status": call.get("minutes_status")
    }


@router.post("/calls/{call_id}/minutes/resend")
async def resend_minutes(
    call_id: UUID,
    request: ResendMinutesRequest,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Renvoie le compte-rendu par email."""
    call = await service.get_call(call_id)

    if str(call["user_id"]) != user["id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")

    try:
        result = await service.resend_minutes(call_id, email=request.email)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calls/{call_id}/minutes/regenerate")
async def regenerate_minutes(
    call_id: UUID,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Regenere le compte-rendu d'un appel."""
    call = await service.get_call(call_id)

    if str(call["user_id"]) != user["id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")

    try:
        result = await service.regenerate_minutes(call_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Phone Linking
# =============================================================================
@router.post("/link")
async def link_phone(
    request: LinkPhoneRequest,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """
    Lie un numero de telephone a l'utilisateur.

    Si verify=true, envoie un SMS de verification.
    """
    try:
        result = await service.link_user_phone(
            user_id=UUID(user["id"]),
            phone_number=request.phone_number,
            verify=request.verify
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify")
async def verify_phone(
    request: VerifyPhoneRequest,
    service=Depends(get_phone_service),
    user: dict = Depends(get_current_user)
):
    """Verifie le code SMS et finalise la liaison du telephone."""
    try:
        result = await service.verify_phone(
            user_id=UUID(user["id"]),
            phone_number=request.phone_number,
            code=request.code
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Webhooks (Twilio)
# =============================================================================
@router.post("/twilio-webhook/status/{call_id}")
async def twilio_status_callback(
    call_id: UUID,
    request: Request,
    service=Depends(get_phone_service)
):
    """
    Webhook Twilio pour les mises a jour de statut.
    Note: Ce endpoint doit etre accessible sans auth.
    """
    form = await request.form()
    status = form.get("CallStatus")
    duration = form.get("CallDuration")

    logger.info(
        "twilio_status_callback",
        call_id=str(call_id),
        status=status,
        duration=duration
    )

    if status == "answered":
        await service.handle_call_answered(call_id)
    elif status == "completed":
        await service.handle_call_completed(
            call_id,
            duration_seconds=int(duration) if duration else None
        )

    return {"status": "ok"}


@router.post("/twilio-webhook/recording/{call_id}")
async def twilio_recording_callback(
    call_id: UUID,
    request: Request,
    service=Depends(get_phone_service)
):
    """
    Webhook Twilio pour les enregistrements.
    """
    form = await request.form()
    recording_url = form.get("RecordingUrl")
    recording_sid = form.get("RecordingSid")

    logger.info(
        "twilio_recording_callback",
        call_id=str(call_id),
        recording_sid=recording_sid
    )

    if recording_url:
        # Mettre a jour l'URL d'enregistrement et declencher le traitement
        from sqlalchemy import text

        # Note: Necessiterait une session DB ici
        # Le traitement sera declenche par handle_call_completed

    return {"status": "ok"}


@router.post("/twilio-webhook/twiml/{call_id}")
async def twilio_twiml(call_id: UUID):
    """
    Retourne le TwiML pour l'appel.
    Configure l'enregistrement et le flux audio.
    """
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR">Votre appel AZALPLUS est en cours de connexion.</Say>
    <Dial record="record-from-answer-dual" recordingStatusCallback="/api/phone/twilio-webhook/recording/{call_id}">
        <Number>{{{{to_number}}}}</Number>
    </Dial>
</Response>
"""
    from fastapi.responses import Response
    return Response(content=twiml, media_type="application/xml")
