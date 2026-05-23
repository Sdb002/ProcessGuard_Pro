# ⚙ ProcessGuard Pro v2.0

**Linux Process Monitor & Auto-Kill System**  
Built with Python 3 · Dear PyGui · psutil · SQLite

---

## 🆕 What's New in v2.0

| Feature | v1 | v2 |
|---|---|---|
| Thread-safe UI updates | ✗ (race conditions) | ✅ Queue-based |
| CPU % measurement | Slow (0.05s per process) | ✅ Fast (interval=None, pre-warmed) |
| Alert thresholds | Hardcoded constants | ✅ Configurable sliders in Settings tab |
| Disk alert | Shown but never fired | ✅ Full alert + log |
| Auto-kill rules | Shell script only | ✅ GUI rule builder + duration tracking |
| Process table cap | 60 rows hardcoded | ✅ Paginated (200+ rows) |
| Whitelist | Flat string list | ✅ Regex/glob patterns via config |
| Per-process history | ✗ | ✅ 60-tick CPU/MEM sparklines in popup |
| History & reports | Single-snapshot HTML | ✅ SQLite trend data + 24h sparklines |
| Alert log | File only | ✅ Live in-app viewer tab |
| Network stats | ✗ | ✅ Total net sent/recv in status bar |
| Swap stats | ✗ | ✅ Swap bar in header |
| RSS memory column | ✗ | ✅ Per-process RSS MB column |
| Tray icon | ✗ | ✅ pystray (optional) |
| Docker image | ✗ | ✅ Full self-contained Dockerfile |

---

## 🚀 Quick Start

### Option A — Native (recommended)

**Step 1:** Install dependencies (once only)
```bash
bash scripts/install.sh
```

**Step 2:** Run
```bash
bash scripts/run.sh
```

Or in VSCode: press **`Ctrl+Shift+B`**

---

### Option B — Docker (self-contained, all deps baked in)

**Build the image:**
```bash
bash build_image.sh
```

**Build + run in one step:**
```bash
bash build_image.sh --run
```

**Manual docker run:**
```bash
xhost +local:docker
docker run --rm -it \
  --pid=host \
  --network=host \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/config.json:/app/config.json \
  processguard-pro:latest
```

> **`--pid=host`** is required for psutil to see the host's process list.  
> Without it, only container processes are visible.

---

## 📁 File Structure

```
processguard_pro/
├── main.py                ← GUI entry point (tabs, thread-safe queue)
├── config.py              ← JSON config manager (thresholds, whitelist, rules)
├── process_scanner.py     ← psutil data layer + per-process history rings
├── kill_manager.py        ← kill/suspend/resume/nice with regex whitelist
├── alert_engine.py        ← CPU/RAM/Disk alerts, JSONL log, cooldown
├── autokill_engine.py     ← Rule-based auto-kill with duration tracking
├── reporter.py            ← SQLite history + HTML reports with sparklines
├── config.json            ← Auto-created on first run, edit or use Settings tab
├── requirements.txt       ← Python deps
├── Dockerfile             ← Self-contained image (Python 3.11 + all libs)
├── docker-compose.yml     ← Compose config for easy container launch
├── build_image.sh         ← One-click Docker build/run/push script
│
├── scripts/
│   ├── install.sh         ← Full installer (Python, venv, apt packages)
│   ├── run.sh             ← One-click launcher
│   ├── monitor.sh         ← Cron scanner (reads thresholds from config.json)
│   └── kill_engine.sh     ← Cron auto-killer (reads rules from config.json)
│
├── logs/
│   ├── alerts.log         ← Human-readable alert log
│   ├── alerts.jsonl       ← Machine-readable alert log (for in-app viewer)
│   ├── autokill.log       ← Auto-kill event log
│   ├── kill.log           ← Manual kill/suspend/resume log
│   └── history.db         ← SQLite stats history (7-day retention)
│
├── reports/               ← HTML reports saved here
│
└── .vscode/
    ├── tasks.json         ← Ctrl+Shift+B = Run; also Docker build tasks
    ├── launch.json        ← F5 debug config
    ├── settings.json      ← Python interpreter path
    └── extensions.json    ← Recommended extensions
```

---

## 🖥️ UI Tabs

### 📊 Monitor Tab
- Live CPU/RAM/DISK/SWAP progress bars
- 60-second CPU and RAM sparkline graphs
- Sortable, filterable process table (paginated, up to 200+ rows)
- Columns: PID · Name · CPU% · MEM% · RSS MB · Status · User · ⚠Rule timer · Actions
- **Select** → highlight a process for Kill/Suspend/Resume
- **Details** → popup with per-process 60-tick CPU/MEM sparklines + actions
- Page navigation (◀ Prev / Next ▶)

### 🤖 Auto-Kill Rules Tab
- Add rules by regex pattern + CPU threshold + MEM threshold + duration
- Duration tracking: a process must *continuously* exceed the threshold for N seconds before being killed (prevents false positives on momentary spikes)
- Enable/disable/remove rules live
- Rule violation timers shown as `⚠30s` column in the Monitor table

### 🔔 Alert Log Tab
- Live scrollable list of all alerts with timestamps
- Refresh button to reload; Clear button to purge
- Alerts for CPU, RAM, and Disk (all three now active)

### ⚙ Settings Tab
- Sliders for CPU/RAM/Disk alert thresholds and cooldown period
- Slider for refresh interval (0.5s–10s)
- Max table rows control
- Multi-line whitelist editor (one entry per line, supports regex)
- Save / Reset to defaults

---

## ⌨️ VSCode Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Shift+B` | **Run ProcessGuard Pro** |
| `F5` | Run with debugger |
| `Ctrl+Shift+P` → Run Task | See all tasks (Install, Docker Build, etc.) |

---

## 🔁 Cron Automation

```bash
crontab -e
```

Add:
```
*/5  * * * *  /bin/bash /home/YOUR_USER/processguard_pro/scripts/monitor.sh
*/10 * * * *  /bin/bash /home/YOUR_USER/processguard_pro/scripts/kill_engine.sh
```

Both scripts now read thresholds and rules from `config.json` automatically.

---

## ❗ Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | Run `bash scripts/install.sh` |
| Access denied on kill | Run: `sudo python3 main.py` |
| GUI won't open | Need a graphical desktop (X11/Wayland). Not plain SSH. |
| Docker: no processes visible | Add `--pid=host` to docker run |
| Docker: GUI doesn't appear | Run `xhost +local:docker` first, then `bash build_image.sh --run` |
| Notifications not showing | `sudo apt install libnotify-bin` |
| `libGL.so.1` missing | `sudo apt install libgl1-mesa-glx` |
| pystray tray icon missing | `pip install pystray Pillow` (optional — app works without it) |

---

## ⚠️ Permissions Note

For killing processes owned by other users you need root:
```bash
sudo python3 main.py
# or
sudo bash scripts/run.sh
```

Auto-kill rules and the manual kill button will silently fail (with an error in the status bar) on processes owned by other users unless running as root.
# ProcessGuard_Pro
