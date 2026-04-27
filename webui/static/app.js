// ===== 状态 =====
const state = {
  ready: false,
  ws: null,
  wsReconnectTimer: null,
  streaming: false,
  streamBuffer: '',
  toolDisplayLevel: localStorage.getItem('toolDisplayLevel') || 'normal',
};

// ===== DOM =====
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

const dom = {
  status: $('#status-dot'),
  statusText: $('#status-text'),
  btnRetry: $('#btn-retry'),
  tabs: $$('.nav-btn[data-tab]'),
  panes: $$('.tab-pane'),
  chatMessages: $('#chat-messages'),
  chatInput: $('#chat-input'),
  btnSend: $('#btn-send'),
  btnClear: $('#btn-clear-chat'),
  cronList: $('#cron-list'),
  cronModal: $('#cron-modal'),
  cronForm: $('#cron-form'),
  cronRefresh: $('#btn-refresh-cron'),
  cronAdd: $('#btn-add-cron'),
  reportModal: $('#report-modal'),
  reportDetail: $('#report-detail'),
  logOutput: $('#log-output'),
  logRefresh: $('#btn-refresh-logs'),
  logClear: $('#btn-clear-logs'),
  configOutput: $('#config-output'),
};

// ===== 工具 =====
function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function scrollChat() {
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function setStatus(name, text) {
  dom.status.className = 'dot ' + name;
  if (text !== undefined) dom.statusText.textContent = text;
}

function disableInput() {
  dom.chatInput.disabled = true;
  dom.btnSend.disabled = true;
}

function enableInput() {
  if (!state.ready) return;
  dom.chatInput.disabled = false;
  dom.btnSend.disabled = false;
  dom.chatInput.focus();
}

// ===== Markdown 渲染 =====
function parseMarkdown(text) {
  if (!text) return '';
  // Extract <think> blocks
  let thinkHtml = '';
  text = text.replace(/<think>([\s\S]*?)<\/think>/g, (_, inner) => {
    const rendered = marked.parse(inner.trim());
    thinkHtml += `<details class="think-block"><summary>🤔 推理过程</summary><div class="think-content">${rendered}</div></details>`;
    return '';
  });

  const body = marked.parse(text, { breaks: true });
  return DOMPurify.sanitize(thinkHtml + body);
}

// ===== 消息卡片渲染 =====
function addMsgCard(role, content, extraClass) {
  const card = document.createElement('div');
  card.className = 'msg-card ' + role;
  if (extraClass) card.classList.add(extraClass);

  const meta = document.createElement('div');
  meta.className = 'msg-meta';

  const labels = { user: '你', agent: 'Agent', system: '系统', tool: '工具' };
  const avatars = { user: 'U', agent: 'A', system: '●', tool: '⚡' };
  const avatarCls = { user: 'user-av', agent: 'agent-av', system: 'system-av', tool: 'system-av' };

  const av = document.createElement('span');
  av.className = 'msg-avatar ' + (avatarCls[role] || '');
  av.textContent = avatars[role] || '?';
  meta.appendChild(av);

  const name = document.createElement('span');
  name.textContent = labels[role] || role;
  meta.appendChild(name);

  const time = document.createElement('span');
  time.textContent = new Date().toLocaleTimeString();
  time.style.marginLeft = 'auto';
  meta.appendChild(time);

  card.appendChild(meta);

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  if (role === 'tool') {
    if (content.startsWith('调用工具:')) {
      bubble.innerHTML = `<div class="tool-header">⚡ ${escapeHtml(content)}</div>`;
    } else {
      bubble.innerHTML = `<div class="tool-output">📋 ${escapeHtml(content)}</div>`;
    }
  } else if (role === 'system') {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = parseMarkdown(content);
  }

  card.appendChild(bubble);
  dom.chatMessages.appendChild(card);
  scrollChat();
  return card;
}

// ===== 流式消息渲染 =====
function getOrCreateStreamCard() {
  let el = dom.chatMessages.querySelector('.msg-card.streaming');
  if (!el) {
    el = addMsgCard('agent', '', 'streaming');
    el.querySelector('.msg-bubble').innerHTML = '<div class="thinking-indicator"><div class="spinner"></div> 思考中...</div>';
  }
  return el;
}

function appendStreamToken(text) {
  state.streamBuffer += text;
  const el = getOrCreateStreamCard();
  const bubble = el.querySelector('.msg-bubble');
  if (state.streamBuffer.length > 0) {
    bubble.innerHTML = parseMarkdown(state.streamBuffer);
  }
  scrollChat();
}

function setStreamPlaceholder(html) {
  const el = getOrCreateStreamCard();
  const bubble = el.querySelector('.msg-bubble');
  bubble.innerHTML = html;
  scrollChat();
}

function finalizeStream() {
  const el = dom.chatMessages.querySelector('.msg-card.streaming');
  if (el) el.classList.remove('streaming');
  state.streamBuffer = '';
  state.streaming = false;
  enableInput();
}

function removeStreamMsg() {
  const el = dom.chatMessages.querySelector('.msg-card.streaming');
  if (el) el.remove();
  state.streamBuffer = '';
}

// ===== WebSocket =====
function connectWs() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) return;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  state.ws = new WebSocket(`${proto}//${location.host}/ws/chat`);

  state.ws.onopen = () => {
    console.log('WS 已连接');
    if (state.wsReconnectTimer) { clearTimeout(state.wsReconnectTimer); state.wsReconnectTimer = null; }
  };

  function renderToolEvent(ev) {
    const level = state.toolDisplayLevel;
    if (level === 'hidden') return;

    if (ev.type === 'tool_call') {
      if (level === 'verbose' || level === 'normal') {
        setStreamPlaceholder(`<div class="tool-header">⚡ ${escapeHtml(ev.content)}</div>`);
      } else if (level === 'compact') {
        setStreamPlaceholder(`<span style="color:var(--text-muted);font-size:12px">⚡ 调用工具...</span>`);
      }
    } else if (ev.type === 'tool_result') {
      if (level === 'verbose') {
        setStreamPlaceholder(`<div class="tool-header">⚡ 工具调用</div><div class="tool-output">📋 ${escapeHtml(ev.content)}</div>`);
      } else if (level === 'normal') {
        setStreamPlaceholder(`<div class="tool-header">⚡ 工具调用</div><div class="tool-output" style="font-size:12px">📋 ${escapeHtml(ev.content).slice(0, 80)}${ev.content.length > 80 ? '...' : ''}</div>`);
      }
      // compact: do nothing, already showed badge
    }
  }

  state.ws.onmessage = e => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }

    switch (ev.type) {
      case 'token':
        appendStreamToken(ev.content);
        break;
      case 'tool_call':
      case 'tool_result':
        renderToolEvent(ev);
        break;
      case 'done':
        finalizeStream();
        break;
      case 'error':
        removeStreamMsg();
        addMsgCard('system', ev.content);
        state.streaming = false;
        enableInput();
        break;
      case 'response':
        removeStreamMsg();
        addMsgCard('agent', ev.content);
        state.streaming = false;
        enableInput();
        break;
    }
  };

  state.ws.onclose = () => {
    state.ws = null;
    if (state.ready && !state.streaming)
      state.wsReconnectTimer = setTimeout(connectWs, 3000);
  };
  state.ws.onerror = () => {};
}

