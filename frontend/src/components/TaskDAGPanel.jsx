import React, { useState } from 'react';
import { 
  GitCommit, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  Play, 
  ShieldAlert, 
  Terminal, 
  ListFilter 
} from 'lucide-react';

export default function TaskDAGPanel({
  goals = [],
  selectedGoalId,
  onSelectGoal,
  goalDetails,
  telemetry = [],
  onWakeGoal,
  isWaking = false,
}) {
  const [activeTab, setActiveTab] = useState('dag'); // 'dag' | 'telemetry'

  const activeGoal = goals.find((g) => g.id === selectedGoalId) || goals[0];
  const tasks = goalDetails?.tasks || [];

  return (
    <aside className="tactical-sidebar">
      {/* Navigation Tabs */}
      <div className="sidebar-tabs">
        <button
          className={`tab-btn ${activeTab === 'dag' ? 'active' : ''}`}
          onClick={() => setActiveTab('dag')}
        >
          Graphe de Tâches (DAG)
        </button>
        <button
          className={`tab-btn ${activeTab === 'telemetry' ? 'active' : ''}`}
          onClick={() => setActiveTab('telemetry')}
        >
          Télémetrie & Logs ({telemetry.length})
        </button>
      </div>

      <div className="sidebar-content">
        {activeTab === 'dag' ? (
          <>
            {/* Goal Selector Dropdown */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700 }}>
                OBJECTIF EN COURS D'INSPECTION
              </span>
              <select
                className="form-select"
                value={selectedGoalId || ''}
                onChange={(e) => onSelectGoal(e.target.value)}
              >
                {goals.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.agent_name} — {g.objective.slice(0, 45)}... ({g.status})
                  </option>
                ))}
              </select>
            </div>

            {/* Goal Summary Card */}
            {activeGoal && (
              <div style={{ 
                background: 'rgba(255,255,255,0.03)', 
                border: '1px solid var(--border-subtle)', 
                borderRadius: '12px', 
                padding: '14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--neon-cyan)' }}>
                    {activeGoal.agent_name}
                  </span>
                  <span className={`status-badge ${activeGoal.status.toLowerCase()}`}>
                    {activeGoal.status}
                  </span>
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {activeGoal.objective}
                </p>

                <div style={{ display: 'flex', gap: '10px', marginTop: '6px' }}>
                  <button
                    onClick={() => onWakeGoal(activeGoal.id)}
                    disabled={isWaking}
                    className="btn-cyber primary"
                    style={{ width: '100%', justifyContent: 'center', padding: '6px 12px', fontSize: '0.8rem' }}
                  >
                    <Play size={14} />
                    {isWaking ? "Exécution..." : "Avancer d'un pas (Wake)"}
                  </button>
                </div>
              </div>
            )}

            {/* Task DAG List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700 }}>
                SÉQUENCE D'EXÉCUTION DES TÂCHES ({tasks.length})
              </span>

              {tasks.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  Aucune tâche disponible pour cet objectif.
                </div>
              ) : (
                tasks.map((task, idx) => {
                  const isCompleted = task.status === 'COMPLETED';
                  const isRunning = task.status === 'RUNNING';
                  const isReady = task.status === 'READY';
                  const isBlocked = task.status === 'BLOCKED';

                  return (
                    <div 
                      key={task.id} 
                      className={`task-dag-card ${isRunning ? 'running' : ''}`}
                    >
                      <div className="task-header">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span className="mono" style={{ 
                            fontSize: '0.75rem', 
                            color: 'var(--text-muted)',
                            background: 'rgba(255,255,255,0.06)',
                            padding: '2px 6px',
                            borderRadius: '4px'
                          }}>
                            #{idx + 1}
                          </span>
                          {isCompleted ? (
                            <CheckCircle2 size={16} color="var(--neon-emerald)" />
                          ) : isRunning ? (
                            <Clock size={16} color="var(--neon-cyan)" />
                          ) : isBlocked ? (
                            <AlertCircle size={16} color="var(--neon-rose)" />
                          ) : (
                            <GitCommit size={16} color="var(--text-muted)" />
                          )}
                        </div>

                        <span className={`status-badge ${task.status.toLowerCase()}`} style={{ fontSize: '0.65rem' }}>
                          {task.status}
                        </span>
                      </div>

                      <div className="task-desc">
                        {task.description}
                      </div>

                      {task.decision_id && (
                        <div className="mono" style={{ fontSize: '0.7rem', color: 'var(--neon-indigo)' }}>
                          Décision liée : {task.decision_id.slice(0, 8)}...
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </>
        ) : (
          /* Telemetry & Audit Stream */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700 }}>
              FLUX D'ARBITRAGE ET D'EXÉCUTION EN TEMPS RÉEL
            </span>

            {telemetry.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Aucun événement de télémétrie récent.
              </div>
            ) : (
              telemetry.map((item) => (
                <div 
                  key={item.id}
                  style={{
                    background: 'rgba(0,0,0,0.35)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '10px',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {item.type === 'decision' ? (
                        <ShieldAlert size={14} color="var(--neon-amber)" />
                      ) : (
                        <Terminal size={14} color="var(--neon-emerald)" />
                      )}
                      <strong style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>
                        {item.agent_name}
                      </strong>
                    </div>
                    <span className="mono" style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </span>
                  </div>

                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                    {item.summary}
                  </p>

                  {item.details?.fingerprint && (
                    <div className="mono" style={{ fontSize: '0.68rem', color: 'var(--neon-cyan)' }}>
                      SHA-256 : {item.details.fingerprint}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
