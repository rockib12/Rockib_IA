"""`Swarm` — orchestration d'un essaim d'agents gouvernés à partir d'un objectif.

Le plan (liste d'étapes) peut être :
- fourni explicitement (`plan=[Step(...)]`),
- produit par un planificateur (`planner=callable` ou `LLMPlanner`),
- ou déduit par correspondance lexicale pour les compétences sans argument requis.
Quel que soit le planificateur, CHAQUE étape repasse par l'arbitre déterministe.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union

from .agent import GovernedAgent
from .audit import AuditTrail
from .models import ActionResult, Outcome


@dataclass
class Step:
    agent: str
    skill: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SwarmReport:
    objective: str
    steps: List[Step]
    results: List[ActionResult]

    @property
    def success(self) -> bool:
        return bool(self.results) and all(r.success for r in self.results)

    def summary(self) -> str:
        lines = [f"Objectif : {self.objective}"]
        for r in self.results:
            status = "✓" if r.success else "✗"
            lines.append(
                f"  {status} [{r.outcome.value}] {r.proposal.agent_name}.{r.proposal.skill_name}"
                + (f" → {r.output}" if r.success else f" ({r.error})")
            )
        return "\n".join(lines)


Planner = Callable[[str, Sequence[GovernedAgent]], Union[List[Step], Awaitable[List[Step]]]]

_TOKEN = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)


def _tokens(text: str) -> set:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) > 2}


def keyword_planner(objective: str, agents: Sequence[GovernedAgent]) -> List[Step]:
    """Sélectionne la meilleure compétence sans argument obligatoire par recouvrement lexical."""
    obj = _tokens(objective)
    best: Optional[Step] = None
    best_score = 0
    for ag in agents:
        for sk in ag.skills.values():
            required = [
                p for p in inspect.signature(sk.func).parameters.values()
                if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            ]
            if required:
                continue
            vocab = _tokens(" ".join([sk.name.replace("_", " "), sk.description, " ".join(sk.keywords), sk.domain]))
            score = len(obj & vocab)
            if score > best_score:
                best, best_score = Step(ag.name, sk.name), score
    return [best] if best else []


class LLMPlanner:
    """Planificateur via une API compatible OpenAI (Groq par défaut). Optionnel.

    Le LLM ne fait que PROPOSER des étapes ; il ne contourne jamais l'arbitre.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _catalog(self, agents: Sequence[GovernedAgent]) -> str:
        rows = []
        for ag in agents:
            for sk in ag.skills.values():
                params = list(inspect.signature(sk.func).parameters)
                rows.append(f"- agent={ag.name} skill={sk.name} params={params} : {sk.description}")
        return "\n".join(rows)

    def _call(self, objective: str, agents: Sequence[GovernedAgent]) -> List[Step]:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY manquant pour LLMPlanner")
        prompt = (
            "Tu es le planificateur d'un essaim d'agents. Réponds UNIQUEMENT en JSON : "
            '{"steps":[{"agent":"...","skill":"...","arguments":{...}}]}. '
            f"Compétences disponibles :\n{self._catalog(agents)}\n\nObjectif : {objective}"
        )
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"]
        data = json.loads(content)
        return [Step(s["agent"], s["skill"], s.get("arguments") or {}) for s in data.get("steps", [])]

    async def __call__(self, objective: str, agents: Sequence[GovernedAgent]) -> List[Step]:
        return await asyncio.to_thread(self._call, objective, agents)


class Swarm:
    def __init__(
        self,
        agents: Sequence[GovernedAgent],
        planner: Optional[Planner] = None,
        audit: Optional[AuditTrail] = None,
        stop_on_failure: bool = True,
    ) -> None:
        if not agents:
            raise ValueError("Un essaim nécessite au moins un agent")
        self.agents: Dict[str, GovernedAgent] = {}
        for ag in agents:
            self._register(ag)
        self.planner = planner or keyword_planner
        self.audit = audit or agents[0].audit
        self.stop_on_failure = stop_on_failure

    def _register(self, ag: GovernedAgent) -> None:
        self.agents[ag.name] = ag
        for child in ag.children:
            self._register(child)

    async def plan(self, objective: str) -> List[Step]:
        steps = self.planner(objective, list(self.agents.values()))
        if asyncio.iscoroutine(steps) or isinstance(steps, Awaitable):
            steps = await steps  # type: ignore[misc]
        return list(steps)

    async def run(self, objective: str, plan: Optional[List[Step]] = None) -> SwarmReport:
        steps = plan if plan is not None else await self.plan(objective)
        self.audit.record("swarm.started", objective=objective, steps=[s.__dict__ for s in steps])
        results: List[ActionResult] = []
        for step in steps:
            agent = self.agents.get(step.agent)
            if agent is None:
                self.audit.record("swarm.invalid_step", step=step.__dict__, reason="agent inconnu")
                break
            result = await agent.execute(step.skill, **step.arguments)
            results.append(result)
            if self.stop_on_failure and (not result.success or result.outcome == Outcome.DENY):
                break
        report = SwarmReport(objective, steps, results)
        self.audit.record("swarm.finished", objective=objective, success=report.success)
        return report

    def run_sync(self, objective: str, plan: Optional[List[Step]] = None) -> SwarmReport:
        return asyncio.run(self.run(objective, plan=plan))
