import React, { useState, useMemo, useRef, useCallback } from 'react';
import {
  GitCommit,
  CheckCircle2,
  Clock,
  AlertCircle,
  Play,
  ShieldAlert,
  Terminal,
  ListFilter,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from 'lucide-react';

/**
 * TaskDAGPanel — Console tactique avec graphe SVG interactif
 * des tâches et un flux de télémétrie en temps réel.
 *
 * Phase 4: Visual DAG with topological layout, Bézier edges,
 * status-based node styling, zoom/pan.
 */

// ─── DAG Layout (simplified Sugiyama-like) ────────────────────────

function computeDAGLayout(tasks) {
  if (tasks.length === 0) return { nodes: [], edges: [] };

  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const depsMap = new Map(); // taskId -> [dep taskIds]
  tasks.forEach((t) => {
    depsMap.set(t.id, t.dependencies || []);
  });

  // Topological sort to assign levels
  const levels = new Map();
  const visited = new Set();
  const temp = new Set();

  function getLevel(id) {
    if (levels.has(id)) return levels.get(id);
    if (temp.has(id)) return 0; // cycle guard
    temp.add(id);
    const deps = depsMap.get(id) || [];
    const maxDepLevel = deps.reduce((max, depId) => {
      if (taskMap.has(depId)) {
        return Math.max(max, getLevel(depId) + 1);
      }
      return max;
    }, 0);
    temp.delete(id);
    levels.set(id, maxDepLevel);
    return maxDepLevel;
  }

  tasks.forEach((t) => getLevel(t.id));

  // Group by level
  const byLevel = new Map();
  tasks.forEach((t) => {
    const lv = levels.get(t.id) || 0;
    if (!byLevel.has(lv)) byLevel.set(lv, []);
    byLevel.get(lv).push(t);
  });

  // Compute node positions
  const nodeWidth = 200;
  const nodeHeight = 56;
  const horizontalGap = 60;
  const verticalGap = 30;
  const padX = 30;
  const padY = 30;

  const nodes = [];
  const maxLevelCount = Math.max(
    ...Array.from(byLevel.values()).map((arr) => arr.length),
    1
  );
  const totalWidth = maxLevelCount * (nodeWidth + horizontalGap);

  const sortedLevels = Array.from(byLevel.keys()).sort((a, b) => a - b);

  sortedLevels.forEach((lv) => {
    const tasksAtLevel = byLevel.get(lv);
    const levelWidth = tasksAtLevel.length * (nodeWidth + horizontalGap) - horizontalGap;
    const startX = padX + (totalWidth - levelWidth) / 2;
    const y = padY + lv * (nodeHeight + verticalGap);

    tasksAtLevel.forEach((task, idx) => {
      const x = startX + idx * (nodeWidth + horizontalGap);
      nodes.push({
        id: task.id,
        x,
        y,
        width: nodeWidth,
        height: nodeHeight,
        task,
        level: lv,
      });
    });
  });

  // Compute edges
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const edges = [];
  tasks.forEach((t) => {
    (t.dependencies || []).forEach((depId) => {
      const from = nodeMap.get(depId);
      const to = nodeMap.get(t.id);
      if (from && to) {
        edges.push({ from, to });
      }
    });
  });

  const viewWidth = totalWidth + padX * 2;
  const viewHeight =
    padY * 2 +
    sortedLevels.length * (nodeHeight + verticalGap);

  return { nodes, edges, viewWidth, viewHeight };
}

// ─── Status styling helpers ──────────────────────────────────────

const STATUS_STYLES = {
  COMPLETED: {
    fill: 'rgba(16, 185, 129, 0.15)',
    stroke: '#10B981',
    textColor: '#10B981',
    Icon: CheckCircle2,
  },
  RUNNING: {
    fill: 'rgba(0, 240, 255, 0.15)',
    stroke: '#00F0FF',
    textColor: '#00F0FF',
    Icon: Clock,
  },
  READY: {
    fill: 'rgba(99, 102, 241, 0.12)',
    stroke: '#6366F1',
    textColor: '#6366F1',
    Icon: GitCommit,
  },
  PENDING: {
    fill: 'rgba(100, 116, 139, 0.1)',
    stroke: '#475569',
    textColor: '#64748B',
    Icon: GitCommit,
  },
  BLOCKED: {
    fill: 'rgba(244, 63, 94, 0.15)',
    stroke: '#F43F5E',
    textColor: '#F43F5E',
    Icon: AlertCircle,
  },
};

// ─── DAG SVG Renderer ────────────────────────────────────────────

function DAGGraph({ tasks, onTaskHover }) {
  const { nodes, edges, viewWidth, viewHeight } = useMemo(
    () => computeDAGLayout(tasks),
    [tasks]
  );
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const lastPos = useRef({ x: 0, y: 0 });
  const [hoveredId, setHoveredId] = useState(null);

  const handleMouseDown = (e) => {
    if (e.button === 0) {
      setDragging(true);
      lastPos.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseMove = useCallback(
    (e) => {
      if (!dragging) return;
      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      lastPos.current = { x: e.clientX, y: e.clientY };
      setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
    },
    [dragging]
  );

  const handleMouseUp = () => setDragging(false);
  const handleWheel = (e) => {
    e.stopPropagation();
    setZoom((z) => Math.max(0.3, Math.min(2.5, z - e.deltaY * 0.001)));
  };

  if (tasks.length === 0) {
    return (
      <div
        style={{
          padding: '40px 20px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: '0.85rem',
        }}
      >
        Aucune tâche disponible pour cet objectif.
      </div>
    );
  }

  // Highlight edges connected to hovered node
  const hoveredEdges = new Set();
  if (hoveredId) {
    edges.forEach((e, i) => {
      if (e.from.id === hoveredId || e.to.id === hoveredId) {
        hoveredEdges.add(i);
      }
    });
  }

  return (
    <div style={{ position: 'relative', flex: 1 }}>
      {/* Zoom controls */}
      <div
        style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          display: 'flex',
          gap: '4px',
          zIndex: 5,
        }}
      >
        <button
          className="control-btn"
          onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
          style={{ padding: '4px 6px' }}
        >
          <ZoomIn size={13} />
        </button>
        <button
          className="control-btn"
          onClick={() => setZoom((z) => Math.max(0.3, z - 0.2))}
          style={{ padding: '4px 6px' }}
        >
          <ZoomOut size={13} />
        </button>
        <button
          className="control-btn"
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          style={{ padding: '4px 6px' }}
        >
          <Maximize2 size={13} />
        </button>
      </div>

      <svg
        width="100%"
        height="100%"
        style={{
          cursor: dragging ? 'grabbing' : 'grab',
          minHeight: '260px',
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <g
          transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
        >
          {/* Edges (Bézier curves) */}
          {edges.map((edge, i) => {
            const x1 = edge.from.x + edge.from.width / 2;
            const y1 = edge.from.y + edge.from.height;
            const x2 = edge.to.x + edge.to.width / 2;
            const y2 = edge.to.y;
            const cy1 = y1 + 20;
            const cy2 = y2 - 20;
            const isHighlighted = hoveredEdges.has(i);

            return (
              <g key={`edge-${i}`}>
                <path
                  d={`M ${x1} ${y1} C ${x1} ${cy1}, ${x2} ${cy2}, ${x2} ${y2}`}
                  fill="none"
                  stroke={isHighlighted ? '#00F0FF' : '#334155'}
                  strokeWidth={isHighlighted ? 2.5 : 1.5}
                  strokeDasharray={isHighlighted ? 'none' : '6 4'}
                  opacity={isHighlighted ? 1 : 0.6}
                  style={{ transition: 'all 0.2s ease' }}
                />
                {/* Arrow head */}
                <polygon
                  points={`${x2 - 4},${y2 - 6} ${x2 + 4},${y2 - 6} ${x2},${y2}`}
                  fill={isHighlighted ? '#00F0FF' : '#475569'}
                  style={{ transition: 'fill 0.2s ease' }}
                />
              </g>
            );
          })}

          {/* Nodes */}
          {nodes.map((node) => {
            const st = STATUS_STYLES[node.task.status] || STATUS_STYLES.PENDING;
            const isHovered = hoveredId === node.id;
            const isRunning = node.task.status === 'RUNNING';

            return (
              <g
                key={node.id}
                onMouseEnter={() => {
                  setHoveredId(node.id);
                  onTaskHover?.(node.task);
                }}
                onMouseLeave={() => {
                  setHoveredId(null);
                  onTaskHover?.(null);
                }}
                style={{ cursor: 'pointer' }}
              >
                {/* Running glow */}
                {isRunning && (
                  <rect
                    x={node.x - 3}
                    y={node.y - 3}
                    width={node.width + 6}
                    height={node.height + 6}
                    rx="14"
                    fill="none"
                    stroke="#00F0FF"
                    strokeWidth="1"
                    opacity="0.4"
                  >
                    <animate
                      attributeName="opacity"
                      values="0.2;0.6;0.2"
                      dur="2s"
                      repeatCount="indefinite"
                    />
                  </rect>
                )}

                {/* Node background */}
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx="11"
                  fill={isHovered ? st.fill.replace(')', ', 0.25)').replace('0.1', '0.25').replace('0.12', '0.25').replace('0.15', '0.25') : st.fill}
                  stroke={st.stroke}
                  strokeWidth={isHovered ? 2 : 1}
                  style={{ transition: 'all 0.2s ease' }}
                />

                {/* Index chip */}
                <rect
                  x={node.x + 8}
                  y={node.y + 8}
                  width="24"
                  height="18"
                  rx="4"
                  fill="rgba(255,255,255,0.06)"
                />
                <text
                  x={node.x + 20}
                  y={node.y + 17}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#64748B"
                  fontSize="9"
                  fontFamily="JetBrains Mono, monospace"
                  fontWeight="700"
                >
                  #{node.level + 1}
                </text>

                {/* Task description */}
                <text
                  x={node.x + 38}
                  y={node.y + 22}
                  fill="#E2E8F0"
                  fontSize="11"
                  fontFamily="Inter, sans-serif"
                  fontWeight="500"
                >
                  {node.task.description.length > 22
                    ? node.task.description.slice(0, 20) + '…'
                    : node.task.description}
                </text>

                {/* Status label */}
                <text
                  x={node.x + 38}
                  y={node.y + 40}
                  fill={st.textColor}
                  fontSize="9"
                  fontFamily="Outfit, sans-serif"
                  fontWeight="700"
                  letterSpacing="0.04em"
                >
                  {node.task.status}
                </text>

                {/* Status icon circle */}
                <circle
                  cx={node.x + node.width - 18}
                  cy={node.y + node.height / 2}
                  r="10"
                  fill={st.fill}
                  stroke={st.stroke}
                  strokeWidth="1.5"
                />
                {node.task.status === 'COMPLETED' && (
                  <text
                    x={node.x + node.width - 18}
                    y={node.y + node.height / 2}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={st.textColor}
                    fontSize="11"
                  >
                    ✓
                  </text>
                )}
                {node.task.status === 'RUNNING' && (
                  <circle
                    cx={node.x + node.width - 18}
                    cy={node.y + node.height / 2}
                    r="4"
                    fill={st.textColor}
                  >
                    <animate
                      attributeName="r"
                      values="3;5;3"
                      dur="1.5s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                {node.task.status === 'BLOCKED' && (
                  <text
                    x={node.x + node.width - 18}
                    y={node.y + node.height / 2}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={st.textColor}
                    fontSize="11"
                  >
                    ⚠
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

// ─── Main Panel ──────────────────────────────────────────────────

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
  const [hoveredTask, setHoveredTask] = useState(null);

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
            {/* Goal Selector */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  fontWeight: 700,
                }}
              >
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

            {/* Goal Summary */}
            {activeGoal && (
              <div
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '12px',
                  padding: '14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span
                    style={{
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      color: 'var(--neon-cyan)',
                    }}
                  >
                    {activeGoal.agent_name}
                  </span>
                  <span
                    className={`status-badge ${activeGoal.status.toLowerCase()}`}
                  >
                    {activeGoal.status}
                  </span>
                </div>
                <p
                  style={{
                    fontSize: '0.85rem',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {activeGoal.objective}
                </p>
                <button
                  onClick={() => onWakeGoal(activeGoal.id)}
                  disabled={isWaking}
                  className="btn-cyber primary"
                  style={{
                    width: '100%',
                    justifyContent: 'center',
                    padding: '6px 12px',
                    fontSize: '0.8rem',
                  }}
                >
                  <Play size={14} />
                  {isWaking ? 'Exécution...' : "Avancer d'un pas (Wake)"}
                </button>
              </div>
            )}

            {/* Visual DAG Graph */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--text-muted)',
                  fontWeight: 700,
                }}
              >
                GRAPHE D'EXÉCUTION ({tasks.length} tâches)
              </span>

              <DAGGraph tasks={tasks} onTaskHover={setHoveredTask} />

              {/* Hovered task detail */}
              {hoveredTask && (
                <div
                  style={{
                    background: 'rgba(0,0,0,0.4)',
                    border: '1px solid var(--border-neon-cyan)',
                    borderRadius: '10px',
                    padding: '10px 12px',
                    fontSize: '0.8rem',
                    animation: 'fade-in 0.15s ease',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: '4px',
                    }}
                  >
                    <strong style={{ color: 'var(--neon-cyan)' }}>
                      {hoveredTask.description}
                    </strong>
                    <span
                      className={`status-badge ${hoveredTask.status.toLowerCase()}`}
                      style={{ fontSize: '0.65rem' }}
                    >
                      {hoveredTask.status}
                    </span>
                  </div>
                  {hoveredTask.decision_id && (
                    <div
                      className="mono"
                      style={{
                        fontSize: '0.7rem',
                        color: 'var(--neon-indigo)',
                      }}
                    >
                      Décision liée : {hoveredTask.decision_id.slice(0, 8)}...
                    </div>
                  )}
                  {hoveredTask.result_summary && (
                    <div
                      style={{
                        marginTop: '6px',
                        background: 'rgba(0,0,0,0.5)',
                        border: '1px solid rgba(0, 240, 255, 0.3)',
                        borderRadius: '6px',
                        padding: '6px 8px',
                        fontSize: '0.75rem',
                        fontFamily: 'JetBrains Mono, monospace',
                        color: '#A7F3D0',
                        whiteSpace: 'pre-wrap',
                        maxHeight: '140px',
                        overflowY: 'auto',
                      }}
                    >
                      <div style={{ color: 'var(--neon-cyan)', fontWeight: 700, marginBottom: '2px', fontSize: '0.7rem' }}>
                        ✓ Résultat de la tâche :
                      </div>
                      {hoveredTask.result_summary}
                    </div>
                  )}
                </div>
              )}

              {/* Task Details & Execution Results List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '10px' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 700 }}>
                  DÉTAILS DES TÂCHES & RÉSULTATS ({tasks.length})
                </span>
                {tasks.map((task, idx) => (
                  <div
                    key={task.id}
                    style={{
                      background: 'rgba(0,0,0,0.3)',
                      border: `1px solid ${task.status === 'COMPLETED' ? 'var(--neon-emerald)' : task.status === 'BLOCKED' ? 'var(--neon-rose)' : 'var(--border-subtle)'}`,
                      borderRadius: '8px',
                      padding: '10px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)' }}>
                        #{idx + 1} {task.tool ? `[${task.tool.toUpperCase()}]` : ''}
                      </span>
                      <span className={`status-badge ${task.status.toLowerCase()}`} style={{ fontSize: '0.65rem' }}>
                        {task.status}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#E2E8F0', fontWeight: 500 }}>
                      {task.description}
                    </div>
                    {task.result_summary && (
                      <div
                        style={{
                          marginTop: '4px',
                          background: 'rgba(0,0,0,0.5)',
                          border: '1px solid rgba(0, 240, 255, 0.25)',
                          borderRadius: '6px',
                          padding: '8px 10px',
                          fontSize: '0.75rem',
                          fontFamily: 'JetBrains Mono, monospace',
                          color: '#A7F3D0',
                          whiteSpace: 'pre-wrap',
                          maxHeight: '180px',
                          overflowY: 'auto',
                        }}
                      >
                        <div style={{ color: 'var(--neon-cyan)', fontWeight: 700, marginBottom: '4px', fontSize: '0.7rem' }}>
                          ✓ RÉPONSE / RÉSULTAT OBTENU :
                        </div>
                        {task.result_summary}
                        {task.result_summary.includes('/preview/') && (
                          <div style={{ marginTop: '8px' }}>
                            <a
                              href={task.result_summary.match(/\/api\/v1\/workspaces\/[^\s\n]+/)?.[0] || '#'}
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '6px',
                                background: 'rgba(0, 240, 255, 0.15)',
                                border: '1px solid var(--neon-cyan)',
                                borderRadius: '6px',
                                padding: '5px 12px',
                                color: 'var(--neon-cyan)',
                                textDecoration: 'none',
                                fontSize: '0.75rem',
                                fontWeight: 700,
                                boxShadow: '0 0 10px rgba(0, 240, 255, 0.2)',
                              }}
                            >
                              🌐 Ouvrir le site / l'aperçu en direct ↗
                            </a>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </>

        ) : (
          /* Telemetry Tab */
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <span
              style={{
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                fontWeight: 700,
              }}
            >
              FLUX D'ARBITRAGE ET D'EXÉCUTION EN TEMPS RÉEL
            </span>

            {telemetry.length === 0 ? (
              <div
                style={{
                  padding: '20px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                  fontSize: '0.85rem',
                }}
              >
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
                    gap: '6px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      {item.type === 'decision' ? (
                        <ShieldAlert size={14} color="var(--neon-amber)" />
                      ) : (
                        <Terminal size={14} color="var(--neon-emerald)" />
                      )}
                      <strong
                        style={{
                          fontSize: '0.8rem',
                          color: 'var(--text-primary)',
                        }}
                      >
                        {item.agent_name}
                      </strong>
                    </div>
                    <span
                      className="mono"
                      style={{
                        fontSize: '0.65rem',
                        color: 'var(--text-muted)',
                      }}
                    >
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-secondary)',
                      lineHeight: '1.4',
                    }}
                  >
                    {item.summary}
                  </p>
                  {item.details?.fingerprint && (
                    <div
                      className="mono"
                      style={{
                        fontSize: '0.68rem',
                        color: 'var(--neon-cyan)',
                      }}
                    >
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
