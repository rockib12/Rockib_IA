"""Persistence and tenant-scoped retrieval for consented Concierge leads."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.inbound.models import ConciergeLead
from app.inbound.schemas import CallMeBackRequest


def _retention_cutoff() -> datetime:
    days = max(1, min(settings.CONCIERGE_LEAD_RETENTION_DAYS, 3650))
    return datetime.now(timezone.utc) - timedelta(days=days)


async def record_callback_lead(
    db: AsyncSession,
    site_key: str,
    request: CallMeBackRequest,
) -> ConciergeLead:
    """Persist an explicitly consented callback before acknowledging receipt."""
    await purge_expired_leads(db, commit=False)
    lead = ConciergeLead(
        site_key=site_key,
        contact_name=request.contact_name.strip() if request.contact_name else None,
        phone_number=request.phone_number.strip(),
        topic=request.topic.strip() if request.topic else None,
        channel=request.channel.lower(),
        status="received",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def list_site_leads(db: AsyncSession, site_key: str) -> list[ConciergeLead]:
    """Return only recent leads for the authenticated site owner."""
    await purge_expired_leads(db, commit=False)
    await db.commit()
    result = await db.execute(
        select(ConciergeLead)
        .where(ConciergeLead.site_key == site_key)
        .order_by(ConciergeLead.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


async def purge_expired_leads(db: AsyncSession, *, commit: bool = True) -> int:
    result = await db.execute(delete(ConciergeLead).where(ConciergeLead.created_at < _retention_cutoff()))
    if commit:
        await db.commit()
    return int(result.rowcount or 0)


async def update_lead_status(
    db: AsyncSession,
    site_key: str,
    lead_id: str | uuid.UUID,
    new_status: str,
) -> ConciergeLead | None:
    """Update follow-up status for a tenant's lead (e.g. received -> contacted -> converted)."""
    if isinstance(lead_id, str):
        try:
            lead_id = uuid.UUID(lead_id)
        except ValueError:
            return None

    result = await db.execute(
        select(ConciergeLead).where(
            ConciergeLead.id == lead_id,
            ConciergeLead.site_key == site_key,
        )
    )
    lead = result.scalars().first()
    if not lead:
        return None

    lead.status = new_status
    await db.commit()
    await db.refresh(lead)
    return lead


async def export_leads_csv(db: AsyncSession, site_key: str) -> str:
    """Generate CSV string of tenant leads for CRM or sales team follow-up."""
    leads = await list_site_leads(db, site_key)
    lines = ["id,site_key,contact_name,phone_number,topic,channel,status,created_at"]
    for l in leads:
        name = (l.contact_name or "").replace(",", " ").replace('"', '""')
        topic = (l.topic or "").replace(",", " ").replace("\n", " ").replace('"', '""')
        lines.append(
            f'"{l.id}","{l.site_key}","{name}","{l.phone_number}","{topic}","{l.channel}","{l.status}","{l.created_at.isoformat()}"'
        )
    return "\n".join(lines)

