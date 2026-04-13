/**
 * Impulse AI Analyst Dashboard
 * History, Live Terminal, and Autopilot modes
 * WebSocket, real-time charts, AI chat with code execution
 */

// ===== Configuration =====
const API_BASE = window.location.origin;
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${WS_PROTOCOL}//${window.location.host}/ws/logs`;
const MAX_LOGS_DISPLAY = 100;

// ===== State =====
let ws = null;
let wsConnected = false;
let wsReconnectTimer = null;
let wsReconnectDelay = 1000;
let countdownInterval = null;
let nextRunTimestamp = null;

// History Mode State
let currentHistoryDataId = null;
let historyConversations = [];

// Live Mode State
let mt5Connected = false;
let liveChartInterval = null;
let positionsRefreshInterval = null;
let currentLiveSymbol = 'XAUUSD';
let currentLiveTimeframe = '1m';

// Autopilot State
let autopilotStatus = null;

// ===== DOM Elements =====
const elements = {
    // Connection
    connectionStatus: document.getElementById('connectionStatus'),
    serverTime: document.getElementById('serverTime'),
    refreshBtn: document.getElementById('refreshBtn'),

    // Tab Navigation
    tabButtons: document.querySelectorAll('.tab-btn'),
    historyTab: document.getElementById('historyTab'),
    liveTab: document.getElementById('liveTab'),
    autopilotTab: document.getElementById('autopilotTab'),

    // ===== HISTORY MODE =====
    // Upload
    uploadZone: document.getElementById('uploadZone'),
    fileInput: document.getElementById('fileInput'),
    browseBtn: document.getElementById('browseBtn'),
    uploadStatus: document.getElementById('uploadStatus'),

    // Data Preview
    dataPreviewCard: document.getElementById('dataPreviewCard'),
    dataInfo: document.getElementById('dataInfo'),
    previewTableHead: document.getElementById('previewTableHead'),
    previewTableBody: document.getElementById('previewTableBody'),

    // History Chat
    historyChatMessages: document.getElementById('historyChatMessages'),
    historyChatInput: document.getElementById('historyChatInput'),
    historyChatSend: document.getElementById('historyChatSend'),

    // History Code Output
    historyCodeOutput: document.getElementById('historyCodeOutput'),
    historyCodeBlock: document.getElementById('historyCodeBlock'),
    historyCodeOutputText: document.getElementById('historyCodeOutputText'),
    historyPlots: document.getElementById('historyPlots'),

    // History Trade Setup
    historyTradeSetup: document.getElementById('historyTradeSetup'),
    historyTradeSetupInfo: document.getElementById('historyTradeSetupInfo'),

    // ===== LIVE MODE =====
    // MT5 Connection
    mt5ConnectionGate: document.getElementById('mt5ConnectionGate'),
    liveMt5Url: document.getElementById('liveMt5Url'),
    liveMt5Token: document.getElementById('liveMt5Token'),
    connectMt5Btn: document.getElementById('connectMt5Btn'),
    mt5ConnectionStatus: document.getElementById('mt5ConnectionStatus'),

    // Live Terminal
    liveTerminal: document.getElementById('liveTerminal'),
    liveSymbol: document.getElementById('liveSymbol'),
    liveTimeframe: document.getElementById('liveTimeframe'),
    liveCount: document.getElementById('liveCount'),
    fetchLiveBtn: document.getElementById('fetchLiveBtn'),
    autoRefreshToggle: document.getElementById('autoRefreshToggle'),

    // Live Chart
    liveChart: document.getElementById('liveChart'),
    marketMetrics: document.getElementById('marketMetrics'),

    // Live Chat
    liveChatMessages: document.getElementById('liveChatMessages'),
    liveChatInput: document.getElementById('liveChatInput'),
    liveChatSend: document.getElementById('liveChatSend'),

    // Position Manager
    positionsList: document.getElementById('positionsList'),
    refreshPositionsBtn: document.getElementById('refreshPositionsBtn'),

    // Live Trade Setup
    liveTradeSetup: document.getElementById('liveTradeSetup'),
    liveTradeSetupInfo: document.getElementById('liveTradeSetupInfo'),
    liveTradeActionButtons: document.getElementById('liveTradeActionButtons'),

    // Live Trade Action
    liveTradeAction: document.getElementById('liveTradeAction'),
    liveTradeActionInfo: document.getElementById('liveTradeActionInfo'),
    liveTradeActionButtons2: document.getElementById('liveTradeActionButtons2'),

    // Live Code Output
    liveCodeOutput: document.getElementById('liveCodeOutput'),
    liveCodeBlock: document.getElementById('liveCodeBlock'),
    liveCodeOutputText: document.getElementById('liveCodeOutputText'),
    livePlots: document.getElementById('livePlots'),

    // ===== AUTOPILOT MODE =====
    // Status Bar
    autopilotStatus: document.getElementById('autopilotStatus'),
    nextRun: document.getElementById('nextRun'),
    countdown: document.getElementById('countdown'),
    totalRuns: document.getElementById('totalRuns'),
    currentInterval: document.getElementById('currentInterval'),

    // Controls
    startBtn: document.getElementById('startBtn'),
    stopBtn: document.getElementById('stopBtn'),
    intervalSelect: document.getElementById('intervalSelect'),
    applyIntervalBtn: document.getElementById('applyIntervalBtn'),

    // AI Provider Config
    providerSelect: document.getElementById('providerSelect'),
    modelSelect: document.getElementById('modelSelect'),
    apiKeyInput: document.getElementById('apiKeyInput'),
    mt5UrlInput: document.getElementById('mt5UrlInput'),
    mt5TokenInput: document.getElementById('mt5TokenInput'),
    toggleApiKey: document.getElementById('toggleApiKey'),
    toggleMt5Token: document.getElementById('toggleMt5Token'),
    saveConfigBtn: document.getElementById('saveConfigBtn'),
    configStatus: document.getElementById('configStatus'),

    // Statistics
    successCount: document.getElementById('successCount'),
    errorCount: document.getElementById('errorCount'),
    successRate: document.getElementById('successRate'),
    totalTrades: document.getElementById('totalTrades'),
    totalPnl: document.getElementById('totalPnl'),
    openPositions: document.getElementById('openPositions'),

    // Logs
    logContainer: document.getElementById('logContainer'),
    logLevelFilter: document.getElementById('logLevelFilter'),
    clearLogsBtn: document.getElementById('clearLogsBtn'),

    // Trades
    tradeTableBody: document.getElementById('tradeTableBody'),
    refreshTradesBtn: document.getElementById('refreshTradesBtn'),

    // Toast
    toastContainer: document.getElementById('toastContainer'),

    // Footer
    lastUpdate: document.getElementById('lastUpdate')
};

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Impulse AI Analyst Dashboard initializing...');

    // Setup event listeners
    setupEventListeners();

    // Connect WebSocket
    connectWebSocket();

    // Load initial data based on current tab
    loadAutopilotStatus();
    loadConfig();
    loadStats();
    loadLogs();
    loadTrades();

    // Start server time clock
    updateServerTime();
    setInterval(updateServerTime, 1000);

    console.log('✅ Dashboard initialized');
});

