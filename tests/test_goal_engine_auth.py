"""STEP 6H — Authentification & isolation tenant du Goal Engine.

Ces tests utilisent PostgreSQL réel (fixture db_session) pour prouver
l'isolation par workspace, pas seulement le câblage des dépendances.
`commit()` est neutralisé en `flush()` pour que le rollback final nettoie tout.
"""
from __future__ import annotations

import time
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_db
from app.core.security import create_access_token
from app.goal_engine.models import Goal, GoalStatus
from app.identity.models import Agent, User, UserRole, Workspace, workspace_memberships
from app.main import app
from tests.conftest import make_decision


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def tenants(db_session: AsyncSession):
    """Deux workspaces A/B, un agent et un goal chacun, un utilisateur membre de A seulement."""
    ws_a = Workspace(name="Tenant A", slug=f"ta-{uuid.uuid4().hex[:10]}")
    ws_b = Workspace(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:10]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    agent_a = Agent(workspace_id=ws_a.id, name="Agent A", default_autonomy_level=3)
    agent_b = Agent(workspace_id=ws_b.id, name="Agent B", default_autonomy_level=3)
    db_session.add_all([agent_a, agent_b])
    await db_session.flush()

    goal_a = Goal(
        workspace_id=ws_a.id, agent_id=agent_a.id, objective="Goal A",
        status=GoalStatus.ACTIVE, priority=1, requested_autonomy_level=2, applied_autonomy_level=2,
    )
    goal_b = Goal(
        workspace_id=ws_b.id, agent_id=agent_b.id, objective="Goal B secret",
        status=GoalStatus.ACTIVE, priority=1, requested_autonomy_level=2, applied_autonomy_level=2,
    )
    db_session.add_all([goal_a, goal_b])

    dec_b = make_decision(workspace_id=ws_b.id, agent_id=agent_b.id)
    dec_b.proposed_action = "TENANT_B_SECRET_ACTION"
    db_session.add(dec_b)

    user_a = User(email=f"a-{uuid.uuid4().hex[:8]}@test.io", password_hash="x", is_active=True)
    db_session.add(user_a)
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id, user_id=user_a.id, role=UserRole.admin
        )
    )
    await db_session.flush()

    return {
        "ws_a": ws_a, "ws_b": ws_b,
        "agent_a": agent_a, "agent_b": agent_b,
        "goal_a": goal_a, "goal_b": goal_b,
        "user_a": user_a,
    }


@pytest_asyncio.fixture
async def client_as_user_a(db_session: AsyncSession, tenants):
    """Client HTTP authentifié par un VRAI JWT de user_a (chaîne d'auth complète)."""
    async def _db():
        yield db_session

    # Neutraliser les commits pour que tout soit annulé en fin de test.
    db_session.commit = db_session.flush  # type: ignore[method-assign]

    token = create_access_token({"sub": str(tenants["user_a"].id)})
    app.dependency_overrides[get_async_db] = _db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client():
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# --------------------------------------------------------------------------- #
# 1. Sans token : 401 partout
# --------------------------------------------------------------------------- #

_RANDOM = str(uuid.uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/agents"),
        ("GET", f"/api/v1/agents/{_RANDOM}/logs"),
        ("GET", "/api/v1/goals"),
        ("GET", f"/api/v1/goals/{_RANDOM}"),
        ("POST", "/api/v1/goals"),
        ("POST", f"/api/v1/goals/{_RANDOM}/wake"),
        ("GET", "/api/v1/telemetry"),
        ("GET", f"/api/v1/workspaces/{_RANDOM}/preview/index.html"),
    ],
)
async def test_endpoints_require_authentication(anon_client, method, path):
    body = {
        "workspace_id": _RANDOM, "agent_id": _RANDOM, "objective": "x",
    } if method == "POST" and path.endswith("/goals") else None
    resp = await anon_client.request(method, path, json=body)
    assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"


# --------------------------------------------------------------------------- #
# 2. Isolation des lectures
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_goals_only_returns_member_workspaces(client_as_user_a, tenants):
    resp = await client_as_user_a.get("/api/v1/goals")
    assert resp.status_code == 200
    ids = {g["id"] for g in resp.json()}
    assert str(tenants["goal_a"].id) in ids
    assert str(tenants["goal_b"].id) not in ids


@pytest.mark.asyncio
async def test_list_goals_foreign_workspace_filter_forbidden(client_as_user_a, tenants):
    resp = await client_as_user_a.get("/api/v1/goals", params={"workspace_id": str(tenants["ws_b"].id)})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_agents_only_returns_member_workspaces(client_as_user_a, tenants):
    resp = await client_as_user_a.get("/api/v1/agents")
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()}
    assert str(tenants["agent_a"].id) in ids
    assert str(tenants["agent_b"].id) not in ids


