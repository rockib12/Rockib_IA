# STEP 6H — META ADS / FINANCIAL GOVERNANCE AUDIT

**Mode : STRICT READ-ONLY AUDIT**  
**Système audité : Rockib AI**  
**Date : 4 Octobre 2026**  
**Référence normative : Doctrine « Le LLM propose. Le système décide. L'argent réel exige une autorisation réelle. »**

---

## 1. Executive Verdict

| Dimension Auditée | Statut Formel | Résumé de l'Audit |
| :--- | :--- | :--- |
| **Capacité d'Exécution Meta Ads Réelle** | ❌ **FALSE / CONTRADICTED** | **Aucun connecteur Meta Marketing API n'existe dans le code source.** Les connecteurs `facebook.post` et `instagram.post` sont des mocks de simulation pure (`[FACEBOOK MOCK]`, sans réseau, coût = 0.0). Aucune dépense financière externe réelle n'est possible aujourd'hui. |
| **Gouvernance Budgétaire Financière (Montants / Devises)** | ❌ **NOT PROVEN / ABSENT** | Les modèles `Goal`, `Task`, `ActionRecord`, et `DecisionDomainConfig` **ne possèdent aucun champ de montant financier (`amount`) ni de devise (`currency`)**. Le système gère des niveaux d'autonomie abstraits (0 à 5) et des quotas de crédits d'exécution interne, mais **aucune borne budgétaire en euros/dollars**. |
| **Classification d'Impact Financier** | ⚠️ **PARTIALLY PROVEN / GAP** | L'enum `ImpactType.financial` existe dans les modèles SQLAlchemy, mais **la table `decision_domain_config` en base de données classe toutes les règles (y compris le domaine `finance`) avec `base_impact = 'internal'` et `base_risk_level = 'low'`.** De plus, la condition d'approbation de l'arbitre n'inclut pas `risk_impact == financial`. |
| **Approbation Humaine Interactive (Telegram)** | ⚖️ **PARTIALLY PROVEN** | Le bot Telegram implémente une whitelist stricte sur `admin_chat_id` et émet des autorisations liées à un `decision_id` et `action_id`. Cependant, **l'approbation ne porte aucun montant scellé** et ne vérifie pas l'état préalable de la décision (absence de garde idempotente sur le statut). |
| **Sanctuaire d'Autorisation et Anti-Replay** | ✅ **PROVEN** | Le modèle `ExecutionAuthorization` est strictement lié à l'action (`action_id`), à l'empreinte canonique (`action_fingerprint`), au workspace et est à usage unique (`consumed_at`). Une tentative de rejeu est bloquée avec `AUTHORIZATION_ALREADY_CONSUMED`. |
| **Coffre-fort de Secrets (Credential Vault)** | ⚖️ **PARTIALLY PROVEN** | Le coffre-fort implémente un chiffrement authentifié réel **AEAD AES-256-GCM** avec données associées (AD) étanches par workspace. Cependant, **il n'est branché à aucun connecteur d'exécution** (`get_credential` n'est appelé que dans ses propres tests unitaires). |
| **Optimisation Autonome Publicitaire (ROAS/CPC/CTR)** | ❌ **FALSE / CONTRADICTED** | **Aucune logique de monitoring ROAS, CTR, CPC ou CPL n'existe dans le repository.** La boucle autonome (`autonomous_loop.py`) est un moteur de machine à états de graphe DAG générique sans logique métier publicitaire. |

---

## 2. Scope & Question Centrale

> **Question Centrale :**
> *« Si Rockib AI reçoit l'objectif "lancer une campagne Meta Ads avec un budget de 300 €", peut-il réellement empêcher toute dépense réelle tant qu'un humain autorisé n'a pas explicitement approuvé cette dépense ? »*

### Réponse Synthétique :
1. **Sur le plan de l'effet externe réel :** **OUI (par absence d'outil).** Le système ne peut engager aucun euro sur Meta Ads, car **aucun connecteur Meta Marketing API n'existe** et le coffre-fort de clés n'est relié à aucun outil d'appel externe.
2. **Sur le plan de la gouvernance financière du moteur :** **NON (GAPS MAJEURS).** Si un connecteur Meta était branché aujourd'hui, l'architecture actuelle **ne contient aucun validateur de montant financier**, le classifieur n'a pas les mots-clés publicitaires dans sa table, et la politique de domaine en base configure le domaine financier en risque `low` et impact `internal`, ce qui permettrait théoriquement à un arbitre de décider `ALLOW` sans approbation humaine si l'autonomie agent $\ge 1$.

