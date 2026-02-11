# Health Check Endpoint

The health check endpoint provides real-time status information about background services in the Crypt Master system.

## Endpoint

```
GET /api/health/
```

## Authentication

This endpoint is **public** and does not require authentication.

## Response Format

```json
{
  "overall_status": "healthy|degraded|unhealthy",
  "services": {
    "Portfolio Sync": {
      "status": "healthy|stale|pending|disabled|error|unknown",
      "message": "Running normally",
      "last_run": "2026-02-06T10:30:00Z",
      "age_minutes": 2
    },
    "Bot Sync": {
      "status": "healthy",
      "message": "Running normally",
      "last_run": "2026-02-06T10:31:00Z",
      "age_minutes": 1
    },
    "Public Market Data": {
      "status": "healthy",
      "message": "Running normally",
      "last_run": "2026-02-06T09:45:00Z",
      "age_minutes": 47
    },
    "Signal Accuracy": {
      "status": "healthy",
      "message": "Running normally",
      "last_run": "2026-02-06T09:45:00Z",
      "age_minutes": 47
    }
  },
  "timestamp": "2026-02-06T10:32:15Z"
}
```

## Status Values

### Overall Status

- **healthy**: All services are running normally
- **degraded**: Some services are disabled or pending, but no critical failures
- **unhealthy**: One or more services are stale or experiencing errors

### Service Status

- **healthy**: Service ran recently within expected timeframe
- **stale**: Service hasn't run within expected timeframe (potential issue)
- **pending**: Service hasn't run yet (first execution pending)
- **disabled**: Service is disabled in configuration
- **error**: Error occurred while checking service status
- **unknown**: Service not configured

## Service Thresholds

Each service has a maximum age threshold before being marked as stale:

- **Portfolio Sync**: 10 minutes (runs every 5 minutes)
- **Bot Sync**: 5 minutes (runs every 2 minutes)
- **Public Market Data**: 90 minutes (runs every hour)
- **Signal Accuracy**: 90 minutes (runs every hour)

## Example Usage

### cURL

```bash
curl http://localhost:8000/api/health/
```

### Python

```python
import requests

response = requests.get('http://localhost:8000/api/health/')
data = response.json()

if data['overall_status'] == 'healthy':
    print('All services are healthy')
else:
    print(f'System status: {data["overall_status"]}')
    for service, status in data['services'].items():
        if status['status'] != 'healthy':
            print(f'  {service}: {status["status"]} - {status["message"]}')
```

### JavaScript

```javascript
fetch('/api/health/')
  .then(response => response.json())
  .then(data => {
    if (data.overall_status === 'healthy') {
      console.log('All services are healthy');
    } else {
      console.log(`System status: ${data.overall_status}`);
      Object.entries(data.services).forEach(([service, status]) => {
        if (status.status !== 'healthy') {
          console.log(`  ${service}: ${status.status} - ${status.message}`);
        }
      });
    }
  });
```

## Monitoring Integration

This endpoint can be integrated with monitoring systems:

### Prometheus

Use a JSON exporter to convert the health check response to Prometheus metrics.

### Datadog

Configure a synthetic test to poll the endpoint and alert on non-healthy status.

### Nagios/Icinga

Create a check script that polls the endpoint and returns appropriate exit codes:
- 0 (OK) for "healthy"
- 1 (WARNING) for "degraded"
- 2 (CRITICAL) for "unhealthy"

## Dashboard Integration

The dashboard can display service health status using this endpoint:

```javascript
// In dashboard-websocket.js or similar
async function updateServiceHealth() {
  const response = await fetch('/api/health/');
  const data = await response.json();
  
  // Update UI based on overall_status
  const statusIndicator = document.getElementById('service-health-indicator');
  statusIndicator.className = `status-${data.overall_status}`;
  statusIndicator.textContent = data.overall_status.toUpperCase();
  
  // Update individual service statuses
  Object.entries(data.services).forEach(([service, status]) => {
    const element = document.getElementById(`service-${service.replace(/\s+/g, '-').toLowerCase()}`);
    if (element) {
      element.className = `service-status status-${status.status}`;
      element.textContent = status.message;
    }
  });
}

// Poll every 30 seconds
setInterval(updateServiceHealth, 30000);
updateServiceHealth(); // Initial load
```

## Pionex API Health Check (CLI)

A management command is available to verify Pionex API credentials and connectivity:

```bash
# Basic check (tests public endpoint only)
uv run python manage.py pionex_healthcheck

# Verbose output with sample data
uv run python manage.py pionex_healthcheck -v

# Test authenticated endpoints
uv run python manage.py pionex_healthcheck --test-balances --test-bots

# Full check with all options
uv run python manage.py pionex_healthcheck -v --test-balances --test-bots
```

### Options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Show detailed response information |
| `--test-balances` | Test fetching account balances (requires read permissions) |
| `--test-bots` | Test fetching bot list (requires bot permissions) |

### Output

The command displays:
- Environment configuration (masked API key, trading mode)
- Public endpoint test (symbol retrieval)
- Authenticated endpoint tests (if requested)
- Helpful error messages with troubleshooting suggestions

### Common Issues

| Error | Possible Cause |
|-------|----------------|
| 401 / INVALID_SIGNATURE | Incorrect API secret or system clock drift |
| 403 / Permission denied | API key lacks required permissions or IP not whitelisted |
| 429 | Rate limit exceeded, wait and retry |
| 5xx | Pionex API issues, check status page |

## Data Flow Diagnostic Script

For comprehensive troubleshooting of data flow issues, use the diagnostic script:

```bash
uv run python scripts/diagnose_data_flow.py
```

### What It Checks

1. **Database Data**: Users, profiles, portfolio snapshots, market context, trading pairs, bots, signals, and trades
2. **User API Keys**: Verifies admin user has encrypted API keys configured and can decrypt them
3. **Pionex API Connection**: Tests public endpoints (symbols), authenticated endpoints (balances), and bot API
4. **Sync Services**: Verifies sync services are available and lists registered Celery sync tasks

### Example Output

```
============================================================
DATABASE DATA CHECK
============================================================
Users: 1
  - admin (id=1, is_staff=True)
    Profile: api_key=True, api_secret=True
    Active pairs: ['BTC_USDT', 'ETH_USDT']

Portfolio Snapshots: 24
  Latest: 2026-02-11 10:30:00 - $12,345.67

Market Context Snapshots: 48
  Latest: 2026-02-11 10:15:00 - Regime: RISK_ON
...
```

### When to Use

- Initial setup verification
- Debugging missing data in the dashboard
- Verifying API key configuration
- Checking Pionex connectivity issues
- Confirming Celery tasks are registered

## Requirements

This endpoint satisfies requirement 8.5:
- Provides health check endpoints for each background service
- Returns JSON with service status
- Checks last successful run of each task
