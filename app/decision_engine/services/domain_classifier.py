from typing import Any, Dict, Tuple, Optional
import re
from app.decision_engine.models import PermissionAction, ClassificationStatus
from app.decision_engine.schemas import ClassificationResult

class DomainClassifier:
    """
    Classifier transforming a proposed action into a domain and permission.
    Uses a provided mapping to avoid hardcoding business domains in the service.
    """

    def __init__(self, mapping: Dict[str, Tuple[str, PermissionAction]] = None):
        """
        Initialize with a mapping of keywords to (domain, permission_action).
        Example: {"refund": ("finance", PermissionAction.UPDATE)}
        """
        self.mapping = mapping or {}

    async def classify(
        self, 
        proposed_action: str, 
        objective: str, 
        situation: str
    ) -> ClassificationResult:
        """
        Classifies the action based on the provided mapping and context.
        Uses word boundary matching to avoid false positives on sub-strings.
        """
        try:
            if not all(isinstance(x, str) for x in (proposed_action, objective, situation)):
                return ClassificationResult(status=ClassificationStatus.ERROR)

            text_to_analyze = f"{proposed_action} {objective} {situation}".lower()
            matches = set()
            
            for keyword, result in self.mapping.items():
                # Use regex word boundaries \b to match whole words only
                pattern = rf"\b{re.escape(keyword.lower())}\b"
                if re.search(pattern, text_to_analyze):
                    matches.add(result)

            if not matches:
                return ClassificationResult(status=ClassificationStatus.UNKNOWN)
            if len(matches) > 1:
                return ClassificationResult(status=ClassificationStatus.AMBIGUOUS)

            domain, permission_raw = matches.pop()

            try:
                permission = PermissionAction(permission_raw)
            except ValueError:
                return ClassificationResult(status=ClassificationStatus.ERROR)

            return ClassificationResult(
                domain=domain,
                permission_action=permission,
                status=ClassificationStatus.CERTAIN
            )

        except Exception:
            return ClassificationResult(status=ClassificationStatus.ERROR)
