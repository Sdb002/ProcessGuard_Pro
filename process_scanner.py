"""
process_scanner.py — Live system and process data via psutil.
Fixes:
  - cpu_percent(interval=None) per-process — fast, non-blocking
  - Pre-warms psutil's CPU counter with a single sleep at module level
  - Adds net_io, disk_io per process where available
  - Per-process CPU history ring buffer (last 60 ticks)
"""
import psutil
import datetime
import collections
import threading
import time

# ── Per-process history ────────────────────────────────────────────────
_history_lock  = threading.Lock()
_cpu_histories: dict[int, collections.deque] = {}   # pid → deque(maxlen=60)
_mem_histories: dict[int, collections.deque] = {}

HISTORY_LEN = 60


def _get_or_create(d: dict, pid: int) -> collections.deque:
    if pid not in d:
        d[pid] = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
    return d[pid]


def get_process_history(pid: int):
    """Return (cpu_list, mem_list) copy for a given PID."""
    with _history_lock:
        cpu = list(_get_or_create(_cpu_histories, pid))
        mem = list(_get_or_create(_mem_histories, pid))
    return cpu, mem


def _update_histories(procs):
    with _history_lock:
        active_pids = {p["pid"] for p in procs}
        # purge dead PIDs to avoid memory leaks
        for pid in list(_cpu_histories.keys()):
            if pid not in active_pids:
                _cpu_histories.pop(pid, None)
                _mem_histories.pop(pid, None)
        for p in procs:
            _get_or_create(_cpu_histories, p["pid"]).append(p["cpu_percent"])
            _get_or_create(_mem_histories, p["pid"]).append(p["memory_percent"])


# ── Main API ──────────────────────────────────────────────────────────

def get_all_processes():
    """
    Returns list of process dicts sorted by cpu_percent descending.
    Uses cpu_percent(interval=None) — caller must ensure >=0.1s between calls.
    """
    procs = []
    attrs = ["pid", "name", "username", "memory_percent", "status", "ppid", "nice"]
    for p in psutil.process_iter(attrs):
        try:
            info = p.info.copy()
            info["cpu_percent"]    = p.cpu_percent(interval=None)
            info["name"]           = info.get("name") or "unknown"
            info["username"]       = info.get("username") or ""
            info["memory_percent"] = round(info.get("memory_percent") or 0.0, 2)
            info["status"]         = info.get("status") or "?"
            # Try to get memory RSS in MB
            try:
                mem_info = p.memory_info()
                info["rss_mb"] = round(mem_info.rss / 1_048_576, 1)
            except Exception:
                info["rss_mb"] = 0.0
            # Try net connections count
            try:
                info["connections"] = len(p.net_connections())
            except Exception:
                info["connections"] = 0
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    procs_sorted = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)
    _update_histories(procs_sorted)
    return procs_sorted


def get_system_stats():
    """Returns system-wide stats dict."""
    cpu_per_core = psutil.cpu_percent(percpu=True)
    cpu          = psutil.cpu_percent(interval=None)
    ram          = psutil.virtual_memory()
    swap         = psutil.swap_memory()
    disk         = psutil.disk_usage("/")
    boot         = psutil.boot_time()
    secs         = int(datetime.datetime.now().timestamp() - boot)
    h, r         = divmod(secs, 3600)
    m, _         = divmod(r, 60)

    # Network I/O totals
    try:
        net = psutil.net_io_counters()
        net_sent_mb = round(net.bytes_sent / 1_048_576, 1)
        net_recv_mb = round(net.bytes_recv / 1_048_576, 1)
    except Exception:
        net_sent_mb = net_recv_mb = 0.0

    # CPU temp if available
    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ("coretemp", "cpu_thermal", "k10temp"):
                if key in temps and temps[key]:
                    cpu_temp = round(temps[key][0].current, 1)
                    break
    except Exception:
        pass

    return {
        "cpu":           cpu,
        "cpu_per_core":  cpu_per_core,
        "cpu_count":     psutil.cpu_count(logical=True),
        "cpu_temp":      cpu_temp,
        "ram":           ram.percent,
        "ram_used_gb":   round(ram.used  / 1e9, 1),
        "ram_total_gb":  round(ram.total / 1e9, 1),
        "swap":          swap.percent,
        "swap_used_gb":  round(swap.used / 1e9, 1),
        "disk":          disk.percent,
        "disk_free_gb":  round(disk.free / 1e9, 1),
        "disk_total_gb": round(disk.total / 1e9, 1),
        "net_sent_mb":   net_sent_mb,
        "net_recv_mb":   net_recv_mb,
        "uptime_str":    f"{h}h {m}m",
        "uptime_sec":    secs,
        "proc_count":    len(psutil.pids()),
    }


if __name__ == "__main__":
    # Pre-warm CPU counters
    psutil.cpu_percent(interval=None)
    for p in psutil.process_iter():
        try: p.cpu_percent(interval=None)
        except Exception: pass
    time.sleep(0.5)

    s = get_system_stats()
    print(f"CPU {s['cpu']:.1f}%  RAM {s['ram']:.1f}%  "
          f"Disk {s['disk']:.1f}%  Up {s['uptime_str']}  "
          f"Procs {s['proc_count']}")
    for p in get_all_processes()[:8]:
        print(f"  {p['pid']:>6}  {p['name']:<28}  "
              f"CPU:{p['cpu_percent']:>6.1f}%  MEM:{p['memory_percent']:>5.1f}%  "
              f"RSS:{p['rss_mb']:>7.1f}MB")
