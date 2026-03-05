# =============================================================================
# AZALPLUS - Portal API for Client Mobile App
# =============================================================================
"""
API REST pour le portail client mobile.
Permet aux clients de consulter leurs documents, accepter des devis,
et suivre leurs interventions via authentification par magic link.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from jose import jwt, JWTError
import secrets
import structlog

from .config import settings
from .db import Database
from .notifications import EmailService

logger = structlog.get_logger()

# =============================================================================
# Router
# =============================================================================
portal_api_router = APIRouter(prefix="/api/portal", tags=["Portal Client"])


# =============================================================================
# Schemas
# =============================================================================
class MagicLinkRequest(BaseModel):
    """Request for magic link login."""
    email: EmailStr


class MagicLinkVerifyRequest(BaseModel):
    """Request to verify magic link token."""
    token: str


class PortalTokenResponse(BaseModel):
    """Response with portal access token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    client_name: str
    client_email: str


class AcceptQuoteRequest(BaseModel):
    """Request to accept or reject a quote."""
    accepted: bool
    comment: Optional[str] = None


class DashboardSummary(BaseModel):
    """Client dashboard summary."""
    invoices_pending: int
    invoices_paid: int
    invoices_total_pending: float
    quotes_pending: int
    quotes_accepted: int
    interventions_planned: int
    interventions_completed: int


class InvoiceSummary(BaseModel):
    """Invoice summary for list view."""
    id: str
    numero: str
    date: Optional[str]
    date_echeance: Optional[str]
    montant_ttc: float
    montant_paye: float
    reste_a_payer: float
    statut: str
    pdf_url: Optional[str] = None


class QuoteSummary(BaseModel):
    """Quote summary for list view."""
    id: str
    numero: str
    date: Optional[str]
    date_validite: Optional[str]
    objet: Optional[str]
    montant_ttc: float
    statut: str


class InterventionSummary(BaseModel):
    """Intervention summary for list view."""
    id: str
    numero: Optional[str]
    date_planifiee: Optional[str]
    heure_debut: Optional[str]
    heure_fin: Optional[str]
    description: Optional[str]
    statut: str
    technicien_nom: Optional[str] = None


# =============================================================================
# Magic Link Token Management
# =============================================================================
MAGIC_LINK_EXPIRE_MINUTES = 15
PORTAL_TOKEN_EXPIRE_HOURS = 24


