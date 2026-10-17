/**
 * Rockib Quenum — Official Portfolio Concierge & Voice Calling Widget (Vanilla JS)
 * Embeddable script for https://rockib-quenum.netlify.app/
 *
 * Features:
 *   - Text Chatbot with quick chips.
 *   - Live In-Browser Voice Calling (Web Speech Recognition + Speech Synthesis).
 *   - Phone & WhatsApp Callback Scheduling (dispatched to Agence IIA).
 */
(function () {
  'use strict';

  if (window.__ROCKIB_CONCIERGE_LOADED__) return;
  window.__ROCKIB_CONCIERGE_LOADED__ = true;

  const API_BASE = window.ROCKIB_API_URL || (
    window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? window.location.origin
      : 'https://dion-beaverlike-preceptively.ngrok-free.dev'
  );

  const STORAGE_KEY = 'rq_concierge_conv_id';
  let conversationId = sessionStorage.getItem(STORAGE_KEY) || null;
  let isOpen = false;
  let activeTab = 'chat'; // 'chat' | 'voice' | 'callback'

  // Voice Call State
  let voiceSessionId = null;
  let isCalling = false;
  let recognition = null;
  let isSpeaking = false;

  // 1. Scoped CSS
  const styles = `
    .rq-launcher {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      display: flex;
      align-items: center;
      gap: 10px;
      background: #05070B;
      border: 1px solid #00F0FF;
      color: #EDF5FF;
      padding: 10px 18px;
      border-radius: 9999px;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.8), 0 0 16px rgba(0, 240, 255, 0.35);
      font-family: 'Plex Mono', monospace;
      font-size: 13px;
      font-weight: 600;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .rq-launcher:hover {
      transform: translateY(-2px);
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.9), 0 0 25px rgba(0, 255, 157, 0.5);
      border-color: #00FF9D;
    }
    .rq-pulse {
      width: 8px;
      height: 8px;
      background-color: #00FF9D;
      border-radius: 50%;
      box-shadow: 0 0 10px #00FF9D;
      animation: rq-glow 2s infinite;
    }
    @keyframes rq-glow {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(1.2); }
    }
    .rq-window {
      position: fixed;
      bottom: 84px;
      right: 24px;
      width: 390px;
      max-width: calc(100vw - 32px);
      height: 560px;
      max-height: calc(100vh - 120px);
      background: #060912;
      border: 1px solid rgba(0, 240, 255, 0.28);
      border-radius: 14px;
      display: flex;
      flex-direction: column;
      z-index: 999999;
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.9), 0 0 30px rgba(0, 240, 255, 0.18);
      font-family: 'Plex Mono', monospace;
      color: #EDF5FF;
      overflow: hidden;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      opacity: 0;
      pointer-events: none;
      transform: translateY(12px) scale(0.98);
    }
    .rq-window.rq-open {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0) scale(1);
    }
    .rq-header {
      padding: 12px 16px;
      background: #0A101C;
      border-bottom: 1px solid rgba(0, 240, 255, 0.15);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .rq-title {
      font-size: 13px;
      font-weight: 700;
      color: #00F0FF;
      display: flex;
      align-items: center;
      gap: 6px;
      text-shadow: 0 0 10px rgba(0, 240, 255, 0.4);
    }
    .rq-subtitle {
      font-size: 10px;
      color: #7E90A6;
      margin-top: 1px;
    }
    .rq-close {
      background: none;
      border: none;
      color: #7E90A6;
      cursor: pointer;
      font-size: 16px;
      padding: 4px;
      line-height: 1;
      transition: color 0.2s;
    }
    .rq-close:hover {
      color: #00F0FF;
    }
    .rq-tabs {
      display: flex;
      background: #070B14;
      border-bottom: 1px solid rgba(0, 240, 255, 0.15);
    }
    .rq-tab-btn {
      flex: 1;
      background: none;
      border: none;
      color: #7E90A6;
      font-family: inherit;
      font-size: 11px;
      font-weight: 600;
      padding: 10px 0;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }
    .rq-tab-btn.rq-active {
      color: #00F0FF;
      border-bottom-color: #00F0FF;
      background: #0A101C;
      text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
    }
    .rq-tab-btn:hover {
      color: #EDF5FF;
    }
    .rq-panel {
      flex: 1;
      display: none;
      flex-direction: column;
      overflow-y: auto;
    }
    .rq-panel.rq-active {
      display: flex;
    }
    /* Messages / Chat Styles */
    .rq-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .rq-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .rq-msg-assistant {
      align-self: flex-start;
      background: #0A101E;
      border: 1px solid rgba(0, 240, 255, 0.15);
      color: #EDF5FF;
      border-left: 2px solid #00F0FF;
    }
    .rq-msg-user {
      align-self: flex-end;
      background: linear-gradient(135deg, #00F0FF 0%, #00FF9D 100%);
      color: #03070E;
      font-weight: 700;
      box-shadow: 0 0 14px rgba(0, 240, 255, 0.35);
    }
    .rq-suggestions {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 4px;
    }
    .rq-chip {
      background: #080D1A;
      border: 1px solid rgba(0, 240, 255, 0.15);
      color: #94A3B8;
      font-size: 11px;
      padding: 7px 10px;
      border-radius: 6px;
      cursor: pointer;
      text-align: left;
      font-family: inherit;
      transition: all 0.2s;
    }
    .rq-chip:hover {
      background: rgba(0, 240, 255, 0.08);
      border-color: #00F0FF;
      color: #00F0FF;
      box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
    }
    .rq-input-area {
      padding: 12px;
      background: #0A101C;
      border-top: 1px solid rgba(0, 240, 255, 0.15);
      display: flex;
      gap: 8px;
    }
    .rq-input {
      flex: 1;
      background: #05070B;
      border: 1px solid rgba(0, 240, 255, 0.2);
      border-radius: 6px;
      color: #EDF5FF;
      font-family: inherit;
      font-size: 12px;
      padding: 9px 12px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .rq-input:focus {
      border-color: #00F0FF;
      box-shadow: 0 0 10px rgba(0, 240, 255, 0.25);
    }
    .rq-send {
      background: linear-gradient(135deg, #00F0FF 0%, #00FF9D 100%);
      border: none;
      color: #03070E;
      font-weight: 700;
      border-radius: 6px;
      padding: 0 14px;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
      box-shadow: 0 0 12px rgba(0, 240, 255, 0.3);
    }
    .rq-send:hover {
      transform: translateY(-1px);
      box-shadow: 0 0 18px rgba(0, 240, 255, 0.5);
    }
    .rq-loading {
      align-self: flex-start;
      font-size: 11px;
      color: #00F0FF;
      font-style: italic;
      text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
    }
    /* Voice Panel Styles */
    .rq-voice-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
      text-align: center;
      gap: 20px;
    }
    .rq-voice-orb-wrapper {
      position: relative;
      width: 120px;
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .rq-voice-orb {
      width: 80px;
      height: 80px;
      border-radius: 50%;
      background: radial-gradient(circle, #00F0FF 0%, #070B14 70%);
      border: 2px solid #00F0FF;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      box-shadow: 0 0 25px rgba(0, 240, 255, 0.4);
      cursor: pointer;
      transition: all 0.3s;
    }
    .rq-voice-orb.rq-calling {
      animation: rq-orb-pulse 1.8s infinite;
      border-color: #00FF9D;
      box-shadow: 0 0 40px rgba(0, 255, 157, 0.7);
    }
    @keyframes rq-orb-pulse {
      0%, 100% { transform: scale(1); box-shadow: 0 0 24px rgba(0, 240, 255, 0.4); }
      50% { transform: scale(1.1); box-shadow: 0 0 45px rgba(0, 255, 157, 0.75); }
    }
    .rq-voice-wave {
      display: flex;
      align-items: center;
      gap: 4px;
      height: 24px;
    }
    .rq-wave-bar {
      width: 4px;
      height: 6px;
      background: #00F0FF;
      border-radius: 2px;
      box-shadow: 0 0 6px #00F0FF;
      transition: height 0.15s ease;
    }
    .rq-wave-active .rq-wave-bar {
      animation: rq-wave-anim 0.8s infinite ease-in-out alternate;
    }
    .rq-wave-bar:nth-child(1) { animation-delay: 0.1s; }
    .rq-wave-bar:nth-child(2) { animation-delay: 0.3s; }
    .rq-wave-bar:nth-child(3) { animation-delay: 0.2s; }
    .rq-wave-bar:nth-child(4) { animation-delay: 0.4s; }
    .rq-wave-bar:nth-child(5) { animation-delay: 0.25s; }
    @keyframes rq-wave-anim {
      0% { height: 4px; }
      100% { height: 24px; }
    }
    .rq-voice-status {
      font-size: 13px;
      font-weight: 600;
      color: #EDF5FF;
    }
    .rq-voice-sub {
      font-size: 11px;
      color: #7E90A6;
      max-width: 280px;
      line-height: 1.4;
    }
    .rq-voice-transcript {
      background: #0A101C;
      border: 1px solid rgba(0, 240, 255, 0.15);
      border-radius: 8px;
      padding: 10px 14px;
      font-size: 11px;
      color: #EDF5FF;
      max-width: 100%;
      min-height: 48px;
      text-align: left;
      line-height: 1.4;
    }
    .rq-btn-call {
      background: linear-gradient(135deg, #00F0FF 0%, #00FF9D 100%);
      color: #03070E;
      border: none;
      border-radius: 8px;
      font-family: inherit;
      font-size: 12px;
      font-weight: 700;
      padding: 10px 20px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
      box-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
    }
    .rq-btn-call:hover {
      transform: translateY(-1px);
      box-shadow: 0 0 25px rgba(0, 240, 255, 0.6);
    }
    .rq-btn-hangup {
      background: #DC2626;
      color: #FFFFFF;
    }
    .rq-btn-hangup:hover {
      background: #EF4444;
    }
    /* Callback Panel Styles */
    .rq-callback-container {
      padding: 24px 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .rq-form-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .rq-label {
      font-size: 11px;
      font-weight: 600;
      color: #94A3B8;
    }
    .rq-radio-group {
      display: flex;
      gap: 12px;
    }
    .rq-radio-label {
      font-size: 11px;
      color: #EDF5FF;
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
    }
    .rq-alert {
      padding: 10px 14px;
      border-radius: 6px;
      font-size: 11px;
      line-height: 1.4;
      display: none;
    }
    .rq-alert-success {
      background: rgba(0, 255, 157, 0.12);
      color: #00FF9D;
      border: 1px solid rgba(0, 255, 157, 0.4);
    }
  `;

  // 2. Inject CSS
  const styleEl = document.createElement('style');
  styleEl.innerHTML = styles;
  document.head.appendChild(styleEl);

  // 3. Create DOM elements
  const launcher = document.createElement('div');
  launcher.className = 'rq-launcher';
  launcher.innerHTML = `
    <div class="rq-pulse"></div>
    <span>📞 Concierge & Appel IA</span>
  `;

  const chatWindow = document.createElement('div');
  chatWindow.className = 'rq-window';
  chatWindow.innerHTML = `
    <div class="rq-header">
      <div>
        <div class="rq-title">Rockib Quenum · Concierge IA</div>
        <div class="rq-subtitle">En production, pas en démo · Cotonou</div>
      </div>
      <button class="rq-close" title="Fermer">✕</button>
    </div>
    <div class="rq-tabs">
      <button class="rq-tab-btn rq-active" data-tab="chat">💬 Chat</button>
      <button class="rq-tab-btn" data-tab="voice">🎙️ Appel Vocal</button>
      <button class="rq-tab-btn" data-tab="callback">📲 Me faire appeler</button>
    </div>

    <!-- Panel 1: Chat -->
    <div class="rq-panel rq-active" id="rq-panel-chat">
      <div class="rq-messages" id="rq-messages-container">
        <div class="rq-msg rq-msg-assistant">Bonjour ! Je suis le concierge IA de Rockib Quenum.

Je peux répondre à vos questions sur ses systèmes en production réelle (comme le vendeur IA WhatsApp de MARTISTORE ou le portail client de l'Agence IIA), ou vous aider à cadrer votre projet.

Que souhaitez-vous savoir ?</div>
        <div class="rq-suggestions" id="rq-suggestions-container">
          <button class="rq-chip" data-query="Comment fonctionne le vendeur IA WhatsApp ?">💬 Comment fonctionne le vendeur IA WhatsApp ?</button>
          <button class="rq-chip" data-query="Quels services propose l'Agence IIA ?">🏢 Quels services propose l'Agence IIA ?</button>
          <button class="rq-chip" data-query="Je voudrais un devis pour un projet">⚡ Je voudrais un devis pour un projet</button>
        </div>
      </div>
      <form class="rq-input-area" id="rq-chat-form">
        <input type="text" class="rq-input" id="rq-input-field" placeholder="Posez une question ou laissez un contact..." autocomplete="off" />
        <button type="submit" class="rq-send">➤</button>
      </form>
    </div>

    <!-- Panel 2: Live Voice Calling (ChatGPT Advanced Voice Mode UI) -->
    <div class="rq-panel" id="rq-panel-voice">
      <div class="rq-voice-container" style="justify-content:space-between; padding:18px 20px;">
        <!-- Top Voice Selector Bar -->
        <div style="display:flex; align-items:center; justify-content:space-between; width:100%; gap:6px;">
          <div style="display:flex; align-items:center; gap:6px;">
            <span id="rq-voice-badge" style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#64748B;"></span>
            <span id="rq-voice-mode-label" style="font-size:10px; color:#94A3B8; text-transform:uppercase; letter-spacing:0.08em;">Mode Vocal Temps Réel</span>
          </div>
          <div style="display:flex; align-items:center; gap:5px;">
            <select id="rq-voice-profile" class="rq-input" style="padding:4px 7px; font-size:10px; border-radius:999px; background:#0A101E;">
              <option value="henri">🎙️ Henri HD</option>
              <option value="vivienne">🎙️ Vivienne HD</option>
              <option value="denise">🎙️ Denise HD</option>
              <option value="remy">🎙️ Rémy HD</option>
            </select>
            <button type="button" id="rq-btn-test-voice" title="Écouter cette voix" style="background:#0A101E; border:1px solid rgba(0,240,255,0.35); color:#00F0FF; border-radius:999px; padding:4px 8px; font-size:10px; cursor:pointer;">🔊</button>
          </div>
        </div>

        <!-- Center ChatGPT Fluid Morphing Orb -->
        <div style="position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; margin:4px 0;">
          <canvas id="rq-voice-canvas" width="190" height="190" style="width:190px; height:190px; cursor:pointer;" title="Touchez la sphère pour parler ou interrompre"></canvas>
          <div id="rq-voice-orb" style="display:none;"></div>
          <div id="rq-voice-wave" style="display:none;"></div>
          <div class="rq-voice-status" id="rq-voice-status" style="margin-top:6px; font-size:14px; font-weight:700; color:#EDF5FF; letter-spacing:0.01em;">Touchez pour démarrer</div>
          <div class="rq-voice-sub" id="rq-voice-sub" style="margin-top:2px; font-size:11px; color:#7E90A6;">Conversation fluide mains-libres · Interruption instantanée</div>
        </div>

        <!-- Live Subtitle / Caption Box -->
        <div class="rq-voice-transcript" id="rq-voice-transcript" style="width:100%; min-height:46px; max-height:76px; overflow-y:auto; text-align:center; font-size:11.5px; border-radius:12px; background:rgba(10,16,28,0.85);">
          <em>Parlez librement comme avec ChatGPT : je détecte automatiquement quand vous parlez et quand vous faites une pause.</em>
        </div>

        <!-- Bottom ChatGPT-style Control Dock + Optional Text Bar -->
        <div style="display:flex; flex-direction:column; gap:10px; width:100%; align-items:center;">
          <div style="display:flex; align-items:center; justify-content:center; gap:16px; width:100%;">
            <button type="button" id="rq-btn-mute" title="Couper / Activer le micro" style="display:none; width:44px; height:44px; border-radius:50%; border:1px solid rgba(255,255,255,0.18); background:#111827; color:#EDF5FF; font-size:17px; align-items:center; justify-content:center; cursor:pointer; transition:all 0.2s;">
              🎙️
            </button>
            <button type="button" class="rq-btn-call" id="rq-btn-toggle-call" style="border-radius:999px; padding:11px 24px; font-size:12.5px;">
              <span>📞 Démarrer la conversation</span>
            </button>
            <button type="button" id="rq-btn-send-speech" title="Forcer l'envoi immédiat" style="display:none; width:44px; height:44px; border-radius:50%; border:1px solid rgba(0,255,157,0.5); background:rgba(0,255,157,0.12); color:#00FF9D; font-size:16px; align-items:center; justify-content:center; cursor:pointer; transition:all 0.2s;">
              ✓
            </button>
          </div>
          <form id="rq-voice-quick-form" style="display:flex; gap:6px; width:100%;">
            <input type="text" id="rq-voice-quick-input" class="rq-input" placeholder="Ou écrivez un message au Concierge vocal..." style="font-size:11px; padding:6px 12px; border-radius:999px;" autocomplete="off" />
            <button type="submit" class="rq-send" title="Envoyer" style="padding:0 12px; font-size:11px; border-radius:999px;">➤</button>
          </form>
        </div>
      </div>
    </div>

    <!-- Panel 3: Callback Request -->
    <div class="rq-panel" id="rq-panel-callback">
      <form class="rq-callback-container" id="rq-callback-form">
        <div>
          <div style="font-size: 13px; font-weight: 700; color: #E8A33D;">Demande de Rappel Direct</div>
          <div style="font-size: 11px; color: #8C847A; margin-top: 4px;">
            Laissez votre numéro : Rockib ou un agent de l'équipe vous appelle sous 5 minutes.
          </div>
        </div>

        <div class="rq-alert rq-alert-success" id="rq-callback-success"></div>

        <div class="rq-form-group">
          <label class="rq-label">Votre Numéro de Téléphone (avec indicatif)</label>
          <input type="tel" class="rq-input" id="rq-cb-phone" placeholder="ex: +229 97 00 00 00" required />
        </div>

        <div class="rq-form-group">
          <label class="rq-label">Votre Nom ou Entreprise</label>
          <input type="text" class="rq-input" id="rq-cb-name" placeholder="ex: Marc / MARTI Boutique" />
        </div>

        <div class="rq-form-group">
          <label class="rq-label">Canal souhaité</label>
          <div class="rq-radio-group">
            <label class="rq-radio-label">
              <input type="radio" name="rq-cb-channel" value="whatsapp" checked /> WhatsApp Audio
            </label>
            <label class="rq-radio-label">
              <input type="radio" name="rq-cb-channel" value="phone" /> Appel Téléphonique
            </label>
          </div>
        </div>

        <div class="rq-form-group">
          <label class="rq-label">Sujet principal</label>
          <input type="text" class="rq-input" id="rq-cb-topic" placeholder="ex: Automatisation WhatsApp / Site E-commerce" />
        </div>

        <button type="submit" class="rq-btn-call" style="justify-content: center; width: 100%; margin-top: 8px;">
          <span>📲 Me faire appeler</span>
        </button>
      </form>
    </div>
  `;

  document.body.appendChild(launcher);
  document.body.appendChild(chatWindow);

  // Tabs switching
  const tabBtns = chatWindow.querySelectorAll('.rq-tab-btn');
  const panels = {
    chat: chatWindow.querySelector('#rq-panel-chat'),
    voice: chatWindow.querySelector('#rq-panel-voice'),
    callback: chatWindow.querySelector('#rq-panel-callback'),
  };

  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      activeTab = targetTab;
      tabBtns.forEach((b) => b.classList.remove('rq-active'));
      btn.classList.add('rq-active');

      Object.values(panels).forEach((p) => p.classList.remove('rq-active'));
      panels[targetTab].classList.add('rq-active');
    });
  });

  // Open/Close
  function toggleChat(forceState) {
    isOpen = forceState !== undefined ? forceState : !isOpen;
    if (isOpen) {
      chatWindow.classList.add('rq-open');
    } else {
      chatWindow.classList.remove('rq-open');
      if (isCalling) stopVoiceCall();
    }
  }

  launcher.addEventListener('click', () => toggleChat());
  chatWindow.querySelector('.rq-close').addEventListener('click', () => toggleChat(false));

  // --- Chat Section ---
  const messagesContainer = chatWindow.querySelector('#rq-messages-container');
  const suggestionsContainer = chatWindow.querySelector('#rq-suggestions-container');
  const chatForm = chatWindow.querySelector('#rq-chat-form');
  const inputField = chatWindow.querySelector('#rq-input-field');

  function appendChatMessage(text, role) {
    const el = document.createElement('div');
    el.className = `rq-msg rq-msg-${role}`;
    el.textContent = text;
    messagesContainer.appendChild(el);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  async function sendChatMessage(text) {
    if (!text || !text.trim()) return;
    const userMsg = text.trim();
    appendChatMessage(userMsg, 'user');
    inputField.value = '';

    if (suggestionsContainer) suggestionsContainer.style.display = 'none';

    const loadingEl = document.createElement('div');
    loadingEl.className = 'rq-loading';
    loadingEl.textContent = 'Le concierge formule sa réponse...';
    messagesContainer.appendChild(loadingEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
      const response = await fetch(`${API_BASE}/api/v1/inbound/portfolio/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({
          message: userMsg,
          conversation_id: conversationId,
          page_url: window.location.href,
        }),
      });

      const data = await response.json();
      loadingEl.remove();

      if (data.conversation_id) {
        conversationId = data.conversation_id;
        sessionStorage.setItem(STORAGE_KEY, conversationId);
      }

      appendChatMessage(data.reply || "Je n'ai pas pu obtenir de réponse.", 'assistant');
    } catch (err) {
      loadingEl.remove();
      appendChatMessage('Erreur réseau. Vous pouvez contacter Rockib : rockibdev@gmail.com.', 'assistant');
    }
  }

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendChatMessage(inputField.value);
  });

  suggestionsContainer.addEventListener('click', (e) => {
    const chip = e.target.closest('.rq-chip');
    if (chip) sendChatMessage(chip.getAttribute('data-query'));
  });

  // --- ChatGPT-Style Advanced Voice Mode Section ---
  const orb = chatWindow.querySelector('#rq-voice-orb');
  const wave = chatWindow.querySelector('#rq-voice-wave');
  const voiceCanvas = chatWindow.querySelector('#rq-voice-canvas');
  const voiceBadge = chatWindow.querySelector('#rq-voice-badge');
  const voiceModeLabel = chatWindow.querySelector('#rq-voice-mode-label');
  const voiceStatus = chatWindow.querySelector('#rq-voice-status');
  const voiceSub = chatWindow.querySelector('#rq-voice-sub');
  const voiceTranscript = chatWindow.querySelector('#rq-voice-transcript');
  const btnToggleCall = chatWindow.querySelector('#rq-btn-toggle-call');
  const btnMute = chatWindow.querySelector('#rq-btn-mute');
  const btnSendSpeech = chatWindow.querySelector('#rq-btn-send-speech');
  const voiceProfileSelect = chatWindow.querySelector('#rq-voice-profile');
  const voiceQuickForm = chatWindow.querySelector('#rq-voice-quick-form');
  const voiceQuickInput = chatWindow.querySelector('#rq-voice-quick-input');

  let currentAudio = null;
  let micStream = null;
  let mediaRecorder = null;
  let audioChunks = [];
  let audioCtx = null;
  let micSource = null;
  let micAnalyser = null;
  let micTimeData = null;
  let aiAnalyser = null;
  let aiTimeData = null;
  let vadInterval = null;
  let isProcessingTurn = false;
  let isMuted = false;
  let orbState = 'idle'; // 'idle' | 'listening' | 'user_speaking' | 'thinking' | 'ai_speaking'
  let orbLevel = 0; // 0..1 smoothed audio energy

  if (voiceProfileSelect) {
    const savedVoice = localStorage.getItem('rq_voice_profile');
    if (savedVoice) voiceProfileSelect.value = savedVoice;
    voiceProfileSelect.addEventListener('change', () => {
      localStorage.setItem('rq_voice_profile', voiceProfileSelect.value);
    });
  }

  // Preload browser voices for instant fallback
  if (window.speechSynthesis && typeof window.speechSynthesis.onvoiceschanged !== 'undefined') {
    window.speechSynthesis.onvoiceschanged = function () {
      window.speechSynthesis.getVoices();
    };
  }

  // --- 60 FPS ChatGPT Fluid Sphere Renderer ---
  (function initFluidOrbCanvas() {
    if (!voiceCanvas) return;
    const ctx = voiceCanvas.getContext('2d');
    let phase = 0;

    function computeRmsFromTimeData(analyser, buf) {
      if (!analyser || !buf) return 0;
      try {
        analyser.getByteTimeDomainData(buf);
        let sumSq = 0;
        for (let i = 0; i < buf.length; i++) {
          const d = buf[i] - 128;
          sumSq += d * d;
        }
        return Math.sqrt(sumSq / buf.length); // 0..128
      } catch (e) {
        return 0;
      }
    }

    function renderOrb() {
      requestAnimationFrame(renderOrb);
      if (!isOpen || activeTab !== 'voice') return;

      const w = voiceCanvas.width;
      const h = voiceCanvas.height;
      const cx = w / 2;
      const cy = h / 2;
      ctx.clearRect(0, 0, w, h);

      // Measure real-time audio energy from either AI voice or User mic
      let rawEnergy = 0;
      if (orbState === 'ai_speaking' && aiAnalyser && aiTimeData) {
        rawEnergy = Math.min(1, computeRmsFromTimeData(aiAnalyser, aiTimeData) / 26);
      } else if (orbState === 'ai_speaking') {
        rawEnergy = 0.25 + 0.2 * Math.sin(phase * 3.5);
      } else if ((orbState === 'listening' || orbState === 'user_speaking') && micAnalyser && micTimeData && !isMuted) {
        rawEnergy = Math.min(1, computeRmsFromTimeData(micAnalyser, micTimeData) / 20);
      } else if (orbState === 'thinking') {
        rawEnergy = 0.3 + 0.15 * Math.sin(phase * 5);
      } else {
        rawEnergy = 0.06 * (0.5 + 0.5 * Math.sin(phase * 1.4));
      }

      orbLevel = orbLevel * 0.78 + rawEnergy * 0.22;
      phase += 0.045 + orbLevel * 0.09;

      // Color palette by state (ChatGPT Voice style)
      let c1 = '0, 240, 255';   // Cyan
      let c2 = '99, 102, 241';  // Indigo
      if (orbState === 'user_speaking') {
        c1 = '0, 255, 157';     // Emerald
        c2 = '0, 240, 255';
      } else if (orbState === 'thinking') {
        c1 = '168, 85, 247';    // Violet
        c2 = '0, 240, 255';
      } else if (orbState === 'ai_speaking') {
        c1 = '56, 189, 248';    // Sky Blue (ChatGPT Voice signature)
        c2 = '237, 245, 255';   // Luminous White-Cyan
      }

      const baseR = 46 + orbLevel * 22;

      // Outer atmospheric glow
      const outerGrad = ctx.createRadialGradient(cx, cy, baseR * 0.3, cx, cy, baseR * 1.75);
      outerGrad.addColorStop(0, `rgba(${c1}, ${0.32 + orbLevel * 0.35})`);
      outerGrad.addColorStop(0.55, `rgba(${c2}, ${0.14 + orbLevel * 0.18})`);
      outerGrad.addColorStop(1, 'rgba(6, 9, 18, 0)');
      ctx.fillStyle = outerGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, baseR * 1.75, 0, Math.PI * 2);
      ctx.fill();

      // 3 Fluid morphing organic lobes
      for (let layer = 0; layer < 3; layer++) {
        ctx.beginPath();
        const pts = 64;
        const layerOffset = layer * 2.1;
        const layerR = baseR * (1 - layer * 0.08);
        const amp = (3.5 + orbLevel * 13) * (1 - layer * 0.2);

        for (let i = 0; i <= pts; i++) {
          const angle = (i / pts) * Math.PI * 2;
          const wave1 = Math.sin(angle * 3 + phase + layerOffset) * amp;
          const wave2 = Math.cos(angle * 4 - phase * 1.3 + layerOffset) * (amp * 0.55);
          const r = layerR + wave1 + wave2;
          const x = cx + Math.cos(angle) * r;
          const y = cy + Math.sin(angle) * r;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();

        const grad = ctx.createRadialGradient(
          cx - 10 * Math.cos(phase * 0.7),
          cy - 10 * Math.sin(phase * 0.7),
          layerR * 0.1,
          cx,
          cy,
          layerR * 1.25
        );
        if (layer === 0) {
          grad.addColorStop(0, `rgba(${c2}, 0.55)`);
          grad.addColorStop(1, `rgba(${c1}, 0.22)`);
        } else if (layer === 1) {
          grad.addColorStop(0, `rgba(255, 255, 255, ${0.45 + orbLevel * 0.35})`);
          grad.addColorStop(0.6, `rgba(${c1}, 0.75)`);
          grad.addColorStop(1, `rgba(${c2}, 0.35)`);
        } else {
          grad.addColorStop(0, '#FFFFFF');
          grad.addColorStop(0.45, `rgba(${c1}, 0.92)`);
          grad.addColorStop(1, `rgba(${c2}, 0.75)`);
        }
        ctx.fillStyle = grad;
        ctx.fill();
      }
    }

    requestAnimationFrame(renderOrb);
  })();

  function setOrbUiState(state, statusText, subText) {
    orbState = state;
    if (voiceStatus && statusText) voiceStatus.textContent = statusText;
    if (voiceSub && subText !== undefined) voiceSub.textContent = subText;
    if (voiceBadge && voiceModeLabel) {
      if (state === 'listening' || state === 'user_speaking') {
        voiceBadge.style.background = '#00FF9D';
        voiceBadge.style.boxShadow = '0 0 8px #00FF9D';
        voiceModeLabel.textContent = state === 'user_speaking' ? 'Vous parlez...' : 'Micro Actif · Mains-Libres';
      } else if (state === 'thinking') {
        voiceBadge.style.background = '#A855F7';
        voiceBadge.style.boxShadow = '0 0 8px #A855F7';
        voiceModeLabel.textContent = 'Réflexion IA...';
      } else if (state === 'ai_speaking') {
        voiceBadge.style.background = '#00F0FF';
        voiceBadge.style.boxShadow = '0 0 8px #00F0FF';
        voiceModeLabel.textContent = 'Concierge en train de parler';
      } else {
        voiceBadge.style.background = '#64748B';
        voiceBadge.style.boxShadow = 'none';
        voiceModeLabel.textContent = 'Mode Vocal Temps Réel';
      }
    }
  }

  function ensureMicAudioGraph(stream) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass || !stream) return;
    try {
      if (!audioCtx) audioCtx = new AudioContextClass();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      if (!micAnalyser) {
        micSource = audioCtx.createMediaStreamSource(stream);
        micAnalyser = audioCtx.createAnalyser();
        micAnalyser.fftSize = 512;
        micSource.connect(micAnalyser);
        micTimeData = new Uint8Array(micAnalyser.fftSize);
      }
    } catch (e) {}
  }

  function pickBestBrowserFrenchVoice(preferredGender) {
    if (!window.speechSynthesis) return null;
    var voices = window.speechSynthesis.getVoices() || [];
    var frVoices = voices.filter(function (v) {
      return v.lang && (v.lang.toLowerCase().startsWith('fr') || v.lang.toLowerCase().includes('fr'));
    });
    if (!frVoices.length) return null;

    function scoreVoice(v) {
      var name = (v.name || '').toLowerCase();
      var score = 0;
      if (name.includes('natural') || name.includes('neural') || name.includes('online')) score += 100;
      if (name.includes('multilingual')) score += 40;
      if (name.includes('google')) score += 85;
      if (name.includes('enhanced') || name.includes('premium')) score += 70;
      if (v.lang === 'fr-FR') score += 20;
      if (preferredGender === 'female') {
        if (name.includes('vivienne') || name.includes('denise') || name.includes('eloise') || name.includes('amelie') || name.includes('amélie') || name.includes('audrey')) score += 50;
      } else {
        if (name.includes('henri') || name.includes('remy') || name.includes('rémy') || name.includes('thomas') || name.includes('paul')) score += 50;
      }
      if (name.includes('hortense') || name.includes('desktop')) score -= 45;
      return score;
    }

    frVoices.sort(function (a, b) {
      return scoreVoice(b) - scoreVoice(a);
    });
    return frVoices[0];
  }

  function setVoiceTranscript(speaker, text) {
    voiceTranscript.textContent = '';
    const strong = document.createElement('strong');
    strong.style.color = speaker.startsWith('Vous') ? '#00FF9D' : '#00F0FF';
    strong.textContent = speaker + ' : ';
    voiceTranscript.appendChild(strong);
    voiceTranscript.appendChild(document.createTextNode(text || ''));
  }

  function stopActiveListening() {
    if (vadInterval) {
      clearInterval(vadInterval);
      vadInterval = null;
    }
    if (recognition) {
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;
      try { recognition.abort(); } catch (e) {}
      recognition = null;
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.onstop = null;
      try { mediaRecorder.stop(); } catch (e) {}
    }
    mediaRecorder = null;
    if (btnSendSpeech) btnSendSpeech.style.display = 'none';
  }

  function interruptAiSpeaking() {
    if (!isSpeaking) return;
    isSpeaking = false;
    if (currentAudio) {
      try {
        currentAudio.pause();
        currentAudio.src = '';
      } catch (e) {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (isCalling) {
      listenToUser();
    }
  }

  function speakWithBrowserFallback(text, finishCallback, preferredGender) {
    if (!window.speechSynthesis) {
      finishCallback();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'fr-FR';
    utterance.rate = 1.02;
    utterance.pitch = preferredGender === 'female' ? 1.02 : 0.98;

    const bestVoice = pickBestBrowserFrenchVoice(preferredGender);
    if (bestVoice) utterance.voice = bestVoice;

    utterance.onend = finishCallback;
    utterance.onerror = finishCallback;

    var wordCount = (text || '').split(/\s+/).length;
    var maxWaitMs = Math.max(3500, (wordCount / 2.2) * 1000 + 2500);
    setTimeout(function () {
      if (isSpeaking) finishCallback();
    }, maxWaitMs);

    setTimeout(function () {
      window.speechSynthesis.speak(utterance);
    }, 40);
  }

  async function speakReply(text, onComplete) {
    stopActiveListening();
    if (currentAudio) {
      try {
        currentAudio.pause();
        currentAudio.src = '';
      } catch (e) {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    isSpeaking = true;
    setOrbUiState(
      'ai_speaking',
      'Le Concierge vous répond...',
      isCalling ? 'Touchez la sphère (ou parlez) pour l’interrompre' : 'Lecture de la voix Neuronale HD'
    );

    var bargeInCheckInterval = null;
    var hasEnded = false;
    function finish() {
      if (hasEnded) return;
      hasEnded = true;
      isSpeaking = false;
      if (bargeInCheckInterval) {
        clearInterval(bargeInCheckInterval);
        bargeInCheckInterval = null;
      }
      if (onComplete) onComplete();
    }

    // Monitor microphone during AI speech for hands-free Barge-In (interruption)
    if (isCalling && micAnalyser && micTimeData && !isMuted) {
      let loudFrames = 0;
      bargeInCheckInterval = setInterval(() => {
        if (!isSpeaking || isMuted) return;
        micAnalyser.getByteTimeDomainData(micTimeData);
        let sumSq = 0;
        for (let i = 0; i < micTimeData.length; i++) {
          const d = micTimeData[i] - 128;
          sumSq += d * d;
        }
        const rms = Math.sqrt(sumSq / micTimeData.length);
        if (rms > 18) {
          loudFrames++;
          if (loudFrames >= 4) {
            clearInterval(bargeInCheckInterval);
            bargeInCheckInterval = null;
            interruptAiSpeaking();
          }
        } else {
          loudFrames = Math.max(0, loudFrames - 1);
        }
      }, 90);
    }

    const selectedProfile = (voiceProfileSelect && voiceProfileSelect.value) || 'henri';
    const preferredGender = (selectedProfile === 'vivienne' || selectedProfile === 'denise') ? 'female' : 'male';

    // Option 1: Server Neural HD TTS
    try {
      const ttsResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({ text: text, voice: selectedProfile }),
      });

      if (ttsResp.ok && isSpeaking) {
        const audioBlob = await ttsResp.blob();
        if (audioBlob && audioBlob.size > 200 && isSpeaking) {
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          currentAudio = audio;

          // Connect AI audio to AnalyserNode so the fluid sphere dances to the AI's voice
          try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
              if (!audioCtx) audioCtx = new AudioContextClass();
              if (audioCtx.state === 'suspended') audioCtx.resume();
              const elemSource = audioCtx.createMediaElementSource(audio);
              aiAnalyser = audioCtx.createAnalyser();
              aiAnalyser.fftSize = 512;
              elemSource.connect(aiAnalyser);
              aiAnalyser.connect(audioCtx.destination);
              aiTimeData = new Uint8Array(aiAnalyser.fftSize);
            }
          } catch (graphErr) {}

          audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            currentAudio = null;
            finish();
          };
          audio.onerror = () => {
            URL.revokeObjectURL(audioUrl);
            currentAudio = null;
            speakWithBrowserFallback(text, finish, preferredGender);
          };
          await audio.play();
          return;
        }
      }
    } catch (e) {}

    if (isSpeaking) {
      speakWithBrowserFallback(text, finish, preferredGender);
    }
  }

  async function startVoiceCall() {
    // 1. Unlock microphone immediately on user click gesture
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        if (!micStream || !micStream.active) {
          micStream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          });
        }
        ensureMicAudioGraph(micStream);
      }
    } catch (micErr) {
      setOrbUiState('idle', 'Microphone non autorisé', "Autorisez le micro dans la barre d'adresse ou écrivez ci-dessous.");
    }

    try {
      setOrbUiState('thinking', 'Connexion vocale...', 'Initialisation de la session temps réel');
      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({ page_url: window.location.href }),
      });
      const data = await resp.json();
      voiceSessionId = data.session_id;

      isCalling = true;
      isProcessingTurn = false;
      isMuted = false;
      if (btnMute) {
        btnMute.style.display = 'inline-flex';
        btnMute.textContent = '🎙️';
        btnMute.style.borderColor = 'rgba(0, 255, 157, 0.5)';
      }
      btnToggleCall.classList.add('rq-btn-hangup');
      btnToggleCall.innerHTML = '<span>✕ Terminer</span>';
      setVoiceTranscript('Concierge', data.greeting_text);

      speakReply(data.greeting_text, () => {
        if (isCalling) listenToUser();
      });
    } catch (err) {
      setOrbUiState('idle', 'Erreur de connexion', 'Impossible de joindre le serveur vocal.');
    }
  }

  function listenToUser() {
    if (!isCalling || isSpeaking || isProcessingTurn) return;
    stopActiveListening();

    if (isMuted) {
      setOrbUiState('idle', 'Micro coupé', 'Touchez 🎙️ pour réactiver votre micro');
      return;
    }

    setOrbUiState('listening', 'Je vous écoute...', 'Parlez naturellement, je détecte vos pauses automatiquement');
    if (btnSendSpeech) btnSendSpeech.style.display = 'inline-flex';

    var capturedSpeech = '';
    var finishTimeout = null;
    var turnSubmitted = false;

    function submitRecognizedText(textToSubmit) {
      if (turnSubmitted || !isCalling || isSpeaking || isProcessingTurn) return;
      var cleaned = (textToSubmit || '').trim();
      if (!cleaned) return;
      turnSubmitted = true;
      clearTimeout(finishTimeout);
      stopActiveListening();
      processVoiceTurn(cleaned);
    }

    // Engine A: Browser Web Speech API (instant live captions + fast trigger)
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
      try {
        recognition = new SpeechRec();
        recognition.lang = 'fr-FR';
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = function (event) {
          if (isMuted) return;
          var interim = '';
          var finalTxt = '';
          for (var i = 0; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              finalTxt += event.results[i][0].transcript + ' ';
            } else {
              interim += event.results[i][0].transcript;
            }
          }
          var spoken = (finalTxt + interim).trim();
          if (spoken) {
            capturedSpeech = spoken;
            setOrbUiState('user_speaking', 'Je vous écoute...', 'En train de capter votre voix...');
            setVoiceTranscript('Vous (en direct)', spoken);
            clearTimeout(finishTimeout);
            finishTimeout = setTimeout(function () {
              submitRecognizedText(capturedSpeech);
            }, 1050);
          }
        };

        recognition.onend = function () {
          if (!turnSubmitted && capturedSpeech.trim().length > 1) {
            submitRecognizedText(capturedSpeech);
          }
        };

        recognition.onerror = function () {};
        recognition.start();
      } catch (e) {}
    }

    // Engine B: Calibrated Time-Domain RMS VAD + Groq Whisper STT (works on 100% of browsers)
    if (micStream && micStream.active && typeof window.MediaRecorder !== 'undefined') {
      ensureMicAudioGraph(micStream);
      try {
        audioChunks = [];
        var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '');
        mediaRecorder = mimeType ? new MediaRecorder(micStream, { mimeType: mimeType }) : new MediaRecorder(micStream);

        mediaRecorder.ondataavailable = function (e) {
          if (e.data && e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async function () {
          if (turnSubmitted || !isCalling || isSpeaking || isProcessingTurn || isMuted) return;
          if (capturedSpeech.trim().length > 1) {
            submitRecognizedText(capturedSpeech);
            return;
          }
          var blob = new Blob(audioChunks, { type: mimeType || 'audio/webm' });
          if (blob.size < 800) {
            if (isCalling && !isSpeaking && !isProcessingTurn) {
              setTimeout(listenToUser, 200);
            }
            return;
          }
          setOrbUiState('thinking', 'Transcription...', 'Analyse vocale ultra-rapide');
          try {
            var sttResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/stt`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/octet-stream',
                'X-Audio-Ext': 'webm',
                'ngrok-skip-browser-warning': 'true',
              },
              body: blob,
            });
            if (sttResp.ok) {
              var sttData = await sttResp.json();
              var whisperText = (sttData.transcript || '').trim();
              if (whisperText.length > 1) {
                setVoiceTranscript('Vous', whisperText);
                submitRecognizedText(whisperText);
                return;
              }
            }
          } catch (err) {}
          if (isCalling && !isSpeaking && !isProcessingTurn) {
            setTimeout(listenToUser, 250);
          }
        };

        mediaRecorder.start(200);

        // Calibrated Time-Domain RMS Voice Activity Detection
        if (micAnalyser && micTimeData) {
          var speechFrames = 0;
          var hasSpokenAudio = false;
          var silenceStart = 0;
          var noiseFloor = 1.4;
          var cycleStart = Date.now();

          vadInterval = setInterval(function () {
            if (!isCalling || isSpeaking || turnSubmitted || isMuted) {
              clearInterval(vadInterval);
              vadInterval = null;
              return;
            }
            micAnalyser.getByteTimeDomainData(micTimeData);
            var sumSq = 0;
            for (var i = 0; i < micTimeData.length; i++) {
              var d = micTimeData[i] - 128;
              sumSq += d * d;
            }
            var rms = Math.sqrt(sumSq / micTimeData.length);
            var threshold = Math.max(3.2, Math.min(9.0, noiseFloor * 2.2));

            if (rms > threshold) {
              speechFrames++;
              silenceStart = 0;
              if (speechFrames >= 2) {
                hasSpokenAudio = true;
                setOrbUiState('user_speaking', 'Je vous écoute...', 'Parlez librement...');
              }
            } else {
              if (!hasSpokenAudio) {
                noiseFloor = noiseFloor * 0.92 + rms * 0.08;
              }
              speechFrames = Math.max(0, speechFrames - 1);
              if (hasSpokenAudio) {
                if (!silenceStart) {
                  silenceStart = Date.now();
                } else if (Date.now() - silenceStart > 920) {
                  // 920ms pause after speaking -> auto-send turn like ChatGPT!
                  clearInterval(vadInterval);
                  vadInterval = null;
                  if (capturedSpeech.trim().length > 1) {
                    submitRecognizedText(capturedSpeech);
                  } else if (mediaRecorder && mediaRecorder.state === 'recording') {
                    try { mediaRecorder.stop(); } catch (e) {}
                  }
                }
              } else if (Date.now() - cycleStart > 15000) {
                // Keep buffer fresh during long silence
                cycleStart = Date.now();
                audioChunks = [];
              }
            }
          }, 85);
        }
      } catch (recErr) {}
    }

    if (btnSendSpeech) {
      btnSendSpeech.onclick = function () {
        if (capturedSpeech.trim().length > 1) {
          submitRecognizedText(capturedSpeech);
        } else if (mediaRecorder && mediaRecorder.state === 'recording') {
          if (vadInterval) {
            clearInterval(vadInterval);
            vadInterval = null;
          }
          try { mediaRecorder.stop(); } catch (e) {}
        }
      };
    }
  }

  async function processVoiceTurn(userText) {
    if (!userText || !userText.trim() || isProcessingTurn) return;
    isProcessingTurn = true;
    stopActiveListening();
    setVoiceTranscript('Vous', userText.trim());
    setOrbUiState('thinking', 'Réflexion...', 'Formulation de la réponse vocale');

    try {
      if (!voiceSessionId) {
        const sResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
          body: JSON.stringify({ page_url: window.location.href }),
        });
        const sData = await sResp.json();
        voiceSessionId = sData.session_id;
      }

      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({
          session_id: voiceSessionId,
          user_speech_transcript: userText.trim(),
        }),
      });

      const data = await resp.json();
      isProcessingTurn = false;
      setVoiceTranscript('Concierge', data.agent_reply_text);

      speakReply(data.agent_reply_text, () => {
        if (data.should_end_call) {
          stopVoiceCall();
        } else if (isCalling) {
          listenToUser();
        }
      });
    } catch (err) {
      isProcessingTurn = false;
      setOrbUiState('idle', 'Erreur réseau', 'Vérifiez votre connexion');
      speakReply("Désolé, une coupure est survenue. Pouvez-vous répéter ?", () => {
        if (isCalling) listenToUser();
      });
    }
  }

  if (voiceQuickForm) {
    voiceQuickForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const val = (voiceQuickInput && voiceQuickInput.value || '').trim();
      if (!val) return;
      voiceQuickInput.value = '';
      if (!isCalling) {
        isCalling = true;
        btnToggleCall.classList.add('rq-btn-hangup');
        btnToggleCall.innerHTML = '<span>✕ Terminer</span>';
      }
      await processVoiceTurn(val);
    });
  }

  if (btnMute) {
    btnMute.addEventListener('click', () => {
      if (!isCalling) return;
      isMuted = !isMuted;
      if (isMuted) {
        btnMute.textContent = '🔇';
        btnMute.style.borderColor = 'rgba(239, 68, 68, 0.6)';
        stopActiveListening();
        setOrbUiState('idle', 'Micro en sourdine', 'Touchez 🔇 pour reprendre la parole');
      } else {
        btnMute.textContent = '🎙️';
        btnMute.style.borderColor = 'rgba(0, 255, 157, 0.5)';
        if (!isSpeaking && !isProcessingTurn) listenToUser();
      }
    });
  }

  function stopVoiceCall() {
    isCalling = false;
    isSpeaking = false;
    isProcessingTurn = false;
    isMuted = false;
    stopActiveListening();
    if (micStream) {
      try {
        micStream.getTracks().forEach((t) => t.stop());
      } catch (e) {}
      micStream = null;
      micAnalyser = null;
      micSource = null;
    }
    if (currentAudio) {
      try {
        currentAudio.pause();
        currentAudio.src = '';
      } catch (e) {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    if (btnMute) btnMute.style.display = 'none';
    btnToggleCall.classList.remove('rq-btn-hangup');
    btnToggleCall.innerHTML = '<span>📞 Démarrer la conversation</span>';
    setOrbUiState('idle', 'Conversation terminée', 'Touchez la sphère pour relancer');
  }

  btnToggleCall.addEventListener('click', () => {
    if (isCalling) {
      stopVoiceCall();
    } else {
      startVoiceCall();
    }
  });

  if (voiceCanvas) {
    voiceCanvas.addEventListener('click', () => {
      if (!isCalling) {
        startVoiceCall();
      } else if (isSpeaking) {
        // ChatGPT-style tap-to-interrupt!
        interruptAiSpeaking();
      }
    });
  }

  const btnTestVoice = chatWindow.querySelector('#rq-btn-test-voice');
  if (btnTestVoice) {
    btnTestVoice.addEventListener('click', () => {
      const profile = (voiceProfileSelect && voiceProfileSelect.value) || 'henri';
      const sampleText =
        profile === 'vivienne' || profile === 'denise'
          ? "Bonjour ! Je suis le concierge vocal temps réel de Rockib Quenum. Parlez-moi librement, comme avec ChatGPT."
          : "Bonjour ! Je suis le concierge vocal temps réel de Rockib Quenum. Parlez-moi librement, je vous écoute.";
      setVoiceTranscript('Concierge (Aperçu HD)', sampleText);
      speakReply(sampleText, () => {
        if (!isCalling) setOrbUiState('idle', 'Prêt à discuter', 'Touchez la sphère pour démarrer');
      });
    });
  }

  // --- Callback Request Section ---
  const callbackForm = chatWindow.querySelector('#rq-callback-form');
  const callbackSuccess = chatWindow.querySelector('#rq-callback-success');
  const cbPhone = chatWindow.querySelector('#rq-cb-phone');
  const cbName = chatWindow.querySelector('#rq-cb-name');
  const cbTopic = chatWindow.querySelector('#rq-cb-topic');

  callbackForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const channelInput = callbackForm.querySelector('input[name="rq-cb-channel"]:checked');
    const channel = channelInput ? channelInput.value : 'whatsapp';

    const submitBtn = callbackForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.innerText = 'Enregistrement en cours...';

    try {
      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/request-callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({
          phone_number: cbPhone.value.trim(),
          contact_name: cbName.value.trim() || undefined,
          topic: cbTopic.value.trim() || undefined,
          channel: channel,
          preferred_time: 'immediate',
        }),
      });

      const data = await resp.json();
      callbackSuccess.textContent = data.message;
      callbackSuccess.style.display = 'block';
      callbackForm.reset();
    } catch (err) {
      alert("Erreur lors de la réservation de l'appel. Vous pouvez écrire directement à rockibdev@gmail.com.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<span>📲 Me faire appeler</span>';
    }
  });

})();
