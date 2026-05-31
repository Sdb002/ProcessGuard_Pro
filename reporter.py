"""
reporter.py — Generates timestamped HTML reports with trend charts.
Upgrades:
  - SQLite history store (stats logged every tick)
  - Reports include 24-hour trend sparklines via inline SVG
  - Top-N configurable from config.json
  - Alert summary section
"""
import psutil
import os
import datetime
import sqlite3
import json
import threading
import time

import config
from alert_engine import get_recent_alerts

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
DB_PATH     = os.path.join(os.path.dirname(__file__), "logs", "history.db")
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_db_lock = threading.Lock()


# ── SQLite history ────────────────────────────────────────────────────

def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS stats (
        ts    REAL PRIMARY KEY,
        cpu   REAL, ram REAL, disk REAL,
        procs INTEGER
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON stats(ts)")
    conn.commit()
    return conn


def log_stats(stats: dict):
    """Call this on every refresh tick to record system stats."""
    try:
        with _db_lock:
            conn = _get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO stats VALUES (?,?,?,?,?)",
                (time.time(), stats["cpu"], stats["ram"], stats["disk"], stats["proc_count"])
            )
            conn.commit()
            conn.close()
            # Prune rows older than 7 days
            if int(time.time()) % 300 == 0:
                _prune_old(days=7)
    except Exception as e:
        print(f"[reporter] log_stats error: {e}")


def _prune_old(days: int = 7):
    cutoff = time.time() - days * 86400
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM stats WHERE ts < ?", (cutoff,))
        conn.commit()
        conn.close()


def get_history(hours: int = 24) -> list[tuple]:
    """Return (ts, cpu, ram, disk) rows for the last N hours."""
    since = time.time() - hours * 3600
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT ts, cpu, ram, disk FROM stats WHERE ts >= ? ORDER BY ts",
            (since,)
        ).fetchall()
        conn.close()
    return rows


# ── SVG sparkline ──────────────────────────────────────────────────────

def _sparkline(values: list[float], color: str, width=300, height=50) -> str:
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    vmin, vmax = 0, 100
    xs = [i / (len(values) - 1) * width for i in range(len(values))]
    ys = [height - (v - vmin) / (vmax - vmin) * height for v in values]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (
        f'<svg width="{width}" height="{height}" style="display:block">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'</svg>'
    )


# ── HTML report generator ──────────────────────────────────────────────

