import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  Cpu,
  Coins,
  Clock,
  Sparkles,
  RefreshCw,
  X,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  ShieldCheck,
  Download,
  ExternalLink,
  MessageSquare,
  PhoneCall,
  Check,
  Send,
  Layers,
  Database,
  Lock,
} from 'lucide-react';
import { authFetch } from '../lib/authFetch';

export default function ObservabilityPanel({
  isOpen,
  onClose,
  workspaceId = "00000000-0000-0000-0000-000000000001",
  onNotify = () => {},
}) {
  const [activeTab, setActiveTab] = useState('telemetry'); // 'telemetry' | 'budgets' | 'leads'
  const [loading, setLoading] = useState(false);

  // Données Télémétrie Groq
  const [metrics, setMetrics] = useState(null);
  const [traces, setTraces] = useState([]);
  const [tunnelStatus, setTunnelStatus] = useState(null);

  // Données Budgets & Réservations
  const [budgets, setBudgets] = useState([]);
  const [reservations, setReservations] = useState([]);

  // Données CRM Leads
  const [leads, setLeads] = useState([]);
  const [selectedSiteKey, setSelectedSiteKey] = useState('default_portfolio');

  // Benchmark Qualité
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState(null);

  // Réconciliation formelle
  const [reconcilingId, setReconcilingId] = useState(null);
  const [reconcileEvidence, setReconcileEvidence] = useState('');

  // 1. Charger la télémétrie LLM & Traces
  const fetchTelemetryData = useCallback(async () => {
    try {
      setLoading(true);
      const [metricsRes, tracesRes, tunnelRes] = await Promise.all([
        authFetch('/api/v1/inbound/metrics'),
        authFetch('/api/v1/inbound/traces?limit=30'),
        fetch('/api/v1/inbound/tunnel/status'),
      ]);

      if (metricsRes.ok) {
        setMetrics(await metricsRes.json());
      }
      if (tracesRes.ok) {
        setTraces(await tracesRes.json());
      }
      if (tunnelRes.ok) {
        setTunnelStatus(await tunnelRes.json());
      }
    } catch (err) {
      console.warn("Erreur chargement télémétrie:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // 2. Charger les budgets & réservations PostgreSQL
  const fetchBudgetsData = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setLoading(true);
      const [budgetsRes, resRes] = await Promise.all([
        authFetch(`/api/v1/execution/budgets?workspace_id=${workspaceId}`),
        authFetch(`/api/v1/execution/reservations?workspace_id=${workspaceId}&limit=25`),
      ]);

      if (budgetsRes.ok) {
        setBudgets(await budgetsRes.json());
      }
      if (resRes.ok) {
        setReservations(await resRes.json());
      }
    } catch (err) {
      console.warn("Erreur chargement budgets:", err);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  // 3. Charger les leads CRM
  const fetchLeadsData = useCallback(async () => {
    if (!selectedSiteKey) return;
    try {
      setLoading(true);
      const res = await authFetch(`/api/v1/inbound/sites/${selectedSiteKey}/leads`);
      if (res.ok) {
        setLeads(await res.json());
      }
    } catch (err) {
      console.warn("Erreur chargement leads:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedSiteKey]);

  // Chargement contextuel selon l'onglet actif
  useEffect(() => {
    if (!isOpen) return;
    if (activeTab === 'telemetry') {
      fetchTelemetryData();
    } else if (activeTab === 'budgets') {
      fetchBudgetsData();
    } else if (activeTab === 'leads') {
      fetchLeadsData();
    }
  }, [isOpen, activeTab, fetchTelemetryData, fetchBudgetsData, fetchLeadsData]);

  // Lancer le Benchmark de Référence
  const handleRunBenchmark = async () => {
    try {
      setBenchmarkLoading(true);
      onNotify("Exécution de la Golden Benchmark Suite (6 scénarios)...", "info");
      const res = await authFetch('/api/v1/inbound/benchmark/run', {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setBenchmarkResult(data);
        onNotify(`Benchmark terminé ! Score global : ${data.global_score}/100`, "success");
      } else {
        onNotify("Échec de l'exécution du benchmark", "error");
      }
    } catch (err) {
      onNotify(`Erreur benchmark: ${err.message}`, "error");
    } finally {
      setBenchmarkLoading(false);
    }
  };

  // Mettre à jour le statut d'un lead
  const handleUpdateLeadStatus = async (leadId, newStatus) => {
    try {
      const res = await authFetch(`/api/v1/inbound/sites/${selectedSiteKey}/leads/${leadId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        onNotify(`Statut mis à jour : ${newStatus}`, 'success');
        fetchLeadsData();
      } else {
        onNotify("Erreur lors de la mise à jour du statut", "error");
      }
    } catch (err) {
      onNotify(`Erreur: ${err.message}`, 'error');
    }
  };

  // Réconcilier une tentative
  const handleReconcileAttempt = async (attemptId, resolvedEffect) => {
    if (!reconcileEvidence.trim()) {
      onNotify("Une référence de preuve est obligatoire pour réconcilier", "error");
      return;
    }
    try {
      const res = await authFetch('/api/v1/execution/reconcile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          attempt_id: attemptId,
          resolved_effect: resolvedEffect,
          evidence_reference: reconcileEvidence,
          settle_reservation: true,
        }),
      });
      if (res.ok) {
        onNotify("Réconciliation scellée avec succès", "success");
        setReconcilingId(null);
        setReconcileEvidence('');
        fetchBudgetsData();
      } else {
        const err = await res.json();
        onNotify(`Erreur réconciliation: ${err.detail?.message || err.detail}`, "error");
      }
    } catch (err) {
      onNotify(`Erreur: ${err.message}`, "error");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-window"
        style={{
          maxWidth: '1000px',
          width: '95%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header" style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(168, 85, 247, 0.2))',
                border: '1px solid var(--neon-cyan)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Activity size={22} color="var(--neon-cyan)" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ fontSize: '1.15rem', color: '#FFFFFF', margin: 0, fontWeight: 700 }}>
                  Observabilité Unifiée & Télémétrie IA
                </h3>
                {tunnelStatus && (
                  <span
                    className="mono"
                    style={{
                      fontSize: '0.7rem',
                      padding: '2px 8px',
                      borderRadius: '12px',
                      background: tunnelStatus.tunnel_status === 'ONLINE' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                      color: tunnelStatus.tunnel_status === 'ONLINE' ? 'var(--neon-emerald)' : '#F43F5E',
                      border: `1px solid ${tunnelStatus.tunnel_status === 'ONLINE' ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.4)'}`,
                    }}
                  >
                    ● Tunnel {tunnelStatus.tunnel_status}
                  </span>
                )}
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
                Traces d'exécution Groq LLM · Quotas & Verrous PostgreSQL · Pipeline CRM & Benchmark
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={handleRunBenchmark}
              disabled={benchmarkLoading}
              className="btn-cyber accent-purple"
              style={{ padding: '6px 12px', fontSize: '0.78rem' }}
              title="Évaluer la posture, la sécurité zéro-fuite et la capture de devis"
            >
              <Sparkles size={14} className={benchmarkLoading ? 'spin' : ''} />
              <span>{benchmarkLoading ? 'Benchmark en cours...' : 'Tester Benchmark Qualité'}</span>
            </button>

            <button
              onClick={() => {
                if (activeTab === 'telemetry') fetchTelemetryData();
                else if (activeTab === 'budgets') fetchBudgetsData();
                else if (activeTab === 'leads') fetchLeadsData();
              }}
              className="control-btn"
              title="Rafraîchir"
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

        {/* Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            padding: '10px 24px',
            background: 'rgba(3, 5, 8, 0.4)',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <button
            onClick={() => setActiveTab('telemetry')}
            className={`btn-cyber ${activeTab === 'telemetry' ? 'primary' : 'secondary'}`}
            style={{ fontSize: '0.78rem', padding: '6px 14px' }}
          >
            <Cpu size={14} />
            <span>Télémétrie Groq & Traces ({traces.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('budgets')}
            className={`btn-cyber ${activeTab === 'budgets' ? 'primary' : 'secondary'}`}
            style={{ fontSize: '0.78rem', padding: '6px 14px' }}
          >
            <Coins size={14} />
            <span>Budgets & Verrous PostgreSQL ({budgets.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('leads')}
            className={`btn-cyber ${activeTab === 'leads' ? 'primary' : 'secondary'}`}
            style={{ fontSize: '0.78rem', padding: '6px 14px' }}
          >
            <MessageSquare size={14} />
            <span>Prospects CRM & Capture ({leads.length})</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body" style={{ overflowY: 'auto', flex: 1, padding: '20px 24px' }}>
          
          {/* Section Benchmark Overlay (si exécuté) */}
          {benchmarkResult && (
            <div
              className="glass-panel"
              style={{
                padding: '16px 20px',
                marginBottom: '20px',
                border: '1px solid rgba(168, 85, 247, 0.4)',
                background: 'rgba(168, 85, 247, 0.08)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={16} color="var(--neon-purple)" />
                  <strong style={{ color: '#FFFFFF', fontSize: '0.9rem' }}>
                    Résultats de la Golden Benchmark Suite
                  </strong>
                  <span
                    className="mono"
                    style={{
                      background: 'rgba(16, 185, 129, 0.2)',
                      color: 'var(--neon-emerald)',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                    }}
                  >
                    Score: {benchmarkResult.global_score}/100
                  </span>
                </div>
                <button
                  onClick={() => setBenchmarkResult(null)}
                  className="control-btn"
                  style={{ fontSize: '0.72rem', padding: '2px 6px' }}
                >
                  Masquer
                </button>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '10px' }}>
                {benchmarkResult.scenarios?.map((sc, i) => (
                  <div
                    key={i}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '6px',
                      background: 'rgba(0,0,0,0.3)',
                      border: `1px solid ${sc.passed ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.8rem', color: '#F8FAFC', fontWeight: 600 }}>{sc.name}</span>
                      <span
                        className="mono"
                        style={{
                          fontSize: '0.72rem',
                          color: sc.passed ? 'var(--neon-emerald)' : '#F43F5E',
                          fontWeight: 700,
                        }}
                      >
                        {sc.passed ? 'PASS' : 'FAIL'} ({sc.score}%)
                      </span>
                    </div>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{sc.details}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 1: TÉLÉMÉTRIE GROQ */}
          {activeTab === 'telemetry' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* KPI Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '14px' }}>
                <div className="glass-panel" style={{ padding: '14px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: '6px' }}>
                    <Coins size={14} color="var(--neon-emerald)" />
                    <span>Coût Estimé Total (USD)</span>
                  </div>
                  <div className="mono" style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--neon-emerald)' }}>
                    ${metrics ? metrics.total_cost_usd?.toFixed(4) : '0.0000'}
                  </div>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    Grille officielle Groq Llama 3.3
                  </span>
                </div>

                <div className="glass-panel" style={{ padding: '14px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: '6px' }}>
                    <Cpu size={14} color="var(--neon-cyan)" />
                    <span>Tokens Consommés</span>
                  </div>
                  <div className="mono" style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--neon-cyan)' }}>
                    {metrics ? metrics.total_tokens?.toLocaleString() : '0'}
                  </div>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    Prompt + Complétion
                  </span>
                </div>

                <div className="glass-panel" style={{ padding: '14px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: '6px' }}>
                    <Clock size={14} color="var(--neon-purple)" />
                    <span>Latence Moyenne</span>
                  </div>
                  <div className="mono" style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--neon-purple)' }}>
                    {metrics ? `${metrics.avg_latency_ms} ms` : '0 ms'}
                  </div>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    Génération Groq LPUs
                  </span>
                </div>

                <div className="glass-panel" style={{ padding: '14px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: '6px' }}>
                    <Send size={14} color="#F59E0B" />
                    <span>Routage Telegram</span>
                  </div>
                  <div className="mono" style={{ fontSize: '1.5rem', fontWeight: 800, color: '#F59E0B' }}>
                    {metrics ? metrics.leads_forwarded : '0'} leads
                  </div>
                  <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    Notifiés instantanément à Rockib
                  </span>
                </div>
              </div>

              {/* Feed des Traces Récentes */}
              <div>
                <h4 style={{ color: '#FFFFFF', fontSize: '0.9rem', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={15} color="var(--neon-cyan)" />
                  <span>Journal des Exécutions & Traces ({traces.length})</span>
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {traces.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Aucune trace d'exécution enregistrée pour le moment.
                    </div>
                  ) : (
                    traces.map((trace, idx) => (
                      <div
                        key={idx}
                        className="glass-panel"
                        style={{
                          padding: '12px 16px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '12px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '0.7rem',
                              fontWeight: 700,
                              background: trace.channel === 'voice' ? 'rgba(168, 85, 247, 0.2)' : 'rgba(0, 240, 255, 0.15)',
                              color: trace.channel === 'voice' ? 'var(--neon-purple)' : 'var(--neon-cyan)',
                              border: `1px solid ${trace.channel === 'voice' ? 'rgba(168, 85, 247, 0.4)' : 'rgba(0, 240, 255, 0.3)'}`,
                            }}
                          >
                            {trace.channel?.toUpperCase()}
                          </span>

                          <div>
                            <div style={{ fontSize: '0.83rem', color: '#F8FAFC', fontWeight: 600 }}>
                              {trace.model}
                            </div>
                            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                              Site : <strong style={{ color: '#CBD5E1' }}>{trace.site_key}</strong> · Outils : {trace.tools_called?.join(', ') || 'aucun'}
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                          <div style={{ textAlign: 'right' }}>
                            <div className="mono" style={{ fontSize: '0.78rem', color: 'var(--neon-emerald)' }}>
                              ${trace.cost_usd ? Number(trace.cost_usd).toFixed(4) : '0.0000'}
                            </div>
                            <div className="mono" style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                              {trace.tokens_total} tok · {trace.duration_ms} ms
                            </div>
                          </div>

                          {trace.forwarded_to_telegram && (
                            <span
                              title="Lead transmis par Telegram"
                              style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                background: 'rgba(16, 185, 129, 0.15)',
                                color: 'var(--neon-emerald)',
                                fontSize: '0.68rem',
                                border: '1px solid rgba(16, 185, 129, 0.3)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '3px',
                              }}
                            >
                              <Check size={11} /> Telegram
                            </span>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: BUDGETS & VERROUS POSTGRESQL */}
          {activeTab === 'budgets' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Cartes des Budgets */}
              <div>
                <h4 style={{ color: '#FFFFFF', fontSize: '0.9rem', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Coins size={15} color="var(--neon-emerald)" />
                  <span>Budgets de Quotas par Devise & Période</span>
                </h4>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px' }}>
                  {budgets.length === 0 ? (
                    <div className="glass-panel" style={{ padding: '20px', gridColumn: '1 / -1', textAlign: 'center', color: 'var(--text-muted)' }}>
                      Aucun plafond financier ResourceBudget configuré pour ce workspace.
                    </div>
                  ) : (
                    budgets.map((b) => {
                      const total = Number(b.limit_units);
                      const consumed = Number(b.consumed_units);
                      const held = Number(b.held_units);
                      const remaining = Number(b.remaining_units);
                      const pctConsumed = total > 0 ? Math.min(100, Math.round((consumed / total) * 100)) : 0;
                      const pctHeld = total > 0 ? Math.min(100, Math.round((held / total) * 100)) : 0;

                      return (
                        <div key={b.id} className="glass-panel" style={{ padding: '16px 18px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                            <strong style={{ color: 'var(--neon-cyan)', fontSize: '0.95rem' }}>{b.resource}</strong>
                            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Période: {b.period}</span>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '6px' }}>
                            <span style={{ color: 'var(--text-muted)' }}>Plafond :</span>
                            <span className="mono" style={{ color: '#FFFFFF', fontWeight: 700 }}>{total.toFixed(2)}</span>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '6px' }}>
                            <span style={{ color: '#F59E0B' }}>Engagé (HELD) :</span>
                            <span className="mono" style={{ color: '#F59E0B' }}>{held.toFixed(2)}</span>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '6px' }}>
                            <span style={{ color: 'var(--neon-emerald)' }}>Consommé :</span>
                            <span className="mono" style={{ color: 'var(--neon-emerald)' }}>{consumed.toFixed(2)}</span>
                          </div>

                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '8px' }}>
                            <span style={{ color: 'var(--text-muted)' }}>Disponible :</span>
                            <span className="mono" style={{ color: remaining > 0 ? '#FFFFFF' : '#F43F5E', fontWeight: 700 }}>
                              {remaining.toFixed(2)}
                            </span>
                          </div>

                          {/* Progress Bar composite */}
                          <div className="progress-bar-track" style={{ height: '6px', background: 'rgba(255,255,255,0.08)' }}>
                            <div
                              style={{
                                width: `${pctConsumed}%`,
                                height: '100%',
                                background: 'var(--neon-emerald)',
                                float: 'left',
                              }}
                            />
                            <div
                              style={{
                                width: `${pctHeld}%`,
                                height: '100%',
                                background: '#F59E0B',
                                float: 'left',
                              }}
                            />
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Tableau des Réservations Récentes */}
              <div>
                <h4 style={{ color: '#FFFFFF', fontSize: '0.9rem', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Lock size={15} color="var(--neon-purple)" />
                  <span>Réservations d'Actions & Verrous Atomiques ({reservations.length})</span>
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {reservations.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                      Aucune réservation récente.
                    </div>
                  ) : (
                    reservations.map((r) => (
                      <div
                        key={r.id}
                        className="glass-panel"
                        style={{
                          padding: '10px 14px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span
                            className="mono"
                            style={{
                              fontSize: '0.7rem',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontWeight: 700,
                              background:
                                r.status === 'CONSUMED'
                                  ? 'rgba(16, 185, 129, 0.15)'
                                  : r.status === 'HELD'
                                  ? 'rgba(245, 158, 11, 0.15)'
                                  : 'rgba(255, 255, 255, 0.05)',
                              color:
                                r.status === 'CONSUMED'
                                  ? 'var(--neon-emerald)'
                                  : r.status === 'HELD'
                                  ? '#F59E0B'
                                  : 'var(--text-muted)',
                              border: `1px solid ${
                                r.status === 'CONSUMED'
                                  ? 'rgba(16, 185, 129, 0.3)'
                                  : r.status === 'HELD'
                                  ? 'rgba(245, 158, 11, 0.3)'
                                  : 'rgba(255, 255, 255, 0.1)'
                              }`,
                            }}
                          >
                            {r.status}
                          </span>
                          <span className="mono" style={{ fontSize: '0.78rem', color: '#F8FAFC' }}>
                            {r.resource}
                          </span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                          <span className="mono" style={{ fontSize: '0.85rem', fontWeight: 700, color: '#FFFFFF' }}>
                            {Number(r.units).toFixed(2)}
                          </span>

                          {r.status === 'HELD' && (
                            <button
                              onClick={() => setReconcilingId(r.id)}
                              className="btn-cyber accent-purple"
                              style={{ padding: '3px 8px', fontSize: '0.7rem' }}
                            >
                              Réconcilier
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: PROSPECTS CRM */}
          {activeTab === 'leads' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Site Client :</span>
                  <input
                    type="text"
                    value={selectedSiteKey}
                    onChange={(e) => setSelectedSiteKey(e.target.value)}
                    className="cyber-input"
                    style={{ padding: '4px 10px', fontSize: '0.78rem', width: '180px' }}
                  />
                  <button
                    onClick={fetchLeadsData}
                    className="control-btn"
                    style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                  >
                    Filtrer
                  </button>
                </div>

                <a
                  href={`/api/v1/inbound/sites/${selectedSiteKey}/leads/export`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-cyber secondary"
                  style={{ padding: '6px 12px', fontSize: '0.78rem', textDecoration: 'none' }}
                >
                  <Download size={13} />
                  <span>Exporter CSV</span>
                </a>
              </div>

              {/* Table des Leads */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {leads.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    Aucun prospect capturé pour ce site client.
                  </div>
                ) : (
                  leads.map((ld) => {
                    const cleanPhone = ld.phone?.replace(/[^0-9+]/g, '');
                    const waLink = cleanPhone ? `https://wa.me/${cleanPhone.replace('+', '')}` : null;

                    return (
                      <div
                        key={ld.id}
                        className="glass-panel"
                        style={{
                          padding: '14px 16px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <strong style={{ color: '#FFFFFF', fontSize: '0.92rem' }}>{ld.name || 'Prospect Anonyme'}</strong>
                              <span
                                style={{
                                  padding: '2px 7px',
                                  borderRadius: '4px',
                                  fontSize: '0.68rem',
                                  background: 'rgba(0, 240, 255, 0.1)',
                                  color: 'var(--neon-cyan)',
                                }}
                              >
                                {ld.channel}
                              </span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                              {ld.phone && <span>Tél : {ld.phone} · </span>}
                              {ld.email && <span>Email : {ld.email}</span>}
                            </div>
                          </div>

                          {/* Sélecteur de statut */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <select
                              value={ld.status}
                              onChange={(e) => handleUpdateLeadStatus(ld.id, e.target.value)}
                              className="cyber-input"
                              style={{
                                padding: '3px 8px',
                                fontSize: '0.72rem',
                                color:
                                  ld.status === 'converted'
                                    ? 'var(--neon-emerald)'
                                    : ld.status === 'contacted'
                                    ? 'var(--neon-cyan)'
                                    : '#F59E0B',
                              }}
                            >
                              <option value="received">received (Reçu)</option>
                              <option value="contacted">contacted (Contacté)</option>
                              <option value="converted">converted (Converti)</option>
                              <option value="archived">archived (Archivé)</option>
                            </select>

                            {waLink && (
                              <a
                                href={waLink}
                                target="_blank"
                                rel="noreferrer"
                                className="btn-cyber accent-purple"
                                style={{ padding: '3px 8px', fontSize: '0.7rem', textDecoration: 'none' }}
                                title="Ouvrir WhatsApp"
                              >
                                <PhoneCall size={12} />
                                <span>WhatsApp</span>
                              </a>
                            )}
                          </div>
                        </div>

                        {/* Note & Budget */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#CBD5E1', background: 'rgba(0,0,0,0.2)', padding: '6px 10px', borderRadius: '4px' }}>
                          <span>Besoin : {ld.notes || 'Devis standard'}</span>
                          {ld.budget && <span className="mono" style={{ color: 'var(--neon-emerald)' }}>Budget : {ld.budget}</span>}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
