# Rockib IA — Contrat architectural de l’autonomie contrôlée

Date : 17 septembre 2026  
Statut : contrat cible validé ; implémentation progressive en cinq phases.

Ce document décrit la cible, pas une certification du comportement actuel. Chaque phase doit être livrée avec ses tests. Les noms d’états cibles ne remplacent pas automatiquement les Enums des migrations existantes.

## 1. Vision

Rockib IA reçoit un objectif, construit un plan, prend des décisions, utilise ses outils autorisés, observe les résultats et adapte son plan jusqu’à atteindre l’objectif ou rencontrer une limite.

**Le LLM propose. Le système décide.**

L’humain intervient aux frontières du système, pas à chaque action. Une action préautorisée conforme doit pouvoir être exécutée sans confirmation humaine.

Le LLM ne peut pas s’accorder de permissions, augmenter un budget, modifier une politique ni déclarer une exécution réussie sans preuve.

Principes :

- L’autonomie ne constitue pas une permission universelle.
- Les contrôles automatiques portent sur l’action effectivement retenue.
- Les politiques proviennent d’une autorité authentifiée.
- Un effet est rattaché à une décision, une autorisation et une tentative traçables.
- Les données mémorisées et sorties d’outils ne sont pas des instructions de confiance.
- Un agent enfant ne reçoit jamais plus de capacités que son parent.

## 2. Architecture cible

```text
Objectif + périmètre + critères de réussite + limites
                         |
                    Goal Manager
                         |
                 Planner / Task Graph
                         |
                 Decision Orchestrator
                    /             \
          Memory / Context     Opinions IA
                    \             /
                  Arbitrage déterministe
                         |
                  Action structurée
                         |
              Policy / Permission Engine
                         |
              ALLOW / DENY / ESCALATE / STOP
                         |
                  ALLOW uniquement
                         |
             Réservation + journal durable
                         |
                 Executor / Tool Adapter
                         |
                 Result / Observer
                         |
           Persistance + mise à jour du plan
                         |
            Continuer / Replanifier / Terminer
```

L’arbitrage choisit l’action finale. L’autorisation détermine si cette action précise peut être exécutée. L’exécution ne peut pas la remplacer silencieusement.

La boucle est pilotée par des états persistés et des réveils planifiés : pas de requête HTTP maintenue ouverte ni de `while` infini en mémoire.

| Composant | Responsabilité | Limite |
|---|---|---|
| Goal Manager | Valider objectif, mandant, périmètre et réussite | Le texte d’un objectif n’accorde aucun droit |
| Planner | Décomposer et réviser un graphe de tâches | Ne modifie pas les politiques |
| Orchestrator | Coordonner contexte, opinions, arbitrage et contrôle | Ne remplace pas l’action arbitrée |
| Memory | Fournir un contexte cloisonné et sourcé | Ne transforme pas un souvenir en instruction |
| Arbitrator | Choisir l’action et agréger le risque | Ne délègue pas son autorité au LLM |
| Policy Engine | Vérifier permissions, limites et approbations | Un UUID valide n’est pas une autorisation |
| Executor | Appeler un outil enregistré avec une autorisation valide | N’accepte pas d’action libre hors contrôle |
| Observer | Établir les faits à partir des résultats | Le succès exige une preuve |
| Scheduler | Réveiller les tâches éligibles et gérer les reprises | Ne répète pas aveuglément un effet incertain |
| Audit | Conserver décisions, contrôles et transitions | Ne journalise pas de secrets |

## 3. Contrats conceptuels

Ces contrats ne constituent pas encore des modèles SQL ou Pydantic.

### Goal

- Identifiants : objectif, workspace, agent et autorité mandante.
- Objectif, périmètre et critères vérifiables de réussite.
- Autonomie demandée/appliquée, délégation et politique.
- Budget, échéance, limites d’étapes, de replanifications et d’erreurs.
- État, version et motif de suspension ou de terminaison.
- Éventuel objectif parent et allocation de ressources.

Terminer toutes les tâches d’un plan ne suffit pas à prouver l’atteinte de l’objectif.

### Task

- Identifiant, objectif et agent responsable ; workspace dérivé de l’objectif.
- Description, critères de fin, dépendances et éventuelle tâche parent.
- État, version du plan, priorité et prochaine date d’éligibilité.
- Compteurs persistants de tentatives et répétitions.
- Historique des décisions et exécutions.

Les dépendances sont sans cycle. Les sous-tâches restent dans le périmètre parent. Une tâche peut produire plusieurs décisions : un unique `decision_id` ne représente pas tout son historique.