// ===== Event Listeners =====
function setupEventListeners() {
    // Tab Navigation
    elements.tabButtons.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // ===== HISTORY MODE =====
    elements.browseBtn.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileUpload);

    // Drag and drop
    elements.uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.uploadZone.classList.add('dragover');
    });
    elements.uploadZone.addEventListener('dragleave', () => {
        elements.uploadZone.classList.remove('dragover');
    });
    elements.uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            elements.fileInput.files = e.dataTransfer.files;
            handleFileUpload();
        }
    });

    // Clear Workspace button
    document.getElementById('clearWorkspaceBtn').addEventListener('click', clearWorkspace);

    // Data Source buttons
    document.getElementById('fetchHFBtn').addEventListener('click', fetchFromHuggingFace);
    document.getElementById('fetchYahooBtn').addEventListener('click', fetchFromYahoo);
    document.getElementById('fetchMT5Btn').addEventListener('click', fetchFromMT5);
    document.getElementById('fetchYahooVaultBtn').addEventListener('click', fetchYahooVault);

    // Auto-Sync toggle
    document.getElementById('autoSyncToggle').addEventListener('change', (e) => {
        document.getElementById('autoSyncOptions').style.display = e.target.checked ? 'block' : 'none';
        if (e.target.checked) {
            startAutoSync();
        } else {
            stopAutoSync();
        }
    });

    // Web Intel Search
    document.getElementById('webIntelSearchBtn').addEventListener('click', searchWebIntel);

    // History Chat
    elements.historyChatSend.addEventListener('click', () => sendHistoryChat());
    elements.historyChatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendHistoryChat();
        }
    });

    // ===== LIVE MODE =====
    elements.connectMt5Btn.addEventListener('click', connectMT5);

    elements.fetchLiveBtn.addEventListener('click', fetchLiveCandles);

    elements.autoRefreshToggle.addEventListener('change', (e) => {
        if (e.target.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    // Live Chat
    elements.liveChatSend.addEventListener('click', () => sendLiveChat());
    elements.liveChatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendLiveChat();
        }
    });

    // Position Manager
    elements.refreshPositionsBtn.addEventListener('click', loadPositions);

    // ===== AUTOPILOT MODE =====
    elements.startBtn.addEventListener('click', startAutopilot);
    elements.stopBtn.addEventListener('click', stopAutopilot);
    elements.applyIntervalBtn.addEventListener('click', applyInterval);

    // AI Provider config
    elements.providerSelect.addEventListener('change', onProviderChange);
    elements.toggleApiKey.addEventListener('click', () => toggleVisibility(elements.apiKeyInput, elements.toggleApiKey));
    elements.toggleMt5Token.addEventListener('click', () => toggleVisibility(elements.mt5TokenInput, elements.toggleMt5Token));
    elements.saveConfigBtn.addEventListener('click', saveConfig);
    document.getElementById('useDefaultKeyBtn').addEventListener('click', useDefaultKeys);
    document.getElementById('testConnectionBtn').addEventListener('click', testAIConnection);
    document.getElementById('clearMemoryBtn').addEventListener('click', clearAIMemory);
    document.getElementById('downloadEABtn').addEventListener('click', downloadEAFiles);

    // Logs & Trades
    elements.logLevelFilter.addEventListener('change', loadLogs);
    elements.clearLogsBtn.addEventListener('click', clearLogs);
    elements.refreshTradesBtn.addEventListener('click', loadTrades);
    elements.refreshBtn.addEventListener('click', refreshAll);
}

// ===== Tab Switching =====
function switchTab(tabName) {
    // Update tab buttons
    elements.tabButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update tab content
    elements.historyTab.classList.toggle('active', tabName === 'history');
    elements.liveTab.classList.toggle('active', tabName === 'live');
    elements.autopilotTab.classList.toggle('active', tabName === 'autopilot');

    console.log(`📑 Switched to ${tabName} tab`);

    // Load data for the selected tab
    if (tabName === 'history') {
        // Nothing extra to load
    } else if (tabName === 'live') {
        // Check if MT5 is connected
        if (mt5Connected) {
            loadPositions();
        }
    } else if (tabName === 'autopilot') {
        loadAutopilotStatus();
        loadStats();
    }
}

// ===== HISTORY MODE FUNCTIONS =====

async function handleFileUpload() {
    const file = elements.fileInput.files[0];
    if (!file) return;

    // Check file type
    const validExtensions = ['.csv', '.parquet'];
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();

    if (!validExtensions.includes(fileExt)) {
        showUploadStatus('Invalid file type. Please upload .csv or .parquet', 'error');
        return;
    }

    showUploadStatus(`Uploading ${file.name}...`, 'loading');

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/api/history/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();

        if (data.success) {
            currentHistoryDataId = data.filename;
            showUploadStatus(`✅ ${data.message}`, 'success');
            showDataPreview(data);
            showToast('File uploaded successfully', 'success');
        } else {
            throw new Error(data.message || 'Upload failed');
        }

    } catch (error) {
        console.error('❌ Upload error:', error);
        showUploadStatus(`Upload failed: ${error.message}`, 'error');
        showToast(`Upload failed: ${error.message}`, 'error');
    }
}

function showUploadStatus(message, type) {
    elements.uploadStatus.textContent = message;
    elements.uploadStatus.className = `upload-status ${type}`;
}

function showDataPreview(data) {
    elements.dataPreviewCard.style.display = 'block';

    // Update data info
    elements.dataInfo.innerHTML = `
        <span>📄 <strong>${data.filename}</strong></span>
        <span>📊 <strong>${data.rows.toLocaleString()}</strong> rows</span>
        <span>📐 <strong>${data.columns}</strong> columns</span>
    `;

    // Build table header
    elements.previewTableHead.innerHTML = `
        <tr>${data.column_names.map(col => `<th>${col}</th>`).join('')}</tr>
    `;

    // Build table body (first 10 rows)
    elements.previewTableBody.innerHTML = data.preview.map(row => `
        <tr>${data.column_names.map(col => `<td>${row[col] !== null ? row[col] : '-'}</td>`).join('')}</tr>
    `).join('');
}

