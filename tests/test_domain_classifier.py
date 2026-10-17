import pytest
from app.decision_engine.services.domain_classifier import DomainClassifier
from app.decision_engine.models import PermissionAction, ClassificationStatus
from app.decision_engine.schemas import ClassificationResult

@pytest.mark.asyncio
async def test_classify_certain():
    mapping = {"verify_identity": ("security", PermissionAction.READ)}
    classifier = DomainClassifier(mapping=mapping)
    
    result = await classifier.classify(
        proposed_action="Please verify_identity of the user",
        objective="Onboarding",
        situation="New user signup"
    )
    
    assert result.status == ClassificationStatus.CERTAIN
    assert result.domain == "security"
    assert result.permission_action == PermissionAction.READ

@pytest.mark.asyncio
async def test_classify_unknown():
    mapping = {"verify_identity": ("security", PermissionAction.READ)}
    classifier = DomainClassifier(mapping=mapping)
    
    result = await classifier.classify(
        proposed_action="Do something random",
        objective="Objective",
        situation="Situation"
    )
    
    assert result.status == ClassificationStatus.UNKNOWN
    assert result.domain is None
    assert result.permission_action is None

@pytest.mark.asyncio
async def test_classify_ambiguous():
    mapping = {
        "payment": ("finance", PermissionAction.SPEND),
        "transaction": ("compliance", PermissionAction.READ)
    }
    classifier = DomainClassifier(mapping=mapping)
    
    result = await classifier.classify(
        proposed_action="Process payment transaction",
        objective="Payment",
        situation="Checkout"
    )
    
    assert result.status == ClassificationStatus.AMBIGUOUS
    assert result.domain is None

@pytest.mark.asyncio
async def test_classify_technical_error():
    classifier = DomainClassifier(mapping={})
    result = await classifier.classify(None, None, None)
    assert result.status == ClassificationStatus.ERROR

@pytest.mark.asyncio
async def test_classify_invalid_permission():
    mapping = {"crash": ("domain", "INVALID_ACTION")}
    classifier = DomainClassifier(mapping=mapping)
    result = await classifier.classify("crash", "obj", "sit")
    assert result.status == ClassificationStatus.ERROR


# ===========================================================================
# STEP 6H.2A — Tests de classification des intentions financières
# ===========================================================================
from app.core.dependencies import get_classifier_mapping

@pytest.fixture
def real_classifier():
    return DomainClassifier(mapping=get_classifier_mapping())


