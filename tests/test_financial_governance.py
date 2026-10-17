"""Tests unitaires et d'intégration ciblés pour STEP 6H.1A — Financial Governance Hardening.

Vérifie :
1. Contrat strict de validation de 'amount' (Decimal, int, >0, rejet des floats, rejet NaN/Inf, rejet des unités).
2. Contrat strict de validation de 'currency' (ISO-4217, uppercase, pas de symboles ni minuscules).
3. Cohérence absolue 'amount' / 'cost_estimate' (ActionRecord).
4. Empreinte canonique (compute_fingerprint) et rejet par 'ACTION_FINGERPRINT_CHANGED'.
5. Validation pure du budget ceiling (Cas A à F, fail-closed).
6. Validation pure de la monotonie parent/child (parent ceiling >= child ceiling).
7. Doctrine fail-closed sur cas invalides / absents.
8. Scénario critique d'intégrité de bout en bout avec Reliable Executor.
"""
import math
import uuid
from decimal import Decimal
import pytest

from app.decision_engine.models import (
    ControlOutcome,
    ImpactType,
    PermissionAction,
    ReversibilityLevel,
    RiskLevel,
    Decision,
)
from app.execution.models import ActionRecord, ExecutionAuthorization
from app.execution.services import authorizations, reliable_executor
from app.execution.services.fingerprint import compute_fingerprint
from app.execution.services.financial_governance import (
    FinancialScope,
    FinancialAmountError,
    FinancialCurrencyError,
    FinancialConsistencyError,
    FinancialValidationError,
    BudgetCeilingMissingError,
    BudgetCeilingExceededError,
    BudgetCurrencyMismatchError,
    ParentChildCeilingViolationError,
    validate_financial_amount,
    validate_financial_currency,
    extract_financial_scope,
    verify_action_financial_consistency,
    validate_budget_ceiling,
    validate_parent_child_ceiling,
)


# ===========================================================================
# 1. Tests de validation de 'amount'
# ===========================================================================
class TestFinancialAmountValidation:
    def test_amount_positive_integers_accepted(self):
        assert validate_financial_amount(10) == Decimal("10")
        assert validate_financial_amount(50) == Decimal("50")
        assert validate_financial_amount(300) == Decimal("300")

    def test_amount_decimals_accepted(self):
        assert validate_financial_amount(Decimal("50.00")) == Decimal("50.00")
        assert validate_financial_amount(Decimal("300.50")) == Decimal("300.50")

    def test_amount_clean_numeric_string_accepted(self):
        assert validate_financial_amount("300") == Decimal("300")
        assert validate_financial_amount("50.25") == Decimal("50.25")

    def test_amount_zero_rejected(self):
        with pytest.raises(FinancialAmountError, match="strictly positive"):
            validate_financial_amount(0)

    def test_amount_negative_rejected(self):
        with pytest.raises(FinancialAmountError, match="strictly positive"):
            validate_financial_amount(-1)
        with pytest.raises(FinancialAmountError, match="strictly positive"):
            validate_financial_amount("-50")

    def test_amount_none_rejected(self):
        with pytest.raises(FinancialAmountError, match="required and cannot be None"):
            validate_financial_amount(None)

    def test_amount_with_currency_unit_rejected(self):
        with pytest.raises(FinancialAmountError, match="pure numeric format"):
            validate_financial_amount("300 EUR")
        with pytest.raises(FinancialAmountError, match="pure numeric format"):
            validate_financial_amount("50$")

    def test_amount_nan_and_infinity_rejected(self):
        with pytest.raises(FinancialAmountError, match="finite"):
            validate_financial_amount(Decimal("NaN"))
        with pytest.raises(FinancialAmountError, match="finite"):
            validate_financial_amount(Decimal("Infinity"))
        with pytest.raises(FinancialAmountError, match="pure numeric format"):
            validate_financial_amount("NaN")
        with pytest.raises(FinancialAmountError, match="pure numeric format"):
            validate_financial_amount("Infinity")

    def test_amount_float_rejected_strictly(self):
        """Les floats sont strictement interdits pour éviter les erreurs d'arrondi binaire."""
        with pytest.raises(FinancialAmountError, match="Float type is forbidden"):
            validate_financial_amount(50.0)
        with pytest.raises(FinancialAmountError, match="Float type is forbidden"):
            validate_financial_amount(300.5)


