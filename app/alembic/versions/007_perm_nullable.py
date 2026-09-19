"""Classification incertaine persistee : permission_required nullable.

Revision ID: 007_perm_nullable
Revises: 006_audit_controlled_purge

Quand la classification echoue (AMBIGUOUS/UNKNOWN/ERROR), l'orchestrateur doit
persister une Decision d'escalade. A ce stade aucune permission n'a ete
determinee : fabriquer une valeur par defaut (ex. READ) fausserait l'historique
et violerait l'interdiction de presumer un droit non defini (contrat §6).
La colonne devient donc nullable ; NULL signifie « jamais classifie ».

Note : l'identifiant de revision est volontairement court (<= 32 caracteres),
la colonne alembic_version.version_num etant un VARCHAR(32).
"""
from alembic import op
import sqlalchemy as sa

revision = "007_perm_nullable"
down_revision = "006_audit_controlled_purge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("decisions", "permission_required", nullable=True)


def downgrade() -> None:
    conn = op.get_bind()
    remaining = conn.execute(
        sa.text("SELECT COUNT(*) FROM decisions WHERE permission_required IS NULL")
    ).scalar()
    if remaining:
        raise RuntimeError(
            f"{remaining} decision(s) ont permission_required=NULL "
            "(escalades legitimes). Le downgrade fabriquerait une permission "
            "qui n'a jamais existe — refuse. Traite ou archive ces lignes "
            "manuellement avant de redescendre."
        )
    op.alter_column(
        "decisions",
        "permission_required",
        existing_type=sa.Enum(
            "READ", "CREATE", "UPDATE", "DELETE", "SEND",
            "PUBLISH", "SPEND",
            name="permission_action",
        ),
        nullable=False,
    )
