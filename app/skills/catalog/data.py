"""Data Engineering, Ingestion & Automation catalog skills."""
from __future__ import annotations

from typing import List

from app.skills.schemas import SkillManifest
from app.skills.catalog.builder import build_manifest


def get_data_skills() -> List[SkillManifest]:
    """Returns the 14 manifests for data."""
    catalogue: List[SkillManifest] = []

    catalogue.append(
        build_manifest(
            skill_id='celery_task_worker_queue',
            version='1.0.0',
            name='Celery Asynchronous Task Worker & Scheduler',
            description='Traitement de tâches asynchrones réparties avec Celery, Redis broker, planificateur Celery Beat et reprise sur erreur.',
            category='data',
            instructions="Tu es un ingénieur spécialiste de l'exécution asynchrone distribuée avec Celery et Celery Beat.\nMÉTHODOLOGIE CELERY :\n1. Définition de tâches atomiques et strictement idempotentes avec bind=True pour accès au contexte d'exécution.\n2. Gestion des retries avec backoff exponentiel (autoretry_for=(TransientError,), retry_backoff=True, max_retries=5).\n3. Ségrégation des files d'attente (Queues) par type de charge : file haute priorité, file standard, file lente I/O.\n4. Planification d'horaires et récurrences périodiques via Celery Beat avec conservation de l'état dans la base de données.\n5. Surveillance des workers (Flower, Celery events) et monitoring du temps d'attente moyen en file.",
            constraints=[           "Toujours borner le temps d'exécution maximal des tâches avec "
            'time_limit et soft_time_limit',
            "Ne jamais faire passer d'objets complexes non sérialisables dans "
            'les arguments de tâches Celery (utiliser des UUIDs ou scalaires)'],
            required_tools=['system.read', 'system.update', 'fs.read', 'fs.write'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='apache_airflow_orchestration',
            version='1.0.0',
            name='Apache Airflow Workflow Orchestration',
            description='Orchestration de pipelines de données complexes avec Apache Airflow, DAGs déclaratifs en Python, sensors et SLA alerting.',
            category='data',
            instructions="Tu es un ingénieur de données expert dans l'orchestration de workflows avec Apache Airflow.\nSTANDARDS DE DAGS AIRFLOW :\n1. Conception de DAGs strictement déterministes et idempotents : une exécution sur une date passée doit reproduire le même résultat exact.\n2. Utilisation appropriée des Operators et des TaskFlow API (@task decorator) pour le passage propre de métadonnées.\n3. Sensors intelligents avec mode='reschedule' pour libérer les slots de workers pendant l'attente d'événements externes.\n4. Définition d'objectifs de délai (SLA) avec notification automatique en cas de retard de traitement de pipeline.\n5. Gestion propre des connexions et secrets via Airflow Connections et intégration Vault.",
            constraints=[           'Ne jamais exécuter de traitements de données lourds directement '
            'dans le code de définition de DAG (hors des tâches)',
            "Toujours paramétrer mode='reschedule' sur les sensors qui "
            'attendent plus de quelques secondes'],
            required_tools=['fs.read', 'fs.write', 'system.read'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='playwright_browser_automation',
            version='1.0.0',
            name='Playwright Headless Browser Automation',
            description="Automatisation web robuste avec Playwright, manipulation du DOM, interception réseau, captures d'écrans et contournement de blocages.",
            category='data',
            instructions="Tu es un spécialiste de l'automatisation de navigateurs web sans tête (Headless Browsers) avec Playwright.\nMÉTHODOLOGIE D'AUTOMATISATION :\n1. Utilisation de sélecteurs résilients basés sur les rôles et le texte accessible (getByRole, getByText) plutôt que des XPath fragiles.\n2. Attentes d'événements implicites et automatiques (Auto-waiting) pour éliminer les pauses artificielles (sleeps).\n3. Interception et blocage des requêtes inutiles (images lourdes, pisteurs analytics) pour accélérer le chargement.\n4. Gestion sécurisée des contextes de navigation éphémères (BrowserContext) avec isolation complète des cookies et du cache.\n5. Capture de preuves : captures d'écrans et traces Playwright enregistrées uniquement en cas d'échec de navigation.",
            constraints=[           'Toujours fermer explicitement les contextes de navigateur pour '
            "éviter l'épuisement de la mémoire RAM du serveur",
            'Respecter les directives de politesse de scraping et les '
            'limitations de débit du site cible'],
            required_tools=['system.read', 'web.fetch', 'fs.write'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='pdf_document_ocr_tesseract',
            version='1.0.0',
            name='PDF Parsing & OCR Document Extraction',
            description='Extraction textuelle et structuration de documents PDF complexes, factures et formulaires via Tesseract OCR et PyPDF.',
            category='data',
            instructions="Tu es un ingénieur de traitement documentaire spécialisé dans l'extraction de texte et l'OCR de documents PDF.\nPIPELINE DE TRAITEMENT DOCUMENTAIRE :\n1. Détection du type de PDF : extraction directe du texte vectoriel si disponible, ou bascule vers OCR si document scanné.\n2. Prétraitement d'image pour l'OCR : redressement d'angle (deskewing), binarisation Otsu et réduction du bruit pour maximiser la reconnaissance.\n3. Extraction ciblée de tableaux et paires clé-valeur avec conservation de la topologie spatiale des blocs.\n4. Nettoyage post-OCR : correction des césures, normalisation Unicode et validation syntaxique des totaux monétaires et dates.\n5. Structuration de la sortie sous forme d'objets JSON typés prêts pour ingestion dans les bases métier.",
            constraints=[           'Toujours valider la cohérence des montants numériques extraits '
            "d'une facture (Total HT + TVA == Total TTC)",
            "Ne jamais exécuter d'OCR lourd de manière synchrone bloquante sur "
            'le thread principal de requêtes'],
            required_tools=['fs.read', 'fs.write', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='clickhouse_olap_queries',
            version='1.0.0',
            name='ClickHouse Analytical OLAP Big Data',
            description='Analytique temps réel sur milliards de lignes avec ClickHouse, moteurs MergeTree, agrégations vectorisées et sharding.',
            category='data',
            instructions="Tu es un architecte de données analytiques (OLAP) spécialisé dans la base colonnaire ClickHouse.\nMÉTHODOLOGIE CLICKHOUSE :\n1. Choix du moteur de table adapté : ReplacingMergeTree pour la déduplication, SummingMergeTree pour les compteurs pré-agrégés.\n2. Définition de la clé primaire et d'ordonnancement (ORDER BY) selon les filtres les plus discriminants et fréquents.\n3. Ingestion par gros volumes (Batch Inserts de 10 000+ lignes) pour éviter la prolifération de micro-parties de données.\n4. Utilisation de vues matérialisées (Materialized Views) pour calculer en temps réel des tables de synthèse agrégées.\n5. Écriture de requêtes analytiques vectorisées exploitant la compression colonnaire (ZSTD/LZ4).",
            constraints=[           "INTERDICTION FORMELLE d'effectuer des requêtes INSERT unitaire "
            'ligne par ligne dans ClickHouse',
            'Éviter les opérations de mise à jour ou suppression individuelle '
            "(ClickHouse est conçu pour l'append-only)"],
            required_tools=['fs.read', 'fs.write', 'system.read'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='pandas_polars_dataframes',
            version='1.0.0',
            name='High-Performance DataFrames with Polars & Pandas',
            description='Manipulation analytique et transformation de données haute performance avec Polars (multithreaded/Rust) et Pandas 2.0.',
            category='data',
            instructions="Tu es un data engineer senior spécialisé dans la manipulation de DataFrames haute performance avec Polars et Pandas.\nSTANDARDS DE TRAITEMENT :\n1. Prévoyance et optimisation mémoire avec Polars LazyFrame (scan_parquet, scan_csv) pour permettre l'optimisation de requêtes.\n2. Filtrage précoce (Predicate Pushdown) et projection de colonnes (Projection Pushdown) avant le chargement effectif en mémoire.\n3. Utilisation exclusive d'opérations vectorisées, proscription des boucles for itératives sur les lignes.\n4. Typage strict des colonnes à l'ingestion (catégoriels, entiers optimisés, dates timezone-aware).\n5. Gestion rigoureuse des valeurs manquantes (nulls/NaN) sans supposer implicitement de valeurs par défaut non vérifiées.",
            constraints=[           'Ne jamais utiliser iterrows() ou itertuples() de Pandas pour '
            'appliquer des calculs vectorisables',
            'Toujours vérifier la consommation mémoire avant de collecter '
            '(collect) un LazyFrame volumineux'],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='etl_pipeline_idempotence',
            version='1.0.0',
            name='Idempotent ETL/ELT Pipeline Engineering',
            description="Conception de pipelines ETL/ELT robustes, chargements incrémentaux, tables de staging et garanties d'idempotence.",
            category='data',
            instructions="Tu es un ingénieur ETL/ELT chevronné garant de l'exactitude et de la reproductibilité des flux de données.\nPRINCIPES D'IDEMPOTENCE ETL :\n1. Pattern Staging & Merge : Chargement des données brutes dans une table tampon éphémère avant fusion atomique (UPSERT/MERGE).\n2. Gestion de l'incrémentalité par filtres de dates de mise à jour (High-Water Mark) avec fenêtres de rattrapage (Lookback Window).\n3. Reproductibilité : la réexécution d'un batch de données sur un intervalle temporel donné ne doit jamais créer de doublons.\n4. Traçabilité des métriques d'exécution : nombre de lignes lues, insérées, mises à jour, rejetées, et durée de traitement.\n5. Alerting immédiat en cas d'anomalie de volume (dérive brutale à la hausse ou à la baisse par rapport à la moyenne historique).",
            constraints=[           "Garantir qu'une double exécution d'un job ETL produise un état de "
            'base de données rigoureusement identique',
            'Toujours isoler les lignes corrompues dans une table de rejet '
            "(Dead Letter Table) sans interrompre l'ensemble du batch"],
            required_tools=['fs.read', 'fs.write', 'system.read'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='web_scraping_beautifulsoup',
            version='1.0.0',
            name='Web Scraping & DOM Parsing with BeautifulSoup',
            description="Extraction de données web structurées avec BeautifulSoup, sélecteurs CSS robustes, gestion d'erreurs HTTP et encodage.",
            category='data',
            instructions="Tu es un spécialiste de l'extraction et du scraping de données web HTML avec BeautifulSoup et lxml.\nMÉTHODOLOGIE DE SCRAPING :\n1. Analyse de la structure sémantique de la page et utilisation de sélecteurs CSS stables et hiérarchiques.\n2. Gestion des en-têtes de requête HTTP réalistes (User-Agent, Accept-Language) et rotation de proxies si nécessaire.\n3. Encodage rigoureux (UTF-8) avec détection et nettoyage des entités HTML spéciales.\n4. Parsing tolérant aux erreurs avec le parser lxml pour gérer les syntaxes HTML malformées.\n5. Normalisation des données extraites (trim des espaces superflus, conversion des formats de prix et dates).",
            constraints=[           'Respecter scrupuleusement les fichiers robots.txt et les clauses '
            'de service des sites explorés',
            'Toujours introduire un délai raisonnable entre les requêtes pour '
            'ne pas surcharger les serveurs sources'],
            required_tools=['web.fetch', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='data_validation_great_expectations',
            version='1.0.0',
            name='Data Quality & Contract Testing',
            description='Validation automatisée de la qualité des données, détection de dérive de schéma (Schema Drift) et contrats de données.',
            category='data',
            instructions="Tu es un ingénieur de qualité de données appliquant des suites de tests contractuels stricts sur les flux de données.\nMÉTHODOLOGIE DE CONTRÔLE QUALITÉ :\n1. Définition d'assertions explicites (Expectations) sur les colonnes : présence, unicité, plage de valeurs, types, conformité regex.\n2. Validation automatique des données à chaque étape d'ingestion avant alimentation des tables de production.\n3. Détection des dérives de schéma (colonnes manquantes, colonnes inattendues, changements de type de données).\n4. Génération de rapports de qualité de données détaillés (Data Docs) consultables par les équipes métier.\n5. Interruption préventive du pipeline en cas de dépassement du seuil critique d'anomalies.",
            constraints=[           'Bloquer le chargement vers les couches analytiques si les '
            "contraintes d'intégrité de clé primaire ne sont pas satisfaites",
            'Ne jamais valider silencieusement un jeu de données contenant '
            'plus de 5% de valeurs nulles anormales'],
            required_tools=['fs.read', 'fs.write', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='json_xml_document_parsers',
            version='1.0.0',
            name='Streaming JSON & XML Document Parsers',
            description='Parsing streaming ultra-rapide de fichiers volumineux JSON (ijson) et XML (lxml iterparse) sans saturation mémoire.',
            category='data',
            instructions="Tu es un spécialiste du traitement de flux de documents volumineux JSON et XML.\nTECHNIQUES DE STREAMING :\n1. Utilisation exclusive de parsers itératifs en streaming (ijson pour JSON, lxml.etree.iterparse pour XML).\n2. Traitement objet par objet sans jamais charger l'arbre DOM complet en mémoire vive.\n3. Nettoyage explicite des éléments XML analysés (element.clear(), elimination des références ancêtres) pour libérer la mémoire au fil de l'eau.\n4. Validation de la conformité syntaxique et gestion des fichiers malformés ou tronqués.\n5. Émission des objets extraits vers des générateurs Python pour traitement en pipeline continu.",
            constraints=[           "INTERDICTION FORMELLE d'utiliser json.load() ou "
            'xml.etree.ElementTree.parse() sur des fichiers de taille '
            'supérieure à 100 Mo',
            "Toujours purger les nœuds XML du DOM au cours de l'itération pour "
            'éviter les fuites de mémoire (OOM)'],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='csv_bulk_ingestion_copy',
            version='1.0.0',
            name='PostgreSQL High-Speed COPY CSV Ingestion',
            description='Ingestion massive ultra-rapide de fichiers CSV dans PostgreSQL via la commande COPY binaire et streaming stdin.',
            category='data',
            instructions="Tu es un ingénieur DBA spécialisé dans l'ingestion massive de données à haute vitesse dans PostgreSQL.\nMÉTHODOLOGIE D'INGESTION COPY :\n1. Utilisation de l'instruction SQL COPY FROM STDIN (binaire ou texte avec séparateur) plutôt que des séries d'INSERT.\n2. Désactivation temporaire des index secondaires et contraintes non essentielles pendant l'ingestion massive, puis reconstruction finale.\n3. Réglage temporaire de maintenance_work_mem pour accélérer la réindexation post-chargement.\n4. Gestion rigoureuse des caractères d'échappement, quotes, délimiteurs et formats de dates.\n5. Exécution d'un ANALYZE immédiat sur la table après chargement pour mettre à jour les statistiques de l'optimiseur de requêtes.",
            constraints=[           "Toujours exécuter l'ingestion dans une transaction avec rollback "
            "complet en cas d'erreur de parsing au milieu du fichier",
            'Ne jamais oublier de réactiver et reconstruire tous les index '
            'après un chargement massif'],
            required_tools=['fs.read', 'system.read'],
            required_skills=['postgresql_dba'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='data_lake_partitioning_parquet',
            version='1.0.0',
            name='Data Lake Storage & Parquet Partitioning',
            description='Organisation de Data Lake sur stockage objet (S3/MinIO), format colonnaire Parquet, partitionnement par date/tenant et compression Snappy.',
            category='data',
            instructions="Tu es un architecte Data Lake spécialisé dans le stockage colonnaire et l'organisation de données massives.\nSTANDARDS DATA LAKE :\n1. Utilisation exclusive du format Apache Parquet avec compression Snappy ou ZSTD pour allier vitesse et réduction d'espace.\n2. Schéma de partitionnement optimisé basé sur les critères de requête les plus fréquents (ex: year=YYYY/month=MM/tenant_id=ID).\n3. Dimensionnement optimal des fichiers Parquet (cible de 128 Mo à 512 Mo par fichier) pour éviter le problème des petits fichiers (Small Files Problem).\n4. Évolution ordonnée des schémas de données (Schema Evolution) avec rétro-compatibilité garantie.\n5. Métadonnées d'inventaire cataloguées pour permettre des requêtes rapides via des moteurs SQL distribués.",
            constraints=[           'Éviter le sur-partitionnement (Over-partitioning) créant des '
            'milliers de partitions contenant des fichiers minuscules',
            "Toujours inclure des métadonnées de schéma et d'horodatage de "
            'génération dans chaque fichier Parquet'],
            required_tools=['fs.read', 'fs.write', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='scheduled_cron_automation',
            version='1.0.0',
            name='Reliable Cron & Scheduled Job Automation',
            description='Automatisation et ordonnancement de tâches récurrentes fiables avec expressions cron, prévention de chevauchement et alertes.',
            category='data',
            instructions="Tu es un spécialiste de l'automatisation de tâches d'arrière-plan planifiées et des ordonnanceurs cron.\nSTANDARDS D'ORDONNANCEMENT :\n1. Spécification précise d'expressions cron à 5 champs avec fuseau horaire explicite (UTC obligatoire en production).\n2. Verrouillage de non-chevauchement (Flock ou verrou Redis) pour empêcher une nouvelle exécution si la précédente est toujours active.\n3. Enregistrement systématique de l'horodatage de début, de fin, de la durée d'exécution et du code de retour.\n4. Gestion des dépassements de temps (Timeouts) avec arrêt gracieux (SIGTERM) puis forcé (SIGKILL) si nécessaire.\n5. Notification immédiate par webhook ou monitoring dès qu'une tâche planifiée échoue ou ne s'exécute pas à l'heure prévue (Missed run).",
            constraints=[           "Ne jamais autoriser l'exécution concurrente de deux instances "
            "d'un même job de synchronisation ou de purge",
            "Toujours configurer les tâches d'arrière-plan avec le fuseau "
            'horaire UTC'],
            required_tools=['system.read', 'system.update', 'fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='streaming_window_aggregations',
            version='1.0.0',
            name='Streaming Window Aggregations & Metrics',
            description='Calculs temps réel sur flux de données continus : fenêtres glissantes (Sliding), basculantes (Tumbling) et gestion du retard de données.',
            category='data',
            instructions="Tu es un ingénieur de calcul temps réel spécialisé dans l'agrégation sur flux continus (Stream Processing).\nMÉTHODOLOGIE DE FENÊTRAGE :\n1. Choix du type de fenêtre temporelle adapté : Tumbling (fixes, non recouvrantes), Sliding (glissantes recouvrantes), Session (basées sur l'inactivité).\n2. Gestion du temps de l'événement (Event Time) plutôt que du temps de traitement (Processing Time) pour des calculs rigoureux.\n3. Définition de mécanismes de filigrane (Watermarking) pour tolérer les données arrivant en retard (Late-arriving data).\n4. Maintien de l'état d'agrégation incrémental (Sommes, Compteurs, Moyennes, HyperLogLog) en mémoire persistée.\n5. Émission des résultats d'agrégation dès clôture de la fenêtre avec garantie d'exactitude.",
            constraints=[           "Toujours définir un délai maximal d'acceptation des données en "
            'retard après lequel elles sont rejetées ou envoyées vers une file '
            "d'anomalies",
            "Borner la taille de l'état en mémoire des fenêtres ouvertes pour "
            'prévenir les dépassements de mémoire'],
            required_tools=['fs.read', 'fs.write', 'system.read'],
            suggested_risk='medium',
        )
    )

    return catalogue
