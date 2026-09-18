import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MemoryType(str, PyEnum):
    fact = "fact"
    preference = "preference"
    decision_rule = "decision_rule"
    experience = "experience"
    project_memory = "project_memory"


class MemoryStatus(str, PyEnum):
    supposed = "supposed"
    deduced = "deduced"
    known = "known"
    verified = "verified"


# Types Enum existants en base (migration 001) : noms explicites obligatoires.
MEMORY_TYPE_ENUM = Enum(MemoryType, name="memory_type")
MEMORY_STATUS_ENUM = Enum(MemoryStatus, name="memory_status")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[MemoryType] = mapped_column(MEMORY_TYPE_ENUM, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        MEMORY_STATUS_ENUM, default=MemoryStatus.supposed.value, nullable=False
    )
    
    content: Mapped[str] = mapped_column(nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    
    confidence_level: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    importance_level: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    
    # embedding: Mapped[Optional[List[float]]] = mapped_column(nullable=True) # Si pgvector est activé
    
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relations
    # workspace: Mapped["Workspace"] = relationship(back_populates="memories") # Ajouté si besoin