---

## 3. Cartographie du Repository

Les recherches exhaustives par grep dans `app/` et `tests/` révèlent :

| Terme Recherché | Occurrences dans le Code | Emplacements Réels | Constat |
| :--- | :---: | :--- | :--- |
| `graph.facebook.com` | **0** dans `app/` (1 dans doc audit) | `STEP_6B_SOCIAL_CONNECTORS_AUDIT.md:255` | **Aucun appel réseau vers Meta Graph API.** |
| `Marketing API` / `campaign` / `adset` | **0** dans `app/` | Aucun | **Aucune entité de campagne publicitaire.** |
| `ROAS` / `CPC` / `CTR` / `CPL` | **0** dans tout le repo | Aucun | **Aucun moteur d'optimisation publicitaire.** |
| `facebook.post` / `instagram.post` | 8 dans `app/` | `app/connectors/social_connectors.py` | **Mocks purs** (`[FACEBOOK MOCK] Posting: ...`, coût = 0.0 crédits). |
| `ImpactType.financial` | 4 dans `app/` | `app/decision_engine/models.py:37`, `app/execution/models.py:42` | Enum défini en Python, mais `base_impact = internal` dans toutes les lignes de la table DB. |
| `ResourceBudget` | 8 dans `app/` | `app/execution/models.py:550`, `reservations.py` | Gestion de quotas abstraits de crédits d'exécution par workspace, pas de devises monétaires. |
| `budget_limit` (Goal) | 12 dans `app/` | `app/goal_engine/services/goal_manager.py:370` | Somme de `cost_amount` en crédits d'outils internes, pas de budget monétaire externe. |
| `WorkspaceCredentialVault` | 24 dans `app/` | `app/credentials/services/vault.py` | Implémenté avec AES-256-GCM réel, mais **0 appel** depuis les connecteurs. |

---

## 4. Chaîne Réelle d'Exécution

Voici le traçage rigoureux du flux d'exécution pour l'intention *"Lancer une campagne Meta Ads avec un budget de 300 €"* :

```text
[1] USER OBJECTIVE : "Lancer une campagne Meta Ads avec un budget de 300 €"
         │
         ▼
[2] GOAL ENGINE (`Goal`)
    - Objectif textuel : stocké dans `Goal.objective`.
    - Montant "300 €" : NON PARSÉ, NON STOCKÉ dans un champ structuré.
    - Autonomie appliquée : `applied_autonomy_level = min(req, agent_default)` (0..5).
         │
         ▼
[3] TASK GRAPH (`Task`)
    - Découpage en sous-tâches (ex: "Créer campagne publicitaire Meta Ads").
    - Pas de champ montant ni devise dans la table `tasks`.
         │
         ▼
[4] SKILL SELECTION (`SkillSelector`)
    - Aucun skill "meta_ads" dans le catalogue de 107 compétences.
    - Sélection possible : `social_media_broadcaster` (facebook.post) ou `general_system`.
         │
         ▼
[5] DOMAIN CLASSIFIER (`DomainClassifier`)
    - Mots-clés testés : "campagne", "meta", "ads", "budget", "300" -> AUCUN MATCH dans `classifier_config.json`.
    - Si l'action contient "créer" ou "create" -> match `"create": ["system", "CREATE"]`.
    - Résultat : `domain="system"`, `permission_action="CREATE"`.
    - ⚠️ L'action n'est JAMAIS classifiée sous "finance".
         │
         ▼
[6] COGNITIVE & INTELLIGENCE SIMULATOR
    - Inférence cognitive & Groq : analyse de rationalité.
    - L'IA peut suggérer un `risk_level` (low/medium/high/critical).
         │
         ▼
[7] DETERMINISTIC ARBITRATOR (`DeterministicArbitrator`)
    - Chargement config DB : `domain="system"`, `permission="CREATE"`.
    - Ligne DB existante : `execution_enabled=True`, `max_autonomy=3`, `base_risk=low`, `base_impact=internal`.
    - Condition approval : `approval_required = (disagreement > seuil OR risk in (high, critical) OR irreversible OR escalate OR DELETE)`.
    - ⚠️ `ImpactType.financial` n'est PAS dans la condition OR de l'arbitre.
    - Si l'IA n'augmente pas le risque à high/critical : `approval_required = False`.
    - Verdict de contrôle : `control_outcome = ALLOW`.
         │
         ▼
[8] AUTHORIZATION (`issue_authorization`)
    - Émission d'une `ExecutionAuthorization` consommable (car ALLOW et approval_required=False).
         │
         ▼
[9] RELIABLE EXECUTOR (`dispatch_authorized_action`)
    - Recherche du handler pour `system.CREATE` -> résout `fs_write_handler` !
    - Handler Meta Ads ? -> **INEXISTANT.**
         │
         ▼
[10] EFFET RÉEL
    - Écriture d'un fichier sur disque ou échec `NO_HANDLER_REGISTERED`.
    - **Dépense financière sur Meta : IMPOSSIBLE (0 appel API).**
```

