"""Client HTTP minimal (stdlib) vers un serveur Rockib IA (Cockpit 3D, Goal Engine, Sandbox, Devis P8)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .errors import RockibError


class RockibClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: float = 20.0) -> None:
        self.base_url = (base_url or os.getenv("ROCKIB_URL", "http://127.0.0.1")).rstrip("/")
        self.token = token or os.getenv("ROCKIB_TOKEN")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, form: bool = False) -> Any:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            if form:
                data = urllib.parse.urlencode(body).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RockibError(f"HTTP {exc.code} sur {path} : {detail}") from exc
        except urllib.error.URLError as exc:
            raise RockibError(f"Serveur Rockib injoignable ({self.base_url}) : {exc.reason}") from exc

    # ── Authentification ──
    def login(self, email: str, password: str) -> str:
        data = self._request("POST", "/api/v1/auth/login", {"email": email, "password": password})
        self.token = data["access_token"]
        return self.token

    # ── Endpoints ──
    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/health")

    def list_agents(self, active_only: bool = True) -> List[Dict[str, Any]]:
        return self._request("GET", f"/api/v1/agents?active_only={'true' if active_only else 'false'}")

    def create_goal(self, workspace_id: str, agent_id: str, objective: str, autonomy: int = 2,
                    tasks: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/goals", {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "objective": objective,
            "requested_autonomy_level": autonomy,
            "initial_tasks": tasks or [],
        })

    def auto_swarm(self, goal_id: str, max_sub_agents: int = 3) -> Dict[str, Any]:
        return self._request("POST", f"/api/v1/goals/{goal_id}/auto-swarm", {"max_sub_agents": max_sub_agents})

    def sandbox_run(self, workspace_id: str, code: str, test_code: str = "", timeout_seconds: float = 5.0) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/execution/sandbox/run", {
            "workspace_id": workspace_id,
            "code": code,
            "test_code": test_code,
            "language": "python",
            "timeout_seconds": timeout_seconds,
        })

    def generate_proposal(self, client_name: str, brief: str, company_name: Optional[str] = None) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/inbound/proposal/generate", {
            "client_name": client_name,
            "company_name": company_name,
            "project_brief": brief,
        })
