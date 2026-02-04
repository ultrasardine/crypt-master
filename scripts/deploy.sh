#!/bin/bash
# =============================================================================
# Crypt-Master Deployment Script
# Build ARM64 image, tag, and push to AWS ECR
# Target: EC2 ULTRASARDINE (t4g.small, ARM64) in eu-west-3 (Paris)
# =============================================================================

set -euo pipefail

# Configuration
AWS_REGION="${AWS_REGION:-eu-west-3}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-138120257234}"
REPOSITORY_NAME="${REPOSITORY_NAME:-crypt-master}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_NAME="${ECR_REGISTRY}/${REPOSITORY_NAME}"
PLATFORM="${PLATFORM:-linux/arm64}"

# Get version from pyproject.toml or use 'latest'
VERSION="${VERSION:-$(grep -m1 'version = ' pyproject.toml 2>/dev/null | cut -d'"' -f2 || echo 'latest')}"
GIT_SHA="${GIT_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Print usage
usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  build       Build Docker image for ARM64"
    echo "  push        Push image to ECR"
    echo "  deploy      Build and push (full deployment)"
    echo "  login       Login to ECR"
    echo "  status      Show current image status"
    echo ""
    echo "Options:"
    echo "  --tag TAG   Override image tag (default: version from pyproject.toml)"
    echo "  --latest    Also tag as 'latest'"
    echo ""
    echo "Environment Variables:"
    echo "  AWS_REGION       AWS region (default: eu-west-3)"
    echo "  AWS_ACCOUNT_ID   AWS account ID (default: 138120257234)"
    echo "  VERSION          Image version tag"
    echo ""
    echo "Examples:"
    echo "  $0 build                    # Build ARM64 image"
    echo "  $0 push --latest            # Push with version and latest tags"
    echo "  $0 deploy --tag v1.0.0      # Full deployment with custom tag"
}

# Check prerequisites
check_prerequisites() {
    echo_step "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo_error "Docker is not installed."
        exit 1
    fi
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        echo_error "Docker daemon is not running."
        exit 1
    fi
    
    # Check for buildx (required for multi-platform builds)
    if ! docker buildx version &> /dev/null; then
        echo_error "Docker buildx is not available. Please update Docker."
        exit 1
    fi
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo_error "AWS CLI is not installed."
        exit 1
    fi
    
    echo_info "All prerequisites met."
}

# Login to ECR
ecr_login() {
    echo_step "Logging in to ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "${ECR_REGISTRY}"
    echo_info "Successfully logged in to ECR."
}

# Setup buildx builder for ARM64
setup_buildx() {
    echo_step "Setting up Docker buildx for ARM64..."
    
    BUILDER_NAME="crypt-master-builder"
    
    # Check if builder exists
    if docker buildx inspect "${BUILDER_NAME}" &> /dev/null; then
        echo_info "Using existing builder: ${BUILDER_NAME}"
        docker buildx use "${BUILDER_NAME}"
    else
        echo_info "Creating new builder: ${BUILDER_NAME}"
        docker buildx create --name "${BUILDER_NAME}" --driver docker-container --bootstrap
        docker buildx use "${BUILDER_NAME}"
    fi
}

# Build Docker image
build_image() {
    local tag="${1:-$VERSION}"
    local push_flag="${2:-false}"
    
    echo_step "Building Docker image for ${PLATFORM}..."
    echo_info "Image: ${IMAGE_NAME}:${tag}"
    echo_info "Git SHA: ${GIT_SHA}"
    
    setup_buildx
    
    local build_args=(
        --platform "${PLATFORM}"
        --tag "${IMAGE_NAME}:${tag}"
        --tag "${IMAGE_NAME}:${GIT_SHA}"
        --build-arg "BUILDKIT_INLINE_CACHE=1"
        --cache-from "type=registry,ref=${IMAGE_NAME}:cache"
        --cache-to "type=registry,ref=${IMAGE_NAME}:cache,mode=max"
        --label "org.opencontainers.image.version=${tag}"
        --label "org.opencontainers.image.revision=${GIT_SHA}"
        --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        --file Dockerfile
    )
    
    if [[ "${TAG_LATEST:-false}" == "true" ]]; then
        build_args+=(--tag "${IMAGE_NAME}:latest")
    fi
    
    if [[ "${push_flag}" == "true" ]]; then
        build_args+=(--push)
    else
        build_args+=(--load)
    fi
    
    docker buildx build "${build_args[@]}" .
    
    echo_info "Build completed successfully!"
}

# Push image to ECR
push_image() {
    local tag="${1:-$VERSION}"
    
    echo_step "Pushing image to ECR..."
    
    ecr_login
    
    # Push version tag
    echo_info "Pushing ${IMAGE_NAME}:${tag}..."
    docker push "${IMAGE_NAME}:${tag}"
    
    # Push git SHA tag
    echo_info "Pushing ${IMAGE_NAME}:${GIT_SHA}..."
    docker push "${IMAGE_NAME}:${GIT_SHA}"
    
    # Push latest tag if requested
    if [[ "${TAG_LATEST:-false}" == "true" ]]; then
        echo_info "Pushing ${IMAGE_NAME}:latest..."
        docker push "${IMAGE_NAME}:latest"
    fi
    
    echo_info "Push completed successfully!"
}

# Full deployment (build and push)
deploy() {
    local tag="${1:-$VERSION}"
    
    echo_step "Starting full deployment..."
    echo_info "Version: ${tag}"
    echo_info "Platform: ${PLATFORM}"
    echo_info "Registry: ${ECR_REGISTRY}"
    
    check_prerequisites
    ecr_login
    build_image "${tag}" "true"
    
    echo ""
    echo "=============================================="
    echo_info "Deployment Complete!"
    echo "=============================================="
    echo "Image: ${IMAGE_NAME}:${tag}"
    echo "Git SHA: ${GIT_SHA}"
    echo ""
    echo "Next steps:"
    echo "  1. Go to Portainer on ULTRASARDINE"
    echo "  2. Update the stack with the new image tag"
    echo "  3. Or use: docker compose pull && docker compose up -d"
}

# Show status
show_status() {
    echo_step "Checking image status..."
    
    # Check local images
    echo ""
    echo "Local images:"
    docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" 2>/dev/null || echo "  No local images found"
    
    # Check ECR images
    echo ""
    echo "ECR images (last 5):"
    aws ecr describe-images \
        --repository-name "${REPOSITORY_NAME}" \
        --region "${AWS_REGION}" \
        --query 'sort_by(imageDetails,& imagePushedAt)[-5:].{Tags:imageTags[0],Size:imageSizeInBytes,Pushed:imagePushedAt}' \
        --output table 2>/dev/null || echo "  Unable to fetch ECR images (check AWS credentials)"
}

# Parse arguments
TAG_LATEST="false"
CUSTOM_TAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        build|push|deploy|login|status)
            COMMAND="$1"
            shift
            ;;
        --tag)
            CUSTOM_TAG="$2"
            shift 2
            ;;
        --latest)
            TAG_LATEST="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Use custom tag if provided
if [[ -n "${CUSTOM_TAG}" ]]; then
    VERSION="${CUSTOM_TAG}"
fi

# Execute command
case "${COMMAND:-}" in
    build)
        check_prerequisites
        build_image "${VERSION}" "false"
        ;;
    push)
        check_prerequisites
        push_image "${VERSION}"
        ;;
    deploy)
        deploy "${VERSION}"
        ;;
    login)
        ecr_login
        ;;
    status)
        show_status
        ;;
    *)
        usage
        exit 1
        ;;
esac
