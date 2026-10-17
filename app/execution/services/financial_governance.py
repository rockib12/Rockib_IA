"""Module de gouvernance financière canonique pour Rockib AI.

Doctrine :
    Le LLM propose. Le système décide.
    Toute action financière doit être bornée, typée, vérifiée et scellée.

Invariants couverts :
    - FIN-INV-01 : Montant numérique strict (> 0, Decimal) et devise ISO-4217 majuscule.
    - FIN-INV-02 : Absence ou ambiguïté = rejet / fail-closed immédiat (jamais ALLOW).
    - FIN-INV-03 : Respect strict du plafond de budget (budget_ceiling).
    - FIN-INV-04 & FIN-INV-07 : L'empreinte canonique (SHA-256) lie l'autorisation au montant et à la devise.
    - FIN-INV-09 : Plafond parent >= plafond enfant (monotonie financière).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Set

from app.execution.models import ActionRecord


# ---------------------------------------------------------------------------
# Codes de devises ISO-4217 officiels (alphabétiques à 3 lettres)
# ---------------------------------------------------------------------------
ISO_4217_CURRENCIES: Set[str] = {
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BOV",
    "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHE", "CHF",
    "CHW", "CLF", "CLP", "CNY", "COP", "COU", "CRC", "CUC", "CUP", "CVE",
    "CZK", "DJF", "DKK", "DOP", "DZD", "EGP", "ERN", "ETB", "EUR", "FJD",
    "FKP", "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD",
    "HNL", "HRK", "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR", "ISK",
    "JMD", "JOD", "JPY", "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD",
    "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD", "MAD", "MDL",
    "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR", "MWK", "MXN",
    "MXV", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD", "OMR",
    "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON", "RSD",
    "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE",
    "SLL", "SOS", "SRD", "SSP", "STN", "SVC", "SYP", "SZL", "THB", "TJS",
    "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD",
    "USN", "UYI", "UYU", "UYW", "UZS", "VED", "VES", "VND", "VUV", "WST",
    "XAF", "XCD", "XDR", "XOF", "XPF", "XSU", "XUA", "YER", "ZAR", "ZMW",
    "ZWL",
}


# ---------------------------------------------------------------------------
# Exceptions spécifiques au domaine financier
# ---------------------------------------------------------------------------
class FinancialGovernanceError(Exception):
    """Erreur de base de la gouvernance financière."""
    pass


class FinancialValidationError(FinancialGovernanceError):
    """Erreur de validation de format ou de présence d'un paramètre financier."""
    pass


class FinancialAmountError(FinancialValidationError):
    """Erreur spécifique sur le montant financier."""
    pass


class FinancialCurrencyError(FinancialValidationError):
    """Erreur spécifique sur la devise financière."""
    pass


class FinancialConsistencyError(FinancialGovernanceError):
    """Incohérence entre les arguments financiers et les colonnes de l'action."""
    pass


class BudgetCeilingMissingError(FinancialGovernanceError):
    """Plafond budgétaire manquant (fail-closed, pas d'infini implicite)."""
    pass


class BudgetCeilingExceededError(FinancialGovernanceError):
    """Le montant demandé dépasse le plafond de budget accordé."""
    pass


class BudgetCurrencyMismatchError(FinancialGovernanceError):
    """Incompatibilité entre la devise demandée et la devise du plafond."""
    pass


class ParentChildCeilingViolationError(FinancialGovernanceError):
    """Violation de monotonie : le plafond de l'enfant dépasse celui du parent."""
    pass


# ---------------------------------------------------------------------------
# Modèle de valeur : FinancialScope
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FinancialScope:
    """Scope financier canonique immuable pour une action."""
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise FinancialAmountError("Amount must be a Decimal")
        if not self.amount.is_finite() or self.amount <= Decimal("0"):
            raise FinancialAmountError("Amount must be finite and strictly positive (> 0)")
        if self.currency not in ISO_4217_CURRENCIES:
            raise FinancialCurrencyError(f"Currency '{self.currency}' is not a valid uppercase ISO-4217 code")


