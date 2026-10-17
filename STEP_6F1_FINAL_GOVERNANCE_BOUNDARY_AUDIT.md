# STEP 6F.1 — FINAL GOVERNANCE BOUNDARY AUDIT
## RAPPORT D'AUDIT CONTRADICTOIRE DES FRONTIÈRES DE GOUVERNANCE

- **Système** : Rockib AI
- **Date** : 2026-10-03
- **Auditeur** : Lead Software Architect & AI Systems Engineer (Mode Audit Strict / Read-Only)
- **Cible auditée** : Frontières de gouvernance réelles (Autonomie hiérarchique, Transitivité, Permissions, Shadowing, Enums)
- **Verdict Exécutif** : **PASS WITH GAPS**

---

## 1. Executive Verdict

L'audit contradictoire approfondi mené sur le code réel, les flux d'exécution et les tables de base de données confirme la robustesse générale du système d'arbitrage et de scellement cryptographique, tout en établissant avec précision le statut des frontières de gouvernance :

### **VERDICT GLOBAL : PASS WITH GAPS**

**Conclusions clés par frontière :**
1. **Skill -> Permission & Authorization (PROVEN)** : L'étanchéité est absolue. Un Skill ne confère **jamais** de permission. `required_tools` n'est qu'une chaîne textuelle insérée dans le prompt du LLM. Aucune action n'est exécutée sans un arbitrage serveur `ALLOW` et un jeton d'autorisation unitaire signé.
2. **Dépendances Transitives -> Capacités (PROVEN)** : Une dépendance est **uniquement une précondition de validité** (`PRECONDITION ONLY`). Elle n'élargit en rien les capacités du Skill sélectionné, n'ajoute pas d'outils effectifs et n'injecte pas son texte dans le prompt si elle n'est pas directement sélectionnée.
3. **Budget JIT <= 2 (PROVEN)** : Le sélecteur borne strictement la liste `ActiveSkillContext` retournée à au plus 2 compétences.
4. **Autonomie Hiérarchique (GAP / PARTIALLY PROVEN)** : La formule `applied = min(requested, agent_default, parent_applied)` existe bien sous forme de méthode pure dans `GoalManager.calculate_applied_autonomy`. Cependant, **le câblage d'exécution omet de transmettre `parent_applied_autonomy`** lors de la création de goals dans `app/goal_engine/router.py`, et le handler `agent.spawn` force une autonomie par défaut de 2 sans vérifier le plafond du parent.
5. **Résolution Workspace / Système (PROVEN GAP)** : La requête dans `SkillRegistry.get_skill()` utilise `or_(*conditions)` sans clause `ORDER BY`. En cas de collision de slug entre un skill de workspace et un skill système, la sélection est non-déterministe au niveau SQL.
6. **Contrat SkillCategory (TYPE-ONLY GAP)** : L'inadéquation entre l'énumération `SkillCategory` (6 valeurs) et le catalogue (9 catégories) est un gap de typage strict sans impact à l'exécution, car le champ est typé en `str` dans le schéma Pydantic et en `String(50)` dans la base de données.

---

## 2. Question 1 — Hierarchical Autonomy

### 2.1 Objectif & Traçabilité Réelle
L'audit a tracé le cycle de vie complet de l'autonomie à travers les composants :
```text
Goal Engine (create_goal / router.py)
   ↓
Goal.applied_autonomy_level
   ↓
autonomous_loop.py (build_decision_request)
   ↓
DecisionRequest.requested_autonomy_level
   ↓
DecisionOrchestrator.handle_decision
   ↓
DeterministicArbitrator.arbitrate
   ↓
min(requested_autonomy, allowed_autonomy)
   ↓
Decision.applied_autonomy_level
```

### 2.2 Analyse du Code Réel
1. **La méthode métier** (`app/goal_engine/services/goal_manager.py`, lignes 130-163) :
   ```python
   @staticmethod
   def calculate_applied_autonomy(
       requested_autonomy_level: int,
       agent_default_autonomy: int,
       parent_applied_autonomy: Optional[int] = None,
   ) -> int:
       cap = min(requested_autonomy_level, agent_default_autonomy)
       if parent_applied_autonomy is not None:
           cap = min(cap, parent_applied_autonomy)
       return cap
   ```
   Cette méthode implémente fidèlement l'invariant $applied = \min(req, agent, parent)$.

