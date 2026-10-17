import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  ShieldOff,
  Scale,
  Plus,
  RefreshCw,
  X,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Send,
  Filter,
} from 'lucide-react';
import { authFetch } from '../lib/authFetch';

const OUTCOME_STYLES = {
  ALLOW: {
    color: '#10B981',
    bg: 'rgba(16, 185, 129, 0.12)',
    border: 'rgba(16, 185, 129, 0.35)',
    Icon: ShieldCheck,
    label: 'AUTORISÉ (ALLOW)',
  },
  ESCALATE: {
    color: '#F59E0B',
    bg: 'rgba(245, 158, 11, 0.12)',
    border: 'rgba(245, 158, 11, 0.35)',
    Icon: ShieldAlert,
    label: 'ESCALADÉ (APPROBATION REQUISE)',
  },
  BLOCK: {
    color: '#F43F5E',
    bg: 'rgba(244, 63, 94, 0.12)',
    border: 'rgba(244, 63, 94, 0.35)',
    Icon: ShieldOff,
    label: 'BLOQUÉ (DENY)',
  },
  DENY: {
    color: '#F43F5E',
    bg: 'rgba(244, 63, 94, 0.12)',
    border: 'rgba(244, 63, 94, 0.35)',
    Icon: ShieldOff,
    label: 'BLOQUÉ (DENY)',
  },
};

const RISK_COLORS = {
  low: '#10B981',
  medium: '#00F0FF',
  high: '#F59E0B',
  critical: '#F43F5E',
};

