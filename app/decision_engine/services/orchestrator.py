import json
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.decision_engine.models import (
    ControlOutcome,
    Decision,
    DecisionOutcome,
    DecisionStatus,
    DominantSource,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
)
from app.decision_engine.services.control import set_control
from app.identity.models import Agent
from app.decision_engine.schemas import DecisionRequest, DecisionResponse
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.services.arbitrator import DeterministicArbitrator
from app.decision_engine.services.escalation import notify_escalation
from app.intelligence.services.intelligence_service import IntelligenceService
from app.execution.models import ActionRecord, EffectCertainty
from app.execution.services.authorizations import (
    AuthorizationError,
    issue_authorization,
)
from app.execution.services.fingerprint import (
    compute_fingerprint,
    compute_idempotency_key,
)
from app.execution.services.reliable_executor import dispatch_authorized_action
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

    async def handle_decision(
        self, request: DecisionRequest, *, task_id: Optional[uuid.UUID] = None
    ) -> DecisionResponse:
        # 0. Load agent and mine patterns
        agent = await self._load_agent(request.agent_id)
        patterns = await mine_patterns(self.db, request.workspace_id)

        # 1. Classification
        classification = await self.classifier.classify(
            request.proposed_action, request.objective, request.situation
        )

        if classification.status != "CERTAIN":
            # Classification incertaine : persister une vraie Decision d'escalade
            # (ecart §11 « escalades non persistees »). permission_required reste
            # NULL — inconnu, jamais classifie, pas de valeur fabriquee (§6).
            # Tous les enums sont passes comme membres, jamais comme strings.
            decision = Decision(
                workspace_id=request.workspace_id,
                agent_id=request.agent_id,
                objective=request.objective,
                situation=request.situation,
                proposed_action=request.proposed_action,
                status=DecisionStatus.escalated,
                control_outcome=ControlOutcome.ESCALATE,
                control_reason="CLASSIFICATION_UNCERTAIN",
                permission_required=None,
                permission_granted=False,
                approval_required=True,
                risk_level=RiskLevel.high,
                risk_reversibility=ReversibilityLevel.reversible,
                risk_impact=ImpactType.internal,
                requested_autonomy_level=0,
                applied_autonomy_level=0,
                dominant_source=DominantSource.cognitive,
                final_action=request.proposed_action,
            )
            self.db.add(decision)
            await self.db.commit()
            await self.db.refresh(decision)

            return DecisionResponse(
                decision_id=str(decision.id),
                dominant_source=decision.dominant_source,
                final_action=decision.final_action,
                risk_level=decision.risk_level,
                approval_required=decision.approval_required,
                control_outcome=decision.control_outcome,
                control_reason=decision.control_reason,
                permission_granted=decision.permission_granted,
            )

        classification_domain = classification.domain
        classification_permission = classification.permission_action

        # 1b. Sélection Sémantique JIT des Skills de l'Agent (parmi les 107 Skills)
        active_skills = None
        try:
            from app.skills.services.selector import SkillSelector
            selected = await SkillSelector.select_skills_for_task(
                session=self.db,
                agent_id=request.agent_id,
                workspace_id=request.workspace_id,
                task_skill_hint=classification_domain,
                task_description=f'{request.proposed_action} {request.objective}',
            )
            if selected:
                active_skills = selected
        except Exception:
            active_skills = None

        # 2. Opinions exécutées en parallèle (CognitiveSimulator + IntelligenceService)
        import asyncio
        intel_input = IntelligenceInput(
            objective=request.objective,
            situation=request.situation,
            proposed_action=request.proposed_action,
            domain=classification_domain,
            permission_action=classification_permission,
            active_skills=active_skills,
        )

        cog_opinion, intel_opinion = await asyncio.gather(
            self.cognitive_simulator.simulate(
                CognitiveInput(workspace_id=request.workspace_id, objective=request.objective, situation=request.situation),
                patterns
            ),
            self.intelligence.evaluate(intel_input),
        )

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
            domain=classification_domain,
            permission_action=classification_permission,
            requested_autonomy_level=(
                request.requested_autonomy_level
                if request.requested_autonomy_level is not None
                else agent.default_autonomy_level
            ),
            workspace_id=request.workspace_id,
            agent_id=request.agent_id,
        )

        import json
        def is_json(text: str) -> bool:
            try:
                json.loads(text)
                return True
            except (ValueError, TypeError):
                return False

        # Until actions are structured, a changed action needs a fresh scope/risk
        # evaluation. If the proposed action was unstructured (natural language),
        # transforming it into JSON is the expected behavior, not a reason to escalate.
        if (
            decision.control_outcome == ControlOutcome.ALLOW
            and is_json(request.proposed_action)
            and (
                decision.final_action != request.proposed_action
                or decision.final_action != intel_opinion.suggested_action
            )
        ):
            set_control(decision, ControlOutcome.ESCALATE, "ACTION_REQUIRES_REEVALUATION")

        # 4. Persister la décision, puis l'action structurée correspondante
        #    (l'action est auditable même pour un refus : elle trace ce qui a
        #    été demandé).
        self.db.add(decision)
        await self.db.commit()
        await self.db.refresh(decision)

        tool = classification_domain
        operation = classification_permission.value
        
        # 4b. Extraction robuste des arguments selon la source dominante
        parsed_arguments: dict[str, Any] = {}
        if decision.dominant_source == DominantSource.intelligence:
            parsed_arguments = getattr(intel_opinion, "arguments", {}) or {}
        elif decision.dominant_source == DominantSource.cognitive:
            parsed_arguments = getattr(cog_opinion, "arguments", {}) or {}
        elif decision.dominant_source == DominantSource.consensus:
            parsed_arguments = getattr(intel_opinion, "arguments", {}) or getattr(cog_opinion, "arguments", {}) or {}
        else:
            parsed_arguments = {}

        # Validation défensive : s'assurer que c'est bien un dictionnaire
        if not isinstance(parsed_arguments, dict):
            parsed_arguments = {}

        action_record = ActionRecord(
            workspace_id=decision.workspace_id,
            agent_id=decision.agent_id,
            decision_id=decision.id,
            task_id=task_id,
            objective=decision.objective,
            tool=tool,
            operation=operation,
            arguments=parsed_arguments,
            permission_required=decision.permission_required,
            risk_level=decision.risk_level,
            risk_reversibility=decision.risk_reversibility,
            risk_impact=decision.risk_impact,
            canonical_fingerprint=compute_fingerprint(
                workspace_id=decision.workspace_id,
                agent_id=decision.agent_id,
                tool=tool,
                operation=operation,
                permission_required=decision.permission_required,
                objective=decision.objective,
                arguments=parsed_arguments,
            ),
            idempotency_key=compute_idempotency_key(
                workspace_id=decision.workspace_id,
                tool=tool,
                operation=operation,
                idempotency_scope=str(decision.id),
            ),
            version=1,
        )
        self.db.add(action_record)
        await self.db.flush()

        # 5. Autorisation puis exécution fiable. Aucun effet sans autorisation :
        #    DENY/ESCALATE/STOP n'atteignent jamais ce bloc (INV-01).
        execution_effect = None
        execution_attempt_id = None
        execution_error = None
        execution_output = None
        if decision.control_outcome == ControlOutcome.ALLOW:
            outcome = None
            try:
                authorization = await issue_authorization(
                    self.db, decision=decision, action=action_record, actor="orchestrator"
                )
                outcome = await dispatch_authorized_action(
                    self.db,
                    action=action_record,
                    authorization_id=authorization.id,
                    actor="orchestrator",
                    lease_owner=f"orchestrator:{request.agent_id}",
                    caller_workspace_id=decision.workspace_id,
                )
                execution_effect = outcome.effect.value
                execution_attempt_id = str(outcome.attempt_id)
                execution_output = outcome.output
            except AuthorizationError as exc:
                # Refus contrôlé avant tout effet (handler absent, autorisation
                # expirée/révoquée, empreinte changée) : rien n'a été engagé.
                execution_effect = EffectCertainty.none.value
                execution_error = f"{exc.code}: {exc.message}"

            outcome_row = DecisionOutcome(
                decision_id=decision.id,
                result_summary=(execution_error or (outcome.output or "confirmed"))[:500],
                success=(
                    None
                    if execution_effect == EffectCertainty.unknown.value
                    else (bool(outcome.success) if outcome is not None else False)
                ),
            )
            self.db.add(outcome_row)

        # Extract attributes BEFORE any commit to avoid MissingGreenlet on expired objects
        d_id = str(decision.id)
        d_dominant_source = decision.dominant_source or DominantSource.cognitive
        d_final_action = decision.final_action or request.proposed_action
        d_control_outcome = decision.control_outcome
        d_risk_level = decision.risk_level
        d_approval_required = decision.approval_required
        d_control_reason = decision.control_reason
        d_permission_granted = decision.permission_granted

        if decision.control_outcome == ControlOutcome.ALLOW:
            await self.db.commit()
        elif decision.control_outcome == ControlOutcome.ESCALATE:
            await self.db.commit()
            await notify_escalation(decision=decision, action_record=action_record)

        return DecisionResponse(
            decision_id=d_id,
            dominant_source=d_dominant_source,
            final_action=d_final_action,
            risk_level=d_risk_level,
            approval_required=d_approval_required,
            control_outcome=d_control_outcome,
            control_reason=d_control_reason,
            permission_granted=d_permission_granted,
            execution_effect=execution_effect,
            execution_attempt_id=execution_attempt_id,
            execution_error=execution_error,
            execution_output=execution_output,
        )
