import React, { useState, useEffect, useCallback } from 'react';
import ThreeCanvas from './components/ThreeCanvas';
import CockpitHeader from './components/CockpitHeader';
import AgentActivityCard from './components/AgentActivityCard';
import TaskDAGPanel from './components/TaskDAGPanel';
import SpawnAgentModal from './components/SpawnAgentModal';
import AuthModal from './components/AuthModal';
import DashboardPanel from './components/DashboardPanel';
import CyberTerminal from './components/CyberTerminal';
import EventTimeline from './components/EventTimeline';
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
  const [isSplitView, setIsSplitView] = useState(false);
  const [isSpawnModalOpen, setIsSpawnModalOpen] = useState(false);
  const [spawnParentId, setSpawnParentId] = useState(null);
  const [spawnEvent, setSpawnEvent] = useState(null);
  const [isWaking, setIsWaking] = useState(false);
  const [workspaceId, setWorkspaceId] = useState(DEFAULT_WORKSPACE_ID);
  const [currentUser, setCurrentUser] = useState(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  // New panel states
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);

  // Écouter l'événement 401 pour afficher le modal d'authentification
  useEffect(() => {
    const handleUnauthorized = () => {
      setCurrentUser(null);
      setIsAuthModalOpen(true);
    };
    window.addEventListener('rockib:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('rockib:unauthorized', handleUnauthorized);
  }, []);

  // Charger les agents depuis l'API
  const fetchAgents = useCallback(async () => {
    try {
      const res = await authFetch('/api/v1/agents');
      if (res.ok) {
        const data = await res.json();
        setAgents(data);
        if (data.length > 0 && !selectedAgentId) {
          setSelectedAgentId(data[0].id);
        }
        return data;
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
    const initData = async () => {
      const loadedAgents = await fetchAgents();
      await fetchGoals();
      await fetchTelemetry();

      // Si la base est encore vide d'agents, créons un orchestrateur de démarrage
      if (loadedAgents && loadedAgents.length === 0) {
        try {
          const createRes = await authFetch('/api/v1/agents', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workspace_id: DEFAULT_WORKSPACE_ID,
              name: "Orchestrateur Suprême Rockib",
              role: "Master Orchestrator",
              default_autonomy_level: 3,
            }),
          });
          if (createRes.ok) {
            const newAgent = await createRes.json();
            // Créer un goal initial avec handler system.read
            await authFetch('/api/v1/goals', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                workspace_id: DEFAULT_WORKSPACE_ID,
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

    // Vérifier si un token existe pour restaurer la session utilisateur
    const savedToken = localStorage.getItem('rockib_token');
    if (savedToken) {
      authFetch('/api/v1/auth/me')
        .then((r) => (r.ok ? r.json() : null))
        .then((userData) => {
          if (userData) {
            setCurrentUser(userData);
            initData();
          }
        })
        .catch(() => {});
    }

    // Ne lancer le polling que si un token existe
    if (savedToken) {
      const interval = setInterval(() => {
        fetchAgents();
        fetchGoals();
        fetchTelemetry();
      }, 4500);

      return () => clearInterval(interval);
    }
  }, [currentUser]);

  // Raccourci clavier Ctrl+` pour le terminal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.key === '`') {
        e.preventDefault();
        setIsTerminalOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('rockib_token');
    setCurrentUser(null);
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
        console.log("Résultat wake_goal:", result);
        // Rafraîchissement immédiat
        await fetchAgents();
        await fetchGoals();
        const details = await fetchGoalDetails(goalId);
        await fetchTelemetry();
        return { result, details };
      }
    } catch (err) {
      console.error("Erreur lors de l'appel wake_goal:", err);
      throw err;
    } finally {
      setIsWaking(false);
    }
  };

  // Action : Matérialiser / Spawner un agent dans la matrice 3D
  const handleSpawnAgent = async (agentData) => {
    try {
      const targetWorkspace = agents.length > 0 ? agents[0].workspace_id : DEFAULT_WORKSPACE_ID;
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

        // Si une mission est spécifiée, créer un Goal associé
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

        // Déclencher l'effet d'explosion de particules et le laser 3D
        setSpawnEvent({
          agentId: newAgent.id,
          parentId: agentData.parent_agent_id,
          timestamp: Date.now(),
        });

        // Mettre à jour l'état et sélectionner l'agent
        await fetchAgents();
        await fetchGoals();
        setSelectedAgentId(newAgent.id);
      }
    } catch (err) {
      console.error("Erreur spawn agent:", err);
    }
  };

  // Ouvrir le modal avec parent pré-sélectionné
  const handleOpenSpawnForParent = (parentId) => {
    setSpawnParentId(parentId);
    setIsSpawnModalOpen(true);
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
        isSplitView={isSplitView}
        onToggleSplitView={() => setIsSplitView(!isSplitView)}
        onOpenSpawnModal={() => {
          setSpawnParentId(null);
          setIsSpawnModalOpen(true);
        }}
        onWakeGlobal={() => handleWakeGoal(selectedGoalId || goals[0]?.id)}
        onResetCamera={() => setSelectedAgentId(null)}
        isWaking={isWaking}
        currentUser={currentUser}
        onOpenAuthModal={() => setIsAuthModalOpen(true)}
        onLogout={handleLogout}
        isDashboardOpen={isDashboardOpen}
        onToggleDashboard={() => setIsDashboardOpen(!isDashboardOpen)}
        isTerminalOpen={isTerminalOpen}
        onToggleTerminal={() => setIsTerminalOpen(!isTerminalOpen)}
        isTimelineOpen={isTimelineOpen}
        onToggleTimeline={() => setIsTimelineOpen(!isTimelineOpen)}
      />

      {/* Zone de rendu 3D & HUD */}
      <main className="viewport-area">
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
           const targetWorkspace = agents.length > 0 ? agents[0].workspace_id : DEFAULT_WORKSPACE_ID;
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
          setCurrentUser(userData);
          fetchAgents();
          fetchGoals();
          fetchTelemetry();
        }}
      />
    </div>
  );
}
