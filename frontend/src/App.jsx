import React, { useState, useEffect, useCallback } from 'react';
import ThreeCanvas from './components/ThreeCanvas';
import CockpitHeader from './components/CockpitHeader';
import AgentActivityCard from './components/AgentActivityCard';
import TaskDAGPanel from './components/TaskDAGPanel';
import SpawnAgentModal from './components/SpawnAgentModal';

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

  // Charger les agents depuis l'API
  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/agents');
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
      const res = await fetch('/api/v1/goals');
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
      const res = await fetch(`/api/v1/goals/${goalId}`);
      if (res.ok) {
        const data = await res.json();
        setGoalDetails(data);
      }
    } catch (e) {
      console.warn("Erreur détails goal:", e);
    }
  }, []);

  // Charger la télémétrie
  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/telemetry');
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
      if (loadedAgents.length === 0) {
        try {
          const createRes = await fetch('/api/v1/agents', {
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
            await fetch('/api/v1/goals', {
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

    initData();
    const interval = setInterval(() => {
      fetchAgents();
      fetchGoals();
      fetchTelemetry();
    }, 4500);

    return () => clearInterval(interval);
  }, []);

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
      const res = await fetch(`/api/v1/goals/${goalId}/wake`, {
        method: 'POST',
      });
      if (res.ok) {
        const result = await res.json();
        console.log("Résultat wake_goal:", result);
        // Rafraîchissement immédiat
        await fetchAgents();
        await fetchGoals();
        await fetchGoalDetails(goalId);
        await fetchTelemetry();
      }
    } catch (err) {
      console.error("Erreur lors de l'appel wake_goal:", err);
    } finally {
      setIsWaking(false);
    }
  };

  // Action : Matérialiser / Spawner un agent dans la matrice 3D
  const handleSpawnAgent = async (agentData) => {
    try {
      const targetWorkspace = agents.length > 0 ? agents[0].workspace_id : DEFAULT_WORKSPACE_ID;
      const res = await fetch('/api/v1/agents', {
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
          await fetch('/api/v1/goals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workspace_id: targetWorkspace,
              agent_id: newAgent.id,
              objective: agentData.mission,
              requested_autonomy_level: agentData.default_autonomy_level,
              parent_goal_id: selectedGoalId || null,
              initial_tasks: [
                `Exécuter mission: ${agentData.mission}`,
                "Audit des effets via system.read",
              ],
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
        {selectedAgent && (
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
      </main>

      {/* Modal de création / matérialisation d'agent */}
      <SpawnAgentModal
        isOpen={isSpawnModalOpen}
        onClose={() => setIsSpawnModalOpen(false)}
        parentAgentId={spawnParentId}
        agents={agents}
        onSpawn={handleSpawnAgent}
      />
    </div>
  );
}
