/* MailMind — Frontend App JS */
'use strict';

// ── State ────────────────────────────────────────────────────────────────────
let sessionId = null;
let currentThreadId = null;
let currentProvider = document.getElementById('providerPill')?.textContent?.trim() || '';

// ── DOM references ────────────────────────────────────────────────────────────
const threadSelect   = document.getElementById('threadSelect');
const providerSelect = null;
const providerDesc   = null;
const startBtn       = document.getElementById('startBtn');
const resetBtn       = document.getElementById('resetBtn');
const questionInput  = document.getElementById('questionInput');
const sendBtn        = document.getElementById('sendBtn');
const messages       = document.getElementById('messages');
const emptyState     = document.getElementById('emptyState');
const sessionPanel   = document.getElementById('sessionPanel');
const sessionIdDisp  = document.getElementById('sessionIdDisplay');
const threadIdDisp   = document.getElementById('threadIdDisplay');
const chatTitle      = document.getElementById('chatTitle');
const providerPill   = document.getElementById('providerPill');
const typingInd      = document.getElementById('typingIndicator');
const debugFab       = document.getElementById('debugFab');
const outsideToggle  = document.getElementById('outsideThreadToggle');

// Provider selector removed in Gemini-only build; always use backend default.

// ── Start session ─────────────────────────────────────────────────────────────
if (startBtn) {
  startBtn.addEventListener('click', async () => {
    const threadId = threadSelect?.value;
    if (!threadId) { showToast('Please select a thread first.', 'warn'); return; }

    startBtn.disabled = true;
    startBtn.textContent = 'Starting…';

    try {
      const res  = await fetch('/api/start_session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to start session');

      sessionId       = data.session_id;
      currentThreadId = data.thread_id;

      // Update UI
      chatTitle.textContent = `${data.thread_id} — ${data.thread_subject}`;
      sessionIdDisp.textContent = sessionId;
      threadIdDisp.textContent  = currentThreadId;
      sessionPanel.style.display = '';
      emptyState && (emptyState.style.display = 'none');

      questionInput.disabled = false;
      sendBtn.disabled = false;
      questionInput.focus();
      debugFab.style.display = 'flex';
      messages.innerHTML = '';

      showToast(`Session started on ${data.thread_id}`, 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = 'Start Session';
    }
  });
}

// ── Reset session ─────────────────────────────────────────────────────────────
if (resetBtn) {
  resetBtn.addEventListener('click', async () => {
    if (!sessionId) return;
    await fetch('/api/reset_session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    sessionId = null;
    messages.innerHTML = '';
    questionInput.disabled = true;
    sendBtn.disabled = true;
    sessionPanel.style.display = 'none';
    emptyState && (emptyState.style.display = '');
    chatTitle.textContent = 'Select a thread to begin';
    debugFab.style.display = 'none';
    showToast('Session reset.', 'success');
  });
}

// ── Send message ──────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = questionInput.value.trim();
  if (!text || !sessionId) return;

  questionInput.value = '';
  autoResize();
  appendMessage('user', text);

  typingInd.style.display = 'flex';
  sendBtn.disabled = true;

  try {
    const res  = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        text,
        search_outside_thread: outsideToggle?.checked || false,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ask failed');

    typingInd.style.display = 'none';
    appendBotMessage(data);
    updateDebugPanel(data);
  } catch (e) {
    typingInd.style.display = 'none';
    appendMessage('bot', `⚠️ ${e.message}`);
  } finally {
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

if (sendBtn) sendBtn.addEventListener('click', sendMessage);

if (questionInput) {
  questionInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  questionInput.addEventListener('input', autoResize);
}

function autoResize() {
  if (!questionInput) return;
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + 'px';
}

// ── Message rendering ─────────────────────────────────────────────────────────
function appendMessage(role, text) {
  const wrap = document.createElement('div');
  wrap.className = `message message-${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;
  wrap.appendChild(bubble);
  messages.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function appendBotMessage(data) {
  const wrap = document.createElement('div');
  wrap.className = 'message message-bot';

  // Rewrite banner (only if different)
  if (data.rewrite && data.rewrite !== data.text) {
    const rb = document.createElement('div');
    rb.className = 'rewrite-banner';
    rb.textContent = `🔄 Rewritten: "${data.rewrite}"`;
    wrap.appendChild(rb);
  }

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = renderAnswer(data.answer);
  wrap.appendChild(bubble);

  // Citations bar
  if (data.citations && data.citations.length > 0) {
    const bar = document.createElement('div');
    bar.className = 'citations-bar';
    data.citations.forEach(c => {
      const tag = document.createElement('span');
      tag.className = 'citation';
      tag.title = JSON.stringify(c);
      tag.textContent = c.page
        ? `msg:${c.message_id} p${c.page}`
        : `msg:${c.message_id}`;
      bar.appendChild(tag);
    });
    wrap.appendChild(bar);
  }

  // Meta row
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  meta.innerHTML = `
    <span>⏱ ${data.latency?.split(' ')[0]}</span>
    <span>🔑 ${data.tokens} tok</span>
    <span title="${data.trace_id}">trace:${data.trace_id}</span>
  `;
  wrap.appendChild(meta);

  messages.appendChild(wrap);
  scrollToBottom();
}

function renderAnswer(text) {
  // Highlight [msg: xxx] and [msg: xxx, page: N] as inline citation tags
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\[msg:\s*([\w_]+),\s*page:\s*(\d+)\]/g,
      '<span class="citation">[msg:$1, p:$2]</span>')
    .replace(/\[msg:\s*([\w_]+)\]/g,
      '<span class="citation">[msg:$1]</span>')
    .replace(/\n/g, '<br>');
}

function scrollToBottom() {
  const wrap = document.getElementById('messagesWrap');
  if (wrap) wrap.scrollTop = wrap.scrollHeight;
}

// ── Debug panel ───────────────────────────────────────────────────────────────
function updateDebugPanel(data) {
  const set = (id, val) => { const el=document.getElementById(id); if(el) el.textContent=val; };
  set('debugRewrite',  data.rewrite || '—');
  set('debugProvider', data.provider || '—');
  set('debugLatency',  data.latency || '—');
  set('debugTokens',   data.tokens ?? '—');
  set('debugTrace',    data.trace_id || '—');

  const list = document.getElementById('debugRetrieved');
  if (list) {
    list.innerHTML = '';
    (data.retrieved || []).forEach(r => {
      const li = document.createElement('li');
      li.textContent = `${r.doc_id}  score:${r.score}`;
      list.appendChild(li);
    });
  }
}

window.toggleDebug = function() {
  const panel = document.getElementById('debugPanel');
  if (!panel) return;
  const shown = panel.style.display !== 'none';
  panel.style.display = shown ? 'none' : '';
};

// ── Sidebar toggle (mobile) ───────────────────────────────────────────────────
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');
if (sidebarToggle && sidebar) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
  document.addEventListener('click', e => {
    if (!sidebar.contains(e.target) && e.target !== sidebarToggle) {
      sidebar.classList.remove('open');
    }
  });
}

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const colors = { success: '#34d399', error: '#f87171', warn: '#fbbf24', info: '#5b7fff' };
  const el = document.createElement('div');
  el.textContent = msg;
  Object.assign(el.style, {
    position: 'fixed', bottom: '24px', left: '50%',
    transform: 'translateX(-50%)',
    background: colors[type] || colors.info,
    color: '#000', padding: '8px 16px',
    borderRadius: '6px', fontSize: '0.82rem',
    fontWeight: '500', zIndex: '1000',
    opacity: '0', transition: 'opacity .2s ease',
    boxShadow: '0 4px 12px rgba(0,0,0,.3)',
    maxWidth: '340px', textAlign: 'center',
  });
  document.body.appendChild(el);
  requestAnimationFrame(() => el.style.opacity = '1');
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 200);
  }, 2800);
}