### Action structurée

- Identifiants d’action, objectif, tâche, workspace et agent.
- Outil/opération enregistrés dans un catalogue versionné.
- Arguments validés par le schéma de l’outil.
- Ressources ou destinataires ciblés.
- Permission requise, déterminée ou vérifiée côté serveur.
- Préconditions et effets attendus.
- Coût estimé avec unité explicite, risque et réversibilité.
- Empreinte canonique et clé d’idempotence.

La permission `SEND`, par exemple, ne suffit pas : outil, destinataire, volume et finalité doivent aussi être autorisés.

Tout changement d’arguments, de destinataire ou d’outil crée une nouvelle version exigeant un nouveau contrôle. Une clé d’idempotence identifie une même opération logique, pas chaque nouvelle tentative.

### Decision et Authorization

La décision conserve les avis, l’action finale, le risque et les règles appliquées.

L’autorisation conserve :

- `ALLOW`, `DENY`, `ESCALATE` ou `STOP`.
- Code de motif stable et explication.
- Identités et empreinte de l’action.
- Versions de politique et de délégation.
- Validité, préconditions et réservations.
- Référence d’approbation éventuelle.

`permission_granted` est dérivé du contrôle serveur. Le client et le LLM ne peuvent pas le fixer librement.

### ExecutionResult et Observation

Un résultat distingue un effet confirmé, un échec confirmé sans effet et un effet inconnu. Il conserve les identifiants de tentative et fournisseur, les preuves, erreurs normalisées, coûts et horodatages.

Une observation peut proposer une mise à jour du plan ou de la mémoire. Elle ne modifie pas les permissions ou les budgets accordés.

## 4. Résultats de contrôle

| Résultat | Sens | Suite |
|---|---|---|
| `ALLOW` | Toutes les conditions sont remplies pour cette action | Réserver puis exécuter après vérification de validité |
| `DENY` | Cette action est interdite dans le cadre actuel | Abandonner l’action ; chercher une alternative réellement autorisée |
| `ESCALATE` | Une approbation admissible est nécessaire | Persister la demande et suspendre la branche |
| `STOP` | Le traitement concerné doit s’arrêter | Interdire de nouveaux effets dans le périmètre arrêté |

Ordre de priorité :

1. Annulation ou arrêt d’urgence : `STOP`.
2. Interdiction ferme : `DENY`, même si une autre règle permet une approbation.
3. Condition d’approbation explicitement prévue : `ESCALATE`.
4. `ALLOW` seulement si tous les contrôles obligatoires réussissent.

Une politique absente ou illisible ne produit jamais `ALLOW`. Une indisponibilité technique suspend avec un motif explicite ; elle n’est pas une autorisation.

`STOP` précise sa portée : tâche, objectif, agent, workspace ou système. Une suspension récupérable correspond à `BLOCKED`/`PAUSED`, une annulation à `CANCELLED`, un échec définitif à `FAILED`.

`REPLAN` est une instruction de planification, pas une autorisation d’exécuter.

## 5. Machines à états cibles

Les transitions sont validées et persistées avec motif et version attendue. Toute transition non prévue est refusée. Un état terminal n’est pas remis à zéro silencieusement.

### Goal

