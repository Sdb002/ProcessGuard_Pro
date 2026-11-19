"""Every test gets its own config file, alert log and history database, so
nothing touches the real config.json / logs/ next to the code."""
import copy
import subprocess
import sys

import pytest

import alert_engine
import autokill_engine
import config
import reporter


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config, "_cfg", copy.deepcopy(config.DEFAULTS))
    monkeypatch.setattr(alert_engine, "_JSONL_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setattr(alert_engine, "_last", {"cpu": 0.0, "ram": 0.0, "disk": 0.0})
    monkeypatch.setattr(alert_engine, "_notify", lambda title, msg: None)
    monkeypatch.setattr(reporter, "DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setattr(reporter, "_last_prune", 0.0)
    autokill_engine._violation_start.clear()
    yield
    autokill_engine._violation_start.clear()


@pytest.fixture
def sleeper():
    """A real, harmless child process (named after the Python binary)."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield proc
    if proc.poll() is None:
        proc.kill()
    proc.wait()


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(autokill_engine.time, "time", fake)
    return fake
