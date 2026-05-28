"""
config.py — Centralized configuration with JSON persistence.
All thresholds, whitelist, auto-kill rules, and UI prefs live here.
"""
import json, os, threading

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULTS = {
    "cpu_alert_threshold":  85.0,
    "ram_alert_threshold":  85.0,
    "disk_alert_threshold": 90.0,
    "alert_cooldown_sec":   60.0,
    "refresh_interval_sec": 2.0,
    "autokill_rules": [],          # list of {name_pattern, cpu_thresh, mem_thresh, duration_sec}
    "whitelist": [
        "systemd", "init", "sshd", "bash", "sh", "python3",
        "dearpygui", "main.py", "Xorg", "dbus-daemon",
        "NetworkManager", "code", "gnome", "kwin", "plasmashell"
    ],
    "theme": "dark_green",
    "max_table_rows": 200,
    "report_top_n": 50,
}

_cfg   = {}
_lock  = threading.Lock()


def load():
    global _cfg
    with _lock:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    saved = json.load(f)
                _cfg = {**DEFAULTS, **saved}
                return
            except Exception:
                pass
        _cfg = dict(DEFAULTS)
        _save_unlocked()


def save():
    with _lock:
        _save_unlocked()


def _save_unlocked():
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(_cfg, f, indent=2)
    except Exception as e:
        print(f"[config] save failed: {e}")


def get(key, default=None):
    with _lock:
        return _cfg.get(key, default)


def set(key, value):
    with _lock:
        _cfg[key] = value
    save()


def get_all():
    with _lock:
        return dict(_cfg)


def add_autokill_rule(name_pattern: str, cpu_thresh: float, mem_thresh: float, duration_sec: int):
    with _lock:
        rules = _cfg.get("autokill_rules", [])
        rules.append({
            "name_pattern": name_pattern,
            "cpu_thresh":   cpu_thresh,
            "mem_thresh":   mem_thresh,
            "duration_sec": duration_sec,
            "enabled":      True,
        })
        _cfg["autokill_rules"] = rules
    save()


def remove_autokill_rule(index: int):
    with _lock:
        rules = _cfg.get("autokill_rules", [])
        if 0 <= index < len(rules):
            rules.pop(index)
        _cfg["autokill_rules"] = rules
    save()


def toggle_autokill_rule(index: int):
    with _lock:
        rules = _cfg.get("autokill_rules", [])
        if 0 <= index < len(rules):
            rules[index]["enabled"] = not rules[index].get("enabled", True)
        _cfg["autokill_rules"] = rules
    save()


# Load on import
load()
