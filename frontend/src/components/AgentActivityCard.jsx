import React, { useState, useEffect } from 'react';
import { 
  Bot, 
  Cpu, 
  ShieldCheck, 
  Zap, 
  X, 
  Play, 
  GitFork, 
  CheckCircle2, 
  AlertTriangle,
  Terminal,
  Clock,
  FileText,
  MessageSquare,
  Send
} from 'lucide-react';
import { authFetch } from '../lib/authFetch';

/**
 * AgentActivityCard — Carte holographique affichant en direct
 * ce que fait l'agent sélectionné (pensée, tâche active, sécurité, dialogue P2P, sous-agents).
 */
export default function AgentActivityCard({
  agent,
  allAgents = [],
  parentAgent,
  subAgents = [],
  activeGoal,
  onClose,
  onWakeGoal,
  onSpawnSubAgent,
  onOpenCreateGoal,
  onSelectAgent,
  onDialogueSuccess,
  isWaking = false,
}) {
  if (!agent) return null;

  const isOrchestrator = !agent.parent_agent_id;
  const statusClass = (agent.current_status || 'ready').toLowerCase();

  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  // États pour le Bus de Dialogue P2P Inter-Agents
  const [showP2P, setShowP2P] = useState(false);
  const [targetPeerId, setTargetPeerId] = useState('');
  const [p2pSubject, setP2pSubject] = useState('Synchronisation Technique P2P');
  const [p2pMessage, setP2pMessage] = useState('');
  const [sendingP2P, setSendingP2P] = useState(false);
  const [lastP2PReply, setLastP2PReply] = useState(null);
  const [conveningCouncil, setConveningCouncil] = useState(false);
  const [councilVerdict, setCouncilVerdict] = useState(null);

  // P3 — États pour la Sandbox d'Exécution Isolée (Code + Tests Unitaires)
  const [showSandbox, setShowSandbox] = useState(false);
  const [sandboxCode, setSandboxCode] = useState(
    'def compute_risk_score(autonomy: int, spend: float) -> float:\n    return round(min(1.0, (spend / 1000.0) * (6 - autonomy) * 0.2), 3)\n\nprint("Risk score:", compute_risk_score(3, 450.0))'
  );
  const [sandboxTests, setSandboxTests] = useState(
    'assert compute_risk_score(3, 450.0) == 0.27\nassert compute_risk_score(5, 0.0) == 0.0'
  );
  const [runningSandbox, setRunningSandbox] = useState(false);
  const [sandboxReport, setSandboxReport] = useState(null);

  // P5, P6, P7 — États pour Mémoire Vectorielle (P5), Auto-Swarm (P6) et Veille Proactive (P7)
  const [showMemoryP5, setShowMemoryP5] = useState(false);
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoriesList, setMemoriesList] = useState([]);
  const [searchingMemory, setSearchingMemory] = useState(false);
  const [spawningSwarm, setSpawningSwarm] = useState(false);
  const [swarmResult, setSwarmResult] = useState(null);
  const [runningWatch, setRunningWatch] = useState(false);
  const [watchReport, setWatchReport] = useState(null);

  const peerAgents = allAgents.filter((a) => a.id !== agent.id);

  useEffect(() => {
    if (peerAgents.length > 0 && !targetPeerId) {
      setTargetPeerId(peerAgents[0].id);
    }
  }, [agent?.id, allAgents.length]);

  const fetchAgentLogs = () => {
    if (agent && agent.id) {
      setLoadingLogs(true);
      authFetch(`/api/v1/agents/${agent.id}/logs?limit=30`)
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && data.logs) setLogs(data.logs);
        })
        .catch((err) => console.warn('Erreur chargement logs agent:', err))
        .finally(() => setLoadingLogs(false));
    }
  };

  useEffect(() => {
    fetchAgentLogs();
    setLastP2PReply(null);
    setCouncilVerdict(null);
  }, [agent?.id]);

  const handleConveneCouncil = async () => {
    if (conveningCouncil || peerAgents.length === 0) return;
    setConveningCouncil(true);
    try {
      const objectiveText = activeGoal?.objective || `Coordination stratégique pour ${agent.name}`;
      const actionText = p2pMessage.trim() || agent.current_action || `Audit architectural et sécurité par le Conseil IA`;
      const res = await authFetch('/api/v1/agents/council', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: agent.workspace_id,
          lead_agent_id: agent.id,
          objective: objectiveText,
          proposed_action: actionText,
          max_specialists: 2,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setCouncilVerdict(data);
        fetchAgentLogs();
        if (onDialogueSuccess) onDialogueSuccess(data);
      }
    } catch (err) {
      console.error('Erreur Conseil IA:', err);
    } finally {
      setConveningCouncil(false);
    }
  };

  const handleRunSandbox = async (e) => {
    e.preventDefault();
    if (runningSandbox || !sandboxCode.trim()) return;
    setRunningSandbox(true);
    try {
      const res = await authFetch('/api/v1/execution/sandbox/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: agent.workspace_id,
          code: sandboxCode,
          test_code: sandboxTests,
          language: 'python',
          timeout_seconds: 5.0,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSandboxReport(data);
      }
    } catch (err) {
      console.error('Erreur exécution sandbox:', err);
    } finally {
      setRunningSandbox(false);
    }
  };

  // P5 — Recherche sémantique dans pgvector (768d)
  const handleSearchMemoryP5 = async (e) => {
    if (e) e.preventDefault();
    const q = (memoryQuery || agent.name || 'architecture').trim();
    setSearchingMemory(true);
    try {
      const res = await authFetch(
        `/api/v1/memory/search?workspace_id=${agent.workspace_id}&q=${encodeURIComponent(q)}&limit=6`
      );
      if (res.ok) {
        const data = await res.json();
        setMemoriesList(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error('Erreur recherche mémoire P5:', err);
    } finally {
      setSearchingMemory(false);
    }
  };

  // P6 — Déploiement Auto-Swarm 3D
  const handleTriggerAutoSwarmP6 = async () => {
    if (!activeGoal?.id || spawningSwarm) return;
    setSpawningSwarm(true);
    try {
      const res = await authFetch(`/api/v1/goals/${activeGoal.id}/auto-swarm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_sub_agents: 3 }),
      });
      if (res.ok) {
        const data = await res.json();
        setSwarmResult(data);
        if (onDialogueSuccess) onDialogueSuccess(data);
      }
    } catch (err) {
      console.error('Erreur Auto-Swarm P6:', err);
    } finally {
      setSpawningSwarm(false);
    }
  };

  // P7 — Exécuter la Sonde de Veille Proactive
  const handleRunProactiveWatchP7 = async () => {
    if (runningWatch) return;
    setRunningWatch(true);
    try {
      const res = await authFetch('/api/v1/goals/proactive-watch/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: agent.workspace_id,
          agent_id: agent.id,
          notify_telegram: false,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setWatchReport(data);
      }
    } catch (err) {
      console.error('Erreur Veille Proactive P7:', err);
    } finally {
      setRunningWatch(false);
    }
  };

  const handleSendP2P = async (e) => {
    e.preventDefault();
    if (!targetPeerId || !p2pMessage.trim() || sendingP2P) return;
    setSendingP2P(true);
    try {
      const res = await authFetch('/api/v1/agents/dialogue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: agent.workspace_id,
          sender_agent_id: agent.id,
          recipient_agent_id: targetPeerId,
          subject: p2pSubject || 'Collaboration P2P',
          message: p2pMessage.trim(),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setLastP2PReply(data);
        setP2pMessage('');
        fetchAgentLogs();
        if (onDialogueSuccess) onDialogueSuccess(data);
      }
    } catch (err) {
      console.error('Erreur dialogue P2P:', err);
    } finally {
      setSendingP2P(false);
    }
  };

  return (
    <div className="agent-activity-card glass-panel hud-interactive">
      {/* En-tête de la carte */}
      <div className="card-header">
        <div className="agent-profile">
          <div className="agent-avatar-ring">
            <Bot size={22} color="var(--neon-cyan)" />
          </div>
          <div className="agent-meta">
            <h3>{agent.name}</h3>
            <span className="agent-role">
              {agent.role || (isOrchestrator ? 'Master Orchestrator' : 'Specialized Worker')}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className={`status-badge ${statusClass}`}>
            <span className="status-dot" style={{ 
              backgroundColor: statusClass === 'running' ? 'var(--neon-emerald)' : 'var(--neon-cyan)' 
            }} />
            {agent.current_status}
          </span>
          <button 
            onClick={onClose}
            className="control-btn"
            style={{ padding: '6px', borderRadius: '50%' }}
            title="Fermer l'inspecteur"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Corps de la carte */}
      <div className="card-body">
        {/* Section 1 : Ce que fait l'agent en direct */}
        <div className="info-section">
          <span className="info-section-title">Activité en cours</span>
          <div className="thought-box">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <Cpu size={15} color="var(--neon-cyan)" />
              <strong style={{ color: 'var(--neon-cyan)', fontSize: '0.8rem' }}>ACTION COURANTE</strong>
            </div>
            {agent.current_action || "En attente de consignes ou de réveil autonome..."}
          </div>
        </div>

        {/* Section 2 : Gouvernance & Autonomie */}
        <div className="info-section">
          <span className="info-section-title">Gouvernance & Sécurité</span>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '1fr 1fr', 
            gap: '10px',
            background: 'rgba(0,0,0,0.25)', 
            padding: '10px', 
            borderRadius: '8px' 
          }}>
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>NIVEAU D'AUTONOMIE</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                <ShieldCheck size={16} color="var(--neon-emerald)" />
                <strong style={{ fontSize: '0.9rem' }}>Niveau {agent.default_autonomy_level}/5</strong>
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>AFFILIATION</span>
              <div style={{ marginTop: '2px', fontSize: '0.85rem', color: 'var(--text-highlight)' }}>
                {parentAgent ? (
                  <span 
                    onClick={() => onSelectAgent(parentAgent.id)}
                    style={{ color: 'var(--neon-cyan)', cursor: 'pointer', textDecoration: 'underline' }}
                  >
                    Parent: {parentAgent.name}
                  </span>
                ) : (
                  <span style={{ color: 'var(--neon-indigo)' }}>Agent Racine (Master)</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Section 3 : Objectif actif & Tâches */}
        <div className="info-section">
          <span className="info-section-title">Objectif & Avancement</span>
          <div className="activity-progress">
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>
                {activeGoal ? activeGoal.objective : "Aucun objectif actif assigné"}
              </span>
              <span className="mono" style={{ color: 'var(--neon-cyan)' }}>
                {agent.completed_tasks_count} / {agent.total_tasks_count || 1} tâches
              </span>
            </div>
            <div className="progress-bar-track">
              <div 
                className="progress-bar-fill" 
                style={{ 
                  width: `${agent.total_tasks_count ? Math.round((agent.completed_tasks_count / agent.total_tasks_count) * 100) : 15}%` 
                }} 
              />
            </div>
          </div>
        </div>

        {/* Section 4 : Bus de Dialogue P2P Inter-Agents */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="info-section-title" style={{ color: '#EC4899' }}>
              Bus de Dialogue P2P Inter-Agents
            </span>
            <button
              onClick={() => setShowP2P(!showP2P)}
              className="control-btn"
              style={{ padding: '3px 8px', fontSize: '0.72rem', color: '#EC4899', borderColor: 'rgba(236,72,153,0.35)', display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              <MessageSquare size={12} />
              {showP2P ? 'Fermer Bus P2P' : 'Dialoguer avec un Pair'}
            </button>
          </div>

          {showP2P && (
            <form
              onSubmit={handleSendP2P}
              style={{
                background: 'rgba(236, 72, 153, 0.06)',
                border: '1px solid rgba(236, 72, 153, 0.3)',
                borderRadius: '8px',
                padding: '10px',
                marginTop: '6px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div>
                <label style={{ fontSize: '0.68rem', color: '#F472B6', display: 'block', marginBottom: '3px' }}>
                  AGENT PAIR DESTINATAIRE :
                </label>
                <select
                  value={targetPeerId}
                  onChange={(e) => setTargetPeerId(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    background: '#060A17',
                    border: '1px solid rgba(236, 72, 153, 0.35)',
                    borderRadius: '6px',
                    color: '#F8FAFC',
                    fontSize: '0.76rem',
                  }}
                >
                  {peerAgents.map((pa) => (
                    <option key={pa.id} value={pa.id}>
                      {pa.name} ({pa.role || 'Peer'})
                    </option>
                  ))}
                </select>
              </div>

              <input
                type="text"
                value={p2pMessage}
                onChange={(e) => setP2pMessage(e.target.value)}
                placeholder={`Ex: Peux-tu synchroniser le contrat API avec ${agent.name} ?`}
                style={{
                  width: '100%',
                  padding: '7px 10px',
                  background: '#060A17',
                  border: '1px solid rgba(0, 240, 255, 0.25)',
                  borderRadius: '6px',
                  color: '#F8FAFC',
                  fontSize: '0.76rem',
                }}
              />

              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  type="submit"
                  disabled={sendingP2P || !p2pMessage.trim() || peerAgents.length === 0}
                  className="btn-cyber primary"
                  style={{
                    flex: 1,
                    padding: '6px 10px',
                    fontSize: '0.73rem',
                    justifyContent: 'center',
                    background: 'linear-gradient(135deg, rgba(236, 72, 153, 0.25), rgba(168, 85, 247, 0.25))',
                    borderColor: '#EC4899',
                  }}
                >
                  <Send size={13} />
                  {sendingP2P ? 'Négociation...' : 'Négocier P2P'}
                </button>

                <button
                  type="button"
                  onClick={handleConveneCouncil}
                  disabled={conveningCouncil || peerAgents.length === 0}
                  className="btn-cyber"
                  style={{
                    flex: 1,
                    padding: '6px 10px',
                    fontSize: '0.73rem',
                    justifyContent: 'center',
                    background: 'rgba(16, 185, 129, 0.16)',
                    borderColor: '#10B981',
                    color: '#10B981',
                  }}
                  title="Réunit les spécialistes pertinents via Gemma-2 768d"
                >
                  <ShieldCheck size={13} />
                  {conveningCouncil ? 'Délibération...' : 'Conseil IA (Gemma-2)'}
                </button>
              </div>

              {councilVerdict && (
                <div
                  style={{
                    background: 'rgba(6, 10, 23, 0.94)',
                    borderLeft: '3px solid #EC4899',
                    padding: '8px',
                    borderRadius: '4px',
                    fontSize: '0.71rem',
                  }}
                >
                  <div style={{ color: '#EC4899', fontWeight: 700, marginBottom: '4px' }}>
                    Verdict Conseil IA ({councilVerdict.consensus_stance} — Confiance {Math.round((councilVerdict.consensus_confidence || 0) * 100)}%) :
                  </div>
                  {(councilVerdict.votes || []).map((v) => (
                    <div key={v.agent_id} style={{ color: '#E2E8F0', marginBottom: '4px', lineHeight: 1.35 }}>
                      <strong style={{ color: '#00F0FF' }}>{v.agent_name}</strong> ({v.stance}, sim={v.specialty_similarity}): {v.opinion}
                    </div>
                  ))}
                </div>
              )}

              {lastP2PReply && (
                <div
                  style={{
                    background: 'rgba(6, 10, 23, 0.9)',
                    borderLeft: '3px solid #10B981',
                    padding: '8px',
                    borderRadius: '4px',
                    fontSize: '0.72rem',
                  }}
                >
                  <div style={{ color: '#10B981', fontWeight: 700, marginBottom: '3px' }}>
                    Réponse de {lastP2PReply.recipient_name} (Indexée en Mémoire Vectorielle) :
                  </div>
                  <div style={{ color: '#E2E8F0', lineHeight: 1.4 }}>{lastP2PReply.reply_content}</div>
                </div>
              )}
            </form>
          )}
        </div>

        {/* Section 5 : Sous-agents créés par cet agent + P6 Auto-Swarm 3D */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <span className="info-section-title">
              Sous-Agents déployés ({subAgents.length})
            </span>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                onClick={handleTriggerAutoSwarmP6}
                disabled={spawningSwarmP6}
                className="control-btn"
                title="P6 : Décomposer l'objectif actif en escouade de 3 spécialistes 3D (Architecte, Exécuteur, Sentinelle)"
                style={{ padding: '2px 8px', fontSize: '0.7rem', color: '#00F0FF', borderColor: 'rgba(0, 240, 255, 0.45)' }}
              >
                {spawningSwarmP6 ? 'Déploiement...' : '⚡ Auto-Swarm 3D (P6)'}
              </button>
              <button
                onClick={() => onSpawnSubAgent(agent.id)}
                className="control-btn"
                style={{ padding: '2px 8px', fontSize: '0.7rem', color: 'var(--neon-purple)' }}
              >
                + Déployer
              </button>
            </div>
          </div>

          <div className="subagents-tree">
            {subAgents.length === 0 ? (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic', padding: '6px' }}>
                Cet agent n'a pas encore matérialisé de sous-agent dans la matrice 3D.
              </div>
            ) : (
              subAgents.map((sub) => (
                <div 
                  key={sub.id} 
                  className="subagent-chip"
                  onClick={() => onSelectAgent(sub.id)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <GitFork size={14} color="var(--neon-purple)" />
                    <span style={{ fontSize: '0.82rem', fontWeight: '600' }}>{sub.name}</span>
                  </div>
                  <span className={`status-badge ${sub.current_status.toLowerCase()}`} style={{ fontSize: '0.65rem' }}>
                    {sub.current_status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Section 5b : P3 — Sandbox d'Exécution Isolée (Code, Compilation & Tests) */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="info-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Terminal size={13} color="#10B981" />
              Sandbox d'Exécution Isolée (P3)
            </span>
            <button
              onClick={() => setShowSandbox(!showSandbox)}
              className="control-btn"
              style={{
                padding: '2px 8px',
                fontSize: '0.7rem',
                color: '#10B981',
                borderColor: 'rgba(16, 185, 129, 0.45)',
              }}
            >
              {showSandbox ? 'Masquer Sandbox' : 'Coder & Tester'}
            </button>
          </div>

          {showSandbox && (
            <form
              onSubmit={handleRunSandbox}
              style={{
                marginTop: '8px',
                padding: '10px',
                borderRadius: '8px',
                background: 'rgba(16, 185, 129, 0.06)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div>
                <label style={{ fontSize: '0.68rem', color: '#94A3B8', display: 'block', marginBottom: '3px' }}>
                  CODE PYTHON ISOLÉ (SAST/AST VÉRIFIÉ) :
                </label>
                <textarea
                  rows={3}
                  value={sandboxCode}
                  onChange={(e) => setSandboxCode(e.target.value)}
                  className="mono"
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    background: '#060A17',
                    border: '1px solid rgba(16, 185, 129, 0.35)',
                    borderRadius: '6px',
                    color: '#E2E8F0',
                    fontSize: '0.72rem',
                    resize: 'vertical',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.68rem', color: '#94A3B8', display: 'block', marginBottom: '3px' }}>
                  SUITE D'ASSERTIONS / TESTS UNITAIRES :
                </label>
                <textarea
                  rows={2}
                  value={sandboxTests}
                  onChange={(e) => setSandboxTests(e.target.value)}
                  className="mono"
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    background: '#060A17',
                    border: '1px solid rgba(0, 240, 255, 0.25)',
                    borderRadius: '6px',
                    color: '#E2E8F0',
                    fontSize: '0.72rem',
                    resize: 'vertical',
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={runningSandbox || !sandboxCode.trim()}
                className="btn-cyber"
                style={{
                  padding: '6px 10px',
                  fontSize: '0.73rem',
                  justifyContent: 'center',
                  background: 'rgba(16, 185, 129, 0.18)',
                  borderColor: '#10B981',
                  color: '#10B981',
                }}
              >
                <Play size={13} />
                {runningSandbox ? 'Compilation & Tests en cours...' : 'Compiler & Exécuter en Sandbox'}
              </button>

              {sandboxReport && (
                <div
                  className="mono"
                  style={{
                    background: 'rgba(4, 7, 16, 0.95)',
                    borderLeft: `3px solid ${sandboxReport.execution_ok ? '#10B981' : '#F43F5E'}`,
                    padding: '8px',
                    borderRadius: '4px',
                    fontSize: '0.7rem',
                    color: '#E2E8F0',
                  }}
                >
                  <div style={{ fontWeight: 700, color: sandboxReport.execution_ok ? '#10B981' : '#F43F5E', marginBottom: '4px' }}>
                    {sandboxReport.execution_ok ? '✓ EXÉCUTION & TESTS VALIDÉS' : '✗ ÉCHEC / VIOLATION SAST'} ({sandboxReport.duration_ms} ms | exit={sandboxReport.exit_code})
                  </div>
                  {sandboxReport.stdout && (
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: '#A7F3D0' }}>{sandboxReport.stdout}</pre>
                  )}
                  {sandboxReport.stderr && (
                    <pre style={{ margin: '4px 0 0 0', whiteSpace: 'pre-wrap', color: '#FDA4AF' }}>{sandboxReport.stderr}</pre>
                  )}
                </div>
              )}
            </form>
          )}
        </div>

        {/* Section 5c : P5 — Inspecteur de Mémoire Vectorielle (pgvector 768d) */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="info-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Cpu size={13} color="#38BDF8" />
              Mémoire Vectorielle pgvector (P5)
            </span>
            <button
              onClick={() => setShowMemoryP5(!showMemoryP5)}
              className="control-btn"
              style={{
                padding: '2px 8px',
                fontSize: '0.7rem',
                color: '#38BDF8',
                borderColor: 'rgba(56, 189, 248, 0.45)',
              }}
            >
              {showMemoryP5 ? 'Masquer' : 'Explorer Souvenirs'}
            </button>
          </div>

          {showMemoryP5 && (
            <form
              onSubmit={handleSearchMemoryP5}
              style={{
                marginTop: '8px',
                padding: '10px',
                borderRadius: '8px',
                background: 'rgba(56, 189, 248, 0.06)',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', gap: '6px' }}>
                <input
                  type="text"
                  value={memoryQuery}
                  onChange={(e) => setMemoryQuery(e.target.value)}
                  placeholder="Rechercher par similarité cosinus (768d)..."
                  style={{
                    flex: 1,
                    padding: '6px 8px',
                    background: '#060A17',
                    border: '1px solid rgba(56, 189, 248, 0.35)',
                    borderRadius: '6px',
                    color: '#E2E8F0',
                    fontSize: '0.74rem',
                  }}
                />
                <button
                  type="submit"
                  disabled={searchingMemory}
                  className="btn-cyber"
                  style={{ padding: '6px 10px', fontSize: '0.72rem' }}
                >
                  {searchingMemory ? '...' : 'Chercher'}
                </button>
              </div>

              {memoryResults.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '150px', overflowY: 'auto' }}>
                  {memoryResults.map((mem, i) => (
                    <div
                      key={mem.id || i}
                      style={{
                        background: 'rgba(4, 7, 16, 0.92)',
                        borderLeft: '3px solid #38BDF8',
                        padding: '6px 8px',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38BDF8', fontWeight: 700, marginBottom: '2px' }}>
                        <span>[{mem.memory_type || 'EPISODIC'}]</span>
                        {mem.similarity !== undefined && (
                          <span className="mono">{Math.round(mem.similarity * 100)}% cos</span>
                        )}
                      </div>
                      <div style={{ color: '#CBD5E1', lineHeight: 1.35 }}>{mem.content}</div>
                    </div>
                  ))}
                </div>
              )}
            </form>
          )}
        </div>

        {/* Section 5d : P7 — Sentinelle de Veille Proactive & Auto-Audit */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="info-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldAlert size={13} color="#F59E0B" />
              Veille Proactive & Auto-Audit (P7)
            </span>
            <button
              onClick={handleRunProactiveWatchP7}
              disabled={runningWatchP7}
              className="control-btn"
              style={{
                padding: '2px 8px',
                fontSize: '0.7rem',
                color: '#F59E0B',
                borderColor: 'rgba(245, 158, 11, 0.45)',
              }}
            >
              {runningWatchP7 ? 'Audit en cours...' : 'Lancer Audit P7'}
            </button>
          </div>

          {watchReportP7 && (
            <div
              className="mono"
              style={{
                marginTop: '8px',
                background: 'rgba(4, 7, 16, 0.95)',
                borderLeft: `3px solid ${watchReportP7.overall_health === 'OPTIMAL' ? '#10B981' : '#F59E0B'}`,
                padding: '8px',
                borderRadius: '4px',
                fontSize: '0.7rem',
                color: '#E2E8F0',
              }}
            >
              <div style={{ fontWeight: 700, color: watchReportP7.overall_health === 'OPTIMAL' ? '#10B981' : '#F59E0B', marginBottom: '4px' }}>
                ÉTAT ESSAIM : {watchReportP7.overall_health} ({watchReportP7.duration_ms} ms)
              </div>
              {watchReportP7.probes && Object.entries(watchReportP7.probes).map(([k, v]) => (
                <div key={k} style={{ color: '#94A3B8', fontSize: '0.67rem' }}>
                  • <strong style={{ color: '#E2E8F0' }}>{k}</strong> : {v.status}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Section 6 : Empreinte d'exécution & Connecteurs */}
        <div className="info-section">
          <span className="info-section-title">Connecteurs Sandboxed & Capacités</span>
          <div style={{ 
            background: 'rgba(0,0,0,0.35)', 
            padding: '10px 12px', 
            borderRadius: '8px', 
            fontSize: '0.75rem',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '6px',
            border: '1px solid var(--border-subtle)'
          }}>
            {['system.read', 'sandbox.run (P3)', 'agent.send (P2P)', 'memory.vector', 'content.create', 'web.search', 'fs.write'].map((tool) => (
              <span
                key={tool}
                className="mono"
                style={{
                  padding: '2px 7px',
                  borderRadius: '4px',
                  background: tool.includes('P2P') || tool.includes('vector') ? 'rgba(236, 72, 153, 0.14)' : 'rgba(0, 240, 255, 0.08)',
                  border: `1px solid ${tool.includes('P2P') || tool.includes('vector') ? 'rgba(236, 72, 153, 0.45)' : 'rgba(0, 240, 255, 0.25)'}`,
                  color: tool.includes('P2P') || tool.includes('vector') ? '#F472B6' : 'var(--neon-cyan)',
                  fontSize: '0.7rem',
                }}
              >
                {tool}
              </span>
            ))}
            <span className="mono" style={{ color: 'var(--neon-emerald)', marginLeft: 'auto', fontSize: '0.72rem' }}>
              Zero-Spend Guard
            </span>
          </div>
        </div>

        {/* Section 7 : Journal d'Audit & Logs de l'Agent */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="info-section-title">
              Journal d'Audit & Logs ({logs.length})
            </span>
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="control-btn"
              style={{ padding: '3px 8px', fontSize: '0.72rem', color: 'var(--neon-cyan)', display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              <FileText size={12} />
              {showLogs ? 'Masquer' : 'Afficher'}
            </button>
          </div>

          {showLogs && (
            <div style={{
              background: '#040711',
              border: '1px solid rgba(0, 240, 255, 0.2)',
              borderRadius: '6px',
              padding: '8px',
              maxHeight: '190px',
              overflowY: 'auto',
              marginTop: '6px',
              fontFamily: 'monospace',
              fontSize: '0.72rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}>
              {loadingLogs && <div style={{ color: '#64748B' }}>Chargement des logs de l'agent...</div>}
              {!loadingLogs && logs.length === 0 && <div style={{ color: '#64748B' }}>Aucun log enregistré pour cet agent.</div>}
              {!loadingLogs && logs.map((log) => {
                const badgeColor =
                  log.type === 'p2p_dialogue' ? '#EC4899' :
                  log.level === 'ALLOW' || log.level === 'SUCCESS' ? '#10B981' :
                  log.level === 'DENY' || log.level === 'CRITICAL' ? '#F43F5E' :
                  log.level === 'ESCALATE' || log.level === 'WARNING' ? '#F59E0B' : '#00F0FF';
                return (
                  <div key={log.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '5px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', color: badgeColor, fontWeight: 'bold' }}>
                      <span>[{log.type.toUpperCase()}] {log.title}</span>
                      <span style={{ color: '#64748B', fontSize: '0.65rem' }}>{new Date(log.timestamp).toLocaleTimeString('fr-FR')}</span>
                    </div>
                    <div style={{ color: '#CBD5E1', marginTop: '2px', wordBreak: 'break-word', fontSize: '0.70rem' }}>
                      {log.summary}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Pied de carte avec actions */}
      <div className="card-footer">
        {activeGoal && (
          <button 
            onClick={() => onWakeGoal(activeGoal.id)}
            disabled={isWaking}
            className="btn-cyber primary"
            style={{ flex: 1, justifyContent: 'center' }}
          >
            <Play size={16} />
            {isWaking ? "Exécution..." : "Wake (1 pas)"}
          </button>
        )}

        {onOpenCreateGoal && (
          <button
            onClick={() => onOpenCreateGoal(agent.id)}
            className="btn-cyber secondary"
            style={{ padding: '8px 12px', borderColor: 'rgba(0, 240, 255, 0.35)' }}
            title="Assigner une nouvelle mission DAG à cet agent"
          >
            + Mission
          </button>
        )}

        <button 
          onClick={() => onSpawnSubAgent(agent.id)}
          className="btn-cyber accent-purple"
          style={{ padding: '8px 12px' }}
          title="Créer un sous-agent relié"
        >
          <GitFork size={16} />
          + Sous-Agent
        </button>
      </div>
    </div>
  );
}
