import React, { useState, useEffect } from 'react';
import { 
  Boxes, 
  Layers, 
  Activity, 
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
  Share2,
  Lock,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  LogOut,
  User as UserIcon,
  Sparkles,
  ShieldCheck,
} from 'lucide-react';

export default function CockpitSidebar({
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
  isObservabilityOpen = false,
  onToggleObservability,
  isClientCRMOpen = false,
  onToggleClientCRM,
}) {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    return localStorage.getItem('rockib_sidebar_collapsed') === 'true';
  });

  const toggleCollapsed = () => {
    const nextState = !isCollapsed;
    setIsCollapsed(nextState);
    localStorage.setItem('rockib_sidebar_collapsed', String(nextState));
    // Déclenche l'événement resize pour que Three.js adapte instantanément son canvas WebGL
    setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 150);
  };

  const isHealthy = healthStatus?.status === 'healthy';

  return (
    <aside 
      className={`cockpit-sidebar ${isCollapsed ? 'collapsed' : 'expanded'}`}
      style={{
        width: isCollapsed ? '72px' : '260px',
        minWidth: isCollapsed ? '72px' : '260px',
        height: '100vh',
        background: 'rgba(5, 9, 18, 0.94)',
        backdropFilter: 'blur(20px)',
        borderRight: '1px solid rgba(0, 240, 255, 0.16)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        zIndex: 50,
        transition: 'width 0.22s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.22s cubic-bezier(0.4, 0, 0.2, 1)',
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* 1. TOP HEADER & BRAND */}
      <div>
        <div 
          style={{
            padding: isCollapsed ? '16px 12px' : '18px 16px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.07)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: isCollapsed ? 'center' : 'space-between',
            gap: '10px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
            <div 
              className="brand-logo-glow"
              style={{
                width: '36px',
                height: '36px',
                minWidth: '36px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #00F0FF, #6366F1)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 16px rgba(0, 240, 255, 0.45)',
              }}
            >
              <Boxes size={20} color="#FFFFFF" />
            </div>

            {!isCollapsed && (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span 
                  style={{
                    fontFamily: 'var(--font-heading)',
                    fontSize: '1.05rem',
                    fontWeight: 800,
                    letterSpacing: '-0.02em',
                    background: 'linear-gradient(135deg, #FFFFFF, #94A3B8)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    lineHeight: 1.1,
                  }}
                >
                  ROCKIB IA
                </span>
                <span 
                  style={{
                    fontSize: '0.62rem',
                    fontWeight: 700,
                    color: 'var(--neon-cyan)',
                    letterSpacing: '0.08em',
                    marginTop: '2px',
                  }}
                >
                  3D META-COCKPIT
                </span>
              </div>
            )}
          </div>

          <button
            onClick={toggleCollapsed}
            className="control-btn"
            style={{
              padding: '6px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              background: 'rgba(255, 255, 255, 0.03)',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title={isCollapsed ? "Déplier la barre latérale" : "Réduire la barre latérale"}
          >
            {isCollapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
          </button>
        </div>

        {/* 2. REAL-TIME SYSTEM METRICS CARD */}
        {!isCollapsed ? (
          <div 
            style={{
              margin: '12px 14px',
              padding: '10px 12px',
              background: 'rgba(8, 14, 26, 0.65)',
              border: '1px solid rgba(255, 255, 255, 0.06)',
              borderRadius: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span
                  style={{
                    display: 'inline-block',
                    width: '7px',
                    height: '7px',
                    borderRadius: '50%',
                    backgroundColor: isHealthy ? 'var(--neon-emerald)' : '#F59E0B',
                    boxShadow: `0 0 8px ${isHealthy ? 'var(--neon-emerald)' : '#F59E0B'}`,
                  }}
                />
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Système :</span>
              </div>
              <strong style={{ fontSize: '0.72rem', color: isHealthy ? 'var(--neon-emerald)' : '#F59E0B' }}>
                {isHealthy ? 'ONLINE' : 'DÉGRADÉ'}
              </strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '6px', borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Activity size={12} color="var(--neon-cyan)" />
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Agents:</span>
                <strong style={{ fontSize: '0.75rem', color: '#fff' }}>{agentsCount}</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Layers size={12} color="var(--neon-purple)" />
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Goals:</span>
                <strong style={{ fontSize: '0.75rem', color: '#fff' }}>{goalsCount}</strong>
              </div>
            </div>
          </div>
        ) : (
          <div 
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 0',
              borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
            }}
            title={`Système: ${isHealthy ? 'ONLINE' : 'DÉGRADÉ'} | Agents: ${agentsCount} | Goals: ${goalsCount}`}
          >
            <span
              style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: isHealthy ? 'var(--neon-emerald)' : '#F59E0B',
                boxShadow: `0 0 8px ${isHealthy ? 'var(--neon-emerald)' : '#F59E0B'}`,
              }}
            />
            <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--neon-cyan)', fontWeight: 700 }}>
              {agentsCount}A
            </span>
          </div>
        )}

        {/* 3. NAVIGATION & ACTION SECTIONS (SCROLLABLE) */}
        <div 
          style={{
            padding: isCollapsed ? '8px 8px' : '6px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            maxHeight: 'calc(100vh - 230px)',
            overflowY: 'auto',
          }}
        >
          {/* SECTION: CONSTELLATION 3D */}
          <div>
            {!isCollapsed && (
              <span 
                style={{
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'rgba(255, 255, 255, 0.4)',
                  paddingLeft: '8px',
                  display: 'block',
                  marginBottom: '6px',
                }}
              >
                Constellation 3D
              </span>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <button 
                onClick={onResetCamera} 
                className="sidebar-btn"
                title="Recentrer la caméra sur la constellation d'agents"
              >
                <Compass size={17} color="var(--neon-cyan)" />
                {!isCollapsed && <span>Recentrer</span>}
              </button>

              <button 
                onClick={onToggleSplitView} 
                className={`sidebar-btn ${isSplitView ? 'active' : ''}`}
                title={isSplitView ? "Mode Plein Écran 3D" : "Mode Split Console DAG"}
              >
                {isSplitView ? <Maximize2 size={17} /> : <Columns size={17} />}
                {!isCollapsed && <span>{isSplitView ? "3D Full" : "Split DAG"}</span>}
              </button>
            </div>
          </div>

          {/* SECTION: GOUVERNANCE & ANALYTIQUE */}
          <div>
            {!isCollapsed && (
              <span 
                style={{
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'rgba(255, 255, 255, 0.4)',
                  paddingLeft: '8px',
                  display: 'block',
                  marginBottom: '6px',
                }}
              >
                Gouvernance
              </span>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <button
                onClick={onToggleGovernance}
                className={`sidebar-btn ${isGovernanceOpen ? 'active' : ''}`}
                title={currentUser ? "Centre d'Arbitrage Déterministe & Décisions" : "Arbitrage (Verrouillé — Connexion requise)"}
                style={!currentUser ? { opacity: 0.7 } : {}}
              >
                {currentUser ? <Scale size={17} color="var(--neon-purple)" /> : <Lock size={15} color="#F59E0B" />}
                {!isCollapsed && (
                  <span style={!currentUser ? { color: '#F59E0B' } : {}}>
                    Arbitrage
                  </span>
                )}
              </button>

              <button
                onClick={onToggleDashboard}
                className={`sidebar-btn ${isDashboardOpen ? 'active' : ''}`}
                title="Tableau de bord temps réel"
              >
                <BarChart3 size={17} color="var(--neon-cyan)" />
                {!isCollapsed && <span>Dashboard</span>}
              </button>

              <button
                onClick={onToggleObservability}
                className={`sidebar-btn ${isObservabilityOpen ? 'active' : ''}`}
                title="Observabilité Unifiée, Télémétrie Groq LLM & Budgets"
              >
                <Activity size={17} color="var(--neon-emerald)" />
                {!isCollapsed && <span>Observabilité</span>}
              </button>

              <button
                onClick={onToggleTerminal}
                className={`sidebar-btn ${isTerminalOpen ? 'active' : ''}`}
                title={currentUser ? "Terminal de commandes (Ctrl+`)" : "Terminal (Verrouillé — Connexion requise)"}
                style={!currentUser ? { opacity: 0.7 } : {}}
              >
                {currentUser ? <Terminal size={17} /> : <Lock size={15} color="#F59E0B" />}
                {!isCollapsed && <span style={!currentUser ? { color: '#F59E0B' } : {}}>Terminal</span>}
              </button>

              <button
                onClick={onToggleTimeline}
                className={`sidebar-btn ${isTimelineOpen ? 'active' : ''}`}
                title="Timeline d'événements (audit trail)"
              >
                <Clock size={17} />
                {!isCollapsed && <span>Timeline</span>}
              </button>

              <button
                onClick={onToggleConnectors}
                className={`sidebar-btn ${isConnectorsOpen ? 'active' : ''}`}
                title={currentUser ? "Hub Réseaux Sociaux & Meta Ads (HMAC-SHA256)" : "Réseaux (Verrouillé — Connexion requise)"}
                style={!currentUser ? { opacity: 0.7 } : {}}
              >
                {currentUser ? <Share2 size={17} /> : <Lock size={15} color="#F59E0B" />}
                {!isCollapsed && <span style={!currentUser ? { color: '#F59E0B' } : {}}>Réseaux</span>}
              </button>
            </div>
          </div>

          {/* SECTION: COMMERCIAL & B2B */}
          <div>
            {!isCollapsed && (
              <span 
                style={{
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'rgba(255, 255, 255, 0.4)',
                  paddingLeft: '8px',
                  display: 'block',
                  marginBottom: '6px',
                }}
              >
                Commercial B2B
              </span>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <button
                onClick={onToggleClientCRM}
                className={`sidebar-btn ${isClientCRMOpen ? 'active' : ''}`}
                title="Espace Commercial B2B, CRM Prospects 24h/24 & Intégration Web"
                style={{
                  border: isClientCRMOpen ? '1px solid var(--neon-emerald)' : '1px solid rgba(0, 255, 157, 0.25)',
                  background: isClientCRMOpen ? 'rgba(0, 255, 157, 0.15)' : 'rgba(0, 255, 157, 0.05)',
                }}
              >
                <Briefcase size={17} color="var(--neon-emerald)" />
                {!isCollapsed && (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                    <span style={{ color: 'var(--neon-emerald)', fontWeight: 600 }}>CRM Clients</span>
                    <span 
                      style={{
                        fontSize: '0.62rem',
                        fontWeight: 800,
                        background: 'var(--neon-emerald)',
                        color: '#030508',
                        padding: '1px 5px',
                        borderRadius: '4px',
                      }}
                    >
                      LEADS
                    </span>
                  </div>
                )}
              </button>

              <a
                href="/pro.html"
                target="_blank"
                rel="noreferrer"
                className="sidebar-btn"
                title="Ouvrir la page de présentation commerciale pour vos clients"
                style={{ textDecoration: 'none' }}
              >
                <ExternalLink size={16} color="var(--neon-cyan)" />
                {!isCollapsed && <span>Offre Client B2B</span>}
              </a>
            </div>
          </div>

          {/* SECTION: ACTIONS RAPIDES */}
          <div>
            {!isCollapsed && (
              <span 
                style={{
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: 'rgba(255, 255, 255, 0.4)',
                  paddingLeft: '8px',
                  display: 'block',
                  marginBottom: '6px',
                }}
              >
                Exécution
              </span>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <button 
                onClick={onOpenCreateGoalModal} 
                className="sidebar-btn"
                style={!currentUser ? { opacity: 0.7 } : {}}
                title={currentUser ? "Assigner une nouvelle mission DAG à un agent" : "+ Mission (Verrouillé)"}
              >
                {currentUser ? <Target size={17} color="var(--neon-cyan)" /> : <Lock size={15} color="#F59E0B" />}
                {!isCollapsed && <span style={!currentUser ? { color: '#F59E0B' } : {}}>+ Mission</span>}
              </button>

              <button 
                onClick={onOpenSpawnModal} 
                className="sidebar-btn"
                style={!currentUser ? { opacity: 0.7 } : { background: 'rgba(168, 85, 247, 0.1)', borderColor: 'rgba(168, 85, 247, 0.3)' }}
                title={currentUser ? "Matérialiser un nouvel agent dans la matrice 3D" : "Déployer (Verrouillé)"}
              >
                {currentUser ? <Plus size={17} color="var(--neon-purple)" /> : <Lock size={15} color="#F59E0B" />}
                {!isCollapsed && <span style={!currentUser ? { color: '#F59E0B' } : { color: 'var(--neon-purple)', fontWeight: 600 }}>Déployer Agent</span>}
              </button>

              <button 
                onClick={onWakeGlobal} 
                disabled={isWaking}
                className="sidebar-btn"
                style={{
                  background: isWaking ? 'rgba(0, 240, 255, 0.2)' : 'linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(0, 255, 157, 0.15))',
                  border: '1px solid var(--neon-cyan)',
                  color: 'var(--neon-cyan)',
                }}
                title={currentUser ? "Déclencher 1 cycle d'exécution autonome (wake_goal)" : "Wake (Verrouillé)"}
              >
                <Play size={16} fill={isWaking ? 'transparent' : 'var(--neon-cyan)'} />
                {!isCollapsed && <span style={{ fontWeight: 700 }}>{isWaking ? "Exécution..." : "Wake Loop"}</span>}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 4. BOTTOM USER PROFILE & AUTH */}
      <div 
        style={{
          padding: isCollapsed ? '14px 10px' : '14px 16px',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(3, 5, 12, 0.8)',
        }}
      >
        {currentUser ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: isCollapsed ? 'center' : 'space-between', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '9px', overflow: 'hidden' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  minWidth: '32px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(168, 85, 247, 0.2))',
                  border: '1px solid var(--neon-cyan)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                title={currentUser.email}
              >
                <UserIcon size={16} color="var(--neon-cyan)" />
              </div>

              {!isCollapsed && (
                <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                    {currentUser.first_name || currentUser.email?.split('@')[0] || 'Pilote'}
                  </span>
                  <span style={{ fontSize: '0.65rem', color: 'var(--neon-emerald)' }}>
                    SESSION ACTIVE
                  </span>
                </div>
              )}
            </div>

            <button
              onClick={onLogout}
              className="control-btn"
              style={{ padding: '6px', borderRadius: '8px' }}
              title="Se déconnecter"
            >
              <LogOut size={15} color="var(--text-muted)" />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuthModal}
            className="btn-cyber"
            style={{
              width: '100%',
              padding: isCollapsed ? '10px 0' : '9px 12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              fontSize: '0.78rem',
              background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(99, 102, 241, 0.25))',
              border: '1px solid var(--neon-cyan)',
              color: 'var(--neon-cyan)',
            }}
            title="Se connecter ou créer un compte opérateur"
          >
            <Lock size={14} />
            {!isCollapsed && <span>Connexion</span>}
          </button>
        )}
      </div>
    </aside>
  );
}
