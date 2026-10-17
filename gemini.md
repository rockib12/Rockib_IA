# 🤖 Rockib_ia - Journal de Bord & État du Projet

Ce document sert de source de vérité pour l'état actuel de Rockib AI. Il est mis à jour après chaque étape majeure de conception ou d'implémentation.

## 🎯 Objectif du Projet
Implémenter un système d'arbitrage déterministe et une boucle autonome d'agents IA permettant de décider si une action proposée peut être exécutée automatiquement ou doit être escaladée vers un humain, en se basant sur le risque, l'autonomie et des politiques configurables par domaine.

---

## 🏗️ Architecture Globale

**Flux de données :**
`HTTP Request / UI` $\rightarrow$ `Nginx Reverse Proxy` $\rightarrow$ `Router` $\rightarrow$ `DecisionOrchestrator` $\rightarrow$ `DomainClassifier` $\rightarrow$ `Cognitive/Intelligence Services` $\rightarrow$ `DeterministicArbitrator` $\rightarrow$ `ReliableExecutor` $\rightarrow$ `Persistence (Postgres/Redis)` $\rightarrow$ `Response`

### 1. DomainClassifier (Opérationnel ✅)
- **Rôle** : Transformer une intention textuelle en clés de politique.
- **Contrat** : `(proposed_action, objective, situation)` $\rightarrow$ `(domain, permission_action, status)`.
- **Statuts** : `CERTAIN`, `AMBIGUOUS`, `UNKNOWN`, `ERROR`.
- **Règle de sécurité** : Seuls les résultats `CERTAIN` sont envoyés à l'Arbitrator. Tout état incertain escalade immédiatement.

### 2. DeterministicArbitrator (Opérationnel ✅)
- **Rôle** : Appliquer les règles de risque et d'autonomie sans effets de bord.
- **Logique d'autonomie** : `applied_autonomy_level = min(requested_autonomy_level, allowed_autonomy_level)`.
- **Règles d'arbitrage** : `cognitive_wins`, `intelligence_wins`, `consensus_required`, `escalate`.
- **Déclencheurs d'approbation** : Désaccord > seuil, Risque High/Critical, Irréversibilité, Règle d'escalade, ou Permission `DELETE`.

### 3. Services d'Opinion & Intelligence (Opérationnel ✅)
- **Cognitive Simulator** : Analyse l'intention et simule l'action $\rightarrow$ `suggested_action`, `confidence`.
- **Intelligence Service** : Évalue la rationalité (`RationalAgent`) et le risque (`RiskAnalyst`) via Groq LLM avec garde-fous stricts.

### 4. Reliable Executor (Opérationnel ✅)
- **Rôle** : Exécution transactionnelle et traçabilité des actions (`system_handlers`, connecteurs web, api, fs).

### 5. Goal Engine & Autonomous Loop (Opérationnel ✅)
- **Rôle** : DAG de tâches, planification, machine à états (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `ESCALATED`), orchestration de sous-agents, scheduler externe Celery Beat (`dispatch_active_goals`) et workers Celery (`wake_goal_task`).


### 6. Conteneurisation & Stack Déploiement (Opérationnel ✅)
- **Architecture unifiée All-in-One** : Image Docker unique intégrant le Frontend React/Vite compilé, le Backend FastAPI, et Nginx comme reverse-proxy et serveur de fichiers statiques avec Supervisord.


---

## 📊 État des Composants

