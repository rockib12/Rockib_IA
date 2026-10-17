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
  FileText
} from 'lucide-react';
import { authFetch } from '../lib/authFetch';

/**
 * AgentActivityCard — Carte holographique affichant en direct
 * ce que fait l'agent sélectionné (pensée, tâche active, sécurité, sous-agents).
 */
export default function AgentActivityCard({
  agent,
  parentAgent,
  subAgents = [],
  activeGoal,
  onClose,
  onWakeGoal,
  onSpawnSubAgent,
  onSelectAgent,
  isWaking = false,
}) {
  if (!agent) return null;

  const isOrchestrator = !agent.parent_agent_id;
  const statusClass = (agent.current_status || 'ready').toLowerCase();

  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  useEffect(() => {
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
  }, [agent?.id]);

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

        {/* Section 4 : Sous-agents créés par cet agent */}
        <div className="info-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="info-section-title">
              Sous-Agents déployés ({subAgents.length})
            </span>
            <button
              onClick={() => onSpawnSubAgent(agent.id)}
              className="control-btn"
              style={{ padding: '2px 8px', fontSize: '0.7rem', color: 'var(--neon-purple)' }}
            >
              + Déployer
            </button>
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

        {/* Section 5 : Empreinte d'exécution & Handlers */}
        <div className="info-section">
          <span className="info-section-title">Capacités & Diagnostic</span>
          <div style={{ 
            background: 'rgba(0,0,0,0.35)', 
            padding: '10px 12px', 
            borderRadius: '8px', 
            fontSize: '0.78rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Terminal size={14} color="var(--neon-emerald)" />
              <span>Handler actif : <code className="mono" style={{ color: 'var(--neon-cyan)' }}>system.read</code></span>
            </div>
            <span className="mono" style={{ color: 'var(--neon-emerald)' }}>0.0 credits</span>
          </div>
        </div>

        {/* Section 6 : Journal d'Audit & Logs de l'Agent */}
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
            {isWaking ? "Exécution en cours..." : "Wake & Execute (1 pas)"}
          </button>
        )}

        <button 
          onClick={() => onSpawnSubAgent(agent.id)}
          className="btn-cyber accent-purple"
          style={{ padding: '8px 14px' }}
          title="Créer un sous-agent relié"
        >
          <GitFork size={16} />
          + Sous-Agent
        </button>
      </div>
    </div>
  );
}
