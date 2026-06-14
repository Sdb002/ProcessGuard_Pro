"""
ProcessGuard Pro — main.py  (Upgraded)
──────────────────────────────────────
Features:
  • Thread-safe UI updates via a deque queue
  • Fixed cpu_percent measurement (interval=None, pre-warmed)
  • Tabs: Monitor | Auto-Kill Rules | Alert Log | Settings
  • Per-process popup with CPU/MEM sparklines
  • Configurable thresholds + whitelist editor
  • Auto-kill rules builder UI
  • Alert log viewer (live, clearable)
  • SQLite history logging via reporter.log_stats()
  • Tray icon (pystray, optional)
  • Network + Swap stats
  • Paginated process table (no 60-row cap)
"""

import dearpygui.dearpygui as dpg
import threading
import time
import os
import sys
import collections
import datetime

sys.path.insert(0, os.path.dirname(__file__))

import config
import psutil
from process_scanner import get_all_processes, get_system_stats, get_process_history
from kill_manager     import kill_process, suspend_process, resume_process, nice_process
from alert_engine     import check_and_alert, get_recent_alerts, clear_alerts, set_ui_callback
from autokill_engine  import check_processes, get_violation_timers, set_ui_callback as set_ak_callback
from reporter         import generate_report, log_stats

# ── Global state ───────────────────────────────────────────────────────
selected_pid   = None
running        = True
cpu_history    = collections.deque([0.0] * 60, maxlen=60)
ram_history    = collections.deque([0.0] * 60, maxlen=60)
_ui_queue      = collections.deque()          # thread-safe UI update queue
_page_offset   = 0
_PAGE_SIZE     = 60
_last_procs    = []
_popup_pid     = None

# Pre-warm psutil CPU counters (must happen before first interval=None call)
psutil.cpu_percent(interval=None)
for _p in psutil.process_iter():
    try: _p.cpu_percent(interval=None)
    except Exception: pass


# ── Thread-safe UI queue ───────────────────────────────────────────────

def queue_ui(fn, *args):
    """Queue a UI update function to be run on the main thread."""
    _ui_queue.append((fn, args))


def flush_ui_queue():
    """Drain the queue — called from dpg render loop via set_frame_callback."""
    while _ui_queue:
        try:
            fn, args = _ui_queue.popleft()
            fn(*args)
        except Exception as e:
            print(f"[UI queue] {e}")


# ── Status helpers ────────────────────────────────────────────────────

def set_status(msg: str):
    queue_ui(_set_status_direct, msg)

def _set_status_direct(msg):
    if dpg.does_item_exist("status_text"):
        dpg.set_value("status_text", msg)


# ── Process action callbacks ──────────────────────────────────────────

def on_kill():
    global selected_pid
    if not selected_pid:
        set_status("⚠  Select a process first (click 'Select' in the table)"); return
    ok, msg = kill_process(selected_pid)
    set_status(("✓  " if ok else "✗  ") + msg)
    selected_pid = None

def on_suspend():
    global selected_pid
    if not selected_pid:
        set_status("⚠  Select a process first"); return
    ok, msg = suspend_process(selected_pid)
    set_status(("✓  " if ok else "✗  ") + msg)

def on_resume():
    global selected_pid
    if not selected_pid:
        set_status("⚠  Select a process first"); return
    ok, msg = resume_process(selected_pid)
    set_status(("✓  " if ok else "✗  ") + msg)

def on_report():
    set_status("⏳  Generating report…")
    def _gen():
        path = generate_report()
        set_status(f"✓  Report saved → {path}")
    threading.Thread(target=_gen, daemon=True).start()

def on_select(sender, app_data, user_data):
    global selected_pid
    selected_pid = user_data
    set_status(f"Selected PID {selected_pid}  — use Kill / Suspend / Resume / Details buttons")

def on_details(sender, app_data, user_data):
    _open_process_popup(user_data)

def on_page_prev():
    global _page_offset
    _page_offset = max(0, _page_offset - _PAGE_SIZE)
    _rebuild_table(_last_procs)

