import React, { useState, useEffect, useRef } from 'react';
import {
  BarChart3,
  Bot,
  Target,
  CheckCircle2,
  ShieldCheck,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';

/**
 * DashboardPanel — Tableau de bord temps réel avec KPIs animés,
 * sparklines SVG, donut chart de répartition des tâches.
 */

// ─── Animated Counter ────────────────────────────────────────────

function AnimatedCounter({ value, duration = 800, prefix = '', suffix = '' }) {
  const [display, setDisplay] = useState(0);
  const prevRef = useRef(0);

  useEffect(() => {
    const start = prevRef.current;
    const end = value;
    if (start === end) return;

    const startTime = performance.now();
    const step = (now) => {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(Math.round(start + (end - start) * eased));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
    prevRef.current = end;
  }, [value, duration]);

  return (
    <span className="mono" style={{ fontSize: '1.6rem', fontWeight: 800 }}>
      {prefix}
      {display}
      {suffix}
    </span>
  );
}

// ─── SVG Sparkline ───────────────────────────────────────────────

function Sparkline({ data = [], color = '#00F0FF', width = 120, height = 32 }) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');

  const areaPath = `M0,${height} L${points
    .split(' ')
    .map((p, i) => (i === 0 ? p : `L${p}`))
    .join(' ')} L${width},${height} Z`;

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={`spark-grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${height} ${points} ${width},${height}`}
        fill={`url(#spark-grad-${color.replace('#', '')})`}
      />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ─── SVG Donut Chart ─────────────────────────────────────────────

function DonutChart({ segments = [], size = 100 }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <svg width={size} height={size} viewBox="0 0 100 100">
      {segments.map((seg, i) => {
        const pct = seg.value / total;
        const dashLength = circumference * pct;
        const dashOffset = -offset;
        offset += dashLength;
        return (
          <circle
            key={i}
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={seg.color}
            strokeWidth="8"
            strokeDasharray={`${dashLength} ${circumference - dashLength}`}
            strokeDashoffset={dashOffset}
            transform="rotate(-90 50 50)"
            style={{ transition: 'stroke-dasharray 0.6s ease, stroke-dashoffset 0.6s ease' }}
          />
        );
      })}
      <text
        x="50"
        y="50"
        textAnchor="middle"
        dominantBaseline="middle"
        fill="#F8FAFC"
        fontSize="16"
        fontWeight="800"
        fontFamily="Outfit, sans-serif"
      >
        {total}
      </text>
      <text
        x="50"
        y="64"
        textAnchor="middle"
        fill="#64748B"
        fontSize="8"
        fontFamily="Inter, sans-serif"
      >
        tâches
      </text>
    </svg>
  );
}

// ─── Main Dashboard Panel ────────────────────────────────────────

export default function DashboardPanel({
  isOpen,
  onClose,
  agents = [],
  goals = [],
  telemetry = [],
}) {
  // Historical data for sparklines (accumulated on each render)
  const historyRef = useRef({ agents: [], goals: [], events: [] });

  useEffect(() => {
    const h = historyRef.current;
    h.agents.push(agents.length);
    h.goals.push(goals.length);
    h.events.push(telemetry.length);
    // Keep last 25 data points
    if (h.agents.length > 25) h.agents.shift();
    if (h.goals.length > 25) h.goals.shift();
    if (h.events.length > 25) h.events.shift();
  }, [agents, goals, telemetry]);

  if (!isOpen) return null;

  // Compute KPIs
  const activeAgents = agents.filter(
    (a) => a.current_status === 'RUNNING' || a.current_status === 'READY'
  ).length;
  const idleAgents = agents.filter((a) => a.current_status === 'IDLE').length;
  const activeGoals = goals.filter(
    (g) => g.status === 'ACTIVE' || g.status === 'PLANNING'
  ).length;
  const completedGoals = goals.filter((g) => g.status === 'COMPLETED').length;

  // Task stats aggregated from goals
  const totalTasks = goals.reduce((s, g) => s + (g.tasks_count || 0), 0);
  const completedTasks = goals.reduce(
    (s, g) => s + (g.completed_tasks_count || 0),
    0
  );
  const runningTasks = goals.reduce(
    (s, g) => s + (g.running_tasks_count || 0),
    0
  );
  const pendingTasks = totalTasks - completedTasks - runningTasks;
  const successRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  // Decisions vs executions from telemetry
  const decisions = telemetry.filter((t) => t.type === 'decision').length;
  const executions = telemetry.filter((t) => t.type === 'execution').length;

  const donutSegments = [
    { value: completedTasks, color: '#10B981', label: 'Complétées' },
    { value: runningTasks, color: '#00F0FF', label: 'En cours' },
    { value: pendingTasks, color: '#64748B', label: 'En attente' },
  ];

  return (
    <div className="dashboard-panel glass-panel hud-interactive">
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <BarChart3 size={18} color="var(--neon-cyan)" />
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.95rem',
            }}
          >
            Dashboard Temps Réel
          </span>
        </div>
        <button
          onClick={onClose}
          className="control-btn"
          style={{ padding: '4px', borderRadius: '50%' }}
        >
          <X size={16} />
        </button>
      </div>

      {/* KPI Grid */}
      <div className="dashboard-kpi-grid">
        {/* Agents */}
        <div className="kpi-card">
          <div className="kpi-header">
            <Bot size={15} color="var(--neon-cyan)" />
            <span>Agents Actifs</span>
          </div>
          <AnimatedCounter value={activeAgents} />
          <div className="kpi-sub">
            <span style={{ color: 'var(--text-muted)' }}>
              {idleAgents} idle · {agents.length} total
            </span>
          </div>
          <Sparkline data={historyRef.current.agents} color="#00F0FF" />
        </div>

        {/* Goals */}
        <div className="kpi-card">
          <div className="kpi-header">
            <Target size={15} color="var(--neon-purple)" />
            <span>Objectifs</span>
          </div>
          <AnimatedCounter value={activeGoals} />
          <div className="kpi-sub">
            <span style={{ color: 'var(--text-muted)' }}>
              {completedGoals} complétés · {goals.length} total
            </span>
          </div>
          <Sparkline data={historyRef.current.goals} color="#A855F7" />
        </div>

        {/* Success Rate */}
        <div className="kpi-card">
          <div className="kpi-header">
            <TrendingUp size={15} color="var(--neon-emerald)" />
            <span>Taux de Succès</span>
          </div>
          <AnimatedCounter value={successRate} suffix="%" />
          <div className="kpi-sub">
            <span style={{ color: 'var(--text-muted)' }}>
              {completedTasks}/{totalTasks} tâches
            </span>
          </div>
          <div
            className="progress-bar-track"
            style={{ height: '5px', marginTop: '4px' }}
          >
            <div
              className="progress-bar-fill"
              style={{
                width: `${successRate}%`,
                background:
                  'linear-gradient(90deg, var(--neon-emerald), var(--neon-cyan))',
              }}
            />
          </div>
        </div>

        {/* Arbitrage */}
        <div className="kpi-card">
          <div className="kpi-header">
            <ShieldCheck size={15} color="var(--neon-amber)" />
            <span>Décisions</span>
          </div>
          <AnimatedCounter value={decisions} />
          <div className="kpi-sub">
            <span style={{ color: 'var(--text-muted)' }}>
              {executions} exécutions
            </span>
          </div>
          <Sparkline data={historyRef.current.events} color="#F59E0B" />
        </div>
      </div>

      {/* Donut + Legend */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '20px',
          padding: '12px 20px 16px',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <DonutChart segments={donutSegments} size={80} />
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '5px',
            flex: 1,
          }}
        >
          {donutSegments.map((seg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '0.78rem',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: seg.color,
                  display: 'inline-block',
                  boxShadow: `0 0 8px ${seg.color}`,
                }}
              />
              <span style={{ color: 'var(--text-secondary)' }}>
                {seg.label}
              </span>
              <strong className="mono" style={{ marginLeft: 'auto' }}>
                {seg.value}
              </strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