def create_magic_link_token(client_id: str, tenant_id: str, email: str) -> str:
    """Create a short-lived magic link token."""
    token = secrets.token_urlsafe(32)
    expire = datetime.utcnow() + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)

    payload = {
        "sub": client_id,
        "tenant_id": tenant_id,
        "email": email,
        "type": "magic_link",
        "token": token,
        "exp": expire
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_portal_access_token(client_id: str, tenant_id: str, email: str) -> str:
    """Create a portal access token for authenticated client."""
    expire = datetime.utcnow() + timedelta(hours=PORTAL_TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": client_id,
        "tenant_id": tenant_id,
        "email": email,
        "type": "portal_access",
        "exp": expire
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_portal_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a portal token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            return None

        return payload
    except JWTError:
        return None


# =============================================================================
# Dependencies
# =============================================================================
async def get_portal_client(request: Request) -> Dict[str, Any]:
    """
    Dependency to get authenticated portal client from token.

    Expects Authorization header with Bearer token.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification requis"
        )

    token = auth_header[7:]  # Remove "Bearer " prefix
    payload = decode_portal_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expire"
        )

    if payload.get("type") != "portal_access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Type de token invalide"
        )

    # Verify client still exists and is active
    client_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")

    if not client_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide"
        )

    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("""
                SELECT c.*, t.nom as tenant_nom
                FROM azalplus.clients c
                JOIN azalplus.tenants t ON c.tenant_id = t.id
                WHERE c.id = :client_id
                AND c.tenant_id = :tenant_id
                AND c.deleted_at IS NULL
                AND t.actif = true
            """),
            {"client_id": client_id, "tenant_id": tenant_id}
        )
        client = result.fetchone()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client non trouve"
        )

    return dict(client._mapping)


# =============================================================================
# Auth Routes
# =============================================================================
@portal_api_router.post("/auth/magic-link")
async def request_magic_link(
    data: MagicLinkRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Request a magic link login email.

    Sends an email to the client with a one-time login link.
    """
    email = data.email.lower().strip()

    # Find client by email
    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("""
                SELECT c.id, c.tenant_id, c.nom, c.email, t.nom as tenant_nom
                FROM azalplus.clients c
                JOIN azalplus.tenants t ON c.tenant_id = t.id
                WHERE LOWER(c.email) = :email
                AND c.deleted_at IS NULL
                AND t.actif = true
                LIMIT 1
            """),
            {"email": email}
        )
        client = result.fetchone()

    # Always return success (don't leak whether email exists)
    if not client:
        logger.info("portal_magic_link_unknown_email", email=email[:3] + "***")
        return {"message": "Si un compte existe avec cet email, un lien de connexion sera envoye."}

    client_data = dict(client._mapping)

    # Create magic link token
    magic_token = create_magic_link_token(
        str(client_data["id"]),
        str(client_data["tenant_id"]),
        client_data["email"]
    )

    # Build magic link URL
    base_url = str(request.base_url).rstrip("/")
    # For mobile app, use deep link or web URL
    magic_link_url = f"{base_url}/portal/verify?token={magic_token}"

    # Send email in background
    async def send_magic_link_email():
        try:
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #2563EB 0%, #1d4ed8 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; text-align: center;">
        <h1 style="margin: 0; font-size: 24px;">{client_data.get('tenant_nom', 'AZALPLUS')}</h1>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">Portail Client</p>
    </div>

    <div style="background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
        <p style="margin: 0 0 20px 0;">Bonjour {client_data.get('nom', '')},</p>

        <p style="margin: 0 0 20px 0;">
            Vous avez demande un lien de connexion a votre espace client.
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{magic_link_url}"
               style="display: inline-block; background: #2563EB; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                Me connecter
            </a>
        </div>

        <p style="margin: 0 0 10px 0; color: #666; font-size: 14px;">
            Ce lien est valable pendant {MAGIC_LINK_EXPIRE_MINUTES} minutes.
        </p>

        <p style="margin: 0; color: #666; font-size: 14px;">
            Si vous n'avez pas demande ce lien, ignorez simplement cet email.
        </p>
    </div>

    <div style="background: #1e293b; color: white; padding: 20px; border-radius: 0 0 8px 8px; text-align: center; font-size: 14px;">
        <p style="margin: 0;">{client_data.get('tenant_nom', 'AZALPLUS')}</p>
    </div>
</body>
</html>
            """

            await EmailService.send_email(
                to=client_data["email"],
                subject=f"Connexion a votre espace client - {client_data.get('tenant_nom', 'AZALPLUS')}",
                html_body=html_body,
                text_body=f"Bonjour {client_data.get('nom', '')},\n\nCliquez sur ce lien pour vous connecter: {magic_link_url}\n\nCe lien est valable {MAGIC_LINK_EXPIRE_MINUTES} minutes."
            )

            logger.info("portal_magic_link_sent", email=email[:3] + "***")
        except Exception as e:
            logger.error("portal_magic_link_email_error", error=str(e))

    background_tasks.add_task(send_magic_link_email)

    return {"message": "Si un compte existe avec cet email, un lien de connexion sera envoye."}


@portal_api_router.post("/auth/verify", response_model=PortalTokenResponse)
async def verify_magic_link(data: MagicLinkVerifyRequest):
    """
    Verify a magic link token and return an access token.
    """
    payload = decode_portal_token(data.token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lien invalide ou expire"
        )

    if payload.get("type") != "magic_link":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Type de token invalide"
        )

    client_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    email = payload.get("email")

    # Verify client still exists
    with Database.get_session() as session:
        from sqlalchemy import text
        result = session.execute(
            text("""
                SELECT c.id, c.nom, c.email, t.nom as tenant_nom
                FROM azalplus.clients c
                JOIN azalplus.tenants t ON c.tenant_id = t.id
                WHERE c.id = :client_id
                AND c.tenant_id = :tenant_id
                AND c.deleted_at IS NULL
                AND t.actif = true
            """),
            {"client_id": client_id, "tenant_id": tenant_id}
        )
        client = result.fetchone()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client non trouve"
        )

    client_data = dict(client._mapping)

    # Create access token
    access_token = create_portal_access_token(client_id, tenant_id, email)

    logger.info("portal_client_authenticated", client_id=client_id[:8] + "...")

    return PortalTokenResponse(
        access_token=access_token,
        expires_in=PORTAL_TOKEN_EXPIRE_HOURS * 3600,
        client_name=client_data.get("nom", ""),
        client_email=client_data.get("email", "")
    )


# =============================================================================
# Dashboard Route
# =============================================================================
@portal_api_router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(client: dict = Depends(get_portal_client)):
    """
    Get client dashboard summary.

    Returns counts and totals for invoices, quotes, and interventions.
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        # Invoices stats
        invoices_result = session.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE statut IN ('ENVOYEE', 'PARTIELLE')) as pending,
                    COUNT(*) FILTER (WHERE statut = 'PAYEE') as paid,
                    COALESCE(SUM(total_ttc - COALESCE(montant_paye, 0)) FILTER (WHERE statut IN ('ENVOYEE', 'PARTIELLE')), 0) as total_pending
                FROM azalplus.factures
                WHERE client = :client_id
                AND tenant_id = :tenant_id
                AND deleted_at IS NULL
            """),
            {"client_id": client_id, "tenant_id": tenant_id}
        )
        inv_row = invoices_result.fetchone()

        # Quotes stats
        quotes_result = session.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE statut = 'ENVOYE') as pending,
                    COUNT(*) FILTER (WHERE statut = 'ACCEPTE') as accepted
                FROM azalplus.devis
                WHERE client = :client_id
                AND tenant_id = :tenant_id
                AND deleted_at IS NULL
            """),
            {"client_id": client_id, "tenant_id": tenant_id}
        )
        quote_row = quotes_result.fetchone()

        # Interventions stats
        interventions_result = session.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE statut IN ('PLANIFIEE', 'EN_COURS')) as planned,
                    COUNT(*) FILTER (WHERE statut = 'TERMINEE') as completed
                FROM azalplus.interventions
                WHERE client = :client_id
                AND tenant_id = :tenant_id
                AND deleted_at IS NULL
            """),
            {"client_id": client_id, "tenant_id": tenant_id}
        )
        int_row = interventions_result.fetchone()

    return DashboardSummary(
        invoices_pending=inv_row.pending or 0,
        invoices_paid=inv_row.paid or 0,
        invoices_total_pending=float(inv_row.total_pending or 0),
        quotes_pending=quote_row.pending or 0,
        quotes_accepted=quote_row.accepted or 0,
        interventions_planned=int_row.planned or 0,
        interventions_completed=int_row.completed or 0
    )


# =============================================================================
# Invoices Routes
# =============================================================================
@portal_api_router.get("/invoices")
async def list_invoices(
    client: dict = Depends(get_portal_client),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    List client's invoices.

    Optionally filter by status: ENVOYEE, PARTIELLE, PAYEE, ANNULEE
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        query = """
            SELECT
                id, numero, date, echeance as date_echeance,
                total_ttc as montant_ttc,
                COALESCE(montant_paye, 0) as montant_paye,
                (total_ttc - COALESCE(montant_paye, 0)) as reste_a_payer,
                statut, access_token
            FROM azalplus.factures
            WHERE client = :client_id
            AND tenant_id = :tenant_id
            AND deleted_at IS NULL
        """

        params = {"client_id": client_id, "tenant_id": tenant_id}

        if status:
            query += " AND statut = :status"
            params["status"] = status.upper()

        query += " ORDER BY date DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = session.execute(text(query), params)
        invoices = []

        for row in result:
            row_dict = dict(row._mapping)
            # Format dates
            if row_dict.get("date"):
                row_dict["date"] = row_dict["date"].isoformat() if hasattr(row_dict["date"], "isoformat") else str(row_dict["date"])
            if row_dict.get("date_echeance"):
                row_dict["date_echeance"] = row_dict["date_echeance"].isoformat() if hasattr(row_dict["date_echeance"], "isoformat") else str(row_dict["date_echeance"])

            # Add PDF URL if access token exists
            if row_dict.get("access_token"):
                row_dict["pdf_url"] = f"/portail/facture/{row_dict['access_token']}"

            # Convert UUID to string
            row_dict["id"] = str(row_dict["id"])

            # Remove access_token from response
            row_dict.pop("access_token", None)

            invoices.append(row_dict)

    return {"items": invoices, "total": len(invoices)}


@portal_api_router.get("/invoices/{invoice_id}")
async def get_invoice_detail(
    invoice_id: UUID,
    client: dict = Depends(get_portal_client)
):
    """
    Get detailed invoice information including line items.
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text("""
                SELECT
                    f.*,
                    t.nom as tenant_nom, t.adresse as tenant_adresse,
                    t.email as tenant_email, t.telephone as tenant_telephone,
                    t.siret as tenant_siret
                FROM azalplus.factures f
                JOIN azalplus.tenants t ON f.tenant_id = t.id
                WHERE f.id = :invoice_id
                AND f.client = :client_id
                AND f.tenant_id = :tenant_id
                AND f.deleted_at IS NULL
            """),
            {"invoice_id": str(invoice_id), "client_id": client_id, "tenant_id": tenant_id}
        )
        invoice = result.fetchone()

    if not invoice:
        raise HTTPException(status_code=404, detail="Facture non trouvee")

    invoice_dict = dict(invoice._mapping)

    # Format dates
    for date_field in ["date", "echeance", "created_at", "updated_at"]:
        if invoice_dict.get(date_field) and hasattr(invoice_dict[date_field], "isoformat"):
            invoice_dict[date_field] = invoice_dict[date_field].isoformat()

    # Convert UUIDs to strings
    for uuid_field in ["id", "tenant_id", "client", "created_by", "updated_by"]:
        if invoice_dict.get(uuid_field):
            invoice_dict[uuid_field] = str(invoice_dict[uuid_field])

    # Add PDF URL
    if invoice_dict.get("access_token"):
        invoice_dict["pdf_url"] = f"/portail/facture/{invoice_dict['access_token']}"

    return invoice_dict