# ===========================================================================
# 2. Tests de validation de 'currency'
# ===========================================================================
class TestFinancialCurrencyValidation:
    def test_currency_valid_iso_4217(self):
        assert validate_financial_currency("EUR") == "EUR"
        assert validate_financial_currency("USD") == "USD"
        assert validate_financial_currency("XOF") == "XOF"
        assert validate_financial_currency("CAD") == "CAD"
        assert validate_financial_currency("GBP") == "GBP"

    def test_currency_lowercase_rejected(self):
        with pytest.raises(FinancialCurrencyError, match="strictly uppercase"):
            validate_financial_currency("eur")
        with pytest.raises(FinancialCurrencyError, match="strictly uppercase"):
            validate_financial_currency("usd")

    def test_currency_symbols_rejected(self):
        with pytest.raises(FinancialCurrencyError, match="not a valid ISO-4217 code"):
            validate_financial_currency("€")
        with pytest.raises(FinancialCurrencyError, match="not a valid ISO-4217 code"):
            validate_financial_currency("$")

    def test_currency_verbose_names_rejected(self):
        with pytest.raises(FinancialCurrencyError, match="not a valid ISO-4217 code"):
            validate_financial_currency("EURO")
        with pytest.raises(FinancialCurrencyError, match="whitespace"):
            validate_financial_currency("XOF CFA")

    def test_currency_empty_or_none_rejected(self):
        with pytest.raises(FinancialCurrencyError, match="required and cannot be None"):
            validate_financial_currency(None)
        with pytest.raises(FinancialCurrencyError, match="empty"):
            validate_financial_currency("")

    def test_currency_non_string_rejected(self):
        with pytest.raises(FinancialCurrencyError, match="must be a string"):
            validate_financial_currency(978)  # Code numérique ISO non accepté comme string alpha


# ===========================================================================
# 3. Tests de cohérence 'amount' / 'cost_estimate' (Section 4)
# ===========================================================================
class TestFinancialScopeConsistency:
    def _create_action(self, arguments, cost_estimate=None, cost_unit=None):
        return ActionRecord(
            id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            objective="Campagne pub",
            tool="meta_ads",
            operation="create_campaign",
            arguments=arguments,
            permission_required=PermissionAction.SPEND,
            risk_level=RiskLevel.high,
            risk_reversibility=ReversibilityLevel.irreversible,
            risk_impact=ImpactType.financial,
            cost_estimate=cost_estimate,
            cost_unit=cost_unit,
            canonical_fingerprint="dummy",
            idempotency_key="dummy_key",
            version=1,
        )

    def test_consistency_exact_match(self):
        action = self._create_action(
            arguments={"amount": Decimal("300"), "currency": "EUR"},
            cost_estimate=Decimal("300"),
            cost_unit="EUR",
        )
        scope = verify_action_financial_consistency(action)
        assert scope is not None
        assert scope.amount == Decimal("300")
        assert scope.currency == "EUR"

    def test_inconsistency_amount_mismatch_rejected(self):
        # arguments.amount = 300, cost_estimate = 50 -> REJET
        action1 = self._create_action(
            arguments={"amount": Decimal("300"), "currency": "EUR"},
            cost_estimate=Decimal("50"),
            cost_unit="EUR",
        )
        with pytest.raises(FinancialConsistencyError, match="amount mismatch"):
            verify_action_financial_consistency(action1)

        # arguments.amount = 50, cost_estimate = 300 -> REJET
        action2 = self._create_action(
            arguments={"amount": Decimal("50"), "currency": "EUR"},
            cost_estimate=Decimal("300"),
            cost_unit="EUR",
        )
        with pytest.raises(FinancialConsistencyError, match="amount mismatch"):
            verify_action_financial_consistency(action2)

    def test_inconsistency_currency_mismatch_rejected(self):
        action = self._create_action(
            arguments={"amount": Decimal("50"), "currency": "EUR"},
            cost_estimate=Decimal("50"),
            cost_unit="USD",
        )
        with pytest.raises(FinancialConsistencyError, match="currency mismatch"):
            verify_action_financial_consistency(action)