2. **Le point de rupture (Router)** (`app/goal_engine/router.py`, lignes 307-313) :
   ```python
   # Calcul de l'autonomie appliquée déterministe
   applied_autonomy = GoalManager.calculate_applied_autonomy(
       requested_autonomy_level=payload.requested_autonomy_level,
       agent_default_autonomy=agent.default_autonomy_level,
   )
   ```
   **Observation** : L'argument `parent_applied_autonomy` **n'est pas fourni**. Même si `payload.parent_goal_id` est renseigné, le router ne charge pas le Goal parent pour extraire son `applied_autonomy_level`.

3. **Le point de rupture (Agent Spawn)** (`app/connectors/agent_connectors.py`, lignes 41-53) :
   Lorsqu'un sous-agent est créé via `agent.spawn`, le handler instancie :
   - `Agent(default_autonomy_level=2)` (valeur codée en dur).
   - `Goal(requested_autonomy_level=2, parent_goal_id=None)`.
   Aucune lecture de l'autonomie de l'agent parent déclencheur (`action.agent_id`) n'est effectuée.

4. **Le Decision Engine** (`app/decision_engine/services/arbitrator.py`, ligne 185) :
   L'arbitre applique :
   ```python
   applied_autonomy_level = min(requested_autonomy_level, allowed_autonomy_level)
   ```
   Il ne reçoit aucun paramètre `parent_autonomy_limit` et ne consulte pas la chaîne hiérarchique.

### 2.3 Scénarios d'Évaluation
- **Scénario A (Parent autonomy = 1, Enfant demande 4)** :
  - Si l'enfant est créé via `router.py` avec `agent.default_autonomy_level = 4` :
    - `requested = 4`
    - `allowed = 5` (ex: config domaine)
    - `effective = 4`.
  - **Verdict Scénario A** : **L'enfant dépasse l'autonomie du parent (1 < 4)** en raison de l'omission du paramètre dans `router.py`.
- **Scénario B (Parent autonomy = 3, Enfant demande 5)** :
  - `effective autonomy = min(5, agent_cap, domain_allowed)`. Si agent_cap = 5 et domain_allowed = 5, effective = 5.
- **Scénario C (Parent = 4 -> Child = 3 -> Grandchild = 5)** :
  - L'invariant `Grandchild <= Child <= Parent` n'est **pas garanti au runtime** lors de la création d'objectifs via l'API REST.

### 2.4 Verdict Question 1
- **Classement** : **PARTIALLY PROVEN / GAP (Medium)**
- *Preuve* : `app/goal_engine/services/goal_manager.py:130` contient la logique pure, mais `app/goal_engine/router.py:307` omet de la câbler avec le parent.

---

## 3. Question 2 — Transitive Capability Expansion

### 3.1 Objectif
Déterminer si une dépendance transitive ($A \rightarrow B \rightarrow C$) peut conférer des capacités, outils ou permissions au Skill actif $A$.

### 3.2 Analyse du Code Réel (`app/skills/services/selector.py`)
1. **Éligibilité** : L'agent doit posséder les compétences formellement assignées dans `AgentSkill`.
2. **Sélection directe** : Seuls les scores des compétences directement adaptées au prompt sont retenus dans `selected_versions` jusqu'à concurrence de `max_skills <= 2`.
3. **Vérification transitive** (lignes 215-224) :
   ```python
   for v in selected_versions:
       if v.required_skills:
           transitive_deps = await SkillRegistry.resolve_transitive_dependencies(
               session, v, workspace_id=workspace_id
           )
           for dep in transitive_deps:
               if dep.skill.slug not in eligible_slugs:
                   raise MissingTransitiveSkillDependencyError(...)
   ```
4. **Formatage retourné** (lignes 227-238) :
   ```python
   return [
       ActiveSkillContext(
           id=v.skill.slug,
           name=v.skill.name,
           instructions=v.instructions,
           constraints=v.constraints or [],
           required_tools=v.required_tools or [],
       )
       for v in selected_versions
   ]
   ```

### 3.3 Réponses aux Questions Critiques
- Une dépendance transitive peut-elle ajouter un `required_tool` à $A$ ? **NON**. `ActiveSkillContext.required_tools` ne contient que les outils déclarés dans $A$.
- Une dépendance transitive injecte-t-elle son texte dans le prompt ? **NON**. Seuls les éléments de `selected_versions` sont formatés.
- Une dépendance transitive modifie-t-elle le domaine ou le risque ? **NON**. Le domaine et le risque sont calculés indépendamment par le `DomainClassifier` et le `DeterministicArbitrator`.
- Cas adversarial ($A \rightarrow B [\text{system.write}] \rightarrow C [\text{system.delete}]$) :
  - Si seul $A$ est sélectionné, ni `system.write` ni `system.delete` n'apparaissent dans `ActiveSkillContext.required_tools`.
  - Aucune capacité supplémentaire n'est activée.

