# fire-proof
Fire-Proof is an integrated wildfire safety assistant that provides real-time fire monitoring, AI-generated evacuation guidance, and voice-assisted navigation to help users move from danger to safety.
# Fire-Proof

## System Architecture
```
┌─────────────────────┐     ┌──────────────────────────────────────────────┐     ┌─────────────────────┐
│  OpenRouteService   │     │                  AMD Cloud                   │     │  Government         │
│       API           │────▶│                                              │     │  Websites           │
├─────────────────────┤     │  ┌─────────────────────┐  ┌───────────────┐ │     │  1. ...             │
│    NASA-FIRMS       │────▶│  │      FastAPI         │  │     vLLM      │ │     │  2. ...             │
│    Public API       │     │  │   /api/llm           │──│  Qwen2.5-7B-  │ │     │  ...                │
├─────────────────────┤     │  │   /api/fires         │  │   Instruct    │ │     │  n. ...             │
│    ElevenLabs       │────▶│  │   /api/audio         │  └───────────────┘ │◀────┤                     │
│       API           │     │  │                      │                    │Ingest└─────────────────────┘
└─────────────────────┘     │  │  Host: docker-compose│  ┌───────────────┐ │
                            │  └─────────────────────┘  │   PGVector    │ │
                            │                            │     RAG       │ │
                            │                            └───────────────┘ │
                            └──────────────────────────────────────────────┘
                                          │
                                          │
                            ┌─────────────▼──────────────┐
                            │     React-Native App        │────▶ OpenStreetMaps
                            │       on iPhone             │
                            │  [ text input bar ]         │
                            │  [ x ............. ]        │
                            │        🎙️                   │
                            └─────────────────────────────┘
```

Fire-Proof is a wildfire safety assistant built for Hack 4 Humanity 2026. It combines live fire detection, route planning, voice interaction, and AI-generated guidance to help users understand nearby wildfire risk and move toward safer locations.

The system is designed as a mobile-first emergency support experience. A React Native app provides the user-facing map and navigation flow, while a FastAPI backend aggregates wildfire data, safe destination discovery, routing, voice services, and LLM-based guidance. The architecture is built to support both real-time operational APIs and future knowledge-assisted recommendations through a RAG pipeline.

## What It Does

- Detects nearby wildfire activity using NASA FIRMS data.
- Estimates alert level based on fire distance and density.
- Finds candidate safe places such as hospitals, shelters, fire stations, schools, and community centers.
- Builds evacuation routes with OpenRouteService and attempts to avoid active fire zones.
- Generates concise natural-language guidance through a vLLM-hosted instruction model.
- Supports text-to-speech and speech-to-text workflows through ElevenLabs.
- Displays the full experience in a React Native mobile app backed by OpenStreetMap.

## Architecture Overview

The platform has three main layers:

1. Mobile client: A React Native app running on iPhone that shows the map, fire overlays, route guidance, and user interaction flow.
2. Application backend: A FastAPI service that exposes the main APIs for fire checks, routing, audio, and LLM guidance.
3. Intelligence and data services: External APIs and an internal RAG stack provide fire data, route computation, voice processing, and future document-grounded recommendations.

## Core Components

### React Native App

The frontend is built with Expo and React Native. It uses device location, polls backend endpoints for wildfire conditions, renders fire zones and routes on the map, and presents step-by-step evacuation guidance in a mobile-friendly interface.

### FastAPI Backend

The backend acts as the orchestration layer. It normalizes external data, computes alert levels, selects safe destinations, requests route plans, and exposes a simple HTTP API that the app can consume in real time.

Primary backend responsibilities include:

- `/api/fires/check`: quick fire alert checks near a location.
- `/api/navigate`: aggregated fire, safe-place, and evacuation response.
- `/api/route`: direct route calculation between two points.
- `/api/guidance`: navigation-aware AI safety guidance.
- `/api/audio/text-to-speech`: audio generation from text.
- `/api/audio/speech-to-text`: speech transcription.
- `/api/llm/*`: general LLM access and health checks.

### vLLM and RAG

The architecture includes a vLLM inference service running a Qwen 2.5 Instruct model, alongside a PGVector-based retrieval pipeline. This is intended to support grounded safety guidance by ingesting reference material such as government websites, emergency guidance, and other trusted sources.

In the current implementation, the backend already supports LLM-based response generation. The RAG block reflects the intended knowledge layer for expanding guidance quality and trustworthiness.

## External Integrations

- NASA FIRMS: wildfire hotspot and fire activity data.
- OpenRouteService: routing and evacuation path generation.
- OpenStreetMap / Overpass: nearby safe-place discovery and mapping data.
- ElevenLabs: text-to-speech and speech-to-text.
- Government and public safety sources: designed as ingest sources for the RAG knowledge base.

## Tech Stack

- Frontend: Expo, React Native, TypeScript, MapLibre
- Backend: FastAPI, Python, Pydantic, HTTPX
- AI layer: vLLM, Qwen instruct model, PGVector-based RAG
- Infrastructure: Docker Compose
- Mapping and geospatial services: OpenStreetMap, Overpass, OpenRouteService

## Project Goal

Fire-Proof aims to reduce the time between risk detection and action. Instead of showing fire data alone, it turns multiple services into a single decision-support workflow: identify danger, understand severity, locate safer destinations, generate a route, and communicate guidance in clear text or voice.

This makes the project a practical prototype for emergency navigation and wildfire response assistance on mobile devices.
