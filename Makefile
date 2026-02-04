# =============================================================================
# Crypt Master - Makefile
# Automated cryptocurrency trading system with Pionex integration
# =============================================================================

.PHONY: help install dev clean test lint format typecheck \
        docker-build docker-up docker-down docker-logs docker-shell \
        db-migrate db-makemigrations db-shell db-reset \
        run run-web run-market-agent run-bot-agent run-celery \
        deploy ecr-login ecr-push coverage docs

# Default target
.DEFAULT_GOAL := help

# =============================================================================
# VARIABLES
# =============================================================================

PYTHON := uv run python
PYTEST := uv run pytest
RUFF := uv run ruff
MYPY := uv run mypy
CELERY := uv run celery

# Docker
DOCKER_COMPOSE := docker compose
IMAGE_NAME := 138120257234.dkr.ecr.eu-west-3.amazonaws.com/crypt-master
IMAGE_TAG ?= latest

# Colors for terminal output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

# =============================================================================
# HELP
# =============================================================================

help: ## Show this help message
	@echo ""
	@echo "$(CYAN)Crypt Master - Development Commands$(RESET)"
	@echo "======================================"
	@echo ""
	@echo "$(GREEN)Setup & Installation:$(RESET)"
	@grep -E '^(install|dev|clean):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Development Server:$(RESET)"
	@grep -E '^(run|run-web|run-market-agent|run-bot-agent|run-celery):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Testing:$(RESET)"
	@grep -E '^(test|test-unit|test-property|test-integration|coverage):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Code Quality:$(RESET)"
	@grep -E '^(lint|format|typecheck|check-all):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Database:$(RESET)"
	@grep -E '^(db-migrate|db-makemigrations|db-shell|db-reset):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Docker:$(RESET)"
	@grep -E '^(docker-build|docker-up|docker-down|docker-logs|docker-shell|docker-clean):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Deployment:$(RESET)"
	@grep -E '^(deploy|ecr-login|ecr-push|ecr-setup):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# SETUP & INSTALLATION
# =============================================================================

install: ## Install production dependencies
	@echo "$(CYAN)Installing production dependencies...$(RESET)"
	uv sync
	@echo "$(GREEN)✓ Dependencies installed$(RESET)"

dev: ## Install all dependencies including dev tools
	@echo "$(CYAN)Installing all dependencies (including dev)...$(RESET)"
	uv sync --extra dev
	@echo "$(GREEN)✓ Dev dependencies installed$(RESET)"

clean: ## Remove build artifacts, caches, and temporary files
	@echo "$(CYAN)Cleaning up...$(RESET)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	rm -rf .hypothesis/ 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(RESET)"

# =============================================================================
# DEVELOPMENT SERVER
# =============================================================================

run: ## Run Django development server
	@echo "$(CYAN)Starting Django development server...$(RESET)"
	$(PYTHON) manage.py runserver

run-web: ## Run Gunicorn production server locally
	@echo "$(CYAN)Starting Gunicorn server...$(RESET)"
	uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --reload

run-market-agent: ## Run the market analysis agent
	@echo "$(CYAN)Starting Market Analysis Agent...$(RESET)"
	$(PYTHON) -m agents.market_agent

run-bot-agent: ## Run the bot management agent
	@echo "$(CYAN)Starting Bot Management Agent...$(RESET)"
	$(PYTHON) -m agents.bot_agent

run-celery: ## Run Celery worker
	@echo "$(CYAN)Starting Celery worker...$(RESET)"
	$(CELERY) -A config worker -l info

run-celery-beat: ## Run Celery beat scheduler
	@echo "$(CYAN)Starting Celery beat...$(RESET)"
	$(CELERY) -A config beat -l info

# =============================================================================
# TESTING
# =============================================================================

test: ## Run all tests
	@echo "$(CYAN)Running all tests...$(RESET)"
	$(PYTEST) -v

test-unit: ## Run unit tests only
	@echo "$(CYAN)Running unit tests...$(RESET)"
	$(PYTEST) tests/unit/ -v

test-property: ## Run property-based tests only
	@echo "$(CYAN)Running property-based tests...$(RESET)"
	$(PYTEST) tests/property/ -v

test-integration: ## Run integration tests only
	@echo "$(CYAN)Running integration tests...$(RESET)"
	$(PYTEST) tests/integration/ -v

test-fast: ## Run tests excluding slow property tests
	@echo "$(CYAN)Running fast tests...$(RESET)"
	$(PYTEST) tests/unit/ tests/integration/ -v

