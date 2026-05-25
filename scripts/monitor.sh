#!/bin/bash
# scripts/monitor.sh — Cron-based process scanner (reads thresholds from config.json)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="$ROOT/logs/monitor.log"
CONFIG="$ROOT/config.json"

# Parse thresholds from config.json (requires jq; fallback to defaults)
if command -v jq &>/dev/null && [ -f "$CONFIG" ]; then
    THRESHOLD_CPU=$(jq -r '.cpu_alert_threshold // 85' "$CONFIG" | cut -d. -f1)
    THRESHOLD_MEM=$(jq -r '.ram_alert_threshold // 85' "$CONFIG" | cut -d. -f1)
else
    THRESHOLD_CPU=85
    THRESHOLD_MEM=85
fi

mkdir -p "$(dirname "$LOGFILE")"
echo "=== Scan: $(date)  CPU>${THRESHOLD_CPU}%  MEM>${THRESHOLD_MEM}% ===" >> "$LOGFILE"

ps aux --no-headers | awk '{print $1, $2, $3, $4, $11}' | \
while read user pid cpu mem cmd; do
    cpu_int="${cpu%.*}"
    mem_int="${mem%.*}"
    if [ "$cpu_int" -gt "$THRESHOLD_CPU" ] 2>/dev/null; then
        echo "  HIGH CPU: $cmd  PID=$pid  CPU=$cpu%  USER=$user" >> "$LOGFILE"
    fi
    if [ "$mem_int" -gt "$THRESHOLD_MEM" ] 2>/dev/null; then
        echo "  HIGH MEM: $cmd  PID=$pid  MEM=$mem%  USER=$user" >> "$LOGFILE"
    fi
done

echo "  Scan complete." >> "$LOGFILE"

# Rotate log if over 5 MB
LOG_SIZE=$(stat -c%s "$LOGFILE" 2>/dev/null || echo 0)
if [ "$LOG_SIZE" -gt 5242880 ]; then
    mv "$LOGFILE" "${LOGFILE}.1"
    echo "=== Log rotated: $(date) ===" > "$LOGFILE"
fi
