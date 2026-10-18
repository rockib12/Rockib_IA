"""Router FastAPI pour les connecteurs Réseaux Sociaux & Meta HMAC (Phase 6).

Fournit :
- GET /api/v1/connectors/status : Liste l'état de connexion des 7 réseaux pour le workspace.
- POST /api/v1/connectors/save : Enregistre de manière chiffrée (AES-256-GCM) les identifiants d'un réseau.
- POST /api/v1/connectors/test : Déclenche un test de publication ou d'envoi avec signature HMAC-SHA256.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.connectors.social_connectors import (
    compute_meta_appsecret_proof,
    get_credential_safe,
)
from app.core.database import get_async_db
from app.credentials.models import WorkspaceCredential
from app.credentials.services.vault import credential_vault
from app.execution.models import ActionRecord
from app.execution.services.reliable_executor import dispatch_authorized_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["Social Connectors & Meta Ads"])


class NetworkStatusItem(BaseModel):
    id: str
    name: str
    category: str
    icon: str
    is_connected: bool
    mode: str  # "live" | "sandbox"
    has_hmac: bool
    configured_keys: List[str]
    description: str


class SaveCredentialsRequest(BaseModel):
    workspace_id: uuid.UUID
    provider: str = Field(..., description="ex: 'meta', 'twitter', 'linkedin', 'discord'")
    credentials: Dict[str, str] = Field(..., description="Paires clé-valeur (ex: access_token, app_secret, page_id)")


class TestConnectorRequest(BaseModel):
    workspace_id: uuid.UUID
    tool: str = Field(..., description="ex: 'facebook', 'instagram', 'whatsapp', 'meta_ads', 'twitter', 'linkedin', 'discord'")
    operation: str = Field(default="post", description="ex: 'post', 'create', 'send'")
    arguments: Dict[str, Any] = Field(default_factory=dict)


@router.get("/status", response_model=List[NetworkStatusItem])
async def get_connectors_status(
    workspace_id: Optional[uuid.UUID] = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Retourne l'état de configuration et de sécurité HMAC des 7 réseaux sociaux."""
    ws_id = workspace_id or (current_user.workspaces[0].id if getattr(current_user, "workspaces", None) else None)

    # Vérification des clés dans le Vault ou dans l'environnement
    meta_token = await get_credential_safe(ws_id, "meta", "access_token") or await get_credential_safe(ws_id, "meta", "page_access_token")
    meta_secret = await get_credential_safe(ws_id, "meta", "app_secret")
    page_id = await get_credential_safe(ws_id, "meta", "page_id")
    ig_id = await get_credential_safe(ws_id, "meta", "instagram_account_id")
    ad_act_id = await get_credential_safe(ws_id, "meta", "ad_account_id")
    wa_phone_id = await get_credential_safe(ws_id, "meta", "whatsapp_phone_number_id")
    wa_token = await get_credential_safe(ws_id, "meta", "whatsapp_access_token")

    tw_token = await get_credential_safe(ws_id, "twitter", "bearer_token")
    li_token = await get_credential_safe(ws_id, "linkedin", "access_token")
    dc_url = await get_credential_safe(ws_id, "discord", "webhook_url")

    networks = [
        NetworkStatusItem(
            id="facebook",
            name="Facebook Pages Pro",
            category="Meta",
            icon="facebook",
            is_connected=bool(meta_token and page_id),
            mode="live" if bool(meta_token and page_id) else "sandbox",
            has_hmac=bool(meta_secret),
            configured_keys=[k for k, v in [("page_access_token", meta_token), ("page_id", page_id), ("app_secret", meta_secret)] if v],
            description="Publication officielle sur Page Pro avec signature HMAC appsecret_proof.",
        ),
        NetworkStatusItem(
            id="instagram",
            name="Instagram Business",
            category="Meta",
            icon="instagram",
            is_connected=bool(meta_token and ig_id),
            mode="live" if bool(meta_token and ig_id) else "sandbox",
            has_hmac=bool(meta_secret),
            configured_keys=[k for k, v in [("access_token", meta_token), ("instagram_account_id", ig_id), ("app_secret", meta_secret)] if v],
            description="Publication automatique 2 étapes (Conteneur + Média) signée HMAC.",
        ),
        NetworkStatusItem(
            id="meta_ads",
            name="Meta Ads (Facebook & IG)",
            category="Meta Marketing",
            icon="target",
            is_connected=bool(meta_token and ad_act_id),
            mode="live" if bool(meta_token and ad_act_id) else "sandbox",
            has_hmac=bool(meta_secret),
            configured_keys=[k for k, v in [("access_token", meta_token), ("ad_account_id", ad_act_id), ("app_secret", meta_secret)] if v],
            description="Création de campagnes publicitaires avec garde-fou budgétaire et HMAC.",
        ),
        NetworkStatusItem(
            id="whatsapp",
            name="WhatsApp Cloud API",
            category="Meta Business",
            icon="message-circle",
            is_connected=bool(wa_token and wa_phone_id),
            mode="live" if bool(wa_token and wa_phone_id) else "sandbox",
            has_hmac=bool(meta_secret),
            configured_keys=[k for k, v in [("whatsapp_access_token", wa_token), ("whatsapp_phone_number_id", wa_phone_id), ("app_secret", meta_secret)] if v],
            description="Messagerie interactive et validation HMAC des webhooks X-Hub-Signature-256.",
        ),
        NetworkStatusItem(
            id="twitter",
            name="Twitter / X API v2",
            category="Social Media",
            icon="twitter",
            is_connected=bool(tw_token),
            mode="live" if bool(tw_token) else "sandbox",
            has_hmac=False,
            configured_keys=[k for k, v in [("bearer_token", tw_token)] if v],
            description="Diffusion de publications sur le réseau X via l'API v2 officielle.",
        ),
        NetworkStatusItem(
            id="linkedin",
            name="LinkedIn UGC",
            category="B2B Network",
            icon="linkedin",
            is_connected=bool(li_token),
            mode="live" if bool(li_token) else "sandbox",
            has_hmac=False,
            configured_keys=[k for k, v in [("access_token", li_token)] if v],
            description="Partage d'articles et de posts sur les profils et pages entreprise.",
        ),
        NetworkStatusItem(
            id="discord",
            name="Discord Alerts & Webhooks",
            category="Internal Comms",
            icon="bell",
            is_connected=bool(dc_url),
            mode="live" if bool(dc_url) else "sandbox",
            has_hmac=False,
            configured_keys=[k for k, v in [("webhook_url", dc_url)] if v],
            description="Canaux d'équipe et webhooks d'alertes instantanés.",
        ),
    ]

    return networks


