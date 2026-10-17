"""Unit and integration tests for Rockib AI Skill System (Registry, Hasher, Selector).

Verifies invariants:
- SKILL-INV-01: Declarative non-permissive knowledge.
- SKILL-INV-02: Monotonic parent-to-child delegation.
- SKILL-INV-04 / SKILL-INV-08: Cryptographic immutability and content_hash seal.
- SKILL-INV-09: Bounded dependency closure and cycle detection.
"""
from __future__ import annotations

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.decision_engine.models import (
    ArbitrationRule,
    DecisionDomainConfig,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.identity.models import Agent, Workspace
from app.skills.models import Skill, SkillVersion
from app.skills.schemas import (
    SkillCategory,
    SkillManifest,
    SkillManifestDependencies,
    SkillManifestGovernanceHints,
    SkillManifestIdentity,
    SkillManifestKnowledge,
    SkillManifestMetadata,
    SkillManifestVersioning,
    compute_canonical_content_hash,
    verify_skill_manifest_hash,
)
from app.skills.services.registry import (
    MissingTransitiveSkillDependencyError,
    SkillDependencyCycleError,
    SkillHashTamperingError,
    SkillRegistry,
    SkillVersionImmutableViolationError,
)
from app.skills.services.selector import SkillConflictError, SkillDelegationError, SkillSelector


def _create_dummy_manifest(
    skill_id: str,
    version: str,
    instructions: str,
    required_tools: list[str] | None = None,
    required_skills: list[str] | None = None,
    constraints: list[str] | None = None,
    is_system: bool = True,
    conflicts_with: list[str] | None = None,
) -> SkillManifest:
    knowledge = SkillManifestKnowledge(
        instructions=instructions,
        constraints=constraints or ["Do not delete system files"],
    )
    deps = SkillManifestDependencies(
        required_tools=required_tools or ["fs.read"],
        required_skills=required_skills or [],
    )
    content_hash = compute_canonical_content_hash(knowledge, deps)

    return SkillManifest(
        manifest_version="1.0",
        identity=SkillManifestIdentity(id=skill_id, is_system=is_system),
        versioning=SkillManifestVersioning(version=version, content_hash=content_hash),
        metadata=SkillManifestMetadata(
            name=f"Test Skill {skill_id}",
            description="A test skill for unit testing",
            category="engineering",
        ),
        knowledge=knowledge,
        dependencies=deps,
        governance_hints=SkillManifestGovernanceHints(
            suggested_risk="low",
            conflicts_with=conflicts_with or [],
        ),
    )


def test_canonical_content_hash_invariance():
    """Different tool order or CRLF line endings produce the exact same content_hash."""
    k1 = SkillManifestKnowledge(instructions="Line 1\r\nLine 2\r\n", constraints=["  C1  ", "C2"])
    d1 = SkillManifestDependencies(required_tools=["web.search", "fs.read"], required_skills=["git"])

    k2 = SkillManifestKnowledge(instructions="Line 1\nLine 2\n", constraints=["C1", "C2"])
    d2 = SkillManifestDependencies(required_tools=["fs.read", "web.search"], required_skills=["git"])

    hash1 = compute_canonical_content_hash(k1, d1)
    hash2 = compute_canonical_content_hash(k2, d2)

    assert hash1 == hash2
    assert hash1.startswith("sha256:")

    # Any single character change alters the hash
    k3 = SkillManifestKnowledge(instructions="Line 1\nLine 2.\n", constraints=["C1", "C2"])
    hash3 = compute_canonical_content_hash(k3, d2)
    assert hash3 != hash1


@pytest.mark.asyncio
async def test_register_manifest_success_and_idempotency(db_session: AsyncSession):
    manifest = _create_dummy_manifest(
        skill_id="python_testing",
        version="1.0.0",
        instructions="Always write pytest fixtures and mock external calls.",
        required_tools=["fs.read", "fs.write"],
    )

    # First registration
    v1 = await SkillRegistry.register_manifest(db_session, manifest)
    assert v1.semver == "1.0.0"
    assert v1.content_hash == manifest.versioning.content_hash

    # Idempotent re-registration
    v2 = await SkillRegistry.register_manifest(db_session, manifest)
    assert v2.id == v1.id


@pytest.mark.asyncio
async def test_register_manifest_tampering_rejection(db_session: AsyncSession):
    manifest = _create_dummy_manifest(
        skill_id="tampered_skill",
        version="1.0.0",
        instructions="Normal instructions here.",
    )
    # Manually alter the instructions without recomputing the hash
    manifest.knowledge.instructions = "MALICIOUS INJECTED INSTRUCTION"

    with pytest.raises(SkillHashTamperingError):
        await SkillRegistry.register_manifest(db_session, manifest)


@pytest.mark.asyncio
async def test_register_manifest_immutable_version_violation(db_session: AsyncSession):
    manifest1 = _create_dummy_manifest(
        skill_id="immutable_skill",
        version="1.0.0",
        instructions="Original instructions version 1.0.0.",
    )
    await SkillRegistry.register_manifest(db_session, manifest1)

    # Submit same version 1.0.0 with different instructions (new hash)
    manifest2 = _create_dummy_manifest(
        skill_id="immutable_skill",
        version="1.0.0",
        instructions="Modified instructions trying to reuse version 1.0.0.",
    )
    with pytest.raises(SkillVersionImmutableViolationError):
        await SkillRegistry.register_manifest(db_session, manifest2)


@pytest.mark.asyncio
async def test_dependency_cycle_detection(db_session: AsyncSession):
    # Skill A requires B, Skill B requires A
    m_a = _create_dummy_manifest("cycle_a", "1.0.0", "Instructions A", required_skills=["cycle_b"])
    m_b = _create_dummy_manifest("cycle_b", "1.0.0", "Instructions B", required_skills=["cycle_a"])

    ver_a = await SkillRegistry.register_manifest(db_session, m_a)
    await SkillRegistry.register_manifest(db_session, m_b)

    with pytest.raises(SkillDependencyCycleError):
        await SkillRegistry.resolve_transitive_dependencies(db_session, ver_a)


@pytest.mark.asyncio
async def test_self_dependency(db_session: AsyncSession):
    """Vérifie qu'une auto-dépendance (A -> A) est immédiatement rejetée comme cycle."""
    m_self = _create_dummy_manifest("cycle_self", "1.0.0", "Self instructions", required_skills=["cycle_self"])
    ver_self = await SkillRegistry.register_manifest(db_session, m_self)

    with pytest.raises(SkillDependencyCycleError):
        await SkillRegistry.resolve_transitive_dependencies(db_session, ver_self)


@pytest.mark.asyncio
async def test_missing_direct_dependency(db_session: AsyncSession):
    """Vérifie qu'une dépendance directe manquante dans le registry lève MissingTransitiveSkillDependencyError."""
    m_orphan = _create_dummy_manifest("orphan_skill", "1.0.0", "Orphan instructions", required_skills=["non_existent_skill"])
    ver_orphan = await SkillRegistry.register_manifest(db_session, m_orphan)

    with pytest.raises(MissingTransitiveSkillDependencyError):
        await SkillRegistry.resolve_transitive_dependencies(db_session, ver_orphan)


@pytest.mark.asyncio
async def test_missing_transitive_dependency(db_session: AsyncSession):
    """Vérifie que A -> B -> C avec C absent des assignations de l'agent bloque la sélection JIT."""
    ws = Workspace(name="Transitive WS", slug=f"ws-trans-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Test Agent", role="Worker", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    # Créer la chaîne A -> B -> C dans le registry
    m_c = _create_dummy_manifest("trans_c", "1.0.0", "Instructions C")
    m_b = _create_dummy_manifest("trans_b", "1.0.0", "Instructions B", required_skills=["trans_c"])
    m_a = _create_dummy_manifest("trans_a", "1.0.0", "Instructions A", required_skills=["trans_b"])

    ver_c = await SkillRegistry.register_manifest(db_session, m_c)
    ver_b = await SkillRegistry.register_manifest(db_session, m_b)
    ver_a = await SkillRegistry.register_manifest(db_session, m_a)

    # Assigner A et B à l'agent, mais PAS C
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_a)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_b)

    # La sélection de trans_a doit lever MissingTransitiveSkillDependencyError car trans_c manque
    with pytest.raises(MissingTransitiveSkillDependencyError):
        await SkillSelector.select_skills_for_task(
            db_session,
            agent_id=agent.id,
            workspace_id=ws.id,
            task_skill_hint="trans_a",
        )


