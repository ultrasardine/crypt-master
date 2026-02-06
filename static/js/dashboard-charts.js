/**
 * Dashboard Charts
 * 
 * Implements portfolio value, drawdown, and bot performance charts
 * using Chart.js library with Tailwind color palette.
 * 
 * Requirements: 5.1, 5.2, 5.3, 5.5, 5.6
 */

class DashboardCharts {
    constructor() {
        this.portfolioChart = null;
        this.drawdownChart = null;
        this.botPerformanceChart = null;
        this.currentPeriod = '24h';
        
        // Tailwind color palette
        this.colors = {
            emerald: {
                400: 'rgb(52, 211, 153)',
                500: 'rgb(16, 185, 129)',
                600: 'rgb(5, 150, 105)',
            },
            red: {
                400: 'rgb(248, 113, 113)',
                500: 'rgb(239, 68, 68)',
                600: 'rgb(220, 38, 38)',
            },
            indigo: {
                400: 'rgb(129, 140, 248)',
                500: 'rgb(99, 102, 241)',
                600: 'rgb(79, 70, 229)',
            },
            slate: {
                300: 'rgb(203, 213, 225)',
                400: 'rgb(148, 163, 184)',
                500: 'rgb(100, 116, 139)',
                600: 'rgb(71, 85, 105)',
                700: 'rgb(51, 65, 85)',
            },
            amber: {
                400: 'rgb(251, 191, 36)',
                500: 'rgb(245, 158, 11)',
            },
        };
        
        // Chart.js default configuration
        this.defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: this.colors.slate[300],
                        font: {
                            family: 'system-ui, -apple-system, sans-serif',
                            size: 12,
                        },
                    },
                },
                tooltip: {
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
                    titleColor: this.colors.slate[100],
                    bodyColor: this.colors.slate[300],
                    borderColor: this.colors.slate[700],
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {},
                },
            },
            scales: {
                x: {
                    grid: {
                        color: this.colors.slate[700],
                        drawBorder: false,
                    },
                    ticks: {
                        color: this.colors.slate[400],
                        font: {
                            size: 11,
                        },
                    },
                },
                y: {
                    grid: {
                        color: this.colors.slate[700],
                        drawBorder: false,
                    },
                    ticks: {
                        color: this.colors.slate[400],
                        font: {
                            size: 11,
                        },
                    },
                },
            },
        };
    }
    
    /**
     * Initialize all charts
     * Requirements: 5.1, 5.2, 5.3
     */
    init() {
        this.initPortfolioChart();
        this.initDrawdownChart();
        this.initBotPerformanceChart();
        this.setupPeriodButtons();
    }
    
    /**
     * Initialize portfolio value chart
     * Requirements: 5.1
     */
    initPortfolioChart() {
        const canvas = document.getElementById('portfolio-value-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // Get initial data from context
        const chartData = window.portfolioChartData || [];
        
        this.portfolioChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.map(d => this.formatTimestamp(d.timestamp)),
                datasets: [{
                    label: 'Portfolio Value',
                    data: chartData.map(d => d.total_value),
                    borderColor: this.colors.indigo[500],
                    backgroundColor: this.createGradient(ctx, this.colors.indigo[500], 0.1),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: this.colors.indigo[400],
                    pointHoverBorderColor: '#fff',
                    pointHoverBorderWidth: 2,
                }],
            },
            options: {
                ...this.defaultOptions,
                plugins: {
                    ...this.defaultOptions.plugins,
                    tooltip: {
                        ...this.defaultOptions.plugins.tooltip,
                        callbacks: {
                            label: (context) => {
                                return `Value: $${context.parsed.y.toFixed(2)}`;
                            },
                        },
                    },
                },
                scales: {
                    ...this.defaultOptions.scales,
                    y: {
                        ...this.defaultOptions.scales.y,
                        ticks: {
                            ...this.defaultOptions.scales.y.ticks,
                            callback: (value) => `$${value.toFixed(0)}`,
                        },
                    },
                },
            },
        });
    }
    
    /**
     * Initialize drawdown chart
     * Requirements: 5.2
     */
    initDrawdownChart() {
        const canvas = document.getElementById('drawdown-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // Get initial data from context
        const chartData = window.portfolioChartData || [];
        
        this.drawdownChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.map(d => this.formatTimestamp(d.timestamp)),
                datasets: [{
                    label: 'Drawdown',
                    data: chartData.map(d => d.drawdown),
                    borderColor: this.colors.red[500],
                    backgroundColor: this.createGradient(ctx, this.colors.red[500], 0.1),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: this.colors.red[400],
                    pointHoverBorderColor: '#fff',
                    pointHoverBorderWidth: 2,
                }],
            },
            options: {
                ...this.defaultOptions,
                plugins: {
                    ...this.defaultOptions.plugins,
                    tooltip: {
                        ...this.defaultOptions.plugins.tooltip,
                        callbacks: {
                            label: (context) => {
                                return `Drawdown: ${context.parsed.y.toFixed(2)}%`;
                            },
                        },
                    },
                },
                scales: {
                    ...this.defaultOptions.scales,
                    y: {
                        ...this.defaultOptions.scales.y,
                        reverse: true,
                        ticks: {
                            ...this.defaultOptions.scales.y.ticks,
                            callback: (value) => `${value.toFixed(0)}%`,
                        },
                    },
                },
            },
        });
    }
    
    /**
     * Initialize bot performance chart
     * Requirements: 5.3
     */
    initBotPerformanceChart() {
        const canvas = document.getElementById('bot-performance-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // Get initial data from context
        const botData = window.botPerformanceData || [];
        
        // Group bots by status and create datasets
        const activeBots = botData.filter(b => b.status === 'ACTIVE');
        const stoppedBots = botData.filter(b => b.status === 'STOPPED');
        
        const datasets = [];
        
        // Add active bots
        activeBots.forEach((bot, index) => {
            const color = bot.pnl_percent >= 0 ? this.colors.emerald[500] : this.colors.red[500];
            datasets.push({
                label: `${bot.trading_pair} (${bot.bot_type})`,
                data: [{
                    x: new Date(bot.created_at).getTime(),
                    y: 0,
                }, {
                    x: Date.now(),
                    y: bot.pnl_percent,
                }],
                borderColor: color,
                backgroundColor: color,
                borderWidth: 2,
                fill: false,
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 5,
            });
        });
        
        this.botPerformanceChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: datasets,
            },
            options: {
                ...this.defaultOptions,
                plugins: {
                    ...this.defaultOptions.plugins,
                    legend: {
                        ...this.defaultOptions.plugins.legend,
                        display: datasets.length <= 10, // Hide legend if too many bots
                    },
                    tooltip: {
                        ...this.defaultOptions.plugins.tooltip,
                        callbacks: {
                            label: (context) => {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                return `${label}: ${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'hour',
                            displayFormats: {
                                hour: 'MMM d, HH:mm',
                            },
                        },
                        grid: {
                            color: this.colors.slate[700],
                            drawBorder: false,
                        },
                        ticks: {
                            color: this.colors.slate[400],
                            font: {
                                size: 11,
                            },
                        },
                    },
                    y: {
                        ...this.defaultOptions.scales.y,
                        ticks: {
                            ...this.defaultOptions.scales.y.ticks,
                            callback: (value) => `${value >= 0 ? '+' : ''}${value.toFixed(0)}%`,
                        },
                    },
                },
            },
        });
    }
    
    /**
     * Setup period selection buttons
     */
    setupPeriodButtons() {
        const buttons = document.querySelectorAll('.chart-period-btn');
        buttons.forEach(button => {
            button.addEventListener('click', (e) => {
                const period = e.target.dataset.period;
                this.changePeriod(period);
                
                // Update button styles
                buttons.forEach(btn => {
                    btn.classList.remove('bg-indigo-600');
                    btn.classList.add('bg-slate-700');
                });
                e.target.classList.remove('bg-slate-700');
                e.target.classList.add('bg-indigo-600');
            });
        });
    }
    
    /**
     * Change chart period
     */
    changePeriod(period) {
        this.currentPeriod = period;
        
        // In a real implementation, this would fetch new data from the server
        // For now, we'll just filter the existing data
        console.log(`[Charts] Changing period to ${period}`);
        
        // Could trigger a data refresh here
        // this.refreshCharts();
    }
    
    /**
     * Update portfolio chart with new data
     * Requirements: 5.5
     */
    updatePortfolioChart(data) {
        if (!this.portfolioChart) return;
        
        const timestamp = new Date(data.timestamp);
        const value = parseFloat(data.total_value);
        const drawdown = parseFloat(data.drawdown);
        
        // Add new data point to portfolio chart
        this.portfolioChart.data.labels.push(this.formatTimestamp(timestamp));
        this.portfolioChart.data.datasets[0].data.push(value);
        
        // Keep only last N points based on period
        const maxPoints = this.getMaxPointsForPeriod();
        if (this.portfolioChart.data.labels.length > maxPoints) {
            this.portfolioChart.data.labels.shift();
            this.portfolioChart.data.datasets[0].data.shift();
        }
        
        this.portfolioChart.update('none'); // Update without animation for real-time feel
        
        // Update drawdown chart
        if (this.drawdownChart) {
            this.drawdownChart.data.labels.push(this.formatTimestamp(timestamp));
            this.drawdownChart.data.datasets[0].data.push(drawdown);
            
            if (this.drawdownChart.data.labels.length > maxPoints) {
                this.drawdownChart.data.labels.shift();
                this.drawdownChart.data.datasets[0].data.shift();
            }
            
            this.drawdownChart.update('none');
        }
    }
    
    /**
     * Update bot performance chart with new data
     * Requirements: 5.5
     */
    updateBotPerformance(data) {
        if (!this.botPerformanceChart) return;
        
        // Find the dataset for this bot
        const datasetIndex = this.botPerformanceChart.data.datasets.findIndex(
            ds => ds.label.includes(data.symbol)
        );
        
        if (datasetIndex === -1) {
            // Bot not in chart, could add it dynamically
            console.log('[Charts] Bot not found in performance chart:', data.bot_id);
            return;
        }
        
        // Update the last data point
        const dataset = this.botPerformanceChart.data.datasets[datasetIndex];
        const lastPoint = dataset.data[dataset.data.length - 1];
        
        if (lastPoint) {
            lastPoint.x = Date.now();
            lastPoint.y = parseFloat(data.pnl_percent);
            
            // Update color based on P&L
            const color = data.pnl_percent >= 0 ? this.colors.emerald[500] : this.colors.red[500];
            dataset.borderColor = color;
            dataset.backgroundColor = color;
        }
        
        this.botPerformanceChart.update('none');
    }
    
    /**
     * Refresh all charts with new data
     */
    async refreshCharts() {
        // In a real implementation, this would fetch fresh data from the server
        console.log('[Charts] Refreshing charts...');
        
        // For now, just update with existing data
        // In production, you'd make an API call here
    }
    
    /**
     * Create gradient for chart background
     */
    createGradient(ctx, color, opacity) {
        const gradient = ctx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, color.replace('rgb', 'rgba').replace(')', `, ${opacity})`));
        gradient.addColorStop(1, color.replace('rgb', 'rgba').replace(')', ', 0)'));
        return gradient;
    }
    
    /**
     * Format timestamp for chart labels
     */
    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        
        if (this.currentPeriod === '24h') {
            return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        } else if (this.currentPeriod === '7d') {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } else {
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
    }
    
    /**
     * Get maximum number of data points based on period
     */
    getMaxPointsForPeriod() {
        switch (this.currentPeriod) {
            case '24h':
                return 48; // 30-minute intervals
            case '7d':
                return 168; // Hourly
            case '30d':
                return 720; // Hourly
            default:
                return 48;
        }
    }
    
    /**
     * Destroy all charts
     */
    destroy() {
        if (this.portfolioChart) {
            this.portfolioChart.destroy();
            this.portfolioChart = null;
        }
        if (this.drawdownChart) {
            this.drawdownChart.destroy();
            this.drawdownChart = null;
        }
        if (this.botPerformanceChart) {
            this.botPerformanceChart.destroy();
            this.botPerformanceChart = null;
        }
    }
}

// Initialize charts when DOM is ready
let dashboardCharts = null;

document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on dashboard page
    if (document.getElementById('portfolio-value-chart')) {
        // Wait for Chart.js to load
        if (typeof Chart !== 'undefined') {
            dashboardCharts = new DashboardCharts();
            dashboardCharts.init();
        } else {
            console.error('[Charts] Chart.js library not loaded');
        }
    }
});

// Export for use in other scripts
window.dashboardCharts = dashboardCharts;