| Composant | État | Fichier | Note |
| :--- | :--- | :--- | :--- |
| **Models** | ✅ Opérationnel | `app/decision_engine/models.py`, `app/identity/models.py` | Schémas SQLAlchemy et Enums |
| **Schemas** | ✅ Opérationnel | `app/decision_engine/schemas.py`, `app/goal_engine/schemas.py` | Pydantic (Request/Response) |
| **Classifier** | ✅ Opérationnel | `app/decision_engine/services/domain_classifier.py` | Mapping keyword $\rightarrow$ domain |
| **Arbitrator** | ✅ Opérationnel | `app/decision_engine/services/arbitrator.py` | Logique déterministe pure |
| **Orchestrator**| ✅ Opérationnel | `app/decision_engine/services/orchestrator.py` | Coordination complète du flux |
| **Routers** | ✅ Opérationnel | `app/decision_engine/router.py`, `app/goal_engine/router.py`, `app/identity/router.py` | Endpoints REST v1 |
| **Cognitive** | ✅ Opérationnel | `app/cognitive/services/simulation.py` | Simulation cognitive |
| **Intelligence**| ✅ Opérationnel | `app/intelligence/services/intelligence_service.py` | Intégration LLM (Groq) |
| **Execution** | ✅ Opérationnel | `app/execution/services/reliable_executor.py` | Exécution avec idempotence et baux |
| **Credentials**| ✅ Opérationnel | `app/credentials/models.py`, `app/credentials/services/vault.py` | Coffre-fort de secrets multi-tenant chiffré AEAD AES-256-GCM |
| **Skills**    | ✅ Opérationnel | `app/skills/models.py`, `app/skills/schemas.py`, `app/skills/services/registry.py`, `app/skills/services/selector.py` | Modèles relationnels, hachage SHA-256, registre et sélection JIT |
| **Catalog**   | ✅ Opérationnel | `app/skills/catalog.py` | Les 5 skills scellés (Portfolio Ambassador, Lead Qualif, React 19, Django 5.2, Cyberdéfense) |
| **Inbound**   | ✅ Opérationnel | `app/inbound/router.py`, `app/inbound/services/portfolio_handler.py`, `app/inbound/services/voice_call_service.py` | Gateway public pour widget portfolio, Voice Calling, capture de leads et rappels téléphoniques pour Agence IIA |
| **Widget JS** | ✅ Opérationnel | `frontend/public/rockib-concierge.js` | Chatbot flottant & Appel vocal direct in-browser (Web Speech) + demande de rappel |
| **Frontend**  | ✅ Opérationnel | `frontend/` | Cockpit 3D Three.js, DAG Panel, Agents Cards |
| **Docker**    | ✅ Opérationnel | `Dockerfile`, `docker-compose.yml`, `nginx.conf`, `supervisord.conf` | Image unifiée Front + Back + Nginx |

---

## 🧪 Statut des Tests
- **686 tests unitaires et d'intégration réussis (100% verts, 0 warning)** :
  - `tests/test_system_handlers.py` & `tests/test_connectors.py` ✅ *(Connecteurs production, dont `content.create` sandboxed, zero-spend)*
  - `tests/test_celery_tasks.py` & `tests/test_wake_runner.py` ✅ *(Boucle de réveil Celery Beat et workers)*
  - `tests/test_security_hardening.py` ✅ *(37 tests : Hardening P0/P1/P4/P5/P6/P7 — Telegram Webhook Secret, SSRF & DNS resolution + immunité DNS Rebinding par épinglage IP socket, Credential Vault fail-fast, Auth & Multi-tenant isolation sur `/api/v1/decisions/`, CSP Sandbox `/preview/`, Anti-Bruteforce Auth, `X-Request-ID`, TTL Sessions, Rate-Limiting Vocal, Healthcheck DB/Redis & Validation stricte Pydantic)*
  - `tests/test_goal_engine_auth.py` ✅ *(27 tests : Authentification OAuth2/JWT sur tous les endpoints Goal Engine, isolation stricte multi-tenant 403/404, URLs signées HMAC-SHA256 avec TTL 1h et domaine séparé, prévention anti-énumération)*
  - `tests/test_skill_system.py` ✅ *(47 tests : 107 Skills Catalog, scellement SHA-256, Core 5 immuables, Registry, Selector JIT, dépendances DAG, exclusion mutuelle, priorisation déterministe workspace/system, alignement enum SkillCategory)*
  - `tests/test_agent_connectors.py` & `tests/test_goal_manager.py` ✅ *(Autonomie hiérarchique bornée strictement : parent >= enfant, scénarios 1 à 5 + test adversarial)*
  - `tests/test_workspace_credentials.py` ✅ *(Vault multi-tenant, chiffrement AEAD AES-256-GCM, isolation TEST-SOC-03 & tamper rejection)*
  - `tests/test_telegram_integration.py` ✅ *(Bot interactif, inline keyboard approval, recherche temps réel)*
  - `tests/test_inbound_voice_call.py` ✅ *(Appels vocaux in-browser, TTS sans markdown & rappel téléphonique/WhatsApp)*
  - `tests/test_inbound_portfolio.py` ✅ *(Tests E2E de la passerelle portfolio, capture lead & rate limiting)*
  - `tests/test_arguments_pipeline.py` ✅
  - `tests/test_fs_write.py` ✅
  - `tests/test_domain_classifier.py` ✅
  - `tests/test_arbitrator.py` ✅
  - `tests/test_auth.py` ✅
  - `tests/test_orchestrator.py` ✅
  - `tests/test_intelligence_service.py` & `tests/test_intelligence_wiring.py` ✅
  - `tests/test_groq_provider.py` ✅
  - `tests/test_autonomous_loop_wake.py` ✅
  - `tests/test_execution_reliable.py` & `tests/test_execution_integration.py` ✅
  - `tests/test_goal_manager.py` & `tests/test_goal_model.py` ✅

