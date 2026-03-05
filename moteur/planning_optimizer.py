# =============================================================================
# AZALPLUS - Optimisation Planning RDV/Interventions
# =============================================================================
"""
Service d'optimisation des plannings basé sur:
- Temps de trajet entre les points
- Horaires de travail des employés
- Disponibilités existantes
"""

import math
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Any
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth import require_auth
from .tenant import get_current_tenant
from .db import Database

logger = structlog.get_logger()

router = APIRouter(prefix="/api/planning", tags=["Planning"])


# =============================================================================
# Models
# =============================================================================

class TimeSlot(BaseModel):
    """Créneau horaire disponible."""
    start: datetime
    end: datetime
    score: float = 0.0  # Score d'optimisation (plus haut = meilleur)
    travel_time_before: int = 0  # Temps trajet avant en minutes
    travel_time_after: int = 0  # Temps trajet après en minutes
    reason: str = ""  # Explication du score


class OptimizationRequest(BaseModel):
    """Requête d'optimisation."""
    collaborateur_id: Optional[str] = None
    date_souhaitee: Optional[str] = None  # YYYY-MM-DD
    duree_minutes: int = 60
    adresse_rdv: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    type_event: str = "RDV"  # RDV, REUNION, INTERVENTION


class OptimizationResponse(BaseModel):
    """Réponse d'optimisation."""
    slots: List[TimeSlot]
    collaborateur_id: Optional[str] = None
    collaborateur_nom: Optional[str] = None
    message: str = ""


# =============================================================================
# Helpers
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance en km entre deux points GPS."""
    R = 6371  # Rayon de la Terre en km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


def estimate_travel_time(distance_km: float, mode: str = "car") -> int:
    """Estime le temps de trajet en minutes."""
    # Vitesse moyenne selon le mode
    speeds = {
        "car": 40,  # km/h en ville/périurbain
        "walk": 5,
        "bike": 15,
        "transit": 25
    }
    speed = speeds.get(mode, 40)

    # Temps en minutes + 10 min de marge
    travel_time = (distance_km / speed) * 60 + 10
    return int(travel_time)


def parse_time(time_str: str) -> time:
    """Parse une heure au format HH:MM."""
    try:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except:
        return time(9, 0)


def get_working_days(jours_str: str) -> List[int]:
    """Parse les jours travaillés."""
    try:
        return [int(j.strip()) for j in jours_str.split(",")]
    except:
        return [1, 2, 3, 4, 5]  # Lun-Ven par défaut


# =============================================================================
# Service
# =============================================================================

async def get_employee_schedule(
    tenant_id: UUID,
    collaborateur_id: str
) -> Dict[str, Any]:
    """Récupère les horaires d'un employé."""

    employee = await Database.get_by_id("employes", tenant_id, collaborateur_id)

    if not employee:
        return {
            "heure_debut": time(9, 0),
            "heure_fin": time(18, 0),
            "pause_debut": time(12, 0),
            "pause_fin": time(14, 0),
            "jours_travail": [1, 2, 3, 4, 5],
            "latitude": None,
            "longitude": None
        }

    return {
        "heure_debut": parse_time(employee.get("heure_debut", "09:00")),
        "heure_fin": parse_time(employee.get("heure_fin", "18:00")),
        "pause_debut": parse_time(employee.get("pause_dejeuner_debut", "12:00")),
        "pause_fin": parse_time(employee.get("pause_dejeuner_fin", "14:00")),
        "jours_travail": get_working_days(employee.get("jours_travail", "1,2,3,4,5")),
        "latitude": employee.get("latitude_depart"),
        "longitude": employee.get("longitude_depart"),
        "nom": f"{employee.get('prenom', '')} {employee.get('nom', '')}".strip()
    }