async function sendHistoryChat() {
    const message = elements.historyChatInput.value.trim();
    if (!message) return;

    if (!currentHistoryDataId) {
        showToast('Please upload or fetch data first', 'warning');
        return;
    }

    // Add user message
    addChatMessage(elements.historyChatMessages, 'user', message);
    elements.historyChatInput.value = '';

    // Show typing indicator
    const typingId = addChatMessage(elements.historyChatMessages, 'assistant', 'Analyzing data...', true);

    try {
        const response = await fetch(`${API_BASE}/api/ai/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_id: 'history'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Chat failed');
        }

        const data = await response.json();

        // Remove typing indicator
        removeChatMessage(elements.historyChatMessages, typingId);

        // Add AI response
        addChatMessage(elements.historyChatMessages, 'assistant', data.ai_text);

        // Show code output if any
        if (data.code_executed) {
            elements.historyCodeOutput.style.display = 'block';
            elements.historyCodeBlock.textContent = data.code_output || 'No output';
            elements.historyCodeOutputText.textContent = data.code_error || '';
            elements.historyCodeOutputText.className = data.code_error ? 'code-output error' : 'code-output';

            // Render plots
            if (data.figures && data.figures.length > 0) {
                elements.historyPlots.innerHTML = '';
                data.figures.forEach((fig, idx) => {
                    const plotDiv = document.createElement('div');
                    plotDiv.className = 'plot-container';
                    plotDiv.id = `historyPlot${idx}`;
                    elements.historyPlots.appendChild(plotDiv);
                    Plotly.newPlot(`historyPlot${idx}`, fig.data, fig.layout, { responsive: true });
                });
            }

            // Show self-heal attempts if any
            if (data.self_heal_attempts > 0) {
                elements.historyCodeOutputText.textContent += `\n\n🔄 Self-healing: ${data.self_heal_attempts} retry attempt(s)`;
            }
        }

        // Show trade setup if detected
        if (data.trade_setup) {
            elements.historyTradeSetup.style.display = 'block';
            elements.historyTradeSetupInfo.innerHTML = formatTradeSetupInfo(data.trade_setup);
        }

        // Show trade action if detected (for position management)
        if (data.trade_action) {
            elements.historyTradeAction.style.display = 'block';
            elements.historyTradeActionInfo.innerHTML = formatTradeActionInfo(data.trade_action);
            document.getElementById('historyTradeActionButtons').innerHTML = `
                <button class="btn btn-primary" onclick="executeTradeAction('${data.trade_action.action}', ${data.trade_action.ticket || 0}, ${data.trade_action.new_sl || 'null'}, ${data.trade_action.new_tp || 'null'})">
                    <i class="fas fa-check"></i> Apply
                </button>
                <button class="btn btn-secondary" onclick="ignoreTradeAction('history')">
                    <i class="fas fa-times"></i> Ignore
                </button>
            `;
        }

    } catch (error) {
        console.error('❌ Chat error:', error);
        removeChatMessage(elements.historyChatMessages, typingId);
        addChatMessage(elements.historyChatMessages, 'assistant', `❌ Error: ${error.message}`);
    }
}

// ===== DATA SOURCE FUNCTIONS =====

async function fetchFromHuggingFace() {
    const symbol = prompt("Enter symbol (e.g., XAUUSD):", "XAUUSD");
    if (!symbol) return;

    showUploadStatus('Fetching from HuggingFace...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/api/data/sync/huggingface?symbol=${symbol}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            currentHistoryDataId = data.data_id;
            showUploadStatus(`✅ ${data.message}`, 'success');
            showToast('Data loaded from HuggingFace', 'success');
        } else {
            showUploadStatus(`❌ ${data.message}`, 'error');
            showToast(data.message, 'error');
        }
    } catch (error) {
        showUploadStatus(`Fetch failed: ${error.message}`, 'error');
        showToast(`Fetch failed: ${error.message}`, 'error');
    }
}

async function fetchFromYahoo() {
    const symbol = prompt("Enter symbol (e.g., GC=F, NVDA):", "GC=F");
    if (!symbol) return;

    showUploadStatus('Fetching from Yahoo Finance...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/api/data/yahoo/fetch?symbol=${symbol}&period=1y&interval=1d`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            currentHistoryDataId = data.data_id;
            showUploadStatus(`✅ ${data.message}`, 'success');
            showToast('Data loaded from Yahoo Finance', 'success');
        } else {
            showUploadStatus(`❌ ${data.detail || 'Fetch failed'}`, 'error');
        }
    } catch (error) {
        showUploadStatus(`Fetch failed: ${error.message}`, 'error');
    }
}

async function fetchFromMT5() {
    const symbol = prompt("Enter symbol (e.g., XAUUSD):", "XAUUSD");
    if (!symbol) return;

    showUploadStatus('Fetching from MT5...', 'loading');

    try {
        const response = await fetch(`${API_BASE}/api/data/sync/mt5?symbol=${symbol}&timeframe=1m&count=1000`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            currentHistoryDataId = data.data_id;
            showUploadStatus(`✅ ${data.message}`, 'success');
            showToast('Data loaded from MT5', 'success');
        } else {
            showUploadStatus(`❌ ${data.detail || 'Fetch failed'}`, 'error');
        }
    } catch (error) {
        showUploadStatus(`Fetch failed: ${error.message}`, 'error');
    }
}

async function fetchYahooVault() {
    const symbol = document.getElementById('yahooSymbol').value.trim();
    if (!symbol) {
        showYahooStatus('Please enter a ticker symbol', 'error');
        return;
    }

    const period = document.getElementById('yahooPeriod').value;
    const interval = document.getElementById('yahooInterval').value;
    const archive = document.getElementById('yahooArchiveToggle').checked;

    showYahooStatus(`Fetching ${symbol} from Yahoo Finance...`, 'loading');

    try {
        const response = await fetch(`${API_BASE}/api/data/yahoo/fetch?symbol=${symbol}&period=${period}&interval=${interval}&archive_to_hf=${archive}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            currentHistoryDataId = data.data_id;
            showYahooStatus(`✅ ${data.message}${data.archived_to_hf ? ' + Archived to Cloud' : ''}`, 'success');
            showToast('Data vaulted successfully', 'success');
        } else {
            showYahooStatus(`❌ ${data.detail || 'Fetch failed'}`, 'error');
        }
    } catch (error) {
        showYahooStatus(`Fetch failed: ${error.message}`, 'error');
    }
}

function showYahooStatus(message, type) {
    const el = document.getElementById('yahooStatus');
    el.textContent = message;
    el.className = `upload-status ${type}`;
}

// ===== AUTO-SYNC FUNCTIONS =====
let autoSyncInterval = null;

function startAutoSync() {
    const intervalMin = parseInt(document.getElementById('autoSyncInterval').value);
    const intervalMs = intervalMin * 60 * 1000;

    showAutoSyncStatus(`🔄 Auto-sync enabled - Every ${intervalMin} minute${intervalMin > 1 ? 's' : ''}`, 'success');

    autoSyncInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/api/data/sync/auto`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbols: ['XAUUSD', 'EURUSD'] })
            });

            const data = await response.json();
            if (data.success) {
                showAutoSyncStatus(`✅ Synced at ${new Date().toLocaleTimeString()}`, 'success');
            }
        } catch (error) {
            showAutoSyncStatus(`❌ Sync failed: ${error.message}`, 'error');
        }
    }, intervalMs);
}

function stopAutoSync() {
    if (autoSyncInterval) {
        clearInterval(autoSyncInterval);
        autoSyncInterval = null;
    }
    showAutoSyncStatus('⏹️ Auto-sync disabled', 'error');
}

function showAutoSyncStatus(message, type) {
    const el = document.getElementById('autoSyncStatus');
    el.textContent = message;
    el.className = `upload-status ${type}`;
}

// ===== WEB INTEL SEARCH =====

async function searchWebIntel() {
    const query = document.getElementById('webIntelQuery').value.trim();
    if (!query) {
        showToast('Please enter a research topic', 'warning');
        return;
    }

    const maxResults = parseInt(document.getElementById('webIntelMaxResults').value);
    const searchType = document.getElementById('webIntelType').value;
    const resultsDiv = document.getElementById('webIntelResults');

    resultsDiv.innerHTML = '<div class="text-muted text-center">🔍 Searching...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/data/web/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                max_results: maxResults,
                search_type: searchType
            })
        });

        const data = await response.json();

        if (data.success && data.results.length > 0) {
            let html = `<div class="sentiment-badge">${data.sentiment || 'Neutral'}</div>`;
            html += `<div class="results-count">${data.results.length} results found</div>`;

            data.results.forEach((r, i) => {
                html += `
                    <div class="result-item">
                        <h4><a href="${r.href}" target="_blank">${r.title}</a></h4>
                        <p class="result-body">${r.body}</p>
                        <a href="${r.href}" target="_blank" class="result-link">Read full article →</a>
                    </div>
                `;
            });

            resultsDiv.innerHTML = html;
        } else {
            resultsDiv.innerHTML = '<div class="text-muted text-center">No results found</div>';
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="text-muted text-center">❌ Search failed: ${error.message}</div>`;
    }
}

// ===== LIVE MODE FUNCTIONS =====

async function connectMT5() {
    const url = elements.liveMt5Url.value.trim();
    const token = elements.liveMt5Token.value.trim();

    if (!url || !token) {
        showMt5ConnectionStatus('Please enter URL and Token', 'error');
        return;
    }

    showMt5ConnectionStatus('Connecting to MT5 server...', 'loading');
    elements.connectMt5Btn.disabled = true;
    elements.connectMt5Btn.innerHTML = '<span class="spinner"></span> Connecting...';

    try {
        const response = await fetch(`${API_BASE}/api/live/connect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, token })
        });

        const data = await response.json();

        if (data.success && data.mt5_initialized) {
            mt5Connected = true;
            showMt5ConnectionStatus('✅ Connection established!', 'success');
            elements.liveTerminal.style.display = 'block';
            showToast('MT5 connected successfully', 'success');

            // Auto-fetch candles
            fetchLiveCandles();

            // Start position refresh
            startPositionsAutoRefresh();
        } else {
            mt5Connected = false;
            showMt5ConnectionStatus(`❌ ${data.message}`, 'error');
            elements.liveTerminal.style.display = 'none';
        }

    } catch (error) {
        console.error('❌ MT5 connection error:', error);
        showMt5ConnectionStatus(`Connection failed: ${error.message}`, 'error');
        elements.liveTerminal.style.display = 'none';
    } finally {
        elements.connectMt5Btn.disabled = false;
        elements.connectMt5Btn.innerHTML = '<i class="fas fa-link"></i> Connect';
    }
}

