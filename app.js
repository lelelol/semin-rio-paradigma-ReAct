// ========================================
// OLLAMA DASHBOARD — App Logic
// ========================================

const API_BASE = 'http://localhost:11434';
let selectedChatModel = null;
let chatHistory = [];
let isStreaming = false;

// ========================================
// INITIALIZATION
// ========================================
document.addEventListener('DOMContentLoaded', () => {
    initCyberDefense();
    connectCyberWs();
});



// ========================================
// DASHBOARD
// ========================================
async function loadDashboard() {
    try {
        const [tagsRes, psRes] = await Promise.all([
            fetch(`${API_BASE}/api/tags`),
            fetch(`${API_BASE}/api/ps`)
        ]);

        const tagsData = await tagsRes.json();
        const psData = await psRes.json();

        const models = tagsData.models || [];
        const running = psData.models || [];

        // Stats
        document.getElementById('totalModels').textContent = models.length;
        document.getElementById('totalSize').textContent = formatBytes(models.reduce((acc, m) => acc + (m.size || 0), 0));
        document.getElementById('runningModels').textContent = running.length;
        document.getElementById('serverStatus').textContent = 'Online';
        document.getElementById('serverStatus').style.color = 'var(--success)';

        // Models table
        renderModelsTable(models);

        // Running models
        renderRunningModels(running);

    } catch (err) {
        document.getElementById('totalModels').textContent = '—';
        document.getElementById('totalSize').textContent = '—';
        document.getElementById('runningModels').textContent = '—';
        document.getElementById('serverStatus').textContent = 'Offline';
        document.getElementById('serverStatus').style.color = 'var(--error)';
        document.getElementById('modelsTableContainer').innerHTML = `
            <div class="empty-state">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <p>Não foi possível conectar ao Ollama.<br>Verifique se o servidor está rodando em <code>localhost:11434</code></p>
            </div>`;
    }
}

function renderModelsTable(models) {
    if (models.length === 0) {
        document.getElementById('modelsTableContainer').innerHTML = `
            <div class="empty-state">
                <p>Nenhum modelo instalado. Vá para "Baixar Modelo" para começar.</p>
            </div>`;
        return;
    }

    const html = `
        <table>
            <thead>
                <tr>
                    <th>Modelo</th>
                    <th>Tamanho</th>
                    <th>Quantização</th>
                    <th>Modificado</th>
                    <th>Ações</th>
                </tr>
            </thead>
            <tbody>
                ${models.map(m => `
                    <tr>
                        <td><span class="model-name">${escapeHtml(m.name)}</span></td>
                        <td><span class="model-size">${formatBytes(m.size || 0)}</span></td>
                        <td>${m.details?.quantization_level ? `<span class="model-quant">${escapeHtml(m.details.quantization_level)}</span>` : '—'}</td>
                        <td style="color: var(--text-secondary); font-size: 0.82rem;">${formatDate(m.modified_at)}</td>
                        <td>
                            <div style="display: flex; gap: 6px;">
                                <button class="btn btn-ghost btn-sm" onclick="chatWithModel('${escapeAttr(m.name)}')" title="Conversar">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                                    Chat
                                </button>
                                <button class="btn btn-danger btn-sm" onclick="deleteModel('${escapeAttr(m.name)}')" title="Remover">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                                </button>
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>`;

    document.getElementById('modelsTableContainer').innerHTML = html;
}

function renderRunningModels(models) {
    const container = document.getElementById('runningModelsContainer');

    if (models.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>Nenhum modelo em execução no momento</p>
            </div>`;
        return;
    }

    container.innerHTML = models.map(m => `
        <div class="running-model-card">
            <div class="running-dot"></div>
            <div class="running-model-info">
                <div class="running-model-name">${escapeHtml(m.name)}</div>
                <div class="running-model-meta">
                    Tamanho: ${formatBytes(m.size || 0)} • 
                    VRAM: ${formatBytes(m.size_vram || 0)} •
                    Expira: ${m.expires_at ? formatDate(m.expires_at) : '—'}
                </div>
            </div>
        </div>
    `).join('');
}

