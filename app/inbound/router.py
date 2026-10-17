"""FastAPI router for Inbound Portfolio Gateway."""
from __future__ import annotations

import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.telegram.services.telegram_service import telegram_service

from app.inbound.schemas import (
    CallMeBackRequest,
    CallMeBackResponse,
    ConciergeSiteConfigPublic,
    ConciergeSiteConfigUpsertRequest,
    ConciergeSiteConfigUpsertResponse,
    PortfolioInboundMessageRequest,
    PortfolioInboundResponse,
    VoiceCallSessionRequest,
    VoiceCallSessionResponse,
    VoiceCallTurnRequest,
    VoiceCallTurnResponse,
    VoiceTTSRequest,
)
from app.inbound.services.portfolio_handler import PortfolioConciergeService
from app.inbound.services.site_config_service import site_config_service
from app.inbound.services.voice_call_service import VoiceCallService

router = APIRouter(prefix="/inbound", tags=["Inbound Portfolio"])
concierge_service = PortfolioConciergeService()
voice_service = VoiceCallService()


@router.get("/sites")
async def list_concierge_sites():
    """Lists all available customizable site concierges."""
    return {"sites": site_config_service.list_public_configs(), "status": "ok"}


@router.get("/sites/{site_key}/config", response_model=ConciergeSiteConfigPublic)
async def get_concierge_site_config(site_key: str) -> ConciergeSiteConfigPublic:
    """Returns the public customization & knowledge base config for a specific client site_key."""
    return site_config_service.get_public_config(site_key)


@router.put("/sites/{site_key}/config", response_model=ConciergeSiteConfigUpsertResponse)
async def upsert_concierge_site_config(
    site_key: str,
    body: ConciergeSiteConfigUpsertRequest,
    request: Request,
) -> ConciergeSiteConfigUpsertResponse:
    """Creates or updates a client site's customizable concierge & knowledge base."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de modifications en peu de temps. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )

    try:
        public_cfg, saved_token = site_config_service.upsert_site_config(site_key, body)
        snippet = f'<script src="https://rockib-quenum.netlify.app/rockib-concierge.js" data-site-key="{public_cfg.site_key}" defer></script>'
        return ConciergeSiteConfigUpsertResponse(
            status="saved",
            message=f"Concierge et base de connaissances du site '{public_cfg.site_key}' enregistrés avec succès !",
            config=public_cfg,
            client_token=saved_token,
            embed_script=snippet,
            embed_snippet=snippet,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/portfolio/message", response_model=PortfolioInboundResponse)
async def post_portfolio_message(
    body: PortfolioInboundMessageRequest,
    request: Request,
) -> PortfolioInboundResponse:
    """Public gateway for the embeddable portfolio chat widget.

    Receives visitor questions, provides informed answers about Rockib's work,
    and captures leads for Agence IIA.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    return await concierge_service.handle_message(body, client_ip=client_ip)


@router.post("/portfolio/voice/session", response_model=VoiceCallSessionResponse)
async def start_voice_call_session(
    body: VoiceCallSessionRequest,
    request: Request,
) -> VoiceCallSessionResponse:
    """Initiates an in-browser live voice calling session."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de sessions vocales ouvertes. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    return voice_service.start_call_session(body)


@router.post("/portfolio/voice/turn", response_model=VoiceCallTurnResponse)
async def handle_voice_turn(
    body: VoiceCallTurnRequest,
    request: Request,
) -> VoiceCallTurnResponse:
    """Exchanges a vocal speech turn between the visitor and the Concierge."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    return await voice_service.handle_voice_turn(body, client_ip=client_ip)


@router.post("/portfolio/voice/tts")
async def synthesize_voice_tts(
    body: VoiceTTSRequest,
    request: Request,
) -> Response:
    """Synthesizes Neural HD MP3 audio (fr-FR-HenriNeural / fr-FR-VivienneMultilingualNeural)."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes de synthèse vocale. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )

    try:
        audio_bytes = await voice_service.synthesize_neural_speech(
            text=body.text,
            voice_profile=body.voice,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neural TTS unavailable: {type(exc).__name__}",
        )


@router.post("/portfolio/voice/stt")
async def transcribe_voice_stt(
    request: Request,
):
    """Transcribes raw audio bytes from the visitor's microphone via Groq Whisper."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes vocales. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )

    audio_bytes = await request.body()
    if not audio_bytes or len(audio_bytes) > 2 * 1024 * 1024:
        return {"transcript": "", "status": "empty"}

    ext = request.headers.get("x-audio-ext", "webm").strip().lower()
    if ext not in ("webm", "ogg", "mp4", "m4a", "wav"):
        ext = "webm"

    transcript = await voice_service.transcribe_audio_bytes(audio_bytes, filename=f"speech.{ext}")
    return {"transcript": transcript, "status": "ok" if transcript else "empty"}



@router.post("/portfolio/voice/request-callback", response_model=CallMeBackResponse)
async def request_callback(
    body: CallMeBackRequest,
    request: Request,
) -> CallMeBackResponse:
    """Schedules a direct phone call or WhatsApp call from Rockib or an agency agent."""
    from app.inbound.services.portfolio_handler import is_rate_limited

    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes de rappel. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    return await voice_service.schedule_callback(body)


@router.get("/portfolio/health")
async def get_portfolio_inbound_health():
    """Health check for the portfolio concierge integration."""
    return {
        "status": "healthy",
        "service": "Portfolio Concierge Inbound Gateway & Voice Engine",
        "portfolio_target": "https://rockib-quenum.netlify.app/",
        "features": ["text_chat", "voice_calling", "neural_tts", "callback_scheduling"],
    }


@router.post("/telegram/webhook")
async def telegram_inbound_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """Réception en direct des messages et arbitrages interactifs Telegram protégée par secret_token."""
    configured_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not configured_secret or not x_telegram_bot_api_secret_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret token",
        )
    if not secrets.compare_digest(x_telegram_bot_api_secret_token, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret token",
        )

    update = await request.json()
    return await telegram_service.process_update(update, db)