# ===========================================================================
# 4. Tests d'empreinte canonique & Anti-Replay (Section 5)
# ===========================================================================
class TestFinancialFingerprintIntegrity:
    def test_fingerprint_differs_when_amount_changes(self):
        ws_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        fp_50 = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Lancer campagne",
            arguments={"amount": "50", "currency": "EUR"},
        )

        fp_300 = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Lancer campagne",
            arguments={"amount": "300", "currency": "EUR"},
        )

        assert fp_50 != fp_300, "50 EUR fingerprint MUST differ from 300 EUR fingerprint"

    def test_fingerprint_differs_when_currency_changes(self):
        ws_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        fp_eur = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Lancer campagne",
            arguments={"amount": "50", "currency": "EUR"},
        )

        fp_usd = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Lancer campagne",
            arguments={"amount": "50", "currency": "USD"},
        )

        assert fp_eur != fp_usd, "50 EUR fingerprint MUST differ from 50 USD fingerprint"

    def test_authorization_validity_rejects_fingerprint_tampering(self):
        ws_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        action_id = uuid.uuid4()

        args_50 = {"amount": "50", "currency": "EUR"}
        fp_50 = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Lancer campagne",
            arguments=args_50,
        )

        action = ActionRecord(
            id=action_id,
            workspace_id=ws_id,
            agent_id=agent_id,
            objective="Lancer campagne",
            tool="meta_ads",
            operation="create_campaign",
            arguments=args_50,
            permission_required=PermissionAction.SPEND,
            risk_level=RiskLevel.high,
            risk_reversibility=ReversibilityLevel.irreversible,
            risk_impact=ImpactType.financial,
            canonical_fingerprint=fp_50,
            idempotency_key="key_1",
            version=1,
        )

        auth = ExecutionAuthorization(
            id=uuid.uuid4(),
            decision_id=uuid.uuid4(),
            action_id=action_id,
            workspace_id=ws_id,
            agent_id=agent_id,
            action_fingerprint=fp_50,  # Autorisation émise sur 50 EUR
            action_version=1,
            outcome=ControlOutcome.ALLOW,
            approval_required=False,
        )

        # 1. État nominal : l'autorisation est valide
        assert authorizations.evaluate_validity(auth, action) is None

        # 2. Altération de l'action : passage à 300 EUR
        args_300 = {"amount": "300", "currency": "EUR"}
        fp_300 = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Lancer campagne",
            arguments=args_300,
        )
        action.arguments = args_300
        action.canonical_fingerprint = fp_300

        # 3. L'autorisation rejette formellement l'altération avec ACTION_FINGERPRINT_CHANGED
        refusal = authorizations.evaluate_validity(auth, action)
        assert refusal == "ACTION_FINGERPRINT_CHANGED"


