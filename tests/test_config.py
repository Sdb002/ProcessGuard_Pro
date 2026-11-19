import json

import config


def test_rules_persist_to_disk():
    config.add_autokill_rule("stress", 90.0, 0.0, 10)
    saved = json.load(open(config.CONFIG_PATH))
    assert saved["autokill_rules"] == [
        {"name_pattern": "stress", "cpu_thresh": 90.0, "mem_thresh": 0.0, "duration_sec": 10, "enabled": True}
    ]


def test_toggle_and_remove_rule():
    config.add_autokill_rule("a", 50, 0, 5)
    config.add_autokill_rule("b", 50, 0, 5)
    config.toggle_autokill_rule(0)
    assert [r["enabled"] for r in config.get("autokill_rules")] == [False, True]
    config.remove_autokill_rule(0)
    assert [r["name_pattern"] for r in config.get("autokill_rules")] == ["b"]
    config.remove_autokill_rule(99)  # out of range: ignored
    assert len(config.get("autokill_rules")) == 1


def test_adding_rules_never_changes_the_defaults():
    config.load()  # no file yet: starts from DEFAULTS
    config.add_autokill_rule("x", 10, 0, 1)
    assert config.DEFAULTS["autokill_rules"] == []


def test_reset_restores_defaults():
    config.add_autokill_rule("x", 10, 0, 1)
    config.set("cpu_alert_threshold", 42.0)
    config.reset()
    assert config.get("autokill_rules") == []
    assert config.get("cpu_alert_threshold") == config.DEFAULTS["cpu_alert_threshold"]
    assert json.load(open(config.CONFIG_PATH))["autokill_rules"] == []


def test_saved_file_overrides_defaults_and_keeps_new_keys(tmp_path):
    json.dump({"cpu_alert_threshold": 70.0}, open(config.CONFIG_PATH, "w"))
    config.load()
    assert config.get("cpu_alert_threshold") == 70.0
    assert config.get("ram_alert_threshold") == config.DEFAULTS["ram_alert_threshold"]


def test_corrupt_file_falls_back_to_defaults():
    open(config.CONFIG_PATH, "w").write("{not json")
    config.load()
    assert config.get("theme") == config.DEFAULTS["theme"]