@pytest.mark.asyncio
async def test_valid_transitive_dependency(db_session: AsyncSession):
    """Vérifie que la chaîne A -> B -> C complète et assignée est résolue avec succès."""
    ws = Workspace(name="Valid Transitive WS", slug=f"ws-vtrans-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Full Agent", role="Worker", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    m_c = _create_dummy_manifest("vtrans_c", "1.0.0", "Valid Instructions C")
    m_b = _create_dummy_manifest("vtrans_b", "1.0.0", "Valid Instructions B", required_skills=["vtrans_c"])
    m_a = _create_dummy_manifest("vtrans_a", "1.0.0", "Valid Instructions A", required_skills=["vtrans_b"])

    ver_c = await SkillRegistry.register_manifest(db_session, m_c)
    ver_b = await SkillRegistry.register_manifest(db_session, m_b)
    ver_a = await SkillRegistry.register_manifest(db_session, m_a)

    # Assigner toute la chaîne A, B, C
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_a)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_b)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_c)

    # Vérification Registry
    deps = await SkillRegistry.resolve_transitive_dependencies(db_session, ver_a)
    assert len(deps) == 2
    assert {d.skill.slug for d in deps} == {"vtrans_b", "vtrans_c"}

    # Vérification Selector JIT
    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent.id,
        workspace_id=ws.id,
        task_skill_hint="vtrans_a",
    )
    assert len(selected) >= 1
    assert selected[0].id == "vtrans_a"


@pytest.mark.asyncio
async def test_conflicting_skills_rejected(db_session: AsyncSession):
    """Vérifie que deux skills mutuellement exclusifs ne sont jamais injectés conjointement."""
    ws = Workspace(name="Conflict WS", slug=f"ws-conf-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Conflict Agent", role="Worker", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    # Skill A déclare conflit avec B
    m_a = _create_dummy_manifest("conflict_a", "1.0.0", "Use Framework A for API", conflicts_with=["conflict_b"])
    m_b = _create_dummy_manifest("conflict_b", "1.0.0", "Use Framework B for API", conflicts_with=["conflict_a"])

    ver_a = await SkillRegistry.register_manifest(db_session, m_a)
    ver_b = await SkillRegistry.register_manifest(db_session, m_b)

    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_a)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_b)

    # Vérification fonctionnelle are_skills_conflicting et verify_no_conflicts
    assert SkillSelector.are_skills_conflicting(ver_a, ver_b) is True
    assert SkillSelector.are_skills_conflicting(ver_b, ver_a) is True
    with pytest.raises(SkillConflictError):
        SkillSelector.verify_no_conflicts([ver_a, ver_b])

    # Sélection JIT avec tâche ciblant les deux frameworks : un seul doit être retenu, le second rejeté
    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent.id,
        workspace_id=ws.id,
        task_description="Build API using Framework A and Framework B",
        max_skills=2,
    )
    selected_ids = [s.id for s in selected]
    # Les deux ne doivent JAMAIS être présents conjointement
    assert not ("conflict_a" in selected_ids and "conflict_b" in selected_ids)
    assert len(selected) == 1


