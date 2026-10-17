# STEP 6B — SOCIAL CONNECTORS / META INTEGRATION AUDIT

## 0. Audit Metadata

- **System Name**: Rockib AI (Autonomous AI Operating & Governance Engine)
- **Audit Step**: STEP 6B — Social Connectors & Meta Integration Audit
- **Audit Mode**: READ-ONLY / AUDIT ONLY (Strict zero modification, zero implementation, zero secrets, zero network mutations)
- **Audit Date**: 2026-09-29T16:00:00+01:00
- **Auditor Role**: Lead Software Architect & Autonomous AI Systems Engineer
- **Git Commit Hash**: `d6398a19b33cac8f1710e56ed28dd4ae4b4d912d`
- **Core Foundational Axiom**: *« Le LLM propose. Le système décide. »*
- **Primary Objective**: Établir avec preuve formelle l'état réel de l'intégration des réseaux sociaux (notamment l'écosystème Meta : WhatsApp, Instagram, Facebook, ainsi que Twitter/X et Discord), cartographier les frontières d'autorisation, auditer l'isolation multi-workspace et déterminer les prérequis pour une future intégration réelle sans contourner la gouvernance déterministe.
- **Historique & Acquis Notifiés (Ce qui a été réalisé jusqu'à présent)** :
  1. *Phase 1 — Moteur d'Arbitrage Déterministe* : `DomainClassifier` (statuts `CERTAIN`, `AMBIGUOUS`, `UNKNOWN`), `DeterministicArbitrator` (`min(requested, allowed)`), `CognitiveSimulator`, `IntelligenceService` (Groq LLM avec garde-fous stricts).
  2. *Phase 2 — Moteur d'Exécution Transactionnelle* : `ReliableExecutor` (PostgreSQL ACID, `SELECT ... FOR UPDATE`, baux distribués, idempotence stricte `idempotency_key`, table `audit_entries` immuable protégée par triggers SQL).
  3. *Phase 3 — Moteur de Buts & Tâches (Goal Engine)* : Machine à états finis (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `ESCALATED`), DAG de tâches ordonnancé, admission control concurrentiel, workers et scheduler Celery Beat.
  4. *Phase 4 — Skill System Cryptographique* : Tables relationnelles (`skills`, `skill_versions`, `workspace_skills`, `agent_skills`), hachage canonique SHA-256 scellé (`content_hash == sha256:...`), détection d'altération (`SkillHashTamperingError`), délégation strictement monotone (`SKILL-INV-02`), catalogue des 5 compétences fondamentales (`portfolio_ambassador`, `lead_qualification`, `frontend_react`, `backend_django`, `cybersecurity_defensive`).
  5. *Phase 5 — Passerelle Inbound & Conciergerie Vocale* : Gateway publique `/api/v1/inbound/portfolio/message`, appel vocal direct in-browser (Web Speech API + synthèse Groq LLM vocale naturelle sans Markdown), qualification commerciale et pontage vers l'Agence IIA.
  6. *Phase 6 — Cockpit 3D & Observabilité* : Interface React 19 / Three.js, visualiseur DAG, logs d'audit forensique temps réel par agent (`GET /api/v1/agents/{id}/logs`, `GET /api/v1/telemetry`), terminal cybernétique CLI (`logs <agent>`).
  7. *Validation Globale* : **449 tests unitaires et d'intégration automatisés réussis (100% verts)**.

---

## 1. Executive Summary

L'audit technique approfondi du repository Rockib AI révèle une **séparation nette entre l'infrastructure d'exécution/gouvernance et les connecteurs sociaux** :

1. **Les connecteurs sociaux existants sont 100% des simulations (Mocks)** :
   Le fichier `app/connectors/social_connectors.py` (71 lignes) contient 5 fonctions : `facebook_post_handler`, `instagram_post_handler`, `whatsapp_send_handler`, `twitter_post_handler`, et `discord_send_handler`. Toutes ces fonctions simulent une latence réseau via `await asyncio.sleep(1.0)`, émettent un log applicatif (ex: `logger.info("[FACEBOOK MOCK] Posting: ...")`), et renvoient un `ExecutionResult(success=True)` statique sans effectuer **aucun appel réseau réel**, sans charger **aucun secret**, et sans interagir avec l'extérieur.
2. **La tuyauterie d'enregistrement existe mais n'est pas invoquée au démarrage** :
   Dans `app/execution/services/system_handlers.py`, la fonction `install_production_handlers()` enregistre ces connecteurs auprès du `_ACTION_HANDLERS` registry du `ReliableExecutor`. Cependant, cette fonction n'est appelée ni au démarrage de FastAPI (`app/main.py`), ni dans le worker Celery. Elle n'est invoquée explicitement que dans certains tests unitaires (`tests/test_system_handlers.py`).
3. **Le principe INV-01 est formellement respecté** :
   Le `ReliableExecutor` (`app/execution/services/reliable_executor.py`) impose un verrouillage PostgreSQL strict de l'autorisation (`authorizations.lock_authorization`), vérifie sa validité, la consomme de manière atomique avant d'invoquer le handler. Aucun effet externe ne peut être produit via `dispatch_authorized_action` sans une autorisation serveur préalable (`ALLOW`).
4. **Absence totale de gestion des secrets et d'isolation multi-workspace pour les connecteurs sociaux** :
   Les variables de configuration dans `app/core/config.py` relatives à WhatsApp (`WHATSAPP_API_URL`, `WHATSAPP_SESSION_ID`, `WHATSAPP_API_KEY`) sont globales, optionnelles et **strictement non consommées** par `social_connectors.py`. Il n'existe aucune table ou modèle permettant d'associer un compte WhatsApp, Facebook ou Instagram à un `workspace_id` donné.
5. **Absence complète de Webhook Inbound pour l'écosystème Meta** :
   Aucun endpoint ne gère le handshake GET Meta (`hub.mode`, `hub.challenge`, `hub.verify_token`) ni la réception POST des payloads WhatsApp / Messenger / Instagram signés par HMAC SHA-256 (`x-hub-signature-256`). Le seul endpoint de webhook existant (`POST /webhooks/trigger` dans `app/goal_engine/router.py`) utilise un secret statique en clair (`ROCKIB_SECRET_KEY`) et n'est pas conçu pour les formats Meta.
6. **Verdict d'implémentation** : **NOT READY FOR PRODUCTION / READY FOR ARCHITECTURAL STAGING**. Le système possède une fondation de gouvernance solide, mais requiert une abstraction de gestion des credentials par workspace, un contrat de connecteur résilient (timeout, circuit-breaker, retries bornés), et un validateur de webhooks HMAC avant toute activation réelle.

---

## 2. Repository Evidence

La cartographie réelle du repository confirme la présence des fichiers et modules suivants :

| Chemin du Fichier | Nature | Preuve d'Existence |
| :--- | :--- | :--- |
| `app/connectors/social_connectors.py` | Connecteurs Sociaux Mock | **VERIFIED** (71 lignes, 5 handlers mockés) |
| `app/connectors/whatsapp.py` | Connecteur WhatsApp dédié | **VERIFIED** (2 lignes, stub avec docstring *à implémenter*) |
| `app/connectors/twilio.py` | Connecteur Twilio | **VERIFIED** (2 lignes, stub avec docstring *à implémenter*) |
| `app/connectors/n8n.py` | Connecteur n8n | **VERIFIED** (2 lignes, stub avec docstring *à implémenter*) |
| `app/connectors/fs_connector.py` | Connecteur Système de Fichiers | **VERIFIED** (Sandboxing workspace root validé) |
| `app/connectors/web_connectors.py` | Connecteur Recherche Web | **VERIFIED** (DuckDuckGo search & fetch) |
| `app/connectors/api_connector.py` | Connecteur HTTP API générique | **VERIFIED** (Appels REST HTTP génériques) |
| `app/connectors/agent_connectors.py` | Spawning de sous-agents | **VERIFIED** (Création d'agents dépendants) |
| `app/execution/services/system_handlers.py` | Registre officiel des Handlers | **VERIFIED** (`install_production_handlers()`, L55-L100) |
| `app/execution/services/reliable_executor.py` | Exécuteur Transactionnel Garanti | **VERIFIED** (`dispatch_authorized_action()`, L140-L270) |
| `app/execution/services/fingerprint.py` | Empreinte Canonique & Idempotence | **VERIFIED** (SHA-256 sur payload canonique) |
| `app/execution/services/authorizations.py` | Cycle de vie des Autorisations | **VERIFIED** (Lock, issue, consume, revoke) |
| `app/execution/models.py` | Schémas SQLAlchemy ACID | **VERIFIED** (`ActionRecord`, `ExecutionAuthorization`, etc.) |
| `app/decision_engine/classifier_config.json` | Dictionnaire de classification | **VERIFIED** (Mots-clés `send`, `publish`, etc.) |
| `app/decision_engine/services/escalation.py` | Service d'Escalade Humaine | **VERIFIED** (2 lignes, stub *à implémenter*) |
| `app/core/config.py` | Configuration Pydantic Settings | **VERIFIED** (Variables WHATSAPP et TWILIO déclarées) |
| `app/inbound/router.py` | Passerelle Inbound Portfolio | **VERIFIED** (Endpoints message, voice session/turn/callback) |
| `app/skills/catalog.py` | Catalogue des 5 Skills Scellés | **VERIFIED** (Scellement SHA-256 canonique) |

---

## 3. Existing Social Connector Inventory

Analyse exhaustive du fichier `app/connectors/social_connectors.py` :

| Connector Function | Tool | Operation | Real Network Call | Mock | Validation | Timeout | Retry | Idempotency | Secret Handling | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `facebook_post_handler` | `facebook` | `post` | **NON** (0 appel) | **OUI** (`asyncio.sleep(1.0)`) | Vérifie `args.get("text")` non vide | **AUCUN** | **AUCUN** | **ABSENT** au niveau connecteur | **AUCUN** (aucun token lu) | **MOCK SIMULATION** |
| `instagram_post_handler` | `instagram` | `post` | **NON** (0 appel) | **OUI** (`asyncio.sleep(1.0)`) | Vérifie `args.get("image_url")` non vide | **AUCUN** | **AUCUN** | **ABSENT** au niveau connecteur | **AUCUN** (aucun token lu) | **MOCK SIMULATION** |
| `whatsapp_send_handler` | `whatsapp` | `send` | **NON** (0 appel) | **OUI** (`asyncio.sleep(1.0)`) | Vérifie `phone_number` et `message` | **AUCUN** | **AUCUN** | **ABSENT** au niveau connecteur | **AUCUN** (aucun token lu) | **MOCK SIMULATION** |
| `twitter_post_handler` | `twitter` | `post` | **NON** (0 appel) | **OUI** (`asyncio.sleep(1.0)`) | Vérifie `args.get("text")` non vide | **AUCUN** | **AUCUN** | **ABSENT** au niveau connecteur | **AUCUN** (aucun token lu) | **MOCK SIMULATION** |
| `discord_send_handler` | `discord` | `send` | **NON** (0 appel) | **OUI** (`asyncio.sleep(1.0)`) | Vérifie `channel_id` et `content` | **AUCUN** | **AUCUN** | **ABSENT** au niveau connecteur | **AUCUN** (aucun webhook lu) | **MOCK SIMULATION** |

---

## 4. Handler Inventory

Analyse des enregistrements dans `app/execution/services/system_handlers.py` et `app/execution/services/reliable_executor.py` :

| Handler | Registry Key (Tool, Op) | Registered in `install_production_handlers`? | Directly Callable? | Authorization Boundary | External Side Effect | Mock/Real | Identified Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `facebook_post_handler` | `("facebook", "post")` | **OUI** (L96) | **OUI** (Fonction Python publique exportée) | `dispatch_authorized_action` vérifie l'autorisation | **NUL** (Log local uniquement) | **MOCK** | Risque d'appel direct non gouverné si importée ailleurs |
| `instagram_post_handler` | `("instagram", "post")` | **OUI** (L97) | **OUI** (Fonction Python publique exportée) | `dispatch_authorized_action` vérifie l'autorisation | **NUL** (Log local uniquement) | **MOCK** | Idem |
| `whatsapp_send_handler` | `("whatsapp", "send")` | **OUI** (L98) | **OUI** (Fonction Python publique exportée) | `dispatch_authorized_action` vérifie l'autorisation | **NUL** (Log local uniquement) | **MOCK** | Idem |
| `twitter_post_handler` | `("twitter", "post")` | **OUI** (L99) | **OUI** (Fonction Python publique exportée) | `dispatch_authorized_action` vérifie l'autorisation | **NUL** (Log local uniquement) | **MOCK** | Idem |
| `discord_send_handler` | `("discord", "send")` | **OUI** (L100) | **OUI** (Fonction Python publique exportée) | `dispatch_authorized_action` vérifie l'autorisation | **NUL** (Log local uniquement) | **MOCK** | Idem |
| `telegram` | *(Non enregistré)* | **NON** | N/A | N/A | N/A | **ABSENT** | Déclaré uniquement dans le portfolio Netlify |
| `linkedin` | *(Non enregistré)* | **NON** | N/A | N/A | N/A | **ABSENT** | Déclaré uniquement dans les documentations |

---

## 5. Execution Pipeline Trace

Traçabilité formelle d'une intention d'action sociale à travers la chaîne de gouvernance :

```text
Objective / Goal Input
  ↓
Task (Task Graph / DAG)
  ↓
Cognitive / Rational Proposition (LLM suggère : tool="whatsapp", operation="send", arguments={...})
  ↓
DomainClassifier (classifier_config.json : "send" → ["communication", "SEND"])
  ↓
DeterministicArbitrator (Politique de domaine : communication/SEND → Risque MEDIUM, Autonomie requise)
  ↓
Verdict Serveur : [ALLOW | DENY | ESCALATE | STOP]
  ↓ (Si ALLOW uniquement)
authorizations.issue_authorization(db, decision, action)
  ↓ (Génération UUID + calcul canonical_fingerprint)
ReliableExecutor.dispatch_authorized_action(db, action, authorization_id, ...)
  ↓ 1. Verrouillage PostgreSQL SELECT ... FOR UPDATE (authorizations.lock_authorization)
  ↓ 2. Évaluation de validité (non révoquée, non expirée, fingerprint intact)
  ↓ 3. Réservation atomique de quota (reservations.reserve_quota)
  ↓ 4. Consommation irréversible de l'autorisation (authorizations.consume_authorization)
  ↓ 5. Prise de bail de tentative (attempts_service.claim_attempt) + COMMIT pré-effet
  ↓ 6. Exécution du Handler résolu : get_action_handler("whatsapp", "send")
  ↓ 7. Appel : whatsapp_send_handler(action)
  ↓ 8. Enregistrement du résultat (SUCCEEDED / FAILED / UNKNOWN) + Audit append-only
```

### Réponse à la Question Critique

> **Existe-t-il un chemin permettant à un agent, Skill, handler ou connector d'exécuter une action sociale sans passer par l'autorisation obligatoire ?**

* **Par le pipeline standard de l'Agent / Goal Engine** : **NON (PROUVÉ)**.
  La boucle autonome `app/goal_engine/services/autonomous_loop.py` (`_execute_step`, L196-L230) appelle obligatoirement `orchestrator.process(...)`, puis vérifie `if decision.outcome != DecisionOutcome.ALLOW: return`. Elle ne délègue à l'exécuteur que via `dispatch_authorized_action(db, action=action, authorization_id=auth.id, ...)`.
* **Par invocation directe de code Python (Vulnérabilité d'architecture interne)** : **OUI (PROUVÉ DANS LE CODE)**.
  Les fonctions `facebook_post_handler`, `whatsapp_send_handler`, etc., dans `app/connectors/social_connectors.py` ne contiennent **aucun contrôle d'autorisation interne** (`assert action.has_valid_authorization`). Si un développeur ou un futur script interne importe `from app.connectors.social_connectors import whatsapp_send_handler` et l'appelle avec un `ActionRecord` quelconque créé en mémoire, la fonction s'exécute sans passer par PostgreSQL ni par le `ReliableExecutor`.

---

## 6. Authorization Boundary

La frontière de sécurité est actuellement positionnée dans `app/execution/services/reliable_executor.py` (`dispatch_authorized_action`) :

1. **Vérification d'appartenance au Workspace (`INV-02`)** :
   ```python
   # reliable_executor.py:159-163
   if caller_workspace_id is not None and caller_workspace_id != action.workspace_id:
       raise AuthorizationError("WORKSPACE_MISMATCH", "Action hors du workspace de l'appelant.")
   ```
2. **Intégrité de l'Empreinte (`INV-03`)** :
   Le hachage SHA-256 recalculé au vol sur `(workspace_id, agent_id, tool, operation, permission_required, objective, arguments)` doit correspondre strictement au `action_fingerprint` scellé dans l'autorisation en base (`authorizations.py:evaluate_validity`).
3. **Consommation Irréversible (`INV-14`)** :
   L'autorisation passe à `is_consumed = True` avant que le handler social ne soit appelé. Une seconde tentative avec la même autorisation échoue avec `ALREADY_CONSUMED`.

---

## 7. INV-01 Analysis : Authorization Before Effect

> **Invariant INV-01** : *« Aucun effet réel externe ne doit se produire avant l'autorisation correspondante. »*

- **Examen de `social_connectors.py`** :
  Actuellement, aucun appel HTTP externe (`httpx.post`, `requests.post`) n'existe. Les effets sont strictement nuls (logs stdout).
- **Architecture de flux futur** :
  L'ordre d'exécution dans `reliable_executor.py` garantit :
  $$\text{Decision} \xrightarrow{\text{ALLOW}} \text{Issue Authorization} \xrightarrow{\text{Lock \& Consume}} \text{Commit Lease} \xrightarrow{\text{Effect}} \text{Record Result}$$
  Il n'existe aucun chemin où un connecteur est déclenché avant la persistance de l'autorisation serveur.
- **Statut INV-01** : **VERIFIED COMPLIANT (Sur le pipeline de gouvernance)**.

---

## 8. ActionRecord / Fingerprint / Idempotency

Vérification des 7 questions fondamentales :

1. **Une publication Facebook possède-t-elle une identité d'action ?**
   **OUI (VERIFIED)** : Représentée par une ligne unique dans la table `actions` avec son `id: UUID` (clé primaire).
2. **Un message WhatsApp possède-t-il une identité d'action ?**
   **OUI (VERIFIED)** : Même structure `ActionRecord`.
3. **Une publication Instagram possède-t-elle une identité d'action ?**
   **OUI (VERIFIED)** : Même structure `ActionRecord`.
4. **Deux retries peuvent-ils publier deux fois ?**
   **NON (VERIFIED)** : La contrainte d'unicité `UniqueConstraint("workspace_id", "idempotency_key", name="uq_actions_workspace_idempotency")` dans `app/execution/models.py` (L111-L113) interdit d'insérer deux actions logiques identiques dans le même workspace. De plus, `authorizations.consume_authorization` empêche la double consommation.
5. **Le fingerprint inclut-il les arguments pertinents ?**
   **OUI (VERIFIED)** : `app/execution/services/fingerprint.py` (L60-L69) sérialise canoniquement `arguments` (avec tri des dictionnaires et listes récursif) ainsi que `tool`, `operation`, `permission_required`, `objective`. Si le destinataire WhatsApp ou le texte du post change, l'empreinte change.
6. **Les réponses externes sont-elles persistées ?**
   **PARTIELLEMENT (VERIFIED)** : `ExecutionResult.provider_reference` est persisté dans `ExecutionResultRecord.provider_reference` (colonne `String(255)`). Mais le JSON brut complet retourné par les API externes n'a pas de colonne dédiée `provider_raw_response: JSON` dans `execution_results`.
7. **Une action déjà exécutée peut-elle être rejouée ?**
   **NON (VERIFIED)** : Si `attempt.status == SUCCEEDED`, le bail est clos et l'autorisation consommée. Tenter de la redispatcher renvoie `ALREADY_CONSUMED` (`authorizations.py:90`).

---

## 9. Permission Analysis

Analyse de la dissociation stricte : **Tool != Permission** et **Skill != Permission** :

1. **Tool availability != Permission** :
   Le fait que `("facebook", "post")` soit enregistré dans `_ACTION_HANDLERS` indique seulement que le serveur sait techniquement exécuter cette opération. Cela ne confère aucun droit à un agent.
2. **Skill required_tools != Permission** :
   Dans le `Skill System` (`app/skills/models.py` et `catalog.py`), un Skill peut déclarer `required_tools: ["whatsapp.send"]`. Cette liste est informative pour le `CognitiveSimulator` et l'agent.
   *Vérification du code* : Dans `app/skills/services/registry.py` et `app/skills/services/selector.py`, **aucun code n'insère de droits ou ne bypass l'Arbitrator**. L'agent formule une intention textuelle qui est classifiée par le `DomainClassifier` et soumise aux politiques serveur du `DeterministicArbitrator`.
3. **Permissions requises déduites** :
   - `whatsapp.send` $\rightarrow$ `PermissionAction.SEND` (Domaine `communication`)
   - `facebook.post` $\rightarrow$ `PermissionAction.PUBLISH` (Domaine `communication`)
   - `instagram.post` $\rightarrow$ `PermissionAction.PUBLISH` (Domaine `communication`)
   - `twitter.post` $\rightarrow$ `PermissionAction.PUBLISH` (Domaine `communication`)
   - `discord.send` $\rightarrow$ `PermissionAction.SEND` (Domaine `communication`)

---

## 10. Skill System Compatibility

Respect des invariants cryptographiques du Skill System :

1. **Règle formelle `SKILL-INV-01` & `SKILL-INV-06`** : *« Un Skill ne donne jamais de permission. »*
   Les compétences sociales futures (ex: `social_media_manager`, `whatsapp_concierge`) ne feront que guider la formulation du prompt LLM.
2. **Règle formelle `SKILL-INV-02` (Monotonie de la délégation)** :
   $$\text{effective\_skills}(\text{child}) \subseteq \text{effective\_skills}(\text{parent})$$
   Si un agent parent ne possède pas le skill `social_media_manager`, aucun sous-agent qu'il instancie ne pourra recevoir ce skill.
3. **Isolation de Workspace (`SKILL-INV-04`)** :
   Les compétences personnalisées sont cloisonnées par `workspace_id` dans la table pivot `workspace_skills`. Un agent d'un client B ne peut pas exécuter un skill privé du client A.

---

## 11. Configuration & Secrets

Audit des variables dans `app/core/config.py` et les fichiers d'environnement :

| Variable | Location | Used by | Secret? | Actually consumed? | Default Value | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `WHATSAPP_API_URL` | `app/core/config.py:30` | Aucun | OUI (URL/Host) | **NON** (0 référence) | `None` | **DECLARED / UNUSED** |
| `WHATSAPP_SESSION_ID` | `app/core/config.py:31` | Aucun | NON (Identifiant) | **NON** (0 référence) | `"rockib_session"` | **DECLARED / UNUSED** |
| `WHATSAPP_API_KEY` | `app/core/config.py:32` | Aucun | OUI (API Key) | **NON** (0 référence) | `None` | **DECLARED / UNUSED** |
| `TWILIO_ACCOUNT_SID` | `app/core/config.py:35` | Aucun | OUI (Identifiant) | **NON** (0 référence) | `None` | **DECLARED / UNUSED** |
| `TWILIO_AUTH_TOKEN` | `app/core/config.py:36` | Aucun | OUI (Secret Token) | **NON** (0 référence) | `None` | **DECLARED / UNUSED** |
| `TWILIO_PHONE_NUMBER` | `app/core/config.py:37` | Aucun | NON (Numéro) | **NON** (0 référence) | `None` | **DECLARED / UNUSED** |
| `OWNER_PHONE_NUMBER` | `app/core/config.py:38` | Aucun | OUI (PII / Téléphone) | **NON** (0 référence) | `None` | **DECLARED / UNUSED** |
| `META_APP_ID` | Absent | N/A | NON | **NON** | N/A | **ABSENT** |
| `META_APP_SECRET` | Absent | N/A | OUI | **NON** | N/A | **ABSENT** |
| `META_ACCESS_TOKEN` | Absent | N/A | OUI | **NON** | N/A | **ABSENT** |
| `META_VERIFY_TOKEN` | Absent | N/A | OUI | **NON** | N/A | **ABSENT** |
| `INSTAGRAM_ACCOUNT_ID` | Absent | N/A | NON | **NON** | N/A | **ABSENT** |
| `FACEBOOK_PAGE_ID` | Absent | N/A | NON | **NON** | N/A | **ABSENT** |

---

## 12. Meta References

Inventaire des mentions de Meta dans le repository :

- **Documentation & PRD** :
  - `PRD_AUTONOMOUS_AGENCY.md:117` : Référence à *« MARTISTORE (martistore.shop) : Vendeur IA WhatsApp + boutique complète en ligne (Flask, Celery, PostgreSQL, Meta Cloud API, Groq, CLIP vision). »*
  - `gemini.md:106` : Étude de cas *« MARTISTORE (Commerce WhatsApp & CLIP) »*.
  - `app/inbound/services/portfolio_handler.py:71` : Présentation du vendeur IA WhatsApp de MARTISTORE.
- **Références d'API / Versions** :
  - Aucune URL de type `graph.facebook.com` en dur dans le code Python actuel.
  - Les versions d'API Meta (ex: v21.0 ou v22.0) n'apparaissent que dans les échanges conceptuels et ne sont pas codées dans l'application.

---

## 13. Inbound / Webhook Analysis

Audit de la réception d'événements externes :

| Platform | GET Verification | POST Receiver | Signature Validation | Deduplication | Persistence | Router | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WhatsApp (Meta Cloud)** | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** | **AUCUN** | **NON IMPLÉMENTÉ** |
| **Instagram DM / Webhook** | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** | **AUCUN** | **NON IMPLÉMENTÉ** |
| **Facebook Messenger** | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** | **AUCUN** | **NON IMPLÉMENTÉ** |
| **Portfolio Concierge** | N/A | `POST /inbound/portfolio/message` | Rate-limiting IP | Mémoire session | PostgreSQL Leads | `app/inbound/router.py` | **OPÉRATIONNEL** |
| **Generic Goal Webhook** | **ABSENT** | `POST /goal_engine/webhooks/trigger` | Clé en clair (`ROCKIB_SECRET_KEY`) | **AUCUNE** | Table `goals` | `app/goal_engine/router.py` | **EXPÉRIMENTAL / RISQUE** |

---

## 14. Escalation Analysis

Analyse du fichier `app/decision_engine/services/escalation.py` :

- **Contenu réel du fichier** : 2 lignes (`"""Service d'escalade (WhatsApp / appel) pour les décisions en attente d'approbation (à implémenter)."""`).
- **Création d'une escalade** :
  Actuellement, lorsqu'une décision est `ESCALATE` par l'Arbitrator, un enregistrement est créé dans la table `decisions` avec `outcome = DecisionOutcome.ESCALATE`.
- **Notification** : **NON IMPLÉMENTÉE**. Rockib n'est notifié ni par WhatsApp ni par Telegram. L'escalade reste visible uniquement par polling SQL ou via le cockpit 3D (`GET /api/v1/decisions`).
- **Reprise après approbation** :
  L'endpoint `POST /api/v1/decisions/{decision_id}/approve` (dans `app/decision_engine/router.py`) permet à un administrateur humain authentifié de délivrer l'approbation via l'interface web, mais aucune passerelle bidirectionnelle WhatsApp (`Tapez 1 pour approuver`) n'existe.

---

## 15. Retry / Concurrency / Failure Analysis

Analyse des 7 scénarios de défaillance réseau et concurrence :

| Scénario | Comportement Actuel | Risque Identifié | Preuve Code |
| :--- | :--- | :--- | :--- |
| **Scenario A : Deux workers reçoivent la même tâche sociale** | Protégé par bail d'exécution exclusif (`claim_attempt` sous lock DB). Le second worker échoue avec `ALREADY_CLAIMED`. | Faible sur la tâche. | `attempts.py:45-75` |
| **Scenario B : Meta répond lentement (> timeout)** | Si `timeout_seconds` expire, `reliable_executor.py:220-227` intercepte `asyncio.TimeoutError` et classe l'effet en `EffectCertainty.unknown`. | Risque de timeout prématuré si l'API externe est lente. | `reliable_executor.py:220` |
| **Scenario C : Coupure réseau post-envoi Meta** | L'exception réseau est capturée (`reliable_executor.py:228-235`), classée en `EffectCertainty.unknown`. L'action n'est **JAMAIS rejouée à l'aveugle** (`INV-09`). | Conforme à l'invariant. Requiert une réconciliation manuelle ou un query de statut. | `reliable_executor.py:234` |
| **Scenario D : Rockib retry la même action** | L'idempotence bloque : `authorizations.consume_authorization` empêche de réutiliser l'autorisation. | Conforme à l'invariant. | `authorizations.py:85` |
| **Scenario E : Deux agents demandent exactement le même post** | L'insertion dans la table `actions` échoue pour le second agent si même `(workspace_id, idempotency_key)`. Si les clés diffèrent, les deux s'exécutent. | Double publication possible si deux agents indépendants formulent des `idempotency_scope` différents. | `models.py:112` |
| **Scenario F : Un webhook entrant est reçu deux fois** | Aucun système de déduplication de webhook (par `entry[0].id` ou `message.mid`) n'existe actuellement. | Risque critique de double prise en compte d'un message entrant. | `app/inbound/` |
| **Scenario G : Crash worker post-effet pré-commit** | Le commit pré-effet (`reliable_executor.py:210`) garantit que la tentative est enregistrée `RUNNING`. Au redémarrage, elle est réconciliable. | Géré par la conception Phase 2. | `reliable_executor.py:210` |

---

## 16. Rate Limiting

- **Au niveau global / connecteurs externes** : **ABSENT**. Aucun token bucket, aucun circuit-breaker, aucune gestion des en-têtes HTTP 429 (`Retry-After`) n'est codé pour les API tierces.
- **Au niveau de l'Inbound Portfolio** : **EXISTS**. Un dictionnaire glissant en mémoire (`PortfolioConciergeService._rate_limits`) limite les messages entrants à 20 requêtes par minute par adresse IP (`portfolio_handler.py:116`).

---

## 17. Observability / Auditability

- **Logs & Traces** :
  Toute exécution via `ReliableExecutor` crée une entrée dans la table `execution_attempts` et `execution_results`.
- **Table d'Audit Append-Only (`audit_entries`)** :
  Protégée par des triggers PostgreSQL interdisant tout `UPDATE` ou `DELETE`. Événements journalisés : `CONTROL_EVALUATED`, `AUTHORIZATION_ISSUED`, `AUTHORIZATION_CONSUMED`, `EFFECT_CONFIRMED`, `EFFECT_UNKNOWN`.
- **Réponse à la question d'audit** :
  > *Peut-on reconstruire après coup exactement pourquoi Rockib AI a publié/envoyé quelque chose ?*
  **OUI (VERIFIED)** : La corrélation `action.id` $\leftrightarrow$ `decision.id` $\leftrightarrow$ `task.id` $\leftrightarrow$ `goal.id` permet de remonter l'objectif racine, la recommandation du LLM, l'arbitrage déterministe et l'horodatage exact.

---

## 18. Workspace / Credential Isolation

- **État Actuel** : **CRITICAL GAP**.
  Il n'existe aucune colonne `workspace_id` pour les identifiants d'API externes dans la configuration. Si des clés Meta ou WhatsApp sont injectées dans les variables d'environnement globales (`app/core/config.py`), **tous les workspaces et tous les agents partagent les mêmes identifiants**.
- **Risque de contamination croisée** :
  Un agent opérant pour le client du *Workspace Alpha* pourrait envoyer un message WhatsApp ou publier sur la Page Facebook configurée globalement pour le propriétaire ou pour un autre client.

---

## 19. Existing Test Coverage

Audit de la suite de tests automatisée :

- **Résultat de la commande réelle** :
  `python -m pytest --ignore=tests/test_celery_tasks.py -q`
  **Sortie** : `449 passed, 1041 warnings in 52.57s` (100% verts).
- **Couverture des connecteurs sociaux** :
  - `tests/test_connectors.py` : Teste **uniquement** `fs_read_handler` (path traversal, existence de fichier). **Zéro test sur les réseaux sociaux**.
  - `tests/test_system_handlers.py` : Teste `system_read_handler`, le registry d'actions et `dispatch_authorized_action`. **Zéro test sur les réseaux sociaux**.
  - `tests/test_inbound_voice_call.py` : Teste la simulation de demande de rappel téléphonique/WhatsApp (validation de schéma).
- **Constat formel** : **Il existe 0 test unitaire ou d'intégration exécutant ou validant `facebook_post_handler`, `instagram_post_handler`, `whatsapp_send_handler`, `twitter_post_handler`, ou `discord_send_handler`.**

---

## 20. Missing Test Matrix

Matrice des tests obligatoires avant toute activation réelle :

| Test ID | Catégorie | Scénario | Invariant Attendu | Priorité |
| :--- | :--- | :--- | :--- | :--- |
| `TEST-SOC-01` | Unit | Validation des arguments manquants pour chaque handler social | Rejet propre avec `ExecutionResult(success=False)` | **HAUTE** |
| `TEST-SOC-02` | Authorization | Tentative d'exécution d'un handler social avec une autorisation révoquée | Rejet immédiat avec `AuthorizationError("REVOKED")` | **CRITIQUE** |
| `TEST-SOC-03` | Security | Isolation multi-workspace des credentials sociaux | Refus d'accès au token d'un autre workspace | **CRITIQUE** |
| `TEST-SOC-04` | Idempotency | Double appel du même envoi WhatsApp avec même `idempotency_key` | Un seul envoi réel au fournisseur, second rejeté ou résultat en cache | **CRITIQUE** |
| `TEST-SOC-05` | Failure | Simulation HTTP 429 (Rate Limit) de l'API Meta | Transition vers `UNKNOWN` ou retry avec backoff sans crash | **HAUTE** |
| `TEST-SOC-06` | Failure | Simulation HTTP 500 / Timeout ambigu pendant l'appel Meta | Invariant `INV-09` respecté : pas de répétition aveugle | **CRITIQUE** |
| `TEST-SOC-07` | Webhook | Vérification de la signature HMAC SHA-256 (`x-hub-signature-256`) | Rejet immédiat HTTP 403 si signature invalide | **CRITIQUE** |
| `TEST-SOC-08` | Webhook | Réception d'un doublon de webhook Meta (`mid` déjà vu) | Acquittement HTTP 200 sans déclencher de second Goal | **HAUTE** |
| `TEST-SOC-09` | Injection | Message WhatsApp contenant une tentative de prompt injection | Strictement traité comme `USER_DATA` non privilégié | **CRITIQUE** |

---

## 21. Threat Model (Mini-Threat Model Connecteurs Sociaux)

| ID | Menace | Surface d'Attaque | Contrôle Existant | Gap Actuel | Sévérité | Preuve Code |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **T1** | Fuite de tokens API | Logs applicatifs, ActionRecord, Sentry | Aucun token réel chargé | Aucun masque de secret dans `ActionRecord.arguments` | **HIGH** | `app/connectors/social_connectors.py` |
| **T2** | Action externe non autorisée | Appel direct de handler sans passer par l'arbitre | `ReliableExecutor` vérifie l'autorisation | Les fonctions handler sont publiques et directement importables | **MEDIUM** | `reliable_executor.py:168` |
| **T3** | Escalade de privilèges via Skill | Déclaration `required_tools: ["whatsapp.send"]` | Le Skill System ne délivre aucune permission | Aucun gap : le design neutralise cette menace | **LOW** | `app/skills/services/registry.py` |
| **T4** | Crossover d'identifiants entre Workspaces | Paramètres globaux partagés | Aucun pour les secrets sociaux | Pas de table de credentials partitionnée par workspace | **CRITICAL** | `app/core/config.py:30-38` |
| **T5** | Replay d'action déjà autorisée | Réutilisation d'un `authorization_id` | `authorizations.consume_authorization` | Aucun gap : consommation atomique sous lock | **LOW** | `authorizations.py:75-95` |
| **T6** | Double publication accidentelle | Retry réseau en cas de timeout Meta | Invariant `INV-09` (`EffectCertainty.unknown`) | Absence d'identifiant d'idempotence client transmis à l'API Meta | **HIGH** | `social_connectors.py` |
| **T7** | Usurpation de Webhook Inbound | Requêtes forgées sur l'endpoint FastAPI | Aucune validation de signature Meta codée | Absence du header `x-hub-signature-256` | **CRITICAL** | `app/goal_engine/router.py:742` |
| **T8** | Replay de Webhook Inbound | Réémission du même payload Meta valide | Aucune déduplication sur l'ID de message | Risque de ré-exécution en boucle | **HIGH** | `app/goal_engine/router.py` |
| **T9** | Injection de prompt via message entrant | Contenu de message WhatsApp transmis au LLM | Le LLM propose, l'Arbitre décide | Le texte entrant pourrait manipuler la description de l'intention | **HIGH** | `app/inbound/services/portfolio_handler.py` |
| **T10** | Contenu social diffamatoire ou illicite | Post généré par l'IA et publié directement | Arbitrage humain (`ESCALATE`) si risque haut | Politiques d'arbitrage à calibrer sur la communication externe | **MEDIUM** | `app/decision_engine/classifier_config.json` |

---

## 22. Prompt Injection via Social Media

Analyse du traitement des entrées non fiables :

- **Constat** : Un message WhatsApp entrant est une **donnée brute non sécurisée (`USER_DATA`)**.
- **Séparation Donnée vs Instruction** :
  Dans l'état actuel de la passerelle Inbound (`app/inbound/services/portfolio_handler.py:126-150`), le message du visiteur est inséré dans un prompt système structuré :
  ```python
  prompt = f"Tu es l'agent d'accueil... Question du visiteur : {user_message}"
  ```
  Le modèle Groq répond directement sans exécuter d'outil.
- **Principe de Préservation** :
  Si un message entrant demande une action privilégiée (*« Efface la base de données »* ou *« Publie un message frauduleux sur Facebook »*), l'action proposée par le LLM est obligatoirement soumise au `DomainClassifier` et au `DeterministicArbitrator`.
  - L'action `delete` sera classée `system.DELETE` $\rightarrow$ Risque `CRITICAL` $\rightarrow$ Escalade obligatoire ou rejet (`DENY`).
  - **Preuve formelle** : *Aucune entrée utilisateur externe ne peut débloquer une autorisation sans validation du serveur.*

---

## 23. INV-01 ... INV-16 Non-Regression

Évaluation de l'impact des connecteurs sociaux sur la suite des invariants du système :

| Invariant | Intitulé Formel | Impact Connecteur Social | Niveau de Risque | Preuve Code |
| :--- | :--- | :--- | :--- | :--- |
| **INV-01** | Aucun effet sans autorisation valide | Nul si appelé via `ReliableExecutor`. | **CONFORME** | `reliable_executor.py:168` |
| **INV-02** | Isolation du workspace | **ÉLEVÉ** sur les credentials (manque de scoping par workspace). | **RISQUE CRITIQUE** | `app/core/config.py` |
| **INV-03** | Action arbitrée immuable | Nul : toute modification d'argument brise l'empreinte SHA-256. | **CONFORME** | `fingerprint.py:82` |
| **INV-04** | Risque transmis et non abaissé | Nul : l'Arbitrator applique le risque calculé par les règles et le `RiskAnalyst`. | **CONFORME** | `arbitrator.py:65` |
| **INV-05** | Autonomie zéro préservée | Nul : l'autonomie appliquée est régie par `min(requested, allowed)`. | **CONFORME** | `arbitrator.py:110` |
| **INV-06** | Autorité extérieure au LLM | Nul : l'IA ne peut jamais auto-signer une autorisation. | **CONFORME** | `authorizations.py:25` |
| **INV-07** | Délégation restrictive | Nul : un sous-agent ne peut excéder les outils du parent. | **CONFORME** | `app/skills/services/selector.py` |
| **INV-08** | Budget partagé / Anti-doublon | Nul : `uq_actions_workspace_idempotency` protège l'opération logique. | **CONFORME** | `models.py:112` |
| **INV-09** | Pas de répétition aveugle | Nul : Timeout ambigu produit `EffectCertainty.unknown`. | **CONFORME** | `reliable_executor.py:220` |
| **INV-10** | États terminaux protégés | Nul : Tâche `COMPLETED` ne peut être réexécutée silencieusement. | **CONFORME** | `app/goal_engine/models.py` |
| **INV-11** | Audit durable | Nul : Table `audit_entries` append-only enregistre la tentative et le résultat. | **CONFORME** | `app/execution/services/audit.py` |
| **INV-12** | Succès vérifiable | Nul : Résultat observable persisté dans `execution_results`. | **CONFORME** | `reliable_executor.py:247` |
| **INV-13** | Boucle bornée | Nul : Compteurs de pas du Goal Engine appliqués. | **CONFORME** | `autonomous_loop.py` |
| **INV-14** | Révocation effective | Nul : Autorisation révoquée détectée avant l'appel d'outil. | **CONFORME** | `authorizations.py:115` |
| **INV-15** | Reprise cohérente | Nul : Crash de worker pendant l'appel laisse l'état en `RUNNING` inspectable. | **CONFORME** | `reliable_executor.py:210` |
| **INV-16** | Autonomie effective | Nul : Action pré-autorisée conforme exécutée sans confirmation si autonomie $\ge$ niveau requis. | **CONFORME** | `arbitrator.py:125` |

---

## 24. Target Architecture — Design Only (Aucun Code)

### Architecture Conceptuelle Cible — Outbound (Sortant)

```text
[Skill System]
      ↓ fournit les connaissances métier (méthode de rédaction, ton)
[Agent LLM]
      ↓ propose l'intention formelle (tool="whatsapp", operation="send", arguments={to, text})
[DomainClassifier]
      ↓ classifie en domaine "communication", permission "SEND"
[DeterministicArbitrator]
      ↓ applique les règles : Risque MEDIUM, Autonomie requise
[Authorization Engine]
      ↓ délivre l'ExecutionAuthorization (SHA-256 scellé, statut ALLOW)
[ReliableExecutor]
      ↓ lock autorisation, réserve quota, consomme autorisation, pose le bail d'attempt
[Credential Vault Scoped]
      ↓ lookup sécurisé du token Meta/WhatsApp pour le workspace_id spécifique
[Real Meta Connector]
      ↓ validation payload, appel HTTP POST avec timeout strict et header d'idempotence
[External Meta API (Graph / Cloud)]
      ↓ retour HTTP 200 (message_id) ou HTTP 4xx/5xx
[ReliableExecutor Record]
      ↓ persistance de EffectCertainty.confirmed ou EffectCertainty.unknown + Audit Append-Only
```

### Architecture Conceptuelle Cible — Inbound (Entrant)

```text
[External Meta Platform (WhatsApp / Messenger / Instagram)]
      ↓ POST Webhook avec signature HMAC SHA-256 dans l'en-tête
[FastAPI Inbound Router]
      ↓ 1. Vérification cryptographique de la signature (hmac.compare_digest)
      ↓ 2. Extraction du message_id unique et vérification anti-rejeu (Redis / DB)
      ↓ 3. Normalisation canonique en Untrusted Inbound Event
[Goal Engine / Inbound Dispatcher]
      ↓ Création d'une tâche de traitement non privilégiée
[Decision Engine & Execution Pipeline]
      ↓ Même gouvernance stricte pour toute action sortante consécutive
```

---

## 25. Future Connector Contract (Design Only)

Tout connecteur réel devra impérativement implémenter le contrat suivant :

1. **Entrée Normalisée** : Accepte un `ActionRecord` immuable validé côté serveur.
2. **Isolation des Identifiants** : Ne lit aucun token depuis l'environnement global ; utilise un service de résolution `get_workspace_credential(workspace_id, provider)`.
3. **Validation Pré-vol Locale** : Valide les formats stricts (ex: numéro E.164 international pour WhatsApp, URL HTTPS valide pour Instagram) avant tout appel réseau.
4. **Idempotence Distribuée** : Transmet l'identifiant d'idempotence au fournisseur externe (si supporté) pour interdire le doublon physique en cas de retry.
5. **Timeouts Bornés & Non-Bloquants** : Timeout d'appel HTTP strict ($\le 10$ secondes) encapsulé dans `asyncio.wait_for`.
6. **Normalisation des Erreurs** :
   - HTTP 401/403 $\rightarrow$ `INVALID_CREDENTIALS` (effet nul).
   - HTTP 429 $\rightarrow$ `RATE_LIMITED` (effet nul, requiert backoff).
   - Timeout / HTTP 502/503/504 $\rightarrow$ `EffectCertainty.unknown` (effet incertain, jamais rejoué aveuglément).
   - HTTP 200 $\rightarrow$ `EffectCertainty.confirmed` avec stockage du `provider_reference`.

---

## 26. Recommended Implementation Sequence

Ordre logique d'implémentation fondé sur les dépendances techniques :

1. **PHASE A : Abstraction des Identifiants par Workspace (Credential Vault)**
   - Créer le modèle de stockage chiffré des secrets tiers (`workspace_credentials`) lié à `workspace_id`.
   - Garantir l'étanchéité multi-tenant (`INV-02`).
2. **PHASE B : Contrat d'Exécution & Connecteur Outbound WhatsApp Réel**
   - Implémenter le vrai client HTTP asynchrone pour Meta Cloud API.
   - Brancher la résolution dynamique des credentials.
   - Écrire la suite de tests unitaires et mocks HTTP (`pytest-mock` / `respx`).
3. **PHASE C : Webhook Inbound Meta Sécurisé**
   - Implémenter le GET challenge (`hub.challenge`, `hub.verify_token`).
   - Implémenter le POST receiver avec validation stricte HMAC SHA-256 (`x-hub-signature-256`).
   - Implémenter le cache de déduplication des messages entrants.
4. **PHASE D : Connecteurs Outbound Instagram & Facebook (Meta Graph API)**
   - Publications de médias Instagram (création de container + publication).
   - Publications sur Page Facebook.
5. **PHASE E : Passerelle d'Escalade Interactive**
   - Compléter `app/decision_engine/services/escalation.py` pour envoyer les demandes d'arbitrage sur le WhatsApp de l'administrateur avec validation par callback signé.

---

## 27. GO / NO-GO Criteria

| Critère | Seuil Requis | Statut Actuel | Verdict |
| :--- | :--- | :--- | :--- |
| **Isolation Multi-Workspace des Secrets** | Tokens stockés par `workspace_id` chiffré | Variables globales statiques | **NO-GO** |
| **Validation Cryptographique Webhooks** | Vérification HMAC SHA-256 obligatoire | Absent (clé en clair `ROCKIB_SECRET_KEY`) | **NO-GO** |
| **Couverture de Tests des Connecteurs** | Tests unitaires avec mocks d'erreurs HTTP | 0 test sur les connecteurs sociaux | **NO-GO** |
| **Gestion des Réponses Incertaines** | Respect strict de `INV-09` (`unknown`) | Opérationnel dans `ReliableExecutor` | **GO** |
| **Conformité Arbitrage Déterministe** | Respect strict de `INV-01` et `INV-06` | 100% vérifié (449 tests verts) | **GO** |
| **Statut Global pour Production Réelle** | Tous les critères au vert | 3 critères majeurs bloquants | **NOT READY FOR PRODUCTION** |

---

## 28. Findings

### FINDING-SOC-001

Severity: CRITICAL  
Category: Workspace Isolation / Credential Management  
Status: VERIFIED  
File: `app/core/config.py`  
Symbol: `Settings.WHATSAPP_API_URL`, `Settings.WHATSAPP_API_KEY`  
Evidence: `app/core/config.py:30-33`

Description:
Les variables d'authentification pour les services externes sont déclarées au niveau global de l'application dans `Settings`. Il n'existe aucun modèle en base de données permettant de rattacher un compte WhatsApp, Facebook ou Instagram à un `workspace_id`.

Impact:
Violation potentielle de l'invariant `INV-02` (Isolation de workspace) : si un token est renseigné, tous les agents de tous les workspaces utiliseront le même compte externe, provoquant des fuites d'actions entre clients.

Recommendation:
Créer un modèle relationnel `WorkspaceCredential` sécurisé et chiffré associant `workspace_id`, `provider` et les tokens d'accès.

Modification performed:
NO

---

### FINDING-SOC-002

Severity: CRITICAL  
Category: Inbound Security / Webhook Spoofing  
Status: VERIFIED  
File: `app/goal_engine/router.py`  
Symbol: `webhook_trigger`  
Evidence: `app/goal_engine/router.py:742-743` (`if payload.api_key != "ROCKIB_SECRET_KEY": raise HTTPException(...)`)

Description:
L'unique endpoint de webhook générique du Goal Engine utilise une clé API en dur écrite en clair dans le code (`ROCKIB_SECRET_KEY`) sans vérification de signature cryptographique HMAC ni déduplication.

Impact:
Vulnérabilité critique aux attaques par rejeu et usurpation d'identité. Non conforme aux spécifications de sécurité des webhooks Meta (`x-hub-signature-256`).

Recommendation:
Remplacer cette vérification par une signature HMAC sécurisée via `hmac.compare_digest` et créer des routeurs dédiés pour les payloads normalisés des plateformes externes.

Modification performed:
NO

---

### FINDING-SOC-003

Severity: HIGH  
Category: Testing / Reliability  
Status: VERIFIED  
File: `tests/test_connectors.py`  
Symbol: Suite de tests des connecteurs  
Evidence: `tests/test_connectors.py:1-105`

Description:
Les fonctions de connecteurs sociaux déclarées dans `app/connectors/social_connectors.py` ne font l'objet d'aucun test unitaire ou d'intégration dans la suite de tests officielle.

Impact:
Aucune garantie automatisée sur le comportement des connecteurs en cas de payload invalide ou de transition d'état.

Recommendation:
Développer une suite de tests unitaires complète couvrant les cas nominaux et d'erreur pour chaque connecteur.

Modification performed:
NO

---

### FINDING-SOC-004

Severity: MEDIUM  
Category: Architecture / Handler Direct Invocation  
Status: VERIFIED  
File: `app/connectors/social_connectors.py`  
Symbol: `facebook_post_handler`, `whatsapp_send_handler`, etc.  
Evidence: `app/connectors/social_connectors.py:14-71`

Description:
Les handlers sociaux sont des fonctions coroutines asynchrones publiques qui ne vérifient pas la présence ou la validité de l'autorisation au sein de leur propre corps, comptant exclusivement sur l'appelant `dispatch_authorized_action`.

Impact:
Si un développeur ou un agent interne invoque directement la fonction sans passer par le `ReliableExecutor`, l'effet externe (lorsqu'il sera réel) se produira sans trace d'autorisation.

Recommendation:
Encapsuler les handlers dans une couche de garde stricte exigeant un objet de contexte d'autorisation validé ou rendre les fonctions privées au module d'exécution.

Modification performed:
NO

---

### FINDING-SOC-005

Severity: LOW  
Category: Dead Code / Unused Configuration  
Status: VERIFIED  
File: `app/connectors/whatsapp.py`, `app/connectors/twilio.py`, `app/connectors/n8n.py`  
Symbol: Modules stubs  
Evidence: Fichiers de 2 lignes contenant uniquement une docstring

Description:
Plusieurs fichiers de connecteurs existent sous forme de squelettes vides non branchés.

Impact:
Confusion potentielle sur le niveau d'avancement du système sans impact sur la sécurité.

Recommendation:
Consolider les connecteurs dans une architecture unifiée lors de la phase d'implémentation.

Modification performed:
NO

---

## 29. Critical Risks

1. **Risque de Fuite Multi-Workspace (Tenant Crossover)** :
   Tant que les clés d'API externes ne sont pas partitionnées par `workspace_id`, brancher un token Meta réel exposerait le système à ce qu'un agent client publie sur le compte officiel de Rockib ou d'un autre client.
2. **Risque de Facturation & Bannissement Fournisseur (Quota & Rate Limit)** :
   L'absence d'un limiteur de débit sortant (rate limiter) et d'un circuit-breaker vers l'API Meta Graph pourrait entraîner le bannissement temporaire ou définitif du numéro WhatsApp Business en cas de boucle d'agent non maîtrisée.
3. **Risque d'Exécution de Webhooks Forgés** :
   L'absence de validation `x-hub-signature-256` permettrait à un attaquant distant d'injecter de faux messages WhatsApp ou commentaires pour déclencher des tâches dans le Goal Engine.

---

## 30. Unknowns

1. **Type de Compte WhatsApp Cible (Cloud API vs On-Premises Gateway)** :
   Le repository contient à la fois des références à `Meta Cloud API` (PRD) et à `WHATSAPP_API_URL` (VPS WhatsApp-Web / Baileys). Le choix d'infrastructure définitif n'est pas formalisé dans le code.
2. **Niveau de Permission Requis par Métier** :
   Les seuils d'arbitrage exacts (niveau de risque et autonomie) pour autoriser un post Facebook ou un envoi de message WhatsApp sans escalade humaine devront être validés dans les politiques de domaine de production.

---

## 31. Final Verdict

```text
Repository state:
STABLE & TESTED (449/449 tests passing, 100% green). All core governance, arbitrator, reliable executor, goal engine, and skill systems are verified and operational.

Social connector state:
100% MOCK / SIMULATION. Handlers are registered in system_handlers.py but only perform local logging and asyncio.sleep(1.0). Zero real network calls exist.

Authorization state:
VERIFIED COMPLIANT (INV-01). The ReliableExecutor strictly enforces server-issued authorization before calling any registered handler. Direct execution is blocked on the governed path.

Webhook state:
NOT IMPLEMENTED FOR META. No verification of hub.challenge or HMAC SHA-256 signatures exists for WhatsApp, Instagram, or Facebook.

Security state:
SECURE ON CURRENT FOOTPRINT, BUT BLOCKED FOR REAL CREDENTIALS due to the absence of workspace-scoped secret management.

Idempotency state:
VERIFIED COMPLIANT ON DB LEVEL. UniqueConstraint on (workspace_id, idempotency_key) and canonical SHA-256 fingerprinting prevent duplicate logical operations.

Workspace isolation state:
ENFORCED ON INTERNAL ARTIFACTS (INV-02), ABSENT ON EXTERNAL CREDENTIALS (Finding SOC-001).

Skill compatibility:
VERIFIED COMPLIANT. Skills do not confer permissions; tool requirements remain non-authoritative.

Implementation readiness:
NOT READY FOR PRODUCTION / READY FOR ARCHITECTURAL STAGING.

Critical blockers:
1. Absence of WorkspaceCredential table for isolated multi-tenant API tokens.
2. Absence of HMAC SHA-256 signature verification for inbound Meta webhooks.
3. Zero test coverage on social connector modules.

Non-blocking gaps:
1. Stub files (whatsapp.py, twilio.py, n8n.py) to be consolidated.
2. Rate-limiter and circuit-breaker for external Graph API calls.

Unknowns:
1. Definitive selection between Meta Cloud API and VPS Baileys gateway for WhatsApp.
2. Production threshold calibration for automated social publishing permissions.

Verdict:
AUDIT COMPLETE — ZERO MODIFICATION PERFORMED. SYSTEM IS FULLY GOVERNED BUT CANNOT BE CONNECTED TO REAL SOCIAL NETWORKS BEFORE RESOLVING THE 3 CRITICAL BLOCKERS (CREDENTIAL VAULT, WEBHOOK HMAC VALIDATION, UNIT TEST SUITE).
```
