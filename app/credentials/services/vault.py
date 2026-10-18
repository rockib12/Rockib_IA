"""Service de gestion sécurisée du Credential Vault (Phase A).

Implémente le chiffrement authentifié au repos (AEAD AES-256-GCM) lié
au contexte de workspace pour garantir mathématiquement l'invariant INV-02.
"""
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.credentials.exceptions import (
    CredentialDuplicateError,
    CredentialIsolationError,
    CredentialNotFoundError,
    CredentialTamperingError,
)
from app.credentials.models import WorkspaceCredential
from app.credentials.schemas import ResolvedCredential

# Contexte HKDF fixe pour dériver une clé de 256 bits dédiée au vault
VAULT_HKDF_INFO = b"rockib-workspace-credential-vault-v1"


def derive_master_key() -> bytes:
    """Dérive de manière déterministe une clé AES-256 (32 octets) via HKDF-SHA256."""
    key = settings.CREDENTIAL_VAULT_KEY
    if not key:
        raise RuntimeError(
            "CRITICAL: CREDENTIAL_VAULT_KEY is not defined. "
            "The Credential Vault requires an explicit encryption key and cannot fallback to JWT secrets."
        )
    ikm = key.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=VAULT_HKDF_INFO,
    )
    return hkdf.derive(ikm)


def _compute_associated_data(workspace_id: uuid.UUID, provider: str, key_alias: str) -> bytes:
    """Construit les données associées (AD) pour sceller le secret au workspace et au provider."""
    return f"{str(workspace_id).lower()}:{provider.strip().lower()}:{key_alias.strip().lower()}".encode("utf-8")


def encrypt_secret(
    workspace_id: uuid.UUID,
    provider: str,
    key_alias: str,
    raw_secret: str,
) -> Tuple[str, str]:
    """Chiffre un secret avec AES-256-GCM et retourne (ciphertext_b64, secret_fingerprint).

    Le nonce aléatoire de 12 octets est préfixé au ciphertext avant encodage Base64.
    """
    key = derive_master_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ad = _compute_associated_data(workspace_id, provider, key_alias)

    ciphertext = aesgcm.encrypt(nonce, raw_secret.encode("utf-8"), associated_data=ad)
    encrypted_payload = base64.b64encode(nonce + ciphertext).decode("ascii")

    fingerprint = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    return encrypted_payload, fingerprint


def decrypt_secret(
    workspace_id: uuid.UUID,
    provider: str,
    key_alias: str,
    encrypted_secret_b64: str,
) -> str:
    """Déchiffre un secret chiffré par encrypt_secret.

    Lève `CredentialTamperingError` si la clé, le nonce, le ciphertext ou l'AD
    (workspace_id, provider, key_alias) ne correspondent pas exactement.
    """
    try:
        raw_data = base64.b64decode(encrypted_secret_b64.encode("ascii"))
        if len(raw_data) < 28:  # 12 bytes nonce + min 16 bytes tag
            raise CredentialTamperingError("Payload chiffré tronqué ou corrompu.")
        nonce = raw_data[:12]
        ciphertext = raw_data[12:]

        key = derive_master_key()
        aesgcm = AESGCM(key)
        ad = _compute_associated_data(workspace_id, provider, key_alias)

        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=ad)
        return plaintext.decode("utf-8")
    except InvalidTag as exc:
        raise CredentialTamperingError(
            f"Échec de validation d'intégrité AEAD : le secret a été altéré ou transféré depuis un autre workspace."
        ) from exc
    except Exception as exc:
        if isinstance(exc, CredentialTamperingError):
            raise
        raise CredentialTamperingError(f"Erreur de déchiffrement : {exc}") from exc


