# Crypt-Master Deployment Guide

This guide covers deploying Crypt-Master to AWS EC2 via Portainer.

## Target Environment

- **EC2 Instance**: ULTRASARDINE (t4g.small, ARM64)
- **Region**: eu-west-3 (Paris)
- **Container Registry**: AWS ECR
- **Orchestration**: Portainer

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    EC2 - ULTRASARDINE                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Portainer                         │   │
│  │  ┌─────────┐ ┌──────────────┐ ┌─────────────────┐  │   │
│  │  │   web   │ │ market-agent │ │    bot-agent    │  │   │
│  │  │  :8000  │ │              │ │                 │  │   │
│  │  └────┬────┘ └──────┬───────┘ └────────┬────────┘  │   │
│  │       │             │                  │           │   │
│  │  ┌────┴─────────────┴──────────────────┴────────┐  │   │
│  │  │                   Redis                       │  │   │
│  │  │                   :6379                       │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  │       │                                            │   │
│  │  ┌────┴─────────────────────────────────────────┐  │   │
│  │  │                 PostgreSQL                    │  │   │
│  │  │                   :5432                       │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **AWS CLI** configured with credentials that have ECR access
2. **Docker** with buildx support for ARM64 builds
3. **Portainer** running on the target EC2 instance
4. **ECR Repository** created (see below)

## Step 1: Create ECR Repository

Run the setup script (one-time):

```bash
./scripts/ecr-setup.sh
```

This creates:
- ECR repository `crypt-master` in eu-west-3
- Lifecycle policy to retain last 10 images
- Image scanning enabled on push

## Step 2: Build and Push Image

### Option A: Full Deployment (Recommended)

```bash
./scripts/deploy.sh deploy --latest
```

This will:
1. Login to ECR
2. Build ARM64 image using Docker buildx
3. Push with version tag, git SHA tag, and `latest` tag

### Option B: Step by Step

```bash
# Login to ECR
./scripts/deploy.sh login

# Build locally
./scripts/deploy.sh build

# Push to ECR
./scripts/deploy.sh push --latest
```

### Custom Version Tag

```bash
./scripts/deploy.sh deploy --tag v1.2.3 --latest
```

## Step 3: Portainer Stack Configuration

### Access Portainer

1. Navigate to `https://<EC2-IP>:9443`
2. Login with your Portainer credentials

### Create Stack

1. Go to **Stacks** → **Add stack**
2. Name: `crypt-master`
3. Build method: **Upload** or **Web editor**

### Upload docker-compose.yml

Upload the `docker-compose.yml` file from the repository, or paste its contents.

### Configure Environment Variables

In Portainer, add these environment variables:

#### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key (generate unique) | `your-50-char-random-string` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `strong-random-password` |
| `PIONEX_API_KEY` | Your Pionex API key | `abc123...` |
| `PIONEX_API_SECRET` | Your Pionex API secret | `xyz789...` |

#### Optional Variables (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_TAG` | `latest` | Docker image tag to deploy |
| `DEBUG` | `False` | Django debug mode |
| `DRY_RUN` | `True` | Simulate trades without real orders |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `POSTGRES_DB` | `cryptmaster` | Database name |
| `POSTGRES_USER` | `cryptmaster` | Database user |

#### Risk Management Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RISK_MAX_POSITION_PCT` | `0.10` | Max position size (10%) |
| `RISK_MAX_PER_TRADE` | `0.02` | Max risk per trade (2%) |
| `RISK_MAX_DRAWDOWN` | `0.20` | Max drawdown before halt (20%) |
| `RISK_MIN_CONFIDENCE` | `0.85` | Min signal confidence (85%) |

#### Analysis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANALYSIS_INTERVAL_SECONDS` | `60` | Market analysis interval |
| `RSI_PERIOD` | `14` | RSI calculation period |
| `MACD_FAST` | `12` | MACD fast period |
| `MACD_SLOW` | `26` | MACD slow period |
| `BOLLINGER_PERIOD` | `20` | Bollinger Bands period |

#### Optional LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ENABLED` | `False` | Enable LLM news analysis |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | LLM model to use |

### Deploy Stack

1. Click **Deploy the stack**
2. Wait for all services to start (may take 1-2 minutes)
3. Check service health in Portainer

## Step 4: Verify Deployment

### Check Service Status

In Portainer, verify all containers are running:
- `crypt-master_web_1` - Django web app
- `crypt-master_market-agent_1` - Market analysis
- `crypt-master_bot-agent_1` - Bot management
- `crypt-master_celery_1` - Async tasks
- `crypt-master_celery-beat_1` - Scheduled tasks
- `crypt-master_postgres_1` - Database
- `crypt-master_redis_1` - Cache/broker

### Access Dashboard

Navigate to `http://<EC2-IP>:8000` to access the dashboard.

### Check Logs

In Portainer, click on a container and view logs, or use:

```bash
# SSH to EC2 and run:
docker compose -f /path/to/docker-compose.yml logs -f web
```

## Step 5: Initial Setup

### Run Migrations

The first time you deploy, run migrations:

```bash
# In Portainer, open console for 'web' container:
python manage.py migrate
```

### Create Admin User

```bash
python manage.py createsuperuser
```

### Collect Static Files

Static files are collected during image build, but if needed:

```bash
python manage.py collectstatic --noinput
```

## Updating Deployment

### Deploy New Version

1. Build and push new image:
   ```bash
   ./scripts/deploy.sh deploy --tag v1.2.4 --latest
   ```

2. In Portainer:
   - Go to your stack
   - Click **Pull and redeploy**
   - Or update `IMAGE_TAG` environment variable and redeploy

### Rolling Back

To rollback to a previous version:

1. In Portainer, update `IMAGE_TAG` to the previous version
2. Redeploy the stack

Or use a specific git SHA:
```bash
IMAGE_TAG=abc1234 docker compose pull
docker compose up -d
```

## Troubleshooting

### Container Won't Start

1. Check logs in Portainer
2. Verify environment variables are set correctly
3. Ensure PostgreSQL and Redis are healthy first

### Database Connection Issues

1. Verify `POSTGRES_PASSWORD` matches in all services
2. Check PostgreSQL container logs
3. Ensure `postgres` service is healthy before other services start

### API Connection Issues

1. Verify `PIONEX_API_KEY` and `PIONEX_API_SECRET` are correct
2. Check network connectivity from EC2 to Pionex API
3. Review market-agent logs for API errors

### High Memory Usage

The t4g.small has 2GB RAM. If memory is constrained:
1. Reduce `GUNICORN_WORKERS` to 1
2. Reduce Celery concurrency
3. Consider upgrading instance type

## Security Recommendations

1. **Never commit secrets** - Use Portainer environment variables
2. **Enable DRY_RUN initially** - Test thoroughly before live trading
3. **Use strong passwords** - Generate random passwords for PostgreSQL
4. **Restrict network access** - Use security groups to limit port access
5. **Monitor logs** - Set up log monitoring for suspicious activity
6. **Regular updates** - Keep images updated with security patches

## Backup and Recovery

### Database Backup

```bash
# Create backup
docker exec crypt-master_postgres_1 pg_dump -U cryptmaster cryptmaster > backup.sql

# Restore backup
docker exec -i crypt-master_postgres_1 psql -U cryptmaster cryptmaster < backup.sql
```

### Volume Backup

Portainer volumes are stored in `/var/lib/docker/volumes/`. Back up:
- `crypt-master_postgres_data`
- `crypt-master_redis_data`
