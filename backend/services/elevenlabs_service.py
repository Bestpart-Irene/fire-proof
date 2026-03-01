import os

import httpx
from fastapi import HTTPException, UploadFile


ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_TTS_MODEL = "eleven_multilingual_v2"
DEFAULT_STT_MODEL = "scribe_v1"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


def _get_api_key() -> str:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ELEVENLABS_API_KEY is not configured.",
        )
    return api_key


async def text_to_speech(
    text: str,
    voice_id: str | None = None,
    model_id: str = DEFAULT_TTS_MODEL,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> tuple[bytes, str]:
    resolved_voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID")
    if not resolved_voice_id:
        raise HTTPException(
            status_code=400,
            detail="voice_id is required or set ELEVENLABS_VOICE_ID.",
        )

    payload = {
        "text": text,
        "model_id": model_id,
        "output_format": output_format,
    }
    headers = {
        "xi-api-key": _get_api_key(),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{resolved_voice_id}",
            headers=headers,
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text or "ElevenLabs text-to-speech request failed.",
        )

    return response.content, response.headers.get("content-type", "audio/mpeg")


async def speech_to_text(
    audio_file: UploadFile,
    model_id: str = DEFAULT_STT_MODEL,
) -> dict:
    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    content = await audio_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    files = {
        "file": (
            audio_file.filename,
            content,
            audio_file.content_type or "application/octet-stream",
        ),
    }
    data = {
        "model_id": model_id,
    }
    headers = {
        "xi-api-key": _get_api_key(),
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{ELEVENLABS_BASE_URL}/speech-to-text",
            headers=headers,
            data=data,
            files=files,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text or "ElevenLabs speech-to-text request failed.",
        )

    return response.json()
