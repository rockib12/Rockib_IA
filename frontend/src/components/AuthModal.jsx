import React, { useState } from 'react';
import { Lock, Mail, User, Key, X, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react';

export default function AuthModal({
  isOpen,
  onClose,
  onLoginSuccess,
}) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === 'login') {
        const res = await fetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email.trim(), password }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || "Échec de connexion : vérifiez vos identifiants.");
        }

        const tokenData = await res.json();
        localStorage.setItem('rockib_token', tokenData.access_token);

        // Récupérer le profil utilisateur
        const meRes = await fetch('/api/v1/auth/me', {
          headers: { Authorization: `Bearer ${tokenData.access_token}` },
        });
        const userData = meRes.ok ? await meRes.json() : { email };

        onLoginSuccess(userData);
        onClose();
      } else {
        // Inscription
        const res = await fetch('/api/v1/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: email.trim(),
            password,
            first_name: firstName.trim() || undefined,
            last_name: lastName.trim() || undefined,
          }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || "Impossible de créer le compte.");
        }

        const tokenData = await res.json();
        localStorage.setItem('rockib_token', tokenData.access_token);

        const userData = { email, first_name: firstName, last_name: lastName };
        onLoginSuccess(userData);
        onClose();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-window" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '440px' }}>
        {/* En-tête */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ 
              width: '36px', 
              height: '36px', 
              borderRadius: '10px', 
              background: 'linear-gradient(135deg, var(--neon-cyan), var(--neon-indigo))',
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              boxShadow: '0 0 16px rgba(0, 240, 255, 0.35)'
            }}>
              <Lock size={18} color="#FFFFFF" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.1rem', color: '#FFFFFF' }}>
                {mode === 'login' ? 'Authentification Cockpit' : 'Créer un Compte Pilote'}
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Accès au réseau souverain d'agents autonomes
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

        {/* Onglets de mode */}
        <div style={{ 
          display: 'flex', 
          borderBottom: '1px solid var(--border-subtle)',
          padding: '0 24px',
          background: 'rgba(0, 0, 0, 0.2)' 
        }}>
          <button
            type="button"
            className={`tab-btn ${mode === 'login' ? 'active' : ''}`}
            onClick={() => { setMode('login'); setError(null); }}
            style={{ flex: 1 }}
          >
            Connexion
          </button>
          <button
            type="button"
            className={`tab-btn ${mode === 'register' ? 'active' : ''}`}
            onClick={() => { setMode('register'); setError(null); }}
            style={{ flex: 1 }}
          >
            Inscription
          </button>
        </div>

        {/* Formulaire */}
        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ padding: '20px 24px' }}>
            {error && (
              <div style={{ 
                background: 'rgba(244, 63, 94, 0.15)', 
                border: '1px solid rgba(244, 63, 94, 0.4)', 
                borderRadius: '8px', 
                padding: '10px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: '#FECDD3',
                fontSize: '0.82rem'
              }}>
                <AlertCircle size={16} color="var(--neon-rose)" />
                <span>{error}</span>
              </div>
            )}

            {mode === 'register' && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label>PRÉNOM</label>
                  <input 
                    type="text"
                    className="form-input"
                    placeholder="Prénom"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>NOM</label>
                  <input 
                    type="text"
                    className="form-input"
                    placeholder="Nom"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className="form-group">
              <label>ADRESSE EMAIL</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="email"
                  className="form-input"
                  style={{ width: '100%', paddingLeft: '36px' }}
                  placeholder="pilote@rockib.ai"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
                <Mail size={16} color="var(--text-muted)" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
              </div>
            </div>

            <div className="form-group">
              <label>MOT DE PASSE</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="password"
                  className="form-input"
                  style={{ width: '100%', paddingLeft: '36px' }}
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <Key size={16} color="var(--text-muted)" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
              </div>
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
              disabled={loading || !email.trim() || !password}
              className="btn-cyber primary"
              style={{ padding: '8px 22px' }}
            >
              <Sparkles size={15} />
              <span>
                {loading 
                  ? "Authentification..." 
                  : mode === 'login' ? "Se Connecter" : "Créer mon Compte"
                }
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
