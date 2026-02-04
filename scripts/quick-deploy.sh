#!/bin/bash
# =============================================================================
# Quick Deploy Script
# Simplified deployment for common use cases
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Crypt-Master Quick Deploy${NC}"
echo "=========================="
echo ""

case "${1:-}" in
    dev)
        echo "Building for local development..."
        docker compose build
        docker compose up -d
        echo ""
        echo "Services started! Access dashboard at http://localhost:8000"
        ;;
    prod)
        echo "Deploying to production (ECR + Portainer)..."
        "${SCRIPT_DIR}/deploy.sh" deploy --latest
        ;;
    logs)
        docker compose logs -f "${2:-web}"
        ;;
    restart)
        docker compose restart "${2:-}"
        ;;
    stop)
        docker compose down
        ;;
    status)
        docker compose ps
        ;;
    *)
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  dev      Build and run locally"
        echo "  prod     Build ARM64 and push to ECR"
        echo "  logs     View logs (optionally specify service)"
        echo "  restart  Restart services"
        echo "  stop     Stop all services"
        echo "  status   Show service status"
        ;;
esac