| État | Sens | Sorties |
|---|---|---|
| `PENDING` | Accepté, non planifié | `PLANNING`, `CANCELLED`, `FAILED` |
| `PLANNING` | Construction/révision bornée du plan | `ACTIVE`, `PAUSED`, `FAILED`, `CANCELLED` |
| `ACTIVE` | Objectif en cours | `PLANNING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `PAUSED` | Attente d’une condition explicite | `PLANNING`, `ACTIVE`, `FAILED`, `CANCELLED` |
| `COMPLETED` | Réussite vérifiée | Terminal |
| `FAILED` | Poursuite abandonnée | Terminal |
| `CANCELLED` | Annulé | Terminal |

### Task

| État | Sens | Sorties |
|---|---|---|
| `PENDING` | Dépendances non satisfaites | `READY`, `BLOCKED`, `CANCELLED`, `FAILED` |
| `READY` | Éligible | `RUNNING`, `BLOCKED`, `CANCELLED`, `FAILED` |
| `RUNNING` | Prise en charge par un worker | `COMPLETED`, `BLOCKED`, `FAILED`, `CANCELLED` |
| `BLOCKED` | Attente : quota, approbation, résultat inconnu | `READY`, `FAILED`, `CANCELLED` |
| `COMPLETED` | Critères de fin vérifiés | Terminal |
| `FAILED` | Échec définitif | Terminal |
| `CANCELLED` | Annulée ou obsolète | Terminal |

`BLOCKED -> READY` exige la levée du blocage et le respect des limites ; cela ne préautorise pas la prochaine action.

`RUNNING` correspond au rôle de `ACTIVE` dans le modèle Task actuel. Le renommage exige une migration explicite.

### Decision et Execution

Cycle cible de décision :

```text
PROPOSED -> EVALUATED
EVALUATED -> AUTHORIZED | DENIED | WAITING_APPROVAL | STOPPED
WAITING_APPROVAL -> EVALUATED | EXPIRED | DENIED | STOPPED
AUTHORIZED -> CONSUMED | EXPIRED | REVOKED
```

L’approbation entraîne une réévaluation, pas une exécution directe.

Cycle d’une tentative :

```text
PENDING -> RUNNING -> SUCCEEDED | FAILED | UNKNOWN
PENDING -> CANCELLED
UNKNOWN -> SUCCEEDED | FAILED
```

`UNKNOWN` signifie que l’effet peut avoir eu lieu. Seules des preuves de réconciliation permettent sa résolution. Un timeout n’autorise pas une répétition aveugle.

Une annulation pendant un appel externe interdit les étapes suivantes, sans prouver l’annulation de l’effet en cours.

## 6. Permissions, autonomie et risque

### Contrôles obligatoires

1. Authentifier le mandant et identifier l’agent actif.
2. Vérifier son appartenance au workspace.
3. Vérifier la délégation et ses révocations.
4. Vérifier outil, opération et ressources autorisées.
5. Vérifier le périmètre de l’objectif et de la tâche.
6. Vérifier budget, quotas, échéances et répétitions.
7. Vérifier autonomie et politique de risque.
8. Vérifier les approbations éventuelles.
9. Persister le résultat de contrôle.

L’Executor revérifie avant l’effet les conditions mutables : révocation, expiration, annulation, versions et réservation.

### Autonomie numérique

```text
requested = valeur explicite si fournie, sinon défaut de l’agent
applied = min(requested, plafond agent, plafond délégation,
              plafond objectif, plafond politique, plafond parent)