### 3.4 Verdict Question 2
- **Verdict** : **PRECONDITION ONLY (PROVEN)**.
- *Conclusion* : Une dépendance transitive est une condition sine qua non de validité opérationnelle de l'agent, et non un mécanisme d'héritage implicite de capacités.

---

## 4. Question 3 — required_tools -> Permission -> Authorization

### 4.1 Traçabilité Complète de la Chaîne
```text
[SkillManifest.required_tools]
       ↓ (Copie brute déclarative)
[ActiveSkillContext.required_tools]
       ↓ (Injection textuelle prompt: <declared_tools>)
[RationalAgent]
       ↓ (Génération JSON: suggested_action)
[DomainClassifier]
       ↓ (Analyse textuelle indépendante: (domain, permission, CERTAIN))
[DeterministicArbitrator]
       ↓ (Application matrice decision_domain_config en DB)
[ControlOutcome.ALLOW / ESCALATE / DENY]
       ↓ (Si ALLOW uniquement)
[issue_authorization()]
       ↓ (Jeton cryptographique à usage unique)
[ReliableExecutor.dispatch_authorized_action()]
       ↓ (Vérification signature, empreinte, TTL, verrou DB)
[Action Handler sandboxé]
```

### 4.2 Tests Adversariaux
- **Test A (Outil `system.delete` déclaré dans Skill sans permission)** :
  - `RationalAgent` propose `fs.delete`.
  - `DomainClassifier` classe en `PermissionAction.DELETE`.
  - `DeterministicArbitrator` détecte `DELETE` $\rightarrow$ `approval_required = True`, `control_outcome = ESCALATE`.
  - `issue_authorization()` n'est **pas appelée**.
  - Aucune exécution n'a lieu.
- **Test B (Skill déclare `system.write` mais LLM demande `delete`)** :
  - `DomainClassifier` analyse l'action réelle demandée (`delete`), ignorant `system.write`.
  - L'action est traitée comme un `DELETE` et escaladée.
- **Test C (Outil privilégié sans droit)** :
  - `issue_authorization()` vérifie strictement `decision.permission_granted is True` et `decision.control_outcome == ControlOutcome.ALLOW`.
- **Test D (Action ALLOW sans jeton)** :
  - `ReliableExecutor.dispatch_authorized_action()` lève immédiatement `AuthorizationError("NO_AUTHORIZATION")` si le jeton est absent ou invalide.

### 4.3 Question Centrale
- Existe-t-il un chemin permettant à un Skill de créer ou d'influencer directement un jeton d'autorisation ?
  - **NON (PROVEN)**.

### 4.4 Verdict Question 3
- **Verdict** : **PROVEN**.
- *Conclusion* : La règle architecturale *« Skill never grants permission »* est rigoureusement et hermétiquement respectée à chaque palier.

---

## 5. Question 4 — Workspace / System Shadowing

### 5.1 Analyse du Code (`app/skills/services/registry.py`, lignes 178-185)
```python
@staticmethod
async def get_skill(
    session: AsyncSession,
    slug: str,
    workspace_id: Optional[UUID] = None,
) -> Optional[Skill]:
    """Fetch a skill by slug, searching workspace first then system scope."""
    conditions = [and_(Skill.slug == slug, Skill.is_system == True)]
    if workspace_id:
        conditions.append(and_(Skill.slug == slug, Skill.workspace_id == workspace_id))

    stmt = select(Skill).where(or_(*conditions)).options(selectinload(Skill.versions))
    res = await session.execute(stmt)
    return res.scalars().first()
```

### 5.2 Examen Contradictoire
- **Promesse du docstring** : *"searching workspace first then system scope"*.
- **Réalité SQL** : `SELECT ... WHERE (slug = :s AND is_system = True) OR (slug = :s AND workspace_id = :ws) LIMIT 1`.
- Sans clause `ORDER BY`, PostgreSQL renvoie la première ligne qui correspond selon son plan d'accès séquentiel ou d'index. L'ordre de retour est indéfini par les standards relationnels.
- **Impact dans le sélecteur** :
  - Le sélecteur JIT direct (`SkillSelector.select_skills_for_task`) n'appelle **pas** `get_skill()`. Il filtre par `AgentSkill` et vérifie `WorkspaceSkill.is_enabled`.
  - Cependant, `SkillRegistry.resolve_transitive_dependencies()` appelle `get_skill(session, dep_slug, workspace_id)` (ligne 244).
  - En conséquence, la résolution transitive d'un slug identique présent à la fois en système et en workspace privé est **non-déterministe**.

