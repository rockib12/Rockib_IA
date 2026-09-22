import React from 'react';
import { 
  Boxes, 
  Layers, 
  Activity, 
  Sparkles, 
  Play, 
  Plus, 
  Compass, 
  Columns, 
  Maximize2 
} from 'lucide-react';

export default function CockpitHeader({
  agentsCount = 0,
  goalsCount = 0,
  isSplitView = false,
  onToggleSplitView,
  onOpenSpawnModal,
  onWakeGlobal,
  onResetCamera,
  isWaking = false,
}) {
  return (
    <header className="cockpit-header">
      {/* Brand & Identity */}
      <div className="brand-section">
        <div className="brand-logo-glow">
          <Boxes size={20} color="#FFFFFF" />
        </div>
        <div>
          <span className="brand-title">ROCKIB IA</span>
          <span className="brand-badge" style={{ marginLeft: '8px' }}>
            3D META-COCKPIT
          </span>
        </div>
      </div>

      {/* Real-time Status & Metrics */}
      <div className="header-metrics">
        <div className="metric-pill">
          <span className="status-dot" />
          <span>PostgreSQL & Engine :</span>
          <strong>ONLINE</strong>
        </div>

        <div className="metric-pill">
          <Activity size={14} color="var(--neon-cyan)" />
          <span>Agents Actifs :</span>
          <strong>{agentsCount}</strong>
        </div>

        <div className="metric-pill">
          <Layers size={14} color="var(--neon-purple)" />
          <span>Objectifs (Goals) :</span>
          <strong>{goalsCount}</strong>
        </div>
      </div>

      {/* Control Actions */}
      <div className="header-actions">
        <button 
          onClick={onResetCamera} 
          className="btn-cyber secondary"
          title="Recentrer la caméra sur la constellation d'agents"
        >
          <Compass size={15} />
          <span>Recentrer</span>
        </button>

        <button 
          onClick={onToggleSplitView} 
          className={`btn-cyber ${isSplitView ? 'primary' : 'secondary'}`}
          title={isSplitView ? "Passer en plein écran 3D immersif" : "Ouvrir la console tactique latérale"}
        >
          {isSplitView ? <Maximize2 size={15} /> : <Columns size={15} />}
          <span>{isSplitView ? "3D Immersif" : "Cockpit Split"}</span>
        </button>

        <button 
          onClick={onOpenSpawnModal} 
          className="btn-cyber accent-purple"
          title="Matérialiser un nouvel agent dans la matrice 3D"
        >
          <Plus size={16} />
          <span>Déployer Agent</span>
        </button>

        <button 
          onClick={onWakeGlobal} 
          disabled={isWaking}
          className="btn-cyber primary"
          title="Déclencher 1 cycle d'exécution autonome (wake_goal)"
        >
          <Play size={16} />
          <span>{isWaking ? "Exécution..." : "Wake Loop"}</span>
        </button>
      </div>
    </header>
  );
}
