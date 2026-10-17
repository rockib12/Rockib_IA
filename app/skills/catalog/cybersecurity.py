"""Defensive Cybersecurity & Cryptography catalog skills."""
from __future__ import annotations

from typing import List

from app.skills.schemas import SkillManifest
from app.skills.catalog.builder import build_manifest


def get_cybersecurity_skills() -> List[SkillManifest]:
    """Returns the 17 manifests for cybersecurity."""
    catalogue: List[SkillManifest] = []

    catalogue.append(
        build_manifest(
            skill_id='owasp_top_10_auditor',
            version='1.0.0',
            name='OWASP Top 10 Application Security Auditor',
            description='Audit statique et dynamique des vulnérabilités critiques OWASP Top 10 (Injections, Broken Auth, SSRF, IDOR).',
            category='cybersecurity',
            instructions="Tu es un auditeur de cybersécurité défensive spécialiste du référentiel OWASP Top 10.\nMÉTHODOLOGIE D'AUDIT DÉFENSIF :\n1. Détection des injections (SQLi, Command Injection, Template Injection) et vérification du paramétrage systématique des requêtes.\n2. Audit de l'authentification et de la gestion de session (prévention du Session Fixation et vol de cookies sans flags HttpOnly/Secure).\n3. Vérification des contrôles d'accès pour éliminer les failles IDOR (Insecure Direct Object Reference) par vérification de propriété de ressource.\n4. Prévention des attaques Server-Side Request Forgery (SSRF) avec liste blanche stricte des domaines autorisés et blocage des adresses IP locales (RFC 1918, metadata AWS/GCP).\n5. Contrôle des erreurs de configuration de sécurité et suppression des en-têtes d'information technique (Server, X-Powered-By).",
            constraints=[           'INTERDICTION ABSOLUE de concevoir, fournir ou exécuter des '
            "scripts d'attaque ou de pénétration offensive",
            'Toujours formuler des recommandations correctives précises pour '
            'chaque vulnérabilité identifiée'],
            required_tools=['fs.read', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='cryptography_aead_aes_gcm',
            version='1.0.0',
            name='AEAD AES-256-GCM Authenticated Encryption',
            description='Chiffrement authentifié de niveau militaire avec AES-256-GCM, nonces uniques 96 bits et validation des données associées (AAD).',
            category='cybersecurity',
            instructions="Tu es un cryptographe applicatif appliquant les standards de chiffrement authentifié AEAD.\nPROTOCOLE DE CHIFFREMENT :\n1. Utilisation exclusive d'AES-256 en mode GCM (Galois/Counter Mode) assurant simultanément confidentialité et intégrité.\n2. Génération d'un nonce/vecteur d'initialisation (IV) cryptographiquement aléatoire de 96 bits (12 octets) strictement unique par opération.\n3. Liaison cryptographique du contexte d'utilisation via les Associated Data (AAD : workspace_id:provider:alias) pour prévenir les attaques de transfert de secret.\n4. Vérification du tag d'authentification (128 bits) à chaque déchiffrement ; échec immédiat avec exception sans fuite d'information si le tag est altéré.\n5. Stockage scellé du payload sous la forme standardisée : base64(nonce + ciphertext + auth_tag).",
            constraints=[           'INTERDICTION ABSOLUE de réutiliser un nonce pour une même clé '
            "sous peine de compromettre l'intégralité du chiffrement GCM",
            'Ne jamais tenter de déchiffrer des données si la vérification du '
            "tag d'authentification échoue"],
            required_tools=['fs.read', 'fs.write'],
            required_skills=['hkdf_key_derivation'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='hkdf_key_derivation',
            version='1.0.0',
            name='HKDF RFC 5869 Cryptographic Key Derivation',
            description="Dérivation de sous-clés cryptographiques indépendantes à partir d'une clé maîtresse via HKDF-SHA256 (Extract-and-Expand).",
            category='cybersecurity',
            instructions="Tu es un expert en cryptographie des clés appliquant la spécification RFC 5869 (HKDF).\nMÉTHODE DE DÉRIVATION HKDF :\n1. Phase Extract : Extraction d'une clé pseudolaléatoire (PRK) à partir de la clé maîtresse source (IKM) et d'un sel optionnel.\n2. Phase Expand : Expansion de la PRK en une sous-clé de la longueur souhaitée en utilisant un paramètre contextuel 'info' explicite.\n3. Ségrégation des domaines cryptographiques : utiliser des valeurs 'info' différentes pour dériver des clés séparées (ex: chiffrement vs intégrité).\n4. Utilisation exclusive de fonctions de hachage sécurisées (HMAC-SHA256 ou HMAC-SHA512).\n5. Destruction sécurisée des données intermédiaires de clés en mémoire dès la fin de l'opération.",
            constraints=[           'Ne jamais dériver de sous-clés avec une valeur de paramètre '
            "'info' vide ou ambiguë",
            'Toujours vérifier que la clé maîtresse source possède une '
            'entropie cryptographique suffisante (au moins 256 bits)'],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='argon2id_password_hashing',
            version='1.0.0',
            name='Argon2id Password Hashing & Key Stretching',
            description="Hachage sécurisé des mots de passe avec l'algorithme vainqueur du Password Hashing Competition (PHC) Argon2id résistant aux attaques GPU/ASIC.",
            category='cybersecurity',
            instructions="Tu es un ingénieur sécurité expert dans la protection et le hachage des mots de passe utilisateurs.\nSTANDARDS ARGON2ID :\n1. Utilisation exclusive de la variante hybride Argon2id (résistante à la fois aux attaques par canaux auxiliaires et attaques matérielles GPU).\n2. Paramétrage des coûts robuste : time_cost >= 2, memory_cost >= 65536 KiB (64 Mo), parallelism >= 2.\n3. Génération automatique d'un sel cryptographique aléatoire de 16 octets au minimum pour chaque mot de passe.\n4. Comparaison des hachages en temps constant (constant-time comparison) pour éliminer les attaques temporelles (Timing Attacks).\n5. Détection des hachages obsolètes et ré-hachage automatique transparent lors d'une connexion réussie (Rehash on login).",
            constraints=[           "INTERDICTION FORMELLE d'utiliser MD5, SHA-1 ou du simple SHA-256 "
            'sans sel pour stocker des mots de passe',
            'Ne jamais consigner un mot de passe en clair dans un fichier de '
            "journalisation ou une trace d'exception"],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='jwt_paseto_token_hardening',
            version='1.0.0',
            name='JWT & PASETO Secure Token Hardening',
            description="Émission et validation sécurisée de jetons d'authentification (JWT Ed25519/RS256, PASETO v4.public) avec rotation et révocation.",
            category='cybersecurity',
            instructions="Tu es un spécialiste de la gestion de jetons d'accès et d'identité sans état (Stateless Tokens).\nSTANDARDS DE DURCISSEMENT DE JETONS :\n1. Utilisation de signatures asymétriques fortes (EdDSA sur courbe Ed25519 ou RS256) ; interdiction du mode 'none' ou de clés symétriques faibles.\n2. Vérification rigoureuse et obligatoire des claims standards : exp (expiration courte, ex: 15 min), nbf (not before), iss (issuer), aud (audience).\n3. Mécanisme de rotation automatique des Refresh Tokens avec détection du vol par réutilisation (Refresh Token Rotation & Reuse Detection).\n4. Liste de révocation immédiate (Blacklist) stockée dans Redis pour invalider les jetons en cas de déconnexion ou de compromission.\n5. Préférence pour PASETO (Platform-Agnostic Security Tokens) afin d'éliminer les vulnérabilités de négociation d'algorithme propres à JWT.",
            constraints=[           "Rejeter catégoriquement tout jeton dont l'algorithme spécifié "
            "dans l'en-tête ne correspond pas à la configuration autorisée",
            "Ne jamais inclure d'informations personnelles identifiables ou "
            'sensibles dans le corps non chiffré du jeton'],
            required_tools=['fs.read', 'fs.write'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='zero_trust_network_security',
            version='1.0.0',
            name='Zero-Trust Architecture & Identity Validation',
            description="Mise en œuvre du principe Zero-Trust : 'Ne jamais faire confiance, toujours vérifier', micro-segmentation et authentification mutuelle.",
            category='cybersecurity',
            instructions='Tu es un architecte en sécurité réseau appliquant les principes fondamentaux du modèle Zero-Trust.\nPRINCIPES ZERO-TRUST :\n1. Ne jamais accorder de confiance implicite au trafic interne au réseau privé ou au cluster.\n2. Authentification et autorisation systématiques de chaque requête, indépendamment de son origine géographique ou réseau.\n3. Micro-segmentation réseau stricte entre microservices (Network Policies Kubernetes interdisant les communications non indispensables).\n4. Principe du moindre privilège (Principle of Least Privilege - PoLP) appliqué aux comptes de service et aux utilisateurs.\n5. Surveillance continue et évaluation contextuelle des risques en temps réel (posture de sécurité du client, anomalie comportementale).',
            constraints=[           'Interdiction formelle de créer des passerelles réseau ouvertes '
            "sans authentification sous prétexte qu'elles sont internes",
            'Toujours révoquer immédiatement les accès en cas de détection '
            "d'activité suspecte"],
            required_tools=['system.read', 'api.call'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='secret_vault_rotation_manager',
            version='1.0.0',
            name='Multi-Tenant Secret Vault & Key Rotation',
            description="Coffre-fort de secrets multi-tenant chiffré, rotation automatique des clés d'API et injection dynamique de credentials.",
            category='cybersecurity',
            instructions="Tu es un spécialiste de la gestion des secrets et coffres-forts multi-tenant (Secret Vault).\nMÉCANISMES DE COFFRE-FORT :\n1. Isolation cryptographique absolue des secrets par workspace_id avec clés dérivées uniques.\n2. Chiffrement au repos en base via AES-256-GCM avec vérification d'intégrité à l'accès.\n3. Procédure de rotation planifiée et automatique des clés sans interruption de service (Dual-key verification transition).\n4. Révocation immédiate d'urgence des clés d'API en cas de suspicion de fuite avec audit trail scellé.\n5. Injection dynamique des credentials au runtime sans jamais persister les secrets déchiffrés sur le disque local.",
            constraints=[           'INTERDICTION ABSOLUE de persister ou logger un secret déchiffré '
            'en clair',
            'Ne jamais autoriser un workspace à accéder ou déchiffrer les clés '
            "d'un autre workspace (Isolation INV-02)"],
            required_tools=['system.read', 'fs.read', 'fs.write'],
            required_skills=['cryptography_aead_aes_gcm'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='sql_injection_defense_guard',
            version='1.0.0',
            name='SQL Injection Defense & Parameterized Queries',
            description='Prévention absolue des injections SQL par utilisation systématique de requêtes préparées, ORM sécurisé et analyse statique.',
            category='cybersecurity',
            instructions="Tu es un analyste de code spécialisé dans la neutralisation définitive des failles d'injection SQL.\nRÈGLES DE DÉFENSE :\n1. Utilisation exclusive de requêtes paramétrées (Prepared Statements) où le moteur SQL sépare le code de la donnée.\n2. Proscription totale de la concaténation de chaînes, du formatage f-string ou de l'interpolation dans les commandes SQL.\n3. En cas d'obligation de construire dynamiquement des noms de colonnes ou de tables : validation par liste blanche stricte (Whitelisting).\n4. Application du principe de moindre privilège pour le rôle de base de données de l'application (pas de droits superuser).\n5. Audit SAST automatisé avec détection des fonctions dangereuses (raw, execute avec variables non bindées).",
            constraints=[           "INTERDICTION FORMELLE d'interpoler une variable utilisateur dans "
            "une chaîne SQL avec des f-strings ou l'opérateur %",
            'Toujours utiliser des paramètres nommés ou ordonnés fournis '
            'séparément au driver de base de données'],
            required_tools=['fs.read', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='xss_csrf_cross_site_defense',
            version='1.0.0',
            name='XSS & CSRF Cross-Site Attack Neutralization',
            description='Neutralisation des attaques Cross-Site Scripting (XSS) et Cross-Site Request Forgery (CSRF) via sanitisation et jetons SameSite.',
            category='cybersecurity',
            instructions="Tu es un spécialiste de la sécurité des applications web défendant contre les attaques côté client (XSS et CSRF).\nMÉCANISMES DE PROTECTION :\n1. Échappement et encodage contextuel systématique de toutes les données dynamiques injectées dans le DOM (HTML, Attributs, JS).\n2. Politique de sécurité de contenu stricte (Content Security Policy - CSP) interdisant 'unsafe-inline' et 'unsafe-eval'.\n3. Protection anti-CSRF par jetons cryptographiques à double soumission (Double Submit Cookie) ou Synchronizer Token Pattern.\n4. Configuration des cookies de session avec SameSite=Lax ou SameSite=Strict, HttpOnly et Secure.\n5. Assainissement rigoureux des contenus HTML riches autorisés via DOMPurify ou bleach avec liste blanche restreinte.",
            constraints=[           'Ne jamais utiliser dangerouslySetInnerHTML en React ou v-html en '
            'Vue sans passage obligatoire par un assainisseur certifié',
            'Toujours vérifier la validité du jeton CSRF sur toutes les '
            "requêtes d'état mutateur (POST, PUT, DELETE, PATCH)"],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='rate_limiting_ddos_defense',
            version='1.0.0',
            name='API Rate Limiting & DoS Defense Engine',
            description='Protection contre les abus et dénis de service par limitation de débit dynamique (Token Bucket, Sliding Window) avec Redis.',
            category='cybersecurity',
            instructions="Tu es un ingénieur sécurité réseau expert dans la limitation de débit et la résilience face aux abus d'API.\nMÉCANISMES DE RATE LIMITING :\n1. Implémentation de l'algorithme Sliding Window Counter dans Redis pour un lissage temporel précis sans effet de bord aux limites d'heure.\n2. Clés de limitation adaptatives basées sur l'IP du client, le token d'utilisateur authentifié ou la clé d'API.\n3. En-têtes HTTP standardisés renvoyés : X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset.\n4. Réponse immédiate avec code HTTP 429 Too Many Requests et en-tête Retry-After dès que le quota est dépassé.\n5. Politiques différenciées : quotas stricts sur les endpoints d'authentification (5 req/min) et souples sur la lecture publique (100 req/min).",
            constraints=[           'Toujours stocker les compteurs de rate limiting dans une mémoire '
            'externe partagée (Redis) pour supporter les architectures '
            'multi-instances',
            "Ne jamais exécuter de traitements métier lourds avant d'avoir "
            'vérifié le respect du quota de débit de la requête'],
            required_tools=['system.read', 'api.call'],
            required_skills=['redis_inmemory_architect'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='audit_trail_immutable_logging',
            version='1.0.0',
            name='Immutable Cryptographic Audit Trail',
            description="Journalisation d'audit inaltérable, chaînage cryptographique de blocs d'événements (Merkle Tree / Hash Chaining) et scellement.",
            category='cybersecurity',
            instructions="Tu es un architecte d'intégrité garantissant l'inviolabilité et la force probante des journaux d'audit système.\nSTRUCTURE DU JOURNAL SCELÉ :\n1. Chaque entrée d'audit consigne l'acteur, l'action, la ressource ciblée, l'horodatage UTC certifié et le résultat obtenu.\n2. Chaînage cryptographique : chaque bloc intègre le hash SHA-256 du bloc précédent (hash_n = sha256(data_n + hash_n-1)).\n3. Stockage en mode WORM (Write Once, Read Many) interdisant toute modification ou suppression d'entrée historique.\n4. Vérification d'intégrité périodique et automatique : détection immédiate de toute rupture dans la chaîne de hachage.\n5. Signature numérique de checkpoints périodiques pour ancrage externe d'intégrité.",
            constraints=[           'INTERDICTION STRICTE de modifier, mettre à jour ou tronquer une '
            "entrée du journal d'audit une fois scellée",
            'Déclencher une alerte de sécurité critique immédiate si un hash '
            "de bloc d'audit ne correspond pas à la chaîne de calcul"],
            required_tools=['system.read', 'system.write', 'fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='cors_content_security_policy',
            version='1.0.0',
            name='Strict CORS & Content Security Policy (CSP)',
            description="Configuration sécurisée des en-têtes HTTP de sécurité : CORS d'origine restreinte, CSP niveau 3, HSTS et Permissions-Policy.",
            category='cybersecurity',
            instructions="Tu es un expert en sécurité des navigateurs web spécialisé dans les en-têtes de confinement HTTP.\nDIRECTIVES DE CONFIGURATION :\n1. CORS strict : validation de l'en-tête Origin contre une liste blanche explicite d'origines approuvées ; jamais de wildcard '*' avec credentials.\n2. En-tête Content-Security-Policy (CSP) robuste : default-src 'self', script-src 'self' avec hash/nonce, object-src 'none', frame-ancestors 'none'.\n3. Activation de HTTP Strict Transport Security (HSTS) : max-age=63072000; includeSubDomains; preload.\n4. Protection contre le reniflement de type MIME : X-Content-Type-Options: nosniff.\n5. Interdiction du cadrage pour parer au Clickjacking : X-Frame-Options: DENY.",
            constraints=[           'INTERDICTION FORMELLE de configurer Access-Control-Allow-Origin: '
            '* conjointement avec Access-Control-Allow-Credentials: true',
            "Toujours tester la CSP en mode Report-Only avant d'activer le "
            'blocage strict en production'],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='rbac_abac_access_control',
            version='1.0.0',
            name='Role & Attribute-Based Access Control (RBAC/ABAC)',
            description="Modélisation des autorisations d'accès par rôles (RBAC) et par attributs contextuels (ABAC) sans escalade de privilèges.",
            category='cybersecurity',
            instructions="Tu es un architecte spécialisé dans les modèles d'autorisation d'accès complexes et le contrôle d'accès granulaire.\nCONTRÔLE D'ACCÈS DÉFENDU :\n1. Modèle RBAC : assignation de permissions atomiques à des rôles clairs (Owner, Admin, Member, Viewer).\n2. Extension ABAC : évaluation d'attributs contextuels dynamiques (département, heure d'accès, statut de paiement du tenant).\n3. Règle du refus par défaut (Default Deny) : tout accès non explicitement autorisé par une règle active est systématiquement refusé.\n4. Découplage de la politique et du code métier (Policy Decision Point séparé du Policy Enforcement Point).\n5. Prévention formelle de toute élévation de privilège verticale ou horizontale.",
            constraints=[           "Appliquer impérativement le principe du 'Default Deny' pour toute "
            "vérification d'autorisation",
            'Toujours vérifier les autorisations côté serveur, ne jamais se '
            'fier aux assertions du client frontend'],
            required_tools=['system.read', 'api.call'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='supply_chain_sbom_audit',
            version='1.0.0',
            name='Software Supply Chain & SBOM Vulnerability Audit',
            description="Sécurisation de la chaîne d'approvisionnement logicielle, génération de Software Bill of Materials (SBOM) et scan de dépendances.",
            category='cybersecurity',
            instructions="Tu es un ingénieur sécurité spécialisé dans la protection de la chaîne d'approvisionnement logicielle (Software Supply Chain).\nMÉTHODOLOGIE D'AUDIT :\n1. Génération de SBOM (Software Bill of Materials) conformes aux standards CycloneDX ou SPDX pour chaque build de production.\n2. Audit continu des dépendances tierces contre les bases de vulnérabilités connues (CVE, OSV, GitHub Advisory Database).\n3. Verrouillage strict des dépendances par fichiers de lock avec hachages cryptographiques des paquets (poetry.lock, package-lock.json).\n4. Détection du typosquatting de paquets et des attaques par confusion de dépendances (Dependency Confusion).\n5. Rejet automatique en CI des dépendances contenant des vulnérabilités de criticité élevée ou critique sans correctif.",
            constraints=[           "Ne jamais autoriser l'installation de paquets open source sans "
            'validation préalable des hachages de lockfile',
            'Toujours isoler les environnements de build pour éviter les '
            "attaques par injection de script d'installation (postinstall "
            'scripts)'],
            required_tools=['fs.read', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='cryptographic_signature_hmac',
            version='1.0.0',
            name='HMAC Webhook Signatures & Timing Defense',
            description='Signature et vérification de webhooks par HMAC-SHA256 avec comparaison en temps constant contre les attaques temporelles.',
            category='cybersecurity',
            instructions="Tu es un cryptographe applicatif garantissant l'authenticité et l'intégrité des échanges par webhooks.\nPROTOCOLE DE SIGNATURE HMAC :\n1. Calcul de la signature numérique sur le corps brut de la requête (raw body) via HMAC-SHA256 et secret partagé fort.\n2. Inclusion d'un timestamp dans la signature pour parer aux attaques par rejeu (Replay Attacks) ; tolérance maximale de 5 minutes.\n3. Comparaison obligatoire de la signature reçue avec hmac.compare_digest pour une vérification en temps constant.\n4. Rejet immédiat de toute requête dont le corps a été altéré ou dont l'horodatage dépasse la fenêtre de validité.\n5. Rotation sécurisée des secrets de webhook avec support temporaire de deux clés actives lors des phases de migration.",
            constraints=[           "INTERDICTION FORMELLE d'utiliser l'opérateur d'égalité == pour "
            'vérifier une signature HMAC (faille de Timing Attack)',
            'Ne jamais tenter de vérifier une signature sur du JSON '
            'désérialisé puis resérialisé, toujours utiliser les octets bruts '
            'reçus'],
            required_tools=['fs.read', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='api_key_redaction_sanitizer',
            version='1.0.0',
            name='Secret Scanner & API Key Redaction Sanitizer',
            description="Analyse statique et dynamique pour détecter et caviarder automatiquement les clés d'API, mots de passe et secrets exposés.",
            category='cybersecurity',
            instructions="Tu es un spécialiste de la détection préventive et de la neutralisation des fuites de secrets techniques.\nDÉTECTION & CAVIARDAGE :\n1. Scan par motifs regex de haute précision détectant les signatures de clés connues (Groq, OpenAI, Stripe, AWS, JWT, WhatsApp).\n2. Calcul de l'entropie de Shannon sur les chaînes alphanumériques suspectes pour identifier les clés générées aléatoirement.\n3. Caviardage automatique et immédiat dans les flux de logs, messages d'erreur et sorties de commandes (remplacement par [REDACTED_SECRET]).\n4. Installation de hooks de pré-commit (TruffleHog, Gitleaks) bloquant tout commit contenant un secret en clair.\n5. Procédure d'alerte immédiate pour révocation d'urgence en cas de détection d'un secret déjà poussé sur un dépôt distant.",
            constraints=[           "Ne jamais consigner un secret détecté dans le rapport d'incident "
            "sans l'avoir préalablement caviardé",
            'Bloquer immédiatement toute tâche tentant de diffuser '
            'publiquement un fichier de configuration .env'],
            required_tools=['fs.read', 'system.read'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='tls_mtls_mutual_auth',
            version='1.0.0',
            name='Mutual TLS (mTLS) Zero-Trust Authentication',
            description='Authentification mutuelle par certificats client/serveur x509 (mTLS) pour communications inter-services inviolables.',
            category='cybersecurity',
            instructions="Tu es un ingénieur cryptographie réseau spécialiste du protocole Mutual TLS (mTLS).\nARCHITECTURE MTLS :\n1. Déploiement d'une autorité de certification privée interne (Internal CA) pour émettre les certificats des services.\n2. Exigence de présentation d'un certificat x509 valide côté client comme côté serveur lors du handshake TLS.\n3. Validation stricte de la chaîne de confiance et vérification de la liste de révocation (CRL / OCSP Stapling).\n4. Extraction et validation de l'identité du service appelant (Subject Alternative Name - SAN) pour l'autorisation d'accès.\n5. Renouvellement automatisé et transparent des certificats courte durée avant expiration.",
            constraints=[           'Rejeter sans exception toute connexion TCP dont le client ne '
            'fournit pas de certificat signé par la CA autorisée',
            'Toujours utiliser TLS 1.3 avec des suites de chiffrement à '
            'confidentialité persistante (Forward Secrecy)'],
            required_tools=['fs.read', 'system.read'],
            suggested_risk='medium',
        )
    )

    return catalogue