# ===========================================================================
# 5. Tests de Budget Ceiling (Section 6, Cas A à F)
# ===========================================================================
class TestBudgetCeilingValidation:
    def test_case_a_under_ceiling_valid(self):
        # ceiling = 50 EUR, requested = 30 EUR -> VALID
        assert validate_budget_ceiling(
            requested_amount=Decimal("30"),
            requested_currency="EUR",
            ceiling_amount=Decimal("50"),
            ceiling_currency="EUR",
        ) == Decimal("30")

    def test_case_b_exact_ceiling_valid(self):
        # ceiling = 50 EUR, requested = 50 EUR -> VALID
        assert validate_budget_ceiling(
            requested_amount=Decimal("50"),
            requested_currency="EUR",
            ceiling_amount=Decimal("50"),
            ceiling_currency="EUR",
        ) == Decimal("50")

    def test_case_c_slightly_over_ceiling_invalid(self):
        # ceiling = 50 EUR, requested = 51 EUR -> INVALID
        with pytest.raises(BudgetCeilingExceededError, match="exceeds budget ceiling"):
            validate_budget_ceiling(
                requested_amount=Decimal("51"),
                requested_currency="EUR",
                ceiling_amount=Decimal("50"),
                ceiling_currency="EUR",
            )

    def test_case_d_significantly_over_ceiling_invalid(self):
        # ceiling = 50 EUR, requested = 300 EUR -> INVALID
        with pytest.raises(BudgetCeilingExceededError, match="exceeds budget ceiling"):
            validate_budget_ceiling(
                requested_amount=Decimal("300"),
                requested_currency="EUR",
                ceiling_amount=Decimal("50"),
                ceiling_currency="EUR",
            )

    def test_case_e_currency_mismatch_invalid(self):
        # ceiling = 50 EUR, requested = 50 USD -> INVALID / CURRENCY_MISMATCH
        with pytest.raises(BudgetCurrencyMismatchError, match="does not match ceiling currency"):
            validate_budget_ceiling(
                requested_amount=Decimal("50"),
                requested_currency="USD",
                ceiling_amount=Decimal("50"),
                ceiling_currency="EUR",
            )

    def test_case_f_ceiling_absent_invalid_fail_closed(self):
        # ceiling absent, requested = 300 EUR -> INVALID (fail-closed, pas d'infini)
        with pytest.raises(BudgetCeilingMissingError, match="Budget ceiling is missing"):
            validate_budget_ceiling(
                requested_amount=Decimal("300"),
                requested_currency="EUR",
                ceiling_amount=None,
                ceiling_currency=None,
            )


# ===========================================================================
# 6. Tests Parent / Child Ceiling (Section 7)
# ===========================================================================
class TestParentChildCeilingValidation:
    def test_parent_child_strictly_lower_valid(self):
        # parent = 50 EUR, child = 30 EUR -> VALID
        assert validate_parent_child_ceiling(
            parent_ceiling_amount=Decimal("50"),
            parent_ceiling_currency="EUR",
            child_ceiling_amount=Decimal("30"),
            child_ceiling_currency="EUR",
        ) == Decimal("30")

    def test_parent_child_equal_valid(self):
        # parent = 50 EUR, child = 50 EUR -> VALID
        assert validate_parent_child_ceiling(
            parent_ceiling_amount=Decimal("50"),
            parent_ceiling_currency="EUR",
            child_ceiling_amount=Decimal("50"),
            child_ceiling_currency="EUR",
        ) == Decimal("50")

    def test_parent_child_exceeded_invalid(self):
        # parent = 50 EUR, child = 100 EUR -> INVALID
        with pytest.raises(ParentChildCeilingViolationError, match="exceeds parent ceiling"):
            validate_parent_child_ceiling(
                parent_ceiling_amount=Decimal("50"),
                parent_ceiling_currency="EUR",
                child_ceiling_amount=Decimal("100"),
                child_ceiling_currency="EUR",
            )

    def test_parent_child_missing_parent_ceiling_fail_closed(self):
        with pytest.raises(BudgetCeilingMissingError, match="Parent budget ceiling is missing"):
            validate_parent_child_ceiling(
                parent_ceiling_amount=None,
                parent_ceiling_currency=None,
                child_ceiling_amount=Decimal("50"),
                child_ceiling_currency="EUR",
            )

    def test_parent_child_currency_mismatch_invalid(self):
        with pytest.raises(BudgetCurrencyMismatchError, match="does not match parent ceiling"):
            validate_parent_child_ceiling(
                parent_ceiling_amount=Decimal("50"),
                parent_ceiling_currency="EUR",
                child_ceiling_amount=Decimal("30"),
                child_ceiling_currency="USD",
            )


# ===========================================================================
# 7. Tests Fail-Closed & Extraction (Section 8)
# ===========================================================================
class TestFailClosedExtraction:
    def test_amount_absent_fails_closed(self):
        with pytest.raises(FinancialAmountError):
            extract_financial_scope({"currency": "EUR"}, strict=True)

    def test_currency_absent_fails_closed(self):
        with pytest.raises(FinancialCurrencyError):
            extract_financial_scope({"amount": 50}, strict=True)

    def test_both_absent_fails_closed_in_strict_mode(self):
        with pytest.raises(FinancialValidationError):
            extract_financial_scope({}, strict=True)

    def test_both_absent_returns_none_in_non_strict_mode(self):
        assert extract_financial_scope({}, strict=False) is None

    def test_invalid_decimal_or_currency_fails_closed(self):
        with pytest.raises(FinancialAmountError):
            extract_financial_scope({"amount": "invalid", "currency": "EUR"})
        with pytest.raises(FinancialCurrencyError):
            extract_financial_scope({"amount": 50, "currency": "INVALID"})


