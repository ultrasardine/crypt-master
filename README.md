# Crypt Master

Automated cryptocurrency trading system with Pionex exchange integration.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

Crypt Master is a fully automated cryptocurrency trading system that integrates with the Pionex exchange. It provides multi-factor market analysis, automated bot management, risk controls, and a real-time dashboard for monitoring trading activity.

### Key Capabilities

- **Multi-Tenant Architecture**: Complete user data isolation with per-user encrypted API keys
- **Multi-factor Market Analysis**: Technical indicators (RSI, MACD, Bollinger Bands, ADX, Stochastic), sentiment analysis, and volume anomaly detection
- **Automated Bot Management**: Create, monitor, and stop Grid, DCA, and Infinity Grid bots based on market signals
- **Risk Management**: Kelly Criterion position sizing, drawdown limits, per-trade risk limits, and automatic bot stopping
- **Dry-Run Mode**: Test strategies safely without executing real trades
- **Real-Time Dashboard**: WebSocket-powered live updates for signals, bot status, and performance metrics
- **Backtesting**: Test strategies against historical data before deploying

---

## Features

### Trading Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Dry-Run** (default) | Simulates all trades without API calls | Strategy testing, development |
| **Live** | Executes real trades via Pionex API | Production trading |

### Supported Bot Types

| Bot Type | Strategy | Best For |
|----------|----------|----------|
| **Grid Bot** | Buy low, sell high within a price range | Range-bound markets (ADX < 25) |
| **DCA Bot** | Dollar-cost averaging at intervals | Accumulation in trending markets |
| **Infinity Grid** | Grid trading without upper limit | Long-term bullish positions |

### Technical Indicators

| Indicator | Default Period | Signal Logic |
|-----------|----------------|--------------|
| RSI | 14 | < 30 = Buy, > 70 = Sell |
| MACD | 12/26/9 | MACD > Signal = Buy |
| Bollinger Bands | 20, 2σ | Below lower = Buy, Above upper = Sell |
| ADX | 14 | > 25 = Strong trend |
| Stochastic | 14/3/3 | < 20 = Buy, > 80 = Sell |

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CRYPT MASTER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │   Market Agent   │────▶│      Redis       │◀────│    Bot Agent     │    │
│  │                  │     │   (Pub/Sub)      │     │                  │    │
│  │  • Fetch prices  │     │                  │     │  • Create bots   │    │
│  │  • Calculate TA  │     │  Signals Channel │     │  • Stop bots     │    │
│  │  • Generate      │     │  Bot Events      │     │  • Monitor P&L   │    │
│  │    signals       │     │                  │     │  • Risk checks   │    │
│  └──────────────────┘     └──────────────────┘     └──────────────────┘    │
│           │                        │                        │               │
│           │                        │                        │               │
│           ▼                        ▼                        ▼               │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         PostgreSQL Database                           │  │
│  │  • Trading pairs  • Signals  • Bots  • Bot events  • Trades          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│           │                        │                        │               │
│           │                        │                        │               │
│           ▼                        ▼                        ▼               │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │   Django Web     │     │  Celery Workers  │     │   Pionex API     │    │
│  │                  │     │                  │     │                  │    │
│  │  • Dashboard     │     │  • Async tasks   │     │  • Market data   │    │
│  │  • REST API      │     │  • Notifications │     │  • Bot CRUD      │    │
│  │  • Admin panel   │     │  • Reports       │     │  • Orders        │    │
│  │  • WebSocket     │     │                  │     │  • Balances      │    │
│  └──────────────────┘     └──────────────────┘     └──────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
crypt-master/
├── agents/                 # Long-running agent services
│   ├── bot_agent.py       # Bot lifecycle management
│   └── market_agent.py    # Market analysis & signal generation
│
├── apps/                   # Django applications
│   ├── analysis/          # Market analysis views & backtesting
│   ├── api/               # REST API endpoints
│   ├── bots/              # Bot models and management
│   ├── core/              # Core models (TradingPair, APIKey)
│   ├── dashboard/         # Dashboard views & WebSocket consumers
│   └── trading/           # Trading signals and trades
│
├── config/                 # Django configuration
│   ├── settings.py        # Main settings
│   ├── test_settings.py   # Test configuration
│   ├── urls.py            # URL routing
│   ├── celery.py          # Celery configuration
│   └── asgi.py            # ASGI application
│
├── lib/                    # Shared library code
│   ├── analysis/          # Technical analysis, sentiment, signals
│   ├── pionex/            # Pionex API client
│   ├── risk/              # Risk management
│   ├── simulation/        # Dry-run simulator
│   ├── messaging/         # Redis pub/sub, WebSocket
│   ├── logging/           # Structured logging
│   ├── config/            # Configuration utilities
│   ├── crypto/            # API key encryption
│   └── multitenancy/      # User data isolation
│
├── templates/              # Django HTML templates
├── static/                 # Static assets (CSS)
├── tests/                  # Test suite
│   ├── unit/              # Unit tests
│   ├── property/          # Property-based tests (Hypothesis)
│   └── integration/       # Integration tests
│
├── scripts/                # Deployment scripts
├── docs/                   # Documentation
└── logs/                   # Log files
```

### Data Flow

1. **Market Agent** fetches price data from Pionex API every 60 seconds
2. **Technical Analysis** calculates indicators (RSI, MACD, BB, etc.)
3. **Signal Generator** produces BUY/SELL/HOLD signals with confidence scores
4. **Signals** are published to Redis and stored in PostgreSQL
5. **Bot Agent** subscribes to signals and evaluates bot actions
6. **Risk Manager** validates all bot operations against limits
7. **Dashboard** receives real-time updates via WebSocket

---

## Requirements

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.13+ | 3.13+ |
| PostgreSQL | 16+ | 16+ |
| Redis | 7+ | 7+ |
| Memory | 2GB | 4GB |
| Storage | 10GB | 20GB |

### System Dependencies

```bash
# macOS
brew install ta-lib postgresql redis

