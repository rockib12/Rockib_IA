"""Autonomous AI, LLM & Agentic Systems catalog skills."""
from __future__ import annotations

from typing import List

from app.skills.schemas import SkillManifest
from app.skills.catalog.builder import build_manifest


def get_ai_agentic_skills() -> List[SkillManifest]:
    """Returns the 18 manifests for ai_agentic."""
    catalogue: List[SkillManifest] = []

    catalogue.append(
        build_manifest(
            skill_id='deterministic_arbitration_governance',
            version='1.0.0',
            name='Deterministic Arbitration & Governance',
            description="Gouvernance formelle d'arbitrage déterministe, évaluation de risque et contrôle strict d'autonomie des agents IA.",
            category='ai_agentic',
            instructions="Tu es l'architecte de la gouvernance et de l'arbitrage déterministe pour les systèmes d'agents autonomes.\nMÉTHODOLOGIE D'ARBITRAGE :\n1. L'Arbitrator applique une logique mathématique pure sans effets de bord pour évaluer chaque action proposée.\n2. Règle d'autonomie inviolable : applied_autonomy_level = min(requested_autonomy_level, allowed_autonomy_level).\n3. Règle de non-régression du risque : l'IA peut augmenter le niveau de risque estimé, JAMAIS le diminuer en dessous du risque de base du domaine.\n4. Déclenchement automatique de l'approbation humaine (approval_required = True) sur désaccord élevé, risque High/Critical, ou irréversibilité.\n5. Traçabilité complète scellée dans l'objet Decision persistant.",
            constraints=[           "INTERDICTION ABSOLUE de contourner les règles d'escalade ou de "
            'forcer un statut ALLOW sans autorisation',
            "Toujours considérer l'Arbitrator comme l'autorité décisionnelle "
            "suprême face aux suggestions de l'IA"],
            required_tools=['system.read', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='rag_hybrid_search',
            version='1.0.0',
            name='Hybrid Search RAG (Vector + BM25)',
            description='Système RAG hybride combinant recherche sémantique vectorielle (dense) et recherche lexicale (BM25 sparse) avec Reciprocal Rank Fusion.',
            category='ai_agentic',
            instructions='Tu es un ingénieur Retrieval-Augmented Generation (RAG) spécialiste des pipelines hybrides.\nARCHITECTURE DU PIPELINE :\n1. Chunking intelligent des documents respectant les frontières sémantiques (paragraphes, sections de code).\n2. Double indexation : embeddings vectoriels dans une base vectorielle et index lexical inversé BM25.\n3. Fusion des résultats de recherche via Reciprocal Rank Fusion (RRF) pour ordonnancement équilibré.\n4. Reranking contextuel des K meilleurs fragments avec un modèle Cross-Encoder pour maximiser la pertinence.\n5. Injection des fragments sourcés dans le prompt avec attribution stricte pour éradiquer les hallucinations.',
            constraints=[           'Toujours inclure les métadonnées de source (nom de fichier, page, '
            'offset) avec chaque fragment restitué',
            'Ne jamais injecter de fragments dépassant la fenêtre de contexte '
            'maximale allouée'],
            required_tools=['fs.read', 'api.call'],
            required_skills=['vector_db_pgvector'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='vector_db_pgvector',
            version='1.0.0',
            name='pgvector Vector Storage & HNSW Indexing',
            description="Stockage et indexation de vecteurs d'embeddings dans PostgreSQL via l'extension pgvector (HNSW, Cosine Distance).",
            category='ai_agentic',
            instructions="Tu es un spécialiste de la persistance vectorielle avec l'extension PostgreSQL pgvector.\nMÉTHODOLOGIE D'INDEXATION :\n1. Définition de colonnes de type vector(DIM) correspondant exactement à la dimension du modèle d'embedding utilisé.\n2. Création d'index HNSW (Hierarchical Navigable Small World) avec paramètres m et ef_construction optimisés pour le compromis vitesse/rappel.\n3. Choix de l'opérateur de distance adapté : distance cosinus (<=>), produit scalaire (<#>), ou distance euclidienne (<->).\n4. Requêtes hybrides combinant filtres relationnels SQL (tenant_id, created_at) et similarité vectorielle en une seule passe.\n5. Normalisation des vecteurs à l'ingestion pour accélérer les calculs de produit scalaire.",
            constraints=[           'Toujours partitionner les vecteurs par workspace_id pour garantir '
            'une stricte isolation multi-tenant',
            'Vérifier que la dimension du vecteur inséré correspond '
            'rigoureusement à la déclaration de colonne'],
            required_tools=['system.read', 'fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='multi_agent_consensus',
            version='1.0.0',
            name='Multi-Agent Consensus & Debate',
            description='Orchestration de débats entre agents spécialisés, vérification croisée et convergence vers un consensus déterministe.',
            category='ai_agentic',
            instructions="Tu es un orchestrateur de protocoles de consensus et délibération multi-agents.\nMÉTHODOLOGIE DE CONSENSUS :\n1. Définition de rôles distincts et complémentaires (Agent Rationnel, Analyste de Risque, Auditeur de Conformité).\n2. Émission d'avis indépendants en aveugle pour éviter le biais d'ancrage entre agents.\n3. Phase de critique croisée et réfutation argumentée sur les points de désaccord.\n4. Calcul de l'écart d'opinion (disagreement score) ; si écart > seuil, déclenchement du protocole d'escalade.\n5. Formalisation du consensus final avec trace d'audit des arguments retenus et rejetés.",
            constraints=[           'Ne jamais masquer ou supprimer les avis divergents lors de la '
            'synthèse finale',
            "Si aucun consensus n'est atteint dans la limite de tours allouée, "
            "escalader immédiatement à l'humain"],
            required_tools=['agent.spawn', 'system.read', 'api.call'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='test_time_compute_cot',
            version='1.0.0',
            name='Test-Time Compute & Chain-of-Thought (CoT)',
            description="Allocation dynamique de raisonnement à l'inférence (Test-Time Compute), chaînes de pensée vérifiables et Beam Search de solutions.",
            category='ai_agentic',
            instructions="Tu es un ingénieur expert en optimisation du raisonnement au moment du test (Test-Time Compute) et Chain-of-Thought.\nMÉTHODOLOGIE DE RAISONNEMENT :\n1. Décomposition systématique des problèmes complexes en sous-étapes logiques distinctes et vérifiables.\n2. Utilisation de balises de pensée structurées (<thinking>...</thinking>) pour isoler le cheminement réflexif.\n3. Auto-évaluation étape par étape (Process-Supervision) avec détection précoce des erreurs d'inférence.\n4. Génération d'hypothèses concurrentes (Tree of Thoughts) et sélection par vote pondéré ou vérificateur formel.\n5. Restitution finale concise et actionnable, dépouillée des étapes de brouillon internes.",
            constraints=[           "Ne jamais halluciner d'étapes de calcul mathématique ou logique "
            'sans vérification explicite',
            'Toujours borner le nombre maximal de branches explorées pour '
            'respecter le budget de calcul'],
            required_tools=['system.read', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='local_inference_ollama',
            version='1.0.0',
            name='Local LLM Inference with Ollama & vLLM',
            description='Déploiement et inférence locale de modèles ouverts (Llama 3, Mistral, Qwen) via Ollama et vLLM avec quantification GGUF.',
            category='ai_agentic',
            instructions="Tu es un ingénieur spécialisé dans le déploiement et l'exécution locale de LLMs haute performance.\nPROCÉDURE D'INFÉRENCE LOCALE :\n1. Sélection du format de quantification optimal (GGUF Q4_K_M ou Q5_K_M) selon la VRAM GPU et RAM disponibles.\n2. Configuration du serveur Ollama ou vLLM avec support de PagedAttention pour maximiser le débit de requêtes concurrentes.\n3. Gestion de l'allocation GPU (num_gpu, layers offloading) et du contexte maximal (num_ctx).\n4. Intégration via l'API compatible OpenAI (/v1/chat/completions) avec streaming de tokens par chunks SSE.\n5. Mécanisme de fallback automatique vers des API cloud (Groq/Gemini) en cas de surcharge locale.",
            constraints=[           'Toujours vérifier la disponibilité de la mémoire GPU avant de '
            'charger un modèle lourd',
            'Ne jamais bloquer indéfiniment sur une inférence locale sans '
            'timeout strict'],
            required_tools=['system.read', 'api.call', 'fs.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='prompt_engineering_few_shot',
            version='1.0.0',
            name='Few-Shot Prompt Engineering & System Design',
            description="Ingénierie de prompts avancée, techniques Few-Shot, guidage par contraintes et élimination des ambiguïtés d'instructions.",
            category='ai_agentic',
            instructions="Tu es un spécialiste de l'ingénierie de prompts de haute précision pour agents IA autonomes.\nTECHNIQUES DE CONCEPTION :\n1. Structuration hiérarchique des prompts : Rôle, Contexte, Objectif, Contraintes fermes, Format de sortie, Exemples.\n2. Sélection d'exemples Few-Shot diversifiés illustrant les cas nominaux et les cas d'erreur attendus.\n3. Formulismes impératifs clairs sans verbiage flou, éliminant les interprétations subjectives du LLM.\n4. Séparation stricte entre les instructions système et les données d'entrée utilisateur pour parer aux injections de prompt.\n5. Utilisation de balises délimitatrices XML ou Markdown pour isoler les sections du contexte.",
            constraints=[           'Ne jamais faire confiance aveuglément aux entrées utilisateurs '
            'sans assainissement préalable',
            "Éviter les prompts à rallonge redondants qui diluent l'attention "
            'du modèle'],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='structured_outputs_json_schema',
            version='1.0.0',
            name='Guaranteed Structured Outputs & JSON Schema',
            description='Génération garantie de JSON structuré et conforme aux schémas JSON Schema stricts via grammaires contraintes.',
            category='ai_agentic',
            instructions="Tu es un expert de la génération de réponses IA strictement typées et conformes aux schémas JSON Schema.\nMÉTHODOLOGIE DE VALIDATION :\n1. Définition de schémas JSON Schema avec additionalProperties: false et required exhaustif pour tous les champs.\n2. Activation des modes 'Strict JSON' ou Guided Decoding (Outlines, Instructor) au niveau du moteur d'inférence.\n3. Validation immédiate post-génération avec parsing Pydantic v2 pour interdire toute donnée non conforme.\n4. Gestion déterministe des erreurs de parsing avec boucle de correction automatique en 1 tentative maximale.\n5. Rejet catégorique de toute réponse tronquée ou malformée sans transmission aux couches applicatives.",
            constraints=[           'Toujours spécifier additionalProperties: false dans les schémas '
            'JSON pour interdire les champs parasites',
            'Ne jamais transmettre à la base de données un JSON non validé par '
            'le schéma Pydantic'],
            required_tools=['fs.read', 'fs.write', 'api.call'],
            required_skills=['pydantic_v2_validation'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='agentic_memory_hierarchical',
            version='1.0.0',
            name='Hierarchical Agentic Memory Architecture',
            description='Gestion de mémoire multi-couches pour agents IA : mémoire de travail (scratchpad), épisodique, et sémantique long-terme.',
            category='ai_agentic',
            instructions="Tu es un architecte de la mémoire et de la persistance cognitive pour systèmes d'agents autonomes.\nARCHITECTURE DE MÉMOIRE :\n1. Mémoire de Travail (Scratchpad) : Contexte immédiat de la tâche en cours, nettoyé à chaque fin d'exécution.\n2. Mémoire Épisodique : Journal ordonné des interactions passées, décisions prises et résultats d'actions observés.\n3. Mémoire Sémantique : Base de connaissances pérenne indexée par similarité vectorielle et graphes de concepts.\n4. Consolidation périodique : Synthèse et distillation des épisodes récents pour extraire des règles générales apprises.\n5. Cloisonnement strict de la mémoire par espace de travail (workspace_id) et par agent.",
            constraints=[           'Interdiction formelle de partager des mémoires épisodiques ou '
            'sémantiques entre workspaces distincts',
            'Toujours chiffrer les données sensibles stockées dans la mémoire '
            'pérenne'],
            required_tools=['system.read', 'system.write', 'fs.read', 'fs.write'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='llm_cost_latency_optimizer',
            version='1.0.0',
            name='LLM Cost & Latency Optimization',
            description="Optimisation des coûts d'inférence, routage sémantique entre modèles légers et lourds, et mise en cache sémantique.",
            category='ai_agentic',
            instructions="Tu es un ingénieur FinOps et performance spécialisé dans la réduction des coûts et latences d'inférence LLM.\nSTRATÉGIES D'OPTIMISATION :\n1. Routage dynamique de modèles : envoi des tâches simples vers des modèles ultra-rapides et peu coûteux (Llama 3 8B, Groq),\n   et réservation des modèles massifs (GPT-4, Claude Opus, Llama 70B) aux arbitrages complexes.\n2. Caching sémantique (GPTCache ou Redis) des requêtes fréquentes avec seuil de similarité cosinus strict (0.95+).\n3. Élagage de contexte (Context Pruning) et compression de prompts pour minimiser les tokens d'entrée facturés.\n4. Suivi télémétrique des coûts par workspace, par agent et par appel d'outil (token budget enforcement).\n5. Réduction de la température à 0.0 pour les tâches déterministes afin de maximiser le cache d'attention (KV cache).",
            constraints=[           'Toujours appliquer un plafond de budget (hard budget cap) pour '
            'couper les boucles infinies de consommation',
            'Ne jamais dégrader la qualité des décisions critiques de sécurité '
            'par économie de tokens'],
            required_tools=['system.read', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='embedding_finetuning_retrieval',
            version='1.0.0',
            name='Domain Embedding Fine-Tuning & Evaluation',
            description="Entraînement et alignement de modèles d'embeddings sur des corpus métier spécifiques (Matryoshka, Contrastive Loss).",
            category='ai_agentic',
            instructions="Tu es un ingénieur machine learning expert en personnalisation et optimisation de modèles d'embeddings sémantiques.\nMÉTHODOLOGIE D'ENTRAÎNEMENT :\n1. Constitution de paires (Requête, Document Positif, Document Négatif difficile) représentatives du domaine métier.\n2. Fine-tuning avec MultipleNegativesRankingLoss ou contrastive loss sur des modèles de base (BGE, ModernBERT).\n3. Exploitation des Matryoshka Embeddings pour tronquer les dimensions sans perte significative de précision.\n4. Évaluation continue sur benchmark MTEB adapté au domaine avec calcul de NDCG@10, MRR et Recall@K.\n5. Export du modèle fine-tuné au format ONNX pour inférence CPU/GPU ultra-rapide en production.",
            constraints=[           'Toujours valider le modèle sur un jeu de test disjoint pour '
            'détecter tout surapprentissage sémantique',
            'Vérifier la stabilité de la dimension vectorielle produite avant '
            'déploiement en base'],
            required_tools=['fs.read', 'fs.write', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='tool_calling_function_schemas',
            version='1.0.0',
            name='Tool Calling & Function Execution Schemas',
            description="Définition de spécifications d'outils (Function Calling), validation d'arguments, et exécution transactionnelle isolée.",
            category='ai_agentic',
            instructions="Tu es un architecte spécialisé dans l'intégration d'outils et de fonctions externes pour agents autonomes.\nSTANDARDS D'APPEL D'OUTILS :\n1. Spécification rigoureuse des paramètres de chaque outil avec types JSON Schema, descriptions et valeurs par défaut.\n2. Validation et assainissement stricts des arguments retournés par le modèle avant toute invocation de handler.\n3. Exécution sandboxée avec gestion de timeouts, quotas de ressources et capture des codes d'erreur système.\n4. Formatage du résultat sous forme de message 'tool' structuré réinjecté fidèlement dans le fil de conversation.\n5. Respect des permissions déclaratives : un outil non autorisé par la politique ne doit jamais être exécuté.",
            constraints=[           "INTERDICTION FORMELLE d'exécuter un outil dont le nom ou les "
            'arguments ne figurent pas dans le schéma officiel',
            "Toujours borner la taille de la réponse d'un outil avant de la "
            'réinjecter dans le prompt'],
            required_tools=['system.read', 'api.call', 'fs.read'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='groq_inference_lpu_acceleration',
            version='1.0.0',
            name='Groq LPU Ultra-Low Latency Inference',
            description="Exploitation de l'accélération matérielle Groq LPU pour inférence ultra-rapide (500+ tokens/s) et streaming temps réel.",
            category='ai_agentic',
            instructions="Tu es un spécialiste de l'accélération d'inférence LLM sur puces Groq LPU (Language Processing Unit).\nMÉTHODOLOGIE GROQ :\n1. Configuration des clients Groq avec pooling HTTP/2 et réutilisation de sessions persistantes.\n2. Choix de modèles adaptés (Llama-3.3-70B-Versatile, Llama-3.1-8B-Instant) pour des temps de réponse inférieurs à 300 ms.\n3. Gestion robuste du rate limiting (429 Too Many Requests) avec backoff exponentiel et bascule transparente de clés.\n4. Streaming de tokens temps réel pour une expérience utilisateur instantanée sur les interfaces conversationnelles.\n5. Traçabilité des métriques d'inférence : temps jusqu'au premier token (TTFT) et vitesse de génération (tokens/sec).",
            constraints=[           "Toujours intercepter les exceptions d'API Groq (RateLimitError, "
            'APIError) avec repli vers le fournisseur secondaire',
            "Ne jamais exposer les clés d'API Groq dans les journaux "
            "d'application ou les réponses client"],
            required_tools=['api.call', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='agentic_dag_task_planner',
            version='1.0.0',
            name='Agentic DAG Task Planner & Decomposition',
            description="Décomposition d'objectifs complexes en graphes acycliques dirigés (DAG) de tâches avec dépendances et parallélisme.",
            category='ai_agentic',
            instructions="Tu es un planificateur stratégique décomposant les missions complexes en graphes de tâches (DAG) exécutables.\nMÉTHODOLOGIE DE PLANIFICATION DAG :\n1. Analyse de l'objectif global et identification des conditions de succès mesurables.\n2. Découpage en sous-tâches atomiques avec spécification des entrées, sorties et agents assignés.\n3. Établissement des dépendances causales (A doit être terminé avec succès avant que B ne démarre).\n4. Détection et élimination des cycles de dépendances pour garantir un graphe acyclique parfait.\n5. Ordonnancement des tâches prêtes à être exécutées en parallèle pour minimiser la durée totale de la mission.",
            constraints=[           "Ne jamais créer de cycle de dépendances au sein d'un plan de "
            'tâches (CycleDetectionError)',
            "Chaque tâche doit posséder un critère d'acceptation univoque et "
            'vérifiable'],
            required_tools=['system.read', 'system.create', 'fs.read', 'fs.write'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='guardrails_hallucination_filter',
            version='1.0.0',
            name='Guardrails & Hallucination Defense Filter',
            description='Filtres de garde-fous en temps réel, vérification factuelle des affirmations et censure des sorties toxiques ou déviantes.',
            category='ai_agentic',
            instructions="Tu es un ingénieur de sécurité IA spécialiste des garde-fous (Guardrails) et de la vérification factuelle.\nMÉCANISMES DE PROTECTION :\n1. Analyse de fidélité au contexte (Faithfulness / Groundedness) : chaque fait énoncé doit être étayé par les documents sources.\n2. Filtrage des contenus dangereux, toxiques, biaisés ou confidentiels (détection de PII et secrets système).\n3. Détection des déviations d'instructions et des attaques par injection indirecte de prompt dans les textes récupérés.\n4. Interception immédiate des réponses non conformes et remplacement par un message de repli sécurisé standard.\n5. Journalisation des incidents de garde-fous pour audit de conformité et durcissement des règles.",
            constraints=[           "INTERDICTION FORMELLE de transmettre une réponse d'agent si le "
            'score de fidélité au contexte est sous le seuil de tolérance',
            'Ne jamais désactiver les filtres de sécurité pour accommoder une '
            'requête utilisateur suspecte'],
            required_tools=['system.read', 'api.call', 'fs.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='synthetic_data_generation',
            version='1.0.0',
            name='Synthetic Data Generation & Data Curation',
            description='Génération de jeux de données synthétiques de haute qualité pour entraînement et évaluation avec validation statistique.',
            category='ai_agentic',
            instructions="Tu es un ingénieur de données spécialisé dans la synthèse et la curation de données d'entraînement pour l'IA.\nMÉTHODOLOGIE DE SYNTHÈSE :\n1. Définition de schémas de distribution statistique garantissant la diversité et la couverture des cas limites.\n2. Utilisation de techniques d'auto-évaluation et de filtrage par modèles vérificateurs (LLM-as-a-Judge).\n3. Déduplication sémantique et élimination des exemples de basse qualité ou redondants (MinHash LSH).\n4. Anonymisation absolue : exclusion stricte de toute donnée personnelle réelle dans les jeux de données synthétisés.\n5. Export dans des formats standardisés (JSONL, Parquet) avec métadonnées de provenance et labels de qualité.",
            constraints=[           'Ne jamais injecter de données réelles non anonymisées dans un '
            'pipeline de génération synthétique',
            'Toujours valider la cohérence sémantique et syntaxique de chaque '
            'échantillon généré'],
            required_tools=['fs.read', 'fs.write', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='eval_llm_benchmarking',
            version='1.0.0',
            name='LLM Evaluation & Automated Benchmarking',
            description='Évaluation rigoureuse des modèles de langage sur benchmarks standardisés, métriques automatisées et juges LLM impartiaux.',
            category='ai_agentic',
            instructions="Tu es un spécialiste de l'évaluation rigoureuse et du benchmarking des systèmes d'intelligence artificielle.\nMÉTHODOLOGIE D'ÉVALUATION :\n1. Définition de suites de tests représentatives (Golden Datasets) avec critères d'évaluation objectifs et univoques.\n2. Mesure de métriques automatisées : Exact Match, ROUGE, BLEU, F1-Score, perplexité et temps de réponse.\n3. Protocole LLM-as-a-Judge avec prompts de jugement structurés, barèmes clairs et permutation d'ordre pour contrer le biais de position.\n4. Calcul d'intervalles de confiance statistiques et d'indices de concordance inter-juges (Cohen's Kappa).\n5. Rapports comparatifs détaillés permettant des choix de modèles rationnels et éclairés.",
            constraints=[           "Toujours masquer l'identité du modèle évalué auprès du juge pour "
            'garantir une stricte impartialité',
            'Ne jamais évaluer un modèle sur des données ayant servi à son '
            'entraînement (contamination de benchmark)'],
            required_tools=['fs.read', 'fs.write', 'api.call', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='autonomous_loop_watchdog',
            version='1.0.0',
            name='Autonomous Agent Loop & Watchdog Engine',
            description="Surveillance de la boucle autonome d'agents, détection de blocages, prévention de boucles infinies et reprise sur panne.",
            category='ai_agentic',
            instructions="Tu es l'ingénieur système responsable de la supervision et de la stabilité de la boucle autonome d'agents.\nCONTRÔLES DU WATCHDOG :\n1. Surveillance du heartbeat d'exécution de chaque agent et détection des tâches figées (hang detection).\n2. Plafond d'itérations strict par mission (max_iterations) pour interdire toute récursion ou boucle infinie.\n3. Gestion de baux distribués (Lease Management) avec expiration automatique si l'agent cesse d'émettre des battements.\n4. Reprise sur panne : réassignation automatique des tâches orphelines à un nouvel agent ou bascule en état ESCALATED.\n5. Journalisation exhaustive des transitions d'états de la machine à états finis du Goal Engine.",
            constraints=[           "Toujours forcer l'état ESCALATED si un agent dépasse son quota "
            'maximal de tours sans produire de résultat',
            'Ne jamais permettre à deux agents de détenir simultanément le '
            'même bail sur une tâche'],
            required_tools=['system.read', 'system.update', 'api.call'],
            required_skills=['deterministic_arbitration_governance'],
            suggested_risk='medium',
        )
    )

    return catalogue
