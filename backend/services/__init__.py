from .fire_service import (
    fetch_fires,
    create_danger_zones,
    determine_alert_level,
    calculate_distance_km,
    is_point_in_danger_zone,
)

from .osm_service import (
    fetch_safe_places,
    search_place_by_name,
)

from .cell_service import (
    fetch_cell_towers_opencellid,
    estimate_cell_coverage,
    mark_towers_in_fire_zones,
    check_route_coverage,
    estimate_coverage_simple,
)

from .routing_service import (
    get_route,
    get_route_to_nearest_safe_place,
    decode_polyline,
)

from .elevenlabs_service import (
    text_to_speech,
    speech_to_text,
)

__all__ = [
    # Fire
    "fetch_fires",
    "create_danger_zones",
    "determine_alert_level",
    "calculate_distance_km",
    "is_point_in_danger_zone",
    # OSM
    "fetch_safe_places",
    "search_place_by_name",
    # Cell
    "fetch_cell_towers_opencellid",
    "estimate_cell_coverage",
    "mark_towers_in_fire_zones",
    "check_route_coverage",
    "estimate_coverage_simple",
    # Routing
    "get_route",
    "get_route_to_nearest_safe_place",
    "decode_polyline",
    # Audio
    "text_to_speech",
    "speech_to_text",
]