---

## 🚀 Dernières Résolutions (Skill System & Agence Multi-Agents IIA)
1. **Implémentation Complète du Skill System** :
   - Tables relationnelles (`skills`, `skill_versions`, `workspace_skills`, `agent_skills`) créées via la migration Alembic `010_create_skill_system_tables.py`.
   - Normalisation canonique et scellement cryptographique par hash SHA-256 (`content_hash == sha256:...`) avec stricte immuabilité (`SKILL-INV-08`).
   - Détection des altérations de contenu (`SkillHashTamperingError`) et des cycles de dépendances (`SkillDependencyCycleError`).
   - Délégation parent-enfant strictement monotone (`SKILL-INV-02`) interdisant toute escalade de compétences.
2. **Catalogue Officiel des 5 Compétences Fondamentales** (`app/skills/catalog.py`) :
   - `portfolio_ambassador` : Base de connaissances authentique issue de `https://rockib-quenum.netlify.app/` (MARTISTORE, WaAuto, Agence IIA, SaaS multi-boutique, posture de production).
   - `lead_qualification` : Qualification commerciale et pontage vers le schéma `Lead` de l'agence IIA.
   - `frontend_react` : Conventions React 19, Vite, Framer Motion et intercepteur JWT Axios alignées sur `iia-frontend`.
   - `backend_django` : Architecture Django 5.2, DRF, Celery, SimpleJWT et webhooks HMAC `#progress:N` / `#step:done` alignées sur `iia_project`.
   - `cybersecurity_defensive` : Audit statique SAST, règles OWASP, détection de fuite de tokens et inviolabilité de la barrière HTTP 402 sur les livrables.
3. **Passerelle Inbound Portfolio & Capture de Leads Agence** :
   - Endpoint public `POST /api/v1/inbound/portfolio/message` protégé par rate-limiting dynamique (20 requêtes/minute par IP).
   - Traitement par le service Concierge avec transmission automatique des prospects qualifiés vers l'API de l'agence IIA (`POST /api/leads/`).
   - Composant web autonome `frontend/public/rockib-concierge.js` prêt à être injecté dans `https://rockib-quenum.netlify.app/` via `<script src="https://api.rockib.ai/static/rockib-concierge.js" defer></script>`.
4. **Non-régression Globale Absolue** : Suite de tests portée à 443 tests (100% verts).
5. **Refonte Architecturale Complète & Posture Lead Software Architect & AI Systems** :
   - Refactorisation intégrale de `index.html` pour abandonner la posture "freelance générique" au profit d'une stature de **Lead Software Architect & Autonomous AI Systems Engineer**.
   - **HUD Topologique Interactif** : Pipeline d'architecture dynamique avec inspection détaillée des 5 nœuds d'ingestion, classification, simulation, arbitrage déterministe et exécution transactionnelle.
   - **Console CLI Interactive Intégrée** : Véritable terminal bash/zsh dans le portfolio acceptant les commandes `help`, `arch`, `metrics`, `systems`, `governance`, `skills`, `contact`, `clear`.
   - **Études de Cas Système Approfondies** : Spécifications techniques complètes pour `Rockib AI Engine`, `MARTISTORE (Commerce WhatsApp & CLIP)`, `WaAuto (Multi-tenant B2B)` et `Agence IIA (Portail Client & Gating SAST)`.
   - **Manifeste d'Ingénierie** : 4 principes fondamentaux (Suprématie Déterministe, Idempotence, Zero-Trust, Résilience).
   - **Bilinguisme Temps Réel (FR / EN)** et monitoring de latence cluster simulée.
6. **Déploiement en Production Confirmé (Netlify Live)** :
   - Commit `7fb38bf` poussé sur `https://github.com/rockib12/rockib-portfolio.git` (`origin/master`).
   - Déploiement vérifié avec succès en direct sur `https://rockib-quenum.netlify.app/` en moins de 6 secondes. Widget d'appel vocal et conciergerie IA pleinement opérationnels.
