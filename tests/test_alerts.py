import alert_engine
import config


def stats(cpu=10.0, ram=10.0, disk=10.0):
    return {"cpu": cpu, "ram": ram, "disk": disk, "ram_used_gb": 1, "ram_total_gb": 8, "disk_free_gb": 50}


def test_alert_fires_above_threshold_and_is_logged():
    seen = []
    alert_engine.set_ui_callback(lambda key, value, msg: seen.append(key))
    try:
        alert_engine.check_and_alert(stats(cpu=99.0, disk=95.0))
    finally:
        alert_engine.set_ui_callback(None)
    assert seen == ["cpu", "disk"]
    assert [a["key"] for a in alert_engine.get_recent_alerts()] == ["cpu", "disk"]


def test_cooldown_suppresses_repeats():
    config.set("alert_cooldown_sec", 3600)
    alert_engine.check_and_alert(stats(ram=99.0))
    alert_engine.check_and_alert(stats(ram=99.0))
    assert len(alert_engine.get_recent_alerts()) == 1


def test_below_threshold_is_quiet_and_clear_empties_the_log():
    alert_engine.check_and_alert(stats())
    assert alert_engine.get_recent_alerts() == []
    alert_engine.check_and_alert(stats(cpu=99.0))
    alert_engine.clear_alerts()
    assert alert_engine.get_recent_alerts() == []
