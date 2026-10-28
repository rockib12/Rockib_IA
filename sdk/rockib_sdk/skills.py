"""Compétences scellées SHA-256 (`@skill`).

Chaque compétence est normalisée canoniquement (métadonnées + code source) puis
scellée par un condensat `sha256:...`. Toute altération ultérieure est détectée
par `Skill.verify()` avant exécution (équivalent de `SKILL-INV-08` côté serveur).
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from .errors import SkillIntegrityError
from .models import Permission, RiskLevel


def _source_of(func: Callable[..., Any]) -> str:
    try:
        return textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        # Fonctions définies dynamiquement : on scelle le bytecode
        code = getattr(func, "__code__", None)
        return code.co_code.hex() if code else repr(func)


@dataclass
class Skill:
    name: str
    func: Callable[..., Any]
    domain: str = "general"
    permission: Permission = Permission.READ
    risk: RiskLevel = RiskLevel.LOW
    reversible: bool = True
    description: str = ""
    version: str = "1.0.0"
    spend_arg: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    source: str = ""
    content_hash: str = ""

    def canonical_payload(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "domain": self.domain,
            "permission": self.permission.value,
            "risk": self.risk.value,
            "reversible": self.reversible,
            "description": self.description.strip(),
            "spend_arg": self.spend_arg,
            "keywords": sorted(k.lower() for k in self.keywords),
            "source": self.source,
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def compute_hash(self) -> str:
        digest = hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def seal(self) -> "Skill":
        self.content_hash = self.compute_hash()
        return self

    def verify(self) -> None:
        """Lève `SkillIntegrityError` si la compétence a été modifiée après scellement."""
        current_source = _source_of(self.func)
        if current_source != self.source or self.compute_hash() != self.content_hash:
            raise SkillIntegrityError(
                f"Compétence '{self.name}' altérée : condensat attendu {self.content_hash}"
            )

    async def invoke(self, **kwargs: Any) -> Any:
        result = self.func(**kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "permission": self.permission.value,
            "risk": self.risk.value,
            "reversible": self.reversible,
            "version": self.version,
            "content_hash": self.content_hash,
        }


def skill(
    _func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    domain: str = "general",
    permission: Union[Permission, str] = Permission.READ,
    risk: Union[RiskLevel, str] = RiskLevel.LOW,
    reversible: bool = True,
    description: Optional[str] = None,
    version: str = "1.0.0",
    spend_arg: Optional[str] = None,
    keywords: Optional[List[str]] = None,
) -> Any:
    """Décorateur transformant une fonction (sync ou async) en `Skill` scellée.

    Exemple :
        @skill(domain="finance", permission="SPEND", risk="HIGH",
               reversible=False, spend_arg="montant_eur")
        def virement(montant_eur: int, iban: str) -> str: ...
    """

    def decorator(func: Callable[..., Any]) -> Skill:
        sk = Skill(
            name=name or func.__name__,
            func=func,
            domain=domain,
            permission=Permission(permission),
            risk=RiskLevel(risk),
            reversible=reversible,
            description=(description or inspect.getdoc(func) or "").strip(),
            version=version,
            spend_arg=spend_arg,
            keywords=list(keywords or []),
            source=_source_of(func),
        )
        if spend_arg and sk.permission != Permission.SPEND:
            sk.permission = Permission.SPEND
        return sk.seal()

    if _func is not None:
        return decorator(_func)
    return decorator
