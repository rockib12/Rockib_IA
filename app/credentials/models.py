"""Modèle relationnel pour le stockage chiffré des secrets externes par workspace.

Garantit le respect de l'invariant INV-02 (Isolation du workspace) :
Chaque secret est rattaché de manière étanche à un workspace_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceCredential(Base):
    """Stockage sécurisé et partitionné des secrets de services tiers (Meta, WhatsApp, Twitter, etc.).

    Le champ `encrypted_secret` contient la charge chiffrée par AES-256-GCM liée
    cryptographiquement aux données associées (AD) : `workspace_id:provider:key_alias`.
    """

    __tablename__ = "workspace_credentials"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "provider",
            "key_alias",
            name="uq_workspace_credentials_provider_alias",
        ),
        Index("ix_workspace_credentials_workspace_provider", "workspace_id", "provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Identifiant du service : "whatsapp", "meta", "facebook", "instagram", "twitter", "discord", etc.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Alias permettant d'avoir plusieurs comptes d'un même provider par workspace (ex: "default", "marketing", "support")
    key_alias: Mapped[str] = mapped_column(String(100), default="default", nullable=False)

    # Nonce (12 bytes) + Ciphertext + Tag (16 bytes) encodés en Base64
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)

    # Empreinte SHA-256 du secret brut ou du payload pour comparaison sans déchiffrement
    secret_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    # Données publiques non sensibles : ex. {"phone_number_id": "...", "page_id": "...", "app_id": "..."}
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    # Relation vers le Workspace parent
    workspace = relationship("Workspace", backref="credentials")
