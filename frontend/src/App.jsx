import React, { useState, useEffect, useCallback } from 'react';
import ThreeCanvas from './components/ThreeCanvas';
import CockpitHeader from './components/CockpitHeader';
import AgentActivityCard from './components/AgentActivityCard';
import TaskDAGPanel from './components/TaskDAGPanel';
import SpawnAgentModal from './components/SpawnAgentModal';
import CreateGoalModal from './components/CreateGoalModal';
import GovernancePanel from './components/GovernancePanel';
import AuthModal from './components/AuthModal';
import DashboardPanel from './components/DashboardPanel';
import CyberTerminal from './components/CyberTerminal';
import EventTimeline from './components/EventTimeline';
import SocialConnectorsPanel from './components/SocialConnectorsPanel';
import ObservabilityPanel from './components/ObservabilityPanel';
import ClientCRMModal from './components/ClientCRMModal';
import { authFetch } from './lib/authFetch';

// Workspace par défaut pour l'environnement local
const DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001";

export default function App() {
  const [agents, setAgents] = useState([]);
  const [goals, setGoals] = useState([]);
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const [selectedGoalId, setSelectedGoalId] = useState(null);
  const [goalDetails, setGoalDetails] = useState(null);
  const [telemetry, setTelemetry] = useState([]);
  const [healthStatus, setHealthStatus] = useState({ status: 'healthy', database: 'up', redis: 'up' });
  const [toasts, setToasts] = useState([]);
  const [isSplitView, setIsSplitView] = useState(false);
  const [isSpawnModalOpen, setIsSpawnModalOpen] = useState(false);
  const [spawnParentId, setSpawnParentId] = useState(null);
  const [isCreateGoalOpen, setIsCreateGoalOpen] = useState(false);
  const [goalAgentId, setGoalAgentId] = useState(null);
  const [spawnEvent, setSpawnEvent] = useState(null);
  const [isWaking, setIsWaking] = useState(false);
  const [workspaceId, setWorkspaceId] = useState(DEFAULT_WORKSPACE_ID);
  const [currentUser, setCurrentUser] = useState(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  // Panel states
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);
  const [isGovernanceOpen, setIsGovernanceOpen] = useState(false);
  const [isConnectorsOpen, setIsConnectorsOpen] = useState(false);
  const [isObservabilityOpen, setIsObservabilityOpen] = useState(false);
  const [isClientCRMOpen, setIsClientCRMOpen] = useState(false);

  const addToast = useCallback((message, type = 'info') => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev.slice(-3), { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4200);
  }, []);

  // Écouter l'événement 401 pour afficher le modal d'authentification
  useEffect(() => {
    const handleUnauthorized = () => {
      setCurrentUser(null);
      setIsAuthModalOpen(true);
    };
    window.addEventListener('rockib:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('rockib:unauthorized', handleUnauthorized);
  }, []);

  // Sonde de santé profonde PostgreSQL & Redis
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/health');
      if (res.ok) {
        const data = await res.json();
        setHealthStatus({
          status: data.status || 'healthy',
          database: data.components?.database || 'up',
          redis: data.components?.redis || 'up',
        });
      }
    } catch {
      setHealthStatus({ status: 'degraded', database: 'down', redis: 'down' });
    }
  }, []);

  // Charger les agents depuis l'API
  const fetchAgents = useCallback(async () => {
    try {
      const res = await authFetch('/api/v1/agents?active_only=true');
      if (res.ok) {
        const data = await res.json();
        // Conserve uniquement les orchestrateurs et les sous-agents en cours de mission
        const activeAgents = data.filter((a) => !(a.is_ephemeral && a.is_finished));
        setAgents(activeAgents);
        if (activeAgents.length > 0) {
          if (!selectedAgentId || !activeAgents.some((a) => a.id === selectedAgentId)) {
            setSelectedAgentId(activeAgents[0].id);
          }
        }
        return activeAgents;
      }
    } catch (e) {
      console.warn("Backend FastAPI non joignable pour les agents, initialisation démo...", e);
    }
    return [];
  }, [selectedAgentId]);

  // Charger les goals
  const fetchGoals = useCallback(async () => {
    try {
      const res = await authFetch('/api/v1/goals');
      if (res.ok) {
        const data = await res.json();
        setGoals(data);
        if (data.length > 0 && !selectedGoalId) {
          setSelectedGoalId(data[0].id);
        }
        return data;
      }
    } catch (e) {
      console.warn("Erreur chargement goals:", e);
    }
    return [];
  }, [selectedGoalId]);

  // Charger les détails du goal sélectionné (DAG de tâches)
  const fetchGoalDetails = useCallback(async (goalId) => {
    if (!goalId) return;
    try {
      const res = await authFetch(`/api/v1/goals/${goalId}`);
      if (res.ok) {
        const data = await res.json();
        setGoalDetails(data);
        return data;
      }
    } catch (e) {
      console.warn("Erreur détails goal:", e);
    }
    return null;
  }, []);

  // Charger la télémétrie
  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await authFetch('/api/v1/telemetry');
      if (res.ok) {
        const data = await res.json();
        setTelemetry(data);
      }
    } catch (e) {
      console.warn("Erreur télémétrie:", e);
    }
  }, []);

  // Initialisation et boucle de rafraîchissement
  useEffect(() => {
    fetchHealth();
    const healthTimer = setInterval(fetchHealth, 12000);
    return () => clearInterval(healthTimer);
  }, [fetchHealth]);

  useEffect(() => {
    const initData = async (targetWsId) => {
      const activeWs = targetWsId || workspaceId || DEFAULT_WORKSPACE_ID;
      const loadedAgents = await fetchAgents();
      await fetchGoals();
      await fetchTelemetry();

      // Si la base est encore vide d'agents, créons un orchestrateur de démarrage dans le workspace de l'opérateur
      if (loadedAgents && loadedAgents.length === 0) {
        try {
          const createRes = await authFetch('/api/v1/agents', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workspace_id: activeWs,
              name: "Orchestrateur Suprême Rockib",
              role: "Master Orchestrator",
              default_autonomy_level: 3,
            }),
          });
          if (createRes.ok) {
            const newAgent = await createRes.json();
            await authFetch('/api/v1/goals', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                workspace_id: activeWs,
                agent_id: newAgent.id,
                objective: "Contrôle d'intégrité globale et cartographie du réseau d'agents",
                requested_autonomy_level: 3,
                initial_tasks: [
                  "Diagnostic d'intégrité système (system.read)",
                  "Évaluation de charge des sous-agents",
                  "Validation de la clôture déterministe",
                ],
              }),
            });
            await fetchAgents();
            await fetchGoals();
          }
        } catch (err) {
          console.warn("Impossible de semer l'agent initial:", err);
        }
      }
    };

    const savedToken = localStorage.getItem('rockib_token');
    if (savedToken) {
      authFetch('/api/v1/auth/me')
        .then((r) => (r.ok ? r.json() : null))
        .then((userData) => {
          if (userData) {
            setCurrentUser(userData);
            if (userData.default_workspace_id) {
              setWorkspaceId(userData.default_workspace_id);
            }
            initData(userData.default_workspace_id);
          }
        })
        .catch(() => {});
    }

    if (savedToken) {
      const interval = setInterval(() => {
        fetchAgents();
        fetchGoals();
        fetchTelemetry();
      }, 4500);

      return () => clearInterval(interval);
    }
  }, [currentUser?.id]);

  // Raccourcis clavier (Ctrl+` pour Terminal, Ctrl+G pour Gouvernance)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.key === '`') {
        e.preventDefault();
        setIsTerminalOpen((prev) => !prev);
      } else if (e.ctrlKey && (e.key === 'g' || e.key === 'G')) {
        e.preventDefault();
        setIsGovernanceOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('rockib_token');
    setCurrentUser(null);
    setAgents([]);
    setGoals([]);
    addToast('Session déconnectée.', 'info');
  };

  // Mettre à jour les détails du goal actif
  useEffect(() => {
    if (selectedGoalId) {
      fetchGoalDetails(selectedGoalId);
    }
  }, [selectedGoalId, fetchGoalDetails]);

  // Action : Réveil autonome (wake_goal)
  const handleWakeGoal = async (goalId) => {
    if (!goalId || isWaking) return;
    setIsWaking(true);
    try {
      const res = await authFetch(`/api/v1/goals/${goalId}/wake`, {
        method: 'POST',
      });
      if (res.ok) {
        const result = await res.json();
        await fetchAgents();
        await fetchGoals();
        const details = await fetchGoalDetails(goalId);
        await fetchTelemetry();
        addToast(
          `Cycle autonome exécuté : ${result.status} (${result.execution_effect || 'ok'})`,
          result.status === 'EXECUTED' || result.status === 'GOAL_COMPLETED' ? 'success' : 'info'
        );
        return { result, details };
      } else {
        addToast("Échec de l'exécution du cycle Wake.", 'error');
      }
    } catch (err) {
      console.error("Erreur lors de l'appel wake_goal:", err);
      addToast("Erreur réseau lors de l'appel Wake.", 'error');
      throw err;
    } finally {
      setIsWaking(false);
    }
  };

  // Action : Créer une nouvelle mission DAG
  const handleCreateGoalModalSubmit = async (goalPayload) => {
    const targetWorkspace = agents.length > 0 ? agents[0].workspace_id : (workspaceId || DEFAULT_WORKSPACE_ID);
    const res = await authFetch('/api/v1/goals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace_id: targetWorkspace,
        agent_id: goalPayload.agent_id,
        objective: goalPayload.objective,
        priority: goalPayload.priority || 1,
        requested_autonomy_level: goalPayload.requested_autonomy_level ?? 3,
        initial_tasks: goalPayload.initial_tasks,
      }),
    });

    if (res.ok) {
      const created = await res.json();
      setSelectedGoalId(created.id);
      await fetchGoals();
      await fetchGoalDetails(created.id);
      await fetchAgents();
      setIsSplitView(true);
      addToast(`Mission DAG créée : "${created.objective.slice(0, 42)}..."`, 'success');
      return created;
    } else {
      addToast("Erreur lors de la création de la mission DAG.", 'error');
    }
  };

  // Action : Matérialiser / Spawner un agent dans la matrice 3D
  const handleSpawnAgent = async (agentData) => {
    try {
      const targetWorkspace = agents.length > 0 ? agents[0].workspace_id : (workspaceId || DEFAULT_WORKSPACE_ID);
      const res = await authFetch('/api/v1/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: targetWorkspace,
          name: agentData.name,
          role: agentData.role,
          default_autonomy_level: agentData.default_autonomy_level,
          parent_agent_id: agentData.parent_agent_id || null,
        }),
      });

      if (res.ok) {
        const newAgent = await res.json();

        if (agentData.mission) {
          await authFetch('/api/v1/goals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workspace_id: targetWorkspace,
              agent_id: newAgent.id,
              objective: agentData.mission,
              requested_autonomy_level: agentData.default_autonomy_level,
              parent_goal_id: selectedGoalId || null,
            }),
          });
        }

        setSpawnEvent({
          agentId: newAgent.id,
          parentId: agentData.parent_agent_id,
          timestamp: Date.now(),
        });

        await fetchAgents();
        await fetchGoals();
        setSelectedAgentId(newAgent.id);
        addToast(`Agent "${newAgent.name}" matérialisé dans l'espace 3D !`, 'success');
      } else {
        addToast("Impossible de déployer l'agent (vérifiez votre session).", 'error');
      }
    } catch (err) {
      console.error("Erreur spawn agent:", err);
      addToast("Erreur lors du déploiement de l'agent.", 'error');
    }
  };

  // Ouvrir le modal avec parent pré-sélectionné
  const handleOpenSpawnForParent = (parentId) => {
    setSpawnParentId(parentId);
    setIsSpawnModalOpen(true);
  };

  const handleOpenCreateGoalForAgent = (agId = null) => {
    setGoalAgentId(agId || selectedAgentId || agents[0]?.id || null);
    setIsCreateGoalOpen(true);
  };

  // Trouver l'agent sélectionné et ses sous-agents
  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
  const parentAgent = selectedAgent?.parent_agent_id 
    ? agents.find((a) => a.id === selectedAgent.parent_agent_id) 
    : null;
  const subAgents = selectedAgent 
    ? agents.filter((a) => a.parent_agent_id === selectedAgent.id) 
    : [];
  const agentActiveGoal = goals.find((g) => g.agent_id === selectedAgent?.id) || goals[0];

  return (
    <div className="app-container">
      {/* Barre d'en-tête Cockpit */}
      <CockpitHeader
        agentsCount={agents.length}
        goalsCount={goals.length}
        healthStatus={healthStatus}
        isSplitView={isSplitView}
        onToggleSplitView={() => setIsSplitView(!isSplitView)}
        onOpenSpawnModal={() => {
          if (!currentUser) {
            addToast("Accès Verrouillé : Connectez-vous pour déployer un agent.", "warning");
            setIsAuthModalOpen(true);
            return;
          }
          setSpawnParentId(null);
          setIsSpawnModalOpen(true);
        }}
        onOpenCreateGoalModal={() => {
          if (!currentUser) {
            addToast("Accès Verrouillé : Connectez-vous pour créer une mission DAG.", "warning");
            setIsAuthModalOpen(true);
            return;
          }
          handleOpenCreateGoalForAgent(selectedAgentId);
        }}
        onWakeGlobal={() => {
          if (!currentUser) {
            addToast("Accès Verrouillé : Connectez-vous pour exécuter le réveil autonome.", "warning");
            setIsAuthModalOpen(true);
            return;
          }
          handleWakeGoal(selectedGoalId || goals[0]?.id);
        }}
        onResetCamera={() => setSelectedAgentId(null)}
        isWaking={isWaking}
        currentUser={currentUser}
        onOpenAuthModal={() => setIsAuthModalOpen(true)}
        onLogout={handleLogout}
        isDashboardOpen={isDashboardOpen}
        onToggleDashboard={() => setIsDashboardOpen(!isDashboardOpen)}
        isTerminalOpen={isTerminalOpen}
        onToggleTerminal={() => {
          if (!currentUser) {
            addToast("Accès Verrouillé : Connectez-vous pour ouvrir le Terminal de commandes.", "warning");
            setIsAuthModalOpen(true);
            return;
          }
          setIsTerminalOpen(!isTerminalOpen);
        }}
        isTimelineOpen={isTimelineOpen}
        onToggleTimeline={() => setIsTimelineOpen(!isTimelineOpen)}
        isGovernanceOpen={isGovernanceOpen}
        onToggleGovernance={() => {
          if (!currentUser) {
            addToast("Accès Verrouillé : Connectez-vous pour accéder au centre d'Arbitrage.", "warning");
            setIsAuthModalOpen(true);
            return;
          }
          setIsGovernanceOpen(!isGovernanceOpen);
        }}
        isConnectorsOpen={isConnectorsOpen}
        onToggleConnectors={() => {
          if (!currentUser) {
            addToast("Accès Verrouillé : Connectez-vous pour accéder au Hub Réseaux & Meta Ads.", "warning");
            setIsAuthModalOpen(true);
            return;
          }
          setIsConnectorsOpen(!isConnectorsOpen);
        }}
        isObservabilityOpen={isObservabilityOpen}
        onToggleObservability={() => setIsObservabilityOpen(!isObservabilityOpen)}
        isClientCRMOpen={isClientCRMOpen}
        onToggleClientCRM={() => setIsClientCRMOpen(!isClientCRMOpen)}
      />

      {/* Zone de rendu 3D & HUD */}
      <main className="viewport-area">
        {/* Notifications Toast Holographiques */}
        {toasts.length > 0 && (
          <div
            style={{
              position: 'fixed',
              top: '76px',
              right: '24px',
              zIndex: 9999,
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              pointerEvents: 'none',
            }}
          >
            {toasts.map((t) => {
              const borderColor =
                t.type === 'success'
                  ? '#10B981'
                  : t.type === 'error'
                  ? '#F43F5E'
                  : t.type === 'warning'
                  ? '#F59E0B'
                  : 'var(--neon-cyan)';
              return (
                <div
                  key={t.id}
                  style={{
                    background: 'rgba(8, 12, 24, 0.92)',
                    backdropFilter: 'blur(14px)',
                    border: `1px solid ${borderColor}`,
                    borderLeft: `4px solid ${borderColor}`,
                    borderRadius: '8px',
                    padding: '10px 16px',
                    color: '#F8FAFC',
                    fontSize: '0.82rem',
                    boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
                    maxWidth: '380px',
                  }}
                >
                  {t.message}
                </div>
              );
            })}
          </div>
        )}

        {/* Bannière d'accueil si non authentifié */}
        {!currentUser && (
          <div
            className="glass-panel hud-interactive"
            style={{
              position: 'absolute',
              bottom: '28px',
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 30,
              padding: '14px 24px',
              borderRadius: '12px',
              border: '1px solid rgba(0, 240, 255, 0.35)',
              display: 'flex',
              alignItems: 'center',
              gap: '18px',
              background: 'rgba(8, 12, 24, 0.88)',
              boxShadow: '0 0 30px rgba(0, 240, 255, 0.15)',
            }}
          >
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#FFFFFF' }}>
                Cockpit Spatial Rockib IA — Mode Visiteur
              </div>
              <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                Connectez-vous ou créez un compte opérateur pour déployer vos agents 3D, lancer des missions DAG et auditer l'Arbitrateur déterministe.
              </div>
            </div>
            <button
              onClick={() => setIsAuthModalOpen(true)}
              className="btn-cyber primary"
              style={{ whiteSpace: 'nowrap' }}
            >
              Se Connecter / Créer un Compte
            </button>
          </div>
        )}

        {/* Scène 3D WebGL (Three.js) */}
        <ThreeCanvas
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={(id) => {
            setSelectedAgentId(id);
            const agentGoal = goals.find((g) => g.agent_id === id);
            if (agentGoal) setSelectedGoalId(agentGoal.id);
          }}
          isSplitView={isSplitView}
          spawnEvent={spawnEvent}
        />

        {/* Fiche d'activité holographique de l'agent sélectionné */}
        {selectedAgent && !isTimelineOpen && (
          <AgentActivityCard
            agent={selectedAgent}
            parentAgent={parentAgent}
            subAgents={subAgents}
            activeGoal={agentActiveGoal}
            onClose={() => setSelectedAgentId(null)}
            onWakeGoal={handleWakeGoal}
            onSpawnSubAgent={handleOpenSpawnForParent}
            onOpenCreateGoal={handleOpenCreateGoalForAgent}
            onSelectAgent={(id) => {
              setSelectedAgentId(id);
              const g = goals.find((x) => x.agent_id === id);
              if (g) setSelectedGoalId(g.id);
            }}
            isWaking={isWaking}
          />
        )}

        {/* Console tactique latérale en mode Split */}
        {isSplitView && (
          <TaskDAGPanel
            goals={goals}
            selectedGoalId={selectedGoalId}
            onSelectGoal={(id) => setSelectedGoalId(id)}
            goalDetails={goalDetails}
            telemetry={telemetry}
            onWakeGoal={handleWakeGoal}
            isWaking={isWaking}
          />
        )}

        {/* Dashboard Panel (bottom-left) */}
        <DashboardPanel
          isOpen={isDashboardOpen}
          onClose={() => setIsDashboardOpen(false)}
          agents={agents}
          goals={goals}
          telemetry={telemetry}
        />

        {/* Event Timeline (right side) */}
        <EventTimeline
          isOpen={isTimelineOpen}
          onClose={() => setIsTimelineOpen(false)}
          telemetry={telemetry}
        />
      </main>

      {/* Terminal CLI (bottom overlay) */}
      <CyberTerminal
        isOpen={isTerminalOpen}
        onClose={() => setIsTerminalOpen(false)}
        agents={agents}
        goals={goals}
        telemetry={telemetry}
        onWakeGoal={handleWakeGoal}
        onSpawnAgent={handleSpawnAgent}
        onSelectAgent={(id) => {
          setSelectedAgentId(id);
          const g = goals.find((x) => x.agent_id === id);
          if (g) setSelectedGoalId(g.id);
        }}
        onCreateGoal={async (agentId, objective) => {
           const targetWorkspace = agents.length > 0 ? agents[0].workspace_id : (workspaceId || DEFAULT_WORKSPACE_ID);
           const res = await authFetch('/api/v1/goals', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                workspace_id: targetWorkspace,
                agent_id: agentId,
                objective: objective,
                requested_autonomy_level: 2,
              }),
            });
            if (!res.ok) throw new Error("Erreur de l'API lors de la création de la mission.");
            const created = await res.json();
            setSelectedGoalId(created.id);
            await fetchGoals();
            await fetchGoalDetails(created.id);
            return created;
        }}
      />

      {/* Centre d'Arbitrage Déterministe & Décisions */}
      <GovernancePanel
        isOpen={isGovernanceOpen}
        onClose={() => setIsGovernanceOpen(false)}
        agents={agents}
        workspaceId={agents[0]?.workspace_id || workspaceId}
        onNotify={addToast}
      />

      {/* Hub Réseaux Sociaux & Meta Ads (HMAC-SHA256) */}
      <SocialConnectorsPanel
        isOpen={isConnectorsOpen}
        onClose={() => setIsConnectorsOpen(false)}
        workspaceId={agents[0]?.workspace_id || workspaceId}
        currentUser={currentUser}
        onOpenAuth={() => setIsAuthModalOpen(true)}
        addToast={addToast}
      />

      {/* Espace Commercial B2B, CRM Prospects & Intégration Web */}
      <ClientCRMModal
        isOpen={isClientCRMOpen}
        onClose={() => setIsClientCRMOpen(false)}
        workspaceId={agents[0]?.workspace_id || workspaceId}
        onNotify={addToast}
      />

      {/* Observabilité Unifiée, Télémétrie Groq LLM & Quotas */}
      <ObservabilityPanel
        isOpen={isObservabilityOpen}
        onClose={() => setIsObservabilityOpen(false)}
        workspaceId={agents[0]?.workspace_id || workspaceId}
        onNotify={addToast}
      />

      {/* Modal de création d'une nouvelle mission DAG */}
      <CreateGoalModal
        isOpen={isCreateGoalOpen}
        onClose={() => setIsCreateGoalOpen(false)}
        agents={agents}
        defaultAgentId={goalAgentId}
        onCreateGoal={handleCreateGoalModalSubmit}
      />

      {/* Modal de création / matérialisation d'agent */}
      <SpawnAgentModal
        isOpen={isSpawnModalOpen}
        onClose={() => setIsSpawnModalOpen(false)}
        parentAgentId={spawnParentId}
        agents={agents}
        onSpawn={handleSpawnAgent}
      />

      {/* Modal d'Authentification / Connexion */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onLoginSuccess={(userData) => {
          if (userData?.default_workspace_id) {
            setWorkspaceId(userData.default_workspace_id);
          }
          setCurrentUser(userData);
          fetchAgents();
          fetchGoals();
          fetchTelemetry();
          addToast(`Bienvenue dans le Cockpit 3D, ${userData.first_name || userData.email} !`, 'success');
        }}
      />
    </div>
  );
}


