"""FastAPI router for Inbound Portfolio Gateway."""
from __future__ import annotations

import secrets
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.proxy import get_client_ip
from app.core.database import get_async_db
from app.core.dependencies import get_optional_user
from app.identity.models import User
from app.telegram.services.telegram_service import telegram_service

from datetime import datetime, timezone

from app.inbound.schemas import (
    BenchmarkSuiteReport,
    CallMeBackRequest,
    CallMeBackResponse,
    ConciergeLeadStatusUpdateRequest,
    ConciergeLeadSummary,
    ConciergeMetricsResponse,
    ConciergeSiteConfigPublic,
    ConciergeSiteConfigPrivate,
    ConciergeSiteConfigUpsertRequest,
    ConciergeSiteConfigUpsertResponse,
    ConciergeTraceSummary,
    ConciergeTunnelStatusResponse,
    PortfolioInboundMessageRequest,
    PortfolioInboundResponse,
    VoiceCallSessionRequest,
    VoiceCallSessionResponse,
    VoiceCallTurnRequest,
    VoiceCallTurnResponse,
    VoiceTTSRequest,
    VoiceCapabilitiesResponse,
)
from app.inbound.services.portfolio_handler import PortfolioConciergeService, is_request_rate_limited
from app.inbound.services.site_config_service import site_config_service
from app.inbound.services.leads import export_leads_csv, list_site_leads, record_callback_lead, update_lead_status
from app.inbound.services.voice_call_service import VoiceCallService
from app.inbound.services.tracing import concierge_tracing_service
from app.inbound.services.quality_evaluator import ConciergeQualityEvaluator
from app.inbound.services.realtime_voice_service import RealtimeVoiceBridge


router = APIRouter(prefix="/inbound", tags=["Inbound Portfolio"])
concierge_service = PortfolioConciergeService()
voice_service = VoiceCallService()


@router.get("/sites")
async def list_concierge_sites():
    """Lists all available customizable site concierges."""
    return {"sites": site_config_service.list_public_configs(), "status": "ok"}