7. **Dossier d'Architecte Agrandi, Lightbox Photo Zoom & Hub Écosystème GitHub / LinkedIn** :
   - **Vue Profil Exécutif Agrandie (`#view-profile`)** : Portrait grand format avec badge de vérification d'architecte, métriques de rigueur (443 tests, 100% ACID), biographie complète de Lead Software Architect et footprint opérationnel (Rockib AI, MARTISTORE, WaAuto, Agence IIA).
   - **Modal Lightbox Zoom HD (`#photoModal`)** : Agrandissement en haute résolution de `rockib_profile.jpg` avec HUD cyberpunk, fermeture clavier `ESC` et clic extérieur.
   - **Vue Écosystème GitHub & Codebases (`#view-github`)** : Intégration directe du profil GitHub `@rockib12`, 6 fiches de repositories phares avec stack et liens, et cartes d'accès direct vers LinkedIn (`rockib-quenum-974471306`), WhatsApp et Email.
   - **Navigation & Clavier 9 Vues** : Raccourcis `⌘1` à `⌘9`, commande `Ctrl+K` avec recherche instantanée, et commandes CLI `profile`, `github`, `photo`, `linkedin` intégrées.
   - **Déploiement en Production (Commit `5bc71d2`)** : Poussé sur `master` et vérifié en direct sur `https://rockib-quenum.netlify.app/`.
8. **Intégration Complète de la Console Root Admin & Refonte Cyberpunk** :
   - **Vue 10 dans le Cockpit (`#view-admin`)** : Interface de commande administrateur accessible depuis la barre latérale (`10. Console Admin (Root)`), le raccourci `⌘0`, le bouton Root Admin dans le header, et la palette `Ctrl+K`.
   - **Contrôleur d'Authentification & Télémétrie** : Connexion via l'API Render (`https://rockib-portfolio.onrender.com/api/auth/login`), badge de statut dynamique (`SESSION ACTIVE (ROOT)`), tuiles de métriques réelles (visiteurs uniques, vues journalières via `/api/admin/analytics`), déclencheur de test du bot Telegram (`/api/telegram/test`) et verrouillage/déconnexion de session.
   - **Commandes Terminal CLI Étendues** : Commandes `admin`, `root`, `login`, `console` ajoutées à l'interpréteur de commandes du portfolio pour basculer instantanément vers le panneau admin.
   - **Refonte Visuelle d'`admin.html`** : Harmonisation stylistique complète avec le cockpit cyberpunk dark luxury (`#030508`, `Space Grotesk`, `JetBrains Mono`, bordures néon cyan et glassmorphism), ajout de passerelles de retour directes vers `index.html` sur l'écran de login et la barre de navigation.
   - **Déploiement en Production Confirmé (Netlify Live)** : Commit `7063310` poussé sur `origin/master`, déployé et vérifié en direct avec code HTTP 200 sur `https://rockib-quenum.netlify.app/` et `https://rockib-quenum.netlify.app/admin.html`.
9. **Réintégration Dynamique des Données Backend & Bilinguisme Exhaustif FR / EN** :
   - **Ingestion Dynamique Multi-Source** : Le cockpit interroge l'API live Render (`/api/projects`, `/api/skills`, `/api/status`). Fallback statique robuste et injection automatique des nouveaux projets créés depuis la console Root Admin ou le bot Telegram dans la grille `#systemsAppGrid`.
   - **Bilinguisme Intégral Temps Réel (FR / EN)** : Dictionnaires de traduction étendus couvrant les 10 vues du cockpit (Topologie HUD, Systèmes déployés, Gouvernance & Arbitrage, Matrice de Compétences, Footprint d'impact, Manifeste d'ingénierie, Profil exécutif, Hub GitHub, Console Admin). Support du formatage HTML enrichi, bascule fluide avec conservation dans `localStorage ('rockib_lang')` et mise à jour bilingue des descriptions dynamiques (`desc_fr` / `desc_en`).
   - **Validation & Synchronisation du Frontend React/Vite** : Build de production `dist/` validé en 5.52s, hash SHA-256 de `rockib-concierge.js` synchronisé à 100%.
   - **Déploiement en Production (Commit `6b5c1a8`)** : Poussé sur `master` et vérifié en direct sur `https://rockib-quenum.netlify.app/`.
10. **Neutralisation de Faille Inbound & Implémentation du Workspace Credential Vault (Phase A)** :
   - **Neutralisation de Sécurité Immédiate** : L'endpoint vulnérable `POST /webhooks/trigger` avec clé en dur publique a été révoqué et retourne désormais `501 Not Implemented`.
   - **Modèle Relationnel `WorkspaceCredential` & Migration 011** : Table `workspace_credentials` créée et partitionnée par `workspace_id`, `provider` et `key_alias` avec unicité stricte.
   - **Chiffrement Authentifié AEAD AES-256-GCM** : Clé maîtresse dérivée par HKDF-SHA256 ; secret lié cryptographiquement aux Associated Data `workspace_id:provider:key_alias` empêchant tout transfert illicite entre tenants.
   - **Preuve Formelle d'Isolation INV-02 (`TEST-SOC-03`)** : 6 tests unitaires et de sécurité d'intrusion validés (`tests/test_workspace_credentials.py`).
