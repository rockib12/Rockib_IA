# STEP 6H.1A — Financial Scope & Canonical Governance

**Date :** 2026-10-05  
**Projet :** Rockib AI  
**Statut :** PROVEN & LOCKED  
**Doctrine :** *Le LLM propose. Le système décide.*  
**Décisions :** `ALLOW` | `DENY` | `ESCALATE` | `STOP`

---

## 1. Scope

L'étape STEP 6H.1A implémente le cadre strict de validation et d'intégrité du scope financier sans modification de schéma de base de données (zéro migration SQL) :

* **Ancrage atomique :**
  ```text
  ActionRecord.arguments
      ├── amount (Decimal > 0, strict)
      └── currency (ISO-4217, uppercase)
  ```
* **Intégrité cryptographique :**
  ```text
  ActionRecord.canonical_fingerprint (SHA-256 de canonical_payload incluant arguments)
  ```
* **Cohérence de source unique :**
  ```text
  arguments.amount == ActionRecord.cost_estimate
  arguments.currency == ActionRecord.cost_unit
  ```
* **Plafond budgétaire hiérarchique :**
  ```text
  Goal.goal_metadata
      ├── budget_ceiling (Decimal)
      └── budget_currency (ISO-4217)
  ```

---

## 2. Financial Amount Contract

Le contrat de montant financier (`validate_financial_amount`) applique les règles strictes suivantes :

| Valeur testée | Résultat | Justification / Erreur levée |
| :--- | :--- | :--- |
| `10`, `50`, `300` | ✅ ACCEPTÉ | Entiers positifs convertis canoniquement en `Decimal`. |
| `Decimal("50.00")`, `Decimal("300.50")` | ✅ ACCEPTÉ | `Decimal` fini strictement positif. |
| `"300"`, `"50.25"` | ✅ ACCEPTÉ | Chaîne numérique pure sans unité ni symbole. |
| `0` | ❌ REFUSÉ | `FinancialAmountError: Amount must be strictly positive (> 0)`. |
| `-1`, `"-50"` | ❌ REFUSÉ | `FinancialAmountError: Amount must be strictly positive (> 0)`. |
| `None` | ❌ REFUSÉ | `FinancialAmountError: Amount is required and cannot be None`. |
| `"300 EUR"`, `"50$"` | ❌ REFUSÉ | `FinancialAmountError: Amount string must be a pure numeric format without currency or symbols`. |
| `Decimal("NaN")`, `Decimal("Infinity")`, `"NaN"` | ❌ REFUSÉ | `FinancialAmountError: Amount must be finite (NaN and Infinity are forbidden)`. |
| `50.0`, `300.5` (`float`) | ❌ REFUSÉ | `FinancialAmountError: Float type is forbidden for financial amounts to avoid binary rounding issues`. |

---

## 3. Currency Contract

Le contrat de devise (`validate_financial_currency`) impose :

* **Format :** Chaîne de 3 lettres strictes, sans espaces, 100% en majuscules.
* **Norme :** Appartenance obligatoire au référentiel officiel `ISO_4217_CURRENCIES` (160+ devises mondiales).

| Devise testée | Résultat | Justification / Erreur levée |
| :--- | :--- | :--- |
| `"EUR"`, `"USD"`, `"XOF"`, `"CAD"`, `"GBP"` | ✅ ACCEPTÉ | Code alphabétique ISO-4217 majuscule valide. |
| `"eur"`, `"usd"` | ❌ REFUSÉ | `FinancialCurrencyError: Currency code must be strictly uppercase`. |
| `"€"`, `"$"` | ❌ REFUSÉ | `FinancialCurrencyError: not a valid ISO-4217 code`. |
| `"EURO"` | ❌ REFUSÉ | `FinancialCurrencyError: not a valid ISO-4217 code`. |
| `"XOF CFA"` | ❌ REFUSÉ | `FinancialCurrencyError: Currency string must not be empty or contain whitespace`. |
| `""`, `None` | ❌ REFUSÉ | `FinancialCurrencyError: Currency is required and cannot be None / empty`. |
| `978` (entier) | ❌ REFUSÉ | `FinancialCurrencyError: Currency must be a string`. |

---

## 4. Amount / Cost Consistency

La fonction `verify_action_financial_consistency` empêche toute divergence entre les arguments d'exécution et les métadonnées d'estimation de la table `actions` :

* `arguments.amount == 300` et `cost_estimate == 50` $\rightarrow$ ❌ Levé : `FinancialConsistencyError` (amount mismatch).
* `arguments.amount == 50` et `cost_estimate == 300` $\rightarrow$ ❌ Levé : `FinancialConsistencyError` (amount mismatch).
* `arguments.currency == "EUR"` et `cost_unit == "USD"` $\rightarrow$ ❌ Levé : `FinancialConsistencyError` (currency mismatch).
* `arguments.amount == 300`, `arguments.currency == "EUR"`, `cost_estimate == 300`, `cost_unit == "EUR"` $\rightarrow$ ✅ Validé.

