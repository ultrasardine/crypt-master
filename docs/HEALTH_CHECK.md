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

## Requirements

This endpoint satisfies requirement 8.5:
- Provides health check endpoints for each background service
- Returns JSON with service status
- Checks last successful run of each task
