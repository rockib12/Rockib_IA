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

    <!-- Panel 2: Live Voice Calling -->
    <div class="rq-panel" id="rq-panel-voice">
      <div class="rq-voice-container">
        <div class="rq-voice-orb-wrapper">
          <div class="rq-voice-orb" id="rq-voice-orb">🎙️</div>
        </div>
        <div class="rq-voice-wave" id="rq-voice-wave">
          <div class="rq-wave-bar"></div>
          <div class="rq-wave-bar"></div>
          <div class="rq-wave-bar"></div>
          <div class="rq-wave-bar"></div>
          <div class="rq-wave-bar"></div>
        </div>
        <div>
          <div class="rq-voice-status" id="rq-voice-status">Appel vocal en direct</div>
          <div class="rq-voice-sub" id="rq-voice-sub">Parlez directement avec le Concierge IA (Voix Neuronale HD).</div>
        </div>
        <div style="display:flex; align-items:center; gap:6px; width:100%; justify-content:center; flex-wrap:wrap;">
          <label for="rq-voice-profile" style="font-size:10px; color:#7E90A6;">Voix HD :</label>
          <select id="rq-voice-profile" class="rq-input" style="padding:5px 8px; font-size:11px; max-width:195px;">
            <option value="henri">Henri Neural HD (Homme)</option>
            <option value="vivienne">Vivienne Neural HD (Femme)</option>
            <option value="denise">Denise Neural HD (Femme)</option>
            <option value="remy">Rémy Neural HD (Homme)</option>
          </select>
          <button type="button" id="rq-btn-test-voice" title="Écouter un extrait de cette voix" style="background:#0A101E; border:1px solid #00F0FF; color:#00F0FF; border-radius:6px; padding:5px 9px; font-size:11px; font-family:inherit; cursor:pointer;">🔊 Tester</button>
        </div>
        <div class="rq-voice-transcript" id="rq-voice-transcript" style="width: 100%;">
          <em>Appuyez sur "Démarrer l'appel" pour discuter à voix haute...</em>
        </div>
        <button class="rq-btn-call" id="rq-btn-toggle-call">
          <span>📞 Démarrer l'appel vocal</span>
        </button>
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

  // --- Voice Calling Section ---
  const orb = chatWindow.querySelector('#rq-voice-orb');
  const wave = chatWindow.querySelector('#rq-voice-wave');
  const voiceStatus = chatWindow.querySelector('#rq-voice-status');
  const voiceTranscript = chatWindow.querySelector('#rq-voice-transcript');
  const btnToggleCall = chatWindow.querySelector('#rq-btn-toggle-call');
  const voiceProfileSelect = chatWindow.querySelector('#rq-voice-profile');
  let currentAudio = null;

  if (voiceProfileSelect) {
    const savedVoice = localStorage.getItem('rq_voice_profile');
    if (savedVoice) voiceProfileSelect.value = savedVoice;
    voiceProfileSelect.addEventListener('change', () => {
      localStorage.setItem('rq_voice_profile', voiceProfileSelect.value);
    });
  }

  // Preload browser voices for instant Option 2 fallback
  if (window.speechSynthesis && typeof window.speechSynthesis.onvoiceschanged !== 'undefined') {
    window.speechSynthesis.onvoiceschanged = function () {
      window.speechSynthesis.getVoices();
    };
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
    strong.textContent = speaker + ' : ';
    voiceTranscript.appendChild(strong);
    voiceTranscript.appendChild(document.createTextNode(text || ''));
  }

  function speakWithBrowserFallback(text, finishCallback, preferredGender) {
    if (!window.speechSynthesis) {
      finishCallback();
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'fr-FR';
    utterance.rate = 1.0;
    utterance.pitch = preferredGender === 'female' ? 1.02 : 0.98;

    const bestVoice = pickBestBrowserFrenchVoice(preferredGender);
    if (bestVoice) utterance.voice = bestVoice;

    utterance.onend = finishCallback;
    utterance.onerror = finishCallback;

    var wordCount = (text || '').split(/\s+/).length;
    var maxWaitMs = Math.max(3500, (wordCount / 2.1) * 1000 + 2500);
    setTimeout(function () {
      if (isSpeaking) finishCallback();
    }, maxWaitMs);

    setTimeout(function () {
      window.speechSynthesis.speak(utterance);
    }, 50);
  }

  async function speakReply(text, onComplete) {
    if (currentAudio) {
      try {
        currentAudio.pause();
        currentAudio.src = '';
      } catch (e) {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    isSpeaking = true;
    wave.classList.add('rq-wave-active');
    voiceStatus.textContent = 'Le Concierge vous parle (Voix HD)...';

    var hasEnded = false;
    function finish() {
      if (hasEnded) return;
      hasEnded = true;
      isSpeaking = false;
      wave.classList.remove('rq-wave-active');
      if (isCalling) voiceStatus.textContent = 'À votre écoute...';
      if (onComplete) onComplete();
    }

    const selectedProfile = (voiceProfileSelect && voiceProfileSelect.value) || 'henri';
    const preferredGender = (selectedProfile === 'vivienne' || selectedProfile === 'denise') ? 'female' : 'male';

    // Option 1: Try Neural HD Server TTS first
    try {
      const ttsResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({ text: text, voice: selectedProfile }),
      });

      if (ttsResp.ok) {
        const audioBlob = await ttsResp.blob();
        if (audioBlob && audioBlob.size > 200) {
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          currentAudio = audio;
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
    } catch (e) {
      // Fallback to Option 2 (Ranked Browser Neural Voice)
    }

    // Option 2: Smart Ranked Browser Neural Voice Fallback
    speakWithBrowserFallback(text, finish, preferredGender);
  }

  async function startVoiceCall() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      alert("Votre navigateur ne supporte pas la reconnaissance vocale. Utilisez Chrome, Edge ou Safari.");
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({ page_url: window.location.href }),
      });
      const data = await resp.json();
      voiceSessionId = data.session_id;

      isCalling = true;
      orb.classList.add('rq-calling');
      btnToggleCall.classList.add('rq-btn-hangup');
      btnToggleCall.innerHTML = '<span>🔴 Raccrocher</span>';
      voiceStatus.textContent = 'Appel en cours';
      setVoiceTranscript('Concierge', data.greeting_text);

      // Speak greeting
      speakReply(data.greeting_text, () => {
        listenToUser();
      });
    } catch (err) {
      voiceStatus.textContent = 'Erreur de connexion';
      voiceTranscript.textContent = "Impossible de joindre le serveur vocal.";
    }
  }

  function listenToUser() {
    if (!isCalling) return;
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) return;

    try {
      if (recognition) {
        recognition.onend = null;
        recognition.onerror = null;
        try { recognition.abort(); } catch(e) {}
      }
    } catch(e) {}

    recognition = new SpeechRec();
    recognition.lang = 'fr-FR';
    recognition.continuous = false;
    recognition.interimResults = true;

    var finishTimeout = null;

    recognition.onstart = function() {
      voiceStatus.textContent = 'À votre écoute... Parlez.';
    };

    recognition.onresult = function(event) {
      var interim = '';
      var final = '';
      for (var i = 0; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          final += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      var spoken = (final || interim).trim();
      if (spoken) {
        setVoiceTranscript('Vous', spoken);
        clearTimeout(finishTimeout);
        finishTimeout = setTimeout(function() {
          try { recognition.stop(); } catch(e) {}
        }, 1200);
      }
    };

    recognition.onend = async function() {
      clearTimeout(finishTimeout);
      var transcript = voiceTranscript.innerText.replace(/^Vous\s*:\s*/i, '').trim();
      if (isCalling && transcript && !isSpeaking) {
        await processVoiceTurn(transcript);
      } else if (isCalling && !isSpeaking) {
        setTimeout(listenToUser, 500);
      }
    };

    recognition.onerror = function() {
      clearTimeout(finishTimeout);
      if (isCalling && !isSpeaking) {
        setTimeout(listenToUser, 800);
      }
    };

    try {
      recognition.start();
    } catch(err) {
      setTimeout(listenToUser, 800);
    }
  }

  async function processVoiceTurn(userText) {
    voiceStatus.textContent = 'Traitement de votre parole...';
    try {
      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
        body: JSON.stringify({
          session_id: voiceSessionId,
          user_speech_transcript: userText,
        }),
      });

      const data = await resp.json();
      setVoiceTranscript('Concierge', data.agent_reply_text);

      speakReply(data.agent_reply_text, () => {
        if (data.should_end_call) {
          stopVoiceCall();
        } else {
          listenToUser();
        }
      });
    } catch (err) {
      voiceStatus.textContent = 'Erreur réseau';
      speakReply("Désolé, une coupure est survenue. Pouvez-vous répéter ?", () => {
        listenToUser();
      });
    }
  }

  function stopVoiceCall() {
    isCalling = false;
    isSpeaking = false;
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
    }
    if (currentAudio) {
      try {
        currentAudio.pause();
        currentAudio.src = '';
      } catch (e) {}
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    orb.classList.remove('rq-calling');
    wave.classList.remove('rq-wave-active');
    btnToggleCall.classList.remove('rq-btn-hangup');
    btnToggleCall.innerHTML = "<span>📞 Démarrer l'appel vocal</span>";
    voiceStatus.textContent = 'Appel terminé';
  }

  btnToggleCall.addEventListener('click', () => {
    if (isCalling) {
      stopVoiceCall();
    } else {
      startVoiceCall();
    }
  });

  orb.addEventListener('click', () => {
    if (!isCalling) startVoiceCall();
  });

  const btnTestVoice = chatWindow.querySelector('#rq-btn-test-voice');
  if (btnTestVoice) {
    btnTestVoice.addEventListener('click', () => {
      const profile = (voiceProfileSelect && voiceProfileSelect.value) || 'henri';
      const sampleText =
        profile === 'vivienne' || profile === 'denise'
          ? "Bonjour ! Je suis le concierge vocal haute définition de Rockib Quenum. Je peux vous présenter MARTISTORE, WaAuto et l'Agence IIA."
          : "Bonjour ! Je suis le concierge vocal haute définition de Rockib Quenum. Parlez-moi de votre projet d'architecture ou d'automatisation IA.";
      setVoiceTranscript('Concierge (Test HD)', sampleText);
      speakReply(sampleText, () => {
        if (!isCalling) voiceStatus.textContent = 'Prêt pour votre appel vocal';
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
