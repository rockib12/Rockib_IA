"""Tests unitaires du registry des handlers d'actions (STEP 5C.3).

Vérifie les garanties de l'API de registration :
- validation stricte des types et arguments
- rejet des fonctions synchrones
- idempotence sur le même handler
- protection contre les écrasements accidentels (doublons différents)
- remplacement explicite via replace=True
- réinitialisation via clear_action_handlers
"""
from __future__ import annotations

import pytest

from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult
from app.execution.services.reliable_executor import (
    clear_action_handlers,
    get_action_handler,
    register_action_handler,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Isole chaque test en vidant le registre avant et après l'exécution."""
    clear_action_handlers()
    yield
    clear_action_handlers()


async def _dummy_handler(action: ActionRecord) -> ExecutionResult:
    return ExecutionResult(success=True, output="dummy")


async def _other_handler(action: ActionRecord) -> ExecutionResult:
    return ExecutionResult(success=True, output="other")


def test_1_registration_and_lookup_success():
    """Test 1 — Enregistrement réussi et restitution du même handler."""
    register_action_handler("system", "read", _dummy_handler)
    resolved = get_action_handler("system", "read")
    assert resolved is _dummy_handler


def test_2_absent_handler_returns_none():
    """Test 2 — Requête d'un handler non enregistré retourne None."""
    assert get_action_handler("unknown_tool", "unknown_operation") is None


@pytest.mark.parametrize("empty_tool", ["", "   ", "\t\n"])
def test_3_reject_empty_tool(empty_tool: str):
    """Test 3 — Rejet d'un nom de tool vide ou blanc."""
    with pytest.raises(ValueError, match="tool must be a non-empty string"):
        register_action_handler(empty_tool, "read", _dummy_handler)


@pytest.mark.parametrize("empty_op", ["", "   ", "\t\n"])
def test_4_reject_empty_operation(empty_op: str):
    """Test 4 — Rejet d'un nom d'opération vide ou blanc."""
    with pytest.raises(ValueError, match="operation must be a non-empty string"):
        register_action_handler("system", empty_op, _dummy_handler)


@pytest.mark.parametrize("invalid_tool", [None, 123, [], {}, 1.5])
def test_5_reject_non_string_tool(invalid_tool):
    """Test 5 — Rejet d'un tool de type non-string."""
    with pytest.raises(TypeError, match="tool must be a str"):
        register_action_handler(invalid_tool, "read", _dummy_handler)


@pytest.mark.parametrize("invalid_op", [None, 123, [], {}, 1.5])
def test_6_reject_non_string_operation(invalid_op):
    """Test 6 — Rejet d'une operation de type non-string."""
    with pytest.raises(TypeError, match="operation must be a str"):
        register_action_handler("system", invalid_op, _dummy_handler)


@pytest.mark.parametrize("invalid_handler", [None, "not_callable", 123, [], object()])
def test_7_reject_non_callable_handler(invalid_handler):
    """Test 7 — Rejet d'un handler non-callable."""
    with pytest.raises(TypeError, match="handler must be callable"):
        register_action_handler("system", "read", invalid_handler)


def test_8_reject_synchronous_handler():
    """Test 8 — Rejet d'une fonction synchrone."""
    def sync_handler(action: ActionRecord) -> ExecutionResult:
        return ExecutionResult(success=True, output="sync")

    with pytest.raises(TypeError, match="handler must be an async coroutine function"):
        register_action_handler("system", "read", sync_handler)


def test_9_idempotent_registration_same_handler():
    """Test 9 — Idempotence stricte si le même handler exact est ré-enregistré."""
    register_action_handler("system", "read", _dummy_handler)
    # Deuxième enregistrement identique : aucun effet de bord, pas d'exception
    register_action_handler("system", "read", _dummy_handler)
    assert get_action_handler("system", "read") is _dummy_handler


def test_10_reject_duplicate_different_handler_without_replace():
    """Test 10 — Erreur déterministe lors de l'enregistrement d'un handler différent sans replace."""
    register_action_handler("system", "read", _dummy_handler)
    with pytest.raises(ValueError, match="Handler already registered for system.read"):
        register_action_handler("system", "read", _other_handler)
    # Le handler d'origine reste en place
    assert get_action_handler("system", "read") is _dummy_handler


def test_11_explicit_replace_succeeds():
    """Test 11 — Remplacement autorisé avec replace=True."""
    register_action_handler("system", "read", _dummy_handler)
    register_action_handler("system", "read", _other_handler, replace=True)
    assert get_action_handler("system", "read") is _other_handler


def test_12_clear_action_handlers():
    """Test 12 — clear_action_handlers réinitialise complètement le registre."""
    register_action_handler("system", "read", _dummy_handler)
    register_action_handler("filesystem", "write", _other_handler)
    assert get_action_handler("system", "read") is not None
    assert get_action_handler("filesystem", "write") is not None

    clear_action_handlers()

    assert get_action_handler("system", "read") is None
    assert get_action_handler("filesystem", "write") is None