// ========================================
// MODELS DETAIL
// ========================================
async function loadModelsDetail() {
    const container = document.getElementById('modelsDetailContainer');
    try {
        const res = await fetch(`${API_BASE}/api/tags`);
        const data = await res.json();
        const models = data.models || [];

        if (models.length === 0) {
            container.innerHTML = `<div class="empty-state"><p>Nenhum modelo instalado</p></div>`;
            return;
        }

        container.innerHTML = models.map(m => {
            const d = m.details || {};
            return `
                <div class="model-detail-card">
                    <div class="model-detail-header">
                        <span class="model-detail-name">${escapeHtml(m.name)}</span>
                        <div class="model-detail-actions">
                            <button class="btn btn-ghost btn-sm" onclick="chatWithModel('${escapeAttr(m.name)}')">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                                Chat
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="deleteModel('${escapeAttr(m.name)}')">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                                Remover
                            </button>
                        </div>
                    </div>
                    <div class="model-meta-grid">
                        <div class="model-meta-item">
                            <span class="model-meta-label">Família</span>
                            <span class="model-meta-value">${escapeHtml(d.family || '—')}</span>
                        </div>
                        <div class="model-meta-item">
                            <span class="model-meta-label">Parâmetros</span>
                            <span class="model-meta-value">${escapeHtml(d.parameter_size || '—')}</span>
                        </div>
                        <div class="model-meta-item">
                            <span class="model-meta-label">Quantização</span>
                            <span class="model-meta-value">${escapeHtml(d.quantization_level || '—')}</span>
                        </div>
                        <div class="model-meta-item">
                            <span class="model-meta-label">Tamanho</span>
                            <span class="model-meta-value">${formatBytes(m.size || 0)}</span>
                        </div>
                        <div class="model-meta-item">
                            <span class="model-meta-label">Formato</span>
                            <span class="model-meta-value">${escapeHtml(d.format || '—')}</span>
                        </div>
                        <div class="model-meta-item">
                            <span class="model-meta-label">Modificado</span>
                            <span class="model-meta-value">${formatDate(m.modified_at)}</span>
                        </div>
                    </div>
                </div>`;
        }).join('');

    } catch (err) {
        container.innerHTML = `<div class="empty-state"><p>Erro ao carregar modelos: ${escapeHtml(err.message)}</p></div>`;
    }
}

// ========================================
// CHAT
// ========================================
function initChat() {
    const input = document.getElementById('chatInput');
    const tempSlider = document.getElementById('chatTemperature');

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 150) + 'px';
    });

    tempSlider.addEventListener('input', () => {
        document.getElementById('tempValue').textContent = tempSlider.value;
    });
}

async function loadChatModels() {
    const container = document.getElementById('chatModelList');
    try {
        const res = await fetch(`${API_BASE}/api/tags`);
        const data = await res.json();
        const models = data.models || [];

        container.innerHTML = models.map(m => `
            <div class="chat-model-item ${selectedChatModel === m.name ? 'selected' : ''}" 
                 onclick="selectChatModel('${escapeAttr(m.name)}', this)">
                ${escapeHtml(m.name)}
            </div>
        `).join('');

        if (models.length === 0) {
            container.innerHTML = `<p style="color: var(--text-muted); font-size: 0.82rem; padding: 8px;">Nenhum modelo disponível</p>`;
        }
    } catch {
        container.innerHTML = `<p style="color: var(--text-muted); font-size: 0.82rem; padding: 8px;">Erro ao carregar modelos</p>`;
    }
}

function selectChatModel(name, el) {
    selectedChatModel = name;
    document.querySelectorAll('.chat-model-item').forEach(i => i.classList.remove('selected'));
    el.classList.add('selected');

    // Clear chat
    chatHistory = [];
    const messagesEl = document.getElementById('chatMessages');
    messagesEl.innerHTML = `
        <div class="empty-chat">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <p>Modelo <strong>${escapeHtml(name)}</strong> selecionado. Comece a conversar!</p>
        </div>`;

    showToast(`Modelo ${name} selecionado`, 'info');
}

function chatWithModel(name) {
    switchSection('chat');
    selectedChatModel = name;
    loadChatModels();

    chatHistory = [];
    const messagesEl = document.getElementById('chatMessages');
    messagesEl.innerHTML = `
        <div class="empty-chat">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <p>Modelo <strong>${escapeHtml(name)}</strong> selecionado. Comece a conversar!</p>
        </div>`;
}

