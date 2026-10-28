"""Tests du SDK Rockib : arbitrage, budget, scellement, hiérarchie, audit, essaim, CLI."""
import json
from decimal import Decimal

import pytest

from rockib_sdk import (
    AuditTrail,
    AutoApprove,
    AutonomyEscalationError,
    BudgetViolationError,
    DenyAll,
    GovernedAgent,
    Outcome,
    Policy,
    SkillIntegrityError,
    SkillNotGrantedError,
    Step,
    Swarm,
    skill,
    verify_entries,
)
from rockib_sdk.audit import AuditIntegrityError
from rockib_sdk.cli import main as cli_main


@skill(domain="ops", keywords=["diagnostic", "sante"])
def diagnostic() -> str:
    """Diagnostic de santé système."""
    return "OK"


@skill(domain="finance", permission="SPEND", risk="HIGH", reversible=False, spend_arg="montant")
def payer(montant: int, cible: str) -> str:
    """Paiement fournisseur."""
    return f"payé {montant} à {cible}"


@skill(domain="data", permission="DELETE", risk="MEDIUM")
def purger(table: str) -> str:
    return f"purge {table}"


@skill(domain="ops")
def explose() -> str:
    raise RuntimeError("panne")


def make_agent(**kw):
    defaults = dict(
        name="Root", autonomy_level=4, skills=[diagnostic, payer, purger, explose],
        budget_ceiling=1000, policy=Policy(auto_spend_limit=100), approval=AutoApprove(),
    )
    defaults.update(kw)
    return GovernedAgent(**defaults)


async def test_low_risk_action_is_allowed_and_executed():
    ag = make_agent()
    res = await ag.execute("diagnostic")
    assert res.outcome == Outcome.ALLOW and res.success and res.output == "OK"


async def test_high_risk_irreversible_spend_escalates_then_runs_when_approved():
    ag = make_agent()
    res = await ag.execute("payer", montant=300, cible="OVH")
    assert res.outcome == Outcome.ESCALATE
    assert res.success and res.approved_by == "auto_approve"
    assert ag.budget.remaining() == Decimal("700")


async def test_escalation_rejected_by_default_fail_closed():
    ag = make_agent(approval=None)
    assert isinstance(ag.approval, DenyAll)
    res = await ag.execute("payer", montant=10, cible="X")
    assert not res.executed and res.error == "HUMAN_REJECTED"
    assert ag.budget.remaining() == Decimal("1000")


async def test_delete_always_escalates():
    ag = make_agent(approval=DenyAll())
    res = await ag.execute("purger", table="users")
    assert res.outcome == Outcome.ESCALATE and "Permission DELETE" in res.decision.reasons


async def test_budget_ceiling_violation_denied_before_approval():
    ag = make_agent()
    res = await ag.execute("payer", montant=5000, cible="X")
    assert res.outcome == Outcome.DENY and res.decision.error_code == "BUDGET_CEILING_VIOLATION"
    assert not res.executed


async def test_float_amount_is_rejected():
    ag = make_agent()
    res = await ag.execute("payer", montant=12.5, cible="X")
    assert res.outcome == Outcome.DENY and res.decision.error_code == "INVALID_AMOUNT"
    with pytest.raises(BudgetViolationError):
        GovernedAgent("Bad", budget_ceiling=10.0)


async def test_failed_execution_releases_held_budget():
    ag = make_agent()
    res = await ag.execute("explose")
    assert res.executed and not res.success and "panne" in res.error
    assert ag.budget.held == 0


def test_child_autonomy_and_skills_are_monotone():
    root = make_agent(autonomy_level=2)
    with pytest.raises(AutonomyEscalationError):
        root.spawn("Rogue", autonomy_level=5)
    child = root.spawn("Child", autonomy_level=1, skills=["diagnostic"])
    assert child.autonomy_level == 1
    with pytest.raises(SkillNotGrantedError):
        GovernedAgent("X", autonomy_level=1, skills=[payer], parent=child)


async def test_child_budget_bounded_by_parent_and_propagates():
    root = make_agent(budget_ceiling=500)
    with pytest.raises(BudgetViolationError):
        root.spawn("Greedy", budget_ceiling=900)
    child = root.spawn("Treso", skills=["payer"], budget_ceiling=400)
    res = await child.execute("payer", montant=350, cible="OVH")
    assert res.success
    assert child.budget.remaining() == Decimal("50")
    assert root.budget.remaining() == Decimal("150")
    second = await child.execute("payer", montant=100, cible="OVH")
    assert second.outcome == Outcome.DENY


async def test_requested_autonomy_cannot_exceed_allowed():
    ag = make_agent(autonomy_level=1, approval=DenyAll())
    res = await ag.execute("diagnostic", requested_autonomy=5)
    assert res.decision.applied_autonomy == 1


async def test_tampered_skill_is_blocked():
    @skill(domain="ops")
    def fragile() -> str:
        return "v1"

    ag = make_agent(skills=[fragile])
    fragile.description = "modifié après scellement"
    with pytest.raises(SkillIntegrityError):
        await ag.execute("fragile")


async def test_audit_chain_detects_tampering(tmp_path):
    path = tmp_path / "audit.jsonl"
    ag = make_agent(audit=AuditTrail(path))
    await ag.execute("diagnostic")
    await ag.execute("payer", montant=20, cible="A")
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert verify_entries(entries) == len(entries) >= 4
    entries[0]["data"]["decision"]["outcome"] = "ALLOW_FORGED"
    with pytest.raises(AuditIntegrityError):
        verify_entries(entries)


async def test_swarm_keyword_planner_and_explicit_plan():
    root = make_agent()
    root.spawn("Treso", autonomy_level=3, skills=["payer"], budget_ceiling=200)
    swarm = Swarm([root])
    auto = await swarm.run("Lance un diagnostic de santé")
    assert auto.success and auto.steps[0].skill == "diagnostic"

    report = await swarm.run("Payer", plan=[
        Step("Treso", "payer", {"montant": 150, "cible": "A"}),
        Step("Treso", "payer", {"montant": 150, "cible": "B"}),
    ])
    assert not report.success
    assert [r.outcome for r in report.results] == [Outcome.ESCALATE, Outcome.DENY]


async def test_async_skill_and_callable_approval():
    @skill(domain="ops", permission="SEND", risk="HIGH")
    async def notifier(msg: str) -> str:
        return f"envoyé: {msg}"

    seen = []

    async def approve(proposal, decision):
        seen.append(proposal.skill_name)
        return True

    ag = make_agent(skills=[notifier], approval=approve)
    res = await ag.execute("notifier", msg="hello")
    assert res.success and res.output == "envoyé: hello" and seen == ["notifier"]


def test_cli_init_skills_and_audit(tmp_path, capsys):
    assert cli_main(["init", str(tmp_path)]) == 0
    assert cli_main(["skills", str(tmp_path / "agents.py")]) == 0
    out = capsys.readouterr().out
    assert "diagnostic_systeme" in out and "payer_facture" in out

    trail = AuditTrail(tmp_path / "a.jsonl")
    trail.record("test", value=1)
    trail.record("test", value=2)
    assert cli_main(["audit", str(tmp_path / "a.jsonl")]) == 0
