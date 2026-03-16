# =============================================================================
# AZALPLUS - Calendar Utilities
# =============================================================================
"""
Utilitaires pour le calcul de charge de travail du calendrier.
Calcule les temps de trajet entre interventions/RDV.
"""

import math
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
import structlog

from .db import Database

logger = structlog.get_logger()

# Cache simple pour les coordonnées géocodées
_geocode_cache: Dict[str, Tuple[float, float]] = {}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance en km entre deux points GPS (formule de Haversine).
    """
    R = 6371  # Rayon de la Terre en km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def estimate_travel_time(distance_km: float, speed_kmh: float = 40) -> int:
    """
    Estime le temps de trajet en minutes.
    Vitesse moyenne par défaut: 40 km/h (milieu urbain/périurbain).
    """
    if distance_km <= 0:
        return 0
    hours = distance_km / speed_kmh
    return max(5, int(hours * 60))  # Minimum 5 minutes


async def geocode_address(address: str, city: str, postal_code: str = "") -> Optional[Tuple[float, float]]:
    """
    Géocode une adresse française via l'API adresse.data.gouv.fr.
    Retourne (latitude, longitude) ou None si échec.
    """
    cache_key = f"{address}|{city}|{postal_code}".lower().strip()

    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    try:
        query = f"{address} {postal_code} {city}".strip()
        if not query or len(query) < 5:
            return None

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api-adresse.data.gouv.fr/search/",
                params={"q": query, "limit": 1}
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("features"):
                    coords = data["features"][0]["geometry"]["coordinates"]
                    result = (coords[1], coords[0])  # [lon, lat] -> (lat, lon)
                    _geocode_cache[cache_key] = result
                    return result
    except Exception as e:
        logger.warning("geocode_error", address=query, error=str(e))

    return None


async def get_company_coordinates(tenant_id: UUID) -> Optional[Tuple[float, float]]:
    """
    Récupère les coordonnées de l'entreprise du tenant.
    """
    try:
        entreprises = Database.query(
            "entreprise",
            tenant_id,
            limit=1
        )

        if entreprises:
            ent = entreprises[0]
            address = ent.get("adresse", "")
            city = ent.get("ville", "")
            postal_code = ent.get("code_postal", "")

            if address and city:
                return await geocode_address(address, city, postal_code)
    except Exception as e:
        logger.warning("get_company_coords_error", error=str(e))

    return None


async def calculate_calendar_workload(
    tenant_id: UUID,
    year: int,
    month: int
) -> Dict[int, Dict[str, Any]]:
    """
    Calcule la charge de travail par jour pour un mois donné.

    Retourne un dict {jour: {total_minutes, travel_minutes, work_minutes, events_count}}

    Logique des temps de trajet:
    - Si événement précédent < 1h avant → trajet depuis lieu précédent
    - Sinon → trajet depuis l'entreprise
    """

    # Dates du mois
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    start_str = start_date.strftime("%Y-%m-%dT00:00:00")
    end_str = end_date.strftime("%Y-%m-%dT00:00:00")

    # Récupérer les coordonnées de l'entreprise
    company_coords = await get_company_coordinates(tenant_id)

    # Récupérer interventions et agenda
    interventions = Database.query(
        "interventions",
        tenant_id,
        filters={
            "date_prevue_debut__gte": start_str,
            "date_prevue_debut__lt": end_str
        },
        limit=500,
        order_by="date_prevue_debut ASC"
    )

    agenda_items = Database.query(
        "agenda",
        tenant_id,
        filters={
            "date_debut__gte": start_str,
            "date_debut__lt": end_str
        },
        limit=500,
        order_by="date_debut ASC"
    )

    # Normaliser les événements
    events = []

    for item in interventions:
        date_str = item.get("date_prevue_debut")
        if not date_str:
            continue

        try:
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00").replace(" ", "T"))
        except:
            continue

        events.append({
            "type": "intervention",
            "datetime": dt,
            "duration_minutes": float(item.get("duree_prevue_minutes") or 60),
            "address": item.get("adresse_ligne1", ""),
            "city": item.get("ville", ""),
            "postal_code": item.get("code_postal", ""),
            "lat": item.get("geoloc_arrivee_lat"),
            "lng": item.get("geoloc_arrivee_lng"),
        })

    for item in agenda_items:
        date_str = item.get("date_debut")
        if not date_str:
            continue

        try:
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00").replace(" ", "T"))
        except:
            continue

        # Calculer durée depuis date_fin si disponible
        duration = 30  # défaut 30 min
        if item.get("date_fin"):
            try:
                end_dt = datetime.fromisoformat(str(item["date_fin"]).replace("Z", "+00:00").replace(" ", "T"))
                duration = max(0, (end_dt - dt).total_seconds() / 60)
            except:
                pass

        events.append({
            "type": "agenda",
            "datetime": dt,
            "duration_minutes": duration,
            "address": item.get("adresse", ""),
            "city": item.get("ville", ""),
            "postal_code": item.get("code_postal", ""),
            "lat": None,
            "lng": None,
        })

    # Trier par datetime
    events.sort(key=lambda x: x["datetime"])

    # Calculer les temps de trajet et agréger par jour
    workload_by_day: Dict[int, Dict[str, Any]] = {}

    for i, event in enumerate(events):
        day = event["datetime"].day

        if day not in workload_by_day:
            workload_by_day[day] = {
                "total_minutes": 0,
                "travel_minutes": 0,
                "work_minutes": 0,
                "events_count": 0
            }

        # Ajouter la durée de travail
        work_duration = event["duration_minutes"]
        workload_by_day[day]["work_minutes"] += work_duration
        workload_by_day[day]["events_count"] += 1

        # Calculer le temps de trajet
        travel_minutes = 0

        # Obtenir les coordonnées de cet événement
        event_coords = None
        if event["lat"] and event["lng"]:
            event_coords = (float(event["lat"]), float(event["lng"]))
        elif event["address"] and event["city"]:
            event_coords = await geocode_address(
                event["address"],
                event["city"],
                event.get("postal_code", "")
            )

        if event_coords:
            # Chercher l'événement précédent
            start_coords = None

            if i > 0:
                prev_event = events[i - 1]
                time_gap = (event["datetime"] - prev_event["datetime"]).total_seconds() / 3600

                # Si moins d'1h depuis le précédent, partir de là
                if time_gap <= 1:
                    if prev_event["lat"] and prev_event["lng"]:
                        start_coords = (float(prev_event["lat"]), float(prev_event["lng"]))
                    elif prev_event["address"] and prev_event["city"]:
                        start_coords = await geocode_address(
                            prev_event["address"],
                            prev_event["city"],
                            prev_event.get("postal_code", "")
                        )

            # Si pas de précédent proche, partir de l'entreprise
            if not start_coords:
                start_coords = company_coords

            # Calculer le trajet
            if start_coords:
                distance = haversine_distance(
                    start_coords[0], start_coords[1],
                    event_coords[0], event_coords[1]
                )
                travel_minutes = estimate_travel_time(distance)

        workload_by_day[day]["travel_minutes"] += travel_minutes
        workload_by_day[day]["total_minutes"] = (
            workload_by_day[day]["work_minutes"] +
            workload_by_day[day]["travel_minutes"]
        )

    return workload_by_day
