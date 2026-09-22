import React, { useState } from 'react';
import { Bot, Sparkles, X, GitFork, Shield } from 'lucide-react';

export default function SpawnAgentModal({
  isOpen,
  onClose,
  parentAgentId,
  agents = [],
  onSpawn,
}) {
  const [name, setName] = useState('');
  const [role, setRole] = useState('Worker Spécialisé');
  const [selectedParentId, setSelectedParentId] = useState(parentAgentId || '');
  const [autonomyLevel, setAutonomyLevel] = useState(2);
  const [mission, setMission] = useState('');
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    try {
      await onSpawn({
        name: name.trim(),
        role: role.trim(),
        parent_agent_id: selectedParentId || null,
        default_autonomy_level: Number(autonomyLevel),
        mission: mission.trim(),
      });
      setName('');
      setMission('');
      onClose();
    } catch (err) {
      console.error("Erreur spawn agent:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-window" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ 
              width: '34px', 
              height: '34px', 
              borderRadius: '8px', 
              background: 'linear-gradient(135deg, var(--neon-purple), var(--neon-cyan))',
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center' 
            }}>
              <Sparkles size={18} color="#FFFFFF" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', color: '#FFFFFF' }}>
                Matérialiser un Nouvel Agent 3D
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Déploiement procédural dans la constellation spatiale
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

        {/* Modal Form */}
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label>NOM DE L'AGENT CYBERNÉTIQUE</label>
              <input 
                type="text"
                className="form-input"
                placeholder="Ex: Diagnostic Sentinel Alpha"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div className="form-group">
                <label>RÔLE DE L'AGENT</label>
                <select 
                  className="form-select"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  <option value="Worker Spécialisé">Worker Spécialisé</option>
                  <option value="Security Sentinel">Sentinelle de Sécurité</option>
                  <option value="Cognitive Analyst">Analyste Cognitif</option>
                  <option value="System Scout">Scout Système</option>
                  <option value="Sub-Orchestrator">Sous-Orchestrateur</option>
                </select>
              </div>

              <div className="form-group">
                <label>AGENT PARENT (CRÉATEUR)</label>
                <select 
                  className="form-select"
                  value={selectedParentId}
                  onChange={(e) => setSelectedParentId(e.target.value)}
                >
                  <option value="">Aucun (Agent Racine)</option>
                  {agents.map((ag) => (
                    <option key={ag.id} value={ag.id}>
                      {ag.name} ({ag.role || 'Agent'})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-group">
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <label>NIVEAU D'AUTONOMIE ATTRIBUÉ</label>
                <span className="mono" style={{ fontSize: '0.8rem', color: 'var(--neon-emerald)' }}>
                  Niveau {autonomyLevel} / 5
                </span>
              </div>
              <input 
                type="range"
                min="0"
                max="5"
                step="1"
                value={autonomyLevel}
                onChange={(e) => setAutonomyLevel(e.target.value)}
                style={{ accentColor: 'var(--neon-cyan)', cursor: 'pointer', height: '6px' }}
              />
            </div>

            <div className="form-group">
              <label>OBJECTIF / MISSION ASSIGNÉE (INITIAL GOAL)</label>
              <textarea 
                className="form-input"
                rows="3"
                placeholder="Ex: Effectuer un audit de télémétrie système via system.read"
                value={mission}
                onChange={(e) => setMission(e.target.value)}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button 
              type="button" 
              onClick={onClose}
              className="btn-cyber secondary"
            >
              Annuler
            </button>
            <button 
              type="submit" 
              disabled={loading || !name.trim()}
              className="btn-cyber primary"
            >
              <Sparkles size={15} />
              <span>{loading ? "Déploiement 3D..." : "Faire Émerger dans l'Espace 3D"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
