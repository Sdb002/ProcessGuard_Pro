#!/bin/bash
# scripts/kill_engine.sh — Cron-based auto-killer (reads config.json for rules)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="$ROOT/logs/kill_engine.log"
CONFIG="$ROOT/config.json"

mkdir -p "$(dirname "$LOGFILE")"
echo "=== Auto-Kill: $(date) ===" >> "$LOGFILE"

# Build whitelist from config.json (jq) or use hardcoded fallback
if command -v jq &>/dev/null && [ -f "$CONFIG" ]; then
    WHITELIST_JSON=$(jq -r '.whitelist // [] | .[]' "$CONFIG" 2>/dev/null)
else
    WHITELIST_JSON="systemd
sshd
bash
python3
Xorg
dbus
NetworkManager
code"
fi

is_whitelisted() {
    local cmd="$1"
    while IFS= read -r safe; do
        [[ "$cmd" == *"$safe"* ]] && return 0
    done <<< "$WHITELIST_JSON"
    return 1
}

# Process auto-kill rules from config.json
if command -v jq &>/dev/null && [ -f "$CONFIG" ]; then
    RULES=$(jq -c '.autokill_rules // [] | .[] | select(.enabled == true)' "$CONFIG" 2>/dev/null)
    if [ -n "$RULES" ]; then
        while IFS= read -r rule; do
            PATTERN=$(echo "$rule" | jq -r '.name_pattern')
            CPU_T=$(echo   "$rule" | jq -r '.cpu_thresh // 90' | cut -d. -f1)
            MEM_T=$(echo   "$rule" | jq -r '.mem_thresh // 0'  | cut -d. -f1)

            ps aux --no-headers | awk '{print $2, $3, $4, $11}' | \
            while read pid cpu mem cmd; do
                cpu_int="${cpu%.*}"
                mem_int="${mem%.*}"

                # Check pattern match
                if ! echo "$cmd" | grep -qiE "$PATTERN" 2>/dev/null; then continue; fi

                # Skip whitelisted
                is_whitelisted "$cmd" && continue

                # Check thresholds
                cpu_over=0; mem_over=0
                [ "$CPU_T" -gt 0 ] && [ "$cpu_int" -gt "$CPU_T" ] && cpu_over=1
                [ "$MEM_T" -gt 0 ] && [ "$mem_int" -gt "$MEM_T" ] && mem_over=1

                if [ "$cpu_over" -eq 1 ] || [ "$mem_over" -eq 1 ]; then
                    echo "  RULE-KILL: $cmd  PID=$pid  CPU=$cpu%  MEM=$mem%  pattern=$PATTERN" >> "$LOGFILE"
                    kill -TERM "$pid" 2>/dev/null
                    sleep 2
                    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
                fi
            done
        done <<< "$RULES"
    fi
fi

echo "  Done." >> "$LOGFILE"