class WorkspaceCredentialVault:
    """Service asynchrone d'accès et d'administration du Credential Vault."""

    @staticmethod
    async def store_credential(
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        provider: str,
        raw_secret: str,
        key_alias: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        caller_workspace_id: Optional[uuid.UUID] = None,
    ) -> WorkspaceCredential:
        """Enregistre ou met à jour de façon chiffrée un credential pour un workspace."""
        if caller_workspace_id is not None and caller_workspace_id != workspace_id:
            raise CredentialIsolationError(
                f"L'appelant du workspace {caller_workspace_id} ne peut pas stocker un credential pour {workspace_id}."
            )

        provider_norm = provider.strip().lower()
        alias_norm = key_alias.strip().lower()
        metadata_dict = dict(metadata or {})

        encrypted_b64, fingerprint = encrypt_secret(
            workspace_id=workspace_id,
            provider=provider_norm,
            key_alias=alias_norm,
            raw_secret=raw_secret,
        )

        # Vérifier si un credential existe déjà pour ce triplet
        stmt = select(WorkspaceCredential).where(
            WorkspaceCredential.workspace_id == workspace_id,
            WorkspaceCredential.provider == provider_norm,
            WorkspaceCredential.key_alias == alias_norm,
        )
        existing = (await db.execute(stmt)).scalars().first()

        if existing is not None:
            existing.encrypted_secret = encrypted_b64
            existing.secret_fingerprint = fingerprint
            existing.metadata_json = metadata_dict
            existing.is_active = True
            await db.flush()
            return existing

        cred = WorkspaceCredential(
            workspace_id=workspace_id,
            provider=provider_norm,
            key_alias=alias_norm,
            encrypted_secret=encrypted_b64,
            secret_fingerprint=fingerprint,
            metadata_json=metadata_dict,
            is_active=True,
        )
        db.add(cred)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise CredentialDuplicateError(provider=provider_norm, key_alias=alias_norm) from exc

        return cred

    @staticmethod
    async def get_credential(
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        provider: str,
        key_alias: str = "default",
        caller_workspace_id: Optional[uuid.UUID] = None,
    ) -> ResolvedCredential:
        """Récupère et déchiffre un credential après validation stricte d'isolation (INV-02)."""
        # RÈGLE CRITIQUE D'ISOLATION (INV-02)
        if caller_workspace_id is not None and caller_workspace_id != workspace_id:
            raise CredentialIsolationError(
                f"Accès refusé (INV-02) : L'appelant ({caller_workspace_id}) ne peut pas accéder aux secrets du workspace {workspace_id}."
            )

        provider_norm = provider.strip().lower()
        alias_norm = key_alias.strip().lower()

        stmt = select(WorkspaceCredential).where(
            WorkspaceCredential.workspace_id == workspace_id,
            WorkspaceCredential.provider == provider_norm,
            WorkspaceCredential.key_alias == alias_norm,
            WorkspaceCredential.is_active.is_(True),
        )
        record = (await db.execute(stmt)).scalars().first()

        if record is None:
            raise CredentialNotFoundError(provider=provider_norm, key_alias=alias_norm)

        # Déchiffrement AEAD avec liaison cryptographique
        decrypted_secret = decrypt_secret(
            workspace_id=record.workspace_id,
            provider=record.provider,
            key_alias=record.key_alias,
            encrypted_secret_b64=record.encrypted_secret,
        )

        return ResolvedCredential(
            workspace_id=record.workspace_id,
            provider=record.provider,
            key_alias=record.key_alias,
            raw_secret=decrypted_secret,
            metadata=dict(record.metadata_json or {}),
            secret_fingerprint=record.secret_fingerprint,
        )

    @staticmethod
    async def list_credentials(
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        caller_workspace_id: Optional[uuid.UUID] = None,
    ) -> List[WorkspaceCredential]:
        """Liste les credentials enregistrés pour un workspace sans révéler les secrets."""
        if caller_workspace_id is not None and caller_workspace_id != workspace_id:
            raise CredentialIsolationError(
                f"Accès refusé (INV-02) : Impossible de lister les identifiants d'un autre workspace."
            )

        stmt = (
            select(WorkspaceCredential)
            .where(WorkspaceCredential.workspace_id == workspace_id)
            .order_by(WorkspaceCredential.provider, WorkspaceCredential.key_alias)
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def delete_credential(
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        provider: str,
        key_alias: str = "default",
        caller_workspace_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Supprime définitivement un identifiant du Vault."""
        if caller_workspace_id is not None and caller_workspace_id != workspace_id:
            raise CredentialIsolationError(
                f"Accès refusé (INV-02) : Impossible de supprimer les identifiants d'un autre workspace."
            )

        provider_norm = provider.strip().lower()
        alias_norm = key_alias.strip().lower()

        stmt = select(WorkspaceCredential).where(
            WorkspaceCredential.workspace_id == workspace_id,
            WorkspaceCredential.provider == provider_norm,
            WorkspaceCredential.key_alias == alias_norm,
        )
        record = (await db.execute(stmt)).scalars().first()
        if record is None:
            return False

        await db.delete(record)
        await db.flush()
        return True


# Instance singleton pour commodité d'accès
credential_vault = WorkspaceCredentialVault()
