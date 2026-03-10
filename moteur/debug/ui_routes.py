# =============================================================================
# AZALPLUS - Debug UI Routes
# =============================================================================
"""
Routes HTML pour l'interface debug.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from uuid import UUID

from ..tenant import TenantContext
from ..config import settings
from .service import DebugService

# Templates
templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter(prefix="/debug", tags=["Debug UI"])


async def require_createur(request: Request):
    """Vérifie que l'utilisateur est le créateur. Accès restreint pour le moment."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")

    # Créateur uniquement
    email = getattr(user, "email", None) or user.get("email")
    if email != settings.CREATEUR_EMAIL:
        raise HTTPException(status_code=403, detail="Accès réservé au créateur")

    return user


@router.get("/", response_class=HTMLResponse)
async def debug_index(request: Request, user=Depends(require_createur)):
    """Dashboard debug."""
    return templates.TemplateResponse("debug/index.html", {"request": request})


@router.get("/new", response_class=HTMLResponse)
async def debug_new(request: Request, user=Depends(require_createur)):
    """Formulaire nouveau bug."""
    return templates.TemplateResponse("debug/new.html", {"request": request})


@router.get("/bugs/{bug_id}", response_class=HTMLResponse)
async def debug_bug_detail(
    request: Request,
    bug_id: UUID,
    user=Depends(require_createur)
):
    """Détail d'un bug."""
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant non défini")

    bug = await DebugService.get_bug(tenant_id, bug_id)
    if not bug:
        raise HTTPException(status_code=404, detail="Bug non trouvé")

    return templates.TemplateResponse("debug/bug_detail.html", {
        "request": request,
        "bug": bug
    })


@router.get("/bugs/{bug_id}/chat", response_class=HTMLResponse)
async def debug_chat(
    request: Request,
    bug_id: UUID,
    user=Depends(require_createur)
):
    """Interface chat avec Simon."""
    tenant_id = TenantContext.get_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant non défini")

    bug = await DebugService.get_bug(tenant_id, bug_id)
    if not bug:
        raise HTTPException(status_code=404, detail="Bug non trouvé")

    return templates.TemplateResponse("debug/chat.html", {
        "request": request,
        "bug": bug
    })


@router.get("/errors", response_class=HTMLResponse)
async def debug_errors(request: Request, user=Depends(require_createur)):
    """Liste des erreurs Guardian (mode replay)."""
    return templates.TemplateResponse("debug/errors.html", {"request": request})
