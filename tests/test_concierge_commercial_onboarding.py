"""STEP 4 — Commercial Onboarding, Lead Lifecycle Management & Tunnel Diagnostics."""
from __future__ import annotations

import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.inbound.services.site_config_service import site_config_service


@pytest.mark.asyncio
async def test_tunnel_status_endpoint():
    """Verify GET /api/v1/inbound/tunnel/status diagnostics for cloud/local tunnels."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/inbound/tunnel/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "operational"
        assert data["tunnel_reachable"] is True
        assert data["active_sites_count"] >= 1
        assert "backend_time" in data


@pytest.mark.asyncio
async def test_commercial_onboarding_and_lead_lifecycle():
    """End-to-end verification of onboarding a new tenant, capturing leads, and updating status."""
    site_key = f"boutique-test-{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    ip_octet = uuid.uuid4().int % 200 + 10

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Forwarded-For": f"198.51.100.{ip_octet}"},
    ) as client:
        # 1. Onboard new client site
        onboard_payload = {
            "business_name": "Boutique Mode Cotonou",
            "subtitle": "Prêt-à-porter & Accessoires",
            "launcher_label": "🛍️ Conseiller Mode IA",
            "primary_color": "#A855F7",
            "default_voice": "vivienne",
            "assistant_role": "Tu es la conseillère style et vente de la boutique.",
            "welcome_message": "Bienvenue chez Boutique Mode ! Comment puis-je vous aider ?",
            "voice_greeting": "Bonjour ! Je suis votre conseillère style.",
            "quick_chips": ["Robes de soirée", "Horaires"],
            "knowledge_base": "CATALOGUE : Robes de soirée 25.000 FCFA, Costumes 45.000 FCFA. Livraison 24h.",
            "pricing_rule": "Orientez vers WhatsApp pour finaliser la commande.",
            "contact_whatsapp": "+229 01 97 11 22 33",
            "contact_email": "contact@boutiquemode.bj",
        }
        resp = await client.put(f"/api/v1/inbound/sites/{site_key}/config", json=onboard_payload)
        assert resp.status_code == 200
        saved = resp.json()
        token = saved["client_token"]
        assert token is not None
        assert "data-site-key" in saved["embed_script"]

        # 2. Visitor records a callback request for this site
        callback_payload = {
            "site_key": site_key,
            "phone_number": "+229 97 99 88 77",
            "contact_name": "Mme Mensah",
            "topic": "Commande urgente 3 robes de soirée",
            "channel": "whatsapp",
            "preferred_time": "immediate",
            "consent": True,
        }
        cb_resp = await client.post("/api/v1/inbound/portfolio/voice/request-callback", json=callback_payload)
        assert cb_resp.status_code == 200
        cb_data = cb_resp.json()
        lead_id = cb_data["callback_id"]
        assert cb_data["status"] == "scheduled"

        # 3. List leads without token -> 403 Forbidden
        denied_resp = await client.get(f"/api/v1/inbound/sites/{site_key}/leads")
        assert denied_resp.status_code == 403

        # 4. List leads with valid token -> 200 OK
        list_resp = await client.get(
            f"/api/v1/inbound/sites/{site_key}/leads",
            headers={"X-Concierge-Token": token},
        )
        assert list_resp.status_code == 200
        leads = list_resp.json()
        assert len(leads) >= 1
        lead = next(l for l in leads if l["id"] == lead_id)
        assert lead["contact_name"] == "Mme Mensah"
        assert lead["phone_number"] == "+229 97 99 88 77"
        assert lead["status"] == "received"

        # 5. Update lead status to 'contacted'
        patch_resp = await client.patch(
            f"/api/v1/inbound/sites/{site_key}/leads/{lead_id}/status",
            json={"status": "contacted"},
            headers={"X-Concierge-Token": token},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "contacted"

        # 6. Update lead status to 'converted'
        conv_resp = await client.patch(
            f"/api/v1/inbound/sites/{site_key}/leads/{lead_id}/status",
            json={"status": "converted"},
            headers={"X-Concierge-Token": token},
        )
        assert conv_resp.status_code == 200
        assert conv_resp.json()["status"] == "converted"

        # 7. Attempt invalid status -> 422 Unprocessable Entity
        bad_status_resp = await client.patch(
            f"/api/v1/inbound/sites/{site_key}/leads/{lead_id}/status",
            json={"status": "invalid_status_xyz"},
            headers={"X-Concierge-Token": token},
        )
        assert bad_status_resp.status_code == 422

        # 8. Export leads as CSV
        csv_resp = await client.get(
            f"/api/v1/inbound/sites/{site_key}/leads/export",
            headers={"X-Concierge-Token": token},
        )
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers["content-type"]
        csv_text = csv_resp.text
        assert "phone_number" in csv_text
        assert "+229 97 99 88 77" in csv_text
        assert "Mme Mensah" in csv_text
        assert "converted" in csv_text

        # 9. Tenant isolation : Another tenant token cannot access or patch this lead
        other_site_key = f"other-tenant-{uuid.uuid4().hex[:8]}"
        other_onboard = dict(onboard_payload, business_name="Autre Clinique")
        other_resp = await client.put(f"/api/v1/inbound/sites/{other_site_key}/config", json=other_onboard)
        other_token = other_resp.json()["client_token"]

        # Other tenant tries to patch Boutique's lead under their own site key -> 404
        hijack_resp = await client.patch(
            f"/api/v1/inbound/sites/{other_site_key}/leads/{lead_id}/status",
            json={"status": "archived"},
            headers={"X-Concierge-Token": other_token},
        )
        assert hijack_resp.status_code == 404

        # Other tenant tries to patch Boutique's lead using their own token on Boutique's endpoint -> 403
        wrong_token_resp = await client.patch(
            f"/api/v1/inbound/sites/{site_key}/leads/{lead_id}/status",
            json={"status": "archived"},
            headers={"X-Concierge-Token": other_token},
        )
        assert wrong_token_resp.status_code == 403
