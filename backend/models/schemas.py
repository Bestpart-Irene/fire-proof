from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class AlertLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Coordinate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class FireData(BaseModel):
    latitude: float
    longitude: float
    brightness: Optional[float] = None
    acq_date: Optional[str] = None
    acq_time: Optional[str] = None
    satellite: Optional[str] = None
    confidence: Optional[str] = None
    frp: Optional[float] = None
    distance_km: Optional[float] = None
    danger_radius_km: Optional[float] = None


class SafePlaceType(str, Enum):
    HOSPITAL = "hospital"
    FIRE_STATION = "fire_station"
    POLICE = "police"
    SHELTER = "shelter"
    SCHOOL = "school"
    COMMUNITY_CENTER = "community_center"
    STADIUM = "stadium"


class SafePlace(BaseModel):
    id: str
    name: Optional[str] = None
    place_type: SafePlaceType
    latitude: float
    longitude: float
    distance_km: float
    address: Optional[str] = None
    phone: Optional[str] = None
    is_in_danger_zone: bool = False
    has_cell_coverage: bool = True
    route_distance_km: Optional[float] = None
    route_duration_minutes: Optional[float] = None
    route_passes_danger_zone: bool = False


class CellTower(BaseModel):
    latitude: float
    longitude: float
    mcc: int
    mnc: int
    lac: int
    cell_id: int
    radio: str
    range_m: Optional[int] = None
    is_operational: bool = True


class DangerZone(BaseModel):
    center_lat: float
    center_lng: float
    radius_km: float
    fire_id: Optional[str] = None
    risk_level: AlertLevel = AlertLevel.HIGH


class RouteStep(BaseModel):
    instruction: str
    distance_m: float
    duration_s: float
    latitude: float
    longitude: float


class SafeRoute(BaseModel):
    origin: Coordinate
    destination: Coordinate
    destination_name: Optional[str] = None
    distance_km: float
    duration_minutes: float
    geometry: str
    steps: list[RouteStep] = []
    avoids_fire_zones: bool = True
    has_cell_coverage_throughout: bool = True
    danger_zones_nearby: list[DangerZone] = []
    warnings: list[str] = []


class NavigationResponse(BaseModel):
    user_location: Coordinate
    alert_level: AlertLevel
    fires_detected: int
    closest_fire_km: Optional[float] = None
    danger_zones: list[DangerZone] = []
    safe_places: list[SafePlace] = []
    recommended_destination: Optional[SafePlace] = None
    route: Optional[SafeRoute] = None
    cell_coverage_status: str = "unknown"
    warnings: list[str] = []
    evacuation_recommended: bool = False


class TextToSpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: Optional[str] = None
    model_id: str = "eleven_multilingual_v2"
    output_format: str = "mp3_44100_128"


class SpeechToTextResponse(BaseModel):
    text: str
    language_code: Optional[str] = None
