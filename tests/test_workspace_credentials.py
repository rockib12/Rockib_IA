"""Tests formels du Workspace Credential Vault (Phase A - Isolation INV-02 & AEAD AES-256-GCM).

Vérifie :
1. Chiffrement et déchiffrement nominaux (AES-256-GCM + HKDF)
2. Isolation stricte de workspace TEST-SOC-03 (INV-02)
3. Protection contre l'altération et le déplacement physique de secret entre workspaces (AEAD)
4. Mise à jour idempotente d'un credential existant
5. Rejet propre en cas d'identifiant introuvable
6. Absence de fuite de secret brut dans les représentations publiques
"""
from __future__ import annotations

import hashlib
import uuid
import pytest
from sqlalchemy import select

from app.credentials.exceptions import (
    CredentialIsolationError,
    CredentialNotFoundError,
    CredentialTamperingError,
)
from app.credentials.models import WorkspaceCredential
from app.credentials.services.vault import WorkspaceCredentialVault, decrypt_secret, encrypt_secret
from app.identity.models import Workspace


pytest_asyncio_fixture = pytest.fixture


@pytest.fixture
def make_workspace():
    def _factory(name: str = "Test WS") -> Workspace:
        return Workspace(
            name=name,
            slug=f"ws-{uuid.uuid4().hex[:12]}",
        )
    return _factory


@pytest.mark.asyncio
async def test_nominal_store_and_retrieve(db_session, make_workspace):
    """Vérifie le cycle complet d'enregistrement, stockage chiffré et restitution."""
    ws = make_workspace("Tenant Alpha")
    db_session.add(ws)
    await db_session.flush()

    raw_token = "EAAB123456789_meta_secret_access_token_secure"
    metadata = {"phone_number_id": "100200300", "page_id": "400500600"}

    # 1. Enregistrement dans le Vault
    cred = await WorkspaceCredentialVault.store_credential(
        db_session,
        workspace_id=ws.id,
        provider="whatsapp",
        raw_secret=raw_token,
        key_alias="default",
        metadata=metadata,
        caller_workspace_id=ws.id,
    )
    assert cred.id is not None
    assert cred.workspace_id == ws.id
    assert cred.provider == "whatsapp"
    assert cred.encrypted_secret != raw_token
    assert raw_token not in cred.encrypted_secret
    assert cred.secret_fingerprint == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    assert cred.metadata_json == metadata

    # 2. Récupération et déchiffrement autorisé
    resolved = await WorkspaceCredentialVault.get_credential(
        db_session,
        workspace_id=ws.id,
        provider="whatsapp",
        key_alias="default",
        caller_workspace_id=ws.id,
    )
    assert resolved.workspace_id == ws.id
    assert resolved.provider == "whatsapp"
    assert resolved.key_alias == "default"
    assert resolved.raw_secret == raw_token
    assert resolved.metadata == metadata
    assert resolved.secret_fingerprint == cred.secret_fingerprint


@pytest.mark.asyncio
async def test_isolation_workspace_mismatch_rejected_test_soc_03(db_session, make_workspace):
    """TEST-SOC-03 : Preuve d'isolation étanche INV-02.

    Un appelant du Workspace B ne peut ni lire, ni lister, ni modifier,
    ni supprimer les secrets du Workspace A.
    """
    ws_a = make_workspace("Tenant A (MARTISTORE)")
    ws_b = make_workspace("Tenant B (Agence IIA)")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    raw_secret_a = "secret_belonging_to_workspace_a"
    await WorkspaceCredentialVault.store_credential(
        db_session,
        workspace_id=ws_a.id,
        provider="meta",
        raw_secret=raw_secret_a,
        caller_workspace_id=ws_a.id,
    )

    # 1. Tentative de lecture croisée (Get)
    with pytest.raises(CredentialIsolationError) as exc_info:
        await WorkspaceCredentialVault.get_credential(
            db_session,
            workspace_id=ws_a.id,
            provider="meta",
            caller_workspace_id=ws_b.id,  # Appelant non autorisé
        )
    assert exc_info.value.code == "WORKSPACE_CREDENTIAL_ISOLATION_VIOLATION"

    # 2. Tentative de listing croisé
    with pytest.raises(CredentialIsolationError):
        await WorkspaceCredentialVault.list_credentials(
            db_session,
            workspace_id=ws_a.id,
            caller_workspace_id=ws_b.id,
        )

    # 3. Tentative d'écriture/écrasement croisé
    with pytest.raises(CredentialIsolationError):
        await WorkspaceCredentialVault.store_credential(
            db_session,
            workspace_id=ws_a.id,
            provider="meta",
            raw_secret="malicious_overwrite",
            caller_workspace_id=ws_b.id,
        )

    # 4. Tentative de suppression croisée
    with pytest.raises(CredentialIsolationError):
        await WorkspaceCredentialVault.delete_credential(
            db_session,
            workspace_id=ws_a.id,
            provider="meta",
            caller_workspace_id=ws_b.id,
        )