export default function GovernancePanel({
  isOpen,
  onClose,
  agents = [],
  workspaceId,
  onNotify,
}) {
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [outcomeFilter, setOutcomeFilter] = useState('ALL');
  const [showSimulator, setShowSimulator] = useState(false);

  // Simulator form state
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [objective, setObjective] = useState('Maintenance et diagnostic du système');
  const [situation, setSituation] = useState('Exécution nominale en environnement de production');
  const [proposedAction, setProposedAction] = useState('Lire les métriques système via system.read');
  const [autonomyLevel, setAutonomyLevel] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch('/api/v1/decisions/?limit=50');
      if (res.ok) {
        const data = await res.json();
        setDecisions(data);
      }
    } catch (err) {
      console.warn('Erreur chargement des décisions:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchDecisions();
      if (agents.length > 0 && !selectedAgentId) {
        setSelectedAgentId(agents[0].id);
      }
    }
  }, [isOpen, agents, selectedAgentId, fetchDecisions]);

  if (!isOpen) return null;

  const handleSimulateDecision = async (e) => {
    e.preventDefault();
    const targetAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
    if (!targetAgent) {
      onNotify?.('Veuillez d’abord déployer un agent.', 'warning');
      return;
    }

    setSubmitting(true);
    setLastResult(null);
    try {
      const res = await authFetch('/api/v1/decisions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: targetAgent.workspace_id || workspaceId,
          agent_id: targetAgent.id,
          objective: objective.trim(),
          situation: situation.trim(),
          proposed_action: proposedAction.trim(),
          requested_autonomy_level: Number(autonomyLevel),
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setLastResult(data);
        onNotify?.(
          `Arbitrage terminé : ${data.control_outcome} (${data.control_reason})`,
          data.control_outcome === 'ALLOW' ? 'success' : 'warning'
        );
        await fetchDecisions();
      } else {
        const err = await res.json().catch(() => ({}));
        onNotify?.(err.detail || 'Erreur lors de la soumission de la décision.', 'error');
      }
    } catch (err) {
      onNotify?.('Erreur réseau lors de la soumission à l’Arbitrateur.', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const filteredDecisions = decisions.filter((d) => {
    if (outcomeFilter === 'ALL') return true;
    return d.control_outcome === outcomeFilter;
  });

  const allowCount = decisions.filter((d) => d.control_outcome === 'ALLOW').length;
  const escalateCount = decisions.filter((d) => d.control_outcome === 'ESCALATE').length;
  const blockCount = decisions.filter(
    (d) => d.control_outcome === 'BLOCK' || d.control_outcome === 'DENY'
  ).length;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-window"
        style={{ maxWidth: '820px', width: '94%', maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(0, 240, 255, 0.25))',
                border: '1px solid var(--neon-cyan)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Scale size={20} color="var(--neon-cyan)" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', color: '#FFFFFF', margin: 0 }}>
                Centre d'Arbitrage Déterministe & Gouvernance
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
                Registre d'audit des décisions IA · Évaluation de risque & autonomie multi-tenant
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => setShowSimulator(!showSimulator)}
              className={`btn-cyber ${showSimulator ? 'primary' : 'accent-purple'}`}
              style={{ padding: '6px 12px', fontSize: '0.78rem' }}
            >
              <Plus size={14} />
              <span>{showSimulator ? 'Fermer le Simulateur' : 'Tester un Arbitrage'}</span>
            </button>
            <button
              onClick={fetchDecisions}
              className="control-btn"
              title="Rafraîchir les décisions"
              style={{ padding: '6px' }}
            >
              <RefreshCw size={15} className={loading ? 'spin' : ''} />
            </button>
            <button
              onClick={onClose}
              className="control-btn"
              style={{ padding: '6px', borderRadius: '50%' }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="modal-body" style={{ overflowY: 'auto', flex: 1 }}>
          {/* Summary Bar */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '10px',
              marginBottom: '16px',
            }}
          >
            <div
              onClick={() => setOutcomeFilter('ALL')}
              style={{
                background: outcomeFilter === 'ALL' ? 'rgba(0, 240, 255, 0.12)' : 'rgba(0,0,0,0.3)',
                border: `1px solid ${outcomeFilter === 'ALL' ? 'var(--neon-cyan)' : 'var(--border-subtle)'}`,
                borderRadius: '8px',
                padding: '10px 12px',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>TOTAL DÉCISIONS</div>
              <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: '#FFF' }}>
                {decisions.length}
              </div>
            </div>

            <div
              onClick={() => setOutcomeFilter('ALLOW')}
              style={{
                background: outcomeFilter === 'ALLOW' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(0,0,0,0.3)',
                border: `1px solid ${outcomeFilter === 'ALLOW' ? '#10B981' : 'var(--border-subtle)'}`,
                borderRadius: '8px',
                padding: '10px 12px',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontSize: '0.68rem', color: '#10B981' }}>AUTORISÉES (ALLOW)</div>
              <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: '#10B981' }}>
                {allowCount}
              </div>
            </div>

            <div
              onClick={() => setOutcomeFilter('ESCALATE')}
              style={{
                background: outcomeFilter === 'ESCALATE' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(0,0,0,0.3)',
                border: `1px solid ${outcomeFilter === 'ESCALATE' ? '#F59E0B' : 'var(--border-subtle)'}`,
                borderRadius: '8px',
                padding: '10px 12px',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontSize: '0.68rem', color: '#F59E0B' }}>ESCALADÉES</div>
              <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: '#F59E0B' }}>
                {escalateCount}
              </div>
            </div>

            <div
              onClick={() => setOutcomeFilter('BLOCK')}
              style={{
                background: outcomeFilter === 'BLOCK' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(0,0,0,0.3)',
                border: `1px solid ${outcomeFilter === 'BLOCK' ? '#F43F5E' : 'var(--border-subtle)'}`,
                borderRadius: '8px',
                padding: '10px 12px',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontSize: '0.68rem', color: '#F43F5E' }}>BLOQUÉES</div>
              <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: '#F43F5E' }}>
                {blockCount}
              </div>
            </div>
          </div>

          {/* Interactive Arbitrator Simulator */}
          {showSimulator && (
            <form
              onSubmit={handleSimulateDecision}
              style={{
                background: 'rgba(13, 19, 36, 0.9)',
                border: '1px solid var(--neon-cyan)',
                borderRadius: '10px',
                padding: '16px',
                marginBottom: '18px',
                boxShadow: '0 0 24px rgba(0, 240, 255, 0.12)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '12px',
                }}
              >
                <strong style={{ color: 'var(--neon-cyan)', fontSize: '0.85rem' }}>
                  ⚡ SOUMETTRE UNE INTENTION À L'ARBITRATEUR DÉTERMINISTE
                </strong>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    type="button"
                    className="control-btn"
                    style={{ fontSize: '0.68rem', padding: '3px 8px' }}
                    onClick={() => {
                      setObjective('Diagnostic de santé du système');
                      setProposedAction('Lire les journaux système via system.read');
                      setAutonomyLevel(3);
                    }}
                  >
                    Preset : Lecture Sûre
                  </button>
                  <button
                    type="button"
                    className="control-btn"
                    style={{ fontSize: '0.68rem', padding: '3px 8px', color: '#10B981' }}
                    onClick={() => {
                      setObjective('Production éditoriale');
                      setProposedAction('Rédige un script vidéo promotionnel pour le produit');
                      setAutonomyLevel(3);
                    }}
                  >
                    Preset : Content Create
                  </button>
                  <button
                    type="button"
                    className="control-btn"
                    style={{ fontSize: '0.68rem', padding: '3px 8px', color: '#F59E0B' }}
                    onClick={() => {
                      setObjective('Campagne sponsorisée');
                      setProposedAction('Lancer un achat publicitaire sponsorisé de 500 EUR');
                      setAutonomyLevel(4);
                    }}
                  >
                    Preset : Finance Spend (Escalade)
                  </button>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group" style={{ marginBottom: '8px' }}>
                  <label>AGENT DEMANDEUR</label>
                  <select
                    className="form-select"
                    value={selectedAgentId}
                    onChange={(e) => setSelectedAgentId(e.target.value)}
                  >
                    {agents.map((ag) => (
                      <option key={ag.id} value={ag.id}>
                        {ag.name} (Autonomie {ag.default_autonomy_level}/5)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group" style={{ marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <label>AUTONOMIE REQUISE</label>
                    <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--neon-cyan)' }}>
                      Niveau {autonomyLevel} / 5
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="5"
                    value={autonomyLevel}
                    onChange={(e) => setAutonomyLevel(e.target.value)}
                    style={{ accentColor: 'var(--neon-cyan)', width: '100%', marginTop: '6px' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group" style={{ marginBottom: '8px' }}>
                  <label>OBJECTIF</label>
                  <input
                    type="text"
                    className="form-input"
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group" style={{ marginBottom: '8px' }}>
                  <label>SITUATION CONTEXTUELLE</label>
                  <input
                    type="text"
                    className="form-input"
                    value={situation}
                    onChange={(e) => setSituation(e.target.value)}
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label>ACTION PROPOSÉE (INTENTION ANALYSÉE PAR LE DOMAIN CLASSIFIER)</label>
                <input
                  type="text"
                  className="form-input"
                  value={proposedAction}
                  onChange={(e) => setProposedAction(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', alignItems: 'center' }}>
                <button type="submit" disabled={submitting} className="btn-cyber primary">
                  <Send size={14} />
                  <span>{submitting ? 'Arbitrage en cours...' : 'Exécuter l’Arbitrage'}</span>
                </button>
              </div>

              {lastResult && (
                <div
                  style={{
                    marginTop: '12px',
                    padding: '12px',
                    borderRadius: '8px',
                    background: 'rgba(0,0,0,0.45)',
                    border: `1px solid ${
                      OUTCOME_STYLES[lastResult.control_outcome]?.color || 'var(--neon-cyan)'
                    }`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong
                      style={{
                        color: OUTCOME_STYLES[lastResult.control_outcome]?.color || '#FFF',
                        fontSize: '0.85rem',
                      }}
                    >
                      Verdict : {lastResult.control_outcome} — {lastResult.control_reason}
                    </strong>
                    <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Risque: {lastResult.risk_level?.toUpperCase()} | Source: {lastResult.dominant_source}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Action retenue : <code className="mono">{lastResult.final_action}</code>
                  </div>
                </div>
              )}
            </form>
          )}

          {/* Decisions Table / List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {filteredDecisions.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '36px 20px',
                  color: 'var(--text-muted)',
                  fontSize: '0.85rem',
                }}
              >
                {loading
                  ? 'Chargement du registre des décisions...'
                  : 'Aucune décision enregistrée pour ce filtre. Cliquez sur "Tester un Arbitrage" ou "Wake" pour générer des décisions.'}
              </div>
            ) : (
              filteredDecisions.map((dec) => {
                const style = OUTCOME_STYLES[dec.control_outcome] || OUTCOME_STYLES.ESCALATE;
                const OutcomeIcon = style.Icon;
                const riskColor = RISK_COLORS[dec.risk_level?.toLowerCase()] || '#94A3B8';

                return (
                  <div
                    key={dec.decision_id}
                    style={{
                      background: 'rgba(13, 19, 36, 0.65)',
                      border: `1px solid ${style.border}`,
                      borderRadius: '8px',
                      padding: '12px 14px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <OutcomeIcon size={16} color={style.color} />
                        <span
                          className="mono"
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            color: style.color,
                            padding: '2px 8px',
                            borderRadius: '4px',
                            background: style.bg,
                          }}
                        >
                          {dec.control_outcome}
                        </span>
                        <span
                          className="mono"
                          style={{
                            fontSize: '0.72rem',
                            color: 'var(--text-secondary)',
                            background: 'rgba(255,255,255,0.05)',
                            padding: '2px 7px',
                            borderRadius: '4px',
                          }}
                        >
                          {dec.control_reason}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          className="mono"
                          style={{
                            fontSize: '0.68rem',
                            color: riskColor,
                            border: `1px solid ${riskColor}55`,
                            padding: '1px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          RISQUE : {(dec.risk_level || 'unknown').toUpperCase()}
                        </span>
                        {dec.approval_required && (
                          <span
                            style={{
                              fontSize: '0.68rem',
                              color: '#F59E0B',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            <Lock size={11} /> Approbation Humaine
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ fontSize: '0.83rem', color: '#F8FAFC', fontWeight: 500 }}>
                      {dec.final_action}
                    </div>

                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontSize: '0.7rem',
                        color: 'var(--text-muted)',
                      }}
                    >
                      <span className="mono">ID: {dec.decision_id?.slice(0, 12)}...</span>
                      <span>
                        Source dominante : <strong style={{ color: 'var(--neon-cyan)' }}>{dec.dominant_source}</strong>
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