### 5.3 Classification & Gravité
- Ce n'est pas un risque d'escalade de privilège direct (car le workspace skill doit être valide et assigné), mais un **défaut de déterminisme et d'isolation de nommage**.
- **Verdict** : **REAL DETERMINISM GAP (PROVEN GAP - Medium)**.

---

## 6. Question 5 — SkillCategory Contract

### 6.1 Usages de `SkillCategory`
Une recherche exhaustive sur l'ensemble du dépôt révèle que `SkillCategory` est uniquement défini dans `app/skills/schemas.py` :
```python
class SkillCategory(str, Enum):
    ENGINEERING = "engineering"
    RESEARCH = "research"
    SECURITY = "security"
    MARKETING = "marketing"
    OPERATIONS = "operations"
    GENERAL = "general"
```
Dans `SkillManifestMetadata` :
```python
category: str = Field(default=SkillCategory.GENERAL.value)
```
Dans `Skill` (SQLAlchemy) :
```python
category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
```

### 6.2 Analyse d'Impact
- Le champ `category` est typé en `str` dans le modèle Pydantic et en `String(50)` dans PostgreSQL.
- Aucun composant de décision, d'autorisation ou d'exécution ne filtre ou ne branche sa logique sur `category`.
- Les 107 compétences du catalogue, incluant les catégories `devops`, `cybersecurity`, `data`, `business`, `ai_agentic`, sont validées, enregistrées et persistées sans aucune erreur de validation ou de base de données.
- **Verdict** : **TYPE-ONLY GAP (NO REAL IMPACT - Low)**.

---

## 7. Cross-Boundary Test

Simulation analytique de bout en bout d'une attaque composée :
```text
Workspace A
   ↓
Skill A (assigné à Child Agent)
   ↓
required_skills = ["B"]
   ↓
required_tools = ["system.write"]
   ↓
Child Agent (default_autonomy_level = 5)
   ↓
Parent Agent (default_autonomy_level = 2)
   ↓
Tâche : "Écrire un fichier système de configuration"
```

### Évaluation pas à pas :
1. **Skill A sélectionnable ?** -> **OUI**, à condition que B soit également assigné à l'enfant dans Workspace A.
2. **B sélectionnable ?** -> **OUI** (comme prérequis validé, ou co-sélectionné si budget disponible).
3. **`system.write` disponible ?** -> **NON exécutable**. Présent uniquement comme métadonnée d'orientation dans le prompt du LLM.
4. **Permission obtenue ?** -> **NON**. Le Skill n'a aucun pouvoir d'attribution.
5. **Autonomie de l'enfant ?** -> **5**, car `router.py` et `agent.spawn` n'ont pas plafonné l'autonomie au niveau du parent (2).
6. **Plafond parent respecté ?** -> **NON (FAIL au niveau router)**. L'enfant fonctionne à une autonomie supérieure à celle du parent.
7. **Action ALLOW possible ?** -> **OUI conditionnellement** : Si la table `decision_domain_config` autorise l'autonomie demandée (ex: `allowed_autonomy = 3` pour `fs.write`) et que le risque est faible, l'Arbitrator renvoie `ALLOW`.
8. **Autorisation émise ?** -> **OUI**, un jeton unitaire est émis sur la base de la décision serveur.
9. **Exécution possible ?** -> **OUI**, mais **STRICTEMENT SANDBOXÉE** par `fs_write_handler` au répertoire du workspace de l'enfant. Aucune fuite hors workspace n'est permise.

**Constat du test composé** : L'attaque ne permet **aucune violation de sandbox ni aucune escalade de permission arbitraire**, mais confirme que le défaut de propagation de `parent_applied_autonomy` permet à un sous-agent d'opérer avec une autonomie décisionnelle supérieure à celle de son créateur.

---

## 8. Governance Boundary Matrix

