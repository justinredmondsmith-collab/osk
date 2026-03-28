#!/bin/bash
# Real Device Test Script
# Automates validation testing with Android phones

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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
Real Device Test - Automates validation with Android phones

USAGE:
    ./scripts/real_device_test.sh [command] [options]

COMMANDS:
    setup       Start Osk hub and show join info
    monitor     Monitor hub while testing (run in separate terminal)
    collect     Collect results and generate report
    stop        Stop hub and cleanup

EXAMPLES:
    # Terminal 1: Setup hub
    ./scripts/real_device_test.sh setup

    # Terminal 2: Monitor
    ./scripts/real_device_test.sh monitor

    # Join phones, wait 10-30 minutes...

    # Terminal 1: Collect results
    ./scripts/real_device_test.sh collect

    # Cleanup
    ./scripts/real_device_test.sh stop

REQUIREMENTS:
    - Android phone with Chrome
    - Phone and laptop on same WiFi
    - Phone battery at 50%+
EOF
}

OUTPUT_DIR=""
HUB_IP=""
DASHBOARD_CODE=""

cmd_setup() {
    log_info "Setting up Osk hub for real device test..."
    
    # Create output directory
    OUTPUT_DIR="${PROJECT_ROOT}/output/real-device-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$OUTPUT_DIR"
    log_info "Output directory: $OUTPUT_DIR"
    
    # Check if hub already running
    if osk status &> /dev/null; then
        log_warn "Hub already running, stopping..."
        osk stop 2>/dev/null || true
        sleep 2
    fi
    
    # Start hub
    log_info "Starting Osk hub..."
    osk start --fresh "Real Device Validation"
    
    # Get hub info
    HUB_IP=$(hostname -I | awk '{print $1}')
    log_info "Hub IP: $HUB_IP"
    
    # Get dashboard code
    log_info "Getting dashboard code..."
    DASHBOARD_INFO=$(osk dashboard 2>&1)
    DASHBOARD_CODE=$(echo "$DASHBOARD_INFO" | grep "dashboard_code =" | cut -d' ' -f3)
    
    # Save info
    cat > "$OUTPUT_DIR/test-info.txt" << EOF
Real Device Validation Test
============================
Date: $(date)
Hub IP: $HUB_IP
Dashboard Code: $DASHBOARD_CODE
Join URL: https://${HUB_IP}:8444/join

INSTRUCTIONS FOR PHONE:
1. Connect to same WiFi as laptop
2. Open Chrome
3. Go to: https://${HUB_IP}:8444/join
4. When SSL warning appears, tap "Advanced" → "Proceed"
5. Enter code: ${DASHBOARD_CODE}
6. Select "Sensor" role
7. Grant camera, mic, location permissions
8. Keep phone on and Chrome open for test duration

COORDINATOR COMMANDS:
- Check members: osk members
- View dashboard: https://${HUB_IP}:8444/coordinator
- Stop test: osk stop
EOF
    
    # Display info
    echo ""
    log_success "Hub ready!"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "                    JOIN INSTRUCTIONS"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  1. Connect your phone to WiFi"
  echo ""
    echo "  2. Open Chrome on phone"
    echo ""
    echo "  3. Navigate to:"
    echo "     ${GREEN}https://${HUB_IP}:8444/join${NC}"
    echo ""
    echo "  4. When SSL warning appears:"
    echo "     Tap Advanced → Proceed to [IP] (unsafe)"
    echo ""
    echo "  5. Enter code: ${GREEN}${DASHBOARD_CODE}${NC}"
    echo ""
    echo "  6. Select role: ${GREEN}Sensor${NC}"
    echo ""
    echo "  7. Grant all permissions (camera, mic, location)"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    log_info "Info saved to: $OUTPUT_DIR/test-info.txt"
    echo ""
    log_info "Next steps:"
    echo "  1. Join your phone(s) using instructions above"
    echo "  2. In another terminal, run: ./scripts/real_device_test.sh monitor"
    echo "  3. Test for 10-30 minutes"
    echo "  4. Run: ./scripts/real_device_test.sh collect"
}