0 <= applied <= requested <= 5
```

`0` doit être conservé ; `requested or default` viole ce contrat.

- `0` : aucune exécution autonome d’outil ; un mandat ponctuel explicite est nécessaire, en plus des autres contrôles.
- `1..5` : profils progressifs à définir par politique et outil avant activation.
- `5` : jamais une permission universelle.

En l’absence de définition, aucun droit supplémentaire n’est présumé.

### Risque et approbation

Le risque final ne descend jamais sous le plancher de la politique. L’avis IA peut augmenter le risque, pas abaisser ce plancher. Une confiance élevée n’accorde aucun droit. Des confiances proches ne prouvent pas la compatibilité des actions proposées.

Une action sensible peut être préautorisée dans un périmètre précis si une politique explicite le prévoit, jamais par déduction du LLM.

Une approbation :

- Provient d’un acteur authentifié compétent dans le workspace.
- Porte sur une action, une empreinte, une portée et une échéance.
- Ne neutralise pas une interdiction non dérogeable.
- N’accorde pas implicitement des permissions permanentes.
- Ne supprime ni quotas ni conditions de sécurité.
- Devient caduque si l’action change.

L’autonomie ne dispense pas d’autorisation sur les systèmes tiers ni du respect des restrictions des outils.

## 7. Héritage, budgets et quotas

```text
permissions_enfant ⊆ permissions_parent
périmètre_enfant ⊆ périmètre_parent
autonomie_enfant <= autonomie_parent
échéance_enfant <= échéance_parent
```

Les capacités effectives sont l’intersection de celles du parent, de la délégation enfant et des politiques applicables.

Le graphe de délégation est sans cycle, de profondeur bornée et rattaché à une autorité identifiable. Un enfant ne peut éditer sa délégation ni créer d’autres agents pour récupérer des droits.

Le budget parent est partagé, jamais recopié :

- Une allocation enfant réduit le disponible parent.
- Les réservations sont atomiques sur la chaîne de délégation.
- Les allocations/consommations ne sont pas comptées deux fois.
- Un coût inconnu n’est pas nul ; un coût non bornable ne reçoit pas une permission automatique de dépense.
- La révocation parent bloque les nouvelles autorisations descendantes.

Les unités sont explicites : devise, messages, tokens, appels IA, durée ou actions. Les montants utilisent une arithmétique décimale cohérente.

Les fenêtres de quotas sont définies (jour UTC ou fenêtre glissante, par exemple). Tous les workers et enfants partagent les compteurs autoritatifs. Replanifier ou redémarrer ne les réinitialise pas.

## 8. Exécution fiable et audit

Séquence cible :

1. Valider action et politique.
2. Vérifier atomiquement les ressources.
3. Persister décision, autorisation, réservations et intention d’exécution.
4. Confier l’intention à un worker avec prise en charge exclusive.
5. Revérifier les préconditions et appeler l’outil.
6. Persister résultat, coût et transitions.
7. Réconcilier les réservations et réveiller l’Observer.

La persistance avant l’effet ne remplace pas celle du résultat après l’effet.

### Idempotence et concurrence

- Une contrainte durable protège l’opération logique contre les doublons.
- La prise en charge utilise un verrouillage ou une transition conditionnelle versionnée.
- Un bail expiré ne prouve pas l’absence d’effet.
- La clé d’idempotence est transmise au fournisseur lorsqu’il la prend en charge.
- Sans garantie fournisseur, l’exécution « exactement une fois » n’est pas promise.
- Un effet ambigu passe à `UNKNOWN` et doit être réconcilié.
- Une compensation est une nouvelle action soumise à autorisation.

Une transaction PostgreSQL seule ne rend pas atomique un effet sur une API distante.

### Audit durable

Conserver identifiants corrélés, versions de politique, motif du contrôle, empreinte d’action, transitions, acteur, horodatages, tentatives, coûts et références de preuve/approbation.

Le journal est protégé contre les modifications par les agents exécutants. Accès, conservation et effacement légal sont contrôlés. Pas de secrets ni de données personnelles inutiles.

Un logger `INFO` complète l’audit ; il ne garantit pas sa durabilité.

## 9. Boucle autonome bornée

Contrat non exécutable tel quel :

```text
Réveiller un objectif actif
 -> vérifier annulation, échéance et limites
 -> vérifier les critères de réussite
 -> sélectionner une tâche prête
 -> proposer et arbitrer une action structurée
 -> contrôler :
      ALLOW    : exécuter, observer, persister
      DENY     : enregistrer, envisager une alternative autorisée
      ESCALATE : persister l’attente, suspendre la branche
      STOP     : arrêter le périmètre concerné avec motif
 -> vérifier progression, coûts, erreurs et répétitions
 -> terminer ou planifier une étape bornée