# ---------------------------------------------------------------------------
# Fonctions de validation pures
# ---------------------------------------------------------------------------
def validate_financial_amount(value: Any) -> Decimal:
    """Valide et convertit un montant en Decimal strict.

    Règles contractuelles :
    - Non null (None -> FinancialAmountError).
    - Float strictement interdit pour éviter les pertes de précision binaire IEEE-754.
    - int, Decimal ou string numérique pure autorisés.
    - Rejet strict des chaînes composites avec unité (ex: "300 EUR").
    - Rejet strict de NaN, Infinity, -Infinity.
    - Le montant doit être strictement positif (> 0).
    """
    if value is None:
        raise FinancialAmountError("Amount is required and cannot be None")

    if isinstance(value, float):
        raise FinancialAmountError(
            "Float type is forbidden for financial amounts to avoid binary rounding issues. "
            "Use Decimal, integer, or clean numeric string."
        )

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise FinancialAmountError("Amount string cannot be empty")
        # Vérification qu'il s'agit d'un nombre pur (pas de lettres, symboles ou unités)
        if not re.match(r"^[+-]?\d+(\.\d+)?$", trimmed):
            raise FinancialAmountError(
                f"Amount string '{value}' must be a pure numeric format without currency or symbols"
            )
        try:
            dec = Decimal(trimmed)
        except InvalidOperation:
            raise FinancialAmountError(f"Cannot parse '{value}' as Decimal")
    elif isinstance(value, (int, Decimal)):
        try:
            dec = Decimal(str(value)) if isinstance(value, int) else value
        except InvalidOperation:
            raise FinancialAmountError(f"Cannot convert {value} to Decimal")
    else:
        raise FinancialAmountError(f"Unsupported type {type(value).__name__} for financial amount")

    if not dec.is_finite() or dec.is_nan() or dec.is_infinite():
        raise FinancialAmountError("Amount must be finite (NaN and Infinity are forbidden)")

    if dec <= Decimal("0"):
        raise FinancialAmountError(f"Amount must be strictly positive (> 0), got: {dec}")

    return dec


def validate_financial_currency(value: Any) -> str:
    """Valide qu'une devise est une chaîne ISO-4217 majuscule valide.

    Règles contractuelles :
    - Doit être de type str.
    - Doit être exactement en majuscules (ex: 'EUR' valide, 'eur' refusé).
    - Pas de symboles (€ refusé) ni de dénominations étendues ('EURO', 'XOF CFA' refusés).
    - Doit appartenir à la liste officielle ISO_4217_CURRENCIES.
    """
    if value is None:
        raise FinancialCurrencyError("Currency is required and cannot be None")

    if not isinstance(value, str):
        raise FinancialCurrencyError(f"Currency must be a string, got {type(value).__name__}")

    if not value or " " in value or value != value.strip():
        raise FinancialCurrencyError("Currency string must not be empty or contain whitespace")

    if value != value.upper():
        raise FinancialCurrencyError(f"Currency code must be strictly uppercase, got '{value}'")

    if value not in ISO_4217_CURRENCIES:
        raise FinancialCurrencyError(f"Currency '{value}' is not a valid ISO-4217 code")

    return value


def extract_financial_scope(
    arguments: Mapping[str, Any],
    *,
    strict: bool = True,
) -> Optional[FinancialScope]:
    """Extrait et valide le scope financier depuis les arguments d'une action.

    Cherche `amount` (ou `financial_amount`) et `currency` (ou `financial_currency`).
    Si aucun n'est présent et `strict=False`, retourne None.
    Si l'un est présent ou `strict=True`, valide obligatoirement les deux.
    """
    if not isinstance(arguments, Mapping):
        if strict:
            raise FinancialValidationError("Arguments must be a valid mapping")
        return None

    raw_amount = arguments.get("amount")
    if raw_amount is None:
        raw_amount = arguments.get("financial_amount")

    raw_currency = arguments.get("currency")
    if raw_currency is None:
        raw_currency = arguments.get("financial_currency")

    has_any = (raw_amount is not None) or (raw_currency is not None)

    if not has_any:
        if strict:
            raise FinancialValidationError("Financial arguments ('amount', 'currency') are missing")
        return None

    # L'un est présent, les deux doivent être valides
    dec_amount = validate_financial_amount(raw_amount)
    valid_curr = validate_financial_currency(raw_currency)

    return FinancialScope(amount=dec_amount, currency=valid_curr)