# =============================================================================
# Quotes Routes
# =============================================================================
@portal_api_router.get("/quotes")
async def list_quotes(
    client: dict = Depends(get_portal_client),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    List client's quotes.

    Optionally filter by status: BROUILLON, ENVOYE, ACCEPTE, REFUSE, EXPIRE
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        query = """
            SELECT
                id, numero, date, validite as date_validite,
                objet, total_ttc as montant_ttc, statut, access_token
            FROM azalplus.devis
            WHERE client = :client_id
            AND tenant_id = :tenant_id
            AND deleted_at IS NULL
        """

        params = {"client_id": client_id, "tenant_id": tenant_id}

        if status:
            query += " AND statut = :status"
            params["status"] = status.upper()

        query += " ORDER BY date DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = session.execute(text(query), params)
        quotes = []

        for row in result:
            row_dict = dict(row._mapping)
            # Format dates
            if row_dict.get("date"):
                row_dict["date"] = row_dict["date"].isoformat() if hasattr(row_dict["date"], "isoformat") else str(row_dict["date"])
            if row_dict.get("date_validite"):
                row_dict["date_validite"] = row_dict["date_validite"].isoformat() if hasattr(row_dict["date_validite"], "isoformat") else str(row_dict["date_validite"])

            # Add view URL if access token exists
            if row_dict.get("access_token"):
                row_dict["view_url"] = f"/portail/devis/{row_dict['access_token']}"

            # Convert UUID to string
            row_dict["id"] = str(row_dict["id"])

            # Remove access_token from response
            row_dict.pop("access_token", None)

            quotes.append(row_dict)

    return {"items": quotes, "total": len(quotes)}


@portal_api_router.get("/quotes/{quote_id}")
async def get_quote_detail(
    quote_id: UUID,
    client: dict = Depends(get_portal_client)
):
    """
    Get detailed quote information including line items.
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text("""
                SELECT
                    d.*,
                    t.nom as tenant_nom, t.adresse as tenant_adresse,
                    t.email as tenant_email, t.telephone as tenant_telephone,
                    t.siret as tenant_siret
                FROM azalplus.devis d
                JOIN azalplus.tenants t ON d.tenant_id = t.id
                WHERE d.id = :quote_id
                AND d.client = :client_id
                AND d.tenant_id = :tenant_id
                AND d.deleted_at IS NULL
            """),
            {"quote_id": str(quote_id), "client_id": client_id, "tenant_id": tenant_id}
        )
        quote = result.fetchone()

    if not quote:
        raise HTTPException(status_code=404, detail="Devis non trouve")

    quote_dict = dict(quote._mapping)

    # Format dates
    for date_field in ["date", "validite", "created_at", "updated_at"]:
        if quote_dict.get(date_field) and hasattr(quote_dict[date_field], "isoformat"):
            quote_dict[date_field] = quote_dict[date_field].isoformat()

    # Convert UUIDs to strings
    for uuid_field in ["id", "tenant_id", "client", "created_by", "updated_by"]:
        if quote_dict.get(uuid_field):
            quote_dict[uuid_field] = str(quote_dict[uuid_field])

    # Add view URL
    if quote_dict.get("access_token"):
        quote_dict["view_url"] = f"/portail/devis/{quote_dict['access_token']}"

    # Check if quote can be accepted
    quote_dict["can_accept"] = quote_dict.get("statut") == "ENVOYE"

    return quote_dict


@portal_api_router.post("/quotes/{quote_id}/accept")
async def accept_quote(
    quote_id: UUID,
    data: AcceptQuoteRequest,
    client: dict = Depends(get_portal_client)
):
    """
    Accept or reject a quote.
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        # Verify quote exists and belongs to client
        result = session.execute(
            text("""
                SELECT id, statut, numero
                FROM azalplus.devis
                WHERE id = :quote_id
                AND client = :client_id
                AND tenant_id = :tenant_id
                AND deleted_at IS NULL
            """),
            {"quote_id": str(quote_id), "client_id": client_id, "tenant_id": tenant_id}
        )
        quote = result.fetchone()

        if not quote:
            raise HTTPException(status_code=404, detail="Devis non trouve")

        quote_data = dict(quote._mapping)

        # Check if quote can be accepted
        if quote_data["statut"] != "ENVOYE":
            raise HTTPException(
                status_code=400,
                detail="Ce devis ne peut plus etre modifie"
            )

        # Update quote status
        new_status = "ACCEPTE" if data.accepted else "REFUSE"

        session.execute(
            text("""
                UPDATE azalplus.devis
                SET statut = :status,
                    updated_at = NOW()
                WHERE id = :quote_id AND tenant_id = :tenant_id
            """),
            {"status": new_status, "quote_id": str(quote_id), "tenant_id": tenant_id}
        )
        session.commit()

    logger.info(
        "portal_quote_response",
        quote_id=str(quote_id)[:8] + "...",
        accepted=data.accepted
    )

    return {
        "success": True,
        "message": "Devis accepte" if data.accepted else "Devis refuse",
        "new_status": new_status
    }


# =============================================================================
# Interventions Routes
# =============================================================================
@portal_api_router.get("/interventions")
async def list_interventions(
    client: dict = Depends(get_portal_client),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    List client's interventions.

    Optionally filter by status: PLANIFIEE, EN_COURS, TERMINEE, ANNULEE
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        query = """
            SELECT
                i.id, i.numero, i.date_planifiee, i.heure_debut, i.heure_fin,
                i.description, i.statut,
                u.nom || ' ' || COALESCE(u.prenom, '') as technicien_nom
            FROM azalplus.interventions i
            LEFT JOIN azalplus.utilisateurs u ON i.technicien = u.id
            WHERE i.client = :client_id
            AND i.tenant_id = :tenant_id
            AND i.deleted_at IS NULL
        """

        params = {"client_id": client_id, "tenant_id": tenant_id}

        if status:
            query += " AND i.statut = :status"
            params["status"] = status.upper()

        query += " ORDER BY i.date_planifiee DESC NULLS LAST LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = session.execute(text(query), params)
        interventions = []

        for row in result:
            row_dict = dict(row._mapping)

            # Format dates
            if row_dict.get("date_planifiee"):
                row_dict["date_planifiee"] = row_dict["date_planifiee"].isoformat() if hasattr(row_dict["date_planifiee"], "isoformat") else str(row_dict["date_planifiee"])

            # Format times
            if row_dict.get("heure_debut"):
                row_dict["heure_debut"] = str(row_dict["heure_debut"])
            if row_dict.get("heure_fin"):
                row_dict["heure_fin"] = str(row_dict["heure_fin"])

            # Convert UUID to string
            row_dict["id"] = str(row_dict["id"])

            interventions.append(row_dict)

    return {"items": interventions, "total": len(interventions)}


@portal_api_router.get("/interventions/{intervention_id}")
async def get_intervention_detail(
    intervention_id: UUID,
    client: dict = Depends(get_portal_client)
):
    """
    Get detailed intervention information.
    """
    client_id = str(client["id"])
    tenant_id = str(client["tenant_id"])

    with Database.get_session() as session:
        from sqlalchemy import text

        result = session.execute(
            text("""
                SELECT
                    i.*,
                    u.nom as technicien_nom, u.prenom as technicien_prenom,
                    u.email as technicien_email, u.telephone as technicien_telephone,
                    t.nom as tenant_nom
                FROM azalplus.interventions i
                LEFT JOIN azalplus.utilisateurs u ON i.technicien = u.id
                JOIN azalplus.tenants t ON i.tenant_id = t.id
                WHERE i.id = :intervention_id
                AND i.client = :client_id
                AND i.tenant_id = :tenant_id
                AND i.deleted_at IS NULL
            """),
            {"intervention_id": str(intervention_id), "client_id": client_id, "tenant_id": tenant_id}
        )
        intervention = result.fetchone()

    if not intervention:
        raise HTTPException(status_code=404, detail="Intervention non trouvee")

    intervention_dict = dict(intervention._mapping)

    # Format dates
    for date_field in ["date_planifiee", "date_realisation", "created_at", "updated_at"]:
        if intervention_dict.get(date_field) and hasattr(intervention_dict[date_field], "isoformat"):
            intervention_dict[date_field] = intervention_dict[date_field].isoformat()

    # Format times
    for time_field in ["heure_debut", "heure_fin"]:
        if intervention_dict.get(time_field):
            intervention_dict[time_field] = str(intervention_dict[time_field])

    # Convert UUIDs to strings
    for uuid_field in ["id", "tenant_id", "client", "technicien", "created_by", "updated_by"]:
        if intervention_dict.get(uuid_field):
            intervention_dict[uuid_field] = str(intervention_dict[uuid_field])

    return intervention_dict


# =============================================================================
# Client Profile Route
# =============================================================================
@portal_api_router.get("/profile")
async def get_profile(client: dict = Depends(get_portal_client)):
    """
    Get client profile information.
    """
    # Return safe client data (no internal fields)
    return {
        "id": str(client["id"]),
        "nom": client.get("nom"),
        "email": client.get("email"),
        "telephone": client.get("telephone"),
        "adresse": client.get("adresse"),
        "code_postal": client.get("code_postal"),
        "ville": client.get("ville"),
        "pays": client.get("pays"),
        "tenant_nom": client.get("tenant_nom")
    }
