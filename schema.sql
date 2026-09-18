-- =========================================================
-- ROCKIB AI — UNIFIED SYSTEM SCHEMA (PHASE 0)
-- PostgreSQL
-- =========================================================

-- ---------------------------------------------------------
-- EXTENSIONS & ENUMS
-- ---------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Optionnel : Activation de pgvector pour la recherche sémantique s'il est présent sur le serveur VPS
-- CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE workspace_type AS ENUM (
    'owner',        -- L'espace personnel principal (OWNER/ROCKIB)
    'client'        -- Les futurs espaces clients cloisonnés
);

CREATE TYPE user_role AS ENUM (
    'owner',        -- Vous (accès global et absolu)
    'admin',        -- Administrateur d'un espace client
    'viewer'        -- Accès lecture seule (ex: client consultant ses rapports)
);

CREATE TYPE memory_type AS ENUM (
    'fact',             -- Fait brut, indiscutable (ex: "IIA Factory a 3 employés")
    'preference',       -- Vos préférences personnelles (ex: "Préfère WhatsApp après 18h")
    'decision_rule',    -- Règle déduite des arbitrages (ex: "Toujours refuser les appels le dimanche")
    'experience',       -- Leçons apprises par feedback (ex: "L'envoi tardif de ce rapport a généré de l'anxiété")
    'project_memory'    -- Contexte projet court/moyen terme (jalons, contraintes, état actuel)
);

CREATE TYPE memory_status AS ENUM (
    'supposed',     -- Supposé : Hypothèse faible en attente d'observation
    'deduced',      -- Déduit : Déduction logique faite par l'IA basée sur des patterns
    'known',        -- Connu : Déclaré explicitement par vous ou une source fiable
    'verified'      -- Vérifié : Confirmé de manière empirique par l'usage ou le feedback direct
);

CREATE TYPE arbitration_rule AS ENUM (
    'cognitive_wins',
    'intelligence_wins',
    'consensus_required',
    'escalate'
);

CREATE TYPE dominant_source AS ENUM (
    'cognitive',
    'intelligence',
    'consensus'
);

CREATE TYPE risk_level AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE reversibility_level AS ENUM (
    'reversible',
    'partially_reversible',
    'irreversible'
);

CREATE TYPE impact_type AS ENUM (
    'internal',
    'client_facing',
    'financial',
    'reputational'
);

CREATE TYPE permission_action AS ENUM (
    'READ',
    'CREATE',
    'UPDATE',
    'DELETE',
    'SEND',
    'PUBLISH',
    'SPEND'
);

CREATE TYPE decision_status AS ENUM (
    'pending_approval',
    'executed',
    'rejected',
    'escalated',
    'expired'
);

-- ---------------------------------------------------------
-- TRIGGER FUNCTION: updated_at
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------
-- COUCHE 1 : IDENTITÉ & WORKSPACES
-- ---------------------------------------------------------

CREATE TABLE workspaces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(150) NOT NULL,
    slug            VARCHAR(50) UNIQUE NOT NULL, -- ex: 'rockib-owner', 'client-iia-factory'
    type            workspace_type NOT NULL DEFAULT 'client',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_workspaces_updated_at
    BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- Table pivot d'association Utilisateurs <-> Workspaces avec rôle
