#!/bin/bash
# Browser Sensor Lab - Containerized Chrome browsers for Osk testing
# Alternative to Android emulators - uses headless Chrome in containers
#
# Usage: ./scripts/browser_sensor_lab.sh [command] [options]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
DEFAULT_COUNT=5
CONTAINER_PREFIX="osk-browser"
DEFAULT_IMAGE="docker.io/browserless/chrome:latest"
BASE_PORT=3100

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

show_help() {
    cat << 'EOF'
Browser Sensor Lab - Containerized Chrome for Osk Testing

This is a lightweight alternative to Android emulators. It runs headless
Chrome browsers in containers that can connect to your Osk hub as sensors.

USAGE:
    ./scripts/browser_sensor_lab.sh <command> [options]

COMMANDS:
    start     Start N Chrome containers (default: 5)
    stop      Stop all containers
    status    Show running containers
    test      Connect to hub and validate

OPTIONS:
    --count N       Number of browsers (default: 5)
    --hub-url URL   Osk hub URL
    --duration S    Test duration in seconds (default: 600)

EXAMPLES:
    # Start 5 browsers
    ./scripts/browser_sensor_lab.sh start --count 5
    
    # Connect to hub and test
    ./scripts/browser_sensor_lab.sh test --hub-url http://192.168.1.100:8080
    
    # Stop all
    ./scripts/browser_sensor_lab.sh stop

LIMITATIONS:
    - Not real Android devices (no battery/thermal data)
    - WebRTC behavior differs from mobile browsers
    - For hub pipeline capacity testing, not device realism

For real-device validation, borrow Android phones and use:
    docs/runbooks/chromebook-lab-smoke.md
EOF
}

cmd_start() {
    local count=5
    local image="$DEFAULT_IMAGE"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --count) count="$2"; shift 2 ;;
            --image) image="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    
    log_info "Starting $count Chrome browser(s)..."
    
    if ! command -v podman &> /dev/null; then
        log_error "Podman not found. Install: sudo dnf install podman"
        exit 1
    fi
    
    # Pull image
    log_info "Pulling Chrome container image..."
    podman pull "$image" 2>&1 | tail -5
    
    # Start containers
    for i in $(seq 1 $count); do
        local name="${CONTAINER_PREFIX}-${i}"
        local port=$((BASE_PORT + i))
        
        if podman container exists "$name" 2>/dev/null; then
            podman rm -f "$name" 2>/dev/null || true
        fi
        
        log_info "Starting browser $i/$count on port $port..."
        
        podman run -d \
            --name "$name" \
            -p "${port}:3000" \
            -e "CONNECTION_TIMEOUT=600000" \
            -e "MAX_CONCURRENT_SESSIONS=1" \
            "$image" 2>&1 > /dev/null
            
        log_success "Container $name started"
    done
    
    log_info "Waiting for browsers to initialize (10s)..."
    sleep 10
    
    # Health check
    local ready=0
    for i in $(seq 1 $count); do
        local port=$((BASE_PORT + i))
        if curl -s "http://127.0.0.1:${port}/pressure" > /dev/null 2>&1; then
            ready=$((ready + 1))
        fi
    done
    
    log_success "$ready/$count browsers ready"
    log_info "Browser endpoints available at:"
    for i in $(seq 1 $count); do
        local port=$((BASE_PORT + i))
        log_info "  Browser-$i: http://localhost:${port}"
    done
}

cmd_stop() {
    log_info "Stopping all browser containers..."
    
    for container in $(podman ps -a --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}-" || true); do
        log_info "Stopping $container..."
        podman stop "$container" 2>/dev/null || true
        podman rm "$container" 2>/dev/null || true
    done
    
    log_success "All browsers stopped"
}

cmd_status() {
    log_info "Checking browser status..."
    
    local containers=$(podman ps --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}-" || true)
    
    if [[ -z "$containers" ]]; then
        log_warn "No browser containers running"
        return
    fi
    
    echo
    echo "Container Status:"
    echo "================="
    podman ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep "^${CONTAINER_PREFIX}-" || true
    
    echo
    echo "Health Check:"
    echo "============="
    for i in $(seq 1 20); do
        local name="${CONTAINER_PREFIX}-${i}"
        local port=$((BASE_PORT + i))
        
        if ! podman container exists "$name" 2>/dev/null; then
            continue
        fi
        
        if curl -s "http://127.0.0.1:${port}/pressure" > /dev/null 2>&1; then
            echo "  Browser-$i (port $port): Ready ✓"
        else
            echo "  Browser-$i (port $port): Not ready"
        fi
    done
}

cmd_test() {
    local hub_url=""
    local duration=600
    local count=5
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --hub-url) hub_url="$2"; shift 2 ;;
            --duration) duration="$2"; shift 2 ;;
            --count) count="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    
    if [[ -z "$hub_url" ]]; then
        local host_ip=$(hostname -I | awk '{print $1}')
        hub_url="http://${host_ip}:8080"
        log_warn "--hub-url not specified, using: $hub_url"
    fi
    
    log_info "Testing $count browsers against $hub_url"
    
    # Ensure browsers are running
    local running=$(podman ps --format '{{.Names}}' | grep -c "^${CONTAINER_PREFIX}-" || true)
    if [[ $running -lt $count ]]; then
        log_info "Starting $count browsers..."
        cmd_start --count "$count"
    fi
    
    # Test connections
    log_info "Connecting browsers to hub..."
    local connected=0
    
    for i in $(seq 1 $count); do
        local port=$((BASE_PORT + i))
        local join_url="${hub_url}/join"
        
        # Use browserless API to navigate
        local response=$(curl -s -X POST "http://127.0.0.1:${port}/goto" \
            -H "Content-Type: application/json" \
            -d "{\"url\": \"${join_url}\"}" 2>/dev/null || echo "")
        
        if [[ -n "$response" ]]; then
            connected=$((connected + 1))
            log_success "Browser-$i connected"
        else
            log_warn "Browser-$i failed to connect"
        fi
        
        sleep 1
    done
    
    log_info "$connected/$count browsers connected"
    
    # Monitor
    log_info "Monitoring for ${duration}s..."
    local start_time=$(date +%s)
    local end_time=$((start_time + duration))
    
    while [[ $(date +%s) -lt $end_time ]]; do
        local remaining=$((end_time - $(date +%s)))
        local mins=$((remaining / 60))
        local secs=$((remaining % 60))
        
        printf "\r  Remaining: %02d:%02d  " "$mins" "$secs"
        sleep 5
    done
    echo
    
    log_success "Test complete!"
    log_info "Check your Osk dashboard for observation data"
}

# Main
case "${1:-help}" in
    start)
        shift
        cmd_start "$@"
        ;;
    stop)
        shift
        cmd_stop "$@"
        ;;
    status)
        shift
        cmd_status "$@"
        ;;
    test)
        shift
        cmd_test "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