# Ubuntu/Debian
sudo apt-get install -y build-essential libta-lib-dev postgresql redis-server

# TA-Lib from source (if not available via package manager)
wget https://github.com/ta-lib/ta-lib/releases/download/v0.4.0/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib-0.4.0
./configure --prefix=/usr/local
make && sudo make install
sudo ldconfig
```

---

## Quick Start

### Using Docker (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/crypt-master.git
cd crypt-master

# 2. Copy environment file
cp .env.example .env

# 3. Edit .env with your settings
# At minimum, set POSTGRES_PASSWORD and DJANGO_SECRET_KEY

# 4. Start all services
make docker-up

# 5. Run database migrations
make docker-db-migrate

# 6. Access the dashboard
open http://localhost:8000
```

### Local Development

```bash
# 1. Clone and enter directory
git clone https://github.com/your-org/crypt-master.git
cd crypt-master

# 2. Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install dependencies
make dev

# 4. Copy and configure environment
cp .env.example .env
# Edit .env - set USE_SQLITE=True for quick start

# 5. Run migrations
make db-migrate

# 6. Start development server
make run
```

---

## Installation

### Step 1: Install uv Package Manager

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv
```

### Step 2: Install Project Dependencies

```bash
# Production dependencies only
make install

# Development dependencies (includes testing tools)
make dev
```

### Step 3: Install TA-Lib

TA-Lib is required for technical analysis. See [Requirements](#requirements) for installation instructions.

### Step 4: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your configuration (see [Configuration](#configuration)).

### Step 5: Initialize Database

```bash
# Using SQLite (development)
export USE_SQLITE=True
make db-migrate

# Using PostgreSQL
# Ensure PostgreSQL is running and DATABASE_URL is set
make db-migrate
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# =============================================================================
# Django Settings
# =============================================================================
DJANGO_SECRET_KEY=your-secret-key-here    # Generate with: make secrets-generate
DEBUG=True                                  # Set False in production
ALLOWED_HOSTS=localhost,127.0.0.1

# =============================================================================
# Database
# =============================================================================
# PostgreSQL (production)
DATABASE_URL=postgres://cryptmaster:password@localhost:5432/cryptmaster

# SQLite (development only)
USE_SQLITE=True

# =============================================================================
# Redis
# =============================================================================
REDIS_URL=redis://localhost:6379/0

# =============================================================================
# Pionex API (Required for live trading)
# =============================================================================
PIONEX_API_KEY=your-api-key
PIONEX_API_SECRET=your-api-secret

# =============================================================================
# Trading Mode
# =============================================================================
DRY_RUN=True                               # Set False for live trading (CAUTION!)

# =============================================================================
# Risk Management
# =============================================================================
RISK_MAX_POSITION_PCT=0.10                 # Max 10% of portfolio per position
RISK_MAX_PER_TRADE=0.02                    # Max 2% risk per trade
RISK_MAX_DRAWDOWN=0.20                     # Stop trading at 20% drawdown
RISK_MIN_CONFIDENCE=0.85                   # Min 85% confidence for bot creation
RISK_BOT_LOSS_THRESHOLD=0.10               # Auto-stop bots at 10% loss

# =============================================================================
# Analysis Configuration
# =============================================================================
ANALYSIS_INTERVAL_SECONDS=60               # Market analysis frequency
RSI_PERIOD=14
MACD_FAST=12
MACD_SLOW=26
MACD_SIGNAL=9
BOLLINGER_PERIOD=20
BOLLINGER_STD=2.0

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL=INFO
DJANGO_LOG_LEVEL=INFO
APP_LOG_LEVEL=DEBUG
AGENT_LOG_LEVEL=DEBUG

