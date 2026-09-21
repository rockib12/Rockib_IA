import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TaskStatus(str, PyEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


# Type Enum existant en base (migrations 003, 008, 009) : nom explicite obligatoire.
TASK_STATUS_ENUM = Enum(TaskStatus, name="task_status")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("id", "goal_id", name="uq_tasks_id_goal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("decisions.id"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        TASK_STATUS_ENUM, default=TaskStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relations
    goal: Mapped["Goal"] = relationship("Goal", back_populates="tasks")

    # Dépendances amont requises par CETTE tâche (task_id == self.id)
    dependencies: Mapped[List["TaskDependency"]] = relationship(
        "TaskDependency",
        primaryjoin="Task.id == TaskDependency.task_id",
        foreign_keys="TaskDependency.task_id",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    # Tâches descendantes qui dépendent de CETTE tâche (depends_on_task_id == self.id)
    dependents: Mapped[List["TaskDependency"]] = relationship(
        "TaskDependency",
        primaryjoin="Task.id == TaskDependency.depends_on_task_id",
        foreign_keys="TaskDependency.depends_on_task_id",
        back_populates="depends_on_task",
        cascade="all, delete-orphan",
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint(
            "task_id != depends_on_task_id",
            name="check_task_no_self_dependency",
        ),
        UniqueConstraint(
            "task_id",
            "depends_on_task_id",
            name="uq_task_dependencies_task_depends",
        ),
        ForeignKeyConstraint(
            ["task_id", "goal_id"],
            ["tasks.id", "tasks.goal_id"],
            name="fk_task_dependencies_task_goal",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["depends_on_task_id", "goal_id"],
            ["tasks.id", "tasks.goal_id"],
            name="fk_task_dependencies_depends_goal",
            ondelete="CASCADE",
        ),
        Index("ix_task_dependencies_goal_id", "goal_id"),
        Index("ix_task_dependencies_task_id", "task_id"),
        Index("ix_task_dependencies_depends_on", "depends_on_task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relations explicites vers Task (primaryjoin & foreign_keys désambiguïsés)
    task: Mapped["Task"] = relationship(
        "Task",
        primaryjoin="TaskDependency.task_id == Task.id",
        foreign_keys=[task_id],
        back_populates="dependencies",
    )
    depends_on_task: Mapped["Task"] = relationship(
        "Task",
        primaryjoin="TaskDependency.depends_on_task_id == Task.id",
        foreign_keys=[depends_on_task_id],
        back_populates="dependents",
    )
    goal: Mapped["Goal"] = relationship("Goal")
