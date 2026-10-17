"""URLs signées HMAC pour la prévisualisation des fichiers de workspace (STEP 6H).

Les liens /preview/ sont ouverts dans un nouvel onglet : le navigateur n'y joint
pas le header Authorization. Ils portent donc une signature à durée limitée,
liée cryptographiquement au couple (workspace_id, chemin). La signature est
calculée À LA LECTURE (réponse authentifiée), jamais stockée en base.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
import uuid
from urllib.parse import quote

from app.core.config import settings

PREVIEW_TTL_SECONDS = 3600
_DOMAIN = b"rockib.preview.v1"

# /api/v1/workspaces/<uuid>/preview/<chemin sans espace, quote, parenthèse ni '?'>
_PREVIEW_LINK_RE = re.compile(
    r"/api/v1/workspaces/(?P<ws>[0-9a-fA-F-]{36})/preview/(?P<path>[^\s\"'<>()?#]+)"
)


def _key() -> bytes:
    # Clé dérivée : séparation de domaine vis-à-vis de la signature JWT.
    return hmac.new(settings.JWT_SECRET_KEY.encode(), _DOMAIN, hashlib.sha256).digest()


def _normalize_path(path: str) -> str:
    return path.lstrip("/")


def _mac(workspace_id: uuid.UUID | str, path: str, exp: int) -> str:
    msg = f"{str(workspace_id).lower()}\n{_normalize_path(path)}\n{exp}".encode()
    return hmac.new(_key(), msg, hashlib.sha256).hexdigest()


def sign_preview(workspace_id: uuid.UUID | str, path: str, ttl: int = PREVIEW_TTL_SECONDS) -> tuple[int, str]:
    exp = int(time.time()) + ttl
    return exp, _mac(workspace_id, path, exp)


def verify_preview(workspace_id: uuid.UUID | str, path: str, exp: int | None, sig: str | None) -> bool:
    if exp is None or not sig:
        return False
    if int(exp) < int(time.time()):
        return False
    return hmac.compare_digest(_mac(workspace_id, path, int(exp)), sig)


def sign_preview_links(text: str | None) -> str | None:
    """Ajoute ?exp=&sig= à chaque lien /preview/ présent dans un texte."""
    if not text:
        return text

    def _sub(m: re.Match) -> str:
        ws, path = m.group("ws"), m.group("path")
        exp, sig = sign_preview(ws, path)
        return f"{m.group(0)}?exp={exp}&sig={quote(sig)}"

    return _PREVIEW_LINK_RE.sub(_sub, text)
