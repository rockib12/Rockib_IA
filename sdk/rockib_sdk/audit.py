"""Journal d'audit infalsifiable (chaîne de hachage SHA-256, format JSONL)."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .errors import AuditIntegrityError

GENESIS = "sha256:" + "0" * 64


def _default(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return asdict(obj)
    return str(obj)


def _hash_entry(entry: Dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=_default, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuditTrail:
    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.path = Path(path) if path else None
        self.entries: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self.entries = load_entries(self.path)

    @property
    def last_hash(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def record(self, event: str, **data: Any) -> Dict[str, Any]:
        with self._lock:
            entry: Dict[str, Any] = {
                "seq": len(self.entries) + 1,
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "data": json.loads(json.dumps(data, default=_default, ensure_ascii=False)),
                "prev_hash": self.last_hash,
            }
            entry["hash"] = _hash_entry(entry)
            self.entries.append(entry)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return entry

    def verify(self) -> int:
        return verify_entries(self.entries)


def load_entries(path: Union[str, Path]) -> List[Dict[str, Any]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def verify_entries(entries: List[Dict[str, Any]]) -> int:
    """Retourne le nombre d'entrées valides ; lève `AuditIntegrityError` sinon."""
    prev = GENESIS
    for idx, entry in enumerate(entries, start=1):
        if entry.get("prev_hash") != prev:
            raise AuditIntegrityError(f"Chaîne rompue à l'entrée #{idx}")
        if _hash_entry(entry) != entry.get("hash"):
            raise AuditIntegrityError(f"Entrée #{idx} altérée")
        prev = entry["hash"]
    return len(entries)
