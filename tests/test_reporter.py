import threading
import time

import reporter

TICK = {"cpu": 12.5, "ram": 40.0, "disk": 70.0, "proc_count": 321}


def test_stats_are_recorded_and_read_back():
    reporter.log_stats(TICK)
    rows = reporter.get_history(hours=1)
    assert len(rows) == 1
    assert rows[0][1:] == (12.5, 40.0, 70.0)


def test_rows_older_than_seven_days_are_pruned():
    conn = reporter._get_conn()
    conn.execute("INSERT INTO stats VALUES (?,?,?,?,?)", (time.time() - 8 * 86400, 1, 1, 1, 1))
    conn.commit(); conn.close()
    reporter.log_stats(TICK)   # first tick prunes (no prune has run yet)
    conn = reporter._get_conn()
    assert conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0] == 1
    conn.close()


def test_pruning_does_not_deadlock():
    # log_stats used to call _prune_old while holding the same lock
    worker = threading.Thread(target=reporter.log_stats, args=(TICK,), daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "log_stats deadlocked while pruning"


def test_sparkline_scales_to_the_box():
    svg = reporter._sparkline([0, 100], "#0f0", width=100, height=50)
    assert "0.0,50.0 100.0,0.0" in svg
    assert reporter._sparkline([5], "#0f0").startswith("<svg")
