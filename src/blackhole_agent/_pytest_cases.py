"""Pytest plugin copied into a private shard directory by suite_shards."""

import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

import pytest


def pytest_configure(config):
    parallel = config.getoption("numprocesses", default=0) or config.getoption("dist", default="no") != "no"
    if parallel or hasattr(config, "workerinput"):
        if os.environ.get("_BLACKHOLE_CASE_DEADLINE"):
            raise pytest.UsageError("Blackhole case deadlines require serial pytest execution")
        return
    config.pluginmanager.register(_Cases(Path(__file__).resolve().parent))


class _Cases:
    def __init__(self, directory):
        self.directory = directory
        self.events = (directory / "events").open("a", encoding="ascii", buffering=1)
        self.positions = defaultdict(deque)
        self.current = None
        self.limit = float(os.environ.get("_BLACKHOLE_CASE_DEADLINE") or 0)
        self.deadline = 0.0

    def pytest_unconfigure(self):
        self.events.close()

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, config, items):
        yield  # Observe the final selection, including -k, marks and parametrization.
        collection = self.directory / "collection.json"
        names = [item.nodeid for item in items]
        if collection.exists():
            if names != json.loads(collection.read_bytes())["nodeids"]:
                raise pytest.UsageError("pytest collection changed during timeout recovery")
            recovery = json.loads((self.directory / "recovery.json").read_bytes())
            entered = set(recovery["entered"])
            if config.option.maxfail:
                config.option.maxfail -= recovery["failures"]
        else:
            collection.write_text(json.dumps({"nodeids": names, "maxfail": config.option.maxfail}), encoding="ascii")
            entered = set()
        for i, item in enumerate(items):
            if i not in entered:
                self.positions[item].append(i)
        if entered:
            config.hook.pytest_deselected(items=[item for i, item in enumerate(items) if i in entered])
            items[:] = [item for i, item in enumerate(items) if i not in entered]

    def record(self, event, value):
        print(json.dumps([self.current, event, value]), file=self.events)

    def next_phase(self, phase):
        now = time.monotonic()
        if self.limit and now >= self.deadline:
            # The old phase overran between parent polls. Leave it identifiable
            # and stop before entering another fixture, body or finalizer.
            self.record("expired", None)
            os._exit(124)
        self.record(phase, now)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_protocol(self, item):
        self.current = self.positions[item].popleft()
        started = time.monotonic()
        self.deadline = started + self.limit
        self.record("setup", started)
        yield
        self.next_phase("finished")
        self.current = None

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_call(self):
        self.next_phase("call")
        yield

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_teardown(self):
        self.next_phase("teardown")
        yield

    def pytest_runtest_logreport(self, report):
        if self.current is not None:
            self.record("result", (report.when, report.outcome, report.duration))
