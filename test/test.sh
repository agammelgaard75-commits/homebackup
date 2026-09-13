#!/bin/bash

# Verify Nginx Installation Prerequisites

set -e

OUTPUT_FILE="prereq_report.txt"
ERRORS=0

check_ubuntu_version() {
    echo "=== Checking Ubuntu Version ==="
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        VERSION_ID=$(echo $VERSION_ID | cut -d. -f1)
        echo "Detected OS: ${PRETTY_NAME}"
        echo "Ubuntu Version: 24.${VERSION_ID}"
        
        if [ "$VERSION_ID" = "24" ]; then
            echo "[OK] Ubuntu 24.x confirmed"
        else
            echo "[WARN] Expected Ubuntu 24.04, found ${PRETTY_NAME}"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "[ERROR] /etc/os-release not found"
        ERRORS=$((ERRORS + 1))
    fi
}

check_network_connectivity() {
    echo ""
    echo "=== Checking Network Connectivity ==="
    
    if command -v curl >/dev/null 2>&1; then
        if curl -s --connect-timeout 5 https://www.google.com > /dev/null 2>&1; then
            echo "[OK] HTTPS connectivity verified"
        else
            echo "[WARN] HTTPS connectivity failed, trying HTTP"
            if curl -s --connect-timeout 5 http://www.google.com > /dev/null 2>&1; then
                echo "[OK] HTTP connectivity verified"
            else
                echo "[ERROR] No network connectivity detected"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget --spider -q --timeout=5 https://www.google.com 2>/dev/null; then
            echo "[OK] HTTPS connectivity verified (via wget)"
        else
            echo "[WARN] HTTPS failed, trying HTTP"
            if wget --spider -q --timeout=5 http://www.google.com 2>/dev/null; then
                echo "[OK] HTTP connectivity verified (via wget)"
            else
                echo "[ERROR] No network connectivity detected"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    elif command -v ping >/dev/null 2>&1; then
        if ping -c 1 -W 5 google.com > /dev/null 2>&1; then
            echo "[OK] Network connectivity verified (via ping)"
        else
            echo "[ERROR] Cannot verify network connectivity"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "[WARN] No network tools available for verification"
    fi
}

check_disk_space() {
    echo ""
    echo "=== Checking Disk Space ==="
    
    if command -v df >/dev/null 2>&1; then
        ROOT_SPACE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
        ROOT_SIZE=$(df / | awk 'NR==2 {print $4}')
        echo "Root filesystem: ${ROOT_SIZE} (${ROOT_SPACE}% used)"
        
        if [ "$ROOT_SPACE" -lt 90 ]; then
            echo "[OK] Sufficient disk space available (>=10% free)"
        else
            echo "[WARN] Disk usage is high (${ROOT_SPACE}% used)"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "[WARN] Cannot check disk space (df not found)"
    fi
}

check_required_commands() {
    echo ""
    echo "=== Checking Required Commands ==="
    
    REQUIRED=("curl" "wget" "ping" "df")
    for cmd in "${REQUIRED[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "[OK] $cmd is available"
        else
            echo "[WARN] $cmd not found (optional)"
        fi
    done
}

generate_report() {
    echo ""
    echo "=== Prerequisites Report ==="
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Hostname: $(hostname 2>/dev/null || echo 'unknown')"
    echo ""
}

# Main execution
generate_report
check_ubuntu_version
check_network_connectivity
check_disk_space
check_required_commands

# Final summary
echo ""
echo "=== Summary ==="
if [ $ERRORS -eq 0 ]; then
    echo "[SUCCESS] All prerequisites verified. Ready for nginx installation."
else
    echo "[PARTIAL] Found ${ERRORS} issue(s). Review warnings above."
fi