function showMt5ConnectionStatus(message, type) {
    elements.mt5ConnectionStatus.textContent = message;
    elements.mt5ConnectionStatus.className = `connection-status-text ${type}`;
}

async function fetchLiveCandles() {
    const symbol = elements.liveSymbol.value;
    const timeframe = elements.liveTimeframe.value;
    const count = parseInt(elements.liveCount.value);

    currentLiveSymbol = symbol;
    currentLiveTimeframe = timeframe;

    elements.fetchLiveBtn.disabled = true;
    elements.fetchLiveBtn.innerHTML = '<span class="spinner"></span> Fetching...';

    try {
        const response = await fetch(`${API_BASE}/api/live/candles`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, timeframe, count })
        });

        const data = await response.json();

        if (data.success && data.data.length > 0) {
            renderLiveChart(data.data);
            updateMarketMetrics(data.data);
            showToast(`Loaded ${data.count} candles for ${symbol}`, 'success');
        } else {
            showToast('No data available', 'warning');
        }

    } catch (error) {
        console.error('❌ Fetch candles error:', error);
        showToast(`Failed to fetch data: ${error.message}`, 'error');
    } finally {
        elements.fetchLiveBtn.disabled = false;
        elements.fetchLiveBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Fetch Data';
    }
}

function renderLiveChart(candles) {
    // Convert to arrays for Plotly
    const times = candles.map(c => c.time);
    const opens = candles.map(c => c.open);
    const highs = candles.map(c => c.high);
    const lows = candles.map(c => c.low);
    const closes = candles.map(c => c.close);

    const trace = {
        x: times,
        open: opens,
        high: highs,
        low: lows,
        close: closes,
        type: 'candlestick',
        name: currentLiveSymbol
    };

    const layout = {
        title: `${currentLiveSymbol} - ${currentLiveTimeframe}`,
        template: 'plotly_dark',
        height: 500,
        margin: { l: 50, r: 20, t: 50, b: 50 },
        xaxis: {
            rangeslider: { visible: false }
        },
        yaxis: {
            domain: [0, 1]
        }
    };

    Plotly.newPlot('liveChart', [trace], layout, { responsive: true });
}

function updateMarketMetrics(candles) {
    if (candles.length === 0) return;

    const last = candles[candles.length - 1];
    const prev = candles.length > 1 ? candles[candles.length - 2] : last;

    const change = last.close - prev.open;
    const changePercent = ((change / prev.open) * 100).toFixed(2);
    const isUp = change >= 0;

    elements.marketMetrics.innerHTML = `
        <div class="metric-item">
            <div class="metric-label">Current</div>
            <div class="metric-value ${isUp ? 'up' : 'down'}">${last.close.toFixed(5)}</div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Open</div>
            <div class="metric-value">${last.open.toFixed(5)}</div>
        </div>
        <div class="metric-item">
            <div class="metric-label">High</div>
            <div class="metric-value up">${last.high.toFixed(5)}</div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Low</div>
            <div class="metric-value down">${last.low.toFixed(5)}</div>
        </div>
        <div class="metric-item">
            <div class="metric-label">Change</div>
            <div class="metric-value ${isUp ? 'up' : 'down'}">${isUp ? '+' : ''}${changePercent}%</div>
        </div>
    `;
}

function startAutoRefresh() {
    if (liveChartInterval) clearInterval(liveChartInterval);
    liveChartInterval = setInterval(() => {
        if (mt5Connected) {
            fetchLiveCandles();
        }
    }, 60000); // Every 60 seconds
    console.log('📡 Auto-refresh enabled');
}

function stopAutoRefresh() {
    if (liveChartInterval) {
        clearInterval(liveChartInterval);
        liveChartInterval = null;
    }
    console.log('📡 Auto-refresh disabled');
}