# ===========================================================================
# 8. Test Critique d'Intégrité de Bout en Bout avec Reliable Executor (Section 9)
# ===========================================================================
@pytest.mark.asyncio
class TestCriticalIntegrityReliableExecutor:
    async def test_full_chain_action_tampering_rejected_by_executor(
        self, db_session, workspace_agent
    ):
        """Scénario critique :
        1. Action créée avec amount = 50, currency = EUR.
        2. Décision ALLOW et ExecutionAuthorization émise.
        3. Altération de l'action à amount = 300.
        4. Exécution tentée via dispatch_authorized_action.
        5. Rejet immédiat avec AuthorizationError('ACTION_FINGERPRINT_CHANGED').
        """
        workspace, agent = workspace_agent
        ws_id = workspace.id
        agent_id = agent.id
        action_id = uuid.uuid4()
        decision_id = uuid.uuid4()

        # 1. Action autorisée sur 50 EUR
        args_50 = {"amount": "50", "currency": "EUR"}
        fp_50 = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Campagne pub",
            arguments=args_50,
        )

        action = ActionRecord(
            id=action_id,
            workspace_id=ws_id,
            agent_id=agent_id,
            decision_id=decision_id,
            objective="Campagne pub",
            tool="meta_ads",
            operation="create_campaign",
            arguments=args_50,
            permission_required=PermissionAction.SPEND,
            risk_level=RiskLevel.high,
            risk_reversibility=ReversibilityLevel.irreversible,
            risk_impact=ImpactType.financial,
            cost_estimate=Decimal("50"),
            cost_unit="EUR",
            canonical_fingerprint=fp_50,
            idempotency_key=f"meta_ads_{uuid.uuid4()}",
            version=1,
        )
        db_session.add(action)

        decision = Decision(
            id=decision_id,
            workspace_id=ws_id,
            agent_id=agent_id,
            objective="Campagne pub",
            situation="Active",
            proposed_action="create_campaign",
            control_outcome=ControlOutcome.ALLOW,
            control_reason="POLICY_ALLOW",
            action_fingerprint=fp_50,
            risk_level=RiskLevel.high,
            risk_reversibility=ReversibilityLevel.irreversible,
            risk_impact=ImpactType.financial,
            requested_autonomy_level=1,
            applied_autonomy_level=1,
            permission_required=PermissionAction.SPEND,
            permission_granted=True,
            approval_required=False,
        )
        db_session.add(decision)
        await db_session.flush()

        # Émission d'une autorisation serveur réelle
        auth = await authorizations.issue_authorization(
            db_session,
            decision=decision,
            action=action,
            actor="test_runner",
        )
        await db_session.commit()

        # 2. Altération malveillante ou non synchronisée : passage à 300 EUR
        args_300 = {"amount": "300", "currency": "EUR"}
        fp_300 = compute_fingerprint(
            workspace_id=ws_id,
            agent_id=agent_id,
            tool="meta_ads",
            operation="create_campaign",
            permission_required=PermissionAction.SPEND,
            objective="Campagne pub",
            arguments=args_300,
        )
        action.arguments = args_300
        action.canonical_fingerprint = fp_300
        action.cost_estimate = Decimal("300")
        await db_session.commit()

        # 3. L'exécuteur tente de dispaticher l'action autorisée
        with pytest.raises(authorizations.AuthorizationError) as exc_info:
            await reliable_executor.dispatch_authorized_action(
                db_session,
                action=action,
                authorization_id=auth.id,
                actor="test_runner",
                lease_owner="worker_1",
            )

        # 4. Vérification formelle du code de refus
        assert exc_info.value.code == "ACTION_FINGERPRINT_CHANGED"
        assert "Autorisation non valide au moment de l'effet" in exc_info.value.message
