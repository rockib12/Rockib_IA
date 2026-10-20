"""Durable, tenant-scoped lead records for the Concierge."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConciergeLead(Base):
    __tablename__ = "concierge_leads"
    __table_args__ = (
        Index("ix_concierge_leads_site_created", "site_key", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_key: Mapped[str] = mapped_column(String(63), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    consent_version: Mapped[str] = mapped_column(String(20), nullable=False, default="2026-10")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class ConciergeExecutionTrace(Base):
    """Detailed telemetry and audit trace per conversation turn / execution."""
    __tablename__ = "concierge_execution_traces"
    __table_args__ = (
        Index("ix_concierge_traces_site_created", "site_key", "created_at"),
        Index("ix_concierge_traces_conv_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    site_key: Mapped[str] = mapped_column(String(63), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="chat")
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tools_called: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    result_status: Mapped[str] = mapped_column(String(30), nullable=False, default="ok")
    lead_captured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transferred_to_rockib: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