function sendWsMessage(text) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    connectWs();
    return false;
  }
  state.ws.send(JSON.stringify({ message: text }));
  return true;
}

async function sendPostFallback(text) {
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await r.json();
    removeStreamMsg();
    if (data.error) addMsgCard('system', data.error);
    else addMsgCard('agent', data.output || '(空响应)');
  } catch (e) {
    removeStreamMsg();
    addMsgCard('system', '请求失败: ' + e.message);
  } finally {
    state.streaming = false;
    enableInput();
  }
}

// ===== 自动初始化 =====
async function autoInit() {
  setStatus('busy', '正在初始化...');
  disableInput();

  try {
    const r = await fetch('/api/init', { method: 'POST' });
    if (!r.ok) throw new Error((await r.json()).detail || '初始化失败');
    state.ready = true;
    setStatus('online', 'Agent 已就绪');
    dom.btnRetry.classList.add('hidden');
    enableInput();
    connectWs();
    refreshCron();
    refreshConfig();
  } catch (e) {
    setStatus('error', '初始化失败: ' + e.message);
    dom.btnRetry.classList.remove('hidden');
  }
}

dom.btnRetry.addEventListener('click', autoInit);

// ===== 发送消息 =====
function sendMessage() {
  const text = dom.chatInput.value.trim();
  if (!text) return;
  if (!state.ready) { addMsgCard('system', 'Agent 正在初始化...'); return; }
  if (state.streaming) { addMsgCard('system', '请等待上一条消息完成'); return; }

  dom.chatInput.value = '';
  addMsgCard('user', text);

  if (sendWsMessage(text)) {
    state.streaming = true;
    disableInput();
    getOrCreateStreamCard();
  } else {
    state.streaming = true;
    disableInput();
    getOrCreateStreamCard();
    sendPostFallback(text);
  }
}