def on_page_next():
    global _page_offset, _last_procs
    max_off = max(0, (len(_last_procs) - 1) // _PAGE_SIZE * _PAGE_SIZE)
    _page_offset = min(max_off, _page_offset + _PAGE_SIZE)
    _rebuild_table(_last_procs)


# ── Per-process popup ─────────────────────────────────────────────────

def _open_process_popup(pid: int):
    global _popup_pid
    _popup_pid = pid
    if dpg.does_item_exist("proc_popup"):
        dpg.delete_item("proc_popup")

    try:
        p    = psutil.Process(pid)
        name = p.name()
        cpu_h, mem_h = get_process_history(pid)
    except Exception:
        set_status(f"✗  PID {pid} no longer exists."); return

    with dpg.window(
        label=f"Process Details — {name} (PID {pid})",
        tag="proc_popup", modal=True,
        width=520, height=380,
        pos=[210, 180],
        on_close=lambda: dpg.delete_item("proc_popup"),
    ):
        dpg.add_text(f"  {name}", color=(0,255,140))
        dpg.add_text(f"  PID: {pid}  |  Status: {p.status() if p.is_running() else 'gone'}",
                     color=(80,120,100))
        try:
            mi = p.memory_info()
            dpg.add_text(f"  RSS: {mi.rss/1_048_576:.1f} MB  |  VMS: {mi.vms/1_048_576:.1f} MB",
                         color=(80,120,100))
        except Exception: pass
        dpg.add_separator(); dpg.add_spacer(height=6)

        with dpg.plot(label="CPU % — last 60 ticks", height=110, width=490):
            dpg.add_plot_axis(dpg.mvXAxis, no_tick_labels=True)
            dpg.set_axis_limits(dpg.last_item(), 0, 60)
            ax = dpg.add_plot_axis(dpg.mvYAxis)
            dpg.set_axis_limits(ax, 0, 100)
            dpg.add_line_series(list(range(60)), cpu_h, parent=ax, label="CPU%")

        dpg.add_spacer(height=6)

        with dpg.plot(label="MEM % — last 60 ticks", height=110, width=490):
            dpg.add_plot_axis(dpg.mvXAxis, no_tick_labels=True)
            dpg.set_axis_limits(dpg.last_item(), 0, 60)
            ax2 = dpg.add_plot_axis(dpg.mvYAxis)
            dpg.set_axis_limits(ax2, 0, 100)
            dpg.add_line_series(list(range(60)), mem_h, parent=ax2, label="MEM%")

        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Kill",    callback=lambda: (kill_process(pid), dpg.delete_item("proc_popup"), set_status(f"✓ Killed PID {pid}")), width=100)
            dpg.add_button(label="Suspend", callback=lambda: (suspend_process(pid), set_status(f"✓ Suspended PID {pid}")), width=100)
            dpg.add_button(label="Resume",  callback=lambda: (resume_process(pid),  set_status(f"✓ Resumed PID {pid}")),  width=100)
            dpg.add_button(label="Close",   callback=lambda: dpg.delete_item("proc_popup"), width=100)


# ── Table rebuild (diff-free full rebuild, uses slot deletion) ─────────

def _rebuild_table(procs: list[dict]):
    global _last_procs
    _last_procs = procs
    if not dpg.does_item_exist("proc_table"):
        return

    filt    = dpg.get_value("filter_box").lower() if dpg.does_item_exist("filter_box") else ""
    sort_by = dpg.get_value("sort_combo")         if dpg.does_item_exist("sort_combo")  else "CPU%"

    filtered = [p for p in procs if filt in p["name"].lower()] if filt else procs

    if sort_by == "MEM%":
        filtered = sorted(filtered, key=lambda x: x["memory_percent"], reverse=True)
    elif sort_by == "PID":
        filtered = sorted(filtered, key=lambda x: x["pid"])
    elif sort_by == "Name":
        filtered = sorted(filtered, key=lambda x: x["name"].lower())
    # default: CPU% — already sorted from scanner

    page_procs = filtered[_page_offset: _page_offset + _PAGE_SIZE]

    # Update pagination label
    total = len(filtered)
    start = _page_offset + 1
    end   = min(_page_offset + _PAGE_SIZE, total)
    if dpg.does_item_exist("page_label"):
        dpg.set_value("page_label", f"Showing {start}–{end} of {total}  (page {_page_offset//_PAGE_SIZE+1})")

    dpg.delete_item("proc_table", children_only=True, slot=1)

    violations = get_violation_timers(procs)

    for p in page_procs:
        cpu_v = p["cpu_percent"]
        mem_v = p["memory_percent"]
        c_col = (255, 70, 70)   if cpu_v > 70 else ((255,180, 0) if cpu_v > 40 else (0, 210,130))
        m_col = (255,180,  0)   if mem_v > 50 else (170,200,185)
        v_sec = violations.get(p["pid"], {})
        viol_str = f"⚠{max(v_sec.values()):.0f}s" if v_sec else ""

        with dpg.table_row(parent="proc_table"):
            dpg.add_text(str(p["pid"]),                color=(100,130,115))
            dpg.add_text(p["name"][:30])
            dpg.add_text(f"{cpu_v:>6.1f}",             color=c_col)
            dpg.add_text(f"{mem_v:>5.1f}",             color=m_col)
            dpg.add_text(f"{p.get('rss_mb',0):>7.1f}", color=(130,160,145))
            dpg.add_text(p["status"][:10],             color=(90,130,110))
            dpg.add_text((p["username"] or "")[:16],   color=(70,100, 85))
            dpg.add_text(viol_str,                     color=(255,100, 0))
            with dpg.group(horizontal=True):
                dpg.add_button(label="Sel",     small=True, callback=on_select,  user_data=p["pid"])
                dpg.add_spacer(width=2)
                dpg.add_button(label="Details", small=True, callback=on_details, user_data=p["pid"])


# ── Settings tab callbacks ────────────────────────────────────────────

def on_save_settings():
    config.set("cpu_alert_threshold",  dpg.get_value("set_cpu_thresh"))
    config.set("ram_alert_threshold",  dpg.get_value("set_ram_thresh"))
    config.set("disk_alert_threshold", dpg.get_value("set_disk_thresh"))
    config.set("alert_cooldown_sec",   dpg.get_value("set_cooldown"))
    config.set("refresh_interval_sec", dpg.get_value("set_refresh"))
    config.set("max_table_rows",       int(dpg.get_value("set_max_rows")))
    raw_wl = dpg.get_value("set_whitelist")
    config.set("whitelist", [w.strip() for w in raw_wl.splitlines() if w.strip()])
    set_status("✓  Settings saved to config.json")

def on_reset_settings():
    import config as _c
    _c._cfg = dict(_c.DEFAULTS)
    _c.save()
    _load_settings_values()
    set_status("✓  Settings reset to defaults")

def _load_settings_values():
    if dpg.does_item_exist("set_cpu_thresh"):
        dpg.set_value("set_cpu_thresh",  config.get("cpu_alert_threshold"))
        dpg.set_value("set_ram_thresh",  config.get("ram_alert_threshold"))
        dpg.set_value("set_disk_thresh", config.get("disk_alert_threshold"))
        dpg.set_value("set_cooldown",    config.get("alert_cooldown_sec"))
        dpg.set_value("set_refresh",     config.get("refresh_interval_sec"))
        dpg.set_value("set_max_rows",    float(config.get("max_table_rows") or 200))
        dpg.set_value("set_whitelist",   "\n".join(config.get("whitelist") or []))


# ── Auto-kill rules callbacks ─────────────────────────────────────────

def on_add_rule():
    pattern  = dpg.get_value("ak_pattern").strip()
    cpu_t    = dpg.get_value("ak_cpu")
    mem_t    = dpg.get_value("ak_mem")
    dur      = int(dpg.get_value("ak_duration"))
    if not pattern:
        set_status("⚠  Enter a process name pattern first"); return
    config.add_autokill_rule(pattern, cpu_t, mem_t, dur)
    _refresh_rules_table()
    set_status(f"✓  Auto-kill rule added: '{pattern}'  CPU>{cpu_t}%  MEM>{mem_t}%  for {dur}s")

def on_remove_rule(sender, app_data, user_data):
    config.remove_autokill_rule(user_data)
    _refresh_rules_table()
    set_status(f"✓  Rule #{user_data+1} removed")

def on_toggle_rule(sender, app_data, user_data):
    config.toggle_autokill_rule(user_data)
    _refresh_rules_table()
    rules = config.get("autokill_rules") or []
    if 0 <= user_data < len(rules):
        state = "enabled" if rules[user_data].get("enabled", True) else "disabled"
        set_status(f"✓  Rule #{user_data+1} {state}")

def _refresh_rules_table():
    if not dpg.does_item_exist("rules_table"):
        return
    dpg.delete_item("rules_table", children_only=True, slot=1)
    rules = config.get("autokill_rules") or []
    if not rules:
        with dpg.table_row(parent="rules_table"):
            dpg.add_text("No rules defined yet.", color=(80,110,95))
            for _ in range(5): dpg.add_text("")
        return
    for i, r in enumerate(rules):
        enabled = r.get("enabled", True)
        col     = (0,210,130) if enabled else (100,100,100)
        with dpg.table_row(parent="rules_table"):
            dpg.add_text(r.get("name_pattern",""),    color=col)
            dpg.add_text(f"{r.get('cpu_thresh',0):.0f}%",  color=col)
            dpg.add_text(f"{r.get('mem_thresh',0):.0f}%",  color=col)
            dpg.add_text(f"{r.get('duration_sec',30)}s",   color=col)
            with dpg.group(horizontal=True):
                lbl = "Disable" if enabled else "Enable"
                dpg.add_button(label=lbl,    small=True, callback=on_toggle_rule, user_data=i)
                dpg.add_spacer(width=4)
                dpg.add_button(label="Remove", small=True, callback=on_remove_rule, user_data=i)


# ── Alert log callbacks ───────────────────────────────────────────────

def on_clear_alerts():
    clear_alerts()
    _refresh_alert_log()
    set_status("✓  Alert log cleared")

def _refresh_alert_log():
    if not dpg.does_item_exist("alert_log_table"):
        return
    dpg.delete_item("alert_log_table", children_only=True, slot=1)
    alerts = get_recent_alerts(100)
    if not alerts:
        with dpg.table_row(parent="alert_log_table"):
            dpg.add_text("No alerts recorded.", color=(80,110,95))
            dpg.add_text(""); dpg.add_text("")
        return
    for a in reversed(alerts):
        ts  = datetime.datetime.fromtimestamp(a["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        col = (255, 80, 80) if a["key"]=="cpu" else ((100,180,255) if a["key"]=="ram" else (255,200,0))
        with dpg.table_row(parent="alert_log_table"):
            dpg.add_text(ts,              color=(80,110,95))
            dpg.add_text(a["label"],      color=col)
            dpg.add_text(a.get("msg",""), color=(160,190,175))

# Alert badge callback
def _on_alert(key, value, msg):
    queue_ui(_set_status_direct, f"🔔 ALERT — {msg}")

set_ui_callback(_on_alert)
set_ak_callback(lambda pid, name, ok, msg, rule:
    queue_ui(_set_status_direct, f"🤖 AUTO-KILL: {msg}"))


# ── Theme ─────────────────────────────────────────────────────────────

def _apply_theme():
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,        ( 8, 12, 10))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,         (12, 18, 14))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,         (18, 28, 22))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,  (24, 38, 30))
            dpg.add_theme_color(dpg.mvThemeCol_Button,          ( 0,140, 80))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,   ( 0,180,100))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,    ( 0,110, 60))
            dpg.add_theme_color(dpg.mvThemeCol_Header,          ( 0, 80, 50,160))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,   ( 0,120, 70,200))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,   ( 0, 90, 55))
            dpg.add_theme_color(dpg.mvThemeCol_Text,            (190,220,205))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight,( 25, 45, 35))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBg,      (  8, 14, 11))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt,   ( 12, 20, 16))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,     (  8, 12, 10))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,         ( 12, 18, 14))
            dpg.add_theme_color(dpg.mvThemeCol_Tab,             ( 15, 30, 22))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered,      (  0,140, 80))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive,       (  0,110, 65))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,      (  0,180,100))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive,(  0,220,130))
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  6)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   4)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding,     4)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     8, 6)
    dpg.bind_theme(t)


