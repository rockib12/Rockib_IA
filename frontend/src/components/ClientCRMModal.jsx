import React, { useState, useEffect, useCallback } from 'react';
import { 
  Briefcase, 
  Users, 
  Phone, 
  MessageSquare, 
  CheckCircle2, 
  ExternalLink, 
  Copy, 
  Check, 
  Download, 
  Clock, 
  DollarSign, 
  X, 
  Sparkles,
  Search,
  Filter,
  ArrowUpRight
} from 'lucide-react';
import { authFetch } from '../lib/authFetch';

export default function ClientCRMModal({
  isOpen,
  onClose,
  workspaceId,
  onNotify,
}) {
  const [activeTab, setActiveTab] = useState('pipeline'); // 'pipeline' | 'embed' | 'roi' | 'proposal'
  const [selectedSiteKey, setSelectedSiteKey] = useState('rockib-portfolio');
  const [availableSites, setAvailableSites] = useState([]);
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [copiedSnippet, setCopiedSnippet] = useState(false);

  // P8 : Auto-Proposal Engine State
  const [propClientName, setPropClientName] = useState('Entreprise Partenaire');
  const [propCompany, setPropCompany] = useState('Groupe B2B');
  const [propBrief, setPropBrief] = useState('Plateforme SaaS e-commerce multi-boutique avec agent IA WhatsApp et paiement sécurisé');
  const [generatingProposal, setGeneratingProposal] = useState(false);
  const [generatedProposal, setGeneratedProposal] = useState(null);

  const handleGenerateProposalP8 = async (e) => {
    if (e) e.preventDefault();
    if (!propBrief.trim()) return;
    try {
      setGeneratingProposal(true);
      const res = await authFetch('/api/v1/inbound/proposal/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_name: propClientName || 'Client',
          company_name: propCompany || null,
          project_brief: propBrief,
          currency: 'EUR',
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setGeneratedProposal(data);
      if (onNotify) onNotify(`Proposition P8 générée (${data.estimated_budget_eur} € / ${data.estimated_days}j)`, 'success');
    } catch (err) {
      if (onNotify) onNotify(`Erreur devis P8: ${err.message}`, 'error');
    } finally {
      setGeneratingProposal(false);
    }
  };

  // Charger la liste des sites disponibles
  const fetchSites = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/inbound/sites');
      if (res.ok) {
        const data = await res.json();
        if (data.sites && data.sites.length > 0) {
          setAvailableSites(data.sites);
        }
      }
    } catch (e) {
      console.warn("Erreur chargement sites:", e);
    }
  }, []);

  // Charger les prospects pour le site sélectionné
  const fetchLeads = useCallback(async () => {
    if (!selectedSiteKey) return;
    try {
      setLoading(true);
      const res = await authFetch(`/api/v1/inbound/sites/${selectedSiteKey}/leads`);
      if (res.ok) {
        const data = await res.json();
        setLeads(data);
      } else {
        // Mode hors ligne ou initial
        setLeads([]);
      }
    } catch (e) {
      console.warn("Erreur chargement leads:", e);
    } finally {
      setLoading(false);
    }
  }, [selectedSiteKey]);

  useEffect(() => {
    if (isOpen) {
      fetchSites();
      fetchLeads();
    }
  }, [isOpen, fetchSites, fetchLeads]);

  // Mettre à jour le statut d'un prospect
  const handleUpdateStatus = async (leadId, newStatus) => {
    try {
      const res = await authFetch(`/api/v1/inbound/sites/${selectedSiteKey}/leads/${leadId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        if (onNotify) onNotify(`Statut prospect actualisé : ${newStatus}`, 'success');
        fetchLeads();
      } else {
        if (onNotify) onNotify("Échec de mise à jour du statut", 'error');
      }
    } catch (err) {
      if (onNotify) onNotify(`Erreur: ${err.message}`, 'error');
    }
  };

  // Copier le snippet d'intégration
  const handleCopySnippet = () => {
    const snippet = `<script src="${window.location.origin}/static/rockib-concierge.js" data-site-key="${selectedSiteKey}" defer></script>`;
    navigator.clipboard.writeText(snippet);
    setCopiedSnippet(true);
    if (onNotify) onNotify("Snippet JavaScript copié dans le presse-papier !", "success");
    setTimeout(() => setCopiedSnippet(false), 3000);
  };

  if (!isOpen) return null;

  // Filtrage des prospects
  const filteredLeads = leads.filter((ld) => {
    const matchesSearch = 
      (ld.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (ld.phone || '').includes(searchQuery) ||
      (ld.email || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (ld.notes || '').toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || ld.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // Calcul des KPIs
  const totalLeads = leads.length;
  const newLeads = leads.filter(l => l.status === 'received').length;
  const contactedLeads = leads.filter(l => l.status === 'contacted').length;
  const convertedLeads = leads.filter(l => l.status === 'converted').length;
  const conversionRate = totalLeads > 0 ? Math.round((convertedLeads / totalLeads) * 100) : 0;
  const hoursSaved = (totalLeads * 0.4).toFixed(1); // ~24 min gagnées par prospect qualifié

  return (
    <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 1100 }}>
      <div 
        className="modal-window"
        style={{
          maxWidth: '1050px',
          width: '95%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(6, 10, 20, 0.95)',
          border: '1px solid rgba(0, 240, 255, 0.3)',
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.8), 0 0 30px rgba(0, 240, 255, 0.15)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* HEADER */}
        <div 
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(0, 255, 157, 0.2))',
                border: '1px solid var(--neon-cyan)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Briefcase size={22} color="var(--neon-cyan)" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ fontSize: '1.2rem', color: '#FFFFFF', margin: 0, fontWeight: 700 }}>
                  Espace Commercial & CRM Prospects
                </h3>
                <span
                  style={{
                    fontSize: '0.7rem',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    background: 'rgba(0, 255, 157, 0.15)',
                    color: 'var(--neon-emerald)',
                    fontWeight: 700,
                    border: '1px solid rgba(0, 255, 157, 0.3)',
                  }}
                >
                  PROD B2B
                </span>
              </div>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Gestion centralisée des contacts capturés 24h/24, suivi commercial et intégration web.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <a
              href="/pro.html"
              target="_blank"
              rel="noreferrer"
              className="btn-cyber secondary"
              style={{ fontSize: '0.78rem', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px' }}
              title="Ouvrir la page de présentation commerciale pour vos clients"
            >
              <span>Fiche Commerciale</span>
              <ExternalLink size={13} />
            </a>
            <button 
              onClick={onClose} 
              className="control-btn"
              style={{ padding: '6px', borderRadius: '8px' }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* NAVIGATION ONGLETS & SÉLECTEUR SITE */}
        <div
          style={{
            padding: '12px 24px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(3, 5, 12, 0.6)',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          {/* Tabs */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setActiveTab('pipeline')}
              className={`btn-cyber ${activeTab === 'pipeline' ? 'primary' : 'secondary'}`}
              style={{ padding: '6px 14px', fontSize: '0.82rem' }}
            >
              <Users size={14} />
              <span>Pipeline Prospects ({totalLeads})</span>
            </button>

            <button
              onClick={() => setActiveTab('embed')}
              className={`btn-cyber ${activeTab === 'embed' ? 'primary' : 'secondary'}`}
              style={{ padding: '6px 14px', fontSize: '0.82rem' }}
            >
              <Sparkles size={14} />
              <span>Code d'Intégration Web</span>
            </button>

            <button
              onClick={() => setActiveTab('roi')}
              className={`btn-cyber ${activeTab === 'roi' ? 'primary' : 'secondary'}`}
              style={{ padding: '6px 14px', fontSize: '0.82rem' }}
            >
              <DollarSign size={14} />
              <span>Impact Commercial & ROI</span>
            </button>

            <button
              onClick={() => setActiveTab('proposal')}
              className={`btn-cyber ${activeTab === 'proposal' ? 'primary' : 'secondary'}`}
              style={{ padding: '6px 14px', fontSize: '0.82rem' }}
            >
              <Sparkles size={14} />
              <span>⚡ Devis IA Auto (P8)</span>
            </button>
          </div>

          {/* Site Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Site Client :</span>
            <select
              value={selectedSiteKey}
              onChange={(e) => setSelectedSiteKey(e.target.value)}
              className="cyber-input"
              style={{ padding: '5px 12px', fontSize: '0.8rem', minWidth: '170px' }}
            >
              {availableSites.length > 0 ? (
                availableSites.map(s => (
                  <option key={s.site_key} value={s.site_key}>
                    {s.business_name || s.site_key}
                  </option>
                ))
              ) : (
                <>
                  <option value="rockib-portfolio">Portfolio Rockib Quenum</option>
                  <option value="martistore">Boutique MARTISTORE</option>
                  <option value="ywaola-motors">Ywaola Motors (Auto)</option>
                </>
              )}
            </select>
          </div>
        </div>

        {/* MODAL BODY */}
        <div style={{ padding: '24px', overflowY: 'auto', flexGrow: 1 }}>
          {/* TAB 1: PIPELINE PROSPECTS */}
          {activeTab === 'pipeline' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Executive KPI Bar */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px' }}>
                <div className="glass-panel" style={{ padding: '14px 18px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Total Prospects</div>
                  <div className="mono" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--neon-cyan)' }}>
                    {totalLeads}
                  </div>
                </div>

                <div className="glass-panel" style={{ padding: '14px 18px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Nouveaux (À Traiter)</div>
                  <div className="mono" style={{ fontSize: '1.6rem', fontWeight: 800, color: '#F59E0B' }}>
                    {newLeads}
                  </div>
                </div>

                <div className="glass-panel" style={{ padding: '14px 18px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Clients Convertis</div>
                  <div className="mono" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--neon-emerald)' }}>
                    {convertedLeads}
                  </div>
                </div>

                <div className="glass-panel" style={{ padding: '14px 18px', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Temps Gagné Commercial</div>
                  <div className="mono" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--neon-purple)' }}>
                    +{hoursSaved}h
                  </div>
                </div>
              </div>

              {/* Action & Filter Bar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1 }}>
                  <div style={{ position: 'relative', width: '280px' }}>
                    <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
                    <input
                      type="text"
                      placeholder="Rechercher par nom, téléphone, email..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="cyber-input"
                      style={{ paddingLeft: '32px', width: '100%', fontSize: '0.8rem' }}
                    />
                  </div>

                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="cyber-input"
                    style={{ fontSize: '0.8rem', padding: '6px 10px' }}
                  >
                    <option value="all">Tous les statuts</option>
                    <option value="received">Nouveau (Reçu)</option>
                    <option value="contacted">Contacté</option>
                    <option value="converted">Converti</option>
                    <option value="archived">Archivé</option>
                  </select>
                </div>

                <a
                  href={`/api/v1/inbound/sites/${selectedSiteKey}/leads/export`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-cyber secondary"
                  style={{ fontSize: '0.8rem', padding: '6px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Download size={14} />
                  <span>Exporter CSV</span>
                </a>
              </div>

              {/* Leads Cards Grid */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {loading ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                    Chargement des contacts en cours...
                  </div>
                ) : filteredLeads.length === 0 ? (
                  <div 
                    className="glass-panel" 
                    style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}
                  >
                    <div style={{ fontSize: '1.8rem', marginBottom: '8px' }}>📭</div>
                    <div style={{ fontWeight: 600, color: '#fff', marginBottom: '4px' }}>Aucun prospect pour ce filtre</div>
                    <div style={{ fontSize: '0.8rem' }}>
                      Les visiteurs qui laisseront leurs coordonnées sur votre site apparaîtront immédiatement ici.
                    </div>
                  </div>
                ) : (
                  filteredLeads.map((ld) => {
                    const cleanPhone = (ld.phone || '').replace(/[^0-9+]/g, '');
                    const waLink = cleanPhone 
                      ? `https://wa.me/${cleanPhone.replace('+', '')}?text=${encodeURIComponent(`Bonjour ${ld.name || ''}, suite à votre demande sur notre site, je me permets de vous contacter.`)}` 
                      : null;
                    const phoneCallLink = cleanPhone ? `tel:${cleanPhone}` : null;

                    return (
                      <div
                        key={ld.id}
                        className="glass-panel"
                        style={{
                          padding: '16px 20px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '12px',
                          borderLeft: `4px solid ${
                            ld.status === 'converted' ? 'var(--neon-emerald)' :
                            ld.status === 'contacted' ? 'var(--neon-cyan)' :
                            ld.status === 'received' ? '#F59E0B' : 'var(--text-muted)'
                          }`
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px' }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                              <strong style={{ fontSize: '1rem', color: '#FFFFFF' }}>
                                {ld.name || 'Prospect Anonyme'}
                              </strong>
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  padding: '2px 7px',
                                  borderRadius: '4px',
                                  background: ld.channel === 'voice' ? 'rgba(168, 85, 247, 0.15)' : 'rgba(0, 240, 255, 0.12)',
                                  color: ld.channel === 'voice' ? 'var(--neon-purple)' : 'var(--neon-cyan)',
                                  fontWeight: 700,
                                }}
                              >
                                {ld.channel === 'voice' ? '🎙️ VOCAL' : '💬 CHAT ÉCRIT'}
                              </span>
                              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                {ld.created_at ? new Date(ld.created_at).toLocaleString('fr-FR') : 'Récemment'}
                              </span>
                            </div>

                            <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '4px', display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
                              {ld.phone && <span>📞 <strong>{ld.phone}</strong></span>}
                              {ld.email && <span>✉️ <strong>{ld.email}</strong></span>}
                              {ld.budget && <span style={{ color: 'var(--neon-emerald)' }}>💰 Budget : {ld.budget}</span>}
                            </div>
                          </div>

                          {/* Statut Selector */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Statut :</span>
                            <select
                              value={ld.status}
                              onChange={(e) => handleUpdateStatus(ld.id, e.target.value)}
                              className="cyber-input"
                              style={{
                                fontSize: '0.78rem',
                                padding: '4px 8px',
                                color: ld.status === 'converted' ? 'var(--neon-emerald)' : ld.status === 'contacted' ? 'var(--neon-cyan)' : '#F59E0B',
                                fontWeight: 700,
                              }}
                            >
                              <option value="received">Reçu (Nouveau)</option>
                              <option value="contacted">Contacté</option>
                              <option value="converted">Converti (Client)</option>
                              <option value="archived">Archivé / Non Retenu</option>
                            </select>
                          </div>
                        </div>

                        {/* Contenu de la demande / Notes */}
                        {ld.notes && (
                          <div
                            style={{
                              background: 'rgba(0, 0, 0, 0.35)',
                              padding: '10px 14px',
                              borderRadius: '8px',
                              fontSize: '0.82rem',
                              color: '#CBD5E1',
                              borderLeft: '2px solid rgba(255, 255, 255, 0.1)',
                            }}
                          >
                            <strong>Demande du prospect :</strong> {ld.notes}
                          </div>
                        )}

                        {/* Boutons d'Action Directe 1-Clic */}
                        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', paddingTop: '4px' }}>
                          {waLink && (
                            <a
                              href={waLink}
                              target="_blank"
                              rel="noreferrer"
                              className="btn-cyber"
                              style={{
                                background: 'rgba(37, 211, 102, 0.15)',
                                borderColor: 'rgba(37, 211, 102, 0.4)',
                                color: '#25D366',
                                fontSize: '0.75rem',
                                padding: '5px 12px',
                                textDecoration: 'none',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '6px',
                                fontWeight: 600,
                              }}
                            >
                              <MessageSquare size={13} />
                              <span>Relancer sur WhatsApp</span>
                            </a>
                          )}

                          {phoneCallLink && (
                            <a
                              href={phoneCallLink}
                              className="btn-cyber secondary"
                              style={{
                                fontSize: '0.75rem',
                                padding: '5px 12px',
                                textDecoration: 'none',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '6px',
                              }}
                            >
                              <Phone size={13} />
                              <span>Appeler Directement</span>
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* TAB 2: CODE D'INTÉGRATION */}
          {activeTab === 'embed' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
              <div className="glass-panel" style={{ padding: '24px' }}>
                <h4 style={{ color: '#fff', fontSize: '1.05rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={16} color="var(--neon-cyan)" />
                  <span>Script Prêt à l'Emploi pour le Site : {selectedSiteKey}</span>
                </h4>
                <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                  Copiez cette ligne unique et collez-la juste avant la balise <code>&lt;/body&gt;</code> de votre site web. Le widget se chargera immédiatement.
                </p>

                <div 
                  className="mono"
                  style={{
                    background: '#020408',
                    border: '1px solid rgba(0, 240, 255, 0.3)',
                    borderRadius: '8px',
                    padding: '14px 18px',
                    fontSize: '0.82rem',
                    color: 'var(--neon-emerald)',
                    wordBreak: 'break-all',
                    marginBottom: '16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '12px',
                  }}
                >
                  <span>
                    &lt;script src="{window.location.origin}/static/rockib-concierge.js" data-site-key="{selectedSiteKey}" defer&gt;&lt;/script&gt;
                  </span>
                  <button
                    onClick={handleCopySnippet}
                    className="btn-cyber primary"
                    style={{ padding: '6px 12px', fontSize: '0.75rem', flexShrink: 0 }}
                  >
                    {copiedSnippet ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedSnippet ? "Copié !" : "Copier"}</span>
                  </button>
                </div>
              </div>

              {/* Guide CMS */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                <div className="glass-panel" style={{ padding: '18px' }}>
                  <strong style={{ color: '#fff', fontSize: '0.9rem', display: 'block', marginBottom: '6px' }}>
                    WordPress / WooCommerce
                  </strong>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Allez dans <em>Extensions &gt; Ajouter</em>, installez "WPCode" ou collez le script dans <code>footer.php</code>.
                  </p>
                </div>

                <div className="glass-panel" style={{ padding: '18px' }}>
                  <strong style={{ color: '#fff', fontSize: '0.9rem', display: 'block', marginBottom: '6px' }}>
                    Shopify / Boutique
                  </strong>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Dans votre thème, ouvrez <code>theme.liquid</code> et collez le script juste avant <code>&lt;/body&gt;</code>.
                  </p>
                </div>

                <div className="glass-panel" style={{ padding: '18px' }}>
                  <strong style={{ color: '#fff', fontSize: '0.9rem', display: 'block', marginBottom: '6px' }}>
                    Wix / Squarespace / Webflow
                  </strong>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Dans les paramètres du site &gt; <em>Code personnalisé</em>, ajoutez le script en pied de page (Footer).
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: IMPACT ROI & VALEUR AJOUTÉE */}
          {activeTab === 'roi' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="glass-panel" style={{ padding: '24px' }}>
                <h4 style={{ color: '#fff', fontSize: '1.05rem', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <DollarSign size={16} color="var(--neon-emerald)" />
                  <span>Rapport Financier & Rentabilité Commerciale</span>
                </h4>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '20px' }}>
                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Valeur Pipeline Estimée</div>
                    <div className="mono" style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--neon-emerald)', marginTop: '4px' }}>
                      {(totalLeads * 50000).toLocaleString('fr-FR')} FCFA
                    </div>
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Sur base moyenne de 50 000 FCFA / client</span>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Coût IA Moyen par Conversation</div>
                    <div className="mono" style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--neon-cyan)', marginTop: '4px' }}>
                      $0.0035 / conv
                    </div>
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Grille officielle Groq Llama 3.3</span>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Taux d'Amortissement</div>
                    <div className="mono" style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--neon-purple)', marginTop: '4px' }}>
                      100% AMORTI
                    </div>
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Rentabilisé dès 1 vente additionnelle</span>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '10px' }}>
                  <div style={{ fontSize: '0.85rem', color: '#CBD5E1' }}>
                    Vous souhaitez présenter cette offre à d'autres clients ou partenaires ?
                  </div>
                  <a
                    href="/pro.html"
                    target="_blank"
                    rel="noreferrer"
                    className="btn-cyber primary"
                    style={{ fontSize: '0.82rem', padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <span>Ouvrir la Landing Page Commerciale</span>
                    <ArrowUpRight size={14} />
                  </a>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: P8 — AUTO-PROPOSAL ENGINE (GÉNÉRATEUR DE DEVIS & ARCHITECTURE IA) */}
          {activeTab === 'proposal' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              <form onSubmit={handleGenerateProposalP8} className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <h4 style={{ color: '#fff', fontSize: '1.02rem', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Sparkles size={16} color="var(--neon-cyan)" />
                  <span>P8 — Moteur Autonome de Proposition Technique & Chiffrage Commercial</span>
                </h4>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Nom du Client / Contact</label>
                    <input
                      type="text"
                      value={propClientName}
                      onChange={(e) => setPropClientName(e.target.value)}
                      className="cyber-input"
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Société / Organisation</label>
                    <input
                      type="text"
                      value={propCompany}
                      onChange={(e) => setPropCompany(e.target.value)}
                      className="cyber-input"
                      style={{ width: '100%' }}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Cahier des Charges / Besoin Exprimé par le Prospect (analysé par Gemma-2 768d) :
                  </label>
                  <textarea
                    rows={3}
                    value={propBrief}
                    onChange={(e) => setPropBrief(e.target.value)}
                    className="cyber-input"
                    style={{ width: '100%', resize: 'vertical' }}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="submit"
                    disabled={generatingProposal || !propBrief.trim()}
                    className="btn-cyber primary"
                    style={{ padding: '8px 18px', fontSize: '0.84rem' }}
                  >
                    <Sparkles size={14} />
                    <span>{generatingProposal ? 'Génération Architecturale en cours...' : 'Générer Proposition & Chiffrage'}</span>
                  </button>
                </div>
              </form>

              {generatedProposal && (
                <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px', borderLeft: '4px solid var(--neon-emerald)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                    <div>
                      <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--neon-cyan)' }}>{generatedProposal.proposal_ref}</span>
                      <h4 style={{ margin: '2px 0 0 0', color: '#fff', fontSize: '1.05rem' }}>
                        Architecture & Chiffrage pour {generatedProposal.client_name}
                      </h4>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div className="mono" style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--neon-emerald)' }}>
                          {generatedProposal.estimated_budget_eur.toLocaleString('fr-FR')} € HT
                        </div>
                        <div className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          ({generatedProposal.estimated_budget_fcfa.toLocaleString('fr-FR')} FCFA • {generatedProposal.estimated_days} jours-homme)
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(generatedProposal.proposal_markdown || '');
                          if (onNotify) onNotify('Proposition Markdown copiée dans le presse-papier !', 'success');
                        }}
                        className="btn-cyber secondary"
                        style={{ padding: '6px 12px', fontSize: '0.78rem' }}
                      >
                        <Copy size={13} />
                        <span>Copier Markdown</span>
                      </button>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {(generatedProposal.recommended_stack || []).map((tech, i) => (
                      <span
                        key={i}
                        className="mono"
                        style={{
                          fontSize: '0.7rem',
                          padding: '3px 8px',
                          borderRadius: '6px',
                          background: 'rgba(0, 240, 255, 0.1)',
                          border: '1px solid rgba(0, 240, 255, 0.3)',
                          color: '#00F0FF',
                        }}
                      >
                        {tech}
                      </span>
                    ))}
                  </div>

                  <pre
                    className="mono"
                    style={{
                      margin: 0,
                      padding: '12px',
                      borderRadius: '8px',
                      background: 'rgba(3, 6, 14, 0.9)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      color: '#E2E8F0',
                      fontSize: '0.74rem',
                      maxHeight: '260px',
                      overflowY: 'auto',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {generatedProposal.proposal_markdown}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