# =============================================================================
# Optional: LLM News Analysis
# =============================================================================
LLM_ENABLED=False
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Pionex API Setup

1. Log in to [Pionex](https://www.pionex.com/)
2. Go to **Settings** → **API Management**
3. Create a new API key with the following permissions:
   - Read account information
   - Trade spot
   - Manage trading bots
4. Copy the API Key and Secret to your `.env` file

> ⚠️ **Security**: Never commit API keys to version control. Keep your `.env` file secure.

---

## Usage

### Starting Services

#### Development (Local)

```bash
# Terminal 1: Django web server
make run

# Terminal 2: Market analysis agent
make run-market-agent

# Terminal 3: Bot management agent
make run-bot-agent

# Terminal 4: Celery worker (optional, for async tasks)
make run-celery
```

#### Production (Docker)

```bash
# Start all services
make docker-up

# View logs
make docker-logs

# Stop all services
make docker-down
```

### Dashboard Access

Once running, access the dashboard at: **http://localhost:8000**

### Trading Workflow

#### 1. Configure Trading Pairs

Navigate to **Settings** → **Trading Pairs** and add the pairs you want to trade:

```
Example: BTC_USDT, ETH_USDT, SOL_USDT
```

#### 2. Monitor Signals

The Market Agent automatically generates signals. View them in:
- **Dashboard** → **Signals** tab
- **API**: `GET /api/signals/`

#### 3. Bot Management

Bots are created automatically when:
- Signal confidence ≥ 85% (configurable)
- Risk limits allow new positions
- Market conditions favor the bot type

Manual bot management:
- **Dashboard** → **Bots** tab
- **API**: `POST /api/bots/`

#### 4. Review Performance

- **Dashboard** → **Performance** tab shows P&L
- **Logs**: `logs/trading.log` for detailed trade history

### Example: Creating a Bot via API

```bash
# Create a Grid Bot
curl -X POST http://localhost:8000/api/bots/ \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC_USDT",
    "bot_type": "GRID",
    "investment": "1000.00",
    "params": {
      "lower_price": 40000,
      "upper_price": 50000,
      "grid_count": 10
    }
  }'

# Create a DCA Bot
curl -X POST http://localhost:8000/api/bots/ \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETH_USDT",
    "bot_type": "DCA",
    "investment": "500.00",
    "params": {
      "interval_hours": 24,
      "orders_count": 10
    }
  }'
```

### Example: Querying Signals

```bash
# Get latest signals
curl http://localhost:8000/api/signals/

# Get signals for specific symbol
curl http://localhost:8000/api/signals/?symbol=BTC_USDT

# Get only BUY signals
curl http://localhost:8000/api/signals/?direction=BUY
```

---

## Development

### Code Style

This project uses:
- **ruff** for linting and formatting (line-length: 100)
- **mypy** for static type checking (strict mode)
- **Type hints** required on all function signatures
- **Docstrings** required for public functions and classes

```bash
# Run linter
make lint

# Auto-fix linting issues
make lint-fix

# Format code
make format

# Type check
make typecheck

# Run all checks
make check-all
```

### Adding New Features

#### 1. Create a New Django App

```bash
cd apps
uv run python ../manage.py startapp myfeature
```

#### 2. Add to INSTALLED_APPS

Edit `config/settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "apps.myfeature",
]
```

#### 3. Create Models, Views, URLs

Follow Django conventions. See existing apps for patterns.

#### 4. Write Tests

```bash
# Create test file
touch tests/unit/test_myfeature.py
```

```python
# tests/unit/test_myfeature.py
import pytest

def test_my_feature():
    assert True
```

### Adding New Technical Indicators

Edit `lib/analysis/technical.py`:

```python
def calculate_my_indicator(
    self,
    prices: list[float] | NDArray[np.floating],
    period: int = 14,
) -> MyIndicatorResult:
    """
    Calculate My Custom Indicator.
    
    Args:
        prices: Array of closing prices
        period: Calculation period
        
    Returns:
        MyIndicatorResult with value and signal
    """
    prices_arr = self._to_numpy(prices)
    
    if len(prices_arr) < period:
        return MyIndicatorResult(
            value=None,
            signal=SignalDirection.HOLD,
            data_insufficient=True,
        )
    
    # Your calculation here
    value = talib.MY_INDICATOR(prices_arr, timeperiod=period)
    
    return MyIndicatorResult(value=float(value[-1]), signal=SignalDirection.HOLD)
```

---

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run property-based tests
make test-property

# Run integration tests
make test-integration

# Run with coverage report
make coverage
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests
│   ├── test_technical_analyzer.py
│   ├── test_signal_generator.py
│   ├── test_risk_manager.py
│   └── ...
├── property/                # Property-based tests (Hypothesis)
│   ├── test_technical_properties.py
│   ├── test_confidence_properties.py
│   └── ...
└── integration/             # Integration tests
    ├── test_api.py
    └── ...
```

### Writing Tests

#### Unit Test Example

```python
# tests/unit/test_my_feature.py
import pytest
from lib.analysis.technical import TechnicalAnalyzer

class TestTechnicalAnalyzer:
    def test_rsi_oversold(self):
        """RSI below 30 should signal BUY."""
        analyzer = TechnicalAnalyzer()
        # Create prices that result in low RSI
        prices = [100 - i * 0.5 for i in range(20)]
        
        result = analyzer.calculate_rsi(prices)
        
        assert result.value is not None
        assert result.value < 30
        assert result.signal == SignalDirection.BUY
```

#### Property-Based Test Example

```python
# tests/property/test_technical_properties.py
from hypothesis import given, strategies as st
from lib.analysis.technical import TechnicalAnalyzer

class TestTechnicalProperties:
    @given(st.lists(st.floats(min_value=1, max_value=1000), min_size=20, max_size=100))
    def test_rsi_always_in_range(self, prices):
        """RSI should always be between 0 and 100."""
        analyzer = TechnicalAnalyzer()
        result = analyzer.calculate_rsi(prices)
        
        if result.value is not None:
            assert 0 <= result.value <= 100
```

---

## Deployment

### AWS ECR Deployment

#### Prerequisites

- AWS CLI configured with appropriate credentials
- Docker with buildx support
- Access to target EC2 instance

#### One-Time Setup

```bash
# Create ECR repository
make ecr-setup
```

#### Deploy

```bash
# Full deployment (build ARM64 image + push to ECR)
make deploy

# Or step by step:
make ecr-login
make ecr-push IMAGE_TAG=v1.0.0
```

### Portainer Deployment

1. Access Portainer at `https://your-ec2-ip:9443`
2. Create new Stack named `crypt-master`
3. Upload `docker-compose.yml` or paste contents
4. Configure environment variables
5. Deploy stack

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed instructions.

### Production Checklist

- [ ] Set `DEBUG=False`
- [ ] Generate secure `DJANGO_SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set strong `POSTGRES_PASSWORD`
- [ ] Configure Pionex API credentials
- [ ] Review risk management settings
- [ ] Start with `DRY_RUN=True` to verify setup
- [ ] Monitor logs for errors
- [ ] Set up log rotation
- [ ] Configure backups for PostgreSQL

---

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/signals/` | List trading signals |
| GET | `/api/signals/{id}/` | Get signal details |
| GET | `/api/bots/` | List all bots |
| POST | `/api/bots/` | Create a new bot |
| GET | `/api/bots/{id}/` | Get bot details |
| DELETE | `/api/bots/{id}/` | Stop a bot |
| GET | `/api/trades/` | List executed trades |
| GET | `/api/balances/` | Get account balances |
| GET | `/api/pairs/` | List trading pairs |
| POST | `/api/pairs/` | Add trading pair |
| GET | `/health/` | Health check endpoint |

### WebSocket

Connect to `/ws/dashboard/` for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/dashboard/');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'signal':
      console.log('New signal:', data.signal);
      break;
    case 'bot_created':
      console.log('Bot created:', data.bot);
      break;
    case 'bot_stopped':
      console.log('Bot stopped:', data.bot_id);
      break;
  }
};
```

---

## Troubleshooting

### Common Issues

#### TA-Lib Installation Fails

```bash
# Ensure C library is installed first
# macOS
brew install ta-lib

# Then reinstall Python package
uv sync --reinstall-package ta-lib
```

#### Database Connection Error

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Or use SQLite for development
export USE_SQLITE=True
```

#### Redis Connection Error

```bash
# Check Redis is running
redis-cli ping

# Start Redis
# macOS
brew services start redis

# Linux
sudo systemctl start redis
```

#### Docker Services Not Starting

```bash
# Check logs
make docker-logs

# Rebuild images
make docker-build

# Reset everything
make docker-clean
make docker-up
```

### Log Files

| Log File | Contents |
|----------|----------|
| `logs/crypt-master.log` | General application logs |
| `logs/trading.log` | Trading decisions and orders |
| `logs/bots.log` | Bot lifecycle events |
| `logs/errors.log` | Error-level logs only |

### Getting Help

1. Check the logs: `make logs-tail`
2. Verify environment: `make env-check`
3. Review configuration in `.env`
4. Check [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for deployment issues

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
