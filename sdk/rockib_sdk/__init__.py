"""Rockib SDK — Framework d'agents IA gouvernés, déterministes et auditables.

    from rockib_sdk import GovernedAgent, Swarm, skill

Chaque action d'agent passe par un arbitre déterministe (ALLOW / ESCALATE / DENY)
avant exécution, avec budget hiérarchique, compétences scellées SHA-256 et
journal d'audit chaîné.
"""
from .agent import GovernedAgent
from .approval import (
    ApprovalHandler,
    AutoApprove,
    CallableApproval,
    ConsoleApproval,
    DenyAll,
    TelegramNotifier,
)
from .arbitrator import DeterministicArbitrator, Policy
from .audit import AuditTrail, verify_entries
from .budget import BudgetLedger
from .client import RockibClient
from .errors import (
    AuditIntegrityError,
    AutonomyEscalationError,
    BudgetViolationError,
    RockibError,
    SkillIntegrityError,
    SkillNotGrantedError,
)
from .models import ActionProposal, ActionResult, Decision, Outcome, Permission, RiskLevel
from .skills import Skill, skill
from .swarm import LLMPlanner, Step, Swarm, SwarmReport, keyword_planner

__version__ = "0.1.0"

__all__ = [
    "GovernedAgent", "Swarm", "Step", "SwarmReport", "LLMPlanner", "keyword_planner",
    "skill", "Skill", "Policy", "DeterministicArbitrator", "BudgetLedger",
    "AuditTrail", "verify_entries", "RockibClient",
    "ApprovalHandler", "DenyAll", "AutoApprove", "ConsoleApproval", "CallableApproval", "TelegramNotifier",
    "ActionProposal", "ActionResult", "Decision", "Outcome", "Permission", "RiskLevel",
    "RockibError", "SkillIntegrityError", "SkillNotGrantedError", "AutonomyEscalationError",
    "BudgetViolationError", "AuditIntegrityError", "__version__",
]
