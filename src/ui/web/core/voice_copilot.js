(() => {
  const App = window.eHadiApp;
  const ic = App.icon;

  let voiceState = 'idle';
  let voiceEngine = 'gemini';
  let ttsEnabled = true;
  let activeAudio = null;
  let hideHudTimer = null;

  function setVoiceState(nextState, statusText = '') {
    voiceState = nextState;
    clearTimeout(hideHudTimer);
    const aura = document.getElementById('ehAmbientAura');
    const orb = document.getElementById('ehVoiceOrb');
    const hud = document.getElementById('ehVoiceHud');
    const hudTxt = document.getElementById('ehVoiceHudText');

    if (aura) { aura.dataset.state = nextState; aura.classList.toggle('active', nextState !== 'idle'); }
    if (orb) { orb.dataset.state = nextState; orb.classList.toggle('active', nextState !== 'idle'); }
    if (hud) {
      hud.dataset.state = nextState;
      if (nextState !== 'idle') hud.classList.add('open');
      else if (statusText) {
        hud.classList.add('open');
        hideHudTimer = setTimeout(() => hud.classList.remove('open'), 6000);
      } else hud.classList.remove('open');
    }
    if (hudTxt && statusText) hudTxt.textContent = statusText;
    syncControls();
  }

  function syncControls() {
    const engLbl = voiceEngine === 'whisper' ? 'ویسپر آفلاین' : 'جمینای آنلاین';
    document.querySelectorAll('[data-vc-engine-lbl]').forEach(el => { el.textContent = engLbl; });
    document.querySelectorAll('[data-vc-tts-btn]').forEach(btn => {
      btn.innerHTML = `${ic(ttsEnabled ? 'volume2' : 'volumeX', 14)}<span>${ttsEnabled ? 'صدا: روشن' : 'صدا: خاموش'}</span>`;
      btn.classList.toggle('active', ttsEnabled);
    });
  }

  async function toggleEngine() {
    voiceEngine = voiceEngine === 'gemini' ? 'whisper' : 'gemini';
    syncControls();
    await window.pywebview?.api?.set_voice_preferences?.(voiceEngine, ttsEnabled);
  }

  async function toggleTts() {
    ttsEnabled = !ttsEnabled;
    syncControls();
    await window.pywebview?.api?.set_voice_preferences?.(voiceEngine, ttsEnabled);
  }

  function playPersianAudio(dataUri, doneText) {
    if (!ttsEnabled || !dataUri) { setVoiceState('idle', doneText); return; }
    try {
      if (activeAudio) { activeAudio.pause(); activeAudio = null; }
      activeAudio = new Audio(dataUri);
      setVoiceState('speaking', doneText);
      activeAudio.onended = () => setVoiceState('idle', doneText);
      activeAudio.onerror = () => setVoiceState('idle', doneText);
      activeAudio.play().catch(() => setVoiceState('idle', doneText));
    } catch (_) { setVoiceState('idle', doneText); }
  }

  function mountAiVoiceUi() {
    document.getElementById('ehAiFluidCanvas')?.remove();
    document.getElementById('ehAiEdgeOverlay')?.remove();
    document.getElementById('vcTopGroup')?.remove();
    document.getElementById('vcChatInline')?.remove();
    document.getElementById('ehVoiceCopilotBar')?.remove();

    if (!document.getElementById('ehAmbientAura')) {
      const aura = document.createElement('div');
      aura.id = 'ehAmbientAura';
      aura.className = 'eh-ambient-aura';
      document.body.appendChild(aura);
    }

    if (!document.getElementById('ehVoiceOrb')) {
      const orb = document.createElement('button');
      orb.id = 'ehVoiceOrb';
      orb.type = 'button';
      orb.className = 'eh-voice-orb eh-orb-minimal';
      orb.title = 'دستیار صوتی هوشمند (Alt + Space)';
      orb.innerHTML = `<span class="eh-orb-core">${ic('micOn', 20)}</span>`;
      orb.addEventListener('click', startOrStopVoice);
      document.body.appendChild(orb);
    }

    if (!document.getElementById('ehVoiceHud')) {
      const hud = document.createElement('div');
      hud.id = 'ehVoiceHud';
      hud.className = 'eh-voice-hud eh-dynamic-island';
      hud.innerHTML = `
        <div class="eh-hud-eq" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
        <div class="eh-hud-text" id="ehVoiceHudText">در حال شنیدن...</div>
        <div class="eh-hud-actions">
          <button type="button" class="eh-hud-chip" data-vc-switch><span data-vc-engine-lbl>جمینای آنلاین</span></button>
          <button type="button" class="eh-hud-chip" data-vc-tts-btn>${ic('volume2', 14)}<span>صدا: روشن</span></button>
          <button type="button" class="eh-hud-stop" id="btnHudStop" title="توقف">${ic('close', 14)}</button>
        </div>
      `;
      document.body.appendChild(hud);
      hud.querySelector('[data-vc-switch]').addEventListener('click', toggleEngine);
      hud.querySelector('[data-vc-tts-btn]').addEventListener('click', toggleTts);
      hud.querySelector('#btnHudStop').addEventListener('click', () => {
        if (voiceState === 'listening') window.pywebview?.api?.stop_voice_recording?.();
        if (activeAudio) { activeAudio.pause(); activeAudio = null; }
        setVoiceState('idle');
      });
    }
    syncControls();
  }

  async function startOrStopVoice() {
    mountAiVoiceUi();
    if (voiceState === 'listening') {
      setVoiceState('processing', 'در حال تحلیل و پاسخ‌گویی...');
      await window.pywebview?.api?.stop_voice_recording?.();
      return;
    }
    if (voiceState === 'processing') return;
    if (activeAudio) { activeAudio.pause(); activeAudio = null; }

    setVoiceState('listening', 'گوش می‌دهم... صحبت کنید');
    try {
      const res = await window.pywebview?.api?.listen_voice_command?.(voiceEngine, ttsEnabled);
      if (!res || !res.ok) {
        const errMsg = res?.error || 'خطا در تشخیص گفتار';
        setVoiceState('idle', errMsg);
        window.showToast?.(errMsg, 'warning');
        return;
      }
      executeVoiceResult(res);
    } catch (err) {
      setVoiceState('idle', 'خطای صوتی: ' + (err?.message || err || 'نامشخص'));
    }
  }

  function autoSubmitChat(text) {
    App.goPage('chat');
    setTimeout(() => {
      const inp = document.querySelector('#page-chat textarea, #page-chat input[type="text"]');
      if (!inp) return;
      inp.value = text;
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      if (typeof window.sendMessage === 'function') { window.sendMessage(); return; }
      const btn = document.querySelector('#page-chat button[onclick*="send"], #btnSend, #btnSendChat, #page-chat .primary-btn');
      if (btn) { btn.click(); return; }
      inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
    }, 220);
  }

  function executeVoiceResult(res) {
    const displayMsg = res.reply || `«${res.transcript}»`;
    if (res.audio_uri) playPersianAudio(res.audio_uri, displayMsg);
    else setVoiceState('idle', displayMsg);

    switch (res.kind) {
      case 'open_modal': App.openModal(res.target); break;
      case 'boardroom':
        App.openModal('exec_analytics');
        setTimeout(() => document.getElementById('btnOpenBoardroom')?.click(), 350);
        break;
      case 'set_theme': App.applyTheme(res.target); break;
      case 'toggle_sidebar': App.toggleSidebar(Boolean(res.target)); break;
      case 'chat_prompt': autoSubmitChat(res.transcript); break;
    }
  }

  document.addEventListener('keydown', (e) => {
    if (e.altKey && e.code === 'Space') { e.preventDefault(); startOrStopVoice(); }
  });

  window.addEventListener('pywebviewready', () => { setTimeout(mountAiVoiceUi, 180); });
})();