async function sendLiveChat() {
    const message = elements.liveChatInput.value.trim();
    if (!message) return;

    if (!mt5Connected) {
        showToast('Please connect to MT5 first', 'warning');
        return;
    }

    // Add user message
    addChatMessage(elements.liveChatMessages, 'user', message);
    elements.liveChatInput.value = '';

    // Show typing indicator
    const typingId = addChatMessage(elements.liveChatMessages, 'assistant', 'Analyzing live market...', true);

    try {
        const response = await fetch(`${API_BASE}/api/ai/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_id: 'live',
                symbol: currentLiveSymbol,
                timeframe: currentLiveTimeframe
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Chat failed');
        }

        const data = await response.json();

        // Remove typing indicator
        removeChatMessage(elements.liveChatMessages, typingId);

        // Add AI response
        addChatMessage(elements.liveChatMessages, 'assistant', data.ai_text);

        // Show code output if any
        if (data.code_executed) {
            elements.liveCodeOutput.style.display = 'block';
            elements.liveCodeBlock.textContent = data.code_output || 'No output';
            elements.liveCodeOutputText.textContent = data.code_error || '';
            elements.liveCodeOutputText.className = data.code_error ? 'code-output error' : 'code-output';

            // Render plots
            if (data.figures && data.figures.length > 0) {
                elements.livePlots.innerHTML = '';
                data.figures.forEach((fig, idx) => {
                    const plotDiv = document.createElement('div');
                    plotDiv.className = 'plot-container';
                    plotDiv.id = `livePlot${idx}`;
                    elements.livePlots.appendChild(plotDiv);
                    Plotly.newPlot(`livePlot${idx}`, fig.data, fig.layout, { responsive: true });
                });
            }
        }

        // Show trade setup if detected
        if (data.trade_setup) {
            elements.liveTradeSetup.style.display = 'block';
            elements.liveTradeSetupInfo.innerHTML = formatTradeSetupInfo(data.trade_setup);
            elements.liveTradeActionButtons.innerHTML = `
                <button class="btn btn-primary" onclick="executeTrade('${data.trade_setup.direction}', ${data.trade_setup.entry_price}, ${data.trade_setup.stop_loss || 'null'}, ${data.trade_setup.take_profit || 'null'}, ${data.trade_setup.lot_size || 0.1})">
                    <i class="fas fa-bolt"></i> Market Execute
                </button>
                <button class="btn btn-secondary" onclick="placePendingOrder('${data.trade_setup.direction}', ${data.trade_setup.entry_price}, ${data.trade_setup.stop_loss || 'null'}, ${data.trade_setup.take_profit || 'null'}, ${data.trade_setup.lot_size || 0.1})">
                    <i class="fas fa-clock"></i> Smart Pending
                </button>
            `;
        }

        // Show trade action if detected
        if (data.trade_action) {
            elements.liveTradeAction.style.display = 'block';
            elements.liveTradeActionInfo.innerHTML = formatTradeActionInfo(data.trade_action);
            elements.liveTradeActionButtons2.innerHTML = `
                <button class="btn btn-primary" onclick="executeTradeAction('${data.trade_action.action}', ${data.trade_action.ticket}, ${data.trade_action.new_sl || 'null'}, ${data.trade_action.new_tp || 'null'})">
                    <i class="fas fa-check"></i> Apply
                </button>
                <button class="btn btn-secondary" onclick="ignoreTradeAction()">
                    <i class="fas fa-times"></i> Ignore
                </button>
            `;
        }

    } catch (error) {
        console.error('❌ Live chat error:', error);
        removeChatMessage(elements.liveChatMessages, typingId);
        addChatMessage(elements.liveChatMessages, 'assistant', `❌ Error: ${error.message}`);
    }
}

async function loadPositions() {
    if (!mt5Connected) return;

    try {
        const response = await fetch(`${API_BASE}/api/live/positions`);
        const data = await response.json();

        if (data.success) {
            renderPositions(data);
        }

    } catch (error) {
        console.error('❌ Load positions error:', error);
    }
}

function renderPositions(data) {
    if (data.open_count === 0) {
        elements.positionsList.innerHTML = '<p class="text-muted text-center">No open positions</p>';
        return;
    }

    elements.positionsList.innerHTML = data.positions.map(pos => `
        <div class="position-item">
            <div class="position-header">
                <span class="position-symbol">${pos.symbol}</span>
                <span class="position-direction ${pos.direction.toLowerCase() === 'buy' ? 'buy' : 'sell'}">
                    ${pos.direction}
                </span>
            </div>
            <div class="position-details">
                <div class="position-detail">
                    <span class="position-label">Ticket</span>
                    <span class="position-value">#${pos.ticket}</span>
                </div>
                <div class="position-detail">
                    <span class="position-label">Entry</span>
                    <span class="position-value">${pos.entry_price}</span>
                </div>
                <div class="position-detail">
                    <span class="position-label">Current</span>
                    <span class="position-value">${pos.current_price}</span>
                </div>
                <div class="position-detail">
                    <span class="position-label">P&L</span>
                    <span class="position-value position-pnl ${pos.profit >= 0 ? 'positive' : 'negative'}">
                        ${pos.profit >= 0 ? '+' : ''}$${pos.profit.toFixed(2)}
                    </span>
                </div>
                <div class="position-detail">
                    <span class="position-label">SL</span>
                    <span class="position-value">${pos.sl || '-'}</span>
                </div>
                <div class="position-detail">
                    <span class="position-label">TP</span>
                    <span class="position-value">${pos.tp || '-'}</span>
                </div>
            </div>
            <div class="position-actions">
                <button class="btn btn-sm btn-danger" onclick="closePositionDirect(${pos.ticket})">
                    <i class="fas fa-times"></i> Close
                </button>
                <button class="btn btn-sm btn-secondary" onclick="modifyPositionDirect(${pos.ticket}, '${pos.sl || ''}', '${pos.tp || ''}')">
                    <i class="fas fa-edit"></i> Modify SL/TP
                </button>
            </div>
        </div>
    `).join('');
}

function startPositionsAutoRefresh() {
    if (positionsRefreshInterval) clearInterval(positionsRefreshInterval);
    positionsRefreshInterval = setInterval(() => {
        if (mt5Connected) {
            loadPositions();
        }
    }, 30000); // Every 30 seconds
}

// ===== Trade Execution Functions =====

async function executeTrade(direction, entry, sl, tp, lot) {
    if (!mt5Connected) {
        showToast('MT5 not connected', 'error');
        return;
    }

    const action = direction.toUpperCase();

    try {
        const response = await fetch(`${API_BASE}/api/live/order/place`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentLiveSymbol,
                action: action,
                volume: lot,
                sl: sl,
                tp: tp,
                comment: '[AI_ANALYST]'
            })
        });

        const data = await response.json();

        if (data.success) {
            showToast(`✅ ${action} order placed! Ticket: #${data.ticket}`, 'success');
            loadPositions();
        } else {
            showToast(`❌ Order failed: ${data.message}`, 'error');
        }

    } catch (error) {
        console.error('❌ Execute trade error:', error);
        showToast(`Trade execution failed: ${error.message}`, 'error');
    }
}

async function placePendingOrder(direction, entry, sl, tp, lot) {
    if (!mt5Connected) {
        showToast('MT5 not connected', 'error');
        return;
    }

    // Fetch current tick to determine order type
    try {
        const symbolResponse = await fetch(`${API_BASE}/api/live/symbol/${currentLiveSymbol}`);
        const symbolData = await symbolResponse.json();

        if (!symbolData.success) {
            throw new Error('Failed to get symbol info');
        }

        const ask = symbolData.ask;
        const bid = symbolData.bid;

        let smartAction;
        if (direction.toUpperCase() === 'BUY') {
            smartAction = entry < ask ? 'BUY_LIMIT' : 'BUY_STOP';
        } else {
            smartAction = entry > bid ? 'SELL_LIMIT' : 'SELL_STOP';
        }

        const response = await fetch(`${API_BASE}/api/live/order/place`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: currentLiveSymbol,
                action: smartAction,
                volume: lot,
                price: entry,
                sl: sl,
                tp: tp,
                comment: '[AI_ANALYST_PENDING]'
            })
        });

        const data = await response.json();

        if (data.success) {
            showToast(`✅ ${smartAction} pending order placed! Ticket: #${data.ticket}`, 'success');
            loadPositions();
        } else {
            showToast(`❌ Order failed: ${data.message}`, 'error');
        }

    } catch (error) {
        console.error('❌ Pending order error:', error);
        showToast(`Pending order failed: ${error.message}`, 'error');
    }
}

async function executeTradeAction(action, ticket, sl, tp) {
    if (!mt5Connected) {
        showToast('MT5 not connected', 'error');
        return;
    }

    try {
        let response;

        if (action === 'CLOSE_POSITION') {
            response = await fetch(`${API_BASE}/api/live/order/close`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticket })
            });
        } else if (action.includes('MODIFY')) {
            response = await fetch(`${API_BASE}/api/live/order/modify?ticket=${ticket}&sl=${sl}&tp=${tp}`, {
                method: 'POST'
            });
        }

        const data = await response.json();

        if (data.success) {
            showToast(`✅ ${action} executed successfully!`, 'success');
            loadPositions();
        } else {
            showToast(`❌ Action failed: ${data.message}`, 'error');
        }

    } catch (error) {
        console.error('❌ Trade action error:', error);
        showToast(`Action failed: ${error.message}`, 'error');
    }
}

function ignoreTradeAction(mode = 'live') {
    if (mode === 'history') {
        document.getElementById('historyTradeAction').style.display = 'none';
    } else {
        elements.liveTradeAction.style.display = 'none';
    }
    showToast('Trade suggestion ignored', 'info');
}