// ===== Cron =====
async function refreshCron() {
  try {
    const r = await fetch('/api/cron/jobs');
    if (!r.ok) return;
    const data = await r.json();
    dom.cronList.innerHTML = '';
    for (const j of data.jobs || []) {
      const sched = j.cron_expr || j.run_at || (j.interval_seconds ? '每' + j.interval_seconds + '秒' : '?');
      dom.cronList.innerHTML += `
        <div class="cron-card">
          <div class="cron-name">${escapeHtml(j.name)}</div>
          <div class="cron-meta">ID: ${j.job_id} | 调度: ${escapeHtml(sched)} <span class="cron-badge ${j.enabled ? 'enabled' : 'disabled'}">${j.enabled ? '启用' : '暂停'}</span>${j.last_run_at ? ' | 上次: ' + j.last_run_at.slice(0, 19) : ''}</div>
          <div class="cron-actions">
            <button class="btn-small" onclick="deleteCronJob('${j.job_id}')">删除</button>
            <button class="btn-small" onclick="viewCronReports('${j.job_id}')">报告</button>
          </div>
        </div>`;
    }
    if (!data.jobs || !data.jobs.length) dom.cronList.innerHTML = '<p style="color:var(--text-muted);padding:16px;">暂无定时任务</p>';
  } catch (e) { console.error(e); }
}

window.deleteCronJob = async id => {
  if (!confirm('删除该任务？')) return;
  await fetch('/api/cron/jobs/' + id, { method: 'DELETE' });
  refreshCron();
};

window.viewCronReports = async jobId => {
  try {
    const r = await fetch('/api/cron/reports');
    const data = await r.json();
    const reports = (data.reports || []).filter(r => r.job_id === jobId);
    dom.reportDetail.innerHTML = reports.length
      ? reports.map(r => `<div class="cron-card" style="cursor:pointer" onclick="showReportDetail('${r.report_id}')"><div class="cron-meta">${r.triggered_at.slice(0, 19)} ${r.read ? '' : '🔵'}</div><div>${escapeHtml(r.summary)}</div></div>`).join('')
      : '<p style="color:var(--text-muted)">暂无报告</p>';
    dom.reportModal.classList.remove('hidden');
  } catch (e) { console.error(e); }
};

window.showReportDetail = async rid => {
  const r = await (await fetch('/api/cron/reports/' + rid)).json();
  dom.reportDetail.innerHTML = `
    <div class="cron-card">
      <div class="cron-meta">触发: ${r.triggered_at.slice(0, 19)} | Job: ${r.job_id}</div>
      <div style="margin-top:8px"><strong>指令:</strong> ${escapeHtml(r.task_prompt)}</div>
      <div style="margin-top:8px"><strong>输出:</strong></div>
      <pre style="background:var(--bg-primary);padding:8px;border-radius:4px;margin-top:4px;overflow-x:auto;font-size:13px;">${escapeHtml(r.output)}</pre>
      ${r.conversation && r.conversation.length ? `<div style="margin-top:12px"><strong>对话 (${r.conversation.length}):</strong></div>${r.conversation.map(c => `<div style="margin-top:4px;font-size:13px"><strong>${c.role === 'user' ? '你' : 'Agent'}:</strong> ${escapeHtml(c.content).slice(0, 300)}</div>`).join('')}` : ''}
    </div>`;
};

