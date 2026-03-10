# =============================================================================
# AZALPLUS - Debug Router
# =============================================================================
"""
API endpoints pour le module Debug.
Accessible uniquement aux utilisateurs avec le rôle 'debugger' ou 'admin'.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import Optional
from uuid import UUID
import structlog

from ..auth import get_current_user
from ..tenant import TenantContext, get_current_tenant
from ..ratelimit import RateLimiter
from ..config import settings
from .schemas import (
    BugCreate, BugFromReplay, BugResponse, BugListResponse,
    TestValidation, TestListResponse,
    ChatSend, ChatResponse, AnalyzeRequest, AnalyzeResponse,
    GuardianErrorListResponse, DebugStats
)
from .service import DebugService
from .models import BugStatut

logger = structlog.get_logger()

router = APIRouter(prefix="/api/debug", tags=["Debug"])


# =============================================================================
# Dépendances
# =============================================================================
async def require_createur(request: Request):
    """Vérifie que l'utilisateur est le créateur. Accès restreint pour le moment."""
    user = request.state.user
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")

    # Créateur uniquement
    email = getattr(user, "email", None) or user.get("email")
    if email != settings.CREATEUR_EMAIL:
        raise HTTPException(status_code=403, detail="Accès réservé au créateur")

    return user


async def get_debug_context(request: Request):
    """Récupère le contexte debug (tenant_id, user_id)."""
    user = await require_createur(request)
    tenant_id = TenantContext.get_tenant_id()

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant non défini")

    user_id = getattr(user, "id", None) or user.get("sub")

    return {
        "tenant_id": UUID(str(tenant_id)),
        "user_id": UUID(str(user_id)),
        "ip_address": request.client.host if request.client else None
    }


# =============================================================================
# Rate Limiting pour Simon (appels IA)
# =============================================================================
SIMON_RATE_LIMIT = 20  # 20 appels par minute


async def check_simon_rate_limit(request: Request):
    """Vérifie le rate limit pour les appels à Simon."""
    user = request.state.user
    user_id = getattr(user, "id", None) or user.get("sub")

    key = f"simon:user:{user_id}"
    allowed, current, limit, reset_in = await RateLimiter.check_limit(
        key=key,
        limit=SIMON_RATE_LIMIT,
        window=60
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Trop de demandes à Simon. Réessayez dans {reset_in} secondes."
        )


# =============================================================================
# Bugs - CRUD
# =============================================================================
@router.post("/bugs", response_model=dict, status_code=201)
async def create_bug(
    data: BugCreate,
    ctx: dict = Depends(get_debug_context)
):
    """Crée un nouveau bug (mode ticket)."""
    try:
        result = await DebugService.create_bug(
            tenant_id=ctx["tenant_id"],
            user_id=ctx["user_id"],
            data=data
        )
        return result
    except Exception as e:
        logger.error("debug_create_bug_error", error=str(e))
        raise HTTPException(status_code=500, detail="Erreur lors de la création du bug")