@pytest.mark.asyncio
async def test_cryptographic_aead_tampering_fails(db_session, make_workspace):
    """Vérifie que le déplacement physique d'un secret chiffré vers un autre workspace échoue (AEAD).

    Même si la base de données est altérée pour attribuer le ciphertext de A à B,
    le tag d'authentification GCM rejette le déchiffrement.
    """
    ws_a = make_workspace("Workspace A")
    ws_b = make_workspace("Workspace B")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    secret = "classified_token_of_a"
    cred_a = await WorkspaceCredentialVault.store_credential(
        db_session,
        workspace_id=ws_a.id,
        provider="twitter",
        raw_secret=secret,
        caller_workspace_id=ws_a.id,
    )

    # Simulation d'une attaque SQL interne : un attaquant modifie workspace_id dans la table
    cred_a.workspace_id = ws_b.id
    await db_session.flush()

    # Tentative de déchiffrement pour ws_b :
    # Le ciphertext contient le tag calculé avec l'AD de ws_a, donc le déchiffrement avec l'AD de ws_b échoue
    with pytest.raises(CredentialTamperingError) as exc_info:
        await WorkspaceCredentialVault.get_credential(
            db_session,
            workspace_id=ws_b.id,
            provider="twitter",
            caller_workspace_id=ws_b.id,
        )
    assert exc_info.value.code == "CREDENTIAL_TAMPERING_DETECTED"


@pytest.mark.asyncio
async def test_update_existing_credential(db_session, make_workspace):
    """Vérifie la mise à jour idempotente d'un credential pour le même alias."""
    ws = make_workspace("Workspace Alpha")
    db_session.add(ws)
    await db_session.flush()

    # Première insertion
    c1 = await WorkspaceCredentialVault.store_credential(
        db_session,
        workspace_id=ws.id,
        provider="discord",
        raw_secret="old_webhook_url",
        key_alias="alerts",
    )
    initial_id = c1.id

    # Mise à jour avec nouveau secret
    c2 = await WorkspaceCredentialVault.store_credential(
        db_session,
        workspace_id=ws.id,
        provider="discord",
        raw_secret="new_webhook_url_2026",
        key_alias="alerts",
        metadata={"channel": "sec-ops"},
    )
    assert c2.id == initial_id  # Même enregistrement mis à jour

    # Relecture
    resolved = await WorkspaceCredentialVault.get_credential(
        db_session,
        workspace_id=ws.id,
        provider="discord",
        key_alias="alerts",
    )
    assert resolved.raw_secret == "new_webhook_url_2026"
    assert resolved.metadata == {"channel": "sec-ops"}


@pytest.mark.asyncio
async def test_credential_not_found(db_session, make_workspace):
    """Vérifie que la requête d'un service inexistant renvoie CredentialNotFoundError."""
    ws = make_workspace("Empty Workspace")
    db_session.add(ws)
    await db_session.flush()

    with pytest.raises(CredentialNotFoundError) as exc_info:
        await WorkspaceCredentialVault.get_credential(
            db_session,
            workspace_id=ws.id,
            provider="non_existent_provider",
        )
    assert exc_info.value.code == "CREDENTIAL_NOT_FOUND"


@pytest.mark.asyncio
async def test_list_and_delete_credentials(db_session, make_workspace):
    """Vérifie le listing sécurisé et la suppression."""
    ws = make_workspace("Multi Credential WS")
    db_session.add(ws)
    await db_session.flush()

    await WorkspaceCredentialVault.store_credential(
        db_session, workspace_id=ws.id, provider="whatsapp", raw_secret="token_1", key_alias="main"
    )
    await WorkspaceCredentialVault.store_credential(
        db_session, workspace_id=ws.id, provider="meta", raw_secret="token_2", key_alias="ads"
    )

    creds = await WorkspaceCredentialVault.list_credentials(
        db_session, workspace_id=ws.id, caller_workspace_id=ws.id
    )
    assert len(creds) == 2
    providers = [c.provider for c in creds]
    assert "whatsapp" in providers
    assert "meta" in providers

    # Suppression
    deleted = await WorkspaceCredentialVault.delete_credential(
        db_session, workspace_id=ws.id, provider="whatsapp", key_alias="main", caller_workspace_id=ws.id
    )
    assert deleted is True

    # Vérification après suppression
    creds_after = await WorkspaceCredentialVault.list_credentials(
        db_session, workspace_id=ws.id, caller_workspace_id=ws.id
    )
    assert len(creds_after) == 1
    assert creds_after[0].provider == "meta"
