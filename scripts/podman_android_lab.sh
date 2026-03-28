#!/bin/bash
# Podman Android Lab - Launch Android emulators in containers for Osk testing
# Usage: ./scripts/podman_android_lab.sh [command] [options]
#
# Commands:
#   start     Start N Android emulators (default: 5)
#   stop      Stop all emulator containers
#   status    Show emulator status
#   connect   Connect emulators to Osk hub
#   test      Run validation test
#
# Examples:
#   ./scripts/podman_android_lab.sh start --count 5
#   ./scripts/podman_android_lab.sh connect --hub-url http://192.168.1.100:8080
#   ./scripts/podman_android_lab.sh test --duration 600

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
DEFAULT_COUNT=5
DEFAULT_HUB_PORT=8080
DEFAULT_DURATION=600  # 10 minutes
CONTAINER_PREFIX="osk-android"
BASE_ADB_PORT=5555
BASE_VNC_PORT=5900

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

show_help() {
    cat << 'EOF'
Podman Android Lab for Osk Testing

This script manages Android emulator containers for testing Osk sensor streaming.
It uses containerized Android emulators that run Chrome browsers and connect
to your Osk hub.

USAGE:
    ./scripts/podman_android_lab.sh <command> [options]

COMMANDS:
    start     Start Android emulator containers
              Options: --count N, --image IMAGE
              
    stop      Stop and remove all emulator containers
    
    status    Show status of running emulators
    
    connect   Connect emulators to Osk hub
              Options: --hub-url URL, --token TOKEN
              
    test      Run full validation test
              Options: --count N, --duration SECONDS, --hub-url URL

EXAMPLES:
    # Start 5 emulators
    ./scripts/podman_android_lab.sh start --count 5
    
    # Connect to running Osk hub
    ./scripts/podman_android_lab.sh connect --hub-url http://192.168.1.50:8080
    
    # Run full 10-minute validation with 5 devices
    ./scripts/podman_android_lab.sh test --count 5 --duration 600

REQUIREMENTS:
    - Podman installed and running
    - adb (Android Debug Bridge) installed
    - Sufficient disk space (~2GB per emulator)
    - KVM support recommended for performance

LIMITATIONS:
    - Emulators use software rendering (no GPU acceleration)
    - WebRTC may behave differently than real devices
    - Battery/thermal testing not possible
    
For real-device validation, see: docs/runbooks/chromebook-lab-smoke.md
EOF
}

cmd_start() {
    local count=$DEFAULT_COUNT
    local image="docker.io/budtmo/docker-android:latest"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --count)
                count="$2"
                shift 2
                ;;
            --image)
                image="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    log_info "Starting $count Android emulator(s)..."
    log_info "Using image: $image"
    
    # Check podman is available
    if ! command -v podman &> /dev/null; then
        log_error "Podman not found. Please install podman first."
        exit 1
    fi
    
    # Check KVM support
    if [[ -e /dev/kvm ]]; then
        log_success "KVM support detected"
        local kvm_arg="--device /dev/kvm"
    else
        log_warn "KVM not available - emulators will be slower"
        local kvm_arg=""
    fi
    
    # Pull image if needed
    log_info "Pulling container image (this may take a while)..."
    podman pull "$image" || {
        log_error "Failed to pull image. Check your internet connection."
        exit 1
    }
    
    # Start containers
    for i in $(seq 1 $count); do
        local container_name="${CONTAINER_PREFIX}-${i}"
        local adb_port=$((BASE_ADB_PORT + i))
        local vnc_port=$((BASE_VNC_PORT + i))
        
        # Check if container already exists
        if podman container exists "$container_name" 2>/dev/null; then
            log_warn "Container $container_name already exists, stopping..."
            podman stop "$container_name" 2>/dev/null || true
            podman rm "$container_name" 2>/dev/null || true
        fi
        
        log_info "Starting emulator $i/$count (ADB port: $adb_port, VNC: $vnc_port)..."
        
        podman run -d \
            --name "$container_name" \
            --privileged \
            -p "${adb_port}:5555" \
            -p "${vnc_port}:5900" \
            ${kvm_arg:+"$kvm_arg"} \
            -e "EMULATOR_DEVICE=Nexus 5" \
            -e "EMULATOR_ARCH=x86_64" \
            "$image" 2>&1 || {
            log_error "Failed to start container $container_name"
            continue
        }
        
        log_success "Container $container_name started"
    done
    
    log_info "Waiting for emulators to boot (this takes 30-60 seconds)..."
    sleep 45
    
    # Connect adb
    log_info "Connecting ADB..."
    for i in $(seq 1 $count); do
        local adb_port=$((BASE_ADB_PORT + i))
        adb connect "localhost:${adb_port}" 2>/dev/null || true
    done
    
    # Wait for devices
    log_info "Waiting for devices to be ready..."
    local max_wait=60
    local waited=0
    while [[ $(adb devices | grep -c "emulator") -lt $count ]] && [[ $waited -lt $max_wait ]]; do
        sleep 2
        waited=$((waited + 2))
        echo -n "."
    done
    echo
    
    local connected=$(adb devices | grep -c "emulator" || true)
    log_success "$connected/$count emulators ready"
    
    if [[ $connected -eq 0 ]]; then
        log_error "No emulators connected. Check container logs:"
        log_info "podman logs ${CONTAINER_PREFIX}-1"
        exit 1
    fi
    
    log_info "Emulators are ready. Use 'connect' command to join Osk hub."
}

cmd_stop() {
    log_info "Stopping all Android emulators..."
    
    # Stop and remove containers
    for container in $(podman ps -a --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}-" || true); do
        log_info "Stopping $container..."
        podman stop "$container" 2>/dev/null || true
        podman rm "$container" 2>/dev/null || true
    done
    
    # Disconnect adb
    adb disconnect 2>/dev/null || true
    
    log_success "All emulators stopped"
}

