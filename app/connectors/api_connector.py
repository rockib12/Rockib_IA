import httpx
import logging
from decimal import Decimal
from typing import Dict, Any

from app.core.network_security import (
    SSRFSecurityViolation,
    validate_url_for_ssrf,
    create_pinned_async_transport,
)
from app.execution.models import ActionRecord
from app.execution.services.executor import ExecutionResult

logger = logging.getLogger(__name__)

async def api_call_handler(action: ActionRecord) -> ExecutionResult:
    """Connecteur universel 'api.call' pour interagir avec des APIs externes."""
    args = action.arguments or {}
    url = args.get("url")
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body", None)
    
    if not url:
        return ExecutionResult(success=False, output=None, error="Missing 'url' argument")
    
    if method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
        return ExecutionResult(success=False, output=None, error=f"Unsupported method: {method}")

    # Contrôle de sécurité anti-SSRF (DNS préalable + IP privées + métadonnées)
    try:
        validated_ips = validate_url_for_ssrf(url)
    except SSRFSecurityViolation as e:
        logger.warning(f"[API CALL] SSRF violation blocked for URL '{url}': {e}")
        return ExecutionResult(
            success=False,
            output=None,
            error=f"SSRF Security Violation: {str(e)}",
            error_code="SSRF_SECURITY_VIOLATION",
        )
        
    try:
        pinned_ip = validated_ips[0]
        transport = create_pinned_async_transport(pinned_ip)
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
            request_kwargs: Dict[str, Any] = {"headers": headers}
            if body and method in ["POST", "PUT", "PATCH"]:
                request_kwargs["json"] = body
                
            response = await client.request(method, url, **request_kwargs)
            response.raise_for_status()
            
            output = response.text
            # Tronquer l'output si trop long
            if len(output) > 20000:
                output = output[:20000] + "\n\n[TRUNCATED]"
                
            logger.info(f"[API CALL] {method} {url} -> Status {response.status_code}")
            return ExecutionResult(success=True, output=output, error=None, cost_amount=Decimal("0.0"), cost_unit="credits")
            
    except httpx.HTTPStatusError as e:
        logger.error(f"[API CALL] HTTP Error on {url}: {e.response.status_code}")
        return ExecutionResult(success=False, output=None, error=f"HTTP Error: {e.response.status_code} - {e.response.text}", error_code="API_HTTP_ERROR")
    except Exception as e:
        logger.error(f"[API CALL] Error on {url}: {e}")
        return ExecutionResult(success=False, output=None, error=str(e), error_code="API_ERROR")