@pytest.mark.asyncio
async def test_goal_details_foreign_returns_404(client_as_user_a, tenants):
    resp = await client_as_user_a.get(f"/api/v1/goals/{tenants['goal_b'].id}")
    assert resp.status_code == 404
    ok = await client_as_user_a.get(f"/api/v1/goals/{tenants['goal_a'].id}")
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_agent_logs_foreign_returns_404(client_as_user_a, tenants):
    resp = await client_as_user_a.get(f"/api/v1/agents/{tenants['agent_b'].id}/logs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_telemetry_does_not_leak_foreign_decisions(client_as_user_a, tenants):
    resp = await client_as_user_a.get("/api/v1/telemetry", params={"limit": 100})
    assert resp.status_code == 200
    assert "TENANT_B_SECRET_ACTION" not in resp.text


# --------------------------------------------------------------------------- #
# 3. Écritures
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_goal_in_foreign_workspace_forbidden(client_as_user_a, tenants):
    resp = await client_as_user_a.post("/api/v1/goals", json={
        "workspace_id": str(tenants["ws_b"].id),
        "agent_id": str(tenants["agent_b"].id),
        "objective": "intrusion",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_goal_with_foreign_agent_rejected(client_as_user_a, tenants):
    resp = await client_as_user_a.post("/api/v1/goals", json={
        "workspace_id": str(tenants["ws_a"].id),
        "agent_id": str(tenants["agent_b"].id),
        "objective": "agent volé",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_goal_with_foreign_parent_goal_rejected(client_as_user_a, tenants):
    resp = await client_as_user_a.post("/api/v1/goals", json={
        "workspace_id": str(tenants["ws_a"].id),
        "agent_id": str(tenants["agent_a"].id),
        "objective": "parent étranger",
        "parent_goal_id": str(tenants["goal_b"].id),
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_goal_in_own_workspace_succeeds(client_as_user_a, tenants):
    resp = await client_as_user_a.post("/api/v1/goals", json={
        "workspace_id": str(tenants["ws_a"].id),
        "agent_id": str(tenants["agent_a"].id),
        "objective": "mission légitime",
        "parent_goal_id": str(tenants["goal_a"].id),
        "requested_autonomy_level": 5,
    })
    assert resp.status_code == 200, resp.text
    # Plafond hiérarchique (STEP 6G) toujours appliqué : parent = 2
    assert resp.json()["applied_autonomy_level"] == 2


@pytest.mark.asyncio
async def test_wake_foreign_goal_returns_404(client_as_user_a, tenants):
    resp = await client_as_user_a.post(f"/api/v1/goals/{tenants['goal_b'].id}/wake")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# 4. Preview : URL signée HMAC
# --------------------------------------------------------------------------- #


@pytest.fixture
def preview_file(tmp_path, monkeypatch, tenants):
    monkeypatch.setattr(settings, "WORKSPACES_ROOT", str(tmp_path))
    ws_dir = tmp_path / str(tenants["ws_a"].id)
    ws_dir.mkdir()
    (ws_dir / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return tenants["ws_a"].id


@pytest.mark.asyncio
async def test_preview_valid_signature_ok(anon_client, preview_file):
    from app.core.signed_urls import sign_preview

    exp, sig = sign_preview(preview_file, "index.html")
    resp = await anon_client.get(
        f"/api/v1/workspaces/{preview_file}/preview/index.html", params={"exp": exp, "sig": sig}
    )
    assert resp.status_code == 200
    assert "ok" in resp.text


@pytest.mark.asyncio
async def test_preview_expired_signature_forbidden(anon_client, preview_file):
    from app.core.signed_urls import sign_preview

    exp, sig = sign_preview(preview_file, "index.html", ttl=-10)
    resp = await anon_client.get(
        f"/api/v1/workspaces/{preview_file}/preview/index.html", params={"exp": exp, "sig": sig}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_tampered_signature_forbidden(anon_client, preview_file):
    from app.core.signed_urls import sign_preview

    exp, sig = sign_preview(preview_file, "index.html")
    bad = ("0" if sig[0] != "0" else "1") + sig[1:]
    resp = await anon_client.get(
        f"/api/v1/workspaces/{preview_file}/preview/index.html", params={"exp": exp, "sig": bad}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_signature_not_transferable_to_other_workspace(anon_client, preview_file):
    from app.core.signed_urls import sign_preview

    exp, sig = sign_preview(preview_file, "index.html")
    other = uuid.uuid4()
    resp = await anon_client.get(
        f"/api/v1/workspaces/{other}/preview/index.html", params={"exp": exp, "sig": sig}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_signature_not_transferable_to_other_path(anon_client, preview_file):
    from app.core.signed_urls import sign_preview

    exp, sig = sign_preview(preview_file, "index.html")
    resp = await anon_client.get(
        f"/api/v1/workspaces/{preview_file}/preview/other.html", params={"exp": exp, "sig": sig}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_preview_path_traversal_blocked_even_with_signature(anon_client, preview_file):
    from app.core.signed_urls import sign_preview

    path = "../secret.txt"
    exp, sig = sign_preview(preview_file, path)
    resp = await anon_client.get(
        f"/api/v1/workspaces/{preview_file}/preview/%2E%2E/secret.txt", params={"exp": exp, "sig": sig}
    )
    assert resp.status_code in (403, 404)
    assert "top secret" not in resp.text


@pytest.mark.asyncio
async def test_preview_member_bearer_ok_without_signature(client_as_user_a, preview_file):
    resp = await client_as_user_a.get(f"/api/v1/workspaces/{preview_file}/preview/index.html")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_goal_details_signs_preview_links(client_as_user_a, tenants):
    """Les liens /preview/ renvoyés au cockpit doivent porter exp & sig."""
    from app.core.signed_urls import sign_preview_links

    ws = tenants["ws_a"].id
    raw = f"Fichier créé : /api/v1/workspaces/{ws}/preview/site/index.html (ok)"
    signed = sign_preview_links(raw)
    assert f"/api/v1/workspaces/{ws}/preview/site/index.html?exp=" in signed
    assert "&sig=" in signed
    assert signed.endswith(" (ok)")
