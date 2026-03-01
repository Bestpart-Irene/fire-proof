import math

from .cell_service import estimate_coverage_simple
from .fire_service import create_danger_zones, determine_alert_level, fetch_fires
from .osm_service import fetch_safe_places
from .routing_service import get_route_to_nearest_safe_place


def _bearing_to_cardinal(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
    lat1 = math.radians(origin_lat)
    lat2 = math.radians(dest_lat)
    diff_lng = math.radians(dest_lng - origin_lng)

    x = math.sin(diff_lng) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(diff_lng)
    initial_bearing = math.degrees(math.atan2(x, y))
    normalized = (initial_bearing + 360) % 360

    directions = [
        "north",
        "northeast",
        "east",
        "southeast",
        "south",
        "southwest",
        "west",
        "northwest",
    ]
    index = round(normalized / 45) % len(directions)
    return directions[index]


def _build_instruction_text(alert_level: str, closest_fire_km: float | None, warnings: list[str]) -> str:
    if alert_level in {"critical", "high"}:
        base = "Immediate evacuation is recommended."
    elif alert_level == "medium":
        base = "Move carefully and prepare to leave the area."
    elif closest_fire_km is not None:
        base = "No immediate evacuation is required, but stay alert."
    else:
        base = "No nearby fire was detected from the current feed."

    if closest_fire_km is not None:
        base += f" The nearest fire is about {closest_fire_km:.1f} kilometers away."

    if warnings:
        base += f" Warning: {warnings[0]}."

    return base


def _build_guidance_text(
    destination_name: str | None,
    destination_direction: str | None,
    destination_distance_km: float | None,
    route_distance_km: float | None,
    route_duration_minutes: float | None,
    route_steps: list[str],
    alert_level: str,
    closest_fire_km: float | None,
    warnings: list[str],
) -> str:
    intro = _build_instruction_text(alert_level, closest_fire_km, warnings)

    if not destination_direction or destination_distance_km is None:
        return (
            f"{intro} A verified escape path is not available right now. "
            "If conditions worsen, move away from smoke and flames, keep low, and contact emergency services."
        )

    location_phrase = f"toward the {destination_direction}"
    if destination_name:
        location_phrase += f" to reach {destination_name}"

    route_phrase = f" for about {destination_distance_km:.1f} kilometers"
    if route_distance_km is not None and route_duration_minutes is not None:
        route_phrase = (
            f" for about {route_distance_km:.1f} kilometers, roughly {route_duration_minutes:.0f} minutes"
        )

    steps_text = ""
    if route_steps:
        steps_text = " Follow these steps: " + " Then ".join(route_steps[:3]) + "."

    return f"{intro} Head {location_phrase}{route_phrase}.{steps_text}"


async def build_evacuation_guidance(
    latitude: float,
    longitude: float,
) -> dict:
    warnings: list[str] = []

    try:
        fires = await fetch_fires(latitude, longitude, radius_km=50)
        danger_zones = create_danger_zones(fires)
        closest_fire_km = fires[0].distance_km if fires else None
        alert_level = determine_alert_level(closest_fire_km, len(fires))
    except Exception as exc:
        fires = []
        danger_zones = []
        closest_fire_km = None
        alert_level = "none"
        warnings.append(f"Could not fetch fire data: {exc}")

    safe_places = []
    try:
        places = await fetch_safe_places(
            latitude,
            longitude,
            radius_km=20,
            danger_zones=danger_zones,
        )
        safe_places = [place for place in places if not place.is_in_danger_zone]
    except Exception as exc:
        warnings.append(f"Could not fetch safe places: {exc}")

    coverage = estimate_coverage_simple(latitude, longitude, danger_zones)
    if not coverage.get("has_coverage"):
        warnings.append("Cell coverage may be degraded in your area")

    route = None
    destination = safe_places[0] if safe_places else None

    if safe_places:
        destinations = [
            {"lat": place.latitude, "lng": place.longitude, "name": place.name, "id": place.id}
            for place in safe_places[:5]
        ]
        try:
            result = await get_route_to_nearest_safe_place(
                latitude,
                longitude,
                destinations,
                danger_zones=danger_zones,
            )
            if result:
                route, dest_info = result
                destination = next((place for place in safe_places if place.id == dest_info["id"]), destination)
        except Exception as exc:
            warnings.append(f"Could not calculate route: {exc}")

    destination_direction = None
    destination_distance_km = None
    route_steps: list[str] = []

    if destination:
        destination_direction = _bearing_to_cardinal(
            latitude,
            longitude,
            destination.latitude,
            destination.longitude,
        )
        destination_distance_km = destination.distance_km

    if route:
        route_steps = [step.instruction for step in route.steps if step.instruction]

    guidance_text = _build_guidance_text(
        destination_name=destination.name if destination else None,
        destination_direction=destination_direction,
        destination_distance_km=destination_distance_km,
        route_distance_km=route.distance_km if route else None,
        route_duration_minutes=route.duration_minutes if route else None,
        route_steps=route_steps,
        alert_level=alert_level.value if hasattr(alert_level, "value") else str(alert_level),
        closest_fire_km=closest_fire_km,
        warnings=warnings,
    )

    return {
        "guidance_text": guidance_text,
        "alert_level": alert_level.value if hasattr(alert_level, "value") else str(alert_level),
        "closest_fire_km": closest_fire_km,
        "destination_name": destination.name if destination else None,
        "destination_direction": destination_direction,
        "destination_distance_km": destination_distance_km,
        "route_distance_km": route.distance_km if route else None,
        "route_duration_minutes": route.duration_minutes if route else None,
        "route_steps": route_steps[:3],
        "warnings": warnings,
    }