coverage: ## Run tests with coverage report
	@echo "$(CYAN)Running tests with coverage...$(RESET)"
	$(PYTEST) --cov=apps --cov=lib --cov=agents --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/$(RESET)"

# =============================================================================
# CODE QUALITY
# =============================================================================

lint: ## Run linter (ruff check)
	@echo "$(CYAN)Running linter...$(RESET)"
	$(RUFF) check .

lint-fix: ## Run linter and auto-fix issues
	@echo "$(CYAN)Running linter with auto-fix...$(RESET)"
	$(RUFF) check . --fix

format: ## Format code with ruff
	@echo "$(CYAN)Formatting code...$(RESET)"
	$(RUFF) format .
	@echo "$(GREEN)✓ Code formatted$(RESET)"

format-check: ## Check code formatting without changes
	@echo "$(CYAN)Checking code format...$(RESET)"
	$(RUFF) format . --check

typecheck: ## Run type checker (mypy)
	@echo "$(CYAN)Running type checker...$(RESET)"
	$(MYPY) .

check-all: lint format-check typecheck ## Run all code quality checks
	@echo "$(GREEN)✓ All checks passed$(RESET)"

# =============================================================================
# DATABASE
# =============================================================================

db-migrate: ## Apply database migrations
	@echo "$(CYAN)Applying migrations...$(RESET)"
	$(PYTHON) manage.py migrate
	@echo "$(GREEN)✓ Migrations applied$(RESET)"

db-makemigrations: ## Create new migrations
	@echo "$(CYAN)Creating migrations...$(RESET)"
	$(PYTHON) manage.py makemigrations
	@echo "$(GREEN)✓ Migrations created$(RESET)"

db-shell: ## Open database shell
	@echo "$(CYAN)Opening database shell...$(RESET)"
	$(PYTHON) manage.py dbshell

db-reset: ## Reset database (WARNING: destroys all data)
	@echo "$(RED)WARNING: This will destroy all data!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	@echo "$(CYAN)Resetting database...$(RESET)"
	$(PYTHON) manage.py flush --no-input
	$(PYTHON) manage.py migrate
	@echo "$(GREEN)✓ Database reset$(RESET)"