async function sendMessage() {
    if (isStreaming) return;

    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;

    if (!selectedChatModel) {
        showToast('Selecione um modelo primeiro', 'error');
        return;
    }

    const messagesEl = document.getElementById('chatMessages');
    
    // Remove empty state
    const emptyChat = messagesEl.querySelector('.empty-chat');
    if (emptyChat) emptyChat.remove();

    // Add user message
    appendMessage('user', message);
    chatHistory.push({ role: 'user', content: message });

    input.value = '';
    input.style.height = 'auto';

    // Add typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'message assistant';
    typingEl.id = 'typingIndicator';
    typingEl.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>`;
    messagesEl.appendChild(typingEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    isStreaming = true;
    document.getElementById('sendBtn').disabled = true;

    try {
        const temperature = parseFloat(document.getElementById('chatTemperature').value);

        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: selectedChatModel,
                messages: chatHistory,
                stream: true,
                options: { temperature }
            })
        });

        // Remove typing indicator
        typingEl.remove();

        // Create assistant message element
        const assistantMsgEl = appendMessage('assistant', '');
        const contentEl = assistantMsgEl.querySelector('.message-content');
        let fullResponse = '';

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n').filter(l => l.trim());

            for (const line of lines) {
                try {
                    const json = JSON.parse(line);
                    if (json.message?.content) {
                        fullResponse += json.message.content;
                        contentEl.textContent = fullResponse;
                        messagesEl.scrollTop = messagesEl.scrollHeight;
                    }
                } catch {}
            }
        }

        chatHistory.push({ role: 'assistant', content: fullResponse });

    } catch (err) {
        typingEl.remove();
        appendMessage('assistant', `Erro: ${err.message}`);
        showToast('Erro ao se comunicar com o modelo', 'error');
    }

    isStreaming = false;
    document.getElementById('sendBtn').disabled = false;
}

function appendMessage(role, content) {
    const messagesEl = document.getElementById('chatMessages');
    const msgEl = document.createElement('div');
    msgEl.className = `message ${role}`;

    const avatar = role === 'user' ? 'Vc' : 'AI';

    msgEl.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">${escapeHtml(content)}</div>`;

    messagesEl.appendChild(msgEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return msgEl;
}

// ========================================
// PULL MODEL
// ========================================
async function pullModel() {
    const input = document.getElementById('pullModelName');
    const name = input.value.trim();
    if (!name) {
        showToast('Digite o nome do modelo', 'error');
        return;
    }

    await startPull(name);
}

function quickPull(name) {
    document.getElementById('pullModelName').value = name;
    startPull(name);
}

async function startPull(name) {
    const progressEl = document.getElementById('pullProgress');
    const progressBar = document.getElementById('pullProgressBar');
    const statusEl = document.getElementById('pullStatus');
    const pullBtn = document.getElementById('pullBtn');

    progressEl.classList.remove('hidden');
    pullBtn.disabled = true;
    progressBar.style.width = '0%';
    statusEl.textContent = `Baixando ${name}...`;
    showToast(`Iniciando download: ${name}`, 'info');

    try {
        const res = await fetch(`${API_BASE}/api/pull`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, stream: true })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n').filter(l => l.trim());

            for (const line of lines) {
                try {
                    const json = JSON.parse(line);
                    
                    if (json.total && json.completed) {
                        const pct = Math.round((json.completed / json.total) * 100);
                        progressBar.style.width = pct + '%';
                        statusEl.textContent = `${json.status} — ${pct}% (${formatBytes(json.completed)} / ${formatBytes(json.total)})`;
                    } else if (json.status) {
                        statusEl.textContent = json.status;
                        if (json.status === 'success') {
                            progressBar.style.width = '100%';
                        }
                    }
                } catch {}
            }
        }

        showToast(`Modelo ${name} baixado com sucesso!`, 'success');
        loadDashboard();

    } catch (err) {
        statusEl.textContent = `Erro: ${err.message}`;
        showToast(`Erro ao baixar ${name}: ${err.message}`, 'error');
    }

    pullBtn.disabled = false;
}