// ===== 日志 & 配置 =====
async function refreshLogs() {
  try {
    const r = await fetch('/api/logs?lines=100');
    dom.logOutput.textContent = ((await r.json()).logs || []).join('');
  } catch (e) { dom.logOutput.textContent = '获取失败'; }
}

async function refreshConfig() {
  try {
    const r = await fetch('/api/config');
    dom.configOutput.textContent = JSON.stringify(await r.json(), null, 2);
  } catch (e) { dom.configOutput.textContent = '获取失败'; }
}

// ===== Tab 切换 =====
dom.tabs.forEach(btn => {
  btn.addEventListener('click', () => {
    dom.tabs.forEach(b => b.classList.remove('active'));
    dom.panes.forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const tab = document.getElementById('tab-' + btn.dataset.tab);
    if (tab) tab.classList.add('active');
    if (btn.dataset.tab === 'cron') refreshCron();
    if (btn.dataset.tab === 'logs') refreshLogs();
    if (btn.dataset.tab === 'config') refreshConfig();
  });
});

// ===== 事件绑定 =====
dom.btnSend.addEventListener('click', sendMessage);
dom.chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
dom.btnClear.addEventListener('click', () => { dom.chatMessages.innerHTML = ''; });
dom.cronAdd.addEventListener('click', () => {
  dom.cronModal.classList.remove('hidden');
  document.querySelectorAll('.cron-dep').forEach(el => el.style.display = 'none');
});
dom.cronRefresh.addEventListener('click', refreshCron);
dom.logRefresh.addEventListener('click', refreshLogs);
dom.logClear.addEventListener('click', () => { dom.logOutput.textContent = ''; });

$$('.modal-close').forEach(el => {
  el.addEventListener('click', () => el.closest('.modal').classList.add('hidden'));
});
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal')) e.target.classList.add('hidden');
});

// Cron 表单
if (dom.cronForm) {
  const typeSel = dom.cronForm.querySelector('[name="schedule_type"]');
  typeSel.addEventListener('change', () => {
    document.querySelectorAll('.cron-dep').forEach(el => {
      el.style.display = el.dataset.type === typeSel.value ? 'block' : 'none';
    });
  });
  dom.cronForm.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(dom.cronForm);
    const body = {
      name: fd.get('name'), task_prompt: fd.get('task_prompt'),
      schedule_type: fd.get('schedule_type'),
      cron_expr: fd.get('cron_expr') || null,
      run_at: fd.get('run_at') ? new Date(fd.get('run_at')).toISOString() : null,
      interval_seconds: fd.get('interval_seconds') ? parseInt(fd.get('interval_seconds')) : null,
      llm_provider: fd.get('llm_provider') || null,
      llm_model: fd.get('llm_model') || null,
    };
    try {
      const r = await fetch('/api/cron/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (r.ok) { dom.cronModal.classList.add('hidden'); dom.cronForm.reset(); refreshCron(); }
      else alert('创建失败: ' + ((await r.json()).detail || '未知错误'));
    } catch (e) { alert('创建失败: ' + e.message); }
  });
}

// ===== 工具显示等级下拉 =====
const LEVEL_LABELS = { verbose: '详细', normal: '标准', compact: '简洁', hidden: '隐藏' };
const dropdown = document.getElementById('tool-level-dropdown');
const trigger = dropdown?.querySelector('.dropdown-trigger');
const items = dropdown?.querySelectorAll('.dropdown-item');

function updateToolLevel(level) {
  state.toolDisplayLevel = level;
  localStorage.setItem('toolDisplayLevel', level);
  const label = document.getElementById('tool-level-label');
  if (label) label.textContent = LEVEL_LABELS[level] || level;
  items?.forEach(el => el.classList.toggle('active', el.dataset.level === level));
}

if (trigger) {
  trigger.addEventListener('click', e => {
    e.stopPropagation();
    dropdown.classList.toggle('open');
  });
  document.addEventListener('click', () => dropdown.classList.remove('open'));
}

items?.forEach(el => {
  el.addEventListener('click', () => {
    updateToolLevel(el.dataset.level);
    dropdown.classList.remove('open');
  });
});

// 从 localStorage 恢复
updateToolLevel(state.toolDisplayLevel);

// ===== 启动 =====
autoInit();