async def get_existing_events(
    tenant_id: UUID,
    collaborateur_id: str,
    date_start: datetime,
    date_end: datetime
) -> List[Dict]:
    """Récupère les événements existants (agenda + interventions)."""

    events = []

    # Agenda
    try:
        agenda_items = await Database.query(
            "agenda", tenant_id,
            filters={
                "collaborateur_id": collaborateur_id,
                "date_debut__gte": date_start.isoformat(),
                "date_debut__lte": date_end.isoformat(),
                "statut__ne": "ANNULE"
            }
        )
        for item in agenda_items.get("items", []):
            events.append({
                "start": datetime.fromisoformat(item["date_debut"]) if item.get("date_debut") else None,
                "end": datetime.fromisoformat(item["date_fin"]) if item.get("date_fin") else None,
                "type": "agenda",
                "lieu": item.get("adresse"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude")
            })
    except Exception as e:
        logger.debug("agenda_query_error", error=str(e))

    # Interventions
    try:
        interventions = await Database.query(
            "interventions", tenant_id,
            filters={
                "technicien_id": collaborateur_id,
                "date_prevue__gte": date_start.isoformat(),
                "date_prevue__lte": date_end.isoformat(),
                "statut__nin": ["ANNULEE", "TERMINEE"]
            }
        )
        for item in interventions.get("items", []):
            start = datetime.fromisoformat(item["date_prevue"]) if item.get("date_prevue") else None
            duration = item.get("duree_estimee", 60)
            events.append({
                "start": start,
                "end": start + timedelta(minutes=duration) if start else None,
                "type": "intervention",
                "lieu": item.get("adresse"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude")
            })
    except Exception as e:
        logger.debug("interventions_query_error", error=str(e))

    # Réunions
    try:
        reunions = await Database.query(
            "reunions", tenant_id,
            filters={
                "organisateur_id": collaborateur_id,
                "date_debut__gte": date_start.isoformat(),
                "date_debut__lte": date_end.isoformat(),
                "statut__ne": "ANNULEE"
            }
        )
        for item in reunions.get("items", []):
            events.append({
                "start": datetime.fromisoformat(item["date_debut"]) if item.get("date_debut") else None,
                "end": datetime.fromisoformat(item["date_fin"]) if item.get("date_fin") else None,
                "type": "reunion"
            })
    except Exception as e:
        logger.debug("reunions_query_error", error=str(e))

    # Filtrer les événements valides
    events = [e for e in events if e.get("start")]

    return sorted(events, key=lambda x: x["start"])


def find_available_slots(
    schedule: Dict,
    events: List[Dict],
    target_date: datetime,
    duration_minutes: int,
    rdv_lat: Optional[float] = None,
    rdv_lon: Optional[float] = None
) -> List[TimeSlot]:
    """Trouve les créneaux disponibles optimisés."""

    slots = []

    # Vérifier si c'est un jour travaillé
    weekday = target_date.isoweekday()
    if weekday not in schedule["jours_travail"]:
        return []

    # Définir les plages horaires de la journée
    day_start = datetime.combine(target_date.date(), schedule["heure_debut"])
    day_end = datetime.combine(target_date.date(), schedule["heure_fin"])
    pause_start = datetime.combine(target_date.date(), schedule["pause_debut"])
    pause_end = datetime.combine(target_date.date(), schedule["pause_fin"])

    # Événements du jour
    day_events = [e for e in events if e["start"].date() == target_date.date()]

    # Créer les créneaux potentiels (toutes les 30 min)
    current = day_start
    duration = timedelta(minutes=duration_minutes)

    while current + duration <= day_end:
        slot_end = current + duration

        # Skip si pendant la pause déjeuner
        if current < pause_end and slot_end > pause_start:
            current = pause_end
            continue

        # Vérifier les conflits avec événements existants
        has_conflict = False
        prev_event = None
        next_event = None

        for event in day_events:
            event_end = event.get("end") or (event["start"] + timedelta(hours=1))

            # Conflit direct
            if current < event_end and slot_end > event["start"]:
                has_conflict = True
                break

            # Événement précédent
            if event_end <= current:
                if not prev_event or event_end > prev_event.get("end", event["start"]):
                    prev_event = event

            # Événement suivant
            if event["start"] >= slot_end:
                if not next_event or event["start"] < next_event["start"]:
                    next_event = event

        if not has_conflict:
            # Calculer le score et les temps de trajet
            score = 100.0
            travel_before = 0
            travel_after = 0
            reasons = []

            # Bonus/malus selon l'heure
            hour = current.hour
            if 9 <= hour <= 11:
                score += 10
                reasons.append("Créneau matinée optimal")
            elif 14 <= hour <= 16:
                score += 5
                reasons.append("Créneau après-midi")
            elif hour < 9 or hour >= 17:
                score -= 20
                reasons.append("Horaire limite")

            # Calcul temps de trajet si coordonnées fournies
            if rdv_lat and rdv_lon:
                # Trajet depuis événement précédent ou point de départ
                if prev_event and prev_event.get("latitude") and prev_event.get("longitude"):
                    dist = haversine_distance(
                        prev_event["latitude"], prev_event["longitude"],
                        rdv_lat, rdv_lon
                    )
                    travel_before = estimate_travel_time(dist)

                    # Vérifier qu'on a le temps d'arriver
                    prev_end = prev_event.get("end") or (prev_event["start"] + timedelta(hours=1))
                    available_travel = (current - prev_end).total_seconds() / 60

                    if available_travel < travel_before:
                        score -= 30
                        reasons.append(f"Trajet serré ({travel_before} min)")
                    else:
                        score += 10
                        reasons.append(f"Temps trajet OK ({travel_before} min)")

                elif schedule.get("latitude") and schedule.get("longitude"):
                    dist = haversine_distance(
                        schedule["latitude"], schedule["longitude"],
                        rdv_lat, rdv_lon
                    )
                    travel_before = estimate_travel_time(dist)
                    reasons.append(f"Depuis base ({travel_before} min)")

                # Trajet vers événement suivant
                if next_event and next_event.get("latitude") and next_event.get("longitude"):
                    dist = haversine_distance(
                        rdv_lat, rdv_lon,
                        next_event["latitude"], next_event["longitude"]
                    )
                    travel_after = estimate_travel_time(dist)

                    available_travel = (next_event["start"] - slot_end).total_seconds() / 60

                    if available_travel < travel_after:
                        score -= 30
                        reasons.append(f"Trajet suivant serré")
                    else:
                        score += 5

            # Bonus si créneau proche d'autres événements (optimisation tournée)
            if prev_event:
                gap_before = (current - (prev_event.get("end") or prev_event["start"])).total_seconds() / 60
                if gap_before < 60:
                    score += 15
                    reasons.append("Enchainement optimal")

            slots.append(TimeSlot(
                start=current,
                end=slot_end,
                score=max(0, min(100, score)),
                travel_time_before=travel_before,
                travel_time_after=travel_after,
                reason=" | ".join(reasons) if reasons else "Créneau disponible"
            ))

        current += timedelta(minutes=30)

    # Trier par score décroissant
    slots.sort(key=lambda x: x.score, reverse=True)

    return slots[:10]  # Top 10 créneaux


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_planning(
    request: OptimizationRequest,
    user: dict = Depends(require_auth),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """
    Propose des créneaux optimisés pour un RDV/intervention.

    Prend en compte:
    - Horaires de travail du collaborateur
    - Événements existants (agenda, interventions, réunions)
    - Temps de trajet entre les points
    """

    # Déterminer le collaborateur
    collab_id = request.collaborateur_id or user.get("id")

    if not collab_id:
        raise HTTPException(status_code=400, detail="Collaborateur non spécifié")

    # Récupérer les horaires
    schedule = await get_employee_schedule(tenant_id, collab_id)

    # Déterminer la date cible
    if request.date_souhaitee:
        try:
            target_date = datetime.strptime(request.date_souhaitee, "%Y-%m-%d")
        except:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    # Si la date est passée, prendre demain
    if target_date.date() < datetime.now().date():
        target_date = datetime.now()

    # Chercher sur plusieurs jours si nécessaire
    all_slots = []
    search_date = target_date

    for _ in range(7):  # Chercher sur 7 jours max
        # Récupérer les événements
        day_start = datetime.combine(search_date.date(), time(0, 0))
        day_end = datetime.combine(search_date.date(), time(23, 59))

        events = await get_existing_events(tenant_id, collab_id, day_start, day_end)

        # Trouver les créneaux
        slots = find_available_slots(
            schedule,
            events,
            search_date,
            request.duree_minutes,
            request.latitude,
            request.longitude
        )

        all_slots.extend(slots)

        if len(all_slots) >= 10:
            break

        search_date += timedelta(days=1)

    # Trier par score
    all_slots.sort(key=lambda x: x.score, reverse=True)

    return OptimizationResponse(
        slots=all_slots[:10],
        collaborateur_id=collab_id,
        collaborateur_nom=schedule.get("nom", ""),
        message=f"{len(all_slots)} créneaux trouvés" if all_slots else "Aucun créneau disponible"
    )


@router.get("/disponibilites")
async def get_disponibilites(
    collaborateur_id: str = Query(..., description="ID du collaborateur"),
    date: str = Query(..., description="Date au format YYYY-MM-DD"),
    user: dict = Depends(require_auth),
    tenant_id: UUID = Depends(get_current_tenant)
):
    """Retourne les disponibilités d'un collaborateur pour une date."""

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except:
        raise HTTPException(status_code=400, detail="Format de date invalide (YYYY-MM-DD)")

    schedule = await get_employee_schedule(tenant_id, collaborateur_id)

    day_start = datetime.combine(target_date.date(), time(0, 0))
    day_end = datetime.combine(target_date.date(), time(23, 59))

    events = await get_existing_events(tenant_id, collaborateur_id, day_start, day_end)

    return {
        "date": date,
        "collaborateur_id": collaborateur_id,
        "horaires": {
            "debut": schedule["heure_debut"].strftime("%H:%M"),
            "fin": schedule["heure_fin"].strftime("%H:%M"),
            "pause_debut": schedule["pause_debut"].strftime("%H:%M"),
            "pause_fin": schedule["pause_fin"].strftime("%H:%M")
        },
        "evenements": [
            {
                "debut": e["start"].strftime("%H:%M"),
                "fin": e["end"].strftime("%H:%M") if e.get("end") else None,
                "type": e["type"]
            }
            for e in events
        ]
    }
