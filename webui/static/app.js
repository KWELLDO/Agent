// ===== 状态 =====
const state = {
  ready: false,
  initError: null,
  ws: null,
};

// ===== DOM 引用 =====
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const dom = {
  status: $('#status-dot'),
  tabs: $$('.nav-btn[data-tab]'),
  panes: $$('.tab-pane'),
  chatMessages: $('#chat-messages'),
  chatInput: $('#chat-input'),
  btnSend: $('#btn-send'),
  btnClear: $('#btn-clear-chat'),
  btnInit: $('#btn-init'),
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
function setStatus(stateName) {
  dom.status.className = 'dot ' + stateName;
}

function addMsg(role, content) {
  const el = document.createElement('div');
  el.className = 'msg ' + role;
  el.textContent = content;
  dom.chatMessages.appendChild(el);
  el.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ===== 初始化 =====
async function initAgent() {
  setStatus('busy');
  dom.btnInit.disabled = true;
  dom.btnInit.textContent = '初始化中...';
  try {
    const resp = await fetch('/api/init', { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '初始化失败');
    }
    const data = await resp.json();
    state.ready = true;
    setStatus('online');
    addMsg('system', 'Agent 已就绪');
    dom.btnInit.textContent = '已就绪';
    refreshCron();
    refreshConfig();
  } catch (e) {
    state.initError = e.message;
    setStatus('error');
    addMsg('error', '初始化失败: ' + e.message);
    dom.btnInit.textContent = '重试初始化';
    dom.btnInit.disabled = false;
  }
}

// ===== 聊天 =====
async function sendMessage() {
  const text = dom.chatInput.value.trim();
  if (!text) return;
  if (!state.ready) {
    addMsg('system', '请先点击"初始化"');
    return;
  }

  dom.chatInput.value = '';
  addMsg('user', text);

  const loadingEl = document.createElement('div');
  loadingEl.className = 'msg system';
  loadingEl.textContent = '思考中...';
  dom.chatMessages.appendChild(loadingEl);

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await resp.json();
    loadingEl.remove();
    if (data.error) {
      addMsg('error', data.error);
    } else {
      addMsg('agent', data.output || '(空响应)');
    }
  } catch (e) {
    loadingEl.remove();
    addMsg('error', '请求失败: ' + e.message);
  }
}

// ===== Cron =====
async function refreshCron() {
  try {
    const resp = await fetch('/api/cron/jobs');
    if (!resp.ok) return;
    const data = await resp.json();
    dom.cronList.innerHTML = '';
    for (const j of data.jobs || []) {
      const card = document.createElement('div');
      card.className = 'cron-card';
      const schedule = j.cron_expr || j.run_at || (j.interval_seconds ? '每' + j.interval_seconds + '秒' : '?');
      card.innerHTML = `
        <div class="cron-name">${escapeHtml(j.name)}</div>
        <div class="cron-meta">
          ID: ${j.job_id} | 调度: ${escapeHtml(schedule)}
          <span class="cron-badge ${j.enabled ? 'enabled' : 'disabled'}">${j.enabled ? '启用' : '暂停'}</span>
          ${j.last_run_at ? '| 上次: ' + j.last_run_at.slice(0, 19) : ''}
        </div>
        <div class="cron-actions">
          <button class="btn-small" onclick="deleteCronJob('${j.job_id}')">删除</button>
          <button class="btn-small" onclick="viewCronReports('${j.job_id}')">报告</button>
        </div>
      `;
      dom.cronList.appendChild(card);
    }
    if (!data.jobs || data.jobs.length === 0) {
      dom.cronList.innerHTML = '<p style="color:var(--text-muted);padding:16px;">暂无定时任务</p>';
    }
  } catch (e) {
    console.error('刷新 cron 失败', e);
  }
}

async function deleteCronJob(jobId) {
  if (!confirm('确定删除该定时任务？')) return;
  try {
    const resp = await fetch('/api/cron/jobs/' + jobId, { method: 'DELETE' });
    if (resp.ok) refreshCron();
  } catch (e) {
    console.error('删除失败', e);
  }
}

async function viewCronReports(jobId) {
  try {
    const resp = await fetch('/api/cron/reports');
    if (!resp.ok) return;
    const data = await resp.json();
    const reports = (data.reports || []).filter(r => r.job_id === jobId);
    if (reports.length === 0) {
      dom.reportDetail.innerHTML = '<p style="color:var(--text-muted)">暂无报告</p>';
    } else {
      dom.reportDetail.innerHTML = reports.map(r => `
        <div class="cron-card" style="cursor:pointer" onclick="showReportDetail('${r.report_id}')">
          <div class="cron-meta">${r.triggered_at.slice(0, 19)} ${r.read ? '' : '🔵'}</div>
          <div>${escapeHtml(r.summary)}</div>
        </div>
      `).join('');
    }
    dom.reportModal.classList.remove('hidden');
  } catch (e) {
    console.error('获取报告失败', e);
  }
}

async function showReportDetail(reportId) {
  try {
    const resp = await fetch('/api/cron/reports/' + reportId);
    if (!resp.ok) return;
    const r = await resp.json();
    dom.reportDetail.innerHTML = `
      <div class="cron-card">
        <div class="cron-meta">触发: ${r.triggered_at.slice(0, 19)} | Job: ${r.job_id}</div>
        <div style="margin-top:8px"><strong>指令:</strong> ${escapeHtml(r.task_prompt)}</div>
        <div style="margin-top:8px"><strong>输出:</strong></div>
        <pre style="background:var(--bg-primary);padding:8px;border-radius:4px;margin-top:4px;overflow-x:auto;font-size:13px;">${escapeHtml(r.output)}</pre>
        ${r.conversation && r.conversation.length ? `
          <div style="margin-top:12px"><strong>对话 (${r.conversation.length}):</strong></div>
          ${r.conversation.map(c => `<div style="margin-top:4px;font-size:13px"><strong>${c.role === 'user' ? '你' : 'Agent'}:</strong> ${escapeHtml(c.content).slice(0, 300)}</div>`).join('')}
        ` : ''}
      </div>
    `;
  } catch (e) {
    console.error('获取报告详情失败', e);
  }
}

// ===== 日志 =====
async function refreshLogs() {
  try {
    const resp = await fetch('/api/logs?lines=100');
    const data = await resp.json();
    dom.logOutput.textContent = (data.logs || []).join('');
  } catch (e) {
    dom.logOutput.textContent = '获取日志失败: ' + e.message;
  }
}

// ===== 配置 =====
async function refreshConfig() {
  try {
    const resp = await fetch('/api/config');
    const data = await resp.json();
    dom.configOutput.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    dom.configOutput.textContent = '获取配置失败: ' + e.message;
  }
}

// ===== Tab 切换 =====
dom.tabs.forEach(btn => {
  btn.addEventListener('click', () => {
    dom.tabs.forEach(b => b.classList.remove('active'));
    dom.panes.forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const tab = document.getElementById('tab-' + btn.dataset.tab);
    if (tab) tab.classList.add('active');

    // 懒加载
    if (btn.dataset.tab === 'cron') refreshCron();
    if (btn.dataset.tab === 'logs') refreshLogs();
    if (btn.dataset.tab === 'config') refreshConfig();
  });
});

// ===== 事件绑定 =====
dom.btnInit.addEventListener('click', initAgent);
dom.btnSend.addEventListener('click', sendMessage);
dom.chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
dom.btnClear.addEventListener('click', () => {
  dom.chatMessages.innerHTML = '';
});
dom.cronAdd.addEventListener('click', () => {
  dom.cronModal.classList.remove('hidden');
  document.querySelectorAll('.cron-dep').forEach(el => el.style.display = 'none');
});
dom.cronRefresh.addEventListener('click', refreshCron);
dom.logRefresh.addEventListener('click', refreshLogs);
dom.logClear.addEventListener('click', () => { dom.logOutput.textContent = ''; });

// 弹窗关闭
$$('.modal-close').forEach(el => {
  el.addEventListener('click', () => {
    el.closest('.modal').classList.add('hidden');
  });
});
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal')) {
    e.target.classList.add('hidden');
  }
});

