#!/bin/bash
# =============================================================================
# ECR Repository Setup Script
# Creates the ECR repository for crypt-master in AWS eu-west-3 (Paris)
# =============================================================================

set -euo pipefail

# Configuration
AWS_REGION="${AWS_REGION:-eu-west-3}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-138120257234}"
REPOSITORY_NAME="${REPOSITORY_NAME:-crypt-master}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo_error "AWS CLI is not installed. Please install it first."
    echo "  macOS: brew install awscli"
    echo "  Linux: curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip' && unzip awscliv2.zip && sudo ./aws/install"
    exit 1
fi

# Check AWS credentials
echo_info "Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo_error "AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

CALLER_IDENTITY=$(aws sts get-caller-identity --output json)
echo_info "Authenticated as: $(echo "$CALLER_IDENTITY" | grep -o '"Arn": "[^"]*"' | cut -d'"' -f4)"

# Check if repository already exists
echo_info "Checking if repository '${REPOSITORY_NAME}' exists in ${AWS_REGION}..."
if aws ecr describe-repositories --repository-names "${REPOSITORY_NAME}" --region "${AWS_REGION}" &> /dev/null; then
    echo_warn "Repository '${REPOSITORY_NAME}' already exists."
    REPO_URI=$(aws ecr describe-repositories --repository-names "${REPOSITORY_NAME}" --region "${AWS_REGION}" --query 'repositories[0].repositoryUri' --output text)
    echo_info "Repository URI: ${REPO_URI}"
    exit 0
fi

# Create ECR repository
echo_info "Creating ECR repository '${REPOSITORY_NAME}' in ${AWS_REGION}..."
aws ecr create-repository \
    --repository-name "${REPOSITORY_NAME}" \
    --region "${AWS_REGION}" \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    --image-tag-mutability MUTABLE \
    --tags Key=Project,Value=crypt-master Key=Environment,Value=production

echo_info "Repository created successfully!"

# Get repository URI
REPO_URI=$(aws ecr describe-repositories --repository-names "${REPOSITORY_NAME}" --region "${AWS_REGION}" --query 'repositories[0].repositoryUri' --output text)
echo_info "Repository URI: ${REPO_URI}"

# Set lifecycle policy to clean up old images
echo_info "Setting lifecycle policy to retain last 10 images..."
aws ecr put-lifecycle-policy \
    --repository-name "${REPOSITORY_NAME}" \
    --region "${AWS_REGION}" \
    --lifecycle-policy-text '{
        "rules": [
            {
                "rulePriority": 1,
                "description": "Keep last 10 images",
                "selection": {
                    "tagStatus": "any",
                    "countType": "imageCountMoreThan",
                    "countNumber": 10
                },
                "action": {
                    "type": "expire"
                }
            }
        ]
    }'

echo_info "Lifecycle policy set successfully!"

# Print summary
echo ""
echo "=============================================="
echo_info "ECR Repository Setup Complete!"
echo "=============================================="
echo "Repository Name: ${REPOSITORY_NAME}"
echo "Repository URI:  ${REPO_URI}"
echo "Region:          ${AWS_REGION}"
echo ""
echo "Next steps:"
echo "  1. Build the Docker image: ./scripts/deploy.sh build"
echo "  2. Push to ECR: ./scripts/deploy.sh push"
echo "  3. Deploy via Portainer"
echo ""
