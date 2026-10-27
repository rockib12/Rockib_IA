from typing import Any, Dict, Tuple, Optional
import re
from app.decision_engine.models import PermissionAction, ClassificationStatus
from app.decision_engine.schemas import ClassificationResult

class DomainClassifier:
    """Classifier transforming a proposed action into a domain and permission.

    Enforces deterministic financial intent detection (STEP 6H.2A):
    - Explicit financial/spending intentions take precedence over generic system verbs.
    - Preserves distinction between SPEND vs READ/ANALYZE.
    - Supports word boundaries strictly (no substring false positives on 'ad').
    - Fail-closed on ambiguities across distinct non-system domains.
    """

    CURRENCY_PATTERN = re.compile(
        r"(?:(?:\d+(?:[.,]\d+)?\s*(?:eur|usd|xof|cad|gbp|chf|aud|jpy|€|\$|euros?|dollars?)\b)|(?:(?:\$|€)\s*\d+(?:[.,]\d+)?))",
        re.IGNORECASE,
    )
    SPEND_VERBS = re.compile(
        r"\b(dépenser|dépense|dépenses|spend|spending|payer|paye|paiement|payment|pay|acheter|achète|achat|buy|purchase|sponsoriser|sponsorise|sponsor|sponsoring|promouvoir|promote|booster|booste|boost)\b",
        re.IGNORECASE,
    )
    AD_OBJECTS = re.compile(
        r"\b(campagne|campagnes|campaign|campaigns|publicité|publicités|publicite|publicites|ad|ads|pub|pubs|meta ads|facebook ads|instagram ads)\b",
        re.IGNORECASE,
    )
    AD_ACTIONS = re.compile(
        r"\b(créer|crée|create|création|lancer|lance|launch|start|run|fais|faire|make|mets|mettre|set up)\b",
        re.IGNORECASE,
    )
    BUDGET_VERBS = re.compile(
        r"\b(augmenter|augmente|augmenté|increase|mettre|mets|set|modifier|modifie|change|ajoute|ajouter|add|double|doubler|fixer|fixe)\b",
        re.IGNORECASE,
    )
    READ_ANALYZE_PATTERNS = re.compile(
        r"\b(analyse|analyser|analysez|analyze|analysis|ctr|cpc|roas|cpl|liste|lister|list|montre|montre-moi|show|show me|donne-moi|give me|performances?|statistiques?|stats?|vérifie|verifier|check|inspect|quel est|quelle est|what is|combien|how much|explique|explain|qu\'est-ce|what is a)\b",
        re.IGNORECASE,
    )

    WRAPPER_PREFIX_PATTERN = re.compile(
        r"^(?:analyse et exécution(?: de l'objectif)?\s*:\s*|mission\s*:\s*|exécuter mission\s*:\s*)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        mapping: Dict[str, Tuple[str, PermissionAction]] = None,
        use_gemma_semantic: bool = False,
    ):
        """Initialize with a mapping of keywords to (domain, permission_action).
        Example: {"refund": ("finance", PermissionAction.UPDATE)}
        """
        self.mapping = mapping or {}
        self.use_gemma_semantic = use_gemma_semantic

    def _detect_financial_intent(
        self, proposed_action: str, objective: str, situation: str
    ) -> Optional[Tuple[str, PermissionAction]]:
        act_text = proposed_action.lower()
        full_text = f"{proposed_action} {objective} {situation}".lower()

        # 1. READ / INQUIRY check first: distinguish SPEND vs READ/ANALYZE
        is_read = bool(self.READ_ANALYZE_PATTERNS.search(act_text)) or (
            bool(self.READ_ANALYZE_PATTERNS.search(full_text))
            and not bool(self.SPEND_VERBS.search(full_text))
            and not bool(self.CURRENCY_PATTERN.search(full_text))
        )
        has_direct_spend = bool(self.SPEND_VERBS.search(full_text))

        if is_read and not has_direct_spend and not bool(self.CURRENCY_PATTERN.search(full_text)):
            if re.search(r"\b(budget|dépensé|dépenses|spent|spend)\b", full_text):
                return ("finance", PermissionAction.READ)
            if self.AD_OBJECTS.search(full_text):
                return ("research", PermissionAction.READ)
            if re.search(r"\b(meta ads|campagne|publicité)\b", full_text):
                return ("research", PermissionAction.READ)

        # 2. Explicit SPEND intentions evaluated across full_text (proposed_action + objective + situation)
        if self.SPEND_VERBS.search(full_text):
            return ("finance", PermissionAction.SPEND)

        if "budget" in full_text and (
            self.BUDGET_VERBS.search(full_text) or self.CURRENCY_PATTERN.search(full_text)
        ):
            return ("finance", PermissionAction.SPEND)

        if (
            (self.AD_ACTIONS.search(full_text) and self.AD_OBJECTS.search(full_text))
            or re.search(
                r"\b(campagne publicitaire|advertising campaign|ad campaign|promotion payante|paid promotion|paid ad|campagne facebook|campagne instagram|facebook ad|instagram ad)\b",
                full_text,
            )
        ):
            return ("finance", PermissionAction.SPEND)

        if re.search(r"\b(mets|mettre|mettez|injecter|injecte)\b.*\b(argent|money|budget)\b", full_text):
            return ("finance", PermissionAction.SPEND)

        if re.search(r"\b(post|publication|campagne|ad|pub)\b", full_text) and self.CURRENCY_PATTERN.search(full_text):
            return ("finance", PermissionAction.SPEND)

        if self.AD_OBJECTS.search(full_text) and self.CURRENCY_PATTERN.search(full_text):
            return ("finance", PermissionAction.SPEND)

        return None

    async def classify(
        self, 
        proposed_action: str, 
        objective: str, 
        situation: str
    ) -> ClassificationResult:
        """Classifies the action based on the provided mapping, financial patterns, and context.
        Uses word boundary matching to avoid false positives on sub-strings.
        """
        try:
            if not all(isinstance(x, str) for x in (proposed_action, objective, situation)):
                return ClassificationResult(status=ClassificationStatus.ERROR)

            # Nettoyer d'éventuels préfixes de wrapper de tâche système (ex: "Analyse et exécution de l'objectif : ")
            clean_action = self.WRAPPER_PREFIX_PATTERN.sub("", proposed_action).strip() or proposed_action

            # 1. Prioriser l'action proposée explicite pour éviter les faux positifs dus à l'objectif parent
            matches = set()
            for keyword, result in self.mapping.items():
                pattern = rf"\b{re.escape(keyword.lower())}\b"
                if re.search(pattern, clean_action.lower()):
                    matches.add(result)

            # 2. Si aucun mot-clé direct n'est trouvé, analyser le contexte élargi
            if not matches:
                text_to_analyze = f"{clean_action} {objective} {situation}".lower()
                for keyword, result in self.mapping.items():
                    pattern = rf"\b{re.escape(keyword.lower())}\b"
                    if re.search(pattern, text_to_analyze):
                        matches.add(result)

            # 2b. Règle de priorité CONTENT-CLASS-INV-01 :
            # Une intention de rédaction explicite (content/CREATE) évince les verbes
            # génériques sans effet externe (lectures, system/CREATE). Toute autre
            # correspondance (SEND, PUBLISH, DELETE, finance, infrastructure...) est
            # conservée et rend donc la classification AMBIGUOUS (fail-closed).
            if any(m[0] == "content" and m[1] == "CREATE" for m in matches):
                generic = {
                    m for m in matches
                    if m[0] != "content"
                    and (m[1] == "READ" or (m[0] == "system" and m[1] == "CREATE"))
                }
                matches.difference_update(generic)

            # 3. Évaluation déterministe de l'intention financière (STEP 6H.2A)
            fin_intent = self._detect_financial_intent(proposed_action, objective, situation)
            if fin_intent is not None:
                fin_domain, fin_perm = fin_intent
                if fin_perm == PermissionAction.SPEND:
                    # Règle de priorité FIN-CLASS-INV-02 :
                    # Une intention SPEND évince les actions techniques génériques (system, infrastructure, etc.)
                    tech_matches = {
                        m for m in matches if m[0] in {"system", "infrastructure", "testing", "monitoring"}
                    }
                    matches.difference_update(tech_matches)
                    matches.add((fin_domain, fin_perm))
                elif fin_perm == PermissionAction.READ:
                    # En lecture/inspection, éliminer les correspondances techniques génériques si présentes
                    tech_matches = {m for m in matches if m[0] in {"system", "infrastructure"}}
                    matches.difference_update(tech_matches)
                    if not matches:
                        matches.add((fin_domain, fin_perm))

            if not matches:
                if self.use_gemma_semantic:
                    from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
                    gemma_res, _ = await GemmaRecognitionEngine.recognize_domain(
                        proposed_action=clean_action,
                        objective=objective,
                        situation=situation,
                    )
                    return gemma_res
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

    async def classify_with_gemma(
        self,
        proposed_action: str,
        objective: str,
        situation: str,
    ) -> ClassificationResult:
        """Classification hybride : règles déterministes en priorité absolue + reconnaissance vectorielle Gemma-2."""
        res = await self.classify(proposed_action, objective, situation)
        if res.status != ClassificationStatus.UNKNOWN:
            return res
        from app.intelligence.services.gemma_recognition import GemmaRecognitionEngine
        gemma_res, _ = await GemmaRecognitionEngine.recognize_domain(
            proposed_action=proposed_action,
            objective=objective,
            situation=situation,
        )
        return gemma_res
