#!/bin/bash
# Smart API Gateway - Docker Quick Commands

set -e

DOCKER_COMPOSE="docker-compose"
COMPOSE_FILE="docker/docker-compose.yml"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Main commands
case "${1:-help}" in
    build)
        log_info "Building Docker images..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE build
        log_success "Build complete!"
        ;;
    
    up)
        log_info "Starting services..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE up -d
        log_success "Services started!"
        log_info "Waiting for services to be ready..."
        sleep 5
        ;;
    
    down)
        log_info "Stopping services..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE down
        log_success "Services stopped!"
        ;;
    
    restart)
        log_info "Restarting services..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE restart
        log_success "Services restarted!"
        ;;
    
    logs)
        SERVICE=${2:-gateway}
        log_info "Following logs for $SERVICE..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f $SERVICE
        ;;
    
    ps)
        log_info "Checking service status..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE ps
        ;;
    
    test)
        log_info "Running tests..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE exec gateway pytest tests/ -v
        log_success "Tests complete!"
        ;;
    
    clean)
        log_warn "Removing containers and volumes..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE down -v
        log_success "Cleanup complete!"
        ;;
    
    reset)
        log_warn "Full reset (rebuild + restart)..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE down -v
        $DOCKER_COMPOSE -f $COMPOSE_FILE build --no-cache
        $DOCKER_COMPOSE -f $COMPOSE_FILE up -d
        log_success "Reset complete!"
        ;;
    
    health)
        log_info "Checking service health..."
        echo ""
        echo -e "${BLUE}Gateway (8000):${NC}"
        curl -s http://localhost:8000/health | python -m json.tool 2>/dev/null || echo "❌ Not responding"
        echo ""
        echo -e "${BLUE}Auth Service (9001):${NC}"
        curl -s http://localhost:9001/auth/health | python -m json.tool 2>/dev/null || echo "❌ Not responding"
        echo ""
        echo -e "${BLUE}Chat Service (9002):${NC}"
        curl -s http://localhost:9002/chat/health | python -m json.tool 2>/dev/null || echo "❌ Not responding"
        echo ""
        echo -e "${BLUE}AI Service (9003):${NC}"
        curl -s http://localhost:9003/ai/health | python -m json.tool 2>/dev/null || echo "❌ Not responding"
        echo ""
        ;;
    
    shell)
        SERVICE=${2:-gateway}
        log_info "Entering $SERVICE container shell..."
        $DOCKER_COMPOSE -f $COMPOSE_FILE exec $SERVICE bash
        ;;
    
    stats)
        log_info "Showing container stats..."
        docker stats
        ;;
    
    help)
        echo ""
        echo -e "${GREEN}Smart API Gateway - Docker Quick Commands${NC}"
        echo ""
        echo "Usage: bash docker_run.sh <command> [options]"
        echo ""
        echo -e "${BLUE}Service Management:${NC}"
        echo "  build              Build all Docker images"
        echo "  up                 Start all services"
        echo "  down               Stop all services"
        echo "  restart            Restart all services"
        echo "  reset              Full reset (remove volumes, rebuild, restart)"
        echo "  clean              Remove all containers and volumes"
        echo ""
        echo -e "${BLUE}Monitoring:${NC}"
        echo "  ps                 Show running containers"
        echo "  logs [service]     Follow service logs (default: gateway)"
        echo "  stats              Show container resource usage"
        echo "  health             Check all service health endpoints"
        echo ""
        echo -e "${BLUE}Development:${NC}"
        echo "  test               Run pytest suite"
        echo "  shell [service]    Enter service container shell (default: gateway)"
        echo ""
        echo -e "${BLUE}Examples:${NC}"
        echo "  bash docker_run.sh build"
        echo "  bash docker_run.sh up"
        echo "  bash docker_run.sh logs gateway"
        echo "  bash docker_run.sh test"
        echo "  bash docker_run.sh shell auth"
        echo ""
        ;;
    
    *)
        log_error "Unknown command: $1"
        echo "Run 'bash docker_run.sh help' for available commands"
        exit 1
        ;;
esac