// ========================================
// DELETE MODEL
// ========================================
async function deleteModel(name) {
    if (!confirm(`Tem certeza que deseja remover o modelo "${name}"?`)) return;

    try {
        const res = await fetch(`${API_BASE}/api/delete`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        if (res.ok) {
            showToast(`Modelo ${name} removido`, 'success');
            loadDashboard();
            loadModelsDetail();
        } else {
            const errData = await res.json().catch(() => ({}));
            showToast(`Erro ao remover: ${errData.error || res.statusText}`, 'error');
        }
    } catch (err) {
        showToast(`Erro: ${err.message}`, 'error');
    }
}

// ========================================
// UTILITIES
// ========================================
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('pt-BR', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return '—';
    }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function escapeAttr(str) {
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    toast.innerHTML = `${icons[type] || icons.info}<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease-out forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ========================================
// CYBER DEFENSE — WebSocket & UI
// ========================================
const BACKEND_BASE = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';
let cyberWs = null;
let cyberSimRunning = false;
let cyberAlertCount = 0;

function initCyberDefense() {
    // Will connect WebSocket when user navigates to Cyber Defense tab
}

function connectCyberWs() {
    if (cyberWs && cyberWs.readyState === WebSocket.OPEN) return;

    const statusEl = document.getElementById('cyberWsStatus');
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('span');

    try {
        cyberWs = new WebSocket(WS_URL);

        cyberWs.onopen = () => {
            dot.className = 'status-dot online';
            text.textContent = 'Conectado ao Backend';
            addConsoleLine('system', '[SYSTEM]', 'Conectado ao servidor Python (FastAPI). Pronto para operar.');
            showToast('Conectado ao backend Cyber Defense', 'success');
        };

        cyberWs.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleCyberEvent(msg);
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        cyberWs.onclose = () => {
            dot.className = 'status-dot offline';
            text.textContent = 'Desconectado';
            addConsoleLine('system', '[SYSTEM]', 'Conexão perdida. Tentando reconectar em 5s...');
            setTimeout(() => {
                if (document.querySelector('#section-cyber.active')) {
                    connectCyberWs();
                }
            }, 5000);
        };

        cyberWs.onerror = () => {
            dot.className = 'status-dot offline';
            text.textContent = 'Erro de conexão';
        };
    } catch (err) {
        dot.className = 'status-dot offline';
        text.textContent = 'Backend offline';
        addConsoleLine('system', '[SYSTEM]', `Erro: ${err.message}. Certifique-se que o server.py está rodando (python server.py).`);
    }
}

function handleCyberEvent(msg) {
    const { type, data } = msg;

    switch (type) {
        case 'init':
            // Initial state from server
            if (data.model) {
                document.getElementById('agentModelBadge').textContent = data.model;
            }
            if (data.is_running) {
                cyberSimRunning = true;
                updateSimButton();
            }
            if (data.agent_stats) updateCyberStats(data.agent_stats);
            break;

        case 'new_alert':
            addAlertToFeed(data);
            break;

        case 'alert_received':
            addConsoleLine('alert', '[ALERT]',
                `Alerta recebido: ${data.alert?.rule?.description || 'Unknown'} | src: ${data.alert?.data?.src_ip || '?'} → :${data.alert?.data?.dest_port || '?'}`);
            break;

        case 'reasoning_start':
            const agentPrefix = data.agent ? `[${data.agent}]` : '[THINKING]';
            addConsoleLine('thought', agentPrefix, `Passo ${data.step} — analisando alerta ${data.alert_id}...`, data.agent);
            break;

        case 'reasoning_step':
            const stepPrefix = data.agent ? `[${data.agent}]` : '[THOUGHT]';
            addConsoleLine('thought', stepPrefix, data.thought || 'Processando...', data.agent);
            if (data.action && data.action !== 'finish' && !data.action.startsWith('Route')) {
                addConsoleLine('action', '[ACTION]', `Tool: ${data.action} | Args: ${JSON.stringify(data.action_input)}`, data.agent);
            }
            break;

        case 'action_executing':
            const execPrefix = data.agent ? `[${data.agent} EXEC]` : '[EXEC]';
            addConsoleLine('action', execPrefix, `Executando ${data.tool}(${JSON.stringify(data.arguments)})...`, data.agent);
            break;

        case 'action_result':
            const status = data.result?.status === 'success' ? '✓' : '✗';
            addConsoleLine('result', `[RESULT ${status}]`, data.result?.message || JSON.stringify(data.result), data.agent);
            updateFirewallRules();
            break;

        case 'mitigation_complete':
            addConsoleLine('complete', '[MITIGATED]', `${data.summary} (${data.steps_taken} passos)`);
            break;

        case 'stats_update':
            updateCyberStats(data);
            break;

        case 'simulation_started':
            cyberSimRunning = true;
            updateSimButton();
            addConsoleLine('system', '[SYSTEM]', `Simulação iniciada — cenário: ${data.scenario}, intervalo: ${data.interval}s`);
            showToast('Simulação iniciada', 'info');
            break;

        case 'simulation_stopped':
            cyberSimRunning = false;
            updateSimButton();
            addConsoleLine('system', '[SYSTEM]', 'Simulação parada.');
            showToast('Simulação parada', 'info');
            break;

        case 'model_changed':
            document.getElementById('agentModelBadge').textContent = data.model;
            addConsoleLine('system', '[SYSTEM]', `Modelo alterado para: ${data.model}`);
            break;
    }
}

// --- Alert Feed ---
function addAlertToFeed(alert) {
    const feed = document.getElementById('cyberAlertFeed');

    // Remove empty state
    const emptyState = feed.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    cyberAlertCount++;

    const severity = alert.severity || 'medium';
    const item = document.createElement('div');
    item.className = 'alert-item';
    item.innerHTML = `
        <div class="alert-severity ${severity}"></div>
        <div class="alert-info">
            <div class="alert-desc">${escapeHtml(alert.rule?.description || 'Unknown alert')}</div>
            <div class="alert-meta">
                <span class="alert-badge ${severity}">${severity}</span>
                <span>${escapeHtml(alert.data?.src_ip || '?')}:${escapeHtml(alert.data?.src_port || '?')} → ${escapeHtml(alert.data?.dest_ip || '?')}:${escapeHtml(alert.data?.dest_port || '?')}</span>
                <span>${alert.alert_type || ''}</span>
            </div>
        </div>`;

    // Add to top
    feed.insertBefore(item, feed.firstChild);

    // Keep max 50
    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

// --- Console ---
function addConsoleLine(type, prefix, text, agent = '') {
    const console_el = document.getElementById('cyberConsole');
    const line = document.createElement('div');
    const agentClass = agent ? agent.toLowerCase() : '';
    line.className = `console-line ${type} ${agentClass}`.trim();
    line.innerHTML = `<span class="console-prefix">${escapeHtml(prefix)}</span><span>${escapeHtml(text)}</span>`;
    console_el.appendChild(line);
    console_el.scrollTop = console_el.scrollHeight;

    // Keep max 200 lines
    while (console_el.children.length > 200) {
        console_el.removeChild(console_el.firstChild);
    }
}

// --- Stats ---
function updateCyberStats(stats) {
    if (stats.alerts_processed !== undefined)
        document.getElementById('cyberAlertsTotal').textContent = stats.alerts_processed;
    if (stats.actions_executed !== undefined)
        document.getElementById('cyberActionsTotal').textContent = stats.actions_executed;
    if (stats.ips_blocked !== undefined)
        document.getElementById('cyberIpsBlocked').textContent = stats.ips_blocked;
    if (stats.total_reasoning_steps !== undefined)
        document.getElementById('cyberReasoningSteps').textContent = stats.total_reasoning_steps;
}

// --- Simulation Controls ---
function toggleSimulation() {
    if (!cyberWs || cyberWs.readyState !== WebSocket.OPEN) {
        showToast('Conecte ao backend primeiro (python server.py)', 'error');
        connectCyberWs();
        return;
    }

    if (cyberSimRunning) {
        cyberWs.send(JSON.stringify({ command: 'stop_simulation' }));
    } else {
        const scenario = document.getElementById('scenarioSelect').value;
        const interval = parseFloat(document.getElementById('intervalInput').value) || 8;
        cyberWs.send(JSON.stringify({
            command: 'start_simulation',
            scenario,
            interval,
        }));
    }
}

function sendManualAlert() {
    if (!cyberWs || cyberWs.readyState !== WebSocket.OPEN) {
        showToast('Conecte ao backend primeiro', 'error');
        connectCyberWs();
        return;
    }

    const scenario = document.getElementById('scenarioSelect').value;
    cyberWs.send(JSON.stringify({ command: 'manual_alert', scenario }));
}

function updateSimButton() {
    const btn = document.getElementById('startSimBtn');
    if (cyberSimRunning) {
        btn.className = 'btn btn-stop';
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
            Parar Simulação`;
    } else {
        btn.className = 'btn btn-primary';
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Iniciar Simulação`;
    }
}

// --- Firewall Rules ---
async function updateFirewallRules() {
    try {
        const res = await fetch(`${BACKEND_BASE}/api/firewall`);
        const data = await res.json();
        const rules = data.rules || [];
        const container = document.getElementById('firewallRulesContainer');

        if (rules.length === 0) {
            container.innerHTML = `<div class="empty-state"><p>Nenhuma regra aplicada ainda.</p></div>`;
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Ação</th>
                        <th>IP Origem</th>
                        <th>Host Alvo</th>
                        <th>Data</th>
                    </tr>
                </thead>
                <tbody>
                    ${rules.map(r => `
                        <tr>
                            <td style="color: var(--text-muted);">${r.id}</td>
                            <td><span class="alert-badge critical">${escapeHtml(r.action)}</span></td>
                            <td><span class="model-name">${escapeHtml(r.source_ip)}</span></td>
                            <td style="color: var(--text-secondary); font-size: 0.82rem;">${escapeHtml(r.target_host)}</td>
                            <td style="color: var(--text-secondary); font-size: 0.82rem;">${formatDate(r.created_at)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
    } catch {
        // Backend not running, silently ignore
    }
}
