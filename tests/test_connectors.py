import pytest
import uuid
import os
import asyncio
from pathlib import Path

from app.execution.models import ActionRecord
from app.connectors.fs_connector import fs_read_handler, WORKSPACES_ROOT

@pytest.fixture
def workspace_dir(tmp_path):
    """Crée un dossier temporaire simulant un workspace."""
    ws_id = uuid.uuid4()
    ws_dir = tmp_path / str(ws_id)
    ws_dir.mkdir(parents=True, exist_ok=True)
    
    # Crée un fichier de test valide
    test_file = ws_dir / "secret.txt"
    test_file.write_text("Hello Rockib", encoding="utf-8")
    
    # Crée un fichier HORS du workspace pour tester le directory traversal
    out_file = tmp_path / "passwd"
    out_file.write_text("root:x:0:0", encoding="utf-8")
    
    return ws_id, ws_dir, out_file

@pytest.mark.asyncio
async def test_fs_read_valid_file(workspace_dir, monkeypatch):
    """Test la lecture d'un fichier valide."""
    ws_id, ws_dir, out_file = workspace_dir
    
    # On mock WORKSPACES_ROOT pour le test
    monkeypatch.setattr("app.connectors.fs_connector.WORKSPACES_ROOT", ws_dir.parent)
    
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=uuid.uuid4(),
        tool="fs",
        operation="read",
        arguments={"path": "secret.txt"}
    )
    
    result = await fs_read_handler(action)
    assert result.success is True
    assert result.output == "Hello Rockib"
    assert result.error is None

@pytest.mark.asyncio
async def test_fs_read_path_traversal_blocked(workspace_dir, monkeypatch):
    """Test la protection contre le path traversal."""
    ws_id, ws_dir, out_file = workspace_dir
    monkeypatch.setattr("app.connectors.fs_connector.WORKSPACES_ROOT", ws_dir.parent)
    
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=uuid.uuid4(),
        tool="fs",
        operation="read",
        arguments={"path": "../passwd"}
    )
    
    result = await fs_read_handler(action)
    assert result.success is False
    assert result.error_code == "PATH_TRAVERSAL"
    
@pytest.mark.asyncio
async def test_fs_read_file_not_found(workspace_dir, monkeypatch):
    """Test la lecture d'un fichier inexistant."""
    ws_id, ws_dir, out_file = workspace_dir
    monkeypatch.setattr("app.connectors.fs_connector.WORKSPACES_ROOT", ws_dir.parent)
    
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=uuid.uuid4(),
        tool="fs",
        operation="read",
        arguments={"path": "does_not_exist.txt"}
    )
    
    result = await fs_read_handler(action)
    assert result.success is False
    assert result.error_code == "FILE_NOT_FOUND"

@pytest.mark.asyncio
async def test_fs_read_missing_path(workspace_dir, monkeypatch):
    """Test l'erreur si l'argument path est manquant."""
    ws_id, ws_dir, out_file = workspace_dir
    monkeypatch.setattr("app.connectors.fs_connector.WORKSPACES_ROOT", ws_dir.parent)
    
    action = ActionRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        agent_id=uuid.uuid4(),
        tool="fs",
        operation="read",
        arguments={} # Aucun path
    )
    
    result = await fs_read_handler(action)
    assert result.success is False
    assert result.error_code == "MISSING_ARG_PATH"
