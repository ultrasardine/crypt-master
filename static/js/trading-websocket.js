/**
 * Trading WebSocket Client
 * 
 * Handles real-time updates for orders, fills, balances, and tickers from Pionex.
 * 
 * Requirements:
 * - 10.1: Show connection status indicator
 * - 10.2: Update orders table without page refresh
 * - 10.3: Update fills table without page refresh
 * - 10.4: Update portfolio display without page refresh
 * - 10.5: Handle reconnection attempts
 * - 9.3: Update ticker cards on ticker_update message with animations
 */

class TradingWebSocket {
    constructor(options = {}) {
        this.wsUrl = options.wsUrl || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/trading/`;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.ws = null;
        this.isConnected = false;
        this.isConnecting = false;
        this.isIntentionallyClosed = false;
        this.subscribedSymbols = new Set();
        this.pingInterval = null;
        
        // Callbacks
        this.onOrderUpdate = options.onOrderUpdate || null;
        this.onFillUpdate = options.onFillUpdate || null;
        this.onBalanceUpdate = options.onBalanceUpdate || null;
        this.onTickerUpdate = options.onTickerUpdate || null;
        this.onConnectionStatusChange = options.onConnectionStatusChange || null;
        
        // Auto-connect if specified
        if (options.autoConnect !== false) {
            this.connect();
        }
    }
    
    /**
     * Connect to the WebSocket server.
     * Requirements: 10.1, 10.5
     */
    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        
        this.isConnecting = true;
        this.isIntentionallyClosed = false;
        this._updateConnectionStatus('connecting', 'Connecting...');
        
        try {
            this.ws = new WebSocket(this.wsUrl);
            
            this.ws.onopen = () => {
                console.log('Trading WebSocket connected');
                this.isConnected = true;
                this.isConnecting = false;
                this.reconnectDelay = 1000;
                this.reconnectAttempts = 0;
                
                // Re-subscribe to previously subscribed symbols
                for (const symbol of this.subscribedSymbols) {
                    this._sendSubscribe(symbol);
                }
                
                // Start ping interval
                this._startPingInterval();
            };
            
            this.ws.onclose = (event) => {
                console.log('Trading WebSocket closed:', event.code, event.reason);
                this.isConnected = false;
                this.isConnecting = false;
                this._stopPingInterval();
                this._updateConnectionStatus('disconnected', 'Disconnected');
                
                // Attempt to reconnect if not intentionally closed
                if (!this.isIntentionallyClosed) {
                    this._scheduleReconnect();
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('Trading WebSocket error:', error);
                this._updateConnectionStatus('error', 'Connection Error');
            };
            
            this.ws.onmessage = (event) => {
                this._handleMessage(event.data);
            };
            
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.isConnecting = false;
            this._scheduleReconnect();
        }
    }
    
    /**
     * Disconnect from the WebSocket server.
     */
    disconnect() {
        this.isIntentionallyClosed = true;
        this._stopPingInterval();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
    }
    
    /**
     * Subscribe to updates for a specific symbol.
     * @param {string} symbol - Trading pair symbol (e.g., "BTC_USDT")
     */
    subscribe(symbol) {
        this.subscribedSymbols.add(symbol);
        if (this.isConnected) {
            this._sendSubscribe(symbol);
        }
    }
    
    /**
     * Unsubscribe from updates for a specific symbol.
     * @param {string} symbol - Trading pair symbol
     */
    unsubscribe(symbol) {
        this.subscribedSymbols.delete(symbol);
        if (this.isConnected) {
            this._send({ type: 'unsubscribe', symbol: symbol });
        }
    }
    
    /**
     * Get current connection status.
     */
    getStatus() {
        if (this.isConnected) {
            this._send({ type: 'get_status' });
        }
    }
    
    /**
     * Send a ping to keep the connection alive.
     */
    ping() {
        if (this.isConnected) {
            this._send({ type: 'ping' });
        }
    }
    
    // =========================================================================
    // Private Methods
    // =========================================================================
    
    _send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    _sendSubscribe(symbol) {
        this._send({ type: 'subscribe', symbol: symbol });
    }
    
    _handleMessage(data) {
        try {
            const message = JSON.parse(data);
            
            switch (message.type) {
                case 'connection_status':
                    this._updateConnectionStatus(
                        message.connected ? 'connected' : 'disconnected',
                        message.message
                    );
                    break;
                    
                case 'order_update':
                    if (this.onOrderUpdate) {
                        this.onOrderUpdate(message.data);
                    }
                    break;
                    
                case 'fill_update':
                    if (this.onFillUpdate) {
                        this.onFillUpdate(message.data);
                    }
                    break;
                    
                case 'balance_update':
                    if (this.onBalanceUpdate) {
                        this.onBalanceUpdate(message.data);
                    }
                    break;
                    
                case 'ticker_update':
                    if (this.onTickerUpdate) {
                        this.onTickerUpdate(message.data);
                    }
                    break;
                    
                case 'subscribed':
                    console.log('Subscribed to:', message.symbol);
                    break;
                    
                case 'unsubscribed':
                    console.log('Unsubscribed from:', message.symbol);
                    break;
                    
                case 'pong':
                    // Ping response received
                    break;
                    
                case 'error':
                    console.error('WebSocket error:', message.message);
                    break;
                    
                default:
                    console.log('Unknown message type:', message.type);
            }
            
        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
        }
    }
    
    /**
     * Update connection status indicator in UI.
     * Requirements: 10.1, 10.5
     * @param {string} status - Status: 'connecting', 'connected', 'disconnected', 'reconnecting', 'error', 'failed'
     * @param {string} message - Status message
     */
    _updateConnectionStatus(status, message) {
        if (this.onConnectionStatusChange) {
            this.onConnectionStatusChange(status === 'connected', message);
        }
        
        // Update status indicator if it exists
        const statusIndicator = document.getElementById('ws-connection-status');
        const statusText = document.getElementById('ws-connection-text');
        
        if (statusIndicator) {
            // Remove all status classes
            statusIndicator.className = 'h-2 w-2 rounded-full transition-colors';
            
            // Add appropriate status class with animation
            switch (status) {
                case 'connected':
                    statusIndicator.className = 'relative flex h-2 w-2';
                    statusIndicator.innerHTML = `
                        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                        <span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
                    `;
                    break;
                case 'connecting':
                case 'reconnecting':
                    statusIndicator.className = 'relative flex h-2 w-2';
                    statusIndicator.innerHTML = `
                        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"></span>
                        <span class="relative inline-flex h-2 w-2 rounded-full bg-amber-500"></span>
                    `;
                    break;
                case 'error':
                case 'failed':
                    statusIndicator.className = 'h-2 w-2 rounded-full bg-red-500';
                    statusIndicator.innerHTML = '';
                    break;
                default: // disconnected
                    statusIndicator.className = 'h-2 w-2 rounded-full bg-slate-500';
                    statusIndicator.innerHTML = '';
            }
            statusIndicator.title = message;
        }
        
        if (statusText) {
            statusText.textContent = message;
            statusText.className = 'text-xs transition-colors';
            
            switch (status) {
                case 'connected':
                    statusText.classList.add('text-emerald-400');
                    break;
                case 'connecting':
                case 'reconnecting':
                    statusText.classList.add('text-amber-400');
                    break;
                case 'error':
                case 'failed':
                    statusText.classList.add('text-red-400');
                    break;
                default:
                    statusText.classList.add('text-slate-500');
            }
        }
    }
    
    /**
     * Schedule reconnection with exponential backoff.
     * Requirements: 10.5
     */
    _scheduleReconnect() {
        if (this.isIntentionallyClosed || this.isConnecting) {
            return;
        }
        
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            this._updateConnectionStatus('failed', 'Connection Failed');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );
        
        console.log(`Reconnecting in ${delay / 1000}s (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        this._updateConnectionStatus('reconnecting', `Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    _startPingInterval() {
        this._stopPingInterval();
        this.pingInterval = setInterval(() => {
            this.ping();
        }, 30000);
    }
    
    _stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}


// =========================================================================
// Order Table Update Functions
// Requirements: 10.2
// =========================================================================

/**
 * Update an order row in the orders table.
 * @param {Object} order - Order data from WebSocket
 */
function updateOrderRow(order) {
    const row = document.getElementById(`order-row-${order.order_id}`);
    
    if (!row) {
        // Order not in current view, might need to add it
        console.log('Order not found in table:', order.order_id);
        return;
    }
    
    // Update filled size
    const filledCell = row.querySelector('td:nth-child(6)');
    if (filledCell) {
        const size = parseFloat(order.size);
        const filledSize = parseFloat(order.filled_size);
        const fillPercent = size > 0 ? ((filledSize / size) * 100).toFixed(1) : 0;
        filledCell.innerHTML = `
            ${order.filled_size}
            <span class="text-slate-500">(${fillPercent}%)</span>
        `;
    }
    
    // Update status
    const statusCell = row.querySelector('td:nth-child(7)');
    if (statusCell) {
        const statusClass = order.status === 'OPEN' 
            ? 'bg-sky-900/50 text-sky-400' 
            : 'bg-slate-600 text-slate-300';
        statusCell.innerHTML = `
            <span class="inline-flex items-center rounded-full ${statusClass} px-2.5 py-0.5 text-xs font-medium">
                ${order.status}
            </span>
        `;
    }
    
    // If order is closed, fade out and remove from open orders table
    if (order.status === 'CLOSED') {
        row.classList.add('opacity-50');
        setTimeout(() => {
            row.remove();
            // Update order count
            updateOrderCount(-1);
        }, 2000);
    }
    
    // Flash animation to indicate update
    row.classList.add('bg-indigo-900/30');
    setTimeout(() => {
        row.classList.remove('bg-indigo-900/30');
    }, 1000);
}

/**
 * Update the order count display.
 * @param {number} delta - Change in count (positive or negative)
 */
function updateOrderCount(delta) {
    const countEl = document.querySelector('.text-lg.font-semibold.text-slate-100');
    if (countEl) {
        const currentCount = parseInt(countEl.textContent) || 0;
        countEl.textContent = Math.max(0, currentCount + delta);
    }
}


// =========================================================================
// Fill Table Update Functions
// Requirements: 10.3
// =========================================================================

/**
 * Add a new fill row to the fills table.
 * @param {Object} fill - Fill data from WebSocket
 */
function addFillRow(fill) {
    const tbody = document.getElementById('fills-tbody');
    if (!tbody) return;
    
    const sideClass = fill.side === 'BUY' 
        ? 'bg-emerald-900/50 text-emerald-400' 
        : 'bg-red-900/50 text-red-400';
    const sideDotClass = fill.side === 'BUY' ? 'bg-emerald-400' : 'bg-red-400';
    const roleClass = fill.role === 'TAKER'
        ? 'bg-amber-900/50 text-amber-400'
        : 'bg-sky-900/50 text-sky-400';
    
    const row = document.createElement('tr');
    row.id = `fill-row-${fill.id}`;
    row.className = 'transition-colors hover:bg-slate-700/50 bg-emerald-900/20';
    row.innerHTML = `
        <td class="whitespace-nowrap px-4 py-4 text-sm font-medium text-slate-100">${fill.symbol}</td>
        <td class="whitespace-nowrap px-4 py-4 text-sm">
            <span class="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold ${sideClass}">
                <span class="h-1.5 w-1.5 rounded-full ${sideDotClass}"></span>
                ${fill.side}
            </span>
        </td>
        <td class="whitespace-nowrap px-4 py-4 text-sm">
            <span class="inline-flex items-center rounded-full ${roleClass} px-2.5 py-0.5 text-xs font-medium">
                ${fill.role}
            </span>
        </td>
        <td class="whitespace-nowrap px-4 py-4 text-right text-sm font-medium text-slate-100">${fill.price}</td>
        <td class="whitespace-nowrap px-4 py-4 text-right text-sm text-slate-300">${fill.size}</td>
        <td class="whitespace-nowrap px-4 py-4 text-right text-sm text-slate-400">${fill.fee} ${fill.fee_coin}</td>
        <td class="whitespace-nowrap px-4 py-4 text-sm text-slate-400">${formatTimestamp(fill.timestamp)}</td>
    `;
    
    // Insert at the top of the table
    tbody.insertBefore(row, tbody.firstChild);
    
    // Remove highlight after animation
    setTimeout(() => {
        row.classList.remove('bg-emerald-900/20');
    }, 2000);
    
    // Update fill count
    const countEl = document.querySelector('[data-fill-count]');
    if (countEl) {
        const currentCount = parseInt(countEl.textContent) || 0;
        countEl.textContent = currentCount + 1;
    }
}


// =========================================================================
// Balance Update Functions
// Requirements: 10.4
// =========================================================================

/**
 * Update balance display.
 * @param {Object} data - Balance update data from WebSocket
 */
function updateBalances(data) {
    const balances = data.balances || [];
    
    for (const balance of balances) {
        // Update balance elements if they exist
        const freeEl = document.querySelector(`[data-balance-free="${balance.currency}"]`);
        const lockedEl = document.querySelector(`[data-balance-locked="${balance.currency}"]`);
        const totalEl = document.querySelector(`[data-balance-total="${balance.currency}"]`);
        
        if (freeEl) {
            animateValueChange(freeEl, balance.free);
        }
        
        if (lockedEl) {
            animateValueChange(lockedEl, balance.locked);
        }
        
        if (totalEl) {
            animateValueChange(totalEl, balance.total);
        }
    }
}

/**
 * Animate a value change with a flash effect.
 * @param {HTMLElement} element - Element to update
 * @param {string} newValue - New value to display
 */
function animateValueChange(element, newValue) {
    const oldValue = element.textContent;
    if (oldValue === newValue) return;
    
    element.textContent = newValue;
    element.classList.add('text-emerald-400');
    setTimeout(() => element.classList.remove('text-emerald-400'), 1000);
}


// =========================================================================
// Ticker Update Functions
// Requirements: 9.3
// =========================================================================

/**
 * Update a ticker card with new data and animate price changes.
 * @param {Object} ticker - Ticker data from WebSocket
 */
function updateTickerCard(ticker) {
    // Find the ticker card by symbol
    const tickerCard = document.querySelector(`[data-ticker-symbol="${ticker.symbol}"]`);
    if (!tickerCard) {
        console.log('Ticker card not found:', ticker.symbol);
        return;
    }
    
    // Get previous price for comparison
    const priceEl = tickerCard.querySelector('[data-ticker-price]');
    const previousPrice = priceEl ? parseFloat(priceEl.dataset.tickerPrice || priceEl.textContent) : 0;
    const newPrice = parseFloat(ticker.close);
    
    // Determine price direction for animation
    const priceDirection = newPrice > previousPrice ? 'up' : newPrice < previousPrice ? 'down' : 'none';
    
    // Update price with animation
    if (priceEl) {
        priceEl.textContent = ticker.close;
        priceEl.dataset.tickerPrice = ticker.close;
        
        // Apply flash animation based on direction
        if (priceDirection === 'up') {
            flashElement(priceEl, 'bg-emerald-900/50');
        } else if (priceDirection === 'down') {
            flashElement(priceEl, 'bg-red-900/50');
        }
        
        // Update price color based on change percent
        priceEl.classList.remove('text-emerald-400', 'text-red-400');
        if (ticker.change_percent >= 0) {
            priceEl.classList.add('text-emerald-400');
        } else {
            priceEl.classList.add('text-red-400');
        }
    }
    
    // Update change percent badge
    const changeEl = tickerCard.querySelector('[data-ticker-change]');
    if (changeEl) {
        const changePercent = parseFloat(ticker.change_percent);
        const isPositive = changePercent >= 0;
        const formattedChange = isPositive ? `+${changePercent.toFixed(2)}%` : `${changePercent.toFixed(2)}%`;
        
        changeEl.innerHTML = `
            <svg class="mr-1 h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="${isPositive ? 'M4.5 15.75l7.5-7.5 7.5 7.5' : 'M19.5 8.25l-7.5 7.5-7.5-7.5'}" />
            </svg>
            ${formattedChange}
        `;
        
        changeEl.className = `inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            isPositive ? 'bg-emerald-900/50 text-emerald-400' : 'bg-red-900/50 text-red-400'
        }`;
    }
    
    // Update high/low/volume/count
    const highEl = tickerCard.querySelector('[data-ticker-high]');
    if (highEl) highEl.textContent = ticker.high;
    
    const lowEl = tickerCard.querySelector('[data-ticker-low]');
    if (lowEl) lowEl.textContent = ticker.low;
    
    const volumeEl = tickerCard.querySelector('[data-ticker-volume]');
    if (volumeEl) volumeEl.textContent = ticker.volume;
    
    const countEl = tickerCard.querySelector('[data-ticker-count]');
    if (countEl) countEl.textContent = ticker.count || 'N/A';
    
    // Flash the entire card to indicate update
    flashElement(tickerCard, 'border-indigo-500');
}

/**
 * Update book ticker display.
 * @param {Object} bookTicker - Book ticker data from WebSocket
 */
function updateBookTicker(bookTicker) {
    // Find the book ticker section by symbol
    const tickerCard = document.querySelector(`[data-ticker-symbol="${bookTicker.symbol}"]`);
    if (!tickerCard) return;
    
    const bidEl = tickerCard.querySelector('[data-book-bid]');
    if (bidEl) {
        animateValueChange(bidEl, bookTicker.bid_price);
    }
    
    const askEl = tickerCard.querySelector('[data-book-ask]');
    if (askEl) {
        animateValueChange(askEl, bookTicker.ask_price);
    }
    
    const spreadEl = tickerCard.querySelector('[data-book-spread]');
    if (spreadEl) {
        spreadEl.textContent = bookTicker.spread;
    }
    
    // Also update book ticker table if it exists
    const tableRow = document.querySelector(`tr[data-book-ticker-symbol="${bookTicker.symbol}"]`);
    if (tableRow) {
        const cells = tableRow.querySelectorAll('td');
        if (cells.length >= 6) {
            animateValueChange(cells[1], bookTicker.bid_price);
            cells[2].textContent = bookTicker.bid_size;
            animateValueChange(cells[3], bookTicker.ask_price);
            cells[4].textContent = bookTicker.ask_size;
            cells[5].textContent = bookTicker.spread;
        }
    }
}


/**
 * Flash an element with a temporary class for visual feedback.
 * @param {HTMLElement} element - Element to flash
 * @param {string} flashClass - CSS class to apply temporarily
 */
function flashElement(element, flashClass) {
    element.classList.add(flashClass);
    setTimeout(() => {
        element.classList.remove(flashClass);
    }, 500);
}


// =========================================================================
// Utility Functions
// =========================================================================

/**
 * Format a timestamp for display.
 * @param {string} timestamp - ISO timestamp string
 * @returns {string} Formatted timestamp
 */
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/**
 * Format a number with appropriate decimal places.
 * @param {number|string} value - Value to format
 * @param {number} decimals - Number of decimal places
 * @returns {string} Formatted number
 */
function formatNumber(value, decimals = 2) {
    const num = parseFloat(value);
    if (isNaN(num)) return value;
    return num.toFixed(decimals);
}


// =========================================================================
// Auto-initialize on page load
// =========================================================================

let tradingWs = null;

document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on a trading page
    const tradingPage = document.querySelector('[data-trading-ws]');
    if (!tradingPage) return;
    
    // Get symbols to subscribe to from data attribute
    const symbols = tradingPage.dataset.tradingWs 
        ? tradingPage.dataset.tradingWs.split(',').filter(s => s.trim())
        : [];
    
    tradingWs = new TradingWebSocket({
        onOrderUpdate: updateOrderRow,
        onFillUpdate: addFillRow,
        onBalanceUpdate: updateBalances,
        onTickerUpdate: function(data) {
            // Handle both 24hr ticker and book ticker updates
            if (data.type === 'book_ticker') {
                updateBookTicker(data);
            } else {
                updateTickerCard(data);
            }
        },
        onConnectionStatusChange: (connected, message) => {
            console.log('Connection status:', connected, message);
        },
    });
    
    // Subscribe to specified symbols
    for (const symbol of symbols) {
        tradingWs.subscribe(symbol.trim());
    }
});

// Export for use in other scripts
window.TradingWebSocket = TradingWebSocket;
window.tradingWs = tradingWs;
window.updateOrderRow = updateOrderRow;
window.addFillRow = addFillRow;
window.updateBalances = updateBalances;
window.updateTickerCard = updateTickerCard;
window.updateBookTicker = updateBookTicker;