11. **Intégration Complète du Bot Telegram Interactif & Pipeline de Recherche Autonome** :
   - **Contrôleur Telegram Dédié (`app/telegram/services/telegram_service.py`)** : Bot `@masterrockibot` connecté avec sécurité Zero-Trust par Whitelist (`TELEGRAM_ADMIN_CHAT_ID`). Rejet immédiat de tout expéditeur non autorisé.
   - **Escalade Interactive par Boutons Inline** : Lors d'un arbitrage `ControlOutcome.ESCALATE`, envoi automatique d'une alerte avec boutons interactifs `[✅ Approuver]` et `[❌ Rejeter]`. Le clic administrateur déverrouille l'autorisation serveur (`issue_authorization`), bascule la décision à `ALLOW` et met à jour le message Telegram en direct avec horodatage scellé.
   - **Commandes & Création de Missions DAG** : Prise en charge des commandes `/start`, `/status`, `/agents`, `/goals` et saisie libre d'objectifs avec décomposition DAG séquentielle immédiate (`Task`).
   - **Pipeline de Recherche et Synthèse Temps Réel** : Recherche web contextuelle (Google News RSS, DuckDuckGo, Wikipédia) + inférence haute capacité Groq (`openai/gpt-oss-120b`) avec acheminement direct et instantané du rapport exécutif complet sur le compte Telegram de Rockib.
   - **Non-Régression Globale Absolue** : Suite de tests portée à **461 tests automatisés réussis (100% verts)** (`tests/test_telegram_integration.py`).
12. **STEP 6D — Durcissement Complet du Skill Registry (Prêt pour les 107 Skills)** :
   - **Résolution Déterministe des Dépendances Transitives** : Ajout de `MissingTransitiveSkillDependencyError` (`app/skills/services/registry.py`), correction du chemin de cycle par slug, validation de la présence de versions actives et vérification de la fermeture transitive complète au moment du JIT.
   - **Gestion Symétrique de l'Exclusion Mutuelle (`conflicts_with`)** : Implémentation de `are_skills_conflicting` et `verify_no_conflicts` (`app/skills/services/selector.py`), filtrage déterministe score/slug pour éliminer les compétences conflictuelles en sélection conjointe.
   - **Isolation Formelle des Workspaces & Non-Élévation de Privilèges** : Tests rigoureux prouvant l'invisibilité des compétences privées hors de leur workspace d'origine, disponibilité sans faille des compétences système (`is_system=True`), et indépendance stricte entre `required_tools` et les autorisations de l'Arbitrator (`approval_required=True` sur DELETE ou ESCALATE).
   - **Visibilité et Résilience du Seeding au Démarrage** : Remplacement de l'interception silencieuse dans `app/main.py` par une journalisation critique et un blocage préventif en cas d'erreur d'intégrité (`SkillRegistryError`), avec support prouvé de l'idempotence et des montées de version SemVer.
   - **Intégrité Cryptographique des 5 Compétences Fondamentales Inviolée** : Les 5 hashes canoniques SHA-256 historiques demeurent 100% identiques et scellés.
   - **Non-Régression Totale Validée** : Suite de tests portée à **479 tests automatisés réussis (100% verts)** (`STEP_6D_SKILL_REGISTRY_HARDENING.md`).
13. **STEP 6E — Déploiement Complet du Catalogue de 107 Skills & Scellement Cryptographique** :
   - **Déploiement Modulaire sous `app/skills/catalog/`** : Architecture scindée en 6 sous-domaines industriels (`core.py`, `engineering.py`, `ai_agentic.py`, `devops.py`, `cybersecurity.py`, `data.py`, `business.py`, `builder.py`, `__init__.py`) avec stub de rétrocompatibilité `app/skills/catalog.py`.
   - **Préservation Absolue des 5 Compétences Fondamentales** : Condensats SHA-256 rigoureusement inchangés (`portfolio_ambassador`, `lead_qualification`, `frontend_react`, `backend_django`, `cybersecurity_defensive`).
   - **Validation Cryptographique & DAG Intégrale** : 107/107 condensats SHA-256 validés, 0 cycle de dépendance, 0 dépendance manquante, symétrie stricte des conflits, déclaration neutre de `required_tools`.
   - **Seeding en Base de Données Idempotent** : Déploiement vérifié de 107 compétences système (`SELECT COUNT(*) FROM skills WHERE is_system = True` = 107).
   - **Non-Régression Totale Validée** : Suite de tests portée à **494 tests automatisés réussis (100% verts)** (`STEP_6E_107_SKILLS_DEPLOYMENT.md`).