# ── UI Builder ────────────────────────────────────────────────────────

def build_ui():
    with dpg.window(tag="win", label="ProcessGuard Pro", no_close=True, no_move=True, no_resize=True):

        dpg.add_text("⚙  ProcessGuard Pro", color=(0,255,140))
        dpg.add_text("Linux Process Monitor & Auto-Kill System  v2.0",  color=(50,90,70))
        dpg.add_separator(); dpg.add_spacer(height=4)

        # ── Stats row ──
        with dpg.group(horizontal=True):
            for tag, label in [("cpu_bar","CPU"), ("ram_bar","RAM"), ("disk_bar","DISK"), ("swap_bar","SWAP")]:
                dpg.add_text(f"{label}:", color=(0,200,120))
                dpg.add_progress_bar(tag=tag, default_value=0.0, width=148, height=18, overlay="0%")
                dpg.add_spacer(width=10)
            dpg.add_text("", tag="uptime_lbl",   color=(50,90,70))
            dpg.add_spacer(width=12)
            dpg.add_text("", tag="proccount_lbl", color=(50,90,70))

        dpg.add_spacer(height=6)

        # ── Graphs ──
        with dpg.group(horizontal=True):
            for tag_x, tag_y, tag_s, label in [
                ("cx","cy","cpu_series","CPU % — last 60 s"),
                ("rx","ry","ram_series","RAM % — last 60 s"),
            ]:
                with dpg.plot(label=label, height=110, width=460):
                    dpg.add_plot_axis(dpg.mvXAxis, tag=tag_x, no_tick_labels=True)
                    dpg.set_axis_limits(tag_x, 0, 60)
                    dpg.add_plot_axis(dpg.mvYAxis, tag=tag_y, label="%")
                    dpg.set_axis_limits(tag_y, 0, 100)
                    dpg.add_line_series(list(range(60)), [0.0]*60, tag=tag_s, parent=tag_y)
                dpg.add_spacer(width=8)

        dpg.add_spacer(height=6)
        dpg.add_separator()
        dpg.add_spacer(height=4)

        # ── Tab bar ──
        with dpg.tab_bar():

            # ── Tab 1: Monitor ──────────────────────────────────────
            with dpg.tab(label="  📊 Monitor  "):
                dpg.add_spacer(height=6)

                # Action bar
                with dpg.group(horizontal=True):
                    dpg.add_button(label="🔴 Kill",     callback=on_kill,    width=110, height=30)
                    dpg.add_spacer(width=4)
                    dpg.add_button(label="⏸ Suspend",  callback=on_suspend, width=110, height=30)
                    dpg.add_spacer(width=4)
                    dpg.add_button(label="▶ Resume",    callback=on_resume,  width=110, height=30)
                    dpg.add_spacer(width=4)
                    dpg.add_button(label="📋 Report",   callback=on_report,  width=120, height=30)
                    dpg.add_spacer(width=16)
                    dpg.add_text("Filter:", color=(60,100,80))
                    dpg.add_input_text(tag="filter_box", hint="search by name…", width=190)
                    dpg.add_spacer(width=12)
                    dpg.add_text("Sort:", color=(60,100,80))
                    dpg.add_combo(["CPU%","MEM%","PID","Name"], tag="sort_combo",
                                  default_value="CPU%", width=90)

                dpg.add_spacer(height=6)

                # Process table
                with dpg.table(
                    tag="proc_table", header_row=True, resizable=True,
                    scrollY=True, height=310,
                    borders_innerH=True, borders_outerH=True,
                    borders_innerV=True, borders_outerV=True,
                    row_background=True,
                    policy=dpg.mvTable_SizingStretchProp,
                ):
                    dpg.add_table_column(label="PID",      width_fixed=True, init_width_or_weight=68)
                    dpg.add_table_column(label="Name",     init_width_or_weight=190)
                    dpg.add_table_column(label="CPU%",     init_width_or_weight=72)
                    dpg.add_table_column(label="MEM%",     init_width_or_weight=68)
                    dpg.add_table_column(label="RSS MB",   init_width_or_weight=78)
                    dpg.add_table_column(label="Status",   init_width_or_weight=80)
                    dpg.add_table_column(label="User",     init_width_or_weight=100)
                    dpg.add_table_column(label="⚠Rule",   width_fixed=True, init_width_or_weight=60)
                    dpg.add_table_column(label="Actions",  width_fixed=True, init_width_or_weight=118)

                # Pagination bar
                dpg.add_spacer(height=4)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="◀ Prev", callback=on_page_prev, width=80, height=24)
                    dpg.add_spacer(width=8)
                    dpg.add_text("", tag="page_label", color=(70,110,90))
                    dpg.add_spacer(width=8)
                    dpg.add_button(label="Next ▶", callback=on_page_next, width=80, height=24)

            # ── Tab 2: Auto-Kill Rules ───────────────────────────────
            with dpg.tab(label="  🤖 Auto-Kill Rules  "):
                dpg.add_spacer(height=8)
                dpg.add_text("Define rules to automatically kill runaway processes.", color=(90,140,115))
                dpg.add_text("A process must exceed the threshold continuously for the duration before being killed.",
                             color=(60,95,80))
                dpg.add_spacer(height=10)

                # Add rule form
                with dpg.group(horizontal=True):
                    dpg.add_text("Process name pattern (regex):", color=(0,200,120))
                    dpg.add_input_text(tag="ak_pattern", hint="e.g. chrome|firefox", width=200)
                    dpg.add_spacer(width=12)
                    dpg.add_text("CPU >", color=(0,200,120))
                    dpg.add_slider_float(tag="ak_cpu", default_value=90.0,
                                         min_value=0, max_value=100, width=120)
                    dpg.add_text("%  MEM >", color=(0,200,120))
                    dpg.add_slider_float(tag="ak_mem", default_value=0.0,
                                         min_value=0, max_value=100, width=100)
                    dpg.add_text("%  For", color=(0,200,120))
                    dpg.add_slider_int(tag="ak_duration", default_value=30,
                                        min_value=5, max_value=300, width=90)
                    dpg.add_text("s", color=(0,200,120))
                    dpg.add_spacer(width=8)
                    dpg.add_button(label="+ Add Rule", callback=on_add_rule, width=110, height=28)

                dpg.add_spacer(height=10)
                dpg.add_separator()
                dpg.add_spacer(height=8)
                dpg.add_text("Active Rules:", color=(0,200,120))
                dpg.add_spacer(height=6)

                with dpg.table(
                    tag="rules_table", header_row=True,
                    borders_innerH=True, borders_outerH=True,
                    borders_innerV=True, borders_outerV=True,
                    row_background=True, height=260,
                    policy=dpg.mvTable_SizingStretchProp,
                ):
                    dpg.add_table_column(label="Pattern",   init_width_or_weight=200)
                    dpg.add_table_column(label="CPU Thresh", width_fixed=True, init_width_or_weight=90)
                    dpg.add_table_column(label="Mem Thresh", width_fixed=True, init_width_or_weight=90)
                    dpg.add_table_column(label="Duration",   width_fixed=True, init_width_or_weight=80)
                    dpg.add_table_column(label="Actions",    width_fixed=True, init_width_or_weight=160)

                _refresh_rules_table()

            # ── Tab 3: Alert Log ─────────────────────────────────────
            with dpg.tab(label="  🔔 Alert Log  "):
                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_text("Live alert log (last 100 entries)", color=(0,200,120))
                    dpg.add_spacer(width=20)
                    dpg.add_button(label="🔄 Refresh", width=100, height=26,
                                   callback=lambda: _refresh_alert_log())
                    dpg.add_spacer(width=8)
                    dpg.add_button(label="🗑 Clear",   width=90, height=26,
                                   callback=on_clear_alerts)
                dpg.add_spacer(height=8)

                with dpg.table(
                    tag="alert_log_table", header_row=True,
                    borders_innerH=True, borders_outerH=True,
                    borders_innerV=True, borders_outerV=True,
                    row_background=True, scrollY=True, height=420,
                    policy=dpg.mvTable_SizingStretchProp,
                ):
                    dpg.add_table_column(label="Timestamp",  init_width_or_weight=160)
                    dpg.add_table_column(label="Metric",     width_fixed=True, init_width_or_weight=70)
                    dpg.add_table_column(label="Message",    init_width_or_weight=400)

                _refresh_alert_log()

            # ── Tab 4: Settings ──────────────────────────────────────
            with dpg.tab(label="  ⚙ Settings  "):
                dpg.add_spacer(height=8)
                dpg.add_text("Alert Thresholds", color=(0,200,120))
                dpg.add_separator(); dpg.add_spacer(height=6)

                with dpg.group(horizontal=True):
                    dpg.add_text("CPU alert %:", color=(160,200,180))
                    dpg.add_slider_float(tag="set_cpu_thresh",
                                         default_value=config.get("cpu_alert_threshold"),
                                         min_value=10, max_value=100, width=220,
                                         format="%.0f%%")
                    dpg.add_spacer(width=24)
                    dpg.add_text("RAM alert %:", color=(160,200,180))
                    dpg.add_slider_float(tag="set_ram_thresh",
                                         default_value=config.get("ram_alert_threshold"),
                                         min_value=10, max_value=100, width=220,
                                         format="%.0f%%")

                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_text("Disk alert %:", color=(160,200,180))
                    dpg.add_slider_float(tag="set_disk_thresh",
                                         default_value=config.get("disk_alert_threshold"),
                                         min_value=10, max_value=100, width=220,
                                         format="%.0f%%")
                    dpg.add_spacer(width=24)
                    dpg.add_text("Alert cooldown (s):", color=(160,200,180))
                    dpg.add_slider_float(tag="set_cooldown",
                                         default_value=config.get("alert_cooldown_sec"),
                                         min_value=10, max_value=600, width=220,
                                         format="%.0fs")

                dpg.add_spacer(height=12)
                dpg.add_text("Monitoring", color=(0,200,120))
                dpg.add_separator(); dpg.add_spacer(height=6)

                with dpg.group(horizontal=True):
                    dpg.add_text("Refresh interval (s):", color=(160,200,180))
                    dpg.add_slider_float(tag="set_refresh",
                                         default_value=config.get("refresh_interval_sec"),
                                         min_value=0.5, max_value=10, width=220,
                                         format="%.1fs")
                    dpg.add_spacer(width=24)
                    dpg.add_text("Max table rows:", color=(160,200,180))
                    dpg.add_slider_float(tag="set_max_rows",
                                         default_value=float(config.get("max_table_rows") or 200),
                                         min_value=20, max_value=500, width=220,
                                         format="%.0f")

                dpg.add_spacer(height=12)
                dpg.add_text("Process Whitelist  (one entry per line, regex/name)", color=(0,200,120))
                dpg.add_separator(); dpg.add_spacer(height=4)
                dpg.add_input_text(tag="set_whitelist",
                                   default_value="\n".join(config.get("whitelist") or []),
                                   multiline=True, width=700, height=140)

                dpg.add_spacer(height=12)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="💾  Save Settings", callback=on_save_settings,
                                   width=160, height=32)
                    dpg.add_spacer(width=10)
                    dpg.add_button(label="↺  Reset Defaults", callback=on_reset_settings,
                                   width=150, height=32)

        dpg.add_spacer(height=4)
        dpg.add_separator()

        # Status bar
        with dpg.group(horizontal=True):
            dpg.add_text("●", color=(0,200,120))
            dpg.add_text("Ready — refreshing every 2 seconds", tag="status_text", color=(120,170,145))
            dpg.add_spacer(width=40)
            dpg.add_text("", tag="net_lbl", color=(50,90,70))