def generate_report() -> str:
    now    = datetime.datetime.now()
    top_n  = config.get("report_top_n") or 50
    cpu    = psutil.cpu_percent(interval=1)
    ram    = psutil.virtual_memory()
    disk   = psutil.disk_usage("/")
    swap   = psutil.swap_memory()

    # Process snapshot
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent",
                                   "memory_percent", "status"]):
        try:
            i = p.info.copy()
            i["cpu_percent"] = p.cpu_percent(interval=0.02)
            procs.append(i)
        except Exception:
            pass
    procs = sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:top_n]

    # History for sparklines
    history = get_history(hours=24)
    cpu_hist  = [r[1] for r in history][-120:]
    ram_hist  = [r[2] for r in history][-120:]
    disk_hist = [r[3] for r in history][-120:]

    sp_cpu  = _sparkline(cpu_hist,  "#00ff88")
    sp_ram  = _sparkline(ram_hist,  "#00aaff")
    sp_disk = _sparkline(disk_hist, "#ffaa00")

    # Recent alerts
    alerts     = get_recent_alerts(20)
    alert_rows = ""
    for a in reversed(alerts):
        ts  = datetime.datetime.fromtimestamp(a["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        col = "#ff5555" if a["key"] == "cpu" else ("#ffaa00" if a["key"] == "ram" else "#ffcc00")
        alert_rows += (
            f"<tr><td style='color:#667'>{ts}</td>"
            f"<td style='color:{col};font-weight:bold'>{a['label']}</td>"
            f"<td>{a['value']:.1f}%</td>"
            f"<td style='color:#99b'>{a['msg']}</td></tr>"
        )

    # Process rows
    proc_rows = ""
    for i, p in enumerate(procs):
        bg  = "#0f1a14" if i % 2 == 0 else "#121f18"
        cpu_v = p.get("cpu_percent") or 0
        mem_v = p.get("memory_percent") or 0
        c_col = "#ff5555" if cpu_v > 70 else ("#ffaa00" if cpu_v > 40 else "#00cc88")
        proc_rows += (
            f"<tr style='background:{bg}'>"
            f"<td>{p.get('pid','')}</td>"
            f"<td>{(p.get('name') or '')[:35]}</td>"
            f"<td style='color:{c_col};font-weight:bold'>{cpu_v:.1f}%</td>"
            f"<td>{mem_v:.1f}%</td>"
            f"<td style='color:#778'>{p.get('status','')}</td>"
            f"<td style='color:#667'>{(p.get('username') or '')[:20]}</td></tr>"
        )

    # Autokill rules
    rules     = config.get("autokill_rules") or []
    rule_rows = ""
    for r in rules:
        status = "✓ Enabled" if r.get("enabled", True) else "✗ Disabled"
        rule_rows += (
            f"<tr><td>{r.get('name_pattern','')}</td>"
            f"<td>{r.get('cpu_thresh',0)}%</td>"
            f"<td>{r.get('mem_thresh',0)}%</td>"
            f"<td>{r.get('duration_sec',30)}s</td>"
            f"<td style='color:#00cc88'>{status}</td></tr>"
        )
    if not rule_rows:
        rule_rows = "<tr><td colspan='5' style='color:#445'>No auto-kill rules defined</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>ProcessGuard Pro — {now.strftime('%Y-%m-%d %H:%M')}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0f0d;color:#c0d8c8;font-family:'Courier New',monospace;padding:32px;line-height:1.5}}
  h1{{color:#00ff88;letter-spacing:3px;margin-bottom:4px;font-size:22px}}
  h2{{color:#00cc66;letter-spacing:2px;font-size:14px;margin:28px 0 12px;border-bottom:1px solid #1a3028;padding-bottom:6px}}
  p.sub{{color:#447055;font-size:12px;margin-bottom:20px}}
  .cards{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}}
  .card{{background:#0f1a14;border:1px solid #1a3028;border-radius:8px;padding:14px 20px;min-width:160px}}
  .card .v{{font-size:28px;font-weight:bold;color:#00ff88}}
  .card .l{{font-size:10px;color:#447055;letter-spacing:1px;margin-top:4px}}
  .card .spark{{margin-top:8px}}
  table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:24px}}
  th{{background:#0f1a14;color:#00cc66;text-align:left;padding:8px 12px;border-bottom:2px solid #1a3028;letter-spacing:1px;font-size:10px;text-transform:uppercase}}
  td{{padding:6px 12px;border-bottom:1px solid #0c1510;vertical-align:middle}}
  footer{{color:#2a4a38;font-size:10px;margin-top:32px;text-align:center}}
</style></head><body>
<h1>⚙ ProcessGuard Pro — System Report</h1>
<p class="sub">{now.strftime('%A, %B %d %Y  ·  %H:%M:%S')}  ·  Auto-generated</p>

<h2>System Overview</h2>
<div class="cards">
  <div class="card"><div class="v">{cpu:.1f}%</div><div class="l">CPU USAGE</div><div class="spark">{sp_cpu}</div></div>
  <div class="card"><div class="v">{ram.percent:.1f}%</div><div class="l">RAM  {round(ram.used/1e9,1)}/{round(ram.total/1e9,1)} GB</div><div class="spark">{sp_ram}</div></div>
  <div class="card"><div class="v">{disk.percent:.1f}%</div><div class="l">DISK  {round(disk.free/1e9,1)} GB free</div><div class="spark">{sp_disk}</div></div>
  <div class="card"><div class="v">{swap.percent:.1f}%</div><div class="l">SWAP  {round(swap.used/1e9,1)}/{round(swap.total/1e9,1)} GB</div></div>
  <div class="card"><div class="v">{len(procs)}</div><div class="l">TOP PROCESSES SHOWN</div></div>
</div>

<h2>Recent Alerts</h2>
<table>
  <thead><tr><th>Time</th><th>Metric</th><th>Value</th><th>Message</th></tr></thead>
  <tbody>{alert_rows if alert_rows else "<tr><td colspan='4' style='color:#445'>No alerts recorded</td></tr>"}</tbody>
</table>

<h2>Auto-Kill Rules</h2>
<table>
  <thead><tr><th>Pattern</th><th>CPU&nbsp;Thresh</th><th>Mem&nbsp;Thresh</th><th>Duration</th><th>Status</th></tr></thead>
  <tbody>{rule_rows}</tbody>
</table>

<h2>Top {top_n} Processes by CPU</h2>
<table>
  <thead><tr><th>PID</th><th>Name</th><th>CPU%</th><th>MEM%</th><th>Status</th><th>User</th></tr></thead>
  <tbody>{proc_rows}</tbody>
</table>

<footer>ProcessGuard Pro · {now.strftime('%Y-%m-%d %H:%M:%S')} · Auto-generated</footer>
</body></html>"""

    path = os.path.join(REPORTS_DIR, f"report_{now.strftime('%Y%m%d_%H%M%S')}.html")
    with open(path, "w") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    print("Report saved:", generate_report())