14. **STEP 6G — Durcissement Complet de la Gouvernance (Hardening Validé)** :
   - **Fix 1 — Autonomie Hiérarchique Monotone Câblée** : Intégration de `parent_applied_autonomy` dans `app/goal_engine/router.py` et `app/connectors/agent_connectors.py`. Invariant formel validé : tout sous-agent ou sous-objectif est strictement plafonné par l'autonomie appliquée de son parent ($applied \le parent\_applied$). Scénarios 1 à 5 et test adversarial couverts (parent=1, requis=5 $\rightarrow$ appliqué=1, JAMAIS 5).
   - **Fix 2 — Résolution Déterministe Workspace / Système** : Ajout explicite de `.order_by(Skill.is_system.asc(), Skill.created_at.desc())` dans `app/skills/services/registry.py` (`get_skill`). Priorité garantie du skill de workspace sur le skill système de même slug, fallback automatique et étanchéité multi-tenant validée.
   - **Fix 3 — Alignement Exhaustif du Contrat SkillCategory** : Extension de l'Enum Pydantic `SkillCategory` (`app/skills/schemas.py`) aux 11 catégories (`engineering`, `ai_agentic`, `devops`, `cybersecurity`, `data`, `business`, `marketing`, `operations`, `security`, `research`, `general`).
   - **Scellement Cryptographique et Zéro-Migration Confirmés** : 107/107 hashes SHA-256 validés, Core 5 immuables, 107 compétences système en base (`is_system = True`), 0 migration SQL ajoutée.
   - **Non-Régression Totale Validée** : Suite de tests portée à **502 tests automatisés réussis (100% verts)** (`STEP_6G_GOVERNANCE_HARDENING.md`).
15. **STEP 6H — Authentification & Cloisonnement Multi-Tenant du Goal Engine** :
   - **Sécurisation Exhaustive des 8 Endpoints (`app/goal_engine/router.py`)** : Décoration par dépendances FastAPI `get_current_user` et `assert_workspace_member`. Filtrage systématique par appartenance workspace (`workspace_id.in_(user_ws_ids)`).
   - **Anti-Énumération Zero-Trust** : Retourne `HTTP 404 Not Found` (au lieu de 403) sur les tentatives d'accès direct à un identifiant (`/goals/{id}`, `/agents/{id}/logs`, `/goals/{id}/wake`) d'un workspace étranger.
   - **Prévisualisation de Fichiers Signée HMAC-SHA256 (`app/core/signed_urls.py`)** : Implémentation d'URLs temporaires avec signature cryptographique (`exp`, `sig`, TTL 1h) et domaine de séparation `b"rockib.preview.v1"`. Permet l'ouverture directe dans des onglets de navigateur sans fuite de Bearer token.
   - **Front-End Hardening & Client `authFetch`** : Création de `frontend/src/lib/authFetch.js` avec injection automatique du token JWT et émission de l'événement `rockib:unauthorized` (HTTP 401). Interruption propre des boucles de polling quand la session expire.
   - **Composition Monotone Multi-Paliers** : Prise en charge stricte du minimum de tous les plafonds hiérarchiques (`min(caps)`) dans `app/connectors/agent_connectors.py`.
   - **Non-Régression & Scellement** : 27 nouveaux tests dédiés (`tests/test_goal_engine_auth.py`), 107/107 skills et hashes intacts, suite globale portée à **530 tests unitaires et d'intégration réussis (100% verts)** (`STEP_6H_GOAL_ENGINE_AUTH.md`).
