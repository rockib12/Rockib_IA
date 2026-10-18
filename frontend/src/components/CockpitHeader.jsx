import React, { useState } from 'react';
import { 
  Boxes, 
  Layers, 
  Activity, 
  Sparkles, 
  Play, 
  Plus, 
  Compass, 
  Columns, 
  Maximize2,
  BarChart3,
  Terminal,
  Clock,
  Scale,
  Target,
  Menu,
  X,
  Share2,
  Lock,
} from 'lucide-react';

export default function CockpitHeader({
  agentsCount = 0,
  goalsCount = 0,
  healthStatus = { status: 'healthy', database: 'up', redis: 'up' },
  isSplitView = false,
  onToggleSplitView,
  onOpenSpawnModal,
  onOpenCreateGoalModal,
  onWakeGlobal,
  onResetCamera,
  isWaking = false,
  currentUser = null,
  onOpenAuthModal,
  onLogout,
  isDashboardOpen = false,
  onToggleDashboard,
  isTerminalOpen = false,
  onToggleTerminal,
  isTimelineOpen = false,
  onToggleTimeline,
  isGovernanceOpen = false,
  onToggleGovernance,
  isConnectorsOpen = false,
  onToggleConnectors,
}) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const isHealthy = healthStatus?.status === 'healthy';

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
        <div
          className="metric-pill"
          title={`PostgreSQL: ${healthStatus?.database || 'up'} | Redis: ${healthStatus?.redis || 'up'}`}
        >
          <span
            className="status-dot"
            style={{
              backgroundColor: isHealthy ? 'var(--neon-emerald)' : '#F59E0B',
              boxShadow: `0 0 8px ${isHealthy ? 'var(--neon-emerald)' : '#F59E0B'}`,
            }}
          />
          <span>DB & Redis :</span>
          <strong style={{ color: isHealthy ? 'var(--neon-emerald)' : '#F59E0B' }}>
            {isHealthy ? 'ONLINE' : 'DEGRADED'}
          </strong>
        </div>

        <div className="metric-pill">
          <Activity size={14} color="var(--neon-cyan)" />
          <span>Agents :</span>
          <strong>{agentsCount}</strong>
        </div>

        <div className="metric-pill">
          <Layers size={14} color="var(--neon-purple)" />
          <span>Goals :</span>
          <strong>{goalsCount}</strong>
        </div>
      </div>

      {/* Mobile hamburger */}
      <button
        className="mobile-menu-toggle control-btn"
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
      >
        {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Control Actions */}
      <div className={`header-actions ${isMobileMenuOpen ? 'mobile-open' : ''}`}>
        {/* View Controls Group */}
        <div className="action-group">
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
            title={isSplitView ? "Plein écran 3D" : "Console tactique latérale"}
          >
            {isSplitView ? <Maximize2 size={15} /> : <Columns size={15} />}
            <span>{isSplitView ? "3D Full" : "Split DAG"}</span>
          </button>
        </div>

        {/* Panel Toggles Group */}
        <div className="action-group">
          <button
            onClick={onToggleGovernance}
            className={`btn-cyber ${isGovernanceOpen ? 'active-panel' : 'secondary'}`}
            title="Centre d'Arbitrage Déterministe & Décisions"
          >
            <Scale size={15} />
            <span>Arbitrage</span>
          </button>

          <button
            onClick={onToggleDashboard}
            className={`btn-cyber ${isDashboardOpen ? 'active-panel' : 'secondary'}`}
            title="Tableau de bord temps réel"
          >
            <BarChart3 size={15} />
            <span>Dashboard</span>
          </button>

          <button
            onClick={onToggleTerminal}
            className={`btn-cyber ${isTerminalOpen ? 'active-panel' : 'secondary'}`}
            title="Terminal de commandes (Ctrl+`)"
          >
            <Terminal size={15} />
            <span>Terminal</span>
          </button>

          <button
            onClick={onToggleTimeline}
            className={`btn-cyber ${isTimelineOpen ? 'active-panel' : 'secondary'}`}
            title="Timeline d'événements (audit trail)"
          >
            <Clock size={15} />
            <span>Timeline</span>
          </button>

          <button
            onClick={onToggleConnectors}
            className={`btn-cyber ${isConnectorsOpen ? 'active-panel' : 'secondary'}`}
            title={currentUser ? "Hub Réseaux Sociaux & Meta Ads (HMAC-SHA256)" : "Verrouillé — Connexion requise"}
            style={!currentUser ? { opacity: 0.8, borderColor: 'rgba(245, 158, 11, 0.45)' } : {}}
          >
            {currentUser ? <Share2 size={15} /> : <Lock size={14} color="#F59E0B" />}
            <span style={!currentUser ? { color: '#F59E0B' } : {}}>Réseaux</span>
          </button>
        </div>

        {/* Primary Actions Group */}
        <div className="action-group">
          <button 
            onClick={onOpenCreateGoalModal} 
            className="btn-cyber secondary"
            style={{ borderColor: 'rgba(0, 240, 255, 0.35)' }}
            title="Assigner une nouvelle mission DAG à un agent"
          >
            <Target size={15} />
            <span>+ Mission</span>
          </button>

          <button 
            onClick={onOpenSpawnModal} 
            className="btn-cyber accent-purple"
            title="Matérialiser un nouvel agent dans la matrice 3D"
          >
            <Plus size={16} />
            <span>Déployer</span>
          </button>

          <button 
            onClick={onWakeGlobal} 
            disabled={isWaking}
            className="btn-cyber primary"
            title="Déclencher 1 cycle d'exécution autonome (wake_goal)"
          >
            <Play size={16} />
            <span>{isWaking ? "Exec..." : "Wake"}</span>
          </button>
        </div>

        {/* User Account */}
        {currentUser ? (
          <div className="action-group">
            <div className="metric-pill" style={{ borderColor: 'var(--neon-cyan)', background: 'rgba(0, 240, 255, 0.08)' }}>
              <span className="status-dot" />
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                {currentUser.first_name || currentUser.email?.split('@')[0] || 'Pilote'}
              </span>
            </div>
            <button
              onClick={onLogout}
              className="btn-cyber secondary"
              style={{ padding: '6px 10px', fontSize: '0.75rem' }}
              title="Se déconnecter"
            >
              Logout
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuthModal}
            className="btn-cyber"
            style={{ 
              background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(99, 102, 241, 0.25))',
              border: '1px solid var(--neon-cyan)',
              color: 'var(--neon-cyan)',
              boxShadow: '0 0 14px rgba(0, 240, 255, 0.2)'
            }}
            title="Se connecter ou créer un compte"
          >
            Connexion
          </button>
        )}
      </div>
    </header>
  );
}

