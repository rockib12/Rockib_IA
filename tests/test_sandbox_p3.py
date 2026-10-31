"""Tests unitaires et de sécurité pour P3 — Sandbox d'Exécution Isolée pour les Agents."""
import json
import os
import uuid
import pytest

from app.connectors.sandbox_connector import (
    _build_clean_room_env,
    execute_in_sandbox,
    sandbox_run_handler,
    validate_python_code_safety,
)
from app.execution.models import ActionRecord


@pytest.mark.asyncio
async def test_sandbox_compile_execute_and_unit_tests_success():
    code = """
def fibonacci(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print("Fib(10) =", fibonacci(10))
"""
    test_code = """
assert fibonacci(0) == 0
assert fibonacci(1) == 1
assert fibonacci(10) == 55
"""
    report = await execute_in_sandbox(code=code, test_code=test_code, timeout_seconds=5.0)
    assert report.compile_ok is True
    assert report.execution_ok is True
    assert report.tests_passed is True
    assert report.exit_code == 0
    assert "Fib(10) = 55" in report.stdout
    assert len(report.security_violations) == 0


@pytest.mark.asyncio
async def test_sandbox_sast_blocks_dangerous_imports_and_calls():
    # 1. Import interdit (os / subprocess / socket)
    v1 = validate_python_code_safety("import os\nos.system('whoami')")
    assert any("FORBIDDEN_IMPORT" in v for v in v1)

    # 2. Appel eval / open interdit
    v2 = validate_python_code_safety("data = open('/etc/passwd').read()")
    assert any("FORBIDDEN_CALL" in v for v in v2)

    # 3. Tentative d'évasion AST (__subclasses__)
    v3 = validate_python_code_safety("x = ().__class__.__base__.__subclasses__()")
    assert any("SANDBOX_ESCAPE_ATTEMPT" in v for v in v3)

    # 4. Tentative de lecture de secret .env
    v4 = validate_python_code_safety("secret = 'CREDENTIAL_VAULT_KEY'")
    assert any("SECURITY_POLICY_VIOLATION" in v for v in v4)


def test_clean_room_env_strips_all_server_secrets(tmp_path):
    os.environ["JWT_SECRET_KEY"] = "test_super_secret"
    os.environ["CREDENTIAL_VAULT_KEY"] = "test_vault_secret"
    clean_env = _build_clean_room_env(tmp_path)
    assert "JWT_SECRET_KEY" not in clean_env
    assert "CREDENTIAL_VAULT_KEY" not in clean_env
    assert "GROQ_API_KEY" not in clean_env
    assert clean_env["PYTHONNOUSERSITE"] == "1"


@pytest.mark.asyncio
async def test_sandbox_run_handler_action_record():
    action_ok = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="sandbox",
        operation="run",
        arguments={
            "code": "def add(x, y):\n    return x + y\nprint(add(7, 8))",
            "test_code": "assert add(7, 8) == 15",
        },
    )
    res_ok = await sandbox_run_handler(action_ok)
    assert res_ok.success is True
    parsed = json.loads(res_ok.output)
    assert parsed["tests_passed"] is True
    assert "15" in parsed["stdout"]

    action_blocked = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        tool="sandbox",
        operation="run",
        arguments={
            "code": "import subprocess\nsubprocess.run(['ls'])",
        },
    )
    res_blocked = await sandbox_run_handler(action_blocked)
    assert res_blocked.success is False
    assert res_blocked.error_code == "SANDBOX_SECURITY_VIOLATION"


@pytest.mark.asyncio
async def test_p8_auto_proposal_engine_generates_architecture_and_budget():
    from app.inbound.services.proposal_generator import AutoProposalEngine

    proposal = await AutoProposalEngine.generate_proposal(
        client_name="Amadou Diallo",
        company_name="MartiGroup Africa",
        project_brief="Créer une plateforme SaaS e-commerce multi-boutique avec agent IA WhatsApp et paiement Stripe/Mobile Money",
        currency="EUR",
    )
    assert proposal["proposal_ref"].startswith("PROP-RK-")
    assert proposal["estimated_days"] >= 8
    assert proposal["estimated_budget_eur"] > 0
    assert proposal["estimated_budget_fcfa"] > proposal["estimated_budget_eur"] * 600
    assert len(proposal["recommended_stack"]) >= 4
    assert len(proposal["phases"]) == 4
    assert "PROPOSITION D'ARCHITECTURE" in proposal["proposal_markdown"]
    assert "Amadou Diallo" in proposal["proposal_markdown"]


@pytest.mark.asyncio
async def test_p9_lead_hunter_engine_discovers_prospects_and_builds_outreach_scripts():
    from app.inbound.services.lead_hunter import LeadHunterEngine

    report = await LeadHunterEngine.hunt_and_prepare_outreach(
        niche="Agences immobilières",
        location="Cotonou",
        max_leads=3,
        save_to_crm=False,
        notify_telegram=False,
    )
    assert report["sector_key"] == "immobilier"
    assert report["total_found"] == 3
    first = report["prospects"][0]
    assert "company_name" in first
    assert "whatsapp" in first["scripts"]
    assert "linkedin" in first["scripts"]
    assert "email" in first["scripts"]
    assert first["proposal_ref"].startswith("PROP-RK-")
    assert "PROPOSITION D'ARCHITECTURE" in first["proposal_markdown"]