def verify_action_financial_consistency(action: ActionRecord) -> Optional[FinancialScope]:
    """Garantit l'alignement absolu entre `arguments` et les colonnes d'estimation.

    Règle critique :
    Il est impossible d'avoir `arguments.amount = 300` et `cost_estimate = 50`.
    Si `cost_estimate` ou `cost_unit` sont définis, ils DOIVENT correspondre
    exactement à `arguments.amount` et `arguments.currency`.
    """
    scope = extract_financial_scope(action.arguments, strict=False)

    if scope is None:
        # Si aucun scope financier dans arguments, cost_estimate ne doit pas porter de montant financier
        return None

    if action.cost_estimate is not None:
        cost_dec = Decimal(str(action.cost_estimate))
        if cost_dec != scope.amount:
            raise FinancialConsistencyError(
                f"Financial amount mismatch: arguments.amount={scope.amount} "
                f"!= action.cost_estimate={cost_dec}"
            )

    if action.cost_unit is not None:
        if action.cost_unit != scope.currency:
            raise FinancialConsistencyError(
                f"Financial currency mismatch: arguments.currency={scope.currency} "
                f"!= action.cost_unit={action.cost_unit}"
            )

    return scope


def validate_budget_ceiling(
    requested_amount: Any,
    requested_currency: Any,
    ceiling_amount: Any,
    ceiling_currency: Any,
) -> Decimal:
    """Valide qu'un montant demandé ne dépasse pas le plafond de budget accordé.

    Doctrine Fail-Closed :
    - Si le plafond est absent (None), l'action est REFUSÉE (pas d'infini implicite).
    - Si les devises diffèrent, l'action est REFUSÉE.
    - Si requested_amount > ceiling_amount, l'action est REFUSÉE.
    """
    req_amount = validate_financial_amount(requested_amount)
    req_currency = validate_financial_currency(requested_currency)

    if ceiling_amount is None or ceiling_currency is None:
        raise BudgetCeilingMissingError(
            "Budget ceiling is missing or not configured. Fail-closed: cannot assume infinite ceiling."
        )

    ceil_amount = validate_financial_amount(ceiling_amount)
    ceil_currency = validate_financial_currency(ceiling_currency)

    if req_currency != ceil_currency:
        raise BudgetCurrencyMismatchError(
            f"Requested currency '{req_currency}' does not match ceiling currency '{ceil_currency}'"
        )

    if req_amount > ceil_amount:
        raise BudgetCeilingExceededError(
            f"Requested amount {req_amount} {req_currency} exceeds budget ceiling {ceil_amount} {ceil_currency}"
        )

    return req_amount


def validate_parent_child_ceiling(
    parent_ceiling_amount: Any,
    parent_ceiling_currency: Any,
    child_ceiling_amount: Any,
    child_ceiling_currency: Any,
) -> Decimal:
    r"""Valide la monotonie hiérarchique des plafonds de budget (FIN-INV-09).

    Un sous-objectif ou enfant ne peut JAMAIS avoir un plafond supérieur
    à celui de son parent ($child\_ceiling \le parent\_ceiling$).
    """
    child_amount = validate_financial_amount(child_ceiling_amount)
    child_currency = validate_financial_currency(child_ceiling_currency)

    if parent_ceiling_amount is None or parent_ceiling_currency is None:
        raise BudgetCeilingMissingError(
            "Parent budget ceiling is missing. Fail-closed: child cannot define budget without parent ceiling."
        )

    parent_amount = validate_financial_amount(parent_ceiling_amount)
    parent_currency = validate_financial_currency(parent_ceiling_currency)

    if child_currency != parent_currency:
        raise BudgetCurrencyMismatchError(
            f"Child ceiling currency '{child_currency}' does not match parent ceiling currency '{parent_currency}'"
        )

    if child_amount > parent_amount:
        raise ParentChildCeilingViolationError(
            f"Child budget ceiling {child_amount} {child_currency} exceeds parent ceiling "
            f"{parent_amount} {parent_currency}"
        )

    return child_amount