cmd_monitor() {
    log_info "Monitoring hub resources..."
    log_info "Press Ctrl+C to stop"
    echo ""
    
    if [[ -z "${OUTPUT_DIR:-}" ]]; then
        # Try to find latest output directory
        OUTPUT_DIR=$(ls -td ${PROJECT_ROOT}/output/real-device-* 2>/dev/null | head -1 || true)
        if [[ -z "$OUTPUT_DIR" ]]; then
            OUTPUT_DIR="${PROJECT_ROOT}/output/real-device-monitor-$(date +%Y%m%d-%H%M%S)"
            mkdir -p "$OUTPUT_DIR"
        fi
    fi
    
    echo "timestamp,cpu_percent,memory_mb" > "$OUTPUT_DIR/hub-metrics.csv"
    
    while true; do
        HUB_PID=$(pgrep -f "osk hub" || true)
        if [[ -n "$HUB_PID" ]]; then
            CPU_MEM=$(ps -p "$HUB_PID" -o %cpu=,%mem= 2>/dev/null || echo "0.0,0.0")
            CPU=$(echo "$CPU_MEM" | awk '{print $1}')
            MEM_PERCENT=$(echo "$CPU_MEM" | awk '{print $2}')
            
            # Convert memory % to MB (rough estimate)
            TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
            MEM_MB=$(echo "$TOTAL_MEM * $MEM_PERCENT / 100" | bc -l 2>/dev/null || echo "0")
            
            echo "$(date +%Y-%m-%dT%H:%M:%S),$CPU,$MEM_MB" >> "$OUTPUT_DIR/hub-metrics.csv"
            
            # Show member count
            MEMBER_COUNT=$(osk members --json 2>/dev/null | grep -c '"name"' || echo "0")
            
            printf "\r  $(date +%H:%M:%S) | CPU: %5.1f%% | MEM: %6.1f MB | Members: %d  " \
                "$CPU" "$MEM_MB" "$MEMBER_COUNT"
        fi
        sleep 5
    done
}

cmd_collect() {
    log_info "Collecting test results..."
    
    # Find latest output directory
    OUTPUT_DIR=$(ls -td ${PROJECT_ROOT}/output/real-device-* 2>/dev/null | head -1 || true)
    if [[ -z "$OUTPUT_DIR" ]]; then
        log_error "No test output directory found"
        exit 1
    fi
    
    log_info "Using output directory: $OUTPUT_DIR"
    
    # Collect status
    log_info "Collecting hub status..."
    osk status --json > "$OUTPUT_DIR/final-status.json" 2>/dev/null || true
    
    # Collect members
    log_info "Collecting member data..."
    osk members --json > "$OUTPUT_DIR/members.json" 2>/dev/null || true
    
    # Export evidence
    log_info "Exporting evidence..."
    osk evidence export --output "$OUTPUT_DIR/evidence.zip" 2>/dev/null || true
    
    # Generate report
    log_info "Generating report..."
    cat > "$OUTPUT_DIR/RESULTS.md" << 'EOF'
# Real Device Validation Results

**Date:** TEST_DATE
**Hub IP:** HUB_IP
**Test Duration:** See metrics.csv

## Hub Performance

### CPU/Memory Usage
See: hub-metrics.csv

### Final Status
See: final-status.json

## Members

See: members.json

## Evidence

Exported: evidence.zip

## Phone Data

| Phone | Model | Android | Chrome | Battery Start | Battery End | Drain/Hour | Status |
|-------|-------|---------|--------|---------------|-------------|------------|--------|
| 1     |       |         |        |               |             |            |        |

## Conclusions

[Fill in after test]

## Sign-off

- [ ] All phones connected
- [ ] Data collected
- [ ] No critical errors
- [ ] Battery drain acceptable (<25%/hour)

**Result:** [PASS / FAIL]
EOF
    
    # Fill in template
    sed -i "s/TEST_DATE/$(date)/" "$OUTPUT_DIR/RESULTS.md"
    sed -i "s/HUB_IP/$(hostname -I | awk '{print $1}')/" "$OUTPUT_DIR/RESULTS.md"
    
    log_success "Results collected!"
    echo ""
    echo "Output files:"
    ls -la "$OUTPUT_DIR/"
    echo ""
    log_info "Edit $OUTPUT_DIR/RESULTS.md to add phone battery data"
}

cmd_stop() {
    log_info "Stopping test and cleaning up..."
    
    osk stop 2>/dev/null || true
    
    log_success "Hub stopped"
    log_info "Test complete! Check output directory for results"
}

# Main
case "${1:-help}" in
    setup)
        cmd_setup
        ;;
    monitor)
        cmd_monitor
        ;;
    collect)
        cmd_collect
        ;;
    stop)
        cmd_stop
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