# ── Background refresh ────────────────────────────────────────────────

def refresh_loop():
    global running
    tick = 0
    while running:
        try:
            stats = get_system_stats()
            procs = get_all_processes()

            # Log history for reports
            log_stats(stats)

            interval  = config.get("refresh_interval_sec") or 2.0
            alert_int = max(1, int(120 / max(interval, 0.5)))

            def _update(s=stats, p=procs, t=tick, ai=alert_int):
                if not dpg.is_dearpygui_running():
                    return

                # Bars
                for tag, key in [("cpu_bar","cpu"),("ram_bar","ram"),
                                   ("disk_bar","disk"),("swap_bar","swap")]:
                    val = s.get(key, 0)
                    if dpg.does_item_exist(tag):
                        dpg.set_value(tag, val / 100.0)
                        dpg.configure_item(tag, overlay=f"{val:.1f}%")

                if dpg.does_item_exist("uptime_lbl"):
                    dpg.set_value("uptime_lbl",
                        f"Up: {s['uptime_str']}  |  {s['ram_used_gb']}/{s['ram_total_gb']} GB RAM")
                if dpg.does_item_exist("proccount_lbl"):
                    dpg.set_value("proccount_lbl", f"Procs: {s['proc_count']}")
                if dpg.does_item_exist("net_lbl"):
                    dpg.set_value("net_lbl",
                        f"↑ {s['net_sent_mb']} MB  ↓ {s['net_recv_mb']} MB  net total")

                # CPU history for graphs
                cpu_history.append(s["cpu"])
                ram_history.append(s["ram"])
                if dpg.does_item_exist("cpu_series"):
                    dpg.set_value("cpu_series", [list(range(60)), list(cpu_history)])
                if dpg.does_item_exist("ram_series"):
                    dpg.set_value("ram_series", [list(range(60)), list(ram_history)])

                # Table
                _rebuild_table(p)

                # Alerts every alert_int ticks
                if t % ai == 0:
                    check_and_alert(s)

                # Auto-kill check every tick
                check_processes(p)

            queue_ui(_update)
            tick += 1
        except Exception as e:
            print(f"[refresh_loop] {e}")

        time.sleep(config.get("refresh_interval_sec") or 2.0)


