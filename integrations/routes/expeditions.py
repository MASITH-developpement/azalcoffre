# =============================================================================
# AZALPLUS - Routes API Expéditions (Multi-transporteurs)
# =============================================================================
"""
Routes pour les expéditions multi-transporteurs.

Endpoints:
    POST /api/expeditions/rates         - Comparer les tarifs
    POST /api/expeditions/create        - Créer une expédition
    GET  /api/expeditions/{id}          - Détails expédition
    GET  /api/expeditions/{id}/tracking - Suivi colis
    GET  /api/expeditions/{id}/label    - Télécharger étiquette
    GET  /api/expeditions/pickup-points - Points relais
    DELETE /api/expeditions/{id}        - Annuler expédition
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io

from integrations.settings import get_settings, Settings
from integrations.transporteurs import (
    TransporteurFactory,
    ExpeditionService,
    Address,
    Parcel,
    Carrier,
    ShipmentStatus,
    CarrierError,
    ColissimoClient,
    MondialRelayClient
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/expeditions", tags=["expeditions"])


# =============================================================================
# Modèles Pydantic
# =============================================================================

class AddressModel(BaseModel):
    """Adresse d'expédition."""
    name: str = Field(..., min_length=1)
    company: str = ""
    street1: str = Field(..., min_length=1)
    street2: str = ""
    city: str = Field(..., min_length=1)
    postal_code: str = Field(..., min_length=5, max_length=10)
    country: str = Field("FR", min_length=2, max_length=2)
    phone: str = ""
    email: str = ""

    def to_address(self) -> Address:
        return Address(
            name=self.name,
            company=self.company,
            street1=self.street1,
            street2=self.street2,
            city=self.city,
            postal_code=self.postal_code,
            country=self.country,
            phone=self.phone,
            email=self.email
        )


class ParcelModel(BaseModel):
    """Colis à expédier."""
    weight: float = Field(..., gt=0, description="Poids en kg")
    length: float = Field(0, ge=0, description="Longueur en cm")
    width: float = Field(0, ge=0, description="Largeur en cm")
    height: float = Field(0, ge=0, description="Hauteur en cm")
    value: float = Field(0, ge=0, description="Valeur déclarée en EUR")
    description: str = ""

    def to_parcel(self) -> Parcel:
        return Parcel(
            weight=self.weight,
            length=self.length,
            width=self.width,
            height=self.height,
            value=self.value,
            description=self.description
        )


class RatesRequest(BaseModel):
    """Requête comparaison tarifs."""
    sender: AddressModel
    recipient: AddressModel
    parcels: list[ParcelModel] = Field(..., min_length=1)


class ShipmentRate(BaseModel):
    """Tarif d'expédition."""
    carrier: str
    service: str
    price: float
    currency: str = "EUR"
    delivery_days: int
    delivery_date: Optional[str] = None
    pickup_available: bool = False


class CreateShipmentRequest(BaseModel):
    """Requête création expédition."""
    sender: AddressModel
    recipient: AddressModel
    parcels: list[ParcelModel] = Field(..., min_length=1)
    carrier: str = Field(..., description="colissimo, chronopost, mondial_relay, etc.")
    service: str = Field(..., description="Code service transporteur")
    pickup_point_id: Optional[str] = Field(None, description="ID point relais")
    commande_id: Optional[UUID] = Field(None, description="Lier à une commande")


class ShipmentResponse(BaseModel):
    """Réponse création expédition."""
    shipment_id: str
    tracking_number: str
    carrier: str
    service: str
    label_url: Optional[str] = None
    status: str


class TrackingEvent(BaseModel):
    """Événement de suivi."""
    timestamp: str
    status: str
    location: str
    description: str
    carrier_status: str = ""


class PickupPoint(BaseModel):
    """Point relais."""
    id: str
    name: str
    address: str
    city: str
    postal_code: str
    hours: dict = {}
    distance: Optional[float] = None


# =============================================================================
# Dépendances
# =============================================================================

def get_carrier_factory(settings: Settings = Depends(get_settings)) -> TransporteurFactory:
    """Créer la factory des transporteurs configurés."""
    factory = TransporteurFactory()

    if settings.transporteurs.colissimo.is_configured:
        factory.register_colissimo(settings.transporteurs.colissimo.to_config())

    if settings.transporteurs.mondial_relay.is_configured:
        factory.register_mondial_relay(settings.transporteurs.mondial_relay.to_config())

    # Chronopost nécessite SOAP, pas encore implémenté
    # if settings.transporteurs.chronopost.is_configured:
    #     factory.register_chronopost(settings.transporteurs.chronopost.to_config())

    return factory


# =============================================================================
# Routes Tarifs
# =============================================================================