---

## 5. Budget Ceiling Validation

La fonction pure `validate_budget_ceiling` valide le plafond selon la doctrine fail-closed :

* **Cas A :** `ceiling = 50 EUR`, `requested = 30 EUR` $\rightarrow$ ✅ **VALID** (inférieur au plafond).
* **Cas B :** `ceiling = 50 EUR`, `requested = 50 EUR` $\rightarrow$ ✅ **VALID** (égal au plafond).
* **Cas C :** `ceiling = 50 EUR`, `requested = 51 EUR` $\rightarrow$ ❌ **INVALID** (`BudgetCeilingExceededError`).
* **Cas D :** `ceiling = 50 EUR`, `requested = 300 EUR` $\rightarrow$ ❌ **INVALID** (`BudgetCeilingExceededError`).
* **Cas E :** `ceiling = 50 EUR`, `requested = 50 USD` $\rightarrow$ ❌ **INVALID** (`BudgetCurrencyMismatchError`).
* **Cas F :** `ceiling absent (None)`, `requested = 300 EUR` $\rightarrow$ ❌ **INVALID** (`BudgetCeilingMissingError` — fail-closed, aucun plafond infini présumé).

---

## 6. Parent / Child Ceiling Validation

La fonction pure `validate_parent_child_ceiling` garantit l'invariant formel **FIN-INV-09** ($child\_ceiling \le parent\_ceiling$) :

* `parent = 50 EUR`, `child = 30 EUR` $\rightarrow$ ✅ **VALID**.
* `parent = 50 EUR`, `child = 50 EUR` $\rightarrow$ ✅ **VALID**.
* `parent = 50 EUR`, `child = 100 EUR` $\rightarrow$ ❌ **INVALID** (`ParentChildCeilingViolationError`).
* `parent = None`, `child = 50 EUR` $\rightarrow$ ❌ **INVALID** (`BudgetCeilingMissingError` — fail-closed).
* `parent = 50 EUR`, `child = 30 USD` $\rightarrow$ ❌ **INVALID** (`BudgetCurrencyMismatchError`).

---

## 7. Fingerprint Integrity & Anti-Tampering

* **Sensibilité de l'empreinte canonique :**
  * `compute_fingerprint(amount=50, currency=EUR) != compute_fingerprint(amount=300, currency=EUR)`.
  * `compute_fingerprint(amount=50, currency=EUR) != compute_fingerprint(amount=50, currency=USD)`.
* **Invalidation d'autorisation :**
  * Si une autorisation est émise pour une action sur 50 EUR, et que les arguments sont altérés pour 300 EUR :
    `authorizations.evaluate_validity(auth, action)` retourne immédiatement `"ACTION_FINGERPRINT_CHANGED"`.

---

## 8. Negative Tests & Scénario Critique Réel

Dans `TestCriticalIntegrityReliableExecutor` :
1. Une action `ActionRecord` (50 EUR) et une décision `Decision` sont persistées dans PostgreSQL avec `workspace_agent`.
2. Une autorisation serveur réelle `ExecutionAuthorization` est émise via `authorizations.issue_authorization()`.
3. L'action est altérée à 300 EUR (nouveau hash SHA-256 dans l'action).
4. La tentative de dispatching par le véritable exécuteur transactionnel `reliable_executor.dispatch_authorized_action()` lève immédiatement :
   ```python
   AuthorizationError: ACTION_FINGERPRINT_CHANGED ("Autorisation non valide au moment de l'effet.")
   ```
5. Aucune exécution d'outil n'a lieu. La protection est inviolable.

---

## 9. Regression & Métriques

* **Tests ciblés ajoutés :** 38 tests (`tests/test_financial_governance.py`), 100% passés.
* **Suite globale de non-régression :** **611 tests passés (100% verts, 0 échec)**.
* **Catalogue 107 Skills & Core 5 Skills :** 47/47 tests réussis, SHA-256 hashes 100% intacts.
* **Migrations SQL :** **0 migration** créée.

---

## 10. Remaining Gaps & Prochaines Étapes

Cette étape verrouille la représentation et la validation du scope financier. Les étapes suivantes porteront sur :
1. **Étape 2 / 2A :** Classification de domaine & intentions publicitaires (`classifier_config.json`, `DomainClassifier`) pour diriger les actions de dépenses vers `finance` / `SPEND`.
2. **Étape 3 / 3A :** Durcissement de l'Arbitrator (`approval_required = True` systématique sur impact financier ou `SPEND`).
3. **Étape 4 / 5 :** Liaison formelle de l'approbation humaine (Telegram inline buttons / API) au montant et à la devise exacts.
4. **Étape 6 / 7 :** Enforcement au niveau de l'Executor et des connecteurs.

---

## 11. Verdict

**STATUT : PROVEN & LOCKED**  
Le système rend désormais techniquement et cryptographiquement impossible de représenter, manipuler ou autoriser silencieusement un scope financier invalide, altéré ou non borné.