@pytest.mark.asyncio
class TestFinancialIntentClassification:
    """Valide les 38 cas de la matrice de classification financière."""

    # 1. Intentions publicitaires avec montant / devise (FR & EN)
    @pytest.mark.parametrize("action_text", [
        "Créer une campagne Facebook avec 300 EUR",
        "Lance une publicité Instagram avec 50 USD",
        "Augmente le budget de la campagne à 200 EUR",
        "Crée une campagne Meta Ads de 300 €",
        "Dépenser 100 EUR en publicité",
        "Sponsoriser cette publication avec 20 EUR",
        "Acheter cette campagne publicitaire",
        "Payer 50 EUR",
        "Effectuer un paiement de 100 USD",
        "Create a Facebook campaign with 300 EUR",
        "Launch an Instagram ad with 50 USD",
        "Increase the campaign budget to 500 EUR",
        "Promote this post with 20 USD",
        "fais une pub de 300 EUR",
        "mets 300 EUR dans la campagne",
        "mets de l'argent sur cette campagne",
        "booste ce post pour 300 EUR",
        "promote this post with $300",
        "set campaign budget to 300 EUR",
    ])
    async def test_financial_spend_intent_explicit(self, real_classifier, action_text):
        result = await real_classifier.classify(action_text, "", "")
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == "finance"
        assert result.permission_action == PermissionAction.SPEND

    # 2. Intentions financières sans montant explicite (Section 9: montant absent)
    @pytest.mark.parametrize("action_text", [
        "Créer une campagne publicitaire",
        "Lancer une campagne Facebook",
        "Lance une publicité Instagram",
        "Augmente le budget",
        "Sponsorise cette publication",
    ])
    async def test_financial_spend_intent_without_amount(self, real_classifier, action_text):
        """L'absence de montant ne doit PAS déclasser l'action en simple system/CREATE."""
        result = await real_classifier.classify(action_text, "", "")
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == "finance"
        assert result.permission_action == PermissionAction.SPEND

    # 3. Devises variées (EUR, USD, XOF, CAD, GBP, symboles)
    @pytest.mark.parametrize("currency_action", [
        "Créer une campagne Facebook avec 300 EUR",
        "Créer une campagne Facebook avec 300 USD",
        "Créer une campagne Facebook avec 300 XOF",
        "Créer une campagne Facebook avec 300 CAD",
        "Créer une campagne Facebook avec 300 GBP",
        "Créer une campagne Facebook avec 300 €",
        "Créer une campagne Facebook avec $300",
        "Créer une campagne Facebook avec 300 euros",
        "Créer une campagne Facebook avec 300 dollars",
    ])
    async def test_financial_spend_currencies(self, real_classifier, currency_action):
        result = await real_classifier.classify(currency_action, "", "")
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == "finance"
        assert result.permission_action == PermissionAction.SPEND

    # 4. Actions de lecture / analyse : ne doivent JAMAIS être SPEND (Section 6, 8, 16)
    @pytest.mark.parametrize("read_text,expected_domain", [
        ("Analyse mes campagnes Facebook", "research"),
        ("Liste mes campagnes Instagram", "research"),
        ("Donne-moi le CTR de mes publicités", "research"),
        ("Analyse mon CPC", "research"),
        ("Montre-moi mes campagnes", "research"),
        ("Vérifie la campagne actuelle", "research"),
        ("Quel est le budget actuel ?", "finance"),
        ("Combien ai-je dépensé ?", "finance"),
        ("Explique-moi comment fonctionne Meta Ads", "research"),
        ("Qu'est-ce qu'une campagne publicitaire ?", "research"),
    ])
    async def test_read_and_analysis_not_spend(self, real_classifier, read_text, expected_domain):
        """READ / ANALYZE != SPEND."""
        result = await real_classifier.classify(read_text, "", "")
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == expected_domain
        assert result.permission_action == PermissionAction.READ
        assert result.permission_action != PermissionAction.SPEND

    # 5. Prévention des faux positifs sur les frontières de mots (Section 13)
    @pytest.mark.parametrize("fp_text", [
        "address user",
        "administrator login",
        "addition of numbers",
    ])
    async def test_word_boundary_no_false_positive(self, real_classifier, fp_text):
        """Le mot 'ad' ne doit pas matcher arbitrairement dans 'address', etc."""
        result = await real_classifier.classify(fp_text, "", "")
        assert result.status == ClassificationStatus.UNKNOWN
        assert result.domain is None
        assert result.permission_action is None

    # 6. Priorité absolue : FIN-CLASS-INV-02
    async def test_priority_over_generic_create(self, real_classifier):
        """'Créer une campagne Facebook avec 300 EUR' ne doit PAS devenir system/CREATE."""
        result = await real_classifier.classify("Créer une campagne Facebook avec 300 EUR", "", "")
        assert result.domain == "finance"
        assert result.permission_action == PermissionAction.SPEND
        assert result.domain != "system"
        assert result.permission_action != PermissionAction.CREATE

    # 7. Déterminisme strict : aucun contournement LLM (FIN-CLASS-INV-07, FIN-CLASS-INV-08)
    async def test_determinism_and_no_llm_degradation(self, real_classifier):
        # Même si le contexte ou la situation prétend qu'il s'agit d'une simple création système
        result = await real_classifier.classify(
            proposed_action="Créer une campagne Facebook avec 300 EUR",
            objective="Simple creation of post",
            situation="LLM claims this is non-financial",
        )
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == "finance"
        assert result.permission_action == PermissionAction.SPEND

    # 8. GAP-CLASS-01 Closure : Détection financière distribuée (objective / situation / contexte partagé)
    @pytest.mark.parametrize("act,obj,sit", [
        ("create", "Créer une campagne Facebook avec 300 EUR", ""),
        ("create", "", "L'utilisateur demande de lancer une campagne Facebook avec 300 EUR."),
        ("create campaign", "Facebook advertising", "Budget autorisé : 300 EUR"),
        ("create", "Facebook campaign", "Spend 300 EUR"),
        ("create", "Lancer une publicité Instagram avec 50 USD", ""),
        ("update", "Augmente le budget de la campagne à 200 EUR", ""),
        ("run", "Sponsoriser cette publication avec 20 EUR", ""),
        ("deploy", "Meta Ads campaign", "Budget de 100 EUR"),
    ])
    async def test_gap_class_01_context_bypass_closed(self, real_classifier, act, obj, sit):
        """L'intention de dépense dans objective ou situation force strictement finance/SPEND."""
        result = await real_classifier.classify(act, obj, sit)
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == "finance"
        assert result.permission_action == PermissionAction.SPEND

    # 9. Non-régression : les actions non financières avec verbes génériques restent dans leur domaine
    @pytest.mark.parametrize("act,obj,sit,expected_domain,expected_perm", [
        ("create", "Créer un nouveau fichier", "Initialisation du projet", "system", PermissionAction.CREATE),
        ("update", "Mettre à jour la configuration", "Maintenance", "system", PermissionAction.UPDATE),
        ("delete", "Supprimer les logs temporaires", "Nettoyage disque", "system", PermissionAction.DELETE),
        ("read", "Lire le document d'architecture", "Revue technique", "system", PermissionAction.READ),
    ])
    async def test_non_financial_generic_actions_preserve_origin(
        self, real_classifier, act, obj, sit, expected_domain, expected_perm
    ):
        """Prouve que finance/SPEND n'est PAS la réponse par défaut et préserve les domaines réels."""
        result = await real_classifier.classify(act, obj, sit)
        assert result.status == ClassificationStatus.CERTAIN
        assert result.domain == expected_domain
        assert result.permission_action == expected_perm


