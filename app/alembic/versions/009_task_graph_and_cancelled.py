"""Task CANCELLED enum value & task_dependencies table.

Revision ID: 009_task_graph_and_cancelled
Revises: 008_task_running
Create Date: 2026-09-20 08:00:00.000000

1. Ajout de la valeur terminale CANCELLED a l'ENUM natif task_status (§5).
2. Contrainte d'unicite composite sur tasks(id, goal_id) pour permettre
   les cles etrangeres composites garantissant l'appartenance au meme Goal.
3. Creation de la table task_dependencies avec contraintes d'integrite :
   - pas d'auto-dependance (CHECK task_id != depends_on_task_id)
   - unicite de l'arc (UNIQUE task_id, depends_on_task_id)
   - verification que les deux taches appartiennent STRICTEMENT au meme goal_id
     via FK composites (task_id, goal_id) -> tasks(id, goal_id)
     et (depends_on_task_id, goal_id) -> tasks(id, goal_id).
"""
from alembic import op
import sqlalchemy as sa

revision = "009_task_graph_and_cancelled"
down_revision = "008_task_running"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Ajout de CANCELLED a task_status
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'CANCELLED'")

    # 2. Contrainte unique composite sur tasks(id, goal_id) pour FK composite
    op.create_unique_constraint("uq_tasks_id_goal_id", "tasks", ["id", "goal_id"])

    # 3. Creation de la table task_dependencies
    op.create_table(
        "task_dependencies",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("goal_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_task_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "task_id != depends_on_task_id",
            name="check_task_no_self_dependency",
        ),
        sa.UniqueConstraint(
            "task_id",
            "depends_on_task_id",
            name="uq_task_dependencies_task_depends",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "goal_id"],
            ["tasks.id", "tasks.goal_id"],
            name="fk_task_dependencies_task_goal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id", "goal_id"],
            ["tasks.id", "tasks.goal_id"],
            name="fk_task_dependencies_depends_goal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name="fk_task_dependencies_goal",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_task_dependencies_goal_id", "task_dependencies", ["goal_id"]
    )
    op.create_index(
        "ix_task_dependencies_task_id", "task_dependencies", ["task_id"]
    )
    op.create_index(
        "ix_task_dependencies_depends_on",
        "task_dependencies",
        ["depends_on_task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_dependencies_depends_on", table_name="task_dependencies")
    op.drop_index("ix_task_dependencies_task_id", table_name="task_dependencies")
    op.drop_index("ix_task_dependencies_goal_id", table_name="task_dependencies")
    op.drop_table("task_dependencies")
    op.drop_constraint("uq_tasks_id_goal_id", "tasks", type_="unique")
