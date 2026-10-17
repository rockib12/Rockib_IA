import uuid
import pytest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.connectors.fs_connector import fs_write_handler
from app.execution.models import ActionRecord


@pytest.mark.asyncio
async def test_fs_write_handler_success(tmp_path):
    workspace_id = uuid.uuid4()
    with patch.object(settings, "WORKSPACES_ROOT", str(tmp_path)):
        # Re-initialize WORKSPACES_ROOT in module if needed
        import app.connectors.fs_connector as fs_mod
        orig_root = fs_mod.WORKSPACES_ROOT
        fs_mod.WORKSPACES_ROOT = tmp_path

        try:
            action = MagicMock(spec=ActionRecord)
            action.workspace_id = workspace_id
            action.objective = "Créer une page d'accueil moderne"
            action.arguments = {
                "path": "index.html",
                "content": "<html><body><h1>Rockib AI</h1></body></html>"
            }

            res = await fs_write_handler(action)

            assert res.success is True
            assert res.error is None
            assert res.cost_amount == Decimal("0.0")
            assert res.cost_unit == "credits"
            assert "index.html" in res.output
            assert "/preview/index.html" in res.output

            target_file = tmp_path / str(workspace_id) / "index.html"
            assert target_file.exists()
            assert target_file.read_text(encoding="utf-8") == "<html><body><h1>Rockib AI</h1></body></html>"
        finally:
            fs_mod.WORKSPACES_ROOT = orig_root


@pytest.mark.asyncio
async def test_fs_write_handler_path_traversal(tmp_path):
    workspace_id = uuid.uuid4()
    import app.connectors.fs_connector as fs_mod
    orig_root = fs_mod.WORKSPACES_ROOT
    fs_mod.WORKSPACES_ROOT = tmp_path

    try:
        action = MagicMock(spec=ActionRecord)
        action.workspace_id = workspace_id
        action.objective = "Piratage"
        action.arguments = {
            "path": "../../../secret.txt",
            "content": "interdit"
        }

        res = await fs_write_handler(action)
        assert res.success is False
        assert res.error_code == "PATH_TRAVERSAL"
    finally:
        fs_mod.WORKSPACES_ROOT = orig_root


@pytest.mark.asyncio
async def test_fs_write_handler_missing_workspace():
    action = MagicMock(spec=ActionRecord)
    action.workspace_id = None
    action.arguments = {"path": "test.txt", "content": "hello"}

    res = await fs_write_handler(action)
    assert res.success is False
    assert res.error_code == "MISSING_WORKSPACE"


@pytest.mark.asyncio
async def test_fs_write_handler_auto_code_generation(tmp_path):
    workspace_id = uuid.uuid4()
    import app.connectors.fs_connector as fs_mod
    orig_root = fs_mod.WORKSPACES_ROOT
    fs_mod.WORKSPACES_ROOT = tmp_path

    try:
        action = MagicMock(spec=ActionRecord)
        action.workspace_id = workspace_id
        action.objective = "Créer un site vitrine pour une startup IA"
        action.arguments = {"path": "index.html"}  # No content supplied

        res = await fs_write_handler(action)
        assert res.success is True
        assert res.error is None
        
        target_file = tmp_path / str(workspace_id) / "index.html"
        assert target_file.exists()
        content = target_file.read_text(encoding="utf-8")
        assert len(content) > 100
        assert "<!DOCTYPE html>" in content or "<html" in content
    finally:
        fs_mod.WORKSPACES_ROOT = orig_root
