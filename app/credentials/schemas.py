"""Schémas Pydantic pour le Credential Vault (Phase A)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CredentialCreateRequest(BaseModel):
    """Payload de création d'un identifiant externe dans le Vault."""

    provider: str = Field(..., min_length=2, max_length=50, description="ex: 'whatsapp', 'meta', 'twitter'")
    key_alias: str = Field(default="default", min_length=1, max_length=100, description="Alias du compte")
    secret: SecretStr = Field(..., description="Token, mot de passe ou clé privée à chiffrer")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Métadonnées publiques (phone_id, page_id...)")

    model_config = ConfigDict(extra="forbid")


class CredentialSummary(BaseModel):
    """Vue publique/API d'un identifiant sans jamais exposer le secret brut."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    provider: str
    key_alias: str
    secret_fingerprint: str
    metadata: Dict[str, Any] = Field(alias="metadata_json")
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ResolvedCredential(BaseModel):
    """Objet interne délivré uniquement aux connecteurs autorisés après déchiffrement."""

    workspace_id: uuid.UUID
    provider: str
    key_alias: str
    raw_secret: str
    metadata: Dict[str, Any]
    secret_fingerprint: str
