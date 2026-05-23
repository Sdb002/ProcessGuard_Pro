"""
alert_engine.py — Desktop + log alerts for CPU, RAM, Disk.
Upgrades:
  - Disk alert added (was missing)
  - Thresholds from config (not hardcoded)
  - Structured log entries (JSON-lines) for in-app log viewer
  - Per-metric cooldown tracking
  - Callback hook for UI badge updates
"""
import logging
import os
import json
import time
import threading

import config

LOG_DIR  = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Human-readable alert log
_alert_logger = logging.getLogger("alerts")
_alert_logger.setLevel(logging.INFO)
if not _alert_logger.handlers:
    fh = logging.FileHandler(os.path.join(LOG_DIR, "alerts.log"))
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    _alert_logger.addHandler(fh)

# JSON-lines log for in-app viewer
_JSONL_PATH = os.path.join(LOG_DIR, "alerts.jsonl")

_lock  = threading.Lock()
_last  = {"cpu": 0.0, "ram": 0.0, "disk": 0.0}

# UI callback: set from main.py to receive (metric, value) on alert
_ui_callback = None


def set_ui_callback(fn):
    global _ui_callback
    _ui_callback = fn


def check_and_alert(stats: dict):
    now      = time.time()
    cooldown = config.get("alert_cooldown_sec") or 60.0

    checks = [
        ("cpu",  stats["cpu"],  config.get("cpu_alert_threshold")  or 85.0, "CPU"),
        ("ram",  stats["ram"],  config.get("ram_alert_threshold")  or 85.0, "RAM"),
        ("disk", stats["disk"], config.get("disk_alert_threshold") or 90.0, "DISK"),
    ]

    for key, value, thresh, label in checks:
        with _lock:
            last_time = _last.get(key, 0.0)
        if value > thresh and (now - last_time) > cooldown:
            _fire_alert(key, label, value, stats)
            with _lock:
                _last[key] = now


def _fire_alert(key: str, label: str, value: float, stats: dict):
    title = f"⚠ HIGH {label}"

    if key == "cpu":
        msg = f"CPU at {value:.1f}%"
    elif key == "ram":
        msg = f"RAM at {value:.1f}% ({stats.get('ram_used_gb', '?')}/{stats.get('ram_total_gb', '?')} GB)"
    else:
        msg = f"Disk at {value:.1f}% ({stats.get('disk_free_gb', '?')} GB free)"

    # Desktop notification
    _notify(title, msg)

    # Human log
    _alert_logger.warning(f"{label} ALERT  {value:.1f}%")

    # JSON-lines log
    entry = {
        "ts":    time.time(),
        "key":   key,
        "label": label,
        "value": value,
        "msg":   msg,
    }
    try:
        with open(_JSONL_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

    # UI hook
    if _ui_callback:
        try:
            _ui_callback(key, value, msg)
        except Exception:
            pass


def _notify(title: str, msg: str):
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, timeout=6)
    except Exception:
        print(f"[ALERT] {title}: {msg}")


def get_recent_alerts(n: int = 100) -> list[dict]:
    """Return the last n alert entries from the JSONL log."""
    entries = []
    try:
        with open(_JSONL_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return entries[-n:]


def clear_alerts():
    try:
        open(_JSONL_PATH, "w").close()
    except Exception:
        pass
