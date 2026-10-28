"""Grand livre budgétaire hiérarchique (réservation → consommation / libération).

Invariants :
- Montants en `Decimal` / `int` uniquement (les `float` sont rejetés).
- Le plafond d'un enfant est strictement borné par le restant de son parent.
- Toute consommation enfant est répercutée sur toute la chaîne d'ancêtres.
"""
from __future__ import annotations

import threading
from decimal import Decimal
from typing import Optional, Union

from .errors import BudgetViolationError

Number = Union[int, str, Decimal]


def to_decimal(value: Number) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise BudgetViolationError("Les montants float sont interdits (utilisez int, str ou Decimal)")
    try:
        dec = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise BudgetViolationError(f"Montant invalide : {value!r}") from exc
    if dec < 0:
        raise BudgetViolationError("Montant négatif interdit")
    return dec


class BudgetLedger:
    def __init__(self, ceiling: Optional[Number] = None, parent: Optional["BudgetLedger"] = None) -> None:
        self._lock = threading.RLock()
        self.parent = parent
        self.ceiling: Optional[Decimal] = to_decimal(ceiling) if ceiling is not None else None
        self.spent = Decimal("0")
        self.held = Decimal("0")
        if parent is not None:
            parent_remaining = parent.remaining()
            if parent_remaining is not None:
                if self.ceiling is None or self.ceiling > parent_remaining:
                    if self.ceiling is not None:
                        raise BudgetViolationError(
                            f"Plafond enfant {self.ceiling} > restant parent {parent_remaining}"
                        )
                    self.ceiling = parent_remaining

    def remaining(self) -> Optional[Decimal]:
        with self._lock:
            own = None if self.ceiling is None else self.ceiling - self.spent - self.held
            if self.parent is not None:
                parent_rem = self.parent.remaining()
                if parent_rem is not None:
                    own = parent_rem if own is None else min(own, parent_rem)
            return own

    def hold(self, amount: Decimal) -> None:
        with self._lock:
            rem = self.remaining()
            if rem is not None and amount > rem:
                raise BudgetViolationError(f"QUOTA_EXCEEDED : {amount} > {rem}")
            self.held += amount
            if self.parent is not None:
                self.parent.hold(amount)

    def commit(self, amount: Decimal) -> None:
        with self._lock:
            self.held -= amount
            self.spent += amount
            if self.parent is not None:
                self.parent.commit(amount)

    def release(self, amount: Decimal) -> None:
        with self._lock:
            self.held -= amount
            if self.parent is not None:
                self.parent.release(amount)
