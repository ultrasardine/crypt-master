/**
 * Dashboard WebSocket Client
 * 
 * Handles real-time updates for the dashboard via WebSocket connection.
 * Implements automatic reconnection with exponential backoff.
 * 
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
 */

class DashboardWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.pingInterval = null;
        this.isConnecting = false;
        this.isIntentionallyClosed = false;
        
        // Bind methods
        this.connect = this.connect.bind(this);
        this.handleOpen = this.handleOpen.bind(this);
        this.handleMessage = this.handleMessage.bind(this);
        this.handleError = this.handleError.bind(this);
        this.handleClose = this.handleClose.bind(this);
        this.reconnect = this.reconnect.bind(this);
        this.sendPing = this.sendPing.bind(this);
    }
    
    /**
     * Connect to WebSocket server
     */
    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        
        this.isConnecting = true;
        this.isIntentionallyClosed = false;
        
        // Determine WebSocket protocol (ws:// or wss://)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/dashboard/`;
        
        console.log('[WebSocket] Connecting to:', wsUrl);
        
        try {
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = this.handleOpen;
            this.ws.onmessage = this.handleMessage;
            this.ws.onerror = this.handleError;
            this.ws.onclose = this.handleClose;
        } catch (error) {
            console.error('[WebSocket] Connection error:', error);
            this.isConnecting = false;
            this.reconnect();
        }
    }
    
    /**
     * Handle WebSocket connection opened
     */
    handleOpen(event) {
        console.log('[WebSocket] Connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        
        // Update connection status indicator
        this.updateConnectionStatus('connected');
        
        // Start ping interval to keep connection alive
        this.startPingInterval();
    }
    
    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            const messageType = data.type;
            
            console.log('[WebSocket] Received:', messageType, data);
            
            // Update last updated timestamp
            this.updateLastUpdatedTime();
            
            // Route message to appropriate handler
            switch (messageType) {
                case 'portfolio_update':
                    this.handlePortfolioUpdate(data);
                    break;
                case 'bot_update':
                    this.handleBotUpdate(data);
                    break;
                case 'bot_created':
                    this.handleBotCreated(data);
                    break;
                case 'bot_stopped':
                    this.handleBotStopped(data);
                    break;
                case 'bot_performance':
                    this.handleBotPerformance(data);
                    break;
                case 'signal_update':
                    this.handleSignalUpdate(data);
                    break;
                case 'sentiment_update':
                    this.handleSentimentUpdate(data);
                    break;
                case 'alert':
                    this.handleAlert(data);
                    break;
                case 'trade_executed':
                    this.handleTradeExecuted(data);
                    break;
                case 'pong':
                    // Ping response received
                    break;
                case 'error':
                    console.error('[WebSocket] Server error:', data.message);
                    break;
                default:
                    console.warn('[WebSocket] Unknown message type:', messageType);
            }
        } catch (error) {
            console.error('[WebSocket] Error parsing message:', error);
        }
    }
    
    /**
     * Handle WebSocket error
     */
    handleError(event) {
        console.error('[WebSocket] Error:', event);
        this.updateConnectionStatus('error');
    }
    
    /**
     * Handle WebSocket connection closed
     */
    handleClose(event) {
        console.log('[WebSocket] Closed:', event.code, event.reason);
        this.isConnecting = false;
        
        // Stop ping interval
        this.stopPingInterval();
        
        // Update connection status
        this.updateConnectionStatus('disconnected');
        
        // Attempt reconnection if not intentionally closed
        if (!this.isIntentionallyClosed) {
            this.reconnect();
        }
    }
    
    /**
     * Reconnect with exponential backoff
     */
    reconnect() {
        if (this.isIntentionallyClosed || this.isConnecting) {
            return;
        }
        
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WebSocket] Max reconnection attempts reached');
            this.updateConnectionStatus('failed');
            return;
        }
        
        this.reconnectAttempts++;
        
        // Calculate delay with exponential backoff
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );
        
        console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        this.updateConnectionStatus('reconnecting');
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    /**
     * Close WebSocket connection
     */
    close() {
        this.isIntentionallyClosed = true;
        this.stopPingInterval();
        
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
    
    /**
     * Start ping interval to keep connection alive
     */
    startPingInterval() {
        this.stopPingInterval();
        this.pingInterval = setInterval(this.sendPing, 30000); // Ping every 30 seconds
    }
    
    /**
     * Stop ping interval
     */
    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
    
    /**
     * Send ping message to server
     */
    sendPing() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
        }
    }
    
    /**
     * Update connection status indicator in UI
     */
    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connection-status');
        if (!statusElement) return;
        
        const statusConfig = {
            connected: {
                html: `
                    <span class="relative flex h-3 w-3">
                        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                        <span class="relative inline-flex h-3 w-3 rounded-full bg-emerald-500"></span>
                    </span>
                    <span class="text-sm font-medium text-slate-300">Connected</span>
                `
            },
            disconnected: {
                html: `
                    <span class="relative flex h-3 w-3">
                        <span class="relative inline-flex h-3 w-3 rounded-full bg-slate-500"></span>
                    </span>
                    <span class="text-sm font-medium text-slate-400">Disconnected</span>
                `
            },
            reconnecting: {
                html: `
                    <span class="relative flex h-3 w-3">
                        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"></span>
                        <span class="relative inline-flex h-3 w-3 rounded-full bg-amber-500"></span>
                    </span>
                    <span class="text-sm font-medium text-amber-400">Reconnecting...</span>
                `
            },
            error: {
                html: `
                    <span class="relative flex h-3 w-3">
                        <span class="relative inline-flex h-3 w-3 rounded-full bg-red-500"></span>
                    </span>
                    <span class="text-sm font-medium text-red-400">Connection Error</span>
                `
            },
            failed: {
                html: `
                    <span class="relative flex h-3 w-3">
                        <span class="relative inline-flex h-3 w-3 rounded-full bg-red-500"></span>
                    </span>
                    <span class="text-sm font-medium text-red-400">Connection Failed</span>
                `
            }
        };
        
        const config = statusConfig[status] || statusConfig.disconnected;
        statusElement.innerHTML = config.html;
    }
    
    /**
     * Update last updated timestamp in UI
     */
    updateLastUpdatedTime() {
        const lastUpdatedElement = document.getElementById('last-updated');
        if (!lastUpdatedElement) return;
        
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        
        lastUpdatedElement.innerHTML = `Last updated: <span class="font-medium text-slate-300">${timeString}</span>`;
    }
    
    /**
     * Handle portfolio update message
     * Requirements: 6.1
     */
    handlePortfolioUpdate(data) {
        // Update portfolio values in DOM
        this.updateElement('.portfolio-total-value', `$${parseFloat(data.total_value).toFixed(2)}`);
        this.updateElement('.portfolio-available-balance', `$${parseFloat(data.available_balance).toFixed(2)}`);
        this.updateElement('.portfolio-allocated-to-bots', `$${parseFloat(data.allocated_to_bots).toFixed(2)}`);
        this.updateElement('.portfolio-high-water-mark', `$${parseFloat(data.high_water_mark).toFixed(2)}`);
        
        // Update drawdown with color coding
        const drawdown = parseFloat(data.drawdown);
        const drawdownElement = document.querySelector('.portfolio-drawdown');
        if (drawdownElement) {
            drawdownElement.textContent = `${drawdown.toFixed(2)}%`;
            
            // Update color based on drawdown level
            drawdownElement.classList.remove('text-emerald-400', 'text-amber-400', 'text-red-400');
            if (drawdown > 10) {
                drawdownElement.classList.add('text-red-400');
            } else if (drawdown > 5) {
                drawdownElement.classList.add('text-amber-400');
            } else {
                drawdownElement.classList.add('text-emerald-400');
            }
        }
        
        // Trigger chart update if charts are initialized
        if (window.dashboardCharts && window.dashboardCharts.updatePortfolioChart) {
            window.dashboardCharts.updatePortfolioChart(data);
        }
    }
    
    /**
     * Handle bot update message
     * Requirements: 6.2
     */
    handleBotUpdate(data) {
        // Find bot row in table
        const botRow = document.querySelector(`tr[data-bot-id="${data.bot_id}"]`);
        if (!botRow) {
            // Bot not in current view, could add it dynamically
            console.log('[WebSocket] Bot not found in table:', data.bot_id);
            return;
        }
        
        // Update bot P&L
        const pnlCell = botRow.querySelector('.bot-pnl');
        if (pnlCell) {
            const pnl = parseFloat(data.pnl);
            pnlCell.textContent = `$${pnl.toFixed(2)}`;
            pnlCell.classList.remove('text-emerald-400', 'text-red-400');
            pnlCell.classList.add(pnl >= 0 ? 'text-emerald-400' : 'text-red-400');
        }
        
        // Update bot status
        const statusCell = botRow.querySelector('.bot-status');
        if (statusCell) {
            const statusBadge = statusCell.querySelector('span');
            if (statusBadge) {
                statusBadge.textContent = data.status;
                
                // Update badge color
                statusBadge.classList.remove('bg-emerald-900/50', 'text-emerald-400', 'bg-slate-600', 'text-slate-300', 'bg-red-900/50', 'text-red-400', 'bg-amber-900/50', 'text-amber-400');
                if (data.status === 'ACTIVE') {
                    statusBadge.classList.add('bg-emerald-900/50', 'text-emerald-400');
                } else if (data.status === 'STOPPED') {
                    statusBadge.classList.add('bg-slate-600', 'text-slate-300');
                } else if (data.status === 'ERROR') {
                    statusBadge.classList.add('bg-red-900/50', 'text-red-400');
                } else {
                    statusBadge.classList.add('bg-amber-900/50', 'text-amber-400');
                }
            }
        }
        
        // Trigger chart update if charts are initialized
        if (window.dashboardCharts && window.dashboardCharts.updateBotPerformance) {
            window.dashboardCharts.updateBotPerformance(data);
        }
    }
    
    /**
     * Handle bot created message
     * Requirements: 6.2
     */
    handleBotCreated(data) {
        console.log('[WebSocket] Bot created:', data);
        
        // Show notification
        this.showNotification('success', 'Bot Created', `${data.bot_type} bot created for ${data.symbol}`);
        
        // Could dynamically add bot to table here
        // For now, user can refresh to see new bot
    }
    
    /**
     * Handle bot stopped message
     * Requirements: 6.2
     */
    handleBotStopped(data) {
        console.log('[WebSocket] Bot stopped:', data);
        
        // Show notification
        const pnlText = data.final_pnl ? ` (P&L: $${parseFloat(data.final_pnl).toFixed(2)})` : '';
        this.showNotification('info', 'Bot Stopped', `${data.symbol} bot stopped${pnlText}`);
        
        // Update bot status in table
        this.handleBotUpdate({
            bot_id: data.bot_id,
            status: 'STOPPED',
            symbol: data.symbol,
            pnl: data.final_pnl || '0'
        });
    }
    
    /**
     * Handle bot performance message
     * Requirements: 6.2
     */
    handleBotPerformance(data) {
        // Update bot in table
        this.handleBotUpdate(data);
        
        // Show warning if underperforming
        if (data.is_underperforming) {
            this.showNotification('warning', 'Bot Underperforming', `${data.symbol} bot is underperforming`);
        }
    }
    
    /**
     * Handle signal update message
     * Requirements: 6.3
     */
    handleSignalUpdate(data) {
        console.log('[WebSocket] Signal update:', data);
        
        // Find signals table
        const signalsTable = document.querySelector('.signals-table tbody');
        if (!signalsTable) return;
        
        // Could add new signal row dynamically
        // For now, just show notification for high confidence signals
        if (data.meets_threshold && data.confidence >= 85) {
            this.showNotification(
                'info',
                'High Confidence Signal',
                `${data.direction} signal for ${data.symbol} (${data.confidence.toFixed(1)}%)`
            );
        }
    }
    
    /**
     * Handle sentiment update message
     * Requirements: 6.4
     */
    handleSentimentUpdate(data) {
        console.log('[WebSocket] Sentiment update:', data);
        
        // Update Fear & Greed Index
        const fgiValue = document.querySelector('.fear-greed-index-value');
        if (fgiValue) {
            fgiValue.textContent = data.fear_greed_index;
        }
        
        const fgiClassification = document.querySelector('.fear-greed-classification');
        if (fgiClassification) {
            fgiClassification.textContent = data.classification;
            
            // Update badge color
            fgiClassification.classList.remove('bg-red-900/50', 'text-red-400', 'bg-amber-900/50', 'text-amber-400', 'bg-slate-600', 'text-slate-300', 'bg-sky-900/50', 'text-sky-400', 'bg-emerald-900/50', 'text-emerald-400');
            
            if (data.classification === 'Extreme Greed') {
                fgiClassification.classList.add('bg-red-900/50', 'text-red-400');
            } else if (data.classification === 'Greed') {
                fgiClassification.classList.add('bg-amber-900/50', 'text-amber-400');
            } else if (data.classification === 'Neutral') {
                fgiClassification.classList.add('bg-slate-600', 'text-slate-300');
            } else if (data.classification === 'Fear') {
                fgiClassification.classList.add('bg-sky-900/50', 'text-sky-400');
            } else {
                fgiClassification.classList.add('bg-emerald-900/50', 'text-emerald-400');
            }
        }
    }
    
    /**
     * Handle alert message
     * Requirements: 6.5
     */
    handleAlert(data) {
        const levelMap = {
            'info': 'info',
            'warning': 'warning',
            'error': 'error',
            'critical': 'error'
        };
        
        this.showNotification(levelMap[data.level] || 'info', data.title, data.message);
    }
    
    /**
     * Handle trade executed message
     */
    handleTradeExecuted(data) {
        console.log('[WebSocket] Trade executed:', data);
        
        this.showNotification(
            'success',
            'Trade Executed',
            `${data.side} ${data.quantity} ${data.symbol} @ $${parseFloat(data.price).toFixed(2)}`
        );
    }
    
    /**
     * Update element text content
     */
    updateElement(selector, value) {
        const element = document.querySelector(selector);
        if (element) {
            element.textContent = value;
        }
    }
    
    /**
     * Show notification toast
     */
    showNotification(type, title, message) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed bottom-4 right-4 z-50 max-w-sm rounded-lg border p-4 shadow-lg transition-all duration-300 ${
            type === 'success' ? 'border-emerald-500 bg-emerald-900/90 text-emerald-100' :
            type === 'error' ? 'border-red-500 bg-red-900/90 text-red-100' :
            type === 'warning' ? 'border-amber-500 bg-amber-900/90 text-amber-100' :
            'border-sky-500 bg-sky-900/90 text-sky-100'
        }`;
        
        notification.innerHTML = `
            <div class="flex items-start gap-3">
                <div class="flex-1">
                    <p class="font-semibold">${title}</p>
                    <p class="mt-1 text-sm opacity-90">${message}</p>
                </div>
                <button onclick="this.parentElement.parentElement.remove()" class="text-current opacity-70 hover:opacity-100">
                    <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
}

// Initialize WebSocket when DOM is ready
let dashboardWS = null;

document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on dashboard page
    if (document.getElementById('connection-status')) {
        dashboardWS = new DashboardWebSocket();
        dashboardWS.connect();
        
        // Clean up on page unload
        window.addEventListener('beforeunload', () => {
            if (dashboardWS) {
                dashboardWS.close();
            }
        });
    }
});

// Export for use in other scripts
window.dashboardWS = dashboardWS;