CREATE TABLE workspace_memberships (
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    role            user_role NOT NULL DEFAULT 'viewer',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TRIGGER trg_workspace_memberships_updated_at
    BEFORE UPDATE ON workspace_memberships
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------
-- COUCHE 1.5 : AGENTS
-- ---------------------------------------------------------

CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name            VARCHAR(150) NOT NULL,       -- ex: 'Sales Agent', 'Support Agent'
    role            VARCHAR(100),                -- domaine de spécialisation
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_agents_updated_at
    BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------
-- COUCHE 2 : MÉMOIRE À 5 COUCHES (MEMORY LAYER)
-- ---------------------------------------------------------

CREATE TABLE memories (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    type                memory_type NOT NULL,
    status              memory_status NOT NULL DEFAULT 'supposed',
    
    content             TEXT NOT NULL,              -- Contenu textuel de la mémoire
    metadata            JSONB NOT NULL DEFAULT '{}', -- Propriétés dynamiques (tags, catégories, contexte temporel)
    
    -- Pondération (Importance / Freshness / Confidence)
    confidence_level    NUMERIC(4,3) NOT NULL CHECK (confidence_level BETWEEN 0.000 AND 1.000), -- Fiabilité de la mémoire
    importance_level    NUMERIC(4,3) NOT NULL CHECK (importance_level BETWEEN 0.000 AND 1.000), -- Poids de la mémoire
    
    -- Optionnel : Embedding vectoriel pour recherche de proximité sémantique (RAG)
    -- embedding        vector(1536), 
    
    last_accessed_at    TIMESTAMPTZ NOT NULL DEFAULT now(), -- Utilisé pour calculer la "fraîcheur" (Decay Rate)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index pour accélérer la recherche par type, statut et fraîcheur
CREATE INDEX idx_memories_workspace_type ON memories (workspace_id, type);
CREATE INDEX idx_memories_status ON memories (status);
CREATE INDEX idx_memories_last_accessed ON memories (last_accessed_at DESC);
-- Index GIN sur les métadonnées pour des requêtes flexibles
CREATE INDEX idx_memories_metadata ON memories USING gin (metadata);

CREATE TRIGGER trg_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------
-- COUCHE 4 : CONFIGURATION DES DOMAINES DE DÉCISION
-- ---------------------------------------------------------

CREATE TABLE decision_domain_config (
    id                      SERIAL PRIMARY KEY,
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    domain                  VARCHAR(100) NOT NULL,       -- ex: 'social_media', 'finance', 'client_support'
    permission_action       permission_action NOT NULL,  -- ex: 'SEND', 'SPEND'...

    arbitration_rule        arbitration_rule NOT NULL,
    base_risk_level         risk_level NOT NULL,
    base_reversibility      reversibility_level NOT NULL,
    base_impact             impact_type NOT NULL,

    disagreement_threshold  NUMERIC(3,2) NOT NULL DEFAULT 0.40,  -- au-delà => approval obligatoire
    approval_timeout_minutes INTEGER NOT NULL DEFAULT 60,        -- avant escalade WhatsApp/appel

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (workspace_id, domain, permission_action)
);

CREATE TRIGGER trg_domain_config_updated_at
    BEFORE UPDATE ON decision_domain_config
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------
-- COUCHE 4 : DÉCISIONS (ARBITRAGES DU DECISION ENGINE)
-- ---------------------------------------------------------

CREATE TABLE decisions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id                UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    domain_config_id        INTEGER REFERENCES decision_domain_config(id),

    objective               TEXT NOT NULL,
    situation               TEXT NOT NULL,
    proposed_action         TEXT NOT NULL,

    -- Avis des deux couches
    cognitive_action        TEXT,
    cognitive_confidence    NUMERIC(4,3),                 -- 0.000 - 1.000
    intelligence_action     TEXT,
    intelligence_confidence NUMERIC(4,3),

    -- Arbitrage
    dominant_source         dominant_source,
    disagreement            NUMERIC(4,3),

    -- Risque (base config + ajustement IA, jamais < base)
    risk_level              risk_level NOT NULL,
    risk_reversibility      reversibility_level NOT NULL,
    risk_impact             impact_type NOT NULL,
    risk_ai_adjusted        BOOLEAN NOT NULL DEFAULT false,

    -- Autonomie
    requested_autonomy_level SMALLINT NOT NULL CHECK (requested_autonomy_level BETWEEN 0 AND 5),
    applied_autonomy_level   SMALLINT NOT NULL CHECK (applied_autonomy_level BETWEEN 0 AND 5),
    CONSTRAINT applied_never_exceeds_requested
        CHECK (applied_autonomy_level <= requested_autonomy_level),

    -- Permission
    permission_required     permission_action NOT NULL,
    permission_granted      BOOLEAN NOT NULL DEFAULT false,

    -- Approbation
    approval_required       BOOLEAN NOT NULL DEFAULT false,
    approval_reason         TEXT,
    approved_by             UUID REFERENCES users(id),    -- NULL tant que non approuvé
    approved_at             TIMESTAMPTZ,
    escalated_at            TIMESTAMPTZ,                  -- horodatage de l'escalade WhatsApp/appel

    -- Décision finale
    final_action             TEXT,
    final_confidence         NUMERIC(4,3),
    status                    decision_status NOT NULL DEFAULT 'pending_approval',

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at               TIMESTAMPTZ
);

CREATE INDEX idx_decisions_workspace_status ON decisions (workspace_id, status);
CREATE INDEX idx_decisions_agent ON decisions (agent_id);
CREATE INDEX idx_decisions_pending_timeout
    ON decisions (status, created_at)
    WHERE status = 'pending_approval';

CREATE TRIGGER trg_decisions_updated_at
    BEFORE UPDATE ON decisions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------
-- COUCHE 4 : OUTCOMES (BOUCLE D'APPRENTISSAGE)
-- ---------------------------------------------------------

CREATE TABLE decision_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id         UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,

    result_summary      TEXT NOT NULL,          -- ce qui s'est réellement passé
    success              BOOLEAN,                -- l'objectif a-t-il été atteint ?
    lesson               TEXT,                   -- leçon extraite pour le Cognitive Model

    cognitive_was_right  BOOLEAN,                -- pour ajuster la confiance future
    intelligence_was_right BOOLEAN,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outcomes_decision ON decision_outcomes (decision_id);
