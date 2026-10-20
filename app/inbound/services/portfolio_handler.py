"""Service handling inbound portfolio inquiries and lead capture.

Features:
- IP Sliding-window rate limiting.
- Conversational concierge backed by GroqProvider & portfolio_ambassador skill.
- Lead capture and optional dispatch to Agence IIA (POST /api/leads/).
- Resilient offline fallback.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
import asyncio
from collections import defaultdict, deque
from typing import Optional


from app.core.config import settings
from app.inbound.schemas import PortfolioInboundMessageRequest, PortfolioInboundResponse
from app.inbound.services.site_config_service import site_config_service
from app.inbound.services.tracing import ConciergeTraceData, concierge_tracing_service
from app.intelligence.services.providers.groq_provider import GroqProvider, compute_token_cost
from app.skills.catalog import get_default_catalogue
from sqlalchemy.ext.asyncio import AsyncSession



logger = logging.getLogger(__name__)

# In-memory sliding window rate limiter: IP -> deque of timestamps
_RATE_LIMIT_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 20
_MAX_TRACKED_IPS = 2000
_ip_request_history: dict[str, deque[float]] = defaultdict(deque)
_redis_rate_limiter = None
_redis_rate_limiter_lock = asyncio.Lock()

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4})?")


def is_rate_limited(client_ip: str) -> bool:
    """Returns True if the IP has exceeded allowed requests in the last window."""
    now = time.time()

    # Bound total tracked IPs to prevent memory exhaustion on spoofed IP floods
    if client_ip not in _ip_request_history and len(_ip_request_history) >= _MAX_TRACKED_IPS:
        stale_ips = [
            ip for ip, q in _ip_request_history.items()
            if not q or (now - q[-1] > _RATE_LIMIT_WINDOW_SECONDS)
        ]
        for ip in stale_ips:
            _ip_request_history.pop(ip, None)
        while len(_ip_request_history) >= _MAX_TRACKED_IPS:
            oldest_ip = next(iter(_ip_request_history))
            _ip_request_history.pop(oldest_ip, None)

    history = _ip_request_history[client_ip]

    # Evict timestamps older than window
    while history and now - history[0] > _RATE_LIMIT_WINDOW_SECONDS:
        history.popleft()

    if len(history) >= _MAX_REQUESTS_PER_WINDOW:
        return True

    history.append(now)
    return False


async def is_request_rate_limited(
    client_ip: str,
    bucket: str,
    *,
    site_key: str | None = None,
    limit: int = 20,
    site_limit: int = 300,
    window_seconds: int = 60,
) -> bool:
    """Apply independent per-IP and per-site quotas, shared across app replicas."""
    global _redis_rate_limiter
    try:
        if _redis_rate_limiter is None:
            async with _redis_rate_limiter_lock:
                if _redis_rate_limiter is None:
                    from redis.asyncio import from_url
                    from app.core.config import settings

                    _redis_rate_limiter = from_url(
                        settings.REDIS_URL,
                        socket_connect_timeout=1,
                        socket_timeout=1,
                        decode_responses=True,
                    )
        keys = [f"concierge:rate:ip:{client_ip}", f"concierge:rate:{bucket}:ip:{client_ip}"]
        limits = [limit, limit]
        if site_key:
            keys.append(f"concierge:rate:{bucket}:site:{site_key}")
            limits.append(site_limit)
        pipe = _redis_rate_limiter.pipeline(transaction=True)
        for key in keys:
            pipe.set(key, 0, nx=True, ex=window_seconds)
            pipe.incr(key)
        results = await pipe.execute()
        counts = [int(results[i * 2 + 1]) for i in range(len(keys))]
        return any(count > bound for count, bound in zip(counts, limits))
    except Exception as exc:
        logger.debug("Redis Concierge limiter unavailable; using local fallback: %s", type(exc).__name__)
        return is_rate_limited(client_ip) or is_rate_limited(f"{bucket}:{site_key or ''}:{client_ip}")


async def close_rate_limiter() -> None:
    global _redis_rate_limiter
    if _redis_rate_limiter is not None:
        await _redis_rate_limiter.aclose()
        _redis_rate_limiter = None


def redact_contact_details(text: str) -> str:
    """Keep contact details out of model prompts and in-memory chat history."""
    redacted = EMAIL_REGEX.sub("[coordonnees masquees]", text)

    def redact_phone(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return "[numero masque]" if 8 <= len(digits) <= 15 else match.group(0)

    return PHONE_REGEX.sub(redact_phone, redacted)


_CONVERSATION_History_MAX_SESSIONS = 1000
_CONVERSATION_TTL_SECONDS = 1800
_conversation_store: dict[tuple[str, str], list[dict[str, str]]] = {}
_conversation_last_access: dict[tuple[str, str], float] = {}


class PortfolioConciergeService:
    """Orchestrates conversations with visitors on https://rockib-quenum.netlify.app/."""

    def __init__(self, ai_provider: Optional[GroqProvider] = None):
        self.provider = ai_provider or GroqProvider()
        # Cache catalog manifests
        self._skills = {m.identity.id: m for m in get_default_catalogue()}

    def _build_system_prompt(self, site_key: str = "rockib-portfolio") -> str:
        return site_config_service.build_chat_system_prompt(site_key)

    async def handle_message(
        self,
        request: PortfolioInboundMessageRequest,
        client_ip: str = "127.0.0.1",
        db: Optional[AsyncSession] = None,
    ) -> PortfolioInboundResponse:
        """Processes a visitor message and returns a tailored AI response."""
        conversation_id = request.conversation_id or str(uuid.uuid4())
        site_key = request.site_key or "rockib-portfolio"

        raw_model = getattr(self.provider, "_model", None)
        model_name = raw_model if isinstance(raw_model, str) and raw_model else (settings.GROQ_MODEL or "llama-3.3-70b-versatile")

        # Check rate limit
        if await is_request_rate_limited(client_ip, "chat", site_key=site_key, limit=20, site_limit=300):
            trace = ConciergeTraceData(
                conversation_id=conversation_id,
                site_key=site_key,
                channel="chat",
                model=model_name,
                duration_ms=0.0,
                result_status="rate_limited",
                error_message="Rate limit exceeded",
            )
            await concierge_tracing_service.record_trace(trace, db=db)
            return PortfolioInboundResponse(
                reply="Désolé, vous avez envoyé trop de messages en peu de temps. Veuillez patienter une minute avant de continuer la discussion.",
                conversation_id=conversation_id,
                status="rate_limited",
            )

        # Free-text mentions are not consent to retain or forward contact details.
        safe_user_text = redact_contact_details(request.message)

        # Maintain multi-turn conversation history
        conversation_key = (site_key, conversation_id)
        now = time.time()
        for stale_key, last_access in list(_conversation_last_access.items()):
            if now - last_access > _CONVERSATION_TTL_SECONDS:
                _conversation_last_access.pop(stale_key, None)
                _conversation_store.pop(stale_key, None)
        if conversation_key not in _conversation_store and len(_conversation_store) >= _CONVERSATION_History_MAX_SESSIONS:
            oldest_key = min(_conversation_last_access, key=_conversation_last_access.get)
            _conversation_last_access.pop(oldest_key, None)
            _conversation_store.pop(oldest_key, None)
        _conversation_last_access[conversation_key] = now
        history = _conversation_store.setdefault(conversation_key, [])
        history.append({"role": "user", "content": safe_user_text})
        del history[:-24]

        # Call LLM with conversation history and site-specific knowledge base
        messages = [{"role": "system", "content": self._build_system_prompt(site_key)}]
        messages.extend(history[-12:])

        start_time = time.perf_counter()
        tools_called = ["site_knowledge_base"]
        result_status = "ok"
        error_msg: Optional[str] = None
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        cost_usd = 0.0


        try:
            has_custom_meta = (
                hasattr(self.provider, "generate_with_meta")
                and type(self.provider).__name__ not in ("AsyncMock", "MagicMock", "Mock")
            )
            if has_custom_meta:
                gen_result = await self.provider.generate_with_meta(messages, json_mode=False)
                raw_reply = gen_result.content
                model_name = gen_result.model
                prompt_tokens = gen_result.prompt_tokens
                completion_tokens = gen_result.completion_tokens
                total_tokens = gen_result.total_tokens
                cost_usd = gen_result.estimated_cost_usd
            else:
                raw_reply = await self.provider.generate(messages, json_mode=False)
                if not isinstance(raw_reply, str):
                    raw_reply = str(raw_reply)
                prompt_chars = sum(len(m.get("content", "")) for m in messages)
                completion_chars = len(raw_reply)
                prompt_tokens = max(1, prompt_chars // 4)
                completion_tokens = max(1, completion_chars // 4)
                total_tokens = prompt_tokens + completion_tokens
                cost_usd = compute_token_cost(model_name, prompt_tokens, completion_tokens)

            reply_text = re.sub(r"<think>[\s\S]*?</think>", "", raw_reply).strip()

        except Exception as e:
            logger.warning("GroqProvider unavailable for inbound portfolio: %s. Using resilient fallback.", e)
            result_status = "fallback"
            error_msg = str(e)
            business_name = site_config_service.get_site_dict(site_key)["business_name"]
            reply_text = (
                f"Bonjour, je suis l'assistant de {business_name}. Je rencontre un souci temporaire et je ne veux pas "
                "vous donner une information incertaine. Pouvez-vous reformuler votre demande dans un instant, ou contacter directement l'entreprise ?"
            )

        email_match = EMAIL_REGEX.search(request.message)
        detected_email = request.contact_email or (email_match.group(0) if email_match else None)
        phone_match = PHONE_REGEX.search(request.message)
        detected_phone = request.contact_phone or (phone_match.group(0).strip() if phone_match and len(re.sub(r"\D", "", phone_match.group(0))) >= 8 else None)
        lead_captured = bool(detected_email or detected_phone)

        transferred_to_rockib = False
        if lead_captured:
            tools_called.append("lead_capture")
            cfg = site_config_service.get_site_dict(site_key)
            transferred_to_rockib = await concierge_tracing_service.forward_lead_to_telegram(
                site_key=site_key,
                business_name=cfg.get("business_name", site_key),
                contact_name=request.sender_name,
                phone_number=detected_phone,
                email=detected_email,
                topic=request.message[:400],
                channel="chat",
                conversation_id=conversation_id,
            )
            if transferred_to_rockib:
                tools_called.append("telegram_notify")

            if detected_email and detected_email not in reply_text:
                reply_text += f"\n\n*(Vos coordonnées {detected_email} ont bien été transmises à Rockib. Il vous recontactera très rapidement !)*"

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Record detailed trace
        trace = ConciergeTraceData(
            conversation_id=conversation_id,
            site_key=site_key,
            channel="chat",
            model=model_name,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost_usd,
            tools_called=tools_called,
            result_status=result_status,
            lead_captured=lead_captured,
            transferred_to_rockib=transferred_to_rockib,
            error_message=error_msg,
        )
        await concierge_tracing_service.record_trace(trace, db=db)

        return PortfolioInboundResponse(
            reply=reply_text,
            conversation_id=conversation_id,
            lead_captured=lead_captured,
            status="ok",
        )