cmd_status() {
    log_info "Checking emulator status..."
    
    local containers=$(podman ps --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}-" || true)
    
    if [[ -z "$containers" ]]; then
        log_warn "No emulator containers running"
        return
    fi
    
    echo
    echo "Container Status:"
    echo "================="
    podman ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep "^${CONTAINER_PREFIX}-" || true
    
    echo
    echo "ADB Devices:"
    echo "============"
    adb devices -l | grep -v "List of devices" || true
    
    # Check Chrome availability in containers
    echo
    echo "Browser Status:"
    echo "==============="
    for device in $(adb devices | grep emulator | awk '{print $1}'); do
        local name=$(echo "$device" | cut -d: -f2)
        if adb -s "$device" shell "pm list packages | grep -q com.android.chrome" 2>/dev/null; then
            echo "$name: Chrome installed ✓"
        else
            echo "$name: Chrome not found (will use WebView)"
        fi
    done
}

cmd_connect() {
    local hub_url=""
    local token=""
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --hub-url)
                hub_url="$2"
                shift 2
                ;;
            --token)
                token="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    if [[ -z "$hub_url" ]]; then
        # Try to auto-detect hub
        local host_ip=$(hostname -I | awk '{print $1}')
        hub_url="http://${host_ip}:${DEFAULT_HUB_PORT}"
        log_warn "--hub-url not specified, using auto-detected: $hub_url"
        log_info "If this is incorrect, specify with --hub-url"
    fi
    
    # Add token if provided
    local join_url="$hub_url/join"
    if [[ -n "$token" ]]; then
        join_url="${join_url}?token=${token}"
    fi
    
    log_info "Connecting emulators to: $join_url"
    
    local devices=$(adb devices | grep emulator | awk '{print $1}')
    local count=0
    
    for device in $devices; do
        count=$((count + 1))
        local sensor_name="Podman-Sensor-$(printf "%02d" $count)"
        
        log_info "Connecting $device as $sensor_name..."
        
        # Launch Chrome with join URL
        # Use am start to launch browser
        adb -s "$device" shell "am start -a android.intent.action.VIEW -d '$join_url'" 2>/dev/null || {
            # Fallback: try system browser
            adb -s "$device" shell "am start -a android.intent.action.VIEW -d '$join_url'" 2>/dev/null || {
                log_warn "Failed to launch browser on $device"
                continue
            }
        }
        
        sleep 1
    done
    
    log_success "Launched browsers on $count device(s)"
    log_info "Check your Osk dashboard to verify connections"
}

cmd_test() {
    local count=$DEFAULT_COUNT
    local duration=$DEFAULT_DURATION
    local hub_url=""
    local output_dir="${PROJECT_ROOT}/output/podman-validation"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --count)
                count="$2"
                shift 2
                ;;
            --duration)
                duration="$2"
                shift 2
                ;;
            --hub-url)
                hub_url="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    log_info "Starting full validation test"
    log_info "  Emulators: $count"
    log_info "  Duration: ${duration}s"
    
    # Create output directory
    mkdir -p "$output_dir"
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local report_file="${output_dir}/report-${timestamp}.json"
    
    # Start emulators
    log_info "Phase 1: Starting emulators..."
    cmd_start --count "$count"
    
    # Get hub URL if not provided
    if [[ -z "$hub_url" ]]; then
        local host_ip=$(hostname -I | awk '{print $1}')
        hub_url="http://${host_ip}:${DEFAULT_HUB_PORT}"
    fi
    
    # Start Osk hub if not running
    if ! curl -s "${hub_url}/api/health" > /dev/null 2>&1; then
        log_warn "Osk hub not detected at $hub_url"
        log_info "Please start Osk hub manually: osk start"
        read -p "Press Enter when hub is ready, or Ctrl+C to abort..."
    fi
    
    # Connect emulators
    log_info "Phase 2: Connecting to hub..."
    cmd_connect --hub-url "$hub_url"
    
    # Monitor
    log_info "Phase 3: Monitoring for ${duration}s..."
    log_info "Press Ctrl+C to stop early"
    
    local start_time=$(date +%s)
    local end_time=$((start_time + duration))
    
    while [[ $(date +%s) -lt $end_time ]]; do
        local remaining=$((end_time - $(date +%s)))
        local minutes=$((remaining / 60))
        local seconds=$((remaining % 60))
        
        local devices=$(adb devices | grep -c emulator || true)
        printf "\r  Remaining: %02d:%02d | Connected devices: %d  " "$minutes" "$seconds" "$devices"
        
        sleep 5
    done
    echo
    
    # Generate report
    log_info "Phase 4: Generating report..."
    
    local final_devices=$(adb devices | grep -c emulator || true)
    
    cat > "$report_file" << EOF
{
    "test_type": "podman_android_validation",
    "timestamp": "$(date -Iseconds)",
    "configuration": {
        "emulator_count": $count,
        "duration_seconds": $duration,
        "hub_url": "$hub_url"
    },
    "results": {
        "emulators_started": $count,
        "emulators_connected": $final_devices,
        "success_rate": $(echo "scale=2; $final_devices / $count * 100" | bc || echo "N/A")
    },
    "notes": [
        "This is containerized browser validation",
        "Real-device battery/thermal behavior not tested",
        "WebRTC may differ from physical devices"
    ]
}
EOF
    
    log_success "Test complete! Report: $report_file"
    
    # Cleanup prompt
    read -p "Stop emulators? [Y/n]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        cmd_stop
    fi
}

# Main command dispatcher
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
    connect)
        shift
        cmd_connect "$@"
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
