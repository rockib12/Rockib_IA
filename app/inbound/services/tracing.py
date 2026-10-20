"""Telemetry, execution traces, cost estimation, and lead dispatch for the Concierge."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.inbound.models import ConciergeExecutionTrace
from app.inbound.schemas import ConciergeMetricsResponse, ConciergeTraceSummary
from app.intelligence.services.providers.groq_provider import compute_token_cost
from app.telegram.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ConciergeTraceData:
    conversation_id: str
    site_key: str
    channel: str = "chat"
    model: str = "llama-3.3-70b-versatile"
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    tools_called: List[str] = field(default_factory=list)
    result_status: str = "ok"
    lead_captured: bool = False
    transferred_to_rockib: bool = False
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class ConciergeTracingService:
    """Manages execution tracing, cost metrics, and lead alerts across chat and voice turns."""

    def __init__(self, max_in_memory_traces: int = 1000):
        self._max_traces = max_in_memory_traces
        self._in_memory_traces: deque[ConciergeTraceData] = deque(maxlen=max_in_memory_traces)

    async def record_trace(
        self,
        trace: ConciergeTraceData,
        db: Optional[AsyncSession] = None,
    ) -> ConciergeTraceData:
        """Stores trace in fast in-memory buffer and optionally persists to DB."""
        if trace.total_tokens == 0:
            trace.total_tokens = trace.prompt_tokens + trace.completion_tokens
        if trace.estimated_cost_usd == 0.0 and trace.total_tokens > 0:
            trace.estimated_cost_usd = compute_token_cost(
                trace.model, trace.prompt_tokens, trace.completion_tokens
            )

        self._in_memory_traces.appendleft(trace)

        if db is not None:
            try:
                db_trace = ConciergeExecutionTrace(
                    id=trace.id,
                    conversation_id=trace.conversation_id,
                    site_key=trace.site_key,
                    channel=trace.channel,
                    model=trace.model,
                    duration_ms=trace.duration_ms,
                    prompt_tokens=trace.prompt_tokens,
                    completion_tokens=trace.completion_tokens,
                    total_tokens=trace.total_tokens,
                    estimated_cost_usd=trace.estimated_cost_usd,
                    tools_called=json.dumps(trace.tools_called),
                    result_status=trace.result_status,
                    lead_captured=trace.lead_captured,
                    transferred_to_rockib=trace.transferred_to_rockib,
                    error_message=trace.error_message,
                    created_at=trace.created_at,
                )
                db.add(db_trace)
                await db.commit()
            except Exception as exc:
                logger.warning("Could not persist trace to DB: %s", exc)
                await db.rollback()

        return trace

    async def forward_lead_to_telegram(
        self,
        *,
        site_key: str,
        business_name: str,
        contact_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        topic: Optional[str] = None,
        channel: str = "chat",
        conversation_id: Optional[str] = None,
    ) -> bool:
        """Transfers a captured lead to Rockib's Telegram bot with zero-trust formatting."""
        if not telegram_service.is_configured():
            logger.debug("Telegram bot not configured; skipping lead push.")
            return False

        lines = [
            "🎯 *NOUVEAU LEAD CONCIERGE CAPTURÉ*",
            f"🏢 *Site client :* `{site_key}` ({business_name})",
            f"📡 *Canal :* `{channel.upper()}`",
        ]
        if contact_name:
            lines.append(f"👤 *Nom :* {contact_name}")
        if phone_number:
            lines.append(f"📞 *Téléphone / WhatsApp :* `{phone_number}`")
        if email:
            lines.append(f"✉️ *Email :* `{email}`")
        if topic:
            lines.append(f"💬 *Besoin exprimé :* {topic}")
        if conversation_id:
            lines.append(f"🆔 *Session :* `{conversation_id[:16]}...`")

        lines.append(f"⏱️ *Horodatage :* `{_utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`")

        msg = "\n".join(lines)
        try:
            res = await telegram_service.send_message(
                chat_id=telegram_service.admin_chat_id,
                text=msg,
                parse_mode="Markdown",
            )
            return bool(res and res.get("ok"))
        except Exception as exc:
            logger.warning("Failed forwarding lead to Telegram: %s", exc)
            return False

    async def get_traces(
        self,
        *,
        conversation_id: Optional[str] = None,
        site_key: Optional[str] = None,
        limit: int = 50,
        db: Optional[AsyncSession] = None,
    ) -> List[ConciergeTraceSummary]:
        """Retrieves execution traces from DB if available, falling back to in-memory store."""
        if db is not None:
            try:
                stmt = select(ConciergeExecutionTrace).order_by(desc(ConciergeExecutionTrace.created_at)).limit(limit)
                if conversation_id:
                    stmt = stmt.where(ConciergeExecutionTrace.conversation_id == conversation_id)
                if site_key:
                    stmt = stmt.where(ConciergeExecutionTrace.site_key == site_key)

                rows = (await db.execute(stmt)).scalars().all()
                if rows:
                    res: List[ConciergeTraceSummary] = []
                    for r in rows:
                        try:
                            tools = json.loads(r.tools_called) if isinstance(r.tools_called, str) else []
                        except Exception:
                            tools = []
                        res.append(
                            ConciergeTraceSummary(
                                id=r.id,
                                conversation_id=r.conversation_id,
                                site_key=r.site_key,
                                channel=r.channel,
                                model=r.model,
                                duration_ms=r.duration_ms,
                                prompt_tokens=r.prompt_tokens,
                                completion_tokens=r.completion_tokens,
                                total_tokens=r.total_tokens,
                                estimated_cost_usd=r.estimated_cost_usd,
                                tools_called=tools,
                                result_status=r.result_status,
                                lead_captured=r.lead_captured,
                                transferred_to_rockib=r.transferred_to_rockib,
                                error_message=r.error_message,
                                created_at=r.created_at,
                            )
                        )
                    return res
            except Exception as exc:
                logger.debug("DB traces query failed, falling back to memory: %s", exc)

        # Fallback to in-memory deque
        filtered = list(self._in_memory_traces)
        if conversation_id:
            filtered = [t for t in filtered if t.conversation_id == conversation_id]
        if site_key:
            filtered = [t for t in filtered if t.site_key == site_key]

        return [
            ConciergeTraceSummary(
                id=t.id,
                conversation_id=t.conversation_id,
                site_key=t.site_key,
                channel=t.channel,
                model=t.model,
                duration_ms=t.duration_ms,
                prompt_tokens=t.prompt_tokens,
                completion_tokens=t.completion_tokens,
                total_tokens=t.total_tokens,
                estimated_cost_usd=t.estimated_cost_usd,
                tools_called=t.tools_called,
                result_status=t.result_status,
                lead_captured=t.lead_captured,
                transferred_to_rockib=t.transferred_to_rockib,
                error_message=t.error_message,
                created_at=t.created_at,
            )
            for t in filtered[:limit]
        ]

    def get_metrics_summary(self, site_key: Optional[str] = None) -> ConciergeMetricsResponse:
        """Calculates aggregated telemetry metrics over tracked executions."""
        traces = list(self._in_memory_traces)
        if site_key:
            traces = [t for t in traces if t.site_key == site_key]

        total_requests = len(traces)
        if total_requests == 0:
            return ConciergeMetricsResponse(
                site_key=site_key,
                total_requests=0,
                avg_duration_ms=0.0,
                total_prompt_tokens=0,
                total_completion_tokens=0,
                total_tokens=0,
                total_cost_usd=0.0,
                success_rate=1.0,
                lead_captured_count=0,
                lead_capture_rate=0.0,
                transferred_count=0,
                by_channel={},
                by_model={},
            )

        total_duration = sum(t.duration_ms for t in traces)
        total_prompt = sum(t.prompt_tokens for t in traces)
        total_completion = sum(t.completion_tokens for t in traces)
        total_tokens = sum(t.total_tokens for t in traces)
        total_cost = sum(t.estimated_cost_usd for t in traces)
        ok_count = sum(1 for t in traces if t.result_status == "ok")
        leads_count = sum(1 for t in traces if t.lead_captured)
        transfers = sum(1 for t in traces if t.transferred_to_rockib)

        by_channel: dict[str, int] = {}
        by_model: dict[str, int] = {}
        for t in traces:
            by_channel[t.channel] = by_channel.get(t.channel, 0) + 1
            by_model[t.model] = by_model.get(t.model, 0) + 1

        return ConciergeMetricsResponse(
            site_key=site_key,
            total_requests=total_requests,
            avg_duration_ms=round(total_duration / total_requests, 2),
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            success_rate=round(ok_count / total_requests, 4),
            lead_captured_count=leads_count,
            lead_capture_rate=round(leads_count / total_requests, 4),
            transferred_count=transfers,
            by_channel=by_channel,
            by_model=by_model,
        )


# Global tracing service singleton
concierge_tracing_service = ConciergeTracingService()