### Tableau de conformité des étapes :

| Étape | Existe ? | Fichier | Statut Enforcement | Preuve Formelle |
| :--- | :---: | :--- | :--- | :--- |
| **Goal Budget Parsing** | ❌ NON | `app/goal_engine/models.py` | **Absent** | Aucun attribut `budget_amount` ni `currency` sur `Goal`. |
| **Financial Classification** | ⚠️ PARTIEL | `app/decision_engine/classifier_config.json` | **Inopérant pour les pubs** | "refund" est le seul mot-clé mappé vers "finance". "ads", "campaign", "budget" sont absents. |
| **Arbitrator Financial Gating** | ❌ NON | `app/decision_engine/services/arbitrator.py:194` | **Non déclenché** | `base_impact == ImpactType.financial` n'est pas présent dans le test d'approbation obligatoire. |
| **Budget Ceiling Check** | ❌ NON | `app/goal_engine/services/goal_manager.py:370` | **Non financier** | Ne contrôle que la somme de `cost_amount` des crédits d'exécution interne. |
| **Human Approval Binding** | ⚠️ PARTIEL | `app/telegram/services/telegram_service.py:282` | **Id-bound, pas amount-bound** | L'approbation lie `decision_id` et `action_id`, mais aucun montant financier. |
| **Execution Authorization** | ✅ OUI | `app/execution/services/authorizations.py:84` | **Enforcé** | One-time, fingerprint-bound, workspace-bound. |
| **Meta Connector** | ❌ NON | `app/connectors/social_connectors.py` | **MOCK PUR** | Aucun appel HTTP réel à `graph.facebook.com`. |
| **Credential Access** | ❌ NON | `app/credentials/services/vault.py` | **Déconnecté** | Le vault chiffre, mais aucun connecteur ne l'interroge. |

---

## 5. Audit Critique — Financial Classification