// Cron 表单依赖显示
if (dom.cronForm) {
  const typeSelect = dom.cronForm.querySelector('[name="schedule_type"]');
  typeSelect.addEventListener('change', () => {
    document.querySelectorAll('.cron-dep').forEach(el => {
      el.style.display = el.dataset.type === typeSelect.value ? 'block' : 'none';
    });
  });

  dom.cronForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(dom.cronForm);
    const body = {
      name: fd.get('name'),
      task_prompt: fd.get('task_prompt'),
      schedule_type: fd.get('schedule_type'),
      cron_expr: fd.get('cron_expr') || null,
      run_at: fd.get('run_at') ? new Date(fd.get('run_at')).toISOString() : null,
      interval_seconds: fd.get('interval_seconds') ? parseInt(fd.get('interval_seconds')) : null,
      llm_provider: fd.get('llm_provider') || null,
      llm_model: fd.get('llm_model') || null,
    };
    try {
      const resp = await fetch('/api/cron/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        dom.cronModal.classList.add('hidden');
        dom.cronForm.reset();
        refreshCron();
      } else {
        const err = await resp.json();
        alert('创建失败: ' + (err.detail || '未知错误'));
      }
    } catch (e) {
      alert('创建失败: ' + e.message);
    }
  });
}

// ===== 自动初始化 =====
(async () => {
  // 检查状态
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    if (data.ready) {
      state.ready = true;
      setStatus('online');
      dom.btnInit.textContent = '已就绪';
      refreshCron();
      refreshConfig();
      return;
    }
  } catch (e) {
    // 服务未就绪，需要用户点击初始化
  }
  setStatus('offline');
})();
