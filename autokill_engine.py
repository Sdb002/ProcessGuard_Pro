"""
autokill_engine.py — Rule-based auto-kill engine.
Rules defined in config.json → autokill_rules list.
Each rule: { name_pattern, cpu_thresh, mem_thresh, duration_sec, enabled }
A process must *continuously* exceed the threshold for duration_sec before being killed.
"""
import re
import time
import logging
import os
import threading
import psutil

import config
import kill_manager

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_ak_logger = logging.getLogger("autokill")
_ak_logger.setLevel(logging.INFO)
if not _ak_logger.handlers:
    fh = logging.FileHandler(os.path.join(LOG_DIR, "autokill.log"))
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    _ak_logger.addHandler(fh)

# pid → { rule_index → first_violation_timestamp }
_violation_start: dict[int, dict[int, float]] = {}
_lock = threading.Lock()

# UI callback: called when a process is auto-killed
_ui_callback = None


def set_ui_callback(fn):
    global _ui_callback
    _ui_callback = fn


def check_processes(procs: list[dict]):
    """
    Called on every refresh tick with the current process list.
    Checks each enabled rule against each process.
    """
    rules = config.get("autokill_rules") or []
    if not rules:
        return

    active_pids = {p["pid"] for p in procs}

    with _lock:
        # Purge dead PIDs
        for pid in list(_violation_start.keys()):
            if pid not in active_pids:
                del _violation_start[pid]

    for proc in procs:
        pid  = proc["pid"]
        name = proc["name"]

        # Never auto-kill whitelisted processes
        if kill_manager._is_whitelisted(name):
            continue

        for idx, rule in enumerate(rules):
            if not rule.get("enabled", True):
                continue

            pattern      = rule.get("name_pattern", "")
            cpu_thresh   = float(rule.get("cpu_thresh",   0))
            mem_thresh   = float(rule.get("mem_thresh",   0))
            duration_sec = float(rule.get("duration_sec", 30))

            # Match name
            try:
                if not re.search(pattern, name, re.IGNORECASE):
                    continue
            except re.error:
                continue

            # Check thresholds
            cpu_over = cpu_thresh > 0 and proc["cpu_percent"] >= cpu_thresh
            mem_over = mem_thresh > 0 and proc["memory_percent"] >= mem_thresh
            triggered = cpu_over or mem_over

            with _lock:
                if triggered:
                    pid_map = _violation_start.setdefault(pid, {})
                    if idx not in pid_map:
                        pid_map[idx] = time.time()
                    elif time.time() - pid_map[idx] >= duration_sec:
                        # Time exceeded — kill it
                        _execute_kill(pid, name, rule, proc)
                        pid_map.pop(idx, None)
                else:
                    # Not currently violating — reset timer
                    _violation_start.get(pid, {}).pop(idx, None)


def _execute_kill(pid: int, name: str, rule: dict, proc: dict):
    ok, msg = kill_manager.kill_process(pid, graceful=True)
    reason = (
        f"rule='{rule.get('name_pattern')}' "
        f"cpu={proc['cpu_percent']:.1f}% "
        f"mem={proc['memory_percent']:.1f}% "
        f"duration={rule.get('duration_sec')}s"
    )
    if ok:
        _ak_logger.info(f"AUTO-KILLED  PID={pid} name={name}  {reason}")
    else:
        _ak_logger.warning(f"AUTO-KILL FAILED  PID={pid} name={name}  {reason}  err={msg}")

    if _ui_callback:
        try:
            _ui_callback(pid, name, ok, msg, rule)
        except Exception:
            pass


def get_violation_timers(procs: list[dict]) -> dict[int, dict]:
    """
    Returns { pid: { rule_idx: elapsed_sec } } for in-progress violations.
    Used by the UI to show countdown bars.
    """
    result = {}
    now = time.time()
    with _lock:
        for pid, rule_map in _violation_start.items():
            result[pid] = {idx: round(now - ts, 1) for idx, ts in rule_map.items()}
    return result
