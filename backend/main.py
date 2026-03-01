from fastapi import FastAPI, HTTPException, Query, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional, Any, Dict, List, Literal
from dotenv import load_dotenv
import os
import time
from io import BytesIO

import httpx
from pydantic import BaseModel, Field

load_dotenv()

from models import (
    AlertLevel,
    Coordinate,
    NavigationResponse,
    SafeRoute,
    TextToSpeechRequest,
    SpeechToTextResponse,
)
from services import (
    fetch_fires,
    create_danger_zones,
    determine_alert_level,
    fetch_safe_places,
    estimate_coverage_simple,
    get_route,
    get_route_to_nearest_safe_place,
    text_to_speech,
    speech_to_text,
)

# ----------------------------
# vLLM config (env-driven)
# ----------------------------
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL")
VLLM_MODEL = os.getenv("VLLM_MODEL")
VLLM_API_KEY = os.getenv("VLLM_API_KEY")  # optional
VLLM_TIMEOUT_S = float(os.getenv("VLLM_TIMEOUT_S"))
VLLM_MAX_TOKENS = int(os.getenv("VLLM_MAX_TOKENS"))
VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE"))

_vllm_client: Optional[httpx.AsyncClient] = None


def _vllm_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLLM_API_KEY}"
    return headers


async def _call_vllm_chat(
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    top_p: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calls vLLM OpenAI-compatible /chat/completions endpoint.
    Assumes VLLM_BASE_URL includes /v1 (default: http://vllm:8000/v1)
    """
    global _vllm_client
    if _vllm_client is None:
        # Should not happen if startup event runs, but keep safe fallback
        timeout = httpx.Timeout(VLLM_TIMEOUT_S, connect=10.0)
        _vllm_client = httpx.AsyncClient(timeout=timeout)

    url = f"{VLLM_BASE_URL}/chat/completions"
    payload: Dict[str, Any] = {
        "model": VLLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p is not None:
        payload["top_p"] = top_p

    try:
        resp = await _vllm_client.post(url, headers=_vllm_headers(), json=payload)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach vLLM at {url}: {e}")

    if resp.status_code >= 400:
        try:
            err = resp.json()
        except Exception:
            err = {"error": resp.text[:500]}
        raise HTTPException(
            status_code=502,
            detail={"vllm_status": resp.status_code, "vllm_error": err},
        )

    try:
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="vLLM returned non-JSON response.")


def _extract_vllm_text(vllm_resp: Dict[str, Any]) -> str:
    try:
        return vllm_resp["choices"][0]["message"]["content"]
    except Exception:
        return ""


# ----------------------------
# Request/Response models (local)
# ----------------------------
class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LLMChatRequest(BaseModel):
    messages: List[LLMMessage] = Field(..., min_length=1)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None


class LLMChatResponse(BaseModel):
    model: str
    latency_s: float
    text: str
    raw: Dict[str, Any]


class GuidanceRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    fire_radius_km: float = Field(50, ge=10, le=200)
    safe_place_radius_km: float = Field(20, ge=5, le=50)
    include_route: bool = True
    user_context: Optional[str] = None  # e.g. "asthma, pets, elderly"
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


class GuidanceResponse(BaseModel):
    navigation: NavigationResponse
    guidance_text: str
    model: str
    latency_s: float
    raw: Dict[str, Any]


app = FastAPI(
    title="Fire-Proof API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    global _vllm_client
    timeout = httpx.Timeout(VLLM_TIMEOUT_S, connect=10.0)
    _vllm_client = httpx.AsyncClient(timeout=timeout)


@app.on_event("shutdown")
async def _shutdown():
    global _vllm_client
    if _vllm_client is not None:
        await _vllm_client.aclose()
        _vllm_client = None


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Fire-Proof API",
        "version": "1.0.0",
    }


# ----------------------------
# vLLM endpoints
# ----------------------------
@app.get("/api/llm/health")
async def llm_health():
    """
    Pings vLLM /models so you can verify the inference server is reachable from this API container.
    """
    global _vllm_client
    if _vllm_client is None:
        raise HTTPException(status_code=500, detail="vLLM client not initialized")

    url = f"{VLLM_BASE_URL}/models"
    try:
        resp = await _vllm_client.get(url, headers=_vllm_headers())
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"vLLM health check failed: {e}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail={"status": resp.status_code, "body": resp.text[:500]})

    return {"ok": True, "model": VLLM_MODEL, "vllm_models": resp.json()}


@app.post("/api/llm/chat", response_model=LLMChatResponse)
async def llm_chat(req: LLMChatRequest):
    """
    Generic pass-through chat endpoint to vLLM.
    Useful as a building block for later RAG + NWS orchestration.
    """
    temperature = req.temperature if req.temperature is not None else VLLM_TEMPERATURE
    max_tokens = req.max_tokens if req.max_tokens is not None else VLLM_MAX_TOKENS

    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    t0 = time.time()
    raw = await _call_vllm_chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=req.top_p,
    )
    latency = time.time() - t0
    text = _extract_vllm_text(raw)

    return LLMChatResponse(
        model=VLLM_MODEL,
        latency_s=round(latency, 3),
        text=text,
        raw=raw,
    )


# ----------------------------
# Existing endpoints (unchanged)
# ----------------------------
@app.get("/api/fires/check")
async def check_fire_alert(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    alert_threshold_km: float = Query(10, ge=1, le=100),
    days: int = Query(1, ge=1, le=10),
):
    try:
        fires = await fetch_fires(latitude, longitude, radius_km=alert_threshold_km + 10, days=days)
        nearby = [f for f in fires if (f.distance_km or 999) <= alert_threshold_km]
        closest_km = fires[0].distance_km if fires else None

        return {
            "is_alert": len(nearby) > 0,
            "alert_level": determine_alert_level(closest_km, len(nearby)),
            "fires_within_threshold": len(nearby),
            "closest_fire_km": closest_km,
            "threshold_km": alert_threshold_km,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/navigate", response_model=NavigationResponse)
async def get_navigation_data(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    fire_radius_km: float = Query(50, ge=10, le=200),
    safe_place_radius_km: float = Query(20, ge=5, le=50),
    include_route: bool = Query(True),
    days: int = Query(1, ge=1, le=10),
):
    warnings = []

    try:
        fires = await fetch_fires(latitude, longitude, radius_km=fire_radius_km, days=days)
        danger_zones = create_danger_zones(fires)
        closest_fire_km = fires[0].distance_km if fires else None
        alert_level = determine_alert_level(closest_fire_km, len(fires))
    except Exception as e:
        fires = []
        danger_zones = []
        closest_fire_km = None
        alert_level = AlertLevel.NONE
        warnings.append(f"Could not fetch fire data: {e}")

    if len(fires) == 0:
        return NavigationResponse(
            user_location=Coordinate(latitude=latitude, longitude=longitude),
            alert_level=AlertLevel.NONE,
            fires_detected=0,
            closest_fire_km=None,
            danger_zones=[],
            safe_places=[],
            recommended_destination=None,
            route=None,
            cell_coverage_status="normal",
            warnings=warnings,
            evacuation_recommended=False,
        )

    safe_places = []
    try:
        places = await fetch_safe_places(
            latitude, longitude,
            radius_km=safe_place_radius_km,
            danger_zones=danger_zones,
        )
        safe_places = [p for p in places if not p.is_in_danger_zone]
    except Exception as e:
        warnings.append(f"Could not fetch safe places: {e}")

    coverage = estimate_coverage_simple(latitude, longitude, danger_zones)
    cell_status = coverage.get('quality', 'unknown')
    if not coverage.get('has_coverage'):
        warnings.append("Cell coverage may be degraded in your area")

    route = None
    recommended = None

    if include_route and safe_places:
        destinations = [
            {"lat": p.latitude, "lng": p.longitude, "name": p.name, "id": p.id}
            for p in safe_places[:5]
        ]

        try:
            result = await get_route_to_nearest_safe_place(
                latitude, longitude,
                destinations,
                danger_zones=danger_zones,
            )
            if result:
                route, dest_info = result
                recommended = next((p for p in safe_places if p.id == dest_info['id']), None)
                if recommended:
                    recommended.route_distance_km = route.distance_km
                    recommended.route_duration_minutes = route.duration_minutes
        except Exception as e:
            warnings.append(f"Could not calculate route: {e}")

    return NavigationResponse(
        user_location=Coordinate(latitude=latitude, longitude=longitude),
        alert_level=alert_level,
        fires_detected=len(fires),
        closest_fire_km=closest_fire_km,
        danger_zones=danger_zones,
        safe_places=safe_places,
        recommended_destination=recommended,
        route=route,
        cell_coverage_status=cell_status,
        warnings=warnings,
        evacuation_recommended=alert_level in [AlertLevel.CRITICAL, AlertLevel.HIGH],
    )


@app.get("/api/route", response_model=SafeRoute)
async def get_safe_route(
    origin_lat: float = Query(..., ge=-90, le=90),
    origin_lng: float = Query(..., ge=-180, le=180),
    dest_lat: float = Query(..., ge=-90, le=90),
    dest_lng: float = Query(..., ge=-180, le=180),
    avoid_fires: bool = Query(True),
    profile: str = Query("driving-car"),
    days: int = Query(1, ge=1, le=10),
):
    danger_zones = []
    if avoid_fires:
        try:
            mid_lat = (origin_lat + dest_lat) / 2
            mid_lng = (origin_lng + dest_lng) / 2
            fires = await fetch_fires(mid_lat, mid_lng, radius_km=100, days=days)
            danger_zones = create_danger_zones(fires)
        except Exception:
            pass

    try:
        route = await get_route(
            origin_lat, origin_lng,
            dest_lat, dest_lng,
            danger_zones=danger_zones if avoid_fires else None,
            profile=profile,
        )

        if not route:
            raise HTTPException(
                status_code=404,
                detail="No route found. The destination may be unreachable due to fire zones."
            )

        return route

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing error: {e}")


# ----------------------------
# Optional: Guidance endpoint (navigation + LLM)
# ----------------------------
@app.post("/api/guidance", response_model=GuidanceResponse)
async def generate_guidance(req: GuidanceRequest):
    """
    Generates short safety guidance using the existing navigation logic + vLLM.
    This is NOT a full RAG yet; it’s a structured way to produce concise instructions.
    """
    # Reuse the same logic as /api/navigate (keeps behavior consistent)
    nav = await get_navigation_data(
        latitude=req.latitude,
        longitude=req.longitude,
        fire_radius_km=req.fire_radius_km,
        safe_place_radius_km=req.safe_place_radius_km,
        include_route=req.include_route,
    )

    # Build a compact summary for the LLM (avoid dumping huge objects)
    nav_summary = {
        "alert_level": str(nav.alert_level),
        "fires_detected": nav.fires_detected,
        "closest_fire_km": nav.closest_fire_km,
        "cell_coverage_status": nav.cell_coverage_status,
        "evacuation_recommended": nav.evacuation_recommended,
        "recommended_destination": (
            {
                "name": nav.recommended_destination.name,
                "distance_km": nav.recommended_destination.route_distance_km,
                "duration_min": nav.recommended_destination.route_duration_minutes,
            }
            if nav.recommended_destination else None
        ),
        "warnings": nav.warnings,
    }

    temperature = req.temperature if req.temperature is not None else VLLM_TEMPERATURE
    max_tokens = req.max_tokens if req.max_tokens is not None else VLLM_MAX_TOKENS

    prompt = (
        "You are a wildfire safety assistant. "
        "Given the navigation summary, write clear, short, actionable guidance in plain language. "
        "Do not invent facts. If evacuation is recommended, say so, but avoid giving legal orders. "
        "Include a short checklist. Keep it under 10 bullet points.\n\n"
        f"User context: {req.user_context or 'none'}\n"
        f"Navigation summary: {nav_summary}\n"
    )

    t0 = time.time()
    raw = await _call_vllm_chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    latency = time.time() - t0
    text = _extract_vllm_text(raw)

    return GuidanceResponse(
        navigation=nav,
        guidance_text=text,
        model=VLLM_MODEL,
        latency_s=round(latency, 3),
        raw=raw,
    )

@app.post("/api/audio/text-to-speech")
async def generate_speech(payload: TextToSpeechRequest):
    """
    Convert text to speech using ElevenLabs API.
    Returns audio file in MP3 format.
    """
    audio_bytes, content_type = await text_to_speech(
        text=payload.text,
        voice_id=payload.voice_id,
        model_id=payload.model_id,
        output_format=payload.output_format,
    )

    return StreamingResponse(
        BytesIO(audio_bytes),
        media_type=content_type,
        headers={
            "Content-Disposition": "inline; filename=tts-output.mp3",
        },
    )


@app.post("/api/audio/speech-to-text", response_model=SpeechToTextResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    model_id: str = Query("scribe_v1"),
):
    """
    Convert speech to text using ElevenLabs Speech-to-Text API.
    """
    result = await speech_to_text(file, model_id=model_id)
    return {
        "text": result.get("text", ""),
        "language_code": result.get("language_code"),
    }