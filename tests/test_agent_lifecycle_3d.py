import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from app.main import app
from app.core.database import get_async_db
from app.core.security import create_access_token
from app.identity.models import Agent, User, Workspace, WorkspaceType, UserRole, workspace_memberships
from app.goal_engine.models import Goal, GoalStatus
from app.task_engine.models import Task, TaskStatus


@pytest_asyncio.fixture
async def setup_tenants(db_session: AsyncSession):
    ws_a = Workspace(name="Tenant 3D Alpha", slug=f"t3d-{uuid.uuid4().hex[:8]}", type=WorkspaceType.client)
    db_session.add(ws_a)
    await db_session.flush()

    user_a = User(email=f"operator-{uuid.uuid4().hex[:6]}@rockib.ai", password_hash="dummy")
    db_session.add(user_a)
    await db_session.flush()

    await db_session.execute(
        insert(workspace_memberships).values(
            workspace_id=ws_a.id,
            user_id=user_a.id,
            role=UserRole.admin,
        )
    )

    root_agent = Agent(
        workspace_id=ws_a.id,
        name="Orchestrateur Suprême Rockib",
        role="Lead Autonomous Architect",
        default_autonomy_level=3,
    )
    db_session.add(root_agent)
    await db_session.flush()

    return {
        "workspace": ws_a,
        "user": user_a,
        "root_agent": root_agent,
    }


@pytest_asyncio.fixture
async def client_auth(db_session: AsyncSession, setup_tenants):
    async def _db():
        yield db_session

    db_session.commit = db_session.flush

    token = create_access_token({"sub": str(setup_tenants["user"].id)})
    app.dependency_overrides[get_async_db] = _db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_agent_lifecycle_3d_materialization_and_dematerialization(
    client_auth,
    setup_tenants,
    db_session: AsyncSession,
):
    """Vérifie le cycle de vie 3D des agents :

    1. L'orchestrateur racine reste permanent (is_ephemeral=False, is_finished=False).
    2. Un sous-agent créé pour une tâche apparaît actif (is_ephemeral=True, is_finished=False).
    3. Lorsque toutes ses tâches sont terminées, il passe à is_finished=True.
    4. Avec active_only=true, le sous-agent terminé disparaît de la flotte du Cockpit 3D.
    5. Avec active_only=false, tous les agents sont renvoyés pour l'audit et l'historique.
    """
    ws = setup_tenants["workspace"]
    root_agent = setup_tenants["root_agent"]

    # 1. Création d'un sous-agent spécialisé (ex: Code Synthesizer) lié au parent
    sub_agent = Agent(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        name="Sub-Agent Code Synthesizer",
        role="Frontend Specialist",
        is_active=True,
        default_autonomy_level=2,
    )
    db_session.add(sub_agent)
    await db_session.flush()

    # 2. Création de son objectif et de ses tâches en cours
    sub_goal = Goal(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        agent_id=sub_agent.id,
        objective="Génération et rendu du site responsive",
        status=GoalStatus.ACTIVE,
        priority=1,
        requested_autonomy_level=2,
        applied_autonomy_level=2,
        goal_metadata={"spawned_by": str(root_agent.id)},
    )
    db_session.add(sub_goal)
    await db_session.flush()

    task1 = Task(
        id=uuid.uuid4(),
        goal_id=sub_goal.id,
        description="Génération du code HTML5 et styles CSS",
        status=TaskStatus.RUNNING,
    )
    task2 = Task(
        id=uuid.uuid4(),
        goal_id=sub_goal.id,
        description="Vérification et packaging (system.read)",
        status=TaskStatus.PENDING,
    )
    db_session.add_all([task1, task2])
    await db_session.flush()

    # 3. Vérification : en cours de travail, le sous-agent apparaît dans le cockpit
    resp_active = await client_auth.get(f"/api/v1/agents?workspace_id={ws.id}&active_only=true")
    assert resp_active.status_code == 200
    active_data = resp_active.json()
    active_ids = {a["id"] for a in active_data}

    assert str(root_agent.id) in active_ids
    assert str(sub_agent.id) in active_ids

    sub_agent_active_info = next(a for a in active_data if a["id"] == str(sub_agent.id))
    assert sub_agent_active_info["is_ephemeral"] is True
    assert sub_agent_active_info["is_finished"] is False
    assert sub_agent_active_info["current_status"] == "RUNNING"
    assert sub_agent_active_info["parent_agent_id"] == str(root_agent.id)

    # 4. Achèvement de tout le travail du sous-agent (les 2 tâches passent à COMPLETED)
    task1.status = TaskStatus.COMPLETED
    task2.status = TaskStatus.COMPLETED
    sub_goal.status = GoalStatus.COMPLETED
    await db_session.flush()

    # 5. Vérification Cockpit (active_only=true) : le sous-agent a disparu du cockpit !
    resp_demat = await client_auth.get(f"/api/v1/agents?workspace_id={ws.id}&active_only=true")
    assert resp_demat.status_code == 200
    demat_data = resp_demat.json()
    demat_ids = {a["id"] for a in demat_data}

    # L'orchestrateur racine est toujours présent
    assert str(root_agent.id) in demat_ids
    # Le sous-agent terminé s'est dématérialisé (disparu du cockpit)
    assert str(sub_agent.id) not in demat_ids

    # 6. Vérification complète (active_only=false) : toujours disponible pour l'audit
    resp_all = await client_auth.get(f"/api/v1/agents?workspace_id={ws.id}&active_only=false")
    assert resp_all.status_code == 200
    all_data = resp_all.json()
    all_ids = {a["id"] for a in all_data}

    assert str(root_agent.id) in all_ids
    assert str(sub_agent.id) in all_ids

    sub_agent_finished_info = next(a for a in all_data if a["id"] == str(sub_agent.id))
    assert sub_agent_finished_info["is_ephemeral"] is True
    assert sub_agent_finished_info["is_finished"] is True
    assert sub_agent_finished_info["current_status"] == "COMPLETED"