@router.post("/save")
async def save_connector_credentials(
    payload: SaveCredentialsRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Enregistre de manière chiffrée (AEAD AES-256-GCM) les clés du réseau dans le Vault."""
    saved_keys = []
    for key_alias, secret_value in payload.credentials.items():
        if secret_value and secret_value.strip():
            await credential_vault.store_credential(
                db=db,
                workspace_id=payload.workspace_id,
                provider=payload.provider.lower().strip(),
                key_alias=key_alias.lower().strip(),
                raw_secret=secret_value.strip(),
            )
            saved_keys.append(key_alias)

    await db.commit()

    # Aperçu de l'appsecret_proof si Meta
    proof_preview = None
    if payload.provider.lower() == "meta" and "app_secret" in payload.credentials and "access_token" in payload.credentials:
        proof_preview = compute_meta_appsecret_proof(payload.credentials["app_secret"], payload.credentials["access_token"])

    return {
        "status": "success",
        "provider": payload.provider,
        "saved_keys": saved_keys,
        "hmac_proof_preview": proof_preview,
        "encryption": "AEAD AES-256-GCM (HKDF-SHA256)",
    }


@router.post("/test")
async def test_connector_action(
    payload: TestConnectorRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Déclenche l'action du connecteur pour tester la publication en direct ou en sandbox."""
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=payload.workspace_id,
        agent_id=getattr(current_user, "id", uuid.uuid4()),
        decision_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        objective=f"Test interactif {payload.tool}.{payload.operation}",
        tool=payload.tool.lower().strip(),
        operation=payload.operation.lower().strip(),
        arguments=payload.arguments,
        canonical_fingerprint="f" * 64,
        idempotency_key="k" * 64,
        version=1,
    )

    from app.connectors.social_connectors import (
        discord_send_handler,
        facebook_post_handler,
        instagram_post_handler,
        linkedin_post_handler,
        meta_ads_create_handler,
        twitter_post_handler,
        whatsapp_send_handler,
    )

    handlers = {
        ("facebook", "post"): facebook_post_handler,
        ("instagram", "post"): instagram_post_handler,
        ("whatsapp", "send"): whatsapp_send_handler,
        ("meta_ads", "create"): meta_ads_create_handler,
        ("twitter", "post"): twitter_post_handler,
        ("linkedin", "post"): linkedin_post_handler,
        ("discord", "send"): discord_send_handler,
    }

    key = (action.tool, action.operation)
    handler = handlers.get(key)
    if not handler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aucun handler configuré pour ({action.tool}, {action.operation})",
        )

    result = await handler(action)
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "provider_reference": result.provider_reference,
        "cost_amount": float(result.cost_amount) if result.cost_amount else 0.0,
        "cost_unit": result.cost_unit,
    }