16. **Sécurisation Critique P0/P1 — Hardening de Production** :
   - **P0-1 (Telegram Webhook Secret)** : Validation stricte en amont du header `X-Telegram-Bot-Api-Secret-Token` avec timing-safe comparison (`secrets.compare_digest`), levée immédiate de `403 Forbidden` si manquant ou invalide, et transmission automatique du paramètre `secret_token` via `set_webhook`.
   - **P0-2 (Protection Anti-SSRF & DNS Rebinding)** : Module `app/core/network_security.py` déployé avec validation de schéma (`http`/`https`), résolution DNS obligatoire pré-requête (`socket.getaddrinfo`), blocage systématique des boucles locales (`127.0.0.0/8`), plages privées RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), adresses de lien local, réservées, multicast et métadonnées cloud (`169.254.169.254`). Suivi pas-à-pas des redirections HTTP (max 3 sauts) interdisant tout contournement SSRF via redirection 3xx (`SSRF_REDIRECT_BLOCKED`). Neutralisation formelle du DNS Rebinding (TOCTOU) par transport personnalisé `PinnedIPBackend` qui force le socket TCP sur l'IP pré-validée en préservant le SNI TLS et les headers `Host`.
   - **P1-1 (Fail-Fast Credential Vault)** : Suppression du fallback permissif sur `JWT_SECRET_KEY` dans `derive_master_key()`. Exigence explicite de `CREDENTIAL_VAULT_KEY` ou arrêt immédiat du serveur (`RuntimeError`) au démarrage (`lifespan`) si la clé par défaut du template est détectée.
   - **P1-2 (Authentification et Isolation Multi-Tenant sur `/api/v1/decisions/`)** : Décoration obligatoire par `get_current_user`, vérification d'appartenance au workspace via `assert_workspace_member` (HTTP 403), et vérification que l'agent ciblé appartient bien audit workspace avec protection anti-énumération (HTTP 404 au lieu de 403).
   - **Non-Régression Totale Validée** : Suite de tests portée à **573 tests unitaires et d'intégration réussis (100% verts)** (`tests/test_security_hardening.py`, `tests/test_api_connector.py`, `tests/test_web_connectors.py`, `tests/test_telegram_integration.py`).
17. **STEP 6H.1A — Socle de Gouvernance Financière & Intégrité du Périmètre** :
   - **Périmètre Canonique d'Action** : Extraction et validation stricte de `amount` (Decimal positif non nul, zéro/négatif/nan/float interdit) et `currency` (code ISO-4217 en majuscules uniquement) dans `ActionRecord.arguments`.
   - **Plafond Budgétaire Hiérarchique** : Validation stricte de `budget_ceiling` et `budget_currency` dans `Goal.goal_metadata`. Respect strict du principe monotone parent-enfant ($ceiling_{enfant} \le ceiling_{parent}$).
   - **Intégrité Cryptographique Scellée** : `ActionRecord.canonical_fingerprint` scelle `amount` et `currency`. Toute altération du montant ou de la devise invalide immédiatement l'autorisation d'exécution au niveau du `ReliableExecutor`.
   - **Fail-Closed par Défaut** : Toute omission de montant/devise ou plafond absent en contexte financier déclenche un rejet immédiat (`FinancialValidationError`). 0 migration DB requise.
   - **Suite Dédiée** : 38 tests unitaires et d'intégration validés (`tests/test_financial_governance.py`).
18. **STEP 6H.2A — Classification des Intentions Financières & Fermeture GAP-CLASS-01** :
   - **Détection des Intentions Financières** : Mots-clés de dépenses publicitaires (`spend`, `payer`, `achat`, `sponsor`, `promote`, `boost`, etc.) et analytiques (`ctr`, `cpc`, `roas`, `cpl`) intégrés dans `app/decision_engine/classifier_config.json`.
   - **Éviction Déterministe des Domaines Techniques** : Règle d'invariance `FIN-CLASS-INV-02` dans `app/decision_engine/services/domain_classifier.py` qui évince systématiquement les domaines techniques (`system`, `infrastructure`, `testing`, `monitoring`) au profit de `finance / SPEND` dès qu'un motif financier est détecté.
   - **Fermeture Définitive de GAP-CLASS-01** : Évaluation exhaustive des motifs regex financiers sur l'ensemble du contexte textuel `full_text = f"{proposed_action} {objective} {situation}".lower()`, fermant toute tentative de contournement par injection du budget dans l'objectif ou la situation.
   - **Validation Globale** : 65 tests classifier validés (`tests/test_domain_classifier.py`), 103 tests combinés finance/classifier.