@router.post("/rates", response_model=list[ShipmentRate])
async def get_shipping_rates(
    request: RatesRequest,
    factory: TransporteurFactory = Depends(get_carrier_factory)
):
    """
    Comparer les tarifs de tous les transporteurs configurés.

    Retourne les tarifs triés par prix croissant.
    Inclut le délai de livraison estimé.
    """
    try:
        sender = request.sender.to_address()
        recipient = request.recipient.to_address()
        parcels = [p.to_parcel() for p in request.parcels]

        rates = await factory.get_all_rates(sender, recipient, parcels)

        return [
            ShipmentRate(
                carrier=r.carrier.value,
                service=r.service,
                price=r.price,
                currency=r.currency,
                delivery_days=r.delivery_days,
                delivery_date=r.delivery_date.isoformat() if r.delivery_date else None,
                pickup_available=r.pickup_available
            )
            for r in rates
        ]

    except CarrierError as e:
        logger.error(f"Erreur tarifs: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await factory.close_all()


@router.get("/rates/commande/{commande_id}", response_model=list[ShipmentRate])
async def get_order_shipping_rates(
    commande_id: UUID,
    settings: Settings = Depends(get_settings)
):
    """
    Récupérer les tarifs d'expédition pour une commande.

    Utilise les adresses et poids de la commande pour calculer les tarifs.
    """
    # TODO: Injecter DB
    service = ExpeditionService(db=None, tenant_id=UUID("00000000-0000-0000-0000-000000000000"))

    try:
        rates = await service.get_shipping_rates(commande_id)

        return [
            ShipmentRate(
                carrier=r.carrier.value,
                service=r.service,
                price=r.price,
                currency=r.currency,
                delivery_days=r.delivery_days,
                pickup_available=r.pickup_available
            )
            for r in rates
        ]

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Routes Expéditions
# =============================================================================

@router.post("/create", response_model=ShipmentResponse)
async def create_shipment(
    request: CreateShipmentRequest,
    factory: TransporteurFactory = Depends(get_carrier_factory)
):
    """
    Créer une expédition et générer l'étiquette.

    L'étiquette est générée automatiquement et disponible via /label.
    Le numéro de suivi est immédiatement utilisable.
    """
    try:
        # Valider le transporteur
        try:
            carrier = Carrier(request.carrier.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Transporteur inconnu: {request.carrier}. "
                       f"Disponibles: {[c.value for c in Carrier]}"
            )

        sender = request.sender.to_address()
        recipient = request.recipient.to_address()
        parcels = [p.to_parcel() for p in request.parcels]

        label = await factory.create_shipment(
            carrier=carrier,
            sender=sender,
            recipient=recipient,
            parcels=parcels,
            service=request.service
        )

        # TODO: Sauvegarder en base avec commande_id si fourni

        return ShipmentResponse(
            shipment_id=label.tracking_number,  # Utiliser tracking comme ID
            tracking_number=label.tracking_number,
            carrier=carrier.value,
            service=request.service,
            label_url=label.label_url or f"/api/expeditions/{label.tracking_number}/label",
            status=ShipmentStatus.LABEL_GENERATED.value
        )

    except CarrierError as e:
        logger.error(f"Erreur création expédition: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await factory.close_all()


@router.post("/commande/{commande_id}/ship", response_model=ShipmentResponse)
async def ship_order(
    commande_id: UUID,
    carrier: str = Query(..., description="Transporteur"),
    service: str = Query(..., description="Service"),
    pickup_point_id: Optional[str] = Query(None, description="Point relais"),
    settings: Settings = Depends(get_settings)
):
    """
    Créer une expédition pour une commande existante.

    Récupère automatiquement les adresses et articles de la commande.
    Met à jour le statut de la commande à "EXPEDIEE".
    """
    # TODO: Injecter DB
    service_exp = ExpeditionService(db=None, tenant_id=UUID("00000000-0000-0000-0000-000000000000"))

    try:
        result = await service_exp.create_expedition(
            commande_id=commande_id,
            carrier=Carrier(carrier.lower()),
            service=service,
            pickup_point_id=pickup_point_id
        )

        return ShipmentResponse(
            shipment_id=str(result["expedition_id"]),
            tracking_number=result["tracking_number"],
            carrier=result["carrier"],
            service=service,
            label_url=result.get("label_url"),
            status=ShipmentStatus.LABEL_GENERATED.value
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CarrierError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Routes Suivi
# =============================================================================

@router.get("/{tracking_number}/tracking", response_model=list[TrackingEvent])
async def get_tracking(
    tracking_number: str,
    carrier: str = Query(..., description="Transporteur"),
    factory: TransporteurFactory = Depends(get_carrier_factory)
):
    """
    Récupérer le suivi d'un colis.

    Retourne tous les événements de suivi dans l'ordre chronologique inverse.
    """
    try:
        carrier_enum = Carrier(carrier.lower())
        events = await factory.get_tracking(carrier_enum, tracking_number)

        return [
            TrackingEvent(
                timestamp=e.timestamp.isoformat(),
                status=e.status.value,
                location=e.location,
                description=e.description,
                carrier_status=e.carrier_status
            )
            for e in events
        ]

    except CarrierError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await factory.close_all()


@router.get("/{tracking_number}")
async def get_shipment_details(
    tracking_number: str
):
    """
    Récupérer les détails d'une expédition.

    Inclut les informations de l'envoi et le dernier statut.
    """
    # TODO: Récupérer depuis la DB
    return {
        "tracking_number": tracking_number,
        "status": "unknown",
        "message": "Implémentation en cours - récupérer depuis la base de données"
    }


@router.get("/{tracking_number}/label")
async def download_label(
    tracking_number: str
):
    """
    Télécharger l'étiquette d'expédition.

    Format: PDF A4 ou étiquette 10x15cm selon le transporteur.
    """
    # TODO: Récupérer le label depuis la DB ou le transporteur

    # Pour l'exemple, retourner une erreur
    raise HTTPException(
        status_code=404,
        detail="Étiquette non trouvée. L'étiquette peut avoir été générée en base64 lors de la création."
    )


# =============================================================================
# Routes Points Relais
# =============================================================================

@router.get("/pickup-points", response_model=list[PickupPoint])
async def get_pickup_points(
    postal_code: str = Query(..., description="Code postal"),
    country: str = Query("FR", description="Code pays"),
    carrier: str = Query("mondial_relay", description="Transporteur"),
    limit: int = Query(10, ge=1, le=20),
    settings: Settings = Depends(get_settings)
):
    """
    Rechercher les points relais proches.

    Actuellement supporté: Mondial Relay
    Retourne les points triés par distance.
    """
    if carrier.lower() != "mondial_relay":
        raise HTTPException(
            status_code=400,
            detail="Points relais uniquement disponibles pour Mondial Relay"
        )

    if not settings.transporteurs.mondial_relay.is_configured:
        raise HTTPException(status_code=503, detail="Mondial Relay non configuré")

    try:
        client = MondialRelayClient(settings.transporteurs.mondial_relay.to_config())
        points = await client.get_pickup_points(postal_code, country, limit)
        await client.close()

        return [
            PickupPoint(
                id=p["id"],
                name=p["name"],
                address=p["address"],
                city=p["city"],
                postal_code=p["postal_code"],
                hours=p.get("hours", {}),
                distance=p.get("distance")
            )
            for p in points
        ]

    except CarrierError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Routes Annulation
# =============================================================================

@router.delete("/{tracking_number}")
async def cancel_shipment(
    tracking_number: str,
    carrier: str = Query(..., description="Transporteur"),
    factory: TransporteurFactory = Depends(get_carrier_factory)
):
    """
    Annuler une expédition.

    Note: L'annulation n'est possible que si le colis n'a pas encore été
    déposé chez le transporteur. Certains transporteurs ne supportent pas
    l'annulation via API.
    """
    try:
        carrier_enum = Carrier(carrier.lower())
        client = factory.get_client(carrier_enum)

        if not client:
            raise HTTPException(
                status_code=400,
                detail=f"Transporteur {carrier} non configuré"
            )

        success = await client.cancel_shipment(tracking_number)

        if success:
            return {"status": "cancelled", "tracking_number": tracking_number}
        else:
            raise HTTPException(
                status_code=400,
                detail="Annulation impossible. Le colis a peut-être déjà été déposé."
            )

    except CarrierError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await factory.close_all()


# =============================================================================
# Routes Configuration
# =============================================================================

@router.get("/carriers")
async def get_configured_carriers(settings: Settings = Depends(get_settings)):
    """
    Liste des transporteurs configurés.
    """
    carriers = []

    if settings.transporteurs.colissimo.is_configured:
        carriers.append({
            "id": "colissimo",
            "name": "Colissimo",
            "logo": "https://www.colissimo.fr/img/logo.svg",
            "services": ["DOM", "DOS", "BPR", "A2P"],
            "pickup_points": False
        })

    if settings.transporteurs.chronopost.is_configured:
        carriers.append({
            "id": "chronopost",
            "name": "Chronopost",
            "logo": "https://www.chronopost.fr/img/logo.svg",
            "services": ["01", "02", "16"],
            "pickup_points": True
        })

    if settings.transporteurs.mondial_relay.is_configured:
        carriers.append({
            "id": "mondial_relay",
            "name": "Mondial Relay",
            "logo": "https://www.mondialrelay.fr/img/logo.svg",
            "services": ["24R"],
            "pickup_points": True
        })

    return {
        "carriers": carriers,
        "count": len(carriers)
    }


@router.get("/stats")
async def get_expedition_stats(
    period: str = Query("month", description="day, week, month, year")
):
    """
    Statistiques des expéditions.

    Retourne:
    - Nombre d'expéditions par transporteur
    - Coût moyen
    - Délai moyen de livraison
    """
    # TODO: Implémenter avec la DB
    return {
        "period": period,
        "total_shipments": 0,
        "by_carrier": {},
        "average_cost": 0,
        "average_delivery_days": 0,
        "delivery_success_rate": 0
    }