| Boundary | Expected Invariant | Actual Behavior | Evidence | Verdict |
| :--- | :--- | :--- | :--- | :---: |
| **Skill -> Permission** | Skill never grants permission | Declarative metadata only in LLM prompt | `app/execution/services/authorizations.py:50-82` | **PROVEN** |
| **Skill -> Tool** | Declarative only | 16 tools mapped to registered sandbox handlers | `app/execution/services/system_handlers.py:55-101` | **PROVEN** |
| **Dependency -> Capability** | No implicit capability expansion | Transitive dependencies are pre-requisites only | `app/skills/services/selector.py:215-238` | **PROVEN** |
| **JIT -> Active Skills** | Budget <= 2 | Strictly bounded by `max_skills <= 2` loop break | `app/skills/services/selector.py:201-202` | **PROVEN** |
| **Parent -> Child Autonomy** | Child <= Parent | Pure logic in GoalManager, omitted in router & spawn | `app/goal_engine/router.py:307-313` | **GAP** |
| **Workspace -> System** | Deterministic resolution | `get_skill` lacks `ORDER BY`, nondeterministic on collision | `app/skills/services/registry.py:183` | **GAP** |
| **SkillCategory -> Runtime** | Valid contract | Enum has 6 categories, catalog uses 9, but `str` avoids error | `app/skills/schemas.py:27,74` | **TYPE-ONLY GAP** |
| **Authorization -> Executor** | No token = no execution | Dispatch validates token, signature, lease, expiry | `app/execution/services/reliable_executor.py:243-300` | **PROVEN** |

---

## 9. Findings

### Récapitulatif
- **CRITICAL** : 0
- **HIGH** : 0
- **MEDIUM** : 2
- **LOW** : 1
- **INFO** : 1

### Détail des Findings
1. **[MEDIUM] `GAP_HIERARCHICAL_AUTONOMY_WIRING`** :
   - *Fichier* : `app/goal_engine/router.py`, lignes 307-313 & `app/connectors/agent_connectors.py`, lignes 41-53.
   - *Observation* : L'API de création de Goal n'extrait pas `parent_applied_autonomy` pour le passer à `GoalManager.calculate_applied_autonomy`, et `agent.spawn` code l'autonomie en dur à 2.
   - *Impact* : Un enfant peut être créé avec une autonomie effective plus élevée que celle de son parent.
2. **[MEDIUM] `GAP_SHADOW_ORDER_BY`** :
   - *Fichier* : `app/skills/services/registry.py`, ligne 183.
   - *Observation* : `select(Skill).where(or_(*conditions))` est dépourvu de tri explicite.
   - *Impact* : Résolution non-déterministe lors de la résolution de dépendances transitives si un workspace skill possède le même slug qu'un system skill.
3. **[LOW] `ENUM_CATEGORY_MISALIGNMENT`** :
   - *Fichier* : `app/skills/schemas.py`, classe `SkillCategory`.
   - *Observation* : L'enum comporte 6 membres, le catalogue en utilise 9.
   - *Impact* : Aucun bug runtime, mais incohérence formelle du typage de schéma.
4. **[INFO] `TRANSITIVE_DEP_PREREQUISITE_SEMANTICS`** :
   - *Fichier* : `app/skills/services/selector.py`, lignes 215-238.
   - *Observation* : Les dépendances requises sont des prérequis d'habilitation nécessaires à la validation, sans injection de contexte additionnel dans le prompt.

---

## 10. Remaining Gaps

Les gaps identifiés ne bloquent pas le fonctionnement de base ni la sécurité d'exécution des outils, mais doivent être ordonnancés pour correction :
1. Intégrer la lecture de `parent_applied_autonomy` dans `router.py` et dans `agent_spawn_handler`.
2. Ajouter `.order_by(Skill.is_system.asc())` dans `SkillRegistry.get_skill()`.
3. Étendre l'enum `SkillCategory` avec les catégories industrielles déployées au STEP 6E.

---

## 11. Recommended Next Step

Effectuer une passe ciblée de durcissement (STEP 6G ou correctif d'architecture) appliquant exclusivement les trois correctifs ci-dessus, sans modifier le catalogue de 107 compétences dont les condensats SHA-256 demeurent strictement scellés et valides.

---

## 12. Final Verdict

# ⚠️ FINAL VERDICT: PASS WITH GAPS

L'étanchéité des autorisations, l'imperméabilité des compétences aux privilèges et le bornage JIT sont formellement démontrés (**PROVEN**). Les gaps d'autonomie hiérarchique au niveau de l'API router et de tri SQL de résolution de collision sont documentés avec preuves reproductibles et ne remettent pas en cause la sécurité fondamentale du système d'exécution.
