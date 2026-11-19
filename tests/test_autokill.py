import pytest

import autokill_engine
import config
import kill_manager


@pytest.fixture
def kills(monkeypatch):
    """Record kill requests instead of killing anything."""
    calls = []

    def fake_kill(pid, graceful=True):
        calls.append(pid)
        return True, "killed"

    monkeypatch.setattr(kill_manager, "kill_process", fake_kill)
    return calls


def proc(pid=4242, name="stress-ng", cpu=0.0, mem=0.0):
    return {"pid": pid, "name": name, "cpu_percent": cpu, "memory_percent": mem}


def test_kills_only_after_threshold_held_for_duration(clock, kills):
    config.add_autokill_rule("stress", 80.0, 0.0, 10)
    hot = [proc(cpu=95.0)]
    autokill_engine.check_processes(hot)        # starts the timer
    clock.advance(9)
    autokill_engine.check_processes(hot)
    assert kills == []                          # 9 s < 10 s
    clock.advance(1)
    autokill_engine.check_processes(hot)
    assert kills == [4242]


def test_dropping_below_threshold_resets_the_timer(clock, kills):
    config.add_autokill_rule("stress", 80.0, 0.0, 10)
    autokill_engine.check_processes([proc(cpu=95.0)])
    clock.advance(8)
    autokill_engine.check_processes([proc(cpu=10.0)])   # cooled down
    clock.advance(8)
    autokill_engine.check_processes([proc(cpu=95.0)])   # timer restarts here
    clock.advance(8)
    autokill_engine.check_processes([proc(cpu=95.0)])
    assert kills == []


def test_memory_threshold_and_case_insensitive_regex(clock, kills):
    config.add_autokill_rule("^chrom(e|ium)$", 0.0, 50.0, 0)
    autokill_engine.check_processes([proc(1, "Chromium", mem=60.0), proc(2, "chromedriver", mem=60.0)])
    clock.advance(0.1)
    autokill_engine.check_processes([proc(1, "Chromium", mem=60.0), proc(2, "chromedriver", mem=60.0)])
    assert kills == [1]


def test_disabled_rules_whitelist_and_bad_regex_are_skipped(clock, kills):
    config.add_autokill_rule("stress", 1.0, 0.0, 0)
    config.toggle_autokill_rule(0)                       # disabled
    config.add_autokill_rule("([", 1.0, 0.0, 0)          # invalid regex
    config.add_autokill_rule(".*", 1.0, 0.0, 0)          # matches everything...
    procs = [proc(1, "stress-ng", cpu=99), proc(2, "systemd", cpu=99)]
    for _ in range(2):
        autokill_engine.check_processes(procs)
        clock.advance(1)
    assert kills == [1]                                  # ...except whitelisted systemd


def test_flash_worker_is_no_longer_protected_by_sh(clock, kills):
    config.add_autokill_rule("flash", 50.0, 0.0, 0)
    for _ in range(2):
        autokill_engine.check_processes([proc(7, "flash_worker", cpu=99)])
        clock.advance(1)
    assert kills == [7]


def test_timers_for_exited_processes_are_dropped(clock, kills):
    config.add_autokill_rule("stress", 80.0, 0.0, 10)
    autokill_engine.check_processes([proc(cpu=95.0)])
    assert 4242 in autokill_engine.get_violation_timers([])
    autokill_engine.check_processes([proc(pid=1, name="other")])
    assert 4242 not in autokill_engine.get_violation_timers([])
