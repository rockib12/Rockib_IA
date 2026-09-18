import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List
from sqlalchemy import DateTime, Enum, ForeignKey, String, SmallInteger, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class GoalStatus(str, PyEnum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Type Enum existant en base (migration 003) : nom explicite obligatoire.
GOAL_STATUS_ENUM = Enum(GoalStatus, name="goal_status")

class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    objective: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[GoalStatus] = mapped_column(
        GOAL_STATUS_ENUM, default=GoalStatus.PENDING, nullable=False
    )
    priority: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    requested_autonomy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    applied_autonomy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    parent_goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("goals.id"), nullable=True)
    goal_metadata: Mapped[dict] = mapped_column(JSON, default={}, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relations
    parent_goal: Mapped[Optional["Goal"]] = relationship("Goal", remote_side=[id])
    tasks: Mapped[List["Task"]] = relationship(back_populates="goal", cascade="all, delete-orphan")