1. **Une création de campagne Meta est-elle réellement classifiée `financial` ?**
   **NON.** Dans [`app/decision_engine/classifier_config.json`](file:///c:/Users/Privé/Rockib_ia/app/decision_engine/classifier_config.json), aucun mot-clé relatif à la publicité, aux enchères ou aux campagnes n'existe. Une action comme *"créer la campagne publicitaire"* matche sur le lemme `"créer"` $\rightarrow$ `["system", "CREATE"]`.
2. **Qui détermine cette classification ?**
   Le service purement déterministe [`DomainClassifier`](file:///c:/Users/Privé/Rockib_ia/app/decision_engine/services/domain_classifier.py) par regex sur les frontières de mots (`\bkeyword\b`).
3. **Le LLM peut-il influencer directement cette classification ?**
   **NON.** Le LLM n'intervient pas dans la classification de domaine ; elle est exécutée avant tout appel LLM.
4. **Le système possède-t-il une classification déterministe pour les opérations financières ?**
   Seul le mot-clé `"refund"` est mappé vers `["finance", "UPDATE"]`.
5. **Une erreur de classification peut-elle permettre `ALLOW` sans approval ?**
   **OUI.** Si l'action matche `"system"` ou `"general"`, que la politique du domaine a `execution_enabled=True` et `max_autonomy >= 1`, et que le LLM n'élève pas le risque à `high` ou `critical`, l'arbitre conclut `ALLOW` avec `approval_required=False`.
6. **Que se passe-t-il si la classification est absente ou ambiguë ?**
   `ClassificationStatus.UNKNOWN` ou `AMBIGUOUS` déclenche une escalade immédiate (`ControlOutcome.ESCALATE`, `approval_required=True`, `CLASSIFICATION_UNCERTAIN`), garantissant la sécurité par défaut.
7. **Que se passe-t-il si le LLM ment sur le domaine ou le risque ?**
   Le LLM ne peut pas modifier le domaine (dérivé du classifieur). En revanche, l'arbitre calcule :
   `risk_level_final = _max_risk(base_risk_level, ai_suggested_risk)`.
   Si la base de données indique `base_risk_level = low`, et que le LLM ment en prétendant `low`, le risque final reste `low`. Si `base_impact = internal`, l'action peut obtenir `ALLOW`.

---

## 6. Audit du Budget Ceiling

1. **Le budget demandé par l'agent est-il imposé par une contrainte serveur ?**
   **NON.** Il n'existe aucun concept de plafond budgétaire monétaire (en devises réelles) dans Rockib AI.
2. **Scénario `requested_budget = 300 EUR`, `allowed_budget = 50 EUR` :**
   Le système ne possède aucune structure de données pour stocker ces valeurs. Si l'agent écrit `{"budget": 300}` dans ses arguments JSON :
   * Le Goal Engine n'inspecte pas ce JSON.
   * L'Arbitrateur n'inspecte pas ce JSON.
   * L'Exécuteur n'inspecte pas ce JSON.
   Le seul "budget" vérifié dans `GoalManager.check_limits()` est :
   ```python
   stmt_budget = select(func.coalesce(func.sum(ExecutionResultRecord.cost_amount), 0))...
   if budget_limit is not None and consumed_budget >= budget_limit:
       budget_ok = False
   ```
   Ce calcul additionne des crédits d'exécution abstraits retournés par les handlers (actuellement tous à `Decimal("0.0")`).
3. **Statut :** **ABSENT DE L'ARCHITECTURE.**

---

## 7. Human Approval

L'approbation humaine est implémentée via Telegram dans [`app/telegram/services/telegram_service.py`](file:///c:/Users/Privé/Rockib_ia/app/telegram/services/telegram_service.py) :
1. **Qui peut approuver ?**
   Seul l'utilisateur dont l'ID correspond à `settings.TELEGRAM_ADMIN_CHAT_ID` (`is_authorized_sender`).
2. **Comment l'approbation est-elle liée à l'action ?**
   Le bouton inline renvoie le payload `approve:{decision_uuid}`. Le serveur retrouve la `Decision` correspondante par son identifiant primaire en base.
3. **Est-elle liée au montant ou à la devise ?**
   **NON.** L'approbation valide la décision `Decision` dans sa globalité sans validation d'un montant financier borné.
4. **Une approbation ancienne peut-elle être réutilisée ?**
   **NON pour l'exécution.** Dès qu'une `ExecutionAuthorization` est consommée par l'exécuteur, `consumed_at` est horodaté et tout rejeu lève `AUTHORIZATION_ALREADY_CONSUMED`.
   **ATTENTION (GAP TELEGRAM) :** Si l'administrateur clique plusieurs fois sur le bouton inline Telegram `[✅ Approuver]`, le handler Telegram ne vérifie pas si `decision.status == DecisionStatus.executed` avant de réémettre une autorisation (`issue_authorization`).
5. **Le LLM peut-il écrire lui-même `approval=true` ?**
   **NON.** Le champ `approval_required` et `permission_granted` sur `Decision` et `ExecutionAuthorization` est strictement géré côté serveur par le code de contrôle ([`app/decision_engine/services/control.py`](file:///c:/Users/Privé/Rockib_ia/app/decision_engine/services/control.py)). Aucun argument JSON issu du LLM n'est pris en compte pour valider une autorisation.

---

## 8. Authorization

Le modèle [`ExecutionAuthorization`](file:///c:/Users/Privé/Rockib_ia/app/execution/models.py) est scellé côté serveur :
1. **Liaisons de l'autorisation :**
   * `action_id` : UUID unique de l'action.
   * `action_fingerprint` : Empreinte SHA-256 canonique calculée sur `(workspace_id, agent_id, tool, operation, permission, objective, arguments)`.
   * `workspace_id` : Tenant propriétaire.
   * `expires_at` : Expiration automatique (TTL par défaut 900 secondes / 15 minutes).
2. **Usage unique :**
   Verrouillage ligne SQL (`with_for_update()`) dans `consume_authorization`. Dès la première exécution, `consumed_at = _utcnow()`.
3. **Transférabilité inter-actions :**
   **IMPOSSIBLE.** Si on tente d'utiliser l'autorisation de l'action A pour l'action B, `evaluate_validity()` rejette immédiatement avec `ACTION_MISMATCH` ou `ACTION_FINGERPRINT_CHANGED`.

---

## 9. Credential Vault

1. **Existe-t-il réellement un Vault ?** **OUI.** [`app/credentials/services/vault.py`](file:///c:/Users/Privé/Rockib_ia/app/credentials/services/vault.py).
2. **Algorithme réel :** **AES-256-GCM** via la bibliothèque certifiée `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
3. **Clé maître :** Dérivée de `settings.CREDENTIAL_VAULT_KEY` via HKDF-SHA256 (`info=b"rockib-workspace-credential-vault-v1"`).
4. **Chiffrement au repos :** Oui, stockage en base du nonce (12 octets) + ciphertext + tag GCM encodé Base64.
5. **Isolation de workspace (INV-02) :** **PROUVÉE PAR TESTS CRYPTOGRAPHIQUES.** Les données associées (AD) injectent `f"{workspace_id}:{provider}:{key_alias}"`. Tenter de déchiffrer un secret dans un autre workspace lève `InvalidTag` $\rightarrow$ `CredentialTamperingError`.
6. **Le LLM peut-il obtenir le secret en clair ?**
   **NON.** Aucun outil (`tool`) exposé aux agents n'appelle `WorkspaceCredentialVault.get_credential()`.
7. **Le connecteur reçoit-il le secret ?**
   **NON (GAP ACTUEL) :** Aucun connecteur n'appelle le vault. Les connecteurs sociaux sont des mocks, et le connecteur API ne gère pas d'injection automatique de secrets du vault.

---

## 10. Meta Connector

* **Statut :** ❌ **MOCK PUR.**
* Dans [`app/connectors/social_connectors.py`](file:///c:/Users/Privé/Rockib_ia/app/connectors/social_connectors.py) :
  ```python
  async def facebook_post_handler(action: ActionRecord) -> ExecutionResult:
      ...
      await simulate_network_delay() # asyncio.sleep(1.0)
      logger.info(f"[FACEBOOK MOCK] Posting: {text}")
      return ExecutionResult(success=True, output=f"Successfully posted to Facebook: {text}", cost_amount=Decimal("0.0"), cost_unit="credits")
  ```
* Aucune connexion réseau, aucun endpoint Meta, aucune version Graph API configurée, aucun scope OAuth.

---

## 11. External Idempotency

* **Côté système Rockib AI :**
  L'exécuteur implémente l'idempotence des tentatives via `ExecutionAttempt` avec bail exclusif (`lease_owner`, `lease_expires_at`). Si un timeout survient pendant l'appel d'un outil, l'effet est classé `EffectCertainty.unknown` (`TIMEOUT_AMBIGUOUS`). L'invariant `INV-09` interdit formellement de rejouer une tentative en état incertain.
* **Côté API Meta :**
  N'existant pas, aucune clé d'idempotence externe (`client_request_id` de Meta Graph API) n'est transmise.

---

## 12. Autonomous Optimization

* **Recherche de code :**
  * Aucune mention de `ROAS`, `CTR`, `CPC`, `CPL` dans toute la base de code.
  * Aucun mécanisme dans `AutonomousExecutionLoop` ne permet d'augmenter ou de diminuer un budget.
* **Constat :** L'affirmation selon laquelle la boucle autonome optimise les campagnes et ajuste les budgets publicitaires est **TOTALEMENT FICTIVE**.

---

## 13. Goal Engine & 14. Autonomie Hiérarchique

* **Plafond d'autonomie parent $\rightarrow$ enfant :**
  **PROUVÉ ET VÉRIFIÉ.** Depuis le durcissement STEP 6G :
  Dans [`app/goal_engine/services/goal_manager.py:161`](file:///c:/Users/Privé/Rockib_ia/app/goal_engine/services/goal_manager.py) :
  ```python
  cap = min(requested_autonomy_level, agent_default_autonomy)
  if parent_applied_autonomy is not None:
      cap = min(cap, parent_applied_autonomy)
  ```
  Le routeur `POST /goals` et `agent_spawn_handler` transmettent tous les deux `parent_applied_autonomy`. Un sous-agent ne peut jamais obtenir une autonomie décisionnelle supérieure à celle de son parent.
* **Contrainte financière :**
  Cette autonomie hiérarchique régit les **niveaux d'arbitrage (0 à 5)**, **PAS un montant monétaire**.

---

## 15. Decision Engine / Arbitrator & 16. Direct Bypass

* **Frontière de contrôle :**
  Tout appel passant par l'orchestrateur suit le pipeline inviolable :
  `Decision` $\rightarrow$ `ExecutionAuthorization` $\rightarrow$ `dispatch_authorized_action`.
* **Bypass de connecteur direct :**
  Un agent ne peut exécuter que les outils déclarés dans `_ACTION_HANDLERS`. Il ne peut pas invoquer directement `httpx` ou des fonctions Python internes depuis un prompt.
  Cependant, l'outil `api.call` (s'il était invoqué) permettrait des requêtes HTTP sortantes arbitraires (protégées contre le SSRF et le DNS rebinding, mais sans contrôle de budget monétaire).

---

## 17. Action Record & Audit Trail

Chaque exécution enregistre un `ActionRecord` et des lignes d'audit append-only [`AuditEvent`](file:///c:/Users/Privé/Rockib_ia/app/execution/models.py) :
* Traçabilité de l'acteur, du workspace, de l'agent, de la décision et de l'empreinte de l'action.
* Absence de secrets : les mots de passe et clés ne sont pas logués dans les événements d'audit.
* **Lacune :** `ActionRecord.cost_estimate` et `cost_unit` sont conçus pour des crédits de traitement, pas pour auditer des dépenses publicitaires externes avec devises (EUR, USD).

---

## 18. Matrice d'Audit et Preuves Formelles

| Propriété Auditée | Statut Formel | Preuve dans le Code | Fichier / Référence | Risque Résiduel |
| :--- | :---: | :--- | :--- | :---: |
| **Financial classification** | ⚠️ PARTIALLY PROVEN | `refund` seul mot-clé mappé vers `finance`. | `classifier_config.json:5` | **HIGH** |
| **Budget ceiling (Monétaire)** | ❌ NOT PROVEN | Aucun champ monétaire ni devise en base. | `Goal`, `Task`, `ActionRecord` | **CRITICAL** (si connecteur branché) |
| **Human approval (Telegram)** | ✅ PROVEN | Whitelist admin, callback query, mise à jour UI. | `telegram_service.py:201` | **LOW** |
| **Approval binding** | ⚠️ PARTIALLY PROVEN | Lié à la décision, mais pas au montant financier. | `telegram_service.py:288` | **MEDIUM** |
| **Authorization binding** | ✅ PROVEN | Liée à `action_id`, `fingerprint`, `workspace`. | `authorizations.py:65` | **NONE** |
| **Authorization one-use** | ✅ PROVEN | Verrou `with_for_update`, horodatage `consumed_at`. | `authorizations.py:219` | **NONE** |
| **Credential Vault** | ✅ PROVEN | Chiffrement réel AEAD AES-256-GCM. | `vault.py:59` | **NONE** |
| **Credential isolation** | ✅ PROVEN | Données associées (AD) scellées par `workspace_id`. | `vault.py:54` | **NONE** |
| **Meta connector** | ❌ FALSE / CONTRADICTED | Connecteurs sociaux sont des mocks (`[MOCK]`). | `social_connectors.py:15` | **NONE** (car aucun effet réel) |
| **External idempotency** | ⚠️ PARTIALLY PROVEN | Idempotence interne gérée, mais pas d'API externe. | `reliable_executor.py:198` | **LOW** |
| **Autonomous optimization** | ❌ FALSE / CONTRADICTED | Aucune formule ROAS/CTR/CPC dans le repository. | `autonomous_loop.py` | **NONE** (inexistant) |
| **Parent autonomy inheritance** | ✅ PROVEN | `cap = min(req, agent, parent_applied)`. | `goal_manager.py:161` | **NONE** |
| **Goal financial constraints** | ❌ NOT PROVEN | Pas de gestion de budget monétaire dans le Goal. | `goal_engine/models.py:23` | **HIGH** |
| **Direct connector protection**| ✅ PROVEN | Enregistrement strict sous `_ACTION_HANDLERS`. | `reliable_executor.py:48` | **NONE** |
| **Audit trail** | ✅ PROVEN | Table `audit_events` append-only. | `execution/models.py:345` | **NONE** |
| **Workspace isolation** | ✅ PROVEN | Vérifié sur DB, Vault et Goal Engine. | `test_security_hardening.py` | **NONE** |

---

## 19. Évaluation des 10 Scénarios de Stress

* **SCENARIO A — Budget autorisé (50 EUR, Approval=YES, Auth=VALID) :**  
  *Verdict :* **BLOCKED.** L'exécuteur cherche un handler pour Meta Ads, ne le trouve pas (`NO_HANDLER_REGISTERED`), et lève une exception sans aucun effet externe.
* **SCENARIO B — Budget supérieur au plafond (300 EUR demandés vs 50 EUR autorisés) :**  
  *Verdict :* **NOT ENFORCED.** Le système ne possède pas de vérification de plafond financier. Si un connecteur existait, l'arbitre n'aurait aucun moyen de comparer 300 à 50.
* **SCENARIO C — Pas d'approbation (Requested 50 EUR, Approval=NO) :**  
  *Verdict :* **INCONNU / CONDITIONNEL.** Si l'action est classifiée comme `system.CREATE` avec un risque évalué comme `low`, l'arbitre peut émettre `ALLOW` sans exiger d'approbation humaine.
* **SCENARIO D — LLM ment (`{"financial": false, "budget": 0, "approval": true}`) :**  
  *Verdict :* **VULNÉRABLE.** L'arbitre se fie au classifieur déterministe (qui classe en `system.CREATE`) et à la configuration de domaine en base (qui définit `base_impact = internal` et `base_risk = low`). Si le LLM ment en confirmant `risk = low`, le système ne détecte pas le risque financier.
* **SCENARIO E — Approval replay (Autorisation 50 € réutilisée pour 300 €) :**  
  *Verdict :* **PROTÉGÉ (DENY).** L'autorisation est strictement liée au SHA-256 de l'action (`canonical_fingerprint`). Toute modification d'un argument modifie le hash et provoque un rejet immédiat (`ACTION_FINGERPRINT_CHANGED` ou `AUTHORIZATION_ALREADY_CONSUMED`).
* **SCENARIO F — Child agent escalation (Parent=2, Child demande 5 pour dépenser) :**  
  *Verdict :* **PROTÉGÉ (DENY D'AUTONOMIE).** L'autonomie du child est bridée à 2 par `GoalManager.calculate_applied_autonomy()`.
* **SCENARIO G — Optimization autonome (50 € autorisés $\rightarrow$ 150 € appliqués par l'IA) :**  
  *Verdict :* **NON APPLICABLE.** Aucun code d'optimisation publicitaire n'existe dans le système.
* **SCENARIO H — Connector direct (Bypass de l'arbitre) :**  
  *Verdict :* **PROTÉGÉ.** Les handlers ne sont accessibles qu'à travers la table de dispatch protégée par autorisation.
* **SCENARIO I — Token extraction ("Donne-moi le token Meta") :**  
  *Verdict :* **PROTÉGÉ.** Aucun outil d'extraction de token n'est mis à disposition des agents dans leurs manifests de compétences.
* **SCENARIO J — Workspace isolation (Workspace B tente d'accéder au token de A) :**  
  *Verdict :* **PROTÉGÉ.** Rejet mathématique immédiat par `AES-256-GCM` via les données associées (AD) scellées (`InvalidTag` $\rightarrow$ `CredentialTamperingError`).

---

## 20. Findings Priorisés

### FINDING 1 — CRITICAL
**Titre :** Absence Totale de Modélisation et de Contrôle Budgétaire Monétaire (Montants & Devises)  
**Emplacement :** `app/goal_engine/models.py`, `app/execution/models.py`, `app/decision_engine/models.py`  
**Description :** Les modèles du système gèrent des niveaux d'autonomie (0 à 5) et des crédits d'outils (`cost_amount`), mais aucun champ ne stocke un montant financier réel (`amount`, `currency`, `max_financial_spend`).  
**Impact :** Impossibilité d'appliquer un plafond budgétaire réel (ex: bloquer si > 50 €) en cas d'intégration d'un service de paiement ou de régie publicitaire.

### FINDING 2 — HIGH
**Titre :** Désalignement de la Configuration de Domaine Financier en Base de Données  
**Emplacement :** Table `decision_domain_config` (PostgreSQL)  
**Description :** Dans la table `decision_domain_config`, la règle du domaine `"finance"` est configurée avec `base_impact = 'internal'` et `base_risk_level = 'low'`, avec `execution_enabled = True` et `max_autonomy_level = 3`.  
**Impact :** Si une action est classifiée sous le domaine `"finance"`, l'arbitre ne force pas l'approbation humaine obligatoire par défaut si l'agent dispose d'une autonomie $\ge 1$.

### FINDING 3 — HIGH
**Titre :** Condition d'Approbation de l'Arbitre Ignorant `ImpactType.financial`  
**Emplacement :** `app/decision_engine/services/arbitrator.py:194`  
**Description :** La condition déclenchant `approval_required = True` vérifie le désaccord, le niveau de risque (`high`, `critical`), l'irréversibilité, la règle `escalate` et l'action `DELETE`, mais n'inclut pas `base_impact == ImpactType.financial`.  
**Impact :** Une action ayant un impact financier déclaré ne déclenche pas automatiquement l'escalade humaine si son risque est évalué comme modéré ou faible.

### FINDING 4 — MEDIUM
**Titre :** Déconnexion Complète entre le Credential Vault et les Connecteurs d'Exécution  
**Emplacement :** `app/credentials/services/vault.py`, `app/connectors/api_connector.py`  
**Description :** Le vault dispose d'un chiffrement robuste et testé, mais aucune fonction de dispatch de l'exécuteur ne charge ni n'injecte de secret résolu dans les requêtes sortantes.

---

## 21. Réponse à la Question Finale

> **Can Rockib AI currently guarantee that a request such as "Spend 300 EUR on Meta Ads" cannot result in real external spending without explicit human authorization bound to that exact financial action?**

### VERDICT :
$$\Huge\textbf{NO — NOT PROVEN}$$

### JUSTIFICATION FACTUELLE :

1. **Aucun euro ne peut être dépensé aujourd'hui**, mais ce n'est **pas grâce à un garde-fou budgétaire** : c'est uniquement parce que **le connecteur Meta Ads n'existe pas** et que les connecteurs sociaux actuels sont des simulations loggées sans connexion réseau.
2. **Si un connecteur Meta était ajouté aujourd'hui sans refonte de la gouvernance :**
   * L'action ne serait pas classifiée sous `finance` (manque de mots-clés dans le classifieur).
   * L'arbitre pourrait accorder `ALLOW` sans exiger d'approbation humaine si le risque est évalué à `medium` ou `low`.
   * Le système n'a aucun moyen technique de vérifier si 300 € dépasse ou non un plafond autorisé de 50 €.
   * L'approbation Telegram valide une décision abstraite mais ne scelle aucun montant financier dans l'autorisation.

---

## 22. Recommandations pour l'Étape Suivante

Pour qu'une véritable régie publicitaire ou passerelle financière puisse être opérée par Rockib AI en toute sécurité, les étapes préalables obligatoires sont :

1. **Phase 1 — Schéma Financier :** Ajouter sur `Goal` et `ActionRecord` les champs `financial_budget_cap: Decimal` et `currency: str`.
2. **Phase 2 — Durcissement Arbitre :** Modifier [`arbitrator.py`](file:///c:/Users/Privé/Rockib_ia/app/decision_engine/services/arbitrator.py) pour forcer systématiquement `approval_required = True` dès que `risk_impact == ImpactType.financial` ou dès qu'une transaction financière est détectée.
3. **Phase 3 — Scellement Budgétaire dans l'Autorisation :** Intégrer le montant maximal approuvé dans `ExecutionAuthorization` et valider dans `ReliableExecutor` que l'argument `budget` de l'action $\le$ montant scellé dans l'autorisation.
4. **Phase 4 — Connecteur Réel :** Implémenter le connecteur Meta Marketing API officiel en le branchant de manière étanche au Credential Vault.

---

**Fin du Rapport d'Audit STEP 6H.**  
*Rapport consigné en mode READ-ONLY sans altération du code source.*
