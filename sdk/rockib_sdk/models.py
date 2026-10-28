"""Types fondamentaux du SDK Rockib (énumérations, propositions, décisions, résultats)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Permission(str, Enum):
    """Aligné sur `PermissionAction` du moteur Rockib IA."""

    READ = "READ"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SEND = "SEND"
    PUBLISH = "PUBLISH"
    SPEND = "SPEND"


class Outcome(str, Enum):
    ALLOW = "ALLOW"
    ESCALATE = "ESCALATE"
    DENY = "DENY"


@dataclass(frozen=True)
class ActionProposal:
    """Action proposée par un agent, soumise à l'arbitrage AVANT toute exécution."""

    agent_name: str
    skill_name: str
    domain: str
    permission: Permission
    risk: RiskLevel
    reversible: bool
    requested_autonomy: int
    allowed_autonomy: int
    amount: Optional[Decimal] = None
    currency: str = "EUR"
    arguments: Dict[str, Any] = field(default_factory=dict)
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    applied_autonomy: int
    reasons: List[str]
    approval_required: bool
    error_code: Optional[str] = None


@dataclass
class ActionResult:
    proposal: ActionProposal
    decision: Decision
    executed: bool
    success: bool
    output: Any = None
    error: Optional[str] = None
    approved_by: Optional[str] = None
    finished_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def outcome(self) -> Outcome:
        return self.decision.outcome