```

Sans tâche prête, attendre un événement connu ou constater un blocage ; ne pas boucler à vide.

Limiter de façon persistante étapes, durée, budget (y compris appels IA), tentatives, replanifications, répétitions, absence de progression, erreurs et nombre/profondeur d’enfants.

Un refus ne peut pas être contourné par reformulation d’une opération au même effet interdit. L’apprentissage enrichit le contexte, pas les permissions.

L’arrêt d’urgence est vérifié avant chaque nouvel effet. Les opérations engagées restent suivies jusqu’à un résultat établi ou explicitement incertain.

## 10. Invariants et validation

| ID | Invariant | Preuve attendue |
|---|---|---|
| INV-01 | Aucun effet sans autorisation valide | Aucun appel d’outil pour `DENY`, `ESCALATE`, `STOP` |
| INV-02 | Isolation du workspace | Agent extérieur rejeté avant accès au contexte/outil |
| INV-03 | Action arbitrée immuable | Modification d’arguments invalidant l’autorisation |
| INV-04 | Risque transmis et non abaissé | Risque IA supérieur conservé dans la décision |
| INV-05 | Autonomie zéro préservée | `0` ne devient pas le défaut agent |
| INV-06 | Autorité extérieure au LLM | Une permission « accordée » par l’IA n’a aucun effet |
| INV-07 | Délégation restrictive | L’enfant ne dépasse jamais les capacités parent |
| INV-08 | Budget partagé | Pas de double réservation du même solde |
| INV-09 | Pas de répétition aveugle | Timeout ambigu produisant `UNKNOWN` |
| INV-10 | États terminaux protégés | Pas de remise en exécution silencieuse |
| INV-11 | Audit durable | Refus, escalades et tentatives persistés et corrélés |
| INV-12 | Succès vérifiable | Critères de Goal observables satisfaits |
| INV-13 | Boucle bornée | Absence de progrès déclenchant attente/arrêt |
| INV-14 | Révocation effective | Autorisation expirée/révoquée non consommée |
| INV-15 | Reprise cohérente | Compteurs et opérations incertaines conservés |
| INV-16 | Autonomie effective | Action préautorisée conforme exécutée sans confirmation |

Les futurs tests doivent couvrir services, HTTP, PostgreSQL, concurrence, reprises et adaptateurs contrôlés. Les mocks seuls ne prouvent pas les garanties de persistance.

## 11. Existant et écarts constatés lors de l’audit

Cette section décrit le point de départ, pas des corrections déjà livrées.

| Zone | Existant / écart |
|---|---|
| Goal | Modèle et états présents, comportement opérationnel absent |
| Task | `ACTIVE` au lieu du rôle cible `RUNNING` ; historique/dépendances à enrichir |
| Decision | `pending_approval`, `executed`, `rejected`, `escalated`, `expired` ; autorisation/exécution à séparer |
| Orchestrator | Risque omis, action arbitrée écrasée, escalades non persistées |
| Injection | Arbitre sans session ; simulateur omis par la factory |
| Guard | Contrôles de permission effective et de validité incomplets |
| Autonomie | Plafond fixe à 5 ; zéro remplacé par défaut |
| Risque | Analyste retournant systématiquement `low` |
| Identity | Authentification et appartenance workspace non opérationnelles |
| Memory | Mélange Decimal/float ; filtre `decision` absent de l’Enum |
| Persistance | Noms d’Enums divergents, métadonnées Alembic incomplètes |
| Audit | Log `INFO`, pas de garantie durable |
| Outils | Connecteurs squelettiques |
| Tests | Majoritairement simulés ; intégration et concurrence à ajouter |

Références : `app/goal_engine/models.py`, `app/task_engine/models.py`, `app/decision_engine/models.py`, `app/decision_engine/services/orchestrator.py`, `app/decision_engine/services/arbitrator.py`, `app/core/dependencies.py`, `app/execution/services/guard.py`, `app/execution/services/executor.py`, `app/execution/services/auditor.py`, `app/identity/services/isolation.py`, `app/alembic/env.py`.

Les migrations futures doivent préserver le sens des états et l’historique.

## 12. Ordre d’implémentation

### Phase 1 — Decision Engine

Préserver l’action arbitrée ; transmettre le risque ; charger les politiques ; dériver `permission_granted` côté serveur ; préserver zéro ; définir `ALLOW / DENY / ESCALATE / STOP`.

**Sortie : une décision conserve son action et son risque ; aucune absence de politique ne peut autoriser une action.**

Tests sans connecter d’outils externes. Cette phase ne constitue pas une livraison de l’ensemble des contrôles futurs ni une activation de routes non authentifiées.

### Phase 2 — Exécution fiable

Structurer Action/Authorization/Execution/Result ; états, audit durable, réservations, idempotence ; corriger la persistance nécessaire ; identité et isolation avant exposition HTTP.

Sortie : effet contrôlé traçable après redémarrage ; concurrence et résultat incertain testés.

### Phase 3 — Autonomous Loop

Rendre Goal/Task opérationnels ; observation, reprises, replanification bornée ; profils d’autonomie, critères de réussite et arrêt d’urgence.

Sortie : objectif préautorisé atteint sans confirmation intermédiaire, ou arrêt explicite sans dépassement des limites.

### Phase 4 — Outils réels

Connecteurs activés un à un ; droits, conditions d’usage, schémas, quotas, coûts et réconciliation. Aucun exécuteur universel d’actions libres.

Sortie : chaque outil n’est accessible que par le chemin d’autorisation.

### Phase 5 — Hiérarchie multi-agent

Délégation restrictive, révocation, profondeur bornée, budgets partagés et supervision.

Sortie : contribution de plusieurs agents sans multiplication des ressources ni élargissement du périmètre.

## 13. Paramètres à fixer avant la phase concernée

- Profils précis d’autonomie `1..5`.
- Autorités de délégation et révocation.
- Politiques de risque et interdictions non dérogeables.
- Unités/fenêtres de quotas et coûts incertains.
- Critères de réussite par objectif.
- Stockage et conservation d’audit.
- Ordonnancement, reprise et réconciliation par outil.
- Migration et compatibilité des états.

Ces paramètres ne sont pas laissés à l’invention du LLM à l’exécution.

## Conclusion

La cible est une autonomie réelle dans un cadre explicite : décider et agir sans confirmation systématique, avec permissions, budgets, états et délégations vérifiables.

L’implémentation consolide le moteur existant avant d’ajouter la boucle autonome, les outils réels et les sous-agents.