db-seed: ## Seed database with sample data
	@echo "$(CYAN)Seeding database...$(RESET)"
	$(PYTHON) manage.py loaddata fixtures/*.json 2>/dev/null || echo "No fixtures found"
	@echo "$(GREEN)✓ Database seeded$(RESET)"

# =============================================================================
# DJANGO MANAGEMENT
# =============================================================================

shell: ## Open Django shell
	@echo "$(CYAN)Opening Django shell...$(RESET)"
	$(PYTHON) manage.py shell

createsuperuser: ## Create Django superuser
	@echo "$(CYAN)Creating superuser...$(RESET)"
	$(PYTHON) manage.py createsuperuser

collectstatic: ## Collect static files
	@echo "$(CYAN)Collecting static files...$(RESET)"
	$(PYTHON) manage.py collectstatic --noinput
	@echo "$(GREEN)✓ Static files collected$(RESET)"

# =============================================================================
# DOCKER - LOCAL DEVELOPMENT
# =============================================================================

docker-build: ## Build Docker image locally
	@echo "$(CYAN)Building Docker image...$(RESET)"
	$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✓ Docker image built$(RESET)"

docker-up: ## Start all Docker services
	@echo "$(CYAN)Starting Docker services...$(RESET)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Services started$(RESET)"
	@echo "$(CYAN)Dashboard: http://localhost:8000$(RESET)"

docker-down: ## Stop all Docker services
	@echo "$(CYAN)Stopping Docker services...$(RESET)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Services stopped$(RESET)"

docker-restart: ## Restart all Docker services
	@echo "$(CYAN)Restarting Docker services...$(RESET)"
	$(DOCKER_COMPOSE) restart
	@echo "$(GREEN)✓ Services restarted$(RESET)"

docker-logs: ## View Docker logs (all services)
	$(DOCKER_COMPOSE) logs -f

docker-logs-web: ## View web service logs
	$(DOCKER_COMPOSE) logs -f web

docker-logs-agents: ## View agent logs
	$(DOCKER_COMPOSE) logs -f market-agent bot-agent

docker-shell: ## Open shell in web container
	@echo "$(CYAN)Opening shell in web container...$(RESET)"
	$(DOCKER_COMPOSE) exec web /bin/bash

docker-clean: ## Remove all Docker resources (volumes, images)
	@echo "$(RED)WARNING: This will remove all Docker data!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	@echo "$(CYAN)Cleaning Docker resources...$(RESET)"
	$(DOCKER_COMPOSE) down -v --rmi local
	@echo "$(GREEN)✓ Docker resources cleaned$(RESET)"

docker-ps: ## Show running Docker containers
	$(DOCKER_COMPOSE) ps

docker-stats: ## Show Docker container stats
	docker stats --no-stream $$($(DOCKER_COMPOSE) ps -q)

# =============================================================================
# DOCKER - DATABASE OPERATIONS
# =============================================================================

docker-db-migrate: ## Run migrations in Docker
	@echo "$(CYAN)Running migrations in Docker...$(RESET)"
	$(DOCKER_COMPOSE) exec web python manage.py migrate
	@echo "$(GREEN)✓ Migrations applied$(RESET)"

docker-db-shell: ## Open database shell in Docker
	$(DOCKER_COMPOSE) exec postgres psql -U cryptmaster -d cryptmaster

docker-db-backup: ## Backup database from Docker
	@echo "$(CYAN)Backing up database...$(RESET)"
	$(DOCKER_COMPOSE) exec postgres pg_dump -U cryptmaster cryptmaster > backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✓ Database backed up$(RESET)"

# =============================================================================
# DEPLOYMENT - AWS ECR
# =============================================================================

ecr-login: ## Login to AWS ECR
	@echo "$(CYAN)Logging into AWS ECR...$(RESET)"
	aws ecr get-login-password --region eu-west-3 | docker login --username AWS --password-stdin 138120257234.dkr.ecr.eu-west-3.amazonaws.com
	@echo "$(GREEN)✓ Logged into ECR$(RESET)"

ecr-setup: ## Create ECR repository (one-time setup)
	@echo "$(CYAN)Setting up ECR repository...$(RESET)"
	./scripts/ecr-setup.sh
	@echo "$(GREEN)✓ ECR repository created$(RESET)"

ecr-push: ecr-login ## Build and push image to ECR
	@echo "$(CYAN)Building and pushing to ECR...$(RESET)"
	docker buildx build --platform linux/arm64 -t $(IMAGE_NAME):$(IMAGE_TAG) --push .
	@echo "$(GREEN)✓ Image pushed to ECR$(RESET)"

deploy: ## Full deployment (build + push + tag latest)
	@echo "$(CYAN)Starting full deployment...$(RESET)"
	./scripts/deploy.sh deploy --latest
	@echo "$(GREEN)✓ Deployment complete$(RESET)"

deploy-quick: ## Quick deploy (push only, no rebuild)
	@echo "$(CYAN)Quick deployment...$(RESET)"
	./scripts/quick-deploy.sh
	@echo "$(GREEN)✓ Quick deployment complete$(RESET)"

# =============================================================================
# UTILITIES
# =============================================================================

env-check: ## Verify environment configuration
	@echo "$(CYAN)Checking environment...$(RESET)"
	@test -f .env && echo "$(GREEN)✓ .env file exists$(RESET)" || echo "$(RED)✗ .env file missing$(RESET)"
	@$(PYTHON) -c "import django; print('$(GREEN)✓ Django installed$(RESET)')" 2>/dev/null || echo "$(RED)✗ Django not installed$(RESET)"
	@$(PYTHON) -c "import talib; print('$(GREEN)✓ TA-Lib installed$(RESET)')" 2>/dev/null || echo "$(RED)✗ TA-Lib not installed$(RESET)"
	@which redis-cli > /dev/null && echo "$(GREEN)✓ Redis CLI available$(RESET)" || echo "$(YELLOW)⚠ Redis CLI not found$(RESET)"

logs-tail: ## Tail application logs
	tail -f logs/*.log

logs-clear: ## Clear all log files
	@echo "$(CYAN)Clearing logs...$(RESET)"
	rm -f logs/*.log
	touch logs/.gitkeep
	@echo "$(GREEN)✓ Logs cleared$(RESET)"

secrets-generate: ## Generate a new Django secret key
	@echo "$(CYAN)Generating secret key...$(RESET)"
	@$(PYTHON) -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

update-deps: ## Update all dependencies
	@echo "$(CYAN)Updating dependencies...$(RESET)"
	uv lock --upgrade
	uv sync --extra dev
	@echo "$(GREEN)✓ Dependencies updated$(RESET)"