async function closePositionDirect(ticket) {
    if (!confirm(`Close position #${ticket}?`)) return;

    try {
        const response = await fetch(`${API_BASE}/api/live/order/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket })
        });

        const data = await response.json();
        if (data.success) {
            showToast(`✅ Position #${ticket} closed!`, 'success');
            loadPositions(); // Refresh positions
        } else {
            showToast(`❌ Failed: ${data.message}`, 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

async function modifyPositionDirect(ticket, currentSL, currentTP) {
    const newSL = prompt('Enter new Stop Loss (leave empty to keep current):', currentSL);
    if (newSL === null) return; // User cancelled

    const newTP = prompt('Enter new Take Profit (leave empty to keep current):', currentTP);
    if (newTP === null) return; // User cancelled

    try {
        const slVal = newSL.trim() === '' ? null : parseFloat(newSL);
        const tpVal = newTP.trim() === '' ? null : parseFloat(newTP);

        const response = await fetch(`${API_BASE}/api/live/order/modify?ticket=${ticket}&sl=${slVal}&tp=${tpVal}`, {
            method: 'POST'
        });

        const data = await response.json();
        if (data.success) {
            showToast(`✅ Position #${ticket} modified!`, 'success');
            loadPositions(); // Refresh positions
        } else {
            showToast(`❌ Failed: ${data.message}`, 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// ===== Chat Helper Functions =====

function addChatMessage(container, role, content, isTyping = false) {
    const msgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message';
    msgDiv.id = msgId;

    const icon = role === 'user' ? 'fa-user' : 'fa-robot';
    const roleClass = role === 'user' ? 'user' : 'assistant';

    msgDiv.innerHTML = `
        <div class="chat-message-role ${roleClass}">
            <i class="fas ${icon}"></i> ${role === 'user' ? 'You' : 'AI Analyst'}
            ${isTyping ? '<span class="spinner"></span>' : ''}
        </div>
        <div class="chat-message-content">${escapeHtml(content)}</div>
    `;

    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;

    return msgId;
}

function removeChatMessage(container, msgId) {
    const msg = container.querySelector(`#${msgId}`);
    if (msg) msg.remove();
}

function formatTradeSetupInfo(setup) {
    const direction = setup.direction.toUpperCase();
    const badge = direction === 'BUY' ? '🟢 BUY' : '🔴 SELL';

    return `
        <h3>${badge} — ${setup.symbol}</h3>
        ${setup.reasoning ? `<p><span class="label">Reasoning:</span> <span class="value">${setup.reasoning}</span></p>` : ''}
        <p><span class="label">Entry:</span> <span class="value">${setup.entry_price}</span></p>
        <p><span class="label">Stop Loss:</span> <span class="value">${setup.stop_loss || 'N/A'}</span></p>
        <p><span class="label">Take Profit:</span> <span class="value">${setup.take_profit || 'N/A'}</span></p>
        <p><span class="label">Lot Size:</span> <span class="value">${setup.lot_size || 0.1}</span></p>
        ${setup.risk_reward ? `<p><span class="label">Risk/Reward:</span> <span class="value">${setup.risk_reward.toFixed(2)}</span></p>` : ''}
    `;
}

function formatTradeActionInfo(action) {
    const actionIcons = {
        'CLOSE_POSITION': '🚪',
        'MODIFY_SL': '🛡️',
        'MODIFY_TP': '🎯',
        'MODIFY_SLTP': '⚙️',
        'ADD_TO_POSITION': '📈'
    };

    const icon = actionIcons[action.action] || '📋';

    return `
        <h3>${icon} ${action.action.replace('_', ' ')}</h3>
        <p><span class="label">Ticket:</span> <span class="value">#${action.ticket}</span></p>
        ${action.reasoning ? `<p><span class="label">Reasoning:</span> <span class="value">${action.reasoning}</span></p>` : ''}
        ${action.new_sl ? `<p><span class="label">New SL:</span> <span class="value">${action.new_sl}</span></p>` : ''}
        ${action.new_tp ? `<p><span class="label">New TP:</span> <span class="value">${action.new_tp}</span></p>` : ''}
    `;
}

// ===== AUTOPILOT MODE FUNCTIONS =====
// (Reusing existing functions from original dashboard.js)

async function startAutopilot() {
    try {
        elements.startBtn.disabled = true;
        elements.startBtn.innerHTML = '<span class="spinner"></span> Starting...';

        const response = await fetch(`${API_BASE}/autopilot/start`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start');
        }

        const data = await response.json();
        showToast('Autopilot started successfully', 'success');
        await loadAutopilotStatus();

    } catch (error) {
        console.error('❌ Error starting autopilot:', error);
        showToast(`Failed to start: ${error.message}`, 'error');
        elements.startBtn.disabled = false;
        elements.startBtn.innerHTML = '<i class="fas fa-play"></i> Start Autopilot';
    }
}

async function stopAutopilot() {
    try {
        elements.stopBtn.disabled = true;
        elements.stopBtn.innerHTML = '<span class="spinner"></span> Stopping...';

        const response = await fetch(`${API_BASE}/autopilot/stop`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to stop');
        }

        const data = await response.json();
        showToast('Autopilot stopped', 'warning');
        await loadAutopilotStatus();

    } catch (error) {
        console.error('❌ Error stopping autopilot:', error);
        showToast(`Failed to stop: ${error.message}`, 'error');
        elements.stopBtn.disabled = false;
        elements.stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Autopilot';
    }
}

async function applyInterval() {
    const intervalSeconds = parseInt(elements.intervalSelect.value);

    try {
        elements.applyIntervalBtn.disabled = true;
        elements.applyIntervalBtn.innerHTML = '<span class="spinner"></span>';

        const response = await fetch(`${API_BASE}/autopilot/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interval_seconds: intervalSeconds })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update interval');
        }

        const data = await response.json();
        showToast(`Interval updated to ${intervalSeconds / 60} minutes`, 'success');
        await loadAutopilotStatus();

    } catch (error) {
        console.error('❌ Error updating interval:', error);
        showToast(`Failed to update: ${error.message}`, 'error');
    } finally {
        elements.applyIntervalBtn.disabled = false;
        elements.applyIntervalBtn.innerHTML = '<i class="fas fa-check"></i> Apply';
    }
}

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/autopilot/config`);

        if (!response.ok) {
            console.warn('⚠️ No configuration found');
            return;
        }

        const config = await response.json();

        elements.intervalSelect.value = config.interval_seconds;
        elements.currentInterval.textContent = `${config.interval_minutes} min`;

        if (config.ai_provider) {
            elements.providerSelect.value = config.ai_provider;
            await onProviderChange();

            if (config.model_name) {
                elements.modelSelect.value = config.model_name;
            }
        }

        if (config.mt5_url) {
            elements.mt5UrlInput.value = config.mt5_url;
        }

    } catch (error) {
        console.error('❌ Error loading config:', error);
    }
}

async function useDefaultKeys() {
    try {
        showToast('Loading default keys from server...', 'info');

        const response = await fetch(`${API_BASE}/api/config/default-keys`);
        const data = await response.json();

        if (data.success) {
            const keys = data.keys;

            // Auto-select the default provider
            elements.providerSelect.value = keys.default_provider;
            await onProviderChange();

            // Auto-select the default model
            if (keys.default_model) {
                elements.modelSelect.value = keys.default_model;
            }

            // Fill in the API key for the selected provider
            let apiKey = '';
            switch (keys.default_provider) {
                case 'NVIDIA':
                    apiKey = keys.nvidia_api_key;
                    break;
                case 'Gemini':
                    apiKey = keys.gemini_api_key;
                    break;
                case 'Groq':
                    apiKey = keys.groq_api_key;
                    break;
                case 'OpenRouter':
                case 'OpenRouter (Free)':
                    apiKey = keys.open_router_api_key;
                    break;
                case 'Bytez':
                    apiKey = keys.bytez_api_key;
                    break;
                case 'Cerebras':
                    apiKey = keys.cerebras_api_key;
                    break;
            }

            // Fill in the fields
            elements.apiKeyInput.value = apiKey;
            elements.mt5UrlInput.value = keys.mt5_url;
            elements.mt5TokenInput.value = keys.mt5_token;

            showToast('✅ Default keys loaded! Click "Save Configuration" to apply.', 'success');
        } else {
            showToast('Failed to load default keys', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

async function testAIConnection() {
    const provider = elements.providerSelect.value;
    if (!provider) {
        showToast('Please select an AI provider first', 'warning');
        return;
    }

    const btn = document.getElementById('testConnectionBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Testing...';

    try {
        // Get the providers endpoint
        const response = await fetch(`${API_BASE}/ai/providers`);
        const data = await response.json();

        if (data.providers && data.providers.includes(provider)) {
            showToast(`✅ ${provider} is available and configured`, 'success');
        } else {
            showToast(`❌ ${provider} not found or not configured`, 'error');
        }
    } catch (error) {
        showToast(`Connection test failed: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-plug-circle-check"></i> Test AI Connection';
    }
}

async function clearAIMemory() {
    try {
        const response = await fetch(`${API_BASE}/api/ai/chat/reset?conversation_id=history`, {
            method: 'POST'
        });

        if (response.ok) {
            // Clear frontend chat messages
            elements.historyChatMessages.innerHTML = '';
            elements.liveChatMessages.innerHTML = '';
            showToast('✅ AI memory cleared!', 'success');
        } else {
            showToast('Failed to clear memory', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

function clearWorkspace() {
    if (confirm('Clear all uploaded data and chat history?')) {
        // Clear datastore references
        currentHistoryDataId = null;

        // Clear UI
        elements.historyChatMessages.innerHTML = '';
        elements.liveChatMessages.innerHTML = '';
        elements.dataPreviewCard.style.display = 'none';
        elements.historyCodeOutput.style.display = 'none';
        elements.historyTradeSetup.style.display = 'none';
        elements.historyTradeAction.style.display = 'none';

        // Clear file input
        elements.fileInput.value = '';
        elements.uploadStatus.className = 'upload-status';
        elements.uploadStatus.textContent = '';

        showToast('✅ Workspace cleared!', 'success');
    }
}

async function downloadEAFiles() {
    try {
        // Create a download link for the EA files
        // Since we don't have a backend endpoint for this yet, we'll inform the user
        showToast('📦 EA files are located in the project root folder', 'info');

        // In a real implementation, you'd create a zip download endpoint
        // For now, direct the user to the files
        const confirmed = confirm('EA files (MA_Impulse_Logger.ex5 and .mq5) are in the project root. Open folder?');
        if (confirmed) {
            // This won't work in browser, but we can show the path
            showToast('Files location: d:\\date-wise\\06-04-2026\\impulse_analyst\\', 'info');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

async function saveConfig() {
    const provider = elements.providerSelect.value;
    const model = elements.modelSelect.value;
    const apiKey = elements.apiKeyInput.value;
    const mt5Url = elements.mt5UrlInput.value;
    const mt5Token = elements.mt5TokenInput.value;

    if (!provider) {
        showConfigStatus('Please select an AI provider', 'error');
        return;
    }

    if (!model) {
        showConfigStatus('Please select an AI model', 'error');
        return;
    }

    if (!apiKey) {
        showConfigStatus('Please enter your API key', 'error');
        return;
    }

    if (!mt5Url) {
        showConfigStatus('Please enter MT5 server URL', 'error');
        return;
    }

    if (!mt5Token) {
        showConfigStatus('Please enter MT5 token', 'error');
        return;
    }

    try {
        elements.saveConfigBtn.disabled = true;
        elements.saveConfigBtn.innerHTML = '<span class="spinner"></span> Saving...';

        const response = await fetch(`${API_BASE}/autopilot/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ai_provider: provider,
                model_name: model,
                api_key: apiKey,
                mt5_url: mt5Url,
                mt5_token: mt5Token
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save config');
        }

        const data = await response.json();
        showConfigStatus('Configuration saved successfully!', 'success');
        showToast('Configuration saved', 'success');

        elements.apiKeyInput.value = '';
        elements.mt5TokenInput.value = '';

    } catch (error) {
        console.error('❌ Error saving config:', error);
        showConfigStatus(`Error: ${error.message}`, 'error');
    } finally {
        elements.saveConfigBtn.disabled = false;
        elements.saveConfigBtn.innerHTML = '<i class="fas fa-save"></i> Save Configuration';
    }
}

function showConfigStatus(message, type) {
    elements.configStatus.textContent = message;
    elements.configStatus.className = `config-status ${type}`;
    setTimeout(() => {
        elements.configStatus.className = 'config-status';
    }, 5000);
}

async function onProviderChange() {
    const provider = elements.providerSelect.value;

    if (!provider) {
        elements.modelSelect.innerHTML = '<option value="">-- Select Provider First --</option>';
        elements.modelSelect.disabled = true;
        return;
    }

    try {
        elements.modelSelect.innerHTML = '<option value="">Loading models...</option>';
        elements.modelSelect.disabled = true;

        const response = await fetch(`${API_BASE}/ai/providers`);
        const providersData = await response.json();

        const models = providersData.details[provider]?.models || [];

        elements.modelSelect.innerHTML = '';

        if (models.length === 0) {
            elements.modelSelect.innerHTML = '<option value="">No models available</option>';
            return;
        }

        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            elements.modelSelect.appendChild(option);
        });

        elements.modelSelect.disabled = false;

    } catch (error) {
        console.error('❌ Error loading models:', error);
        elements.modelSelect.innerHTML = '<option value="">Error loading models</option>';
        showToast('Failed to load models', 'error');
    }
}

async function loadAutopilotStatus() {
    try {
        const response = await fetch(`${API_BASE}/autopilot/status`);

        if (!response.ok) {
            console.warn('⚠️ Failed to load status');
            return;
        }

        const status = await response.json();
        autopilotStatus = status;
        updateStatusUI(status);

    } catch (error) {
        console.error('❌ Error loading status:', error);
    }
}

function updateStatusUI(status) {
    if (status.enabled) {
        elements.autopilotStatus.innerHTML = '<span class="badge badge-active">ACTIVE</span>';
        elements.startBtn.disabled = true;
        elements.stopBtn.disabled = false;
    } else {
        elements.autopilotStatus.innerHTML = '<span class="badge badge-inactive">INACTIVE</span>';
        elements.startBtn.disabled = false;
        elements.stopBtn.disabled = true;
    }

    if (status.next_run) {
        nextRunTimestamp = status.next_run;
        const nextRunDate = new Date(status.next_run);
        elements.nextRun.textContent = nextRunDate.toLocaleTimeString();
        startCountdown(nextRunDate);
    } else {
        elements.nextRun.textContent = '--:--:--';
        elements.countdown.textContent = '--:--';
        stopCountdown();
    }

    const totalRunsCount = status.success_count + status.error_count;
    elements.totalRuns.textContent = totalRunsCount;
    elements.currentInterval.textContent = `${status.interval_minutes} min`;
    elements.intervalSelect.value = status.interval_seconds;

    elements.lastUpdate.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/autopilot/stats`);

        if (!response.ok) {
            console.warn('⚠️ Failed to load stats');
            return;
        }

        const stats = await response.json();
        updateStatsUI(stats);

    } catch (error) {
        console.error('❌ Error loading stats:', error);
    }
}

function updateStatsUI(stats) {
    elements.successCount.textContent = stats.success_count;
    elements.errorCount.textContent = stats.error_count;
    elements.successRate.textContent = `${stats.success_rate.toFixed(1)}%`;
    elements.totalTrades.textContent = stats.total_trades;
    elements.openPositions.textContent = stats.open_positions;

    const pnl = stats.total_pnl || 0;
    const pnlFormatted = pnl >= 0 ? `+$${pnl.toFixed(2)}` : `-$${Math.abs(pnl).toFixed(2)}`;
    elements.totalPnl.textContent = pnlFormatted;
    elements.totalPnl.className = `stat-value ${pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
}

// ===== WebSocket Connection =====
function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        console.log('⚠️ WebSocket already connected');
        return;
    }

    console.log('🔌 Connecting to WebSocket:', WS_URL);

    try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log('✅ WebSocket connected');
            wsConnected = true;
            wsReconnectDelay = 1000;
            updateConnectionStatus(true);

            ws.send('ping');
            setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send('ping');
                }
            }, 30000);
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleWebSocketMessage(message);
            } catch (error) {
                console.error('❌ Error parsing WebSocket message:', error);
            }
        };

        ws.onclose = () => {
            console.log('🔌 WebSocket disconnected');
            wsConnected = false;
            updateConnectionStatus(false);
            scheduleReconnect();
        };

        ws.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            ws.close();
        };
    } catch (error) {
        console.error('❌ Failed to create WebSocket:', error);
        scheduleReconnect();
    }
}

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'pong':
            break;
        case 'new_log':
            addLogToUI(message.data);
            break;
        case 'status_update':
            updateStatusFromMessage(message.data);
            break;
        default:
            console.log('📨 Unknown message type:', message.type);
    }
}

function scheduleReconnect() {
    if (wsReconnectTimer) return;

    console.log(`🔄 Reconnecting in ${wsReconnectDelay / 1000}s...`);

    wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null;
        wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
        connectWebSocket();
    }, wsReconnectDelay);
}

