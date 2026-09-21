"""Task ACTIVE -> RUNNING : renommage a sens preserve.

Revision ID: 008_task_running
Revises: 007_perm_nullable

Le type PostgreSQL ``task_status`` est un vrai ENUM : le renommage se fait au
niveau du type (catalogue), pas des lignes. ``ALTER TYPE ... RENAME VALUE``
remappe la valeur atomiquement — les lignes existantes en ACTIVE sont
preservees et relues comme RUNNING (§5, §11). Aucun UPDATE, aucune fenetre ou
deux labels coexisteraient avec le meme sens, aucun historique perdu.

Constate pre-migration (2026-09-19) : tables ``tasks`` et ``goals`` vides
(COUNT(*) = 0) — aucun backfill requis, la migration reste ecrite pour
preserver d'eventuelles lignes futures/passees.
"""
from alembic import op

revision = "008_task_running"
down_revision = "007_perm_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_status RENAME VALUE 'ACTIVE' TO 'RUNNING'")


def downgrade() -> None:
    op.execute("ALTER TYPE task_status RENAME VALUE 'RUNNING' TO 'ACTIVE'")
