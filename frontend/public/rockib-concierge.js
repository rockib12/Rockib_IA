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

  const widgetScript = document.currentScript || document.querySelector('script[data-site-key]') || document.querySelector('script[src*="rockib-concierge"]');
  const API_BASE = String(window.ROCKIB_API_URL || widgetScript?.getAttribute('data-api-base') || (
    window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? 'http://127.0.0.1:8080'
      : 'https://dion-beaverlike-preceptively.ngrok-free.dev'
  )).replace(/\/+$/, '');

  function detectInitialSiteKey() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('concierge_site')) return urlParams.get('concierge_site').trim();
    } catch (e) {}
    if (window.ROCKIB_SITE_KEY) return String(window.ROCKIB_SITE_KEY).trim();
    const scriptTag = widgetScript;
    if (scriptTag && scriptTag.getAttribute('data-site-key')) {
      return scriptTag.getAttribute('data-site-key').trim();
    }
    return 'rockib-portfolio';
  }

  let currentSiteKey = detectInitialSiteKey();
  let sitePrimaryRgb = '0, 240, 255';
  let currentSiteConfig = null;

  const conversationStorageKey = (siteKey) => 'rq_concierge_conv_id_' + siteKey;
  let conversationId = sessionStorage.getItem(conversationStorageKey(currentSiteKey)) || null;
  let isOpen = false;
  let activeTab = 'chat'; // 'chat' | 'voice' | 'callback'

  // Voice Call State
  let voiceSessionId = null;
  let isCalling = false;
  let recognition = null;
  let isSpeaking = false;

  // 1. Scoped CSS
  const styles = `
    :root {
      --rq-accent: #00F0FF;
      --rq-accent-rgb: 0, 240, 255;
    }
    .rq-launcher {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      display: flex;
      align-items: center;
      gap: 10px;
      background: #05070B;
      border: 1px solid var(--rq-accent);
      color: #EDF5FF;
      padding: 10px 18px;
      border-radius: 9999px;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.8), 0 0 16px rgba(var(--rq-accent-rgb), 0.35);
      font-family: 'Plex Mono', monospace;
      font-size: 13px;
      font-weight: 600;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .rq-launcher.rq-pos-left {
      right: auto;
      left: 24px;
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
      border: 1px solid rgba(var(--rq-accent-rgb), 0.32);
      border-radius: 14px;
      display: flex;
      flex-direction: column;
      z-index: 999999;
      box-shadow: 0 16px 45px rgba(0, 0, 0, 0.9), 0 0 30px rgba(var(--rq-accent-rgb), 0.18);
      font-family: 'Plex Mono', monospace;
      color: #EDF5FF;
      overflow: hidden;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      opacity: 0;
      pointer-events: none;
      transform: translateY(12px) scale(0.98);
    }
    .rq-window.rq-pos-left {
      right: auto;
      left: 24px;
    }
    .rq-window.rq-open {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0) scale(1);
    }
    .rq-header {
      padding: 12px 16px;
      background: #0A101C;
      border-bottom: 1px solid rgba(var(--rq-accent-rgb), 0.15);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .rq-title {
      font-size: 13px;
      font-weight: 700;
      color: var(--rq-accent);
      display: flex;
      align-items: center;
      gap: 6px;
      text-shadow: 0 0 10px rgba(var(--rq-accent-rgb), 0.4);
    }
    .rq-subtitle {
      font-size: 10px;
      color: #7E90A6;
      margin-top: 1px;
    }
    .rq-header-actions {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .rq-btn-icon {
      background: none;
      border: none;
      color: #7E90A6;
      cursor: pointer;
      font-size: 15px;
      padding: 4px 6px;
      line-height: 1;
      border-radius: 6px;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .rq-btn-icon:hover {
      color: var(--rq-accent);
      background: rgba(255, 255, 255, 0.08);
    }
    /* ChatGPT Floating Round Call Orb (Rondelle Flottante) */
    .rq-floating-orb {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #0F172A, #030712 90%);
      border: 2px solid var(--rq-accent);
      box-shadow: 0 10px 32px rgba(0, 0, 0, 0.9), 0 0 25px rgba(var(--rq-accent-rgb), 0.45);
      z-index: 1000000;
      cursor: pointer;
      display: none;
      align-items: center;
      justify-content: center;
      transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease;
      user-select: none;
    }
    .rq-floating-orb.rq-pos-left {
      right: auto;
      left: 24px;
    }
    .rq-floating-orb.rq-visible {
      display: flex;
      animation: rq-orb-pop 0.32s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .rq-floating-orb:hover {
      transform: scale(1.08) translateY(-2px);
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.95), 0 0 35px rgba(0, 240, 255, 0.65);
      border-color: #00F0FF;
    }
    @keyframes rq-orb-pop {
      0% { opacity: 0; transform: scale(0.4) translateY(20px); }
      100% { opacity: 1; transform: scale(1) translateY(0); }
    }
    .rq-floating-canvas {
      width: 62px;
      height: 62px;
      border-radius: 50%;
      pointer-events: none;
    }
    .rq-floating-badge {
      position: absolute;
      top: -2px;
      right: -2px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #00FF9D;
      border: 2px solid #030712;
      box-shadow: 0 0 8px #00FF9D;
      animation: rq-glow 1.8s infinite;
    }
    .rq-floating-tooltip {
      position: absolute;
      bottom: 78px;
      right: 0;
      background: rgba(6, 10, 20, 0.94);
      border: 1px solid rgba(0, 240, 255, 0.35);
      border-radius: 8px;
      padding: 5px 10px;
      font-size: 11px;
      color: #EDF5FF;
      white-space: nowrap;
      pointer-events: none;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.7);
      opacity: 0;
      transform: translateY(6px);
      transition: all 0.2s ease;
    }
    .rq-floating-orb:hover .rq-floating-tooltip {
      opacity: 1;
      transform: translateY(0);
    }
    .rq-floating-controls {
      position: absolute;
      top: -28px;
      left: 50%;
      transform: translateX(-50%);
      display: none;
      gap: 6px;
      background: rgba(3, 7, 18, 0.94);
      border: 1px solid rgba(0, 240, 255, 0.35);
      border-radius: 999px;
      padding: 3px 8px;
      backdrop-filter: blur(8px);
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.6);
      white-space: nowrap;
    }
    .rq-floating-orb:hover .rq-floating-controls {
      display: flex;
    }
    .rq-floating-btn {
      background: none;
      border: none;
      color: #EDF5FF;
      cursor: pointer;
      font-size: 12px;
      padding: 2px 4px;
      display: grid;
      place-items: center;
      border-radius: 4px;
      transition: all 0.15s;
    }
    .rq-floating-btn:hover {
      color: #00F0FF;
      transform: scale(1.2);
    }
    .rq-floating-btn.hangup:hover {
      color: #FF3366;
    }
    .rq-tabs {
      display: flex;
      background: #070B14;
      border-bottom: 1px solid rgba(var(--rq-accent-rgb), 0.15);
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
      color: var(--rq-accent);
      border-bottom-color: var(--rq-accent);
      background: #0A101C;
      text-shadow: 0 0 8px rgba(var(--rq-accent-rgb), 0.4);
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
      border: 1px solid rgba(var(--rq-accent-rgb), 0.18);
      color: #EDF5FF;
      border-left: 2px solid var(--rq-accent);
    }
    .rq-msg-user {
      align-self: flex-end;
      background: linear-gradient(135deg, var(--rq-accent) 0%, #00FF9D 100%);
      color: #03070E;
      font-weight: 700;
      box-shadow: 0 0 14px rgba(var(--rq-accent-rgb), 0.35);
    }
    .rq-suggestions {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 4px;
    }
    .rq-chip {
      background: #080D1A;
      border: 1px solid rgba(var(--rq-accent-rgb), 0.18);
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
      background: rgba(var(--rq-accent-rgb), 0.1);
      border-color: var(--rq-accent);
      color: var(--rq-accent);
      box-shadow: 0 0 10px rgba(var(--rq-accent-rgb), 0.2);
    }
    .rq-nav-banner {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      background: rgba(var(--rq-accent-rgb), 0.12);
      border: 1px solid var(--rq-accent);
      color: #EDF5FF;
      font-size: 11px;
      font-weight: 600;
      padding: 5px 10px;
      border-radius: 999px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .rq-nav-banner:hover {
      background: rgba(var(--rq-accent-rgb), 0.25);
      box-shadow: 0 0 12px rgba(var(--rq-accent-rgb), 0.4);
      transform: translateY(-1px);
    }
    @keyframes rq-section-glow {
      0% { box-shadow: 0 0 0 rgba(0, 240, 255, 0); }
      50% { box-shadow: 0 0 40px rgba(0, 240, 255, 0.65), 0 0 20px rgba(0, 255, 157, 0.5); }
      100% { box-shadow: 0 0 0 rgba(0, 240, 255, 0); }
    }
    .rq-highlight-target {
      animation: rq-section-glow 2.2s cubic-bezier(0.16, 1, 0.3, 1) ease-out;
      border-radius: 14px;
    }
    .rq-input-area {
      padding: 12px;
      background: #0A101C;
      border-top: 1px solid rgba(var(--rq-accent-rgb), 0.15);
      display: flex;
      gap: 8px;
    }
    .rq-input {
      flex: 1;
      background: #05070B;
      border: 1px solid rgba(var(--rq-accent-rgb), 0.22);
      border-radius: 6px;
      color: #EDF5FF;
      font-family: inherit;
      font-size: 12px;
      padding: 9px 12px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .rq-input:focus {
      border-color: var(--rq-accent);
      box-shadow: 0 0 10px rgba(var(--rq-accent-rgb), 0.25);
    }
    .rq-send {
      background: linear-gradient(135deg, var(--rq-accent) 0%, #00FF9D 100%);
      border: none;
      color: #03070E;
      font-weight: 700;
      border-radius: 6px;
      padding: 0 14px;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
      box-shadow: 0 0 12px rgba(var(--rq-accent-rgb), 0.3);
    }
    .rq-send:hover {
      transform: translateY(-1px);
      box-shadow: 0 0 18px rgba(var(--rq-accent-rgb), 0.5);
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
      <div style="cursor:pointer; flex:1; overflow:hidden;" id="rq-header-drag" title="Cliquer pour réduire ou agrandir">
        <div class="rq-title">
          <span class="rq-pulse" style="width:7px; height:7px;"></span>
          <span id="rq-header-title-text">Rockib Quenum · Co-Architecte &amp; IA</span>
        </div>
        <div class="rq-subtitle" id="rq-header-subtitle">Architecture · Projets · Vocal Temps Réel</div>
      </div>
      <div class="rq-header-actions">
        <button class="rq-btn-icon" id="rq-btn-minimize" title="Minimiser la fenêtre">🗕</button>
        <button class="rq-btn-icon rq-close" id="rq-btn-close" title="Fermer">✕</button>
      </div>
    </div>
    <div class="rq-tabs">
      <button class="rq-tab-btn rq-active" data-tab="chat">💬 Assistant & Archi</button>
      <button class="rq-tab-btn" data-tab="voice">🎙️ Vocal Live</button>
      <button class="rq-tab-btn" data-tab="callback">📲 Rappel</button>
    </div>

    <!-- Panel 1: Chat -->
    <div class="rq-panel rq-active" id="rq-panel-chat">
      <div class="rq-messages" id="rq-messages-container">
        <div class="rq-msg rq-msg-assistant">Bonjour ! Je suis l'Assistant IA et Co-Architecte de Rockib Quenum.

Je peux vous proposer des idées concrètes d'applications ou d'automatisations IA pour votre activité, concevoir votre architecture technique, ou vous présenter ses systèmes en production (Rockib AI Engine, MARTISTORE, WaAuto, Agence IIA).

Quelle est votre activité ou votre idée de projet ?</div>
        <div class="rq-suggestions" id="rq-suggestions-container">
          <button class="rq-chip" data-query="Propose-moi des idées concrètes d'automatisation IA et d'applications rentables pour développer mon activité.">💡 Propose-moi des idées d'IA pour mon activité</button>
          <button class="rq-chip" data-query="Je souhaite être rappelé directement par Rockib pour discuter de mon projet et du devis.">📞 Demander à être rappelé par Rockib</button>
          <button class="rq-chip" data-query="Présente-moi en détail les projets en production de Rockib (Rockib AI, MARTISTORE, WaAuto, Agence IIA).">🚀 Découvrir les projets en production de Rockib</button>
          <button class="rq-chip" data-query="Propose-moi une architecture technique complète et moderne pour mon futur projet.">🏗️ Concevoir l'architecture de mon projet</button>
        </div>
      </div>
      <form class="rq-input-area" id="rq-chat-form">
        <input type="text" class="rq-input" id="rq-input-field" placeholder="Parlez-moi de votre activité, demandez des idées..." autocomplete="off" />
        <button type="submit" class="rq-send">➤</button>
      </form>
    </div>

    <!-- Panel 2: Live Voice Calling (ChatGPT Advanced Voice Mode UI) -->
    <div class="rq-panel" id="rq-panel-voice">
      <div class="rq-voice-container" style="justify-content:space-between; padding:14px 18px;">
        <!-- Top Voice Selector Bar -->
        <div style="display:flex; align-items:center; justify-content:space-between; width:100%; gap:6px;">
          <div style="display:flex; align-items:center; gap:6px;">
            <span id="rq-voice-badge" style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#64748B;"></span>
            <span id="rq-voice-mode-label" style="font-size:10px; color:#94A3B8; text-transform:uppercase; letter-spacing:0.08em;">Co-Architecte Vocal</span>
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
        <div style="position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; margin:2px 0;">
          <canvas id="rq-voice-canvas" width="176" height="176" style="width:176px; height:176px; cursor:pointer;" title="Touchez la sphère pour parler ou interrompre"></canvas>
          <div id="rq-voice-orb" style="display:none;"></div>
          <div id="rq-voice-wave" style="display:none;"></div>
          <div class="rq-voice-status" id="rq-voice-status" style="margin-top:4px; font-size:13.5px; font-weight:700; color:#EDF5FF; letter-spacing:0.01em;">Touchez pour démarrer</div>
          <div id="rq-voice-meter" style="display:none; align-items:center; justify-content:center; gap:4px; height:18px; margin:4px 0;">
            <span class="rq-vu-bar" style="display:inline-block; width:3.5px; height:4px; background:#00FF9D; border-radius:2px; transition:height 0.05s ease;"></span>
            <span class="rq-vu-bar" style="display:inline-block; width:3.5px; height:7px; background:#00FF9D; border-radius:2px; transition:height 0.05s ease;"></span>
            <span class="rq-vu-bar" style="display:inline-block; width:3.5px; height:11px; background:#00FF9D; border-radius:2px; transition:height 0.05s ease;"></span>
            <span class="rq-vu-bar" style="display:inline-block; width:3.5px; height:7px; background:#00FF9D; border-radius:2px; transition:height 0.05s ease;"></span>
            <span class="rq-vu-bar" style="display:inline-block; width:3.5px; height:4px; background:#00FF9D; border-radius:2px; transition:height 0.05s ease;"></span>
          </div>
          <div class="rq-voice-sub" id="rq-voice-sub" style="margin-top:2px; font-size:10.5px; color:#7E90A6;">Idées de projets · Architectures · Projets en production</div>
        </div>

        <!-- Live Subtitle / Caption Box -->
        <div class="rq-voice-transcript" id="rq-voice-transcript" style="width:100%; min-height:48px; max-height:94px; overflow-y:auto; text-align:center; font-size:11.5px; border-radius:12px; background:rgba(10,16,28,0.85);">
          <em>Parlez de votre activité : je vous propose des idées d'IA, une architecture sur mesure et je vous mets en relation directe avec Rockib !</em>
        </div>

        <!-- Quick Voice Topics + Bottom Control Dock -->
        <div style="display:flex; flex-direction:column; gap:8px; width:100%; align-items:center;">
          <div style="display:flex; gap:5px; flex-wrap:wrap; justify-content:center; width:100%;">
            <button type="button" class="rq-voice-topic-chip" data-prompt="Je souhaite laisser mes coordonnées téléphoniques pour que Rockib me rappelle pour mon projet." style="background:rgba(232,163,61,0.12); border:1px solid rgba(232,163,61,0.4); color:#EDF5FF; border-radius:999px; padding:4px 9px; font-size:10px; cursor:pointer;">📞 Demander un Rappel</button>
            <button type="button" class="rq-voice-topic-chip" data-prompt="Propose-moi des idées innovantes de projets IA et d'automatisations rentables que Rockib peut créer pour une entreprise." style="background:rgba(0,255,157,0.08); border:1px solid rgba(0,255,157,0.3); color:#EDF5FF; border-radius:999px; padding:4px 9px; font-size:10px; cursor:pointer;">💡 Proposer des Idées</button>
            <button type="button" class="rq-voice-topic-chip" data-prompt="Présente-moi les projets en production de Rockib Quenum." style="background:rgba(0,240,255,0.08); border:1px solid rgba(0,240,255,0.3); color:#EDF5FF; border-radius:999px; padding:4px 9px; font-size:10px; cursor:pointer;">🚀 Ses Projets</button>
            <button type="button" class="rq-voice-topic-chip" data-prompt="Propose-moi une architecture technique moderne et explique comment voir le prix avec Rockib." style="background:rgba(168,85,247,0.1); border:1px solid rgba(168,85,247,0.35); color:#EDF5FF; border-radius:999px; padding:4px 9px; font-size:10px; cursor:pointer;">🏗️ Devis & Archi</button>
          </div>
          <div style="display:flex; align-items:center; justify-content:center; gap:14px; width:100%;">
            <button type="button" id="rq-btn-mute" title="Couper / Activer le micro" style="display:none; width:40px; height:40px; border-radius:50%; border:1px solid rgba(255,255,255,0.18); background:#111827; color:#EDF5FF; font-size:16px; align-items:center; justify-content:center; cursor:pointer; transition:all 0.2s;">
              🎙️
            </button>
            <button type="button" class="rq-btn-call" id="rq-btn-toggle-call" style="border-radius:999px; padding:10px 22px; font-size:12px;">
              <span>📞 Démarrer la conversation</span>
            </button>
            <button type="button" id="rq-btn-send-speech" title="Forcer l'envoi immédiat" style="display:none; width:40px; height:40px; border-radius:50%; border:1px solid rgba(0,255,157,0.5); background:rgba(0,255,157,0.12); color:#00FF9D; font-size:15px; align-items:center; justify-content:center; cursor:pointer; transition:all 0.2s;">
              ✓
            </button>
          </div>
          <form id="rq-voice-quick-form" style="display:flex; gap:6px; width:100%;">
            <input type="text" id="rq-voice-quick-input" class="rq-input" placeholder="Ou écrivez votre sujet d'architecture / question ici..." style="font-size:11px; padding:6px 12px; border-radius:999px;" autocomplete="off" />
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

  const floatingOrb = document.createElement('div');
  const orbPosClass = (typeof posClass !== 'undefined' && posClass) ? ' ' + posClass : '';
  floatingOrb.className = 'rq-floating-orb' + orbPosClass;
  floatingOrb.id = 'rq-floating-orb';
  floatingOrb.innerHTML = `
    <div class="rq-floating-badge" id="rq-floating-badge"></div>
    <canvas class="rq-floating-canvas" id="rq-floating-canvas" width="62" height="62"></canvas>
    <div class="rq-floating-tooltip" id="rq-floating-tooltip">Appel vocal IA actif · Touchez pour rouvrir</div>
    <div class="rq-floating-controls">
      <button type="button" class="rq-floating-btn" id="rq-float-mute" title="Couper / Activer le micro">🎙️</button>
      <button type="button" class="rq-floating-btn hangup" id="rq-float-hangup" title="Raccrocher">✕</button>
    </div>
  `;

  document.body.appendChild(launcher);
  document.body.appendChild(chatWindow);
  document.body.appendChild(floatingOrb);

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

  // Open/Close & Minimize State
  let isMinimized = false;

  function toggleMinimize(forceState) {
    isMinimized = forceState !== undefined ? forceState : !isMinimized;
    const tooltip = floatingOrb.querySelector('#rq-floating-tooltip');

    if (isMinimized) {
      // Hide full chat window and launcher, reveal the round floating orb
      chatWindow.classList.remove('rq-open');
      launcher.style.display = 'none';
      floatingOrb.classList.add('rq-visible');
      if (tooltip) {
        tooltip.textContent = isCalling
          ? 'Appel vocal IA actif · Touchez pour rouvrir'
          : 'Concierge IA · Touchez pour rouvrir';
      }
    } else {
      // Restore full chat window, hide round floating orb
      floatingOrb.classList.remove('rq-visible');
      if (isOpen) {
        chatWindow.classList.add('rq-open');
        launcher.style.display = 'none';
      } else {
        launcher.style.display = '';
      }
    }
  }

  function toggleChat(forceState) {
    isOpen = forceState !== undefined ? forceState : !isOpen;
    if (isOpen) {
      chatWindow.classList.add('rq-open');
      launcher.style.display = 'none';
      toggleMinimize(false);
    } else {
      chatWindow.classList.remove('rq-open');
      launcher.style.display = '';
      floatingOrb.classList.remove('rq-visible');
      isMinimized = false;
      if (isCalling) stopVoiceCall();
    }
  }

  // Clicking the floating orb restores the full window
  floatingOrb.addEventListener('click', (e) => {
    // If click was on control buttons, don't trigger parent restore
    if (e.target.closest('.rq-floating-controls')) return;
    toggleMinimize(false);
  });

  // Floating controls: Mute & Hangup
  const floatMuteBtn = floatingOrb.querySelector('#rq-float-mute');
  if (floatMuteBtn) {
    floatMuteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (btnMute) btnMute.click();
      floatMuteBtn.textContent = isMuted ? '🔇' : '🎙️';
    });
  }

  const floatHangupBtn = floatingOrb.querySelector('#rq-float-hangup');
  if (floatHangupBtn) {
    floatHangupBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      stopVoiceCall();
      toggleMinimize(false);
      toggleChat(false);
    });
  }

  launcher.addEventListener('click', () => {
    if (isMinimized) {
      toggleMinimize(false);
    } else {
      toggleChat();
    }
  });

  const btnClose = chatWindow.querySelector('#rq-btn-close') || chatWindow.querySelector('.rq-close');
  if (btnClose) {
    btnClose.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleChat(false);
    });
  }

  const btnMinimize = chatWindow.querySelector('#rq-btn-minimize');
  if (btnMinimize) {
    btnMinimize.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleMinimize();
    });
  }

  const headerDrag = chatWindow.querySelector('#rq-header-drag');
  if (headerDrag) {
    headerDrag.addEventListener('click', () => {
      if (isMinimized) {
        toggleMinimize(false);
      }
    });
  }

  // --- Chat Section ---
  const messagesContainer = chatWindow.querySelector('#rq-messages-container');
  const suggestionsContainer = chatWindow.querySelector('#rq-suggestions-container');
  const chatForm = chatWindow.querySelector('#rq-chat-form');
  const inputField = chatWindow.querySelector('#rq-input-field');

  // --- Autonomous Navigation & Co-Pilot Action Engine ---
  const NAV_TARGET_MAP = {
    'projets': '#projets',
    'projet': '#projets',
    'projects': '#projets',
    'realisations': '#projets',
    'martistore': '#card-martistore',
    'waauto': '#card-waauto-commercial',
    'rockib-ai': '#card-rockib-ai',
    'agence-iia': '#card-agence-iia',
    'connaissances': '#connaissances',
    'competences': '#connaissances',
    'skills': '#connaissances',
    'technologies': '#connaissances',
    'stack': '#connaissances',
    'idees': '#idees-ia',
    'idees-ia': '#idees-ia',
    'innovations': '#idees-ia',
    'services': '#services',
    'offres': '#services',
    'contact': '#contact',
    'devis': '#contact',
    'tarifs': '#contact',
    'prix': '#contact',
    'concierge': 'concierge-ia.html',
    'concierge-ia': 'concierge-ia.html',
    'concierge-ia.html': 'concierge-ia.html',
  };

  function resolveNavTarget(rawTarget) {
    if (!rawTarget) return null;
    let clean = rawTarget.trim().replace(/^\[+|\]+$/g, '');
    const lower = clean.toLowerCase().replace(/^#/, '');
    if (NAV_TARGET_MAP[lower]) return NAV_TARGET_MAP[lower];
    if (clean.startsWith('#') || clean.endsWith('.html') || clean.includes('/')) return clean;
    return '#' + clean;
  }

  function detectUserNavIntent(userQuery) {
    if (!userQuery) return null;
    const q = userQuery.toLowerCase();
    if (q.includes('projet') || q.includes('réalisation') || q.includes('realisation') || q.includes('martistore') || q.includes('waauto')) return '#projets';
    if (q.includes('compétence') || q.includes('competence') || q.includes('techno') || q.includes('stack') || q.includes('connaissance')) return '#connaissances';
    if (q.includes('idée') || q.includes('idee') || q.includes('innovation') || q.includes('secteur')) return '#idees-ia';
    if (q.includes('service') || q.includes('offre') || q.includes('prestation')) return '#services';
    if (q.includes('contact') || q.includes('prix') || q.includes('tarif') || q.includes('devis') || q.includes('numéro') || q.includes('numero') || q.includes('email') || q.includes('whatsapp') || q.includes('rappel')) return '#contact';
    if (q.includes('concierge') || q.includes('widget') || q.includes('vocal')) return 'concierge-ia.html';
    return null;
  }

  function executeNavigationAction(target, userInitiated) {
    if (!target) return false;
    const cleanTarget = resolveNavTarget(target);
    if (!cleanTarget) return false;

    // Case 1: In-page anchor (e.g. #projets, #connaissances, #idees-ia, #services, #contact)
    if (cleanTarget.startsWith('#')) {
      try {
        const id = cleanTarget.replace('#', '');
        const elem = document.getElementById(id) || document.querySelector(cleanTarget);
        if (elem) {
          elem.scrollIntoView({ behavior: 'smooth', block: 'start' });
          elem.classList.remove('rq-highlight-target');
          void elem.offsetWidth;
          elem.classList.add('rq-highlight-target');
          setTimeout(() => {
            elem.classList.remove('rq-highlight-target');
          }, 3500);
          return true;
        }
      } catch (err) {}
    }

    // Case 2: Relative or full URL (e.g. concierge-ia.html, /concierge-ia.html, https://...)
    if (cleanTarget.endsWith('.html') || cleanTarget.includes('/') || cleanTarget.startsWith('http')) {
      if (userInitiated) {
        window.location.href = cleanTarget;
      } else {
        setTimeout(() => {
          window.location.href = cleanTarget;
        }, 1600);
      }
      return true;
    }
    return false;
  }

  function parseAndExecuteNav(rawText) {
    if (!rawText) return { cleanText: '', navTarget: null };

    // Flexible multi-format matching: [[NAV:...]], [NAV:...], or NAV:...
    let navTarget = null;
    let cleanText = rawText;

    const navMatch = rawText.match(/\[\[NAV:([^\]]+)\]\]/i) ||
                     rawText.match(/\[NAV:([^\]]+)\]/i) ||
                     rawText.match(/\bNAV:\s*([#a-zA-Z0-9_\-\.\/]+)/i);

    if (navMatch) {
      navTarget = resolveNavTarget(navMatch[1]);
      cleanText = cleanText
        .replace(/\[\[NAV:[^\]]+\]\]/gi, '')
        .replace(/\[NAV:[^\]]+\]/gi, '')
        .replace(/\bNAV:\s*[#a-zA-Z0-9_\-\.\/]+/gi, '')
        .trim();
    }

    if (navTarget) {
      executeNavigationAction(navTarget, false);
    }
    return { cleanText: cleanText, navTarget: navTarget };
  }

  function appendChatMessage(text, role, navTarget) {
    const el = document.createElement('div');
    el.className = `rq-msg rq-msg-${role}`;
    el.textContent = text;

    if (role === 'assistant' && navTarget) {
      const banner = document.createElement('div');
      banner.className = 'rq-nav-banner';
      const label = navTarget.startsWith('#')
        ? `📍 Naviguer vers ${navTarget.replace('#', '')}`
        : `🔗 Ouvrir ${navTarget}`;
      banner.innerHTML = `<span>🧭</span> <span>${label}</span>`;
      banner.addEventListener('click', (e) => {
        e.stopPropagation();
        executeNavigationAction(navTarget, true);
      });
      el.appendChild(document.createElement('br'));
      el.appendChild(banner);
    }

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
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true', },
        body: JSON.stringify({
          message: userMsg,
          conversation_id: conversationId,
          page_url: window.location.href,
          site_key: currentSiteKey,
        }),
      });

      const data = await response.json();
      loadingEl.remove();

      if (data.conversation_id) {
        conversationId = data.conversation_id;
        sessionStorage.setItem(conversationStorageKey(currentSiteKey), conversationId);
      }

      const rawReply = data.reply || "Je n'ai pas pu obtenir de réponse.";
      const parsed = parseAndExecuteNav(rawReply);
      appendChatMessage(parsed.cleanText, 'assistant', parsed.navTarget);
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
    if (!voiceCanvas || typeof voiceCanvas.getContext !== 'function') return;
    const ctx = voiceCanvas.getContext('2d');
    const floatingCanvas = floatingOrb ? floatingOrb.querySelector('#rq-floating-canvas') : null;
    const floatCtx = (floatingCanvas && typeof floatingCanvas.getContext === 'function')
      ? floatingCanvas.getContext('2d')
      : null;
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

    function drawFluidBlob(targetCtx, w, h, radiusScale) {
      const cx = w / 2;
      const cy = h / 2;
      targetCtx.clearRect(0, 0, w, h);

      // Color palette by state (ChatGPT Voice style, using client's primary color)
      let c1 = sitePrimaryRgb;  // Client Accent (default Cyan)
      let c2 = '99, 102, 241';  // Indigo
      if (orbState === 'user_speaking') {
        c1 = '0, 255, 157';     // Emerald
        c2 = sitePrimaryRgb;
      } else if (orbState === 'thinking') {
        c1 = '168, 85, 247';    // Violet
        c2 = sitePrimaryRgb;
      } else if (orbState === 'ai_speaking') {
        c1 = sitePrimaryRgb;
        c2 = '237, 245, 255';   // Luminous White-Cyan
      }

      const baseR = (46 + orbLevel * 22) * radiusScale;

      // Outer atmospheric glow
      const outerGrad = targetCtx.createRadialGradient(cx, cy, baseR * 0.3, cx, cy, baseR * 1.75);
      outerGrad.addColorStop(0, `rgba(${c1}, ${0.32 + orbLevel * 0.35})`);
      outerGrad.addColorStop(0.55, `rgba(${c2}, ${0.14 + orbLevel * 0.18})`);
      outerGrad.addColorStop(1, 'rgba(6, 9, 18, 0)');
      targetCtx.fillStyle = outerGrad;
      targetCtx.beginPath();
      targetCtx.arc(cx, cy, baseR * 1.75, 0, Math.PI * 2);
      targetCtx.fill();

      // 3 Fluid morphing organic lobes
      for (let layer = 0; layer < 3; layer++) {
        targetCtx.beginPath();
        const pts = 48;
        const layerOffset = layer * 2.1;
        const layerR = baseR * (1 - layer * 0.08);
        const amp = (3.5 + orbLevel * 13) * (1 - layer * 0.2) * radiusScale;

        for (let i = 0; i <= pts; i++) {
          const angle = (i / pts) * Math.PI * 2;
          const wave1 = Math.sin(angle * 3 + phase + layerOffset) * amp;
          const wave2 = Math.cos(angle * 4 - phase * 1.3 + layerOffset) * (amp * 0.55);
          const r = layerR + wave1 + wave2;
          const x = cx + Math.cos(angle) * r;
          const y = cy + Math.sin(angle) * r;
          if (i === 0) targetCtx.moveTo(x, y);
          else targetCtx.lineTo(x, y);
        }
        targetCtx.closePath();

        const grad = targetCtx.createRadialGradient(
          cx - 10 * Math.cos(phase * 0.7) * radiusScale,
          cy - 10 * Math.sin(phase * 0.7) * radiusScale,
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
        targetCtx.fillStyle = grad;
        targetCtx.fill();
      }
    }

    function renderOrb() {
      requestAnimationFrame(renderOrb);

      const isMainActive = isOpen && activeTab === 'voice';
      const isFloatActive = isMinimized;

      if (!isMainActive && !isFloatActive) return;

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

      if (isMainActive && ctx) {
        drawFluidBlob(ctx, voiceCanvas.width, voiceCanvas.height, 1.0);
      }

      if (isFloatActive && floatCtx && floatingCanvas) {
        // Render scaled down to 62x62 in the floating circular disc!
        drawFluidBlob(floatCtx, floatingCanvas.width, floatingCanvas.height, 0.34);
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
    const floatBadge = floatingOrb ? floatingOrb.querySelector('#rq-floating-badge') : null;
    if (floatBadge) {
      if (state === 'listening' || state === 'user_speaking') {
        floatBadge.style.background = '#00FF9D';
        floatBadge.style.boxShadow = '0 0 10px #00FF9D';
      } else if (state === 'thinking') {
        floatBadge.style.background = '#A855F7';
        floatBadge.style.boxShadow = '0 0 10px #A855F7';
      } else if (state === 'ai_speaking') {
        floatBadge.style.background = '#00F0FF';
        floatBadge.style.boxShadow = '0 0 10px #00F0FF';
      } else {
        floatBadge.style.background = '#00FF9D';
        floatBadge.style.boxShadow = '0 0 6px #00FF9D';
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
      recognition.onstart = null;
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;
      try { recognition.abort(); } catch (e) {}
      recognition = null;
    }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.onstop = null;
      mediaRecorder.ondataavailable = null;
      try { mediaRecorder.stop(); } catch (e) {}
    }
    mediaRecorder = null;
    if (btnSendSpeech) btnSendSpeech.style.display = 'none';
    const meter = chatWindow.querySelector('#rq-voice-meter');
    if (meter) meter.style.display = 'none';
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

    // Watchdog timer: GUARANTEES finish() is called so it NEVER stays stuck in speaking mode!
    var maxDuration = Math.max(3500, ((text || '').length / 12) * 1000 + 3000);
    var safetyTimeout = setTimeout(function () {
      if (isSpeaking) finish();
    }, maxDuration);

    function finish() {
      if (hasEnded) return;
      hasEnded = true;
      clearTimeout(safetyTimeout);
      isSpeaking = false;
      if (bargeInCheckInterval) {
        clearInterval(bargeInCheckInterval);
        bargeInCheckInterval = null;
      }
      if (onComplete) onComplete();
    }

    // Monitor microphone during AI speech for hands-free Barge-In (interruption on sustained speech)
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
        if (rms > 28) {
          loudFrames++;
          if (loudFrames >= 5) {
            clearInterval(bargeInCheckInterval);
            bargeInCheckInterval = null;
            interruptAiSpeaking();
          }
        } else {
          loudFrames = Math.max(0, loudFrames - 1);
        }
      }, 100);
    }

    const selectedProfile = (voiceProfileSelect && voiceProfileSelect.value) || 'henri';
    const preferredGender = (selectedProfile === 'vivienne' || selectedProfile === 'denise') ? 'female' : 'male';

    // Option 1: Server Neural HD TTS
    try {
      const ttsResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true', },
        body: JSON.stringify({ text: text, voice: selectedProfile }),
      });

      if (ttsResp.ok && isSpeaking) {
        const audioBlob = await ttsResp.blob();
        if (audioBlob && audioBlob.size > 200 && isSpeaking) {
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
    } catch (e) {}

    if (isSpeaking) {
      speakWithBrowserFallback(text, finish, preferredGender);
    }
  }

  async function startVoiceCall() {
    // 0. Synchronously unlock Web Audio Context on user gesture
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        if (!audioCtx) audioCtx = new AudioContextClass();
        if (audioCtx.state === 'suspended') audioCtx.resume();
      }
    } catch (e) {}

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
      setOrbUiState('idle', 'Microphone requis', "Cliquez sur l'icône de cadenas pour autoriser le micro, ou écrivez.");
      return;
    }

    try {
      setOrbUiState('thinking', 'Connexion vocale...', 'Initialisation de la session temps réel');
      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true', },
        body: JSON.stringify({ page_url: window.location.href, site_key: currentSiteKey }),
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
      setOrbUiState('idle', 'Micro en sourdine', 'Touchez 🎙️ pour réactiver votre micro');
      return;
    }

    const voiceMeter = chatWindow.querySelector('#rq-voice-meter');
    if (voiceMeter) voiceMeter.style.display = 'inline-flex';
    setOrbUiState('listening', 'Micro actif · Je vous écoute...', 'Parlez naturellement ou touchez la sphère pour valider');
    if (btnSendSpeech) btnSendSpeech.style.display = 'inline-flex';

    var capturedSpeech = '';
    var finishTimeout = null;
    var turnSubmitted = false;
    var recognitionActive = false;

    function submitRecognizedText(textToSubmit) {
      if (turnSubmitted || !isCalling || isSpeaking || isProcessingTurn) return;
      var cleaned = (textToSubmit || '').trim();
      if (!cleaned) return;
      turnSubmitted = true;
      clearTimeout(finishTimeout);
      stopActiveListening();
      processVoiceTurn(cleaned);
    }

    // Engine A: Browser Web Speech API (continuous self-healing session)
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
      try {
        recognition = new SpeechRec();
        recognition.lang = 'fr-FR';
        recognition.continuous = false; // continuous = false with onend auto-restart is 10x more resilient in Chrome
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        recognition.onstart = function () {
          recognitionActive = true;
        };

        recognition.onresult = function (event) {
          if (isMuted || turnSubmitted) return;
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
            setOrbUiState('user_speaking', 'Micro actif · Je vous entends...', 'Parlez librement...');
            setVoiceTranscript('Vous (en direct)', spoken);
            clearTimeout(finishTimeout);
            // 980ms of silence after speaking auto-submits turn
            finishTimeout = setTimeout(function () {
              submitRecognizedText(capturedSpeech);
            }, 980);
          }
        };

        recognition.onerror = function (err) {
          if (err && err.error === 'no-speech') {
            return;
          }
        };

        recognition.onend = function () {
          recognitionActive = false;
          if (turnSubmitted) return;
          if (capturedSpeech.trim().length > 1) {
            submitRecognizedText(capturedSpeech);
          } else if (isCalling && !isSpeaking && !isProcessingTurn && !isMuted) {
            // Keep speech recognition continuously running!
            setTimeout(function () {
              if (isCalling && !isSpeaking && !isProcessingTurn && !turnSubmitted && !recognitionActive) {
                try { recognition.start(); } catch (e) {}
              }
            }, 120);
          }
        };

        recognition.start();
      } catch (e) {}
    }

    // Engine B: MediaRecorder + Groq Whisper STT backup + Real-time VU-Meter
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
          if (blob.size < 600) {
            if (isCalling && !isSpeaking && !isProcessingTurn) {
              setTimeout(listenToUser, 200);
            }
            return;
          }
          setOrbUiState('thinking', 'Transcription vocale...', 'Analyse Groq Whisper');
          try {
            var sttResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/stt`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/octet-stream',
                'X-Audio-Ext': 'webm', 'ngrok-skip-browser-warning': 'true'
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

        mediaRecorder.start(250);

        // Real-time audio VU Meter + VAD loop
        var vuBars = chatWindow.querySelectorAll('.rq-vu-bar');
        var speechFrames = 0;
        var hasSpokenAudio = false;
        var silenceStart = 0;
        var noiseFloor = 1.2;

        vadInterval = setInterval(function () {
          if (!isCalling || isSpeaking || turnSubmitted || isMuted) {
            clearInterval(vadInterval);
            vadInterval = null;
            return;
          }

          var rms = 0;
          if (micAnalyser && micTimeData) {
            micAnalyser.getByteTimeDomainData(micTimeData);
            var sumSq = 0;
            for (var i = 0; i < micTimeData.length; i++) {
              var d = micTimeData[i] - 128;
              sumSq += d * d;
            }
            rms = Math.sqrt(sumSq / micTimeData.length);
          }

          // Animate the 5 VU bars based on actual mic energy
          if (vuBars && vuBars.length) {
            var baseH = Math.min(18, Math.max(3.5, rms * 1.5));
            vuBars[0].style.height = Math.max(3, baseH * 0.65) + 'px';
            vuBars[1].style.height = Math.max(4, baseH * 0.95) + 'px';
            vuBars[2].style.height = Math.max(5, baseH * 1.2) + 'px';
            vuBars[3].style.height = Math.max(4, baseH * 0.95) + 'px';
            vuBars[4].style.height = Math.max(3, baseH * 0.65) + 'px';
          }

          var threshold = Math.max(2.6, Math.min(7.5, noiseFloor * 1.9));

          if (rms > threshold) {
            speechFrames++;
            silenceStart = 0;
            if (speechFrames >= 2) {
              hasSpokenAudio = true;
              if (orbState !== 'user_speaking') {
                setOrbUiState('user_speaking', 'Micro actif · Je vous entends...', 'Parlez librement...');
              }
            }
          } else {
            if (!hasSpokenAudio) {
              noiseFloor = noiseFloor * 0.94 + rms * 0.06;
            }
            speechFrames = Math.max(0, speechFrames - 1);
            if (hasSpokenAudio) {
              if (!silenceStart) {
                silenceStart = Date.now();
              } else if (Date.now() - silenceStart > 950) {
                // 950ms pause after speaking -> auto-submit!
                clearInterval(vadInterval);
                vadInterval = null;
                if (capturedSpeech.trim().length > 1) {
                  submitRecognizedText(capturedSpeech);
                } else if (mediaRecorder && mediaRecorder.state === 'recording') {
                  try { mediaRecorder.stop(); } catch (e) {}
                }
              }
            }
          }
        }, 70);
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

    // Immediate local navigation if user requested a section
    const directUserNav = detectUserNavIntent(userText.trim());
    if (directUserNav) {
      executeNavigationAction(directUserNav, false);
    }

    try {
      if (!voiceSessionId) {
        const sResp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true', },
          body: JSON.stringify({ page_url: window.location.href, site_key: currentSiteKey }),
        });
        const sData = await sResp.json();
        voiceSessionId = sData.session_id;
      }

      const resp = await fetch(`${API_BASE}/api/v1/inbound/portfolio/voice/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true', },
        body: JSON.stringify({
          session_id: voiceSessionId,
          user_speech_transcript: userText.trim(),
          site_key: currentSiteKey,
        }),
      });

      const data = await resp.json();
      isProcessingTurn = false;
      const parsedVoice = parseAndExecuteNav(data.agent_reply_text);
      setVoiceTranscript('Concierge', parsedVoice.cleanText);

      speakReply(parsedVoice.cleanText, () => {
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

  function bindVoiceTopicChips() {
    chatWindow.querySelectorAll('.rq-voice-topic-chip').forEach((chip) => {
      chip.onclick = async () => {
        const prompt = chip.getAttribute('data-prompt');
        if (!prompt) return;
        if (isSpeaking) interruptAiSpeaking();
        if (!isCalling) {
          isCalling = true;
          btnToggleCall.classList.add('rq-btn-hangup');
          btnToggleCall.innerHTML = '<span>✕ Terminer</span>';
        }
        await processVoiceTurn(prompt);
      };
    });
  }
  bindVoiceTopicChips();

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

    const floatTooltip = floatingOrb ? floatingOrb.querySelector('#rq-floating-tooltip') : null;
    if (floatTooltip) {
      floatTooltip.textContent = 'Concierge IA · Touchez pour rouvrir';
    }
    const floatMute = floatingOrb ? floatingOrb.querySelector('#rq-float-mute') : null;
    if (floatMute) floatMute.textContent = '🎙️';
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
      } else if (!isSpeaking && !isProcessingTurn) {
        // Tap while listening -> force immediate submission like walkie-talkie!
        if (btnSendSpeech) btnSendSpeech.click();
      }
    });
  }

  const btnTestVoice = chatWindow.querySelector('#rq-btn-test-voice');
  if (btnTestVoice) {
    btnTestVoice.addEventListener('click', () => {
      const profile = (voiceProfileSelect && voiceProfileSelect.value) || 'henri';
      const bizName = (currentSiteConfig && currentSiteConfig.business_name) || 'Rockib Quenum';
      const sampleText =
        (currentSiteConfig && currentSiteConfig.voice_greeting) ||
        `Bonjour ! Je suis le concierge vocal temps réel de ${bizName}. Parlez-moi librement, je vous écoute.`;
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
        headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true', },
        body: JSON.stringify({
          phone_number: cbPhone.value.trim(),
          contact_name: cbName.value.trim() || undefined,
          topic: cbTopic.value.trim() || undefined,
          channel: channel,
          preferred_time: 'immediate',
          site_key: currentSiteKey,
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

  // --- Multi-Tenant Site Configuration & Branding Loader ---
  function hexToRgbString(hex) {
    if (!hex || typeof hex !== 'string') return '0, 240, 255';
    let h = hex.replace('#', '').trim();
    if (h.length === 3) {
      h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    }
    if (h.length !== 6) return '0, 240, 255';
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    if (isNaN(r) || isNaN(g) || isNaN(b)) return '0, 240, 255';
    return `${r}, ${g}, ${b}`;
  }

  function applySiteConfig(cfg, resetConversation) {
    if (!cfg) return;
    currentSiteConfig = cfg;
    if (cfg.site_key) {
      currentSiteKey = cfg.site_key;
    }

    // 1. Primary Color & CSS Custom Properties
    const primaryColor = cfg.primary_color || '#00F0FF';
    sitePrimaryRgb = hexToRgbString(primaryColor);
    document.documentElement.style.setProperty('--rq-accent', primaryColor);
    document.documentElement.style.setProperty('--rq-accent-rgb', sitePrimaryRgb);

    // 2. Position (left / right)
    if (cfg.position === 'left') {
      launcher.classList.add('rq-pos-left');
      chatWindow.classList.add('rq-pos-left');
    } else {
      launcher.classList.remove('rq-pos-left');
      chatWindow.classList.remove('rq-pos-left');
    }

    // 3. Header Title, Subtitle & Launcher Label
    const titleEl = chatWindow.querySelector('.rq-title');
    const subEl = chatWindow.querySelector('.rq-subtitle');
    const launcherSpan = launcher.querySelector('span');
    if (titleEl && cfg.business_name) titleEl.textContent = cfg.business_name;
    if (subEl && cfg.subtitle) subEl.textContent = cfg.subtitle;
    if (launcherSpan && cfg.launcher_label) launcherSpan.textContent = cfg.launcher_label;

    // 4. Default Voice Profile
    if (voiceProfileSelect && cfg.default_voice) {
      voiceProfileSelect.value = cfg.default_voice;
    }

    // 5. Welcome Message & Quick Chips
    if (resetConversation) {
      conversationId = null;
      sessionStorage.removeItem(conversationStorageKey(currentSiteKey));
      voiceSessionId = null;
      messagesContainer.innerHTML = '';
      const welcomeEl = document.createElement('div');
      welcomeEl.className = 'rq-msg rq-msg-assistant';
      welcomeEl.textContent = cfg.welcome_message || 'Bonjour ! Comment puis-je vous aider ?';
      messagesContainer.appendChild(welcomeEl);
      messagesContainer.appendChild(suggestionsContainer);
      suggestionsContainer.style.display = 'flex';
    } else {
      const firstAssistantMsg = messagesContainer.querySelector('.rq-msg-assistant');
      if (firstAssistantMsg && cfg.welcome_message && messagesContainer.querySelectorAll('.rq-msg').length === 1) {
        firstAssistantMsg.textContent = cfg.welcome_message;
      }
    }

    if (Array.isArray(cfg.quick_chips) && cfg.quick_chips.length > 0 && suggestionsContainer) {
      suggestionsContainer.innerHTML = cfg.quick_chips
        .map((chipText) => {
          const clean = String(chipText).replace(/"/g, '&quot;');
          return `<button class="rq-chip" data-query="${clean}">${clean}</button>`;
        })
        .join('');
    }

    // 6. Voice Topic Chips
    const voiceTopicsWrap = chatWindow.querySelector('#rq-panel-voice .rq-voice-topic-chip')?.parentElement;
    if (voiceTopicsWrap && Array.isArray(cfg.voice_topic_chips) && cfg.voice_topic_chips.length > 0) {
      voiceTopicsWrap.innerHTML = cfg.voice_topic_chips
        .map((vc) => {
          const lbl = String(vc.label || '').replace(/"/g, '&quot;');
          const prm = String(vc.prompt || vc.label || '').replace(/"/g, '&quot;');
          return `<button type="button" class="rq-voice-topic-chip" data-prompt="${prm}" style="background:rgba(${sitePrimaryRgb},0.1); border:1px solid rgba(${sitePrimaryRgb},0.35); color:#EDF5FF; border-radius:999px; padding:4px 9px; font-size:10px; cursor:pointer;">${lbl}</button>`;
        })
        .join('');
      bindVoiceTopicChips();
    }
  }

  async function loadSiteConfig(siteKeyToLoad, resetConv) {
    const targetKey = (siteKeyToLoad || currentSiteKey || 'rockib-portfolio').trim();
    currentSiteKey = targetKey;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/inbound/sites/${encodeURIComponent(targetKey)}/config`, {
        headers: { 'ngrok-skip-browser-warning': 'true' },
      });
      if (resp.ok) {
        const cfg = await resp.json();
        applySiteConfig(cfg, Boolean(resetConv));
        return cfg;
      }
    } catch (e) {}
    return null;
  }

  // Auto-load site config on startup if custom site or always sync
  loadSiteConfig(currentSiteKey, false);

  // Expose public API for live studio customization & external triggers
  window.RockibConcierge = {
    reloadSite: (newSiteKey) => loadSiteConfig(newSiteKey, true),
    applyConfig: (cfgObject) => applySiteConfig(cfgObject, true),
    open: (tab) => {
      toggleChat(true);
      if (tab && panels[tab]) {
        const btn = chatWindow.querySelector(`.rq-tab-btn[data-tab="${tab}"]`);
        if (btn) btn.click();
      }
    },
    close: () => toggleChat(false),
    minimize: () => toggleMinimize(true),
    maximize: () => toggleMinimize(false),
    navigate: (target) => executeNavigationAction(target, true),
    getSiteKey: () => currentSiteKey,
    getApiBase: () => API_BASE,
  };

})();
