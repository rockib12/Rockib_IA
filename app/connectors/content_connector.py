"""Connecteur 'content.create' : rédaction de texte sans effet externe.

Périmètre strict :
- Génère un document texte (script, scénario, prompts, brief...) via le LLM.
- Écrit le résultat UNIQUEMENT dans le dossier sandbox du workspace
  (``WORKSPACES_ROOT/<workspace_id>/content/``).
- Aucun envoi, aucune publication, aucune dépense, aucun appel à une API payante
  autre que le LLM déjà utilisé par le moteur de décision.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.core.config import settings
from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 20_000

SYSTEM_PROMPT = (
    "Tu es un rédacteur professionnel au sein de Rockib AI. "
    "Tu produis uniquement le document demandé, en français, en Markdown, "
    "complet et directement exploitable. Tu n'inventes aucun fait sur l'utilisateur : "
    "si une information manque (noms de projets, chiffres), tu laisses un champ "
    "explicite à compléter entre crochets, par exemple [NOM DU PROJET]."
)


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "document"


def _get_provider():
    # Import local : évite de charger le client LLM tant que le handler n'est pas appelé.
    from app.intelligence.services.providers.groq_provider import GroqProvider

    return GroqProvider()


async def content_create_handler(action: ActionRecord) -> ExecutionResult:
    """Handler pour (content, create)."""
    if (action.tool or "").lower() != "content" or (action.operation or "").lower() != "create":
        return ExecutionResult(success=False, output=None, error="Invalid tool/operation", error_code="INVALID_TOOL")
    if action.workspace_id is None:
        return ExecutionResult(success=False, output=None, error="Missing workspace_id", error_code="MISSING_WORKSPACE")

    brief = ((action.arguments or {}).get("brief") or action.objective or "").strip()
    if not brief:
        return ExecutionResult(success=False, output=None, error="Empty brief", error_code="MISSING_BRIEF")

    try:
        text = await _get_provider().generate(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": brief},
            ],
            json_mode=False,
        )
    except Exception as exc:  # LLM indisponible : aucun effet produit
        logger.warning("content.create LLM failure: %s", exc)
        return ExecutionResult(success=False, output=None, error=str(exc)[:300], error_code="LLM_ERROR")

    text = (text or "").strip()[:MAX_OUTPUT_CHARS]
    if not text:
        return ExecutionResult(success=False, output=None, error="Empty LLM output", error_code="EMPTY_OUTPUT")

    workspace_dir = (Path(settings.WORKSPACES_ROOT).resolve() / str(action.workspace_id)).resolve()
    out_dir = (workspace_dir / "content").resolve()
    out_dir.relative_to(workspace_dir)  # garde-fou sandbox
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{stamp}-{_slugify(brief)}.md"

    def _write() -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    await asyncio.to_thread(_write)
    rel_path = target.relative_to(workspace_dir).as_posix()

    return ExecutionResult(
        success=True,
        output=f"[content:{rel_path}]\n{text}",
        error=None,
        error_code=None,
        provider_reference=f"content:{rel_path}",
        cost_amount=Decimal("0.0"),
        cost_unit="credits",
        effect_unknown=False,
    )
