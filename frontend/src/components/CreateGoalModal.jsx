import React, { useState, useEffect } from 'react';
import { Target, Plus, Trash2, X, Sparkles, Layers } from 'lucide-react';

export default function CreateGoalModal({
  isOpen,
  onClose,
  agents = [],
  defaultAgentId = null,
  onCreateGoal,
}) {
  const [agentId, setAgentId] = useState(defaultAgentId || '');
  const [objective, setObjective] = useState('');
  const [priority, setPriority] = useState(1);
  const [autonomyLevel, setAutonomyLevel] = useState(3);
  const [tasks, setTasks] = useState([
    'Analyse du périmètre et diagnostic initial (system.read)',
    'Exécution et synthèse structurée du livrable',
  ]);
  const [newTaskText, setNewTaskText] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (defaultAgentId) {
        setAgentId(defaultAgentId);
      } else if (agents.length > 0 && !agentId) {
        setAgentId(agents[0].id);
      }
    }
  }, [isOpen, defaultAgentId, agents, agentId]);

  if (!isOpen) return null;

  const handleAddTask = () => {
    const trimmed = newTaskText.trim();
    if (!trimmed) return;
    setTasks([...tasks, trimmed]);
    setNewTaskText('');
  };

  const handleRemoveTask = (idx) => {
    setTasks(tasks.filter((_, i) => i !== idx));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!objective.trim() || !agentId) return;

    setLoading(true);
    try {
      await onCreateGoal({
        agent_id: agentId,
        objective: objective.trim(),
        priority: Number(priority),
        requested_autonomy_level: Number(autonomyLevel),
        initial_tasks: tasks.filter((t) => t.trim().length > 0),
      });
      setObjective('');
      onClose();
    } catch (err) {
      console.error('Erreur création objectif:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-window"
        style={{ maxWidth: '580px', width: '92%' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '34px',
                height: '34px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, var(--neon-cyan), var(--neon-purple))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Target size={18} color="#FFFFFF" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.05rem', color: '#FFFFFF', margin: 0 }}>
                Assigner une Nouvelle Mission DAG
              </h3>
              <p style={{ fontSize: '0.74rem', color: 'var(--text-muted)', margin: 0 }}>
                Planification séquentielle de tâches sous gouvernance déterministe
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="control-btn"
            style={{ padding: '6px', borderRadius: '50%' }}
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>AGENT RESPONSABLE</label>
              <select
                className="form-select"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                required
              >
                {agents.map((ag) => (
                  <option key={ag.id} value={ag.id}>
                    {ag.name} ({ag.role || 'Agent'}) — Autonomie max {ag.default_autonomy_level}/5
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>OBJECTIF DE LA MISSION</label>
              <textarea
                className="form-input"
                rows="2"
                placeholder="Ex: Rédiger un script vidéo promotionnel ou effectuer un diagnostic système..."
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <label>NIVEAU D'AUTONOMIE REQUIS</label>
                  <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--neon-emerald)' }}>
                    {autonomyLevel} / 5
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="5"
                  step="1"
                  value={autonomyLevel}
                  onChange={(e) => setAutonomyLevel(e.target.value)}
                  style={{ accentColor: 'var(--neon-cyan)', cursor: 'pointer', marginTop: '6px' }}
                />
              </div>

              <div className="form-group">
                <label>PRIORITÉ D'EXÉCUTION (1-100)</label>
                <input
                  type="number"
                  min="1"
                  max="100"
                  className="form-input"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Layers size={13} color="var(--neon-purple)" />
                <span>TÂCHES INITIALES DU GRAPHE DAG ({tasks.length})</span>
              </label>

              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Ajouter une étape au DAG..."
                  value={newTaskText}
                  onChange={(e) => setNewTaskText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddTask();
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={handleAddTask}
                  className="btn-cyber secondary"
                  style={{ padding: '0 12px' }}
                >
                  <Plus size={15} />
                </button>
              </div>

              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  maxHeight: '150px',
                  overflowY: 'auto',
                }}
              >
                {tasks.map((t, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      background: 'rgba(0, 0, 0, 0.35)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '6px',
                      padding: '6px 10px',
                      fontSize: '0.8rem',
                    }}
                  >
                    <span>
                      <strong className="mono" style={{ color: 'var(--neon-cyan)', marginRight: '8px' }}>
                        #{idx + 1}
                      </strong>
                      {t}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleRemoveTask(idx)}
                      className="control-btn"
                      style={{ padding: '3px', color: '#F43F5E' }}
                      title="Retirer cette tâche"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" onClick={onClose} className="btn-cyber secondary">
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading || !objective.trim()}
              className="btn-cyber primary"
            >
              <Sparkles size={15} />
              <span>{loading ? 'Création du DAG...' : 'Lancer la Mission DAG'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