@pytest.mark.asyncio
async def test_non_conflicting_skills_allowed(db_session: AsyncSession):
    """Vérifie que des skills non-conflictuels sont tous deux injectés avec succès."""
    ws = Workspace(name="Non Conflict WS", slug=f"ws-nconf-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Non Conflict Agent", role="Worker", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    m_a = _create_dummy_manifest("compat_a", "1.0.0", "Build database layer postgres")
    m_b = _create_dummy_manifest("compat_b", "1.0.0", "Build caching layer redis")

    ver_a = await SkillRegistry.register_manifest(db_session, m_a)
    ver_b = await SkillRegistry.register_manifest(db_session, m_b)

    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_a)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_b)

    assert SkillSelector.are_skills_conflicting(ver_a, ver_b) is False
    SkillSelector.verify_no_conflicts([ver_a, ver_b])

    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent.id,
        workspace_id=ws.id,
        task_description="Build database postgres and caching redis",
        max_skills=2,
    )
    selected_ids = [s.id for s in selected]
    assert "compat_a" in selected_ids
    assert "compat_b" in selected_ids
    assert len(selected) == 2


@pytest.mark.asyncio
async def test_conflict_is_deterministic(db_session: AsyncSession):
    """Vérifie que le départage d'un conflit est strictement déterministe sur N exécutions."""
    ws = Workspace(name="Deterministic Conflict WS", slug=f"ws-detconf-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Det Agent", role="Worker", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    m_x = _create_dummy_manifest("det_x", "1.0.0", "Identical score instructions for X", conflicts_with=["det_y"])
    m_y = _create_dummy_manifest("det_y", "1.0.0", "Identical score instructions for Y", conflicts_with=["det_x"])

    ver_x = await SkillRegistry.register_manifest(db_session, m_x)
    ver_y = await SkillRegistry.register_manifest(db_session, m_y)

    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_x)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_y)

    results = []
    for _ in range(10):
        sel = await SkillSelector.select_skills_for_task(
            db_session,
            agent_id=agent.id,
            workspace_id=ws.id,
            task_description="Execute task matching both det_x and det_y equally",
            max_skills=2,
        )
        assert len(sel) == 1
        results.append(sel[0].id)

    # 100% déterministe : exactement le même skill gagnant à chaque run
    assert len(set(results)) == 1
    assert results[0] == "det_x"


@pytest.mark.asyncio
async def test_conflict_does_not_grant_permissions(db_session: AsyncSession):
    """Vérifie que la résolution d'un conflit n'émet ni n'altère aucune autorisation système."""
    ws = Workspace(name="Perm Isolation WS", slug=f"ws-piso-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Auth Agent", role="Worker", default_autonomy_level=1)
    db_session.add(agent)
    await db_session.flush()

    m_conf = _create_dummy_manifest(
        "perm_conf_a",
        "1.0.0",
        "Sensitive operation instructions",
        required_tools=["system.delete", "fs.write"],
        conflicts_with=["perm_conf_b"],
    )
    ver_conf = await SkillRegistry.register_manifest(db_session, m_conf)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver_conf)

    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent.id,
        workspace_id=ws.id,
        task_skill_hint="perm_conf_a",
    )
    assert len(selected) == 1
    assert "system.delete" in selected[0].required_tools
    await db_session.refresh(agent)
    assert agent.default_autonomy_level == 1


@pytest.mark.asyncio
async def test_monotonic_delegation_and_selection(db_session: AsyncSession):
    ws = Workspace(name="Delegation WS", slug=f"ws-del-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    parent = Agent(workspace_id=ws.id, name="Parent Agent", role="Senior Dev", default_autonomy_level=3)
    child = Agent(workspace_id=ws.id, name="Child Agent", role="Junior Dev", default_autonomy_level=1)
    db_session.add_all([parent, child])
    await db_session.flush()

    m_allowed = _create_dummy_manifest("allowed_skill", "1.0.0", "Parent possesses this.")
    m_forbidden = _create_dummy_manifest("forbidden_skill", "1.0.0", "Parent does not have this.")

    ver_allowed = await SkillRegistry.register_manifest(db_session, m_allowed)
    ver_forbidden = await SkillRegistry.register_manifest(db_session, m_forbidden)

    # Assign allowed skill to parent
    await SkillSelector.assign_skill_to_agent(db_session, parent.id, ver_allowed)

    # Child receives allowed skill from parent -> Success
    await SkillSelector.assign_skill_to_agent(
        db_session, child.id, ver_allowed, granted_by_agent_id=parent.id
    )

    # Child attempts to receive forbidden skill from parent -> Rejection
    with pytest.raises(SkillDelegationError):
        await SkillSelector.assign_skill_to_agent(
            db_session, child.id, ver_forbidden, granted_by_agent_id=parent.id
        )

    # JIT Selection
    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=child.id,
        workspace_id=ws.id,
        task_skill_hint="allowed_skill",
        task_description="Execute allowed task",
    )
    assert len(selected) == 1
    assert selected[0].id == "allowed_skill"
    assert selected[0].content_hash == ver_allowed.content_hash


@pytest.mark.asyncio
async def test_seed_core_catalogue(db_session: AsyncSession):
    from app.skills.catalog import get_core_catalogue

    catalogue = get_core_catalogue()
    assert len(catalogue) == 5

    # Verify each manifest in catalogue is validly sealed
    for manifest in catalogue:
        assert verify_skill_manifest_hash(manifest) is True

    # Check slugs
    core_slugs = {m.identity.id for m in catalogue}
    expected_slugs = {
        "portfolio_ambassador",
        "lead_qualification",
        "frontend_react",
        "backend_django",
        "cybersecurity_defensive",
    }
    assert core_slugs == expected_slugs



