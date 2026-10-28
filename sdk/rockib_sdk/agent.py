"""`GovernedAgent` — agent dont chaque action passe par l'arbitre déterministe."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Union

from .approval import ApprovalCallable, ApprovalHandler, as_handler
from .arbitrator import DeterministicArbitrator, Policy
from .audit import AuditTrail
from .budget import BudgetLedger, Number, to_decimal
from .errors import AutonomyEscalationError, BudgetViolationError, SkillNotGrantedError
from .models import ActionProposal, ActionResult, Decision, Outcome
from .skills import Skill

MAX_AUTONOMY = 5


class GovernedAgent:
    def __init__(
        self,
        name: str,
        role: str = "Agent",
        autonomy_level: int = 2,
        skills: Optional[Iterable[Skill]] = None,
        budget_ceiling: Optional[Number] = None,
        currency: str = "EUR",
        policy: Optional[Policy] = None,
        approval: Union[None, ApprovalHandler, ApprovalCallable] = None,
        audit: Optional[AuditTrail] = None,
        parent: Optional["GovernedAgent"] = None,
    ) -> None:
        if not 0 <= autonomy_level <= MAX_AUTONOMY:
            raise ValueError(f"autonomy_level doit être entre 0 et {MAX_AUTONOMY}")
        if parent is not None and autonomy_level > parent.autonomy_level:
            raise AutonomyEscalationError(
                f"'{name}' ({autonomy_level}) ne peut dépasser son parent '{parent.name}' ({parent.autonomy_level})"
            )
        self.name = name
        self.role = role
        self.autonomy_level = autonomy_level
        self.currency = currency
        self.parent = parent
        self.children: List[GovernedAgent] = []
        self.skills: Dict[str, Skill] = {s.name: s for s in (skills or [])}
        if parent is not None:
            missing = set(self.skills) - set(parent.skills)
            if missing:
                raise SkillNotGrantedError(f"Compétences non détenues par le parent : {sorted(missing)}")
        self.arbitrator = DeterministicArbitrator(policy or (parent.arbitrator.policy if parent else None))
        self.approval = as_handler(approval) if approval is not None or parent is None else parent.approval
        self.audit = audit or (parent.audit if parent else AuditTrail())
        self.budget = BudgetLedger(budget_ceiling, parent=parent.budget if parent else None)
        self.history: List[ActionResult] = []

    # ── Hiérarchie ────────────────────────────────────────────────────
    def spawn(
        self,
        name: str,
        role: str = "Sub-Agent",
        autonomy_level: Optional[int] = None,
        skills: Optional[Iterable[Union[str, Skill]]] = None,
        budget_ceiling: Optional[Number] = None,
    ) -> "GovernedAgent":
        """Crée un sous-agent : autonomie ≤ parent, compétences ⊆ parent, budget ≤ restant parent."""
        level = self.autonomy_level if autonomy_level is None else autonomy_level
        selected = [self.skills[s] if isinstance(s, str) else s for s in (skills or self.skills.values())]
        child = GovernedAgent(
            name=name,
            role=role,
            autonomy_level=level,
            skills=selected,
            budget_ceiling=budget_ceiling,
            currency=self.currency,
            parent=self,
        )
        self.children.append(child)
        self.audit.record("agent.spawned", parent=self.name, child=name, autonomy=level)
        return child

    # ── Exécution gouvernée ───────────────────────────────────────────
    def propose(self, skill_name: str, requested_autonomy: Optional[int] = None, **kwargs: Any) -> ActionProposal:
        sk = self.skills.get(skill_name)
        if sk is None:
            raise SkillNotGrantedError(f"'{self.name}' ne possède pas la compétence '{skill_name}'")
        amount: Optional[Decimal] = None
        if sk.spend_arg:
            raw = kwargs.get(sk.spend_arg)
            try:
                amount = to_decimal(raw) if raw is not None else None
            except BudgetViolationError:
                amount = None  # sera refusé par l'arbitre (INVALID_AMOUNT)
        return ActionProposal(
            agent_name=self.name,
            skill_name=sk.name,
            domain=sk.domain,
            permission=sk.permission,
            risk=sk.risk,
            reversible=sk.reversible,
            requested_autonomy=self.autonomy_level if requested_autonomy is None else requested_autonomy,
            allowed_autonomy=self.autonomy_level,
            amount=amount,
            currency=self.currency,
            arguments=dict(kwargs),
        )

    async def execute(self, skill_name: str, requested_autonomy: Optional[int] = None, **kwargs: Any) -> ActionResult:
        proposal = self.propose(skill_name, requested_autonomy=requested_autonomy, **kwargs)
        sk = self.skills[skill_name]
        sk.verify()  # intégrité SHA-256 avant toute exécution

        decision = self.arbitrator.decide(proposal, remaining_budget=self.budget.remaining())
        self.audit.record("decision", proposal=proposal, decision=decision)

        approved_by: Optional[str] = None
        if decision.outcome == Outcome.DENY:
            return self._finish(ActionResult(proposal, decision, False, False, error=decision.error_code))
        if decision.outcome == Outcome.ESCALATE:
            approved = await self.approval.request(proposal, decision)
            self.audit.record("approval", proposal_id=proposal.proposal_id, approved=approved, handler=self.approval.name)
            if not approved:
                return self._finish(ActionResult(proposal, decision, False, False, error="HUMAN_REJECTED"))
            approved_by = self.approval.name

        amount = proposal.amount
        if amount is not None:
            try:
                self.budget.hold(amount)
            except BudgetViolationError as exc:
                denied = Decision(Outcome.DENY, decision.applied_autonomy, [str(exc)], False, "QUOTA_EXCEEDED")
                return self._finish(ActionResult(proposal, denied, False, False, error="QUOTA_EXCEEDED"))
        try:
            output = await sk.invoke(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if amount is not None:
                self.budget.release(amount)
            return self._finish(
                ActionResult(proposal, decision, True, False, error=f"{type(exc).__name__}: {exc}", approved_by=approved_by)
            )
        if amount is not None:
            self.budget.commit(amount)
        return self._finish(ActionResult(proposal, decision, True, True, output=output, approved_by=approved_by))

    def execute_sync(self, skill_name: str, **kwargs: Any) -> ActionResult:
        return asyncio.run(self.execute(skill_name, **kwargs))

    def _finish(self, result: ActionResult) -> ActionResult:
        self.history.append(result)
        self.audit.record(
            "action.result",
            proposal_id=result.proposal.proposal_id,
            agent=self.name,
            skill=result.proposal.skill_name,
            outcome=result.outcome,
            executed=result.executed,
            success=result.success,
            error=result.error,
        )
        return result

    def __repr__(self) -> str:
        return f"<GovernedAgent {self.name!r} autonomy={self.autonomy_level} skills={list(self.skills)}>"
