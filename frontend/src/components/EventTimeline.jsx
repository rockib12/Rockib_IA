import React, { useState, useMemo } from 'react';
import {
  ShieldAlert,
  Terminal,
  Bot,
  Clock,
  Filter,
  ChevronDown,
  ChevronUp,
  Zap,
  MessageSquare,
} from 'lucide-react';

/**
 * EventTimeline — Audit trail vertical temps réel
 * avec filtres par type, timestamps relatifs, et détails expandables.
 */

function relativeTime(ts) {
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return `il y a ${Math.floor(diff)}s`;
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`;
  return new Date(ts).toLocaleDateString('fr-FR');
}

const EVENT_CONFIG = {
  decision: {
    icon: ShieldAlert,
    color: '#F59E0B',
    label: 'Décision',
    bgAlpha: 'rgba(245, 158, 11, 0.08)',
  },
  execution: {
    icon: Terminal,
    color: '#10B981',
    label: 'Exécution',
    bgAlpha: 'rgba(16, 185, 129, 0.08)',
  },
  agent_spawn: {
    icon: Bot,
    color: '#00F0FF',
    label: 'Spawn',
    bgAlpha: 'rgba(0, 240, 255, 0.08)',
  },
  task_update: {
    icon: Zap,
    color: '#A855F7',
    label: 'Tâche',
    bgAlpha: 'rgba(168, 85, 247, 0.08)',
  },
  p2p_dialogue: {
    icon: MessageSquare,
    color: '#EC4899',
    label: 'Dialogue P2P',
    bgAlpha: 'rgba(236, 72, 153, 0.08)',
  },
};

function TimelineEvent({ event }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = EVENT_CONFIG[event.type] || EVENT_CONFIG.execution;
  const Icon = cfg.icon;

  return (
    <div className="timeline-event" style={{ '--event-color': cfg.color }}>
      {/* Timeline Node */}
      <div className="timeline-node">
        <div
          className="timeline-dot"
          style={{
            backgroundColor: cfg.color,
            boxShadow: `0 0 12px ${cfg.color}`,
          }}
        />
      </div>

      {/* Event Card */}
      <div
        className="timeline-card"
        onClick={() => setExpanded(!expanded)}
        style={{
          borderColor: expanded
            ? cfg.color
            : 'var(--border-subtle)',
          background: expanded ? cfg.bgAlpha : 'rgba(17, 24, 43, 0.6)',
        }}
      >
        <div className="timeline-card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Icon size={14} color={cfg.color} />
            <strong style={{ fontSize: '0.82rem' }}>{event.agent_name}</strong>
            <span
              className="timeline-type-badge"
              style={{
                backgroundColor: cfg.bgAlpha,
                color: cfg.color,
                border: `1px solid ${cfg.color}40`,
              }}
            >
              {cfg.label}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span
              className="mono"
              style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}
            >
              {relativeTime(event.timestamp)}
            </span>
            {expanded ? (
              <ChevronUp size={12} color="var(--text-muted)" />
            ) : (
              <ChevronDown size={12} color="var(--text-muted)" />
            )}
          </div>
        </div>

        <p
          style={{
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
            lineHeight: '1.4',
            margin: '4px 0 0',
          }}
        >
          {event.summary}
        </p>

        {expanded && event.details && (
          <div className="timeline-details">
            {Object.entries(event.details).map(([key, value]) =>
              value ? (
                <div key={key} className="detail-row">
                  <span className="detail-key">{key}</span>
                  <span className="detail-value mono">
                    {typeof value === 'object'
                      ? JSON.stringify(value)
                      : String(value)}
                  </span>
                </div>
              ) : null
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function EventTimeline({
  isOpen,
  onClose,
  telemetry = [],
}) {
  const [filters, setFilters] = useState({
    decision: true,
    execution: true,
    agent_spawn: true,
    task_update: true,
    p2p_dialogue: true,
  });

  const filteredEvents = useMemo(
    () => telemetry.filter((e) => filters[e.type] !== false),
    [telemetry, filters]
  );

  const toggleFilter = (type) => {
    setFilters((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  if (!isOpen) return null;

  return (
    <div className="event-timeline glass-panel hud-interactive">
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 18px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Clock size={16} color="var(--neon-cyan)" />
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '0.9rem',
            }}
          >
            Timeline — Audit Trail
          </span>
          <span
            className="mono"
            style={{
              fontSize: '0.7rem',
              padding: '1px 6px',
              background: 'rgba(0, 240, 255, 0.1)',
              borderRadius: '4px',
              color: 'var(--neon-cyan)',
            }}
          >
            {filteredEvents.length}
          </span>
        </div>
        <button
          onClick={onClose}
          className="control-btn"
          style={{ padding: '4px', borderRadius: '50%' }}
        >
          <span style={{ fontSize: '14px' }}>✕</span>
        </button>
      </div>

      {/* Filters */}
      <div className="timeline-filters">
        {Object.entries(EVENT_CONFIG).map(([type, cfg]) => (
          <button
            key={type}
            className={`filter-chip ${filters[type] ? 'active' : ''}`}
            onClick={() => toggleFilter(type)}
            style={{
              '--chip-color': cfg.color,
              borderColor: filters[type] ? cfg.color : 'transparent',
              color: filters[type] ? cfg.color : 'var(--text-muted)',
              background: filters[type]
                ? `${cfg.color}15`
                : 'rgba(255,255,255,0.03)',
            }}
          >
            <cfg.icon size={12} />
            {cfg.label}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="timeline-scroll">
        {filteredEvents.length === 0 ? (
          <div
            style={{
              padding: '40px 20px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '0.85rem',
            }}
          >
            Aucun événement correspondant aux filtres.
          </div>
        ) : (
          <div className="timeline-list">
            {filteredEvents.map((event) => (
              <TimelineEvent key={event.id} event={event} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
