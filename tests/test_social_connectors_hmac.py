"""Tests unitaires et de sécurité cryptographique HMAC pour les connecteurs Meta & Réseaux Sociaux.

Vérifie :
- Calcul déterministe de la preuve d'application Meta appsecret_proof (HMAC-SHA256).
- Validation cryptographique timing-safe des webhooks entrants Meta X-Hub-Signature-256.
- Protection contre l'altération de payload (tampering rejection).
- Exécution des connecteurs Facebook, Instagram, WhatsApp, Meta Ads, Twitter, LinkedIn et Discord.
- Respect strict de la politique de sécurité financière sur les budgets publicitaires Meta Ads.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from decimal import Decimal

import pytest

from app.connectors.social_connectors import (
    compute_meta_appsecret_proof,
    discord_send_handler,
    facebook_post_handler,
    instagram_post_handler,
    linkedin_post_handler,
    meta_ads_create_handler,
    twitter_post_handler,
    verify_meta_webhook_hmac,
    whatsapp_send_handler,
)
from app.execution.models import ActionRecord


# ---------------------------------------------------------------------------
# Tests Cryptographiques HMAC-SHA256
# ---------------------------------------------------------------------------

def test_meta_appsecret_proof_calculation():
    """Vérifie le calcul conforme au standard officiel Meta : hmac_sha256(app_secret, access_token)."""
    app_secret = "meta_app_secret_test_12345"
    access_token = "EAABwzLix...token_user_page"

    expected = hmac.new(
        app_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    proof = compute_meta_appsecret_proof(app_secret, access_token)
    assert proof == expected
    assert len(proof) == 64  # Condensat SHA256 hexadécimal


def test_meta_appsecret_proof_empty_fallback():
    """Vérifie le retour d'une chaîne vide si les clés sont manquantes."""
    assert compute_meta_appsecret_proof("", "token") == ""
    assert compute_meta_appsecret_proof("secret", "") == ""


def test_meta_webhook_hmac_verification_valid():
    """Valide l'acceptation d'un webhook Meta avec signature X-Hub-Signature-256 authentique."""
    app_secret = "rockib_meta_webhook_secret_999"
    payload = b'{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"messages":[{"text":{"body":"Bonjour"}}]}}]}]}'

    signature = "sha256=" + hmac.new(app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    assert verify_meta_webhook_hmac(payload, app_secret, signature) is True


def test_meta_webhook_hmac_verification_tampered_payload():
    """Rejette immédiatement un webhook dont le contenu a été altéré par un attaquant (Anti-Tampering)."""
    app_secret = "rockib_meta_webhook_secret_999"
    legit_payload = b'{"amount": 100}'
    tampered_payload = b'{"amount": 9999}'

    signature = "sha256=" + hmac.new(app_secret.encode("utf-8"), legit_payload, hashlib.sha256).hexdigest()

    # Le payload a été falsifié -> rejet formel
    assert verify_meta_webhook_hmac(tampered_payload, app_secret, signature) is False


def test_meta_webhook_hmac_verification_bad_secret():
    """Rejette un webhook si le secret applicatif ne correspond pas."""
    payload = b'{"event": "ping"}'
    signature = "sha256=" + hmac.new(b"secret_a", payload, hashlib.sha256).hexdigest()

    assert verify_meta_webhook_hmac(payload, "secret_b", signature) is False


# ---------------------------------------------------------------------------
# Tests des Handlers d'Exécution
# ---------------------------------------------------------------------------

def _make_social_action(tool: str, operation: str, arguments: dict) -> ActionRecord:
    return ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        objective=f"Test {tool}.{operation}",
        tool=tool,
        operation=operation,
        arguments=arguments,
        canonical_fingerprint="f" * 64,
        idempotency_key="k" * 64,
        version=1,
    )


@pytest.mark.asyncio
async def test_facebook_post_nominal():
    action = _make_social_action("facebook", "post", {"text": "Nouveau lancement Rockib AI !"})
    res = await facebook_post_handler(action)
    assert res.success is True
    assert "Facebook" in res.output
    assert res.provider_reference is not None


@pytest.mark.asyncio
async def test_facebook_post_missing_text():
    action = _make_social_action("facebook", "post", {})
    res = await facebook_post_handler(action)
    assert res.success is False
    assert "Missing 'text'" in res.error


@pytest.mark.asyncio
async def test_instagram_post_nominal():
    action = _make_social_action("instagram", "post", {
        "image_url": "https://rockib-quenum.netlify.app/og-image.png",
        "caption": "Architecture IA en production #AI",
    })
    res = await instagram_post_handler(action)
    assert res.success is True
    assert "Instagram" in res.output


@pytest.mark.asyncio
async def test_instagram_post_missing_image():
    action = _make_social_action("instagram", "post", {"caption": "Sans image"})
    res = await instagram_post_handler(action)
    assert res.success is False
    assert "Missing 'image_url'" in res.error


@pytest.mark.asyncio
async def test_whatsapp_send_nominal():
    action = _make_social_action("whatsapp", "send", {
        "phone_number": "+2290146420922",
        "message": "Bonjour, votre commande MARTISTORE a bien été expédiée !",
    })
    res = await whatsapp_send_handler(action)
    assert res.success is True
    assert "WhatsApp" in res.output


@pytest.mark.asyncio
async def test_whatsapp_send_missing_args():
    action = _make_social_action("whatsapp", "send", {"phone_number": "+2290146420922"})
    res = await whatsapp_send_handler(action)
    assert res.success is False
    assert "Missing 'phone_number' or 'message'" in res.error


@pytest.mark.asyncio
async def test_meta_ads_create_nominal():
    action = _make_social_action("meta_ads", "create", {
        "name": "Campagne Promo MARTISTORE Q4",
        "objective": "OUTCOME_SALES",
        "daily_budget_cents": 1500,  # 15.00 EUR
    })
    res = await meta_ads_create_handler(action)
    assert res.success is True
    assert "Campaign 'Campagne Promo MARTISTORE Q4'" in res.output
    assert res.cost_amount == Decimal("15.0")
    assert res.cost_unit == "EUR"


@pytest.mark.asyncio
async def test_meta_ads_create_financial_cap_enforcement():
    """Vérifie que l'Arbitre et le connecteur bloquent tout budget excessif non autorisé."""
    action = _make_social_action("meta_ads", "create", {
        "name": "Campagne Attaque Dépense Excessive",
        "daily_budget_cents": 200000,  # 2 000.00 EUR -> Dépasse le plafond autorisé de 500€
    })
    res = await meta_ads_create_handler(action)
    assert res.success is False
    assert res.error_code == "FINANCIAL_POLICY_VIOLATION"
    assert "Budget exceeds maximum safety threshold" in res.error


@pytest.mark.asyncio
async def test_twitter_post_nominal():
    action = _make_social_action("twitter", "post", {"text": "Système d'arbitrage déterministe en ligne 🚀"})
    res = await twitter_post_handler(action)
    assert res.success is True
    assert "tweeted" in res.output


@pytest.mark.asyncio
async def test_linkedin_post_nominal():
    action = _make_social_action("linkedin", "post", {"text": "Retour d'expérience sur l'architecture multi-agents."})
    res = await linkedin_post_handler(action)
    assert res.success is True
    assert "LinkedIn" in res.output


@pytest.mark.asyncio
async def test_discord_send_nominal():
    action = _make_social_action("discord", "send", {
        "channel_id": "123456789",
        "content": "Déploiement réussi sur Netlify !",
    })
    res = await discord_send_handler(action)
    assert res.success is True
    assert "Discord" in res.output
