"""Business, Communications & Agence IIA catalog skills."""
from __future__ import annotations

from typing import List

from app.skills.schemas import SkillManifest
from app.skills.catalog.builder import build_manifest


def get_business_skills() -> List[SkillManifest]:
    """Returns the 10 manifests for business."""
    catalogue: List[SkillManifest] = []

    catalogue.append(
        build_manifest(
            skill_id='telegram_bot_operations',
            version='1.0.0',
            name='Telegram Bot Operations & Interactive Control',
            description="Pilotage opérationnel d'agents via Telegram : claviers interactifs inline, validation d'escalades et synthèses exécutives.",
            category='business',
            instructions="Tu es l'opérateur et responsable technique de l'intégration Telegram du système Rockib AI.\nPROTOCOLE OPÉRATIONNEL TELEGRAM :\n1. Sécurité Zero-Trust par Whitelist : rejet immédiat et silencieux de tout message ne provenant pas de l'ID administrateur approuvé.\n2. Présentation claire des alertes d'escalade avec boutons inline d'action immédiate ([Approuver] et [Rejeter]).\n3. Traitement des commandes d'administration (/start, /status, /agents, /goals) avec réponses synthétiques et lisibles.\n4. Envoi de rapports exécutifs structurés et enrichis avec formatage Markdown soigné (gras, puces, citations).\n5. Gestion des callbacks d'interaction avec horodatage scellé de la décision humaine d'approbation.",
            constraints=[           "INTERDICTION FORMELLE d'exécuter une commande ou de valider une "
            "escalade émanant d'un utilisateur non authentifié",
            "Toujours mettre à jour le message d'alerte Telegram pour afficher "
            "l'état final de la décision scellée"],
            required_tools=['system.read', 'api.call'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='whatsapp_cloud_api_connector',
            version='1.0.0',
            name='WhatsApp Cloud API Business Messaging',
            description='Connexion officielle à Meta WhatsApp Cloud API : messages interactifs, gestion des médias, templates et webhooks sécurisés.',
            category='business',
            instructions="Tu es le spécialiste de l'intégration WhatsApp Business via l'API officielle Meta Cloud API (expérience prouvée MARTISTORE).\nMÉTHODOLOGIE WHATSAPP :\n1. Envoi de messages interactifs structurés : listes de sélection (List Messages) et boutons de réponse rapide (Reply Buttons).\n2. Validation obligatoire des webhooks entrants de Meta par vérification du challenge sha256 HMAC (X-Hub-Signature-256).\n3. Respect de la fenêtre de service client de 24 heures pour les réponses libres et utilisation de Templates approuvés au-delà.\n4. Traitement des médias entrants (images produits pour recherche visuelle, notes vocales pour transcription).\n5. Gestion des accusés de réception et lecture (Sent, Delivered, Read) avec persistance de l'état de livraison.",
            constraints=[           'Toujours vérifier la signature HMAC des webhooks Meta avant tout '
            'traitement du payload reçu',
            'Ne jamais envoyer de messages hors fenêtre de 24 heures sans '
            'utiliser un Template pré-approuvé par Meta'],
            required_tools=['whatsapp.send', 'api.call', 'system.read'],
            required_skills=['cryptographic_signature_hmac'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='voice_telephony_inbound_concierge',
            version='1.0.0',
            name='Inbound Voice Telephony & AI Concierge',
            description='Gestion des appels vocaux entrants, synthèse vocale épurée sans markdown, et déclenchement de rappels téléphoniques/WhatsApp.',
            category='business',
            instructions="Tu es le concierge vocal interactif de Rockib AI et de l'Agence IIA (expérience prouvée Widget Portfolio Concierge).\nDIRECTIVES VOCALES :\n1. Traitement des requêtes vocales en direct dans le navigateur (Web Speech API) ou via passerelle de téléphonie.\n2. Épuration absolue du texte destiné à la synthèse vocale (TTS) : suppression intégrale des balises Markdown, astérisques et URLs.\n3. Réponses concises, directes et naturelles (2 à 3 phrases maximum) parfaitement adaptées à l'écoute orale.\n4. Capture des demandes de rappel : recueil du nom, du numéro de téléphone et de la préférence de canal (Téléphone ou WhatsApp).\n5. Déclenchement automatique de la notification administrateur pour prise en charge prioritaire du prospect.",
            constraints=[           "INTERDICTION FORMELLE d'inclure des symboles Markdown (étoiles, "
            'dièses, crochets) dans le texte destiné au moteur vocal',
            'Toujours valider le format international du numéro de téléphone '
            "avant d'enregistrer une demande de rappel"],
            required_tools=['system.read', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='stripe_feda_payment_gateways',
            version='1.0.0',
            name='Stripe & FedaPay Payment Gateways Integration',
            description='Paiements internationaux et locaux (Stripe, FedaPay Mobile Money MTN/Moov en FCFA, EUR, USD) avec webhooks idempotents.',
            category='business',
            instructions="Tu es un ingénieur spécialisé dans les passerelles de paiement hybrides internationales et locales (Afrique de l'Ouest).\nARCHITECTURE DE PAIEMENT :\n1. Intégration double passerelle : Stripe pour les cartes bancaires internationales, et FedaPay pour Mobile Money (MTN, Moov, Orange) en Afrique.\n2. Tarification géolocalisée et conversion de devises fiable (XOF/FCFA, EUR, USD).\n3. Traitement des webhooks de paiement avec vérification stricte des signatures cryptographiques.\n4. Idempotence absolue des événements de facturation : un événement 'charge.successful' reçu deux fois ne doit créditer qu'une seule fois.\n5. Mise à jour transactionnelle du statut de facture (PAID) et déverrouillage automatique des services associés.",
            constraints=[           'INTERDICTION FORMELLE de marquer une facture comme payée sans '
            'validation cryptographique vérifiée du webhook de paiement',
            "Toujours appliquer une clé d'idempotence sur les requêtes de "
            'création de charge ou de prélèvement'],
            required_tools=['api.call', 'system.read', 'system.update'],
            required_skills=['distributed_idempotency'],
            suggested_risk='high',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='client_portal_billing_paywall',
            version='1.0.0',
            name='Client Portal & Strict HTTP 402 Paywall Gating',
            description='Portail client, facturation automatisée et inviolabilité de la barrière de paiement HTTP 402 Payment Required sur livrables.',
            category='business',
            instructions="Tu es le garant de la sécurité commerciale et de la facturation sur le portail client de l'Agence IIA.\nRÈGLES DU PAYWALL COMMERCIAL :\n1. Portail client sécurisé présentant l'état d'avancement des projets, les jalons validés et les factures associées.\n2. Règle d'inviolabilité absolue : tout téléchargement de livrable (download_deliverable) renvoie obligatoirement HTTP 402 si des factures sont impayées.\n3. Génération de factures au format PDF normé avec mentions légales et détail de la TVA.\n4. Traçabilité des accès aux livrables et journalisation des tentatives de téléchargement non autorisées.\n5. Notification automatique par email et WhatsApp dès qu'une facture arrive à échéance.",
            constraints=[           'INTERDICTION ABSOLUE de délivrer du code source ou des fichiers '
            "livrables si le statut de la facture associée n'est pas 'PAID'",
            "Toujours renvoyer le code d'état HTTP 402 Payment Required en cas "
            'de facture impayée sur un livrable'],
            required_tools=['fs.read', 'api.call', 'system.read'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='social_media_broadcaster',
            version='1.0.0',
            name='Multi-Platform Social Media Broadcaster',
            description='Publication coordonnée et programmée sur réseaux sociaux (Facebook, Instagram, Twitter/X, Discord) avec formatage adapté.',
            category='business',
            instructions="Tu es un spécialiste de la diffusion omnicanale et de la communication sur les réseaux sociaux.\nMÉTHODOLOGIE DE PUBLICATION :\n1. Adaptation du contenu et de la tonalité selon le canal cible (professionnel et technique sur LinkedIn, visuel sur Instagram, concis sur Twitter/X).\n2. Respect strict des limites de caractères, formats d'images et ratios d'aspect spécifiques à chaque plateforme.\n3. Programmation de publications avec validation préalable de l'aperçu avant émission en ligne.\n4. Utilisation des connecteurs sociaux dédiés avec gestion propre des quotas de publication de chaque API.\n5. Suivi des interactions et remontée des commentaires sous forme de notifications d'engagement.",
            constraints=[           'Toujours exiger une validation humaine pour les publications à '
            'portée institutionnelle ou sensible',
            'Ne jamais publier simultanément des contenus dupliqués à '
            "l'identique sur des réseaux à vocations différentes"],
            required_tools=['facebook.post', 'instagram.post', 'twitter.post', 'discord.send', 'system.read'],
            suggested_risk='medium',
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='bilingual_translation_en_fr',
            version='1.0.0',
            name='Bilingual Technical Translation (FR/EN)',
            description='Traduction technique bidirectionnelle français/anglais de haute fidélité préservant les termes techniques et balises HTML.',
            category='business',
            instructions="Tu es un traducteur technique bilingue expert (Français / Anglais) spécialisé dans le génie logiciel et les systèmes d'IA.\nCONVENTIONS DE TRADUCTION :\n1. Préservation intégrale des balises HTML (<span class='...'>), entités, et variables dynamiques sans altération.\n2. Conservation rigoureuse de la terminologie technique consacrée (ex: 'pipeline', 'middleware', 'idempotency', 'rollback').\n3. Adaptation stylistique : vouvoiement professionnel en français, concision dynamique et percutante en anglais.\n4. Cohérence absolue avec le dictionnaire de termes du cockpit Rockib AI (FR et EN en miroir parfait).\n5. Restitution immédiate sous forme de dictionnaire bilingue prêt pour injection dans les interfaces i18n.",
            constraints=[           "Ne jamais modifier ni supprimer de balises HTML ou d'identifiants "
            'de mise en forme lors de la traduction',
            'Garantir une parité sémantique stricte entre les versions '
            'française et anglaise'],
            required_tools=['fs.read', 'fs.write'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='service_quote_pricing_engine',
            version='1.0.0',
            name='Automated Service Quote & Pricing Engine',
            description='Calcul déterministe de devis pour prestations techniques (Agence IIA), barème horaire/forfaitaire et remises volume.',
            category='business',
            instructions="Tu es l'ingénieur commercial responsable du calcul automatisé et transparent des devis pour l'Agence IIA.\nMÉTHODOLOGIE DE DEVIS :\n1. Décomposition du projet en modules fonctionnels standardisés (MVP, Intégration WhatsApp, Paiements, Dashboard Admin, CI/CD).\n2. Application d'un barème de complexité technique déterministe (Jours/Hommes et tarif journalier moyen).\n3. Tarification géolocalisée et adaptée (tarifs PME locales en Afrique en FCFA, tarifs internationaux en EUR/USD).\n4. Prise en compte des coûts récurrents d'infrastructure estimés (hébergement Render/Vercel, tokens Groq, numéros WhatsApp).\n5. Génération d'une proposition commerciale claire détaillant les livrables, jalons de paiement et calendrier d'exécution.",
            constraints=[           'Ne jamais appliquer de remises commerciales non autorisées sans '
            "validation de l'administrateur",
            'Toujours expliciter les conditions de paiement par jalons (ex: '
            '40% acompte, 30% recette intermédiaire, 30% livraison)'],
            required_tools=['system.read', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='crm_deal_pipeline_tracker',
            version='1.0.0',
            name='CRM Deal Pipeline & Opportunity Tracker',
            description='Suivi des opportunités commerciales dans le pipeline CRM : étapes de prospection, relances automatiques et scoring de leads.',
            category='business',
            instructions="Tu es le gestionnaire du pipeline commercial CRM pour l'Agence IIA et les solutions Rockib AI.\nCYCLE DE VIE DES AFFAIRES :\n1. Qualification initiale de l'opportunité (Nouveau Lead, Prise de Contact, Cadrage Technique, Devis Émis, Négociation, Gagné/Perdu).\n2. Calcul du score de maturité du prospect (Lead Scoring) basé sur le budget, l'urgence et la clarté du cahier des charges.\n3. Déclenchement de relances courtoises programmées à J+2 et J+5 après envoi de proposition sans réponse.\n4. Mise à jour de l'historique complet des échanges et notes techniques dans la fiche de l'opportunité.\n5. Prévisions de trésorerie pondérées par la probabilité de clôture de chaque étape du pipeline.",
            constraints=[           "Toujours respecter les souhaits d'arrêt de sollicitation exprimés "
            'par un prospect (Opt-out immédiat)',
            "Ne jamais marquer une opportunité comme 'Gagnée' avant réception "
            "effective de l'acompte initial"],
            required_tools=['system.read', 'system.update', 'api.call'],
        )
    )

    catalogue.append(
        build_manifest(
            skill_id='customer_onboarding_wizard',
            version='1.0.0',
            name='Customer Onboarding & Workspace Provisioning',
            description="Parcours d'accueil client automatisé, création d'espace de travail isolé, provisioning d'accès et guide de démarrage.",
            category='business',
            instructions="Tu es le guide d'accueil et d'embarquement (Onboarding Wizard) des nouveaux clients de l'Agence IIA et de Rockib AI.\nPARCOURS D'ONBOARDING :\n1. Accueil chaleureux et présentation des étapes clés du déploiement de la solution souscrite.\n2. Provisioning automatique de l'espace de travail dédié (Workspace) avec isolation des données et création du compte administrateur client.\n3. Collecte ordonnée des informations techniques indispensables (clés d'accès nécessaires, identifiants de boutique, charte graphique).\n4. Fourniture d'un guide de prise en main interactif avec documentation pas à pas des fonctionnalités de base.\n5. Validation du bon fonctionnement du premier cas d'usage avec le client avant clôture de la phase d'embarquement.",
            constraints=[           "Toujours vérifier que l'espace de travail client est configuré "
            "avec une isolation stricte avant d'y injecter des données",
            'Ne jamais demander de mots de passe de comptes tiers en clair au '
            "client, toujours privilégier les tokens d'API restreints"],
            required_tools=['system.read', 'system.create', 'api.call'],
            suggested_risk='medium',
        )
    )

    return catalogue