# ── Tray icon (optional) ──────────────────────────────────────────────

def _start_tray():
    try:
        import pystray
        from PIL import Image as PILImage, ImageDraw
        img  = PILImage.new("RGB", (64,64), (8,12,10))
        draw = ImageDraw.Draw(img)
        draw.ellipse([14,14,50,50], fill=(0,200,120))
        icon = pystray.Icon(
            "ProcessGuard Pro", img, "ProcessGuard Pro",
            menu=pystray.Menu(
                pystray.MenuItem("Show",  lambda: None),
                pystray.MenuItem("Quit",  lambda: os._exit(0)),
            )
        )
        icon.run_detached()
    except ImportError:
        pass   # pystray not installed — skip silently
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────

def main():
    global running

    dpg.create_context()
    _apply_theme()

    dpg.create_viewport(
        title="ProcessGuard Pro v2.0",
        width=980, height=870,
        resizable=True,
        small_icon="", large_icon="",
    )
    dpg.setup_dearpygui()
    build_ui()
    dpg.set_primary_window("win", True)

    # Frame callback for thread-safe queue flush
    dpg.set_frame_callback(1, flush_ui_queue)
    # Also flush every frame via render callback
    with dpg.item_handler_registry() as reg:
        pass
    # Use a simple per-frame loop approach
    def _frame_cb():
        flush_ui_queue()
        dpg.set_frame_callback(dpg.get_frame_count() + 1, _frame_cb)
    dpg.set_frame_callback(2, _frame_cb)

    # Start background thread
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    # Optional tray icon
    _start_tray()

    dpg.show_viewport()
    dpg.start_dearpygui()

    running = False
    dpg.destroy_context()


if __name__ == "__main__":
    main()
