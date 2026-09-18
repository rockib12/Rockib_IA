from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.decision_engine.models import ControlOutcome, Decision, DecisionStatus, DominantSource, PermissionAction, RiskLevel
from app.decision_engine.services.control import set_control
from app.identity.models import Agent
from app.decision_engine.schemas import DecisionRequest, DecisionResponse
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.intelligence.services.intelligence_service import IntelligenceService
from app.execution.services.executor import execute
from app.execution.services.auditor import log_execution
from app.intelligence.schemas import IntelligenceInput
from app.cognitive.services.pattern_miner import mine_patterns
from app.cognitive.services.simulation import CognitiveSimulator
from app.cognitive.schemas import CognitiveInput

class DecisionOrchestrator:
    def __init__(
        self,
        db: AsyncSession,
        classifier: DomainClassifier,
        arbitrator: DeterministicArbitrator,
        intelligence: IntelligenceService,
        cognitive_simulator: CognitiveSimulator,
    ):
        self.db = db
        self.classifier = classifier
        self.arbitrator = arbitrator
        self.intelligence = intelligence
        self.cognitive_simulator = cognitive_simulator

    async def _load_agent(self, agent_id: str) -> Agent:
        stmt = select(Agent).where(Agent.id == agent_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def handle_decision(self, request: DecisionRequest) -> DecisionResponse:
        # 0. Load agent and mine patterns
        agent = await self._load_agent(request.agent_id)
        patterns = await mine_patterns(self.db, request.workspace_id)

        # 1. Classification
        classification = await self.classifier.classify(
            request.proposed_action, request.objective, request.situation
        )

        if classification.status != "CERTAIN":
            # Escalate if classification is not CERTAIN
            return DecisionResponse(
                decision_id="escalated",
                dominant_source="human",
                final_action=request.proposed_action,
                risk_level="high",
                approval_required=True,
                control_outcome=ControlOutcome.ESCALATE,
                control_reason="CLASSIFICATION_UNCERTAIN",
                permission_granted=False,
            )

        # 2. Opinions
        # Cognitive Opinion
        cog_opinion = await self.cognitive_simulator.simulate(
            CognitiveInput(workspace_id=request.workspace_id, objective=request.objective, situation=request.situation),
            patterns
        )

        # Intelligence Opinion
        intel_input = IntelligenceInput(
            objective=request.objective,
            situation=request.situation,
            proposed_action=request.proposed_action,
            domain=classification.domain,
            permission_action=classification.permission_action
        )
        intel_opinion = await self.intelligence.evaluate(intel_input)

        # 3. Arbitration
        decision = await self.arbitrator.arbitrate(
            objective=request.objective,
            situation=request.situation,
            proposed_action=request.proposed_action,
            cognitive_opinion={
                "action": cog_opinion.action,
                "confidence": cog_opinion.confidence,
            },
            intelligence_opinion={
                "action": intel_opinion.suggested_action,
                "confidence": intel_opinion.confidence,
                "risk_level": intel_opinion.risk_level,
            },
            domain=classification.domain,
            permission_action=classification.permission_action,
            requested_autonomy_level=(
                request.requested_autonomy_level
                if request.requested_autonomy_level is not None
                else agent.default_autonomy_level
            ),
            workspace_id=request.workspace_id,
            agent_id=request.agent_id,
        )

        # Until actions are structured, a changed action needs a fresh scope/risk
        # evaluation. Preserve it, but never execute it under the original policy.
        if (
            decision.control_outcome == ControlOutcome.ALLOW
            and (
                decision.final_action != request.proposed_action
                or decision.final_action != intel_opinion.suggested_action
            )
        ):
            set_control(decision, ControlOutcome.ESCALATE, "ACTION_REQUIRES_REEVALUATION")

        # 4. Persist
        self.db.add(decision)
        await self.db.commit()
        await self.db.refresh(decision)

        # Only an explicit server-side ALLOW may reach the executor.
        # The executor independently verifies permission and payload integrity.
        if decision.control_outcome == ControlOutcome.ALLOW:
            exec_result = await execute(decision)
            log_execution(decision, exec_result)

        return DecisionResponse(
            decision_id=str(decision.id),
            dominant_source=decision.dominant_source or DominantSource.cognitive,
            final_action=decision.final_action or request.proposed_action,
            risk_level=decision.risk_level,
            approval_required=decision.approval_required,
            control_outcome=decision.control_outcome,
            control_reason=decision.control_reason,
            permission_granted=decision.permission_granted,
        )
