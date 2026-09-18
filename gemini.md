# ?? Rockib_ia - Decision Engine : Journal de Bord & ?tat du Projet

Ce document sert de source de v?rit? pour l'?tat actuel du Decision Engine. Il est mis ? jour apr?s chaque ?tape majeure de conception ou d'impl?mentation.

## ?? Objectif du Projet
Impl?menter un syst?me d'arbitrage d?terministe permettant de d?cider si une action propos?e par un agent IA peut ?tre ex?cut?e automatiquement ou doit ?tre escalad?e vers un humain, en se basant sur le risque, l'autonomie et des politiques configurables par domaine.

---

## ??? Architecture Verrouill?e

**Flux de donn?es :**
`HTTP Request` $ightarrow$ `Router` $ightarrow$ `DecisionOrchestrator` $ightarrow$ `DomainClassifier` $ightarrow$ `Cognitive/Intelligence Services` $ightarrow$ `DeterministicArbitrator` $ightarrow$ `Persistence` $ightarrow$ `Response`

### 1. DomainClassifier (Impl?ment? ?)
- **R?le** : Transformer une intention textuelle en cl?s de politique.
- **Contrat** : `(proposed_action, objective, situation)` $ightarrow$ `(domain, permission_action, status)`.
- **Statuts** : `CERTAIN`, `AMBIGUOUS`, `UNKNOWN`, `ERROR`.
- **R?gle de s?curit?** : Seuls les r?sultats `CERTAIN` sont envoy?s ? l'Arbitrator.

### 2. DeterministicArbitrator (Impl?ment? ?)
- **R?le** : Appliquer les r?gles de risque et d'autonomie.
- **Logique d'autonomie** : `applied_autonomy_level = min(requested_autonomy_level, allowed_autonomy_level)`.
- **R?gles d'arbitrage** : `cognitive_wins`, `intelligence_wins`, `consensus_required`, `escalate`.
- **D?clencheurs d'approbation** : D?saccord > seuil, Risque High/Critical, Irr?versibilit?, R?gle d'escalade, ou Permission `DELETE`.

### 3. Services d'Opinion (Squelettes ?)
- **Cognitive** : Analyse l'intention $ightarrow$ `suggested_action`, `confidence`.
- **Intelligence** : Analyse le risque $ightarrow$ `suggested_action`, `confidence`, `risk_level`.

---

## ?? ?tat des Composants

| Composant | ?tat | Fichier | Note |
| :--- | :--- | :--- | :--- |
| **Models** | ? Op?rationnel | `app/decision_engine/models.py` | Sch?mas SQLAlchemy et Enums |
| **Schemas** | ? Op?rationnel | `app/decision_engine/schemas.py` | Pydantic (Request/Response) |
| **Classifier** | ? Op?rationnel | `app/decision_engine/services/domain_classifier.py` | Mapping keyword $ightarrow$ domain |
| **Arbitrator** | ? Op?rationnel | `app/decision_engine/services/arbitrator.py` | Logique d?terministe |
| **Orchestrator**| ? Absent | N/A | ? impl?menter |
| **Router** | ? Squelette | `app/decision_engine/router.py` | Endpoints ? cr?er |
| **Cognitive** | ? Squelette | `app/cognitive/` | Contrats d?finis, services vides |
| **Intelligence**| ? Squelette | `app/intelligence/` | Contrats d?finis, services vides |
| **Execution** | ? Squelette | `app/execution/` | ? impl?menter |

---

## ?? Contrats Verrouill?s

### S?mantique de l'Autonomie
- **Requested** : Demande sp?cifique de l'action.
- **Allowed** : Limite impos?e par la politique du domaine (`DecisionDomainConfig`).
- **Applied** : `min(requested, allowed)`.

### IntelligenceOutput (Contrat)
- `suggested_action`: `str`
- `confidence`: `float` [0.0, 1.0]
- `risk_level`: `RiskLevel` (Enum)
- `reasoning`: `str`

### CognitiveOutput (Contrat)
- `suggested_action`: `str`
- `confidence`: `float` [0.0, 1.0]
- `reasoning`: `str`

---

## ??? Historique des D?cisions Techniques

- **Arbitrage D?terministe** : Choix d'un moteur pur sans effets de bord pour garantir la pr?dictibilit?.
- **Classification S?mantique** : S?paration du `DomainClassifier` pour ?viter que l'Arbitrator ne g?re du texte libre.
- **Politique de S?curit?** : Toute ambigu?t? (`AMBIGUOUS`, `UNKNOWN`) ou erreur technique (`ERROR`) lors de la classification bloque l'appel ? l'Arbitrator et m?ne ? l'escalade.
- **Gestion du Risque** : Utilisation d'un rang num?rique (`_RISK_RANK`) pour comparer les niveaux de risque.

---

## ?? Prochaines ?tapes (Backlog)
1. [ ] Impl?menter le `DecisionOrchestrator` (Coordination du flux).
2. [ ] Impl?menter les endpoints du `Router` pour tester le flux de bout en bout.
3. [ ] Impl?menter les services `Cognitive` et `Intelligence` (Int?gration LLM).
4. [ ] Impl?menter la persistance r?elle des d?cisions via l'Orchestrator.