19. **Résolution du Domaine Content & Réparation de la Boucle Autonome d'Arrière-Plan (Celery & Exécution)** :
   - **Connecteur `content.create`** (`app/connectors/content_connector.py`) : Rédaction sandboxée de scripts, prompts et documents textuels avec persistance stricte dans `workspaces/<workspace_id>/content/` sans effets de bord réseau ni coûts externes.
   - **Règle de Classification `CONTENT-CLASS-INV-01`** : Invariance déterministe dans `DomainClassifier` assurant qu'une intention de rédaction explicite (`rédige`, `script`, `scénario`, `voix-off`, `prompts`) l'emporte de façon univoque sur les lectures ou actions de création génériques, tout en maintenant le fail-closed absolu sur toute action financière ou externe.
   - **Politique `DecisionDomainConfig` pour `content / CREATE`** : Déployée en base avec risque `low`, réversibilité `reversible`, impact `internal` et autonomie `3`, garantissant un arbitrage `ALLOW (POLICY_ALLOWED)`.
   - **Éradication des Fautes d'Injection & d'Expiration Celery** : Correction des factories `app/core/dependencies.py` qui transmettaient des objets FastAPI `Depends` aux workers d'arrière-plan, et sécurisation de `reliable_executor.py` et `tasks.py` avec `AsyncSessionLocal` (`expire_on_commit=False`) éliminant définitivement les erreurs `MissingGreenlet`.
   - **Exécution Réelle E2E Certifiée** : Mission de script vidéo Motion Design exécutée avec succès (`confirmed`), livrant le fichier de pré-production dans le workspace.
   - **Validation de Non-Régression Globale** : Suite de tests portée à **674 tests unitaires et d'intégration réussis (100% verts)**.
20. **Audit 360° & Durcissement Intégral de Production (Lots P1 à P7)** :
   - **Lot P1 (Sécurité Applicative & Isolation)** : Isolation `Content-Security-Policy: sandbox` et `X-Content-Type-Options: nosniff` sur `/api/v1/workspaces/{id}/preview/{path}` ; liste blanche stricte `CORS_ORIGINS` ; liaison du port debug Uvicorn sur `127.0.0.1:8080:8000` (anti-spoofing `X-Forwarded-For`) ; masquage des exceptions 500 internes ; assainissement DOM (`createTextNode`) dans `rockib-concierge.js` ; et passage de `/api/v1/auth/me` sous `authFetch`.
   - **Lot P2 (Performance SQL & Zéro Warning)** : Éradication des requêtes SQL $N+1$ sur `list_agents`, `list_goals`, `get_telemetry_events` et `get_goal_details` (chargement groupé `WHERE IN`) ; migration complète vers `datetime.now(timezone.utc)` (`_utcnow()`) ramenant les avertissements Pytest de **1 535 à 0**.
   - **Lot P3 (DevSecOps & Bundling)** : Exécution non-root (`uid=10001 rockib`) pour `uvicorn`, `celery_worker` et `celery_beat` sous Supervisord ; découpage `manualChunks` Vite (`vendor-three`, `vendor-ui`) ; réduction de 90 % du contexte Docker via `.dockerignore`.
   - **Lot P4 (Complétude API & Nginx Hardening)** : Implémentation de `GET /api/v1/decisions/{id}` et `GET /api/v1/decisions/` avec isolation multi-tenant et anti-énumération (404) ; ajout des en-têtes HTTP de sécurité Nginx (`server_tokens off`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`).
   - **Lot P5 (Anti-Bruteforce, Observabilité & Résilience Mémoire)** : Rate-limiting IP glissant (429 + `Retry-After`) et protection anti-timing attack sur `/api/v1/auth/login` et `/register` ; middleware de traçabilité `X-Request-ID` validé par regex ; sonde de santé profonde `/api/v1/health` ; et éviction automatique TTL/capacité des sessions d'appel vocal dans `VoiceCallService`.
   - **Lot P6 (Protection Inbound Complète, Plafonnement IP, Healthcheck DB/Redis & Nginx Assets)** : Extension du rate-limiting IP aux endpoints vocaux publics `/portfolio/voice/session` et `/request-callback` ; plafonnement mémoire des IP suivies (`_MAX_TRACKED_IPS = 2000`) dans `portfolio_handler.py` ; sonde `/api/v1/health` vérifiant conjointement PostgreSQL et Redis + fermeture propre du pool (`async_engine.dispose()`) au shutdown ; limite `client_max_body_size 2m;` et préservation des en-têtes de sécurité sur `location /assets/` dans `nginx.conf`.
   - **Lot P7 (Validation Stricte des Schémas Pydantic & Normalisation Email)** : Bornes de longueur sur `UserCreate.password` (`8..128` caractères, anti-DoS Argon2/bcrypt), normalisation systématique des emails en minuscules sur `/register` et `/login`, bornes strictes sur `DecisionRequest`, `CreateGoalRequest`, `CreateAgentRequest` et validation par pattern de `CallMeBackRequest.channel` (`whatsapp|phone`).
   - **Validation de Non-Régression Globale** : Suite de tests portée à **686 tests unitaires et d'intégration réussis (100% verts, 0 warning)**.