function updateConnectionStatus(connected) {
    if (connected) {
        elements.connectionStatus.classList.add('connected');
        elements.connectionStatus.querySelector('.status-text').textContent = 'Connected';
    } else {
        elements.connectionStatus.classList.remove('connected');
        elements.connectionStatus.querySelector('.status-text').textContent = 'Disconnected';
    }
}

function updateStatusFromMessage(data) {
    if (data.enabled !== undefined) {
        loadAutopilotStatus();
    }
}

// ===== Logs =====
async function loadLogs() {
    try {
        const levelFilter = elements.logLevelFilter.value;
        const url = levelFilter === 'ALL'
            ? `${API_BASE}/autopilot/logs?limit=50`
            : `${API_BASE}/autopilot/logs?limit=50&level=${levelFilter}`;

        const response = await fetch(url);

        if (!response.ok) {
            console.warn('⚠️ Failed to load logs');
            return;
        }

        const data = await response.json();

        elements.logContainer.innerHTML = '';

        if (data.logs.length === 0) {
            elements.logContainer.innerHTML = '<div class="text-muted text-center">No logs found</div>';
            return;
        }

        data.logs.reverse().forEach(log => {
            addLogToUI(log, false);
        });

        scrollToBottom();

    } catch (error) {
        console.error('❌ Error loading logs:', error);
    }
}