# --- STEP 6D.3: Workspace Isolation Tests ---


@pytest.mark.asyncio
async def test_workspace_skill_isolation(db_session: AsyncSession):
    """A private skill in Workspace A is strictly inaccessible from Workspace B."""
    ws_a = Workspace(name="WS A", slug=f"ws-a-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS B", slug=f"ws-b-{uuid.uuid4().hex[:8]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    # Workspace A registers a private skill
    m_a = _create_dummy_manifest(
        skill_id="private_tool_a",
        version="1.0.0",
        instructions="Secret operations for Workspace A.",
        is_system=False,
    )
    ver_a = await SkillRegistry.register_manifest(db_session, m_a, workspace_id=ws_a.id)
    assert ver_a.skill.workspace_id == ws_a.id
    assert ver_a.skill.is_system is False

    # Workspace A can locate it
    found_a = await SkillRegistry.get_skill(db_session, "private_tool_a", workspace_id=ws_a.id)
    assert found_a is not None
    assert found_a.id == ver_a.skill_id

    # Workspace B CANNOT locate it
    found_b = await SkillRegistry.get_skill(db_session, "private_tool_a", workspace_id=ws_b.id)
    assert found_b is None

    # Global scope (None) CANNOT locate private skill
    found_global = await SkillRegistry.get_skill(db_session, "private_tool_a", workspace_id=None)
    assert found_global is None


@pytest.mark.asyncio
async def test_workspace_cannot_select_other_workspace_skill(db_session: AsyncSession):
    """An agent operating in Workspace B cannot select private skills of Workspace A."""
    ws_a = Workspace(name="WS A2", slug=f"ws-a2-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS B2", slug=f"ws-b2-{uuid.uuid4().hex[:8]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    agent_b = Agent(workspace_id=ws_b.id, name="Agent in B", role="Worker", default_autonomy_level=1)
    db_session.add(agent_b)
    await db_session.flush()

    m_a = _create_dummy_manifest(
        skill_id="private_tool_a2",
        version="1.0.0",
        instructions="Private skill for A only.",
        is_system=False,
    )
    ver_a = await SkillRegistry.register_manifest(db_session, m_a, workspace_id=ws_a.id)

    # Even if forcefully assigned to agent_b
    await SkillSelector.assign_skill_to_agent(db_session, agent_b.id, ver_a)

    # When running a task in Workspace B, SkillSelector must NOT select Workspace A's skill
    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent_b.id,
        workspace_id=ws_b.id,
        task_skill_hint="private_tool_a2",
    )
    assert len(selected) == 0


@pytest.mark.asyncio
async def test_system_skill_available_as_intended(db_session: AsyncSession):
    """A system skill (is_system=True) is accessible across all workspaces."""
    ws_a = Workspace(name="WS Sys A", slug=f"ws-sysa-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS Sys B", slug=f"ws-sysb-{uuid.uuid4().hex[:8]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    agent_a = Agent(workspace_id=ws_a.id, name="Agent Sys A", default_autonomy_level=2)
    agent_b = Agent(workspace_id=ws_b.id, name="Agent Sys B", default_autonomy_level=2)
    db_session.add_all([agent_a, agent_b])
    await db_session.flush()

    sys_m = _create_dummy_manifest(
        skill_id="global_system_helper",
        version="1.0.0",
        instructions="Global system capabilities.",
        is_system=True,
    )
    sys_ver = await SkillRegistry.register_manifest(db_session, sys_m)

    # Both workspaces can retrieve it
    skill_a = await SkillRegistry.get_skill(db_session, "global_system_helper", workspace_id=ws_a.id)
    skill_b = await SkillRegistry.get_skill(db_session, "global_system_helper", workspace_id=ws_b.id)
    assert skill_a is not None and skill_b is not None
    assert skill_a.id == skill_b.id

    # Assign to both agents
    await SkillSelector.assign_skill_to_agent(db_session, agent_a.id, sys_ver)
    await SkillSelector.assign_skill_to_agent(db_session, agent_b.id, sys_ver)

    # Both agents can select it in their respective workspace
    sel_a = await SkillSelector.select_skills_for_task(db_session, agent_a.id, ws_a.id, "global_system_helper")
    sel_b = await SkillSelector.select_skills_for_task(db_session, agent_b.id, ws_b.id, "global_system_helper")
    assert len(sel_a) == 1 and sel_a[0].id == "global_system_helper"
    assert len(sel_b) == 1 and sel_b[0].id == "global_system_helper"


@pytest.mark.asyncio
async def test_duplicate_workspace_skill_rejected(db_session: AsyncSession):
    """Verifies uniqueness constraint on (workspace_id, slug)."""
    ws_a = Workspace(name="WS Dup A", slug=f"ws-dupa-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS Dup B", slug=f"ws-dupb-{uuid.uuid4().hex[:8]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    # Different workspaces can have the same slug
    s_a = Skill(workspace_id=ws_a.id, slug="custom_analyzer", name="Analyzer A", is_system=False)
    s_b = Skill(workspace_id=ws_b.id, slug="custom_analyzer", name="Analyzer B", is_system=False)
    db_session.add_all([s_a, s_b])
    await db_session.flush()

    # Duplicate in the SAME workspace must be rejected by unique constraint
    dup_s_a = Skill(workspace_id=ws_a.id, slug="custom_analyzer", name="Duplicate Analyzer A", is_system=False)
    db_session.add(dup_s_a)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# --- STEP 6D.4: Permission Isolation Tests ---


@pytest.mark.asyncio
async def test_required_tools_does_not_grant_permission(db_session: AsyncSession):
    """Declared required_tools never grants authorization or bypasses Arbitrator constraints."""
    ws = Workspace(name="Perm Iso WS", slug=f"ws-permiso-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Low Perm Agent", role="Worker", default_autonomy_level=1)
    db_session.add(agent)
    await db_session.flush()

    # Skill declares dangerous tools
    m = _create_dummy_manifest(
        skill_id="danger_tools_skill",
        version="1.0.0",
        instructions="Handle system maintenance.",
        required_tools=["system.delete", "fs.write", "net.raw"],
        is_system=True,
    )
    ver = await SkillRegistry.register_manifest(db_session, m)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver)

    # Verify agent model was not augmented with permissions or elevated autonomy
    await db_session.refresh(agent)
    assert agent.default_autonomy_level == 1

    # Arbitrator check: even with the skill active, a DELETE action requires explicit approval
    arbitrator = DeterministicArbitrator()
    cfg = MagicMock(spec=DecisionDomainConfig)
    cfg.arbitration_rule = ArbitrationRule.cognitive_wins
    cfg.base_risk_level = RiskLevel.medium
    cfg.base_reversibility = ReversibilityLevel.reversible
    cfg.base_impact = ImpactType.internal
    cfg.disagreement_threshold = 0.40
    cfg.max_autonomy_level = 5
    cfg.id = uuid.uuid4()

    with patch.object(DeterministicArbitrator, "_load_domain_config", new_callable=AsyncMock, return_value=cfg):
        decision = await arbitrator.arbitrate(
            objective="Clean logs",
            situation="Disk full",
            proposed_action="system.delete /var/log/app.log",
            cognitive_opinion={"action": "system.delete /var/log/app.log", "confidence": 0.9},
            intelligence_opinion={"action": "system.delete /var/log/app.log", "confidence": 0.9},
            domain="system",
            permission_action=PermissionAction.DELETE,
            requested_autonomy_level=1,
            workspace_id=str(ws.id),
            agent_id=str(agent.id),
        )

    # PermissionAction.DELETE strictly forces approval_required = True
    assert decision.approval_required is True


@pytest.mark.asyncio
async def test_skill_does_not_alter_autonomy_level(db_session: AsyncSession):
    """Assigning or selecting a skill does not alter requested or applied autonomy."""
    ws = Workspace(name="Autonomy WS", slug=f"ws-auto-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Fixed Autonomy Agent", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    m = _create_dummy_manifest("autonomous_skill", "1.0.0", "Auto instructions.")
    ver = await SkillRegistry.register_manifest(db_session, m)
    await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver)

    await db_session.refresh(agent)
    assert agent.default_autonomy_level == 2

    # Arbitrator strictly caps applied autonomy by domain config
    arbitrator = DeterministicArbitrator()
    cfg = MagicMock(spec=DecisionDomainConfig)
    cfg.arbitration_rule = ArbitrationRule.cognitive_wins
    cfg.base_risk_level = RiskLevel.low
    cfg.base_reversibility = ReversibilityLevel.reversible
    cfg.base_impact = ImpactType.internal
    cfg.disagreement_threshold = 0.50
    cfg.max_autonomy_level = 1  # Capped at 1
    cfg.id = uuid.uuid4()

    with patch.object(DeterministicArbitrator, "_load_domain_config", new_callable=AsyncMock, return_value=cfg):
        decision = await arbitrator.arbitrate(
            objective="Do task",
            situation="Normal",
            proposed_action="run_task",
            cognitive_opinion={"action": "run_task", "confidence": 0.9},
            intelligence_opinion={"action": "run_task", "confidence": 0.9},
            domain="dev",
            permission_action=PermissionAction.UPDATE,
            requested_autonomy_level=4,  # Agent requests 4
            workspace_id=str(ws.id),
            agent_id=str(agent.id),
        )
    # applied_autonomy_level = min(4, 1) = 1
    assert decision.applied_autonomy_level == 1


@pytest.mark.asyncio
async def test_skill_does_not_bypass_arbitrator_deny(db_session: AsyncSession):
    """Skill metadata suggesting risk='low' cannot override Arbitrator escalation or high risk rules."""
    arbitrator = DeterministicArbitrator()
    cfg = MagicMock(spec=DecisionDomainConfig)
    cfg.arbitration_rule = ArbitrationRule.escalate
    cfg.base_risk_level = RiskLevel.high
    cfg.base_reversibility = ReversibilityLevel.irreversible
    cfg.base_impact = ImpactType.client_facing
    cfg.disagreement_threshold = 0.40
    cfg.max_autonomy_level = 3
    cfg.id = uuid.uuid4()

    with patch.object(DeterministicArbitrator, "_load_domain_config", new_callable=AsyncMock, return_value=cfg):
        decision = await arbitrator.arbitrate(
            objective="Deploy change",
            situation="Deploying to prod",
            proposed_action="deploy_service",
            cognitive_opinion={"action": "deploy_service", "confidence": 0.95},
            intelligence_opinion={"action": "deploy_service", "confidence": 0.95, "risk_level": "low"},
            domain="production",
            permission_action=PermissionAction.UPDATE,
            requested_autonomy_level=3,
            workspace_id="ws-bypass",
            agent_id="agent-bypass",
        )

    # Risk level cannot be downgraded below base_risk_level (RiskLevel.high)
    assert decision.risk_level in {RiskLevel.high, RiskLevel.critical}
    assert decision.approval_required is True


# --- STEP 6D.5: Seed Failure Visibility Tests ---


@pytest.mark.asyncio
async def test_seed_same_version_same_hash_is_idempotent(db_session: AsyncSession):
    """Re-registering identical version with identical hash succeeds and returns the same entry."""
    m = _create_dummy_manifest("seed_idempotent_skill", "1.0.0", "Seed instructions.")
    v1 = await SkillRegistry.register_manifest(db_session, m)
    v2 = await SkillRegistry.register_manifest(db_session, m)
    assert v1.id == v2.id
    assert v1.content_hash == v2.content_hash


@pytest.mark.asyncio
async def test_seed_same_version_different_hash_fails(db_session: AsyncSession):
    """Re-registering same version with altered instructions fails with SkillVersionImmutableViolationError."""
    m1 = _create_dummy_manifest("seed_tamper_skill", "1.0.0", "Original seed instructions.")
    await SkillRegistry.register_manifest(db_session, m1)

    m2 = _create_dummy_manifest("seed_tamper_skill", "1.0.0", "Altered seed instructions.")
    with pytest.raises(SkillVersionImmutableViolationError) as exc_info:
        await SkillRegistry.register_manifest(db_session, m2)
    assert "already sealed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_seed_version_bump_allowed(db_session: AsyncSession):
    """Registering an updated manifest with bumped SemVer succeeds."""
    m_v1 = _create_dummy_manifest("seed_bump_skill", "1.0.0", "Version 1 instructions.")
    v1 = await SkillRegistry.register_manifest(db_session, m_v1)

    m_v2 = _create_dummy_manifest("seed_bump_skill", "1.1.0", "Version 1.1 instructions with upgrades.")
    v2 = await SkillRegistry.register_manifest(db_session, m_v2)

    assert v1.skill_id == v2.skill_id
    assert v1.semver == "1.0.0"
    assert v2.semver == "1.1.0"
    assert v1.content_hash != v2.content_hash

    # Active version is the latest
    active = await SkillRegistry.get_active_version(db_session, v1.skill_id)
    assert active is not None
    assert active.semver == "1.1.0"


# --- STEP 6E: 107 Skills Catalog Tests ---


def test_default_catalogue_contains_107_skills():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    assert len(catalogue) == 107

    # Validate category breakdown
    cat_counts = {}
    for m in catalogue:
        cat = m.metadata.category
        # Normalize legacy categories to official mapping
        norm_cat = "business" if cat in ("marketing", "operations") else ("cybersecurity" if cat == "security" else cat)
        cat_counts[norm_cat] = cat_counts.get(norm_cat, 0) + 1

    assert cat_counts["engineering"] == 25
    assert cat_counts["ai_agentic"] == 18
    assert cat_counts["devops"] == 20
    assert cat_counts["cybersecurity"] == 18
    assert cat_counts["data"] == 14
    assert cat_counts["business"] == 12


def test_all_skill_slugs_unique():
    import re
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    slug_pattern = re.compile(r"^[a-z0-9_]{3,50}$")
    seen_slugs = set()

    for m in catalogue:
        slug = m.identity.id
        assert slug_pattern.match(slug), f"Slug format invalid: {slug}"
        assert slug not in seen_slugs, f"Duplicate slug found: {slug}"
        seen_slugs.add(slug)

    assert len(seen_slugs) == 107


def test_all_skill_hashes_valid():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    for m in catalogue:
        assert verify_skill_manifest_hash(m) is True, f"Hash verification failed for {m.identity.id}"


def test_all_skill_versions_valid():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    for m in catalogue:
        assert m.versioning.version == "1.0.0", f"Unexpected version for {m.identity.id}"


def test_core_skills_unchanged():
    from app.skills.catalog import get_core_catalogue, get_default_catalogue

    baseline = {
        "portfolio_ambassador": "sha256:11872bf3b84d8f6d5b0c7ea16855af016ae53f29ea23e65ccf48d95af476d103",
        "lead_qualification": "sha256:6f306e9916903df84c815c282b5eff90420eb2f834d95cdbf955febd839f378d",
        "frontend_react": "sha256:c72d424070b55ef1e21731fe9104ca34793bc6d5982df7b8b057f9d817ff3226",
        "backend_django": "sha256:6cd46b6c23d922551d6f0810d430822d5d70dfeeeb8c1897bb646b66391ea4d5",
        "cybersecurity_defensive": "sha256:0cf6b3f8e7574e1a3673cd1b79bbbe7ff865a14040c053d712826f6f2707e0ce",
    }

    core_cat = get_core_catalogue()
    assert len(core_cat) == 5
    for m in core_cat:
        expected = baseline[m.identity.id]
        assert m.versioning.content_hash == expected, f"Core hash altered: {m.identity.id}"

    default_cat = get_default_catalogue()
    default_dict = {m.identity.id: m for m in default_cat}
    for slug, expected in baseline.items():
        assert slug in default_dict
        assert default_dict[slug].versioning.content_hash == expected


def test_no_self_dependencies():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    for m in catalogue:
        assert m.identity.id not in m.dependencies.required_skills, f"Self dependency in {m.identity.id}"


def test_no_dependency_cycles():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    graph = {m.identity.id: m.dependencies.required_skills for m in catalogue}

    visited = {}  # 0: unvisited, 1: visiting, 2: visited

    def dfs(node, path):
        visited[node] = 1
        for dep in graph.get(node, []):
            if visited.get(dep, 0) == 1:
                raise ValueError(f"Cycle detected: {' -> '.join(path + [dep])}")
            if visited.get(dep, 0) == 0:
                dfs(dep, path + [dep])
        visited[node] = 2

    for slug in graph:
        if visited.get(slug, 0) == 0:
            dfs(slug, [slug])


def test_all_dependencies_exist():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    all_slugs = {m.identity.id for m in catalogue}

    for m in catalogue:
        for dep in m.dependencies.required_skills:
            assert dep in all_slugs, f"Missing dependency {dep} in skill {m.identity.id}"


@pytest.mark.asyncio
async def test_transitive_dependencies_valid(db_session: AsyncSession):
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    by_slug = {m.identity.id: m for m in catalogue}

    target = by_slug.get("alembic_database_migrations")
    assert target is not None
    assert "postgresql_dba" in target.dependencies.required_skills

    # Seed dependencies
    await SkillRegistry.register_manifest(db_session, by_slug["postgresql_dba"])
    ver_target = await SkillRegistry.register_manifest(db_session, target)

    resolved = await SkillRegistry.resolve_transitive_dependencies(db_session, ver_target)
    assert len(resolved) >= 1
    assert any(r.skill.slug == "postgresql_dba" for r in resolved)


def test_conflicts_are_valid():
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    all_slugs = {m.identity.id for m in catalogue}
    conflict_map = {m.identity.id: set(m.governance_hints.conflicts_with) for m in catalogue}

    for slug, confs in conflict_map.items():
        for conf in confs:
            assert conf in all_slugs, f"Conflict with unknown skill {conf} in {slug}"
            assert conf != slug, f"Self conflict in {slug}"
            assert slug in conflict_map.get(conf, set()), f"Asymmetric conflict between {slug} and {conf}"


def test_required_tools_are_declarative():
    from app.skills.catalog import get_default_catalogue

    known_tools = {
        "system.read", "system.create", "system.update", "system.write",
        "infrastructure.create", "infrastructure.update",
        "fs.read", "fs.write", "fs.create",
        "web.search", "web.fetch", "api.call",
        "agent.spawn", "agent.create",
        "facebook.post", "instagram.post", "whatsapp.send", "twitter.post", "discord.send",
    }

    catalogue = get_default_catalogue()
    for m in catalogue:
        for tool in m.dependencies.required_tools:
            assert tool in known_tools, f"Unknown tool {tool} in {m.identity.id}"


@pytest.mark.asyncio
async def test_jit_selector_handles_107_skills(db_session: AsyncSession):
    from app.skills.catalog import get_default_catalogue

    ws = Workspace(name="Scale WS", slug=f"ws-scale-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Full Scale Agent", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    catalogue = get_default_catalogue()
    sample_slugs = [
        "python_fastapi", "postgresql_dba", "typescript_advanced",
        "redis_inmemory_architect", "rag_hybrid_search", "vector_db_pgvector",
        "docker_multistage_builder", "owasp_top_10_auditor", "celery_task_worker_queue",
        "telegram_bot_operations",
    ]

    by_slug = {m.identity.id: m for m in catalogue}
    for slug in sample_slugs:
        ver = await SkillRegistry.register_manifest(db_session, by_slug[slug])
        await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver)

    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent.id,
        workspace_id=ws.id,
        task_skill_hint="fastapi",
        task_description="Build a high performance async API with endpoints",
    )
    assert len(selected) > 0
    assert len(selected) <= 2
    assert selected[0].id == "python_fastapi"


@pytest.mark.asyncio
async def test_max_skills_limit_is_respected(db_session: AsyncSession):
    from app.skills.catalog import get_default_catalogue

    ws = Workspace(name="Max Limit WS", slug=f"ws-max-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    agent = Agent(workspace_id=ws.id, name="Max Limit Agent", default_autonomy_level=2)
    db_session.add(agent)
    await db_session.flush()

    catalogue = get_default_catalogue()
    for m in catalogue[:12]:
        ver = await SkillRegistry.register_manifest(db_session, m)
        await SkillSelector.assign_skill_to_agent(db_session, agent.id, ver)

    selected = await SkillSelector.select_skills_for_task(
        db_session,
        agent_id=agent.id,
        workspace_id=ws.id,
        task_skill_hint=None,
        task_description="Perform general engineering tasks",
    )
    assert len(selected) <= 2


@pytest.mark.asyncio
async def test_seed_107_skills_idempotent(db_session: AsyncSession):
    from app.skills.catalog import seed_default_skills

    seeded_1 = await seed_default_skills(db_session)
    assert len(seeded_1) == 107

    seeded_2 = await seed_default_skills(db_session)
    assert len(seeded_2) == 107

    for v1, v2 in zip(seeded_1, seeded_2):
        assert v1.id == v2.id
        assert v1.content_hash == v2.content_hash


@pytest.mark.asyncio
async def test_immutable_version_violation_preserved(db_session: AsyncSession):
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    orig = catalogue[0]
    await SkillRegistry.register_manifest(db_session, orig)

    tampered_knowledge = SkillManifestKnowledge(
        instructions="Tampered instructions altering sealed skill.",
        constraints=orig.knowledge.constraints,
    )
    tampered_hash = compute_canonical_content_hash(tampered_knowledge, orig.dependencies)
    tampered_manifest = SkillManifest(
        manifest_version="1.0",
        identity=orig.identity,
        versioning=SkillManifestVersioning(version="1.0.0", content_hash=tampered_hash),
        metadata=orig.metadata,
        knowledge=tampered_knowledge,
        dependencies=orig.dependencies,
        governance_hints=orig.governance_hints,
    )

    with pytest.raises(SkillVersionImmutableViolationError):
        await SkillRegistry.register_manifest(db_session, tampered_manifest)


@pytest.mark.asyncio
async def test_workspace_skill_shadows_system_skill_deterministically(db_session: AsyncSession):
    """FIX 2: Workspace skill shadows system skill when workspace_id is provided."""
    ws = Workspace(name="WS Shadow", slug=f"ws-shadow-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    slug = f"shadow_skill_{uuid.uuid4().hex[:6]}"

    # Register system skill
    sys_m = _create_dummy_manifest(
        skill_id=slug,
        version="1.0.0",
        instructions="System instructions for shadow skill.",
        is_system=True,
    )
    await SkillRegistry.register_manifest(db_session, sys_m)

    # Register workspace skill with identical slug
    ws_m = _create_dummy_manifest(
        skill_id=slug,
        version="1.0.0",
        instructions="Workspace custom instructions for shadow skill.",
        is_system=False,
    )
    await SkillRegistry.register_manifest(db_session, ws_m, workspace_id=ws.id)

    # When querying with workspace_id, the workspace skill MUST be returned
    resolved = await SkillRegistry.get_skill(db_session, slug, workspace_id=ws.id)
    assert resolved is not None
    assert resolved.is_system is False
    assert resolved.workspace_id == ws.id

    # When querying without workspace_id, the system skill MUST be returned
    sys_resolved = await SkillRegistry.get_skill(db_session, slug, workspace_id=None)
    assert sys_resolved is not None
    assert sys_resolved.is_system is True
    assert sys_resolved.workspace_id is None


@pytest.mark.asyncio
async def test_workspace_skill_shadows_even_when_system_created_later(db_session: AsyncSession):
    """FIX 2: Workspace skill wins even if system skill was inserted AFTER it in time."""
    ws = Workspace(name="WS Shadow Order", slug=f"ws-so-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    slug = f"shadow_order_{uuid.uuid4().hex[:6]}"

    # 1. Register workspace skill FIRST (older created_at)
    ws_m = _create_dummy_manifest(
        skill_id=slug,
        version="1.0.0",
        instructions="Workspace custom instructions created first.",
        is_system=False,
    )
    await SkillRegistry.register_manifest(db_session, ws_m, workspace_id=ws.id)

    # 2. Register system skill SECOND (newer created_at)
    sys_m = _create_dummy_manifest(
        skill_id=slug,
        version="1.0.0",
        instructions="System instructions created later.",
        is_system=True,
    )
    await SkillRegistry.register_manifest(db_session, sys_m)

    # Must STILL return the workspace skill because is_system=False takes precedence over is_system=True
    resolved = await SkillRegistry.get_skill(db_session, slug, workspace_id=ws.id)
    assert resolved is not None
    assert resolved.is_system is False
    assert resolved.workspace_id == ws.id



@pytest.mark.asyncio
async def test_workspace_skill_fallback_to_system_when_absent(db_session: AsyncSession):
    """FIX 2: System skill is returned when no workspace skill exists for the workspace."""
    ws = Workspace(name="WS Fallback", slug=f"ws-fallback-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()

    slug = f"fallback_skill_{uuid.uuid4().hex[:6]}"
    sys_m = _create_dummy_manifest(
        skill_id=slug,
        version="1.0.0",
        instructions="System fallback instructions.",
        is_system=True,
    )
    await SkillRegistry.register_manifest(db_session, sys_m)

    resolved = await SkillRegistry.get_skill(db_session, slug, workspace_id=ws.id)
    assert resolved is not None
    assert resolved.is_system is True
    assert resolved.workspace_id is None


@pytest.mark.asyncio
async def test_workspace_a_cannot_see_workspace_b_skill_in_get_skill(db_session: AsyncSession):
    """FIX 2: Workspace A cannot see Workspace B skill via get_skill."""
    ws_a = Workspace(name="WS Iso A", slug=f"ws-iso-a-{uuid.uuid4().hex[:8]}")
    ws_b = Workspace(name="WS Iso B", slug=f"ws-iso-b-{uuid.uuid4().hex[:8]}")
    db_session.add_all([ws_a, ws_b])
    await db_session.flush()

    slug = f"ws_b_only_{uuid.uuid4().hex[:6]}"
    ws_b_m = _create_dummy_manifest(
        skill_id=slug,
        version="1.0.0",
        instructions="WS B only instructions.",
        is_system=False,
    )
    await SkillRegistry.register_manifest(db_session, ws_b_m, workspace_id=ws_b.id)

    # ws_b sees it
    res_b = await SkillRegistry.get_skill(db_session, slug, workspace_id=ws_b.id)
    assert res_b is not None
    assert res_b.workspace_id == ws_b.id

    # ws_a CANNOT see it
    res_a = await SkillRegistry.get_skill(db_session, slug, workspace_id=ws_a.id)
    assert res_a is None

    # Global scope (None) cannot see it either
    res_none = await SkillRegistry.get_skill(db_session, slug, workspace_id=None)
    assert res_none is None


def test_skill_category_enum_contains_all_expected_values():
    """FIX 3: SkillCategory enum has all 11 expected values (backward compatible + new)."""
    expected = {
        "engineering",
        "ai_agentic",
        "devops",
        "cybersecurity",
        "data",
        "business",
        "marketing",
        "operations",
        "security",
        "research",
        "general",
    }
    actual = {cat.value for cat in SkillCategory}
    assert expected == actual


def test_all_107_catalog_categories_parseable_by_enum():
    """FIX 3: Every category used in the 107 catalog can be parsed by SkillCategory."""
    from app.skills.catalog import get_default_catalogue

    catalogue = get_default_catalogue()
    assert len(catalogue) == 107

    seen_categories = set()
    for manifest in catalogue:
        cat_str = manifest.metadata.category
        seen_categories.add(cat_str)
        # Must parse cleanly without raising ValueError
        enum_member = SkillCategory(cat_str)
        assert enum_member.value == cat_str

    # Verify that all 6 domain categories are present in the catalog
    assert {"engineering", "ai_agentic", "devops", "cybersecurity", "data", "business"}.issubset(seen_categories)


def test_skill_category_serialization_roundtrip():
    """FIX 3: SkillCategory serializes to string and deserializes correctly in Pydantic."""
    from pydantic import BaseModel

    class CategoryHolder(BaseModel):
        category: SkillCategory

    for cat in SkillCategory:
        # String instantiation
        holder = CategoryHolder(category=cat.value)
        assert holder.category == cat

        # JSON dump produces raw string value
        json_data = holder.model_dump_json()
        assert f'"{cat.value}"' in json_data

        # Parsing back from JSON
        reparsed = CategoryHolder.model_validate_json(json_data)
        assert reparsed.category == cat