@router.post("/bugs/replay", response_model=dict, status_code=201)
async def create_bug_from_replay(
    data: BugFromReplay,
    ctx: dict = Depends(get_debug_context)
):
    """Crée un bug depuis une erreur Guardian (mode replay)."""
    try:
        result = await DebugService.create_bug_from_replay(
            tenant_id=ctx["tenant_id"],
            user_id=ctx["user_id"],
            data=data
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("debug_create_replay_error", error=str(e))
        raise HTTPException(status_code=500, detail="Erreur lors de la création du bug")


@router.get("/bugs", response_model=BugListResponse)
async def list_bugs(
    skip: int = 0,
    limit: int = 25,
    statut: Optional[str] = None,
    mes_bugs: bool = False,
    ctx: dict = Depends(get_debug_context)
):
    """Liste les bugs avec pagination."""
    user_id = ctx["user_id"] if mes_bugs else None

    return await DebugService.list_bugs(
        tenant_id=ctx["tenant_id"],
        skip=skip,
        limit=limit,
        statut=statut,
        user_id=user_id
    )


@router.get("/bugs/{bug_id}")
async def get_bug(
    bug_id: UUID,
    ctx: dict = Depends(get_debug_context)
):
    """Récupère un bug par son ID."""
    bug = await DebugService.get_bug(ctx["tenant_id"], bug_id)
    if not bug:
        raise HTTPException(status_code=404, detail="Bug non trouvé")
    return bug


@router.post("/bugs/{bug_id}/close")
async def close_bug(
    bug_id: UUID,
    ctx: dict = Depends(get_debug_context)
):
    """Ferme un bug."""
    success = await DebugService.update_bug_statut(
        ctx["tenant_id"], bug_id, BugStatut.FERME, ctx["user_id"]
    )
    if not success:
        raise HTTPException(status_code=404, detail="Bug non trouvé")
    return {"success": True}


# =============================================================================
# Simon - Analyse
# =============================================================================
@router.post("/bugs/{bug_id}/analyze", response_model=AnalyzeResponse)
async def analyze_bug(
    bug_id: UUID,
    request: Request,
    ctx: dict = Depends(get_debug_context),
    _: None = Depends(check_simon_rate_limit)
):
    """Demande à Simon d'analyser le bug et proposer des tests."""
    try:
        return await DebugService.analyze_bug(
            tenant_id=ctx["tenant_id"],
            bug_id=bug_id,
            user_id=ctx["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("debug_analyze_error", error=str(e), bug_id=str(bug_id))
        raise HTTPException(status_code=500, detail="Erreur lors de l'analyse")


# =============================================================================
# Tests
# =============================================================================
@router.get("/bugs/{bug_id}/tests", response_model=TestListResponse)
async def get_tests(
    bug_id: UUID,
    ctx: dict = Depends(get_debug_context)
):
    """Récupère les tests d'un bug."""
    try:
        return await DebugService.get_tests(ctx["tenant_id"], bug_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/tests/{test_id}")
async def validate_test(
    test_id: UUID,
    data: TestValidation,
    ctx: dict = Depends(get_debug_context)
):
    """Valide un test (OK ou KO)."""
    try:
        await DebugService.validate_test(
            tenant_id=ctx["tenant_id"],
            test_id=test_id,
            user_id=ctx["user_id"],
            data=data
        )
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bugs/{bug_id}/more-tests", response_model=AnalyzeResponse)
async def request_more_tests(
    bug_id: UUID,
    request: Request,
    ctx: dict = Depends(get_debug_context),
    _: None = Depends(check_simon_rate_limit)
):
    """Demande à Simon des tests supplémentaires après échecs."""
    try:
        bug = await DebugService.get_bug(ctx["tenant_id"], bug_id)
        if not bug:
            raise HTTPException(status_code=404, detail="Bug non trouvé")

        tests = await DebugService.get_tests(ctx["tenant_id"], bug_id)
        failed = [t for t in tests.tests if t.statut.value == "ko"]

        if not failed:
            raise HTTPException(status_code=400, detail="Aucun test échoué")

        from .simon import simon
        result = await simon.more_tests(
            titre=bug["titre"],
            description=bug["description"],
            failed_tests=[{"numero": t.numero, "action": t.action} for t in failed],
            comments=[t.commentaire for t in failed if t.commentaire]
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])

        # Sauvegarder les nouveaux tests
        from .service import DebugService
        await DebugService._save_tests_from_chat(bug_id, result["tests"])

        return AnalyzeResponse(
            bug_id=bug_id,
            statut=BugStatut.TESTS_PROPOSES,
            tests=[],  # Les tests seront récupérés via get_tests
            message=result["message"]
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Chat
# =============================================================================
@router.post("/bugs/{bug_id}/chat")
async def send_chat_message(
    bug_id: UUID,
    data: ChatSend,
    request: Request,
    ctx: dict = Depends(get_debug_context),
    _: None = Depends(check_simon_rate_limit)
):
    """Envoie un message dans le chat avec Simon."""
    try:
        return await DebugService.send_chat_message(
            tenant_id=ctx["tenant_id"],
            bug_id=bug_id,
            user_id=ctx["user_id"],
            message=data.message
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/bugs/{bug_id}/chat", response_model=ChatResponse)
async def get_chat_history(
    bug_id: UUID,
    ctx: dict = Depends(get_debug_context)
):
    """Récupère l'historique de conversation."""
    try:
        return await DebugService.get_chat_history(ctx["tenant_id"], bug_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Guardian Errors (Mode Replay)
# =============================================================================
@router.get("/errors", response_model=GuardianErrorListResponse)
async def get_guardian_errors(
    limit: int = 50,
    ctx: dict = Depends(get_debug_context)
):
    """Récupère les erreurs Guardian récentes pour le mode replay."""
    return await DebugService.get_guardian_errors(ctx["tenant_id"], limit)


# =============================================================================
# Stats
# =============================================================================
@router.get("/stats", response_model=DebugStats)
async def get_stats(ctx: dict = Depends(get_debug_context)):
    """Récupère les statistiques du module debug."""
    return await DebugService.get_stats(ctx["tenant_id"])