function addLogToUI(log, scroll = true) {
    const logElement = createLogElement(log);
    elements.logContainer.appendChild(logElement);

    while (elements.logContainer.children.length > MAX_LOGS_DISPLAY) {
        elements.logContainer.removeChild(elements.logContainer.firstChild);
    }

    if (scroll) {
        scrollToBottom();
    }
}

function createLogElement(log) {
    const div = document.createElement('div');
    const timestamp = new Date(log.timestamp);
    const timeStr = timestamp.toLocaleTimeString();
    const level = log.level.toLowerCase();

    div.className = `log-message log-${level}`;
    div.innerHTML = `
        <span class="log-time">${timeStr}</span>
        <span class="log-level">${log.level}</span>
        <span class="log-text">${escapeHtml(log.message)}</span>
    `;

    return div;
}

function clearLogs() {
    elements.logContainer.innerHTML = '<div class="text-muted text-center">Logs cleared</div>';
    showToast('Logs cleared', 'info');
}

// ===== Trades =====
async function loadTrades() {
    try {
        const response = await fetch(`${API_BASE}/trades?limit=50`);

        if (!response.ok) {
            console.warn('⚠️ Failed to load trades');
            return;
        }

        const data = await response.json();
        updateTradeTable(data.trades);

    } catch (error) {
        console.error('❌ Error loading trades:', error);
    }
}

function updateTradeTable(trades) {
    elements.tradeTableBody.innerHTML = '';

    if (trades.length === 0) {
        elements.tradeTableBody.innerHTML = `
            <tr class="empty-row">
                <td colspan="10" class="empty-message">No trades found</td>
            </tr>
        `;
        return;
    }

    trades.forEach(trade => {
        const row = createTradeRow(trade);
        elements.tradeTableBody.appendChild(row);
    });
}

function createTradeRow(trade) {
    const row = document.createElement('tr');
    const timestamp = new Date(trade.timestamp);
    const timeStr = timestamp.toLocaleString();

    const directionClass = trade.direction.toLowerCase() === 'buy' ? 'direction-buy' : 'direction-sell';
    const statusClass = `status-${trade.status.toLowerCase()}`;
    const pnlClass = trade.profit !== null ? (trade.profit >= 0 ? 'pnl-positive' : 'pnl-negative') : '';
    const pnlText = trade.profit !== null ? (trade.profit >= 0 ? `+$${trade.profit.toFixed(2)}` : `-$${Math.abs(trade.profit).toFixed(2)}`) : 'N/A';

    row.innerHTML = `
        <td>${trade.ticket}</td>
        <td>${trade.symbol}</td>
        <td class="${directionClass}">${trade.direction}</td>
        <td>${trade.entry_price}</td>
        <td>${trade.stop_loss || '-'}</td>
        <td>${trade.take_profit || '-'}</td>
        <td>${trade.lot_size}</td>
        <td><span class="${statusClass}">${trade.status.replace('_', ' ')}</span></td>
        <td class="${pnlClass}">${pnlText}</td>
        <td>${timeStr}</td>
    `;

    return row;
}

// ===== Countdown Timer =====
function startCountdown(targetDate) {
    stopCountdown();

    countdownInterval = setInterval(() => {
        const now = new Date();
        const target = new Date(targetDate);
        const diff = target - now;

        if (diff <= 0) {
            elements.countdown.textContent = 'Running...';
            return;
        }

        const minutes = Math.floor(diff / 60000);
        const seconds = Math.floor((diff % 60000) / 1000);

        elements.countdown.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }, 1000);
}

function stopCountdown() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
}

// ===== Utility Functions =====
function updateServerTime() {
    const now = new Date();
    elements.serverTime.textContent = now.toLocaleTimeString();
}

function toggleVisibility(input, button) {
    if (input.type === 'password') {
        input.type = 'text';
        button.querySelector('i').className = 'fas fa-eye-slash';
    } else {
        input.type = 'password';
        button.querySelector('i').className = 'fas fa-eye';
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        info: 'fas fa-info-circle',
        success: 'fas fa-check-circle',
        error: 'fas fa-times-circle',
        warning: 'fas fa-exclamation-triangle'
    };

    toast.innerHTML = `<i class="${icons[type] || icons.info}"></i> ${message}`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function scrollToBottom() {
    elements.logContainer.scrollTop = elements.logContainer.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function refreshAll() {
    elements.refreshBtn.disabled = true;
    elements.refreshBtn.innerHTML = '<span class="spinner"></span> Refreshing...';

    await Promise.all([
        loadAutopilotStatus(),
        loadConfig(),
        loadStats(),
        loadLogs(),
        loadTrades()
    ]);

    elements.refreshBtn.disabled = false;
    elements.refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
    showToast('Dashboard refreshed', 'success');
}