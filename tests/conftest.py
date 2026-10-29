import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cc_sync import core
from cc_sync.paths import Paths


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory, monkeypatch):
    """不讀使用者的 git 設定（簽章、hooks、身分），讓測試在任何機器上行為一致。"""
    empty = tmp_path_factory.mktemp("gitcfg") / "config"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@dataclass
class FakeClaude:
    calls: list[tuple[str, ...]] = field(default_factory=list)
    fail: set[str] = field(default_factory=set)

    def __call__(self, *args: str) -> tuple[bool, str]:
        self.calls.append(args)
        return (args[1] not in self.fail), ""


@dataclass
class Machine:
    paths: Paths
    claude: FakeClaude
    os_name: str

    @property
    def root(self) -> Path:
        return self.paths.root

    def settings(self) -> dict:
        return json.loads(self.paths.settings.read_text(encoding="utf-8"))

    def set_settings(self, data: dict) -> None:
        self.paths.settings.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def edit_settings(self, fn) -> None:
        s = self.settings()
        fn(s)
        self.set_settings(s)

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def bootstrap(self, url: str) -> core.Result:
        return core.bootstrap(self.paths, url, self.claude, os_name=self.os_name)

    def sync(self, **kw) -> core.Result:
        return core.sync(self.paths, self.claude, os_name=self.os_name, **kw)


@pytest.fixture
def remote(tmp_path) -> str:
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return str(path)


@pytest.fixture
def machine(tmp_path):
    def make(name: str, settings: dict | None = None, os_name: str = "windows") -> Machine:
        root = tmp_path / name / ".claude"
        root.mkdir(parents=True)
        m = Machine(Paths(root), FakeClaude(), os_name)
        m.set_settings(settings or {})
        return m
    return make
