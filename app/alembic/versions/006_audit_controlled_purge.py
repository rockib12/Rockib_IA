"""Audit append-only : purge contrôlée pour l'effacement légal.

Revision ID: 006_audit_controlled_purge
Revises: 005_execution_reliable

Le journal reste non réécrivable par les agents exécutants. Une transaction de
maintenance explicitement marquée peut toutefois supprimer des entrées pour un
effacement légal contrôlé (§8) : sans ce chemin, la suppression d'un workspace
serait impossible à cause de la cascade, et l'effacement légal deviendrait une
opération interdite non documentée plutôt qu'une opération contrôlée.
"""
from alembic import op

revision = "006_audit_controlled_purge"
down_revision = "005_execution_reliable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION rockib_audit_append_only() RETURNS trigger AS $$
        BEGIN
            IF current_setting('rockib.audit_maintenance', true) = 'on' THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;
            RAISE EXCEPTION
                'audit_entries est append-only : % refuse (activer rockib.audit_maintenance pour un effacement controle)',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION rockib_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_entries est append-only : % refuse', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )