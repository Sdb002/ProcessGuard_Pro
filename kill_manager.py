"""
kill_manager.py — Safely kill, suspend, or resume processes.
Upgrades:
  - Whitelist loaded from config (not hardcoded)
  - Whitelist entries match whole process names (case-insensitive), with
    shell-style globs: "sh" protects sh but not flash_worker; "gnome-*"
    protects gnome-shell, gnome-session, ...
  - Kills by signal (SIGTERM first, then SIGKILL after grace period)
  - Returns structured result dict
"""
import fnmatch
import psutil
import time
import logging
import os

import config

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "kill.log"),
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
)


def _is_whitelisted(name: str) -> bool:
    """True when `name` is a whitelisted process name or matches a glob.

    Whole-name matching: the old substring search made "sh" protect every
    process with "sh" anywhere in its name (flash_worker, refresh-daemon,
    crashpad_handler), so auto-kill silently skipped them.
    """
    name = (name or "").lower()
    for entry in config.get("whitelist") or []:
        if fnmatch.fnmatchcase(name, entry.strip().lower()):
            return True
    return False


def _result(ok: bool, msg: str) -> tuple[bool, str]:
    return ok, msg


def kill_process(pid: int, graceful: bool = True) -> tuple[bool, str]:
    """
    Kill a process. If graceful=True, sends SIGTERM first then waits 2s,
    then escalates to SIGKILL if still alive.
    """
    try:
        p    = psutil.Process(pid)
        name = p.name()
        if _is_whitelisted(name):
            return _result(False, f"'{name}' is whitelisted — not killed.")
        if graceful:
            p.terminate()
            try:
                p.wait(timeout=2)
                logging.info(f"TERM  PID={pid} name={name}")
                return _result(True, f"Terminated '{name}' (PID {pid})")
            except psutil.TimeoutExpired:
                pass
        p.kill()
        logging.info(f"KILL  PID={pid} name={name}")
        return _result(True, f"Killed '{name}' (PID {pid})")
    except psutil.NoSuchProcess:
        return _result(False, f"PID {pid} no longer exists.")
    except psutil.AccessDenied:
        return _result(False, f"Access denied — try: sudo python3 main.py")
    except Exception as e:
        return _result(False, str(e))


def suspend_process(pid: int) -> tuple[bool, str]:
    try:
        p    = psutil.Process(pid)
        name = p.name()
        if _is_whitelisted(name):
            return _result(False, f"'{name}' is whitelisted — not suspended.")
        p.suspend()
        logging.info(f"SUSP  PID={pid} name={name}")
        return _result(True, f"Suspended '{name}' (PID {pid})")
    except psutil.NoSuchProcess:
        return _result(False, f"PID {pid} not found.")
    except psutil.AccessDenied:
        return _result(False, f"Access denied for PID {pid}.")
    except Exception as e:
        return _result(False, str(e))


def resume_process(pid: int) -> tuple[bool, str]:
    try:
        p    = psutil.Process(pid)
        name = p.name()
        p.resume()
        logging.info(f"RESU  PID={pid} name={name}")
        return _result(True, f"Resumed '{name}' (PID {pid})")
    except psutil.NoSuchProcess:
        return _result(False, f"PID {pid} not found.")
    except psutil.AccessDenied:
        return _result(False, f"Access denied for PID {pid}.")
    except Exception as e:
        return _result(False, str(e))


def nice_process(pid: int, niceness: int) -> tuple[bool, str]:
    """Renice a process (-20 highest priority, 19 lowest)."""
    try:
        p = psutil.Process(pid)
        p.nice(max(-20, min(19, niceness)))
        return _result(True, f"Set nice={niceness} on '{p.name()}' (PID {pid})")
    except psutil.AccessDenied:
        return _result(False, f"Access denied — sudo required to lower niceness.")
    except psutil.NoSuchProcess:
        return _result(False, f"PID {pid} not found.")
    except Exception as e:
        return _result(False, str(e))
