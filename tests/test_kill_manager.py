import os

import psutil
import pytest

import config
import kill_manager


@pytest.mark.parametrize("name, protected", [
    ("sh", True),
    ("bash", True),
    ("SYSTEMD", True),                 # case-insensitive
    ("gnome-shell", True),             # glob: gnome-*
    ("kwin_wayland", True),            # glob: kwin*
    ("flash_worker", False),           # used to match "sh"
    ("refresh-daemon", False),
    ("crashpad_handler", False),
    ("vscode-helper", False),          # used to match "code"
    ("stress-ng", False),
])
def test_whitelist_matches_whole_names(name, protected):
    assert kill_manager._is_whitelisted(name) is protected


def test_whitelist_is_read_from_config():
    config.set("whitelist", ["my-db"])
    assert kill_manager._is_whitelisted("my-db")
    assert not kill_manager._is_whitelisted("bash")


def _allow_python():
    # the test child is a Python process; python3 is whitelisted by default
    config.set("whitelist", ["systemd"])


def test_suspend_resume_and_kill_a_real_process(sleeper):
    _allow_python()
    proc = psutil.Process(sleeper.pid)

    ok, msg = kill_manager.suspend_process(sleeper.pid)
    assert ok, msg
    assert proc.status() == psutil.STATUS_STOPPED

    ok, msg = kill_manager.resume_process(sleeper.pid)
    assert ok, msg
    assert proc.status() != psutil.STATUS_STOPPED

    ok, msg = kill_manager.kill_process(sleeper.pid, graceful=True)
    assert ok, msg
    assert sleeper.wait(timeout=5) is not None


def test_whitelisted_process_is_refused(sleeper):
    name = psutil.Process(sleeper.pid).name()
    config.set("whitelist", [name])
    ok, msg = kill_manager.kill_process(sleeper.pid)
    assert not ok and "whitelisted" in msg
    assert sleeper.poll() is None  # still running
    ok, _ = kill_manager.suspend_process(sleeper.pid)
    assert not ok


def test_missing_pid_is_reported_not_raised(sleeper):
    sleeper.kill(); sleeper.wait()
    for action in (kill_manager.kill_process, kill_manager.suspend_process, kill_manager.resume_process):
        ok, msg = action(sleeper.pid)
        assert not ok and str(sleeper.pid) in msg


def test_renice_clamps_to_valid_range(sleeper):
    _allow_python()
    ok, msg = kill_manager.nice_process(sleeper.pid, 99)
    assert ok, msg
    assert psutil.Process(sleeper.pid).nice() == 19