@router.get("/sites/{site_key}/config", response_model=ConciergeSiteConfigPublic)
async def get_concierge_site_config(site_key: str) -> ConciergeSiteConfigPublic:
    """Returns only browser-safe branding; business prompts and contacts stay private."""
    try:
        return site_config_service.get_public_config(site_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Concierge site not found.")


@router.get("/sites/{site_key}/manage-config", response_model=ConciergeSiteConfigPrivate)
async def get_manage_concierge_site_config(
    site_key: str,
    x_concierge_token: Optional[str] = Header(default=None),
    current_user: Optional[User] = Depends(get_optional_user),
) -> ConciergeSiteConfigPrivate:
    """Returns private setup data only to the site's owner or configured master key."""
    if not (current_user or site_config_service.can_manage_site(site_key, x_concierge_token)):
        raise HTTPException(status_code=403, detail="Invalid concierge management token.")
    try:
        return site_config_service.get_private_config(site_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Concierge site not found.")


@router.get("/sites/{site_key}/leads", response_model=list[ConciergeLeadSummary])
async def get_site_leads(
    site_key: str,
    request: Request,
    x_concierge_token: Optional[str] = Header(default=None),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[ConciergeLeadSummary]:
    """Lists only the recent lead records belonging to the authenticated site."""
    client_ip = get_client_ip(request)
    if await is_request_rate_limited(client_ip, "list-leads", site_key=site_key, limit=20, site_limit=120):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de consultations. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    if not (current_user or site_config_service.can_manage_site(site_key, x_concierge_token)):
        raise HTTPException(status_code=403, detail="Invalid concierge management token.")
    try:
        site_config_service.get_site_dict(site_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Concierge site not found.")
    return await list_site_leads(db, site_key)


@router.patch("/sites/{site_key}/leads/{lead_id}/status", response_model=ConciergeLeadSummary)
async def update_tenant_lead_status(
    site_key: str,
    lead_id: str,
    body: ConciergeLeadStatusUpdateRequest,
    request: Request,
    x_concierge_token: Optional[str] = Header(default=None),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> ConciergeLeadSummary:
    """Updates a lead's follow-up state (contacted, converted, archived)."""
    if not (current_user or site_config_service.can_manage_site(site_key, x_concierge_token)):
        raise HTTPException(status_code=403, detail="Invalid concierge management token.")
    lead = await update_lead_status(db, site_key=site_key, lead_id=lead_id, new_status=body.status)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found for this site.")
    return lead


@router.get("/sites/{site_key}/leads/export")
async def export_tenant_leads_csv(
    site_key: str,
    request: Request,
    x_concierge_token: Optional[str] = Header(default=None),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    """Exports tenant leads as CSV for CRM or spreadsheet import."""
    if not (current_user or site_config_service.can_manage_site(site_key, x_concierge_token)):
        raise HTTPException(status_code=403, detail="Invalid concierge management token.")
    csv_data = await export_leads_csv(db, site_key=site_key)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="leads-{site_key}.csv"'},
    )


@router.get("/tunnel/status", response_model=ConciergeTunnelStatusResponse)
async def get_tunnel_status() -> ConciergeTunnelStatusResponse:
    """Returns gateway availability, Groq LLM readiness, and multi-site status."""
    sites_count = len(site_config_service.list_public_configs())
    groq_ok = bool(settings.GROQ_API_KEY)
    return ConciergeTunnelStatusResponse(
        status="operational",
        backend_time=datetime.now(timezone.utc),
        active_sites_count=sites_count,
        groq_llm_ready=groq_ok,
        voice_tts_ready=True,
        tunnel_reachable=True,
    )



@router.put("/sites/{site_key}/config", response_model=ConciergeSiteConfigUpsertResponse)
async def upsert_concierge_site_config(
    site_key: str,
    body: ConciergeSiteConfigUpsertRequest,
    request: Request,
) -> ConciergeSiteConfigUpsertResponse:
    """Creates or updates a client site's customizable concierge & knowledge base."""

    client_ip = get_client_ip(request)

    if await is_request_rate_limited(client_ip, "manage-config", site_key=site_key, limit=10, site_limit=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de modifications en peu de temps. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )

    try:
        public_cfg, saved_token = site_config_service.upsert_site_config(site_key, body)
        snippet = (
            f'<script src="{settings.CONCIERGE_WIDGET_URL}" '
            f'data-api-base="{settings.PUBLIC_API_URL}" '
            f'data-site-key="{public_cfg.site_key}" defer></script>'
        )
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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/portfolio/message", response_model=PortfolioInboundResponse)
async def post_portfolio_message(
    body: PortfolioInboundMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> PortfolioInboundResponse:
    """Public gateway for the embeddable portfolio chat widget.

    Receives visitor questions, provides informed answers about Rockib's work,
    and captures leads for Agence IIA.
    """
    client_ip = get_client_ip(request)

    try:
        site_config_service.get_site_dict(body.site_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Concierge site not found.")
    return await concierge_service.handle_message(body, client_ip=client_ip, db=db)


@router.get("/voice/capabilities", response_model=VoiceCapabilitiesResponse)
async def get_voice_capabilities() -> VoiceCapabilitiesResponse:
    """Returns status of ElevenLabs Scribe v2 Realtime vs 100% Free Native Mode."""
    from app.inbound.services.elevenlabs_service import elevenlabs_service
    caps = elevenlabs_service.get_capabilities()
    return VoiceCapabilitiesResponse(
        realtime_enabled=caps["realtime_enabled"],
        provider=caps["provider"],
        scribe_model=caps["scribe_model"],
        tts_model=caps["tts_model"],
        barge_in_supported=caps["barge_in_supported"],
    )


@router.post("/portfolio/voice/session", response_model=VoiceCallSessionResponse)
async def start_voice_call_session(
    body: VoiceCallSessionRequest,
    request: Request,
) -> VoiceCallSessionResponse:
    """Initiates an in-browser live voice calling session."""

    client_ip = get_client_ip(request)

    if await is_request_rate_limited(client_ip, "voice-session", site_key=body.site_key or "rockib-portfolio", limit=20, site_limit=120):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de sessions vocales ouvertes. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    try:
        site_config_service.get_site_dict(body.site_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Concierge site not found.")
    return voice_service.start_call_session(body, client_ip=client_ip)


@router.post("/portfolio/voice/turn", response_model=VoiceCallTurnResponse)
async def handle_voice_turn(
    body: VoiceCallTurnRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> VoiceCallTurnResponse:
    """Exchanges a vocal speech turn between the visitor and the Concierge."""
    client_ip = get_client_ip(request)

    return await voice_service.handle_voice_turn(body, client_ip=client_ip, db=db)



@router.post("/portfolio/voice/tts")
async def synthesize_voice_tts(
    body: VoiceTTSRequest,
    request: Request,
) -> Response:
    """Synthesizes Neural HD MP3 audio (fr-FR-HenriNeural / fr-FR-VivienneMultilingualNeural)."""

    client_ip = get_client_ip(request)

    if await is_request_rate_limited(client_ip, "tts", limit=20, site_key="shared", site_limit=180):
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

    client_ip = get_client_ip(request)

    if await is_request_rate_limited(client_ip, "stt", limit=10, site_key="shared", site_limit=90):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes vocales. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )

    max_audio_bytes = 2 * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_audio_bytes:
                raise HTTPException(status_code=413, detail="Audio trop volumineux (limite 2 Mo).")
        except ValueError:
            raise HTTPException(status_code=400, detail="En-t?te Content-Length invalide.")

    chunks: list[bytes] = []
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
        if received_bytes > max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio trop volumineux (limite 2 Mo).")
        chunks.append(chunk)
    audio_bytes = b"".join(chunks)
    if not audio_bytes:
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
    db: AsyncSession = Depends(get_async_db),
) -> CallMeBackResponse:
    """Persists an explicitly consented callback request for its site owner."""

    client_ip = get_client_ip(request)

    if await is_request_rate_limited(client_ip, "callback", site_key=body.site_key or "rockib-portfolio", limit=20, site_limit=120):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes de rappel. Veuillez patienter une minute.",
            headers={"Retry-After": "60"},
        )
    try:
        site_cfg = site_config_service.get_site_dict(body.site_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Concierge site not found.")
    if not body.consent:
        raise HTTPException(status_code=400, detail="Le consentement est requis pour enregistrer cette demande.")
    try:
        lead = await record_callback_lead(db, site_cfg["site_key"], body)
        # Notify Rockib on Telegram
        await concierge_tracing_service.forward_lead_to_telegram(
            site_key=site_cfg["site_key"],
            business_name=site_cfg["business_name"],
            contact_name=body.contact_name,
            phone_number=lead.phone_number,
            topic=body.topic,
            channel=body.channel,
            conversation_id=str(lead.id),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Impossible d'enregistrer la demande pour le moment. Réessayez plus tard.",
        ) from exc

    channel_label = "WhatsApp" if body.channel.lower() == "whatsapp" else "téléphone"
    return CallMeBackResponse(
        callback_id=str(lead.id),
        status="scheduled",
        channel=body.channel,
        phone_number=lead.phone_number,
        message=(
            f"Votre demande de rappel par {channel_label} est enregistrée. "
            f"L'équipe de {site_cfg['business_name']} pourra la consulter et vous recontacter dès que possible."
        ),
        estimated_wait_minutes=5 if (body.preferred_time or "immediate") == "immediate" else 60,
    )


@router.get("/traces", response_model=List[ConciergeTraceSummary])
async def get_concierge_traces(
    site_key: Optional[str] = None,
    conversation_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
) -> List[ConciergeTraceSummary]:
    """Returns conversation and execution traces with latency, cost, and tools called."""
    return await concierge_tracing_service.get_traces(
        conversation_id=conversation_id,
        site_key=site_key,
        limit=min(100, max(1, limit)),
        db=db,
    )


@router.get("/metrics", response_model=ConciergeMetricsResponse)
async def get_concierge_metrics(
    site_key: Optional[str] = None,
) -> ConciergeMetricsResponse:
    """Returns aggregated performance, usage cost, and conversion metrics."""
    return concierge_tracing_service.get_metrics_summary(site_key=site_key)


@router.post("/benchmark/run", response_model=BenchmarkSuiteReport)
async def run_concierge_benchmark() -> BenchmarkSuiteReport:
    """Runs the 6 golden reference scenarios and reports quality, safety and precision."""
    evaluator = ConciergeQualityEvaluator(concierge_service=concierge_service)
    return await evaluator.run_benchmark()


@router.get("/portfolio/health")
async def get_portfolio_inbound_health():
    """Liveness and configuration summary; does not claim external provider uptime."""
    groq_configured = bool(settings.GROQ_API_KEY)
    return {
        "status": "healthy" if groq_configured else "degraded",
        "service": "Portfolio Concierge Inbound Gateway & Voice Engine",
        "portfolio_target": "https://rockib-quenum.netlify.app/",
        "model": settings.GROQ_MODEL,
        "components": {
            "chat_and_transcription_credentials": "configured" if groq_configured else "missing",
            "lead_storage": "postgresql",
            "lead_retention_days": settings.CONCIERGE_LEAD_RETENTION_DAYS,
        },
        "features": ["text_chat", "voice_calling", "neural_tts", "consented_callback_intake", "quality_benchmark"],
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




@router.websocket("/portfolio/voice/ws")
async def voice_realtime_websocket(websocket: WebSocket, site_key: str = "rockib-portfolio", voice: str = "brian"):
    """Full-Duplex Real-Time Voice WebSocket (P2)."""
    bridge = RealtimeVoiceBridge(site_key=site_key, voice_profile=voice)
    await bridge.run(websocket)


from pydantic import BaseModel
from app.inbound.services.realtime_voice_service import RealtimeVoiceBridge
from app.core.dependencies import get_current_user


class AutoProposalRequest(BaseModel):
    client_name: str = "Client Partenaire"
    company_name: str | None = None
    project_summary: str = ""
    project_brief: str | None = None
    budget_hint: str = ""
    timeline_hint: str = ""
    currency: str = "EUR"


@router.post("/proposal/generate")
async def generate_auto_proposal(
    body: AutoProposalRequest,
    current_user: User = Depends(get_current_user),
):
    """P8 — Génère automatiquement l'architecture cible, le découpage en phases et le devis client."""
    from app.inbound.services.proposal_generator import AutoProposalEngine

    return await AutoProposalEngine.generate_proposal(
        client_name=body.client_name,
        company_name=body.company_name,
        project_summary=body.project_summary,
        project_brief=body.project_brief,
        budget_hint=body.budget_hint,
        timeline_hint=body.timeline_hint,
        currency=body.currency,
    )


class LeadHunterRequest(BaseModel):
    niche: str = "Agences immobilières"
    location: str = "Cotonou"
    max_leads: int = 3
    site_key: str = "rockib-portfolio"
    save_to_crm: bool = False
    notify_telegram: bool = False


@router.post("/lead-hunter/run")
async def run_autonomous_lead_hunter(
    body: LeadHunterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """P9 — Agent autonome de prospection B2B : recherche d'entreprises, diagnostic, chiffrage P8 et scripts WhatsApp/LinkedIn/Email."""
    from app.inbound.services.lead_hunter import LeadHunterEngine

    return await LeadHunterEngine.hunt_and_prepare_outreach(
        niche=body.niche,
        location=body.location,
        max_leads=body.max_leads,
        site_key=body.site_key,
        save_to_crm=body.save_to_crm,
        notify_telegram=body.notify_telegram,
        db=db,
    )
